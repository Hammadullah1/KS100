from datetime import datetime

import numpy as np

from .calendar import ExchangeCalendar
from .contracts import TABLES, Bar, CorporateAction, Feature, Macro


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value


def latest(rows, cutoff, keys):
    found = {}
    for row in rows:
        if stamp(row["available_at"]) > cutoff:
            continue
        key = tuple(row[k] for k in keys)
        old = found.get(key)
        if old is None or stamp(row["available_at"]) > stamp(old["available_at"]):
            found[key] = row
        elif stamp(row["available_at"]) == stamp(old["available_at"]) and row != old:
            raise ValueError("ambiguous vintage ordering")
    return list(found.values())


def adjustment(action):
    a = CorporateAction.model_validate(action)
    if not a.resolved:
        raise ValueError("unresolved corporate action")
    if a.kind == "split":
        return 1 / a.ratio
    if a.kind == "bonus":
        return 1 / (1 + a.ratio)
    if a.kind == "rights":
        if a.subscription_price is None or a.previous_close is None:
            raise ValueError("incomplete rights terms")
        return (a.previous_close + a.ratio * a.subscription_price) / ((1 + a.ratio) * a.previous_close)
    return 1.0  # cash dividends excluded from company price-direction target


def adjust_close(value, day, through, actions, cutoff):
    for a in latest(actions, cutoff, ["instrument", "ex_session", "kind"]):
        if str(day) < a["ex_session"] <= str(through):
            value *= adjustment(a)
    return value


def validate_dataset(tables):
    parsed = {k: [TABLES[k].model_validate(r).model_dump(mode="json") for r in v] for k, v in tables.items()}
    calendar = ExchangeCalendar(parsed.get("sessions", []))
    seen = set()
    instruments = {r["id"]: r for r in parsed.get("instruments", [])}
    counts = {}
    for r in parsed.get("bars", []):
        b = Bar.model_validate(r)
        key = (b.instrument, b.session, b.vintage)
        if key in seen:
            raise ValueError("duplicate bar/vintage")
        seen.add(key)
        session = calendar.get(b.session)
        if not session.is_open:
            raise ValueError("bar on a closed day")
        if b.instrument not in instruments:
            raise ValueError("unknown instrument")
        inst = instruments[b.instrument]
        expected = "raw_price" if inst["kind"] == "company" else inst["return_basis"]
        if b.basis != expected:
            raise ValueError("mixed return basis")
        if b.status == "final" and b.available_at < session.closes_at:
            raise ValueError("final bar before session close")
        counts[b.status] = counts.get(b.status, 0) + 1
    # An explicit record may be missing: report, never forward-fill.
    expected = len(calendar.sessions) * len(instruments)
    return {
        "status": "passed",
        "bars": len(seen),
        "statuses": counts,
        "missing_instrument_sessions": expected - len({(a, b) for a, b, _ in seen}),
        "calendar_start": str(calendar.days[0].date),
        "calendar_end": str(calendar.days[-1].date),
        "fixture": any(r.get("fixture") for r in parsed.get("bars", [])),
    }


def macro_asof(rows, series, cutoff, max_age_days):
    eligible = [
        Macro.model_validate(r)
        for r in latest(rows, cutoff, ["series", "reference_period"])
        if r["series"] == series
    ]
    if not eligible:
        return {"value": None, "age_days": None, "missing": 1.0}
    row = max(eligible, key=lambda r: r.reference_period)
    age = (cutoff - row.available_at).total_seconds() / 86400
    if age > max_age_days or row.value is None:
        return {"value": None, "age_days": age, "missing": 1.0}
    return {"value": row.value, "age_days": age, "missing": 0.0}


