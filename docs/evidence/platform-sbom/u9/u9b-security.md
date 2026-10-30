# U9b security audit (security, 2026-10-29)

Scope: the uncommitted U9b diff on `agent/platform-sbom` (HEAD 1a7a9e2), from `git diff HEAD`:
`scripts/bundle.sh`, `scripts/offline_check.sh`, `NOTICE.md`, `README.md`,
`tests/test_offline_bundle.py`, `tests/test_offline_check.py`, `tests/test_sbom_bundle.py`,
`tests/test_sbom_obligations.py`, plus the untracked `tests/test_bundle_sources.py` and the
intent-to-add `licenses/libffi-jna-5.15.0.txt`. Read: handoff U9a/R7/RED/GREEN sections,
`u9a-security.md` (carried items), `libffi-provenance.md`, `expected.md`, `sample-bundle-run.txt`,
the tail of `u9b-green-verify-full.txt`. Probes: `u9b-security-probes.txt` (ke-gates image,
`--network none`; no symlink, FIFO or device made on the host).

## Verdict: FAIL

One blocking finding (L-4). Everything else holds or is informational. The fix is a few lines
in `scripts/bundle.sh` plus test rows; nothing in `scripts/sbom_check.py` needs to change.

## Blocking

### L-4 (high: irreversible deletion; likelihood low; no privilege boundary crossed)

Where: `scripts/bundle.sh` l.88-92 (out made absolute, never normalised), l.123-138 (`--out` and record checks),
l.157-170 (overlap), l.433 (`created`), l.441 (`rm -rf -- "$out"`), l.461 (first `mkdir -p`), l.651-652 (record).

