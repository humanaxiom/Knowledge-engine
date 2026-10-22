# Security audit: platform-supply-chain close-out (2026-10-22)

Scope: `git diff 34fc0c1 -- .github tests` (uncommitted close-out) and the untracked
evidence `ci/ci-39713504156.log`, `ci/ci-39713519072.log`, `psc9/*` (ci-timeout.md,
red-verify-fast.txt, green-verify-fast.txt, green-verify-full.txt), `psc12-windows-run.txt`,
`psc12-verify-fast.txt`. Read-only audit; no repo file modified except this file, the handoff line and the log entry.

## Verdict: PASS (0 critical, 0 high, 0 medium, 0 low; 4 informational)

## 1. `.github/workflows/ci.yml`
- `git diff --stat 34fc0c1 -- .github tests`: ci.yml 1 line changed (+1/-1). The only change is
  `timeout-minutes: 32` -> `37` and its trailing comment (ci.yml:17).
- Unchanged, verified against the full file: `on: push` / `pull_request`; `permissions: contents: read`;
  concurrency group `ci-${{ github.ref }}`, cancel-in-progress; `runs-on: ubuntu-24.04`;
  `actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5.1.0`; `persist-credentials: false`;
  a single step `./scripts/verify.sh full`. No `env:`, no `secrets.*`, no new step or job.
- `tests/test_stack_ready_docs.py`: only `CI_TIMEOUT_MINUTES` 32 -> 37, its docstring, comment and
  assertion message. Arithmetic checks: 1469 s = 24.48 min -> 24.5 x 1.5 = 36.75 -> 37. No security surface.
- Minutes cost (repo `humanaxiom/Knowledge-engine` is PRIVATE per `gh repo view`): the timeout is a
  ceiling, not a charge; billing is on actual runtime, rounded up per job. Every push to a PR branch runs
  the workflow twice (push and pull_request use different `github.ref`, so concurrency does not cancel
  one for the other): measured 25 + 23 = ~48 billed minutes per push. The change only affects a hung or
  runaway job: worst case 2 x 37 = 74 min per push, up from 64 (+10 min, +5 per job). On a 2,000
  min/month allowance that is ~41 green pushes, or ~27 if both runs hang to the cap. Not a finding.

## 2. Evidence scan (patterns and hits)
| Probe | Hits | Disposition |
|---|---|---|
| Token shapes: `gh[pousr]_`, `github_pat_`, `AKIA/ASIA`, PEM `PRIVATE KEY`, `xox?-`, `sk-`, `AIza`, JWT, `bearer`, `basic <b64>`, `scheme://user:pass@` | 2: ci-39713504156.log:88, ci-39713519072.log:88 `AUTHORIZATION: basic ***` | GitHub-masked checkout extraheader; with persist-credentials false it is removed after fetch. Clean. |
| `token`/`secret`/`password`/`api_key`/`credential` words | ci logs :37 `token: ***` (masked), :138/:141 and :154/:157 `[auth] ... pull token for registry-1.docker.io` (BuildKit anonymous pull, no value); `KE_STORES__*__PASSWORD ... not set` warnings (names only, blank); grype rows for the `passwd` package; `.env.example` "placeholder secrets" hints | No values. Clean. |
| `.env.example` placeholder password string (33 chars) searched literally in all files | 0 | Clean. |
| Profile paths: `C:\Users`, `/c/Users`, `/Users/`, `AppData`, `OneDrive`, `/home/<not runner>`, `USERPROFILE`, `$HOME`, `/root/` | 0 | Clean. Only `/home/runner/...` (allowed) and repo paths `C:\repos\Knowledge-engine`, `/c/repos/Knowledge-engine` (psc12-windows-run.txt:580, :771, :808), which are not profile paths. |
| SIDs `S-1-5-21-...`, `S-1-12-...` | 0 | Clean; psc12-windows-run.txt:27 states SIDs were replaced by `<sid>` and none remain. |
| Usernames (`adam`, `asalah`) | 0 | n/a (allowed anyway). |
| Host names | `aria-alien1` psc12-windows-run.txt:2, :43 | Keep (ruling: keep host names). Model host name `aria-gb10-2` and `10.0.0.*`: 0 hits. |
| IPv4 | 127.0.0.1 (all files); 0.0.0.0 (psc12 refusal case); 172.19.0.2 ci logs :3025-3026, :3710-3711 / :3023-3024, :3713-3714; 172.18.0.2 and 192.168.144.2 psc9/green-verify-full.txt:2072-2073, :1548-1549 | All loopback/unspecified or Docker compose bridge addresses (smoke's ci/offline sink). See I-1. |
| IPv6, MAC addresses | 0 | Clean. |
| Registry credentials: `docker login`, `Login Succeeded`, `auths`, `credHelpers`, `credsStore`, `.docker/config` | 0 | Clean. |
| Internal domains (`.internal/.local/.lan/.corp/sfu.ca`), e-mail addresses | 0 | Clean. |
| High-entropy strings >= 32 chars (excluding hex digests, test names, paths) | only commit SHAs, compose project/volume names, runner-image URLs, 2 GitHub Worker IDs (ci logs :7) | Ephemeral GitHub-hosted runner IDs; not secrets. Clean. |
| Non-loopback host IP in the Windows proof | psc12-windows-run.txt:544, :885-886 | The driver resolves it at run time and prints only `<this host non-loopback IPv4, not recorded>` and `connected: False`. Clean. |

Nothing to redact.

## 3. Throwaway `.env` in the Windows proof
- psc12-windows-run.txt shows `.env` only as a diff against `.env.example` (:152-153, :412-413, :571-576,
  :605-606): the marker comment, `KE_ENV=prod`/`dev`, `KE_BIND_ADDRESS=0.0.0.0`/`127.0.0.1`. None are secrets.
- Process environment is listed by name only (:117-120: `COMPOSE_PROJECT_NAME`, `KE_IMAGE_TAG`).
- No `KE_MODEL_UPSTREAM`, `KE_EGRESS_ALLOWLIST` or `KE_STORES__*__PASSWORD` value appears; the .env.example
  placeholder password string is absent; `.env` removed (:710-711, :770-771) and absent now at repo root.

## Informational (non-blocking)
- I-1: psc9/green-verify-full.txt:1548-1549 records `192.168.144.2`, a compose bridge address from Docker
  Desktop's default 192.168.0.0/16 pool on the dev box. Not a LAN address; no redaction needed.
- I-2: `aria-alien1` (psc12-windows-run.txt:2, :43) stays per the user's evidence-redaction ruling.
- I-3: CI logs carry GitHub Worker IDs and runner-image provisioner URLs (ci logs :2-20); public, ephemeral.
- I-4: Cost: see section 1 (+5 min worst case per hung job; double push/pull_request runs are pre-existing).
