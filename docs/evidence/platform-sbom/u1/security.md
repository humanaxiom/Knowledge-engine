# platform-sbom U1 (PSC-14): security audit

Date: 2026-10-22. Auditor: security. Scope: `git diff 31bfed4` (NOTICE.md,
docs/requirements.md, handoff, log) plus untracked `tests/test_notice_ke_app.py`
and `docs/evidence/platform-sbom/u1/`. No dependency, Dockerfile, script,
tracing or agent-tool change. Read-only audit; nothing in the repo was edited.

## Verdict: PASS

No critical or high findings. M-1 is non-blocking but its wording change is
recommended before commit (it passes all three U1 checks, see below).

## Findings

### M-1 (medium): the "Source code" pointer is untrue in every bundle built before U9
NOTICE.md lines 77-80 tell the reader that `THIRD_PARTY_NOTICES.md` "says, in
its "Source code" section, ..." Today `scripts/bundle.sh` (lines 316-329)
writes no such section and the bundle has no `sources/`. So every bundle from
this commit until U9 states a fact that is false. The text does not claim
that a source obligation is met (it says "whether", not "is"), and no written
offer appears anywhere (`grep -i offer` on NOTICE.md and bundle.sh: none).
PSC-15's rule therefore holds. But a recipient is pointed to a source
mechanism that does not exist yet, and PSC-14 (amended 2026-10-23) only
records the gap without closing it. This finding becomes **high** if any
pre-U9 bundle is handed over, or if the branch merges to main before U9 with
the current wording.

Replacement (keep the first sentence and add one; the added sentence stays
true after U9):

```
## Source code

`THIRD_PARTY_NOTICES.md` says, in its "Source code" section, for each
GPL-family component whether its source is in `sources/` of this bundle.
A bundle whose `THIRD_PARTY_NOTICES.md` has no "Source code" section has
no `sources/` and carries no third-party source code, so it does not
itself provide the source that any of these licences requires.
```

### L-1 (low): "the image's SBOM" is a forward reference until U3
The Debian 12 and added-package bullets cite "the image's SBOM" / "the SBOM".
No bundle carries an SBOM before U3 (PSC-13). Recommended wording (still
passes the check, which needs `SBOM` in the block):
- `licence in `/usr/share/doc/*/copyright` inside the image and, where the
  bundle carries one, in the image's SBOM.`
- `licences in `/usr/share/doc/*/copyright` (and the SBOM where the bundle
  carries one).`

### L-2 (low): pip's vendored packages are not MIT, and pip ships no licence files for them
pip 25.0.1 (`License: MIT`, confirmed) vendors 17 packages
(`pip/_vendor/vendor.txt`), including requests, CacheControl, msgpack and
distro (Apache-2.0), certifi (MPL-2.0), distlib and typing_extensions (PSF-2.0),
idna (BSD-3-Clause), pygments (BSD-2-Clause) and resolvelib (ISC). pip 25.0.1
ships no licence file for any of them. Its dist-info holds only LICENSE.txt
and AUTHORS.txt, and `_vendor` has no LICENSE or COPYING file. The bundle's
`licenses/` has no Apache-2.0 or MPL-2.0 text either. Apache-2.0 §4(a) and
MPL-2.0 §3.1 expect the licence to reach the recipient. This gap predates U1
(it comes from the base image), but "(MIT)" understates it. It is not
GPL-family and not merge-blocking. Fix, in order of preference:
1. the PSC-14 follow-up that drops pip from the last stage (the engine does
   not use it), with the NOTICE line removed in the same change;
2. or add a sentence such as "The packages pip vendors, listed in
   `pip/_vendor/vendor.txt`, keep their own licences (among them Apache-2.0
   and MPL-2.0); pip 25.0.1 ships no licence files for them", and add those
   texts to `licenses/`.

Route this to the analyst or architect.

### L-3 (low): CPython is named only as PSF-2.0
`/usr/local/lib/python3.12/LICENSE.txt` (13,936 B, in the image) is the full
licence stack: CWI, CNRI, BeOpen and PSF, with the docs under PSF-2.0 and 0BSD.
SPDX names that whole stack `Python-2.0`. PSF-2.0 names the operative PSF
agreement, so the wording is defensible. It is more accurate to say where the
full text is, and the check still passes: "... under the Python Software
Foundation License (PSF-2.0); `/usr/local/lib/python3.12/LICENSE.txt` inside
the image holds the full licence history."

### I-1 (info, for U5/U6): GPL lines in the added packages' copyright files
`/usr/share/doc/libldap-2.5-0/copyright` has GPL-2+ and GPL-3+ entries
(mostly with Autoconf or Libtool exceptions). Both `libsasl2-2` and
`libsasl2-modules-db` list GPL-3 and GPL-3+ entries. A classifier that reads
copyright `License:` lines will mark these packages as GPL-family. The
source policy (U6) must take them into account: either fetch their deb
source or record a reviewed exemption.

### I-2 (info): libpq5's licence
The bullet says libpq5 is under the PostgreSQL licence. That is its primary
licence. Its copyright file also lists BSD-2/3-Clause, Tcl and custom
permissive terms. No GPL-family lines. Acceptable as worded.

