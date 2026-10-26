"""platform-sbom U3 RED: controls for tests/test_sbom_bundle.py and the U3
edits to tests/test_sbom_generator.py and tests/test_offline_check.py.

Never writes the repository. Each check function runs on the U3 targets
(docs/evidence/platform-sbom/u3/target-*) and on mutants of them. The bundle
cases run the real SbomBundleRunTest / SbomCheckModuleTest methods against a
temporary tree (the files the bundle harness needs, with the target or
mutated bundle.sh, sbom_check.py and compose file), by patching the harness
ROOT and the module paths. The offline_check cases run the real U2 host-half
test on a mutated offline_check.sh (OFFLINE_CHECK patched).

Rows: "must fail" (a check reports a problem / a test fails) or "must pass".
Exit 1 if any row is unexpected.

Usage (needs bash, git and jq: run it in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \
    --profile gates run --rm gates \
    uv run --locked python docs/evidence/platform-sbom/u3/u3_controls.py [--base repo]
`--base repo` uses the repository's own files as the base instead of the
targets (for GREEN).
"""
from __future__ import annotations

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
from tests import test_sbom_bundle as tsb  # noqa: E402
from tests import test_sbom_generator as tsg  # noqa: E402

HERE = Path(__file__).resolve().parent
BASE_REPO = "--base" in sys.argv and sys.argv[sys.argv.index("--base") + 1] == "repo"
if BASE_REPO:
    BUNDLE = (REPO / "scripts" / "bundle.sh").read_text(encoding="utf-8")
    CHECK = (REPO / "scripts" / "sbom_check.py").read_text(encoding="utf-8")
    COMPOSE = (REPO / cs.SBOM_COMPOSE_NAME).read_text(encoding="utf-8")
    OFFLINE = (REPO / "scripts" / "offline_check.sh").read_text(encoding="utf-8")
else:
    BUNDLE = (HERE / "target-bundle.sh").read_text(encoding="utf-8")
    CHECK = (HERE / "target-sbom_check.py").read_text(encoding="utf-8")
    COMPOSE = (HERE / "target-docker-compose.sbom.yml").read_text(encoding="utf-8")
    OFFLINE = (HERE / "target-offline_check.sh").read_text(encoding="utf-8")
SCAN = (REPO / "docker-compose.scan.yml").read_text(encoding="utf-8")
PRE_U3_OFFLINE = __import__("subprocess").run(
    ["git", "-C", str(REPO), "show", "HEAD:scripts/offline_check.sh"], capture_output=True, text=True).stdout

rows: list[tuple[str, str, str, bool, str]] = []


def row(group: str, name: str, want_fail: bool, problems: list[str]) -> None:
    ok = bool(problems) == want_fail
    rows.append((group, name, "must fail" if want_fail else "must pass", ok,
                 (problems[0] if problems else "no problem")[:110]))


def sub(text: str, old: str, new: str, count: int = 1) -> str:
    assert text.count(old) == count, (old, text.count(old))
    return text.replace(old, new)


def load(text: str) -> dict[str, Any]:
    return yaml.load(text, Loader=cs._loader()) or {}  # noqa: S506, SLF001


# ---- static: compose user (L-2), I-2, L-1 ---------------------------------------

USER_LINE = "    user: ${KE_SBOM_USER:?set by scripts/bundle.sh}\n"


