"""platform-offline: the pinned Docker CLI and compose plugin in the gates image.

Criteria: docs/requirements.md PS-3.10 (test names are the PS-3.10 names).
Design: docs/architecture.md §2.2 *Lint* (static release binaries, version
pinned and SHA-256 checked, compose >= 2.24; the gate services never get a
socket or a DOCKER_HOST) and §2.6 item 8. Hash provenance: ruling Q48
(docs/handoffs/archive/platform-offline-part1.md): a hash recorded from an
HTTPS download.docker.com fetch is acceptable for the static CLI, which has
no upstream checksum; the compose plugin pin must equal its upstream
`.sha256`. Provenance itself is checked by security (second fetch), not here:
the gates have no network.

The Dockerfile contract follows the pwsh tarball pin already in
docker/gates.Dockerfile:

    ARG DOCKER_VERSION=X.Y.Z               (or DOCKER_CLI_VERSION)
    ARG DOCKER_SHA256_X64=<64 hex>         (X64 | AMD64 | X86_64)
    ARG DOCKER_SHA256_ARM64=<64 hex>       (ARM64 | AARCH64)
    ARG COMPOSE_VERSION=X.Y.Z              (or DOCKER_COMPOSE_VERSION, COMPOSE_PLUGIN_VERSION)
    ARG COMPOSE_SHA256_X64=<64 hex> / COMPOSE_SHA256_ARM64=<64 hex>
    RUN set -eu; case "$(dpkg --print-architecture)" in
          amd64) ... "$DOCKER_SHA256_X64" ... ;;  arm64) ... "$DOCKER_SHA256_ARM64" ... ;;
        esac; curl -o /tmp/... https://download.docker.com/linux/static/stable/<arch>/docker-${DOCKER_VERSION}.tgz;
        echo "$sha  /tmp/..." | sha256sum -c -; tar ...

Static and fast: nothing here builds the image or runs docker. The real
hashes are proven by the image build in `verify.sh full`, the binaries by
`ci/deployable-offline`, and a wrong hash failing the build by the
reviewer's mutation check (PS-3.10 *Mismatch fails the build*).

platform-supply-chain, PS-3.7 (security L-8, review N-7): PSC-11 (pwsh
telemetry and update check off by an ENV before the first RUN that starts
pwsh) and PSC-10 (PSScriptAnalyzer fetched over HTTPS and checked by hash
before it is unpacked; no gallery install). Design: architecture ADR-KE-013
amendment 1, D7, with the orchestrator ruling of 2026-10-21
(docs/handoffs/platform-supply-chain.md): the pin is the gallery's SHA-512,
`ARG PSSCRIPTANALYZER_SHA512`, checked with `sha512sum -c`.
"""

from __future__ import annotations

import re
import shlex
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from tests import compose_support as cs
from tests.engine_support import ROOT
from tests.test_gate_least_privilege import _logical_lines

GATES_DOCKERFILE = ROOT / "docker" / "gates.Dockerfile"
GATE_SERVICES = cs.ONE_SHOT_SERVICES  # ("gates", "gates-it")

HEX64 = re.compile(r"^[0-9a-f]{64}$")
FIXED_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
AMD64_SUFFIX = r"(?:X64|AMD64|X86_64)"
ARM64_SUFFIX = r"(?:ARM64|AARCH64)"
# Variables that point a Docker client at a daemon. Only `offline-client`
# may set them (it points at `dind`); the gate services never do (§2.2).
DAEMON_ENV = ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")
SOCKET_TEXT = (*cs.SOCKET_MARKERS, "docker.sock")


@dataclass(frozen=True)
class Component:
    label: str
    version_arg: str
    sha_prefix: str
    url: str  # regex for the expanded download URL; {v} is the escaped version
    unpack: str  # regex for the first step that unpacks or installs the download


DOCKER_CLI = Component(
    label="Docker CLI",
    version_arg=r"^DOCKER(?:_CLI)?_VERSION$",
    sha_prefix=r"DOCKER(?:_CLI)?_SHA256_",
    url=r"https://download\.docker\.com/linux/static/stable/[^\s\"'/]+/docker-{v}\.tgz",
    unpack=r"\btar\b|\binstall\b|\bmv\b|\bcp\b|\bln\b|\bchmod\b",
)
COMPOSE_PLUGIN = Component(
    label="compose plugin",
    version_arg=r"^(?:DOCKER_)?COMPOSE(?:_PLUGIN)?_VERSION$",
    sha_prefix=r"(?:DOCKER_)?COMPOSE(?:_PLUGIN)?_SHA256_",
    url=r"https://github\.com/docker/compose/releases/download/v{v}/docker-compose-linux-[^\s\"'/]+",
    unpack=r"\btar\b|\binstall\b|\bmv\b|\bcp\b|\bln\b|\bchmod\b",
)


# --- Dockerfile helpers --------------------------------------------------------

def _args(lines: list[str]) -> dict[str, str]:
    """ARG name -> default value (quotes stripped); ARGs without a default map to ''."""
    out: dict[str, str] = {}
    for ln in lines:
        m = re.match(r"^ARG\s+([A-Za-z_][A-Za-z0-9_]*)(?:=(\S*))?\s*$", ln, re.IGNORECASE)
        if m:
            out[m.group(1)] = (m.group(2) or "").strip("\"'")
    return out


def _expand(text: str, args: dict[str, str]) -> str:
    """Substitute ${NAME} and $NAME for every ARG with a default."""
    for name, value in sorted(args.items(), key=lambda kv: -len(kv[0])):
        if not value:
            continue
        text = text.replace("${" + name + "}", value)
        text = re.sub(rf"\${re.escape(name)}(?![A-Za-z0-9_])", lambda _m, v=value: v, text)
    return text


def _one_arg(args: dict[str, str], pattern: str, what: str) -> tuple[str, str]:
    names = [n for n in args if re.match(pattern, n)]
    if len(names) != 1:
        raise AssertionError(
            f"gates.Dockerfile must declare exactly one ARG for the {what} matching /{pattern}/ "
            f"(found {names}); PS-3.10, the same control as the pwsh tarball")
    return names[0], args[names[0]]


def _runs(lines: list[str]) -> list[str]:
    return [ln for ln in lines if re.match(r"^RUN\s", ln, re.IGNORECASE)]


def _segments(run: str) -> list[tuple[str, str]]:
    """(command, separator that follows it). Pipelines stay one segment."""
    parts = re.split(r"(&&|\|\||;;|;)", run)
    out: list[tuple[str, str]] = []
    for i in range(0, len(parts), 2):
        cmd = parts[i].strip()
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        if cmd:
            out.append((cmd, sep))
        elif out and sep:
            out[-1] = (out[-1][0], out[-1][1] or sep)
    return out


def _branch(run: str, arch: str) -> str | None:
    """The body of the shell `case` branch for an architecture."""
    label = r"(?:amd64|x86_64)" if arch == "amd64" else r"(?:arm64|aarch64)"
    m = re.search(rf"(?<![\w.-]){label}(?:\|[\w.-]+)*\)(.*?);;", run, re.S)
    return m.group(1) if m else None


def _refs(text: str, name: str) -> bool:
    return re.search(rf"\$\{{?{re.escape(name)}(?![A-Za-z0-9_])", text) is not None


def _is_sha_check(cmd: str) -> bool:
    return re.search(r"\bsha256sum\b[^|]*?(?:\s-c\b|\s--check\b|\s-[a-z]*c[a-z]*\b)", cmd) is not None


