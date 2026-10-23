# licenses/CPython-3.12-KaRaMeL.txt provenance (developer, 2026-10-23)

- URL: https://www.python.org/ftp/python/3.12.15/Python-3.12.15.tar.xz
  (`curl -q --proto '=https' --tlsv1.2 --fail`)
- Tarball sha256: c2c4321961fab0fb999d66e0cecf521c2ab3994c7992873ea99e306c1094fd5a (equals the base's PYTHON_SHA256)
- Member Python-3.12.15/Modules/_hacl/include/krml/internal/target.h sha256: d16a59f37a1d4982626870e370889eb9d332a9ad035661b8062f549fc734d061
- Extract (`sed -n '1,/\*\//p'`, 2 lines) sha256: 6b7cb4bd5441f287eeb8b745073c11bc5d2974252bec3b6d8c101ff67f918a26
- Final file (4-line header, blank line, extract) sha256: 323002668cbbd5150617a717d89aa3e00acc128da7588260e470e8eefbab796d
  (`cmp`-equal to the tester's r4-target-CPython-3.12-KaRaMeL.txt)
- Commands: tar -xJf <tarball> <member> (nothing run from it); head -5 r4-target > file; cat extract >> file.
- licenses/Apache-2.0.txt: security's offline `docker run --network none --read-only ... cat /usr/share/common-licenses/Apache-2.0`; 11358 B, sha256 cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30.
