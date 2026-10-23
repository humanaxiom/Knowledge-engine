"""platform-sbom U2 RED: controls for tests/test_sbom_generator.py and the U2
tests of tests/test_offline_check.py (PSC-20).

Never writes the repository. Each check function of the test module runs on
the U2 targets (docs/evidence/platform-sbom/u2/target-*) and on mutants of
them; the bundle.sh cases run the real SbomBundleTest methods against a
temporary tree (a copy of the files the bundle harness needs, with the
mutated bundle.sh and the target compose file), by patching the harness ROOT.
The offline_check.sh cases (re-target, after the architect's U2 decisions) run
the real OfflineCheckScriptTest host-half methods on a mutated
offline_check.sh, by patching the module's OFFLINE_CHECK path.

Rows: "must fail" (the check reports a problem / a test fails) or "must pass".
Exit 1 if any row is unexpected.

Usage (needs bash, git and jq: run it in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \
    --profile gates run --rm --build gates \
    uv run --locked python docs/evidence/platform-sbom/u2/u2_controls.py [--base repo]
`--base repo` uses the repository's own docker-compose.sbom.yml, bundle.sh and
generator-provenance.md as the base instead of the targets (for GREEN).
"""
from __future__ import annotations

import copy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
import yaml  # noqa: E402

from tests import compose_support as cs  # noqa: E402
from tests import test_offline_bundle as tob  # noqa: E402
from tests import test_offline_check as toc  # noqa: E402
from tests import test_sbom_generator as t  # noqa: E402

HERE = Path(__file__).resolve().parent
BASE_REPO = "--base" in sys.argv and sys.argv[sys.argv.index("--base") + 1] == "repo"
if BASE_REPO:
    COMPOSE_TEXT = (REPO / cs.SBOM_COMPOSE_NAME).read_text(encoding="utf-8")
    BUNDLE_TEXT = (REPO / "scripts" / "bundle.sh").read_text(encoding="utf-8")
    PROV_TEXT = t.PROVENANCE.read_text(encoding="utf-8")
    OFFLINE_TEXT = (REPO / "scripts" / "offline_check.sh").read_text(encoding="utf-8")
else:
    COMPOSE_TEXT = (HERE / "target-docker-compose.sbom.yml").read_text(encoding="utf-8")
    BUNDLE_TEXT = (HERE / "target-bundle.sh").read_text(encoding="utf-8")
    PROV_TEXT = (HERE / "target-generator-provenance-shape.md").read_text(encoding="utf-8")
    OFFLINE_TEXT = (HERE / "target-offline_check.sh").read_text(encoding="utf-8")
PRE_U2_OFFLINE = None  # HEAD's offline_check.sh, from git
PRE_U2_BUNDLE = None  # filled from git (HEAD's bundle.sh) when available
DATA: dict[str, Any] = yaml.load(COMPOSE_TEXT, Loader=cs._loader())  # noqa: S506, SLF001
REF = t.generator_ref(DATA)
DIGEST = REF.rsplit("@sha256:", 1)[-1]

rows: list[tuple[str, str, str, bool, str]] = []


def row(group: str, name: str, want_fail: bool, problems: list[str]) -> None:
    failed = bool(problems)
    ok = failed == want_fail
    rows.append((group, name, "must fail" if want_fail else "must pass", ok,
                 (problems[0] if problems else "no problem")[:110]))


def sub(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)


# ---- compose: pin and hardening ------------------------------------------------

def svc(d: dict[str, Any]) -> dict[str, Any]:
    return d["services"]["sbom"]


def env(d: dict[str, Any]) -> dict[str, Any]:
    return svc(d)["environment"]


def vol(d: dict[str, Any], target: str) -> dict[str, Any]:
    return next(v for v in svc(d)["volumes"] if isinstance(v, dict) and v["target"] == target)


