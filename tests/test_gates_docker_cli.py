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
"""

from __future__ import annotations

import re
import shlex
import unittest
from dataclasses import dataclass

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