def compose_controls() -> None:
    g = "compose"
    row(g, "TARGET user", False, tsb.user_problems(load(COMPOSE)))
    row(g, "TARGET hardening (U2 + I-2)", False, tsg.hardening_problems(load(COMPOSE)))
    row(g, "no user", True, tsb.user_problems(load(sub(COMPOSE, USER_LINE, ""))))
    row(g, 'user: "0:0"', True, tsb.user_problems(load(sub(COMPOSE, USER_LINE, '    user: "0:0"\n'))))
    row(g, "user ${KE_SBOM_USER:-}", True,
        tsb.user_problems(load(sub(COMPOSE, USER_LINE, "    user: ${KE_SBOM_USER:-}\n"))))
    row(g, "user ${KE_SBOM_UID:?x}", True,
        tsb.user_problems(load(sub(COMPOSE, USER_LINE, "    user: ${KE_SBOM_UID:?x}\n"))))

    def env(extra: dict[str, str]) -> list[str]:
        d = load(COMPOSE)
        d["services"]["sbom"]["environment"].update(extra)
        return tsg.hardening_problems(d)
    row(g, "HOME=/out/tmp (I-2)", True, env({"HOME": "/out/tmp"}))
    row(g, "HOME=/out/tmp/home (I-2)", True, env({"HOME": "/out/tmp/home"}))
    row(g, "XDG_CACHE_HOME=/out/cache (I-2)", True, env({"XDG_CACHE_HOME": "/out/cache"}))
    row(g, "HOME=/tmp/../out (I-2)", True, env({"HOME": "/tmp/../out"}))
    row(g, "HOME=/tmp/home", False, env({"HOME": "/tmp/home"}))
    row(g, "XDG_CACHE_HOME=/tmp", False, env({"XDG_CACHE_HOME": "/tmp"}))

    def top(text: str, file: str = cs.SBOM_COMPOSE_NAME, allowed: set[str] | None = None) -> list[str]:
        allowed = {"services"} if allowed is None else allowed
        return tsb.top_level_problems(load(text), text, file, allowed)
    row(g, "TARGET top level", False, top(COMPOSE))
    row(g, "top-level include (L-1)", True, top("include:\n  - https://example.invalid/x.yml\n" + COMPOSE))
    row(g, "top-level volumes", True, top(COMPOSE + "volumes:\n  v: {}\n"))
    row(g, "top-level networks", True, top(COMPOSE + "networks:\n  n: {}\n"))
    row(g, "top-level name", True, top("name: fixed\n" + COMPOSE))
    row(g, "x-anchor", False, top("x-common: &c\n  read_only: true\n" + COMPOSE))
    row(g, "extends on sbom (L-1)", True,
        top(sub(COMPOSE, "    network_mode: none\n", "    network_mode: none\n    extends:\n      file: other.yml\n"
                "      service: x\n")))
    scan = dict(file="docker-compose.scan.yml", allowed={"services", "volumes"})
    row(g, "scan TARGET (as committed)", False, top(SCAN, **scan))
    row(g, "scan + include (L-1)", True, top("include:\n  - other.yml\n" + SCAN, **scan))
    row(g, "scan + extends (L-1)", True,
        top(sub(SCAN, "    network_mode: none\n", "    network_mode: none\n    extends: scan-db\n"), **scan))


# ---- static: sbom_check.py stdlib, offline header ----------------------------------

def check_static_controls() -> None:
    g = "sbom_check static"
    row(g, "TARGET", False, tsb.stdlib_problems(CHECK))
    row(g, "import yaml", True, tsb.stdlib_problems("import yaml\n" + CHECK))
    row(g, "from packaging import version", True, tsb.stdlib_problems("from packaging import version\n" + CHECK))
    row(g, "no validate()", True, tsb.stdlib_problems(sub(CHECK, "def validate(", "def check_doc(")
                                                        .replace("validate(doc)", "check_doc(doc)")))
    row(g, "no __main__", True, tsb.stdlib_problems(sub(CHECK, 'if __name__ == "__main__":\n    sys.exit(main(sys.argv[1:]))\n', "")))
    g = "offline header"
    row(g, "TARGET", False, tsb.offline_header_problems(OFFLINE))
    row(g, "pre-U3 (HEAD)", True, tsb.offline_header_problems(PRE_U3_OFFLINE))
    row(g, "pull after bundle.sh", True, tsb.offline_header_problems(
        sub(OFFLINE, "disk floor (7 GiB) -> SBOM generator pull -> bundle.sh ->",
            "disk floor (7 GiB) -> bundle.sh -> SBOM generator pull ->")))


# ---- the tree for the bundle and module cases ---------------------------------------