def _assert_pinned(t: unittest.TestCase, comp: Component) -> None:
    lines = _logical_lines(GATES_DOCKERFILE)
    args = _args(lines)

    version_name, version = _one_arg(args, comp.version_arg, f"{comp.label} version")
    with t.subTest(check=f"{comp.label} version is fixed"):
        t.assertRegex(version, FIXED_VERSION,
                      f"ARG {version_name}={version!r}: a fixed X.Y.Z version, no `latest`, no range")

    shas: dict[str, tuple[str, str]] = {}
    for arch, suffix in (("amd64", AMD64_SUFFIX), ("arm64", ARM64_SUFFIX)):
        shas[arch] = _one_arg(args, rf"^{comp.sha_prefix}{suffix}$", f"{comp.label} {arch} SHA-256")
        with t.subTest(check=f"{comp.label} {arch} hash is 64 hex"):
            t.assertRegex(shas[arch][1], HEX64,
                          f"ARG {shas[arch][0]} must be a committed 64-hex SHA-256 "
                          "(both arches: the gates image is built on aria-gb10 too)")
    with t.subTest(check=f"{comp.label} amd64 and arm64 hashes differ"):
        t.assertNotEqual(shas["amd64"][1], shas["arm64"][1], "one hash pinned for two different files")

    url = re.compile(comp.url.format(v=re.escape(version)))
    hits = [r for r in _runs(lines) if url.search(_expand(r, args))]
    with t.subTest(check=f"{comp.label} download URL contains the pinned version"):
        t.assertEqual(len(hits), 1,
                      f"expected one RUN that downloads the {comp.label} from /{url.pattern}/ "
                      f"(the URL must contain the version {version})")
    if len(hits) != 1:
        return
    run = hits[0]
    expanded = _expand(run, args)

    with t.subTest(check=f"{comp.label} hash is chosen per architecture"):
        for arch in ("amd64", "arm64"):
            body = _branch(run, arch)
            t.assertIsNotNone(body, f"the {comp.label} RUN has no `{arch})` case branch")
            other = "arm64" if arch == "amd64" else "amd64"
            t.assertTrue(_refs(body or "", shas[arch][0]),
                         f"the `{arch})` branch does not use ${shas[arch][0]}")
            t.assertFalse(_refs(body or "", shas[other][0]),
                          f"the `{arch})` branch uses the {other} hash ${shas[other][0]}")

    segs = _segments(expanded)
    fetch = next((i for i, (c, _) in enumerate(segs) if url.search(c)), None)
    t.assertIsNotNone(fetch)
    assert fetch is not None
    fetch_cmd = segs[fetch][0]
    with t.subTest(check=f"{comp.label} is downloaded to /tmp, not straight into place"):
        t.assertRegex(fetch_cmd, r"(?:\s-[A-Za-z]*[oO]|\s--output(?:-document)?)[\s=]*[\"']?/tmp/",
                      f"download the {comp.label} to /tmp and check it before installing it: {fetch_cmd}")
    check = next((i for i in range(fetch + 1, len(segs)) if _is_sha_check(segs[i][0])), None)
    unpack = next((i for i in range(fetch + 1, len(segs))
                   if re.search(comp.unpack, segs[i][0]) and not _is_sha_check(segs[i][0])), None)
    with t.subTest(check=f"{comp.label}: sha256sum -c after the download, before unpack/install"):
        t.assertIsNotNone(check, f"no `sha256sum -c` after the {comp.label} download in the same RUN")
        t.assertIsNotNone(unpack, f"no unpack/install step after the {comp.label} download")
        if check is not None and unpack is not None:
            t.assertLess(check, unpack, f"the {comp.label} is unpacked or installed before "
                                        f"`sha256sum -c`: {segs[unpack][0]}")
    if check is None or unpack is None:
        return
    check_cmd, check_sep = segs[check]
    with t.subTest(check=f"{comp.label}: the check is fail-fast"):
        t.assertNotIn("--ignore-missing", check_cmd, "`--ignore-missing` passes a file it never read")
        t.assertNotEqual(check_sep, "||", f"`sha256sum -c ... ||` swallows a mismatch: {check_cmd}")
        set_e = re.search(r"(?:^RUN\s+|[;&]\s*)set\s+-[A-Za-z]*e", run) is not None
        chained = all(sep == "&&" for _, sep in segs[check:unpack])
        t.assertTrue(set_e or chained,
                     f"a failed `sha256sum -c` must stop the {comp.label} RUN: start it with "
                     "`set -eu;` (as the pwsh RUN) or chain every step to the unpack with &&")
    with t.subTest(check=f"{comp.label}: the committed hash is the control"):
        t.assertNotRegex(expanded, r"https?://\S+\.sha256\b",
                         "no checksum file is fetched at build time: the hash is committed (PS-3.10)")


# --- tests ---------------------------------------------------------------------

class GatesImageDockerCliTest(unittest.TestCase):
    """PS-3.10, static, docker/gates.Dockerfile."""

    def test_gates_image_pins_docker_cli_by_hash(self):  # PS-3.10 *Pinned and hash-checked*
        _assert_pinned(self, DOCKER_CLI)

    def test_gates_image_pins_compose_plugin_by_hash(self):  # PS-3.10 *Pinned and hash-checked*
        _assert_pinned(self, COMPOSE_PLUGIN)
        lines = _logical_lines(GATES_DOCKERFILE)
        with self.subTest(check="installed as a docker CLI plugin"):
            self.assertRegex(" ".join(_runs(lines)), r"cli-plugins/docker-compose\b",
                             "install the compose plugin as `.../cli-plugins/docker-compose` so "
                             "`docker compose` works (architecture §2.2: compose plugin)")

    def test_gates_image_compose_plugin_at_least_2_24(self):  # PS-3.10 *Compose version*
        args = _args(_logical_lines(GATES_DOCKERFILE))
        name, version = _one_arg(args, COMPOSE_PLUGIN.version_arg, "compose plugin version")
        self.assertRegex(version, FIXED_VERSION, f"ARG {name}={version!r} is not a fixed X.Y.Z")
        parsed = tuple(int(p) for p in version.split("."))
        self.assertGreaterEqual(parsed, (2, 24, 0),
                                f"ARG {name}={version}: offline-client needs compose >= 2.24 (§2.5)")

    def test_gates_image_installs_docker_only_from_pinned_binaries(self):  # PS-3.10 *No other route*
        text = GATES_DOCKERFILE.read_text(encoding="utf-8")
        lines = _logical_lines(GATES_DOCKERFILE)
        with self.subTest(check="the detectors catch the banned routes (self-check)"):
            for sample in ("RUN apt-get update && apt-get install -y docker-ce-cli docker-compose-plugin",
                           "RUN apt-get install -y --no-install-recommends docker.io",
                           "RUN curl -fsSL https://get.docker.com | sh",
                           "RUN sh -c \"$(curl -fsSL https://get.docker.com)\"",
                           "RUN wget -qO- https://example.com/i.sh | bash -s",
                           "RUN echo 'deb https://download.docker.com/linux/debian bookworm stable' "
                           "> /etc/apt/sources.list.d/docker.list"):
                self.assertTrue(_banned_routes([sample]), f"detector missed: {sample}")
            self.assertEqual(_banned_routes(["RUN apt-get install -y git jq ca-certificates curl"]), [])
        with self.subTest(check="no Docker package, Docker repo or download piped into a shell"):
            self.assertEqual(_banned_routes(lines), [],
                             "install Docker only from the pinned static binaries (PS-3.10)")
        with self.subTest(check="the Docker CLI and compose plugin come from the pinned binaries"):
            args = _args(lines)
            for comp in (DOCKER_CLI, COMPOSE_PLUGIN):
                names = [n for n in args if re.match(comp.version_arg, n)]
                version = args[names[0]] if len(names) == 1 else "<no version ARG>"
                url = re.compile(comp.url.format(v=re.escape(version)))
                self.assertTrue(any(url.search(_expand(r, args)) for r in _runs(lines)),
                                f"gates.Dockerfile does not install the {comp.label} from its pinned "
                                f"static release (/{url.pattern}/); offline-client needs it (§2.2)")
        with self.subTest(check="every Docker download is one of the two pinned URLs"):
            args = _args(lines)
            urls = re.findall(r"https?://[^\s\"']+", _expand(text, args))
            dockerish = [u for u in urls if re.search(r"docker", u, re.IGNORECASE)]
            allowed = re.compile(r"^https://(?:download\.docker\.com/linux/static/stable/"
                                 r"|github\.com/docker/compose/releases/download/v)")
            self.assertEqual([u for u in dockerish if not allowed.match(u)], [],
                             "a Docker download other than the pinned static CLI and compose release")