## Accuracy checks (all run with `--network none --read-only`)
- Base digest: ke-app last-stage FROM =
  `python:3.12-slim-bookworm@sha256:34386ef0...a07258`, which matches NOTICE.md
  byte for byte. The local base image has that RepoDigest, and its RootFS
  layers are a prefix of `ke-app:bundle-737750d06839` (259 MB, the U0 build).
- Added packages: dpkg list of ke-app minus the base gives exactly
  `libldap-2.5-0 2.5.13+dfsg-5`, `libpq5 15.19-0+deb12u1`,
  `libsasl2-2 2.1.28+dfsg-10` and `libsasl2-modules-db 2.1.28+dfsg-10`.
  Nothing was removed. This matches NOTICE.md and `ADDED_PACKAGES`. The
  libpq5 version equals `ARG LIBPQ_VERSION`. The same result holds on
  `ke-app:wt-33a132fbfdd7`.
- pip: `/usr/local/lib/python3.12/site-packages` holds only pip and
  pip-25.0.1.dist-info. METADATA: `Version: 25.0.1`, `License: MIT`. There is
  no setuptools or wheel. This confirms the developer's figure.
- CPython: `Python 3.12.15` under `/usr/local`; `/usr/local/bin` has no uv.
- The libpq5, libldap-2.5-0, libsasl2-2 and libsasl2-modules-db copyright
  files exist under `/usr/share/doc/*/copyright`.

## The new test file and the controls driver
`tests/test_notice_ke_app.py` reads NOTICE.md and docker/app.Dockerfile.
Its fixtures go to a `tempfile.mkdtemp()` directory that it removes
(`_Scratch`). It has no subprocess, no network access, no eval or exec, no
deserialisation and no environment reads. Its regexes are linear (no nested
quantifiers) and run on repo text. `u1_controls.py` puts the repo root on
`sys.path`, writes only into `TemporaryDirectory()`, and never writes
NOTICE.md. Nothing unsafe.

Wording check: the M-1 and L-1 replacements were applied to a temporary copy
of NOTICE.md (the repo was not touched), and all three checks returned
`[]`. Driver: the session scratchpad `reword_check.py`, which imports
`tests.test_notice_ke_app`.

## Evidence sweep (docs/evidence/platform-sbom/u1/)
- Secret patterns (API keys, tokens, passwords, bearer or auth headers,
  private keys, AKIA, ghp_/gh*_, sk-, xox*, DSNs with credentials, and
  `KE_MODEL_UPSTREAM=`/`KE_EGRESS_ALLOWLIST=` values) match only test names.
- No profile paths (`C:\Users`, `/c/Users`, `AppData`, `/home/`) and no SIDs.
- The only IPs are `127.0.0.1` (loopback, port elided). The URLs are public
  pinned tool downloads.
- `orchestrator-verify-full.txt` ends mid-run (no PASS line yet). It is not
  this gate's input, but the orchestrator should check that it completes.

## Telemetry
No change to tracing, spans or exported attributes.

## Re-check after rework round 1 (2026-10-22)

Scope: `git diff 31bfed4` plus untracked U1 files, including
`licenses/Apache-2.0.txt` and `licenses/MPL-2.0.txt` (NEXT-SESSION.md and the
prompt file are excluded). Human ruling: pip stays in ke-app. Read-only: no repo
file was edited except this section and the scan file. Scan output:
`docs/evidence/platform-sbom/u1/security-recheck-scan.txt`. Image probes ran with
`--network none --read-only` on `ke-app:bundle-31bfed4b6a11`.

### Verdict: PASS

No critical or high findings. M-2 is new and is a one-paragraph wording fix,
recommended before commit; if a bundle ships with the current text, M-2 is high.
The four proposed texts below pass all four U1 checks on a scratch copy (scan §4).

### Status of the first-round findings
- **M-1 CLOSED.** The pointer and the "no Source code section" sentence are now
  true in every bundle until U9. They stay true through U3, which adds SBOMs but no
  `sources/` and no section. They stay true through U9, whose row (N15) copies
  `sources/` and writes the section in one unit; N1 forbids bundles in between.
  Residual L-6 below.
- **L-1 CLOSED.** "Where the bundle carries one" is true before U3 and after it.
- **L-3 CLOSED for the identifier and the pointer.** `Python-2.0` is the SPDX id
  for the PSF, BeOpen, CNRI and CWI stack. LICENSE.txt (13,936 B) is that stack
  plus the note on the docs' PSF/0BSD dual licence. The bullet's added last
  clause is wrong: see M-2.
- **L-2 PARTIAL.** Apache-2.0 §4(a) is met: the full text reaches the recipient.
  `pip/_vendor` has no NOTICE file, so §4(d) has nothing to carry. MPL-2.0 §3.1 is
  met for the licence copy. Residual L-2b below.

### M-2 (medium, new): CPython's LICENSE.txt does not hold "the licences of the third-party code CPython bundles"
The image's LICENSE.txt has zero hits for expat, libmpdec, HACL, SipHash,
Mersenne, "David M. Gay", zlib, libffi and OpenSSL (scan §1). CPython in the image
compiles in expat 2.8.5 and libmpdec 2.5.1: `pyexpat` and `_decimal` link no
system libexpat or libmpdec (scan §2). Those notices live in CPython's
`Doc/license.rst` ("Licenses and Acknowledgements for Incorporated Software"),
which the image does not carry. The clause comes from design-notes N10 (review N3),
not from the developer. The test does not pin it. Replace the last sentence of the
CPython bullet:
```
  licences). `/usr/local/lib/python3.12/LICENSE.txt` inside the image holds
  that licence stack only. CPython also builds in third-party code under
  its own licences (among them expat and libmpdec), whose texts are in
  `licenses/CPython-3.12-incorporated.txt`.
```
This needs L-5's file. Until that file exists, use the honest interim instead:
"... holds that licence stack only; the licences of the third-party code CPython
builds in (among them expat and libmpdec) are not yet in this bundle."

