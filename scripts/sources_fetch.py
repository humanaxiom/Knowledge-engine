"""The source fetch client (platform-sbom U8a; PSC-15, PSC-23 "U8 precision"
U8-2..U8-6; design-notes "N4 amendment, U8" items 1, 2, 4, 5, 6 and 11).

Standard library only, run as `python3 -I`. It fetches the files the committed
source lock pins for one arch and set, checks each against the lock before
anything reads it, and leaves them flat in `--out` as `<sha256>`, with
`fetch.json` (the completion record, A76) written last:

  sources_fetch.py --lock LOCK --policy POLICY --out DIR
                   --arch amd64|arm64 --set sample|full

Exit 0: complete. 1: a failure (one `bundle_fetch: FAIL (stage <stage>: ...;
no retry)` line, never a traceback). 2: a bad argument (nothing requested).

It holds no URL or host literal of its own and reads nothing from the process's settings: the URLs are the
lock's, the hosts are the policy's `hosts`, and the only network hook is
`sources_resolve.OPENER`, reached as `R.OPENER`. Its two siblings are loaded
by path from this file's directory (`-I` puts no script directory on the
module path): `R` is sources_resolve.py (opener, hop rules, `download`,
parsers) and `S` is sbom_check.py (lock rules and the plan).

Order: the lock's entry rules (zero requests on a problem), the plan, the
disk check, then per file one attempt (Q61), size, sha256 and the upstream
digest against the lock, and per entry the `.dsc` or APKBUILD name check (the APKBUILD check in `full`
only, A81: the sample's apk files are the distfiles ones, and a line says
the check was skipped).
A failing file is deleted; nothing unverified is left in `--out`.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import os
import re
import shutil
import sys
import time
from typing import Any
from urllib.parse import urlsplit


def _sibling(name: str) -> Any:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py")
    spec = importlib.util.spec_from_file_location("ke_fetch_" + name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name}.py beside sources_fetch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _sibling("sources_resolve")
S = _sibling("sbom_check")

CLOCK = time.monotonic
RUN_DEADLINE = {"sample": 300, "full": 10800}  # seconds, checked before each request
BINARY = getattr(os, "O_BINARY", 0)


def DISK_FREE(out: str) -> Any:  # noqa: N802 - a test hook, named like the other module hooks
    return shutil.disk_usage(out)


class Fail(Exception):
    """A fail-closed stop: `stage` and the text of its FAIL line."""

    def __init__(self, stage: str, why: str):
        super().__init__(why)
        self.stage = stage
        self.why = why


def _safe(text: Any) -> str:
    """A printable line: control characters escaped and every query dropped
    (a signed redirect URL is never printed, U8-2)."""
    return re.sub(r"\?(?!<query omitted>)\S*", "?<query omitted>", R._clean(text))


def _fail_line(stage: str, why: str) -> str:
    return f"bundle_fetch: FAIL (stage {stage}: {_safe(why)}; no retry)"


def _fetch_fail(url: str, name: str, why: str) -> Fail:
    """`<host>: <file name>: <why>`; a leading host or name already in the
    resolver's text is not repeated."""
    host = (urlsplit(url).hostname or "").lower()
    for prefix in (host + ": ", name + ": "):
        if why.startswith(prefix):
            why = why[len(prefix):]
            break
    return Fail("fetch", f"{host}: {name}: {why}")


def _parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="sources_fetch.py", allow_abbrev=False)
    for flag in ("--lock", "--policy", "--out"):
        ap.add_argument(flag, required=True)
    ap.add_argument("--arch", required=True, choices=["amd64", "arm64"])
    ap.add_argument("--set", required=True, choices=sorted(RUN_DEADLINE), dest="which")
    return ap.parse_args(argv)


