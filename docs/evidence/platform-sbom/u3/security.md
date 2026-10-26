# platform-sbom U3 (PSC-13): security audit, 2026-10-23

Scope: `git diff 98b6d27`, plus the untracked `scripts/sbom_check.py`,
`tests/test_sbom_bundle.py` and `docs/evidence/platform-sbom/u3/`. Raw probe
output is in `u3/security-u3-probes.txt` (P1-P5). The probes were labelled
`--rm` containers and the project `ke-secu3probe-sbom`, and they left nothing
behind.

## Verdict: PASS

No critical or high findings. M-1 (evidence) and L-1 (carry) do not block.

## 1. The syft run

- The argv matches the docker-compose.sbom.yml header and the pinned U3
  target: `-p <project>-sbom --env-file .env.example ... run --rm --pull never
  sbom docker-archive:/in/<name>.tar --scope all-layers -o
  spdx-json=/out/raw.spdx.json`. `$name` matches `^[a-z0-9._-]+$`. `.` and
  `..` cannot get past the `mkdir` of `$sbom_work/$name`. A leading `-` fails
  the checker's NAME_RE and argparse. Both fail closed.
- P3b inspected the real container. User=197610:197121 (the caller). Net=none,
  and it is attached to the `none` network only. RO root, CapDrop ALL, CapAdd
  none, no-new-privileges, not privileged, tmpfs /tmp. Env holds the 8 SYFT_*
  keys and TMPDIR=/out/tmp, with no HOME or XDG. Mounts: /in is a read-only
  bind of the tar dir, /out a read-write bind of the work dir. No socket.
- P3 ran the real thing (ke-gateway tar, 0600) and wrote only
  `/out/raw.spdx.json`. syft empties `/out/tmp` itself. The /in dir is
  unchanged. No containers, networks or volumes were left. The work dir is
  under a fresh `mktemp -d`, never under --out. bundle.sh copies nothing from
  it: only the checker's stdout reaches the bundle. `rm -rf` does not follow
  symlinks that syft might plant.
- The `/.cache/syft` warning is benign. `cache.dir` holds only downloaded
  content (u2/syft-v1.54.1-config.txt:351-356). Every remote lookup is off and
  there is no network, so nothing would be cached. syft falls back to memory
  and writes nothing outside /out. Do not add a writable cache dir. If the
  warning should go, XDG_CACHE_HOME=/tmp is what the I-2 rule allows.

## 2. The checker run

- Trust: `$app_ref` is the image being bundled. It is the same image the
  bundle ships and the one `engine.notices` already runs in (line 293). The
  checker adds no trust beyond that. `python` is /opt/venv/bin/python. `-I`
  drops PYTHONPATH, user site and the script dir, but site-packages `.pth`
  files still run (info I-1). The container has no network, a read-only root,
  CapDrop ALL, no-new-privileges, `--user` the caller, and only read-only
  mounts. Its only output is stdout.
- Injection: the output path is `$app/sboms/$name.spdx.json`, and `$name`
  comes from bundle.sh, not from SBOM content. The manifest pattern-checks
  every path. SBOM content is only parsed (`json.load`) and re-emitted
  (`json.dumps`, ensure_ascii), so control characters are escaped. No eval,
  no shell, no extraction. `config_digest` uses `extractfile` on the tar the
  bundle saved itself, which reads into memory. A symlinked member resolves
  inside the archive. --out must be empty and not a symlink (lines 77-83), so
  the redirect cannot follow a planted link.
- Size and depth: P2 used 200000-deep arrays. `json.load` raises
  RecursionError, which is uncaught: a traceback, then exit 1, then
  bundle.sh dies (fail closed). syft's fixed SPDX schema bounds the depth of
  its output whatever a tar holds. Size grows with the bundle's own images,
  so the worst case is build-host memory or time (info I-2).

## 3. The bundle.sh Windows-host fixes

- `hostpath()` quotes its argument. `cygpath -m --` accepts end-of-options
  (P4). A path with spaces, a semicolon or a command substitution comes back
  as one word and is not evaluated. On Linux it is a plain printf. Every use
  is double-quoted.
- `MSYS_NO_PATHCONV=1` is a per-command prefix on the two docker calls only,
  so it does not leak into the rest of the script.
- mkdir then `chmod 0700`: no TOCTOU, Linux included. Both dirs sit inside
  `mktemp -d`, which is 0700 even under umask 000 (P1). For the moment the
  child is 0777, no other uid can traverse the parent, and the random name
  rules out pre-creation. `mkdir -m` on Linux is not needed.
- Info I-3: `-v src:dst:ro` with an operator-chosen --out or TMPDIR that
  contains a colon could split the spec. The operator controls those paths,
  every mount is read-only, and a bad spec only makes docker refuse.
  Optional fix: `--mount type=bind,...`.

