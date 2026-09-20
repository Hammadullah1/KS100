"""Reproducible research. Synthetic runs never become production evidence."""

import time
from pathlib import Path

import pandas as pd
import yaml

from .calendar import ExchangeCalendar
from .contracts import TARGETS
from .data import build_feature, label_for, latest
from .evaluation import (
    date_blocks,
    high_correctness_supported,
    learn_policy,
    score,
    selection_mask,
    split_blocks,
)
from .models import (
    COMPANY_COLUMNS,
    FEATURE_COLUMNS,
    calibrate,
    calibrated,
    choose_predictor,
    fit_model,
    model_slot,
    model_version,
    predict_model,
)
from .storage import append_record, digest, lock, read_json, write_json


def protocol(path="config/evaluation.yaml"):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def dataset(tables, snapshot, horizon, cutoff, scope="index", fixture=False):
    calendar = ExchangeCalendar(tables["sessions"])
    rows = []
    exclusions = {}
    instruments = [i for i in tables["instruments"] if i["kind"] == scope]
    if scope == "index" and len(instruments) != 1:
        raise ValueError("evaluate each index independently")
    for inst in instruments:
        for s in calendar.sessions:
            if s.update_due_at > cutoff:
                continue
            feature = build_feature(
                tables, inst["id"], str(s.date), s.update_due_at, snapshot, fixture, calendar=calendar
            )
            if not feature.eligible:
                exclusions[feature.exclusion] = exclusions.get(feature.exclusion, 0) + 1
                continue
            try:
                target = calendar.advance(s.date, horizon)
                if target.update_due_at > cutoff:
                    raise ValueError("unmatured at job cutoff")
                # Predeclared first-final target vintage, frozen at the target's data deadline.
                origin_rows = latest(
                    [
                        r
                        for r in tables["bars"]
                        if r["instrument"] == inst["id"] and r["session"] == str(s.date)
                    ],
                    s.update_due_at,
                    ["instrument", "session"],
                )
                outcome = label_for(
                    tables,
                    inst["id"],
                    str(s.date),
                    horizon,
                    target.update_due_at,
                    reference_close=origin_rows[0]["close"],
                    calendar=calendar,
                )
            except ValueError as exc:
                exclusions[str(exc)] = exclusions.get(str(exc), 0) + 1
                continue
            rows.append(
                {
                    "instrument": inst["id"],
                    "session": str(s.date),
                    "cutoff": s.update_due_at.isoformat(),
                    **feature.values,
                    **outcome,
                }
            )
    if not rows:
        raise ValueError("no eligible matured observations")
    frame = pd.DataFrame(rows).sort_values(["session", "instrument"]).reset_index(drop=True)
    return frame, exclusions


