"""Run the example agent and log_event CLI against a stub OTLP/HTTP collector
and assert both deliver spans to /v1/traces (no Phoenix needed)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

RECEIVED: list[str] = []


class Collector(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        request = ExportTraceServiceRequest.FromString(body)
        for resource_spans in request.resource_spans:
            for scope_spans in resource_spans.scope_spans:
                RECEIVED.extend(span.name for span in scope_spans.spans)
        self.send_response(200 if self.path == "/v1/traces" else 404)
        self.end_headers()

    def log_message(self, *args):
        pass


def run(*args: str, env: dict[str, str]) -> None:
    subprocess.run([sys.executable, *args], env=env, check=True)


def main() -> int:
    host = "127.0.0.1"
    server = HTTPServer((host, 0), Collector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {
        **os.environ,
        "HARNESS_TRACING": "otlp",
        "PHOENIX_COLLECTOR_ENDPOINT": f"http://{host}:{server.server_port}",
    }
    log = Path(tempfile.mkdtemp()) / "log.md"
    run("examples/custom_agent.py", env=env)
    run("-m", "harness_telemetry.log_event", "--role", "tester", "--plan-item", "smoke",
        "--action", "ran smoke test", "--gate", "smoke: pass", "--log", str(log), env=env)
    server.shutdown()

    expected = {"Agent Reasoning Loop", "Graph Search", "Synthesize Answer", "tester: ran smoke test"}
    missing = expected - set(RECEIVED)
    if missing or "| tester | smoke |" not in log.read_text(encoding="utf-8"):
        print(f"smoke: FAIL (missing spans: {sorted(missing)})", file=sys.stderr)
        return 1
    print(f"smoke: pass ({len(RECEIVED)} spans exported)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
