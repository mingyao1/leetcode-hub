# BUILD.md — Class LeetCode Hub

Spec for an agent (Claude Code) building this repo from scratch. Read this file top to bottom before writing any code.

---

## 1. What this is

A static dashboard for a class of ~10 people that shows, for each classmate: total solved, current streak, and recently accepted problems, with links back to LeetCode so anyone can jump straight into a problem someone else just did. Supports both LeetCode Global (`leetcode.com`) and LeetCode China (`leetcode.cn`).

No server, no database, no auth. A GitHub Actions cron job fetches from LeetCode's public GraphQL APIs, writes a flat JSON file, and deploys to GitHub Pages.

**Priority order:** working > correct > pretty > complete. This must be demoable within a day.

---

## 2. Rules for the agent

1. **Do the phases in order. Do not skip Phase 0.** Phase 0 discovers the real API shapes. Everything downstream depends on what it finds. If you build on assumed field names you will waste hours.
2. **Do not invent GraphQL field names.** Especially for `leetcode.cn`, whose schema is undocumented and changes. Every field used in the fetcher must have appeared in a real response captured during Phase 0.
3. **Stop and report at each phase gate.** Each phase below has an acceptance check. Run it, show the output, wait for a human before continuing.
4. **Never commit secrets.** No auth tokens, no cookies, no session IDs. Everything here uses public unauthenticated endpoints.
5. **When an assumption in this spec turns out to be wrong**, say so explicitly and propose the fix rather than silently working around it. This spec was written without live API access.

---

## 3. Human steps before Phase 0

These need a browser. The agent cannot do them.

1. Create a **public** GitHub repo (public is required for free Pages + free Actions minutes). Name suggestion: `class-leetcode-hub`.
2. Clone it locally and point the agent at the directory.
3. **Settings → Pages → Build and deployment → Source: `GitHub Actions`.** Not "Deploy from a branch". This must be set before Phase 3.
4. **Settings → Actions → General → Workflow permissions: `Read and write permissions`.** Needed for the fetcher to commit data.
5. Have two LeetCode handles ready for testing: one `leetcode.com` account and one `leetcode.cn` account. Your own plus one classmate's is fine. Without a real CN handle Phase 0 cannot answer the question it exists to answer.

---

## 4. Repo layout

```
users.json                     # source of truth: who's on the board
scripts/
  probe.py                     # Phase 0 only, throwaway-ish, keep for debugging
  fetch.py                     # main entrypoint, run by CI
  validate_users.py            # checks every handle resolves
  lib/
    leetcode.py                # GraphQL clients, one per region
    streaks.py                 # calendar -> streak math
    merge.py                   # resilient merge with previous data.json
cache/
  problems.json                # problem metadata cache (difficulty, paidOnly)
public/
  index.html                   # the whole frontend, single file
  data.json                    # generated, committed
.github/
  workflows/
    probe.yml                  # Phase 0 only
    update.yml                 # cron fetch + deploy
    join.yml                   # Phase 4
  ISSUE_TEMPLATE/
    join.yml                   # Phase 4
README.md
```

Python 3.11+. Only dependency is `requests`. No framework, no build step, no `package.json`.

---

## 5. Data contracts

Define these first; both the fetcher and the frontend code against them.

### `users.json`

```json
[
  {
    "display_name": "Alex",
    "handle": "alexcodes",
    "region": "us",
    "github": "alex-gh"
  }
]
```

- `display_name` — what shows on the board. Classmates choose it. Does not have to be a real name; see §9.
- `handle` — `username` on US, `userSlug` on CN. Same string position, different API param name.
- `region` — `"us"` or `"cn"`.
- `github` — optional, used only by the join workflow to attribute an entry.

A person with accounts on both sites gets two entries. The board treats them as two rows; do not try to merge them.

### `public/data.json`

```json
{
  "generated_at": "2026-08-26T14:00:00Z",
  "timezone": "America/New_York",
  "daily": {
    "date": "2026-08-26",
    "title": "Two Sum",
    "slug": "two-sum",
    "difficulty": "Easy",
    "url": "https://leetcode.com/problems/two-sum/"
  },
  "users": [
    {
      "display_name": "Alex",
      "handle": "alexcodes",
      "region": "us",
      "solved": { "easy": 40, "medium": 25, "hard": 3, "total": 68 },
      "streak": 5,
      "solved_last_7d": 9,
      "active_today": true,
      "last_fetched": "2026-08-26T14:00:00Z",
      "stale": false,
      "error": null
    }
  ],
  "feed": [
    {
      "handle": "alexcodes",
      "display_name": "Alex",
      "region": "us",
      "slug": "two-sum",
      "title": "Two Sum",
      "difficulty": "Easy",
      "paid_only": false,
      "cn_only": false,
      "url": "https://leetcode.com/problems/two-sum/",
      "timestamp": 1756220000
    }
  ]
}
```

