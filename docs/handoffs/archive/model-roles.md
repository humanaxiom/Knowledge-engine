# Handoff: model-roles

Outcome metric moved: neither directly. It makes the engine's model roles point at models that actually exist on the model host (aria-gb10-2), a precondition for any draft a reviewer can act on.
Spec: `docs/requirements.md` (model roles, PS-2.x model wiring). Design: `docs/architecture.md` §2.4 Model wiring.
Base: `agent/platform-offline` @ 8b7425c. Previous handoff: `docs/handoffs/archive/platform-offline.md`.

## 2026-10-20 — orchestrator: item opened
- Human ruling (2026-10-20): compose + rewrite = `qwen3.5:latest`, audit = `gpt-oss:120b`, embed = `nomic-embed-text`. All present on aria-gb10-2:11434 (`GET /api/tags`); closes Q38 with no pulls.
- Scope: config/defaults.yaml model names; any tests/docs that pin the old names (qwen2.5:14b-instruct, llama3.1:8b); a recorded model run against aria-gb10-2 proving each role answers (PS-2.21 style). No new features.
- 2026-10-20 orchestrator: stacked PRs opened (human approved): #1 harness-claude-code→ccr-19465ed4-j1u0m5, #2 harness-followups, #3 platform-config, #4 platform-stack-up, #5 platform-stack-ready, #6 platform-offline (each based on the previous branch). PRs 2–3 heads fail the hook 5 MB timing test on CI (3.3–3.6 s vs 3 s; re-run also failed); fixed by 0f2821c in PR 4. Merge in order with merge-commit or rebase, not squash; delete each branch after merge for auto-retarget.

## 2026-10-20 — analyst: acceptance criteria
- Asked: write the model-roles criteria (role names, fast pins, retired names, recorded aria-gb10-2 run per role, Q38 resolved); note role-specific concerns.
- Wrote `docs/requirements.md` § "Item: model-roles" (placed before ingest-ledger): MR-1 role defaults (compose/rewrite `qwen3.5:latest`, audit `gpt-oss:120b`, embed `nomic-embed-text` dim 768; all four pinned, no inheritance between roles); MR-2 fallback (blocked on Q54); MR-3 scanner knows the new names; MR-4 retired names gone from living files (recorded grep, with history excluded); MR-5 recorded full run: readiness test plus one model-calling test per role (`test_{compose,rewrite,audit,embed}_role_answers`) through `ModelClient`/gateway, with none skipped and the evidence recording `/api/tags` digests and per-role time; MR-6 timeouts unchanged unless measured (Q55); MR-7 Q38 closed.
- Done in this step: PS-1.2 model sentence amended (old wording kept as superseded); requirements open-Q list updated; `docs/open-questions.md` A7 amended, Q38 resolved (A38), Q54 and Q55 added.
- Q54 (blocks MR-2): the ruling names no `fallback_model`; `llama3.1:8b` is not installed; the key is required in the settings but no code reads it. Options: own model, another installed model, or nullable (a schema change).
- For the architect: (1) `ModelClient` has no embedding call, so choose between a new method (needs a span and a unit test) and a direct POST from the test; (2) `gpt-oss:120b` cold load plus reasoning against the 120 s httpx timeout, and Ollama evicting models between roles (test order); (3) reasoning models can return empty content under a low max_tokens; (4) gateway stream `proxy_connect_timeout 5s`, default `proxy_timeout` 10 min; (5) the readiness probe checks only compose `/models`.
- Still to update (developer/architect): `config/defaults.yaml`, `tests/test_engine_config.py`, `tests/test_engine_hardcoded.py` (lines 80-81, 249), `docs/architecture.md` §2.4 layout block (lines 687-690).
- Evidence: `COMPOSE_PROJECT_NAME=ke-analyst-mr scripts/verify.sh fast` gave PASS; output in `docs/evidence/model-roles/analyst-verify-fast.txt`.

## 2026-10-20 — orchestrator: rulings Q54, Q55, embedding call
- Q54: fallback_model for compose, rewrite, audit = `gpt-oss:20b` (installed on aria-gb10-2; faster than the primaries and distinct from them). The human may change it. Unblocks MR-2.
- Q55: accept A55. Timeouts stay 120 s (chat) / 60 s (embed) unless the MR-5 run measures a slower call; a new value only from that measurement.
- Embedding: NO new ModelClient method (no new features; product embeddings arrive with knowledge-plane). test_embed_role_answers posts to `/embeddings` through the gateway forward with the role's base_url, and asserts the gateway host and dim 768.

