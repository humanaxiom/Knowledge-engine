# Observability Log

Append-only. Every agent appends one line per action, oldest first. Never edit
or delete prior entries.

Format: `<ISO timestamp> | <role> | <plan-item-slug> | <action> | <gate result>`

<!-- Example:
2026-09-07T10:00:00Z | analyst | health-check-endpoint | wrote acceptance criteria | plan gate: pending architect
-->
2026-10-18T17:45:42Z | orchestrator | engine-plan | requirements, architecture, open questions drafted incl. corpus+policy revision history | plan gate: awaiting human approval
