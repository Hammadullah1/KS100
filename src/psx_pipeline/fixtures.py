"""Reproducible synthetic test data, isolated from all production commands."""

from datetime import date, datetime, timedelta, timezone

import numpy as np

from .storage import digest


def make_fixture(count=1250):
    rng = np.random.default_rng(731)
    start = date(2019, 1, 1)
    day = start
    sessions = []
    bars = []
    price = 100.0
    opened = 0
    while opened < count + 6:
        is_open = day.weekday() < 5 and not (day.month == 1 and day.day == 10)
        dt = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        # Friday and special-closure behavior are synthetic, not asserted PSX hours.
        close = dt + timedelta(hours=11 if day.weekday() == 4 else 10)
        sessions.append(
            {
                "date": str(day),
                "is_open": is_open,
                "opens_at": (dt + timedelta(hours=4)).isoformat() if is_open else None,
                "closes_at": close.isoformat() if is_open else None,
                "update_due_at": (close + timedelta(hours=3)).isoformat() if is_open else None,
                "evidence": "SYNTHETIC CALENDAR; not exchange history",
                "published_at": "2018-01-01T00:00:00Z",
                "fixture": True,
            }
        )
        if is_open:
            if opened < count:
                old = price
                change = float(rng.normal(0, 0.008))
                price *= 1 + change
                if opened % 37 == 0:
                    price = old
                receipt = close + timedelta(minutes=30)
                bar = {
                    "source": "fixture",
                    "available_at": receipt.isoformat(),
                    "ingested_at": receipt.isoformat(),
                    "published_at": receipt.isoformat(),
                    "vintage": "synthetic-v1",
                    "payload_hash": digest(f"synthetic-{opened}"),
                    "fixture": True,
                    "instrument": "TEST:INDEX:TR",
                    "session": str(day),
                    "basis": "official_total_return",
                    "units": "index_points",
                    "status": "final",
                    "open": old,
                    "close": price,
                    "high": max(old, price) * 1.002,
                    "low": min(old, price) * 0.998,
                    "volume": float(1000 + opened % 41),
                }
                bars.append(bar)
            opened += 1
        day += timedelta(days=1)
    return {
        "instruments": [
            {
                "id": "TEST:INDEX:TR",
                "symbol": "TEST",
                "name": "Synthetic test index",
                "kind": "index",
                "return_basis": "official_total_return",
                "currency": "PKR",
                "source": "fixture",
                "sector": None,
            }
        ],
        "sessions": sessions,
        "bars": bars,
        "actions": [],
        "membership": [],
        "macro": [],
        "flows": [],
        "events": [],
    }