## 2026-10-20 — architect: design
- Asked: design for MR-1..MR-7 with the Q54/Q55/embedding rulings; restore MR-2.
- Wrote `docs/architecture.md`: §2.3 layout block (new names, `gpt-oss:20b` fallback); §2.4 *Model roles* (roles table, no new client method, chat assertions and `max_tokens`, run order and cold loads, timeouts rule, gateway timeouts); §2.6 *model-roles* (first tests); ADR-KE-014 (accepted). No other ADR named the old models.
- `docs/requirements.md`: MR table fallback cells = `gpt-oss:20b`; MR-2 un-blocked, `[unit: test_model_role_defaults]`; it also states that MR-3's scan covers `gpt-oss:20b`.
- Decisions: config only, no schema, client, gateway or span change. Embed test POSTs `{base_url}/embeddings` via `ModelClient(settings,"embed").http_client`. Chat tests call `complete()` unchanged (no `max_tokens`), one-word prompt, assert 200 + `model` + non-empty `content` (not content-or-reasoning); the failure message gives `finish_reason` and the message key names. Order embed→compose→rewrite→audit in `tests/integration/test_model_roles.py` via `load_tests` (unittest would otherwise sort audit first). Each test prints `model-role <role> <model> <s>s` to stderr. No warm-up; `/api/ps` before and after, `ollama show --parameters` recorded. Timeout rule if MR-5 measures an overrun: ceil(1.5 × measured, next 30 s), orchestrator rules; >570 s means escalate (gateway `proxy_timeout` 600 s). Gateway 5 s connect / 10 min idle do not bind.
- For the orchestrator: `docs/open-questions.md` Q54/Q55 still read as open/assumed; mark them ruled (analyst). The requirements "Open questions for this item" Q54 bullet still says it blocks MR-2. MR-4's "`llama3.1:8b` may stay only if Q54 rules it" now means it goes.
- First tests (tester): `test_model_role_defaults` (RED), then `test_no_hardcoded_hosts_or_models` with the new declared set (RED), then update `test_planted_model_name_is_flagged` (stays green). Integration: the four `test_*_role_answers` in the recorded run.
- Evidence: `COMPOSE_PROJECT_NAME=ke-arch-mr scripts/verify.sh fast` gave PASS (685 tests, 8 skipped); see `docs/evidence/model-roles/architect-verify-fast.txt` and `architect.md`.

## 2026-10-20 — analyst: record Q54/Q55 rulings
- Asked: mark Q54/Q55 ruled; un-block MR-2 in the item's open-question list; MR-4 drops the `llama3.1:8b` exception.
- `docs/open-questions.md`: Q54 resolved (A54: fallback `gpt-oss:20b` for compose, rewrite, audit; orchestrator ruling, human may change); Q55 resolved (A55 accepted); original wording kept for the record. A7 and Q38 "follows Q54" pointers now name `gpt-oss:20b`.
- `docs/requirements.md`: PS-1.2 amendment names the `gpt-oss:20b` fallback; MR-4 says `llama3.1:8b` does not stay (retired name, only in superseded text); "Open questions for this item" now reads none open.
- Next: tester/developer per architect's first tests; no criteria changed beyond the above. No tests or code touched; verify not run (docs only, tester editing tests concurrently).

## 2026-10-20 — tester: RED tests
- Wrote `test_model_role_defaults` (MR-1/2/6; old compose/embed model pins moved out of `test_config_defaults_and_env_override` per §2.6 step 1, ADR-KE-014), the new required set in `test_no_hardcoded_hosts_or_models`, the `gpt-oss:120b` plant, `tests/integration/test_model_roles.py` (4 role tests, `load_tests` order), and `ModelRolesSuiteTest` in `tests/test_stack_model_skip.py` (fast: keys unset gives a "not configured" skip with no probe, the run order, and §2.4 assertions/timing lines on a stub host). MR-4 is a recorded grep gate, so it has no test and the developer saves `retired-names-grep.txt`. `COMPOSE_PROJECT_NAME=ke-tester-mr scripts/verify.sh fast` gave the expected RED: 689 tests, failures=13 (12 subtests of `test_model_role_defaults` plus `test_no_hardcoded_hosts_or_models`, all old defaults.yaml values), lint PASS; `docs/evidence/model-roles/red-verify-fast.txt`. Next: developer edits only `config/defaults.yaml` (no test edits needed), then MR-4 grep and MR-5 recorded full run.

## 2026-10-20 — developer: GREEN (config) and MR-4 grep
- Edited only `config/defaults.yaml`: compose/rewrite `qwen3.5:latest`, audit `gpt-oss:120b`, all three fallbacks `gpt-oss:20b`; embed and timeouts unchanged. No test edits. `COMPOSE_PROJECT_NAME=ke-dev-mr scripts/verify.sh full` (model keys unset, no .env) gave PASS (523 s): 689 tests, OK, skipped=8; `test_model_role_defaults` and `test_no_hardcoded_hosts_or_models` now ok; the four `test_*_role_answers` skip "model host not configured"; `docs/evidence/model-roles/green-verify-full.txt`.
- MR-4 grep: config, tests, scripts, README, .env.example and quickstart have 0 hits; the 13 remaining hits are all in `docs/requirements.md`, `docs/open-questions.md` and `docs/architecture.md` ADR-KE-014, text marked superseded or kept for the record, which MR-4 allows; `docs/evidence/model-roles/retired-names-grep.txt`. MR-5 recorded run against aria-gb10-2 is still to do (needs the keys). Not committed.

