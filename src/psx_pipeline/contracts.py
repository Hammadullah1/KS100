"""Versioned strict contracts: no nonfinite values, naive times or extra fields."""

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

TARGETS = {
    "official_total_return": "direction:official-total-return:v1",
    "official_price_return": "direction:official-price-return:v1",
    "adjusted_price": "direction:action-adjusted-ex-dividend:v1",
}


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Provenance(Contract):
    source: str
    available_at: AwareDatetime
    ingested_at: AwareDatetime
    published_at: AwareDatetime | None = None
    availability_evidence: str | None = None
    vintage: str
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    fixture: bool = False

    @model_validator(mode="after")
    def timing(self):
        if self.published_at and self.available_at < self.published_at:
            raise ValueError("available_at precedes publication")
        if self.available_at < self.ingested_at and not self.availability_evidence:
            raise ValueError("historical availability requires evidence")
        if self.available_at > self.ingested_at:
            raise ValueError("availability cannot follow receipt")
        return self


class Instrument(Contract):
    id: str
    symbol: str
    name: str
    kind: Literal["index", "company"]
    return_basis: Literal["official_total_return", "official_price_return", "adjusted_price"]
    currency: str
    source: str
    sector: str | None = None


class Session(Contract):
    date: date
    is_open: bool
    opens_at: AwareDatetime | None
    closes_at: AwareDatetime | None
    update_due_at: AwareDatetime | None
    evidence: str
    published_at: AwareDatetime
    fixture: bool = False

    @model_validator(mode="after")
    def boundaries(self):
        if self.is_open:
            if not (self.opens_at and self.closes_at and self.update_due_at):
                raise ValueError("open sessions require boundaries")
            if not self.opens_at < self.closes_at <= self.update_due_at:
                raise ValueError("invalid session ordering")
        elif any([self.opens_at, self.closes_at, self.update_due_at]):
            raise ValueError("closed day has trading boundaries")
        return self


class Bar(Provenance):
    instrument: str
    session: date
    basis: Literal["official_total_return", "official_price_return", "raw_price"]
    units: Literal["index_points", "PKR"]
    status: Literal["final", "missing", "no_trade", "suspended", "provisional"]
    close: float | None = Field(default=None, gt=0)
    open: float | None = Field(default=None, gt=0)
    high: float | None = Field(default=None, gt=0)
    low: float | None = Field(default=None, gt=0)
    volume: float | None = Field(default=None, ge=0)
    correction_of: str | None = None

    @model_validator(mode="after")
    def prices(self):
        if self.status == "final" and self.close is None:
            raise ValueError("final close missing")
        if self.status in {"missing", "no_trade", "suspended"} and self.close is not None:
            raise ValueError("non-trading/missing close must be null")
        if any(v is not None for v in (self.open, self.high, self.low)):
            if any(v is None for v in (self.open, self.high, self.low, self.close)):
                raise ValueError("partial OHLC")
            if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
                raise ValueError("invalid OHLC")
        if self.basis.startswith("official") != (self.units == "index_points"):
            raise ValueError("unit/basis mismatch")
        return self


class CorporateAction(Provenance):
    instrument: str
    ex_session: date
    kind: Literal["split", "bonus", "rights", "cash_dividend"]
    ratio: float = Field(gt=0)
    subscription_price: float | None = Field(default=None, ge=0)
    previous_close: float | None = Field(default=None, gt=0)
    resolved: bool


class Membership(Provenance):
    instrument: str
    index: str
    effective_from: date
    effective_to: date | None
    weight: float | None = Field(default=None, ge=0, le=1)
    liquidity_rank: int | None = Field(default=None, gt=0)
    sector: str
    exporter_exposure: float | None = None


class Macro(Provenance):
    series: str
    reference_period: date
    value: float | None
    units: str


class Flow(Macro):
    participant: str
    sector: str | None = None


class Event(Provenance):
    event_id: str
    category: str
    scope: Literal["market", "sector", "company"]
    instrument: str | None = None
    sector: str | None = None
    language: Literal["en", "ur", "unknown"]
    language_confidence: float = Field(ge=0, le=1)
    source_url: str
    content_hash: str
    sentiment: float | None = Field(default=None, ge=-1, le=1)
    sentiment_confidence: float | None = Field(default=None, ge=0, le=1)
    encoder_version: str | None = None