## 4. Carried from U2

- L-1 CLOSED. `top_level_problems` (tests/test_sbom_bundle.py:343-356) allows
  only `services` (scan: also `volumes`) and `x-*`. It refuses any service
  `extends` and any `include:`/`extends:` line, and covers both
  docker-compose.sbom.yml and docker-compose.scan.yml (line 580).
- L-2 CLOSED. `user: ${KE_SBOM_USER:?...}`. bundle.sh sets it to
  `id -u:id -g` and requires it to be numeric. Tests: user_problems and
  argv/env (line 938). P3b: User=197610:197121, and the output files are
  owned by the caller.
- I-1 CLOSED. `ref_re` starts `^[a-z0-9]`. A test at line 983 shows the
  refusal comes before any inspect.
- I-2 CLOSED. The compose env has no HOME or XDG (confirmed by P3b). The
  `hardening_problems` fallback allows only `/tmp` and `/tmp/...`, with no
  `/../`.

## 5. Licence evidence

- **M-1 medium (non-blocking; evidence is stale for ke-app).** The developer
  bundle (`u3/bundle-run.txt`, ke-u3bundle) used `ke-app:local`, which is
  image 510c1b59b838, created 2026-10-19 and also tagged
  `ke-app:bundle-98b6d27c1f73`. That is a build from before U0 and U1. Its
  SBOM (`sboms/ke-app.pkgs.tsv`) lists `pkg:pypi/pip@25.0.1` and
  `pkg:pypi/psycopg-binary@3.3.6`, and has no libpq5 deb. A probe of that
  image shows `psycopg_binary.libs` present and `dpkg-query: no packages
  found matching libpq5`. The ke-app section of `gpl-family-packages.md`
  (700 / 83 / 505) therefore describes an image that is no longer built. The
  stack images are digest-pinned, so their sections are fine. `ke-gateway`
  is `:local` too and may be stale for the same reason. verify full bundled
  the fresh `ke-app:wt-33a132fbfdd7` and passed, so the code is proven; only
  the committed evidence is wrong. Fix: re-run the evidence bundle with
  `KE_IMAGE_TAG` set to a fresh build of HEAD. Then regenerate `sboms/*.tsv`,
  the two JSONs and `gpl-family-packages.md` before ruling 5 is decided.
- Plausibility once fresh: ke-app's 505 NOASSERTION entries are 493 cargo
  crates (cargo-auditable data in compiled wheels, which carry no licence),
  6 with no purl, 4 pypi, 1 oci and 1 generic. The other images look right
  for their bases: neo4j 240 maven + 100 deb, postgres 145 deb + 4 golang,
  valkey and gateway apk.
- **L-1 low (carry to architect; pre-existing, now stamped into SBOMs).**
  bundle.sh does not prove that a first-party `ke-*` image was built from
  HEAD. The SBOM creator `Tool: knowledge-engine-bundle-<sha>` and the
  bundle.json git sha can then name a commit the image did not come from.
  That is how M-1 happened. The `ke:image-config` annotation stays true to
  the tar. Suggest: the build stamps `org.opencontainers.image.revision` and
  bundle.sh refuses on a mismatch, or bundle.sh only takes the tag that
  verify builds.
- Sensitive content: the SBOMs hold only in-image paths. The root package is
  the container path `/in/<name>.tar`. File entries are files owned by
  packages, with checksums (`etc/passwd` comes from the public bases).
  Creators and annotations carry the ref, arch, config digest and a 12-hex
  sha. No build host paths, profile paths, usernames, uids or SIDs. Safe to
  commit once regenerated (about 2.1 MB of JSON).

## 6. Evidence sweep (P5)

The diff (2138 lines) and all of u3/ were grepped for private keys,
AKIA/ASIA, gh*_/github_pat_, sk-, xox*, AIza, JWTs, URL userinfo,
C:/Users or /c/Users, S-1-5-21 and key=literal: 0 hits. Path hits are only
`/c/repos/Knowledge-engine/dist/...` (repo path, allowed) and `df` lines. The
KE_MODEL hits are skip reasons, with no values.

## Info

- I-1: site-packages `.pth` files run in the checker. Trust equals the
  shipped image.
- I-2: depth and size bombs fail closed with a traceback. The bounds are
  above.
- I-3: `-v` spec with an operator path containing a colon (see 3).
- I-4: two stderr lines print SBOM values without repr (`package {sid} has
  no name`, `{name} {dist.version}`). Terminal escapes are possible only
  from syft or ke-app metadata. Cosmetic.
- I-5: sbom_check.py:21 still says "(tester's reach target ...; the
  developer owns the real file)". This is stale; it goes to the reviewer.
