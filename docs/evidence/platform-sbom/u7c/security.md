# platform-sbom U7c: security gate audit (deb and apk routes, lock-rule changes, tar reads)

Date: 2026-10-25. Auditor: security. Tree: HEAD 6d8fa4d (U7b) plus the U7c working tree.
`scripts/sources_resolve.py`, `scripts/sources_lock.sh` and `scripts/sbom_check.py` equal
`u7c/target-*`. Design: design-notes l.1565-1892. Probes: `u7c/security-probes.txt` (script
`u7c/security_probes.py`; gates image, `python -I`; pure functions, synthetic tars, one loopback
HTTP server; no external request). verify.sh not run.

## Verdict: PASS

No critical, high or medium finding. U7b R1-L1 (drip feed) is closed. Three low and four
informational notes, all non-blocking. In each case the trust root (snapshot.debian.org or
GitLab, both sha-checked) would have to serve hostile content, or a hand-edited lock would have
to use the gap.

| ID | Severity | Finding (input) |
|---|---|---|
| U7b R1-L1 | **Closed** | `read1(CHUNK)`: a 1-byte per 50 ms drip now hits the deadline (patched to 2 s) at 2.0 s |
| L-1 | low | **The lock rule accepts the APKBUILD from a subdirectory.** On a good `apk:readline@8.2.13-r1` entry, setting the APKBUILD url to `https://gitlab.alpinelinux.org/alpine/aports/-/raw/<commit>/main/readline/sub/APKBUILD` (or `sub/deeper/APKBUILD`) gives no problem. The resolver itself only takes the top-level APKBUILD, but `lock-check` is the gate for any lock, a hand edit included. Fix: allow the subdirectory form only for names other than `APKBUILD` |
| L-2 | low | **`parse_dsc` is not deb822.** (a) `str.splitlines()` also breaks on U+0085, U+2028, U+2029, VT, FF and 0x1c-0x1e, so a field value can start a new field: `Homepage: a<U+2028>Source: evil` sets `Source` to `evil`, and a NEL can do the same to `Checksums-Sha256`. (b) A repeated field silently replaces the earlier one: a second `Checksums-Sha256`/`Files` pair listing `evil.tar.gz` wins. dpkg rejects both. The `.dsc` is sha1-pinned by snapshot, the listed names must be in its srcfiles, and U8 checks every sha256, so the effect is a lock that disagrees with what dpkg-source would read. Fix: normalise CRLF, split on newline only, refuse any other control or line separator, and refuse duplicate fields |
| L-3 | low | **Truncated GitLab listings are detected by header only.** A recursive listing of exactly 100 entries with no `x-next-page` header is taken as complete, so files past the first page would go unlocked (ruling 3: every regular file is locked). Refuse a full page unless `x-next-page` is present and empty, or use `x-total` |
| I-1 | info | `tree?path=<repo>/<origin>` is not URL-encoded. An origin with a plus sign (allowed by the key grammar, for example `libsigc++`) is read as a space, so the listing is empty and the run fails closed with "in neither". This is correctness, not security |
| I-2 | info | A file named in `sha512sums` but present in the tree can be recorded as a GitLab sha256 file and still pass `lock-check`; the resolver uses sha512 for it. The two checks are equally strong (both come from GitLab at the commit) |
| I-3 | info | Sizes from the `.dsc` are not range-checked in the resolver (`0` and `10**20` pass). `lock-check` rejects both afterwards, which fails closed |
| I-4 | info | Carried from U7b: `tar_file_text` ignores whiteouts and skips hard links, so a lower copy of `lib/apk/db/installed` can win. A stanza must still match P, V, origin and a 40-hex commit |

## 1. `parse_dsc` and `dsc_files` (probe U7c-1)
Holds:
- The armour is stripped and text after the signature is ignored (a trailer cannot add files).
- Dash-escapes are undone. CRLF works.
- Names with a slash, `..` or NUL, and names not in srcfiles, are refused.
- Sizes and hashes must be ASCII digits and lower-case hex (Arabic digits are refused).
- Files and Checksums-Sha256 must agree. Checksums-Sha1 must equal snapshot.
- Source and Version must equal the key. A ` .` continuation line in Files is refused.
- 1 MB of continuation lines parses in 0.026 s.

Gaps: L-2 and I-3.

## 2. The snapshot name-to-sha1 map (probe U7c-2)
- One name with two sha1s is refused; the same name and sha1 in two archives is accepted.
- An upper-case sha1 key, non-list entries, a non-string name, or a list `fileinfo` are refused
  as "not the expected JSON".
- Names are not checked in the map itself (`../x` enters it), but every name used is checked
  later: the `.dsc` name is built from the key, and the other names go through `safe_name`.
- The `.dsc` is fetched alone from `/file/<sha1>` with a 1 MiB cap and its sha1 is checked;
  nothing else is fetched.

## 3. GitLab tree and files API (probe U7c-3)
- Refused: symlinks (120000), submodules (type commit, 160000), an int mode, a missing type,
  paths with `..` or `%2e%2e`, a path outside `<repo>/<origin>/` (also `readline-x/`), a name
  that differs from the path basename, a basename collision across subdirectories, and a
  listing that is not a list.
- Tree entries are skipped, and no URL is built from them.
- Every path segment passes the lock name rule before any URL is built.
- JSON bodies stop at 1 MiB. `content_sha256` must be 64 hex.
- The APKBUILD is fetched raw and matched to `content_sha256`, then read as text and never run.
  pkgver and pkgrel must be literals, and a dollar sign or a backtick in sha512sums is refused.
- Gaps: L-3 and I-1.

## 4. Distfiles and raw files
These go through `stream()`, so the U7b round 1 deadline and 4 GiB cap apply, and sha512 is
checked against sha512sums. The URLs are built from validated parts (a `v<major>.<minor>`
branch, a safe name).

## 5. The two lock-rule changes (probe U7c-4)
- **Subdirectory raw paths:** a file in `sub/` is accepted. A segment with `a..b` or `../bash/`
  is refused (the name rule or the plain-path rule). Open: L-1, the APKBUILD in a subdirectory.
- **sha256-only files:** accepted only on GitLab raw at the commit of the entry, with `from`
  `gitlab files API content_sha256 at <that commit>`. Refused: such a file on distfiles, at
  another commit, with `from` naming another commit, with `from` `uv.lock`. A second APKBUILD
  is refused as listed twice. An APKBUILD whose `from` is not the files API text is refused.

## 6. Tar reads (probe U7c-5)
- The top layer wins. A symlink or hard link at the top is skipped (the lower copy is used).
- A member over its limit (16 MiB for the installed db, 1 MiB otherwise) raises
  `TarMemberTooLarge`, in any layer, which fails closed. Names with a `./` prefix match; names
  with a `../` prefix do not.
- `apk_stanzas` keeps the first value of a repeated letter and handles CRLF. It is linear: 3 MB
  takes 0.13 s.
- Open: I-4.

## 7. Evidence hygiene (`u7c/*`, the changed tests, `fake_docker.py`)
- No keys, tokens (no GitLab `glpat-` or `PRIVATE-TOKEN`), signed query strings, private keys,
  password values, profile paths, SIDs, or model-host name or port.
- The credential-URL hits are synthetic userinfo test cases.
- IPs: 127.0.0.1, the stack gateway address in the smoke no-route lines, the fake-docker
  defaults (172.30.0.2, 172.31.0.99), and a Temurin version.
