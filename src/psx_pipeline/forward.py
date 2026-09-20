"""Score real, prospectively issued forecasts; never re-label fixture backtests as forward."""

import pandas as pd

from .data import stamp
from .evaluation import score
from .storage import forecast_key, records


def score_forward(root, cutoff):
    forecasts = [
        f
        for f in records(root, "forecasts")
        if not f["fixture"] and f["p_up"] is not None and stamp(f["issued_at"]) <= cutoff
    ]
    outcomes = {}
    for o in records(root, "outcomes"):
        if stamp(o["recorded_at"]) > cutoff:
            continue
        old = outcomes.get(o["forecast_key"])
        if old is None or stamp(o["recorded_at"]) > stamp(old["recorded_at"]):
            outcomes[o["forecast_key"]] = o
    rows = []
    for f in forecasts:
        outcome = outcomes.get(forecast_key(f))
        if not outcome:
            continue
        if stamp(f["issued_at"]) >= stamp(f["next_open_at"]):
            raise ValueError("non-prospective issuance in forward ledger")
        rows.append(
            {
                "instrument": f["instrument"],
                "session": f["reference_session"],
                "horizon": f["horizon"],
                "model_version": f["model_version"],
                "p_up": f["p_up"],
                "selected": f["signal"] in {"up", "not_up"},
                "label": outcome["label"],
                "direction": outcome["direction"],
                "return_basis": f["return_basis"],
            }
        )
    if not rows:
        return {
            "status": "waiting",
            "reason": "No real prospective forecasts with matured outcomes.",
            "scorecards": [],
        }
    frame = pd.DataFrame(rows)
    scorecards = []
    for (instrument, horizon, version), group in frame.groupby(["instrument", "horizon", "model_version"]):
        metrics = score(group, group.p_up.to_numpy(), group.selected.to_numpy())
        metrics.update(
            stage="forward",
            instrument=instrument,
            horizon=int(horizon),
            model_version=version,
            scope="company" if group.return_basis.iloc[0] == "adjusted_price" else "index",
            public_support=bool(
                group.return_basis.iloc[0] != "adjusted_price"
                or (len(group) >= 200 and group.session.nunique() >= 100)
            ),
            corrections=sum(bool(o["correction_of"]) for o in outcomes.values()),
        )
        scorecards.append(metrics)
    return {"status": "completed", "scorecards": scorecards, "matured": len(rows)}
