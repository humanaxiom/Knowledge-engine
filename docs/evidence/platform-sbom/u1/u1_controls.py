"""U1 control driver (tester; RED 2026-10-22, rework round 1 2026-10-23, round 2
2026-10-23, round 3 2026-10-23, round 4 2026-10-23). Runs each U1 check, and each check U1 round 2 re-targets, on its
target fixture, on every must-pass and must-fail control, and on the
repository's files, and prints one line per case (all problems for the
repository rows).

Checks: tests/test_notice_ke_app.py (base, libpq, pointer, incorporated,
hacl and tracked from round 3, karamel from round 4, evidence), tests/test_ke_app_no_pip.py (pip: the N10a static check) and the
four re-targets: tests/test_psycopg_c.py app_runtime_problems (u0-runtime),
tests/test_image_scan.py final_stage_problems (d10),
tests/test_stack_compose.py unpinned_bases (digest), and the base check's
runtime-stage read (the `flat:` rows of base).

Run from the repo root (the smoke part of --reach needs bash and Linux, so run
it in the gates image):
  uv run --locked python docs/evidence/platform-sbom/u1/u1_controls.py [--red] [--only=CHECK] [--reach]

Labels (review N6): by default every REPO row expects the GREEN tree (no
problems), so a GREEN tree exits 0. `--red` expects round 4's RED instead: the
REPO hacl row (security I-8 wording) and the REPO karamel row (L-9b) fail;
those rows print "(RED expected)". (Round 3's RED rows, hacl/tracked REPO and
the two L-12 digest controls, are GREEN since round 3.)

Round 4 --reach splices r4-target-notice.md (the CPython bullet, and the
KaRaMeL and Apache-2.0 Licence-texts paragraphs) into a scratch copy of
today's NOTICE.md, adds r4-target-CPython-3.12-KaRaMeL.txt (security's
extract under the 4-line header) and r4-target-Apache-2.0.txt (security's
probe copy of base-files' text) to a copy of licenses/, `git add`s licenses/
in a scratch repository, and runs every check and the static classes. The
smoke part is round 3's, unchanged (round 4 does not touch smoke.sh).

Round 3's reach text, kept for the record: --reach spliced r3-target-notice.md (the CPython bullet and the HACL
Licence-texts paragraph) into a scratch copy of today's NOTICE.md, adds
r3-target-CPython-3.12-HACL.txt (built from the architect's extract) to a copy of
licenses/, `git add`s licenses/ in a scratch repository for the tracked check,
replaces smoke.sh's no-pip step with r3-target-smoke-block.sh, and runs the
L-12 controls against a candidate earlier-stage rule (a reach probe only; the
fix in tests/test_stack_compose.py is the developer's).

Round 2's reach text, kept for the record:
--reach splices the three round-2 targets beside this file into scratch copies
(the repository is not touched): r2-target-notice-sections.md into NOTICE.md
(from `## Base of `ke-app`` to the end) and its header, plus a stand-in
extract, as licenses/CPython-3.12-incorporated.txt; r2-target-app.Dockerfile
as docker/app.Dockerfile; r2-target-smoke-block.sh into scripts/smoke.sh after
the psycopg step. It then runs every check, and the static and smoke test
classes that read those files, on the scratch copies."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from tests import test_image_scan as ti  # noqa: E402
from tests import test_ke_app_no_pip as tp  # noqa: E402
from tests import test_notice_ke_app as tn  # noqa: E402
from tests import test_psycopg_c as tc  # noqa: E402
from tests import test_stack_compose as tsc  # noqa: E402
from tests import test_stack_scripts as tss  # noqa: E402

unexpected = 0
count: dict[str, list[int]] = {}
work = Path(tempfile.mkdtemp(prefix="u1-controls-"))
seq = [0]


def w(text: str, name: str) -> Path:
    seq[0] += 1
    p = work / f"{seq[0]:04d}" / name
    p.parent.mkdir(parents=True)
    p.write_bytes(text.encode("utf-8"))
    return p


RED_MODE = "--red" in sys.argv
# --only=<check> (e.g. digest): print and count only that check's rows.
ONLY = next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--only=")), None)


def _lic(notice: str, text: str | None, hacl_text: str | None, karamel_text: str | None = None,
         apache: str | None = None) -> tuple[Path, Path]:
    n = w(notice, "NOTICE.md")
    d = n.parent / "licenses"
    d.mkdir()
    for minor in ("3.12", "3.13"):
        if text is not None:
            (d / f"CPython-{minor}-incorporated.txt").write_bytes(text.encode("utf-8"))
        if hacl_text is not None:
            (d / f"CPython-{minor}-HACL.txt").write_bytes(hacl_text.encode("utf-8"))
        if karamel_text is not None:
            (d / f"CPython-{minor}-KaRaMeL.txt").write_bytes(karamel_text.encode("utf-8"))
    if apache is not None:
        (d / "Apache-2.0.txt").write_bytes(apache.encode("utf-8"))
    return n, d


def incorporated(notice: str, text: str | None, dockerfile: str) -> list[str]:
    n, d = _lic(notice, text, None)
    return tn.incorporated_licence_problems(n, d, w(dockerfile, "app.Dockerfile"))


def hacl(notice: str, text: str | None, hacl_text: str | None, dockerfile: str) -> list[str]:
    n, d = _lic(notice, text, hacl_text)
    return tn.hacl_licence_problems(n, d, w(dockerfile, "app.Dockerfile"))


def karamel(notice: str, text: str | None, hacl_text: str | None, karamel_text: str | None, apache: str | None,
            dockerfile: str, sha: str | None = tn.FIX_APACHE_SHA) -> list[str]:
    """sha None: the check's default, the pinned APACHE_2_SHA256."""
    n, d = _lic(notice, text, hacl_text, karamel_text, apache)
    df = w(dockerfile, "app.Dockerfile")
    return tn.karamel_licence_problems(n, d, df) if sha is None else tn.karamel_licence_problems(n, d, df, sha)


