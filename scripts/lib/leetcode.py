"""GraphQL clients for LeetCode regions. One class per region; all
region-specific field names and URLs live here. Nothing above this layer
should know which site a user is on except for building URLs.

Both USClient and CNClient are backed by fields confirmed live in Phase 0
-- see docs/api-notes.md. CN is served by two separate GraphQL services
with different schemas (leetcode.cn/graphql/ and leetcode.cn/graphql/noj-go/);
do not assume a new CN field lives on whichever endpoint seems obvious
without checking docs/api-notes.md or re-probing.
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


class CNClient:
    """leetcode.cn GraphQL client. Field names confirmed in Phase 0
    (docs/api-notes.md) -- served by two separate GraphQL services with
    different schemas, so this issues two requests per user rather than
    USClient's one.
    """

    region = "cn"
    graphql_url = "https://leetcode.cn/graphql/"
    noj_graphql_url = "https://leetcode.cn/graphql/noj-go/"
    problem_url_template = "https://leetcode.cn/problems/{slug}/"

    _PROFILE_QUERY = """
    query($u: String!) {
      userProfilePublicProfile(userSlug: $u) { profile { userSlug realName } }
      userProfileUserQuestionProgressV2(userSlug: $u) { numAcceptedQuestions { difficulty count } }
    }
    """

    _CALENDAR_AND_RECENT_QUERY = """
    query($u: String!) {
      userCalendar(userSlug: $u, year: null) { submissionCalendar }
      recentACSubmissions(userSlug: $u) { submitTime question { title titleSlug } }
    }
    """

    _QUESTION_QUERY = """
    query($titleSlug: String!) {
      question(titleSlug: $titleSlug) { questionFrontendId title titleSlug difficulty isPaidOnly }
    }
    """

    def __init__(self, session=None):
        self._session = session or requests.Session()

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
            "Referer": "https://leetcode.cn/",
            "Origin": "https://leetcode.cn",
        }

    def _post(self, url, query, variables):
        resp = self._session.post(
            url,
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
        """Two requests: profile+counts on the main endpoint, calendar+recent
        on noj-go. Returns the same shape as USClient.fetch_user_and_recent.
        Raises LeetCodeAPIError if the handle doesn't resolve.
        """
        profile_data = self._post(self.graphql_url, self._PROFILE_QUERY, {"u": handle})
        if profile_data.get("userProfilePublicProfile") is None:
            raise LeetCodeAPIError(f"handle '{handle}' did not resolve (userProfilePublicProfile is null)")

        counts = {"easy": 0, "medium": 0, "hard": 0}
        for row in profile_data["userProfileUserQuestionProgressV2"]["numAcceptedQuestions"]:
            difficulty = row["difficulty"].lower()
            if difficulty in counts:
                counts[difficulty] = row["count"]
        counts["total"] = counts["easy"] + counts["medium"] + counts["hard"]

        activity_data = self._post(self.noj_graphql_url, self._CALENDAR_AND_RECENT_QUERY, {"u": handle})

        recent = [
            {
                "slug": item["question"]["titleSlug"],
                "title": item["question"]["title"],
                "timestamp": int(item["submitTime"]),
            }
            for item in activity_data.get("recentACSubmissions", [])[:limit]
        ]

        return {
            "solved": counts,
            "submission_calendar": activity_data["userCalendar"]["submissionCalendar"],
            "recent": recent,
        }

    def fetch_question(self, slug):
        data = self._post(self.graphql_url, self._QUESTION_QUERY, {"titleSlug": slug})
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


def get_client(region):
    if region == "us":
        return USClient()
    if region == "cn":
        return CNClient()
    raise ValueError(f"unknown region: {region!r}")
