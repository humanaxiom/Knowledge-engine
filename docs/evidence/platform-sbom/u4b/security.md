# platform-sbom U4b: security audit (PSC-26, Q67, N16)

Date: 2026-10-23. Auditor: security. Diff: `git diff 40e2181` plus the untracked
`docker/neo4j.Dockerfile`, `tests/neo4j_support.py`, `tests/test_neo4j_image.py`
and `u4b/`. Probes: `u4b/security-probes.txt` (own containers only, label
`ke.security.u4b=1`, `--rm`, `--network none`). Image audited:
`ke-neo4j:wt-33a132fbfdd7` (ID 4797a370530a, the GREEN `verify full` build; the
same ID as `ke-neo4j:bundle-40e21819680d`).

## Verdict: PASS

No critical, high or medium finding. U4 M-3 is closed. One low and five
informational notes, all non-blocking.

| ID | Severity | Finding |
|---|---|---|
| L-1 | low | The smoke step's `find -xdev` does not look into volumes (`/data`) |
| I-1 | info | `sbom_check.py tree` compares no size or content; NOTICE's "No other file is changed" rests on probe C |
| I-2 | info | The Dockerfile exact-line rule also exempts that literal text on a continuation or heredoc line |
| I-3 | info | NOTICE says "one layer"; the manifest lists two (the second is WORKDIR's empty layer) |
| I-4 | info | ke-neo4j's config has `ArgsEscaped: true` (not compared; no effect on Linux) |
| I-5 | info | Without `products/`, a `NEO4J_PLUGINS` request takes the entrypoint's download path |

## 1. M-3 closed
- Saved tar (`docker save`, probe B): 2 layers. `7274e8ee...` has 8019 entries and none matches
  `products|fleet|genai|.wh.`. `4f4fb700...` is the standard empty layer (0 entries). No config,
  manifest or index blob names products or fleet. The official tar, by contrast, holds
  `var/lib/neo4j/products/` and both jars in layer `86c7147e...` (probe B2).
- Merged filesystem (probe C; whiteouts applied): only the official image has
  `var/lib/neo4j/products`, `neo4j-fleet-management-plugin-1.2.0-v5.jar` and
  `neo4j-genai-plugin-5.26.32.jar`. Running the smoke's `find` in each image prints only
  `LICENSE.txt` in ke-neo4j, and products/ plus the jar in the official one (probe D).
- Bundle: the GREEN run loads 6 tars. Three are first-party (`ke-app`, `ke-gateway`, `ke-neo4j`)
  and three are vendor (`phoenix`, `postgres`, `valkey`, as `ke-vendor/*`). There is no
  `ke-vendor/neo4j` and no official `neo4j`. The official ref is now only in the Dockerfile's FROM,
  NOTICE and tests; no compose file references it. bundle.sh classifies `ke-neo4j:<tag>` as
  first-party: no digest, and it matches `^ke-`. (`ke-vendor/neo4j:0a6e7aedf54a`, 6 days old, is
  still in the local image store from earlier runs. It is not in the bundle.)
- `sbom_check.py neo4j` scans every layer named in manifest.json. A whiteout, opaque or named,
  cannot hide the jar: the lower layer that holds it is scanned and flagged on its own.
  `.wh.products` is flagged as defence in depth. It only reads member names and never extracts.

## 2. Flattened image vs official (probes C, D, E)
- Content, not just attributes: for all 8019 common paths, type, mode, uid, gid, size, link
  target and the content's sha256 are identical. Neither image has xattrs (no file capabilities
  are lost).
- setuid/setgid: the same 12 entries in both (chage, chfn, chsh, expiry, gpasswd, mount, newgrp,
  passwd, su, umount, unix_chkpwd, /var/mail). Nothing is added or widened.
- World-writable: the official set minus products/ and its 2 jars, and no addition (C2). The
  777 on `NEO4J_HOME`, `/data` and `/logs` is upstream's own `chmod -R 777`, unchanged.
- Ownership: `/data`, `/logs` and `/var/lib/neo4j` are 777 neo4j:neo4j (7474) in both; `/` is
  755 root:root, `/tmp` 1777. The official tar's `.` entry (755 0:0) has no ke-neo4j
  counterpart, but the daemon's `/` matches.
- USER is unset in both (`User=""`). Through the real entrypoint, the command runs as
  uid=7474(neo4j) with CapEff 0 in both (probe E). Same tini and entrypoint (sha256 equal).
- Config: Entrypoint, Cmd, Env, WorkingDir, ExposedPorts and Volumes are equal. The only
  differences are compose labels and `ArgsEscaped` (I-4). Nothing is lost or widened.
- The server exits 3 under `--network none` in both images (probe F): that is parity, not a
  regression. The GREEN smoke shows ke-neo4j healthy on `backend`.

