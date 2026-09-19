import argparse
import csv
import os
import random

SHARDS = 8
ROWS_PER_SHARD = 100

FIRST = ["arjun", "priya", "rahul", "sneha", "vikram", "anita", "karthik", "divya"]
LAST = ["sharma", "nair", "iyer", "patel", "reddy", "gupta", "menon", "rao"]
DOMAINS = ["example.com", "mail.co", "testmail.org", "inbox.net"]
COUNTRIES = ["IN", "US", "UK", "SG", "AU"]


def valid_row(rng, uid):
    first = rng.choice(FIRST)
    last = rng.choice(LAST)
    return {
        "user_id": uid,
        "name": f"{first} {last}",
        "email": f"{first}.{last}@{rng.choice(DOMAINS)}",
        "signup_date": f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
        "country": rng.choice(COUNTRIES),
    }


def corrupt(rng, row):
    mode = rng.choice(["no_at", "no_domain", "double_at", "empty_email", "empty_name"])
    if mode == "no_at":
        row["email"] = row["email"].replace("@", ".")
    elif mode == "no_domain":
        row["email"] = row["email"].split("@")[0] + "@"
    elif mode == "double_at":
        row["email"] = row["email"].replace("@", "@@")
    elif mode == "empty_email":
        row["email"] = ""
    elif mode == "empty_name":
        row["name"] = ""
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="shards")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    os.makedirs(args.out_dir, exist_ok=True)

    uid = 1000
    for index in range(SHARDS):
        n_invalid = rng.randint(5, 20)
        rows = []
        for _ in range(ROWS_PER_SHARD):
            rows.append(valid_row(rng, uid))
            uid += 1
        for row in rng.sample(rows, n_invalid):
            corrupt(rng, row)

        path = os.path.join(args.out_dir, f"shard_{index}.csv")
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["user_id", "name", "email", "signup_date", "country"]
            )
            writer.writeheader()
            writer.writerows(rows)

        print(f"shard_{index}.csv rows={ROWS_PER_SHARD} invalid={n_invalid}")


if __name__ == "__main__":
    main()
