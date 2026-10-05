"""Create exactly five runs in a NEW log; never overwrite a previous run."""
import argparse
from pathlib import Path
from agent import ROOT, run

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, default=Path("logs/five-runs.jsonl"))
    args = parser.parse_args()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.log.open("x", encoding="utf-8"):
            pass
    except FileExistsError:
        parser.error("Log already exists; choose a new --log path")
    cases = [("normal-v1", "source.txt", "v1"), ("normal-v2", "source.txt", "v2"),
             ("missing", "missing.txt", "v1"), ("empty", "empty.txt", "v1"),
             ("normal-repeat", "source.txt", "v1")]
    counts = {"success": 0, "error": 0}
    for case, filename, version in cases:
        row, _ = run(ROOT / "samples" / filename, args.log, prompt_version=version, case=case)
        counts[row["status"]] += 1
        print(f'{case:14} {row["status"]:7} {row["run_id"]} {row["error_code"] or "-"}')
    print(f"5 simulated runs; observed: {counts['success']} success, {counts['error']} error")
    print(f"Log: {args.log}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
