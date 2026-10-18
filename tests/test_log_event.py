import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from opentelemetry.trace import StatusCode

from harness_telemetry.log_event import format_line, main
from tests.support import EXPORTER, finished_spans


class LogEventTest(unittest.TestCase):
    def setUp(self):
        EXPORTER.clear()
        self.log = Path(tempfile.mkdtemp()) / "log.md"
        self.log.write_text("# Observability Log\n", encoding="utf-8")

    def run_cli(self, *extra):
        return main([
            "--role", "tester", "--plan-item", "health-check",
            "--log", str(self.log), *extra,
        ])

    def test_appends_one_line_and_emits_session_span(self):
        self.run_cli("--action", "wrote failing test", "--gate", "tdd: red as expected",
                     "--evidence", "docs/evidence/health-check/red.txt")

        line = self.log.read_text(encoding="utf-8").splitlines()[-1]
        timestamp, role, item, action, gate = line.split(" | ")
        self.assertTrue(timestamp.endswith("Z"))
        self.assertEqual((role, item, action, gate),
                         ("tester", "health-check", "wrote failing test", "tdd: red as expected"))

        span = finished_spans()["tester: wrote failing test"]
        self.assertEqual(span.attributes["openinference.span.kind"], "AGENT")
        self.assertEqual(span.attributes["session.id"], "health-check")
        self.assertEqual(span.attributes["tag.tags"], ("tester",))
        self.assertEqual(json.loads(span.attributes["metadata"])["evidence"],
                         "docs/evidence/health-check/red.txt")
        self.assertEqual(span.status.status_code, StatusCode.OK)

    def test_failed_gate_marks_span_error(self):
        self.run_cli("--action", "ran smoke test", "--gate", "smoke: FAIL")
        span = finished_spans()["tester: ran smoke test"]
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    def test_format_line_keeps_one_line_per_entry(self):
        line = format_line("t", "developer", "item", "fixed a|b\nthing", "pass")
        self.assertEqual(line, "t | developer | item | fixed a/b thing | pass")

    def test_rejects_unknown_role(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            main(["--role", "intern", "--plan-item", "x", "--action", "a", "--gate", "g"])


if __name__ == "__main__":
    unittest.main()
