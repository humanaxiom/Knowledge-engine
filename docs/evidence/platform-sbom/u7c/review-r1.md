# platform-sbom U7c rework round 1 review (reviewer, 2026-10-25)

Scope: the U7c GREEN targets against the working tree for scripts/sbom_check.py and
scripts/sources_resolve.py (byte-identical to `u7c/r1-target-*`). Tests: ReworkR1U7c*,
plus the fixture moves (good_entry, ApkFixture.raw). Rulings: design-notes
"U7c rework round 1" l.1894-1984 and item 9, l.1986-2105.

Verdict: **APPROVED.** No blocking findings.

Evidence:
- `u7c/reviewer-r1-controls.txt`: `r1_controls.py --base repo` re-run in the gates image
  (ke-reviewer-u7c): 34 rows, 29 must-fail, 5 must-pass, 0 unexpected.
- `u7c/reviewer-r1-probes.txt`, from `u7c/reviewer-probes/probe_u7c_r1.py`.
- `u7c/r1-green-verify-fast.txt`: 1047 tests, OK.

## Closed
- **B1.** An APKBUILD whose decoded path is not exactly `<repo>/<origin>/APKBUILD` is
  refused ("the APKBUILD is not at <repo>/<origin>/APKBUILD"). On the resolver side the
  APKBUILD is the top-level blob, or the run fails with `<origin>: no APKBUILD at
  <repo>/<origin> at <commit>`.
- **N1.** `parse_dsc` refuses a field named twice, compared case-insensitively
  (`<dsc>: duplicate field <name>`).
- **Security L-2.** CRLF is folded to LF first and the text split on LF only. Every
  character in C0 except TAB and LF, plus DEL, C1, U+2028, U+2029 and a lone CR, fails,
  naming the field (or `-` in the armour or before the first field).
- **N2.** A second top-level `pkgver=`, `pkgrel=` or `sha512sums=` fails; indented ones
  are not counted.
- **L-3.** A page of 100 or more entries fails unless `x-next-page` is present and empty.
- **I-1.** The tree `path=` value is percent-encoded.
- **Item 9, as a rule change.**
  - Every GitLab apk url must be exactly
    `.../projects/alpine%2Faports/repository/files/<P>/raw?ref=<C>`:
    - the query is exactly `ref=` with the entry commit (40 lower-case hex);
    - `<P>` is one segment, canonical by `quote(unquote(P), safe="") == P`;
    - the decoded path has no `%`, no backslash and nothing outside 0x21-0x7e;
    - it reads `<repo>/<origin>/.../<name>`, with no empty, `.` or `..` segment, and is
      exactly three segments for the APKBUILD.
  - The query and `%` are exempt only for kind apk when this exact shape matches. Other
    kinds, other GitLab forms and distfiles keep the U7a rules, and `/-/raw/` is refused.
  - Probes: the old form, another commit and a literal backslash in `<P>` are all
    refused.
  - The resolver builds exactly this form; the metadata call has no `/raw`.
- **The two challenge rows.**
  - A 307 to a plain path, then 418, gives `gitlab.alpinelinux.org: HTTP 418: <url>`.
  - A 307 that keeps the `%2F` API path is refused by the hop rules
    (`refused: not a plain path`).
  - Both give one FAIL line and write no lock.new.json. That refines the item 9 text
    "surfaces as 418" for the same-path case; the test documents it.

## Nits (non-blocking)
- **R1-N1. The decoded middle segments of `<P>` accept any printable character.**
  Item 9 (b) asks only that segments be non-empty and not `.` or `..`. These pass
  `lock_problems` as the `fix-build.patch` url of the fixture entry:
  - decoded `main/readline/..;/fix-build.patch`;
  - decoded `main/readline/a?b/fix-build.patch`;
  - decoded `main/readline/x&ref=0/fix-build.patch`;
  - decoded `main/readline/~@:/fix-build.patch`;
  - decoded `main/readline/-/fix-build.patch`.

  The canonical encoding makes these harmless on the wire: `?`, `&` and `;` stay
  `%3F`, `%26` and `%3B` inside one API parameter, so no query injection and no `/`
  traversal. But the superseded rule (i) and the `_tree_blobs` check in the resolver
  both held every segment to the lock name rule
  (`[A-Za-z0-9][A-Za-z0-9._+~-]{0,254}`, no `..`). Holding the decoded segments to the
  same rule would make the lock side as strict as what the resolver can produce. One
  line and one row; an architect call.
- **R1-N2. `parse_dsc` silently ends a field at a junk line.** A line that is not
  blank, not a continuation and not `Name: value` sets `current = None`, so the
  continuation lines after it are dropped. Probe: a line `junk-without-colon` inserted
  after the first Checksums-Sha256 line keeps 1 of 2 lines. If both Checksums-Sha256
  and Files carried such a line, the multiset compare would agree and the lock would
  miss files. The U8 completeness check (N3) reuses this parser, so it would agree too.
  The `.dsc` is SHA-1-bound to snapshot, and dpkg-source rejects such a file, so this
  is defence in depth: refuse a non-field line in the paragraph (`<dsc>: line is not a
  field`).

## Checked
- `seen` spans the whole `.dsc` body, so a repeated field in a second paragraph also
  fails (stricter than one paragraph; a `.dsc` has one).
- `str.strip()` treats U+2028 and similar as blank, but the blank branch checks the
  refused set first, so they fail.
- Fixture moves: `good_entry` and `ApkFixture.raw` now build the API form. The U7c
  coverage of 152 deb and 19 apk keys still passes `lock_problems` (verify OK).
- PS-1.2: the item 9 shape is compared by parts (`_apk_api_shape`), with no URL
  literal.
- Observability: a maintainer tool; no spans needed.
