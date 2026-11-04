# Q83 (a) re-lock SBOMs (2026-11-02): derived counts and hashes (A77 option 2)

The six SBOM documents themselves are not committed. They stay on the maintainer host at <scratch>/relock-20261102-sboms/.
All six are SPDX JSON (`spdxVersion` present); no syft-json document is among them. "Packages" is `jq '.packages | length'`.

| File | Size (bytes) | SHA-256 | Packages |
|---|---|---|---|
| ke-app.spdx.json | 3093690 | 1f3f8d8112c263f3a2b95f34d119dc260ec94e26a076453df3128d6af0bfaec0 | 154 |
| ke-gateway.spdx.json | 1084317 | 69eb3043b7ee89fa0d40208071e67f83e7f63c10700bab2c71d02ba548614f94 | 72 |
| ke-neo4j.spdx.json | 5263724 | 6c9b5630a178942a03a3b5ca800c061d2fb2620d9ee5aec81f598a931f5c7b34 | 340 |
| phoenix.spdx.json | 3884596 | 07472ee7129572caceee52923b54b37899afbf9943c72a97b8e3052f9d91fae3 | 278 |
| postgres.spdx.json | 6923171 | b6968348dfed0f4e1e5dc33cfea82f9b0c5fb9e024df23657014c8efd0adbe64 | 150 |
| valkey.spdx.json | 558263 | 7adea639d7d6561f10f46ab3a8b4ee8fb5f5ea22a1fd7ef976141c9fcdb1f149 | 25 |

Commands (run in the sboms directory):

    stat -c %s <file>
    sha256sum <file>
    jq '.packages | length' <file>
    jq -r .spdxVersion <file>

Note: `deb:cyrus-sasl2@2.1.28+dfsg-10` keeps `amd64` in the lock because the postgres image's SBOM still lists libsasl2-2 and libsasl2-modules-db at 2.1.28+dfsg-10.
