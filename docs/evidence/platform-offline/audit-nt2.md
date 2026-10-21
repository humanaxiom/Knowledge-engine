# audit-nt2: review + security confirmation of notices round 2 and the offline-check chmod

Verdict: **PASS / APPROVED**. No critical, high or medium finding is new in this round. One low (test gaps) and a few info notes, all non-blocking. M-NT1 (medium, prior round): the Valkey part is now closed, and the remainder is deferred to platform-supply-chain as the handoff records.

Scope: HEAD bed6eca plus staged `LICENSE` and `licenses/BSD-3-Clause-valkey.txt`, unstaged `NOTICE.md`, `engine/notices.py`, `scripts/bundle.sh`, `scripts/offline_check.sh`, `docs/quickstart.md`, `tests/test_{engine_notices,offline_bundle,offline_check}.py`, and the 8 new evidence files.
I read the newest handoff sections, `red-nt2-verify-fast.txt` (677 tests, 27 failures, all new tests), `red-perm-verify-fast.txt` (679 tests, 22 failures, the 2 new perm tests), `red-perm-mutants.txt` and `orchestrator-perm-verify-full.txt` (679 tests OK, skipped=8; offline_check PASS 90 s; verify full PASS 494 s). I also read `ci-39364201188.log`, whose lines 2888-2892 show "Permission denied" on `/bundle/images/*.tar`.
Raw output is in `audit-nt2-probes.txt`. Every ad-hoc `docker run` used `--rm --network none --pull never --label com.docker.compose.project=ke-sec-nt2-*`, and none is left. HEAD, the index and tracked files were not touched.

## Confirmations
1. **L-NT2 (path containment): closed.**
   - The audit-nt P7 cases were re-run against a verbatim copy of the new `notices.py` in the `ke-app:local` Python (3.12.15), plus 19 new cases.
   - Every one of these is now rejected:
     - RECORD `..` entries, whether they lead back into site-packages or out of it (`d1` `licenses/../../../outside`, `rec_dotdot_inside`, `rec_dotdot_far`)
     - absolute RECORD entries and absolute License-File values
     - `../planted` and `licenses/../../planted`
     - a file symlink out of site-packages (absolute or relative, via RECORD, License-File or a `COPYING` name), and a `licenses/` directory symlink out of it
     - a dangling symlink and a symlink loop (no exception)
     - a dist-info directory that is itself a symlink out of site-packages
   - These still count, as intended: plain files, an in-site symlink, and site-packages reached through a symlink.
   - The new docstring is accurate.
   - Mutants:
     - Old M6 (header `..` filter off) is now **killed** by 4 tests.
     - Also killed: m6r and m6rr (RECORD filter off), m6s (containment check off), m6z (no `resolve`), and m6both.
2. **L-NT3 (strict vendor-row parse): closed.**
   - All 41 crafted NOTICE.md files (the 21 from audit-nt plus 20 new) were run through bundle.sh lines 193-250 verbatim.
   - Refused: 0x1F in the Image, Reference or Licence cell (cases 07, 08, 18), DEL, ESC, an inner CR, a tab inside the licence, a pipe in a cell (06), an NBSP licence (17), `see LICENSE` and other prose, `MIT OR`, `AND MIT`, lowercase `or`, and `Unknown`.
   - Accepted: CRLF files, `BSD-3-Clause AND MIT`, `... WITH Classpath-exception-2.0` and `LicenseRef-*`.
   - A malformed row elsewhere in NOTICE.md that carries `@sha256:` also refuses (37).
   - **No shell execution:** cases 05 and 34 created no `/tmp/pwned*`.
   - A missing or empty LICENSE refuses before any write.
   - mawk (gates) and busybox awk give identical output on all 40 cases with a NOTICE.md. gawk was not available locally, so it is untested.
   - Mutants killed: n1 (control-byte check off), n2 (`NF<7`), n3 (no SPDX check), n7 (LICENSE not copied), M2c (by the new placeholder subtests).
   - Survivors: see L-NT6.
3. **L-NT5 (tracked licence files only): closed.** n8 (`ls-files -co`) and n9 (`find`, equivalent to the old `cp -R`) are both killed. `cp -P` plus bundle.sh's existing "neither a file nor a directory" refusal means a tracked symlink fails closed.
4. **The Valkey text matches upstream exactly.** I fetched `https://raw.githubusercontent.com/valkey-io/valkey/8.1.10/COPYING` myself with curl, `--proto =https --tlsv1.2`:
   - sha256 `1a53dca3aab7ce048e91e77b03c0342f3075366f9dede8ec4d19d0cf229e12a0`, 3091 B.
   - `cmp` shows it identical to the working-tree file and to the index blob.
   - Tag 8.1.10 is commit 55a54267.
   - It is also identical to the copy I fetched in audit-nt.
   - `licenses/* -text` applies.