## 2026-10-20 — security: review + security audit
- Verdict PASS / APPROVED. MR-1..MR-7 and ADR-KE-014 conform; no secrets; egress only via guarded client to `gateway` (gates-it internal network as backstop). Mutants M1a-e, M2a, M3a, M4c, M5-M9 killed; MR-4's 12 lines / 13 matches are acceptable in substance. Supply-chain note: `qwen3.5:latest` and untagged `nomic-embed-text` are moving tags, and MR-5 digests are the record. `docs/evidence/model-roles/audit.md`, `audit-mutants.txt`.
- Low, non-blocking, for developer/tester before commit: L-MR1 the stub uses the real allowlist shape and asserts request host == gateway (M1b survives with `gateway,modelhost`); L-MR2 every stderr line must match the timing regex (M4a/b survive); L-MR3 HIDDEN in the model-mismatch case (M3c survives); L-MR4 misroute every role (M2b survives); L-MR5 embed non-200 message echoes the body; L-MR6 the analyst widens MR-4's exception list.

## 2026-10-20 — tester: MR-5 recorded run (aria-gb10-2)
- `KE_MODEL_UPSTREAM=aria-gb10-2:11434 KE_EGRESS_ALLOWLIST=aria-gb10-2 COMPOSE_PROJECT_NAME=ke-tester-mr5 scripts/verify.sh full` gave PASS (578 s; unit 689 OK skipped=8, integration 15 OK skipped=1 (the .env mask test, not model-calling), smoke /readyz ready, offline_check PASS). All 5 model-calling tests ran ok, none skipped: embed 0.1 s (probably warm), compose 32.6 s (cold qwen3.5 load), rewrite 4.2 s (warm), audit 17.7 s (probably cold, not proven: the host has other clients) and `test_readyz_reports_reachable_model_host`. Digests, `/api/show` (no `num_predict` cap), `/api/ps` before and after: `docs/evidence/model-roles/model-run-aria-gb10-2.txt`.
- Q55 not triggered: every call was well inside `timeout_s` (120/60), so no ReadTimeout, warm-up, measurement or timeout proposal, and no config change. Next: review and security, then the orchestrator's own `verify.sh full`.

## 2026-10-20 — analyst: L-MR6 (MR-4 exception list) and A7 tag note
- MR-4 now lists its exceptions exactly: PS-1.2 superseded note, A7/Q38 original wording, Q54/A54 text (open-questions and the item's open-questions summary), MR-4's own text, ADR-KE-014 context. Any other hit fails MR-4.
- Count: the grep gives 12 lines; `grep -o` gives 16 occurrences, not 13 (some lines name both retired names). MR-4 states 12 lines / 16 occurrences. Re-checked after the edit: still 12 lines, all in the list; line numbers shifted, so `retired-names-grep.txt` should be re-recorded before commit.
- A7: one sentence added: config names are tags, not pins; the MR-5 `/api/tags` digests record what was tested (ADR-KE-014).

## 2026-10-20 — tester: tighten L-MR1..L-MR5 (tests only)
- Stub env uses the real allowlist shape (`gateway,modelhost`), the stub records request hosts == {gateway}; every stderr line must match TIMING; HIDDEN/OTHER_MODEL never in failure text; misroute loops all 4 roles; new embed-500 case pins status + content-type only. Integration test: mismatch uses assertTrue (no response model in the message), embed non-200 omits the body. RED first (`tighten-red.txt`, 5 failures for the expected leaks), then `COMPOSE_PROJECT_NAME=ke-tester-mr2 scripts/verify.sh fast` gave PASS (689 OK, skipped=8; `tighten-verify-fast.txt`). Mutants M1b, M2b, M3c, M4a, M4b are now killed; all M1-M9 killed except M3b (harmless); `docs/evidence/model-roles/tighten-mutants.txt`. L-MR6 (docs) is left to the analyst.

## 2026-10-20 — orchestrator: item closed + milestone Done check (model-roles)
- Gates: review+security PASS/APPROVED (audit.md; L-MR1..5 tightened, mutants killed: tighten-mutants.txt); MR-5 recorded run PASS (model-run-aria-gb10-2.txt); orchestrator verify full PASS 558 s WITH the model host (orchestrator-model-verify-full.txt): embed 1.1 s, compose 12.4 s, rewrite 8.8 s, audit 17.8 s, readyz against the real host ok, 15/15 integration tests ran, none skipped. MR-4 grep: 12 lines / 16 matches, all allowed history (retired-names-grep.txt).
- CI note: GitHub CI cannot reach aria-gb10-2, so the role tests skip there with the named reason; the model proof is the recorded local runs above.
- Outcome metrics: drafts reviewed n/a, ratified rules n/a. Not moved, by design: the engine's roles now point at models that exist (precondition for drafting).
- External blockers: Q18 branch protection (Adam Salah); Q14 ratification owners (OWNER-TBD). Q38 closed.
- Carried forward: re-run MR-5 after any model pull on aria-gb10-2 (tags, not pins); record the embed digest with vectors in knowledge-plane; optional readiness digest check.