`feed` is a rolling 30-day window, deduped on `(handle, slug, timestamp)`, sorted newest first.

### `cache/problems.json`

```json
{ "two-sum": { "title": "Two Sum", "difficulty": "Easy", "paid_only": false, "cn_only": false } }
```

Keyed by slug. Problem metadata is immutable, so this is fetched once per slug ever. After the first run only a handful of new slugs appear per cycle.

---

## 6. Phases

### Phase 0 — Probe the APIs

The single highest-risk unknown: **does `leetcode.cn` respond to requests from a GitHub Actions runner?** Runners are Azure US IPs. CN may return 403, may rate-limit, may work fine. Find out now, not after building the normalization layer.

Second unknown: the exact CN schema.

Build `scripts/probe.py`:

- Takes a US handle and a CN handle.
- For each region, issues each candidate query separately and prints the raw JSON response (or the HTTP status and body on failure) — do not merge queries yet, you want to know which individual field breaks.
- Times each request.
- Exits non-zero if any query fails, but only after attempting all of them.

Queries to probe. **US (`https://leetcode.com/graphql/`) — these field names are reliable:**

```graphql
query($username: String!) {
  matchedUser(username: $username) {
    username
    submitStatsGlobal { acSubmissionNum { difficulty count } }
    userCalendar { submissionCalendar streak totalActiveDays }
  }
}
```
```graphql
query($username: String!) {
  recentAcSubmissionList(username: $username, limit: 20) { id title titleSlug timestamp }
}
```
```graphql
query($titleSlug: String!) {
  question(titleSlug: $titleSlug) { questionFrontendId title titleSlug difficulty isPaidOnly }
}
```
```graphql
query { activeDailyCodingChallengeQuestion { date link question { title titleSlug difficulty } } }
```

**CN (`https://leetcode.cn/graphql/`) — treat every one of these as a guess to be verified:**

```graphql
query($userSlug: String!) { userProfilePublicProfile(userSlug: $userSlug) { profile { userSlug realName } } }
```
```graphql
query($userSlug: String!) { userProfileCalendar(userSlug: $userSlug) { submissionCalendar } }
```
```graphql
query($userSlug: String!) { recentAcSubmissions(userSlug: $userSlug, limit: 20) { submissionId question { title titleSlug } submitTime } }
```
```graphql
query($userSlug: String!) { userProfileUserQuestionProgressV2(userSlug: $userSlug) { numAcceptedQuestions { difficulty count } } }
```

CN's solved-count query is the least stable of these and has been renamed more than once. If it errors, the error message usually names the correct field — read it. If you cannot find a working solved-count query in ~15 minutes, note it and move on; streaks and the feed are the important parts and both come from other queries.

Headers for every request, both regions:

```python
{
  "Content-Type": "application/json",
  "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
  "Referer": "https://leetcode.com/",   # or https://leetcode.cn/ for CN
  "Origin":  "https://leetcode.com",    # or https://leetcode.cn
}
```

Default `python-requests` User-Agent gets 403'd. This is not optional.

Then create `.github/workflows/probe.yml`: `workflow_dispatch` only, checkout, setup-python, `pip install requests`, run the probe with handles passed as workflow inputs. Push it and run it from the Actions tab.

**Acceptance:** probe output from *both* your laptop and a GitHub runner, for both regions. Write the findings into `docs/api-notes.md` — the confirmed working query for each of: solved counts, calendar, recent submissions, problem metadata, daily challenge. That file becomes the reference for Phase 1.

**If CN fails from the runner:** stop and report. Options are (a) affected classmates use a `.com` account, (b) drop CN, (c) run the fetcher elsewhere. This is a human decision. Do not build a workaround unprompted.

---

### Phase 1 — Fetcher, local, your handle only

Build `scripts/lib/leetcode.py` with two client classes sharing an interface:

```python
class Client:
    def fetch_user(handle) -> dict   # solved counts, submission calendar
    def fetch_recent(handle, limit=20) -> list
    def fetch_question(slug) -> dict
```

`USClient` and `CNClient` implement it using whatever Phase 0 confirmed. All region differences live here. Nothing above this layer knows which site a user is on except for building URLs.

Per-user, issue **one** combined GraphQL operation covering profile + calendar + recent submissions rather than three round-trips. Verify the combined form works — some servers reject multi-root operations that the individual queries accept. If it fails, fall back to separate requests; not worth fighting.

Sleep 1.5s between users. At 10 users that is a 15-second job.

**`scripts/lib/streaks.py`:**

