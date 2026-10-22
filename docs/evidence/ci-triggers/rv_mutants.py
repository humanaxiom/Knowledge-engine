import sys, pathlib, tempfile
sys.path.insert(0, r"C:\repos\Knowledge-engine")
from tests.test_stack_ready_docs import CiTriggersTest
base = pathlib.Path(r"C:\repos\Knowledge-engine\.github\workflows\ci.yml").read_text(encoding="utf-8")
target = "  push:\n    branches: [ccr-19465ed4-j1u0m5]\n  pull_request:\n"
assert target in base
variants = {
 "pr types filter": target.replace("  pull_request:\n", "  pull_request:\n    types: [opened]\n"),
 "pr empty list []": target.replace("  pull_request:\n", "  pull_request: []\n"),
 "push branches + tags": target.replace("    branches: [ccr-19465ed4-j1u0m5]\n", "    branches: [ccr-19465ed4-j1u0m5]\n    tags: ['v*']\n"),
 "push branches string": target.replace("[ccr-19465ed4-j1u0m5]", "ccr-19465ed4-j1u0m5"),
 "push branches glob": target.replace("[ccr-19465ed4-j1u0m5]", "['ccr-*']"),
 "on list form": None,
 "dup quoted on (bad) + bare on (good)": None,
}
t = CiTriggersTest("test_ci_triggers_push_default_branch_and_pull_request")
for name, block in variants.items():
    if name == "on list form":
        text = base.replace("on:\n", "on: [push, pull_request]\nx_old:\n", 1)
    elif name == "dup quoted on (bad) + bare on (good)":
        text = base.replace("on:\n", '"on": [push, workflow_dispatch]\non:\n', 1)
    else:
        text = base.replace(target, block)
    p = pathlib.Path(tempfile.mkdtemp()) / "ci.yml"
    p.write_text(text, encoding="utf-8")
    try:
        t.assert_triggers(p); r = "pass"
    except AssertionError as e:
        r = "fail: " + str(e).splitlines()[0][:90]
    except Exception as e:
        r = "error: " + type(e).__name__ + " " + str(e)[:80]
    print(f"{name:40s} {r}")
