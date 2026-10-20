# DR38 recorded red runs: offline check (PS-3.2, PS-3.3), 2026-10-20

Tester. Architecture §2.6 "Gates with recorded red runs (DR38)". Each run used its own
scratch copy of the working tree (f7e9074 + the uncommitted offline-check
changes, `.git` copied, `.env`/`.venv`/`dist` left out) with exactly one
deliberate defect (none in the control), and ran the real check from the copy:

    cd <copy> && env -u MSYS_NO_PATHCONV COMPOSE_PROJECT_NAME=ke-dr38-<n> \
      KE_IMAGE_TAG=wt-33a132fbfdd7 PATH=<scratch>/bin:$PATH bash scripts/offline_check.sh

- `KE_IMAGE_TAG=wt-33a132fbfdd7` is the repo checkout's verify tag
  (`scripts/image_tag.sh`), so the bundle holds the images built from this
  tree. No image was built for these runs.
- jq is jq-1.7.1 `jq-windows-amd64.exe`, sha256
  `7451fbbf37feffb9bf262bd97c54f0da558c63f0748e64152dd87b0a07b6d6ab`.
  `sha256sum -c` against the upstream release `sha256sum.txt` gave OK. It sits in
  the scratch dir only, and the host was not modified.
- The project name: `offline_check.sh` always names its own project
  `ke-offline-<random>` (§2.5), so `COMPOSE_PROJECT_NAME=ke-dr38-<n>` is
  overridden by design. Each transcript names the real project. The tail of each
  transcript shows that project has no containers, networks or volumes left
  (compose label filter, which also covers the dind anonymous store) and that
  `dist/` in the copy is empty.

| Run | Defect (copy only) | Expected failure | Observed line | rc | Expectation |
|---|---|---|---|---|---|
| 1 | `docker-compose.yml`: `api` gets `networks: [backend, edge]` | ci/offline fails and names api, because api gets out | `smoke: FAIL (ci/offline: api printed 'connected' for 172.19.0.2:8100, want no_route; it can leave the backend network)` then `offline_check: FAIL (the offline client failed (see its output above))` | 1 | met |
| 2 | `scripts/smoke.sh`: the control probe targets port `1` (closed) instead of `$probe_port` | fails as *inconclusive*, never a pass | `smoke: FAIL (ci/offline inconclusive: the control probe from knowledge-engine_edge to 172.19.0.2:8100 printed 'refused', want connected)` then `offline_check: FAIL (...)` | 1 | met |
| 3 | `scripts/offline_check.sh`: after `bundle.sh`, `rm -f "$bundle_rel/images/valkey.tar"` | install refuses on the manifest before any load | `install: manifest: listed file is missing: images/valkey.tar` then `offline_check: FAIL (...)`; no `loaded ...` line (install.sh loads only after the manifest step) | 1 | met |
| control | none (unmodified copy) | PASS | `smoke: PASS`, `offline-client: image names equal the bundle's; nothing was pulled`, `== offline_check: PASS (93s) ==` | 0 | met |

Transcripts: `dr38-run1.txt`, `dr38-run2.txt`, `dr38-run3.txt`,
`dr38-run0.txt` (control). Profile paths are redacted to `<scratch>`/`<profile>`.

Notes:
- Run 2: the message prints `:8100` because it interpolates `$probe_port`. The
  defect changed only the probe's port argument. The word `refused` is the probe
  of port 1.
- Run 1 stops at api, because the loop exits on the first service. worker is not
  probed in that run.
- Not in this set: the §2.6 `ci/deployable-offline` mutant that removes the tar
  from both the manifest and `bundle.json`, so that it must fail at launch. The
  orchestrator asked for the after-bundling removal (install refuses on the
  manifest) instead.
- Cleanup: the tags `ke-app:bundle-f7e9074f7462`,
  `ke-gateway:bundle-f7e9074f7462` and `ke-vendor/{neo4j,phoenix,postgres,valkey}:<12hex>`
  were untagged afterwards. They already existed before these runs (L-OCa), and
  the runs re-tagged them. Each image keeps its own reference (`wt-` tag or
  vendor digest), so `docker image rm` only untagged them. Other images were not
  touched.