def _banned_routes(lines: list[str]) -> list[str]:
    """Findings for a Docker install route other than the pinned binaries."""
    findings: list[str] = []
    for ln in lines:
        if not re.match(r"^RUN\s", ln, re.IGNORECASE):
            continue
        for m in re.finditer(r"\b(?:apt-get|apt|aptitude)\s+(?:-\S+\s+)*install\b([^;&|]*)", ln):
            for pkg in m.group(1).split():
                name = pkg.split("=", 1)[0].lower()
                if not name.startswith("-") and re.match(r"^(?:docker|moby|containerd|runc)", name):
                    findings.append(f"apt package {pkg}: {ln}")
        if re.search(r"\b(?:get|test)\.docker\.com\b", ln):
            findings.append(f"get.docker.com: {ln}")
        if re.search(r"download\.docker\.com/linux/(?!static/)", ln):
            findings.append(f"Docker package repository: {ln}")
        if re.search(r"\b(?:curl|wget)\b[^;&]*\|\s*(?:sudo\s+)?(?:env\s+\S+\s+)*(?:ba|da|z|k)?sh\b", ln):
            findings.append(f"download piped into a shell: {ln}")
        if re.search(r"\b(?:ba|da|z|k)?sh\s+-c\s+[\"']?\$\(\s*(?:curl|wget)\b", ln):
            findings.append(f"download run by a shell: {ln}")
    return findings


# --- install surface (security audit-cli.md L-CLIb) and HTTPS-only fetch (L-CLIa) ---

# Daemon-side members of the static tarball; none of them may reach the image
# (architecture §2.2: client only).
DAEMON_WORD = re.compile(r"(?<![\w.-])(?:dockerd|containerd(?:-shim[\w-]*)?|runc|ctr|docker-proxy"
                         r"|docker-init)(?![\w.-])")
# tar options that take a value as the next word (GNU tar); `--opt=value` is one word.
_TAR_LONG_WITH_ARG = {"--file", "--directory", "--strip-components", "--exclude", "--transform",
                      "--xform", "--owner", "--group", "--mode", "--files-from", "--exclude-from",
                      "--use-compress-program", "--to-command", "--mtime", "--newer", "--format"}
_TAR_SHORT_WITH_ARG = "fCTXbLIHKNVFg"
PWSH_URL = re.compile(r"https://github\.com/PowerShell/PowerShell/releases/download/")


def _runs_tool(part: str, tool: str) -> bool:
    """True if a pipeline part runs `tool` as a command (not, say, an apt package name)."""
    return re.search(rf"(?:^\s*(?:RUN\s+)?(?:(?:if|then|do|else|!)\s+)?(?:[A-Za-z_]\w*=\S*\s+)*"
                     rf"(?:\S*/)?|\$\(\s*){tool}\s", part) is not None


def _component_run(lines: list[str], comp: Component) -> tuple[list[tuple[str, str]], int, int | None] | None:
    """(segments of the expanded RUN, fetch index, first unpack/install index)
    for the single RUN that downloads the component, or None."""
    args = _args(lines)
    names = [n for n in args if re.match(comp.version_arg, n)]
    if len(names) != 1:
        return None
    url = re.compile(comp.url.format(v=re.escape(args[names[0]])))
    hits = [r for r in _runs(lines) if url.search(_expand(r, args))]
    if len(hits) != 1:
        return None
    segs = _segments(_expand(hits[0], args))
    fetch = next((i for i, (c, _) in enumerate(segs) if url.search(c)), None)
    if fetch is None:
        return None
    unpack = next((i for i in range(fetch + 1, len(segs))
                   if re.search(comp.unpack, segs[i][0]) and not _is_sha_check(segs[i][0])), None)
    return segs, fetch, unpack


def _words(cmd: str) -> list[str]:
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def _command_words(cmd: str, name: str) -> list[str] | None:
    """The words after `name` in the pipeline part of `cmd` that runs it."""
    for part in cmd.split("|"):
        words = _words(part)
        for i, w in enumerate(words):
            if w == name or w.endswith("/" + name):
                return words[i + 1:]
    return None


def _tar_parse(words: list[str]) -> tuple[list[str], list[str]]:
    """(options, operands) of a tar command line (words after `tar`)."""
    opts: list[str] = []
    operands: list[str] = []
    i = 0
    if words and not words[0].startswith("-") and re.match(r"^[A-Za-z]+$", words[0]):
        cluster = words[0]  # old style: `tar xzf FILE`
        opts.append("-" + cluster)
        i = 1
        for ch in cluster:
            if ch in _TAR_SHORT_WITH_ARG and i < len(words):
                opts.append(words[i])
                i += 1
    while i < len(words):
        w = words[i]
        if w == "--":
            operands.extend(words[i + 1:])
            break
        if w.startswith("--"):
            opts.append(w)
            if "=" not in w and w in _TAR_LONG_WITH_ARG and i + 1 < len(words):
                opts.append(words[i + 1])
                i += 1
        elif w.startswith("-") and len(w) > 1:
            opts.append(w)
            for j, ch in enumerate(w[1:], start=1):
                if ch in _TAR_SHORT_WITH_ARG:
                    if j == len(w) - 1 and i + 1 < len(words):
                        opts.append(words[i + 1])
                        i += 1
                    break
        else:
            operands.append(w)
        i += 1
    return opts, operands


def _cli_tar(lines: list[str]) -> tuple[list[str], list[str], str] | str:
    """(options, operands, command) of the one tar step in the Docker CLI RUN,
    or a finding string."""
    found = _component_run(lines, DOCKER_CLI)
    if found is None:
        return "no single Docker CLI download RUN (see test_gates_image_pins_docker_cli_by_hash)"
    segs, fetch, _ = found
    tars = [c for c, _ in segs[fetch + 1:] if re.search(r"(?<![\w/.$-])tar(?![\w.-])", c)]
    if len(tars) != 1:
        return f"expected exactly one tar step after the Docker CLI download, found {tars}"
    words = _command_words(tars[0], "tar")
    if words is None:
        return f"cannot read the tar step: {tars[0]}"
    opts, operands = _tar_parse(words)
    return opts, operands, tars[0]


def _download_path(fetch_cmd: str) -> str | None:
    m = re.search(r"(?:\s-[A-Za-z]*o\s*|\s--output(?:-document)?[\s=]+)[\"']?(/tmp/[^\s\"';]+)", fetch_cmd)
    return m.group(1) if m else None


def _removes(cmd: str, path: str) -> bool:
    words = _command_words(cmd, "rm")
    if words is None or not re.match(r"^\s*rm\b", cmd):
        return False
    for w in (w for w in words if not w.startswith("-")):
        w = w.rstrip("/")
        if w == path or (w not in ("", "/tmp") and path.startswith(w + "/")):
            return True
    return False


def _mode_settings(cmd: str) -> list[str]:
    """Every mode a step sets: `chmod MODE`, `install|mkdir -m MODE`, `tar --mode=MODE`."""
    modes: list[str] = []
    for name in ("chmod", "install", "mkdir", "tar"):
        words = _command_words(cmd, name)
        if words is None:
            continue
        if name == "chmod":
            rest = [w for w in words if not re.match(r"^(?:-[Rfvch]+|--[\w-]+(?:=\S*)?)$", w)]
            if rest:
                modes.append(rest[0])
            continue
        for i, w in enumerate(words):
            if w.startswith("--mode="):
                modes.append(w.split("=", 1)[1])
            elif w == "--mode" and i + 1 < len(words):
                modes.append(words[i + 1])
            elif name != "tar" and re.match(r"^-[A-Za-z]*m", w) and not w.startswith("--"):
                tail = w[w.index("m") + 1:]
                if tail:
                    modes.append(tail)
                elif i + 1 < len(words):
                    modes.append(words[i + 1])
    return modes


