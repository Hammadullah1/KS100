from datetime import date, timedelta

from .contracts import Session


class ExchangeCalendar:
    def __init__(self, rows):
        self.days = sorted([Session.model_validate(r) for r in rows], key=lambda r: r.date)
        self.by_date = {r.date: r for r in self.days}
        if not self.days:
            raise ValueError("calendar unavailable")
        if len(self.by_date) != len(self.days):
            raise ValueError("duplicate calendar date")
        if (self.days[-1].date - self.days[0].date).days + 1 != len(self.days):
            raise ValueError("calendar gap: include closed days")
        self.sessions = [r for r in self.days if r.is_open]
        self.positions = {r.date: i for i, r in enumerate(self.sessions)}

    def get(self, day, cutoff=None):
        day = date.fromisoformat(day) if isinstance(day, str) else day
        if day not in self.by_date:
            raise ValueError("unknown calendar coverage")
        row = self.by_date[day]
        if cutoff and row.published_at > cutoff:
            raise ValueError("calendar not known at cutoff")
        return row

    def advance(self, day, horizon, cutoff=None):
        start = self.get(day, cutoff)
        if not start.is_open:
            raise ValueError("reference is not exchange session")
        index = self.positions[start.date] + horizon
        if index < 0 or index >= len(self.sessions):
            raise ValueError("unknown target calendar")
        end = self.sessions[index]
        cursor = min(start.date, end.date)
        while cursor <= max(start.date, end.date):
            self.get(cursor, cutoff)
            cursor += timedelta(days=1)
        return end

    def window(self, day, count, cutoff=None):
        end = self.get(day, cutoff)
        pos = self.positions.get(end.date, -1)
        if pos < count - 1:
            raise ValueError("insufficient price history")
        return [self.get(r.date, cutoff) for r in self.sessions[pos - count + 1 : pos + 1]]