## 3. PS-1.2 scanner change
- The match is narrow. The form is chosen by `_is_dockerfile(path)`, but an exemption still
  needs `path == p`, which is exactly `docker/neo4j.Dockerfile`. The symbol goes through
  `re.escape` and is anchored `^\s*...\s*$`, so `EXPOSE 7687`, `... 8080`, `.../tcp`,
  `RUN echo EXPOSE ...` and `ENV`/`HEALTHCHECK` lines with 7687 are all still flagged. Other
  Dockerfiles, `docker/neo4j/Dockerfile`, compose and scripts are not exempt. Python exemptions
  keep the assignment form (N4); a bare symbol line is not exempt. The control test
  `test_dockerfile_exemption_covers_only_its_instruction_line` pins all of this.
- I-2: Python `splitlines()` does not know about Dockerfile backslash continuations or heredocs.
  A continuation or heredoc line whose whole text is `EXPOSE 7473 7474 7687` would also be
  exempt. That is the same literal in the same file and cannot hide any other value, so it is
  not actionable.
- The EXEMPTIONS entry gives a reason and its provenance (PSC-26, N16; orchestrator ruling 1),
  and it matches the official ExposedPorts.

## 4. Smoke "no fleet plugin"
- It is injection-safe. The `find` arguments are fixed literals with nothing interpolated, and
  the output is only compared with `[ = ]` and echoed to stderr, never evaluated. The test
  `test_smoke_never_evaluates_the_neo4j_output` covers command substitution, backticks and `;`.
- It fails closed. `set -euo pipefail`; a non-zero `find` exit fails, even when the output looks
  clean. Empty output fails (the LICENSE.txt control is missing). Any extra line fails. The
  failure cases are tested: products/ empty, only genai, the jar in plugins/, fleet elsewhere,
  no control, exit 1.
- L-1: `-xdev` stops at mounts, so a fleet jar in the `neo4j-data` volume (`/data`) or in a
  future bind mount would not be seen. The step proves the image, which is its job; the tar check
  covers what ships. Fix: drop `-xdev` and prune `/proc` and `/sys`, or name the mount points.
  Non-blocking.

## 5. offline_check.sh pull and `sbom_check.py neo4j`
- The pull is by full digest, parsed from the Dockerfile's `FROM ... AS runtime` and checked
  against `^neo4j:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$`. There is one call, no retry, and it
  fails closed. It is the same image the build already fetches by digest, so there is no new
  trust root or host. The CLAUDE.md sentence still holds: the host half "builds and pulls
  images". The gate services' networking is unchanged.
- The checker runs with `--network none --read-only --cap-drop ALL`, no-new-privileges,
  `--pull never`, the caller's uid:gid, `python -I`, and read-only mounts. The work dir comes
  from `mktemp -d` and the EXIT trap cleans it up. `neo4j_ref` starts with `ke-neo4j:`, so it
  cannot start with `-`, and every expansion is quoted.
- The config fields compared exclude only Labels (ruling 5), so an injected USER, Healthcheck,
  OnBuild or Shell would fail the check.

## 6. NOTICE "Base image of `ke-neo4j`"
- Accurate. It gives the pinned base and version, the removed directory and why (a commercial
  licence with Neo4j, Inc.; GenAI unused), and that the rest of the filesystem is unchanged
  (probe C, content sha256). Neo4j Community is unmodified, under GPL-3.0; `LICENSE.txt` names
  Neo4j Sweden AB and GPL v3 (checked in the image), and `licenses/GPL-3.0.txt` exists. Source:
  upstream tag 5.26.32. The section claims nothing untrue. The old vendor row ("used unmodified")
  is gone, and bundle.sh's row parser only reads `|` lines, so the section adds no vendor row.
- I-3: "flattened into one layer" holds for the filesystem, but the manifest has a second, empty
  layer from WORKDIR. Optional wording change: "one filesystem layer".

## 7. Evidence sweep (`u4b/`)
- No keys, tokens, private keys, JWTs, credential URLs, passwords, profile paths, SIDs or
  model-host address in the diff, the new files or `u4b/*` (the regex sweep was run over all of
  them).
- The only IP is `192.168.160.2`, the stack's internal gateway address in the smoke's
  no-route lines.
- `u4b_controls.py` only runs `git show` and unit harnesses in a temp checkout. It makes no
  network calls and does not write the repo.

## Other notes
- I-1: the `tree` subcommand (evidence only, ruling 3) compares type, mode, owner and link but
  not size or content. NOTICE's "No other file is changed" is now backed by probe C. On a digest
  bump, add size and sha256 to `tree_listing` or re-run probe C. Not blocking.
- I-4: `ArgsEscaped` is a Windows-only flag; Linux ignores it.
- I-5: `neo4j-plugins.json` points genai, fleet-management, bloom and GDS at `products/`. When
  that is missing, a `NEO4J_PLUGINS` request goes to `load_plugin_from_url`: bloom and GDS have
  download URLs; genai and fleet-management have none. Nothing in compose, scripts, engine or
  config sets `NEO4J_PLUGINS`, and neo4j sits on `backend`, which has no egress. So the plugin
  cannot come back by default.
