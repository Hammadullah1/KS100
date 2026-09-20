import json

import numpy as np
import pandas as pd
import pytest
import yaml

from psx_pipeline.contracts import utcnow
from psx_pipeline.models import calibrated, predict_model
from psx_pipeline.research import promote, protocol
from psx_pipeline.snapshot_drivers import BRENT_COLUMNS, add_brent
from psx_pipeline.snapshot_research import (
    REGIME,
    available_history,
    make_features,
    read_snapshot,
    run_snapshot,
    training_blocks,
    validate_config,
)


def raw_frame():
    rng = np.random.default_rng(91)
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2020-01-01", periods=420),
            "close": 100 * np.exp(np.cumsum(rng.normal(0.0001, 0.01, 420))),
            "volume": rng.integers(0, 10000, 420),
        }
    )


def config():
    return {
        "version": "test-only",
        "evidence_status": "previously_observed_history_exploratory",
        "horizons": [1, 5],
        "development_dates": 42,
        "evaluation_dates": 42,
        "refresh_dates": 21,
        "fit_window_dates": 126,
        "calibration_dates": 30,
        "minimum_fit_dates": 80,
        "recent_baseline_dates": 63,
        "bootstrap_replicates": 5,
        "selection_metric": "brier",
        "production_eligible": False,
    }


def test_future_prices_do_not_change_past_features_and_unmatured_labels_stay_missing():
    raw = raw_frame()
    altered = raw.copy()
    altered.loc[300:, "close"] *= 2
    altered.loc[300:, "volume"] *= 3
    a, b = make_features(raw, 5), make_features(altered, 5)
    pd.testing.assert_frame_equal(
        a.loc[a.session < str(raw.date.iloc[300].date()), REGIME],
        b.loc[b.session < str(raw.date.iloc[300].date()), REGIME],
    )
    assert a.tail(5).label.isna().all()
    assert a.tail(5).target_session.isna().all()
    assert a.iloc[0].label == int(raw.close.iloc[65] > raw.close.iloc[60])


def test_flat_prices_and_zero_volume_produce_finite_features():
    raw = raw_frame()
    raw["close"], raw["volume"] = 100.0, 0
    features = make_features(raw, 1)
    assert np.isfinite(features[REGIME]).all().all()
    assert features.rsi_14.eq(0.5).all()


@pytest.mark.parametrize("horizon", [1, 5])
def test_training_and_calibration_use_only_matured_labels(horizon):
    frame = make_features(raw_frame(), horizon)
    origin = frame.session.iloc[-30]
    fit, calibration = training_blocks(frame, origin, config())
    assert fit.target_session.max() < calibration.session.min()
    assert calibration.target_session.max() <= origin
    assert calibration.session.max() < origin
    assert len(fit) == 126 and len(calibration) == 30
    assert available_history(frame, origin).target_session.max() <= origin


@pytest.mark.parametrize("problem", ["duplicate", "negative_volume", "infinite", "missing"])
def test_csv_rejects_unsafe_rows(tmp_path, problem):
    raw = raw_frame()
    if problem == "duplicate":
        raw.loc[1, "date"] = raw.loc[0, "date"]
    elif problem == "negative_volume":
        raw.loc[0, "volume"] = -1
    elif problem == "infinite":
        raw.loc[0, "close"] = np.inf
    else:
        raw.loc[0, "close"] = np.nan
    raw.to_csv(tmp_path / "input.csv", index=False)
    with pytest.raises(ValueError):
        read_snapshot(tmp_path / "input.csv")


def test_config_cannot_enable_production_or_claim_fresh_test():
    for changes in [
        {"production_eligible": True},
        {"evidence_status": "untouched"},
        {"refresh_dates": 0},
        {"horizons": [1]},
    ]:
        with pytest.raises(ValueError):
            validate_config({**config(), **changes})


