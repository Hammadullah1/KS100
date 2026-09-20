"""Grouped, purged chronological evaluation and date-block uncertainty."""

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    log_loss,
    precision_recall_fscore_support,
)


def split_blocks(frame, fit_dates=504, block_dates=63, final_dates=252, final=False):
    dates = sorted(frame.session.unique())
    if len(dates) < fit_dates + 4 * block_dates + final_dates:
        raise ValueError("insufficient history for predeclared protocol")
    boundary = len(dates) - final_dates
    ends = (
        [boundary - 3 * block_dates]
        if final
        else list(range(fit_dates, boundary - 4 * block_dates + 1, block_dates))
    )
    if not final and not ends:
        ends = [fit_dates]
    folds = []
    for end in ends:
        ranges = [
            (0, end),
            (end, end + block_dates),
            (end + block_dates, end + 2 * block_dates),
            (end + 2 * block_dates, end + 3 * block_dates),
            (end + 3 * block_dates, len(dates) if final else end + 4 * block_dates),
        ]
        if not final and ranges[-1][1] > boundary:
            continue
        stages = {}
        for i, (a, b) in enumerate(ranges):
            selected = frame[frame.session.isin(dates[a:b])].copy()
            if i < 4:
                next_date = dates[ranges[i + 1][0]]
                next_cutoff = frame.loc[frame.session == next_date, "cutoff"].min()
                selected = selected[
                    (selected.target_session < next_date) & (selected.label_available_at < next_cutoff)
                ]
            stages[["fit", "blend", "calibration", "selection", "evaluation"][i]] = selected
        if any(len(v) == 0 for v in stages.values()):
            raise ValueError("empty stage after purging")
        folds.append(stages)
    if not folds:
        raise ValueError("no complete evaluation fold")
    return folds


def date_blocks(frame, block_dates=63):
    """Partition complete chronological dates, preserving each row's original index."""
    if not isinstance(block_dates, int) or block_dates < 1:
        raise ValueError("rolling block dates must be a positive integer")
    dates = sorted(frame.session.unique())
    for start in range(0, len(dates), block_dates):
        yield frame[frame.session.isin(dates[start : start + block_dates])]


def block_interval(frame, correct, selected, block=10, reps=500, seed=731):
    dates = sorted(frame.session.unique())
    groups = [np.where(frame.session.to_numpy() == d)[0] for d in dates]
    if not np.any(selected):
        return {"low": None, "high": None, "lower_one_sided_95": None, "replicates": 0, "block_dates": block}
    rng = np.random.default_rng(seed)
    estimates = []
    length = min(block, len(dates))
    for _ in range(reps):
        sampled = []
        while len(sampled) < len(dates):
            start = int(rng.integers(0, len(dates) - length + 1))
            sampled.extend(range(start, start + length))
        indices = np.concatenate([groups[i] for i in sampled[: len(dates)]])
        mask = selected[indices]
        if mask.any():
            estimates.append(float(np.mean(correct[indices][mask])))
    if not estimates:
        return {"low": None, "high": None, "lower_one_sided_95": None, "replicates": 0, "block_dates": block}
    return {
        "low": float(np.quantile(estimates, 0.025)),
        "high": float(np.quantile(estimates, 0.975)),
        "lower_one_sided_95": float(np.quantile(estimates, 0.05)),
        "replicates": len(estimates),
        "block_dates": block,
    }