### L-5 (low, new; it comes from the base image, as L-2 did): notices for code built into CPython are not shipped
The BSD-2-Clause (libmpdec) and MIT (expat, HACL*, SipHash) terms, and the dtoa.c
and Mersenne Twister terms, require their notice in copies or in the accompanying
documentation. None is in the bundle or the image. The fix is to ship
`licenses/CPython-3.12-incorporated.txt`: the incorporated-software part of
CPython v3.12.15 `Doc/license.rst`, fetched over HTTPS from the tag. Record its
URL and sha256 in "Licence texts", as the GNU and Valkey lines do. The fetch needs
network, so a maintainer does it. Not GPL-family, so non-blocking.

### L-2b (low, residual of L-2): pip's PSF, BSD, ISC and MIT vendored packages need their own notices
Generic Apache and MPL texts cannot carry per-package copyright lines. pip 25.0.1
(`vendor.txt`, scan §1) vendors distlib and typing_extensions (PSF-2.0), idna
(BSD-3-Clause), pygments (BSD-2-Clause) and resolvelib (ISC). It also vendors
platformdirs, pyproject-hooks, rich, setuptools' pkg_resources, tomli,
truststore and urllib3, all MIT. MIT also requires the notice, and the first audit
missed it. All of these require the copyright and permission notice in copies. pip
ships no licence file for any of them (scan §1).

The bundle does not carry these notices another way. `THIRD_PARTY_NOTICES.md`'s
table covers only `uv.lock` packages, and it lists paths inside the image, not
texts. There is partial cover: `/opt/venv` in the image holds the licence files of
idna 3.20, typing_extensions 4.16.0 and urllib3 2.8.0. These have the same holders
but later versions. Nine packages have no notice anywhere: distlib, pygments,
resolvelib, platformdirs, pyproject-hooks, rich, pkg_resources, tomli and
truststore.

The first audit's fix option 2 ("add those texts") was incomplete. That is this
auditor's error. As a result, the handoff's "no longer a compliance gap"
overstates the position. Fix, for the human to choose:
1. Ship `licenses/pip-25.0.1-vendored.txt`, holding each vendored package's own
   licence file at its `vendor.txt` version. A maintainer fetches each file with
   its sha256, from pip 25.0.1's sdist (`src/pip/_vendor/`; *confirm at fetch*)
   or from each package's own release. Name the file in the pip bullet (text below).
2. Or drop pip from the last stage (the open follow-up).

Proposed pip-bullet text (passes the checks):
```
  The packages pip vendors, listed in `pip/_vendor/vendor.txt`, keep their
  own licences: Apache-2.0 (CacheControl, distro, msgpack, requests),
  MPL-2.0 (certifi), Apache-2.0 OR BSD-2-Clause (packaging), PSF-2.0
  (distlib, typing_extensions), BSD-3-Clause (idna), BSD-2-Clause
  (pygments), ISC (resolvelib) and MIT (platformdirs, pyproject-hooks,
  rich, setuptools' pkg_resources, tomli, truststore, urllib3). pip 25.0.1
  ships no licence files for them, so the bundle carries the Apache-2.0 and
  MPL-2.0 texts as `licenses/Apache-2.0.txt` and `licenses/MPL-2.0.txt`,
  and each package's own licence file, with its copyright notice, in
  `licenses/pip-25.0.1-vendored.txt`.
```
Naming certifi also states plainly which code MPL-2.0 governs (MPL-2.0 §3.1).

### L-6 (low, residual of M-1; the wording was this auditor's): "carries no third-party source code" is false in letter
The image tars carry `.py` source: the stdlib, pip, and psycopg's pure-Python
part. The sentence understates what ships and claims no compliance, so the risk
is low. "These licences" also has no antecedent in its section. Replace the
second sentence (it passes the checks, because NOT_PROVIDED is kept):
```
A bundle whose `THIRD_PARTY_NOTICES.md` has no "Source code" section has
no `sources/`, so it does not itself provide the source that a
GPL-family licence requires.
```

### L-7 (low, new): licenses/Apache-2.0.txt is not the canonical bytes, and the provenance note misstates why
The offline reference is Debian `base-files` 12.4+deb12u15 in the pinned base.
dpkg owns its files, and their md5 matches `base-files.md5sums` (scan §3).
- `/usr/share/common-licenses/MPL-2.0` is 16,726 B with sha256
  `fab3dd6b...863e85`. It is identical to the committed MPL-2.0.txt.