def _git(repo: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


TRACK_REPO = Path(tempfile.mkdtemp(prefix="u1-track-"))
_git(TRACK_REPO, "init", "-q")
for _rel in tn.TRACKED_FILES + tn.UNTRACKED_FILES:
    (TRACK_REPO / _rel).parent.mkdir(parents=True, exist_ok=True)
    (TRACK_REPO / _rel).write_text(_rel + "\n", encoding="utf-8")
_git(TRACK_REPO, "add", "--", *tn.TRACKED_FILES)


def tracked(notice: str, repo: Path = TRACK_REPO, git: str = "git") -> list[str]:
    return tn.untracked_licence_problems(w(notice, "NOTICE.md"), repo, git)


RUN = {
    "base": lambda n, d, a=tn.ADDED_PACKAGES: tn.base_paragraph_problems(w(n, "NOTICE.md"), w(d, "app.Dockerfile"), a),
    "libpq": lambda n: tn.libpq_debian_problems(w(n, "NOTICE.md")),
    "pointer": lambda n: tn.pointer_problems(w(n, "NOTICE.md")),
    "incorp": incorporated,
    "hacl": hacl,
    "karamel": karamel,
    "tracked": tracked,
    "evidence": lambda n: tn.evidence_path_problems(w(n, "NOTICE.md")),
    "pip": lambda d: tp.last_stage_pip_problems(w(d, "app.Dockerfile")),
    "u0-run": lambda d: tc.app_runtime_problems(w(d, "app.Dockerfile")),
    "d10": lambda d: ti.final_stage_problems(w(d, "app.Dockerfile")),
    "digest": lambda d: tsc.unpinned_bases(d),
}


# Round 4's RED rows (--red only): (check, row name).
RED_ROWS = {("hacl", "REPO NOTICE.md + licenses/"), ("karamel", "REPO NOTICE.md + licenses/")}


def row(check: str, name: str, want_fail: bool, problems: list[str], all_problems: bool = False) -> None:
    global unexpected
    if ONLY is not None and check != ONLY:
        return
    if not name.startswith(("TARGET", "REPO", "REACH")):
        count.setdefault(check, [0, 0])[0 if want_fail else 1] += 1
    red = RED_MODE and (check, name) in RED_ROWS
    if red:
        want_fail = not want_fail
    failed = bool(problems)
    ok = failed == want_fail
    unexpected += not ok
    verdict = ("FAILS" if failed else "passes") + (" (RED expected)" if red else "") + ("" if ok else "  <-- UNEXPECTED")
    print(f"{check:8} | {name[:70]:70} | want {'fail' if want_fail else 'pass'} | {verdict}"
          + (f" | {str(problems[0])[:90]}" if problems and not all_problems else ""))
    if all_problems:
        for p in problems:
            print(f"{'':8} |   - {p}")


def cases(check: str, target: tuple, passing: dict, failing: dict) -> None:
    row(check, "TARGET", False, RUN[check](*target))
    for k, v in passing.items():
        row(check, k, False, RUN[check](*(v if isinstance(v, tuple) else (v,))))
    for k, v in failing.items():
        row(check, k, True, RUN[check](*(v if isinstance(v, tuple) else (v,))))


cases("base", (tn.TARGET_NOTICE, tn.TARGET_DOCKERFILE), tn.BASE_PASSING, tn.BASE_CONTROLS)
row("base", "REPO NOTICE.md + app.Dockerfile", False,
    tn.base_paragraph_problems(tn.NOTICE, tn.APP_DOCKERFILE), True)
cases("libpq", (tn.TARGET_NOTICE,), tn.LIBPQ_PASSING, tn.LIBPQ_CONTROLS)
row("libpq", "REPO NOTICE.md", False, tn.libpq_debian_problems(tn.NOTICE), True)
cases("pointer", (tn.TARGET_NOTICE,), {}, tn.POINTER_CONTROLS)
row("pointer", "REPO NOTICE.md", False, tn.pointer_problems(tn.NOTICE), True)
cases("incorp", (tn.TARGET_NOTICE, tn.TARGET_INCORPORATED, tn.TARGET_DOCKERFILE_FLAT), tn.INCORPORATED_PASSING,
      tn.INCORPORATED_CONTROLS)
row("incorp", "REPO NOTICE.md + licenses/", False,
    tn.incorporated_licence_problems(tn.NOTICE, tn.LICENSES, tn.APP_DOCKERFILE), True)
cases("hacl", (tn.TARGET_NOTICE, tn.TARGET_INCORPORATED, tn.TARGET_HACL, tn.TARGET_DOCKERFILE_FLAT),
      tn.HACL_PASSING, tn.HACL_CONTROLS)
row("hacl", "REPO NOTICE.md + licenses/", False,
    tn.hacl_licence_problems(tn.NOTICE, tn.LICENSES, tn.APP_DOCKERFILE), True)
_KT = (tn.TARGET_NOTICE, tn.TARGET_INCORPORATED, tn.TARGET_HACL, tn.TARGET_KARAMEL, tn.FIX_APACHE_TEXT,
       tn.TARGET_DOCKERFILE_FLAT)
cases("karamel", _KT, tn.KARAMEL_PASSING,
      {**tn.KARAMEL_CONTROLS, "the stand-in Apache text against the pinned base-files sha256": (*_KT, None)})
row("karamel", "REPO NOTICE.md + licenses/", False,
    tn.karamel_licence_problems(tn.NOTICE, tn.LICENSES, tn.APP_DOCKERFILE), True)
_tracked_fail: dict = dict(tn.TRACKED_CONTROLS)
_tracked_fail["git cannot run"] = (tn.TRACKED_PASSING["names only tracked files, with a full stop after one"],
                                   TRACK_REPO, "git-not-installed-ke-u1")
_tracked_fail["not a git work tree"] = (tn.TRACKED_PASSING["names only tracked files, with a full stop after one"],
                                        work)
cases("tracked", (tn.TARGET_NOTICE,), tn.TRACKED_PASSING, _tracked_fail)
row("tracked", "REPO NOTICE.md + git index", False, tn.untracked_licence_problems(tn.NOTICE, tn.GIT_ROOT), True)
cases("evidence", (tn.TARGET_NOTICE,), tn.EVIDENCE_PASSING, tn.EVIDENCE_CONTROLS)
row("evidence", "REPO NOTICE.md", False, tn.evidence_path_problems(tn.NOTICE), True)
cases("pip", (tc.TARGET_APP_FLAT,), tp.PIP_PASSING, tp.PIP_CONTROLS)
row("pip", "REPO app.Dockerfile", False, tp.last_stage_pip_problems(tp.APP_DOCKERFILE), True)
cases("u0-run", (tc.TARGET_APP,), tc.RUNTIME_PASSING, tc.RUNTIME_CONTROLS)
row("u0-run", "REPO app.Dockerfile", False, tc.app_runtime_problems(tc.APP_DOCKERFILE), True)
cases("d10", (ti.D10_LEGACY,), ti.D10_PASSING, ti.D10_CONTROLS)
row("d10", "REPO app.Dockerfile", False, ti.final_stage_problems(ti.APP_DOCKERFILE), True)
cases("digest", (tsc.UNPINNED_PASSING["digest-pinned base"],), tsc.UNPINNED_PASSING, tsc.UNPINNED_CONTROLS)
for df in sorted((ROOT / "docker").rglob("*Dockerfile")):
    row("digest", f"REPO {df.name}", False, tsc.unpinned_bases(df.read_text(encoding="utf-8")), True)
_, names, _ = tn.runtime_stage(tn.APP_DOCKERFILE)
print(f"added    | repo shipped-stage apt names {names}; ADDED_PACKAGES {sorted(tn.ADDED_PACKAGES)}")
total_fail = sum(c[0] for c in count.values())
total_pass = sum(c[1] for c in count.values())
for check, (f, p) in count.items():
    print(f"controls {check:8}: {f} must-fail + {p} must-pass")
print(f"controls: {total_fail} must-fail + {total_pass} must-pass = {total_fail + total_pass}")
print(f"unexpected: {unexpected}")


def _run_classes(label: str, classes: list[type]) -> None:
    global unexpected
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in classes)
    with open(os.devnull, "w", encoding="utf-8") as sink:
        result = unittest.TextTestRunner(stream=sink, verbosity=0).run(suite)
    bad = [str(t) for t, _ in result.failures + result.errors]
    unexpected += bool(bad)
    print(f"REACH {label}: ran {result.testsRun}, failures {len(result.failures)}, errors {len(result.errors)}, "
          f"skipped {len(result.skipped)}" + "".join(f"\n      - {b}" for b in bad))


