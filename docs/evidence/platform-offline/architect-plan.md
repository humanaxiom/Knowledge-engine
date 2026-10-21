## 2026-10-19 — architect: platform-offline plan (bundle, install, ci/offline, ci/deployable-offline, carry-ins)

- **Asked:**
  - Check §2.5 and ADR-KE-012 against what was built.
  - Design bundle, install, `ci/offline`, `ci/deployable-offline` and the
    `verify.sh full` stages.
  - Design the carry-ins: L-5, L-8, the ke-app scan, psycopg notices and N6.
  - Estimate the time cost and name the first failing tests.
  - Touch only `docs/architecture.md`.
- **Did (`docs/architecture.md`):**
  - §2.1: networks; services (`gates-it` profile, `probe` dropped, `dind`,
    `offline-client`, `scan-db`/`scan`); profiles; new "Image tags" (N6);
    `probe` removed from the diagram; `offline` isolated.
  - §2.2:
    - the sequence diagram, plus three new stages;
    - `smoke.sh --live` drift;
    - container health drift;
    - new "Unprivileged gates, read-only checkout" (L-5, `.env` mask);
    - Lint: PSScriptAnalyzer by hash (L-8/N-7), the Docker CLI in the gates
      image, gates layer order (N8).
  - §2.3 and ADR-KE-010: `config/verify.env` was never created.
  - §2.5 rewritten: the as-built check, bundle, install, `ci/offline`,
    `ci/deployable-offline`, notices, time cost, spikes S1–S4, rulings
    R1–R7.
  - §2.6: platform-offline tests rewritten in TDD order.
  - ADR-KE-009 amended: step 2/4 drift, DinD consequence corrected, L-5, N6.
  - ADR-KE-012 rewritten.
  - New ADR-KE-013 (image scan).

### Drift found (as built at 4b19971 vs the docs), all fixed in text
- §2.5 put `ke-gates` and `dind` in the bundle, while §2.2 said "the bundle
  carries no gates image": a contradiction. Resolved: stack images only.
- `smoke.sh --live` does not exist. Smoke is two-sided on `KE_IN_GATES`, and
  the gates image sets `KE_IN_GATES=1`, so `offline-client` must empty it.
- ADR-KE-009 step 2 still named a `config/verify.env` overlay (it was never
  created), and step 4 listed no stages after smoke.
- §2.1 put `gates` and `gates-it` under one `gates` profile; as built,
  `gates-it` has its own. `probe` was listed on `backend` and in the diagram
  but never built.
- First-party images are bare names (`ke-app` = `:latest`): N6 is real.
- `.dockerignore` has no `dist/`, so a bundle under the checkout would enter
  every build context.
- The gates image copies code before `uv sync` (N8 is fixed in
  `app.Dockerfile` only).
- The ADR-KE-009 DinD consequence "no third-party Python runs there" is
  untrue once the stack runs inside `dind`.
- Digests checked (by reading compose and the Dockerfiles; none was
  changed):
  - postgres, neo4j, valkey and phoenix are pinned by digest in compose;
  - the python, uv and nginx bases are pinned by digest in the Dockerfiles;
  - pwsh is pinned by sha256;
  - PSScriptAnalyzer is pinned by version only (L-8).

### Decisions (details in §2.5, ADR-KE-012/013)
1. **Bundle.**
   - `scripts/bundle.sh --out <dir> [--tar]`, bash only (R1). It never
     builds or pulls.
   - Inputs and checks: the stack images from `compose config --images`
     (no profile), a strict reference pattern, `linux/amd64`, and a
     containerd store (R2).
   - Output:
     - `docker save --platform linux/amd64` per image; first-party images
       are saved as `ke-<x>:bundle-<sha12>`;
     - `app/`: the unchanged compose file, `.env.example`, `config/`,
       launch/teardown/smoke `.sh`, launch/teardown `.ps1`,
       `net_isolated.sh` and the quickstart;
     - the installers, `NOTICE.md`, `licenses/` and the generated
       `THIRD_PARTY_NOTICES.md`;
     - a line-oriented `bundle.json` (`file`, `ref`, `as`);
     - `MANIFEST.sha256`, whose hash is printed.
2. **Install** (`install.sh <target>`, `install.ps1 -Target`):
   1. The manifest first, with no docker call before it passes:
      - the line grammar;
      - safe paths;
      - the exact file set;
      - non-regular entries refused;
      - the hashes.
   2. A containerd store.
   3. An empty target.
   4. Load.
   5. Resolve each reference, then retag `as` (the bundle becomes `:local`).
   6. Copy `app/`.
3. **`ci/offline`** (host half of smoke, so in verify, live, and inside
   `dind`):
   - The target is the gateway's `edge` IPv4 address and its API listen
     port.
   - Control: a `docker run --rm` of the api image on `<project>_edge` must
     print `connected`, or the gate fails as *inconclusive*.
   - Assertion: `exec` in api and in worker must print `no_route`.
   - New `engine/netprobe.py`: one connect, one word. It is not an agent
     step, so it opens no span.
   - The target needs no internet, which is A46.
