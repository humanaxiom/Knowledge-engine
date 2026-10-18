# Changelog

Maintained by the `marketer` agent. Follows a Keep a Changelog style.

## [Unreleased]

### Added
- Arize Phoenix observability: every agent action logged through
  `harness_telemetry.log_event` is also traced, grouped per plan item in
  Phoenix's Sessions view, with failed gates shown as errors.
- `harness_telemetry` helpers that tag spans with OpenInference kinds
  (AGENT, CHAIN, RETRIEVER, LLM, TOOL) so custom Python agents render as a
  nested trace tree, including retrieved documents and token usage.
- Input/output redaction via `OPENINFERENCE_HIDE_INPUTS`/`_OUTPUTS`.
- Local Phoenix via `docker compose up -d phoenix`.
- Real tests and an OTLP smoke test wired into `scripts/` and CI.

### Changed
- Reviewer and security gates now check tracing coverage and what traces export.
- CI runs with read-only permissions, cancels superseded runs, and uses `uv`.