class Collect(unittest.TestResult):
    def __init__(self) -> None:
        super().__init__()
        self.failed: list[str] = []

    def addSubTest(self, test: Any, subtest: Any, err: Any) -> None:  # noqa: N802
        if err is not None:
            self.failed.append(f"{test._testMethodName} {subtest._subDescription()}: "  # noqa: SLF001
                               f"{str(err[1]).splitlines()[0][:70]}")

    def addFailure(self, test: Any, err: Any) -> None:  # noqa: N802
        self.failed.append(f"{test._testMethodName}: {str(err[1]).splitlines()[0][:80]}")  # noqa: SLF001

    def addError(self, test: Any, err: Any) -> None:  # noqa: N802
        self.failed.append(f"{test._testMethodName} ERROR: {err[1]!r}"[:120])  # noqa: SLF001


def run_tree(tests: list[unittest.TestCase], *, bundle: str = BUNDLE, check: str | None = CHECK,
             compose: str = COMPOSE, extra: Callable[[Path], None] | None = None) -> list[str]:
    tree = Path(tempfile.mkdtemp(prefix="u3tree-"))
    try:
        for rel in (*tob._REPO_COPY, "engine", "harness_telemetry", "docker", "docker-compose.scan.yml"):  # noqa: SLF001
            src = REPO / rel
            if src.is_dir():
                shutil.copytree(src, tree / rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            elif src.is_file():
                (tree / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, tree / rel)
        (tree / cs.SBOM_COMPOSE_NAME).write_text(compose, encoding="utf-8", newline="\n")
        (tree / "scripts" / "bundle.sh").write_text(bundle, encoding="utf-8", newline="\n")
        (tree / "scripts" / "offline_check.sh").write_text(OFFLINE, encoding="utf-8", newline="\n")
        if check is not None:
            (tree / "scripts" / "sbom_check.py").write_text(check, encoding="utf-8", newline="\n")
        if extra:
            extra(tree)
        with mock.patch.object(tob, "ROOT", tree), mock.patch.object(cs, "ROOT", tree), \
                mock.patch.object(tsb, "ROOT", tree), \
                mock.patch.object(tsb, "SBOM_COMPOSE", tree / cs.SBOM_COMPOSE_NAME), \
                mock.patch.object(tsb, "SBOM_CHECK", tree / "scripts" / "sbom_check.py"), \
                mock.patch.object(tsb, "OFFLINE_CHECK", tree / "scripts" / "offline_check.sh"), \
                mock.patch.object(tsb, "SCAN_COMPOSE", tree / "docker-compose.scan.yml"):
            res = Collect()
            unittest.TestSuite(tests).run(res)
        return res.failed
    finally:
        shutil.rmtree(tree, ignore_errors=True)


R = tsb.SbomBundleRunTest
M = tsb.SbomCheckModuleTest
PER_IMAGE = "test_bundle_has_sbom_per_image"
SPDX = "test_sbom_is_spdx_2_3"
RUNTIME = "test_sbom_lists_every_locked_runtime_package"
PINNED = "test_sbom_generator_run_is_pinned"
ARCH = "test_sbom_generator_is_daemon_arch"
DASH = "test_bundle_refuses_ref_starting_with_dash"
FAILURE = "test_bundle_refuses_on_sbom_failure"
ALL_RUN = [PER_IMAGE, SPDX, RUNTIME, PINNED, ARCH, DASH, FAILURE]


def bundle_rows(group: str, cases: list[tuple[str, bool, list[str], dict[str, Any]]]) -> None:
    for name, want_fail, methods, kw in cases:
        row(group, name, want_fail, run_tree([R(m) for m in methods], **kw))


RUN_LINE = ('    docker compose -p "$sbom_project" --env-file .env.example -f docker-compose.sbom.yml \\\n'
            '    run --rm --pull never sbom "docker-archive:/in/$name.tar" --scope all-layers '
            '-o spdx-json=/out/raw.spdx.json \\\n')
RUN_ENV = '  KE_SBOM_IN="$out/images" KE_SBOM_OUT="$work" KE_SBOM_USER="$sbom_user" \\\n'
DOWN_LINE = 'docker compose -p "$sbom_project" --env-file .env.example -f docker-compose.sbom.yml down ) \\\n'
DOWN_ENV = '      && KE_SBOM_IN="$out/images" KE_SBOM_OUT="$sbom_work" KE_SBOM_USER="$sbom_user" \\\n'
B = BUNDLE


def bundle_controls() -> None:
    g = "bundle.sh"
    cases: list[tuple[str, bool, list[str], dict[str, Any]]] = [
        ("TARGET", False, ALL_RUN, {}),
        ("run: no --env-file", True, [PINNED], {"bundle": sub(B, RUN_LINE, RUN_LINE.replace(" --env-file .env.example", ""))}),
        ("run: no --pull never", True, [PINNED], {"bundle": sub(B, RUN_LINE, RUN_LINE.replace(" --pull never", ""))}),
        ("run: -p <project> (not -sbom)", True, [PINNED],
         {"bundle": sub(B, RUN_LINE, RUN_LINE.replace('-p "$sbom_project"', '-p "$project"'))}),
        ("run: --scope squashed", True, [PINNED], {"bundle": sub(B, RUN_LINE, RUN_LINE.replace("all-layers", "squashed"))}),
        ("run: -o spdx-json=/out/sbom.json", True, [PINNED],
         {"bundle": sub(sub(B, RUN_LINE, RUN_LINE.replace("/out/raw.spdx.json", "/out/sbom.json")),
                        "--raw /work/raw.spdx.json", "--raw /work/sbom.json")}),
        ("run: extra -e option", True, [PINNED], {"bundle": sub(B, RUN_LINE, RUN_LINE.replace("run --rm", "run --rm -e X=1"))}),
        ("run: -T added (allowed)", False, [PINNED], {"bundle": sub(B, RUN_LINE, RUN_LINE.replace("run --rm", "run --rm -T"))}),
        ("run: globals reordered (allowed)", False, [PINNED],
         {"bundle": sub(B, RUN_LINE, RUN_LINE.replace('-p "$sbom_project" --env-file .env.example',
                                                      '--env-file .env.example -p "$sbom_project"'))}),
        ("run: KE_SBOM_IN=$out", True, [PINNED], {"bundle": sub(B, RUN_ENV, RUN_ENV.replace('"$out/images"', '"$out"'))}),
        ("run: KE_SBOM_USER=0:0", True, [PINNED], {"bundle": sub(B, RUN_ENV, RUN_ENV.replace('"$sbom_user"', "0:0"))}),
        ("run: no KE_SBOM_USER", True, [PER_IMAGE], {"bundle": sub(B, RUN_ENV, RUN_ENV.replace(' KE_SBOM_USER="$sbom_user"', ""))}),
        ("work dir inside --out", True, [PER_IMAGE, PINNED],
         {"bundle": sub(B, 'sbom_work="$(mktemp -d "${TMPDIR:-/tmp}/ke-sbom.XXXXXXXX")"',
                        'sbom_work="$out/sbom-work"; mkdir -p -- "$sbom_work"')}),
        ("one shared work dir", True, [PINNED],
         {"bundle": sub(B, '  work="$sbom_work/$name"\n  mkdir -m 0700 -- "$work" "$work/tmp"',
                        '  work="$sbom_work/shared"\n  mkdir -p -m 0700 -- "$work/tmp"')}),
        ("no tmp/ in the work dir", True, [PER_IMAGE],
         {"bundle": sub(B, 'mkdir -m 0700 -- "$work" "$work/tmp"', 'mkdir -m 0700 -- "$work"')}),
        ("work dir not removed", True, [PINNED],
         {"bundle": sub(B, '  if [ -n "$sbom_work" ]; then rm -rf -- "$sbom_work"; fi\n', "")}),
        ("no down", True, [PINNED], {"bundle": sub(B, DOWN_LINE, DOWN_LINE.replace(" down )", " ps )"))}),
        ("down: no KE_SBOM_USER", True, [PINNED], {"bundle": sub(B, DOWN_ENV, DOWN_ENV.replace(' KE_SBOM_USER="$sbom_user"', ""))}),
        ("down: no --env-file", True, [PINNED], {"bundle": sub(B, DOWN_LINE, DOWN_LINE.replace(" --env-file .env.example", ""))}),
        ("down: --remove-orphans (allowed)", False, [PINNED], {"bundle": sub(B, DOWN_LINE, DOWN_LINE.replace(" down )", " down --remove-orphans )"))}),
        ("no trap", True, [PINNED, FAILURE], {"bundle": sub(B, "trap sbom_cleanup EXIT\n", "")}),
        ("no generator arch check", True, [ARCH],
         {"bundle": sub(B, '[ "$sbom_platform" = "linux/$arch" ] \\\n', '[ "$sbom_platform" = "$sbom_platform" ] \\\n')}),
        ("ref_re allows a leading -", True, [DASH],
         {"bundle": sub(B, "ref_re='^[a-z0-9][a-z0-9._/-]*", "ref_re='^[a-z0-9._/-]+")}),
        ("checker: no --network none", True, [PINNED], {"bundle": sub(B, "docker run --rm --network none --read-only",
                                                                      "docker run --rm --read-only")}),
        ("checker: no --read-only", True, [PINNED], {"bundle": sub(B, "--network none --read-only --cap-drop ALL",
                                                                   "--network none --cap-drop ALL")}),
        ("checker: no --cap-drop ALL", True, [PINNED], {"bundle": sub(B, " --cap-drop ALL --security-opt", " --security-opt")}),
        ("checker: label -notices", True, [PINNED], {"bundle": sub(B, "${project}-sbomcheck", "${project}-notices")}),
        ("checker: work mount writable", True, [PINNED], {"bundle": sub(B, '-v "$work:/work:ro"', '-v "$work:/work"')}),
        ("checker: no -I", True, [PINNED], {"bundle": sub(B, '"$app_ref" -I /opt/ke', '"$app_ref" /opt/ke')}),
        ("checker: runs in the gateway image", True, [PINNED, RUNTIME],
         {"bundle": sub(B, '--entrypoint python "$app_ref" -I', '--entrypoint python "${vendor_refs[0]}" -I')}),
        ("SBOMs at $out/sboms", True, [PER_IMAGE],
         {"bundle": sub(sub(B, 'mkdir -p -- "$app/sboms"', 'mkdir -p -- "$out/sboms"'),
                        '> "$app/sboms/$name.spdx.json"', '> "$out/sboms/$name.spdx.json"')}),
        ("SBOMs left out of the manifest", True, [PER_IMAGE],
         {"bundle": sub(B, "find . -type f -print0", "find . -type f -not -path './app/sboms/*' -print0")}),
        ("no ke-app runtime check", True, [RUNTIME], {"bundle": sub(B, '  if [ "$ref" = "$app_ref" ]; then\n',
                                                                    '  if false; then\n')}),
        # Equivalent mutant: with a fresh work dir there is no raw document, so
        # the checker refuses the bundle naming the image anyway (defence in depth).
        ("syft failure ignored (equivalent: checker refuses, no raw doc)", False, [FAILURE],
         {"bundle": sub(B, '>&2 || die "SBOM generation failed', '>&2 || true || die "SBOM generation failed')}),
        ("checker failure ignored", True, [RUNTIME, FAILURE],
         {"bundle": sub(B, '> "$app/sboms/$name.spdx.json" || die', '> "$app/sboms/$name.spdx.json" || true || die')}),
    ]
    bundle_rows(g, cases)


C = CHECK


def check_controls() -> None:
    g = "sbom_check.py"
    ann = '''    doc["annotations"] = list(doc.get("annotations") or []) + [
        {"annotationDate": now, "annotationType": "OTHER", "annotator": tool, "comment": f"ke:{k}={v}"}
        for k, v in (("ref", a.ref), ("arch", a.arch), ("image-config", digest))]
'''
    cases: list[tuple[str, bool, list[str], dict[str, Any]]] = [
        ("TARGET (validate table, module)", False, [SPDX], {}),
        ("no annotations", True, [PER_IMAGE], {"check": sub(C, ann, "")}),
        ("annotationType REVIEW", True, [PER_IMAGE], {"check": sub(C, '"annotationType": "OTHER"', '"annotationType": "REVIEW"')}),
        ("annotator not the bundle tool", True, [PER_IMAGE], {"check": sub(C, '"annotator": tool', '"annotator": "Tool: x"')}),
        ("ke:ref is the name", True, [PER_IMAGE], {"check": sub(C, '(("ref", a.ref)', '(("ref", a.name)')}),
        ("name not set to the ref", True, [PER_IMAGE], {"check": sub(C, '    doc["name"] = a.ref\n', "")}),
        ("legacy Config unsupported", True, [PER_IMAGE],
         {"check": sub(C, ' or re.fullmatch(r"([0-9a-f]{64})\\.json", cfg)', "")}),
        ("multi-image tar accepted", True, [PER_IMAGE],
         {"check": sub(C, "if not isinstance(manifest, list) or len(manifest) != 1:", "if not isinstance(manifest, list):")}),
        # Orchestrator ruling (option b): a fresh urn:uuid:<uuid4> per document.
        ("namespace not set (syft's https kept)", True, [SPDX],
         {"check": sub(C, '    doc["documentNamespace"] = f"urn:uuid:{uuid.uuid4()}"\n', "")}),
        ("namespace constant", True, [SPDX],
         {"check": sub(C, 'f"urn:uuid:{uuid.uuid4()}"', '"urn:uuid:0f8fad5b-d9cb-469f-a165-70867728950e"')}),
        ("namespace stable per image (v4-shaped hash of the name): second run repeats", True, [SPDX],
         {"check": sub(C, 'f"urn:uuid:{uuid.uuid4()}"',
                       'f"urn:uuid:{uuid.UUID(bytes=__import__(\'hashlib\').sha256(a.name.encode()).digest()[:16], '
                       'version=4)}"')}),
        ("namespace shared by the bundle (per-run uuid from bundle.sh)", True, [SPDX],
         {"check": sub(sub(C, 'f"urn:uuid:{uuid.uuid4()}"', 'f"urn:uuid:{a.ns or uuid.uuid4()}"'),
                       '    f.add_argument("--site")\n', '    f.add_argument("--site")\n    f.add_argument("--ns")\n'),
          "bundle": sub(sub(B, "trap sbom_cleanup EXIT\n",
                            'trap sbom_cleanup EXIT\nrun_ns="$(cat /proc/sys/kernel/random/uuid)"\n'),
                        '--git-sha "$git_sha" \\\n', '--git-sha "$git_sha" --ns "$run_ns" \\\n')}),
        ("syft creator dropped", True, [SPDX], {"check": sub(C, "creators = list(info.get(\"creators\") or [])",
                                                            "creators = []")}),
        ("created rewritten", True, [SPDX], {"check": sub(C, '    doc["creationInfo"] = info\n',
                                                         '    info["created"] = "2000-01-01T00:00:00Z"\n'
                                                         '    doc["creationInfo"] = info\n')}),
        ("packages dropped (root only)", True, [RUNTIME],
         {"check": sub(C, '    doc["name"] = a.ref\n', '    doc["name"] = a.ref\n'
                       '    doc["packages"] = (doc.get("packages") or [])[:1]\n')}),
        ("pypi names not PEP 503 normalised", True, [PER_IMAGE],
         {"check": sub(C, 'listed.setdefault(_norm(unquote(m.group("name"))), set())',
                       'listed.setdefault(unquote(m.group("name")).lower(), set())')}),
        ("versions not compared", True, [RUNTIME],
         {"check": sub(C, "        if want not in listed.get(name, set()):",
                       "        if name not in listed:")}),
        ("runtime check skipped", True, [RUNTIME], {"check": sub(C, "            problems += runtime_problems(doc, a.site, a.lock)\n",
                                                                "            pass\n")}),
    ]
    vcases = [
        ("validate: spdxVersion not checked", 'if doc.get("spdxVersion") != "SPDX-2.3":', "if False:"),
        ("validate: dataLicense not checked", 'if doc.get("dataLicense") != "CC0-1.0":', "if False:"),
        ("validate: SPDXID not checked", 'if doc.get("SPDXID") != "SPDXRef-DOCUMENT":', "if False:"),
        ("validate: name not checked", 'if not isinstance(doc.get("name"), str) or not doc.get("name"):', "if False:"),
        ("validate: namespace any", "if not isinstance(ns, str) or not NAMESPACE_RE.fullmatch(ns):", "if False:"),
        ("validate: namespace https accepted", "if not isinstance(ns, str) or not NAMESPACE_RE.fullmatch(ns):",
         'if not isinstance(ns, str) or not (NAMESPACE_RE.fullmatch(ns) or ns.startswith("https://")):'),
        ("validate: namespace upper-case accepted", '[0-9a-f]{12}$")\n', '[0-9a-f]{12}$", re.I)\n'),
        ("validate: namespace any uuid version", "-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab]", "-[0-9a-f]{4}-[0-9a-f]{4}-[89ab]"),
        ("validate: namespace any uuid variant", "-[89ab][0-9a-f]{3}-", "-[0-9a-f]{4}-"),
        ("validate: namespace '#' accepted", "NAMESPACE_RE.fullmatch(ns)", 'NAMESPACE_RE.fullmatch(ns.split("#")[0])'),
        ("validate: namespace trailing newline accepted", "NAMESPACE_RE.fullmatch(ns)", "NAMESPACE_RE.match(ns)"),
        ("validate: namespace bare uuid accepted", 'NAMESPACE_RE = re.compile(r"^urn:uuid:',
         'NAMESPACE_RE = re.compile(r"^(?:urn:uuid:)?'),
        ("validate: created any", 'if not RFC3339_UTC.match(str(info.get("created", ""))):', "if False:"),
        ("validate: created any offset", 'RFC3339_UTC = re.compile(r"^\\d{4}-\\d\\d-\\d\\dT\\d\\d:\\d\\d:\\d\\d(?:\\.\\d+)?Z$")',
         'RFC3339_UTC = re.compile(r"^\\d{4}-\\d\\d-\\d\\dT\\d\\d:\\d\\d:\\d\\d(?:\\.\\d+)?(?:Z|[+-]\\d\\d:\\d\\d)$")'),
        ("validate: syft creator not checked", 'if not any(isinstance(c, str) and c.startswith("Tool: syft-") for c in creators):', "if False:"),
        ("validate: SPDXID uniqueness off", "        elif sid in ids:", "        elif False:"),
        ("validate: SPDXID pattern off", 'SPDXID_RE = re.compile(r"^SPDXRef-[A-Za-z0-9.-]+$")', 'SPDXID_RE = re.compile(r"^SPDXRef-.+$")'),
        ("validate: package name not required", '        if not pkg.get("name"):', "        if False:"),
        ("validate: downloadLocation not required", '        if not pkg.get("downloadLocation"):', "        if False:"),
        ("validate: DESCRIBES >= 1", "    if describes != 1:", "    if describes < 1:"),
        ("validate: DESCRIBES <= 1", "    if describes != 1:", "    if describes > 1:"),
        ("validate: ends not resolved", "            if end not in ids and end not in", "            if False and end not in"),
        ("validate: file ids not counted", '            ids.add(f["SPDXID"])', "            pass"),
        ("validate: raises on a list", '    if not isinstance(doc, dict):\n        return ["the document is not a JSON object"]\n', ""),
    ]
    for name, old, new in vcases:
        cases.append((name, True, [SPDX], {"check": sub(C, old, new)}))
    # Module-level SPDX table only (SbomCheckModuleTest) for the validate rows: R and M both have SPDX,
    # so run the module test alone there (faster, and it is the one the table drives).
    for name, want_fail, methods, kw in cases:
        if name.startswith("validate:") or name.startswith("TARGET (validate"):
            row(g, name, want_fail, run_tree([M(SPDX), M("test_sbom_check_is_stdlib_and_never_shipped")], **kw))
        else:
            row(g, name, want_fail, run_tree([R(m) for m in methods], **kw))
    g = "never shipped"

    def dockerfile(tree: Path) -> None:
        p = tree / "docker" / "app.Dockerfile"
        p.write_text(p.read_text(encoding="utf-8") + "\nCOPY scripts/sbom_check.py /opt/ke/\n", encoding="utf-8")

    def engine(tree: Path) -> None:
        (tree / "engine" / "uses_check.py").write_text("import sbom_check\n", encoding="utf-8")
    g2 = "finish CLI (N6 amendment)"
    fin = [M("test_finish_namespace_is_fresh_per_run"), M("test_finish_refuses_uuid_option")]
    row(g2, "TARGET", False, run_tree(fin))
    row(g2, "--uuid accepted (ignored)", True,
        run_tree(fin, check=sub(C, '    f.add_argument("--site")\n', '    f.add_argument("--site")\n    f.add_argument("--uuid")\n')))
    row(g2, "--uuid accepted and used", True,
        run_tree(fin, check=sub(sub(C, '    f.add_argument("--site")\n', '    f.add_argument("--site")\n    f.add_argument("--uuid")\n'),
                                'f"urn:uuid:{uuid.uuid4()}"', 'f"urn:uuid:{a.uuid or uuid.uuid4()}"')))
    row(g2, "namespace constant", True,
        run_tree(fin, check=sub(C, 'f"urn:uuid:{uuid.uuid4()}"', '"urn:uuid:0f8fad5b-d9cb-469f-a165-70867728950e"')))
    row(g2, "namespace v4-shaped hash of the name", True,
        run_tree(fin, check=sub(C, 'f"urn:uuid:{uuid.uuid4()}"',
                                'f"urn:uuid:{uuid.UUID(bytes=__import__(\'hashlib\').sha256(a.name.encode()).digest()[:16], '
                                'version=4)}"')))
    row(g2, "namespace uuid1 (time based, not v4)", True,
        run_tree(fin, check=sub(C, 'f"urn:uuid:{uuid.uuid4()}"', 'f"urn:uuid:{uuid.uuid1()}"')))
    row(g, "TARGET", False, run_tree([M("test_sbom_check_is_stdlib_and_never_shipped")]))
    row(g, "app.Dockerfile copies it", True, run_tree([M("test_sbom_check_is_stdlib_and_never_shipped")], extra=dockerfile))
    row(g, "engine imports it", True, run_tree([M("test_sbom_check_is_stdlib_and_never_shipped")], extra=engine))
    row(g, "bundle.sh copies it", True, run_tree(
        [M("test_sbom_check_is_stdlib_and_never_shipped"), R(PER_IMAGE)],
        bundle=sub(B, 'cp -- scripts/net_isolated.sh "$app/scripts/net_isolated.sh"\n',
                   'cp -- scripts/net_isolated.sh "$app/scripts/net_isolated.sh"\n'
                   'cp -- scripts/sbom_check.py "$app/scripts/sbom_check.py"\n')))
    row(g, "no sbom_check.py (pre-U3)", True, run_tree([M("test_sbom_check_is_stdlib_and_never_shipped"), M(SPDX)],
                                                      check=None))


# ---- offline_check pull (U2 test, U3 edit) -----------------------------------------

PULL = 'KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent KE_SBOM_USER="$(id -u):$(id -g)" \\\n'


def offline_controls() -> None:
    g = "offline_check pull"
    for name, want_fail, text in (
            ("TARGET", False, OFFLINE),
            ("pull without KE_SBOM_USER", True, sub(OFFLINE, PULL, "KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent \\\n")),
            ("pull with KE_SBOM_USER empty", True, sub(OFFLINE, PULL, 'KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent KE_SBOM_USER= \\\n'))):
        tmp = Path(tempfile.mkdtemp(prefix="u3oc-"))
        try:
            script = tmp / "offline_check.sh"
            script.write_text(text, encoding="utf-8", newline="\n")
            with mock.patch.object(toc, "OFFLINE_CHECK", script):
                res = Collect()
                unittest.TestSuite([toc.OfflineCheckScriptTest("test_offline_check_pulls_sbom_generator_before_bundle")]).run(res)
            row(g, name, want_fail, res.failed)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    compose_controls()
    check_static_controls()
    offline_controls()
    bundle_controls()
    check_controls()
    bad = [r for r in rows if not r[3]]
    width = max(len(r[1]) for r in rows)
    print(f"U3 controls ({'base repo' if BASE_REPO else 'targets'}): {len(rows)} rows, "
          f"{sum(1 for r in rows if r[2] == 'must fail')} must-fail, "
          f"{sum(1 for r in rows if r[2] == 'must pass')} must-pass, {len(bad)} unexpected")
    for group, name, want, ok, detail in rows:
        print(f"{'ok ' if ok else 'BAD'} [{group}] {name.ljust(width)} {want:9} | {detail}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
