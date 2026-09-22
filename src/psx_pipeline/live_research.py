"""Daily experimental index estimates. Separate from validated production signals."""

import argparse
import hashlib
import json
import math
import time
from datetime import date, datetime, timedelta, timezone
from datetime import time as daytime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import calibrate, calibrated, predict_model
from .snapshot_research import BASIC, available_history, fit_candidate, make_features, training_blocks
from .storage import digest, write_json

URL = "https://dps.psx.com.pk/timeseries/eod/KSE100"
PK = ZoneInfo("Asia/Karachi")
UTC = timezone.utc


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Observation(StrictModel):
    target_session: date
    up: bool
    correct: bool


class Estimate(StrictModel):
    horizon: Literal[1, 5]
    reference_session: date
    issued_at: datetime
    update_due_at: datetime
    p_up: float = Field(ge=0, le=1)
    p_not_up: float = Field(ge=0, le=1)
    baseline_up: float = Field(ge=0, le=1)
    model_version: str
    reference_hash: str
    outcome: Observation | None = None

    @model_validator(mode="after")
    def check(self):
        if abs(self.p_up + self.p_not_up - 1) > 1e-10:
            raise ValueError("Complementary probabilities required")
        if self.issued_at.tzinfo is None or self.update_due_at.tzinfo is None:
            raise ValueError("Timezone required")
        if self.update_due_at <= self.issued_at:
            raise ValueError("Forecast must be issued before its update deadline")
        return self


class ResearchFeed(StrictModel):
    schema_version: Literal["research-live-v1"] = "research-live-v1"
    mode: Literal["experimental"] = "experimental"
    instrument: Literal["KSE100"] = "KSE100"
    generated_at: datetime
    reference_session: date
    source_url: Literal["https://dps.psx.com.pk/"] = "https://dps.psx.com.pk/"
    model_name: Literal["Logistic regression + recent-frequency blend"] = (
        "Logistic regression + recent-frequency blend"
    )
    validation: Literal["No demonstrated forecasting advantage"] = "No demonstrated forecasting advantage"
    calendar_status: Literal["Weekday update schedule only; exchange holidays unverified"] = (
        "Weekday update schedule only; exchange holidays unverified"
    )
    forecast_basis: Literal["Direction over next recorded closing observations; index basis under review"] = (
        "Direction over next recorded closing observations; index basis under review"
    )
    forecasts: list[Estimate] = Field(min_length=2, max_length=2)
    history: list[Estimate] = Field(max_length=1000)

    @model_validator(mode="after")
    def check(self):
        if self.generated_at.tzinfo is None:
            raise ValueError("Timezone required")
        if sorted(f.horizon for f in self.forecasts) != [1, 5]:
            raise ValueError("Both horizons required")
        if any(
            f.reference_session != self.reference_session or f.issued_at > self.generated_at
            for f in self.forecasts
        ):
            raise ValueError("Invalid current forecast references")
        keys = [(f.reference_session, f.horizon) for f in self.history]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate history")
        return self


def parse_eod(payload, now):
    values = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(values, list) or not values:
        raise ValueError("PSX response has no EOD rows")
    rows = {}
    for row in values:
        if not isinstance(row, list) or len(row) < 3:
            raise ValueError("Unexpected PSX EOD schema")
        stamp, close, volume = map(float, row[:3])
        if not all(math.isfinite(v) for v in [stamp, close, volume]) or close <= 0 or volume < 0:
            raise ValueError("Invalid PSX prices or volume")
        session = datetime.fromtimestamp(stamp, UTC).astimezone(PK).date()
        if session > now.astimezone(PK).date() or session.weekday() >= 5:
            raise ValueError("Future or weekend source date requires review")
        record = {"date": pd.Timestamp(session), "close": close, "volume": volume}
        if session in rows and rows[session] != record:
            raise ValueError("Conflicting duplicate source rows")
        rows[session] = record
    result = pd.DataFrame(rows.values()).sort_values("date").reset_index(drop=True)
    if len(result) < 500:
        raise ValueError("At least 500 source observations required")
    if result.date.diff().dt.days.dropna().max() > 14:
        raise ValueError("Large source-date gap requires review")
    latest = result.date.iloc[-1].date()
    local = now.astimezone(PK)
    if latest == local.date() and local.hour < 18:
        raise ValueError("Wait until after closing-data finalization")
    if (local.date() - latest).days > 4:
        raise ValueError("Source data is too old")
    return result


