# U7e image and bundle tar sizes (developer, 2026-10-27; PSC-27 *Size*, form of u0/size.md)

Docker 29.5.2, Windows host, amd64. `docker image inspect --format '{{.Size}}'` (bytes; `docker images` shows it as 238MB) and `docker save -o <file> <image>` (what scripts/bundle.sh runs per image).

ke-app image (inspect Size):
- before (45411ae, base 34386ef0..., Python 3.12.15): 54,855,049 bytes = `ke-app:bundle-d8ffa2d451ef` (id d1016dd98ed8, created 2026-10-23, `python -V` = 3.12.15). No earlier-U7d ke-app image exists under a 45411ae tag, so this is the nearest built from the same inputs: `git log --oneline d8ffa2d..45411ae -- docker/app.Dockerfile pyproject.toml uv.lock harness_telemetry engine config` is empty and `git diff --stat d8ffa2d 45411ae -- ` the same six paths is empty (the six are every COPY source of docker/app.Dockerfile, l.28-36, plus the Dockerfile; the earlier pathspec missed harness_telemetry and config and named a non-existent `app`).
- after (U7e, base 6dd8b6da..., Python 3.12.16): 54,854,801 bytes = `ke-app:bundle-45411ae2ad3d` (id 2f5a27d04abf, my scripts/bundle.sh run; `python -V` = 3.12.16; same id as `ke-app:u7ewin-45411ae`). `ke-app:wt-33a132fbfdd7` (verify's build, same tree) is 54,854,802.
- delta: -248 bytes (0 MB at `docker images` precision).

Bundle tar (`images/ke-app.tar`):
- before: 54,872,576 bytes (52.3 MiB) = `docker save -o <scratch>/before-ke-app.tar ke-app:bundle-d8ffa2d451ef`.
- after: 54,872,064 bytes (52.3 MiB) = `<scratch>/bundle/b-amd64/images/ke-app.tar` written by `scripts/bundle.sh --out ... --arch amd64` (ls -l; also equal to a `docker save` of the after image, 54,872,064).
- delta: -512 bytes.

The base bump changes package versions only (openssl, ca-certificates, tzdata, CPython micro), so the size is flat. No image, network or container was removed or run for this except `docker run --rm ... python -V` on the two images.
