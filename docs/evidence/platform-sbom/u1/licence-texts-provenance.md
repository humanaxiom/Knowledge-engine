SUPERSEDED 2026-10-23: the human dropped pip from ke-app (N10a); the Apache-2.0 and MPL-2.0 texts this file records were deleted.

# Licence texts provenance (platform-sbom U1 rework round 1)

Both files are byte-for-byte copies (cmp-verified) of licence files from packages locked in uv.lock and installed into .venv by uv, which verifies each wheel hash. Taken offline. Nothing was removed or edited; neither file has a package-specific preamble.

| Committed file | Package | Version | Wheel (uv.lock) | File inside the wheel | Bytes | sha256 |
|---|---|---|---|---|---|---|
| licenses/Apache-2.0.txt | opentelemetry-api | 1.45.1 | opentelemetry_api-1.45.1-py3-none-any.whl (sha256 b31553efa588ae44bc306f863c785c5333a9ecc091248c6ee68b4b6c87fdedfb) | opentelemetry_api-1.45.1.dist-info/licenses/LICENSE | 11357 | c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4 |
| licenses/MPL-2.0.txt | pathspec | 1.1.1 | pathspec-1.1.1-py3-none-any.whl (sha256 a00ce642f577bf7f473932318056212bc4f8bfdf53128c78bbd5af0b9b20b189) | pathspec-1.1.1.dist-info/licenses/LICENSE | 16726 | fab3dd6bdab226f1c08630b1dd917e11fcb4ec5e1e020e2c16f83a0a13863e85 |

Notes: certifi's LICENSE is a ca-bundle notice, not the MPL text, so pathspec was used for MPL-2.0. The MPL file is 16726 bytes, the canonical size. The Apache file is 11357 bytes (canonical 11358 differs by a trailing newline).
Status: both files are untracked; they must be git-added at commit time (bundle.sh ships git ls-files -- licenses).
