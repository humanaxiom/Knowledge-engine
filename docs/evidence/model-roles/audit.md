# model-roles: combined review + security audit (2026-10-20)

**Verdict: PASS / APPROVED** (security: no critical/high; review: conforms to MR-1..MR-7 and ADR-KE-014). Six low findings and one supply-chain note, none merge-blocking. L-MR1 to L-MR4 are test-only hardening, cheap to land before the commit.

Scope: `git diff 8b7425c` plus untracked (`tests/integration/test_model_roles.py`, `docs/handoffs/model-roles.md`, `docs/evidence/model-roles/*`). `docs/knowledge-engine-claude-code-prompt.md` is the user's file, untracked since harness-claude-code and never staged, so it is out of scope.
Mutant run, the environment-dependence check and host notes: `docs/evidence/model-roles/audit-mutants.txt`.

## Conformance
- MR-1/MR-2/MR-6: `config/defaults.yaml` matches the MR table (compose/rewrite `qwen3.5:latest`, audit `gpt-oss:120b`, fallbacks `gpt-oss:20b`, embed unchanged, timeouts unchanged). `test_model_role_defaults` pins all four roles, `base_url` null, fallback distinct from the primaries, embed has no `fallback_model` (file and schema), `readiness.timeout_s` 2, and per-role override with no inheritance (audit and compose markers).
- MR-3: the required declared set has the new names (`gpt-oss:20b` included). The planted fixture uses `gpt-oss:120b`.
- MR-5/§2.4: the four tests match the design. Order comes from `load_tests` (killed M6). Each is `@model_calling` with `require_model_host(self)` first (AST check, killed M5). Chat tests use unchanged `complete()` with no `max_tokens`. They check status 200 through the client's own event hook, the model echo (killed M7) and non-empty stripped `content` with reasoning not accepted (killed M9). The embed test posts through `client.http_client` with dim == `models.embed.dim` (killed M8). A gateway-host assertion is in the shared `_client` (killed M2a). There is one stderr timing line per role. Skip reasons are the exact PS-2.7 "not configured" text for both keys, with no probe.
- MR-7: Q38/A38, Q54/A54 and Q55/A55 are resolved, and the original wording is kept and marked.
- Unit tests that changed: green in the developer's container run (`green-verify-full.txt`) and in my scratch run of `ModelRolesSuiteTest` (3 ok).

## Security checks
- Egress: every request goes through `ModelClient.http_client` (GuardedTransport, `trust_env=False`) to `base_url`, asserted to be host `gateway`. No test names the model host. Defence in depth: `gates-it` is only on the `internal: true` backend network, so a direct request has no route out even if a test regressed.
- Logging: stderr gets only `model-role <role> <model> <s>s`. The chat failure message gives `finish_reason` and message key names only (killed M3a). The prompt and input are fixed, non-personal strings ("Reply with the single word: ready", "ready").
- Secrets: a grep of the diff plus untracked files for key/token/private-key/connection-string patterns finds nothing (only test names and private docker IPs in verify logs). No key is written to files. Skip and failure texts name keys (`KE_MODEL_UPSTREAM`, `KE_EGRESS_ALLOWLIST`), never values.
- Traces: chat goes through the existing `model.<role>` LLM span. `telemetry.hide_inputs` and `hide_outputs` default to true. The embed call is test code (ADR-KE-014), so no span. Nothing new is exported.
- No injection, deserialization, path, SSRF or dependency change (config/tests/docs only; no `uv.lock` change).

## Findings (all low, non-blocking)
- **L-MR1: the direct-host kill depends on the stub's allowlist.** M1a–M1e (embed to the model host, guarded or unguarded) are killed only because the stub env sets `KE_EGRESS_ALLOWLIST=gateway` (EgressDenied), or because the status hook sees no request. With the real-run shape (`gateway,modelhost`) a guarded direct-host embed passes (checked; see evidence). Fix: in the "answers" case use `KE_EGRESS_ALLOWLIST=gateway,modelhost` and `KE_MODEL_UPSTREAM=modelhost:8000`, have `_stub` record `request.url.host`, and assert that the set of hosts is `{"gateway"}`.
- **L-MR2: stderr is not limited to the timing line.** M4a (print the chat result) and M4b (print the embed input and body) survive, because the test filters stderr with `TIMING` instead of asserting that every non-blank line matches it. Fix: assert that every stderr line matches `TIMING` in each stub case.
- **L-MR3: the no-values check covers only the reasoning-only case.** M3c (the model-mismatch message prints `result`) survives. Fix: put `HIDDEN` in `content` in the "response names another model" case, and `assertNotIn(HIDDEN, text)` for every failure text in every case. M3b also survives, but it is harmless: content is empty or whitespace on that path.
- **L-MR4: the misroute subtest covers audit only.** M2b (host assertion skipped for embed) survives. Fix: loop the "base_url not through the gateway" case over all four roles.
- **L-MR5: the embed non-200 message includes `response.text[:300]`.** That is a server body value. §2.4's "keys, never values" rule is stated for chat only. An Ollama or gateway error body carries no prompt data here, but a misrouted upstream could put arbitrary HTML into committed evidence. Option: report only the status and content-type. Accept as-is if the orchestrator prefers the diagnostics.
- **L-MR6 (docs): MR-4 wording vs. hits.** The grep gives 12 lines (13 matches; the handoff says "13 hits"). 5 lines fall outside MR-4's named exceptions (A7 and Q38 original wording, the PS-1.2 note): `requirements.md` 2160, 2167–2169 (MR-4's own text) and 2268 (the Q54 summary), `open-questions.md` 213 (A54), and `architecture.md` 5096 (ADR-KE-014 context). Every hit names a retired model in order to retire it, or is marked superseded or kept for the record. None is a living use, so **MR-4 is met in substance**. The analyst should widen MR-4's exception list to "text that records the retirement (MR-4, Q54/A54, ADR-KE-014 context)" so the criterion matches its evidence, and correct the count.

## Supply-chain note on the ruling (recommend a note; the ruling is unchanged)
- `qwen3.5:latest` is a moving tag. `nomic-embed-text` has no tag, so it is implicitly `:latest`. Ollama `gpt-oss:*` tags are mutable too: only a digest is immutable. Any `ollama pull` on aria-gb10-2 can silently swap the weights behind the same config value. For `:latest` that can also change the parameter size, which changes memory, cold-load time and the 120 s timeout basis.
- Mitigation already in MR-5: the evidence records the `/api/tags` digest per model. Suggested note for ADR-KE-014 and A7:
  1. Config names are tags, not pins. The MR-5 digests are the record of what was verified.
  2. Re-run MR-5 after any pull on the model host.
  3. When knowledge-plane stores embeddings, record the embed model digest with each vector set, so that a silent swap, which needs a re-embed, is detectable.
  4. A later item may have readiness compare the live digests with the recorded ones.
- Trust boundary: weights come from the Ollama registry and the publisher, and they are parsed by the model host's Ollama. Keep that Ollama patched; past pull/GGUF CVEs include CVE-2024-37032. It is outside this repo. Weights are not in the offline bundle, so there is no licence obligation in the bundle today. Confirm each model's licence before any redistribution.

## Host note
On the Windows host venv, 3 pre-existing `ModelSkipHelperTest` cases fail with `ssl.SSLError`, because `environ()` clears the Windows environment. They are ok in the gates container and are not caused by this change (detail in `audit-mutants.txt`).
