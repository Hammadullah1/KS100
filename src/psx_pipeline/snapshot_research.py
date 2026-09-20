"""Bounded CSV research with rolling training and explicit retrospective evidence.

This command does not import a CSV into approved production state. It treats
the source snapshot as retrospective, not as historical publication vintages.
"""

import hashlib
import importlib.metadata
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from lightgbm import LGBMClassifier

from .evaluation import score
from .models import FEATURE_COLUMNS, calibrate, calibrated, fit_model, predict_model
from .storage import write_json

BASIC = FEATURE_COLUMNS + ["volume_change", "volume_relative_20"]
REGIME = BASIC + ["return_60", "drawdown_60", "volatility_ratio", "downside_volatility", "rsi_14"]
MODEL_COLUMNS = {"logistic_basic": BASIC, "logistic_regime": REGIME, "lightgbm_regime": REGIME}
BASELINES = ["neutral", "recent_frequency", "lagged_return"]
CANDIDATES = BASELINES + [name + suffix for name in MODEL_COLUMNS for suffix in ["_raw", "_shrunk"]]


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_snapshot(path):
    raw = pd.read_csv(path)
    if not {"date", "close", "volume"}.issubset(raw.columns):
        raise ValueError("CSV requires date, close and volume columns")
    raw = raw[["date", "close", "volume"]].copy()
    raw["date"] = pd.to_datetime(raw.date, format="%Y-%m-%d", errors="raise")
    for column in ["close", "volume"]:
        raw[column] = pd.to_numeric(raw[column], errors="raise")
    if raw.isna().any().any() or not np.isfinite(raw[["close", "volume"]]).all().all():
        raise ValueError("Missing or nonfinite observations require review")
    if raw.date.duplicated().any():
        raise ValueError("Duplicate dates require explicit reconciliation")
    if (raw.close <= 0).any() or (raw.volume < 0).any():
        raise ValueError("Invalid price or volume")
    if (raw.date.dt.dayofweek >= 5).any():
        raise ValueError("Weekend observations require exchange-calendar review")
    return raw.sort_values("date").reset_index(drop=True)


def make_features(raw, horizon):
    if horizon not in [1, 5]:
        raise ValueError("Only 1 and 5 observation horizons are supported")
    close, volume = np.log(raw.close), np.log1p(raw.volume)
    returns = close.diff()
    f = pd.DataFrame({"session": raw.date.dt.strftime("%Y-%m-%d")})
    for period in [1, 5, 20, 60]:
        f[f"return_{period}"] = close.diff(period)
    f["volatility_20"] = returns.rolling(20).std()
    f["volume_change"] = volume.diff()
    f["volume_relative_20"] = volume - volume.rolling(20).mean()
    f["drawdown_60"] = close - close.rolling(60).max()
    f["volatility_ratio"] = returns.rolling(5).std() / f.volatility_20.clip(lower=1e-8)
    f["downside_volatility"] = np.sqrt(returns.clip(upper=0).pow(2).rolling(20).mean())
    gain, loss = returns.clip(lower=0).rolling(14).mean(), -returns.clip(upper=0).rolling(14).mean()
    f["rsi_14"] = (gain / (gain + loss).replace(0, np.nan)).fillna(0.5)
    f["target_session"] = raw.date.shift(-horizon).dt.strftime("%Y-%m-%d")
    f["future_log_return"] = close.shift(-horizon) - close
    f["label"] = np.where(f.future_log_return.notna(), (f.future_log_return > 0).astype(float), np.nan)
    f["direction"] = np.where(
        f.future_log_return > 0, "up", np.where(f.future_log_return < 0, "down", "unchanged")
    )
    f["instrument"] = "RESEARCH:KSE100:UNRECONCILED_BASIS"
    f = f.iloc[60:].reset_index(drop=True)
    if not np.isfinite(f[REGIME]).all().all():
        raise ValueError("Nonfinite features")
    return f


