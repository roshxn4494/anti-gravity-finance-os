"""TimeScopeService for strict financial date boundary resolution (Changes 10 & 14).

Ensures financial questions evaluate explicit time scopes without silently substituting
periods (e.g. 'this month' never silently defaults to 'latest month in database').
Computes data coverage indicators ('complete', 'partial', 'unknown').
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from .. import db


@dataclass
class TimeScope:
    scope_type: str  # 'current_month' | 'previous_month' | 'calendar_month' | 'rolling_30_days' | 'rolling_90_days' | 'YTD' | 'custom' | 'latest_available'
    start_date: str  # ISO yyyy-mm-dd
    end_date: str    # ISO yyyy-mm-dd
    label: str
    coverage: str    # 'complete' | 'partial' | 'unknown'
    coverage_notes: str
    is_latest_fallback: bool = False


class TimeScopeService:
    def __init__(self, reference_date: date | None = None):
        self.ref_date = reference_date or date.today()

    def get_latest_data_date(self) -> date | None:
        """Finds the latest transaction date in the database."""
        conn = db.connect()
        cur = conn.cursor()
        cur.execute("SELECT MAX(txn_date) FROM transactions")
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            try:
                return datetime.strptime(str(row[0])[:10], "%Y-%m-%d").date()
            except Exception:
                pass
        return None

    def resolve(
        self,
        scope_name: str,
        year: int | None = None,
        month: int | None = None,
        custom_start: str | None = None,
        custom_end: str | None = None,
    ) -> TimeScope:
        """Resolves date boundaries and evaluates coverage against database content."""
        s = scope_name.lower().strip()
        ref = self.ref_date
        latest_db_date = self.get_latest_data_date()

        if s == "current_month":
            start = ref.replace(day=1)
            # end is end of current month
            if ref.month == 12:
                next_month = ref.replace(year=ref.year + 1, month=1, day=1)
            else:
                next_month = ref.replace(month=ref.month + 1, day=1)
            end = next_month - timedelta(days=1)
            label = start.strftime("%B %Y")
            coverage, notes = self._check_coverage(start, end, latest_db_date)
            return TimeScope("current_month", start.isoformat(), end.isoformat(), label, coverage, notes)

        elif s == "previous_month":
            first_curr = ref.replace(day=1)
            last_prev = first_curr - timedelta(days=1)
            first_prev = last_prev.replace(day=1)
            label = first_prev.strftime("%B %Y")
            coverage, notes = self._check_coverage(first_prev, last_prev, latest_db_date)
            return TimeScope("previous_month", first_prev.isoformat(), last_prev.isoformat(), label, coverage, notes)

        elif s == "calendar_month":
            y = year or ref.year
            m = month or ref.month
            start = date(y, m, 1)
            if m == 12:
                next_m = date(y + 1, 1, 1)
            else:
                next_m = date(y, m + 1, 1)
            end = next_m - timedelta(days=1)
            label = start.strftime("%B %Y")
            coverage, notes = self._check_coverage(start, end, latest_db_date)
            return TimeScope("calendar_month", start.isoformat(), end.isoformat(), label, coverage, notes)

        elif s == "rolling_30_days":
            end = ref
            start = end - timedelta(days=30)
            label = f"Last 30 Days ({start.strftime('%d %b')} – {end.strftime('%d %b %Y')})"
            coverage, notes = self._check_coverage(start, end, latest_db_date)
            return TimeScope("rolling_30_days", start.isoformat(), end.isoformat(), label, coverage, notes)

        elif s == "rolling_90_days":
            end = ref
            start = end - timedelta(days=90)
            label = f"Last 90 Days ({start.strftime('%d %b')} – {end.strftime('%d %b %Y')})"
            coverage, notes = self._check_coverage(start, end, latest_db_date)
            return TimeScope("rolling_90_days", start.isoformat(), end.isoformat(), label, coverage, notes)

        elif s == "ytd":
            start = date(ref.year, 1, 1)
            end = ref
            label = f"YTD {ref.year}"
            coverage, notes = self._check_coverage(start, end, latest_db_date)
            return TimeScope("ytd", start.isoformat(), end.isoformat(), label, coverage, notes)

        elif s == "custom" and custom_start and custom_end:
            c_start = datetime.strptime(custom_start, "%Y-%m-%d").date()
            c_end = datetime.strptime(custom_end, "%Y-%m-%d").date()
            label = f"{custom_start} to {custom_end}"
            coverage, notes = self._check_coverage(c_start, c_end, latest_db_date)
            return TimeScope("custom", custom_start, custom_end, label, coverage, notes)

        elif s == "latest_available":
            if not latest_db_date:
                # Fallback to current month if db is empty
                return self.resolve("current_month")
            start = latest_db_date.replace(day=1)
            if latest_db_date.month == 12:
                next_m = latest_db_date.replace(year=latest_db_date.year + 1, month=1, day=1)
            else:
                next_m = latest_db_date.replace(month=latest_db_date.month + 1, day=1)
            end = next_m - timedelta(days=1)
            label = f"{start.strftime('%B %Y')} (Latest Ingested Data)"
            return TimeScope(
                "latest_available",
                start.isoformat(),
                end.isoformat(),
                label,
                "complete",
                f"Resolved to latest statement month in database ending {latest_db_date.isoformat()}.",
                is_latest_fallback=True,
            )

        # Default fallback: calendar month of ref date
        return self.resolve("calendar_month")

    def _check_coverage(self, start: date, end: date, latest_db_date: date | None) -> tuple[str, str]:
        if not latest_db_date:
            return "unknown", "No transactions ingested in database."
        if latest_db_date < start:
            return (
                "partial",
                f"Data boundary gap: Requested period starts on {start.isoformat()}, but latest ingested data is {latest_db_date.isoformat()}.",
            )
        elif latest_db_date < end:
            return (
                "partial",
                f"Partial coverage: Requested period ends on {end.isoformat()}, but statements only imported up to {latest_db_date.isoformat()}.",
            )
        else:
            return "complete", f"Complete statement coverage available through {latest_db_date.isoformat()}."


_timescope_service: TimeScopeService | None = None


def get_timescope_service() -> TimeScopeService:
    global _timescope_service
    if _timescope_service is None:
        _timescope_service = TimeScopeService()
    return _timescope_service
