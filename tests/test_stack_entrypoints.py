"""platform-stack-up (2a), rework round 1: the container entrypoints enforce
their refusals (docs/handoffs/platform-stack.md "rework round 1 of 5").

- Review B2 (PS-2.14 (1), "engine startup in api and worker"):
  - `engine.api.main()` runs `startup()` before uvicorn serves. A refused
    setting stops it before `uvicorn.run`. This is tested here with uvicorn
    mocked, so `main` carries no `pragma: no cover`.
  - The worker is `python -m engine.worker` (architecture §2.4). Its `main()`
    runs `startup()` and then idles. It is a placeholder until PS-2.6. A
    refused setting exits before it idles.
- Security M-3 + L-3 (ADR-KE-009, F-A): the gateway entrypoint refuses to
  start unless `KE_MODEL_UPSTREAM` is empty, or a strict `host:port` (port
  1-65535) whose host is on `KE_EGRESS_ALLOWLIST`. The host match is exact
  and case-folded, against the comma-separated allowlist as the engine reads
  it. Values with a newline, a brace, a semicolon, a quote, whitespace, a
  scheme or a path are refused. Every `docker/gateway/*.sh` is an entrypoint
  check, run in name order, and any non-zero exit stops nginx.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from tests.engine_support import ROOT, base_env, environ, load_settings

VAR = "KE_BIND_ADDRESS"
PASSING = base_env(KE_ENV="ci")
REFUSING = base_env(KE_ENV="ci", KE_BIND_ADDRESS="0.0.0.0")


def _refused() -> type[Exception]:
    from engine.startup import StartupRefused

    return StartupRefused


def _assert_refusal(test: unittest.TestCase, exc: BaseException | None) -> None:
    if isinstance(exc, SystemExit):
        test.assertNotIn(exc.code, (0, None), "the entrypoint exited 0 on a refused setting")
        return
    test.assertIsInstance(exc, _refused(), f"expected a startup refusal, got {exc!r}")
    test.assertEqual(exc.setting, VAR)  # type: ignore[union-attr]


def _main_has_no_pragma(test: unittest.TestCase, rel: str) -> None:
    text = (ROOT / rel).read_text(encoding="utf-8")
    match = re.search(r"^def main\(.*$", text, re.M)
    test.assertIsNotNone(match, f"{rel} has no main()")
    test.assertNotIn("pragma: no cover", match.group(0),  # type: ignore[union-attr]
                     f"{rel} main() is exempt from coverage; it must be tested")


class ApiEntrypointTest(unittest.TestCase):
    def _main(self, env: dict[str, str]) -> tuple[BaseException | None, mock.MagicMock]:
        import uvicorn

        import engine.api as api

        run = mock.MagicMock(name="uvicorn.run")
        with environ(env), mock.patch.object(uvicorn, "run", run):
            patches = [mock.patch.object(api, "run", run)] if hasattr(api, "run") else []
            for p in patches:
                p.start()
            try:
                api.main()
            except BaseException as exc:  # noqa: BLE001 - SystemExit counts too
                return exc, run
            finally:
                for p in patches:
                    p.stop()
        return None, run

    def test_api_main_runs_startup_before_serving(self):
        error, run = self._main(PASSING)
        self.assertIsNone(error, repr(error))
        run.assert_called_once()
        port = run.call_args.kwargs.get("port")
        self.assertEqual(port, load_settings(PASSING).api.listen_port)

    def test_api_main_refused_setting_never_serves(self):  # mutant W1
        error, run = self._main(REFUSING)
        _assert_refusal(self, error)
        run.assert_not_called()

    def test_api_main_is_not_exempt_from_coverage(self):
        _main_has_no_pragma(self, "engine/api.py")


class _Idled(BaseException):
    """Raised by the patched idle primitives: the worker reached its idle loop."""


class WorkerEntrypointTest(unittest.TestCase):
    def _main(self, env: dict[str, str]) -> BaseException | None:
        import importlib

        worker = importlib.import_module("engine.worker")

        def idle(*args: Any, **kwargs: Any) -> Any:
            raise _Idled()

        outcome: list[BaseException | None] = []

        def target() -> None:
            try:
                worker.main()
            except BaseException as exc:  # noqa: BLE001
                outcome.append(exc)
            else:
                outcome.append(None)

        with environ(env), mock.patch.object(signal, "pause", idle), \
                mock.patch.object(time, "sleep", idle):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            thread.join(30)
        if thread.is_alive():
            self.fail("engine.worker.main() neither refused nor idled via signal.pause "
                      "or time.sleep within 30 s")
        return outcome[0]

    def test_worker_main_refused_setting_exits_before_idling(self):
        error = self._main(REFUSING)
        self.assertNotIsInstance(error, _Idled, "the worker idled despite a refused setting")
        _assert_refusal(self, error)

    def test_worker_main_idles_after_a_passing_startup(self):
        error = self._main(PASSING)
        self.assertIsInstance(error, _Idled, f"the worker did not reach its idle loop: {error!r}")

    def test_worker_module_refuses_as_a_process(self):
        env = {**REFUSING, "PYTHONPATH": str(ROOT)}
        result = subprocess.run([sys.executable, "-m", "engine.worker"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0, "python -m engine.worker ran despite a refusal")
        self.assertIn(VAR, result.stdout + result.stderr)

    def test_worker_main_is_not_exempt_from_coverage(self):
        self.assertTrue((ROOT / "engine" / "worker.py").is_file(), "engine/worker.py is missing")
        _main_has_no_pragma(self, "engine/worker.py")


# --------------------------------------------------------------------------
# M-3 + L-3: the gateway entrypoint enforces the egress allowlist
# --------------------------------------------------------------------------

GATEWAY_DIR = ROOT / "docker" / "gateway"
HOST = "model-host.internal"


def _gateway_checks() -> list[Path]:
    return sorted(GATEWAY_DIR.glob("*.sh"))


def _gateway_port_defaults() -> dict[str, str]:
    """Every gateway environment variable whose compose default is a number:
    the values compose hands the container when .env says nothing."""
    from tests import compose_support as cs

    out: dict[str, str] = {}
    for key, value in cs.environment(cs.services().get("gateway", {})).items():
        match = re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?-(\d+)\}", value)
        if match:
            out[key] = match.group(1)
    return out


def _run_entrypoint(upstream: str | None, allowlist: str | None,
                    **overrides: str) -> tuple[int, str]:
    """Run every gateway entrypoint check in order, as /docker-entrypoint.sh
    does; the first non-zero exit stops the start. The port variables carry
    their compose defaults, as compose always sets them (rework 2, security
    L-3: the entrypoint now validates them)."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "KE_ENV": "prod",
           VAR: "127.0.0.1", **_gateway_port_defaults()}
    env.update(overrides)
    if upstream is not None:
        env["KE_MODEL_UPSTREAM"] = upstream
    if allowlist is not None:
        env["KE_EGRESS_ALLOWLIST"] = allowlist
    output = ""
    for script in _gateway_checks():
        result = subprocess.run(["sh", str(script)], env=env, capture_output=True,
                                text=True, timeout=30)
        output += result.stdout + result.stderr
        if result.returncode != 0:
            return result.returncode, output
    return 0, output