def fetch_eod(now):
    error = None
    for attempt in range(3):
        try:
            response = httpx.get(URL, timeout=25, headers={"User-Agent": "KSE100Research/1.0"})
            response.raise_for_status()
            if len(response.content) > 2_000_000:
                raise ValueError("Source response too large")
            return parse_eod(response.json(), now)
        except (httpx.HTTPError, ValueError) as exc:
            error = exc
            if attempt < 2:
                time.sleep(2**attempt)
    raise ValueError(f"PSX update failed: {type(error).__name__}") from error


def deadline(reference):
    day = reference + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, daytime(19, 45), PK).astimezone(UTC)


def close_hash(value):
    return hashlib.sha256(format(float(value), ".10g").encode()).hexdigest()


def build_feed(raw, now, previous=None):
    reference = raw.date.iloc[-1].date()
    due = deadline(reference)
    if now >= due:
        raise ValueError("No fresh closing session; keep prior forecasts labelled stale")
    history = list(previous.history) if previous else []
    if previous and previous.reference_session > reference:
        raise ValueError("Refusing source rollback")
    known = {(f.reference_session, f.horizon): f for f in history}
    config = yaml.safe_load(Path("config/snapshot_research.yaml").read_text())
    forecasts = []
    for horizon in [1, 5]:
        key = (reference, horizon)
        if key in known:
            forecasts.append(known[key])
            continue
        frame = make_features(raw, horizon)
        origin = frame.session.iloc[-1]
        fit, calibration = training_blocks(frame, origin, config)
        model = fit_candidate("logistic_basic", fit, {"logistic_basic": BASIC})
        sigmoid = calibrate(model, calibration)
        recent = float(available_history(frame, origin).tail(config["recent_baseline_dates"]).label.mean())
        probability = 0.5 * float(calibrated(model, sigmoid, frame.tail(1))[0]) + 0.5 * recent
        # No model coefficients or source closing values enter the public feed.
        assert math.isfinite(float(predict_model(model, frame.tail(1))[0]))
        estimate = Estimate(
            horizon=horizon,
            reference_session=reference,
            issued_at=now,
            update_due_at=due,
            p_up=probability,
            p_not_up=1 - probability,
            baseline_up=recent,
            model_version="research-"
            + digest({"model": model, "calibrator": sigmoid, "baseline": recent})[:16],
            reference_hash=close_hash(raw.close.iloc[-1]),
        )
        history.append(estimate)
        forecasts.append(estimate)
    positions = {d.date(): i for i, d in enumerate(raw.date)}
    for estimate in history:
        position = positions.get(estimate.reference_session)
        if estimate.outcome is not None or position is None or position + estimate.horizon >= len(raw):
            continue
        if close_hash(raw.close.iloc[position]) != estimate.reference_hash:
            continue  # A revised reference close must not silently rewrite evaluation.
        target = raw.iloc[position + estimate.horizon]
        # An actual issued forecast must precede the outcome session; no retrospective scoring.
        if estimate.issued_at.astimezone(PK).date() >= target.date.date():
            continue
        up = bool(target.close > raw.close.iloc[position])
        estimate.outcome = Observation(
            target_session=target.date.date(), up=up, correct=(estimate.p_up >= 0.5) == up
        )
    history.sort(key=lambda f: (f.reference_session, f.horizon))
    return ResearchFeed(
        generated_at=now, reference_session=reference, forecasts=forecasts, history=history[-1000:]
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--previous")
    args = parser.parse_args()
    now = datetime.now(UTC)
    previous = None
    if args.previous and Path(args.previous).exists():
        previous = ResearchFeed.model_validate_json(Path(args.previous).read_text())
    raw = fetch_eod(now)
    feed = build_feed(raw, now, previous)
    write_json(args.output, feed.model_dump(mode="json"))
    print(
        json.dumps(
            {
                "status": "completed",
                "reference": str(feed.reference_session),
                "forecast_count": 2,
                "history_count": len(feed.history),
                "mode": feed.mode,
            }
        )
    )


if __name__ == "__main__":
    main()