def run_research(
    frame,
    config,
    horizon,
    snapshot,
    fixture,
    output,
    final=False,
    columns=None,
    target_basis="official_total_return",
):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if final and (output / "final-test.json").exists():
        raise ValueError("final test already opened; preserve original report")
    columns = columns or (COMPANY_COLUMNS if target_basis == "adjusted_price" else FEATURE_COLUMNS)
    design = {
        "config": config,
        "columns": columns,
        "horizon": horizon,
        "snapshot": snapshot,
        "target_basis": target_basis,
        "label_vintage_policy": "first-final by target update deadline; later corrections scored separately",
    }
    frozen = output / "protocol.json"
    if frozen.exists() and read_json(frozen) != design:
        raise ValueError("frozen protocol differs; new research directory required")
    write_json(frozen, design)
    folds = split_blocks(
        frame,
        config["initial_fit_dates"],
        config["development_block_dates"],
        config["final_test_dates"],
        final,
    )
    results = []
    chosen_artifact = None
    start = time.perf_counter()
    for fold_index, fold in enumerate(folds):
        models = [
            fit_model(name, fold["fit"], columns)
            for name in ["frequency", "majority", "lagged_return", "logistic", "lightgbm"]
        ]
        selected = choose_predictor(models, fold["blend"])
        calibrator = calibrate(selected, fold["calibration"])
        selection = calibrated(selected, calibrator, fold["selection"])
        policy = learn_policy(fold["selection"], selection, config)
        evaluation = fold["evaluation"]
        p = calibrated(selected, calibrator, evaluation)
        candidates = {
            m["name"]: score(evaluation, predict_model(m, evaluation), reps=config["bootstrap_replicates"])
            for m in models
        }
        metrics = score(evaluation, p, selection_mask(p, policy), reps=config["bootstrap_replicates"])
        metrics["high_correctness_supported"] = False
        if final and not fixture:
            metrics["high_correctness_supported"] = high_correctness_supported(
                metrics, candidates["frequency"], config
            )
        # Regimes use a fit-period median; no full-series thresholds.
        cut = float(fold["fit"].volatility_20.median())
        regime = {}
        for label, mask in {
            "lower_volatility": evaluation.volatility_20 <= cut,
            "higher_volatility": evaluation.volatility_20 > cut,
        }.items():
            if mask.any():
                regime[label] = score(
                    evaluation[mask],
                    p[mask],
                    selection_mask(p[mask], policy),
                    reps=config["bootstrap_replicates"],
                )
        rolling = []
        for block in date_blocks(evaluation, config.get("rolling_block_dates", 63)):
            idx = evaluation.index.get_indexer(block.index)
            rolling.append(
                score(block, p[idx], selection_mask(p[idx], policy), reps=config["bootstrap_replicates"])
            )
        evidence = {
            "fold": fold_index,
            "stages": {
                name: {
                    "rows": len(f),
                    "dates": int(f.session.nunique()),
                    "start": str(f.session.min()),
                    "end": str(f.session.max()),
                    "last_target": str(f.target_session.max()),
                }
                for name, f in fold.items()
            },
            "chosen": selected["name"],
            "policy": policy,
            "comparison": candidates,
            "selected_model": metrics,
            "regimes": regime,
            "rolling": rolling,
        }
        results.append(evidence)
        chosen_artifact = {
            "schema_version": "1",
            "scope": "company" if target_basis == "adjusted_price" else "index",
            "instrument_ids": sorted(frame.instrument.unique().tolist()),
            "fixture": fixture,
            "horizon": horizon,
            "target_definition": TARGETS[target_basis],
            "return_basis": target_basis,
            "feature_version": "price-v1" if columns in [FEATURE_COLUMNS, COMPANY_COLUMNS] else "drivers-v1",
            "snapshot": snapshot,
            "model": selected,
            "calibrator": calibrator,
            "policy": policy,
            "fit_range": {c: [float(fold["fit"][c].min()), float(fold["fit"][c].max())] for c in columns},
            "last_training_label": str(fold["calibration"].target_session.max()),
            "evaluation": metrics,
            "baseline": candidates["frequency"],
            "protocol_hash": digest(design),
            "stage": "final_test" if final else "historical",
            "evidence_dates": int(evaluation.session.nunique()),
        }
        forecasts = evaluation[["instrument", "session", "target_session", "label", "direction"]].copy()
        forecasts["p_up"] = p
        forecasts["selected"] = selection_mask(p, policy)
        forecasts.to_csv(
            output / f"predictions-{'final' if final else 'development'}-{fold_index}.csv", index=False
        )
    elapsed = time.perf_counter() - start
    chosen_artifact["runtime_seconds"] = elapsed
    chosen_artifact["version"] = model_version(chosen_artifact)
    chosen_artifact["evidence_hash"] = digest(results)
    report = {
        "schema_version": "1",
        "mode": "fixture" if fixture else "research",
        "scope": "software_validation_only" if fixture else "market_research",
        "horizon": horizon,
        "stage": "final_test" if final else "historical",
        "snapshot": snapshot,
        "protocol_hash": digest(design),
        "runtime_seconds": elapsed,
        "folds": results,
        "lightgbm_configurations": 1,
        "maximum_configurations": config["lightgbm_trials_max"],
        "claim": "Synthetic fixture; no financial performance claim."
        if fixture
        else "No demonstrated forecasting advantage until evaluated against the declared promotion criteria.",
    }
    report_path = output / ("final-test.json" if final else "historical.json")
    if report_path.exists() and final:
        raise ValueError("final test already opened; preserve original report")
    write_json(report_path, report)
    write_json(output / "candidate.json", chosen_artifact)
    return report, chosen_artifact


def promote(root, candidate_path, now, config):
    candidate = read_json(candidate_path)
    if candidate["fixture"]:
        raise ValueError("fixture model cannot be promoted")
    if candidate["stage"] != "final_test" or candidate["evidence_dates"] < config["final_test_dates"]:
        raise ValueError("untouched test evidence required")
    if candidate["evaluation"]["brier"] >= candidate["baseline"]["brier"]:
        raise ValueError("no demonstrated probability advantage")
    if candidate["evaluation"]["ece"] > config["maximum_ece"]:
        raise ValueError("calibration gate failed")
    if candidate["runtime_seconds"] > 300:
        raise ValueError("runtime gate failed")
    # A reviewed artifact hash and source permissions are checked by the CLI before this transition.
    with lock(root):
        slot = model_slot(candidate)
        active = Path(root) / f"active-{slot}.json"
        previous = read_json(active) if active.exists() else None
        entry = {
            "at": now.isoformat(),
            "version": candidate["version"],
            "artifact_hash": digest(candidate),
            "previous": previous["version"] if previous else None,
            "evidence_hash": candidate["evidence_hash"],
        }
        append_record(root, "promotions", candidate["version"], entry)
        if previous:
            write_json(Path(root) / f"previous-{slot}.json", previous)
        write_json(Path(root) / "models" / (candidate["version"] + ".json"), candidate)
        write_json(active, candidate)
    return entry