- `/usr/share/common-licenses/Apache-2.0` is 11,358 B with sha256
  `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. This is
  also the widely published hash of apache.org's LICENSE-2.0.txt, which was not
  fetched in this session.

The committed file (11,357 B, `c71d239d...`) is the canonical text minus its
**leading** blank line: the canonical first byte is LF, and the rest is identical
(scan §3). The provenance note says "differs by a trailing newline", which is
wrong. The licence content is word for word the same, so this has no legal effect.
But NOTICE says "unmodified", and the target and test comment cite 11,358 B. The
fix needs no network. In Git Bash, prefix the command with
`MSYS_NO_PATHCONV=1`:
`docker run --rm --network none --entrypoint cat python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 /usr/share/common-licenses/Apache-2.0 > licenses/Apache-2.0.txt`
Expect sha256 `cfc7749b...3d30`. Then correct the provenance note.

### L-8 (low, new; check 5): the "Licence texts" paragraph points recipients to a repo-only path and overclaims
Bundles carry `app/docs/quickstart.md` only (`bundle.sh` line 300). They carry no
`docs/evidence/`, so a recipient cannot follow the pointer. "They cover the
packages that the base's pip vendors" also claims more than two texts can do.
Replacement (true after L-7; a recipient can check it offline, and it passes the
checks):
```
`licenses/Apache-2.0.txt` and `licenses/MPL-2.0.txt` are the Apache License 2.0
and Mozilla Public License 2.0 texts, unmodified: byte for byte the same as
`/usr/share/common-licenses/Apache-2.0` and `/usr/share/common-licenses/MPL-2.0`
(Debian `base-files`) inside the `ke-app` image. They cover the Apache-2.0 and
MPL-2.0 packages that the base's pip vendors.
```
Side benefit: the image itself carries both texts, so §4(a) and §3.1 hold even if
the image travels without the bundle.

### Info
- I-3 (for U9): NOTICE.md and THIRD_PARTY_NOTICES.md say `sources/`, but N9/N10
  put the directory at `app/sources/`. From the root copies that path does not
  resolve. U9 should say `app/sources/`, or state that the paths are relative to
  `app/`.
- I-4 (commit): both licence texts are untracked. `bundle.sh` ships only
  `git ls-files -- licenses`, and its hard check (line 195) covers only
  GPL-3.0.txt and LGPL-3.0.txt. If the texts are not git-added, they are dropped
  silently. The fast test checks the working tree. The orchestrator should confirm
  `git ls-files licenses` lists both at commit, or add them to the line-195 list.

### Evidence sweep (new u1/ files: licence-texts-provenance.md, pip-probe.txt, r1-*-verify-fast.txt, r1-target-notice-sections.md, red-mutants.txt, u1_controls.py)
- Secret patterns: the only hit is the first audit's own description line.
- Profile paths and SIDs: the same single descriptive line, nothing else.
- IPs: loopback, 0.0.0.0, and Docker-internal 172.19.0.2 and 192.168.160.2 from
  the smoke network probe. These are harmless.
- URLs: public licence and tool URLs only.
- pip-probe.txt runs with `--network none` on the pinned digest.
- `orchestrator-verify-full.txt` now ends with `verify full: PASS (697s)`, but it
  predates the rework (20:49, against NOTICE.md and Apache-2.0.txt at 21:06). The
  orchestrator needs a fresh `scripts/verify.sh full` before commit.
- No change to tracing, spans or exported attributes.

## Re-check 2 after rework round 2 (2026-10-22)

Scope: `git diff 31bfed4` plus untracked U1 files, including
`licenses/CPython-3.12-incorporated.txt`; NEXT-SESSION.md and the prompt file are
excluded. Human ruling: pip is dropped and ke-app is flattened (N10a). Read-only:
the only repo writes are this section and two evidence files,
`u1/security-cpython-second-fetch.txt` (Q48) and `u1/security-recheck2-probes.txt`
(image probes). The images were probed by ID: U1 `2c662c94f624` (the GREEN full
build, `ke-app:wt-33a132fbfdd7` and `ke-app:bundle-31bfed4b6a11`), U0 `f113aac6fa37`
and base `34386ef0cb08`. The probes were my own `--rm --network none` runs, labelled
`ke.scratch=sec-u1r2`. No other container was touched.

### Verdict: PASS
There are no critical or high findings. One low finding is new (L-9), and one low
finding predates this change (L-12). Two info items are new, and one carried item
needs action at commit (I-4).

### Q48 second fetch: CONFIRMED
- python.org `Python-3.12.15.tar.xz` was fetched over HTTPS (TLS 1.2 or later,
  `--fail`). Its sha256 `c2c43219...94fd5a` equals the pinned base's
  `PYTHON_SHA256`, which was read offline with `docker image inspect`.
- I extracted exactly one regular-file member, `Doc/license.rst`, into a fresh
  directory and executed nothing from it. Its sha256 `34183287...cadf4e5` equals
  the file's header line.
- The N10a sed extract (808 lines, 38,036 B, `d4f3b214...40698a`) is `cmp`-equal
  to the file minus its 5 header lines. `licenses/* -text` protects the bytes
  from autocrlf.

### Status of the earlier findings
- **M-2 CLOSED.** The bullet now says LICENSE.txt holds "that licence stack only"
  and points to the incorporated-licences file, which exists and is verified.
  Residual: L-9.
- **L-5 CLOSED**, except for HACL* (L-9).
- **L-6 CLOSED.** The Source code text is this auditor's replacement, verbatim.
- **L-8 CLOSED.** The Apache/MPL paragraph is gone. The new "Licence texts"
  paragraph cites a public URL and the header's sha256, and no repo-only path
  (`test_notice_cites_no_repo_evidence_path`).
- **L-2/L-2b CLOSED** by the pip removal (verified in the saved tar, below).
  **L-7 moot**: the file was deleted.
- I-1 and I-3 are carried as before.

### Checks
- **pip gone (check 2).**
  - `docker save` gives 54,872,576 B, matching `size.md`, in 5 layers (U0 has 9,
    the base 4): `/` flattened, `/opt/venv`, `/app`, WORKDIR (empty), and the
    useradd `/etc` files.
  - Across all layers there are 0 pip paths, 0 `.wh.` whiteouts, 0 `_vendor`
    paths and 0 `.whl` files. The dist-infos are only the venv's lock packages.
    The only remaining name that contains `pip` is the stdlib `ensurepip` module,
    with an empty `_bundled/`.
  - `find_spec('pip')` is None in both `/usr/local/bin/python3` and
    `/opt/venv/bin/python`, and there is no pip on PATH.
  - `ensurepip --version` still prints the 25.0.1 constant. This is harmless
    (N10a).
- **Flatten is safe (check 3).** A full lstat walk compared U0 and U1. 547 paths
  are only in U0, all of them pip. 156 are only in U1, all root-owned 0644
  stdlib `__pycache__/*.pyc` (I-5). No other path changed mode, owner, link
  count or link target, and no file carries xattrs in any of the images.
  - Same as the base: setuid/setgid (11, md5 equal), world-writable (`/tmp`,
    `/var/tmp`, `/run/lock`, all 1777), group-writable (12) and hardlinks (4).
  - The runtime user is uid 10001 `ke`. It can write only `/tmp`, `/var/tmp`,
    `/run/lock` and `/var/lock`, the same as U0.
  - dpkg: U1 equals U0 (109 packages). The base plus the four ADDED_PACKAGES,
    and nothing else.
- **Dropped ENVs.** Outside `docs/`, the only mention of `GPG_KEY`,
  `PYTHON_VERSION` or `PYTHON_SHA256` is the Dockerfile comment.
  - grype still identifies CPython through its binary cataloguer (python 3.12.15
    rows), and U4's planned check uses syft's binary cataloguer, not ENV.
  - `GPG_KEY` is a public key ID, not a secret.
  - The Q48 anchor is read from the pinned base, not from ke-app, so nothing
    is lost.
  - The config is otherwise equal to U0's. PATH loses only its duplicate
    `/usr/local/bin`.
- **Smoke no-pip (check 4).**
  - The step takes the container output with `"$(...)" || FAIL` and
    `read -r ... <<<`, compares it only as a quoted string with `-`, and prints
    it only inside a double-quoted message. There is no `$(( ))`, no `eval` and
    no unquoted expansion.
  - Empty output fails, per the orchestrator's ruling. I reproduced this, and
    the test subtest "exits 0 and prints nothing" covers it.
  - The six injection payloads in `test_smoke_never_evaluates_the_pip_token`
    fail closed. See I-6 for the one lax shape.
- **NOTICE (check 5).** Every claim in the new sections was checked against the
  image and the Dockerfile and is true:
  - the shipped stage, the flatten and the base digest;
  - the four added packages and their versions;
  - pip and its wheel are absent, and so is uv;
  - the extract is unmodified, from that URL, with that sha256.
  - Overreach: L-9 only.
- **Scan (check 6).** `ignore: []`. No scan policy, compose or scan script file
  changed: the test diffs only re-target D10 and the pin check, and
  `test_scan_command_is_exactly_the_d5_policy` is ok.
  - The reported rows are 6 Medium and 1 Negligible, all CPython binary rows,
    and none is a fixed High. `scan: done` and `verify full: PASS (718s)`.
  - pip's 6 GHSA rows in U0 are gone: wf93-45jw-7689, 4xh5-x5gv-qwph,
    qwm4-qh6w-59xr, 6vgw-5pg2-w6jp, jp4c-xjxw-mgf9 and 58qw-9mgm-455v.
- **Evidence sweep (check 7).** The new or changed u1/ files are:
  cpython-incorporated-provenance.md, licence-texts-provenance.md, r2-*,
  size.md, u1_controls.py and review.md.
  - Secret patterns: none found.
  - Profile paths and SIDs: none found.
  - IPs: loopback and the Docker-internal 172.30.0.2, 172.19.0.2 and
    192.168.144.2 from the smoke no-route probe.
  - URLs: public only.
  - `KE_MODEL_UPSTREAM` and `KE_EGRESS_ALLOWLIST` are unset, and the model tests
    skip with a named reason.
- **Test code.** `tests/test_ke_app_no_pip.py`, `test_notice_ke_app.py` and
  `u1_controls.py` have no eval, exec, shell or network use.
  - fake_docker's new `exec(compile(...))` runs smoke.sh's own `-c` code in an
    `-I -S -B` child under a temp root.
  - Its `FAKE_API_FILES` paths are test-controlled only.

### L-9 (low, new; an upstream gap): CPython's HACL* MIT notice is in neither the file nor the bundle
- 3.12.15 builds `_md5`, `_sha1`, `_sha2` and `_sha3` (all in the image's
  lib-dynload) from `Modules/_hacl/`.
- Those sources carry an MIT header: "Copyright (c) 2016-2022 INRIA, CMU and
  Microsoft Corporation / Copyright (c) 2022-2023 HACL* Contributors ... shall be
  included in all copies or substantial portions".
- `Doc/license.rst` has 0 `HACL` hits, so the faithful extract cannot carry this
  notice.
- NOTICE's "third-party code ... whose texts are in
  `licenses/CPython-3.12-incorporated.txt`" therefore overclaims for HACL*. It is
  not GPL-family, and it is non-blocking.

Fix, for the analyst or architect to choose:
1. Add `licenses/CPython-3.12-HACL.txt`: the MIT header of
   `Python-3.12.15/Modules/_hacl/Hacl_Hash_SHA2.c`, taken verbatim from the
   same tarball, which is anchored to `PYTHON_SHA256`. Add one NOTICE clause
   pointing to it.
2. Or reword: "... whose texts, as CPython 3.12.15's `Doc/license.rst` lists
   them, are in `licenses/CPython-3.12-incorporated.txt`; that list omits the
   HACL* hash code (MIT) that CPython also builds in."

### L-12 (low; predates this change, kept in the new helper): the digest-pin check accepts a self-named or forward stage
- `test_stack_compose.unpinned_bases` treats every name that appears after `AS`
  anywhere in the file as a stage.
- As a result, `FROM alpine AS alpine` and `FROM later` followed by a later
  `... AS later` both return `[]`, although the first pulls an unpinned image.
  The old code had the same rule.
- There is no live instance: all 7 FROMs in `docker/` are digest-pinned or
  `scratch`.
- Fix (tester): count a name as a stage only when an earlier line defines it,
  and add these two cases to `UNPINNED_CONTROLS`.

### Info
- **I-5:** the 156 `.pyc` files written by pip's own run in `runtime` ship. They
  are root-owned 0644 and not writable by `ke`, so they are harmless. For a
  byte-minimal flatten, use `python -B -m pip uninstall -y pip`.
- **I-6:** `read -r` keeps only the first line. Output of `-` followed by a
  second line holding a pip path would pass. The shipped check cannot produce
  it, because it makes one print and every hit starts with `/` or is
  `pip_(importable)`. Optional hardening that keeps the fail-on-empty ruling:
  compare the whole output with `[ "$pip_out" = - ]`.
- **I-4 (carried; it becomes medium if the commit omits the file):**
  `licenses/CPython-3.12-incorporated.txt` is untracked.
  - `bundle.sh` ships only `git ls-files -- licenses`, and its hard check
    (line 195) lists only GPL-3.0 and LGPL-3.0.
  - The r2 GREEN bundle was therefore built without the file, and NOTICE
    names it.
  - At commit: `git add` the file, and add it to the line-195 list, or add a
    test that every `licenses/...` path NOTICE names is tracked. The
    orchestrator's pre-commit `verify.sh full` must run after the add.

### Telemetry
No change to tracing, spans or exported attributes.

## Re-check 3 after rework round 3 (2026-10-23)

Scope: `git diff 31bfed4`, `git diff --cached` (4 staged files) and untracked u1/
files; NEXT-SESSION.md and the prompt file excluded. Read-only except this
section, `u1/security-recheck3-probes.txt` (all probe output) and the handoff
lines. Own probes only: `--rm --network none --read-only`, label
`ke.scratch=sec-u1r3`, on the pinned base, `2c662c94f624` and `071866c74d68`;
0 labelled containers left. No other container touched.

### Verdict: PASS
No critical or high. L-9, L-12, I-4 and I-6 are closed. KaRaMeL ruling: YES,
compiled in; that is a new low finding, L-9b, with exact fix text below.

### 1. HACL second fetch: CONFIRMED
- My tarball (`cpy-fetch/`) re-hashed: `c2c43219...94fd5a` = the base's
  `PYTHON_SHA256`. 0 links or devices in the member list; 32 members extracted
  to a fresh dir, nothing executed.
- `sed -n '1,/^ \*\/$/p' Modules/_hacl/Hacl_Hash_SHA2.c`: 23 lines,
  `998ce04f...d78c`; `cmp` with `tail -n +6 licenses/CPython-3.12-HACL.txt`:
  equal. File `d83382d7...c483`; index blob = work tree; 0 CR; `-text` applies.

### 2. KaRaMeL ruling: YES, compiled into all four modules
- Build: `Modules/Setup.stdlib.in` l.79-82 build `_md5`, `_sha1`, `_sha3` from
  `_hacl/Hacl_Hash_*.c` and `_sha2` from `libHacl_Hash_SHA2.a`, all with
  `-I$(srcdir)/Modules/_hacl/include`. `Makefile.pre.in` `LIBHACL_HEADERS`
  (l.595-603) lists all six krml headers as deps of every `MODULE__*_DEPS`.
  All four `.so` are in the image's lib-dynload and import under `-I`.
- Includes: each `Hacl_Hash_*.c` -> `internal/Hacl_Hash_*.h` -> `krml/types.h`,
  `krml/lowstar_endianness.h`, `krml/internal/target.h`; `types.h` pulls in
  `fstar_uint128_struct_endianness.h` and `FStar_UInt128_Verified.h` (which pulls
  `FStar_UInt_8_16_32_64.h`).
- Expanded into the object code: `load32_le` x64 (MD5), `load32_be`/`load64_be`
  x16 each (SHA2), `store*`, `KRML_MAYBE_FOR*` loop macros, `KRML_HOST_*`, and
  `KRML_CHECK_SIZE` (SHA3) are KaRaMeL macros, and SHA2 calls the
  `static inline FStar_UInt128_add` x2. These are KaRaMeL code compiled in, not
  just declarations.
- Licence: 5 headers say "Copyright (c) INRIA and Microsoft Corporation. All
  rights reserved. Licensed under the Apache 2.0 License." `types.h` has no
  notice. `CPython-3.12-incorporated.txt` has 0 KaRaMeL/krml/INRIA hits.

### L-9b (low, new; licence attribution, non-blocking): KaRaMeL's Apache-2.0 notice is not shipped or named
- Apache-2.0 4(a) needs a copy of the licence with the object form; the notice
  is how a reader learns it applies. Today the bundle never names KaRaMeL.
- Mitigation (why low): the terms already travel twice. They are in
  `CPython-3.12-incorporated.txt` l.377-552, the OpenSSL section (sections 1-9;
  `diff -w` against base-files differs only in the URL scheme). They are also in
  the image at `/usr/share/common-licenses/Apache-2.0`. Neither is attributed
  to this code.
- Fix (tester RED first, extending `hacl_licence_problems`; then developer):
  1. `licenses/Apache-2.0.txt`: a byte copy, read offline, of the pinned base's
     `/usr/share/common-licenses/Apache-2.0` (base-files 12.4+deb12u15, 11358 B,
     sha256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`;
     verified identical in base, 2c662c94 and 071866c7). Use `docker run --rm
     --network none --read-only --entrypoint /bin/cat
     python:3.12-slim-bookworm@sha256:34386ef0...7258
     /usr/share/common-licenses/Apache-2.0 > licenses/Apache-2.0.txt`. Add no
     header, so the sha256 stays checkable. Then `git add`.
  2. A sibling, `licenses/CPython-3.12-KaRaMeL.txt`, in the N10a shape (4
     header lines, a blank line, the extract). Leave the HACL file as it is,
     since its body is cmp-pinned:
     ```
     CPython 3.12.15: KaRaMeL licence header (Apache-2.0), Modules/_hacl/include/krml/
     Source: Python-3.12.15/Modules/_hacl/include/krml/internal/target.h
     Tarball: https://www.python.org/ftp/python/3.12.15/Python-3.12.15.tar.xz
     Tarball sha256: c2c4321961fab0fb999d66e0cecf521c2ab3994c7992873ea99e306c1094fd5a

     /* Copyright (c) INRIA and Microsoft Corporation. All rights reserved.
        Licensed under the Apache 2.0 License. */
     ```
     Extract: `sed -n '1,/\*\//p' Modules/_hacl/include/krml/internal/target.h`
     (2 lines, 116 B, sha256
     `6b7cb4bd5441f287eeb8b745073c11bc5d2974252bec3b6d8c101ff67f918a26`). The
     other 4 notices say the same; the two FStar files wrap it differently.
     `git add` the file.
  3. In the NOTICE CPython bullet, replace from "; the HACL* hash code" to the
     end of the sentence with: "; the licence of the HACL* hash code (MIT) in
     `_md5`, `_sha1`, `_sha2` and `_sha3`, which that list omits, is in
     `licenses/CPython-3.12-HACL.txt`, and that code compiles in KaRaMeL
     headers (Copyright INRIA and Microsoft Corporation, Apache-2.0), whose
     notice is in `licenses/CPython-3.12-KaRaMeL.txt` and licence text in
     `licenses/Apache-2.0.txt`." This also fixes I-8.
  4. Add two NOTICE "Licence texts" paragraphs:
     "`licenses/CPython-3.12-KaRaMeL.txt` is the licence header of
     `Modules/_hacl/include/krml/internal/target.h` in CPython 3.12.15's
     release tarball
     https://www.python.org/ftp/python/3.12.15/Python-3.12.15.tar.xz,
     unmodified; its header gives the tarball's sha256."
     "`licenses/Apache-2.0.txt` is the Apache License 2.0 as Debian's
     `base-files` ships it at `/usr/share/common-licenses/Apache-2.0` in the
     `ke-app` base image, unmodified (sha256
     `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`)."
  5. Analyst: requirements.md l.~3474 ("`licenses/` gains no Apache-2.0 ...
     text for pip") stays true because it is scoped to pip. Add the KaRaMeL
     reason next to it. The test fixture's `UNTRACKED_FILES`
     `licenses/Apache-2.0.txt` is a scratch-repo control; rename it to avoid
     confusion. Remove "the KaRaMeL headers are unsettled" from the
     COMPLETENESS message.

### 3. NOTICE wording: TRUE, no completeness overclaim
- "CPython's own list of it (among them expat and libmpdec)" describes the
  list, and it is true: the file has both sections. HACL* "(MIT)", the 4
  module names, "which that list omits" and the provenance paragraph are true.
  No "all" or "complete" (`COMPLETENESS_RE` guards it).
- The KaRaMeL omission is L-9b, an omission, not a false claim.
- **I-8 (info):** "the HACL* hash code ... is in `licenses/...HACL.txt`" reads
  as if the code were in the file. Folded into the L-9b fix 3.

### 4. Smoke whole-output no-pip: SAFE
- `pip_out="$(... )" || FAIL`, then `[ "$pip_out" = - ]`. The output is only
  ever a quoted operand or inside a double-quoted message: no `eval`, arithmetic
  expansion, unquoted expansion or `read`. The python is a fixed `-I` string
  with no host input.
- Reproduced (probes section 4):
  - `-` and `-\n\n` pass (command substitution strips trailing newlines, which
    carry no content).
  - These fail: empty, `\n`, `-\n/usr/bin/pip` (second line), ` -`, `-\r`,
    `-o`, `!`, `-a -`, `= -` and a literal `$(touch x)`, which is not run.
- I-6 CLOSED.

### 5. L-12: CLOSED
- `unpinned_bases` adds an alias to `defined` only after it has judged that
  FROM, so `FROM alpine AS alpine` and a forward reference are both flagged.
  Both are in `UNPINNED_CONTROLS`, next to 8 others and 4 passing cases.
- Case-folding matches BuildKit's lower-cased stage names. ARG-based or
  multi-line FROMs fail closed. The repo loop now asserts through the helper.

### 6. I-4: CLOSED by the test; no bundle.sh change needed
- `untracked_licence_problems` finds every `licenses/...` token in NOTICE
  (lookbehind-anchored; subpaths fail closed). It checks each against
  `git ls-files -z -- licenses`, the same source bundle.sh ships from (l.314).
  `GIT_DIR` and related variables are scrubbed, ceiling dirs are set, and it
  fails, never skips, without git or a work tree. Its 6 controls and 2 passing
  cases cover untracked, missing, case and bare-sentence names.
- All 5 licence files are in the index (4 staged).
- The l.195-196 list checks only that a file is non-empty, not that it is
  tracked. Adding the CPython names there would duplicate a list that can
  drift, and is weaker than the test. The test runs in every `verify.sh` and CI
  run, so it is enough.
- **I-7 (info, optional):** if bundles are ever cut from an edited tree without
  verify, a runtime twin of the test in bundle.sh (each NOTICE `licenses/` path
  in `git ls-files`) would cover it.

### 7. Evidence sweep (r3-*, cpython-hacl-provenance.md, base-config.json, u1_controls.py, windows-run.txt, orchestrator-verify-full.txt as of 23:58)
- No secret patterns, profile paths or SIDs. IPs: loopback, 0.0.0.0 and
  Docker-internal 172.30.0.2. URLs: python.org, github, raw.githubusercontent,
  download.docker.com, powershellgallery, and loopback.
- `base-config.json`'s `GPG_KEY` is CPython's public release-signing key ID,
  not a secret.
- `u1_controls.py`'s only `eval` is a mutant string under test (S1). The test
  modules have no shell=True, network or deserialisation.
- `orchestrator-verify-full.txt` was still being written; I swept only the
  part present at that time.

### Carried
I-1 and I-3 as before; I-5 (`.pyc`) is a follow-up per requirements.

### Telemetry
No change to tracing, spans or exported attributes.

## Re-check 4 after rework round 4 (2026-10-23)

Scope: the L-9b fix only (licences/, NOTICE.md, round 4 evidence). Read-only
except this section and `u1/security-recheck4-probes.txt` (all probe output).
Own probes only: `--rm --network none --read-only`, label `ke.scratch=sec-u1r4`,
on the pinned base `34386ef0...7258`; 0 labelled containers left.

### Verdict: PASS. L-9b CLOSED. No critical, high, medium or low open.
- **Fix 1:** `licenses/Apache-2.0.txt` is 11358 B, sha256 `cfc7749b...d30`, and
  `cmp`-equal to `/usr/share/common-licenses/Apache-2.0`, read offline from the
  pinned base (base-files 12.4+deb12u15). It has no header.
- **Fix 2:** in `licenses/CPython-3.12-KaRaMeL.txt` (421 B, `32300266...796d`),
  `tail -n +6` is `cmp`-equal to my re-check 3 extract (116 B, `6b7cb4bd...8a26`).
  `head -n 5` is `cmp`-equal to my header text, and the file is header + extract
  byte for byte. The HACL file is unchanged (`d83382d7...c483`).
- **Fixes 3 and 4:** after whitespace normalisation, NOTICE.md contains the
  bullet tail and both Licence-texts paragraphs exactly as written. I-8 is closed.
- **Fix 5:** requirements l.3495-3497 give the KaRaMeL reason next to the pip
  line. No "unsettled" is left in tests/ or NOTICE.md. The scratch fixture name
  is now `_SCRATCH_UNTRACKED`.
- **Staging:** all four new licence files are in `git diff --cached`, and each
  index blob equals its work tree. Every `licenses/*.txt` has 0 CR bytes.
- **Sweep:** `cpython-karamel-provenance.md`, `r4-*` and
  `licence-texts-provenance.md` are clean. They have no secret patterns (the
  only hits are test names), no profile paths, SIDs or IPs. URLs: python.org,
  github, raw.githubusercontent, apache.org (licence text), download.docker.com,
  powershellgallery. The round 4 test code adds no network access,
  `shell=True`, eval or deserialisation. Its only subprocess call is `git` with
  an argv list.
- Carried: I-1, I-3, I-5 and I-7 (info) as before. No change to telemetry.
