"""Append one line to ``docs/log.md`` and emit the same event as a Phoenix trace.

Every role agent calls this instead of editing ``docs/log.md`` by hand:

    python -m harness_telemetry.log_event --role developer \
        --plan-item health-check-endpoint --action "made test_health pass" \
        --gate "tdd: pass" --evidence docs/evidence/health-check-endpoint/green.txt

The log line is the source of truth and is always written. The trace is
best-effort: each event becomes an AGENT span whose ``session.id`` is the plan
item, so Phoenix's Sessions view shows every role's actions on that item in order.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROLES = (
    "orchestrator", "analyst", "architect", "developer", "tester",
    "reviewer", "security", "documenter", "marketer",
)
FAILING_WORDS = ("fail", "blocked", "changes requested")


def format_line(timestamp: str, role: str, plan_item: str, action: str, gate: str) -> str:
    fields = [timestamp, role, plan_item, action, gate]
    # One line per entry, always: '|' and newlines would break the format.
    return " | ".join(" ".join(f.replace("|", "/").split()) for f in fields)


def gate_failed(gate: str) -> bool:
    return any(word in gate.lower() for word in FAILING_WORDS)


def emit_span(args: argparse.Namespace) -> None:
    from opentelemetry.trace import Status, StatusCode

    from harness_telemetry.tracing import agent_span, set_output, setup_tracing

    provider = setup_tracing(project_name=args.project)
    if provider is None:
        return
    metadata = {"role": args.role, "gate": args.gate, "evidence": args.evidence}
    with agent_span(
        f"{args.role}: {args.action}",
        input=args.action,
        session_id=args.plan_item,
        tags=[args.role],
        metadata={k: v for k, v in metadata.items() if v},
    ) as span:
        set_output(span, args.gate)
        if gate_failed(args.gate):
            span.set_status(Status(StatusCode.ERROR, args.gate))
    provider.force_flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--role", required=True, choices=ROLES)
    parser.add_argument("--plan-item", required=True, help="plan-item slug")
    parser.add_argument("--action", required=True)
    parser.add_argument("--gate", required=True, help='e.g. "tdd: pass", "review: changes requested"')
    parser.add_argument("--evidence", help="path under docs/evidence/<plan-item-slug>/")
    parser.add_argument("--log", default="docs/log.md")
    parser.add_argument("--project", default="harness", help="Phoenix project name")
    args = parser.parse_args(argv)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = format_line(timestamp, args.role, args.plan_item, args.action, args.gate)
    with Path(args.log).open("a", encoding="utf-8") as log:
        log.write(line + "\n")

    try:
        emit_span(args)
    except Exception as exc:  # tracing must never block the audit log
        print(f"log_event: trace not exported ({exc})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