Attack or failure: a `--out` of the form `<missing>/../<name>-<arch>` passes every `--out` check, and the new O-10
cleanup then removes a directory this run did not create. Every test on `--out` (`-L`, `-e`, "not empty", the
record's `-e`, and `created` at l.433) is made on the raw string. The kernel fails any path whose `..` follows a
missing component, so all of them see "absent". `mkdir -p` at l.461 then creates the missing component and writes
into the real, pre-existing target. Probed:

- (a) After any failure following the first write, including Ctrl-C, `rm -rf -- "$out"` (l.441) deletes the
  pre-existing, non-empty directory and everything in it (P2, verbatim l.122-138 and l.433-455). The real script
  passes every pre-write check with such an `--out` (P7: it reaches `docker compose config`; the plain-path control
  is refused "--out is not empty").
- (b) The overlap check is bypassed. `--out <missing>/../<sources>/x-amd64` passes (P1b; real script P9), so the
  bundle is written under `--sources`, against U9-1. If `--sources` lies inside such an adopted `--out` (P1c), a
  failure deletes the fetched set.
- (c) Pre-existing, but now joined to (a): on success, the adopted directory's old files go into the bundle and its
  manifest, and an existing release record at the resolved name is overwritten (`>` at l.652, no noclobber),
  against M-3.

Victims are limited to directories named `*-amd64` or `*-arm64` (an earlier bundle, for example).

Fix:
1. Right after l.85 and l.91, refuse any `.`, `..` or empty segment in `--sources` and `--out`, for example
   `case "$out/" in */./*|*/../*|*//*) usage ;; esac`, and strip every trailing slash
   (`while [[ $x == */ ]]; do x=${x%/}; done`). This also closes I-8 and I-9.
2. Claim `--out` atomically. When `created=1`, run `mkdir -p -- "$(dirname -- "$out")"`, then `mkdir -- "$out"`
   with no `-p`, and set `wrote=1` only after that succeeds. A directory that appears after the l.433 test then
   fails the run instead of being adopted and later deleted. This closes I-10.
3. Write the record with noclobber, `( set -C; printf ... > "$record" )`, and set `record_made=1` only after it
   succeeds.
4. Add rows to `tests/test_bundle_sources.py`:
   - `--out <missing>/../<existing non-empty>-amd64` is refused before any docker write, and that directory is
     unchanged.
   - `--out <missing>/../<sources>/x-amd64` is refused.
   - `--sources <dir>//` and `--sources //` are refused or normalised.

## Informational (non-blocking)

- **I-7** (`scripts/bundle.sh` l.575-578). A `--sources` entry can be swapped between `sources-check` and the copy.
  If it becomes a FIFO, `cp -P` blocks forever (P4: timeout 124). If it becomes a character device, the copy has
  no bound (P4: /dev/zero, 3.98 GB in 2 s) until the disk fills, and then the cleanup runs. This is denial of
  service only. A link is copied as a link and refused at l.618, a directory is refused by `cp` (exit 1), and a
  hard link or changed bytes fail name == hash at l.631. The swap needs write access to `--sources` during the run.
  Optional fix: test `[[ -f $src && ! -L $src ]]` just before each `cp`, and bound the bytes read (for example
  `head -c` at the lock size + 1).
- **I-8** (l.86, l.165-170). `--sources //` becomes `/`, so `sources_real` is `/` and the pattern
  `"$sources_real/"*` becomes `//*`, which never matches. Bash's `pwd -P` also keeps `//` (P1d, P1e). The overlap
  compare therefore cannot see `--out` under `/`. It fails closed only because `/fetch.json` must exist (P10) and
  the container's exact-listing check refuses `/`. Closed by L-4 fix 1.
- **I-9** (l.86, l.144). Only one trailing slash is stripped, so `--sources <link>//` passes the "is a symlink"
  refusal (P13; `<link>` and `<link>/` are refused). Integrity is unaffected: the overlap compare resolves links,
  and name == hash binds the shipped bytes to the lock. This is the shell form of U9a I-1. Closed by L-4 fix 1.
- **I-10** (l.433, l.461). Race: `mkdir -p` adopts a directory that another process creates between the `-e` test
  and the first write. The cleanup then deletes that process's files (P3c). It needs a concurrent same-user
  writer. Closed by L-4 fix 2.
- **I-11** (l.155-170). The overlap check compares paths, not device and inode. A bind mount or a second mount can
  alias `--sources` under `--out` where `cd -P` cannot see it. The bundle only ever creates new names, and
  `sources-check` runs before the first write. Optional fix: compare `stat -c %d:%i` of `--sources` with each
  existing ancestor of `--out`, and the reverse.
- **I-12** (`README.md` l.79-81; `scripts/sbom_check.py` `SECTION_SAMPLE`). A sample-set bundle is marked only in
  its notices (`SECTION_SAMPLE`: "do not distribute") and in `index.json`. `bundle.json` and `install` do not flag
  it. The README wording is correct and does not invite distribution. Optional fix: record `sources_set` in
  `bundle.json` and have `install` print the notice when it is `sample`.

## Checked and holding

- **The sha list from the check (l.414-418).** Each line must match `^[0-9a-f]{64}$` (P5, verbatim). A CR, a `..`
  second line, empty output, a trailing blank line, a leading space and an uppercase digit are all refused.
  Duplicate lines pass this check but fail the count rule (l.637), because the copy makes one file per name. Only
  validated names reach `cp` (l.576). No value from the list reaches `docker run`, `find` or `rm`.
- **The window between check and copy (U9a I-4).** `cp -P` runs with no `-p` and no reflink (l.576). A link is
  copied as a link and refused at l.618 (P4), a directory makes `cp` fail, and a hard link becomes a new inode
  (P4: links=1). Bytes changed after the check fail name == hash (l.631); `test_a_source_file_changed_after_the_check_is_refused`
  pins this. The count rule (l.637) makes the listed set equal the shipped set. The shipped bytes stay bound to
  the lock whatever happens to `--sources` after the check.
- **Nothing writes under `--sources` given a plain path.** Every mount is `:ro`. On the host, `--sources` is only
  read (`ls`, `[ -f ]`, and as the `cp` source). The `..` case is L-4.
- **Overlap.** The equal, inside and containing cases are refused for plain paths, `.` segments and symlinked
  ancestors (P1a, P1f, P1g; real-script controls in P7). The gaps are L-4, I-8 and I-11.
- **Cleanup scope with links.** If `--out` is swapped for a symlink after the first write, `rm -rf -- "$out"`
  removes only the link, and `find -- "$out" -mindepth 1` does not follow it (P3: the target's files survive). A
  symlinked `--out` is refused at l.123 before anything runs. The record is removed only if this run wrote it.
- **Injection.** `--sources-set` takes only `full` or `sample` (a `case`). `--sources` and `--out` always start
  with `/`, and every use is quoted and after `--`. A `:` in the `docker -v` source makes the CLI refuse the spec
  ("too many colons", P12), so it fails closed. The checker's arguments are fixed paths, the daemon-mapped arch,
  the case-checked set and the regex-checked `git_sha`, so the operator's argv never reaches argparse. U9a I-2 is
  therefore unreachable from `bundle.sh`. The manifest path pattern is unchanged, and `app/sources/files/*` must
  also be 64 hex characters.
- **Container hardening.** The three `check_run` invocations (`sources-check`, `index`, `notices`; l.399-408) carry
  exactly the flags of the existing `finish` run (l.558-559): `--rm --network none --read-only --cap-drop ALL
  --security-opt no-new-privileges --pull never --user <caller uid:gid>`, the `-sbomcheck` label, and
  `--entrypoint python ... -I`. Every mount is `:ro`, the lock and the policy included. Output leaves only through
  stdout, which the host redirects. The unhardened `engine.notices` run (l.385) predates U9b and is out of scope.
- **Manifest cap.** The 1 MiB refusal (l.642) comes before the `mv` and the record. The cap is not raised.
- **offline_check.sh.** `dist/<project>-sources` and `dist/<project>-<arch>` are disjoint siblings. It passes
  only `--sources-set sample` (l.268), and its EXIT trap removes both directories (l.170).
- **No new URL or host literal in `scripts/`.** No line `git diff HEAD -- scripts/` adds contains `http(s)://` or
  a domain. The only new URL is the R7 source, in `NOTICE.md` and in the licence file's header.
- **Secrets.** I grepped the diff, the new test file and the licence file for key and credential patterns: AWS,
  GitHub, Slack and OpenAI-style keys, private-key blocks, DB URLs with credentials, `password=`, `api_key=` and
  bearer tokens. Nothing matched. The U9b evidence files hold no profile path, SID, signed query string,
  `KE_MODEL_UPSTREAM` or `KE_EGRESS_ALLOWLIST` value, or private host. They contain only loopback and
  docker-bridge addresses, public build-time URLs and repo-relative `dist/` paths.
- **No gate or test weakened.** The test edits only:
  - add `--sources` and a synthetic lock and policy to the bundle runs;
  - call `_relock_for` on three custom-SBOM runs;
  - use `mkdir(exist_ok=True)`;
  - extend the `app/` list (U9-6, U9-8).

  The `finish`-run count now counts `finish` runs only, and `tests/test_bundle_sources.py` pins the three new
  runs. No assertion was removed, and `scripts/verify.sh` and CI are unchanged.

## libffi licence file (`licenses/libffi-jna-5.15.0.txt`): matches R7

- 1368 B, LF only. `.gitattributes` has `licenses/* -text`, so git converts no line endings.
- The header (3 lines, then a blank line) is exactly the form in section 5 of `libffi-provenance.md`.
- The body after the first blank line is **1132 B, sha256
  `2c9c2acb9743e6b007b91350475308aee44691d96aa20eacef8e199988c8c388`**, equal to the R7 record. Its first line
  keeps the double space ("1996-2022  Anthony Green").
- The header's claims match R7 sections 1-3: libffi 3.4.4, vendored by JNA 5.15.0, path `native/libffi/LICENSE`,
  the jna-tag raw URL and the source sha256.
- The `NOTICE.md` paragraph is R7 section 5's recommended text, verbatim.
- The index blob is the `git add -N` placeholder (e69de29, empty), as expected for intent-to-add.

## Carried items (from `u9a-security.md`)

| Item | Status | Basis |
|---|---|---|
| U9a I-1 (`--dir <link>/`, `index --files <link>` followed) | closed by U9b (checker side) | In `bundle.sh` the checker's `--dir`, `--files` and `--index` are fixed mount points (`/sources`, `/files`, `/idx`). On the host, `<link>` and `<link>/` are refused (P13). The `<link>//` shell variant is new I-9. |
| U9a I-2 (argparse echoes raw argv) | out of scope (checker unchanged); unreachable through `bundle.sh` | Every argument `bundle.sh` passes is fixed or validated. |
| U9a I-4 (the check-to-copy window) | closed by U9b | `cp -P` (l.576), non-regular refusal (l.618), name == hash (l.631) and the count rule (l.637); `test_a_source_file_changed_after_the_check_is_refused`; P4. The remaining denial of service is I-7. |
| U9a I-5 (`notices` reads past the cap if the file grows) | open (info, unchanged) | `sbom_check.py` is not in the diff. In U9b the index is this run's own output, written before `notices` runs and mounted `:ro`; growing it needs a concurrent same-user writer into `--out`. |
| U9a I-6 (the URL column relies on the lock host check) | open (info, unchanged); out of scope for U9b | U9b passes the committed lock and policy `:ro`. `lock_entry_problems` and `notices` are unchanged. |

## For the developer (rework)

Fix L-4 with steps 1-4 above. Step 1 also closes I-8 and I-9, and step 2 closes I-10. I-7, I-11 and I-12 are
optional. Run `scripts/verify.sh full` again, because the diff touches `scripts/`. The security re-audit covers
only the `--out`/`--sources` normalisation, the claim of `--out`, and the record write.

Note: reviewer B-1 (handoff, same day) reports the same unnormalised-path root cause from the overlap side. One normalisation rule (step 1) and the atomic claim (step 2) close both.
