from .contracts import utcnow


def input_gate(feature, candidate, now, update_due):
    if not feature.eligible:
        return feature.exclusion
    if now > update_due:
        return "data update deadline missed"
    if feature.feature_version != candidate["feature_version"]:
        return "feature version mismatch"
    for key, (low, high) in candidate["fit_range"].items():
        value = feature.values.get(key)
        if value is None:
            return "required feature unavailable"
        margin = max(abs(high - low), 1e-8)
        if value < low - margin or value > high + margin:
            return "outside validated input range"
    return None


def deterioration(current, reference, minimum_dates=63):
    if current["unique_dates"] < minimum_dates:
        return {"status": "insufficient_support", "pause": False}
    reasons = []
    if current["brier"] > reference["brier"] + 0.05:
        reasons.append("Brier deterioration exceeds prespecified 0.05")
    if current["ece"] > 0.15:
        reasons.append("calibration warning exceeds 0.15")
    return {
        "status": "pause" if reasons else "monitoring",
        "pause": bool(reasons),
        "reasons": reasons,
        "checked_at": utcnow().isoformat(),
    }
