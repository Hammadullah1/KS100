from copy import deepcopy
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from psx_pipeline.adapters import SourceBlocked, get_json, require
from psx_pipeline.calendar import ExchangeCalendar
from psx_pipeline.contracts import TARGETS, Forecast
from psx_pipeline.operations import backup, reserve_budget, restore
from psx_pipeline.pipeline import daily, mature
from psx_pipeline.publishing import empty_bundle, publish, rollback, verify_bundle
from psx_pipeline.storage import (
    Store,
    append_record,
    digest,
    forecast_key,
    lock,
    read_json,
    records,
)


def test_http200_error_page_is_failure():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, headers={"content-type": "text/html"}, text="<html>Denied</html>")
        )
    ) as client:
        with pytest.raises(ValueError, match="non-JSON"):
            get_json("https://example.invalid", {}, client=client)


def test_http_retry_is_bounded_and_no_credentials_logged():
    calls = []

    def handler(r):
        calls.append(r)
        return httpx.Response(429, headers={"Retry-After": "0"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="retry limit"):
            get_json("https://example.invalid", {"api_key": "PRIVATE"}, client=client, sleep=lambda x: None)
    assert len(calls) == 3


def test_live_collection_gate_is_closed():
    with pytest.raises(SourceBlocked):
        require("psx", ["collection"], live=True)
    with pytest.raises(SourceBlocked):
        require("eia", ["collection"], live=True)


def test_snapshot_vintages_and_tamper(tables, tmp_path):
    store = Store(tmp_path)
    identifier = store.save(tables, fixture=True)
    manifest, loaded = store.load()
    assert len(loaded["bars"]) == 70
    assert store.save(tables, fixture=True) == identifier
    with pytest.raises(ValueError, match="fixture"):
        Store(tmp_path / "real").save(tables)
    file = next((tmp_path / "snapshots" / identifier).rglob("*.parquet"))
    file.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="corrupt"):
        store.load()


def test_ledger_is_immutable_and_idempotent(tmp_path):
    with lock(tmp_path):
        assert append_record(tmp_path, "forecasts", "k", {"p_up": 0.6})
        assert not append_record(tmp_path, "forecasts", "k", {"p_up": 0.6})
        with pytest.raises(ValueError, match="immutable"):
            append_record(tmp_path, "forecasts", "k", {"p_up": 0.9})
    assert len(records(tmp_path, "forecasts")) == 1


def forecast_for(tables, horizon=5):
    c = ExchangeCalendar(tables["sessions"])
    ref = c.sessions[25]
    next_session = c.advance(ref.date, 1)
    target = c.advance(ref.date, horizon)
    bar = next(b for b in tables["bars"] if b["session"] == str(ref.date))
    return Forecast(
        instrument="TEST:INDEX:TR",
        target_definition=TARGETS["official_total_return"],
        return_basis="official_total_return",
        horizon=horizon,
        reference_session=ref.date,
        reference_close=bar["close"],
        cutoff=ref.update_due_at,
        issued_at=ref.update_due_at + timedelta(seconds=1),
        target_session=target.date,
        next_open_at=next_session.opens_at,
        expires_at=target.closes_at,
        update_due_at=next_session.update_due_at,
        p_up=0.6,
        p_not_up=0.4,
        signal="no_strong_signal",
        suppression_reason="fixture only",
        validation_status="research",
        model_version="test-model",
        feature_version="price-v1",
        snapshot="test-snapshot",
        policy="selective-v1",
        scorecard=None,
        fixture=True,
    )


def test_invalid_probabilities_models_and_backdating(tables):
    f = forecast_for(tables).model_dump(mode="json")
    for changes in [
        {"p_up": float("nan")},
        {"p_up": 1.1},
        {"p_not_up": 0.3},
        {"model_version": None},
        {"target_definition": TARGETS["official_price_return"]},
        {"signal": "up"},
        {"issued_at": f["next_open_at"]},
    ]:
        with pytest.raises(ValueError):
            Forecast.model_validate({**f, **changes})


def test_outcomes_append_mature_once_and_correct_separately(tables, tmp_path):
    c = ExchangeCalendar(tables["sessions"])
    f = forecast_for(tables).model_dump(mode="json")
    with lock(tmp_path):
        append_record(tmp_path, "forecasts", forecast_key(f), f)
    target = c.get(f["target_session"])
    assert mature(tmp_path, tables, target.closes_at) == 0
    assert mature(tmp_path, tables, target.update_due_at) == 1
    assert mature(tmp_path, tables, target.update_due_at) == 0
    changed = deepcopy(tables)
    bar = next(b for b in changed["bars"] if b["session"] == f["target_session"])
    correction = {
        **bar,
        "vintage": "v2",
        "close": bar["close"] * 1.001,
        "available_at": (target.update_due_at + timedelta(days=1)).isoformat(),
        "ingested_at": (target.update_due_at + timedelta(days=1)).isoformat(),
        "payload_hash": digest("correction"),
    }
    changed["bars"].append(correction)
    assert mature(tmp_path, changed, target.update_due_at + timedelta(days=2)) == 1
    assert len(records(tmp_path, "outcomes")) == 2
    assert any(o["correction_of"] for o in records(tmp_path, "outcomes"))
    assert records(tmp_path, "forecasts")[0] == f


def test_publication_integrity_and_rollback(tmp_path):
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    b = empty_bundle(now)
    first = publish(tmp_path, b)
    verify_bundle(tmp_path, first)
    pointer = read_json(tmp_path / "latest.json")
    bad = b.model_copy(update={"mode": "fixture"})
    with pytest.raises(ValueError, match="fixture"):
        publish(tmp_path, bad)
    assert read_json(tmp_path / "latest.json") == pointer
    second = publish(tmp_path, empty_bundle(now + timedelta(hours=1)))
    (tmp_path / "bundles" / second / "results.json").write_text("{}")
    with pytest.raises(ValueError, match="hash"):
        rollback(tmp_path, second)
    rollback(tmp_path, first)
    assert read_json(tmp_path / "latest.json") == pointer


def test_permission_and_private_payload_block_publication(tables, tmp_path):
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    b = empty_bundle(now)
    b.metrics = [{"password": "NEVER_PUBLISH"}]
    with pytest.raises(ValueError):
        publish(tmp_path, b, ["psx"])
    b = empty_bundle(now)
    b.sources = [{"secret": "NEVER_PUBLISH"}]
    with pytest.raises(ValueError, match="private"):
        publish(tmp_path, b)


def test_backup_restore_verified_snapshot(tables, tmp_path):
    source = tmp_path / "state"
    Store(source).save(tables, fixture=True)
    report = backup(source, tmp_path / "backup.zip")
    assert report["files"] > 0
    assert restore(tmp_path / "backup.zip", tmp_path / "restored")["verified"]
    assert Store(tmp_path / "restored").load()[0] == Store(source).load()[0]


def test_budget_cap_and_recovery_without_fake_success(tmp_path):
    assert reserve_budget(tmp_path, "one", "daily", 30)["reserved_minutes"] == 30
    assert reserve_budget(tmp_path, "one", "daily", 30)["reserved_minutes"] == 30
    with pytest.raises(ValueError, match="cap"):
        reserve_budget(tmp_path, "two", "daily", 30)
    result = daily(tmp_path)
    assert result["status"] == "blocked"
    assert not records(tmp_path, "forecasts")
