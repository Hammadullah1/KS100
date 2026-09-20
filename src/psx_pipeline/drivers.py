"""Cheap, timestamped feature groups; interactions are hypotheses, not causation."""

from datetime import timedelta

import numpy as np

from .data import latest, macro_asof, stamp


def news_features(events, cutoff, instrument=None, sector=None):
    rows = latest(events, cutoff, ["event_id"])
    seen = set()
    selected = []
    for row in sorted(rows, key=lambda r: r["available_at"]):
        if stamp(row["available_at"]) < cutoff - timedelta(days=7):
            continue
        if row["content_hash"] in seen:
            continue
        if row["scope"] == "company" and row["instrument"] != instrument:
            continue
        if row["scope"] == "sector" and row["sector"] != sector:
            continue
        seen.add(row["content_hash"])
        selected.append(row)
    # Do not infer sentiment from Urdu with an English-only model.
    supported = [
        r
        for r in selected
        if r["sentiment"] is not None and r["encoder_version"] and r["sentiment_confidence"] is not None
    ]
    return {
        "news_count": float(len(selected)),
        "news_market_count": float(sum(r["scope"] == "market" for r in selected)),
        "news_sector_count": float(sum(r["scope"] == "sector" for r in selected)),
        "news_company_count": float(sum(r["scope"] == "company" for r in selected)),
        "news_urdu_count": float(sum(r["language"] == "ur" for r in selected)),
        "news_unknown_language_count": float(sum(r["language"] == "unknown" for r in selected)),
        "news_sentiment": float(np.mean([r["sentiment"] for r in supported])) if supported else None,
        "news_sentiment_missing": float(not supported),
    }


def driver_features(macro, cutoff, groups):
    out = {}
    for name, settings in groups.items():
        if not settings.get("enabled") or "series" not in settings:
            continue
        current = macro_asof(macro, settings["series"], cutoff, settings["max_age_days"])
        previous = macro_asof(macro, settings["series"], cutoff - timedelta(days=7), settings["max_age_days"])
        out.update({f"{name}_{k}": v for k, v in current.items()})
        a, b = current["value"], previous["value"]
        out[f"{name}_change"] = a - b if a is not None and b is not None else None
    if out.get("brent_change") is not None and out.get("fx_change") is not None:
        out["brent_x_fx"] = out["brent_change"] * out["fx_change"]
    return out


def ablation_compare(frame, group_columns, runner):
    # The same origin rows and targets are retained for each comparison.
    reports = {}
    baseline_columns = ["return_1", "return_5", "return_20", "volatility_20"]
    for group, columns in group_columns.items():
        if not columns or any(c not in frame or frame[c].notna().sum() == 0 for c in columns):
            reports[group] = {"status": "unavailable", "reason": "no timed usable observations"}
            continue
        baseline = runner(frame, baseline_columns, group + "-without")
        augmented = runner(frame, baseline_columns + columns, group + "-with")
        deltas = [
            b["selected_model"]["brier"] - a["selected_model"]["brier"]
            for b, a in zip(baseline["folds"], augmented["folds"])
        ]
        reports[group] = {
            "status": "tested",
            "brier_improvement_by_fold": deltas,
            "keep_candidate": len(deltas) >= 2 and all(d > 0 for d in deltas),
            "reason": "requires stable improvement across at least two folds; final-test selection remains frozen",
        }
    return reports
