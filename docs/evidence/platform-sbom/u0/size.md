# U0 image sizes (developer, 2026-10-22)

`docker images` (decimal MB), ke-app image:
- before (platform-supply-chain, psycopg-binary wheel): 265 MB (`ke-app:bundle-d6b70355c452`, built from main d6b7035)
- after (psycopg-c on Debian libpq5 15.19-0+deb12u1): 259 MB (`ke-app:bundle-737750d06839`, from `verify.sh full`)
- delta: -6 MB.
- ke-gates: 1.46 GB before, 1.79 GB after (+gcc, libc6-dev, libpq-dev; not shipped).
- bundle tar size: `verify.sh full` does not print it (grep of green-verify-full.txt found no size line).

apt added only four packages to the runtime stage: libpq5 15.19-0+deb12u1, libldap-2.5-0 2.5.13+dfsg-5,
libsasl2-2 and libsasl2-modules-db 2.1.28+dfsg-10. The krb5 libraries (libgssapi-krb5-2, libk5crypto3,
libkrb5-3, libkrb5support0 1.20.1-2+deb12u5) and libkeyutils1 1.6.3-2 were already in the base image
(corrected per `u0/security.md` I-5; `u0/security-image-inspect.txt`).
ldd of psycopg_c/pq*.so in the image: `libpq.so.5 => /lib/x86_64-linux-gnu/libpq.so.5` (the /lib alias).

## Bundle tar size (B2, developer, 2026-10-23)
Method: `docker save -o <file> <image>` on the ke-app image, which is what `scripts/bundle.sh` runs per image (line 281, after `docker tag`); the tar is the one `images/ke-app.tar` would be. Docker 29.5.2 on the Windows host.
- before: 60,414,464 bytes (57.6 MiB) = `ke-app:sizecheck-737750d`, built from a scratch worktree at 737750d (psycopg-binary; image id b07007fb2ffe, 265 MB in `docker images`; psycopg_binary importable). Tag and worktree removed after.
- after: 58,818,048 bytes (56.1 MiB) = `ke-app:bundle-737750d06839` (psycopg-c on libpq5, image id 42f3710d5537, 259 MB).
- delta: -1,596,416 bytes (-2.6%).