`submissionCalendar` is a JSON **string** (not an object) mapping unix-second timestamps to submission counts. Parse it, convert each timestamp to a date in `America/New_York`, then walk backward from today counting consecutive days with a nonzero count.

Two rules that matter:

- **Today does not break a streak.** If there is no submission today but there was one yesterday, the streak is alive. Only a gap ending *before* yesterday breaks it. Otherwise everyone's streak reads zero every morning.
- **Timezone is explicit.** The US calendar buckets by UTC day, so a 9pm Eastern solve lands on the next UTC day. Normalize to one timezone, defined once as a constant, and put it in `data.json` so the frontend can label it.

Also compute `solved_last_7d` from the same calendar. Note this counts submission-active days' totals, not unique problems — that's fine and it's what the calendar gives you. Do not use the API's own `streak` field even where it exists; the two regions compute it differently and one of them uses UTC.

**Difficulty enrichment:** for each slug in the recent feed, look it up in `cache/problems.json`; on a miss, call `fetch_question` and write it back. Set `cn_only` when the slug matches a CN-exclusive prefix — `LCP`, `LCR`, `LCS`, `剑指`, `面试题` — or when a US metadata lookup for a CN-sourced slug returns null. Those problems have no `leetcode.com` equivalent and linking a global user to them produces a 404.

Capture `isPaidOnly`. Premium-locked links are dead ends for most of the class; the frontend must mark them.

**Resilience — `scripts/lib/merge.py`:** wrap each user's fetch in its own `try/except`. On failure, carry that user's previous entry forward from the existing `data.json`, keep its old `last_fetched`, and set `error` to the exception string. Set `stale: true` when `last_fetched` is more than 12 hours old. Never let one bad handle blank the board — a board that renders empty once teaches the class it's broken, and that is harder to undo than any bug.

The feed merges rather than replaces: union of previous feed and this run's, deduped, trimmed to 30 days. The API only returns the last ~20 submissions per user, so without accumulation the feed is permanently as short as that window.

Write `scripts/validate_users.py`: for every entry in `users.json`, confirm the handle resolves; print a clean pass/fail table. A wrong handle returns `null`, not an error — this script is the only thing that catches typos.

**Acceptance:** `python scripts/fetch.py` with `users.json` containing just you produces a valid `public/data.json`. Then add a deliberately broken handle and confirm the file still contains your good data plus an `error` on the bad row.

---

### Phase 2 — Frontend

Single file `public/index.html`. Tailwind via CDN, vanilla JS, no build step. It will print a console warning about CDN use in production — ignore it.

`fetch('./data.json')` with a cache-buster query param, render, done.

**Three views, tabs, all client-side over the same loaded object:**

1. **Board** — one row per person: display name, region badge, total solved, streak, solved-last-7d, active-today dot. Sortable. Search box. Filters for region and active-today.
2. **Feed** — reverse-chronological recent solves: who, what, difficulty, relative time, link out. This is the tab people will actually use.
3. **Problems** — the feed grouped by problem: title, difficulty, avatars/names of everyone who solved it recently, count. Sorted by recent solver count. This is what makes it a hub rather than a scoreboard — it surfaces what the class is collectively working through.

Pin the daily challenge above the tabs as a shared starting point.

**Requirements:**

- Rank on **streak** and **solved last 7 days**, not lifetime total. Lifetime total mostly measures who started earliest, and it isn't comparable across US and CN anyway — different problem sets, and CN carries extra collections. Show total as a column, never as the sort default.
- Problem links use the region of the **person who solved it**: `leetcode.com/problems/{slug}/` or `leetcode.cn/problems/{slug}/`.
- Visibly mark `paid_only` and `cn_only`. A badge is enough.
- Rows with `stale: true` get a subtle indicator and a tooltip with `last_fetched`. Do not hide them.
- Empty feed says what to do, not just "no data".
- Responsive to mobile — people will check this on a phone. Keyboard focus visible. `prefers-reduced-motion` respected.

**Design:** read `/mnt/skills/public/frontend-design/SKILL.md` and follow its process. Brief: a shared workbench for one class, not a competitive ladder — the tone should make it feel good to be on the board at any level, and make the next problem the obvious thing to click. Avoid the AI-default looks that skill calls out. Pick a type pairing and a palette deliberately and state your reasoning before you write CSS.

**Acceptance:** open `public/index.html` against a hand-written `data.json` containing at least one stale user, one paid-only problem, one CN-only problem, and two people who solved the same problem. All three tabs render correctly. Do this before wiring CI.

---

### Phase 3 — CI/CD

`.github/workflows/update.yml`, one job doing both fetch and deploy:

```yaml
on:
  schedule:
    - cron: "0 */6 * * *"
  workflow_dispatch:
  push:
    branches: [main]
    paths: ["users.json", "public/index.html"]
permissions:
  contents: write
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: false
```

Steps: checkout → setup-python → `pip install requests` → `python scripts/fetch.py` → commit `public/data.json` and `cache/problems.json` if changed → `actions/upload-pages-artifact` with `path: public` → `actions/deploy-pages`.

Four things to get right:

- **Fetch and deploy in the same workflow.** Commits made with the default `GITHUB_TOKEN` do not trigger other workflows, so a separate deploy workflow listening for pushes would silently never fire.
- **Six hours, not four.** Nothing here is time-sensitive and fewer runs means fewer transient failures. `workflow_dispatch` covers debugging.
- **Commit the data.** Git history becomes a free time series if you ever want per-day charts.
- Guard the commit step so an unchanged file doesn't fail the run.

**Acceptance:** manual dispatch succeeds, Pages URL loads with real data, and a second dispatch produces either a clean commit or a correct no-op.

⚠️ Scheduled workflows are **auto-disabled after 60 days of repo inactivity**. Over a long break the board will quietly stop updating. Note this in the README.

---

### Phase 4 — Join flow

Classmates must not need to know git.

**`.github/ISSUE_TEMPLATE/join.yml`** — an issue form with: display name (free text, note that it's public and needn't be a real name), LeetCode handle, region dropdown (`us` / `cn`), and a checkbox acknowledging they've made recent submissions public.

**`.github/workflows/join.yml`** — triggers on `issues: [labeled]`, gated on the label `approved`. You add the label; that one click is the whole moderation model. The repo is public, so anyone on the internet can open an issue — do not auto-commit on `issues: [opened]`.

The job: parse the issue body, validate the handle actually resolves against the right region's API, append to `users.json`, commit, comment on the issue with the result, close it. On validation failure, comment with the reason and leave it open. `permissions: contents: write, issues: write`.

Then dispatch `update.yml` so the new person appears immediately instead of up to six hours later.

**The onboarding message to send the class** — put this in the README too:

> Open a "Join the board" issue with your name and LeetCode handle. One thing first: go to your LeetCode profile settings and make sure recent submissions are **public**. If that's off, the API returns nothing for you and your row will look empty even while you're grinding. Use `leetcode.cn` as your region if that's the site you're on.

That privacy setting is the most common cause of a mysteriously empty row, and it is invisible from the API side — a hidden profile and an inactive user look identical.

**Acceptance:** a real classmate joins end to end without touching a terminal.

---

### Phase 5 — Only after 4 works

Ideas, unordered, none required: per-user sparkline from git history of `data.json`; "problems solved by others that you haven't" (needs a full solved-list per user, which is expensive — check feasibility first); weekly digest issue; topic tags on the feed.

Do not build these before Phase 4 ships. Scope creep is the standard cause of death for this kind of project.

---

## 7. Known gotchas, collected

| Thing | Consequence |
|---|---|
| Default `python-requests` User-Agent | 403 |
| `leetcode.cn` from Azure/GitHub IPs | May be blocked; Phase 0 exists for this |
| `submissionCalendar` is a JSON string | Parse twice |
| US calendar buckets by UTC day | Evening solves land on the wrong day |
| Streak that counts today as a break | Everyone reads 0 each morning |
| Hidden "recent submissions" profile setting | Silent empty feed, indistinguishable from inactivity |
| CN-exclusive slugs (`LCP`, `LCR`, `剑指`, `面试题`) | 404 on `leetcode.com` |
| `isPaidOnly` problems | Dead-end links |
| Recent submissions API returns only ~20 | Feed must accumulate, not replace |
| `GITHUB_TOKEN` commits don't trigger workflows | A split fetch/deploy setup never deploys |
| Scheduled workflows disabled after 60 days idle | Board silently freezes over break |
| Wrong handle returns `null`, not an error | Typos are invisible without `validate_users.py` |
| US and CN totals aren't comparable | Don't rank on lifetime total |

---

## 8. Definition of done

Phase 3 complete. Pages URL loads, shows real data for at least three real classmates including one CN user (or a documented decision to drop CN), streaks are correct against what LeetCode's own profile page shows, and the feed links open the right problems. Phase 4 makes it self-service.

---

## 9. One non-technical note

This is a public site with real names next to LeetCode handles, and it will be indexed and archived. Let people pick a display name that isn't their full legal name, and say so in the join form. Someone's problem-solving pace is more personal than it looks — and a board that quietly pressures the person at the bottom is worse than no board. Rank on streak and recent activity, keep totals de-emphasized, and it stays a hub instead of a ranking.