def score(frame, probability, selected=None, reps=500):
    p = np.asarray(probability, dtype=float)
    y = frame.label.to_numpy(int)
    if len(p) != len(y) or not len(y) or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("invalid probabilities")
    prediction = (p >= 0.5).astype(int)
    correct = prediction == y
    selected = np.ones(len(y), dtype=bool) if selected is None else np.asarray(selected, dtype=bool)
    precision, recall, _, support = precision_recall_fscore_support(
        y, prediction, labels=[0, 1], zero_division=0
    )
    bins = []
    ece = 0.0
    for low in np.arange(0, 1, 0.1):
        mask = (p >= low) & (p < (low + 0.1) if low < 0.89 else p <= 1)
        if not mask.any():
            bins.append({"from": float(low), "count": 0, "mean_probability": None, "observed_up": None})
            continue
        mean = float(p[mask].mean())
        observed = float(y[mask].mean())
        ece += float(mask.mean()) * abs(mean - observed)
        bins.append(
            {"from": float(low), "count": int(mask.sum()), "mean_probability": mean, "observed_up": observed}
        )
    date_scores = (
        pd.DataFrame({"session": frame.session.to_numpy(), "correct": correct, "brier": (p - y) ** 2})
        .groupby("session")
        .mean()
    )
    directions = {}
    for label, name in enumerate(["down_or_unchanged", "up"]):
        mask = selected & (prediction == label)
        directions[name] = {
            "precision": float(precision[label]),
            "recall": float(recall[label]),
            "actual_support": int(support[label]),
            "selected_support": int(mask.sum()),
            "selected_dates": int(frame.loc[mask, "session"].nunique()),
            "selected_correctness": float(correct[mask].mean()) if mask.any() else None,
            "uncertainty": block_interval(frame, correct, mask, reps=reps),
        }
    intervals = [block_interval(frame, correct, selected, b, reps) for b in [5, 10, 20]]
    return {
        "count": len(y),
        "unique_dates": int(frame.session.nunique()),
        "companies": int(frame.instrument.nunique()),
        "matured_outcomes": len(y),
        "start": str(frame.session.min()),
        "end": str(frame.session.max()),
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, np.clip(p, 1e-12, 1 - 1e-12), labels=[0, 1])),
        "accuracy": float(accuracy_score(y, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
        "date_balanced_accuracy": float(date_scores.correct.mean()),
        "date_balanced_brier": float(date_scores.brier.mean()),
        "date_balanced_coverage": float(
            pd.DataFrame({"session": frame.session.to_numpy(), "selected": selected})
            .groupby("session")
            .selected.mean()
            .mean()
        ),
        "date_balanced_selected_correctness": float(
            pd.DataFrame({"session": frame.session.to_numpy()[selected], "correct": correct[selected]})
            .groupby("session")
            .correct.mean()
            .mean()
        )
        if selected.any()
        else None,
        "coverage": float(selected.mean()),
        "abstention_rate": float(1 - selected.mean()),
        "selected_count": int(selected.sum()),
        "selected_dates": int(frame.loc[selected, "session"].nunique()),
        "selected_correctness": float(correct[selected].mean()) if selected.any() else None,
        "uncertainty": intervals[1],
        "block_sensitivity": intervals,
        "directions": directions,
        "calibration": bins,
        "ece": ece,
        "outcome_frequencies": {d: int((frame.direction == d).sum()) for d in ["up", "down", "unchanged"]},
        "correctness_uncertainty": block_interval(frame, correct, np.ones(len(y), bool), reps=reps),
    }


def selection_mask(p, policy):
    p = np.asarray(p)
    return ((p >= policy["up"]) if policy["up"] is not None else np.zeros(len(p), bool)) | (
        (p <= 1 - policy["not_up"]) if policy["not_up"] is not None else np.zeros(len(p), bool)
    )


def learn_policy(frame, p, config):
    policy = {"up": None, "not_up": None, "reason": "insufficient supported validation evidence"}
    p = np.asarray(p)
    correct = (p >= 0.5) == frame.label.to_numpy()
    # Threshold fitting is exploratory. The untouched-test claim gate below retains
    # its larger evidence requirements; a fitted threshold never validates itself.
    # Old frozen protocols without this section keep their original behaviour.
    support = config.get("selection_tuning", config)
    for direction in ["up", "not_up"]:
        for threshold in config["threshold_candidates"]:
            selected = p >= threshold if direction == "up" else p <= 1 - threshold
            if (
                selected.sum() < support["minimum_selected"]
                or frame.loc[selected, "session"].nunique() < support["minimum_selected_dates"]
            ):
                continue
            if selected.mean() < config["minimum_coverage"]:
                continue
            ci = block_interval(frame, correct, selected, reps=config["bootstrap_replicates"])
            if (
                ci["lower_one_sided_95"] is not None
                and ci["lower_one_sided_95"] >= config["required_lower_bound"]
            ):
                policy[direction] = threshold
                break
    if any(policy[d] is not None for d in ["up", "not_up"]):
        policy["reason"] = None
    return policy


def high_correctness_supported(metrics, baseline, config):
    # No claim without an untouched set, natural calibration and direction support.
    for direction in metrics["directions"].values():
        if direction["selected_support"] > 0 and (
            direction["selected_support"] < config["minimum_selected"]
            or direction["selected_dates"] < config["minimum_selected_dates"]
            or direction["uncertainty"]["lower_one_sided_95"] is None
            or direction["uncertainty"]["lower_one_sided_95"] < config["required_lower_bound"]
        ):
            return False
    return bool(
        metrics["selected_count"] >= config["minimum_selected"]
        and metrics["selected_dates"] >= config["minimum_selected_dates"]
        and metrics["coverage"] >= config["minimum_coverage"]
        and metrics["uncertainty"]["lower_one_sided_95"] is not None
        and metrics["uncertainty"]["lower_one_sided_95"] >= config["required_lower_bound"]
        and metrics["brier"] < baseline["brier"]
        and metrics["ece"] <= config["maximum_ece"]
    )