def m(fn: Callable[[dict[str, Any]], None]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def run(d: dict[str, Any]) -> dict[str, Any]:
        d = copy.deepcopy(d)
        fn(d)
        return d
    return run


def _short(d: dict[str, Any]) -> None:
    svc(d)["volumes"] = ["${KE_SBOM_IN:?set by scripts/bundle.sh}:/in:ro",
                         "${KE_SBOM_OUT:?set by scripts/bundle.sh}:/out"]


H = "0123456789abcdef" * 4
COMPOSE_MUTANTS: list[tuple[str, bool, Callable[[dict[str, Any]], dict[str, Any]]]] = [
    ("TARGET", False, m(lambda d: None)),
    ("network_mode removed", True, m(lambda d: svc(d).pop("network_mode"))),
    ("network_mode: bridge", True, m(lambda d: svc(d).update(network_mode="bridge"))),
    ("networks: [default] instead of none", True,
     m(lambda d: (svc(d).pop("network_mode"), svc(d).update(networks=["default"])))),
    ("network_mode: host", True, m(lambda d: svc(d).update(network_mode="host"))),
    ("read_only: false", True, m(lambda d: svc(d).update(read_only=False))),
    ("read_only removed", True, m(lambda d: svc(d).pop("read_only"))),
    ("tmpfs removed", True, m(lambda d: svc(d).pop("tmpfs"))),
    ("tmpfs adds /var/tmp", True, m(lambda d: svc(d)["tmpfs"].append("/var/tmp"))),
    ("tmpfs /tmp:size=64m (still /tmp)", False, m(lambda d: svc(d).update(tmpfs=["/tmp:size=64m"]))),
    ("cap_drop removed", True, m(lambda d: svc(d).pop("cap_drop"))),
    ("cap_drop [NET_RAW]", True, m(lambda d: svc(d).update(cap_drop=["NET_RAW"]))),
    ("cap_add [SYS_ADMIN]", True, m(lambda d: svc(d).update(cap_add=["SYS_ADMIN"]))),
    ("security_opt removed", True, m(lambda d: svc(d).pop("security_opt"))),
    ("no-new-privileges:false", True, m(lambda d: svc(d).update(security_opt=["no-new-privileges:false"]))),
    ("no-new-privileges=true (equals form)", False, m(lambda d: svc(d).update(security_opt=["no-new-privileges=true"]))),
    ("security_opt + seccomp:unconfined", True, m(lambda d: svc(d)["security_opt"].append("seccomp:unconfined"))),
    ("security_opt + apparmor=unconfined", True, m(lambda d: svc(d)["security_opt"].append("apparmor=unconfined"))),
    ("privileged: true", True, m(lambda d: svc(d).update(privileged=True))),
    ("Docker socket bind added", True,
     m(lambda d: svc(d)["volumes"].append({"type": "bind", "source": "/var/run/docker.sock",
                                           "target": "/var/run/docker.sock", "read_only": True}))),
    ("DOCKER_HOST=tcp://host:2375", True, m(lambda d: env(d).update(DOCKER_HOST="tcp://host:2375"))),
    ("DOCKER_CONFIG=/out/tmp", True, m(lambda d: env(d).update(DOCKER_CONFIG="/out/tmp"))),
    ("/in read_only removed", True, m(lambda d: vol(d, "/in").pop("read_only"))),
    ("/in source ${KE_SBOM_IN:-/} (default, not required)", True,
     m(lambda d: vol(d, "/in").update(source="${KE_SBOM_IN:-/}"))),
    ("/in a named volume", True, m(lambda d: vol(d, "/in").update(type="volume", source="sbom-in"))),
    ("/out read_only: true (no writable output)", True, m(lambda d: vol(d, "/out").update(read_only=True))),
    ("/out source ./out (checkout path)", True, m(lambda d: vol(d, "/out").update(source="./out"))),
    ("extra checkout bind ./:/src:ro", True,
     m(lambda d: svc(d)["volumes"].append({"type": "bind", "source": ".", "target": "/src", "read_only": True}))),
    ("extra writable bind /cache", True,
     m(lambda d: svc(d)["volumes"].append({"type": "bind", "source": "${KE_SBOM_OUT:?x}", "target": "/cache"}))),
    ("short-syntax mounts, same meaning", False, m(_short)),
    ("SYFT_CHECK_FOR_APP_UPDATE=true", True, m(lambda d: env(d).update(SYFT_CHECK_FOR_APP_UPDATE="true"))),
    ("SYFT_CHECK_FOR_APP_UPDATE removed", True, m(lambda d: env(d).pop("SYFT_CHECK_FOR_APP_UPDATE"))),
    ("TMPDIR removed", True, m(lambda d: env(d).pop("TMPDIR"))),
    ("TMPDIR=/tmp (unpack into tmpfs memory)", True, m(lambda d: env(d).update(TMPDIR="/tmp"))),
    ("SYFT_JAVA_USE_NETWORK=true", True, m(lambda d: env(d).update(SYFT_JAVA_USE_NETWORK="true"))),
    ("SYFT_JAVA_USE_NETWORK removed", True, m(lambda d: env(d).pop("SYFT_JAVA_USE_NETWORK"))),
    ("SYFT_GOLANG_SEARCH_REMOTE_LICENSES removed", True,
     m(lambda d: env(d).pop("SYFT_GOLANG_SEARCH_REMOTE_LICENSES"))),
    ("SYFT_GOLANG_SEARCH_REMOTE_LICENSES=true", True,
     m(lambda d: env(d).update(SYFT_GOLANG_SEARCH_REMOTE_LICENSES="true"))),
    ("SYFT_JAVASCRIPT_SEARCH_REMOTE_LICENSES=true", True,
     m(lambda d: env(d).update(SYFT_JAVASCRIPT_SEARCH_REMOTE_LICENSES="true"))),
    ("SYFT_JAVASCRIPT_SEARCH_REMOTE_LICENSES removed", True,
     m(lambda d: env(d).pop("SYFT_JAVASCRIPT_SEARCH_REMOTE_LICENSES"))),
    # Re-target (N1 amendment, U2 *Env keys*): the four keys added from `syft config`.
    ("SYFT_JAVA_RESOLVE_TRANSITIVE_DEPENDENCIES removed", True,
     m(lambda d: env(d).pop("SYFT_JAVA_RESOLVE_TRANSITIVE_DEPENDENCIES"))),
    ("SYFT_JAVA_RESOLVE_TRANSITIVE_DEPENDENCIES=true", True,
     m(lambda d: env(d).update(SYFT_JAVA_RESOLVE_TRANSITIVE_DEPENDENCIES="true"))),
    ("SYFT_GOLANG_USE_PACKAGES_LIB removed", True, m(lambda d: env(d).pop("SYFT_GOLANG_USE_PACKAGES_LIB"))),
    ("SYFT_GOLANG_USE_PACKAGES_LIB=true", True, m(lambda d: env(d).update(SYFT_GOLANG_USE_PACKAGES_LIB="true"))),
    ("SYFT_PYTHON_SEARCH_REMOTE_LICENSES removed", True,
     m(lambda d: env(d).pop("SYFT_PYTHON_SEARCH_REMOTE_LICENSES"))),
    ("SYFT_PYTHON_SEARCH_REMOTE_LICENSES=true", True,
     m(lambda d: env(d).update(SYFT_PYTHON_SEARCH_REMOTE_LICENSES="true"))),
    ("SYFT_CPP_VCPKG_ALLOW_GIT_CLONE removed", True, m(lambda d: env(d).pop("SYFT_CPP_VCPKG_ALLOW_GIT_CLONE"))),
    ("SYFT_CPP_VCPKG_ALLOW_GIT_CLONE=true", True,
     m(lambda d: env(d).update(SYFT_CPP_VCPKG_ALLOW_GIT_CLONE="true"))),
    ("SYFT_CPP_VCPKG_ALLOW_GIT_CLONE=False (case-insensitive, still off)", False,
     m(lambda d: env(d).update(SYFT_CPP_VCPKG_ALLOW_GIT_CLONE="False"))),
    ("HTTPS_PROXY passed through from the host", True, m(lambda d: env(d).update(HTTPS_PROXY=None))),
    ("TMPDIR=${TMPDIR} (host interpolation)", True, m(lambda d: env(d).update(TMPDIR="${TMPDIR}"))),
    ("SYFT_JAVA_MAVEN_URL=https://repo (extra, not false)", True,
     m(lambda d: env(d).update(SYFT_JAVA_MAVEN_URL="https://repo.example"))),
    ("SYFT_GOLANG_SEARCH_LOCAL_MOD_CACHE_LICENSES=false (extra, off)", False,
     m(lambda d: env(d).update(SYFT_GOLANG_SEARCH_LOCAL_MOD_CACHE_LICENSES="false"))),
    ("HOME=/out/tmp/home (N1 fallback)", False, m(lambda d: env(d).update(HOME="/out/tmp/home"))),
    ("XDG_CACHE_HOME=/root/.cache (fallback not under /out/tmp)", True,
     m(lambda d: env(d).update(XDG_CACHE_HOME="/root/.cache"))),
    ("an unrelated key LANG=C", True, m(lambda d: env(d).update(LANG="C"))),
    ("ports 8080:80", True, m(lambda d: svc(d).update(ports=["8080:80"]))),
    ("profiles [sbom]", True, m(lambda d: svc(d).update(profiles=["sbom"]))),
    ("restart: always", True, m(lambda d: svc(d).update(restart="always"))),
    ("env_file .env", True, m(lambda d: svc(d).update(env_file=[".env"]))),
    ("devices /dev/fuse", True, m(lambda d: svc(d).update(devices=["/dev/fuse"]))),
    ("extra_hosts", True, m(lambda d: svc(d).update(extra_hosts=["x:1.2.3.4"]))),
    ("volumes_from gateway", True, m(lambda d: svc(d).update(volumes_from=["gateway"]))),
    ("pid: host", True, m(lambda d: svc(d).update(pid="host"))),
    ("ipc: host", True, m(lambda d: svc(d).update(ipc="host"))),
    ("own label: top-level name: knowledge-engine", True, m(lambda d: d.update(name="knowledge-engine"))),
    ("own label: com.docker.compose.project label", True,
     m(lambda d: svc(d).update(labels={"com.docker.compose.project": "knowledge-engine"}))),
    ("own label: container_name", True, m(lambda d: svc(d).update(container_name="ke-sbom"))),
    ("a harmless label (ke.role: sbom)", False, m(lambda d: svc(d).update(labels={"ke.role": "sbom"}))),
    ("image tag only anchore/syft:v1.2.3", True, m(lambda d: svc(d).update(image="anchore/syft:v1.2.3"))),
    ("image anchore/syft:latest@sha256:...", True, m(lambda d: svc(d).update(image="anchore/syft:latest@sha256:" + H))),
    ("image digest only anchore/syft@sha256:...", True, m(lambda d: svc(d).update(image="anchore/syft@sha256:" + H))),
    ("image 63-hex digest", True, m(lambda d: svc(d).update(image="anchore/syft:v1.2.3@sha256:" + H[:63]))),
    ("image anchore/grype", True, m(lambda d: svc(d).update(image="anchore/grype:v1.2.3@sha256:" + H))),
    ("image tag v1.2 (not X.Y.Z)", True, m(lambda d: svc(d).update(image="anchore/syft:v1.2@sha256:" + H))),
    ("service renamed syft", True, m(lambda d: d.update(services={"syft": d["services"]["sbom"]}))),
    ("an extra service `other`", True, m(lambda d: d["services"].update(other={"image": "x"}))),
    ("a sources-fetch service (U8)", False, m(lambda d: d["services"].update({"sources-fetch": {"image": "ke-gates:local"}}))),
]


def compose_controls() -> None:
    for name, want_fail, mut in COMPOSE_MUTANTS:
        d = mut(DATA)
        row("compose", name, want_fail, t.pin_problems(d) + t.hardening_problems(d))


# ---- pin place ------------------------------------------------------------------

def pin_controls() -> None:
    files = {k: v for k, v in t._repo_files().items()}  # noqa: SLF001
    files[cs.SBOM_COMPOSE_NAME] = COMPOSE_TEXT
    cases: list[tuple[str, bool, dict[str, str]]] = [
        ("TARGET", False, files),
        ("bundle.sh holds the literal reference", True,
         {**files, "scripts/bundle.sh": files["scripts/bundle.sh"] + f'\nsbom_ref="{REF}"\n'}),
        ("build.sh holds the digest only", True,
         {**files, "scripts/build.sh": files["scripts/build.sh"] + f"\nSYFT_DIGEST=sha256:{DIGEST}\n"}),
        ("compose comment repeats the reference", True,
         {**files, cs.SBOM_COMPOSE_NAME: COMPOSE_TEXT + f"# pinned: {REF}\n"}),
        ("README.md names anchore/syft:v1.2.3", True,
         {**files, "README.md": files.get("README.md", "") + "\nuse anchore/syft:v1.2.3\n"}),
        ("docker-compose.yml image anchore/syft@sha256", True,
         {**files, "docker-compose.yml": files["docker-compose.yml"] + f"\n# anchore/syft@sha256:{DIGEST}\n"}),
        ("ci.yml pulls anchore/syft:v0", True,
         {**files, ".github/workflows/ci.yml": files.get(".github/workflows/ci.yml", "") + "\n# docker pull anchore/syft:v0\n"}),
        ("docs/ quotes the pin (exempt)", False, {**files, "docs/x.md": REF}),
        ("tests/ quote the pin (exempt)", False, {**files, "tests/x.py": REF}),
        ("prose 'anchore/syft' without tag", False, {**files, "README.md": files.get("README.md", "") + "\nSBOMs by anchore/syft.\n"}),
        ("compose file not committed or new (ignored)", True,
         {k: v for k, v in files.items() if k != cs.SBOM_COMPOSE_NAME}),
    ]
    for name, want_fail, f in cases:
        row("pin place", name, want_fail, t.pin_place_problems(f, DIGEST))


# ---- provenance shape -----------------------------------------------------------

def provenance_controls() -> None:
    ver = t.GENERATOR_REF.match(REF).group(1)  # type: ignore[union-attr]
    cases = [
        ("TARGET (shape fixture)", False, PROV_TEXT),
        ("record missing", True, None),
        ("digest missing", True, PROV_TEXT.replace(DIGEST, "")),
        ("digest truncated", True, PROV_TEXT.replace(DIGEST, DIGEST[:40])),
        ("other release named", True, PROV_TEXT.replace(f"v{ver}", "v9.9.9")),
        ("release with an extra digit", True, PROV_TEXT.replace(f"v{ver}", f"v{ver}1")),
        ("image not named", True, PROV_TEXT.replace("anchore/syft", "the generator")),
    ]
    for name, want_fail, text in cases:
        row("provenance", name, want_fail, t.provenance_problems(REF, text))


# ---- bundle.sh static -----------------------------------------------------------

ANCHOR = "# --- licence notices (PS-3.8)"


def bundle_static_controls() -> None:
    b = BUNDLE_TEXT
    cases = [
        ("TARGET", False, b),
        ("pre-U2 bundle.sh (no generator read)", True, PRE_U2_BUNDLE or ""),
        ("adds docker pull \"$sbom_ref\"", True, sub(b, ANCHOR, 'docker pull "$sbom_ref"\n' + ANCHOR)),
        ("adds compose -f docker-compose.sbom.yml pull sbom", True,
         sub(b, ANCHOR, "docker compose -f docker-compose.sbom.yml pull sbom\n" + ANCHOR)),
        ("adds docker image pull", True, sub(b, ANCHOR, 'docker image pull "$sbom_ref"\n' + ANCHOR)),
        ("notices run --pull missing", True, sub(b, "--pull never --label", "--pull missing --label")),
        ("notices run --pull=always", True, sub(b, "--pull never --label", "--pull=always --label")),
        ("a pull word in a die message only", False,
         sub(b, ANCHOR, 'true || die "pull it first"\n' + ANCHOR)),
        ("a pull word in a comment only", False, sub(b, ANCHOR, "# pull it with bundle_fetch.sh\n" + ANCHOR)),
    ]
    for name, want_fail, text in cases:
        row("bundle static", name, want_fail, t.bundle_static_problems(text))


# ---- bundle.sh behaviour (the real test methods, patched tree) -------------------

class Collect(unittest.TestResult):
    def __init__(self) -> None:
        super().__init__()
        self.failed: list[str] = []

    def addSubTest(self, test: Any, subtest: Any, err: Any) -> None:  # noqa: N802
        if err is not None:
            self.failed.append(f"{test._testMethodName} {subtest._subDescription()}")  # noqa: SLF001

    def addFailure(self, test: Any, err: Any) -> None:  # noqa: N802
        self.failed.append(f"{test._testMethodName}: {str(err[1]).splitlines()[0][:80]}")  # noqa: SLF001

    def addError(self, test: Any, err: Any) -> None:  # noqa: N802
        self.failed.append(f"{test._testMethodName} ERROR: {err[1]!r}"[:120])  # noqa: SLF001


def run_bundle(bundle_text: str) -> list[str]:
    tree = Path(tempfile.mkdtemp(prefix="u2tree-"))
    try:
        for rel in (*tob._REPO_COPY, "engine"):  # noqa: SLF001
            src = REPO / rel
            if src.is_dir():
                shutil.copytree(src, tree / rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            elif src.is_file():
                (tree / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, tree / rel)
        (tree / cs.SBOM_COMPOSE_NAME).write_text(COMPOSE_TEXT, encoding="utf-8", newline="\n")
        (tree / "scripts" / "bundle.sh").write_text(bundle_text, encoding="utf-8", newline="\n")
        with mock.patch.object(tob, "ROOT", tree), \
                mock.patch.object(t, "BUNDLE_SH", tree / "scripts" / "bundle.sh"), \
                mock.patch.object(t, "SBOM_COMPOSE", tree / cs.SBOM_COMPOSE_NAME):
            suite = unittest.TestSuite([t.SbomBundleTest("test_bundle_refuses_when_sbom_generator_absent"),
                                        t.SbomBundleTest("test_bundle_has_no_sbom_generator")])
            res = Collect()
            suite.run(res)
        return res.failed
    finally:
        shutil.rmtree(tree, ignore_errors=True)


SNIP_INSPECT = ('docker image inspect --format \'{{.Id}}\' "$sbom_ref" > /dev/null 2>&1 \\\n'
                '  || die "the SBOM generator image is not present ($sbom_ref); pull it first with: '
                'docker pull $sbom_ref; this script never pulls"\n')
SNIP_READ = ('sbom_ref="$(KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent \\\n'
             '  docker compose --env-file .env.example -f docker-compose.sbom.yml config --images sbom)" \\\n')


def bundle_behaviour_controls() -> None:
    b = BUNDLE_TEXT
    snippet_start = b.index("# --- the SBOM generator (PSC-20")
    snippet = b[snippet_start:b.index(ANCHOR)]
    late = b.replace(snippet, "")
    late = sub(late, 'mkdir -p -- "$out/images"\n', 'mkdir -p -- "$out/images"\n' + snippet)
    cases = [
        ("TARGET", False, b),
        ("pre-U2 bundle.sh (RED reach)", True, PRE_U2_BUNDLE or ""),
        ("presence inspect removed", True, sub(b, SNIP_INSPECT, ":\n")),
        ("inspect result ignored (|| true)", True,
         sub(b, SNIP_INSPECT, 'docker image inspect "$sbom_ref" > /dev/null 2>&1 || true\n')),
        ("check moved after mkdir of --out/images", True, late),
        ("reference hardcoded, compose not read", True,
         sub(b, SNIP_READ, f'sbom_ref="$(printf %s {REF})" \\\n')),
        ("@sha256 not required (tag-only accepted)", True,
         sub(b, '[[ "$sbom_ref" =~ $ref_re && "$sbom_ref" == *"@sha256:"* ]]', '[[ "$sbom_ref" =~ $ref_re ]]')),
        ("config --images without the sbom service", True,
         sub(b, "config --images sbom)", "config --images)")),
        ("required ${VAR:?} mounts not set for the read", True,
         sub(b, "KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent \\\n  docker compose", "docker compose")),
        ("--no-interpolate instead of the dummy values (env-file kept)", False,
         sub(b, "KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent \\\n"
                "  docker compose --env-file .env.example -f docker-compose.sbom.yml config",
             "docker compose --env-file .env.example -f docker-compose.sbom.yml config --no-interpolate")),
        # Re-target (N1 amendment, U2): --env-file .env.example on the read.
        ("read without --env-file .env.example (loads .env)", True,
         sub(b, "docker compose --env-file .env.example -f docker-compose.sbom.yml config",
             "docker compose -f docker-compose.sbom.yml config")),
        ("read with --env-file .env (the model keys)", True,
         sub(b, "docker compose --env-file .env.example -f docker-compose.sbom.yml config",
             "docker compose --env-file .env.example --env-file .env -f docker-compose.sbom.yml config")),
        ("refusal does not name the reference", True,
         sub(b, 'not present ($sbom_ref); pull', 'not present; pull')),
        ("refusal names bundle_fetch.sh (U8 wording, too early)", True,
         sub(b, "pull it first with: docker pull $sbom_ref;", "run scripts/bundle_fetch.sh first;")),
        ("refusal without the pull command", True,
         sub(b, "pull it first with: docker pull $sbom_ref;", "pull it first;")),
        ("pulls when absent", True,
         sub(b, SNIP_INSPECT, 'docker image inspect "$sbom_ref" > /dev/null 2>&1 || docker pull "$sbom_ref" '
                              '> /dev/null 2>&1 \\\n  || die "the SBOM generator image is not present ($sbom_ref)"\n')),
        ("ships docker-compose.sbom.yml in app/", True,
         sub(b, 'cp -- docker-compose.yml .env.example "$app/"\n',
             'cp -- docker-compose.yml .env.example docker-compose.sbom.yml "$app/"\n')),
        ("saves the generator image into the bundle", True,
         sub(b, 'app="$out/app"\n', 'docker save -o "$out/images/syft.tar" "$sbom_ref"\napp="$out/app"\n')),
    ]
    for name, want_fail, text in cases:
        failed = run_bundle(text)
        row("bundle run", name, want_fail, failed)
        if failed:
            for f in failed:
                rows.append(("", "", "", True, "  - " + f[:150]))


# ---- offline_check.sh: the interim pull (re-target) ------------------------------

OFFLINE_METHODS = ("test_offline_check_pulls_sbom_generator_before_bundle",
                   "test_offline_check_stops_when_sbom_pull_fails",
                   # existing host-half tests: the pull must not break them
                   "test_offline_check_host_half_runs_stages_in_order",
                   "test_offline_check_tears_down_on_failure")
PULL = ('KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent \\\n'
        '  docker compose --env-file .env.example -f docker-compose.sbom.yml pull sbom \\\n'
        '  || die "pulling the SBOM generator failed (docker-compose.sbom.yml, service sbom); no retry"\n')
BUNDLE_LINE = 'bash scripts/bundle.sh --out "$bundle_rel" || die "bundle.sh failed"\n'
DISK_ANCHOR = "df_log \"start\"\n"


def run_offline(text: str) -> list[str]:
    tmp = Path(tempfile.mkdtemp(prefix="u2oc-"))
    try:
        script = tmp / "offline_check.sh"
        script.write_text(text, encoding="utf-8", newline="\n")
        with mock.patch.object(toc, "OFFLINE_CHECK", script):
            suite = unittest.TestSuite([toc.OfflineCheckScriptTest(n) for n in OFFLINE_METHODS])
            res = Collect()
            suite.run(res)
        return res.failed
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def offline_controls() -> None:
    o = OFFLINE_TEXT
    no_pull = sub(o, PULL, "")
    cases = [
        ("TARGET", False, o),
        ("pre-U2 offline_check.sh (no pull; RED reach)", True, PRE_U2_OFFLINE or ""),
        ("pull after bundle.sh", True, sub(no_pull, BUNDLE_LINE, BUNDLE_LINE + PULL)),
        ("pull before the disk and Compose checks", True, sub(no_pull, DISK_ANCHOR, PULL + DISK_ANCHOR)),
        ("pull without --env-file .env.example", True,
         sub(o, "docker compose --env-file .env.example -f docker-compose.sbom.yml pull",
             "docker compose -f docker-compose.sbom.yml pull")),
        ("pull through compose() (adds --profile offline)", True,
         sub(o, "  docker compose --env-file .env.example -f docker-compose.sbom.yml pull",
             "  compose -f docker-compose.sbom.yml pull")),
        ("pull without the dummy KE_SBOM_* values", True,
         sub(o, "KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent \\\n  docker compose", "docker compose")),
        ("only KE_SBOM_IN set", True,
         sub(o, "KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent \\\n", "KE_SBOM_IN=/nonexistent \\\n")),
        ("pulls every service of the file", True,
         sub(o, "docker-compose.sbom.yml pull sbom \\\n", "docker-compose.sbom.yml pull \\\n")),
        ("docker pull of a literal ref instead of compose", True,
         sub(o, "  docker compose --env-file .env.example -f docker-compose.sbom.yml pull sbom",
             f"  docker pull {REF}")),
        ("pull failure ignored (|| true)", True,
         sub(o, '  || die "pulling the SBOM generator failed (docker-compose.sbom.yml, service sbom); no retry"\n',
             "  || true\n")),
        ("retries once on failure", True,
         sub(o, '  || die "pulling the SBOM generator failed',
             "  || docker compose --env-file .env.example -f docker-compose.sbom.yml pull sbom \\\n"
             '  || die "pulling the SBOM generator failed')),
        ("other failure message", True,
         sub(o, "pulling the SBOM generator failed (docker-compose.sbom.yml, service sbom); no retry",
             "could not pull syft")),
        ("echo line removed (not required)", False,
         sub(o, 'echo "offline: pulling the SBOM generator (docker-compose.sbom.yml, service sbom)"\n', "")),
        ("-f before --env-file (same meaning)", False,
         sub(o, "docker compose --env-file .env.example -f docker-compose.sbom.yml pull",
             "docker compose -f docker-compose.sbom.yml --env-file .env.example pull")),
    ]
    for name, want_fail, text in cases:
        failed = run_offline(text)
        row("offline_check", name, want_fail, failed)
        if failed:
            for f in failed:
                rows.append(("", "", "", True, "  - " + f[:150]))


def _show(spec: str) -> str | None:
    import subprocess
    try:
        return subprocess.run(["git", "-C", str(REPO), "show", spec], capture_output=True,
                              text=True, check=True).stdout
    except Exception:  # noqa: BLE001
        return None


def _pre_u2() -> str | None:
    return _show("23e3c9b:scripts/bundle.sh")


if __name__ == "__main__":
    PRE_U2_BUNDLE = _pre_u2()
    PRE_U2_OFFLINE = _show("23e3c9b:scripts/offline_check.sh")
    compose_controls()
    pin_controls()
    provenance_controls()
    bundle_static_controls()
    bundle_behaviour_controls()
    offline_controls()
    unexpected = 0
    for group, name, want, ok, why in rows:
        if not group:
            print(f"{'':13} {why}")
            continue
        unexpected += 0 if ok else 1
        print(f"{group:13} | {name[:58]:58} | {want:9} | {'ok' if ok else 'UNEXPECTED'} | {why}")
    counted = [r for r in rows if r[0]]
    print(f"\ncontrols: {len(counted)} ({sum(1 for r in counted if r[2] == 'must fail')} must-fail, "
          f"{sum(1 for r in counted if r[2] == 'must pass')} must-pass), unexpected: {unexpected}")
    sys.exit(1 if unexpected else 0)