def universe_asof(rows, day, cutoff, limit=20):
    items = latest(rows, cutoff, ["instrument", "index", "effective_from"])
    items = [
        r
        for r in items
        if r["effective_from"] <= str(day)
        and (r["effective_to"] is None or str(day) < r["effective_to"])
        and r["liquidity_rank"] is not None
    ]
    # Inconsistent overlapping membership is an error, not a duplicate company.
    if len({r["instrument"] for r in items}) != len(items):
        raise ValueError("overlapping membership")
    return sorted(items, key=lambda r: r["liquidity_rank"])[:limit]


def build_feature(tables, instrument, session, cutoff, snapshot, fixture=False, calendar=None):
    calendar = calendar or ExchangeCalendar(tables["sessions"])
    base = dict(
        instrument=instrument,
        session=session,
        cutoff=cutoff,
        feature_version="price-v1",
        snapshot=snapshot,
        values={},
        inputs=[],
        eligible=False,
        exclusion=None,
        fixture=fixture,
    )
    try:
        window = calendar.window(session, 21, cutoff)
        rows = {
            r["session"]: r
            for r in latest(
                [r for r in tables["bars"] if r["instrument"] == instrument],
                cutoff,
                ["instrument", "session"],
            )
        }
        selected = [rows.get(str(s.date)) for s in window]
        if any(r is None or r["status"] != "final" for r in selected):
            raise ValueError("missing or nonfinal price window")
        actions = [a for a in tables.get("actions", []) if a["instrument"] == instrument]
        prices = np.array(
            [adjust_close(r["close"], r["session"], session, actions, cutoff) for r in selected]
        )
        returns = prices[1:] / prices[:-1] - 1
        if np.max(np.abs(returns)) > 0.25:
            raise ValueError("extreme return requires reviewed correction/action")
        values = {f"return_{n}": float(prices[-1] / prices[-1 - n] - 1) for n in [1, 5, 20]}
        values["volatility_20"] = float(np.std(returns, ddof=1))
        inst = next(i for i in tables["instruments"] if i["id"] == instrument)
        if inst["kind"] == "company":
            members = universe_asof(tables.get("membership", []), session, cutoff)
            member = next((m for m in members if m["instrument"] == instrument), None)
            if member is None:
                raise ValueError("dated liquidity/membership unavailable")
            values["bank_sector"] = float(member["sector"] == "banks")
            values["exporter_exposure"] = member["exporter_exposure"] or 0.0
            values["exporter_missing"] = float(member["exporter_exposure"] is None)
        base.update(values=values, inputs=[r["payload_hash"] for r in selected], eligible=True)
    except ValueError as exc:
        base["exclusion"] = str(exc)
    return Feature(**base)


def label_for(tables, instrument, session, horizon, cutoff, reference_close=None, calendar=None):
    calendar = calendar or ExchangeCalendar(tables["sessions"])
    target = calendar.advance(session, horizon)
    if target.closes_at > cutoff:
        raise ValueError("label has not matured")
    rows = {
        r["session"]: r
        for r in latest(
            [r for r in tables["bars"] if r["instrument"] == instrument], cutoff, ["instrument", "session"]
        )
    }
    start = rows.get(str(session))
    end = rows.get(str(target.date))
    if not start or not end or start["status"] != "final" or end["status"] != "final":
        raise ValueError("outcome close unavailable")
    actions = [a for a in tables.get("actions", []) if a["instrument"] == instrument]
    # An action already effective but unreported by cutoff cannot be adjusted.
    if any(
        str(session) < a["ex_session"] <= str(target.date) and stamp(a["available_at"]) > cutoff
        for a in actions
    ):
        raise ValueError("action terms not available at label cutoff")
    denominator = adjust_close(
        reference_close if reference_close is not None else start["close"],
        session,
        target.date,
        actions,
        cutoff,
    )
    result = end["close"] / denominator - 1
    return {
        "target_session": str(target.date),
        "target_close": end["close"],
        "realized_return": result,
        "label": int(result > 0),
        "direction": "up" if result > 0 else ("down" if result < 0 else "unchanged"),
        "vintage": end["vintage"],
        "label_available_at": end["available_at"],
    }
