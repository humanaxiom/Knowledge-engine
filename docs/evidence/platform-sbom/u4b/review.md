# platform-sbom U4b review (PSC-26, Q67): reviewer, 2026-10-23

Verdict: **APPROVED** (0 blocking, 7 nits).

Scope read: `git diff 40e2181` (21 files) plus untracked `docker/neo4j.Dockerfile`,
`tests/neo4j_support.py`, `tests/test_neo4j_image.py`, `docs/evidence/platform-sbom/u4b/`.
Against: PSC-26 as amended (requirements.md l.4017-4175), design notes N16,
ADR-KE-016 point 12, orchestrator U4b rulings 1-6 (archive/platform-sbom-part7.md).
Read-only: no image built.

## Checked and accepted

- `docker/neo4j.Dockerfile` is byte-identical to `u4b/target-neo4j.Dockerfile` and matches N16
  exactly. FROM is the full PSC-26 digest `AS runtime`; there is one `RUN rm -rf /var/lib/neo4j/products`;
  then `FROM scratch` + `COPY --from=runtime / /` with no `--chown`. ENV has 7 entries in the official order
  with the same values, checked against `u4b/official-config.txt`. WORKDIR, VOLUME, EXPOSE, ENTRYPOINT and CMD
  are in exec form. It sets no USER, HEALTHCHECK, LABEL, STOPSIGNAL, SHELL or ONBUILD. The extra comment lines
  only explain the design.
- Compose `neo4j`: `image: ke-neo4j:${KE_IMAGE_TAG:-local}` plus `build {context: ., dockerfile}`. The service name,
  env, volumes, networks, healthcheck and api `depends_on` are unchanged (pinned by `NEO4J_SERVICE_KEPT`).
  The official ref is gone from compose, and `official_ref_problems` scans every build input.
- `build.sh`/`build.ps1`: only the header changed (N16: no logic change). `bundle.sh`, `install.sh`/`.ps1` and
  `scan.sh` are unchanged (ruling 6, Q68). The full run shows `loaded ke-neo4j.tar as ke-neo4j:bundle-40e21819680d`.
- NOTICE: the neo4j vendor row is removed. The "Base image of `ke-neo4j`" section has the FROM ref byte for byte,
  the removal of products/, "Neo4j Community itself is unmodified", GPL-3.0, the LICENSE.txt path,
  `licenses/GPL-3.0.txt`, and the https upstream at tag 5.26.32. It does not say "used unmodified".
- `source-policy.json`: the 5 neo4j `always` entries are renamed to `ke-neo4j` with their matches unchanged.
- Smoke "no fleet plugin": a single `find / -xdev ( -path products -o -name *fleet-management* -o -path
  LICENSE.txt ) -print`. A non-zero exit fails. Output must equal exactly the control path (whole-output string
  compare, never evaluated), so an empty answer, an extra line or a partial walk all fail closed. The fake-docker
  controls (command substitution, backticks, a semicolon command) prove nothing is evaluated.
- `offline_check.sh`: pulls the neo4j base once, by the Dockerfile FROM digest, validated by regex, before
  `bundle.sh`, with no retry. After drift, the ke-neo4j step runs `sbom_check.py neo4j` in the ke-app image with
  `--network none --read-only --cap-drop ALL no-new-privileges --pull never`, as the caller uid and with ro
  mounts. The work dir is cleaned by the EXIT trap (via `drift_work`). The full run shows
  `sbom_check: ke-neo4j: ok` and `offline: ke-neo4j check:`.
- `sbom_check.py neo4j`: compares 11 config fields, with absent, null and empty treated as one value, and Labels
  excluded (ruling 5). It walks every layer in `manifest.json` (gzip and OCI/legacy), catches products/, the
  `.wh.products` whiteout, an opaque whiteout inside products/ and the jar by name anywhere, and fails on a
  listed-but-missing layer or on zero layers checked. The SBOM is checked by purl (unquoted, any version and
  qualifiers) or by name, and Neo4j Community and Temurin must be present. I/O errors exit 1.
- `sbom_check.py tree`: only in evidence (ruling 3), unit-tested on stub exports.
- PS-1.2 scanner: the Dockerfile form is an exact-line regex (`^\s*<symbol>\s*$`) used only when the path ends in
  `Dockerfile`, and the path is still compared exactly. The Python form is unchanged (N4). `EXEMPTIONS` gains one
  entry with its reason. Controls cover: another EXPOSE shape, an extra port, `/tcp`, ENV/comment/HEALTHCHECK/RUN
  lines, another Dockerfile path, and a bare Python symbol. **Re-ran `u4b_controls.py --base repo` in the gates
  image (ke-gates:wt-33a132fbfdd7, project ke-reviewer-u4b, network none): 61 rows, 45 must-fail,
  16 must-pass, 0 unexpected** (`u4b/review-controls-repo.txt`).
