from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from psx_pipeline.calendar import ExchangeCalendar
from psx_pipeline.contracts import Bar, Macro
from psx_pipeline.data import (
    adjust_close,
    adjustment,
    build_feature,
    label_for,
    macro_asof,
    universe_asof,
    validate_dataset,
)
from psx_pipeline.storage import digest

UTC = timezone.utc


def observation(value, available, vintage="v1"):
    return dict(
        source="fixture",
        series="CPI",
        reference_period="2020-01-01",
        value=value,
        units="percent",
        available_at=available,
        ingested_at=available,
        vintage=vintage,
        payload_hash=digest(vintage),
        fixture=True,
    )


def test_future_release_and_revision_cannot_enter_past_feature():
    rows = [observation(5, "2020-02-01T00:00:00Z"), observation(9, "2020-03-01T00:00:00Z", "v2")]
    assert macro_asof(rows, "CPI", datetime(2020, 1, 31, tzinfo=UTC), 45)["value"] is None
    assert macro_asof(rows, "CPI", datetime(2020, 2, 10, tzinfo=UTC), 45)["value"] == 5
    assert macro_asof(rows, "CPI", datetime(2020, 3, 2, tzinfo=UTC), 45)["value"] == 9
    assert macro_asof(rows, "CPI", datetime(2021, 3, 2, tzinfo=UTC), 45)["missing"] == 1


def test_zero_not_missing_and_historical_evidence_required():
    row = observation(0, "2020-02-01T00:00:00Z")
    assert macro_asof([row], "CPI", datetime(2020, 2, 2, tzinfo=UTC), 45)["value"] == 0
    row["ingested_at"] = "2020-02-02T00:00:00Z"
    with pytest.raises(ValidationError, match="evidence"):
        Macro.model_validate(row)


def test_calendar_has_holiday_friday_and_coverage(tables):
    c = ExchangeCalendar(tables["sessions"])
    assert not c.get("2019-01-10").is_open
    assert str(c.advance("2019-01-09", 1).date) == "2019-01-11"
    assert c.get("2019-01-11").closes_at.hour == 11
    assert str(c.advance("2019-01-09", 5).date) == "2019-01-17"
    with pytest.raises(ValueError, match="coverage"):
        c.get("2030-01-01")
    with pytest.raises(ValueError, match="gap"):
        ExchangeCalendar(tables["sessions"][:5] + tables["sessions"][6:])


def test_five_session_label_never_matures_early(tables):
    c = ExchangeCalendar(tables["sessions"])
    target = c.advance("2019-01-09", 5)
    with pytest.raises(ValueError, match="matured"):
        label_for(tables, "TEST:INDEX:TR", "2019-01-09", 5, target.closes_at - timedelta(seconds=1))
    with pytest.raises(ValueError, match="unavailable"):
        label_for(tables, "TEST:INDEX:TR", "2019-01-09", 5, target.closes_at)
    label = label_for(tables, "TEST:INDEX:TR", "2019-01-09", 5, target.update_due_at)
    assert label["target_session"] == "2019-01-17"


def action(kind, ratio=2, **kwargs):
    return dict(
        source="fixture",
        available_at="2019-01-02T00:00:00Z",
        ingested_at="2019-01-02T00:00:00Z",
        vintage="v1",
        payload_hash=digest(kind),
        fixture=True,
        instrument="TEST:COMPANY",
        ex_session="2019-01-04",
        kind=kind,
        ratio=ratio,
        resolved=True,
        **kwargs,
    )


@pytest.mark.parametrize(
    "kind,ratio,extra,expected",
    [
        ("split", 2, {}, 0.5),
        ("bonus", 0.25, {}, 0.8),
        ("rights", 0.5, {"subscription_price": 50, "previous_close": 100}, 5 / 6),
        ("cash_dividend", 5, {}, 1),
    ],
)
def test_documented_corporate_action_factors(kind, ratio, extra, expected):
    assert adjustment(action(kind, ratio, **extra)) == pytest.approx(expected)
    assert 100 * expected / (100 * adjustment(action(kind, ratio, **extra))) - 1 == pytest.approx(0)


def test_future_and_unresolved_actions(tables):
    a = action("split")
    cutoff = datetime(2019, 1, 3, tzinfo=UTC)
    assert adjust_close(100, "2019-01-01", "2019-01-03", [a], cutoff) == 100
    a["resolved"] = False
    with pytest.raises(ValueError, match="unresolved"):
        adjust_close(100, "2019-01-01", "2019-01-05", [a], datetime(2019, 1, 5, tzinfo=UTC))


def test_missing_no_trade_unchanged_distinct(tables):
    bar = tables["bars"][0]
    assert bar["close"] == bar["open"]
    for status in ["missing", "no_trade", "suspended"]:
        modified = {**bar, "status": status, "close": None, "open": None, "high": None, "low": None}
        assert Bar.model_validate(modified).status == status
    with pytest.raises(ValidationError):
        Bar.model_validate({**bar, "close": 0})
    with pytest.raises(ValidationError):
        Bar.model_validate({**bar, "volume": -1})


def test_missing_or_future_required_price_suppresses_feature(tables):
    c = ExchangeCalendar(tables["sessions"])
    ref = str(c.sessions[40].date)
    cutoff = c.sessions[40].update_due_at
    assert build_feature(tables, "TEST:INDEX:TR", ref, cutoff, "snapshot", True).eligible
    bad = deepcopy(tables)
    bad["bars"][39]["available_at"] = (cutoff + timedelta(hours=2)).isoformat()
    assert not build_feature(bad, "TEST:INDEX:TR", ref, cutoff, "snapshot", True).eligible
    bad = deepcopy(tables)
    bad["bars"].pop(35)
    assert not build_feature(bad, "TEST:INDEX:TR", ref, cutoff, "snapshot", True).eligible


def test_quality_rejects_duplicate_wrong_basis_and_error_ohlc(tables):
    validate_dataset(tables)
    bad = deepcopy(tables)
    bad["bars"].append(bad["bars"][0])
    with pytest.raises(ValueError, match="duplicate"):
        validate_dataset(bad)
    bad = deepcopy(tables)
    bad["bars"][0]["basis"] = "official_price_return"
    with pytest.raises(ValueError, match="basis"):
        validate_dataset(bad)
    with pytest.raises(ValidationError):
        Bar.model_validate({**tables["bars"][0], "high": 1})


def test_membership_is_point_in_time():
    def member(instrument, start, end, rank):
        return {
            "instrument": instrument,
            "index": "TEST",
            "effective_from": start,
            "effective_to": end,
            "liquidity_rank": rank,
            "available_at": start + "T00:00:00Z",
        }

    rows = [member("REMOVED", "2019-01-01", "2020-01-01", 1), member("LATER", "2020-01-01", None, 1)]
    assert universe_asof(rows, "2019-06-01", datetime(2019, 6, 1, tzinfo=UTC))[0]["instrument"] == "REMOVED"
