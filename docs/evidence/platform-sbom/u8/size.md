# platform-sbom U8 size and time record (R10; developer, 2026-10-28)

LOCAL ONLY: Windows dev box (Docker Desktop), amd64, one run each. Q62 counts CI only. Not a budget.

| set | components | files | distinct bytes | on disk (blobs + fetch.json) | pull | fetch (marker) | fetch (client) |
|---|---|---|---|---|---|---|---|
| sample | 7 | 25 | 136571547 | n/a (offline_check df: +136808 KiB used after fetch) | 1 s | 25 s | 23.5 s |
| full | 183 | 716 distinct (876 listed) | 1180936586 | 1181080083 B (716 blobs + fetch.json 143497 B) | 1 s | 615 s | 614.2 s |

Sources: `== sources: done (pull 1 s, fetch 25 s) ==` (u8/sample-run.txt, in verify full, offline_check PASS 233 s, verify full PASS 1113 s);
`== sources: done (pull 1 s, fetch 615 s) ==` (u8/full-run.txt, wall 10m17s). The sample df (offline_check "df start" 678507352 KiB used,
"df after fetch" 678644160 KiB used) is a whole-drive figure and includes other host activity.
