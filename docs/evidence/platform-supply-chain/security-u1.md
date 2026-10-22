# security-u1: PSC-11 + PSC-10 (PSScriptAnalyzer pinned by SHA-512)

- Date: 2026-10-21. Role: security. Branch `agent/platform-supply-chain`; diff `git diff agent/ci-speed-closeout -- docker tests` (`docker/gates.Dockerfile`, `tests/test_gates_docker_cli.py`), uncommitted working tree.
- **Verdict: PASS.** 0 critical, 0 high, 0 medium, 1 low, 6 info.
- Evidence:
  - `docs/evidence/platform-supply-chain/security-u1-psa-hash.txt`: Q48 re-check, with commands and output;
  - `docs/evidence/platform-supply-chain/security-u1-build-checks.txt`: wrong-hash build, no-cache build, image inspection, zip-slip, dash semantics.
- Scratch only: build context and downloads in a session scratch dir, containers and images labelled `ke.audit=security-u1` (tags `ke-sec-u1-psa:*`). No repo file was modified except this verdict and the two evidence files.

## 1. Q48 provenance (D7): MATCH
- The gallery OData `Packages(Id='PSScriptAnalyzer',Version='1.25.0')` returns `PackageHashAlgorithm` = SHA512 and `PackageHash` = `5/tXMm...ExwWYw==`. In hex that is `e7fb5732...131c1663`.
- A fresh download redirects once, `api/v2/package/...` to `https://cdn.powershellgallery.com/packages/psscriptanalyzer.1.25.0.nupkg` (HTTPS), and is 14,658,674 bytes. Its local sha512 is the same value.
- Both equal `ARG PSSCRIPTANALYZER_SHA512` (docker/gates.Dockerfile:41). This agrees with the developer's record `psscriptanalyzer-sha512.txt`.
- Member scan of the real nupkg: 53 entries, no absolute, `..`, drive or backslash names, and no symlink entries.

## 2. The module RUN (docker/gates.Dockerfile:40-49): an unverified or tampered package cannot be unpacked or loaded
- **curl (:43-44).**
  - `--proto '=https' --proto-redir '=https' --tlsv1.2`, no `-k`; `-f` fails on HTTP >= 400; `-L` follows one redirect to the HTTPS CDN.
  - The system CA bundle (Debian `ca-certificates`) is used. A failed or partial transfer exits non-zero, and `set -eu` stops the RUN.
- **Check (:45).**
  - `echo "$PIN  /tmp/psa.nupkg" | sha512sum -c -` runs under dash. A pipeline's status is its last command's, so pipefail is not needed: `echo` cannot fail in a way that hides a mismatch.
  - Proven in a container: empty, wrong, garbage hash and missing file each give exit 1 and the next step is not reached; only the good hash reaches it (build-checks section 5).
  - A real build with a 1-digit-wrong pin stops at `/tmp/psa.nupkg: FAILED`, exit 1, with no unzip or pwsh output (build-checks section 1). It is the first reader of the file; no `||`, no `--ignore-missing`.
- **Zip-slip (:47).**
  - Tested on Python 3.12.15, in the pinned base image. `zipfile -e` → `extractall` strips the leading `/` and `..` components: `../../../../../../tmp/x`, `/tmp/x` and `sub/../../x` all landed inside the target dir.
  - A `S_IFLNK` entry is written as a regular file (zipfile never creates symlinks), so a write "through" it fails with NotADirectoryError, exit 1, and set -e stops the build (build-checks section 4).
  - The hash check is sufficient on its own: no file is read before a SHA-512 match against a pin that equals the publisher's hash, and the real archive has no hostile entries. Sanitisation is defence in depth.
- **Leftovers.**
  - `/tmp` is empty after the build, and the `.nupkg` is removed (:48). A failed RUN commits no layer.
  - Everything under `/usr/local/share/powershell` is root-owned 0644/0755, with no path writable by uid 10001. `.signature.p7s` remains (L-U1-1).