def _unsafe_mode(mode: str) -> bool:
    """setuid, setgid, sticky, or group/world write; an unreadable mode is unsafe."""
    if re.match(r"^[0-7]{3,4}$", mode):
        return int(mode, 8) & 0o7022 != 0
    for clause in mode.split(","):
        m = re.match(r"^([ugoa]*)((?:[+=-][rwxXst]*)+)$", clause)
        if not m:
            return True
        who = m.group(1)
        for op, perms in re.findall(r"([+=-])([rwxXst]*)", m.group(2)):
            if op == "-":
                continue
            if "s" in perms or "t" in perms:
                return True
            if "w" in perms and (who == "" or any(c in who for c in "goa")):
                return True
    return False


def _curl_findings(lines: list[str]) -> list[str]:
    """curl/wget steps in RUN lines that could follow a redirect to plain http
    or negotiate TLS below 1.2 (security audit-cli.md L-CLIa)."""
    findings: list[str] = []
    for run in _runs(lines):
        for seg, _ in _segments(run):
            for part in seg.split("|"):
                if _runs_tool(part, "curl"):
                    if not re.search(r"\s--proto\s+(?:'=https'|\"=https\"|=https)(?=\s|$)", part):
                        findings.append(f"curl without `--proto '=https'`: {part.strip()}")
                    if not re.search(r"\s--tlsv1\.[23](?=\s|$)", part):
                        findings.append(f"curl without `--tlsv1.2`: {part.strip()}")
                    if re.search(r"(?<!\S)(?:--insecure|-[A-Za-z]*k[A-Za-z]*)(?!\S)", part):
                        findings.append(f"curl skips TLS verification: {part.strip()}")
                if _runs_tool(part, "wget") and "--https-only" not in part:
                    findings.append(f"wget without --https-only: {part.strip()}")
    return findings


class GatesImageInstallSurfaceTest(unittest.TestCase):
    """Security audit-cli.md L-CLIb (client only, ownership, leftovers, plugin
    mode) and L-CLIa (HTTPS-only, TLS >= 1.2 fetches); architecture §2.2, PS-3.10."""

    def test_gates_image_extracts_only_the_docker_client(self):  # L-CLIb, mutant T10
        lines = _logical_lines(GATES_DOCKERFILE)
        tar = _cli_tar(lines)
        self.assertNotIsInstance(tar, str, tar)
        assert not isinstance(tar, str)
        opts, operands, cmd = tar
        with self.subTest(check="the tar step extracts"):
            self.assertTrue(any(o in ("--extract", "--get") or re.match(r"^-[A-Za-z]*x", o) for o in opts),
                            f"not an extract: {cmd}")
        with self.subTest(check="exactly the member docker/docker, no wildcard, no member list"):
            self.assertEqual(operands, ["docker/docker"],
                             "extract only `docker/docker` from the static tarball; it also ships "
                             f"dockerd, containerd, runc, ctr, docker-proxy, docker-init: {cmd}")
            self.assertEqual([o for o in opts if o in ("--wildcards", "-T", "--files-from")
                              or o.startswith("--files-from=")], [], f"member selection by pattern/list: {cmd}")
        with self.subTest(check="no daemon binary named in any RUN, COPY or ADD"):
            steps = [ln for ln in lines if re.match(r"^(?:RUN|COPY|ADD)\s", ln, re.IGNORECASE)]
            self.assertEqual([ln for ln in steps if DAEMON_WORD.search(ln)], [],
                             "the gates image is client only (§2.2): no dockerd/containerd/runc/ctr")

    def test_gates_image_docker_client_extracted_with_no_same_owner(self):  # L-CLIb, mutant T13
        lines = _logical_lines(GATES_DOCKERFILE)
        tar = _cli_tar(lines)
        self.assertNotIsInstance(tar, str, tar)
        assert not isinstance(tar, str)
        opts, _, cmd = tar
        self.assertIn("--no-same-owner", opts,
                      "as root, tar keeps the archive owner (runner/runner, uid 1000+); use "
                      f"--no-same-owner so /usr/local/bin/docker is root:root: {cmd}")
        self.assertNotIn("--same-owner", opts, cmd)

    def test_gates_image_removes_docker_downloads_in_the_same_run(self):  # L-CLIb, mutant T14
        lines = _logical_lines(GATES_DOCKERFILE)
        for comp in (DOCKER_CLI, COMPOSE_PLUGIN):
            with self.subTest(component=comp.label):
                found = _component_run(lines, comp)
                self.assertIsNotNone(found, f"no single {comp.label} download RUN")
                assert found is not None
                segs, fetch, unpack = found
                path = _download_path(segs[fetch][0])
                self.assertIsNotNone(path, f"{comp.label} is not downloaded to /tmp: {segs[fetch][0]}")
                self.assertIsNotNone(unpack, f"no unpack/install step after the {comp.label} download")
                assert path is not None and unpack is not None
                self.assertTrue(any(_removes(c, path) for c, _ in segs[unpack + 1:]),
                                f"`rm {path}` after the {comp.label} is installed, in the same RUN, "
                                "or the download stays in an image layer")

    def test_gates_image_compose_plugin_mode_0755(self):  # L-CLIb, mutant T16
        lines = _logical_lines(GATES_DOCKERFILE)
        with self.subTest(check="the mode detector (self-check)"):
            for bad in ("4777", "4755", "2755", "0777", "0775", "1755", "u+s", "g+w", "+w", "a=rwx", "o+wt"):
                self.assertTrue(_unsafe_mode(bad), bad)
            for good in ("0755", "755", "0555", "a+rx", "u+w", "go-w", "+x"):
                self.assertFalse(_unsafe_mode(good), good)
        found = _component_run(lines, COMPOSE_PLUGIN)
        self.assertIsNotNone(found, "no single compose plugin download RUN")
        assert found is not None
        segs, fetch, _ = found
        placing = [c for c, _ in segs[fetch + 1:]
                   if re.search(r"cli-plugins/docker-compose\b", c) and not _is_sha_check(c)]
        with self.subTest(check="the plugin is installed with mode 0755"):
            self.assertTrue(placing, "no step installs .../cli-plugins/docker-compose")
            self.assertTrue(any(m in ("0755", "755") for c in placing for m in _mode_settings(c)),
                            f"install the plugin with `install -m 0755`: {placing}")
        with self.subTest(check="nothing under the Docker install paths is setuid or group/world writable"):
            args = _args(lines)
            touched = [c for r in _runs(lines) for c, _ in _segments(_expand(r, args))
                       if re.search(r"cli-plugins|/usr/local/lib/docker|/usr/local/bin", c)]
            self.assertEqual([(m, c) for c in touched for m in _mode_settings(c) if _unsafe_mode(m)], [],
                             "the Docker client and plugin are root-owned 0755 (audit-cli.md §3)")

    def test_gates_image_curl_downloads_are_https_only_tls12(self):  # L-CLIa
        with self.subTest(check="the detector (self-check)"):
            for sample in ("RUN curl -fsSL -o /tmp/x https://example.com/x",
                           "RUN curl --proto '=https' -fsSL -o /tmp/x https://example.com/x",
                           "RUN curl --tlsv1.2 -fsSL -o /tmp/x https://example.com/x",
                           "RUN curl --proto '=http,https' --tlsv1.2 -fsSL https://example.com/x",
                           "RUN curl --proto '=https' --tlsv1.2 -fsSLk https://example.com/x",
                           "RUN set -eu; wget -qO /tmp/x https://example.com/x"):
                self.assertTrue(_curl_findings([sample]), f"detector missed: {sample}")
            for sample in ("RUN curl --proto '=https' --tlsv1.2 -fsSL -o /tmp/x https://example.com/x",
                           "RUN set -eu; curl --proto =https --tlsv1.3 -fsSL -o /tmp/x \"https://e/x\"; rm /tmp/x"):
                self.assertEqual(_curl_findings([sample]), [], sample)
        lines = _logical_lines(GATES_DOCKERFILE)
        args = _args(lines)
        with self.subTest(check="the pwsh, Docker CLI and compose downloads are curl steps (not vacuous)"):
            curl_parts = [p for r in _runs(lines) for c, _ in _segments(_expand(r, args))
                          for p in c.split("|") if _runs_tool(p, "curl")]
            for label, url in (("pwsh", PWSH_URL),
                               (DOCKER_CLI.label, re.compile(r"https://download\.docker\.com/linux/static/")),
                               (COMPOSE_PLUGIN.label, re.compile(r"https://github\.com/docker/compose/"))):
                self.assertTrue(any(url.search(p) for p in curl_parts), f"no curl step fetches the {label}")
        with self.subTest(check="every curl uses --proto '=https' and --tlsv1.2"):
            self.assertEqual(_curl_findings(lines), [],
                             "use `curl --proto '=https' --tlsv1.2 -fsSL` on every download: with -L a "
                             "redirect could otherwise go to plain http (audit-cli.md L-CLIa)")


