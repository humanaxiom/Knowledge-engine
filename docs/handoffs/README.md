# Handoff Documents

One file per plan item: `docs/handoffs/<plan-item-slug>.md`. Every role that
touches the item reads it before acting and appends a new dated section after
— never rewrites or deletes another role's section. This is how context
survives across stateless subagent invocations.

Suggested section template per append:

```
## <ISO timestamp> — <role>
- Asked to: ...
- Did: ...
- Decided/found: ...
- Evidence: ...
- Next role needs to know: ...
```

Keep each handoff doc forward-looking and under 200 lines (a test enforces
the cap). Move history to `docs/handoffs/archive/`.

## Milestone Done check

Run at the end of every milestone (each committed plan item) and append the
answers to that item's handoff doc before archiving it. The project's outcome
metrics are **drafts a human reviewer has acted on** and **ratified rules**.

```
## <ISO date> — orchestrator: milestone Done check
- Outcome metric(s) this item names: ...
- Value now: ... (query or live page that produced it)
- Value at the last milestone: ...
- If it did not move, why: ...
- External blocker, if any: <what> — <named person> — <date expected>
```

A "Value now" without the query or page that produced it does not count.
