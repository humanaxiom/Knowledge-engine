2026-10-20 architect: docs/architecture.md §2.4 *Model roles* gains a "Tags, not pins" bullet (audit.md §4) and the measured MR-5 times under Timeouts.
ADR-KE-014 Consequences now say: config names are Ollama tags, re-run MR-5 after any pull, knowledge-plane records the embed digest per vector set, readiness digest check is a later item, Ollama patching is the host owner's job.
MR-5 measured (model-run-aria-gb10-2.txt): cold qwen3.5 compose 32.6 s, the longest at about 27% of 120 s, so Q55 was not triggered; no config or test change.
