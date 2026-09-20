from datetime import timedelta

import pytest

from psx_pipeline.calendar import ExchangeCalendar
from psx_pipeline.contracts import TARGETS, utcnow
from psx_pipeline.models import FEATURE_COLUMNS, model_slot
from psx_pipeline.pipeline import issue
from psx_pipeline.publishing import empty_bundle, publish
from psx_pipeline.storage import read_json, records, write_json


def candidate(horizon):
    return {
        "version": f"test-h{horizon}",
        "scope": "index",
        "instrument_ids": ["TEST:INDEX:TR"],
        "fixture": True,
        "horizon": horizon,
        "target_definition": TARGETS["official_total_return"],
        "return_basis": "official_total_return",
        "feature_version": "price-v1",
        "last_training_label": "2019-01-01",
        "fit_range": {k: [-10, 10] for k in FEATURE_COLUMNS},
        "model": {"name": "frequency", "columns": FEATURE_COLUMNS, "p": 0.6},
        "calibrator": {"coef": 1.0, "intercept": 0.0},
        "policy": {"up": None, "not_up": None},
        "evaluation": {"high_correctness_supported": False},
        "evidence_hash": "fixture-only",
    }


def test_issue_rerun_keeps_original_and_missed_boundary_rejected(tables, tmp_path):
    c = ExchangeCalendar(tables["sessions"])
    ref = c.sessions[40]
    cutoff = ref.update_due_at
    for horizon in [1, 5]:
        model = candidate(horizon)
        write_json(tmp_path / ("active-" + model_slot(model) + ".json"), model)
    manifest = {"fixture": True, "snapshot": "fixture-snapshot"}
    original = issue(tmp_path, tables, manifest, str(ref.date), cutoff, cutoff + timedelta(seconds=1), True)
    assert len(original) == 2 and all(f["signal"] == "no_strong_signal" for f in original)
    assert (
        issue(tmp_path, tables, manifest, str(ref.date), cutoff, cutoff + timedelta(minutes=10), True)
        == original
    )
    assert len(records(tmp_path, "forecasts")) == 2
    with pytest.raises(ValueError, match="missed"):
        issue(tmp_path, tables, manifest, str(ref.date), cutoff, c.advance(ref.date, 1).opens_at, True)


def test_partial_publish_preserves_previous_pointer(tmp_path, monkeypatch):
    import psx_pipeline.publishing as publishing

    first = publish(tmp_path, empty_bundle(utcnow()))
    pointer = read_json(tmp_path / "latest.json")

    def fail(*args):
        raise ValueError("simulated corrupt partial write")

    monkeypatch.setattr(publishing, "verify_bundle", fail)
    with pytest.raises(ValueError, match="partial"):
        publish(tmp_path, empty_bundle(utcnow()))
    assert read_json(tmp_path / "latest.json") == pointer and pointer["bundle_id"] == first


def test_stale_required_price_cannot_issue_probability(tables, tmp_path):
    c = ExchangeCalendar(tables["sessions"])
    ref = c.sessions[40]
    cutoff = ref.update_due_at
    tables["bars"] = [r for r in tables["bars"] if r["session"] != str(ref.date)]
    for horizon in [1, 5]:
        model = candidate(horizon)
        write_json(tmp_path / ("active-" + model_slot(model) + ".json"), model)
    result = issue(
        tmp_path,
        tables,
        {"fixture": True, "snapshot": "fixture"},
        str(ref.date),
        cutoff,
        cutoff + timedelta(seconds=1),
        True,
    )
    assert all(f["p_up"] is None and f["signal"] == "unavailable" for f in result)


def test_forward_deterioration_suppresses_new_issuance(tables, tmp_path, monkeypatch):
    import psx_pipeline.pipeline as pipeline
    from psx_pipeline.storage import append_record, digest

    c = ExchangeCalendar(tables["sessions"])
    ref = c.sessions[40]
    cutoff = ref.update_due_at
    model = candidate(1)
    model["fixture"] = False
    model["evaluation"].update(brier=0.2, ece=0.05)
    write_json(tmp_path / ("active-" + model_slot(model) + ".json"), model)
    append_record(
        tmp_path, "promotions", "test", {"version": model["version"], "artifact_hash": digest(model)}
    )
    monkeypatch.setattr(pipeline, "authorize_dataset", lambda *args: [])
    monkeypatch.setattr(
        pipeline,
        "score_forward",
        lambda *args: {
            "scorecards": [
                {
                    "instrument": "TEST:INDEX:TR",
                    "horizon": 1,
                    "model_version": model["version"],
                    "unique_dates": 63,
                    "brier": 0.3,
                    "ece": 0.2,
                }
            ]
        },
    )
    result = issue(
        tmp_path,
        tables,
        {"fixture": False, "snapshot": "test"},
        str(ref.date),
        cutoff,
        cutoff + timedelta(seconds=1),
    )
    assert result[0]["p_up"] is None
    assert "deterioration" in result[0]["suppression_reason"]


def test_company_exposure_missing_is_distinct_from_zero(tables, monkeypatch):
    import psx_pipeline.data as data
    from psx_pipeline.models import COMPANY_COLUMNS

    tables["instruments"][0]["kind"] = "company"
    member = {"instrument": "TEST:INDEX:TR", "sector": "banks", "exporter_exposure": None}
    monkeypatch.setattr(data, "universe_asof", lambda *args: [member])
    ref = ExchangeCalendar(tables["sessions"]).sessions[40]
    missing = data.build_feature(tables, member["instrument"], str(ref.date), ref.update_due_at, "test", True)
    member["exporter_exposure"] = 0.0
    known_zero = data.build_feature(
        tables, member["instrument"], str(ref.date), ref.update_due_at, "test", True
    )
    assert missing.eligible and known_zero.eligible
    assert all(key in missing.values for key in COMPANY_COLUMNS)
    assert missing.values["exporter_missing"] == 1
    assert known_zero.values["exporter_missing"] == 0
    assert missing.values["bank_sector"] == 1