class GatewayUpstreamCheckTest(unittest.TestCase):
    ACCEPTED = {
        "unset": (None, None),
        "empty": ("", ""),
        "empty, allowlist set": ("", "gateway"),
        "host on allowlist": (f"{HOST}:11434", f"gateway,{HOST}"),
        "allowlist with spaces": (f"{HOST}:11434", f"gateway , {HOST} "),
        "case-folded": ("Model-Host.Internal:8000", HOST),
        "IPv4 host on allowlist": ("10.0.0.7:8000", "10.0.0.7"),
        "port 65535": (f"{HOST}:65535", HOST),
    }
    REFUSED = {
        "security M-3 repro": ("one.one.one.one:80", "gateway"),
        "allowlist empty": (f"{HOST}:11434", ""),
        "allowlist unset": (f"{HOST}:11434", None),
        "suffix only": (f"evil-{HOST}:80", HOST),
        "allowlist entry is a superstring": (f"{HOST}:80", f"{HOST}.evil"),
        "subdomain of allowed host": (f"a.{HOST}:80", HOST),
        "no port": (HOST, HOST),
        "empty port": (f"{HOST}:", HOST),
        "empty host": (":11434", HOST),
        "port 0": (f"{HOST}:0", HOST),
        "port too large": (f"{HOST}:65536", HOST),
        "port not numeric": (f"{HOST}:http", HOST),
        "two ports": (f"{HOST}:80:81", HOST),
        "scheme": (f"http://{HOST}:11434", HOST),
        "path": (f"{HOST}:11434/v1", HOST),
        "L-3 newline": (f"{HOST}:11434\nserver {{ listen 9999; }}", HOST),
        "L-3 closing brace": (f'{HOST}:11434";}} server {{ listen 9999; proxy_pass x:1; }} #', HOST),
        "brace": (f"{HOST}:11434}}", HOST),
        "semicolon": (f"{HOST}:11434;", HOST),
        "quote": (f'{HOST}:11434"', HOST),
        "space": (f"{HOST}:11434 x", HOST),
        "leading space": (f" {HOST}:11434", HOST),
        "dollar": (f"${{HOST}}:11434", HOST),
    }

    def setUp(self) -> None:
        self.assertTrue(_gateway_checks(), "docker/gateway has no entrypoint checks")

    def test_gateway_accepts_empty_or_allowlisted_upstream(self):
        for case, (upstream, allowlist) in self.ACCEPTED.items():
            with self.subTest(case=case):
                code, output = _run_entrypoint(upstream, allowlist)
                self.assertEqual(code, 0, output)

    def test_gateway_refuses_upstream_not_on_allowlist_or_malformed(self):
        for case, (upstream, allowlist) in self.REFUSED.items():
            with self.subTest(case=case):
                code, output = _run_entrypoint(upstream, allowlist)
                self.assertNotEqual(code, 0, f"gateway would start forwarding to {upstream!r}")
                self.assertIn("KE_MODEL_UPSTREAM", output, "the refusal must name the variable")

    def test_every_gateway_check_is_installed_as_an_entrypoint_script(self):
        text = (ROOT / "docker" / "gateway.Dockerfile").read_text(encoding="utf-8")
        for script in _gateway_checks():
            with self.subTest(script=script.name):
                self.assertRegex(
                    text, rf"(?m)^COPY\s.*docker/gateway/{re.escape(script.name)}\s+"
                          rf"/docker-entrypoint\.d/",
                    f"{script.name} is not installed into /docker-entrypoint.d/")
                # nginx's 20-envsubst-on-templates.sh renders the upstream; the
                # check must run before it.
                self.assertRegex(script.name, r"^1\d-", f"{script.name} must sort before 20-envsubst")


