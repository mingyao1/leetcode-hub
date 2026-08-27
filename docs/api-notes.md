# API notes — Phase 0 findings

Captured 2026-08-27. Source of truth for Phase 1 (`scripts/lib/leetcode.py`).
Do not add fields to the fetcher that aren't confirmed here.

## US (`leetcode.com`) — CONFIRMED

Tested from both a local laptop and a GitHub Actions `ubuntu-latest` runner
(workflow run [`33037094580`](https://github.com/mingyao1/leetcode-hub/actions/runs/33037094580),
job `probe`, handle `mingyaol`). Output was identical in both environments —
no blocking, no rate limiting, no field differences.

| Purpose | Query | Status |
|---|---|---|
| Solved counts + calendar | `matchedUser(username) { submitStatsGlobal { acSubmissionNum { difficulty count } } userCalendar { submissionCalendar streak totalActiveDays } } ` | Confirmed, HTTP 200, ~0.2–0.4s |
| Recent submissions | `recentAcSubmissionList(username, limit: 20) { id title titleSlug timestamp }` | Confirmed, returns up to 20 entries |
| Problem metadata | `question(titleSlug) { questionFrontendId title titleSlug difficulty isPaidOnly }` | Confirmed |
| Daily challenge | `activeDailyCodingChallengeQuestion { date link question { title titleSlug difficulty } }` | Confirmed |

Notes for Phase 1:

- `userCalendar.submissionCalendar` is a **JSON string**, not an object — confirmed live (`"{\"1769040000\": 1, ...}"`). Must be parsed twice (outer GraphQL JSON, inner calendar JSON), per BUILD.md §7.
- `userCalendar.streak` exists in the live response (`5` for this handle) but BUILD.md §5.1 says **do not use it** — it's UTC-bucketed and diverges from the CN equivalent. Compute streak from `submissionCalendar` ourselves in `streaks.py`.
- `recentAcSubmissionList.timestamp` is a **string**, not a number (`"1787760260"`), despite looking numeric. Cast on ingest.
- `submitStatsGlobal.acSubmissionNum` includes a `"difficulty": "All"` entry alongside Easy/Medium/Hard — filter it out when building `solved.total` (sum Easy+Medium+Hard, or drop the "All" row) to avoid double counting.
- Standard headers (custom `User-Agent` + `Referer`/`Origin` set to `https://leetcode.com/`) were sufficient in both environments. No 403s observed.

## CN (`leetcode.cn`) — CONFIRMED

Tested 2026-08-27 against a real handle (`eddiehuang`) from both a laptop
and a GitHub Actions `ubuntu-latest` runner (workflow run
[`33081674221`](https://github.com/mingyao1/leetcode-hub/actions/runs/33081674221)).
Output was identical in both environments — **`leetcode.cn` is reachable
from an Azure/GitHub runner IP, no blocking, no 403s.** This resolves the
single highest-risk unknown Phase 0 exists to answer.

**Critical finding: CN is served by two separate GraphQL services with
different schemas**, not one. BUILD.md's original CN query guesses were
half right — the profile/solved-counts guesses were correct field names,
but on the wrong assumption that everything lives at one endpoint. The
calendar/recent-submissions guesses were wrong field names entirely,
which is why they failed with "cannot query field" instead of erroring
usefully. Introspection is disabled on both endpoints and error messages
never named the correct field, so the working fields below were found by
capturing leetcode.cn's own production frontend's network requests via
headless Chrome (not from docs or guessing) — see the git history for
`scripts/probe.py` around 2026-08-27 for how.

| Purpose | Endpoint | Query | Status |
|---|---|---|---|
| Profile | `https://leetcode.cn/graphql/` | `userProfilePublicProfile(userSlug) { profile { userSlug realName } }` | Confirmed. Bad handle → `null`, not an error. |
| Solved counts | `https://leetcode.cn/graphql/` | `userProfileUserQuestionProgressV2(userSlug) { numAcceptedQuestions { difficulty count } }` | Confirmed. BUILD.md flagged this as the least stable CN query historically — it happened to be correct as guessed. |
| Problem metadata | `https://leetcode.cn/graphql/` | `question(titleSlug) { questionFrontendId title titleSlug difficulty isPaidOnly }` | Confirmed — same field/shape as US, shared problem DB. |
| Calendar/streak | `https://leetcode.cn/graphql/noj-go/` | `userCalendar(userSlug, year: Int) { streak totalActiveDays submissionCalendar }` | Confirmed. **Not** `userProfileCalendar` — that field doesn't exist. Bad handle → GraphQL error `"must not be null"`, not `null` (differs from the profile endpoint). |
| Recent AC submissions | `https://leetcode.cn/graphql/noj-go/` | `recentACSubmissions(userSlug) { submissionId submitTime question { title titleSlug questionFrontendId } }` | Confirmed. Field is **`recentACSubmissions`** — capital AC, not `recentAcSubmissions`. Genuinely AC-only (unlike `recentSubmissions` on the main endpoint, which is unfiltered and includes failed attempts — do not use that field). |

Notes for Phase 1 `CNClient`:

- Two requests per user minimum (one per endpoint), each can combine its
  own fields into one request the same way US does — e.g.
  `userProfilePublicProfile` + `userProfileUserQuestionProgressV2` combine
  fine on `/graphql/`, and `userCalendar` + `recentACSubmissions` combine
  fine on `/graphql/noj-go/`. Verify the combined forms still work before
  relying on them, same rule as US.
- `userCalendar.submissionCalendar` is the same JSON-string-of-unix-timestamps
  shape as US's `submissionCalendar` — same parsing approach in `streaks.py`
  applies. `userCalendar.streak` exists but, per the same rule as US, don't
  use the API's own streak field — compute it ourselves.
- No CSRF token or auth needed for any of these, despite the real frontend
  sending an `x-csrftoken` header — confirmed working with a plain
  unauthenticated POST and the same headers used for US.
- `numAcceptedQuestions` difficulty values are `"EASY"/"MEDIUM"/"HARD"`
  (uppercase), unlike US's `"Easy"/"Medium"/"Hard"` — normalize casing.

## Phase 0 acceptance status

- [x] Probe output from laptop, US region
- [x] Probe output from GitHub Actions runner, US region
- [x] Probe output from laptop, CN region
- [x] Probe output from GitHub Actions runner, CN region

**Phase 0 is fully closed.** Both regions confirmed reachable and correct
from both environments. CN support can now be built in Phase 1 (was
previously deferred — see git history, no longer applicable).
