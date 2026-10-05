"""Stream terminal run errors; corrupt rows fail visibly, never silently."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import uuid

def validate_row(row):
    """Validate one schema-v1 event, not the lifecycle of a complete run."""
    if not isinstance(row, dict) or type(row.get("schema_version")) is not int or row["schema_version"] != 1:
        raise ValueError("invalid schema")
    for field in ("run_id", "timestamp", "mode", "model", "prompt_version", "case", "event", "status"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError("missing or invalid field")
    if uuid.UUID(row["run_id"]).version != 4:
        raise ValueError("invalid run ID")
    if datetime.fromisoformat(row["timestamp"]).utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError("timestamp must be UTC")
    if type(row.get("seq")) is not int or row["seq"] < 1:
        raise ValueError("invalid sequence")
    if row["mode"] not in {"simulated", "ollama"} or row["prompt_version"] not in {"v1", "v2"}:
        raise ValueError("invalid run metadata")
    starts = {"run_start", "tool_start", "model_start"}
    ends = {"run_end", "tool_end", "model_end"}
    if row["event"] in starts:
        if row["status"] != "running":
            raise ValueError("invalid start status")
    elif row["event"] in ends:
        duration = row.get("duration_ms")
        if type(duration) not in {int, float} or duration < 0:
            raise ValueError("invalid duration")
        try:
            finite = math.isfinite(duration)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("invalid duration")
        if "error_code" not in row:
            raise ValueError("missing error code")
        if row["status"] == "success":
            if row["error_code"] is not None:
                raise ValueError("success cannot have an error code")
        elif row["status"] == "error":
            if not isinstance(row["error_code"], str) or not row["error_code"].strip():
                raise ValueError("error must have an error code")
        else:
            raise ValueError("invalid end status")
    else:
        raise ValueError("unknown event")
    if row["event"].startswith("tool_") and (not isinstance(row.get("tool"), str) or not row["tool"].strip()):
        raise ValueError("invalid tool")
    if row["event"].startswith("model_") and (type(row.get("step")) is not int or row["step"] < 1):
        raise ValueError("invalid model step")

def error_runs(path, run_id=None):
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
                validate_row(row)
                if row.get("event") == "run_end" and row.get("status") == "error":
                    if run_id is None or row["run_id"] == run_id:
                        yield row
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid log row {number}") from exc

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    try:
        for row in error_runs(args.log, args.run_id):
            print(json.dumps(row, ensure_ascii=False))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Cannot read log: {exc}", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
