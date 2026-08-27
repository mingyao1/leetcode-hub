"""Main fetch entrypoint. Reads users.json, hits each region's API, writes
public/data.json and cache/problems.json. Run by CI (.github/workflows/update.yml)
and locally for testing. See BUILD.md Phase 1.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib import merge, streaks
from lib.leetcode import LeetCodeAPIError, get_client

ROOT = Path(__file__).parent.parent
USERS_PATH = ROOT / "users.json"
DATA_PATH = ROOT / "public" / "data.json"
PROBLEMS_CACHE_PATH = ROOT / "cache" / "problems.json"

SLEEP_BETWEEN_USERS = 1.5

CN_ONLY_PREFIXES = ("LCP", "LCR", "LCS", "剑指", "面试题")


def load_json(path, default):
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def is_cn_only_slug(slug):
    return slug.startswith(CN_ONLY_PREFIXES)


def enrich_problem(slug, client, cache):
    """Look up slug in cache; on miss, fetch and write back. Returns the
    cache entry (title/difficulty/paid_only/cn_only)."""
    if slug in cache:
        return cache[slug]

    if is_cn_only_slug(slug):
        entry = {"title": slug, "difficulty": None, "paid_only": False, "cn_only": True}
        cache[slug] = entry
        return entry

    question = client.fetch_question(slug)
    if question is None:
        # US metadata lookup returned null for this slug -> no leetcode.com
        # equivalent, treat as CN-only per BUILD.md Phase 1.
        entry = {"title": slug, "difficulty": None, "paid_only": False, "cn_only": True}
    else:
        entry = {
            "title": question["title"],
            "difficulty": question["difficulty"],
            "paid_only": question["paid_only"],
            "cn_only": False,
        }
    cache[slug] = entry
    return entry


def fetch_one_user(user, client, problems_cache):
    result = client.fetch_user_and_recent(user["handle"])
    by_date = streaks.parse_calendar(result["submission_calendar"])

    fresh = {
        "solved": result["solved"],
        "streak": streaks.compute_streak(by_date),
        "solved_last_7d": streaks.compute_solved_last_7d(by_date),
        "active_today": streaks.compute_active_today(by_date),
    }

    feed_items = []
    for sub in result["recent"]:
        meta = enrich_problem(sub["slug"], client, problems_cache)
        feed_items.append(
            {
                "handle": user["handle"],
                "display_name": user["display_name"],
                "region": user["region"],
                "slug": sub["slug"],
                "title": meta["title"] or sub["title"],
                "difficulty": meta["difficulty"],
                "paid_only": meta["paid_only"],
                "cn_only": meta["cn_only"],
                "url": client.problem_url(sub["slug"]),
                "timestamp": sub["timestamp"],
            }
        )

    return fresh, feed_items


def main():
    users = load_json(USERS_PATH, [])
    previous_data = load_json(DATA_PATH, None)
    problems_cache = load_json(PROBLEMS_CACHE_PATH, {})

    now = datetime.now(tz=timezone.utc)

    user_entries = []
    new_feed_items = []

    for i, user in enumerate(users):
        if i > 0:
            time.sleep(SLEEP_BETWEEN_USERS)

        handle = user["handle"]
        region = user["region"]
        display_name = user["display_name"]

        try:
            client = get_client(region)
            fresh, feed_items = fetch_one_user(user, client, problems_cache)
            user_entries.append(merge.build_user_entry(display_name, handle, region, fresh, now))
            new_feed_items.extend(feed_items)
            print(f"OK   {region}/{handle}: total={fresh['solved']['total']} streak={fresh['streak']}")
        except Exception as exc:
            previous_entry = merge.previous_user_entry(previous_data, handle, region)
            user_entries.append(
                merge.carry_forward_user_entry(display_name, handle, region, previous_entry, str(exc), now)
            )
            print(f"FAIL {region}/{handle}: {exc}")

    feed = merge.merge_feed(previous_data, new_feed_items, now)

    daily = None
    us_users = [u for u in users if u["region"] == "us"]
    if us_users:
        try:
            daily = get_client("us").fetch_daily_challenge()
        except LeetCodeAPIError as exc:
            print(f"FAIL daily challenge: {exc}")
            if previous_data:
                daily = previous_data.get("daily")

    data = {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "timezone": streaks.TIMEZONE,
        "daily": daily,
        "users": user_entries,
        "feed": feed,
    }

    save_json(DATA_PATH, data)
    save_json(PROBLEMS_CACHE_PATH, problems_cache)

    print(f"\nWrote {DATA_PATH} ({len(user_entries)} users, {len(feed)} feed items)")
    print(f"Wrote {PROBLEMS_CACHE_PATH} ({len(problems_cache)} problems cached)")


if __name__ == "__main__":
    main()
