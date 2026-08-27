"""Calendar -> streak math. See BUILD.md Phase 1 and §7 gotchas.

submissionCalendar is a JSON string mapping unix-second timestamps to
submission counts. We bucket each timestamp into a date in TIMEZONE
(not UTC — the US API buckets by UTC day, which puts evening Eastern
solves on the wrong day) and walk backward from today.
"""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TIMEZONE = "America/New_York"
_TZ = ZoneInfo(TIMEZONE)


def parse_calendar(submission_calendar_json):
    """submissionCalendar JSON string -> {date: count} in TIMEZONE."""
    raw = json.loads(submission_calendar_json)
    by_date = {}
    for ts_str, count in raw.items():
        dt = datetime.fromtimestamp(int(ts_str), tz=_TZ)
        date = dt.date()
        by_date[date] = by_date.get(date, 0) + count
    return by_date


def compute_streak(by_date, today=None):
    """Consecutive days with a nonzero count, walking back from today.

    Today does not break a streak: if today has no submissions but
    yesterday does, the streak is still alive. Only a gap that ends
    before yesterday breaks it.
    """
    if today is None:
        today = datetime.now(tz=_TZ).date()

    cursor = today
    if by_date.get(today, 0) == 0:
        cursor = today - timedelta(days=1)

    streak = 0
    while by_date.get(cursor, 0) > 0:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def compute_active_today(by_date, today=None):
    if today is None:
        today = datetime.now(tz=_TZ).date()
    return by_date.get(today, 0) > 0


def compute_solved_last_7d(by_date, today=None):
    """Sum of submission-active-day counts over the trailing 7 days
    (today inclusive). Note: this counts calendar activity, not unique
    problems solved — that's what the calendar gives us."""
    if today is None:
        today = datetime.now(tz=_TZ).date()
    total = 0
    for i in range(7):
        total += by_date.get(today - timedelta(days=i), 0)
    return total
