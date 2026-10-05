"""Print the event sequence of the first run, or a chosen run ID."""
import argparse
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('log', type=Path)
    parser.add_argument('--run-id')
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.log.read_text(encoding='utf-8').splitlines()]
    target = args.run_id or rows[0]['run_id']
    for row in rows:
        if row['run_id'] == target:
            print(row['seq'], row['event'], row['status'])

if __name__ == '__main__':
    main()
