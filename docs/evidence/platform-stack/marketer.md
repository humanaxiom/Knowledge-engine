# marketer: platform-stack-up changelog gate (2026-10-19)

Scope: CHANGELOG.md only. README.md, CLAUDE.md and docs/quickstart.md are
owned by the documenter and were not touched.

## Entry added
CHANGELOG.md, under [Unreleased], new sub-block `### 2026-10-19 (platform-stack-up)`
above the platform-config block. Sections: Added, Changed, Security.

## Claims checked against the tree
- Services and ports: docker-compose.yml publishes only the gateway (47100
  API, 47101 Phoenix, defaults from `.env.example`). Phoenix publishes nothing
  itself (ADR-KE-011 ports amendment).
- Engine >= 28: scripts/launch.sh refuses older engines; docs/quickstart.md
  states the requirement.
- Digest pins: docker-compose.yml image lines for postgres, neo4j, valkey and
  phoenix carry `@sha256:`.
- Gateway upstream and port checks, backend isolation, LAN refusal and
  provider identity: ADR-KE-011 and handoff rework 2 (M-2, M-3, L-3, Q33,
  M5 / R3).

## Gate evidence (from the handoff, not re-run by marketer)
- verify.sh full PASS, 319/319 unit + 3/3 integration, live smoke:
  docs/evidence/platform-stack/green-rework2-final.txt
- Reviewer approved rework 2: docs/evidence/platform-stack/review-rework2.md
- Security PASS, 0 critical/high: docs/evidence/platform-stack/security-rework2.md
- Windows proof PASS (Q31): docs/evidence/platform-stack/windows-proof-rework2.txt

## Not announced
- Commit and CI are not yet done. The entry is staged as text only; the
  orchestrator should confirm CI green on the 2a commit before release.
- Deferred items (review nits, security L-5, L-8, L-9, L-10) are not mentioned.
- Worker is an idle placeholder until platform-stack-ready (2b); the entry
  does not claim job processing.
