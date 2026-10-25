# platform-sbom U7a: security gate audit (the source lock, pure half)

Date: 2026-10-25. Auditor: security. Tree: HEAD 66781a9 (U6) plus the U7a working tree.
`scripts/sbom_check.py` equals `u7a/target-sbom_check.py`; the new test file is
`tests/test_sources_lock.py`. No lock is committed and there is no network. Design:
design-notes "N5 amendment, U7" (items 2, 4, 6) and its resolution-endpoints line. Probes:
`u7a/security-probes.txt` (script `u7a/security_probes.py`; gates image, `python -I`; the baseline
is the tests' `good_lock(SMALL_KEYS)`, which passes clean). verify.sh not run.

## Verdict: PASS

No critical, high or medium finding. Four low and five informational notes, all non-blocking.
`lock_problems` keeps out every host, scheme, userinfo, port, hash, size and file-name smuggle I
tried. What is open is defence in depth for U7b/U7c/U8, before a real lock is committed, plus one
escaping gap and one evidence-hygiene fix.

| ID | Severity | Finding (input) |
|---|---|---|
| L-1 | low | URL charset not restricted: a URL with a tab, CR or LF inside the host or path, a leading NUL or space, a trailing space, a space or non-ASCII in the path passes, because `urlsplit` strips or removes those characters before the host check (`https://files.python<TAB>hosted.org/x.tar.gz`) |
| L-2 | low | Files are not bound to their kind's host and path, except deb: an apk, maven, neo4j, pgdg, pypi or temurin entry passes with every file on another listed host (`pypi:psycopg@3.3.6` from `https://github.com/evil/...`). `pgdg` has no per-kind rule at all: one arbitrary file, no `.dsc`, passes |
| L-3 | low | Raw control bytes in messages: the coverage miss message cleans the purl but prints the key, which is percent-decoded from the SBOM, raw (`pkg:deb/debian/evil@1?upstream=ev%1b%5b2Jil%401` gives `... the lock has no deb:ev<ESC>[2Jil@1 ...`). `_kind_problems` also prints lock keys raw (`deb:x\u001b[2J@1`, `apk:x\u009b2J@1-r0`) |
| L-4 | low (hygiene) | `u7a/reviewer-probes.txt` l.2 holds a Windows user-profile temp path (the absolute path of a scratch probe). Redact before commit (user ruling: redact profile paths) |
| I-1 | info | `HTTPS://` (upper case) passes as https, so a URL's canonical form is not enforced |
| I-2 | info | `size` has no upper bound (`10**30` passes); `name` need not equal the URL's file name; Windows device names (`CON`, `aux.tar.gz`) and `a..b` pass the name rule |
| I-3 | info | An SBOM row can map to a key no lock entry may carry (`pkg:deb/debian/x@1` gives `deb:x@1`, one-letter name; `openjdk@21` gives `temurin:jdk-21`; `upstream=%40` gives `deb:@1`). This fails closed, as a permanent "lock has no ..." miss. A mapping problem would name the cause |
| I-4 | info | Lock JSON nested 100000 deep raises `RecursionError` out of `lock-check` (traceback, exit 1: fails closed but uncaught). `sample_keys` raises `TypeError` on a lock that fails `lock_problems`, so call it only after a clean check |
| I-5 | info | `upstream.from` is free text and is not cleaned; it is never printed today |

## 1. `lock_problems` as the gate (probes U7a-1 to U7a-3)
Rejected, each with a named problem:
- **Userinfo:** `host@evil`, `evil@host`, `u:p@host`, and `evil<backslash>@host`.
- **Host spoofing:**
  - an IDN look-alike (Cyrillic `o`), punycode, a fullwidth dot
  - a trailing dot, upper case, a percent-encoded dot
  - a backslash after the host or as the path
  - IPv4 and IPv6 literals
- **Port:** `:443` and an empty `:`.
- **Wrong scheme:** `http`, `HTTP`, `ftp`, `file`, scheme-relative, `https:/` and `https:` without
  slashes.
- **Query and fragment.**
- **Hashes:** a sha256 upper-case, 63 or 65 long, with a fullwidth digit, or an int.
- **Size:** `0`, `-1`, `True`, `1.0` or `"5"`.
- **File shape:** a sixth file key.
- **Upstream:** an `alg` of `SHA256` or `md5`, sha1 on a pypi file, a value different from the
  sha256, an upper-case or short value, a blank or int `from`.
- **Names:** `../x`, `/etc/passwd`, `a/b`, NUL, `..`, `.x`, 256 characters, a backslash, non-ASCII,
  a newline.
- **deb:** the `.dsc` must sit at `snapshot.debian.org/file/<its own sha1>`, so github.com,
  another sha1, a trailing slash or an upper-case sha1 are rejected. The other deb files must be
  snapshot `/file/<sha1>` URLs, so an orig from `files.pythonhosted.org` is rejected.
- **Hosts:** a pgdg entry is rejected against the committed hosts, because
  `apt-archive.postgresql.org` is not among the nine (O1 (a), Q71). It needs a reviewed hosts
  change at U7c.

Passes that should not, or that are not bound (L-1, L-2, I-1, I-2):
- **L-1:**
  - These URL inputs pass: a tab or LF inside the host, a CR in the path, a leading space or
    NUL, a trailing space, a space or non-ASCII in the path.
  - The Python `urlsplit` removes tab, CR and LF anywhere and strips leading C0 control
    characters and spaces. So the string that was checked is not the string U8 hands to curl.
  - I found no input that turns this into a different host: curl refuses the raw control
    characters, which fails closed.
  - Fix: require the URL to be printable ASCII with no space, backslash, quote or control
    character (for example, fullmatch `https://<host>/[A-Za-z0-9._~%!$&()*+,;=:@/-]*`) and
    `urlunsplit(urlsplit(url)) == url`.
  - A `../` in the path stays on the same listed host (curl normalises it): info.
- **L-2:** bind each kind to the URL shape that item 4 gives it:
  - apk: `gitlab.alpinelinux.org/alpine/aports/-/raw/<commit>/...` or
    `distfiles.alpinelinux.org/distfiles/<branch>/<name>`
  - maven: `repo1.maven.org/maven2/<g path>/<a>/<v>/<name>`
  - pypi: `files.pythonhosted.org/packages/...`
  - temurin: `github.com/adoptium/temurin<feature>-binaries/releases/download/...`
  - neo4j: `github.com/neo4j/neo4j/archive/refs/tags/<ver>.tar.gz`
  - in each case, `name` should be the last segment of the URL where it has one
  - pgdg: at least the deb-shaped `.dsc` rule now

  Today every file is sha256-pinned in a generated, reviewed lock and is never unpacked or run.
  The binding would stop a wrong lock passing the check, without depending on review alone.

## 2. `lock_needs` (probe U7a-5, U7a-7)
- No escape: 32 odd purls were tried, with an empty or `%40` `upstream`, epochs plain and
  `%3A`, `.pgdg`, other distros (`deb/ubuntu`, `apk/wolfi`), `pkg:DEB`, missing namespace,
  version or name, unknown types (npm, golang, cargo, gem, github, oci, generic), an off-version
  Neo4j-group jar, jrt-fs without openjdk, no purl, and a non-purl. Every needs row gives a key or
  a named problem. None gives neither.
- Real fixtures: 458 needs rows map to 458 packages under 182 keys (deb 152, pgdg 3, apk 19,
  neo4j 1, temurin 1, maven 1, pypi 5), with 0 problems. All 182 keys are valid lock keys. The
  counts of the architect hold.
- I-3: some keys cannot be carried by any valid entry. They fail closed, but as an unfixable
  miss; recommend a mapping problem there.

## 3. Miss message escaping (probe U7a-4): L-3
The purl in the miss message goes through `_clean`, as it should. The `{key}` does not, and the
key comes from `unquote(upstream / name / version)`, so the SBOM's `%1b`, `%5d0%3bT%07` and
similar reach stderr raw (3 lines in the probe). Lock keys reach the `_kind_problems` messages
raw (1 deb line and 6 apk lines). Fix: `_clean(key)` in the miss message and in every
`_kind_problems` message (`key`, `want`). The stale message already cleans its key.

## 4. PS-1.2
The only new host literal is `SNAPSHOT_HOST = "snapshot.debian.org"`, with no scheme, plus two
mentions in a docstring and a message. There is no URL literal in `scripts/sbom_check.py` (rule
2), and the host is not a declared config value. The scanner and engine-hardcoded tests pass in
`u7a/green-verify-fast.txt` (949 ran, OK). Its value duplicates a policy host, and it pins the deb
shape: acceptable.

## 5. ReDoS (probe U7a-6)
Each `LOCK_KEY_RES` pattern takes at most 0.04 s on 1 MB of digits, `a-` runs, `1.` runs, `-r`
runs or `jdk-1.` runs. `LOCK_FILE_NAME_RE`, `HEX_RE`, `SNAPSHOT_PATH_RE` and `NEO4J_FROM_RE` take
at most 0.005 s, and `_url_problems` on a 1 MB URL 0.004 s. `lock_problems` on 20000 entries takes
0.86 s, and `lock_needs` on the six fixtures 0.035 s.

## 6. `lock-check` CLI (probe U7a-8)
- A good lock gives rc 0. `--arch x86` gives rc 2. `--sbom "ke app=..."` gives rc 2, through
  `NAME_RE`. `-x=...` is refused by argparse.
- A missing file gives rc 1 with a cleaned message. A CRLF lock gives rc 1, "not in canonical
  form". A deeply nested lock fails with a traceback (I-4).

## 7. Evidence hygiene (`u7a/*`, `tests/test_sources_lock.py`)
- No keys, tokens, private keys, JWTs, password values, model-host name or port, or `KE_*` values.
- The one credential-URL hit is the userinfo case in the test itself, `https://u:p@`
  (synthetic).
- IPs: 127.0.0.1, the stack gateway's internal address in the smoke no-route lines, and a
  Temurin version.
- `u7a_controls.py` works in a `mkdtemp` dir it removes, with no network.
- **L-4:** `u7a/reviewer-probes.txt` l.2 carries a profile path (a SyntaxWarning naming a scratch
  probe of the reviewer). It must be redacted before commit. Owner: reviewer.
