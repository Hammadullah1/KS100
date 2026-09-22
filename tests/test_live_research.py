from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from psx_pipeline.live_research import PK, ResearchFeed, build_feed, deadline, parse_eod


def sample():
    rng = np.random.default_rng(701)
    raw = pd.DataFrame(
        {
            "date": pd.bdate_range("2023-01-02", periods=600),
            "close": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 600))),
            "volume": rng.integers(0, 100000, 600),
        }
    )
    now = datetime.combine(raw.date.iloc[-1].date(), datetime.min.time(), PK).replace(hour=19)
    return raw, now.astimezone(timezone.utc)


def payload(raw):
    return {
        "data": [
            [int(d.timestamp()), float(c), int(v), 99] for d, c, v in raw.itertuples(index=False, name=None)
        ]
    }


def test_eod_duplicates_zero_volume_and_conflicts():
    raw, now = sample()
    raw.loc[0, "volume"] = 0
    data = payload(raw)
    data["data"].append(data["data"][0].copy())
    parsed = parse_eod(data, now)
    assert len(parsed) == 600 and parsed.volume.iloc[0] == 0
    data["data"][-1][1] += 1
    with pytest.raises(ValueError, match="Conflicting"):
        parse_eod(data, now)


def test_eod_fails_for_bad_prices_old_data_and_early_close():
    raw, now = sample()
    data = payload(raw)
    data["data"][0][1] = float("inf")
    with pytest.raises(ValueError, match="Invalid"):
        parse_eod(data, now)
    with pytest.raises(ValueError, match="too old"):
        parse_eod(payload(raw), now + timedelta(days=7))
    with pytest.raises(ValueError, match="finalization"):
        parse_eod(payload(raw), now - timedelta(hours=3))


def test_public_feed_has_no_raw_prices_or_parameters_and_retry_preserves_issuance(monkeypatch):
    raw, now = sample()
    feed = build_feed(raw, now)
    encoded = feed.model_dump(mode="json")
    for prohibited in ['"close":', '"volume":', '"coef":', '"intercept":', '"model_text":']:
        assert prohibited not in feed.model_dump_json()
    assert len(feed.forecasts) == 2 and all(f.outcome is None for f in feed.history)
    assert all(f.p_up + f.p_not_up == pytest.approx(1) for f in feed.forecasts)
    monkeypatch.setattr(
        "psx_pipeline.live_research.fit_candidate",
        lambda *a: pytest.fail("Retry refitted an issued forecast"),
    )
    retry = build_feed(raw, now + timedelta(minutes=5), ResearchFeed.model_validate(encoded))
    assert [f.model_dump() for f in retry.forecasts] == [f.model_dump() for f in feed.forecasts]
    with pytest.raises(ValidationError):
        ResearchFeed.model_validate({**encoded, "raw_prices": []})


def test_matured_outcome_is_scored_only_after_an_actual_issuance():
    raw, now = sample()
    feed = build_feed(raw, now)
    next_date = pd.bdate_range(raw.date.iloc[-1], periods=2)[1]
    extended = pd.concat(
        [raw, pd.DataFrame({"date": [next_date], "close": [raw.close.iloc[-1] * 1.01], "volume": [100]})],
        ignore_index=True,
    )
    next_now = (
        datetime.combine(next_date.date(), datetime.min.time(), PK).replace(hour=19).astimezone(timezone.utc)
    )
    updated = build_feed(extended, next_now, feed)
    old = next(
        f for f in updated.history if f.reference_session == raw.date.iloc[-1].date() and f.horizon == 1
    )
    assert old.outcome is not None and old.outcome.up
    assert old.outcome.correct == (old.p_up >= 0.5)
    assert (
        next(
            f for f in updated.history if f.reference_session == old.reference_session and f.horizon == 5
        ).outcome
        is None
    )


def test_missing_fresh_session_does_not_extend_deadline():
    raw, now = sample()
    with pytest.raises(ValueError, match="No fresh"):
        build_feed(raw, deadline(raw.date.iloc[-1].date()) + timedelta(minutes=1))
