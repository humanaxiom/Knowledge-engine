# Security audit: platform-offline unit 1 (L-5, PS-3.5), 2026-10-19

Scope: `git diff 4b19971` of docker-compose.yml, docker/gates.Dockerfile,
pyproject.toml, scripts/test.sh, scripts/verify.sh, plus the untracked
docker-compose.gates-mask.yml, docker/empty, tests/test_gate_least_privilege.py,
tests/integration/test_gate_least_privilege.py and the changes in
tests/test_harness_followups.py and tests/test_stack_scripts.py.
Raw probe output: docs/evidence/platform-offline/security-l5-probes.txt.
Probes ran from a scratch copy at <scratch>/repo copy (the path has a space) with
projects ke-sec-l5-* and the existing ke-gates image (--pull never, no build).
Every probe container was --rm. No volumes, networks or images were left behind.

**Verdict: PASS.** No critical or high findings. There is one medium and five low findings, none of them merge-blocking.

## Findings

### M-1 (medium): fast mode with no .env does not pin COMPOSE_FILE, so a caller COMPOSE_FILE or an auto-loaded override can undo L-5
- Where: scripts/verify.sh:32-37. COMPOSE_FILE and COMPOSE_PATH_SEPARATOR are exported only inside `if [ -n "$gates_mask" ]`.
- Effect: with no .env, compose falls back to the COMPOSE_FILE inherited from the caller, or, when that is unset, to an auto-loaded docker-compose.override.yml. Both are merged over x-gates, and a `.:/work` entry replaces `.:/work:ro`. The gates container can then write the checkout and .git/hooks.
- Repro (security-l5-probes.txt, p4-config C4/C5): `docker compose ... config gates` with COMPOSE_FILE="docker-compose.yml;rw-overlay.yml" gives /work with read_only null. With COMPOSE_FILE unset and a docker-compose.override.yml containing `services.gates.volumes: [.:/work]`, the result is the same. C6: with .env present, the COMPOSE_FILE that verify sets keeps the override out. The two fast branches therefore select different file sets.
- Why medium and not high: this is not a path from inside the gate, since the gate cannot write an override file. It is a host configuration that silently undoes PS-3.5. The behaviour existed before this change, but L-5 now depends on it. The architect plan for this item also adds an auto-loaded compose override (bundle install), which lands in exactly this path.
- Fix: in fast mode always `export COMPOSE_FILE="docker-compose.yml${gates_mask:+:$gates_mask}" COMPOSE_PATH_SEPARATOR=":"`. Add a unit test (fake docker) asserting that a caller COMPOSE_FILE is replaced, and that an override file in the repo root is not loaded, in both modes, with and without .env.

### L-1 (low): gid 0 makes group-writable root-owned image paths writable by the gate user
- Where: docker/gates.Dockerfile:69-70 (`chown -R 10001:0`, `USER 10001`) and docker-compose.yml:44 (`user: "10001"`, so the primary group is 0).
- Effect: uid 10001 runs as gid=0(root). The PowerShell tarball installs group-writable files and directories (drwxrwxr-x root:root /opt/microsoft/powershell/Modules, the runtime DLLs, 47 directories). Those, and /usr/share/man/man*, are writable inside a run. The container layer is discarded, so nothing survives. Within one run, code running in the tests could tamper with pwsh or PSScriptAnalyzer. Today lint runs before the tests in the same container, so it cannot change the lint result.
- Fix: run as 10001:10001 (`user: "10001:10001"`, `chown -R 10001:10001`), or `chmod -R g-w /opt/microsoft/powershell` at build time.

### L-2 (low): no no-new-privileges and no cap_drop
- Where: docker-compose.yml:37-51 (x-gates).
- Observed (probe p1): NoNewPrivs 0, CapBnd is the Docker default a80425fb, and setuid su, mount, umount, passwd, chsh, chfn, newgrp and gpasswd are present. No escalation was shown: root is locked, and even root lacks CAP_SYS_ADMIN, so /work cannot be remounted read-write.
- Fix (defence in depth): `security_opt: ["no-new-privileges:true"]` and `cap_drop: [ALL]` on x-gates.

### L-3 (low): only .env is masked; gitignored .env.* siblings stay readable
- Where: docker-compose.gates-mask.yml:12,17. .gitignore ignores `.env.*` (except .env.example), so files like .env.local or .env.prod can exist untracked in the root and are readable in both gate services. .git/config is also readable and can hold a credential in a remote URL. This is info only, because git needs .git.
- PS-3.5 names only the repo-root .env, so this meets the criterion. Either document the limit, or fail verify (or mask) when any .env.* other than .env.example exists in the root.

