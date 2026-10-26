# platform-sbom U1 round 4: target NOTICE.md wording (tester, 2026-10-23)

From security re-check 3, L-9b fix text items 1-5 and I-8
(`u1/security.md`), and PSC-14 as amended in round 4. The analyst owns the
wording; these are the forms that the extended
`test_notice_names_cpython_incorporated_licences` (`hacl_licence_problems`,
`karamel_licence_problems`), `test_notice_has_ke_app_base_paragraph` and
`test_notice_named_licence_files_are_tracked` pass (proved by
`u1_controls.py --reach`, `r4-red-mutants.txt`).

The developer:
- replaces NOTICE.md's CPython bullet (from `- CPython 3.12 under` up to the
  `- The Debian 12` bullet) with the block between the `cpython-bullet` markers
  (security fix 3: from "; the HACL* hash code" to the end of the sentence);
- appends the blocks between the `karamel-licence-texts` and
  `apache-licence-texts` markers to "## Licence texts", after the
  `licenses/CPython-3.12-HACL.txt` paragraph, each with a blank line before it
  (security fix 4);
- writes `licenses/CPython-3.12-KaRaMeL.txt`: the 4-line header between the
  `karamel-header` markers (it ends with the blank line), then
  `sed -n '1,/\*\//p'` of `Python-3.12.15/Modules/_hacl/include/krml/internal/target.h`
  from the verified tarball (2 lines, 116 B, sha256 6b7cb4bd...8a26). The
  tester's scratch build from security's extract is
  `r4-target-CPython-3.12-KaRaMeL.txt` (sha256 in `r4-red-mutants.txt`);
- writes `licenses/Apache-2.0.txt` as an offline byte copy of the pinned base's
  `/usr/share/common-licenses/Apache-2.0` (security fix 1, its `docker run
  --network none --read-only` command), no header; sha256
  cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30.
  `r4-target-Apache-2.0.txt` is security's probe copy, used only by the reach;
- runs `git add licenses/CPython-3.12-KaRaMeL.txt licenses/Apache-2.0.txt`.

<!-- cpython-bullet:start -->
- CPython 3.12 under `/usr/local`, under the Python License 2.0 (SPDX
  `Python-2.0`: the PSF licence stacked on the BeOpen, CNRI and CWI
  licences). `/usr/local/lib/python3.12/LICENSE.txt` inside the image holds
  that licence stack only. CPython also builds in third-party code under
  its own licences. CPython's own list of it (among them expat and
  libmpdec) is in `licenses/CPython-3.12-incorporated.txt`; the licence of
  the HACL* hash code (MIT) in `_md5`, `_sha1`, `_sha2` and `_sha3`, which
  that list omits, is in `licenses/CPython-3.12-HACL.txt`, and that code
  compiles in KaRaMeL headers (Copyright INRIA and Microsoft Corporation,
  Apache-2.0), whose notice is in `licenses/CPython-3.12-KaRaMeL.txt` and
  licence text in `licenses/Apache-2.0.txt`.
<!-- cpython-bullet:end -->

<!-- karamel-licence-texts:start -->
`licenses/CPython-3.12-KaRaMeL.txt` is the licence header of
`Modules/_hacl/include/krml/internal/target.h` in CPython 3.12.15's release
tarball https://www.python.org/ftp/python/3.12.15/Python-3.12.15.tar.xz,
unmodified; its header gives the tarball's sha256.
<!-- karamel-licence-texts:end -->

<!-- apache-licence-texts:start -->
`licenses/Apache-2.0.txt` is the Apache License 2.0 as Debian's
`base-files` ships it at `/usr/share/common-licenses/Apache-2.0` in the
`ke-app` base image, unmodified (sha256
`cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`).
<!-- apache-licence-texts:end -->

<!-- karamel-header:start -->
CPython 3.12.15: KaRaMeL licence header (Apache-2.0), Modules/_hacl/include/krml/
Source: Python-3.12.15/Modules/_hacl/include/krml/internal/target.h
Tarball: https://www.python.org/ftp/python/3.12.15/Python-3.12.15.tar.xz
Tarball sha256: c2c4321961fab0fb999d66e0cecf521c2ab3994c7992873ea99e306c1094fd5a

<!-- karamel-header:end -->
