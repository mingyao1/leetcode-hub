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

**Decision (2026-08-27, human call per BUILD.md §2 rule 5):** proceed to
Phase 1 building the **US client only** for now. CN support is deferred,
not dropped — when a real `leetcode.cn` handle becomes available, come
back to this file, run `scripts/probe.py --us-handle mingyaol --cn-handle
<slug>` both locally and via `probe.yml`, fill in this section with real
results, then build `CNClient` in `scripts/lib/leetcode.py`. Until then:

- `users.json` should only contain `region: "us"` entries.
- Do not write a `CNClient` class or guess at its query shapes from the
  table above — those queries are still unverified.
- The daily challenge, streak math, and frontend can all be built and
  demoed fully on US-only data; nothing else in the spec depends on CN.

## Phase 0 acceptance status

- [x] Probe output from laptop, US region
- [x] Probe output from GitHub Actions runner, US region
- [ ] Probe output from laptop, CN region — **blocked on handle**
- [ ] Probe output from GitHub Actions runner, CN region — **blocked on handle**

Per BUILD.md §6 Phase 0's acceptance check requires output from *both*
regions before moving on. **This phase is not fully closed** — US is done,
CN is pending a real handle or an explicit decision to drop it.