def _read(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _place(out: str, url: str, f: dict[str, Any], allow: set[str], hops: list[str]) -> None:
    """One attempt at `url`, written to a `.part` file, checked against the
    lock (size, sha256, upstream digest) and only then renamed to its
    sha256 name. Any failure removes the `.part`."""
    sha, name = f["sha256"], f["name"]
    part = os.path.join(out, f".{sha}.part")
    alg = f["upstream"]["alg"]
    try:
        fd = os.open(part, os.O_CREAT | os.O_EXCL | os.O_WRONLY | BINARY, 0o644)
    except OSError as exc:  # a .part this run did not create is never written or removed
        raise _fetch_fail(url, name, f"write failed: {type(exc).__name__}") from None
    try:
        with os.fdopen(fd, "wb") as fh:
            try:
                digests, size = R.download(url, allow, fh, f["size"], (alg,), hops)
            except R.ResolveError as exc:
                raise _fetch_fail(url, name, str(exc)) from None
            fh.flush()
            os.fsync(fh.fileno())
        if size != f["size"]:
            raise _fetch_fail(url, name, f"size mismatch: got {size}, lock says {f['size']}")
        if digests["sha256"] != sha:
            raise _fetch_fail(url, name, f"sha256 mismatch: got {digests['sha256']}, lock says {sha}")
        if digests[alg] != f["upstream"]["value"]:
            raise _fetch_fail(url, name, f"{alg} mismatch: got {digests[alg]}, "
                                         f"{f['upstream']['from']} says {f['upstream']['value']}")
        os.replace(part, os.path.join(out, sha))
    except OSError as exc:
        raise _fetch_fail(url, name, f"write failed: {type(exc).__name__}") from None
    finally:
        if os.path.lexists(part):
            os.unlink(part)


def _text(out: str, f: dict[str, Any]) -> str:
    """The verified file as UTF-8 text, at most one MiB; never sourced."""
    if f["size"] > R.TEXT_LIMIT:
        raise _fetch_fail(f["url"], f["name"], "over 1 MiB, not checked")
    with open(os.path.join(out, f["sha256"]), "rb") as fh:
        data = fh.read()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise _fetch_fail(f["url"], f["name"], "not UTF-8 text") from None


def _name_check(out: str, key: str, entry: dict[str, Any], which: str) -> None:
    """Item 5: the `.dsc` (deb and pgdg) or the APKBUILD (apk) must list
    exactly the entry's other files. Read from the verified file only. A81:
    for an apk key in the `sample` set the check is skipped and a line says
    so; the condition reads only `which` and the kind, never the plan."""
    kind = key.split(":", 1)[0]
    if kind == "apk" and which == "sample":
        print(f"bundle_fetch: apk {key}: APKBUILD name check skipped (sample set, A81)", flush=True)
        return
    files = entry["files"]
    name, _, ver = key.split(":", 1)[1].rpartition("@")
    if kind in ("deb", "pgdg"):
        target = next(f for f in files if f["name"].endswith(".dsc"))
    elif kind == "apk":
        target = next(f for f in files if f["name"] == "APKBUILD")
    else:
        return
    try:
        if kind == "apk":
            commit = entry["commit"]
            sums = set(R.parse_apkbuild(_text(out, target), commit, ver, name))
            if sums != {(f["name"], f["upstream"]["value"]) for f in files if f["upstream"]["alg"] == "sha512"}:
                raise _fetch_fail(target["url"], target["name"],
                                  f"APKBUILD at {commit}: sha512sums names differ from the lock entry")
        else:
            fields = R.parse_dsc(_text(out, target), target["name"])
            listed = set(R.dsc_listing(fields, target["name"], name, ver))
            if listed != {(f["name"], f["size"], f["sha256"]) for f in files if f is not target}:
                raise _fetch_fail(target["url"], target["name"], "Files/Checksums-Sha256 differ from the lock entry")
    except R.ResolveError as exc:
        raise _fetch_fail(target["url"], target["name"], str(exc)) from None


def _write_record(out: str, which: str, arch: str, lock_text: str, plan: list[tuple[str, dict[str, Any]]]) -> None:
    comps: dict[str, list[dict[str, Any]]] = {}
    for key, f in plan:
        comps.setdefault(key, []).append({"name": f["name"], "sha256": f["sha256"], "size": f["size"]})
    record = {"format": 1, "set": which, "arch": arch, "components": comps,
              "lock_sha256": hashlib.sha256(lock_text.encode("utf-8")).hexdigest()}
    part = os.path.join(out, ".fetch.json.part")
    try:
        fd = os.open(part, os.O_CREAT | os.O_EXCL | os.O_WRONLY | BINARY, 0o644)
    except OSError as exc:  # not ours: left alone
        raise Fail("fetch", f"fetch.json: write failed: {type(exc).__name__}") from None
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(S.lock_text(record).encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(part, os.path.join(out, "fetch.json"))
    except OSError as exc:
        raise Fail("fetch", f"fetch.json: write failed: {type(exc).__name__}") from None
    finally:
        if os.path.lexists(part):
            os.unlink(part)


def _run(args: argparse.Namespace, stage: list[str]) -> None:
    started = CLOCK()
    if os.path.lexists(os.path.join(args.out, "fetch.json")):
        raise Fail("lock", "--out already holds fetch.json")
    lock_text = _read(args.lock)
    with open(args.policy, encoding="utf-8") as fh:
        policy = json.load(fh)
    problems = S.lock_entry_problems(lock_text, policy)
    if problems:
        for line in problems[:20]:
            print(f"bundle_fetch: lock problem: {_safe(line)}", file=sys.stderr)
        raise Fail("lock", problems[0])
    allow = {h.lower() for h in policy["hosts"]}
    lock = json.loads(lock_text)
    try:
        plan = S.fetch_plan(lock, args.arch, args.which)
    except ValueError as exc:
        raise Fail("lock", str(exc)) from None
    if not plan:
        raise Fail("lock", f"the lock lists no entry for {args.arch}")

    stage[0] = "disk"
    sizes = {f["sha256"]: f["size"] for _, f in plan}
    need = sum(sizes.values())
    free = int(DISK_FREE(args.out).free)
    if need > free:
        raise Fail("disk", f"need {need} bytes free in --out, found {free}")

    stage[0] = "fetch"
    held: dict[str, tuple[str, str, int]] = {}
    fetched = 0
    nbytes = 0
    for key, group in itertools.groupby(plan, key=lambda kf: kf[0]):
        for _, f in group:
            sha, name, size = f["sha256"], f["name"], f["size"]
            if sha in held:
                k0, n0, size0 = held[sha]
                print(f"bundle_fetch: held {key} {_safe(name)} sha256={sha} size={size0} (fetched for {k0} {_safe(n0)})",
                      flush=True)
                continue
            if CLOCK() - started > RUN_DEADLINE[args.which]:
                raise _fetch_fail(f["url"], name, f"run deadline {RUN_DEADLINE[args.which]} s passed")
            hops: list[str] = []
            _place(args.out, f["url"], f, allow, hops)
            held[sha] = (key, name, size)
            fetched += 1
            nbytes += size
            print(f"bundle_fetch: ok {key} {_safe(name)} sha256={sha} size={size} hops={','.join(hops)}", flush=True)
        _name_check(args.out, key, lock["components"][key], args.which)

    _write_record(args.out, args.which, args.arch, lock_text, plan)
    print(f"bundle_fetch: fetched {fetched} files, {nbytes} bytes, {len({k for k, _ in plan})} components "
          f"({args.which}, {args.arch}) in {CLOCK() - started:.1f} s", flush=True)


def main(argv: list[str]) -> int:
    try:
        args = _parse(argv)
    except SystemExit:
        return 2
    stage = ["lock"]
    try:
        _run(args, stage)
    except Fail as exc:
        print(_fail_line(exc.stage, exc.why), file=sys.stderr, flush=True)
        return 1
    except Exception as exc:  # noqa: BLE001 - fail closed with one line, never a traceback
        print(_fail_line(stage[0], f"{type(exc).__name__}: {exc}"), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
