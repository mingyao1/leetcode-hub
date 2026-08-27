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
    # Case-insensitive: real slugs are lowercase-hyphenated (e.g.
    # "lcp-01-..."), not the uppercase form the prefixes are written in.
    # This is only an optimization to skip a doomed US lookup -- actual
    # availability is always verified against both APIs regardless.
    lowered = slug.lower()
    return lowered.startswith(tuple(p.lower() for p in CN_ONLY_PREFIXES))


def enrich_problem(slug, us_client, cn_client, cache):
    """Look up slug in cache; on miss, check availability on BOTH regions
    and write back. Returns the cache entry: title/difficulty/paid_only
    plus available_on, a list of "us"/"cn" -- whichever regions the slug
    actually resolves on, checked independently of which region's user
    solved it. This is what lets the frontend show both leetcode.com and
    leetcode.cn links for a shared problem, not just the solver's own
    region's link.

    Only ever hits the network on a cache miss -- once per slug ever,
    same as before, just up to two lookups instead of one.
    """
    if slug in cache:
        return cache[slug]

    us_question = None
    if not is_cn_only_slug(slug):
        us_question = us_client.fetch_question(slug)

    cn_question = cn_client.fetch_question(slug)

    available_on = []
    if us_question is not None:
        available_on.append("us")
    if cn_question is not None:
        available_on.append("cn")

    # Prefer US metadata when both exist -- title/difficulty/paid_only are
    # treated as effectively shared across regions for a common slug; this
    # is a simplification, not something we've verified can differ.
    source = us_question or cn_question
    entry = {
        "title": source["title"] if source else slug,
        "difficulty": source["difficulty"] if source else None,
        "paid_only": source["paid_only"] if source else False,
        "available_on": available_on,
    }
    cache[slug] = entry
    return entry


def fetch_one_user(user, client, us_client, cn_client, problems_cache):
    result = client.fetch_user_and_recent(user["handle"])
    by_date = streaks.parse_calendar(result["submission_calendar"])
    by_date = streaks.apply_precise_recent(by_date, result["recent"])

    fresh = {
        "solved": result["solved"],
        "streak": streaks.compute_streak(by_date),
        "solved_last_7d": streaks.compute_solved_last_7d(by_date),
        "active_today": streaks.compute_active_today(by_date),
    }

    feed_items = []
    for sub in result["recent"]:
        meta = enrich_problem(sub["slug"], us_client, cn_client, problems_cache)
        feed_items.append(
            {
                "handle": user["handle"],
                "display_name": user["display_name"],
                "region": user["region"],
                "slug": sub["slug"],
                "title": meta["title"] or sub["title"],
                "difficulty": meta["difficulty"],
                "paid_only": meta["paid_only"],
                "url_us": us_client.problem_url(sub["slug"]) if "us" in meta["available_on"] else None,
                "url_cn": cn_client.problem_url(sub["slug"]) if "cn" in meta["available_on"] else None,
                "timestamp": sub["timestamp"],
            }
        )

    return fresh, feed_items


def main():
    users = load_json(USERS_PATH, [])
    previous_data = load_json(DATA_PATH, None)
    problems_cache = load_json(PROBLEMS_CACHE_PATH, {})

    now = datetime.now(tz=timezone.utc)

    # Instantiated once regardless of which regions users.json actually
    # contains -- problem-availability checks in enrich_problem() need
    # both, independent of which region solved a given problem.
    us_client = get_client("us")
    cn_client = get_client("cn")
    clients = {"us": us_client, "cn": cn_client}

    user_entries = []
    new_feed_items = []

    for i, user in enumerate(users):
        if i > 0:
            time.sleep(SLEEP_BETWEEN_USERS)

        handle = user["handle"]
        region = user["region"]
        display_name = user["display_name"]

        try:
            client = clients[region]
            fresh, feed_items = fetch_one_user(user, client, us_client, cn_client, problems_cache)
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
            daily = us_client.fetch_daily_challenge()
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
