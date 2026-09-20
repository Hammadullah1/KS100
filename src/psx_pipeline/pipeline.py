from pathlib import Path

import pandas as pd

from .adapters import require
from .calendar import ExchangeCalendar
from .contracts import Forecast, Outcome, utcnow
from .data import build_feature, label_for, latest, stamp, validate_dataset
from .evaluation import selection_mask
from .forward import score_forward
from .models import calibrated
from .monitoring import deterioration, input_gate
from .publishing import empty_bundle
from .storage import Store, append_record, digest, forecast_key, lock, read_json, records, write_json


def authorize_dataset(tables, uses):
    sources = sorted({r["source"] for rows in tables.values() for r in rows if "source" in r})
    for source in sources:
        require(source, uses)
    return sources


def issue(root, tables, manifest, reference, cutoff, issued_at=None, fixture=False):
    issued_at = issued_at or utcnow()
    calendar = ExchangeCalendar(tables["sessions"])
    ref = calendar.get(reference, cutoff)
    next_session = calendar.advance(reference, 1, cutoff)
    if cutoff < ref.closes_at:
        raise ValueError("reference session not completed")
    if issued_at >= next_session.opens_at:
        raise ValueError("missed issuance: next session already opened")
    if manifest["fixture"] != fixture:
        raise ValueError("dataset mode mismatch")
    if not fixture:
        authorize_dataset(tables, ["private_storage", "training"])
    forward = score_forward(root, cutoff)["scorecards"] if not fixture else []
    generated = []
    with lock(root):
        existing = {forecast_key(r): r for r in records(root, "forecasts")}
        for inst in tables["instruments"]:
            for horizon in [1, 5]:
                key = f"{inst['id']}|{reference}|{horizon}|selective-v1"
                if key in existing:
                    generated.append(existing[key])
                    continue
                suffix = digest(inst["id"])[:12] if inst["kind"] == "index" else "pooled"
                candidate_path = Path(root) / f"active-{inst['kind']}-{suffix}-h{horizon}.json"
                if not candidate_path.exists():
                    continue
                candidate = read_json(candidate_path)
                if bool(candidate["fixture"]) != fixture:
                    raise ValueError("model mode mismatch")
                # Safe text/JSON artifacts are accepted only if registered with this exact checksum.
                registrations = records(root, "promotions")
                if not fixture and not any(
                    r["version"] == candidate["version"] and r["artifact_hash"] == digest(candidate)
                    for r in registrations
                ):
                    raise ValueError("unregistered or modified model artifact")
                if candidate["horizon"] != horizon or candidate["return_basis"] != inst["return_basis"]:
                    raise ValueError("target/model mismatch")
                if candidate["scope"] != inst["kind"] or (
                    inst["kind"] == "index" and candidate["instrument_ids"] != [inst["id"]]
                ):
                    raise ValueError("model belongs to a different instrument or scope")
                if candidate["last_training_label"] > reference:
                    raise ValueError("model uses labels after forecast origin")
                target = calendar.advance(reference, horizon, cutoff)
                feature = build_feature(
                    tables, inst["id"], reference, cutoff, manifest["snapshot"], fixture, calendar=calendar
                )
                gate = input_gate(feature, candidate, issued_at, next_session.update_due_at)
                for card in forward:
                    if (
                        card["model_version"] == candidate["version"]
                        and card["horizon"] == horizon
                        and card["instrument"] == inst["id"]
                        and deterioration(card, candidate["evaluation"])["pause"]
                    ):
                        gate = "forward performance deterioration; model paused pending review"
                # A late reference close is not fresh just because tomorrow's deadline is still ahead.
                if issued_at > next_session.opens_at:
                    gate = "missed issuance"
                if any(
                    a["instrument"] == inst["id"]
                    and reference < a["ex_session"] <= str(target.date)
                    and stamp(a["available_at"]) <= cutoff
                    and not a["resolved"]
                    for a in tables.get("actions", [])
                ):
                    gate = "unresolved corporate action"
                source_rows = latest(
                    [r for r in tables["bars"] if r["instrument"] == inst["id"]],
                    cutoff,
                    ["instrument", "session"],
                )
                reference_bar = next(
                    (r for r in source_rows if r["session"] == reference and r["status"] == "final"), None
                )
                if reference_bar is None:
                    gate = "reference close unavailable"
                p = (
                    float(
                        calibrated(
                            candidate["model"], candidate["calibrator"], pd.DataFrame([feature.values])
                        )[0]
                    )
                    if gate is None
                    else None
                )
                signal = "unavailable" if p is None else "no_strong_signal"
                validated = bool(candidate["evaluation"].get("high_correctness_supported")) and not fixture
                if p is not None and validated and selection_mask([p], candidate["policy"])[0]:
                    signal = "up" if p >= 0.5 else "not_up"
                reason = gate or (
                    None if signal in {"up", "not_up"} else "insufficient validated signal evidence"
                )
                f = Forecast(
                    instrument=inst["id"],
                    instrument_name=inst["name"],
                    symbol=inst["symbol"],
                    sector=inst.get("sector"),
                    target_definition=candidate["target_definition"],
                    return_basis=inst["return_basis"],
                    horizon=horizon,
                    reference_session=reference,
                    reference_close=reference_bar["close"] if reference_bar else None,
                    cutoff=cutoff,
                    issued_at=issued_at,
                    target_session=target.date,
                    next_open_at=next_session.opens_at,
                    expires_at=target.closes_at,
                    update_due_at=next_session.update_due_at,
                    p_up=p,
                    p_not_up=1 - p if p is not None else None,
                    signal=signal,
                    suppression_reason=reason,
                    validation_status="unavailable"
                    if p is None
                    else ("validated" if validated else "research"),
                    model_version=candidate["version"],
                    feature_version=feature.feature_version,
                    snapshot=manifest["snapshot"],
                    policy="selective-v1",
                    scorecard=candidate["evidence_hash"],
                    fixture=fixture,
                )
                obj = f.model_dump(mode="json")
                append_record(root, "forecasts", key, obj)
                generated.append(obj)
    if not generated:
        raise ValueError("no active trained model for requested instruments")
    return generated


