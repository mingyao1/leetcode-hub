# leetcode-hub

A shared dashboard for the class: who's solving what on LeetCode, streaks, and a feed of recent solves so you can jump into whatever someone else just did.

**Live board:** https://mingyao1.github.io/leetcode-hub/

## Join the board

Open a ["Join the board"](../../issues/new?template=join.yml) issue with your name and LeetCode handle.

One thing first: go to your LeetCode profile settings and make sure recent submissions are **public**. If that's off, the API returns nothing for you and your row will look empty even while you're grinding. Use `leetcode.cn` as your region if that's the site you're on — note CN support is currently deferred (see `docs/api-notes.md`), so `.cn` join requests will stay open until it ships rather than being added automatically.

Your display name is public and gets indexed by search engines — it doesn't have to be your real name.

## How it works

No server, no database, no auth. A GitHub Actions cron job fetches from LeetCode's public GraphQL APIs every 6 hours, writes `public/data.json`, and deploys to GitHub Pages. See `BUILD.md` for the full spec.

⚠️ **Scheduled workflows are automatically disabled after 60 days of repo inactivity.** Over a long break (e.g. between semesters) the board will quietly stop updating — any push or manual run from the Actions tab re-enables it.