class GateServicesNoDockerHostTest(unittest.TestCase):
    """PS-3.10 *Client only in the gate services* (compose config, static)."""

    def test_gate_services_have_no_docker_host(self):
        defs = [(f, n, s) for f, n, s in cs.all_services() if n in GATE_SERVICES]
        self.assertEqual(sorted({n for _, n, _ in defs}), sorted(GATE_SERVICES))
        for file_name, name, svc in defs:
            with self.subTest(file=file_name, service=name, check="environment"):
                env = cs.environment(svc)
                self.assertEqual([k for k in env if k in DAEMON_ENV], [],
                                 f"{name} points a Docker client at a daemon; only offline-client "
                                 "may (it points at dind, §2.2)")
                self.assertEqual([k for k, v in env.items() if any(s in v for s in SOCKET_TEXT)], [])
            with self.subTest(file=file_name, service=name, check="no env_file"):
                self.assertNotIn("env_file", svc, f"{name}: an env_file could carry DOCKER_HOST")
            with self.subTest(file=file_name, service=name, check="no Docker socket"):
                mounts = [str(v) for v in svc.get("volumes") or []]
                self.assertEqual([m for m in mounts if any(s in m for s in SOCKET_TEXT)], [],
                                 f"{name} mounts a Docker socket")
        with self.subTest(check="gates.Dockerfile sets no daemon variable"):
            env_lines = [ln for ln in _logical_lines(GATES_DOCKERFILE)
                         if re.match(r"^ENV\s", ln, re.IGNORECASE)]
            for var in DAEMON_ENV:
                self.assertEqual([ln for ln in env_lines if re.search(rf"\b{var}\b", ln)], [],
                                 f"the gates image sets {var}; offline-client sets it in compose")
        with self.subTest(check="no gate run passes DOCKER_HOST or a socket"):
            self.assertEqual(_gate_run_leaks(), [])


# --- PS-3.7: pwsh telemetry off (PSC-11) and PSScriptAnalyzer by hash (PSC-10) ---

PWSH_TELEMETRY_ENV = {"POWERSHELL_TELEMETRY_OPTOUT": "1", "POWERSHELL_UPDATECHECK": "Off"}
# pwsh started as a command, shell form `pwsh -...` (also by path) or exec form
# `["pwsh", "-..."]`. `ln -s /opt/microsoft/powershell/pwsh /usr/local/bin/pwsh`
# and `chmod +x .../pwsh` do not start it (architecture §2.6, PSC-11).
PWSH_START = re.compile(r"(?<![\w.-])pwsh(?:\s+|[\"']\s*,\s*[\"'])-")
PSA_VERSION_ARG = "PSSCRIPTANALYZER_VERSION"
PSA_HASH_ARG = "PSSCRIPTANALYZER_SHA512"  # orchestrator ruling 2026-10-21: the gallery's SHA-512
HEX128 = re.compile(r"^[0-9a-f]{128}$")
PSA_URL = "https://www.powershellgallery.com/api/v2/package/PSScriptAnalyzer/{v}"
PSA_MODULE_DIR = "/usr/local/share/powershell/Modules/PSScriptAnalyzer/{v}"
# Repository installs and trust changes: no hash check on what they fetch (D7).
GALLERY_INSTALL = re.compile(
    r"(?<![\w-])(?:Install-Module|Install-PSResource|Save-Module|Save-PSResource|Set-PSRepository"
    r"|Register-PSRepository|Set-PSResourceRepository|Register-PSResourceRepository|inmo)(?![\w-])",
    re.IGNORECASE)
# A step that unpacks an archive (the first one after the download must follow the check).
UNPACK = re.compile(r"\bzipfile\b|\bunzip\b|(?<![\w.-])b?sdtar(?![\w.-])|(?<![\w./-])tar(?![\w.-])"
                    r"|(?<![\w.-])7za?(?![\w.-])|Expand-Archive", re.IGNORECASE)


def _final_stage(lines: list[str]) -> int:
    """Index of the first instruction after the last FROM (ENV does not cross stages)."""
    froms = [i for i, ln in enumerate(lines) if re.match(r"^FROM\s", ln, re.IGNORECASE)]
    return froms[-1] + 1 if froms else 0


def _starts_pwsh(line: str) -> bool:
    if re.match(r"^RUN\s", line, re.IGNORECASE):
        return PWSH_START.search(line) is not None
    # SHELL ["pwsh", ...] makes every later RUN a pwsh run.
    return re.match(r"^SHELL\s", line, re.IGNORECASE) is not None and re.search(r"\bpwsh\b", line) is not None


def _env_pairs(line: str) -> list[tuple[str, str]]:
    """(key, value) set by one ENV instruction, `KEY=VALUE ...` or legacy `KEY VALUE`."""
    m = re.match(r"^ENV\s+(.*)$", line, re.IGNORECASE)
    if not m:
        return []
    words = _words(m.group(1))
    if words and "=" not in words[0]:
        return [(words[0], " ".join(words[1:]))]
    return [(k, v) for k, v in (w.split("=", 1) for w in words if "=" in w)]


def _is_sha512_check(cmd: str) -> bool:
    return re.search(r"\bsha512sum\b[^|]*?(?:\s-c\b|\s--check\b|\s-[a-z]*c[a-z]*\b)", cmd) is not None


# --- PSC-10: the hash check cannot be masked (review-u1 B1) ---
# dash has no pipefail, and `set -e` is off for a negated pipeline, an
# if/elif/while/until condition, any AND-OR member but the last, and a
# background job. A check in any of those, or a download replaced after the
# check, lets a wrong package through: the reviewer's `| cat` mutant built OK
# with a wrong hash (docs/evidence/platform-supply-chain/review-u1.md).
_QUOTED = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'[^']*'")
_CHECK_LEAD = {"if", "elif", "then", "else", "while", "until", "do", "for", "case", "!", "time",
               "exec", "eval", "export", "local", "readonly"}
_REWRITER = re.compile(r"(?<![\w.-])(?:curl|wget|cp|mv|ln|install|dd|tee|rsync|scp|cat|truncate"
                       r"|python3?|perl|pwsh|sh|bash|dash|eval|exec)(?![\w.-])")


def _unquoted(text: str) -> str:
    """`text` with every quoted string emptied: quoted `;`, `&`, `|` or `>` are not shell syntax."""
    return _QUOTED.sub('""', text)


def _errexit_off(run: str) -> list[str]:
    """Each `set` in the RUN that clears -e or -u (`set +e`, `set +eu`, `set +o errexit|nounset`)."""
    found: list[str] = []
    for m in re.finditer(r"(?<![\w$./-])set((?:[ \t]+[^\s;&|)}]+)+)", _unquoted(run)):
        words = m.group(1).split()
        if any(re.match(r"^\+[A-Za-z]*[eu]", w)
               or (w == "+o" and i + 1 < len(words) and words[i + 1] in ("errexit", "nounset"))
               for i, w in enumerate(words)):
            found.append("set" + m.group(1))
    return found


