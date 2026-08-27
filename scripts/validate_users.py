"""Confirm every handle in users.json resolves. A wrong handle returns
null, not an error, so this is the only thing that catches typos.
See BUILD.md Phase 1.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.leetcode import LeetCodeAPIError, get_client

ROOT = Path(__file__).parent.parent
USERS_PATH = ROOT / "users.json"


def main():
    with open(USERS_PATH) as f:
        users = json.load(f)

    rows = []
    all_ok = True
    for user in users:
        handle = user["handle"]
        region = user["region"]
        try:
            client = get_client(region)
            client.fetch_user_and_recent(handle)
            rows.append((region, handle, "PASS", ""))
        except NotImplementedError as exc:
            rows.append((region, handle, "SKIP", str(exc)))
        except LeetCodeAPIError as exc:
            rows.append((region, handle, "FAIL", str(exc)))
            all_ok = False

    width = max((len(f"{r}/{h}") for r, h, _, _ in rows), default=10)
    for region, handle, status, detail in rows:
        label = f"{region}/{handle}".ljust(width)
        line = f"{label}  {status}"
        if detail:
            line += f"  {detail}"
        print(line)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
