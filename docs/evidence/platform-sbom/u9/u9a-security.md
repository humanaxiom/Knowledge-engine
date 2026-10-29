# U9a security audit (security, 2026-10-29)

Scope: the uncommitted U9a diff on `agent/platform-sbom` (HEAD 5cf025c):
`scripts/sbom_check.py` (+503: `fetch_record_problems`, `listing_problems`,
`source_index`, `source_section`, the multi-match rule in `exempt_matches`,
the subcommands `sources-check`, `index` and `notices`), `tests/test_offline_bundle.py`
(+86: install pins), new `tests/test_source_index.py` (no new fixture files;
fixtures are built in the tests). The U8c part 2 docs changes are out of scope.
Read: handoff U9 sections, requirements U9-2..U9-7 and U9-11, design-notes
"N9 amendment, U9" items 3, 5, 6, 7, 10 and 13 and the rulings (Q78-Q80,
O-9..O-12), `u9a-red-verify-fast.txt`, `u9a-controls.txt`, `u9a-green-verify-fast.txt`.
Probes: `u9a-security-probes.txt` (gates image, network none; no host symlinks).

## Verdict: PASS

No critical, high or medium finding. Three low and four info findings,
all non-blocking. L-1 is a gap against design item 13 ("no link is
followed"): fix it in U9a rework or carry it to U9b; it is not exploitable
for wrong output.

## Findings

| ID | Severity | Blocking | Finding |
|---|---|---|---|
| L-1 | low | no | `_record_text` lstats `fetch.json` and then opens it with plain `open(path, "rb")`: no `O_NOFOLLOW`, no `O_NONBLOCK`, no `fstat` of the open fd. A swap between lstat and open is followed. Probe P3: a link swapped in after the lstat was read, `problems=[]` from `_record_text`. A FIFO swapped in hangs the run (8 s timeout). `_sha256_of` does use `O_NOFOLLOW` (P3: ELOOP, errno 40). It does not use `O_NONBLOCK` or `fstat` either, so a planned file swapped for a FIFO after the listing also hangs. Impact is low. The writer needs write access to `--sources` during the run. The record is never trusted for bytes, because every field must canonically equal the lock's plan and every file is re-hashed. In `bundle.sh` the directory is a `:ro` mount, so a redirected read can only see the container's own mounts. The result is a hang (DoS), never wrong output. **Fix:** open both with `O_RDONLY\|O_NOFOLLOW\|O_NONBLOCK\|O_BINARY`, `fstat` the fd, and require `S_ISREG` (and for `fetch.json`, size <= 4 MiB) before reading. |
| L-2 | low | no | `source_section` refuses exactly the design's list (`\|`, backtick, `<`, `>`, `\`, non-`[\x21-\x7e]`; P5: every control char, NUL, ESC, CR/LF, tab, U+202E, NBSP, empty and non-string refused). Markdown link, image and emphasis syntax still passes, e.g. `[click](javascript:alert(1))`, `![img](http://evil/x.png)`, `*bold*`, `#heading`. Lock keys and URLs are already constrained by `lock_entry_problems` (per-kind key regex, policy hosts). Exempt `image` and `package` must equal an SBOM image and purl to match at all. So the only free-text printed value is the policy's `reviewed` (and `listing`, which embeds it). P6: `reviewed="security [x](javascript:alert(1))"` gives a printed section. The policy is committed and security-reviewed, so this is low. **Fix (U9b or later):** pin `reviewed` to a fixed shape (e.g. `^[a-z][a-z-]* \d{4}-\d{2}-\d{2}$`) in `_policy_shape_problems`, or add `[ ] ( ) ! * _ #` to the refusal for every field except URL. |
| L-3 | low | no | `notices` reads `--index` with no size cap and no regular-file check. `notices --index /dev/zero` hangs (P7). The input is the run's own `index.json` on a `:ro` mount (operator path), so this is low. **Fix:** the `_record_text` pattern (lstat regular, fstat, a cap such as 16 MiB; the full index is estimated at 0.5-1 MB). |
| I-1 | info | no | `--dir <link>/` (trailing slash) passes the "is a link" refusal, because `lstat` resolves the slash (P2: exit 0). `index --files <link>` is followed (P7). Both are operator paths. In `bundle.sh` they are bind-mount points, so nothing changes in the real path. Entries inside `--dir` are never followed (P2). |
| I-2 | info | no | argparse's "unrecognized arguments" echoes the caller's argv raw, control bytes included (P7: 9 of 150 random-bytes runs). This is the same for every pre-existing subcommand and is the operator's own input. The U9a code's own messages are `_clean`/`repr`. Random-bytes argv: exits {0, 1, 2}, 0 tracebacks. |
| I-3 | info | no | `fetch_record_problems` raises `RecursionError` on a record nested ~5000 deep within the 4 MiB cap: `json.loads` succeeds, then the `lock_text` re-dump recurses. It does not return a problem. The CLI turns this into one FAIL line (P1), so no traceback reaches the operator. The pure function's "problems, never exceptions" contract has a hole. Fix: catch `RecursionError` around the canonical compare. |
| I-4 | info | no | Forward to U9b: between `sources-check` and the copy, a file in `--sources` can change. The design closes this window only with item 8 (`cp -P`, plus manifest name == sha256 of the shipped bytes, plus the link check). U9b must land and test that rule; U9a's check alone does not bind the shipped bytes. |

## Checked and holding

- **sources-check.** Cap before parse: 4 MiB+1 and a sparse 8 GiB file are refused by `lstat` size (0.13 s, no read). Every other check holds, each with one refusal line and no traceback (P1, P2, P4):
  - deep nesting: refused;
  - duplicate key, CRLF and BOM: not canonical, refused;
  - raw NUL: invalid JSON;
  - escaped NUL/ESC: shown as `\x00\x1b`;
  - non-UTF-8: refused;
  - `format` true, 1.0 or NaN: refused;
  - a float or bool `size`: refused (type compare);
  - an extra file key: refused;
  - a 5000-digit int: refused;
  - `fetch.json` as a link, `--dir` as a link: refused;
  - a planned name that is a link (to `/dev/zero`): refused;
  - an unplanned link: refused;
  - an unlistable dir (0300): `cannot list`, refused (never an empty listing);
  - a dir at 0000, or an unreadable file: refused;
  - nothing written under `--dir` (mtime, size and mode snapshot unchanged).
- **index.** `validate` runs first: a duplicate SPDXID on jna is reported as "not unique" before the exempt rule. Multi-match is refused with both SPDXIDs. Policy-shape checks: a list policy, non-list `exempt` and a non-string `reviewed` are each refused. `git_sha` must be 40 lower-case hex: a trailing newline, upper case, `None` and `g` are each refused. Output is byte-identical in-process and across two CLI runs, and stdout is ASCII-only (`ensure_ascii`). Generator text (name, purl, licence, expression) and policy `reason` are in `index.json` but never in the section (P5, P6: hostile `|`, newline and backtick values print a clean section).
- **CLIs.** One FAIL line, never a traceback. `--git-sha` and `--sbom` are echoed through `repr` (ESC and U+202E escaped) with exit 2. Paths shown are only the operator's own.
- **Install pins.** 12 `_tamper_cases` rows run in both `InstallShTest` and `InstallPs1Test`, through `test_bundle_manifest_rejects_tamper` and `test_install_loads_nothing_when_manifest_fails`:
  - targets: `index.json`, `files/<sha>` and the SBOM;
  - tampers: deleted, byte flipped, unlisted beside it, listed symlink (the link points to identical bytes, so only the link rule can refuse it).
  - `u9a-controls.txt`: each of the 8 single-rule mutations (sh, ps1) fails exactly its three rows, and the controls fail none. The rules are live.
- **Secrets and dependencies.** Fixtures and the diff: secret and profile-path scan, 0 hits (`u9a-security-probes.txt` section 1). Only stdlib imports were added (`hashlib`, `os`, `stat`). No new dependency, no network, no host, no tracing change.

## Rework round 1 (security, 2026-10-29): PASS

Scope: O-14 and "O-14 precision" (design-notes, end of the U9 block); the
rework diff in `scripts/sbom_check.py`. I re-ran every first-round probe plus
new swap, device, sparse-file, Markdown and deep-record probes in the gates
image (`u9a-security-probes.txt`, "Rework round 1" section, sections R1-R5).
Evidence read: `u9a-r1-green-verify-fast.txt` (1270 OK, 8 skips).

| ID | Status | Probe result |
|---|---|---|
| L-1 | closed | `_open_regular` opens with `O_RDONLY\|O_NOFOLLOW\|O_NONBLOCK\|O_BINARY` and fstat-requires a regular file. `fetch.json` swapped after its lstat for a FIFO, a link, a link to `/dev/zero`, or a directory: refused (one line, no hang). Swapped for a sparse 8 GiB file: refused on the fstat size (4 MiB cap). A planned file swapped after the listing for a FIFO, link, device link or directory: `cannot read (OSError)` in 0.2-0.3 s. One grown to 8 GiB: `sha256 mismatch`. `_open_regular` directly: `/dev/zero`, `/dev/null`, FIFO, directory refused (EINVAL); link refused (ELOOP); regular file opened. |
| L-2 | closed (as ruled) | `[ ] ( ) ! * _ #` refused in image, exempt package, exempt image, reviewed and listing. The policy `reviewed="security [x](javascript:alert(1))"` is now refused. The key column (code span, backtick refused) and the URL column accept them, per O-14 precision. The item-7 set (`\|`, backtick, `<`, `>`, `\`, control characters) stays refused in every column. Committed lock: 183 keys and 876 URLs, 0 refused. Committed policy: both exempt entries print. |
| L-3 | closed | `notices --index`: `/dev/zero`, a FIFO, a directory and a link are refused (one FAIL line, 0.1 s). A sparse 8 GiB file and a 16 MiB+1 file are refused on the cap. |
| I-3 | closed | `fetch_record_problems` returns `fetch.json: nested too deeply to check` at depths 2000 and 5000; 20000 is invalid JSON; 950 and 990 are not canonical. It never raises. A list policy is a problem. |

Nothing is weaker than the first-round PASS. Every P0-P7 result is unchanged except the four now closed. Random-bytes argv: 150 runs, exits {0, 1, 2}, 0 tracebacks. The only raw control bytes are argparse's own echo of the operator's argv (I-2, unchanged).

New, info, non-blocking:
- **I-5:** `notices` checks the 16 MiB cap on the fstat size and then `json.load`s the whole file. A regular file that grows after the fstat is read past the cap. It is the run's own `index.json` on a `:ro` mount. Optional hardening: `fh.read(INDEX_MAX + 1)` as for `fetch.json`.
- **I-6:** by the ruling, the URL column takes `[ ] ( ) ! * _ #`. Its safety rests on `lock_entry_problems` (policy hosts) upstream of `index`, because `notices` itself does not re-check URL shape. The committed URLs pass.

Still open from the first round: I-1, I-2 (info), and I-4 (U9b item 8; carried by O-14).