# --------------------------------------------------------------------------
# Rework 2, security L-3: every substituted port is validated
# --------------------------------------------------------------------------

TEMPLATES = GATEWAY_DIR / "templates"
# Substituted by envsubst but not operator input: the nginx image's
# 15-local-resolvers.envsh overwrites it from /etc/resolv.conf whenever
# NGINX_ENTRYPOINT_LOCAL_RESOLVERS is set (asserted below).
NOT_OPERATOR_INPUT = {"NGINX_LOCAL_RESOLVERS"}
# Validated as host:port by 11-ke-upstream-check.sh (M-3), not as a port.
NOT_A_PORT = {"KE_MODEL_UPSTREAM"}

INJECTIONS = {
    "security L-3 location": "80; } location /x { proxy_pass http://1.1.1.1; }",
    "stream listener": "8102; } server { listen 9999; proxy_pass 1.1.1.1:80; }",
    "newline": "8100\nserver { listen 9998; }",
    "address:port": "0.0.0.0:8100",
    "envsubst reference": "${KE_MODEL_UPSTREAM}",
}
BAD_PORTS = {
    "empty": "",
    "zero": "0",
    "65536": "65536",
    "huge": "99999999999999999999",
    "negative": "-1",
    "plus sign": "+80",
    "leading space": " 8100",
    "trailing space": "8100 ",
    "suffix": "80x",
    "hex": "0x50",
    "exponent": "1e3",
    "list": "8100,8101",
    "semicolon": "8100;",
}