def mature(root, tables, cutoff):
    added = 0
    calendar = ExchangeCalendar(tables["sessions"])
    with lock(root):
        prior = records(root, "outcomes")
        for f in records(root, "forecasts"):
            if stamp(f["issued_at"]) > cutoff:
                continue
            try:
                value = label_for(
                    tables,
                    f["instrument"],
                    f["reference_session"],
                    f["horizon"],
                    cutoff,
                    f["reference_close"],
                    calendar=calendar,
                )
            except ValueError:
                continue
            key = forecast_key(f)
            previous = [r for r in prior if r["forecast_key"] == key]
            value.pop("label_available_at")
            identity = digest({"forecast": key, "outcome": value})
            if any(
                r["vintage"] == value["vintage"] and r["target_close"] == value["target_close"]
                for r in previous
            ):
                continue
            latest_old = max(previous, key=lambda r: r["recorded_at"]) if previous else None
            obj = Outcome(
                forecast_key=key,
                recorded_at=cutoff,
                **value,
                correction_of=digest(latest_old) if latest_old else None,
            ).model_dump(mode="json")
            if append_record(root, "outcomes", identity, obj):
                added += 1
    return added


def daily(root, cutoff=None, recovery=False):
    started = utcnow()
    cutoff = cutoff or started
    run_id = started.isoformat()
    if cutoff > started:
        raise ValueError("cutoff is in the future")
    run = {
        "id": run_id,
        "started_at": started.isoformat(),
        "completed_at": None,
        "status": "running",
        "stages": {},
        "reason": None,
    }

    def save():
        with lock(root):
            write_json(Path(root) / "runs" / (digest(run_id) + ".json"), run)

    save()
    try:
        manifest, tables = Store(root).load()
        if manifest["fixture"]:
            raise ValueError("daily production run refuses fixtures")
        authorize_dataset(tables, ["private_storage", "training"])
        calendar = ExchangeCalendar(tables["sessions"])
        from zoneinfo import ZoneInfo

        today = cutoff.astimezone(ZoneInfo("Asia/Karachi")).date()
        current = calendar.get(today, cutoff)
        if not current.is_open:
            run.update(status="skipped", reason="exchange closed")
            return run
        if cutoff < current.update_due_at:
            raise ValueError("waiting for source finalization deadline")
        reference = str(today)
        marker = Path(root) / "completed" / f"{reference}.json"
        if recovery and marker.exists():
            run.update(status="skipped", reason="session already completed")
            return run
        run["stages"]["fetch"] = max(r["ingested_at"] for r in tables["bars"])
        save()
        validate_dataset(tables)
        run["stages"]["validation"] = utcnow().isoformat()
        save()
        # The manual route requires explicit data for today's completed session.
        mature(root, tables, cutoff)
        forecasts = issue(root, tables, manifest, reference, cutoff)
        run["stages"]["prediction"] = utcnow().isoformat()
        with lock(root):
            write_json(
                marker, {"reference": reference, "forecast_keys": [forecast_key(f) for f in forecasts]}
            )
        run["status"] = "completed"
    except (ValueError, FileNotFoundError, KeyError) as exc:
        run.update(status="blocked", reason=str(exc))
    finally:
        run["completed_at"] = utcnow().isoformat()
        save()
    return run


