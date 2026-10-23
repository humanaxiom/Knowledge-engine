# licenses/CPython-3.12-HACL.txt provenance (developer, 2026-10-22)

- URL: https://www.python.org/ftp/python/3.12.15/Python-3.12.15.tar.xz
  (`curl -q --proto '=https' --tlsv1.2 --fail`)
- Tarball sha256: c2c4321961fab0fb999d66e0cecf521c2ab3994c7992873ea99e306c1094fd5a (equals the base's PYTHON_SHA256)
- Member Python-3.12.15/Modules/_hacl/Hacl_Hash_SHA2.c sha256: 30638efb75c8b185bb09c3df6977e3f3c5d21a1e696218cf7ade6bc4d5201b31
- Extract (`sed -n '1,/^ \*\/$/p'`, 23 lines) sha256: 998ce04fb8ad9dedb0bc1b44938f8c3dcf1089780fa105ce1c8c30fb5554d78c
- Final file (N10a 4-line header, blank line, extract) sha256: d83382d7cac3377506f4901d6a145185c85e5504618a58d36c44da6372b4c483
  (`cmp`-equal to the tester's r3-target-CPython-3.12-HACL.txt)
- Commands: tar -xJf <tarball> Python-3.12.15/Modules/_hacl/Hacl_Hash_SHA2.c (nothing run from it);
  head -5 r3-target-CPython-3.12-HACL.txt > licenses/CPython-3.12-HACL.txt; cat extract >> it.