- The 11 re-targeted tests keep their intent and none is weakened:
  - The NOTICE tests (`test_notices_neo4j_has_source_url`, `test_notice_wording_...`) now read the section and
    still require GPL-3.0, an https source and no compliance claim. They also assert there is no official row.
  - The `neo4j` -> `ke-neo4j` renames are in `test_bundle_refuses_on_sbom_failure`, the unlicensed and H-1/L-3
    bundle tests, `PSC22_COMPONENTS`, `R1_ENTRIES` and `r1_required`.
  - In `real_always_problems`, the U3 neo4j fixture stands in for ke-neo4j, with a documented reason.
  - The first-party sets in `test_stack_compose`/`test_offline_check` and the required Dockerfiles gain neo4j.
  - The offline event order gains `pull neo4j base` and `neo4j`.
  - `_base_pulls` excludes only the exact `OFFICIAL_REF`, so a pull by tag is still refused.
- New tests (`tests/test_neo4j_image.py`, 23) run positive and negative controls in every check. Unit and
  fake-docker coverage is good.
- Evidence:
  - RED: 29 unique FAIL/ERROR names, all U4b.
  - Reach: verify fast exit 0.
  - GREEN fast: 871 OK, mypy clean.
  - GREEN full: 871 + 15 tests (8 + 5 skips, all named: Windows ACLs and the model host), smoke step printed,
    offline PASS 198 s, `verify full: PASS (990s)`.
  - File tree: 8028 vs 8025 entries, only products/ and its 2 jars differ, 0 attribute diffs.
  - I cross-checked the unlicensed list against the U4 orchestrator run (`u4/orchestrator-verify-full.txt`):
    28 -> 27, and the only row removed is `pkg:maven/com.neo4j/neo4j-fleet-management-plugin@1.2.0`.
- requirements.md status table: "PSC-26 PENDING U4b" and "U4b next" are accurate before commit.
- Observability: no agent loop, model call, retrieval or tool call is added, so no span is required.

## Findings

Blocking: none.

- **N1 (docs, README).** The README "status" edits are accurate for U0-U4 but do not cover U4b. The offline-check
  paragraph (~l.202-207) lists the outbound pulls as the generator and the ke-app base; it now also pulls the
  official neo4j base by digest and runs the ke-neo4j check. The repo map (~l.319) says `docker/` holds "the gates,
  app and gateway images" and should add neo4j. Documenter, before the U4b commit or at the next status pass.
- **N2 (docs, CHANGELOG).** The in-progress entry stops at U4. U4b is user-visible: neo4j now runs our own
  `ke-neo4j` image without the commercial fleet-management plugin, and NOTICE changes. Marketer.
- **N3 (NOTICE wording).** "...the fleet-management plugin, which is under a commercial licence with Neo4j, Inc.,
  and the GenAI plugin, which the stack does not use." This can read as if the stack uses the fleet plugin, and it
  leaves out the GPL-3.0 licence of the GenAI plugin, which PSC-26 *Notices* names. Suggest "...neither of which
  the stack uses", plus "(GPL-3.0)" after GenAI. Analyst owns the wording; the test needs no change.
- **N4 (evidence, N16 *SBOM*).** N16 asks GREEN evidence to diff the ke-neo4j package list against the U4 neo4j
  SBOM ("the plugin rows go, and nothing else changes"). Only the unlicensed count was recorded. My cross-check
  above covers the unlicensed subset only. Record the full package-list diff, for example in the A34 proof.
- **N5 (evidence, file tree).** `file-tree-evidence.txt` is a summary. PSC-26 says both listings are recorded. Save
  the two `tar -tv` listings, or their sha256 and the diff command, so the result can be re-checked.
- **N6 (`sbom_check.py tree`).** It compares type, mode, uid, gid and the symlink target, but not size. PSC-26
  *Evidence* and N16 list size, and the developer compared it separately. The hard-link normalisation is also
  one-way: an official file becoming a ke-neo4j hardlink, from a different export order, would fail. Add size, or
  narrow the PSC-26 wording, when U5+ next touches the file. It is evidence-only, so not blocking.
- **N7 (scanner edge, `tests/hardcoded_scan.py`).** The Dockerfile exact-line form matches a physical line. The
  same text on a continuation line of another instruction (a `RUN echo` line ending in a backslash, then
  `EXPOSE 7473 7474 7687` on the next line), or inside a heredoc, would also be exempt. This only applies to
  `docker/neo4j.Dockerfile`, where the static Dockerfile tests already forbid any other RUN. Optional: also
  require the previous line not to end in a backslash. Forwarded to security for its PS-1.2 review.
- Cosmetic: `offline_check.sh` reuses `drift_work` so the EXIT trap removes the ke-neo4j work dir. A one-line
  comment would make that reuse clear.
