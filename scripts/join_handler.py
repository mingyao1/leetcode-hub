"""Process a "Join the board" issue once a maintainer labels it `approved`.
Parses the issue-form body, validates the handle against the right
region's API, and appends to users.json on success. Run by
.github/workflows/join.yml. See BUILD.md Phase 4.

Reads ISSUE_NUMBER, ISSUE_BODY, ISSUE_AUTHOR from the environment (not
shell-interpolated — issue bodies are arbitrary public input).

Writes:
  - GITHUB_OUTPUT: status=success|failed|deferred
  - /tmp/join_comment.md: the comment to post back on the issue
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.leetcode import LeetCodeAPIError, get_client

ROOT = Path(__file__).parent.parent
USERS_PATH = ROOT / "users.json"
COMMENT_PATH = Path("/tmp/join_comment.md")

REGION_LABELS = {
    "us (leetcode.com)": "us",
    "cn (leetcode.cn)": "cn",
}


def parse_issue_form(body):
    """GitHub issue-form body -> {header: content}. Fields are rendered
    as '### Header\\n\\ncontent\\n\\n### Next header...'."""
    fields = {}
    parts = re.split(r"^### (.+)$", body, flags=re.MULTILINE)
    # parts[0] is any preamble before the first header; then alternating
    # header, content, header, content, ...
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        fields[header] = content
    return fields


def set_output(status):
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"status={status}\n")


def write_comment(text):
    COMMENT_PATH.write_text(text)


def load_users():
    with open(USERS_PATH) as f:
        return json.load(f)


def save_users(users):
    with open(USERS_PATH, "w") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    body = os.environ.get("ISSUE_BODY", "")
    author = os.environ.get("ISSUE_AUTHOR", "")

    fields = parse_issue_form(body)
    display_name = fields.get("Display name", "").strip()
    handle = fields.get("LeetCode handle", "").strip()
    region_raw = fields.get("Region", "").strip()
    region = REGION_LABELS.get(region_raw)

    if not display_name or not handle or region is None:
        set_output("failed")
        write_comment(
            "Couldn't read this issue — display name, LeetCode handle, and "
            "region all need to be filled in. Please edit the issue and "
            "re-apply the `approved` label."
        )
        return

    if region == "cn":
        set_output("deferred")
        write_comment(
            f"Thanks @{author} — leetcode.cn support isn't wired up yet on "
            "this board (see docs/api-notes.md for why). This issue is "
            "staying open; you'll be added once CN support ships. In the "
            "meantime, if you have a leetcode.com account, feel free to "
            "open a new join request for that instead."
        )
        return

    users = load_users()
    for existing in users:
        if existing["handle"] == handle and existing["region"] == region:
            set_output("failed")
            write_comment(
                f"`{handle}` ({region}) is already on the board as "
                f"\"{existing['display_name']}\". If that's wrong, edit "
                "users.json directly instead."
            )
            return

    try:
        client = get_client(region)
        client.fetch_user_and_recent(handle)
    except LeetCodeAPIError as exc:
        set_output("failed")
        write_comment(
            f"Couldn't validate `{handle}` on leetcode.{'cn' if region == 'cn' else 'com'}: "
            f"{exc}\n\nDouble check the handle, and make sure recent "
            "submissions are set to public in your LeetCode profile "
            "settings. Edit the issue and re-apply `approved` to retry."
        )
        return

    users.append({
        "display_name": display_name,
        "handle": handle,
        "region": region,
        "github": author,
    })
    save_users(users)

    set_output("success")
    write_comment(
        f"Welcome, {display_name}! `{handle}` is validated and added to "
        "the board. It'll show up on the next update, usually within a "
        "few minutes."
    )


if __name__ == "__main__":
    main()
