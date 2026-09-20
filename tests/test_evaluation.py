import numpy as np
import pandas as pd
import pytest

from psx_pipeline.contracts import utcnow
from psx_pipeline.evaluation import (
    date_blocks,
    high_correctness_supported,
    learn_policy,
    score,
    selection_mask,
    split_blocks,
)
from psx_pipeline.models import calibrate, calibrated, fit_model, predict_model
from psx_pipeline.research import promote, protocol
from psx_pipeline.storage import write_json


def frame():
    days = pd.date_range("2020-01-01", periods=210, freq="D")
    rows = []
    for i, d in enumerate(days[:-5]):
        for company in ["ONE", "TWO"]:
            rows.append(
                {
                    "instrument": company,
                    "session": str(d.date()),
                    "target_session": str(days[i + 5].date()),
                    "label_available_at": days[i + 5].isoformat() + "+00:00",
                    "cutoff": d.isoformat() + "+00:00",
                    "label": i % 2,
                    "direction": "up" if i % 2 else ("unchanged" if i % 10 == 0 else "down"),
                    "return_1": 0.01 if i % 2 else -0.01,
                    "return_5": 0.02 if i % 2 else -0.02,
                    "return_20": 0.03,
                    "volatility_20": 0.01,
                }
            )
    return pd.DataFrame(rows).sample(frac=1, random_state=2)


def test_dates_grouped_and_label_intervals_purged_all_stages():
    f = frame()
    folds = split_blocks(f, 50, 20, 40)
    for fold in folds:
        stages = list(fold.values())
        for earlier, later in zip(stages, stages[1:]):
            assert earlier.target_session.max() < later.session.min()
            assert not set(earlier.session) & set(later.session)
        for stage in stages:
            assert (stage.groupby("session").instrument.nunique() == 2).all()
        assert fold["evaluation"].session.max() < sorted(f.session.unique())[-40]


def test_final_test_reserved_and_separate():
    f = frame()
    final = split_blocks(f, 50, 20, 40, True)[0]
    assert final["evaluation"].session.nunique() == 40
    assert final["selection"].target_session.max() < final["evaluation"].session.min()


def test_metrics_support_zero_selection_and_natural_unchanged():
    f = frame().sort_values(["session", "instrument"])
    m = score(f, np.full(len(f), 0.5), np.zeros(len(f), bool), reps=50)
    assert m["selected_correctness"] is None and m["coverage"] == 0
    assert m["unique_dates"] == 205 and m["count"] == 410
    assert m["outcome_frequencies"]["unchanged"] > 0
    assert sum(b["count"] for b in m["calibration"]) == 410
    assert m["uncertainty"]["low"] is None
    with pytest.raises(ValueError):
        score(f, np.full(len(f), np.nan))


def test_preprocessing_and_calibration_are_separate():
    f = frame().sort_values(["session", "instrument"])
    fold = split_blocks(f, 50, 20, 40)[0]
    model = fit_model("logistic", fold["fit"])
    saved = list(model["mean"])
    calibration = calibrate(model, fold["calibration"])
    p = calibrated(model, calibration, fold["evaluation"])
    assert model["mean"] == saved and np.isfinite(p).all()
    assert len(p) == len(fold["evaluation"])
    assert (
        predict_model(fit_model("frequency", fold["fit"]), fold["evaluation"]) == fold["fit"].label.mean()
    ).all()


def test_selection_requires_declared_support():
    f = frame().sort_values(["session", "instrument"]).iloc[:38]
    p = f.label.to_numpy() * 0.9 + 0.05
    policy = learn_policy(f, p, protocol())
    assert not selection_mask(p, policy).any()


def test_selection_can_fit_within_63_dates_without_validating_accuracy():
    f = frame().query("instrument == 'ONE'").sort_values("session").iloc[:63]
    p = np.where(f.label.to_numpy() == 1, 0.95, 0.05)
    config = protocol()
    policy = learn_policy(f, p, config)
    assert policy["up"] is not None and policy["not_up"] is not None
    assert policy["reason"] is None
    metrics = score(f, p, selection_mask(p, policy), reps=50)
    baseline = score(f, np.full(len(f), 0.5), reps=50)
    assert metrics["selected_correctness"] == 1.0
    assert config["minimum_selected"] == 200
    assert config["minimum_selected_dates"] == 100
    assert config["required_lower_bound"] == 0.8
    assert not high_correctness_supported(metrics, baseline, config)


def test_frozen_protocol_without_tuning_section_preserves_original_gate():
    f = frame().query("instrument == 'ONE'").sort_values("session").iloc[:63]
    p = np.where(f.label.to_numpy() == 1, 0.95, 0.05)
    config = protocol()
    del config["selection_tuning"]
    policy = learn_policy(f, p, config)
    assert not selection_mask(p, policy).any()


def test_rolling_blocks_keep_whole_dates_and_every_company_together():
    f = frame()  # Intentionally shuffled: row order must not define the date windows.
    blocks = list(date_blocks(f, 63))
    assert [b.session.nunique() for b in blocks] == [63, 63, 63, 16]
    assert [len(b) for b in blocks] == [126, 126, 126, 32]
    assert sum(len(b) for b in blocks) == len(f)
    seen = set()
    for block in blocks:
        dates = set(block.session)
        assert not seen & dates
        assert (block.groupby("session").instrument.nunique() == 2).all()
        pd.testing.assert_frame_equal(block, f.loc[block.index])
        seen.update(dates)
    assert seen == set(f.session)
    assert all(a.session.max() < b.session.min() for a, b in zip(blocks, blocks[1:]))


@pytest.mark.parametrize("block_dates", [0, -1, 1.5])
def test_rolling_blocks_reject_invalid_lengths(block_dates):
    with pytest.raises(ValueError, match="positive integer"):
        list(date_blocks(frame(), block_dates))


def test_fixture_model_cannot_promote(tmp_path):
    write_json(tmp_path / "candidate.json", {"fixture": True})
    with pytest.raises(ValueError, match="fixture"):
        promote(tmp_path, tmp_path / "candidate.json", utcnow(), protocol())
