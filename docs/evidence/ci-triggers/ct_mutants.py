"""Drive CiTriggersTest.assert_triggers (CT-1) against scratch copies of ci.yml.

Never touches the repo's ci.yml: it reads it, swaps the `on:` block in memory
and writes each variant to the scratchpad.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(r"C:\repos\Knowledge-engine")
sys.path.insert(0, str(REPO))
from tests.test_stack_ready_docs import CiTriggersTest  # noqa: E402

SCRATCH = Path(__file__).resolve().parent / "ci-mutants"
SCRATCH.mkdir(exist_ok=True)
CURRENT_ON = "on:\n  push:\n  pull_request:\n"
TARGET_ON = (
    "on:\n"
    "  # ci-triggers (ADR-KE-015): push runs only for the default branch, and\n"
    "  # every pull request gets one run, so a PR push is verified once. A\n"
    "  # branch with no open PR gets no CI. Renaming the default branch must\n"
    "  # update this list and DEFAULT_BRANCH in tests/test_stack_ready_docs.py.\n"
    "  push:\n"
    "    branches: [ccr-19465ed4-j1u0m5]\n"
    "  pull_request:\n"
)
VARIANTS = {
    "current (repo ci.yml, unchanged)": (CURRENT_ON, "fail"),
    "a target on: block (ADR-KE-015)": (TARGET_ON, "pass"),
    "a2 target, pull_request: {}": (TARGET_ON.replace("  pull_request:\n", "  pull_request: {}\n"), "pass"),
    "b target + workflow_dispatch:": (TARGET_ON + "  workflow_dispatch:\n", "fail"),
    "c push branches: [main]": (TARGET_ON.replace("[ccr-19465ed4-j1u0m5]", "[main]"), "fail"),
    "d push branches + paths-ignore": (
        TARGET_ON.replace("  pull_request:\n", "    paths-ignore: ['**.md']\n  pull_request:\n"), "fail"),
    "e pull_request branches: [ccr-19465ed4-j1u0m5]": (
        TARGET_ON + "    branches: [ccr-19465ed4-j1u0m5]\n", "fail"),
    "f push branches: [ccr-19465ed4-j1u0m5, main]": (
        TARGET_ON.replace("[ccr-19465ed4-j1u0m5]", "[ccr-19465ed4-j1u0m5, main]"), "fail"),
    "g target + pull_request_target:": (TARGET_ON + "  pull_request_target:\n", "fail"),
    "h quoted 'on': key, target": (TARGET_ON.replace("on:\n", '"on":\n', 1), "pass"),
    "i no on: block": ("", "fail"),
}

source = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
assert source.count(CURRENT_ON) == 1, "repo ci.yml on: block is not the expected current shape"
case = CiTriggersTest("test_ci_triggers_push_default_branch_and_pull_request")
bad = 0
print(f"{'variant':<50} {'expected':<8} {'got':<5} reason")
for n, (name, (block, expected)) in enumerate(VARIANTS.items()):
    path = SCRATCH / f"ci-{n:02d}.yml"
    path.write_text(source.replace(CURRENT_ON, block), encoding="utf-8")
    try:
        case.assert_triggers(path)
        got, reason = "pass", ""
    except AssertionError as exc:
        got, reason = "fail", str(exc).splitlines()[0][:110]
    ok = got == expected
    bad += not ok
    print(f"{name:<50} {expected:<8} {got:<5} {'' if ok else 'UNEXPECTED '}{reason}")
print(f"unexpected results: {bad}")
sys.exit(1 if bad else 0)