def available_history(frame, origin):
    """Assumed after-close availability; never infer publication provenance."""
    return frame[(frame.session < origin) & frame.label.notna() & (frame.target_session <= origin)]


def training_blocks(frame, origin, config):
    available = available_history(frame, origin)
    calibration = available.tail(config["calibration_dates"])
    fit = available[available.target_session < calibration.session.min()].tail(config["fit_window_dates"])
    if len(calibration) != config["calibration_dates"] or len(fit) < config["minimum_fit_dates"]:
        raise ValueError("Insufficient matured fit/calibration history")
    if fit.label.nunique() < 2 or calibration.label.nunique() < 2:
        raise ValueError("Both classes required in fit and calibration blocks")
    return fit, calibration


def fit_candidate(name, fit, model_columns=None):
    kind = "lightgbm" if name.startswith("lightgbm") else "logistic"
    columns = (model_columns or MODEL_COLUMNS)[name]
    artifact = fit_model(kind, fit, columns)
    if kind == "lightgbm":
        # Stopping iteration is learned solely within fit, then all fit rows are used.
        model = LGBMClassifier(
            n_estimators=max(1, int(artifact["best_iteration"])),
            num_leaves=7,
            max_depth=3,
            learning_rate=0.03,
            min_child_samples=30,
            reg_lambda=5,
            n_jobs=2,
            verbosity=-1,
            random_state=731,
            deterministic=True,
            force_col_wise=True,
        ).fit(fit[columns], fit.label)
        artifact["text"] = model.booster_.model_to_string()
        artifact["full_fit_refit"] = True
    return artifact


def predict_batch(frame, batch, config, model_columns=None):
    origin = batch.session.iloc[0]
    fit, calibration = training_blocks(frame, origin, config)
    recent = np.array(
        [
            available_history(frame, day).tail(config["recent_baseline_dates"]).label.mean()
            for day in batch.session
        ]
    )
    predictions = {
        "neutral": np.full(len(batch), 0.5),
        "recent_frequency": recent,
        "lagged_return": np.where(batch.return_1 > 0, 0.6, 0.4),
    }
    artifacts = {}
    for name in model_columns or MODEL_COLUMNS:
        model = fit_candidate(name, fit, model_columns)
        sigmoid = calibrate(model, calibration)
        predictions[name + "_raw"] = predict_model(model, batch)
        # Fixed 50:50 shrinkage, no tuning on future/evaluation observations.
        predictions[name + "_shrunk"] = 0.5 * calibrated(model, sigmoid, batch) + 0.5 * recent
        artifacts[name] = {"model": model, "calibrator": sigmoid, "shrink_weight": 0.5}
    boundary = {
        "forecast_start": origin,
        "forecast_end": batch.session.iloc[-1],
        "fit_start": fit.session.min(),
        "fit_end": fit.session.max(),
        "fit_last_target": fit.target_session.max(),
        "fit_rows": len(fit),
        "calibration_start": calibration.session.min(),
        "calibration_end": calibration.session.max(),
        "calibration_last_target": calibration.target_session.max(),
    }
    return predictions, artifacts, boundary


def walk_forward(frame, evaluation, config, model_columns=None):
    records, boundaries = [], []
    artifacts = None
    for start in range(0, len(evaluation), config["refresh_dates"]):
        batch = evaluation.iloc[start : start + config["refresh_dates"]]
        probabilities, artifacts, boundary = predict_batch(frame, batch, config, model_columns)
        boundaries.append(boundary)
        for name, p in probabilities.items():
            row = batch[
                ["instrument", "session", "target_session", "label", "direction", "future_log_return"]
            ].copy()
            row["model"], row["p_up"] = name, p
            records.append(row)
    return pd.concat(records, ignore_index=True), boundaries, artifacts


def summarize(predictions, config):
    return {
        name: score(
            group, group.p_up.to_numpy(), np.zeros(len(group), bool), reps=config["bootstrap_replicates"]
        )
        for name, group in predictions.groupby("model", sort=False)
    }


