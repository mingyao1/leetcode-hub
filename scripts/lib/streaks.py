"""Calendar -> streak math. See BUILD.md Phase 1 and §7 gotchas.

submissionCalendar is a JSON string mapping unix-second timestamps to
submission counts. We bucket each timestamp into a date in TIMEZONE
(not UTC — the US API buckets by UTC day, which puts evening Eastern
solves on the wrong day) and walk backward from today.
"""

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TIMEZONE = "America/New_York"
_TZ = ZoneInfo(TIMEZONE)


def parse_calendar(submission_calendar_json):
    """submissionCalendar JSON string -> {date: count}.

    Each key is midnight UTC of the day LeetCode recorded the submission
    on -- a day marker, not an actual instant. Reconverting that marker
    through TIMEZONE shifts every entry back by up to a day (midnight UTC
    is always still "yesterday evening" in a behind-UTC zone like
    Eastern), so we read the date in UTC as given rather than reconverting
    it. See apply_precise_recent() for how the near-term days that
    streak/active_today actually depend on get corrected to TIMEZONE.
    """
    raw = json.loads(submission_calendar_json)
    by_date = {}
    for ts_str, count in raw.items():
        date = datetime.fromtimestamp(int(ts_str), tz=timezone.utc).date()
        by_date[date] = by_date.get(date, 0) + count
    return by_date


def apply_precise_recent(by_date, recent):
    """Overlay by_date with exact per-submission timestamps from
    recentAcSubmissionList, bucketed by TIMEZONE day boundaries.

    The calendar only gives UTC-day granularity, which can put a
    submission on the wrong side of "today" near the UTC/TIMEZONE
    boundary (BUILD.md's 'evening solve lands on the next UTC day'
    gotcha). recentAcSubmissionList carries exact instants for the ~20
    most recent submissions -- precise enough to fix the near-term days
    that streak, active_today, and solved_last_7d depend on.
    """
    if not recent:
        return dict(by_date)

    precise = {}
    for sub in recent:
        date = datetime.fromtimestamp(sub["timestamp"], tz=_TZ).date()
        precise[date] = precise.get(date, 0) + 1

    lo = min(precise) - timedelta(days=1)
    hi = max(precise) + timedelta(days=1)

    merged = {d: c for d, c in by_date.items() if not (lo <= d <= hi)}
    merged.update(precise)
    return merged


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