@pytest.mark.parametrize("with_brent", [False, True])
def test_research_freezes_selection_reproduces_models_and_refuses_promotion(tmp_path, with_brent):
    raw = raw_frame()
    raw.to_csv(tmp_path / "input.csv", index=False)
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config()))
    output = tmp_path / "experiment"
    brent_path = None
    if with_brent:
        brent_path = tmp_path / "brent.csv"
        pd.DataFrame({"observation_date": raw.date, "DCOILBRENTEU": raw.close}).to_csv(
            brent_path, index=False
        )
    result = run_snapshot(tmp_path / "input.csv", output, tmp_path / "config.yaml", brent_path)
    assert result["production_eligible"] is False
    selections = json.loads((output / "selection.json").read_text())
    summary = json.loads((output / "summary.json").read_text())
    for h in [1, 5]:
        dev = pd.read_csv(output / f"development-h{h}.csv")
        ev = pd.read_csv(output / f"evaluation-h{h}.csv")
        assert dev.target_session.max() < ev.session.min()
        metrics = summary["horizons"][str(h)]
        assert selections[str(h)] == min(
            metrics["development"], key=lambda n: metrics["development"][n]["brier"]
        )
        assert ev.groupby("model").size().eq(42).all()
        assert not ev.duplicated(["session", "model"]).any()
        for name, group in ev.groupby("model"):
            assert metrics["evaluation"][name]["brier"] == pytest.approx(
                ((group.p_up - group.label) ** 2).mean()
            )
        frame = make_features(raw, h)
        if with_brent:
            frame = add_brent(frame, brent_path)
        boundary = json.loads((output / f"evaluation-boundaries-h{h}.json").read_text())[-1]
        batch = frame[
            (frame.session >= boundary["forecast_start"]) & (frame.session <= boundary["forecast_end"])
        ]
        artifact_path = output / f"last-artifacts-h{h}.json"
        artifact = json.loads(artifact_path.read_text())
        for name, model in artifact["artifacts"].items():
            saved = ev[(ev.model == name + "_raw") & ev.session.isin(batch.session)]
            np.testing.assert_allclose(predict_model(model["model"], batch), saved.p_up, atol=1e-12)
            recent = np.array([available_history(frame, day).tail(63).label.mean() for day in batch.session])
            p = 0.5 * calibrated(model["model"], model["calibrator"], batch) + 0.5 * recent
            saved = ev[(ev.model == name + "_shrunk") & ev.session.isin(batch.session)]
            np.testing.assert_allclose(p, saved.p_up, atol=1e-12)
        with pytest.raises(ValueError, match="untouched test"):
            promote(tmp_path, artifact_path, utcnow(), protocol())
    with pytest.raises(ValueError, match="already exists"):
        run_snapshot(tmp_path / "input.csv", output, tmp_path / "config.yaml")


def test_brent_delay_prevents_use_of_recent_and_future_observations(tmp_path):
    raw = raw_frame()
    source = pd.DataFrame({"observation_date": raw.date, "DCOILBRENTEU": raw.close})
    source.to_csv(tmp_path / "brent.csv", index=False)
    frame = make_features(raw, 1)
    origin = pd.Timestamp(frame.session.iloc[150])
    original = add_brent(frame, tmp_path / "brent.csv")
    source.loc[source.observation_date > origin - pd.Timedelta(days=7), "DCOILBRENTEU"] *= 8
    source.to_csv(tmp_path / "altered.csv", index=False)
    modified = add_brent(frame, tmp_path / "altered.csv")
    pd.testing.assert_frame_equal(
        original.loc[original.session <= str(origin.date()), BRENT_COLUMNS],
        modified.loc[modified.session <= str(origin.date()), BRENT_COLUMNS],
    )
    assert original.loc[original.brent_missing.eq(0), "brent_age"].ge(7).all()


def test_stale_brent_is_flagged_and_not_backfilled(tmp_path):
    raw = raw_frame()
    pd.DataFrame({"observation_date": raw.date.iloc[:200], "DCOILBRENTEU": raw.close.iloc[:200]}).to_csv(
        tmp_path / "brent.csv", index=False
    )
    augmented = add_brent(make_features(raw, 1), tmp_path / "brent.csv")
    assert augmented.tail(20).brent_missing.eq(1).all()
    assert augmented.tail(20)[BRENT_COLUMNS[:3]].eq(0).all().all()