def results_bundle(root, now):
    if not (Path(root) / "dataset.json").exists():
        return empty_bundle(now), []
    manifest, tables = Store(root).load()
    if manifest["fixture"]:
        raise ValueError("public bundle refuses fixture state")
    sources = authorize_dataset(tables, ["public_derived"])
    all_forecasts = records(root, "forecasts")
    if not all_forecasts:
        return empty_bundle(now, "No forecasts have been issued."), []
    calendar = ExchangeCalendar(tables["sessions"])
    newest = max(f["reference_session"] for f in all_forecasts)
    current = [f for f in all_forecasts if f["reference_session"] == newest]
    bundle = empty_bundle(now)
    bundle.status = "ready"
    bundle.reason = None
    bundle.forecasts = current
    bundle.history = all_forecasts
    bundle.outcomes = records(root, "outcomes")
    bundle.model_versions = sorted({f["model_version"] for f in all_forecasts if f["model_version"]})
    bundle.update_due_at = min(stamp(f["update_due_at"]) for f in current)
    bundle.calendar_coverage_until = calendar.sessions[-1].closes_at
    bundle.source_session_coverage = newest
    bundle.attribution = [s for s in sources]
    bundle.metrics.extend(
        card for card in score_forward(root, now)["scorecards"] if card.get("public_support", False)
    )
    for path in sorted(Path(root).glob("active-*.json")):
        candidate = read_json(path)
        bundle.metrics.append(
            {
                **candidate["evaluation"],
                "stage": candidate["stage"],
                "scope": candidate["scope"],
                "horizon": candidate["horizon"],
                "model_version": candidate["version"],
                "baseline_brier": candidate["baseline"]["brier"],
            }
        )
    runs = [read_json(p) for p in (Path(root) / "runs").glob("*.json")]
    if runs:
        latest_run = max(runs, key=lambda r: r["started_at"])
        if latest_run["status"] in {"blocked", "failed"}:
            bundle.status = "blocked"
            bundle.reason = latest_run["reason"]
    completed = [r for r in runs if r["status"] == "completed"]
    if completed:
        last = max(completed, key=lambda r: r["completed_at"])
        bundle.stages.update({k: v for k, v in last["stages"].items() if k in bundle.stages})
    if (Path(root) / "publication.json").exists():
        bundle.stages["publication"] = read_json(Path(root) / "publication.json")["completed_at"]
    return bundle, sources