def candidate_unpinned_bases(text: str) -> list[str]:
    """Reach probe for L-12 (not the fix; the developer owns
    tests/test_stack_compose.py): a FROM name is a stage only when an earlier
    FROM line defined it."""
    import re
    defined: set[str] = set()
    out = []
    for m in re.finditer(r"^FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?", text, re.M | re.I):
        image, alias = m.group(1), m.group(2)
        if image.lower() not in defined and image != "scratch" and not tsc.DIGEST.search(image):
            out.append(image)
        if alias:
            defined.add(alias.lower())
    return out


if "--reach" in sys.argv:
    print("---- reach: the round-4 targets spliced into scratch copies ----")
    md = (HERE / "r4-target-notice.md").read_text(encoding="utf-8").replace("\r\n", "\n")

    def part(name: str) -> str:
        return md.split(f"<!-- {name}:start -->\n", 1)[1].split(f"<!-- {name}:end -->", 1)[0]

    bullet, k_para, a_para = part("cpython-bullet"), part("karamel-licence-texts"), part("apache-licence-texts")
    k_header = part("karamel-header")
    today = tn.NOTICE.read_text(encoding="utf-8")
    start = today.index("- CPython 3.12 under")
    end = today.index("- The Debian 12", start)
    notice_text = today[:start] + bullet + today[end:]
    notice_text = notice_text.rstrip("\n") + "\n\n" + k_para + "\n" + a_para
    tree = Path(tempfile.mkdtemp(prefix="u1-reach-"))
    (tree / "docker").mkdir()
    notice = tree / "NOTICE.md"
    notice.write_bytes(notice_text.encode("utf-8"))
    lic = tree / "licenses"
    shutil.copytree(tn.LICENSES, lic)
    # A checkout with core.autocrlf may add CRs to docs/evidence/; the targets are LF.
    k_file = (HERE / "r4-target-CPython-3.12-KaRaMeL.txt").read_bytes().replace(b"\r\n", b"\n")
    assert k_file.startswith(k_header.encode("utf-8")), "r4-target-CPython-3.12-KaRaMeL.txt header differs"
    (lic / "CPython-3.12-KaRaMeL.txt").write_bytes(k_file)
    (lic / "Apache-2.0.txt").write_bytes((HERE / "r4-target-Apache-2.0.txt").read_bytes().replace(b"\r\n", b"\n"))
    app = tree / "docker" / "app.Dockerfile"
    shutil.copyfile(tn.APP_DOCKERFILE, app)
    _git(tree, "init", "-q")
    _git(tree, "add", "--", "licenses")
    gates = ROOT / "docker" / "gates.Dockerfile"
    print("REACH note: licenses/ = the repository's plus r4-target-CPython-3.12-KaRaMeL.txt (target header + "
          "security's extract) and r4-target-Apache-2.0.txt (security's base-files copy); the scratch repository "
          "`git add`s licenses/")
    reach = {
        "base": tn.base_paragraph_problems(notice, app),
        "libpq": tn.libpq_debian_problems(notice),
        "pointer": tn.pointer_problems(notice),
        "incorp": tn.incorporated_licence_problems(notice, lic, app),
        "hacl": tn.hacl_licence_problems(notice, lic, app),
        "karamel": tn.karamel_licence_problems(notice, lic, app),
        "tracked": tn.untracked_licence_problems(notice, tree),
        "evidence": tn.evidence_path_problems(notice),
        "pip": tp.last_stage_pip_problems(app),
        "u0-run": tc.app_runtime_problems(app),
        "u0-build": tc.app_build_problems(app),
        "u0-pin": tc.pin_base_problems(app, gates),
        "u0-psyc": tc.notice_problems(notice, tc.UV_LOCK),
        "d10": ti.final_stage_problems(app),
        "digest": tsc.unpinned_bases(app.read_text(encoding="utf-8")),
    }
    for check, problems in reach.items():
        row(check, "REACH target", False, problems, True)
    # (Round 3's L-12 candidate rows are dropped: unpinned_bases has the rule
    # since round 3, and the digest rows above run it.)
    # The static test classes, with their module paths pointed at the scratch tree.
    patches = [(tn, "NOTICE", notice), (tn, "APP_DOCKERFILE", app), (tn, "LICENSES", lic), (tn, "GIT_ROOT", tree),
               (tp, "APP_DOCKERFILE", app), (tc, "APP_DOCKERFILE", app), (tc, "NOTICE", notice),
               (ti, "APP_DOCKERFILE", app)]
    saved = [(m, a, getattr(m, a)) for m, a, _ in patches]
    for m, a, v in patches:
        setattr(m, a, v)
    try:
        _run_classes("static classes (NoticeKeAppBaseTest, KeAppNoPipStaticTest, PsycopgCStaticTest, AppImageTest)",
                     [tn.NoticeKeAppBaseTest, tp.KeAppNoPipStaticTest, tc.PsycopgCStaticTest, ti.AppImageTest])
    finally:
        for m, a, v in saved:
            setattr(m, a, v)
    if platform.system() != "Linux" or shutil.which("bash") is None:
        print("REACH smoke: SKIPPED (needs bash on Linux; run this driver in the gates image)")
    else:
        block = (HERE / "r3-target-smoke-block.sh").read_text(encoding="utf-8")
        block = block.split("# ---- insert below this line ----\n", 1)[1]
        smoke = (ROOT / "scripts" / "smoke.sh").read_text(encoding="utf-8")
        anchor = 'echo "smoke: psycopg c on Debian libpq5 $deb ($libpq -> $libpq_real)"\n'
        tail = "# ci/offline (PS-3.3"
        assert smoke.count(anchor) == 1 and smoke.count(tail) == 1, "the psycopg step or ci/offline moved"
        head_end = smoke.index(anchor) + len(anchor)
        tail_start = smoke.index(tail)
        print(f"REACH note: smoke.sh lines replaced: {smoke[head_end:tail_start].count(chr(10))} "
              f"(today's no-pip step), by {block.count(chr(10))} target lines")

        def splice(text: str) -> str:
            return smoke[:head_end] + text + "\n" + smoke[tail_start:]

        current = [splice(block)]
        real_copy = tss._copy_repo_files

        def copy_with_target(dest: Path, rels: list[str]) -> None:
            real_copy(dest, rels)
            if "scripts/smoke.sh" in rels:
                (dest / "scripts" / "smoke.sh").write_bytes(current[0].encode("utf-8"))

        tss._copy_repo_files = copy_with_target
        try:
            smoke_classes = [c for n, c in vars(tss).items() if n.startswith("Smoke") and isinstance(c, type)
                             and issubclass(c, unittest.TestCase)]
            _run_classes("smoke: SmokeNoPipTest", [tp.SmokeNoPipTest])
            _run_classes("smoke: SmokePsycopgTest", [tc.SmokePsycopgTest])
            _run_classes(f"smoke: test_stack_scripts {', '.join(c.__name__ for c in smoke_classes)}", smoke_classes)
            # Smoke-block mutants: each must make SmokeNoPipTest fail.
            check_line = '[ "$pip_out" = - ] || {\n'
            fail_line = ("  echo \"smoke: FAIL (no pip: the check in api printed '$pip_out', want '-' (pip in api, "
                         "or no answer))\" >&2\n  exit 1\n}\n")
            r2_compare = ('read -r pip_hits pip_rest <<< "$pip_out"\n'
                          'if [ "$pip_hits" != - ] || [ -n "$pip_rest" ]; then\n'
                          "  echo \"smoke: FAIL (no pip: the check in api printed '$pip_hits${pip_rest:+ $pip_rest}', "
                          "want '-' (pip in api, or no answer))\" >&2\n  exit 1\nfi\n")
            assert block.count(check_line + fail_line) == 1
            mutants = {
                "S1 eval of the container output (M-1)": block.replace(
                    check_line, 'eval "pip_out=$pip_out"\n' + check_line),
                "S2 only the first word compared": block.replace(check_line, '[ "${pip_out%% *}" = - ] || {\n'),
                "S3 no find_spec fallback": block.replace(
                    'if u.find_spec("pip") and not h:\n    h = ["pip (importable)"]\n', ""),
                "S4 walks /usr/local/bin only": block.replace('for r in ("/usr", "/opt")',
                                                              'for r in ("/usr/local/bin",)'),
                "S5 no dist-info/whl names": block.replace(r'|pip-.+\.(dist-info|whl)', ""),
                "S6 no `|| FAIL` on a failed exec": block.replace(
                    ''' || {\n  echo "smoke: FAIL (no pip: the check in api failed)" >&2\n  exit 1\n}''', ""),
                "S7 the venv python, not /usr/local/bin/python3": block.replace(
                    "/usr/local/bin/python3 -I", "python -I"),
                "S8 walks /usr only (misses /opt)": block.replace('for r in ("/usr", "/opt")', 'for r in ("/usr",)'),
                "S9 a pip hit only warns": block.replace(
                    check_line + fail_line,
                    '[ "$pip_out" = - ] || echo "smoke: WARN (pip in api: $pip_out)" >&2\n'),
                "S10 ${pip_out:--} default (empty output read as clean)": block.replace(
                    check_line, '[ "${pip_out:--}" = - ] || {\n'),
                # I-6 (round 3): round 2's first-line read, killed only by the new subtest.
                "S11 round 2's `read -r` first line only (I-6)": block.replace(check_line + fail_line, r2_compare),
                "S12 only the first line compared (head -n1)": block.replace(
                    check_line, '[ "$(printf %s "$pip_out" | head -n1)" = - ] || {\n'),
            }
            for name, text in mutants.items():
                assert text != block, name
                current[0] = splice(text)
                suite = unittest.defaultTestLoader.loadTestsFromTestCase(tp.SmokeNoPipTest)
                with open(os.devnull, "w", encoding="utf-8") as sink:
                    result = unittest.TextTestRunner(stream=sink, verbosity=0).run(suite)
                killed = len(result.failures) + len(result.errors)
                unexpected += killed == 0
                by = sorted({str(t).split(" (")[0] + " " + str(t)[str(t).find("(case="):] for t, _ in result.failures
                             + result.errors})
                print(f"mutant   | {name[:70]:70} | want killed | "
                      + (f"killed ({killed} failing subtests)" if killed else "SURVIVED  <-- UNEXPECTED"))
                for b in by:
                    print(f"         |   by {b[:150]}")
        finally:
            tss._copy_repo_files = real_copy
    print(f"unexpected (with reach): {unexpected}")
shutil.rmtree(work, ignore_errors=True)
shutil.rmtree(TRACK_REPO, ignore_errors=True)
sys.exit(1 if unexpected else 0)