def _psa_check_masking(run: str, args: dict[str, str], path: str) -> list[str]:
    """Ways the module RUN's `sha512sum -c` can fail without failing the RUN,
    or the download can change between the check and the unpack (B1)."""
    segs = _segments(run)
    exp = [_expand(c, args) for c, _ in segs]
    check = next((i for i, c in enumerate(exp) if _is_sha512_check(c)), None)
    if check is None:
        return []  # reported by the "sha512sum -c fed ..." subtest
    findings: list[str] = []
    if re.search(r"(?<![&>|<])&(?![&>])", _unquoted(run)):
        findings.append("a background job (`&`) in the module RUN: a backgrounded check never fails "
                        "the RUN, and a background writer can race it")
    findings.extend(f"`{s}` clears set -eu in the module RUN" for s in _errexit_off(run))
    cmd, sep = segs[check]
    bare = _unquoted(re.sub(r"^RUN\s+", "", cmd))
    words = bare.split()
    if words and (words[0] in _CHECK_LEAD or "=" in words[0]):
        findings.append(f"the check starts with `{words[0]}`: negated, conditional, looped or "
                        f"substituted, it runs with set -e off: {cmd}")
    if "!" in words or re.search(r"[(){}`]", bare):
        findings.append(f"the check is negated, grouped or substituted: {cmd}")
    stages = bare.split("|")
    last = stages[-1].split()
    if not (len(last) >= 3 and re.match(r"^(?:\S*/)?sha512sum$", last[0]) and last[-1] == "-"
            and all(w.startswith("-") for w in last[1:])
            and any(re.match(r"^(?:--check|-[a-z]*c[a-z]*)$", w) for w in last[1:-1])):
        findings.append(f"the check's pipeline must end in `sha512sum -c -` (dash has no "
                        f"pipefail: a later `| cat` or `| tee` hides a mismatch): {cmd}")
    feed = stages[0].split()
    if len(stages) != 2 or not feed or feed[0] not in ("echo", "printf"):
        findings.append(f"the check must be exactly two stages, an `echo`/`printf` feed piped to "
                        f"`sha512sum -c -` (found {len(stages)}; dash has no pipefail, so a second "
                        f"`| ... | sha512sum -c -` or a middle `| tee` stage hides or alters the "
                        f"check, security M-U1R1-1): {cmd}")
    n_sha = len(re.findall(r"(?<![\w.-])sha512sum(?![\w.-])", _expand(run, args)))
    if n_sha != 1:
        findings.append(f"the module RUN names `sha512sum` {n_sha} times: exactly one, the check "
                        f"(a second check of a known-good input can mask it, security M-U1R1-1)")
    if sep not in (";", ""):
        findings.append(f"`{sep}` after the check: set -e ignores a failing AND-OR member that is "
                        f"not the last, and `||` swallows it: {cmd}")
    if check > 0 and segs[check - 1][1] != ";":
        findings.append(f"`{segs[check - 1][1]}` before the check: it can be skipped, or run as a "
                        f"non-last AND-OR member: {segs[check - 1][0]}")
    before = re.sub(r"\$\{[^}]*\}", "", " ; ".join(_unquoted(c) for c, _ in segs[:check]))
    before = re.sub(r"(?<![\w-])case(?![\w-]).*?(?<![\w-])esac(?![\w-])", " ", before)

    def count(pattern: str) -> int:
        return len(re.findall(pattern, before))

    if (count(r"(?<![\w$-])if(?![\w-])") > count(r"(?<![\w$-])fi(?![\w-])")
            or count(r"(?<![\w$-])(?:while|until|for)(?![\w-])") > count(r"(?<![\w$-])done(?![\w-])")
            or before.count("{") > before.count("}") or before.count("(") > before.count(")")):
        findings.append("the check sits inside an if/while/until/for, a `{ }` group or a subshell")
    unpack = next((i for i in range(check + 1, len(exp))
                   if UNPACK.search(exp[i]) and not _is_sha512_check(exp[i])), None)
    base = path.rsplit("/", 1)[-1]
    for i in range(check + 1, len(exp) if unpack is None else unpack):
        between = exp[i]
        if path in between or base in between:
            findings.append(f"the download is touched between the check and the unpack: {between}")
        if _REWRITER.search(between):
            findings.append(f"a step that can fetch, copy, move or write runs between the check and "
                            f"the unpack: {between}")
        if re.search(r"(?<![<&])>(?!&|\s*/dev/null)", _unquoted(between)):
            findings.append(f"a redirect writes a file between the check and the unpack: {between}")
    if unpack is not None and "|" in _unquoted(exp[unpack]):
        findings.append(f"the unpack is in a pipeline (another part can replace the download): {exp[unpack]}")
    return findings


XYZ = re.compile(r"(?<![\d.])\d+\.\d+\.\d+(?!\.?\d)")  # also inside "v1.24.0"
# The window test_stack_scripts' `test_gates_image_has_shellcheck_and_psscriptanalyzer`
# reads a version from: up to 200 characters after "PSScriptAnalyzer".
PSA_COMMENT_WINDOW = 200
PSA_MODULE_PATH = re.compile(r"/Modules/PSScriptAnalyzer/([^\s\"'/;]*)")


def _comment_blocks(text: str) -> list[str]:
    """Runs of consecutive `#` lines, `#` stripped, joined with spaces."""
    blocks: list[str] = []
    current: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            current.append(stripped.lstrip("#").strip())
            continue
        if current:
            blocks.append(" ".join(current))
            current = []
    if current:
        blocks.append(" ".join(current))
    return blocks


def _psa_version_drift(path: Path) -> list[str]:
    """Every x.y.z a comment puts after "PSScriptAnalyzer", and the version
    directory of every module path, that differs from ARG PSSCRIPTANALYZER_VERSION."""
    text = path.read_text(encoding="utf-8")
    instructions = _logical_lines(path)
    args = _args(instructions)
    version = args.get(PSA_VERSION_ARG, "")
    if not FIXED_VERSION.match(version):
        return [f"ARG {PSA_VERSION_ARG}={version!r} is not a fixed x.y.z"]
    drift: list[str] = []
    for block in _comment_blocks(text):
        for mention in re.finditer(r"PSScriptAnalyzer", block, re.IGNORECASE):
            window = block[mention.end():mention.end() + PSA_COMMENT_WINDOW]
            for found in XYZ.finditer(window):
                if found.group(0) != version:
                    drift.append(f"comment: PSScriptAnalyzer ... {found.group(0)} "
                                 f"(near {block[mention.start():mention.end() + found.end()][:120]!r})")
    paths = [m.group(1) for ln in instructions for m in PSA_MODULE_PATH.finditer(_expand(ln, args))]
    if not paths:
        drift.append("no /Modules/PSScriptAnalyzer/<version> path in any instruction")
    drift.extend(f"module path: /Modules/PSScriptAnalyzer/{p}" for p in paths if p != version)
    return drift