class Feature(Contract):
    instrument: str
    session: date
    cutoff: AwareDatetime
    feature_version: str
    snapshot: str
    values: dict[str, float | None]
    inputs: list[str]
    eligible: bool
    exclusion: str | None
    fixture: bool = False


class Forecast(Contract):
    schema_version: Literal["1"] = "1"
    instrument: str
    instrument_name: str | None = None
    symbol: str | None = None
    sector: str | None = None
    target_definition: str
    return_basis: str
    horizon: Literal[1, 5]
    reference_session: date
    reference_close: float | None = Field(gt=0)
    cutoff: AwareDatetime
    issued_at: AwareDatetime
    target_session: date
    next_open_at: AwareDatetime
    expires_at: AwareDatetime
    update_due_at: AwareDatetime
    p_up: float | None = Field(ge=0, le=1)
    p_not_up: float | None = Field(ge=0, le=1)
    signal: Literal["up", "not_up", "no_strong_signal", "unavailable"]
    suppression_reason: str | None
    validation_status: Literal["research", "validated", "unavailable"]
    model_version: str | None
    feature_version: str
    snapshot: str
    policy: str
    scorecard: str | None
    fixture: bool = False

    @model_validator(mode="after")
    def consistent(self):
        if self.target_definition != TARGETS.get(self.return_basis):
            raise ValueError("target and basis mismatch")
        if not self.cutoff <= self.issued_at < self.next_open_at <= self.expires_at:
            raise ValueError("missed issuance or invalid interval")
        if self.target_session <= self.reference_session:
            raise ValueError("target must be future")
        if (self.p_up is None) != (self.p_not_up is None):
            raise ValueError("partial probabilities")
        if self.p_up is not None:
            if abs(self.p_up + self.p_not_up - 1) > 1e-10 or not self.model_version:
                raise ValueError("probability/model mismatch")
        elif self.signal != "unavailable":
            raise ValueError("missing probability requires unavailable")
        if self.signal in {"up", "not_up"}:
            if self.validation_status != "validated" or not self.scorecard or self.suppression_reason:
                raise ValueError("directional signal without evidence")
        elif not self.suppression_reason:
            raise ValueError("abstention needs a reason")
        return self


class Outcome(Contract):
    forecast_key: str
    recorded_at: AwareDatetime
    target_session: date
    target_close: float = Field(gt=0)
    realized_return: float
    label: Literal[0, 1]
    direction: Literal["up", "down", "unchanged"]
    vintage: str
    correction_of: str | None = None


class ModelRecord(Contract):
    version: str
    status: Literal["candidate", "active", "retired"]
    artifact_hash: str
    snapshot: str
    feature_version: str
    target_definition: str
    horizon: Literal[1, 5]
    trained_at: AwareDatetime
    evidence: str
    fixture: bool = False


class Run(Contract):
    id: str
    started_at: AwareDatetime
    completed_at: AwareDatetime | None
    status: Literal["running", "blocked", "failed", "completed", "skipped"]
    stages: dict[str, str]
    reason: str | None


class Bundle(Contract):
    schema_version: Literal["1"] = "1"
    mode: Literal["production", "fixture"]
    generated_at: AwareDatetime
    status: Literal["ready", "blocked", "failed"]
    reason: str | None
    update_due_at: AwareDatetime | None
    calendar_coverage_until: AwareDatetime | None
    source_session_coverage: str | None
    model_versions: list[str]
    forecasts: list[Forecast]
    metrics: list[dict]
    history: list[Forecast]
    outcomes: list[Outcome]
    drivers: list[dict]
    sources: list[dict]
    stages: dict[str, str | None]
    attribution: list[str]


TABLES = {
    "instruments": Instrument,
    "sessions": Session,
    "bars": Bar,
    "actions": CorporateAction,
    "membership": Membership,
    "macro": Macro,
    "flows": Flow,
    "events": Event,
    "features": Feature,
    "forecasts": Forecast,
    "outcomes": Outcome,
    "models": ModelRecord,
    "runs": Run,
}


def utcnow():
    return datetime.now(timezone.utc)
