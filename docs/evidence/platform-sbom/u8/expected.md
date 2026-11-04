# platform-sbom U8: expected values before any real run (R8; orchestrator, 2026-10-28)

From the committed `docker/sources.lock.json` at HEAD 780d523 (lock sha256 `12eebc8cd09e5effc6934a1a3b67decc053cda923720dda07a8909a137fc761b`), by
`sbom_check.fetch_plan` / `sample_keys` over the lock, run read-only with `python3 -I`. A real run
(`bundle_fetch.sh`) must produce exactly these files; any difference is a lock or client defect, never a hand edit.

## sample, amd64: 7 keys, 25 files, 25 distinct sha256, 136571547 distinct bytes

| key | file | size | sha256 |
|---|---|---|---|
| `apk:alpine-baselayout@3.7.1-r8` | `APKBUILD` | 8427 | `c673459076838229d5ebef8f42586a46b4aa3d22e429f6b9ec008f5c6b3889d3` |
| `apk:alpine-baselayout@3.7.1-r8` | `20locale.sh` | 97 | `284a6ef56ab97a13a777c6b01ae14f2cc3d2b7a29c19e750e622e70cc3c73186` |
| `apk:alpine-baselayout@3.7.1-r8` | `aliases.conf` | 1545 | `3ebaba946f213670170c7d69949f690a3854553bd0b1560f1d980cba4c83a942` |
| `apk:alpine-baselayout@3.7.1-r8` | `alpine-baselayout.post-install` | 453 | `dd30b63bfbe4f7d8085f57840e15b84015b3518d6f282a3e0924f73a61000016` |
| `apk:alpine-baselayout@3.7.1-r8` | `alpine-baselayout.pre-install` | 56 | `28ecff91a36f438ca26bc8cc08d857863378aa94eab399a1f413e52501b86f85` |
| `apk:alpine-baselayout@3.7.1-r8` | `alpine-baselayout.pre-upgrade` | 944 | `3f35fa5402d397389f366e8934ba0f800a017a149f4281dc8c22762419e47e10` |
| `apk:alpine-baselayout@3.7.1-r8` | `blacklist.conf` | 2247 | `0e9ab848289bfb20b9b066d05c8b1383a7c92b97ff8072a50806054b5d3fd739` |
| `apk:alpine-baselayout@3.7.1-r8` | `color_prompt.sh.disabled` | 447 | `ba24425c6864a5d17fa0fdaf914c4d21419e47c4d62080c33830af059fe46617` |
| `apk:alpine-baselayout@3.7.1-r8` | `crontab` | 283 | `575d810a9fae5f2f0671c9b2c0ce973e46c7207fbe5cb8d1b0d1836a6a0470e3` |
| `apk:alpine-baselayout@3.7.1-r8` | `group` | 510 | `6fb6ab5a5526e6f4896b70c7e3c350fd475158a1f0d7b5fc0f3f9bd57f1c3be8` |
| `apk:alpine-baselayout@3.7.1-r8` | `i386.conf` | 122 | `6c46c4cbfb8b7594f19eb94801a350fa2221ae9ac5239a8819d15555caa76ae8` |
| `apk:alpine-baselayout@3.7.1-r8` | `inittab` | 570 | `7326d8ad56bf5fea63b1ca516a747ff6e6723e25ae84a93c31620b03de6c001d` |
| `apk:alpine-baselayout@3.7.1-r8` | `passwd` | 702 | `31a94f06f17bc3b9085fccab1d0fa6ee9e79c4a1e4d91f617fa5de95863be015` |
| `apk:alpine-baselayout@3.7.1-r8` | `profile` | 547 | `87e8643d3ce156de0c09370d4d39446f30bd00d264bea248abc191c4d7b9df3e` |
| `apk:alpine-baselayout@3.7.1-r8` | `usr_merge_nag.sh` | 699 | `3add5845c64bec8ef8dfe27087401a83816ea7cdda20e77826d2ba5516c7434c` |
| `apk:alpine-baselayout@3.7.1-r8` | `protocols-6.4` | 3144 | `4959498abbadaa1e50894a266f8d0d94500101cfe5b5f09dcad82e9d5bdfab46` |
| `apk:alpine-baselayout@3.7.1-r8` | `services-6.4` | 12813 | `f6183055fd949f9c53d49ee620f85d0150123ea691d25ed1bba0c641b4ee2f48` |
| `deb:hostname@3.23+nmu1` | `hostname_3.23+nmu1.dsc` | 1281 | `56f2189eaeee638e86d29a05356e7001632e33b2132a41a4634a9ff839264ea6` |
| `deb:hostname@3.23+nmu1` | `hostname_3.23+nmu1.tar.xz` | 12876 | `f3fb39f30b00ba7dba2cec013195d7e1bb215f241153208ccd52da3eedfe7a7d` |
| `maven:javax.xml.bind:jaxb-api@2.2.12` | `jaxb-api-2.2.12-sources.jar` | 245023 | `fd104e7b20b6dbcd1bb27803aaca963a8393ad9b3e39eb8a5ba1b4da1462182e` |
| `neo4j:neo4j@5.26.32` | `5.26.32.tar.gz` | 20907800 | `182ae2e5c3807bc3d7a09770dbf450d2e8667080bde93b3b6c829125db0f91e3` |
| `pgdg:postgresql-common@293.pgdg12+1` | `postgresql-common_293.pgdg12+1.dsc` | 1538 | `fc1b229024670e6d0cf1c40f3987bf1509aecf146791a6e22966fbf764c391da` |
| `pgdg:postgresql-common@293.pgdg12+1` | `postgresql-common_293.pgdg12+1.tar.xz` | 219688 | `7a12dca9e636d56b72f45a00c52fb8cf054c3bf9aba8dc74bcca5fb6be17b07f` |
| `pypi:autocommand@2.2.2` | `autocommand-2.2.2.tar.gz` | 22894 | `878de9423c5596491167225c2a455043c3130fb5b7286ac83443d45e74955f34` |
| `temurin:jdk-21.0.12.1+1` | `OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz` | 115126841 | `573057d03584ae793fb7ec9a14c76d826d9187a53efeefd99da47403a5308234` |