- **Module resolution.**
  - In the built image, as uid 10001: `PSModulePath` = `/usr/local/share/powershell/Modules:/opt/microsoft/powershell/Modules`. `Get-Module -ListAvailable PSScriptAnalyzer` lists only the 1.25.0 copy, and `Import-Module` loads `/usr/local/share/.../1.25.0/PSScriptAnalyzer.psm1`.
  - `$PSHOME/Modules` (pwsh 7.4.21) has no PSScriptAnalyzer.
  - The user-scope path is `$HOME/.local/...`, and `HOME=/`, which uid 10001 cannot write. The compose gate services set no `HOME` or `PSModulePath` and pass no build args (docker-compose.yml:37-56). The repo is mounted read-only and `/tmp` is the only writable path.
  - Shadowing would therefore need code execution inside the gate container already.
- **Import (:49).** `-ErrorAction Stop`, so a broken unpack fails the build.

## 3. PSC-11: in effect before pwsh first runs
- `ENV POWERSHELL_TELEMETRY_OPTOUT=1 POWERSHELL_UPDATECHECK=Off` is at docker/gates.Dockerfile:6-7, directly after the final FROM and before every RUN. Each key is set once (the late ENV block no longer sets them).
- pwsh is first started at :49; the tarball RUN (:24-38) does not start it. The uv stage never runs pwsh.
- Both values are present in the built image's environment (build-checks section 3).

## Findings
| ID | Sev | Where | Finding | Action |
|---|---|---|---|---|
| L-U1-1 | low | docker/gates.Dockerfile:48 | `.signature.p7s` (12,873 B, the NuGet author signature) is left in the module dir. It is inert: never loaded and never verified (D7 rejects NuGet signature verification). | Optional: add it to the `rm` list. Non-blocking. |
| I-U1-2 | info | D7 / docker/gates.Dockerfile:41 | Residual trust: the pin is the gallery-computed PackageHash, so the anchor is the gallery at pin time (TOFU on the gallery). The author signature is not checked. This is the accepted D7 design. | None; record only. |
| I-U1-3 | info | docker/gates.Dockerfile:31, :72, :88 (pre-existing, not in this diff) | The pwsh, docker and compose curls lack `--proto-redir '=https'`. Not exploitable, because each is sha256-checked before use. | Consistency follow-up, optional. |
| I-U1-4 | info | docker/gates.Dockerfile:49, :47 | `-Command "Import-Module ..."` is double-quoted, while D7 says a "fixed single-quoted literal". The string has no `$` or backtick, so there is no expansion and no effect. :47 repeats the literal path instead of `"$dir"`. | Cosmetic. |
| I-U1-5 | info | docs/architecture.md D7 | D7 names `psa-hash.md`; the actual record is `psscriptanalyzer-sha512.txt` (already flagged by the orchestrator). | Docs fix at review. |
| I-U1-6 | info | docs/evidence/platform-supply-chain/red-psc10-11-scratch-green.Dockerfile.txt:40 | Placeholder pin `abab...` (128 hex). It is `.txt`, outside the repo-root `*Dockerfile*` glob (tests/test_gate_least_privilege.py:134), and built by nothing; a build from it would fail closed at sha512sum. | None. |
| I-U1-7 | info | docs/evidence/platform-supply-chain/green-psc10-11-verify-full.txt:1 | The developer's verify full ran without a model host, so the model tests skipped. This diff does not touch model paths, so it is not a security concern. Noted for the orchestrator's own pre-commit full run. | None. |

## 4. Evidence scan (docs/evidence/platform-supply-chain/, all files)
- Profile paths (`X:\Users\...`, `/c/Users/...`, `/home/...`, `/Users/...`, `AppData`): 0 hits.
- SIDs (`S-1-5-..`): 0 hits.
- Secrets: 0 hits. Checked: key/token/password assignments, private-key headers, AWS/GitHub/OpenAI/Slack token shapes, credentialed DB URLs, and long opaque strings (hits were hashes, paths, container names, and the public PackageHash).
- My own two evidence files write the session scratch dir as `<scratch>`, with the profile path redacted.

## Secret grep of the diff
`git diff agent/ci-speed-closeout -- docker tests`: no API keys, tokens, private keys or connection strings. The only long values are the public SHA-512 pin and the test fixtures' hex.

## Traces
Not applicable. The change adds no span, retriever or agent step.
