# platform-sbom U7c review (reviewer, 2026-10-25)

Scope: `git diff HEAD` (6d8fa4d = U7b) of scripts/sources_resolve.py, scripts/sbom_check.py,
scripts/sources_lock.sh, tests/fake_docker.py, tests/test_sources_lock.py and
tests/test_sources_resolve.py. Checked against design-notes "U7c precision"
(l.1565-1804) and "U7c gap rulings" (l.1806-1892).

Verdict: **CHANGES REQUESTED** (B1).

Evidence:
- `u7c/reviewer-controls.txt`: `u7c_controls.py --base repo` re-run in the gates image
  (ke-reviewer-u7c): 79 rows, 75 must-fail, 4 must-pass, 0 unexpected (reproduced).
- `u7c/reviewer-probes.txt`, from `u7c/reviewer-probes/probe_u7c.py`, which uses the
  tests' DebFixture and ApkFixture.

## Blocking

**B1. Rule change (i) also loosens where the APKBUILD may come from** (sbom_check.py
`_binding_problems` apk branch, l.1280-1293).
- Gap ruling (i) lets a GitLab path carry plain subdirectory segments before the name.
  The code applies it to every file, the APKBUILD included.
- `_kind_problems` checks the APKBUILD's count, alg and `from`, but not its path.
- Input: the U7c test ApkFixture entry for `apk:readline@8.2.13-r1`, with the APKBUILD
  url changed to `https://gitlab.alpinelinux.org/alpine/aports/-/raw/<commit>/main/readline/tests/APKBUILD`.
  `lock_problems` gives no apk problem.
- A3 fixes the APKBUILD at `.../<repo>/<origin>/APKBUILD`, and ruling (ii) says "The
  APKBUILD is still required, exactly once". So a committed lock could name a
  subdirectory's recipe as the package's, and verify would stay green. U8 would then
  ship the wrong build recipe as the corresponding source.
- The resolver never produces this (it requires the top-level blob), so only a
  hand-edited or tampered lock reaches it. lock-check is the gate for exactly those.
- Fix: in the apk binding, the file named `APKBUILD` must have exactly the path
  `/alpine/aports/-/raw/<commit>/<repo>/<origin>/APKBUILD`. Add a bad-shape row in
  U7cApkLockRulesTest and a control row.

## Nits (non-blocking)
- **N1. `parse_dsc` keeps the last value of a duplicated field.** deb822 forbids
  duplicates. Probes:
  - two `Version:` fields, first `9.9-9` then `5.2.15-2`, give `5.2.15-2`;
  - a duplicated `Checksums-Sha256:` keeps only the second block.

  The `.dsc` is bound to snapshot by SHA-1, so a real one will not have duplicates. A
  duplicate should still fail (`<dsc>: field <name> appears twice`), cheaply and
  fail-closed.

  Also checked:
  - CRLF in an armoured `.dsc` parses correctly.
  - An armour after a leading blank line still parses; the armour-header lines are not
    taken as fields.
  - A lower-case field name fails closed (`no Checksums-Sha256`).
- **N2. `parse_apkbuild` takes the first `^pkgver=`, `^pkgrel=` and `^sha512sums=`.**
  A later reassignment (`pkgver=9.0`) or a second top-level `sha512sums=` block is
  ignored and the APKBUILD accepted. abuild sources the file, so the last assignment
  wins. As defence in depth (ruling 5), refuse more than one top-level assignment of
  each.
- **N3, carry to U8: apk completeness.** As with deb (round-1 item 4), the lock cannot
  show that every `sha512sums` name has an entry. U8 should check the fetched APKBUILD's
  `sha512sums` names against the entry's sha512 files, by name, size and hash.
- **N4.** A tree listing that holds only `tree` entries (no blobs) counts as "not here".
  That is consistent with ruling 2 (non-empty means blobs). Noted.

## Conformant
- **deb (D1-D7).**
  - srcfiles: the map is name -> sha1 across every archive; two different SHA-1s for
    one name fail; any other shape fails.
  - The `.dsc` name drops the epoch. Only the `.dsc` is streamed (SHA-1 and SHA-256,
    1 MiB cap), its SHA-1 checked against the map, and it must decode as UTF-8.
  - `parse_dsc`: drops the armour header up to the first blank line and everything
    from the signature, and undoes dash-escapes.
  - Source and Version must equal the key; Checksums-Sha256 and Files are required
    (ruling-4 text).
  - Each line is three fields (64 or 32 hex). Both lists must give the same multiset of
    name and size, with unique names. If Checksums-Sha1 is present it must match the
    map.
  - Every name must be safe and in the map, with at least one file.
  - Entries use `/file/<map sha1>`, the sha256 and size from the `.dsc`, and
    `<dsc> Checksums-Sha256`. orig and debian files are not streamed.
  - `SNAPSHOT_PAUSE` is 1.0 s, monotonic.
  - pgdg is skipped as `no pgdg route until Q71`.
- **apk (A1-A5, gap rulings 1-3).**
  - lock-needs reads the top-layer `lib/apk/db/installed` (16 MiB) and
    `etc/alpine-release` (1 MiB), each fail-closed on overflow.
  - Each package needs a stanza with matching `P:`, `V:` and `o:` and a 40-hex `c:`.
    There must be one commit, and the branch from alpine-release must equal the purl
    `distro`.
  - The route is validated before any request (ruling-4 text).
  - The tree listing is recursive with `per_page=100`; `x-next-page` fails; a 404 or
    `200 []` means "not here"; "in both" and "in neither" fail.
  - Tree types: `tree` entries are skipped; a blob must be mode 100644 or 100755;
    symlinks and submodules fail; every segment must be safe; two blobs with one
    basename fail.
  - The top-level APKBUILD is checked against the files API `content_sha256`.
  - `pkgver` and `pkgrel` must be literals; `sha512sums` is a quoted literal block of
    `<128 hex> <name>` lines with unique, safe names.
  - Each file is fetched once: summed tree files raw by sha512, summed others from
    distfiles by sha512, and non-summed tree files by the files API `content_sha256`.
  - The entry carries commit, branch and repo.
- **Rule change (ii).** sha256 is allowed only when the url is on gitlab and `from`
  equals `gitlab files API content_sha256 at <commit>`; the commit is bound through the
  path rule. A distfiles file must be sha512. The APKBUILD `from` is pinned to the new
  text. This is a rule change, not a loosening (B1 is the exception, for (i)).
- **Carried rows.**
  - C1: the pypi JSON url goes through the hop rules (`supplied=True`) before any
    request.
  - C2: the real opener uses `read1`.
  - The `six` literal equals `bundled_names()` (fast test); `--tar` is passed for every
    image.
- **Coverage.** `U7cCoverageTest` resolves all 152 deb and 19 apk fixture keys through
  synthetic routes. None is skipped, and every entry passes `lock_problems`.
- **Tests.**
  - deb: 19 failure rows with exact texts.
  - apk: 22 failure rows, route-shape rows with no request, and unsafe-name rows that
    never build a URL.
  - The CLI and the script `--tar`.
  - U7cApkLockRulesTest pins both rule changes.
- **PS-1.2.** No host URL literal added (f-strings over constants).
- **Observability.** A maintainer tool; no spans needed.
