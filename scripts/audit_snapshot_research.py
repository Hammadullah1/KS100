"""Recompute saved metrics and reproduce final-batch research predictions."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from psx_pipeline.models import calibrated, predict_model
from psx_pipeline.snapshot_drivers import add_brent
from psx_pipeline.snapshot_research import available_history, checksum, make_features, read_snapshot
from psx_pipeline.storage import read_json, write_json


def audit(csv, output, brent=None):
    output = Path(output)
    design = read_json(output / "protocol.json")
    config = design["config"]
    if checksum(csv) != design["data_sha256"]:
        raise ValueError("Index data hash mismatch")
    drivers = design.get("drivers", {})
    if "brent_sha256" in drivers:
        if not brent or checksum(brent) != drivers["brent_sha256"]:
            raise ValueError("Brent data hash mismatch")
    summary = read_json(output / "summary.json")
    selections = read_json(output / "selection.json")
    raw = read_snapshot(csv)
    checks = []
    for horizon in [1, 5]:
        frame = make_features(raw, horizon)
        if brent:
            frame = add_brent(frame, brent)
        for stage in ["development", "evaluation"]:
            saved = pd.read_csv(output / f"{stage}-h{horizon}.csv")
            if saved.duplicated(["session", "model"]).any():
                raise ValueError("Duplicate forecast rows")
            for name, group in saved.groupby("model"):
                expected = frame.set_index("session").loc[group.session]
                np.testing.assert_array_equal(expected.label, group.label)
                np.testing.assert_array_equal(expected.target_session, group.target_session)
                np.testing.assert_allclose(expected.future_log_return, group.future_log_return, atol=1e-12)
                metrics = summary["horizons"][str(horizon)][stage][name]
                np.testing.assert_allclose(
                    metrics["brier"], ((group.p_up - group.label) ** 2).mean(), atol=1e-12
                )
                np.testing.assert_allclose(
                    metrics["accuracy"], ((group.p_up >= 0.5) == group.label).mean(), atol=1e-12
                )
            boundaries = read_json(output / f"{stage}-boundaries-h{horizon}.json")
            for boundary in boundaries:
                assert boundary["fit_last_target"] < boundary["calibration_start"]
                assert boundary["calibration_last_target"] <= boundary["forecast_start"]
                assert boundary["calibration_end"] < boundary["forecast_start"]
        values = summary["horizons"][str(horizon)]
        assert selections[str(horizon)] == min(
            values["development"], key=lambda n: values["development"][n]["brier"]
        )
        boundary = boundaries[-1]
        batch = frame[
            (frame.session >= boundary["forecast_start"]) & (frame.session <= boundary["forecast_end"])
        ]
        recent = np.array(
            [
                available_history(frame, day).tail(config["recent_baseline_dates"]).label.mean()
                for day in batch.session
            ]
        )
        artifacts = read_json(output / f"last-artifacts-h{horizon}.json")
        assert artifacts["stage"] == "snapshot_research" and artifacts["production_eligible"] is False
        for name, artifact in artifacts["artifacts"].items():
            probabilities = {
                "_raw": predict_model(artifact["model"], batch),
                "_shrunk": 0.5 * calibrated(artifact["model"], artifact["calibrator"], batch) + 0.5 * recent,
            }
            for suffix, probability in probabilities.items():
                group = saved[(saved.model == name + suffix) & saved.session.isin(batch.session)]
                np.testing.assert_allclose(probability, group.p_up, atol=1e-12)
        checks.append(
            f"h{horizon}: labels, metrics, selection, temporal boundaries and saved models verified"
        )
    write_json(
        output / "verification.json",
        {
            "passed": True,
            "checks": checks,
            "audit_source_sha256": checksum(__file__),
            "production_eligible": False,
        },
    )
    print("Snapshot audit passed:", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--brent-csv")
    args = parser.parse_args()
    audit(args.csv, args.output, args.brent_csv)
