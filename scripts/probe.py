"""Phase 0 probe: discover real API shapes for leetcode.com and leetcode.cn.

Usage:
    python scripts/probe.py --us-handle <username> [--cn-handle <userSlug>]

Issues each candidate query separately (never merged) and prints the raw
response or HTTP status/body on failure, so we know exactly which field
breaks. Exits non-zero if any query fails, but only after attempting all
of them.

Do not add new queries here based on guesses about what "should" work.
Every field this repo relies on downstream must have appeared in a real
response captured by this script.
"""

import argparse
import json
import sys
import time

import requests

HEADERS_US = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://leetcode.com/",
    "Origin": "https://leetcode.com",
}

HEADERS_CN = {
    "Content-Type": "application/json",
    "User-Agent": HEADERS_US["User-Agent"],
    "Referer": "https://leetcode.cn/",
    "Origin": "https://leetcode.cn",
}

US_URL = "https://leetcode.com/graphql/"
CN_URL = "https://leetcode.cn/graphql/"

US_QUERIES = [
    (
        "us_matched_user",
        """
        query($username: String!) {
          matchedUser(username: $username) {
            username
            submitStatsGlobal { acSubmissionNum { difficulty count } }
            userCalendar { submissionCalendar streak totalActiveDays }
          }
        }
        """,
        lambda handle: {"username": handle},
    ),
    (
        "us_recent_ac_submissions",
        """
        query($username: String!) {
          recentAcSubmissionList(username: $username, limit: 20) { id title titleSlug timestamp }
        }
        """,
        lambda handle: {"username": handle},
    ),
    (
        "us_question",
        """
        query($titleSlug: String!) {
          question(titleSlug: $titleSlug) { questionFrontendId title titleSlug difficulty isPaidOnly }
        }
        """,
        lambda handle: {"titleSlug": "two-sum"},
    ),
    (
        "us_daily_challenge",
        """
        query { activeDailyCodingChallengeQuestion { date link question { title titleSlug difficulty } } }
        """,
        lambda handle: {},
    ),
]

CN_QUERIES = [
    (
        "cn_public_profile",
        """
        query($userSlug: String!) { userProfilePublicProfile(userSlug: $userSlug) { profile { userSlug realName } } }
        """,
        lambda handle: {"userSlug": handle},
    ),
    (
        "cn_calendar",
        """
        query($userSlug: String!) { userProfileCalendar(userSlug: $userSlug) { submissionCalendar } }
        """,
        lambda handle: {"userSlug": handle},
    ),
    (
        "cn_recent_ac_submissions",
        """
        query($userSlug: String!) { recentAcSubmissions(userSlug: $userSlug, limit: 20) { submissionId question { title titleSlug } submitTime } }
        """,
        lambda handle: {"userSlug": handle},
    ),
    (
        "cn_solved_counts",
        """
        query($userSlug: String!) { userProfileUserQuestionProgressV2(userSlug: $userSlug) { numAcceptedQuestions { difficulty count } } }
        """,
        lambda handle: {"userSlug": handle},
    ),
]


def run_query(label, url, headers, query, variables):
    payload = {"query": query, "variables": variables}
    print(f"\n=== {label} ===")
    print(f"URL: {url}")
    print(f"Variables: {json.dumps(variables)}")
    start = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
    except requests.RequestException as exc:
        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.2f}s")
        print(f"REQUEST FAILED: {exc}")
        return False
    elapsed = time.time() - start
    print(f"Elapsed: {elapsed:.2f}s")
    print(f"HTTP {resp.status_code}")
    try:
        body = resp.json()
        print(json.dumps(body, indent=2, ensure_ascii=False))
    except ValueError:
        print(resp.text[:2000])
        return False

    if resp.status_code != 200:
        return False
    if isinstance(body, dict) and body.get("errors"):
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Probe leetcode.com / leetcode.cn GraphQL APIs")
    parser.add_argument("--us-handle", required=True, help="leetcode.com username")
    parser.add_argument("--cn-handle", default=None, help="leetcode.cn userSlug (optional)")
    args = parser.parse_args()

    all_ok = True

    print("################ US (leetcode.com) ################")
    for label, query, var_fn in US_QUERIES:
        ok = run_query(label, US_URL, HEADERS_US, query, var_fn(args.us_handle))
        all_ok = all_ok and ok

    if args.cn_handle:
        print("\n################ CN (leetcode.cn) ################")
        for label, query, var_fn in CN_QUERIES:
            ok = run_query(label, CN_URL, HEADERS_CN, query, var_fn(args.cn_handle))
            all_ok = all_ok and ok
    else:
        print(
            "\n################ CN (leetcode.cn) ################\n"
            "SKIPPED: no --cn-handle provided. CN queries are unverified guesses "
            "until run against a real leetcode.cn handle. See BUILD.md Phase 0."
        )

    print("\n################ SUMMARY ################")
    if args.cn_handle:
        print("All queries attempted (US + CN).")
    else:
        print("US queries attempted. CN queries SKIPPED (no handle).")
    print("OK" if all_ok else "ONE OR MORE QUERIES FAILED (see above)")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