## full, amd64: 184 keys, 879 files, 718 distinct sha256, 1181039856 distinct bytes

*2026-11-02, Q83 (a) re-lock (tester):* recomputed with `sbom_check.fetch_plan` over the regenerated lock (`relock-20261102/fixture-derivation.txt`). One key added, `deb:cyrus-sasl2@2.1.28+dfsg-10+deb12u1` (ke-app rebuilt; 3 files, 2 new sha256, +103270 distinct bytes; its orig.tar.xz is shared with the -10 key); nothing removed; the sample sets are unchanged. Before the re-lock (the lock at HEAD bc5e65e, unchanged since 780d523): 183 keys, 876 files, 716 distinct sha256, 1180936586 distinct bytes.

Keys: `apk:alpine-baselayout@3.7.1-r8`, `apk:alpine-baselayout@3.7.2-r1`, `apk:apk-tools@3.0.3-r1`, `apk:apk-tools@3.0.8-r0`, `apk:busybox@1.37.0-r30`, `apk:busybox@1.37.0-r31`, `apk:gcc@15.2.0-r2`, `apk:gcc@15.2.0-r5`, `apk:geoip@1.6.12-r6`, `apk:gettext@0.24.1-r1`, `apk:libcap-ng@0.8.5-r2`, `apk:libidn2@2.3.8-r0`, `apk:libunistring@1.4.1-r0`, `apk:musl@1.2.5-r21`, `apk:musl@1.2.6-r2`, `apk:pax-utils@1.3.8-r2`, `apk:pax-utils@1.3.9-r1`, `apk:util-linux@2.42.3-r1`, `apk:xz@5.8.2-r0`, `deb:acl@2.3.1-3`, `deb:acl@2.3.2-2`, `deb:adduser@3.134`, `deb:apt@2.6.1`, `deb:apt@3.0.3`, `deb:attr@1:2.5.1-4`, `deb:attr@1:2.5.2-3`, `deb:audit@1:3.0.9-1`, `deb:audit@1:4.0.2-2+deb13u1`, `deb:base-files@12.4+deb12u15`, `deb:base-files@13.8+deb13u7`, `deb:base-passwd@3.6.1`, `deb:base-passwd@3.6.7`, `deb:bash@5.2.15-2`, `deb:bash@5.2.37-2`, `deb:bzip2@1.0.8-5`, `deb:bzip2@1.0.8-6`, `deb:ca-certificates@20250419`, `deb:ca-certificates@20250419~deb12u2`, `deb:cdebconf@0.270`, `deb:cdebconf@0.280`, `deb:coreutils@9.1-1`, `deb:coreutils@9.7-3`, `deb:cyrus-sasl2@2.1.28+dfsg-10`, `deb:cyrus-sasl2@2.1.28+dfsg-10+deb12u1`, `deb:dash@0.5.12-12`, `deb:dash@0.5.12-2`, `deb:db5.3@5.3.28+dfsg2-1`, `deb:db5.3@5.3.28+dfsg2-9`, `deb:debian-archive-keyring@2023.3+deb12u2`, `deb:debian-archive-keyring@2025.1`, `deb:debianutils@5.23.2`, `deb:debianutils@5.7-0.5~deb12u1`, `deb:diffutils@1:3.10-4`, `deb:diffutils@1:3.8-4`, `deb:dpkg@1.21.23`, `deb:dpkg@1.22.22`, `deb:e2fsprogs@1.47.0-2`, `deb:e2fsprogs@1.47.2-3`, `deb:findutils@4.10.0-3`, `deb:findutils@4.9.0-4`, `deb:gcc-12@12.2.0-14+deb12u1`, `deb:gcc-14@14.2.0-19`, `deb:gdbm@1.23-3`, `deb:glibc@2.36-9+deb12u14`, `deb:glibc@2.41-12+deb13u4`, `deb:gmp@2:6.2.1+dfsg1-1.1`, `deb:gmp@2:6.3.0+dfsg-3`, `deb:gnupg2@2.2.40-1.1+deb12u2`, `deb:gnutls28@3.7.9-2+deb12u7`, `deb:gnutls28@3.8.9-3+deb13u4`, `deb:grep@3.11-4`, `deb:grep@3.8-5`, `deb:gzip@1.12-1`, `deb:gzip@1.13-1+deb13u1`, `deb:hostname@3.23+nmu1`, `deb:hostname@3.25`, `deb:icu@72.1-3+deb12u1`, `deb:init-system-helpers@1.65.2+deb12u1`, `deb:init-system-helpers@1.69~deb13u1`, `deb:jq@1.7.1-6+deb13u4`, `deb:keyutils@1.6.3-2`, `deb:keyutils@1.6.3-6`, `deb:krb5@1.20.1-2+deb12u5`, `deb:krb5@1.21.3-5+deb13u1`, `deb:less@590-2.1~deb12u2`, `deb:libassuan@2.5.5-5`, `deb:libcap-ng@0.8.3-1`, `deb:libcap-ng@0.8.5-4`, `deb:libcap2@1:2.66-4+deb12u3`, `deb:libcap2@1:2.75-10+deb13u1`, `deb:libffi@3.4.4-1`, `deb:libffi@3.4.8-2`, `deb:libgcrypt20@1.10.1-3+deb12u1`, `deb:libgpg-error@1.46-1`, `deb:libidn2@2.3.3-1`, `deb:libidn2@2.3.8-2`, `deb:libjson-perl@4.10000-1`, `deb:libksba@1.6.3-2`, `deb:libnsl@1.3.0-2`, `deb:libnsl@1.3.0-3`, `deb:libonig@6.9.9-1`, `deb:libseccomp@2.5.4-1+deb12u1`, `deb:libseccomp@2.6.0-2`, `deb:libselinux@3.4-1`, `deb:libselinux@3.8.1-1`, `deb:libsemanage@3.4-1`, `deb:libsemanage@3.8.1-1`, `deb:libsepol@3.4-2.1`, `deb:libsepol@3.8.1-1`, `deb:libtasn1-6@4.19.0-2+deb12u1`, `deb:libtasn1-6@4.20.0-2+deb13u1`, `deb:libtirpc@1.3.3+ds-1`, `deb:libtirpc@1.3.6+ds-1`, `deb:libunistring@1.0-2`, `deb:libunistring@1.3-2`, `deb:libxcrypt@1:4.4.33-2`, `deb:libxcrypt@1:4.4.38-1`, `deb:libxslt@1.1.35-1+deb12u4`, `deb:libzstd@1.5.4+dfsg2-5`, `deb:libzstd@1.5.7+dfsg-1`, `deb:linux@6.12.113-1`, `deb:lz4@1.10.0-4`, `deb:lz4@1.9.4-1`, `deb:mawk@1.3.4.20200120-3.1`, `deb:mawk@1.3.4.20250131-1`, `deb:netbase@6.4`, `deb:netbase@6.5`, `deb:nettle@3.10.1-1`, `deb:nettle@3.8.1-2`, `deb:npth@1.6-3`, `deb:openldap@2.5.13+dfsg-5`, `deb:openssl@3.0.22-1~deb12u1`, `deb:openssl@3.0.22-1~deb12u2`, `deb:openssl@3.5.7-1~deb13u3`, `deb:p11-kit@0.24.1-2`, `deb:p11-kit@0.25.5-3`, `deb:pam@1.5.2-6+deb12u2`, `deb:pam@1.7.0-5`, `deb:perl@5.36.0-7+deb12u3`, `deb:perl@5.36.0-7+deb12u4`, `deb:perl@5.40.1-6+deb13u1`, `deb:pinentry@1.2.1-1`, `deb:postgresql-15@15.19-0+deb12u1`, `deb:procps@2:4.0.4-9`, `deb:python3.13@3.13.5-2+deb13u5`, `deb:readline@8.2-1.3`, `deb:readline@8.2-6`, `deb:rpcsvc-proto@1.4.3-1`, `deb:rust-sequoia-sqv@1.3.0-3`, `deb:sed@4.9-1+deb12u1`, `deb:sed@4.9-2+deb13u1`, `deb:sensible-utils@0.0.17+nmu1`, `deb:shadow@1:4.13+dfsg1-1+deb12u2`, `deb:shadow@1:4.17.4-2`, `deb:sqlite3@3.40.1-2+deb12u2`, `deb:sqlite3@3.46.1-7+deb13u2`, `deb:systemd@252.39-1~deb12u2`, `deb:systemd@257.13-1~deb13u1`, `deb:sysvinit@3.06-4`, `deb:sysvinit@3.14-4`, `deb:tar@1.34+dfsg-1.2+deb12u1`, `deb:tar@1.35+dfsg-3.1`, `deb:ucf@3.0043+nmu1+deb12u1`, `deb:usrmerge@37~deb12u1`, `deb:util-linux@2.38.1-5+deb12u3`, `deb:util-linux@2.41.5-0+deb13u1`, `deb:wget@1.25.0-2`, `deb:xxhash@0.8.1-1`, `deb:xxhash@0.8.3-2`, `deb:xz-utils@5.4.1-1+deb12u2`, `deb:xz-utils@5.8.1-1+deb13u1`, `deb:xz-utils@5.8.1-1+deb13u2`, `deb:z3@4.8.12-3.1`, `maven:javax.xml.bind:jaxb-api@2.2.12`, `neo4j:neo4j@5.26.32`, `pgdg:postgresql-16@16.15-1.pgdg12+2`, `pgdg:postgresql-18@18.6-1.pgdg12+2`, `pgdg:postgresql-common@293.pgdg12+1`, `pypi:autocommand@2.2.2`, `pypi:ldap3@2.9.1`, `pypi:pandas@2.3.3`, `pypi:psycopg-c@3.3.6`, `pypi:psycopg@3.3.6`, `temurin:jdk-21.0.12.1+1`

## sample, arm64: 0 keys, 0 files, 0 distinct sha256, 0 distinct bytes

| key | file | size | sha256 |
|---|---|---|---|

## full, arm64: 0 keys, 0 files, 0 distinct sha256, 0 distinct bytes

Keys: 

## U9c amendment (A81 option 3; orchestrator, 2026-10-30, before any real run)
The "sample, amd64" table above is superseded for the apk row: `bundle_fetch.sh --set sample` fetches only the sample key's distfiles.alpinelinux.org files (`protocols-6.4` 3144 B, `services-6.4` 12813 B; sha256 as in the table). Sample totals become 7 keys, 10 files, 10 distinct sha256, 136553898 distinct bytes. The 15 GitLab rows of the table are fetched only by `--set full`. Full totals unchanged. See `u9/expected.md` "U9c".