4. **`ci/deployable-offline`** (`scripts/offline_check.sh`, two-sided on
   `KE_OFFLINE_CLIENT`):
   - project `ke-offline-<n>`;
   - `dind`: pinned, Engine ≥ 28, containerd store, privileged, on
     `offline` (internal and isolated), anonymous `/var/lib/docker`, TLS
     certificates on a volume;
   - `offline-client`: `ke-gates`, no checkout mount, bundle read-only,
     tmpfs `/install`;
   - client steps: empty store, a pull must fail, install, launch,
     `KE_SMOKE_OWNS_PROJECT=1` smoke, teardown, image count = bundle;
   - `teardown.sh` accepts exactly `--profile offline`.
5. **`verify.sh full` stages:** build, launch, `gates-it`, smoke,
   `teardown.sh --volumes`, `scan.sh`, `offline_check.sh`. All are script
   calls, so F5 holds; `test_verify_sh_has_no_inlined_commands` gains
   forbidden words.
6. **L-5:**
   - the `x-gates` anchor runs as uid 10001 with the checkout `read_only`;
   - tmpfs `/tmp` with `COVERAGE_FILE`, `MYPY_CACHE_DIR` and `UV_CACHE_DIR`
     there, plus `PYTHONDONTWRITEBYTECODE` and `GIT_OPTIONAL_LOCKS=0`;
   - `.env` masked by an overlay binding `docker/empty`, added only when
     `.env` exists;
   - `test.sh` erases coverage data under `COVERAGE_FILE`.
7. **L-8/N-7:** the PSScriptAnalyzer `.nupkg` is fetched with curl, checked
   with `sha256sum -c` and unzipped; no `Install-Module`. The telemetry ENV
   comes before the first pwsh call. Authenticode was rejected because it
   is Windows-only.
8. **Scan (ADR-KE-013):**
   - the tool is grype, digest pinned, provenance checked by security;
   - `scan-db` (default bridge, database volume only) fetches each run, then
     `scan` (`network_mode: none`) reads the `ke-app` tar;
   - it fails on High or Critical findings that have a fix;
   - ignores need a `reason` and an `until` date.
9. **Notices:** `engine.notices` is run at bundle time inside `ke-app`
   (network none). It lists every distribution with its licence, and fails
   if an LGPL/GPL distribution has no licence file. The committed
   `NOTICE.md` holds the psycopg statement with the source URL from
   `uv.lock` and the vendor-image licence table, both drift-tested.
10. **N6:** the images are `ke-*:${KE_IMAGE_TAG:-local}`. verify exports
    `wt-<sha256(checkout path)[:12]>` per worktree, so `:local` belongs to
    the operator or `install` only.

### Time cost (estimate, §2.5 table)
- Added to `full`: about 4.5–8.5 min.
  - CI: 389 s today → about 10.5–14.5 min, which exceeds the current
    10-min timeout (R5 / A44: raise to 20 first).
  - Local: 146 s → about 5–9 min, under F5's ~15 min.
- Disk: about 6–9 GB at once (R6). Memory stays at today's peak, because
  the verify stack is torn down before `dind` starts.

### Spikes before RED (developer, evidence only)
- **S1:** do digest references survive save and load into `dind`? Check
  from the CI runner and from Docker Desktop, and record the store type.
- **S2:** run the gates as uid 10001 with a read-only checkout; list the
  failing writes.
- **S3:** inside `dind`, can uid 10001 read the client key, and is the
  inner `isolated` option honoured?
- **S4:** CI disk after the build, and the time of `docker save`.

### First failing tests (order; full list §2.6)
1. `test_bundle_manifest_rejects_tamper`: sh and ps1, fake docker, and
   the docker log must be empty on every reject.
2. Install target and daemon refusals; retagging.
3. `test_bundle_lists_every_compose_image`.
4. Bundle contents.
5. Compose offline services.
6. L-5 static test.
7. L-8 static test.
8. N6 tag.
9. The B6 verify stage order.
10. `NetprobeTest` and the smoke `ci/offline` cases.
11. `OfflineCheckScriptTest`.
12. Scan.
13. Notices.
14. Integration: `test_gates_cannot_write_the_checkout`.
15. DR38 red runs of each gate.

### Needs a ruling (R1–R7, §2.5)
- **R1:** no `bundle.ps1` (PS-3.1 names a twin).
- **R2:** the containerd image store is required on the build host and on
  the targets. If the CI runner is classic, choose a fallback.
- **R3:** scan scope (`ke-app` only) and a fresh database every run.
- **R4:** vendor-image redistribution: Neo4j GPL-3.0 source offer and
  Phoenix's licence (to the human).
- **R5:** CI timeout to 20 min before the first offline run (= A44).
- **R6:** runner disk.
- **R7:** conflicts with the analyst draft:
  - "Verification images included": the design drops them;
  - PS-3.5 scope: the design covers both gates;
  - PS-3.8's integration test maps to the bundle-time generator.
  The analyst's supply-chain split fits unchanged.

### Next
- The orchestrator rules on R1–R7, and the analyst reconciles PS-3.1 and
  PS-3.5 with R1 and R7.
- The developer runs spikes S1–S4.
- The tester starts RED with `test_bundle_manifest_rejects_tamper`.
