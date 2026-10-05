import contextlib
import io
import json
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from agent import run, RunLog, AgentError, LogWriteError, chat
import demo
from filter_errors import error_runs, validate_row

class LoggingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.txt"
        self.source.write_text("Một\nHai\nBa\n", encoding="utf-8")
        self.log = self.root / "runs.jsonl"

    def rows(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()]

    def test_success_lifecycle(self):
        summary, result = run(self.source, self.log)
        self.assertEqual(summary["status"], "success")
        self.assertEqual([r["event"] for r in self.rows()], ["run_start", "tool_start", "tool_end", "run_end"])
        self.assertIn("Một", result)

    def test_required_metadata_and_sequence(self):
        run(self.source, self.log)
        rows = self.rows()
        self.assertEqual(len({r["run_id"] for r in rows}), 1)
        self.assertEqual([r["seq"] for r in rows], [1, 2, 3, 4])
        for row in rows:
            self.assertTrue({"model", "prompt_version", "mode", "timestamp", "status"} <= row.keys())
        self.assertGreaterEqual(rows[-1]["duration_ms"], 0)

    def test_missing(self):
        summary, _ = run(self.root / "missing", self.log)
        self.assertEqual(summary["error_code"], "document_missing")
        self.assertEqual(len(list(error_runs(self.log))), 1)

    def test_empty(self):
        self.source.write_text(" \n")
        self.assertEqual(run(self.source, self.log)[0]["error_code"], "document_empty")

    def test_encoding(self):
        self.source.write_bytes(b"\xff")
        self.assertEqual(run(self.source, self.log)[0]["error_code"], "document_encoding")

    def test_append_unique_ids(self):
        one, _ = run(self.source, self.log)
        two, _ = run(self.source, self.log)
        self.assertNotEqual(one["run_id"], two["run_id"])
        self.assertEqual(len(self.rows()), 8)

    def test_no_document_or_exception_text(self):
        with patch("agent.read_document", side_effect=RuntimeError("SECRET-test-token")):
            summary, _ = run(self.source, self.log)
        self.assertEqual(summary["error_code"], "unexpected_error")
        self.assertNotIn("SECRET-test-token", self.log.read_text())

    def test_corrupt_log(self):
        self.log.write_text('{broken}\n')
        with self.assertRaisesRegex(ValueError, "row 1"):
            list(error_runs(self.log))

    def test_filter_not_duplicate_tool_error(self):
        row, _ = run(self.root / "missing", self.log)
        self.assertEqual(len(list(error_runs(self.log, row["run_id"]))), 1)
        self.assertEqual(list(error_runs(self.log, "other")), [])

    def test_live_model_selects_tool(self):
        replies = [{"tool_calls": [{"function": {"name": "read_document", "arguments": {}}}]}, {"content": "- Kết quả"}]
        with patch("agent.chat", side_effect=replies):
            summary, _ = run(self.source, self.log, mode="ollama", model="mock")
        self.assertEqual(summary["status"], "success")
        self.assertEqual(len([r for r in self.rows() if r["event"] == "model_end"]), 2)

    def test_live_requires_tool(self):
        with patch("agent.chat", return_value={"content": "answer"}):
            summary, _ = run(self.source, self.log, mode="ollama", model="mock")
        self.assertEqual(summary["error_code"], "required_tool_not_called")

    def test_live_model_error(self):
        with patch("agent.chat", side_effect=AgentError("model_request_failed")):
            summary, _ = run(self.source, self.log, mode="ollama", model="mock")
        self.assertEqual(summary["error_code"], "model_request_failed")
        self.assertEqual(self.rows()[-2]["event"], "model_end")

    def test_live_unknown_tool(self):
        with patch("agent.chat", return_value={"tool_calls": [{"function": {"name": "shell"}}]}):
            self.assertEqual(run(self.source, self.log, mode="ollama", model="mock")[0]["error_code"], "tool_call_invalid")

    def test_live_step_limit(self):
        msg = {"tool_calls": [{"function": {"name": "read_document", "arguments": {}}}]}
        with patch("agent.chat", return_value=msg):
            self.assertEqual(run(self.source, self.log, mode="ollama", model="mock")[0]["error_code"], "step_limit")

    def test_log_failure_is_visible(self):
        with self.assertRaises(OSError):
            run(self.source, self.root)

    def test_unexpected_tool_closes_error_event(self):
        with patch("agent.read_document", side_effect=RuntimeError("SECRET-test-token")):
            row, _ = run(self.source, self.log)
        self.assertEqual([r["event"] for r in self.rows()], ["run_start", "tool_start", "tool_end", "run_end"])
        self.assertEqual(self.rows()[-2]["error_code"], "unexpected_error")
        self.assertEqual(row["status"], "error")

    def test_unexpected_model_closes_error_event(self):
        with patch("agent.chat", side_effect=RuntimeError("SECRET-test-token")):
            row, _ = run(self.source, self.log, mode="ollama", model="mock")
        self.assertEqual(self.rows()[-2]["event"], "model_end")
        self.assertEqual(row["error_code"], "unexpected_error")
        self.assertNotIn("SECRET-test-token", self.log.read_text())

    def test_live_malformed_function(self):
        for fn in [None, [], "read_document"]:
            with self.subTest(function=fn), patch("agent.chat", return_value={"tool_calls": [{"function": fn}]}):
                row, _ = run(self.source, self.log, mode="ollama", model="mock")
            self.assertEqual(row["error_code"], "tool_call_invalid")

    def test_live_rejects_arguments(self):
        message = {"tool_calls": [{"function": {"name": "read_document", "arguments": {"path": "/private"}}}]}
        with patch("agent.chat", return_value=message):
            row, _ = run(self.source, self.log, mode="ollama", model="mock")
        self.assertEqual(row["error_code"], "tool_call_invalid")
        self.assertFalse(any(r["event"] == "tool_start" for r in self.rows()))

    def test_live_empty_output(self):
        replies = [{"tool_calls": [{"function": {"name": "read_document", "arguments": {}}}]}, {"content": " "}]
        with patch("agent.chat", side_effect=replies):
            row, _ = run(self.source, self.log, mode="ollama", model="mock")
        self.assertEqual(row["error_code"], "model_output_empty")

    def test_filter_rejects_incomplete_row(self):
        self.log.write_text(json.dumps({"schema_version": 1, "run_id": "x"}) + "\n")
        with self.assertRaisesRegex(ValueError, "row 1"):
            list(error_runs(self.log))

    def test_filter_rejects_invalid_field_values(self):
        run(self.source, self.log)
        original = self.rows()[-1]
        changes = [{"seq": True}, {"seq": 0}, {"schema_version": True}, {"run_id": "x"},
                   {"timestamp": "invalid"}, {"timestamp": "2026-10-04T00:00:00"},
                   {"model": ""}, {"status": "running"}, {"event": "unknown"},
                   {"duration_ms": float("nan")}, {"duration_ms": -1}, {"duration_ms": 10 ** 1000},
                   {"error_code": "bad"}, {"status": "error", "error_code": None}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_row({**original, **change})

    def test_emit_rejects_metadata_override_and_content(self):
        log = RunLog(self.log, "simulated", "scripted-demo", "v1", "test")
        for field in ["run_id", "seq", "model", "content"]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                log.emit("run_start", "running", **{field: "SECRET-test-token"})
        self.assertFalse(self.log.exists())

    def test_transient_log_error_is_not_agent_error(self):
        original_open = Path.open
        counter = 0
        def fail_second(path, *args, **kwargs):
            nonlocal counter
            if path == self.log and args and args[0] == "a":
                counter += 1
                if counter == 2:
                    raise OSError("temporary disk error")
            return original_open(path, *args, **kwargs)
        with patch.object(Path, "open", fail_second), self.assertRaises(LogWriteError):
            run(self.source, self.log)
        self.assertEqual([r["event"] for r in self.rows()], ["run_start"])

    def test_run_end_write_failure_is_visible(self):
        original_emit = RunLog.emit
        def fail_end(logger, event, status, **fields):
            if event == "run_end":
                raise LogWriteError("disk error")
            return original_emit(logger, event, status, **fields)
        with patch.object(RunLog, "emit", fail_end), self.assertRaises(LogWriteError):
            run(self.source, self.log)
        self.assertEqual(self.rows()[-1]["event"], "tool_end")

    def test_demo_existing_log_preserved(self):
        self.log.write_text("keep this log")
        with patch.object(sys, "argv", ["demo.py", "--log", str(self.log)]), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                demo.main()
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(self.log.read_text(), "keep this log")

    def test_demo_reports_observed_counts(self):
        samples = self.root / "samples"
        samples.mkdir()
        (samples / "source.txt").write_text("content")
        (samples / "empty.txt").write_text("now nonempty")
        out = io.StringIO()
        with patch.object(demo, "ROOT", self.root), patch.object(sys, "argv", ["demo.py", "--log", str(self.log)]), contextlib.redirect_stdout(out):
            self.assertEqual(demo.main(), 0)
        self.assertIn("observed: 4 success, 1 error", out.getvalue())

    def test_chat_serializes_request(self):
        response = io.StringIO(json.dumps({"message": {"content": "answer"}}))
        with patch("agent.urlopen", return_value=response) as send:
            self.assertEqual(chat([], "mock", "http://localhost:11434", 60), {"content": "answer"})
        request = send.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, "http://localhost:11434/api/chat")
        self.assertFalse(body["stream"])
        self.assertEqual(body["tools"][0]["function"]["name"], "read_document")
        self.assertEqual(send.call_args.kwargs["timeout"], 60)

    def test_chat_rejects_malformed_response(self):
        for data in ["broken", "[]", '{"message": null}']:
            with self.subTest(data=data), patch("agent.urlopen", return_value=io.StringIO(data)):
                with self.assertRaises(AgentError) as error:
                    chat([], "mock", "http://localhost:11434", 60)
                self.assertEqual(error.exception.code, "model_response_invalid")

if __name__ == "__main__":
    unittest.main()
