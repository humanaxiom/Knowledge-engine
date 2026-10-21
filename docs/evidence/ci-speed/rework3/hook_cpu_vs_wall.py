"""Hook cost: wall time vs children CPU time (rusage), idle and under CPU contention.
Run inside the gates image with the repo at /work (read-only), e.g.
  docker run --rm --cpuset-cpus <one cpu> -v <repo>:/work:ro -w /work ke-gates:<tag> \
    python3 docs/evidence/ci-speed/rework3/hook_cpu_vs_wall.py <burners>
<burners> busy-loop processes share the CPU set to model contention."""
import multiprocessing as mp
import os
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, "/work")
from tests.test_block_main_commit_hook import HOOK, claude_code_payload  # noqa: E402


def burn():
    while True:
        pass


def main(burners: int) -> None:
    repo = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True)
    subprocess.run(["git", "-C", repo, "checkout", "-q", "-b", "agent/x"], check=True)
    fake = Path(tempfile.mkdtemp()) / "jq"
    fake.write_text("#!/bin/sh\nexit 127\n")
    fake.chmod(0o755)
    mb, mb5 = 1_000_000, 5_000_000
    cases = {
        ("1MB", "heredoc lines", 3.0): "cat <<'EOF'\n" + "abcdefghi\n" * (mb // 10) + "EOF",
        ("1MB", "unquoted token", 3.0): "echo " + "a" * mb,
        ("5MB", "heredoc lines", 9.0): "cat <<'EOF'\n" + "abcdefghi\n" * (mb5 // 10) + "EOF",
        ("5MB", "one token", 9.0): "echo " + "a" * mb5,
        ("5MB", "windows paths", 9.0): "echo " + "C:\a\b " * (mb5 // 7 + 1),
    }
    procs = [mp.Process(target=burn, daemon=True) for _ in range(burners)]
    for p in procs:
        p.start()
    print(f"cpus={len(os.sched_getaffinity(0))} burners={burners}")
    print(f"{'size':4} {'mode':6} {'shape':15} {'budget':>6} {'wall':>6} {'cpu':>6} {'user':>6} {'sys':>6}")
    for mode in ("jq", "no-jq"):
        env = dict(os.environ)
        if mode == "no-jq":
            env["PATH"] = str(fake.parent) + os.pathsep + env["PATH"]
        for (size, shape, budget), command in cases.items():
            payload = claude_code_payload(command, repo)
            r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
            t0 = time.monotonic()
            out = subprocess.run(["bash", str(HOOK)], input=payload, cwd=repo, env=env,
                                 capture_output=True, text=True, check=True).stdout.strip()
            wall = time.monotonic() - t0
            r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
            u, s = r1.ru_utime - r0.ru_utime, r1.ru_stime - r0.ru_stime
            assert out == "", out
            print(f"{size:4} {mode:6} {shape:15} {budget:6.1f} {wall:6.2f} {u + s:6.2f} {u:6.2f} {s:6.2f}")
    for p in procs:
        p.terminate()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