### L-4 (low): the mask decision is a time-of-check snapshot
- Where: scripts/verify.sh:31. In full mode the check runs before build.sh and launch.sh, which take minutes. A .env created in the meantime, for example by a parallel scripts/launch.sh without KE_ENV_FILE, which copies .env.example, is not masked for gates-it. test_gates_it_cannot_read_repo_env would then fail, which is the fail-safe outcome, but only if the integration suite gets that far.
- Fix (optional): decide the mask immediately before the gates-it run.

### L-5 (low, test adequacy): the runtime mask path passes vacuously without a .env
- Where: tests/integration/test_gate_least_privilege.py:62-67 returns early when /work/.env is absent. That is the case in CI and in the developer run. The fast unit test only checks that the overlay name appears in the logged compose invocation.
- Covered by this audit at runtime: probe p1 (a .env holding REALSECRET with the mask gives 0 bytes, read-only) and p2 P1b (the same .env with no mask is readable, so the probe can detect a leak). Keep the planned orchestrator pre-commit run with a throwaway .env and record it as evidence.

## Focus questions, answered
- **Write the checkout, .git or hooks?** No. EROFS at runtime for /work/x, /work/.git/hooks/pre-commit, /work/.git/config, /work/.git/objects/x, /work/docker/x and /work/.env (Docker Desktop 9p mount, ro). The only exception is M-1, through host configuration. No named volume is attached to either gate service.
- **Read a real .env?** Not with the mask: fast (C2) and full (C1, docker-compose.yml:docker-compose.verify.yml:docker-compose.gates-mask.yml) both resolve /work/.env to docker/empty, read-only. Edge cases:
  - **.env is a directory:** `-e` is true and the mask mount fails with "not a directory", so the container never starts (fails closed).
  - **.env is a symlink:** untested here. This Windows host has no symlink privilege, and a Linux-volume probe was refused by the safety check of the agent tool. Analysis: runc resolves the mount target inside the container rootfs, so the mask lands on the resolved path. A target outside the checkout is never mounted, so there is nothing to read. A dangling link has `-e` false, so no mask is added and there is still nothing to read. A missing target inside the read-only /work fails closed (the same "make mountpoint: read-only file system" error was seen in P3).
  - **Path with spaces:** fine (all probes ran from "repo copy").
  - **Windows separator:** whenever verify sets COMPOSE_FILE it also exports COMPOSE_PATH_SEPARATOR=":", and C3 shows a caller value of ";" is overridden. The file names are relative, so there are no drive-letter colons.
  - **Inherited COMPOSE_FILE:** see M-1.
- **Does tmpfs exec reopen anything?** No. /tmp is rw,nosuid,nodev and per-container. The venv is already writable and executable, so noexec would add nothing, and nothing written there survives the run.
- **Can uid 10001 tamper with /opt/venv in a way later runs see?** No. A marker in /opt/venv and a file in /opt/venv/bin were both absent in the next container (P4). Each run is a fresh container from an immutable image, and the uid cannot write the build context (/work is read-only).
- **Does safe.directory stay /work only?** Yes. The only entry is `file:/etc/gitconfig /work`. HOME is /, and writing //.gitconfig is denied, so no global config can widen it.
- **Any new caller-env leakage into verify.sh?** None beyond M-1. The full-mode KE_* scrub is unchanged. The new gate environment variables are constants (MYPY_CACHE_DIR, PYTHONDONTWRITEBYTECODE, GIT_OPTIONAL_LOCKS), and the gates-it environment adds no new interpolated keys (C1).
- **Secrets:** the diff was grepped for AWS, GitHub, OpenAI and Slack tokens, private keys, credentialed URLs and password/secret/token assignments. The only hit is the test fixture `KE_STORES__POSTGRES__PASSWORD=secret`, written to a temporary .env in tests/test_stack_scripts.py (test_gates_mask_overlay_only_when_env_exists). It is not a credential.

## Note
ke-gates:latest changed ID during this audit (3bde9d9062d9 to 5f472bca1ccc, created 10:59Z). A concurrent run did this (container ke-review-l5-gates-run-*), not this audit, which never built or tagged an image.