class GatesImagePowerShellSupplyChainTest(unittest.TestCase):
    """PS-3.7 (security L-8, review N-7): PSC-11 and PSC-10, static,
    docker/gates.Dockerfile; ADR-KE-013 amendment 1, D7."""

    def test_gates_image_sets_telemetry_optout_before_pwsh(self):  # PSC-11
        with self.subTest(check="the pwsh-start detector (self-check)"):
            for sample in ("RUN pwsh -NoProfile -NonInteractive -Command 'Import-Module X'",
                           "RUN set -eu; /opt/microsoft/powershell/pwsh -c 'x'",
                           'RUN ["pwsh", "-NoProfile", "-Command", "x"]',
                           'SHELL ["pwsh", "-Command"]'):
                self.assertTrue(_starts_pwsh(sample), f"detector missed: {sample}")
            for sample in ("RUN set -eu; ln -s /opt/microsoft/powershell/pwsh /usr/local/bin/pwsh",
                           "RUN chmod +x /opt/microsoft/powershell/pwsh; rm /tmp/x",
                           "ENV POWERSHELL_TELEMETRY_OPTOUT=1"):
                self.assertFalse(_starts_pwsh(sample), sample)
        lines = _logical_lines(GATES_DOCKERFILE)
        final = _final_stage(lines)
        start = next((i for i in range(final, len(lines)) if _starts_pwsh(lines[i])), None)
        with self.subTest(check="a RUN after the final FROM starts pwsh (not vacuous)"):
            self.assertIsNotNone(start, "no RUN after the final FROM starts pwsh; D7's build-time "
                                        "`pwsh ... Import-Module PSScriptAnalyzer` is the one PSC-11 "
                                        "orders the ENV against")
        if start is None:
            return
        for key, value in PWSH_TELEMETRY_ENV.items():
            sets = [(i, v) for i, ln in enumerate(lines) for k, v in _env_pairs(ln) if k == key]
            with self.subTest(key=key, check="set once in the file (moved, not duplicated)"):
                self.assertEqual(len(sets), 1, f"{key} is set by {len(sets)} ENV instructions: "
                                               f"{[lines[i] for i, _ in sets]}")
            with self.subTest(key=key, check="set by an ENV after the final FROM, before pwsh first runs"):
                early = [i for i, v in sets if final <= i < start and v == value]
                self.assertTrue(early,
                                f"`ENV {key}={value}` must come after the final FROM and before the "
                                f"first RUN that starts pwsh ({lines[start][:120]}...); found it at "
                                f"{[(i, v) for i, v in sets]} with that RUN at {start} (PSC-11, N-7: "
                                "otherwise the first pwsh run phones home)")

    def test_gates_image_verifies_psscriptanalyzer_hash(self):  # PSC-10
        with self.subTest(check="the detectors (self-check)"):
            for sample in ("Install-Module PSScriptAnalyzer -RequiredVersion 1.25.0",
                           "install-module PSScriptAnalyzer", "Set-PSRepository PSGallery -InstallationPolicy Trusted",
                           "Install-PSResource PSScriptAnalyzer", "Save-Module X -Path /tmp",
                           "Register-PSRepository -Name x -SourceLocation y"):
                self.assertTrue(GALLERY_INSTALL.search(sample), f"detector missed: {sample}")
            self.assertTrue(_is_sha512_check('echo "$H  /tmp/psa.nupkg" | sha512sum -c -'))
            self.assertTrue(_is_sha512_check("sha512sum --check --strict /tmp/psa.sha512"))
            self.assertFalse(_is_sha512_check('echo "$H  /tmp/psa.nupkg" | sha256sum -c -'))
            self.assertFalse(_is_sha512_check("sha512sum /tmp/psa.nupkg"))
            good = ('RUN set -eu; curl -o /tmp/psa.nupkg "u"; '
                    'echo "$PSSCRIPTANALYZER_SHA512  /tmp/psa.nupkg" | sha512sum -c -; dir="/m"; '
                    'python3 -I -m zipfile -e /tmp/psa.nupkg "/m"; rm -rf /tmp/psa.nupkg')
            self.assertEqual(_psa_check_masking(good, {}, "/tmp/psa.nupkg"), [])
            self.assertEqual(_psa_check_masking(good.replace("echo ", "printf '%s\\n' ", 1), {},
                                                "/tmp/psa.nupkg"), [])
            chk = 'echo "$PSSCRIPTANALYZER_SHA512  /tmp/psa.nupkg" | sha512sum -c -;'
            for old, new in ((chk, chk[:-1] + " | cat;"), (chk, "if " + chk + " then :; fi;"),
                             (chk, "! " + chk), (chk, chk[:-1] + " &"), ("set -eu;", "set -eu; set +e;"),
                             ("set -eu;", "set -eu; set +o errexit;"), ("set -eu;", "set -eu; set +u;"),
                             ('dir="/m";', 'cp /tmp/x /tmp/psa.nupkg;'),
                             # security M-U1R1-1: a second check stage of a known-good input
                             (chk, chk[:-1] + ' | echo "$E  /dev/null" | sha512sum -c -;'),
                             (chk, chk.replace(" | ", " | tee /dev/stderr | ", 1)),
                             ('dir="/m";', 'echo "$E  /dev/null" | sha512sum -c -; dir="/m";'),
                             ("set -eu;", 'set -eu; echo "$E  /dev/null" | sha512sum -c -;'),
                             (chk, 'cat /tmp/psa.sha512 | sha512sum -c -;'),
                             (chk, 'sha512sum -c - < /tmp/psa.sha512;')):
                bad = good.replace(old, new, 1)
                self.assertNotEqual(bad, good)
                self.assertTrue(_psa_check_masking(bad, {}, "/tmp/psa.nupkg"), f"detector missed: {bad}")
        lines = _logical_lines(GATES_DOCKERFILE)
        args = _args(lines)
        with self.subTest(check="no Install-Module, Set-PSRepository or other gallery install"):
            self.assertEqual([ln[max(0, m.start() - 60):m.end() + 60] for ln in lines
                              for m in GALLERY_INSTALL.finditer(ln)], [],
                             "a gallery install has no hash check (security L-8): fetch the .nupkg "
                             "with curl and check it with sha512sum -c instead (PSC-10, D7)")
        version = args.get(PSA_VERSION_ARG, "")
        with self.subTest(check="the version is fixed"):
            self.assertRegex(version, FIXED_VERSION, f"ARG {PSA_VERSION_ARG}={version!r}: a fixed X.Y.Z")
        with self.subTest(check="one committed SHA-512, for both architectures"):
            self.assertEqual(sorted(n for n in args if n.startswith("PSSCRIPTANALYZER_SHA")), [PSA_HASH_ARG],
                             "exactly one hash ARG, the gallery's SHA-512 (ruling 2026-10-21; the "
                             "package does not depend on the architecture)")
            self.assertRegex(args.get(PSA_HASH_ARG, ""), HEX128,
                             f"ARG {PSA_HASH_ARG} must be 128 lowercase hex (SHA-512)")
        if not FIXED_VERSION.match(version):
            self.fail(f"no fixed ARG {PSA_VERSION_ARG}; cannot locate the download")
        url = PSA_URL.format(v=version)
        hits = [i for i, ln in enumerate(lines)
                if re.match(r"^RUN\s", ln, re.IGNORECASE) and url in _expand(ln, args)]
        with self.subTest(check="one RUN downloads the pinned .nupkg from the gallery package endpoint"):
            self.assertEqual(len(hits), 1, f"expected one RUN that fetches {url} (found {len(hits)})")
        if len(hits) != 1:
            return
        run_at = hits[0]
        segs = _segments(lines[run_at])
        exp = [_expand(c, args) for c, _ in segs]
        fetch = next(i for i, c in enumerate(exp) if url in c)
        with self.subTest(check="the RUN is fail-fast: it starts with `set -eu`"):
            self.assertRegex(segs[0][0], r"^RUN\s+set\s+-(?=[A-Za-z]*e)(?=[A-Za-z]*u)[A-Za-z]+$",
                             f"the module RUN must start with `set -eu;`: {segs[0][0]}")
            self.assertLess(0, fetch, "`set -eu` must come before the download")
        curl = next((p for p in exp[fetch].split("|") if _runs_tool(p, "curl") and url in p), "")
        with self.subTest(check="the download is curl over HTTPS only, redirects included, TLS >= 1.2"):
            self.assertTrue(curl, f"the .nupkg is not fetched by curl: {exp[fetch]}")
            q = r"(?:'=https'|\"=https\"|=https)(?=\s|$)"
            self.assertRegex(curl, rf"\s--proto\s+{q}", "curl needs `--proto '=https'`")
            self.assertRegex(curl, rf"\s--proto-redir\s+{q}",
                             "curl -L follows the gallery's redirect: add `--proto-redir '=https'` (D7)")
            self.assertRegex(curl, r"\s--tlsv1\.[23](?=\s|$)", "curl needs `--tlsv1.2`")
            self.assertNotRegex(curl, r"(?<!\S)(?:--insecure|-[A-Za-z]*k[A-Za-z]*)(?!\S)", "curl skips TLS checks")
        path = _download_path(exp[fetch])
        with self.subTest(check="downloaded to /tmp"):
            self.assertIsNotNone(path, f"download the .nupkg to /tmp and check it there: {exp[fetch]}")
        if path is None:
            return
        after = range(fetch + 1, len(exp))
        check = next((i for i in after if _is_sha512_check(exp[i])), None)
        unpack = next((i for i in after if UNPACK.search(exp[i]) and not _is_sha512_check(exp[i])), None)
        touch = next((i for i in after if path in exp[i] or UNPACK.search(exp[i])), None)
        with self.subTest(check="sha512sum -c fed the pinned hash and the download"):
            self.assertIsNotNone(check, "no `sha512sum -c` after the download in the same RUN (ruling "
                                        "2026-10-21: pin the gallery's SHA-512)")
            if check is not None:
                self.assertTrue(_refs(segs[check][0], PSA_HASH_ARG),
                                f"the check is not fed ${PSA_HASH_ARG}: {segs[check][0]}")
                self.assertIn(path, exp[check], f"the check does not name the download {path}")
                self.assertNotIn("--ignore-missing", exp[check], "`--ignore-missing` passes a file it never read")
                self.assertNotEqual(segs[check][1], "||", f"`... ||` swallows a mismatch: {segs[check][0]}")
        with self.subTest(check="the check is the first step that reads the download"):
            self.assertIsNotNone(check)
            self.assertEqual(touch, check, f"the download is read or unpacked before `sha512sum -c`: "
                                           f"{exp[touch] if touch is not None else None}")
        with self.subTest(check="the check cannot be masked and the download is not replaced after it"):
            self.assertEqual(_psa_check_masking(lines[run_at], args, path), [],
                             "under `set -eu` a failing `... | sha512sum -c -` must stop the RUN: exactly "
                             "`echo|printf ... | sha512sum -c -`, the RUN's only sha512sum, not negated, "
                             "conditional, grouped or backgrounded, no `set +e`, and nothing rewrites the "
                             "download before the unpack (review-u1 B1, security M-U1R1-1, D7)")
        module_dir = PSA_MODULE_DIR.format(v=version)
        with self.subTest(check="unpacked after the check with `python3 -I -m zipfile -e` into the module path"):
            self.assertIsNotNone(unpack, "no unpack step after the download")
            if unpack is not None:
                if check is not None:
                    self.assertLess(check, unpack, f"unpacked before the hash check: {exp[unpack]}")
                bare = re.sub(r"[\"']", "", exp[unpack])
                self.assertRegex(bare, rf"\bpython3\s+(?:-[A-Za-z]+\s+)*?-I\s+(?:-[A-Za-z]+\s+)*-m\s+zipfile"
                                       rf"\s+-e\s+{re.escape(path)}\s+{re.escape(module_dir)}/?(?:\s|$)",
                                 f"unpack with `python3 -I -m zipfile -e {path} {module_dir}` (D7)")
        if unpack is None:
            return
        rest = exp[unpack + 1:]
        with self.subTest(check="the .nupkg and the NuGet packaging files are removed in the same RUN"):
            self.assertTrue(any(_removes(c, path) for c in rest), f"`rm {path}` after the unpack")
            removed = " ".join(re.sub(r"[\"']", "", c) for c in rest if re.match(r"^\s*rm\b", c))
            for name, pattern in (("_rels", r"(?:^|[\s/])_rels(?:/|\s|$)"),
                                  ("package", r"(?:^|[\s/])package(?:/|\s|$)"),
                                  ("[Content_Types].xml", r"Content_Types\]?\.xml"),
                                  ("PSScriptAnalyzer.nuspec", r"\.nuspec\b"),
                                  # security L-U1-1: the NuGet signature is packaging, not module content
                                  (".signature.p7s", r"(?:^|[\s/])\.signature\.p7s(?:\s|$)")):
                self.assertRegex(removed, pattern, f"remove {name} from {module_dir} (D7)")
        with self.subTest(check="a build-time Import-Module after the unpack proves it"):
            tail = " ; ".join(rest)
            self.assertRegex(tail, r"(?<![\w.-])pwsh\s+-.*?\bImport-Module\s+(?:-Name\s+)?[\"']?PSScriptAnalyzer\b",
                             "run `pwsh -NoProfile -NonInteractive -Command 'Import-Module "
                             "PSScriptAnalyzer -ErrorAction Stop'` after the unpack, in the same RUN (D7)")
            self.assertRegex(tail, r"-ErrorAction\s+Stop|\$ErrorActionPreference\s*=\s*[\"']?Stop",
                             "a failed import must fail the build: `-ErrorAction Stop`")
        with self.subTest(check="no pwsh runs before the module RUN"):
            self.assertEqual([ln[:120] for ln in lines[_final_stage(lines):run_at] if _starts_pwsh(ln)], [],
                             "the module RUN's Import-Module is the first RUN that starts pwsh (D7); "
                             "drop the trailing `pwsh -Command` from the tarball RUN")

    def test_gates_image_psscriptanalyzer_version_agrees(self):  # PSC-10 guard
        # The comment "PSScriptAnalyzer 1.25.0 (ARG below)" exists so
        # test_stack_scripts' version-pinned regex matches; it duplicates
        # ARG PSSCRIPTANALYZER_VERSION, and the module directory carries it too.
        with self.subTest(check="the detector (self-check)"), tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "Dockerfile"

            def drift(text: str) -> list[str]:
                sample.write_text(text, encoding="utf-8")
                return _psa_version_drift(sample)

            arg = ("ARG PSSCRIPTANALYZER_VERSION=1.25.0\n"
                   "RUN x /usr/local/share/powershell/Modules/PSScriptAnalyzer/")
            self.assertEqual(drift(f"# PSScriptAnalyzer 1.25.0 (ARG below)\n{arg}${{PSSCRIPTANALYZER_VERSION}}\n"), [])
            for bad in (f"# PSScriptAnalyzer v1.24.0\n{arg}$PSSCRIPTANALYZER_VERSION\n",
                        f"# pinned: PSScriptAnalyzer\n# at 1.24.0\n{arg}$PSSCRIPTANALYZER_VERSION\n",
                        f"# PSScriptAnalyzer 1.25.0\n{arg}1.24.0\n",
                        f"# PSScriptAnalyzer 1.25.0\n{arg}\"$V\"\n",
                        "# PSScriptAnalyzer 1.25.0\nARG PSSCRIPTANALYZER_VERSION=1.25.0\n"):
                self.assertTrue(drift(bad), f"detector missed: {bad!r}")
        self.assertEqual(_psa_version_drift(GATES_DOCKERFILE), [],
                         f"every x.y.z a comment gives for PSScriptAnalyzer, and the version directory "
                         f"in /Modules/PSScriptAnalyzer/<v>, must equal ARG {PSA_VERSION_ARG}; "
                         "bump them together")


def _gate_run_leaks() -> list[str]:
    """`compose ... run ... gates|gates-it` commands in scripts/ that pass a
    daemon variable or a socket to the gate container."""
    leaks: list[str] = []
    for path in sorted((ROOT / "scripts").rglob("*")):
        if not path.is_file() or path.suffix not in (".sh", ".ps1") or "__pycache__" in path.parts:
            continue
        joined = re.sub(r"[\\`]\r?\n", " ", path.read_text(encoding="utf-8"))
        for line in joined.splitlines():
            if line.lstrip().startswith("#"):
                continue
            if re.search(r"\bcompose\b.*\brun\b.*\bgates(?:-it)?\b", line) and (
                    any(v in line for v in DAEMON_ENV) or any(s in line for s in SOCKET_TEXT)):
                leaks.append(f"{path.relative_to(ROOT).as_posix()}: {line.strip()}")
    return leaks


if __name__ == "__main__":
    unittest.main()
