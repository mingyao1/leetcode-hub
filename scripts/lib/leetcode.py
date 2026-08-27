"""GraphQL clients for LeetCode regions. One class per region; all
region-specific field names and URLs live here. Nothing above this layer
should know which site a user is on except for building URLs.

Only USClient is implemented. CN support is deferred — see docs/api-notes.md.
The CN query shapes there are unverified guesses; do not implement CNClient
from them without re-running scripts/probe.py against a real leetcode.cn
handle first.
"""

import requests

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class LeetCodeAPIError(Exception):
    pass


class USClient:
    """leetcode.com GraphQL client. Field names confirmed in Phase 0 (docs/api-notes.md)."""

    region = "us"
    graphql_url = "https://leetcode.com/graphql/"
    problem_url_template = "https://leetcode.com/problems/{slug}/"

    _COMBINED_QUERY = """
    query($username: String!) {
      matchedUser(username: $username) {
        username
        submitStatsGlobal { acSubmissionNum { difficulty count } }
        userCalendar { submissionCalendar }
      }
      recentAcSubmissionList(username: $username, limit: 20) { id title titleSlug timestamp }
    }
    """

    _QUESTION_QUERY = """
    query($titleSlug: String!) {
      question(titleSlug: $titleSlug) { questionFrontendId title titleSlug difficulty isPaidOnly }
    }
    """

    _DAILY_QUERY = """
    query { activeDailyCodingChallengeQuestion { date link question { title titleSlug difficulty } } }
    """

    def __init__(self, session=None):
        self._session = session or requests.Session()

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
            "Referer": "https://leetcode.com/",
            "Origin": "https://leetcode.com",
        }

    def _post(self, query, variables):
        resp = self._session.post(
            self.graphql_url,
            headers=self._headers(),
            json={"query": query, "variables": variables},
            timeout=15,
        )
        if resp.status_code != 200:
            raise LeetCodeAPIError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        body = resp.json()
        if body.get("errors"):
            raise LeetCodeAPIError(str(body["errors"]))
        return body["data"]

    def fetch_user_and_recent(self, handle, limit=20):
        """Combined profile + calendar + recent submissions in one request.

        Returns dict with keys: solved (easy/medium/hard/total),
        submission_calendar (raw JSON string), recent (list of dicts).
        Raises LeetCodeAPIError if the handle doesn't resolve.
        """
        data = self._post(self._COMBINED_QUERY, {"username": handle})
        matched = data.get("matchedUser")
        if matched is None:
            raise LeetCodeAPIError(f"handle '{handle}' did not resolve (matchedUser is null)")

        counts = {"easy": 0, "medium": 0, "hard": 0}
        for row in matched["submitStatsGlobal"]["acSubmissionNum"]:
            difficulty = row["difficulty"].lower()
            if difficulty in counts:
                counts[difficulty] = row["count"]
        counts["total"] = counts["easy"] + counts["medium"] + counts["hard"]

        recent = [
            {
                "slug": item["titleSlug"],
                "title": item["title"],
                "timestamp": int(item["timestamp"]),
            }
            for item in data.get("recentAcSubmissionList", [])[:limit]
        ]

        return {
            "solved": counts,
            "submission_calendar": matched["userCalendar"]["submissionCalendar"],
            "recent": recent,
        }

    def fetch_question(self, slug):
        data = self._post(self._QUESTION_QUERY, {"titleSlug": slug})
        question = data.get("question")
        if question is None:
            return None
        return {
            "title": question["title"],
            "difficulty": question["difficulty"],
            "paid_only": bool(question["isPaidOnly"]),
        }

    def problem_url(self, slug):
        return self.problem_url_template.format(slug=slug)

    def fetch_daily_challenge(self):
        data = self._post(self._DAILY_QUERY, {})
        challenge = data["activeDailyCodingChallengeQuestion"]
        question = challenge["question"]
        slug = question["titleSlug"]
        return {
            "date": challenge["date"],
            "title": question["title"],
            "slug": slug,
            "difficulty": question["difficulty"],
            "url": self.problem_url(slug),
        }


def get_client(region):
    if region == "us":
        return USClient()
    if region == "cn":
        raise NotImplementedError(
            "CN support is deferred — see docs/api-notes.md. "
            "Re-run scripts/probe.py against a real leetcode.cn handle before implementing CNClient."
        )
    raise ValueError(f"unknown region: {region!r}")
