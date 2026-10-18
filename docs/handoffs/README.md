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
