"""
Peek at the first N records of a GLEIF Golden Copy file to confirm its
actual field structure before writing matching/join logic against it.
Streams with ijson so this is safe to run against multi-GB files.

Usage:
    pip install ijson
    python src/gleif_peek.py --file /path/to/rr-golden-copy.json --n 3
"""
import argparse
import json
import ijson


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--path", default="records.item", help="ijson path to stream items from")
    args = parser.parse_args()

    count = 0
    with open(args.file, "rb") as f:
        for record in ijson.items(f, args.path):
            print(f"--- record {count} ---")
            print(json.dumps(record, indent=2)[:3000])
            print()
            count += 1
            if count >= args.n:
                break

    if count == 0:
        print(f"No records found at path '{args.path}'. Try --path 'item' or inspect the file's top-level keys manually.")


if __name__ == "__main__":
    main()
