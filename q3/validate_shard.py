import csv
import json
import os
import socket
import sys
import time


def is_valid(row):
    name = (row.get("name") or "").strip()
    email = (row.get("email") or "").strip()
    if not name or not email:
        return False
    if email.count("@") != 1:
        return False
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        return False
    return True


def main():
    index = os.environ.get("JOB_COMPLETION_INDEX")
    if index is None:
        print("JOB_COMPLETION_INDEX is not set", file=sys.stderr)
        sys.exit(1)

    shard_dir = os.environ.get("SHARD_DIR", "shards")
    path = os.path.join(shard_dir, f"shard_{index}.csv")
    hold = int(os.environ.get("HOLD_SECONDS", "5"))

    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    invalid = [r for r in rows if not is_valid(r)]

    result = {
        "shard": int(index),
        "total_rows": len(rows),
        "invalid_rows": len(invalid),
        "pod": os.environ.get("POD_NAME", socket.gethostname()),
        "node": os.environ.get("NODE_NAME", "unknown"),
    }

    print(f"validating {path} on pod={result['pod']} node={result['node']}", flush=True)
    time.sleep(hold)
    print("RESULT_JSON " + json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