def _envsubst_filter() -> re.Pattern[str]:
    text = (ROOT / "docker" / "gateway.Dockerfile").read_text(encoding="utf-8")
    match = re.search(r"NGINX_ENVSUBST_FILTER=['\"]?([^'\"\s]+)", text)
    if match is None:
        raise AssertionError("gateway.Dockerfile sets no NGINX_ENVSUBST_FILTER")
    return re.compile(match.group(1))


def _substituted_variables() -> set[str]:
    """Every name envsubst replaces in the gateway templates: `$NAME` or
    `${NAME}` where NAME passes the image's NGINX_ENVSUBST_FILTER."""
    allowed = _envsubst_filter()
    found: set[str] = set()
    for template in TEMPLATES.iterdir():
        text = template.read_text(encoding="utf-8")
        for name in re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", text):
            if allowed.search(name):
                found.add(name)
    return found


def _port_variables() -> list[str]:
    return sorted(_substituted_variables() - NOT_OPERATOR_INPUT - NOT_A_PORT)


class GatewayPortCheckTest(unittest.TestCase):
    """L-3 (security-rework1.md): KE_GATEWAY_*_LISTEN, KE_API__LISTEN_PORT,
    PHOENIX_PORT and any other substituted port were rendered unchecked, so
    an operator value could add nginx locations or listeners (a proxy_pass to
    1.1.1.1 was demonstrated) and bypass the M-3 allowlist. The entrypoint
    must refuse anything but a decimal integer 1-65535, name the variable,
    and not echo the value."""

    def test_template_variables_are_known(self):
        found = _substituted_variables()
        self.assertTrue(found, "no substituted variables found in docker/gateway/templates")
        for name in ("KE_GATEWAY_API_LISTEN", "KE_GATEWAY_PHOENIX_LISTEN",
                     "KE_GATEWAY_MODEL_LISTEN", "KE_API__LISTEN_PORT", "PHOENIX_PORT"):
            with self.subTest(var=name):
                self.assertIn(name, _port_variables(), f"{name} is not a checked port")

    def test_local_resolvers_is_overwritten_by_the_image(self):
        text = (ROOT / "docker" / "gateway.Dockerfile").read_text(encoding="utf-8")
        self.assertRegex(text, r"NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1",
                         "NGINX_LOCAL_RESOLVERS is exempt only while the image computes it")

    def test_gateway_accepts_valid_ports(self):
        defaults = _gateway_port_defaults()
        for name in _port_variables():
            for value in ("1", "65535", defaults.get(name, "8100")):
                with self.subTest(var=name, value=value):
                    code, output = _run_entrypoint(None, None, **{name: value})
                    self.assertEqual(code, 0, output)

    def test_gateway_refuses_every_bad_or_injected_port(self):
        # Drift: the variable list comes from the templates, so a new `${VAR}`
        # is covered (and fails here) until the entrypoint validates it.
        cases = {**BAD_PORTS, **INJECTIONS}
        for name in _port_variables():
            for case, value in cases.items():
                with self.subTest(var=name, case=case):
                    code, output = _run_entrypoint(None, None, **{name: value})
                    self.assertNotEqual(code, 0,
                                        f"gateway would render {name}={value!r} into nginx config")
                    self.assertIn(name, output, "the refusal must name the variable")
                    if len(value) > 6:
                        self.assertNotIn(value.strip(), output, "the refusal echoes the value")

    def test_every_substituted_variable_refuses_an_injection(self):
        # Every templated name except the image-computed resolver, including
        # KE_MODEL_UPSTREAM (M-3), refuses the L-3 payload.
        payload = INJECTIONS["security L-3 location"]
        for name in sorted(_substituted_variables() - NOT_OPERATOR_INPUT):
            with self.subTest(var=name):
                code, output = _run_entrypoint(None, None, **{name: payload})
                self.assertNotEqual(code, 0, f"{name} accepts an nginx config injection")
                self.assertIn(name, output)


if __name__ == "__main__":
    unittest.main()
