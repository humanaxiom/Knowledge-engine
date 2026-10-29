# platform-sbom U8 hop hosts per kind (R9; developer, 2026-10-28)

From the `hops=` field of the `bundle_fetch: ok` lines: sample (u8/sample-run.txt, 25 lines) and full (u8/full-run.txt, 716 lines).
The sample's chains are all contained in the full run's.

| kind | hop chain (in order) | files in full run |
|---|---|---|
| deb | snapshot.debian.org | 482 |
| pgdg | apt-archive.postgresql.org | 8 |
| apk | gitlab.alpinelinux.org (APKBUILD and package files, 201); distfiles.alpinelinux.org (distfiles tarballs/sources, 17) | 218 |
| neo4j | github.com -> codeload.github.com | 1 |
| temurin | github.com -> release-assets.githubusercontent.com | 1 |
| maven | repo1.maven.org | 1 |
| pypi | files.pythonhosted.org | 5 |

`objects.githubusercontent.com` appears in no `hops=` field in the sample or the full run (0 occurrences in either file).
Temurin's redirect target is `release-assets.githubusercontent.com`. O-2: yes, `objects.githubusercontent.com` was unused for every kind
(only the hosts above were used); it is a candidate to drop from `hosts` in U8b as a reviewed change (U8-10), but `release-assets.githubusercontent.com`
must be in the policy for temurin (check it is already there before editing).
