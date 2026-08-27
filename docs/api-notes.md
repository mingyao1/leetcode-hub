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

## CN (`leetcode.cn`) — UNVERIFIED, NOT TESTED

No real `leetcode.cn` handle was available at the time Phase 0 ran (per user,
2026-08-27). Per BUILD.md §2 rule 2 and rule 5, the CN queries below have
**not** been probed against a live endpoint from either a laptop or a runner,
and must be treated as guesses only — nothing in `scripts/lib/leetcode.py`
should be built against them until they're verified.

Queries staged in `scripts/probe.py` (`CN_QUERIES`), unexecuted:

| Purpose | Query (unverified) |
|---|---|
| Profile | `userProfilePublicProfile(userSlug) { profile { userSlug realName } }` |
| Calendar | `userProfileCalendar(userSlug) { submissionCalendar }` |
| Recent submissions | `recentAcSubmissions(userSlug, limit: 20) { submissionId question { title titleSlug } submitTime }` |
| Solved counts | `userProfileUserQuestionProgressV2(userSlug) { numAcceptedQuestions { difficulty count } }` |

This also means the single highest-risk unknown Phase 0 exists to answer —
**whether `leetcode.cn` responds to requests from a GitHub Actions runner
IP at all** — is still open. It has not failed; it has simply not been run.

**Status: blocked, not resolved.** Per BUILD.md §2 rule 5, this is flagged
rather than worked around. Do not proceed to build CN support in Phase 1
until one of the following happens:

1. A real `leetcode.cn` handle (yours or a classmate's) becomes available,
   `scripts/probe.py --us-handle mingyaol --cn-handle <slug>` is run both
   locally and via `probe.yml`, and this file is updated with real results, or
2. A human decision is made to drop CN support entirely for v1 (BUILD.md §2
   rule states this is explicitly a human call, options being: classmates
   with `.cn` accounts use a `.com` account instead, drop CN, or run the
   fetcher from a non-US-IP host).

## Phase 0 acceptance status

- [x] Probe output from laptop, US region
- [x] Probe output from GitHub Actions runner, US region
- [ ] Probe output from laptop, CN region — **blocked on handle**
- [ ] Probe output from GitHub Actions runner, CN region — **blocked on handle**

Per BUILD.md §6 Phase 0's acceptance check requires output from *both*
regions before moving on. **This phase is not fully closed** — US is done,
CN is pending a real handle or an explicit decision to drop it.