def validate_config(config):
    for key in [
        "development_dates",
        "evaluation_dates",
        "refresh_dates",
        "fit_window_dates",
        "calibration_dates",
        "minimum_fit_dates",
        "recent_baseline_dates",
        "bootstrap_replicates",
    ]:
        if type(config.get(key)) is not int or config[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    if config["fit_window_dates"] < config["minimum_fit_dates"]:
        raise ValueError("Fit window is smaller than minimum fit history")
    if config.get("production_eligible") is not False or config.get("selection_metric") != "brier":
        raise ValueError("Snapshot experiments require research-only Brier selection")
    if config.get("evidence_status") != "previously_observed_history_exploratory":
        raise ValueError("This command does not support independent-test claims")
    if config.get("horizons") != [1, 5]:
        raise ValueError("Use common dates for horizons [1, 5]")


def run_snapshot(csv_path, output, config_path="config/snapshot_research.yaml", brent_path=None):
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    validate_config(config)
    raw = read_snapshot(csv_path)
    frames = {h: make_features(raw, h) for h in config["horizons"]}
    model_columns = dict(MODEL_COLUMNS)
    driver_evidence = {"brent": "not supplied"}
    if brent_path:
        from .snapshot_drivers import BRENT_COLUMNS, add_brent

        frames = {h: add_brent(frame, brent_path) for h, frame in frames.items()}
        model_columns.update(
            {"logistic_brent": BASIC + BRENT_COLUMNS, "lightgbm_brent": BASIC + BRENT_COLUMNS}
        )
        driver_evidence = {
            "brent_sha256": checksum(brent_path),
            "source": "https://fred.stlouisfed.org/series/DCOILBRENTEU",
            "timing": "observation date + 7 calendar days; assumed, not verified publication timing",
            "max_observation_age_days": 21,
            "vintages": "revised snapshot, not point-in-time vintages",
            "feature_source_sha256": checksum(Path(__file__).parent / "snapshot_drivers.py"),
        }
    candidates = BASELINES + [name + suffix for name in model_columns for suffix in ["_raw", "_shrunk"]]
    common = frames[5].loc[frames[5].label.notna(), "session"].tolist()
    size = config["development_dates"] + config["evaluation_dates"]
    if len(common) < size:
        raise ValueError("Insufficient common labelled history")
    development_dates = common[-size : -config["evaluation_dates"]]
    evaluation_dates = common[-config["evaluation_dates"] :]
    for frame in frames.values():
        training_blocks(frame, development_dates[0], config)
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; preserve observed results and choose a new experiment ID")
    output.mkdir(parents=True)
    start = time.perf_counter()
    write_json(
        output / "protocol.json",
        {
            "config": config,
            "data_sha256": checksum(csv_path),
            "rows": len(raw),
            "first_date": str(raw.date.min().date()),
            "last_date": str(raw.date.max().date()),
            "source_hashes": {
                name: checksum(Path(__file__).parent / name)
                for name in ["snapshot_research.py", "models.py", "evaluation.py"]
            },
            "packages": {
                name: importlib.metadata.version(name)
                for name in ["numpy", "pandas", "scikit-learn", "lightgbm"]
            },
            "features": model_columns,
            "candidates": candidates,
            "drivers": driver_evidence,
            "assumptions": [
                "Close and labels ending today available before after-close forecast",
                "Recorded observations exhaust exchange sessions; calendar unverified",
                "Index return basis, source rights and publication vintages unresolved",
            ],
            "development_origin_range": [development_dates[0], development_dates[-1]],
            "evaluation_origin_range": [evaluation_dates[0], evaluation_dates[-1]],
            "production_eligible": False,
        },
    )
    results, selections = {}, {}
    # Save BOTH development selections before opening either evaluation slice.
    for h, frame in frames.items():
        dev = frame[frame.session.isin(development_dates) & (frame.target_session < evaluation_dates[0])]
        predictions, boundaries, _ = walk_forward(frame, dev, config, model_columns)
        metrics = summarize(predictions, config)
        selected = min(candidates, key=lambda name: metrics[name]["brier"])
        selections[str(h)] = selected
        predictions.to_csv(output / f"development-h{h}.csv", index=False)
        write_json(output / f"development-boundaries-h{h}.json", boundaries)
        results[str(h)] = {"primary": selected, "development": metrics}
    write_json(output / "selection.json", selections)
    for h, frame in frames.items():
        evaluation = frame[frame.session.isin(evaluation_dates)]
        predictions, boundaries, artifacts = walk_forward(frame, evaluation, config, model_columns)
        metrics = summarize(predictions, config)
        predictions.to_csv(output / f"evaluation-h{h}.csv", index=False)
        write_json(output / f"evaluation-boundaries-h{h}.json", boundaries)
        write_json(
            output / f"last-artifacts-h{h}.json",
            {
                "fixture": False,
                "stage": "snapshot_research",
                "production_eligible": False,
                "artifacts": artifacts,
                "trained_for": boundaries[-1]["forecast_start"],
            },
        )
        results[str(h)]["evaluation"] = metrics
    result = {
        "status": "completed",
        "evidence_status": config["evidence_status"],
        "production_eligible": False,
        "runtime_seconds": time.perf_counter() - start,
        "horizons": results,
        "candidates": candidates,
        "drivers": driver_evidence,
        "claim": "No independently established forecasting advantage.",
    }
    write_json(output / "summary.json", result)
    write_report(output, result)
    return {
        "status": "completed",
        "report": str(output / "RESULTS.md"),
        "primary": selections,
        "runtime_seconds": result["runtime_seconds"],
        "evidence_status": config["evidence_status"],
        "production_eligible": False,
    }


def write_report(output, result):
    text = [
        "# Rolling snapshot research",
        "**Exploratory results on previously inspected history. No independent high-accuracy claim.**",
        "Models refresh every configured block using only matured labels. Earlier development Brier loss selects each primary; the later observed year is not used to change that selection.",
        "Brier loss is squared probability error (lower is better); constant 50% scores 0.2500. Balanced accuracy weights the two directions equally.",
    ]
    for horizon, values in result["horizons"].items():
        text += [f"## Horizon {horizon}", f"Development-selected primary: **{values['primary']}**."]
        lines = [
            "| Candidate | Development Brier | Evaluation Brier | Accuracy | Balanced accuracy | Down recall |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for name in result["candidates"]:
            m = values["evaluation"][name]
            lines.append(
                f"| {name} | {values['development'][name]['brier']:.4f} | {m['brier']:.4f} | "
                f"{m['accuracy']:.1%} | {m['balanced_accuracy']:.1%} | {m['directions']['down_or_unchanged']['recall']:.1%} |"
            )
        text.append("\n".join(lines))
        primary = values["evaluation"][values["primary"]]
        ci = primary["correctness_uncertainty"]
        text.append(
            f"Primary accuracy block-bootstrap 95% interval: {ci['low']:.1%}–{ci['high']:.1%}. "
            "Overlapping five-session outcomes reduce independent evidence. Intervals do not account for repeated research choices."
        )
    text += [
        f"Total run time: {result['runtime_seconds']:.1f} seconds. CPU only; no new paid service.",
        "Raw CSV is retrospective and has no verified first-publication history. Same-day close availability and exchange-session completeness are assumptions. No missing macro factors were invented. No high-confidence signal policy was fitted in this command; zero selected signals means not evaluated. Artifacts cannot pass the production promotion stage check.",
        "Keep all results. Evaluate a frozen future candidate on forecasts logged before outcomes; do not relabel this already-seen period as a fresh holdout.",
    ]
    if "brent_sha256" in result["drivers"]:
        text.append(
            "Brent features use the FRED/EIA revised daily snapshot with an assumed seven-calendar-day delay and a 21-day staleness limit. This is a driver hypothesis test, not verified historical publication timing or proof of causation."
        )
    (output / "RESULTS.md").write_text("\n\n".join(text) + "\n", encoding="utf-8")