5. **LICENSE is the standard MIT text, verbatim.** It is byte-identical to choosealicense's `mit.txt` with `[year]=2026` and `[fullname]=Humanaxiom`. It is word-identical to SPDX `MIT.txt`, with only the copyright line differing. It has LF line endings, and the working tree equals the index (sha256 `03971a45...b703`).
6. **The chmod is correct and safe.**
   - It names exactly `"$bundle_rel"` (`dist/ke-offline-<random>-<arch>`). It runs after bundle.sh and before `df_log "after bundle"`, so before dind and the client start. It uses `--`.
   - In GNU coreutils 9.1 (gates, uid 10001), `a+rX` gave files 0600→0644, executables 0700→0755 and directories 0700→0755. No write bit was added.
   - `dist/`, a sibling directory, the `.manifest.sha256` record and the targets of embedded symlinks are unchanged: chmod -R does not follow symlinks it meets during traversal. bundle.sh also refuses a symlinked or non-empty `--out` and any non-regular entry.
   - Mutants: the tester's six (dist, a+rwX, plus the hash file, in the trap, after the run) were recorded as caught. My c1 (no chmod: 22 failures), c2 (`$bundle_rel/images` only: 29) and c3 (`a+r` with no X: 12) are all killed.
   - **Opening the throwaway bundle is acceptable.**
     - Others get read access only.
     - It lasts only until the EXIT trap's `rm -rf` (about 90 s locally).
     - The bundle holds the public vendor images, `ke-app` and `ke-gateway` built with `.env*` excluded by `.dockerignore`, tracked `app/` files and `.env.example` only. It holds no secret.
     - Integrity is unaffected: there is no write bit, and the client verifies the manifest.
     - The operator path (`bundle.sh` output) stays private.
     - Residual risk (info): `COPY config` takes the working-tree `config/`, so an untracked local file there would be readable for that window. This predates this change.
7. **NOTICE.md wording is now accurate.**
   - Neo4j reads "Upstream source: ... (tag 5.26.32)", with no compliance claim.
   - Phoenix names all three ELv2 limitations (hosted service, licence-key circumvention, notices) and adds "see the licence text for all limitations".
   - Knowledge Engine is described as "the code in this repository, built into ..." and as MIT, with a pointer to `LICENSE`.
   - The Valkey row and the Licence texts section point to `licenses/BSD-3-Clause-valkey.txt` with the true fetch URL.
   - The psycopg statement is unchanged and accurate.
8. **No secrets.** I grepped 13431 lines (`git diff HEAD` plus the new evidence files). The only hits are test names, compose "variable is not set" warnings, quickstart prose and the GitHub-masked `token: ***`. No profile path or domain SID appears.

## Findings
- **L-NT6 (low; test gaps, surviving mutants; non-blocking).** I probed the behaviour directly and it is correct, but these mutants pass the full 679-test suite with no failure beyond base:
  - n6: the `[ -s LICENSE ]` guard removed. A missing LICENSE then fails late, at `cp`, after `docker save`, leaving tars in `--out` (no manifest or record). An empty LICENSE ships. Fix: add `_assert_nothing_written` to the "missing from the tree: LICENSE" subtest, and add an empty-LICENSE case.
  - n10: the licence-token character class loosened. `BSD;3-Clause`, `MIT,` and `GPL/MIT` would pass. Add one such case.
  - n12: operator positions unchecked. `see the COPYING` and `MIT Apache-2.0 BSD` (odd token counts) would pass. Add one such case.
  - n11: the CR strip removed, so a CRLF NOTICE.md is refused. This matters because quickstart allows WSL as the build host, which can read a Windows CRLF checkout. Add a CRLF control case.
  - n4: the ERR branch removed. It still refuses through "no licence entry", so the outcome is equivalent but the message is less precise. Optionally assert that the refusal says "malformed".
  - n5 (`LC_ALL=C` dropped) is equivalent in the gates image. No test is needed.

## Info
- I-NT5: the in-band `ERR` sentinel collides with a Reference cell that is literally `ERR` (case 33). The message is garbled and contains raw 0x1F bytes, but the run still fails with rc 1. Prefixing every record with a tag would remove this.
- I-NT6: the awk comment says "single-spaced", but `split(s, p, " ")` collapses runs, so `MIT  OR Apache-2.0` is accepted (case 29). Parenthesised SPDX expressions are refused (case 30), which fails closed. NOTICE.md's table guidance (lines 20-21) does not yet say the Licence cell must be an SPDX id or expression.
- I-NT7: `pyproject.toml` declares no `license = "MIT"`. This is for the human or a later item.
- I-NT8: the CI-only permission bug class stays invisible on Docker Desktop. The handoff records the architect's options (`docker cp -a` into a volume, or a Linux daemon context).
- Carried: M-NT1 remainder (GPL-2.0 Alpine and Debian source offers, the ke-app base paragraph for CPython, Debian and `uv`, psycopg-binary's vendored libraries) goes to platform-supply-chain. I-NT1 to I-NT4 are unchanged.
