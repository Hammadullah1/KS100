"""Gated adapters. An HTML error with HTTP 200 is never a successful observation."""

import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol

import httpx
import yaml

from .contracts import TABLES, Macro
from .storage import digest, read_json


class SourceBlocked(ValueError):
    pass


class Adapter(Protocol):
    def fetch(self, start: date, end: date) -> list[dict]: ...


def registry(path="config/sources.yaml"):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))["sources"]


def require(source, uses, live=False, registry_path="config/sources.yaml"):
    row = registry(registry_path).get(source)
    if not row:
        raise SourceBlocked("unregistered source")
    if date.fromisoformat(row["review_expires"]) < datetime.now(timezone.utc).date():
        raise SourceBlocked("source audit expired")
    if not row.get("evidence_url") or not row.get("reviewed_at"):
        raise SourceBlocked("missing permission evidence")
    for use in uses:
        if row["permissions"].get(use) != "approved":
            raise SourceBlocked(f"{source}: {use} permission unverified")
    if live and not row["enabled"]:
        raise SourceBlocked(f"{source}: live adapter disabled")
    return row


class ManualAdapter:
    def __init__(self, source, table, registry_path="config/sources.yaml"):
        self.source, self.table, self.registry_path = source, table, registry_path

    def read(self, path):
        require(self.source, ["private_storage", "training"], registry_path=self.registry_path)
        data = read_json(path)
        if not isinstance(data, list):
            raise ValueError("normalized import must be a JSON array")
        rows = [TABLES[self.table].model_validate(r).model_dump(mode="json") for r in data]
        if any((r.get("source", self.source) != self.source) or r.get("fixture") for r in rows):
            raise ValueError("import source/fixture mismatch")
        return rows


class DisabledAdapter:
    def __init__(self, source, table):
        self.source, self.table = source, table

    def fetch(self, start, end):
        raise SourceBlocked(
            f"{self.source}: approved live endpoint unavailable; use documented manual import"
        )


def get_json(url, params, client=None, sleep=time.sleep):
    # Never log a request URL or exception body: a provider key may be embedded.
    own = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=False)
    try:
        for attempt in range(3):
            try:
                with client.stream("GET", url, params=params) as response:
                    if response.status_code in {429, 500, 502, 503, 504}:
                        if attempt == 2:
                            raise ValueError("source retry limit")
                        delay = min(30, max(2**attempt, float(response.headers.get("Retry-After", "0"))))
                        sleep(delay)
                        continue
                    if response.status_code != 200:
                        raise ValueError(f"source HTTP {response.status_code}")
                    if "json" not in response.headers.get("content-type", "").lower():
                        raise ValueError("source returned non-JSON")
                    chunks = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 5_000_000:
                            raise ValueError("download cap exceeded")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    return json.loads(raw), digest(raw)
            except httpx.TransportError:
                if attempt == 2:
                    raise ValueError("source network failure") from None
                sleep(2**attempt)
        raise ValueError("source retry limit")
    finally:
        if own:
            client.close()


class EIAAdapter:
    def fetch(self, start, end):
        row = require("eia", ["collection", "private_storage", "training"], live=True)
        key = os.environ.get("EIA_API_KEY")
        if not key:
            raise SourceBlocked("EIA_API_KEY missing")
        if (end - start).days > 370:
            raise ValueError("incremental window limited to 370 days")
        data, sha = get_json(
            row["endpoint"],
            {"api_key": key, "start": start.isoformat(), "end": end.isoformat(), "length": 5000},
        )
        return self.parse(data, sha, datetime.now(timezone.utc), start, end)

    @staticmethod
    def parse(payload, sha, received, start, end):
        response = payload.get("response", {})
        data = response.get("data")
        if not isinstance(data, list) or not data:
            raise ValueError("EIA response shape changed or empty")
        if int(response.get("total", len(data))) > len(data):
            raise ValueError("truncated EIA response")
        out = []
        for r in data:
            period = date.fromisoformat(r["period"])
            if not start <= period <= end:
                continue
            value = r.get("value")
            if r.get("series") not in {"RBRTE", "PET.RBRTE.D"}:
                raise ValueError("unexpected EIA series")
            if r.get("units") not in {"Dollars per Barrel", "$/BBL"}:
                raise ValueError("unexpected Brent units")
            out.append(
                Macro(
                    source="eia",
                    series="PET.RBRTE.D",
                    reference_period=period,
                    value=float(value) if value is not None else None,
                    units="USD/barrel",
                    available_at=received,
                    ingested_at=received,
                    vintage=received.isoformat(),
                    payload_hash=sha,
                ).model_dump(mode="json")
            )
        if not out:
            raise ValueError("no EIA observations in requested range")
        return out


ADAPTERS = {
    "psx": DisabledAdapter("psx", "bars"),
    "corporate_actions": DisabledAdapter("corporate_actions", "actions"),
    "membership": DisabledAdapter("membership", "membership"),
    "sbp": DisabledAdapter("sbp", "macro"),
    "fred": DisabledAdapter("fred", "macro"),
    "nccpl": DisabledAdapter("nccpl", "flows"),
    "pbs": DisabledAdapter("pbs", "macro"),
    "disclosures": DisabledAdapter("disclosures", "events"),
    "eia": EIAAdapter(),
}
