"""Resilient merge with the previous public/data.json. A single bad handle
must never blank the board — carry the previous entry forward on failure
instead. See BUILD.md Phase 1 'Resilience'.
"""

from datetime import datetime, timedelta, timezone

STALE_AFTER = timedelta(hours=12)
FEED_WINDOW = timedelta(days=30)


def previous_user_entry(previous_data, handle, region):
    if not previous_data:
        return None
    for entry in previous_data.get("users", []):
        if entry["handle"] == handle and entry["region"] == region:
            return entry
    return None


def build_user_entry(display_name, handle, region, fresh_result, now):
    """fresh_result: dict with solved/streak/solved_last_7d/active_today, or
    None if the fetch failed. On failure, caller must pass the previous
    entry as fresh_result=None and handle carry-forward separately.
    """
    now_iso = now.isoformat().replace("+00:00", "Z")
    return {
        "display_name": display_name,
        "handle": handle,
        "region": region,
        "solved": fresh_result["solved"],
        "streak": fresh_result["streak"],
        "solved_last_7d": fresh_result["solved_last_7d"],
        "active_today": fresh_result["active_today"],
        "last_fetched": now_iso,
        "stale": False,
        "error": None,
    }


def carry_forward_user_entry(display_name, handle, region, previous_entry, error, now):
    if previous_entry is None:
        return {
            "display_name": display_name,
            "handle": handle,
            "region": region,
            "solved": {"easy": 0, "medium": 0, "hard": 0, "total": 0},
            "streak": 0,
            "solved_last_7d": 0,
            "active_today": False,
            "last_fetched": None,
            "stale": True,
            "error": error,
        }

    last_fetched = previous_entry["last_fetched"]
    stale = True
    if last_fetched:
        fetched_dt = datetime.fromisoformat(last_fetched.replace("Z", "+00:00"))
        stale = (now - fetched_dt) > STALE_AFTER

    return {
        "display_name": display_name,
        "handle": handle,
        "region": region,
        "solved": previous_entry["solved"],
        "streak": previous_entry["streak"],
        "solved_last_7d": previous_entry["solved_last_7d"],
        "active_today": previous_entry["active_today"],
        "last_fetched": last_fetched,
        "stale": stale,
        "error": error,
    }


def merge_feed(previous_data, new_feed_items, now):
    """Union of previous feed and this run's, deduped on (handle, slug,
    timestamp), trimmed to the last 30 days, sorted newest first."""
    previous_feed = previous_data.get("feed", []) if previous_data else []
    combined = {}
    for item in previous_feed + new_feed_items:
        key = (item["handle"], item["slug"], item["timestamp"])
        combined[key] = item

    cutoff = now - FEED_WINDOW
    cutoff_ts = cutoff.timestamp()
    items = [item for item in combined.values() if item["timestamp"] >= cutoff_ts]
    items.sort(key=lambda item: item["timestamp"], reverse=True)
    return items
