# platform-sbom U1 round 3: target NOTICE.md wording (tester, 2026-10-23)

From design-notes N10 (round 3, security L-9) and PSC-14 as amended in round 3.
The analyst owns the wording; these are the forms that the extended
`test_notice_names_cpython_incorporated_licences` and
`test_notice_named_licence_files_are_tracked` pass (proved by
`u1_controls.py --reach`, `r3-red-mutants.txt`).

The developer:
- replaces NOTICE.md's CPython bullet (from `- CPython 3.12 under` up to the
  `- The Debian 12` bullet) with the block between the `cpython-bullet` markers;
- adds the block between the `hacl-licence-texts` markers to "## Licence texts",
  after the `licenses/CPython-3.12-incorporated.txt` paragraph, with a blank line
  before it;
- writes `licenses/CPython-3.12-HACL.txt`: the 4-line header shown, a blank line,
  then `sed -n '1,/^ \*\/$/p'` of `Python-3.12.15/Modules/_hacl/Hacl_Hash_SHA2.c`
  from the verified tarball (N10a). The tester's scratch build from the
  architect's extract is `r3-target-CPython-3.12-HACL.txt` (sha256 recorded in
  `r3-red-mutants.txt`);
- runs `git add licenses/CPython-3.12-incorporated.txt licenses/CPython-3.12-HACL.txt`.

<!-- cpython-bullet:start -->
- CPython 3.12 under `/usr/local`, under the Python License 2.0 (SPDX
  `Python-2.0`: the PSF licence stacked on the BeOpen, CNRI and CWI
  licences). `/usr/local/lib/python3.12/LICENSE.txt` inside the image holds
  that licence stack only. CPython also builds in third-party code under
  its own licences. CPython's own list of it (among them expat and
  libmpdec) is in `licenses/CPython-3.12-incorporated.txt`; the HACL* hash
  code (MIT) in `_md5`, `_sha1`, `_sha2` and `_sha3`, which that list
  omits, is in `licenses/CPython-3.12-HACL.txt`.
<!-- cpython-bullet:end -->

<!-- hacl-licence-texts:start -->
`licenses/CPython-3.12-HACL.txt` is the MIT licence header of
`Modules/_hacl/Hacl_Hash_SHA2.c` in CPython 3.12.15's release tarball
https://www.python.org/ftp/python/3.12.15/Python-3.12.15.tar.xz,
unmodified; its header gives the tarball's sha256.
<!-- hacl-licence-texts:end -->

<!-- hacl-header:start -->
CPython 3.12.15: HACL* licence header (MIT), Modules/_hacl/
Source: Python-3.12.15/Modules/_hacl/Hacl_Hash_SHA2.c
Tarball: https://www.python.org/ftp/python/3.12.15/Python-3.12.15.tar.xz
Tarball sha256: c2c4321961fab0fb999d66e0cecf521c2ab3994c7992873ea99e306c1094fd5a

<!-- hacl-header:end -->
