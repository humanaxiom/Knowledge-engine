# platform-config — architect: design folded to human rulings Q30, Q20, Q7 and placeholder secrets

Date: 2026-10-18. File touched: `docs/architecture.md` only.

## Asked
Update the design to Q30 (gates-it gets a route out), the `changeme-` placeholder ruling, Q20 (no macOS),
Q7 (model host `aria-gb10-2`, config only), and fold harness-followups I2 and security L24 into ADR-KE-001.

## Did (`docs/architecture.md`)
- **Header:** ADR-KE-009 accepted with the Q30 amendment; rulings listed.
- **§2.1:** a network table (`edge`, `backend` internal, `gates-it` not internal and holding only `gates-it`,
  `offline` internal). The `gates-it` row is on `backend` plus `gates-it`. The model-host row names `aria-gb10-2` in
  prose, carried by `KE_MODEL_UPSTREAM`. The diagram separates `probe` (backend only) from `gates-it` (route out,
  accepted risk). Model-calling tests use the app path, ModelClient → gateway → upstream, so DR30 applies.
- **§2.2:** status accepted. The `.invalid` upstream is replaced: `config/verify.env` no longer overrides
  `KE_MODEL_UPSTREAM`. There is one probe per run (`GET /models` through ModelClient). If it fails, the tests raise
  `SkipTest("model host unreachable: <KE_MODEL_UPSTREAM> (<reason>)")`. No other test may skip on network grounds.
  The `verify full` sequence diagram gains the probe and the run-or-skip branch. Added: the socket guard is now the
  only test-side layer, and `UV_OFFLINE=1` is set in the gates anchor.
- **§2.3/§2.4:** placeholders are `changeme-<key>`. Refusal 5 is any `SecretStr` starting with `changeme` while
  `env≠dev`. It reads no file and names the key, never the value. The app image no longer copies `.env.example`.
  `.env.example` carries `KE_MODEL_UPSTREAM=aria-gb10-2:<port>` and is the only committed config file that names it.
- **§2.4/§2.5, ADR-KE-012:** macOS removed. The scripts are bash for Linux and PowerShell for Windows. The
  quickstart has two paths. The bundle is linux/amd64, and Apple silicon is out of scope.
- **§2.6:** added fast tests `test_env_example_secrets_use_changeme_prefix`, `test_gates_it_network_topology` and
  `test_model_skip_reason_names_upstream`, plus the integration test `test_model_client_reaches_configured_host`
  (skips by name). `test_socket_guard_blocks_outbound` drops its "raw connection fails because internal" clause,
  and `ci/offline` still proves the app has no route out. platform-stack is no longer blocked.
- **ADR-KE-001:** the amended-by line now covers the `gates-it` network. New "Further consequences":
  - I2: verify.sh needs a grep with PCRE support, and fails closed without it (the FAIL message blames the sentinel).
  - L24: on main, the hook does not catch alias verbs, variables, `eval`, encodings or `gh pr merge`.
  The on-main bypass bullet cross-references this.
- **ADR-KE-003:** "Amended by Q30" note.
- **ADR-KE-009:** rewritten. Status accepted with the amendment. Decision (a), plus the route out that (c) would
  have given. Consequences: local `full` covers more than CI (the CLAUDE.md row is an orchestrator or documenter
  edit), and tests can reach the internet, a risk the human accepted (exfiltration of the checkout and verify env;
  mitigations: no socket, placeholder secrets only, `UV_OFFLINE=1`, unit `gates` without a network).
- **ADR-KE-010/011:** placeholder and Q7 bullets added. ADR-KE-011 notes that the network layer is unchanged for the app.

## Flags for the orchestrator (not assumed)
- F-A: model calls go through the gateway, which already has a route out on `edge`. So no planned test needs
  `gates-it`'s own external route. It is kept because Q30 rules it. If the human only wanted model reachability,
  `gates-it` could stay internal and the internet-exposure risk would go away. Worth one confirming question.
- F-B: the placeholder prefix match is case-sensitive (`changeme`), as ruled. Case-folding (`CHANGEME…`) would be
  stricter. Analyst or orchestrator to decide in PS-1.9.
- Others' edits: the CLAUDE.md "What verify.sh runs that CI cannot" row, the AGENTS.md "denies any commit/push"
  softening (L24), and test.sh's stale testcontainers header are not architect files.

## First tests (unchanged lead)
platform-config RED starts with `test_config_defaults_and_env_override`. The new placeholder tests are step 5 in §2.6.
