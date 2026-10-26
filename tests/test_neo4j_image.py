"""platform-sbom U4b (PSC-26, human ruling Q67): our own neo4j image,
`ke-neo4j`, without the commercial fleet-management plugin.

Criteria: docs/requirements.md PSC-26 (Build, Tags, Image config carried
over, File tree, Plugin absent, SBOM, Bundled as first-party, Compose and
vendoring, Notices, Not scanned). Design: docs/architecture.md ADR-KE-016
point 12; docs/evidence/platform-sbom/design-notes.md N16. Open questions:
Q67 (human: build our own image), Q68 (ke-neo4j is not scanned).

Fast, static:
- `test_neo4j_dockerfile_pins_base_and_removes_products`
- `test_neo4j_dockerfile_redeclares_base_config` (exactly N16's list)
- `test_compose_neo4j_uses_first_party_image`
- the official reference only as the Dockerfile's FROM; build.sh and
  build.ps1 name ke-neo4j; the source policy names ke-neo4j; the NOTICE.md
  "Base image of `ke-neo4j`" section; install.sh and install.ps1 already
  accept `ke-neo4j:bundle-<12 hex>` (N16: no install change; a guard).

Fast, fake docker:
- bundle.sh treats ke-neo4j as first-party (ke-neo4j:bundle-<sha12>,
  images/ke-neo4j.tar, app/sboms/ke-neo4j.spdx.json, no official image);
- smoke: no products/ and no fleet-management file in the live neo4j (N16
  *Smoke*);
- offline_check.sh runs the ke-neo4j check on the bundle it writes.

The `full` tags of PSC-26 run where:
- `[full: ke-neo4j config matches the pinned official image]`: the
  offline check, `sbom_check.py neo4j --official-config --config` on both
  `docker image inspect .Config` (the tester's placement, flagged: N16 does
  not place it);
- `[full: ke-neo4j file tree equals the official image minus products]`:
  the logic is `sbom_check.py tree`, driven here on stub exports; N16 makes
  the run GREEN evidence, "not a gate step", which PSC-26's `full` tag
  contradicts (flagged);
- `[full: ke-neo4j has no fleet-management plugin in image or saved tar]`:
  the image half is the smoke step (N16), the tar half the offline check's
  `sbom_check.py neo4j --tar` on images/ke-neo4j.tar as bundle.sh saved it;
- `[full: ke-neo4j SBOM lists no fleet-management plugin]`: the offline
  check's `sbom_check.py neo4j --sbom` on the SBOM its bundle writes (PSC-26).
The check logic is in scripts/sbom_check.py (stdlib, `python -I`, N3), so
fast tests drive it with stubs and `full` runs it on the real files.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable

import yaml

from tests import neo4j_support as ns
from tests import sbom_support as ss
from tests import test_offline_check as toc
from tests import test_stack_scripts as tss
from tests.engine_support import ROOT
from tests.test_image_scan import _env_pairs
from tests.test_offline_bundle import _BundleBase, _rel
from tests.test_psycopg_c import _exec_service
from tests.test_sbom_bundle import load_sbom_check

DOCKERFILE = ns.NEO4J_DOCKERFILE
DOCKERFILE_REL = "docker/neo4j.Dockerfile"
DOCKERFILE_MISSING = ("docker/neo4j.Dockerfile is missing (PSC-26 *Build*; design-notes N16: the official image "
                      "minus /var/lib/neo4j/products, flattened FROM scratch)")
PRODUCTS = "/var/lib/neo4j/products"
POLICY = ROOT / "docker" / "source-policy.json"
# The neo4j `always` entries of docker/source-policy.json at U4 (PSC-22),
# which U4b renames to ke-neo4j with their matches unchanged (N16).
NEO4J_ALWAYS_MATCHES = {"pkg:generic/oracle/openjdk", "pkg:maven/org.neo4j/neo4j", "upstream=glibc",
                        "pkg:maven/jrt-fs/jrt-fs", "upstream=gcc-14"}
# The neo4j service as it is at U4, other than its image: PSC-26 keeps all of it.
NEO4J_SERVICE_KEPT = {
    "restart": "unless-stopped",
    "networks": ["backend"],
    "environment": {"NEO4J_AUTH": "neo4j/${KE_STORES__NEO4J__PASSWORD}"},
    "volumes": ["neo4j-data:/data"],
    "healthcheck": {"test": ["CMD-SHELL", "cypher-shell -u neo4j -p \"$${NEO4J_AUTH#*/}\" 'RETURN 1' >/dev/null"],
                    "interval": "10s", "timeout": "10s", "retries": 18, "start_period": "20s"},
}
# Last-stage instructions N16 allows; anything else installs, adds or sets
# what the official image does not.
CONFIG_KEYWORDS = ("ENV", "WORKDIR", "VOLUME", "EXPOSE", "ENTRYPOINT", "CMD")
UNSET_KEYWORDS = ("USER", "HEALTHCHECK", "LABEL", "STOPSIGNAL", "ONBUILD", "SHELL", "MAINTAINER")


def fn(name: str) -> Callable[..., Any]:
    """A function of scripts/sbom_check.py, or a failure naming it."""
    got = getattr(load_sbom_check(), name, None)
    if not callable(got):
        raise AssertionError(f"scripts/sbom_check.py has no {name}() (U4b interface, PSC-26; "
                             "tests/test_neo4j_image.py)")
    return got


# --------------------------------------------------------------------------
# docker/neo4j.Dockerfile, statically
# --------------------------------------------------------------------------

def _instructions(text: str) -> list[tuple[str, str]]:
    """(KEYWORD, rest): continuation lines joined, comment lines dropped."""
    out: list[tuple[str, str]] = []
    current = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#") or (not current and not stripped):
            continue
        if stripped.endswith("\\"):
            current += stripped[:-1] + " "
            continue
        current += stripped
        keyword, _, rest = current.strip().partition(" ")
        out.append((keyword.upper(), rest.strip()))
        current = ""
    if current.strip():
        keyword, _, rest = current.strip().partition(" ")
        out.append((keyword.upper(), rest.strip()))
    return out


def _stages(text: str) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    for keyword, rest in _instructions(text):
        if keyword == "FROM":
            words = rest.split()
            flags = [w for w in words if w.startswith("--")]
            words = [w for w in words if not w.startswith("--")]
            name = words[2] if len(words) >= 3 and words[1].lower() == "as" else None
            stages.append({"ref": words[0] if words else "", "name": name, "flags": flags, "body": []})
        elif stages:
            stages[-1]["body"].append((keyword, rest))
        else:
            stages.append({"ref": None, "name": None, "flags": [], "body": [(keyword, rest)]})
    return stages


_RM_PRODUCTS = re.compile(r"^rm\s+(?:-rf|-fr|-r\s+-f|-f\s+-r)\s+(?:--\s+)?/var/lib/neo4j/products/?$")


def dockerfile_build_problems(text: str) -> list[str]:
    """PSC-26 *Build*: FROM the pinned official image by its full digest; that
    stage only removes /var/lib/neo4j/products; the last stage is `FROM
    scratch` + `COPY --from=<that stage> / /` and installs or adds nothing."""
    stages = _stages(text)
    if len(stages) != 2 or stages[0]["ref"] is None:
        return [f"want exactly two stages (the official image, then scratch), found {len(stages)}"]
    base, last = stages
    problems = []
    if base["ref"] != ns.OFFICIAL_REF:
        problems.append(f"the first stage is FROM {base['ref']!r}, not the pinned {ns.OFFICIAL_REF} (PSC-26 Build)")
    if base["flags"]:
        problems.append(f"the first FROM carries {base['flags']} (the daemon's own arch, no --platform)")
    if not base["name"]:
        problems.append("the first stage has no `AS <name>` for the last stage to copy from")
    runs = [rest for kw, rest in base["body"] if kw == "RUN"]
    if not any(_RM_PRODUCTS.match(r) for r in runs):
        problems.append(f"the first stage does not run exactly `rm -rf {PRODUCTS}` (PSC-26: the directory goes)")
    for kw, rest in base["body"]:
        if not (kw == "RUN" and _RM_PRODUCTS.match(rest)):
            problems.append(f"the first stage also has `{kw} {rest}`: it changes no other file and installs "
                            "no package (PSC-26 Build)")
    if last["ref"] != "scratch" or last["flags"]:
        problems.append(f"the last stage is FROM {last['ref']!r}, not scratch: a delete in a stage FROM the base "
                        "leaves the jar in a layer of the saved tar (N16 *Why flatten*)")
    body = last["body"]
    want_copy = [f"--from={base['name']}", "/", "/"]
    if not body or body[0][0] != "COPY" or body[0][1].split() != want_copy:
        problems.append(f"the last stage does not start with `COPY {' '.join(want_copy)}` (N16, as ke-app N10a)")
    for kw, rest in body[1:]:
        if kw not in CONFIG_KEYWORDS:
            problems.append(f"the last stage has `{kw} {rest}`: only the config is set again (PSC-26 Build)")
    return problems


def _json_list(rest: str) -> list[str] | None:
    try:
        value = json.loads(rest)
    except ValueError:
        return None
    return value if isinstance(value, list) and all(isinstance(v, str) for v in value) else None


def dockerfile_config_problems(text: str, official: dict[str, Any] = ns.OFFICIAL_CONFIG) -> list[str]:
    """PSC-26 *Image config carried over*, statically (N16's list): the last
    stage sets ENTRYPOINT, CMD, every Env entry in order, WORKDIR, EXPOSE
    and VOLUME to the official image's, once each, and sets nothing the
    official image leaves unset (USER, HEALTHCHECK, LABEL, STOPSIGNAL,
    ONBUILD, SHELL)."""
    stages = _stages(text)
    if not stages:
        return ["no FROM"]
    body = stages[-1]["body"]
    problems = []
    seen: dict[str, int] = {}
    env: list[str] = []
    for kw, rest in body:
        seen[kw] = seen.get(kw, 0) + 1
        if kw == "ENV":
            env += [f"{k}={v}" for k, v in _env_pairs(rest)]
        elif kw == "ENTRYPOINT" and _json_list(rest) != official["Entrypoint"]:
            problems.append(f"ENTRYPOINT {rest} is not the exec form {json.dumps(official['Entrypoint'])}")
        elif kw == "CMD" and _json_list(rest) != official["Cmd"]:
            problems.append(f"CMD {rest} is not the exec form {json.dumps(official['Cmd'])}")
        elif kw == "WORKDIR" and rest != official["WorkingDir"]:
            problems.append(f"WORKDIR {rest} is not {official['WorkingDir']}")
        elif kw == "EXPOSE":
            ports = {p if "/" in p else p + "/tcp" for p in rest.split()}
            if ports != set(official["ExposedPorts"]):
                problems.append(f"EXPOSE {rest} is not {sorted(official['ExposedPorts'])}")
        elif kw == "VOLUME":
            vols = _json_list(rest) if rest.startswith("[") else rest.split()
            if sorted(vols or []) != sorted(official["Volumes"]):
                problems.append(f"VOLUME {rest} is not {sorted(official['Volumes'])}")
        elif kw in UNSET_KEYWORDS:
            problems.append(f"`{kw} {rest}`: the official image leaves it unset, so ke-neo4j does too (N16)")
    if env != official["Env"]:
        problems.append(f"Env is {env}, want every entry of the official image's, in order: {official['Env']}")
    for kw in ("ENTRYPOINT", "CMD", "WORKDIR", "EXPOSE", "VOLUME"):
        if seen.get(kw, 0) != 1:
            problems.append(f"the last stage sets {kw} {seen.get(kw, 0)} times, want once (FROM scratch drops "
                            "the base's config; PSC-26)")
    return problems


def _target_like() -> str:
    """The N16 Dockerfile, written out here so the controls never depend on
    the file under test."""
    env = " \\\n    ".join(ns.OFFICIAL_ENV)
    return (f"# ke-neo4j (N16)\nFROM {ns.OFFICIAL_REF} AS runtime\nRUN rm -rf {PRODUCTS}\n\nFROM scratch\n"
            f"COPY --from=runtime / /\nENV {env}\nWORKDIR /var/lib/neo4j\nVOLUME [\"/data\", \"/logs\"]\n"
            "EXPOSE 7473 7474 7687\nENTRYPOINT [\"tini\", \"-g\", \"--\", \"/startup/docker-entrypoint.sh\"]\n"
            "CMD [\"neo4j\"]\n")


def _swap(old: str, new: str) -> Callable[[str], str]:
    def change(text: str) -> str:
        assert old in text, old
        return text.replace(old, new, 1)
    return change


class Neo4jDockerfileTest(unittest.TestCase):
    """PSC-26 *Build* and *Image config carried over*, statically."""

    def _text(self) -> str:
        self.assertTrue(DOCKERFILE.is_file(), DOCKERFILE_MISSING)
        return DOCKERFILE.read_text(encoding="utf-8")

    def test_neo4j_dockerfile_pins_base_and_removes_products(self):
        passing = {
            "the N16 Dockerfile": _target_like(),
            "rm -rf -- with a trailing slash": _swap(f"RUN rm -rf {PRODUCTS}", f"RUN rm -rf -- {PRODUCTS}/")(
                _target_like()),
        }
        unpinned = ns.OFFICIAL_REF.split("@", 1)[0]
        failing = {
            "no removal of products/": _swap(f"RUN rm -rf {PRODUCTS}\n", "")(_target_like()),
            "only the fleet jar removed": _swap(f"RUN rm -rf {PRODUCTS}", f"RUN rm -f /{ns.FLEET_JAR}")(
                _target_like()),
            "products/ emptied, not removed": _swap(f"RUN rm -rf {PRODUCTS}", f"RUN rm -rf {PRODUCTS}/*")(
                _target_like()),
            "a second directory removed": _swap(f"RUN rm -rf {PRODUCTS}",
                                                f"RUN rm -rf {PRODUCTS} /var/lib/neo4j/labs")(_target_like()),
            "the last stage is the official image (no flatten)": (
                f"FROM {ns.OFFICIAL_REF}\nRUN rm -rf {PRODUCTS}\n" + _target_like().split("COPY --from=runtime / /\n",
                                                                                          1)[1]),
            "the last stage FROM the build stage": _swap("FROM scratch", "FROM runtime")(_target_like()),
            "an unpinned FROM": _swap(ns.OFFICIAL_REF, unpinned)(_target_like()),
            "another digest": _swap(ns.OFFICIAL_REF, unpinned + "@sha256:" + "0" * 64)(_target_like()),
            "a package install": _swap(f"RUN rm -rf {PRODUCTS}", f"RUN rm -rf {PRODUCTS} && apt-get update && "
                                                                 "apt-get install -y curl")(_target_like()),
            "a second RUN in the build stage": _swap(f"RUN rm -rf {PRODUCTS}\n",
                                                     f"RUN rm -rf {PRODUCTS}\nRUN chmod 0755 /data\n")(_target_like()),
            "COPY of part of the root": _swap("COPY --from=runtime / /", "COPY --from=runtime /var /var")(
                _target_like()),
            "COPY --chown (ownership changes)": _swap("COPY --from=runtime / /", "COPY --chown=7474:7474 "
                                                                               "--from=runtime / /")(_target_like()),
            "a file from the build context": _swap("WORKDIR /var/lib/neo4j", "COPY conf/neo4j.conf /var/lib/neo4j/"
                                                                             "conf/\nWORKDIR /var/lib/neo4j")(
                _target_like()),
            "a RUN in the last stage": _swap("WORKDIR /var/lib/neo4j", "RUN true\nWORKDIR /var/lib/neo4j")(
                _target_like()),
            "--platform on the base": _swap(f"FROM {ns.OFFICIAL_REF}", f"FROM --platform=linux/amd64 "
                                                                       f"{ns.OFFICIAL_REF}")(_target_like()),
        }
        for case, text in passing.items():
            with self.subTest(control=case):
                self.assertEqual(dockerfile_build_problems(text), [], f"a control that must pass failed: {case}")
        for case, text in failing.items():
            with self.subTest(control=case):
                self.assertNotEqual(dockerfile_build_problems(text), [], f"the check passed: {case}")
        self.assertEqual(dockerfile_build_problems(self._text()), [], DOCKERFILE_REL)

    def test_neo4j_dockerfile_redeclares_base_config(self):
        with self.subTest(part="the recorded config is for the pinned digest (re-read on every bump, N16)"):
            self.assertEqual(ns.dockerfile_base_ref() or ns.OFFICIAL_REF, ns.OFFICIAL_REF,
                             "the Dockerfile's base moved: re-read `docker image inspect` and update "
                             "tests/neo4j_support.py OFFICIAL_CONFIG with it (N16)")
        text = _target_like()
        two_env = _swap(" \\\n    NEO4J_TARBALL", "\nENV NEO4J_TARBALL")(text)
        passing = {"the N16 Dockerfile": text, "Env over two ENV lines, same order": two_env,
                   "VOLUME in shell form": _swap('VOLUME ["/data", "/logs"]', "VOLUME /data /logs")(text),
                   "EXPOSE with /tcp": _swap("EXPOSE 7473 7474 7687", "EXPOSE 7473/tcp 7474/tcp 7687/tcp")(text)}
        failing: dict[str, str] = {}
        for kw, line in (("ENTRYPOINT", 'ENTRYPOINT ["tini", "-g", "--", "/startup/docker-entrypoint.sh"]\n'),
                         ("CMD", 'CMD ["neo4j"]\n'), ("WORKDIR", "WORKDIR /var/lib/neo4j\n"),
                         ("EXPOSE", "EXPOSE 7473 7474 7687\n"), ("VOLUME", 'VOLUME ["/data", "/logs"]\n')):
            failing[f"no {kw}"] = _swap(line, "")(text)
        failing["no ENV"] = re.sub(r"ENV PATH=.*?LANG=C\.UTF-8\n", "", text, flags=re.S)
        for i, entry in enumerate(ns.OFFICIAL_ENV):
            key = entry.split("=", 1)[0]
            failing[f"Env without {key}"] = re.sub(rf"\s*\\\n\s*{re.escape(entry)}|{re.escape(entry)} \\\n\s*", "",
                                                   text, count=1)
        failing["Env out of order (NEO4J_HOME first)"] = _swap("ENV PATH=", "ENV NEO4J_HOME=/var/lib/neo4j \\\n"
                                                                            "    PATH=")(
            _swap(" \\\n    NEO4J_HOME=/var/lib/neo4j", "")(text))
        failing["Env with one more entry"] = _swap("LANG=C.UTF-8", "LANG=C.UTF-8 \\\n    NEO4J_PLUGINS=[]")(text)
        failing["Env with another value (LANG)"] = _swap("LANG=C.UTF-8", "LANG=en_US.UTF-8")(text)
        failing["PATH with $PATH (scratch has none)"] = _swap("/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:"
                                                              "/sbin:/bin", "$PATH")(text)
        failing["USER neo4j"] = _swap("WORKDIR", "USER neo4j\nWORKDIR")(text)
        failing["USER 7474:7474"] = _swap("WORKDIR", "USER 7474:7474\nWORKDIR")(text)
        failing["a HEALTHCHECK"] = _swap("WORKDIR", "HEALTHCHECK CMD cypher-shell 'RETURN 1'\nWORKDIR")(text)
        failing["a LABEL"] = _swap("WORKDIR", "LABEL org.opencontainers.image.title=ke-neo4j\nWORKDIR")(text)
        failing["a STOPSIGNAL"] = _swap("WORKDIR", "STOPSIGNAL SIGTERM\nWORKDIR")(text)
        failing["a SHELL"] = _swap("WORKDIR", 'SHELL ["/bin/bash", "-c"]\nWORKDIR')(text)
        failing["ENTRYPOINT in shell form"] = _swap('ENTRYPOINT ["tini", "-g", "--", "/startup/docker-entrypoint.sh"]',
                                                    "ENTRYPOINT tini -g -- /startup/docker-entrypoint.sh")(text)
        failing["CMD console"] = _swap('CMD ["neo4j"]', 'CMD ["neo4j", "console"]')(text)
        failing["WORKDIR elsewhere"] = _swap("WORKDIR /var/lib/neo4j", "WORKDIR /")(text)
        failing["EXPOSE without 7473"] = _swap("EXPOSE 7473 7474 7687", "EXPOSE 7474 7687")(text)
        failing["VOLUME /data only"] = _swap('VOLUME ["/data", "/logs"]', 'VOLUME ["/data"]')(text)
        failing["VOLUME twice"] = _swap('VOLUME ["/data", "/logs"]', 'VOLUME ["/data"]\nVOLUME ["/logs"]')(text)
        for case, value in passing.items():
            with self.subTest(control=case):
                self.assertEqual(dockerfile_config_problems(value), [], f"a control that must pass failed: {case}")
        for case, value in failing.items():
            with self.subTest(control=case):
                self.assertNotEqual(value, text, f"precondition: the mutant changes the text ({case})")
                self.assertNotEqual(dockerfile_config_problems(value), [], f"the check passed: {case}")
        self.assertEqual(dockerfile_config_problems(self._text()), [], DOCKERFILE_REL)


# --------------------------------------------------------------------------
# Compose, build scripts and the official reference
# --------------------------------------------------------------------------

def compose_neo4j_problems(doc: dict[str, Any], text: str) -> list[str]:
    """PSC-26 *Compose and vendoring* on docker-compose.yml (parsed, and its
    text): image ke-neo4j:${KE_IMAGE_TAG:-local}, build of the new Dockerfile,
    everything else of the service and the depends_on edge unchanged, and no
    official reference anywhere in the file."""
    services = doc.get("services") or {}
    svc = services.get("neo4j")
    if not isinstance(svc, dict):
        return ["docker-compose.yml has no neo4j service (the service name stays neo4j)"]
    problems = []
    if svc.get("image") != ns.KE_NEO4J_IMAGE:
        problems.append(f"neo4j's image is {svc.get('image')!r}, want {ns.KE_NEO4J_IMAGE} (PSC-26 Tags)")
    build = svc.get("build")
    if not isinstance(build, dict) or build.get("dockerfile") != DOCKERFILE_REL or build.get("context") != ".":
        problems.append(f"neo4j's build is {build!r}, want {{context: ., dockerfile: {DOCKERFILE_REL}}} (N16)")
    elif set(build) != {"context", "dockerfile"}:
        problems.append(f"neo4j's build sets {sorted(set(build) - {'context', 'dockerfile'})} too (N16: nothing else)")
    for key, want in NEO4J_SERVICE_KEPT.items():
        if svc.get(key) != want:
            problems.append(f"neo4j's {key} changed: {svc.get(key)!r}, want {want!r} (PSC-26: unchanged)")
    extra = sorted(set(svc) - set(NEO4J_SERVICE_KEPT) - {"image", "build"})
    if extra:
        problems.append(f"neo4j gains {extra} (PSC-26: only image and build change)")
    dep = (services.get("api") or {}).get("depends_on") or {}
    if not isinstance(dep, dict) or dep.get("neo4j") != {"condition": "service_healthy"}:
        problems.append("api's depends_on edge to neo4j changed (PSC-26: unchanged)")
    if "neo4j:5-community" in text:
        problems.append("docker-compose.yml still names neo4j:5-community (PSC-26: the official reference leaves it)")
    return problems


def _build_inputs() -> list[Path]:
    """The repo's build inputs: compose files, docker/, scripts/, CI."""
    files = sorted(ROOT.glob("docker-compose*.yml"))
    for top in ("docker", "scripts", ".github"):
        files += sorted(p for p in (ROOT / top).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    return files


def official_ref_problems(files: dict[str, str]) -> list[str]:
    """PSC-26: the official reference appears in the build inputs only as the
    new Dockerfile's FROM, exactly once."""
    problems = []
    hits = {rel: [ln for ln in text.splitlines() if "neo4j:5-community" in ln] for rel, text in files.items()}
    for rel, lines in sorted(hits.items()):
        if not lines:
            continue
        if rel != DOCKERFILE_REL:
            problems.append(f"{rel} names the official image: {lines[0].strip()[:120]}")
        elif [ln.strip() for ln in lines if not ln.lstrip().startswith("#")] != [f"FROM {ns.OFFICIAL_REF} AS runtime"]:
            problems.append(f"{rel} names the official image other than as its one FROM: {lines}")
    if not hits.get(DOCKERFILE_REL):
        problems.append(f"{DOCKERFILE_REL} does not name the official image in its FROM")
    return problems


def _header(text: str) -> str:
    """The leading comment block of a script (shebang skipped), as one line."""
    lines = []
    for line in text.splitlines():
        if line.startswith("#!"):
            continue
        if not line.startswith("#"):
            break
        lines.append(line.lstrip("#").strip())
    return " ".join(lines)


def build_script_problems(name: str, text: str) -> list[str]:
    """build.sh / build.ps1: the header lists ke-neo4j with the images built;
    the logic is unchanged: compose builds every service with a `build:`,
    then `pull --ignore-buildable` (N16), and nothing names or pulls the
    official neo4j image."""
    problems = []
    head = _header(text)
    m = re.search(r"Builds the images \(([^)]*)\)", head)
    built = {w.strip() for w in m.group(1).split(",")} if m else set()
    if "ke-neo4j" not in built:
        problems.append(f"{name}'s header does not list ke-neo4j among the images it builds: {head[:160]!r}")
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    if not re.search(r"docker compose\b.*--profile '\*' build\s*$", code, re.M):
        problems.append(f"{name} no longer runs `docker compose ... --profile '*' build`")
    if not re.search(r"docker compose\b.*--profile '\*' pull --ignore-buildable\s*$", code, re.M):
        problems.append(f"{name} no longer runs `docker compose ... --profile '*' pull --ignore-buildable`")
    if re.search(r"neo4j", code):
        problems.append(f"{name} names neo4j in its code (compose builds ke-neo4j; nothing pulls the official image)")
    return problems


class Neo4jComposeTest(unittest.TestCase):
    """PSC-26 *Compose and vendoring* and *Tags*."""

    def test_compose_neo4j_uses_first_party_image(self):
        path = ROOT / "docker-compose.yml"
        text = path.read_text(encoding="utf-8")
        doc = yaml.safe_load(text)
        good = copy.deepcopy(doc)
        good["services"]["neo4j"]["image"] = ns.KE_NEO4J_IMAGE
        good["services"]["neo4j"]["build"] = {"context": ".", "dockerfile": DOCKERFILE_REL}
        clean = text.replace("neo4j:5-community", "ke-neo4j")
        with self.subTest(control="the U4b service passes"):
            self.assertEqual(compose_neo4j_problems(good, clean), [])

        def mutate(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
            d = copy.deepcopy(good)
            change(d["services"])
            return d
        failing = {
            "the official image (U4)": (mutate(lambda s: s["neo4j"].update(image=ns.OFFICIAL_REF)), clean),
            "ke-neo4j:latest": (mutate(lambda s: s["neo4j"].update(image="ke-neo4j:latest")), clean),
            "no build": (mutate(lambda s: s["neo4j"].pop("build")), clean),
            "build of the app Dockerfile": (mutate(lambda s: s["neo4j"]["build"].update(
                dockerfile="docker/app.Dockerfile")), clean),
            "build with args": (mutate(lambda s: s["neo4j"]["build"].update(args={"X": "1"})), clean),
            "healthcheck changed": (mutate(lambda s: s["neo4j"]["healthcheck"].update(retries=3)), clean),
            "environment changed": (mutate(lambda s: s["neo4j"]["environment"].update(NEO4J_PLUGINS="[]")), clean),
            "a user set": (mutate(lambda s: s["neo4j"].update(user="7474:7474")), clean),
            "volumes changed": (mutate(lambda s: s["neo4j"].update(volumes=["neo4j-data:/data", "x:/logs"])), clean),
            "networks changed": (mutate(lambda s: s["neo4j"].update(networks=["backend", "edge"])), clean),
            "service renamed": (mutate(lambda s: s.update({"graph": s.pop("neo4j")})), clean),
            "api's depends_on edge gone": (mutate(lambda s: s["api"]["depends_on"].pop("neo4j")), clean),
            "the official ref left in a comment": (good, clean + f"\n# was {ns.OFFICIAL_REF}\n"),
        }
        for case, (d, t) in failing.items():
            with self.subTest(control=case):
                self.assertNotEqual(compose_neo4j_problems(d, t), [], f"the check passed: {case}")
        self.assertEqual(compose_neo4j_problems(doc, text), [], "docker-compose.yml")

    def test_neo4j_official_ref_only_in_dockerfile_from(self):
        target = {DOCKERFILE_REL: _target_like(), "docker-compose.yml": "image: ke-neo4j:${KE_IMAGE_TAG:-local}\n"}
        with self.subTest(control="only the Dockerfile's FROM passes"):
            self.assertEqual(official_ref_problems(target), [])
        failing = {
            "compose still pins it": dict(target, **{"docker-compose.yml": f"image: {ns.OFFICIAL_REF}\n"}),
            "a script pulls it": dict(target, **{"scripts/build.sh": f"docker pull {ns.OFFICIAL_REF}\n"}),
            "the Dockerfile names it twice": dict(target, **{DOCKERFILE_REL: _target_like() + f"FROM {ns.OFFICIAL_REF}\n"}),
            "no Dockerfile": {"docker-compose.yml": "image: ke-neo4j:local\n"},
        }
        for case, files in failing.items():
            with self.subTest(control=case):
                self.assertNotEqual(official_ref_problems(files), [], f"the check passed: {case}")
        files = {}
        for p in _build_inputs():
            try:
                files[p.relative_to(ROOT).as_posix()] = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
        self.assertEqual(official_ref_problems(files), [], "the repo's build inputs")

    def test_build_scripts_build_ke_neo4j(self):
        for name in ("build.sh", "build.ps1"):
            text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            with self.subTest(script=name, control="the U4 header (no ke-neo4j) fails"):
                u4 = re.sub(r"ke-neo4j,\s*", "", text)
                self.assertNotEqual(build_script_problems(name, u4), [])
            with self.subTest(script=name, control="an explicit pull of the official image fails"):
                pulled = text + f"\ndocker pull {ns.OFFICIAL_REF}\n"
                self.assertTrue([p for p in build_script_problems(name, pulled) if "names neo4j" in p])
            with self.subTest(script=name):
                self.assertEqual(build_script_problems(name, text), [], f"scripts/{name}")

    def test_install_accepts_ke_neo4j_bundle_tag(self):
        """N16 *Bundle and install*: install.sh and install.ps1 already accept
        `ke-[a-z0-9._-]+:bundle-<12 hex>` and write the neo4j override; no
        install change. A guard, green before and after U4b."""
        sh = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
        ps1 = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
        sh_as = re.search(r"as_re='([^']+)'", sh)
        ps_as = re.search(r"\$asRe = '([^']+)'", ps1)
        self.assertTrue(sh_as and ps_as, "precondition: the installers' `as` patterns")
        assert sh_as and ps_as
        for label, rx in (("install.sh", sh_as.group(1)), ("install.ps1", ps_as.group(1))):
            with self.subTest(installer=label):
                self.assertRegex("ke-neo4j:bundle-0123456789ab", rf"^{rx}$")
                self.assertNotRegex("ke-neo4j:wt-0123456789ab", rf"^{rx}$")


# --------------------------------------------------------------------------
# source policy and NOTICE.md
# --------------------------------------------------------------------------

def policy_problems(always: Any) -> list[str]:
    if not isinstance(always, list):
        return ["docker/source-policy.json has no `always` list"]
    problems = []
    old = [e for e in always if isinstance(e, dict) and e.get("image") == "neo4j"]
    if old:
        problems.append(f"{len(old)} `always` entries still name image neo4j (N16: they name ke-neo4j)")
    matches = {e.get("match") for e in always if isinstance(e, dict) and e.get("image") == "ke-neo4j"}
    if matches != NEO4J_ALWAYS_MATCHES:
        problems.append(f"the ke-neo4j `always` matches are {sorted(matches)}, want U4's neo4j set "
                        f"{sorted(NEO4J_ALWAYS_MATCHES)} unchanged (N16)")
    return problems


def notice_neo4j_problems(text: str, base_ref: str) -> list[str]:
    """PSC-26 *Notices* in the N16 form: no neo4j vendor row; a `Base image
    of ke-neo4j` section with the Dockerfile's base byte for byte, the
    removed products/ and why, Neo4j Community unmodified, GPL-3.0, its
    LICENSE.txt path, the upstream source (https) and the licence text."""
    problems = []
    rows = [ln for ln in text.splitlines() if ln.lstrip().startswith("|")]
    if [r for r in rows if "neo4j:5-community" in r or re.match(r"^\|\s*(?:ke-)?neo4j\s*\|", r)]:
        problems.append("NOTICE.md still has a neo4j vendor row (N16: the row leaves `Vendor images`)")
    parts = re.split(r"(?m)^## ", text)
    sections = [p for p in parts if p.startswith("Base image of `ke-neo4j`")]
    if len(sections) != 1:
        return problems + [f"NOTICE.md has {len(sections)} `## Base image of `ke-neo4j`` sections, want 1 (N16)"]
    body = " ".join(sections[0].split())
    if f"`{base_ref}`" not in sections[0]:
        problems.append(f"the section does not give the base `{base_ref}` byte for byte (the Dockerfile's FROM)")
    for needle, why in ((PRODUCTS, "the removed directory"), ("fleet-management", "the plugin it held"),
                        ("commercial", "why it goes (Q67)"), ("GPL-3.0", "the licence"),
                        ("/var/lib/neo4j/LICENSE.txt", "the licence file inside the image"),
                        ("licenses/GPL-3.0.txt", "the licence text"), ("Upstream source:", "the source (L-NT1)"),
                        ("https://github.com/neo4j/neo4j", "the upstream source"), ("5.26.32", "the version")):
        if needle not in body:
            problems.append(f"the section does not name {needle} ({why})")
    if not re.search(r"Neo4j Community[^.]*\bunmodified\b", body):
        problems.append("the section does not say Neo4j Community itself is unmodified (PSC-26)")
    if re.search(r"(?i)used unmodified", body):
        problems.append("the section says `used unmodified`: ke-neo4j changes the image (PSC-26)")
    if re.search(r"(?i)corresponding source is at", body) or "http://" in body:
        problems.append("the section claims compliance or gives an http source (audit-nt L-NT1)")
    return problems


class Neo4jPolicyAndNoticeTest(unittest.TestCase):

    def test_source_policy_names_ke_neo4j(self):
        always = json.loads(POLICY.read_text(encoding="utf-8")).get("always")
        renamed = [dict(e, image="ke-neo4j") if isinstance(e, dict) and e.get("image") == "neo4j" else e
                   for e in always or []]
        with self.subTest(control="the U4 policy (neo4j keys) fails"):
            u4 = [dict(e, image="neo4j") if isinstance(e, dict) and e.get("image") == "ke-neo4j" else e
                  for e in always or []]
            self.assertNotEqual(policy_problems(u4), [])
        with self.subTest(control="a match dropped in the rename fails"):
            self.assertNotEqual(policy_problems([e for e in renamed if e.get("match") != "upstream=gcc-14"
                                                 or e.get("image") != "ke-neo4j"]), [])
        with self.subTest(part="each ke-neo4j entry matches a package in ke-neo4j's SBOM (stand-in, N16)"):
            flagged, problems = fn("always_matches")("ke-neo4j", ns.ke_neo4j_doc(), renamed)
            self.assertEqual(problems, [])
            self.assertTrue(flagged)
        self.assertEqual(policy_problems(always), [], "docker/source-policy.json")

    def test_notice_has_ke_neo4j_base_section(self):
        text = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
        base = ns.dockerfile_base_ref() or ns.OFFICIAL_REF
        model = ("| Image | Reference |\n|---|---|\n| postgres | `postgres:16@sha256:" + "0" * 64 + "` |\n\n"
                 "## Base image of `ke-neo4j`\n\n`docker/neo4j.Dockerfile` builds `ke-neo4j` from\n"
                 f"`{ns.OFFICIAL_REF}`\n(Neo4j Community 5.26.32) and removes `{PRODUCTS}`, which holds the "
                 "fleet-management plugin under a commercial licence. Neo4j Community itself is unmodified, GPL-3.0 "
                 "(`/var/lib/neo4j/LICENSE.txt`); the text is `licenses/GPL-3.0.txt`. Upstream source: "
                 "https://github.com/neo4j/neo4j (tag 5.26.32).\n\n## Next\n")
        with self.subTest(control="the N16 section passes"):
            self.assertEqual(notice_neo4j_problems(model, ns.OFFICIAL_REF), [])
        failing = {
            "the U4 vendor row kept": f"| neo4j | `{ns.OFFICIAL_REF}` | GPL-3.0 | x | y |\n" + model,
            "another digest": model.replace(ns.OFFICIAL_REF, ns.OFFICIAL_REF[:-1] + "0"),
            "the tag only": model.replace(ns.OFFICIAL_REF, "neo4j:5-community"),
            "products/ not named": model.replace(f"`{PRODUCTS}`", "a directory"),
            "the plugin not named": model.replace("fleet-management plugin", "plugin"),
            "used unmodified": model.replace("Neo4j Community itself is unmodified", "Neo4j Community, used unmodified"),
            "no unmodified statement": model.replace("itself is unmodified", "is shipped"),
            "http source": model.replace("https://github.com", "http://github.com"),
            "no licence path": model.replace("(`/var/lib/neo4j/LICENSE.txt`)", ""),
            "no section": model.split("## Base image")[0],
        }
        for case, value in failing.items():
            with self.subTest(control=case):
                self.assertNotEqual(notice_neo4j_problems(value, ns.OFFICIAL_REF), [], f"the check passed: {case}")
        self.assertEqual(notice_neo4j_problems(text, base), [], "NOTICE.md")


# --------------------------------------------------------------------------
# bundle.sh: ke-neo4j is first-party (fake docker)
# --------------------------------------------------------------------------

def first_party_problems(data: dict[str, Any], files: set[str], sha: str, ref: str) -> list[str]:
    """PSC-26 *Bundled as first-party* on bundle.json (`data`) and the
    bundle's file list."""
    problems = []
    text = json.dumps(data)
    entries = [e for e in data.get("images", []) if "neo4j" in str(e.get("services", "")).split()]
    want = {"file": "images/ke-neo4j.tar", "ref": ref, "as": f"ke-neo4j:bundle-{sha[:12]}", "services": "neo4j"}
    if entries != [want]:
        problems.append(f"bundle.json's neo4j entry is {entries}, want [{want}]")
    for bad in ("ke-vendor/neo4j", "neo4j:5-community"):
        if bad in text:
            problems.append(f"bundle.json names {bad} (the official image does not ship beside ke-neo4j)")
    for rel in ("images/ke-neo4j.tar", "app/sboms/ke-neo4j.spdx.json"):
        if rel not in files:
            problems.append(f"the bundle has no {rel}")
    for rel in ("images/neo4j.tar", "app/sboms/neo4j.spdx.json"):
        if rel in files:
            problems.append(f"the bundle has {rel}")
    return problems


class BundleKeNeo4jTest(_BundleBase, unittest.TestCase):
    """PSC-26 *Bundled as first-party* and *Tags*: bundle.sh, unchanged (N16),
    saves the compose ref ke-neo4j:<tag> as ke-neo4j:bundle-<sha12>."""

    def test_bundle_saves_ke_neo4j_as_first_party(self):
        sha = "a" * 40
        good = {"images": [{"file": "images/ke-neo4j.tar", "ref": "ke-neo4j:local", "as": f"ke-neo4j:bundle-{'a' * 12}",
                            "services": "neo4j"}]}
        files = {"images/ke-neo4j.tar", "app/sboms/ke-neo4j.spdx.json"}
        with self.subTest(control="a ke-neo4j bundle passes"):
            self.assertEqual(first_party_problems(good, files, sha, "ke-neo4j:local"), [])
        u4 = {"images": [{"file": "images/neo4j.tar", "ref": ns.OFFICIAL_REF, "as": "ke-vendor/neo4j:0a6e7aedf54a",
                          "services": "neo4j"}]}
        failing = {
            "the U4 bundle (official image, vendored)": (u4, {"images/neo4j.tar", "app/sboms/neo4j.spdx.json"}),
            "both images": ({"images": good["images"] + [dict(u4["images"][0], services="graph")]},
                            files | {"images/neo4j.tar"}),
            "no SBOM": (good, {"images/ke-neo4j.tar"}),
            "a stale sha": ({"images": [dict(good["images"][0], **{"as": "ke-neo4j:bundle-" + "b" * 12})]}, files),
        }
        for case, (d, f) in failing.items():
            with self.subTest(control=case):
                self.assertNotEqual(first_party_problems(d, f, sha, "ke-neo4j:local"), [], f"the check passed: {case}")
        ref = self.stack.get("neo4j", "")
        self.assertTrue(ref.startswith("ke-neo4j:"), f"compose's neo4j service is {ref!r}, not ke-neo4j (PSC-26)")
        _, _, out, data = self._ok()
        listed = {_rel(p, out) for p in out.rglob("*") if p.is_file()}
        self.assertEqual(first_party_problems(data, listed, self.sha, ref), [])
        manifest = (out / "MANIFEST.sha256").read_text(encoding="utf-8")
        for rel in ("images/ke-neo4j.tar", "app/sboms/ke-neo4j.spdx.json"):
            self.assertIn(f"  {rel}\n", manifest, f"{rel} is listed in the manifest")
        sbom = json.loads((out / "app" / "sboms" / "ke-neo4j.spdx.json").read_text(encoding="utf-8"))
        self.assertEqual(sbom.get("name"), ref, "the SBOM names the compose (wt-/local) ref (N16: ke:ref)")
        notices = (out / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertNotIn("neo4j:5-community", notices, "no official neo4j row among the bundle's stack images")


# --------------------------------------------------------------------------
# The full-check logic (scripts/sbom_check.py), driven on stubs
# --------------------------------------------------------------------------

class _Tmp(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.n = 0

    def _tar(self, layers: list[list[tuple[str, str]]], **kw: Any) -> str:
        self.n += 1
        return str(ns.save_tar(self.tmp / f"t{self.n}" / "ke-neo4j.tar", layers, **kw))


class Neo4jConfigCheckTest(unittest.TestCase):
    """`[full: ke-neo4j config matches the pinned official image]`: the logic."""

    def test_neo4j_config_check_logic(self):
        check = fn("neo4j_config_problems")
        official = copy.deepcopy(ns.OFFICIAL_CONFIG)
        passing = {
            "equal": copy.deepcopy(official),
            "compose's labels (not compared)": dict(copy.deepcopy(official), Labels=ns.COMPOSE_LABELS),
            "unset fields absent, null or empty": dict(copy.deepcopy(official), User="", Healthcheck=None,
                                                      StopSignal="", OnBuild=None, Shell=None),
        }
        failing: dict[str, tuple[dict[str, Any], str]] = {
            "User 7474": (dict(official, User="7474"), "User"),
            "User neo4j": (dict(official, User="neo4j"), "User"),
            "Env out of order": (dict(official, Env=official["Env"][1:] + official["Env"][:1]), "Env"),
            "Env without LANG": (dict(official, Env=official["Env"][:-1]), "Env"),
            "Env with BuildKit's default PATH added": (dict(official, Env=["PATH=/usr/local/sbin:/usr/local/bin:"
                                                                           "/usr/sbin:/usr/bin:/sbin:/bin"]
                                                            + official["Env"]), "Env"),
            "Entrypoint without tini": (dict(official, Entrypoint=["/startup/docker-entrypoint.sh"]), "Entrypoint"),
            "Cmd console": (dict(official, Cmd=["neo4j", "console"]), "Cmd"),
            "WorkingDir /": (dict(official, WorkingDir="/"), "WorkingDir"),
            "ExposedPorts without 7473": (dict(official, ExposedPorts={"7474/tcp": {}, "7687/tcp": {}}), "ExposedPorts"),
            "Volumes without /logs": (dict(official, Volumes={"/data": {}}), "Volumes"),
            "a Healthcheck": (dict(official, Healthcheck={"Test": ["CMD", "true"]}), "Healthcheck"),
            "a StopSignal": (dict(official, StopSignal="SIGINT"), "StopSignal"),
            "an OnBuild": (dict(official, OnBuild=["RUN true"]), "OnBuild"),
            "a Shell": (dict(official, Shell=["/bin/bash", "-c"]), "Shell"),
            "no Entrypoint": ({k: v for k, v in official.items() if k != "Entrypoint"}, "Entrypoint"),
        }
        for case, image in passing.items():
            with self.subTest(case=case):
                self.assertEqual(check(official, image), [], case)
        for case, (image, key) in failing.items():
            with self.subTest(case=case):
                problems = check(official, image)
                self.assertTrue([p for p in problems if key in p], f"no problem names {key} ({case}): {problems}")
        with self.subTest(case="the check is symmetric: the official image differs, ke-neo4j is the recorded one"):
            self.assertNotEqual(check(dict(official, User="7474"), official), [])
        with self.subTest(case="a config that is not an object"):
            self.assertNotEqual(check(official, None), [])


class Neo4jTarCheckTest(_Tmp):
    """`[full: ke-neo4j has no fleet-management plugin in image or saved
    tar]`, the tar half: every layer manifest.json lists, whiteouts too."""

    def test_neo4j_tar_check_logic(self):
        check = fn("neo4j_tar_problems")
        clean = ns.CLEAN_LAYER
        products = [("var/lib/neo4j/products/", "dir"), (ns.FLEET_JAR, "file"), (ns.GENAI_JAR, "file")]
        passing = {
            "one clean layer (oci)": self._tar([clean]),
            "one clean layer (legacy)": self._tar([clean], form="legacy"),
            "a gzip layer, clean": self._tar([clean], compress=(0,)),
            "near misses: productsx/, a fleet- name, labs": self._tar([clean + [
                ("var/lib/neo4j/productsx/", "dir"), ("var/lib/neo4j/lib/neo4j-fleet-client.jar", "file")]]),
        }
        failing = {
            "the official layers (products/ and both jars)": (self._tar([clean + products]), "products"),
            "products/ only, empty": (self._tar([clean + [("var/lib/neo4j/products/", "dir")]]), "products"),
            "the jar in a lower layer, a clean top layer": (self._tar([clean + products, clean]), "products"),
            "a whiteout of products/ over it (U1's pip finding)": (
                self._tar([clean + products, [("var/lib/neo4j/.wh.products", "file")]]), "whiteout"),
            "a whiteout only": (self._tar([clean, [("var/lib/neo4j/.wh.products", "file")]]), "whiteout"),
            "an opaque whiteout in products/": (
                self._tar([clean, [("var/lib/neo4j/products/.wh..wh..opq", "file")]]), "products"),
            "the plugin moved elsewhere": (
                self._tar([clean + [("opt/neo4j-fleet-management-plugin-1.2.0-v5.jar", "file")]]), "fleet"),
            "the plugin in a gzip layer": (self._tar([clean + products], compress=(0,)), "products"),
            "the plugin in legacy layout": (self._tar([clean + products], form="legacy"), "products"),
            "a second manifest entry holds it": (self._tar([clean], extra_images=[[clean + products]]), "products"),
            "a layer listed but not in the tar": (self._tar([clean, [("etc/second", "file")]], drop_blob=1),
                                                  "not in the tar"),
            "./-prefixed names": (self._tar([clean + [("./var/lib/neo4j/products/x.jar", "file")]]), "products"),
        }
        for case, path in passing.items():
            with self.subTest(case=case):
                self.assertEqual(check(path), [], case)
        for case, (path, word) in failing.items():
            with self.subTest(case=case):
                problems = check(path)
                self.assertTrue([p for p in problems if word in p], f"no problem names {word!r} ({case}): {problems}")
        with self.subTest(case="a manifest.json with no image"):
            empty = self.tmp / "empty.tar"
            import io
            import tarfile
            with tarfile.open(empty, "w") as tar:
                info = tarfile.TarInfo("manifest.json")
                info.size = 2
                tar.addfile(info, io.BytesIO(b"[]"))
            self.assertNotEqual(check(str(empty)), [])


class Neo4jSbomCheckTest(unittest.TestCase):
    """`[full: ke-neo4j SBOM lists no fleet-management plugin]`: the logic."""

    def test_neo4j_sbom_check_logic(self):
        check = fn("neo4j_sbom_problems")
        fleet = {"purl": ns.FLEET_PURL, "declared": "NOASSERTION", "concluded": "NOASSERTION"}
        passing = {"ke-neo4j (the U3 neo4j list without products/)": ns.ke_neo4j_doc()}
        failing = {
            "the official image's list (U3)": (ns.ke_neo4j_doc(keep_plugins=True), "fleet-management"),
            "the plugin at another version": (ns.ke_neo4j_doc(extra=(dict(fleet, purl=ns.FLEET_PURL.replace(
                "1.2.0", "1.3.1")),)), "fleet-management"),
            "the plugin by name only (no purl)": (ns.ke_neo4j_doc(extra=({"purl": None, "name":
                                                                           "neo4j-fleet-management-plugin"},)),
                                                  "fleet-management"),
            "the plugin purl percent-encoded": (ns.ke_neo4j_doc(extra=(dict(fleet, purl=ns.FLEET_PURL.replace(
                "com.neo4j", "com%2Eneo4j")),)), "fleet-management"),
            "the plugin purl with qualifiers": (ns.ke_neo4j_doc(extra=(dict(fleet, purl=ns.FLEET_PURL + "?type=jar"),)),
                                                "fleet-management"),
            # syft may name a jar by its file or manifest, not its artifactId:
            # the purl alone must catch it, at any version.
            "the plugin purl under another name": (ns.ke_neo4j_doc(extra=(dict(fleet, name="neo4j-plugin"),)),
                                                   "fleet-management"),
            "the plugin purl at another version, another name": (ns.ke_neo4j_doc(extra=(dict(
                fleet, name="fm", purl=ns.FLEET_PURL.replace("1.2.0", "2.0.0")),)), "fleet-management"),
            "the plugin purl percent-encoded, another name": (ns.ke_neo4j_doc(extra=(dict(
                fleet, name="fm", purl=ns.FLEET_PURL.replace("com.neo4j", "com%2Eneo4j")),)), "fleet-management"),
            "no Neo4j Community": (ss.spdx_doc("ke-neo4j", [r for r in ns.ke_neo4j_rows() if not (r.get("purl") or "")
                                                            .startswith("pkg:maven/org.neo4j/neo4j@")]), "Neo4j"),
            "no Temurin": (ss.spdx_doc("ke-neo4j", [r for r in ns.ke_neo4j_rows() if not (r.get("purl") or "")
                                                    .startswith("pkg:generic/oracle/openjdk@")]), "Temurin"),
        }
        for case, doc in passing.items():
            with self.subTest(case=case):
                self.assertEqual(check(doc), [], case)
        for case, (doc, word) in failing.items():
            with self.subTest(case=case):
                problems = check(doc)
                self.assertTrue([p for p in problems if word in p], f"no problem names {word!r} ({case}): {problems}")
        with self.subTest(case="the image root package is not a component"):
            doc = ns.ke_neo4j_doc()
            doc["packages"][0]["name"] = "/in/neo4j-fleet-management-plugin.tar"
            self.assertEqual(check(doc), [])


class Neo4jTreeCheckTest(_Tmp):
    """`[full: ke-neo4j file tree equals the official image minus products]`:
    the logic (`sbom_check.py tree` on two `docker export` tars).

    U5 (orchestrator U5 ruling 6; U4b review N6, security I-1;
    design-notes "N8 amendment, U5", item 4): `tree_listing` gives path ->
    (type, mode, uid, gid, size, link target), size the member's for a
    regular file and 0 otherwise, and a hard link counts as its target's
    regular file in both listings. The U4b 5-tuple shape (no size) is
    replaced here, in the same change that makes it wrong (CLAUDE.md
    *Contradictions*); the U4b passing case "a hard link written out as a
    regular file" moves to the tar-based tests below, which do not depend
    on how the listing records a hard link."""

    OFFICIAL = {
        ".": ("dir", 0o755, 0, 0, 0, ""), "var/lib/neo4j": ("dir", 0o777, 7474, 7474, 0, ""),
        "var/lib/neo4j/bin": ("dir", 0o755, 7474, 7474, 0, ""),
        "var/lib/neo4j/data": ("symlink", 0o777, 0, 0, 0, "/data"), "data": ("dir", 0o777, 7474, 7474, 0, ""),
        "tmp": ("dir", 0o1777, 0, 0, 0, ""), "usr/bin/su": ("file", 0o4755, 0, 0, 72000, ""),
        "usr/bin/chage": ("file", 0o2755, 0, 42, 80000, ""),
        "var/lib/neo4j/products": ("dir", 0o777, 7474, 7474, 0, ""),
        ns.FLEET_JAR: ("file", 0o777, 7474, 7474, 5000, ""), ns.GENAI_JAR: ("file", 0o777, 7474, 7474, 6000, ""),
    }

    def _image(self, **change: Any) -> dict[str, tuple[str, int, int, int, int, str]]:
        image = {k: v for k, v in self.OFFICIAL.items() if not k.startswith("var/lib/neo4j/products")}
        for k, v in change.items():
            k = k.replace("__", "/")
            if v is None:
                image.pop(k, None)
            else:
                image[k] = v
        return image

    def test_neo4j_tree_check_logic(self):
        check = fn("neo4j_tree_problems")
        passing = {"the official tree minus products/": self._image()}
        failing = {
            "products/ kept": dict(self._image(), **{k: v for k, v in self.OFFICIAL.items() if "products" in k}),
            "a path missing": self._image(**{"usr__bin__su": None}),
            "setuid lost": self._image(**{"usr__bin__su": ("file", 0o755, 0, 0, 72000, "")}),
            "setgid group lost": self._image(**{"usr__bin__chage": ("file", 0o2755, 0, 0, 80000, "")}),
            "sticky bit lost on /tmp": self._image(tmp=("dir", 0o777, 0, 0, 0, "")),
            "owner 7474 lost (COPY --chown or a root copy)": self._image(
                **{"var__lib__neo4j": ("dir", 0o777, 0, 0, 0, "")}),
            "a symlink retargeted": self._image(**{"var__lib__neo4j__data": ("symlink", 0o777, 0, 0, 0, "/srv")}),
            "a symlink made a directory": self._image(**{"var__lib__neo4j__data": ("dir", 0o777, 0, 0, 0, "")}),
            "a path added": self._image(**{"etc__ke-marker": ("file", 0o644, 0, 0, 1, "")}),
            "the jar added elsewhere": self._image(**{"opt__neo4j-fleet-management-plugin.jar":
                                                      ("file", 0o644, 0, 0, 5000, "")}),
            "a regular file's size changed (U5, review N6)": self._image(
                **{"usr__bin__su": ("file", 0o4755, 0, 0, 72001, "")}),
        }
        for case, image in passing.items():
            with self.subTest(case=case):
                self.assertEqual(check(self.OFFICIAL, image), [], case)
        for case, image in failing.items():
            with self.subTest(case=case):
                self.assertNotEqual(check(self.OFFICIAL, image), [], f"the check passed: {case}")

    def _export(self, entries: list[tuple[str, str, int, bytes | str]]) -> str:
        """A `docker export`-shaped tar: (name, kind, mode, content or link)."""
        import io
        import tarfile
        self.n += 1
        path = self.tmp / f"export{self.n}.tar"
        with tarfile.open(path, "w") as tar:
            for name, kind, mode, body in entries:
                info = tarfile.TarInfo(name)
                info.type = {"dir": tarfile.DIRTYPE, "symlink": tarfile.SYMTYPE, "file": tarfile.REGTYPE,
                             "hardlink": tarfile.LNKTYPE}[kind]
                info.mode, info.uid, info.gid = mode, 0, 0
                data = None
                if kind in ("symlink", "hardlink"):
                    info.linkname = str(body)
                elif kind == "file":
                    raw = body if isinstance(body, bytes) else str(body).encode()
                    info.size = len(raw)
                    data = io.BytesIO(raw)
                tar.addfile(info, data)
        return str(path)

    def test_tree_listing_records_regular_file_size(self):
        import io
        import tarfile
        path = self.tmp / "export.tar"
        with tarfile.open(path, "w") as tar:
            for name, (kind, mode, uid, gid, body) in (("var/lib/neo4j/", ("dir", 0o777, 7474, 7474, b"")),
                                                       ("var/lib/neo4j/data", ("symlink", 0o777, 0, 0, "/data")),
                                                       ("usr/bin/su", ("file", 0o4755, 0, 0, b"abc"))):
                info = tarfile.TarInfo(name)
                info.type = {"dir": tarfile.DIRTYPE, "symlink": tarfile.SYMTYPE, "file": tarfile.REGTYPE}[kind]
                info.mode, info.uid, info.gid = mode, uid, gid
                if kind == "symlink":
                    info.linkname = str(body)
                if kind == "file":
                    info.size = len(body)
                tar.addfile(info, io.BytesIO(body) if kind == "file" else None)  # type: ignore[arg-type]
        self.assertEqual(fn("tree_listing")(str(path)),
                         {"var/lib/neo4j": ("dir", 0o777, 7474, 7474, 0, ""),
                          "var/lib/neo4j/data": ("symlink", 0o777, 0, 0, 0, "/data"),
                          "usr/bin/su": ("file", 0o4755, 0, 0, 3, "")},
                         "tree_listing is path -> (type, mode, uid, gid, size, link target) (N8 amendment, U5, "
                         "item 4)")

    def test_tree_check_compares_size_and_hard_links_both_ways(self):
        listing, check = fn("tree_listing"), fn("neo4j_tree_problems")
        perl = ("usr/bin/perl", "file", 0o755, b"#!perl" * 100)
        as_link = [("usr/", "dir", 0o755, b""), ("usr/bin/", "dir", 0o755, b""), perl,
                   ("usr/bin/perl5.40.1", "hardlink", 0o755, "usr/bin/perl")]
        as_file = as_link[:3] + [("usr/bin/perl5.40.1", "file", 0o755, b"#!perl" * 100)]

        def problems(official: list, image: list) -> list[str]:
            return check(listing(self._export(official)), listing(self._export(image)))

        with self.subTest(case="official hard link, ke-neo4j regular file (N16, U4b)"):
            self.assertEqual(problems(as_link, as_file), [])
        with self.subTest(case="official regular file, ke-neo4j hard link (symmetric, U5)"):
            self.assertEqual(problems(as_file, as_link), [], "the hard-link normalisation is one-way (review N6)")
        with self.subTest(case="a size-only difference is a problem (U5, review N6)"):
            bigger = as_file[:2] + [("usr/bin/perl", "file", 0o755, b"#!perl" * 101)] + as_file[3:]
            self.assertNotEqual(problems(as_file, bigger), [], "a regular file that changed size passed")
        with self.subTest(case="the hard link's file differs in size"):
            other = as_file[:3] + [("usr/bin/perl5.40.1", "file", 0o755, b"x")]
            self.assertNotEqual(problems(as_link, other), [], "a hard link and a file of another size passed")
        with self.subTest(case="a hard link whose target is absent (fail closed)"):
            dangling = as_link[:2] + [("usr/bin/perl5.40.1", "hardlink", 0o755, "usr/bin/perl")]
            self.assertNotEqual(problems(as_file[:2] + [as_file[3]], dangling), [], "a dangling hard link passed")
        with self.subTest(case="a hard link with another mode"):
            moded = as_link[:3] + [("usr/bin/perl5.40.1", "hardlink", 0o700, "usr/bin/perl")]
            self.assertNotEqual(problems(as_file, moded), [], "a hard link with another mode passed")


class Neo4jCheckerCliTest(_Tmp):
    """`sbom_check.py neo4j` as the offline check runs it (python -I)."""

    def _run(self, *, sbom: dict[str, Any] | None = None, tar: str | None = None,
             config: dict[str, Any] | None = None) -> subprocess.CompletedProcess:
        self.n += 1
        d = self.tmp / f"cli{self.n}"
        d.mkdir()
        ss.write_json(d / "official.json", ns.OFFICIAL_CONFIG)
        ss.write_json(d / "config.json", config if config is not None else dict(ns.OFFICIAL_CONFIG,
                                                                                Labels=ns.COMPOSE_LABELS))
        ss.write_json(d / "sbom.json", sbom if sbom is not None else ns.ke_neo4j_doc())
        tar = tar or self._tar([ns.CLEAN_LAYER])
        return subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "sbom_check.py"), "neo4j",
                               "--official-config", str(d / "official.json"), "--config", str(d / "config.json"),
                               "--sbom", str(d / "sbom.json"), "--tar", tar],
                              capture_output=True, text=True, timeout=60)

    def test_neo4j_checker_cli(self):
        ok = self._run()
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertRegex(ok.stdout, r"(?m)^sbom_check: ke-neo4j: ok: ", "one summary line on stdout")
        for case, kw, word in (
                ("the plugin in the SBOM", {"sbom": ns.ke_neo4j_doc(keep_plugins=True)}, "fleet-management"),
                ("products/ in the tar", {"tar": self._tar([ns.CLEAN_LAYER + [("var/lib/neo4j/products/", "dir")]])},
                 "products"),
                ("a config change", {"config": dict(ns.OFFICIAL_CONFIG, User="7474")}, "User")):
            with self.subTest(case=case):
                bad = self._run(**kw)
                self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
                self.assertRegex(bad.stderr, rf"(?m)^sbom_check: ke-neo4j: .*{word}")
                self.assertNotIn(": ok:", bad.stdout)
        with self.subTest(case="an unreadable tar"):
            missing = self._run(tar=str(self.tmp / "nope.tar"))
            self.assertEqual(missing.returncode, 1, missing.stdout + missing.stderr)


# --------------------------------------------------------------------------
# offline_check.sh: the ke-neo4j check on the bundle it writes (fake docker)
# --------------------------------------------------------------------------

class OfflineKeNeo4jTest(toc._OfflineBase):
    """The offline check's host half runs `sbom_check.py neo4j` on the bundle
    bundle.sh wrote: the SBOM (PSC-26 *SBOM*), the saved tar (*Plugin
    absent*) and both configs (*Image config carried over*). The step's
    placement is the tester's proposal (N16 does not place it; flagged)."""

    _host_setup = toc.OfflineCheckScriptTest._host_setup
    _sbom_env = toc.OfflineCheckScriptTest._sbom_env
    _host = toc.OfflineCheckScriptTest._host
    _event = staticmethod(toc.OfflineCheckScriptTest._event)
    _event_u2 = toc.OfflineCheckScriptTest._event_u2
    _events_u2 = toc.OfflineCheckScriptTest._events_u2
    _bundle_dirs = toc.OfflineCheckScriptTest._bundle_dirs
    _pairs = staticmethod(toc.OfflineCheckScriptTest._pairs)

    def _checker(self, records: list[dict]) -> list[str]:
        runs = [r["argv"] for r in records if self._event_u2(r) == "neo4j"]
        self.assertEqual(len(runs), 1, f"one `sbom_check.py neo4j` run: {runs}")
        return runs[0] if runs else []

    def test_offline_check_runs_ke_neo4j_check(self):
        result, records, repo = self._host()
        out = self._out(result)
        self.assertEqual(result.returncode, 0, out)
        events = self._events_u2(records)
        for a, b in (("pull neo4j base", "bundle"), ("bundle", "neo4j"), ("drift", "neo4j"), ("neo4j", "up dind")):
            with self.subTest(order=f"{a} before {b}"):
                self.assertTrue(a in events and b in events and events.index(a) < events.index(b), events)
        pulls = [r["argv"] for r in records if self._event_u2(r) == "pull neo4j base"]
        self.assertEqual(pulls, [["pull", ns.dockerfile_base_ref(repo / DOCKERFILE_REL) or "?"]],
                         "one `docker pull <the Dockerfile's FROM ref>`")
        argv = self._checker(records)
        pairs = self._pairs(argv)
        for flag in (("--network", "none"), ("--pull", "never")):
            self.assertIn(flag, pairs)
        self.assertIn("--read-only", argv)
        self.assertIn("ke-app:wt-0123456789ab", argv, "the checker runs in the bundle's ke-app image")
        tail = argv[argv.index("neo4j") + 1:] if "neo4j" in argv else []
        tail_pairs = dict(zip(tail[::2], tail[1::2]))
        self.assertEqual(tail_pairs.get("--sbom"), "/sboms/ke-neo4j.spdx.json")
        self.assertEqual(tail_pairs.get("--tar"), "/images/ke-neo4j.tar")
        self.assertTrue(tail_pairs.get("--official-config") and tail_pairs.get("--config"), tail)
        inspects = [r["argv"] for r in records if r["argv"][:2] == ["image", "inspect"]]
        for ref in (ns.dockerfile_base_ref(repo / DOCKERFILE_REL), toc.NEO4J_WT):
            with self.subTest(inspect=ref):
                self.assertTrue([a for a in inspects if a[-1] == ref and "{{json .Config}}" in a], inspects)
        self.assertRegex(result.stdout, r"(?m)^offline: ke-neo4j check: ", "the step says it passed")
        self.assertEqual(sorted((repo / "dist").glob(".ke-neo4j.*")), [], "the work dir was left behind")

    def test_offline_check_fails_on_ke_neo4j_problems(self):
        bad_sbom = ss.write_json(self.tmp / "bad.spdx.json", ns.ke_neo4j_doc(keep_plugins=True))
        bad_tar = ns.save_tar(self.tmp / "bad" / "ke-neo4j.tar", [ns.CLEAN_LAYER + [(ns.FLEET_JAR, "file")]])
        official = ns.OFFICIAL_REF
        no_neo4j = self.tmp / "no-neo4j-bundle.json"
        no_neo4j.write_text(toc._bundle_json([e for e in toc.BUNDLE_ENTRIES if e["services"] != "neo4j"]),
                            encoding="utf-8")
        cases = {
            "the SBOM lists the plugin": ({"FAKE_STUB_KE_NEO4J_SBOM": str(bad_sbom)}, "fleet-management"),
            "the saved tar holds the plugin": ({"FAKE_STUB_KE_NEO4J_TAR": str(bad_tar)}, "fleet-management"),
            "ke-neo4j runs as another user": ({"FAKE_IMAGE_CONFIGS": json.dumps(
                {official: ns.OFFICIAL_CONFIG, toc.NEO4J_WT: dict(ns.OFFICIAL_CONFIG, User="7474")})}, "User"),
            "the official image is not on the daemon": ({"FAKE_IMAGE_CONFIGS": json.dumps(
                {toc.NEO4J_WT: ns.OFFICIAL_CONFIG})}, "ke-neo4j base"),
            "the bundle has no ke-neo4j": ({"FAKE_STUB_BUNDLE_JSON": str(no_neo4j)}, "ke-neo4j"),
            "the pull of the official image fails": ({"FAKE_DOCKER_FAIL": f"pull {official}"}, "ke-neo4j base"),
        }
        for case, (extra, word) in cases.items():
            with self.subTest(case=case):
                result, records, repo = self._host(**extra)
                out = self._out(result)
                self.assertNotEqual(result.returncode, 0, f"the offline check passed with {case}:\n{out}")
                self.assertNotRegex(out, r"offline_check: PASS")
                self.assertTrue([ln for ln in result.stderr.splitlines() if "FAIL" in ln and word in ln
                                 or "sbom_check: ke-neo4j" in ln and word in ln],
                                f"no failure line names {word!r} ({case}):\n{out}")
                events = self._events_u2(records)
                self.assertNotIn("up dind", events, f"dind started after the failure ({case})")
                self.assertEqual(events[-1:], ["teardown"], f"the trap ran teardown ({case}): {events}")
                self.assertEqual(self._bundle_dirs(repo), [], "the bundle directory was left behind")
                self.assertEqual(sorted((repo / "dist").glob(".ke-*")), [], "a work dir was left behind")


# --------------------------------------------------------------------------
# Smoke: no fleet plugin in the live neo4j (fake docker; N16 *Smoke*)
# --------------------------------------------------------------------------

FLEET_CHECK_RX = r"\bexec\b.*\bneo4j\b.*\bfind\b"


class SmokeNoFleetPluginTest(unittest.TestCase):
    """N16 *Smoke (live stack)*: in the running neo4j service,
    /var/lib/neo4j/products is absent and no file under / is named
    *fleet-management*; whole-output compare, failing closed (U1 form). The
    fake docker models the container's files (tests/fake_docker.py, U4b:
    FAKE_NEO4J_FILES, FAKE_NEO4J_DROP, FAKE_NEO4J_OTHER_FS).

    U5 (U4b security L-1; orchestrator U5 ruling 8; design-notes "N8
    amendment, U5", item 6): no `-xdev`, so the walk enters volumes and
    mounts (/data, /logs); /proc, /sys and /dev are pruned. The U4b passing
    case "a match on another filesystem (-xdev)" is now "a match under /proc
    (pruned)"; a match in the /data volume fails. The fake's
    FAKE_NEO4J_OTHER_FS paths are walked once -xdev is gone. The real step
    runs only in `verify.sh full`."""

    _smoke = tss.SmokeBackendIsolatedTest._smoke
    BASH_ERROR = re.compile(r"(?m)smoke\.sh: line \d+: ")

    def setUp(self) -> None:
        tss.SmokeResolvesWithoutEnvTest.setUp(self)  # type: ignore[arg-type]
        for rel in ("docker/app.Dockerfile", "docker/gates.Dockerfile"):
            dest = self.tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dest)

    @staticmethod
    def _execs(records: list[dict]) -> list[tuple[int, str | None, list[str]]]:
        return [(n, *_exec_service(r["argv"])) for n, r in enumerate(records)
                if r["argv"][:1] == ["compose"] and "exec" in r["argv"]]

    def _assert_fails(self, case: str, extra: dict[str, str]) -> str:
        result, records = self._smoke(**extra)
        out = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, f"smoke passed with {case}:\n{out}")
        self.assertNotIn("smoke: PASS", out)
        self.assertIsNone(self.BASH_ERROR.search(out), f"smoke stopped on a bash error ({case}):\n{out}")
        self.assertTrue([ln for ln in out.splitlines() if "smoke: FAIL" in ln and "fleet" in ln],
                        f"the failure must be a `smoke: FAIL` line naming the fleet plugin ({case}):\n{out}")
        self.assertEqual(tss._smoke_steps(records)[-1:], ["teardown"], "smoke launched it, so it tears down")
        return out

    def test_smoke_checks_no_fleet_plugin_in_neo4j(self):
        passing = {
            "clean ke-neo4j (the fake's default model)": {},
            "near misses: productsx/, a fleet- name that is not fleet-management": {
                "FAKE_NEO4J_FILES": "/var/lib/neo4j/productsx/,/var/lib/neo4j/lib/neo4j-fleet-client.jar"},
            "a match under /proc (pruned, U5)": {"FAKE_NEO4J_OTHER_FS": "/proc/1/fleet-management"},
            "matches under /sys and /dev (pruned, U5)": {
                "FAKE_NEO4J_FILES": "/sys/kernel/fleet-management,/dev/fleet-management0"},
        }
        for case, extra in passing.items():
            with self.subTest(case=case):
                result, records = self._smoke(**extra)
                out = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, out)
                self.assertIn("smoke: PASS", out)
                self.assertIn("== smoke: no fleet plugin ==", result.stdout, "smoke prints the step header")
                execs = self._execs(records)
                checks = [(n, cmd) for n, svc, cmd in execs if svc == "neo4j"]
                self.assertEqual(len(checks), 1, f"smoke runs one check in neo4j: {[c for *_, c in execs]}")
                if not checks:
                    continue
                n, cmd = checks[0]
                self.assertIn("-T", records[n]["argv"], "exec -T (no tty)")
                self.assertFalse({"-xdev", "-mount"} & set(cmd), f"the find stops at mounts (L-1): {cmd}")
                pairs = list(zip(cmd, cmd[1:]))
                for top in ("/proc", "/sys", "/dev"):
                    self.assertIn(("-path", top), pairs, f"the find does not prune {top}: {cmd}")
                self.assertIn("-prune", cmd, f"the find prunes nothing: {cmd}")
                no_pip = [m for m, svc, c in execs if svc == "api" and 'find_spec("pip")' in " ".join(c)]
                self.assertTrue(no_pip and max(no_pip) < n, "the check runs after the no-pip check")

    def test_smoke_fails_when_the_fleet_plugin_is_in_neo4j(self):
        failing = {
            "the official image's products/ (both jars)": {"FAKE_NEO4J_FILES": f"/{ns.FLEET_JAR},/{ns.GENAI_JAR}"},
            "an empty products/": {"FAKE_NEO4J_FILES": "/var/lib/neo4j/products/"},
            "only the GenAI jar left in products/": {"FAKE_NEO4J_FILES": f"/{ns.GENAI_JAR}"},
            "the plugin moved to plugins/": {
                "FAKE_NEO4J_FILES": "/var/lib/neo4j/plugins/neo4j-fleet-management-plugin-1.2.0-v5.jar"},
            "a fleet-management file elsewhere": {"FAKE_NEO4J_FILES": "/opt/fleet-management/agent.conf"},
            "the plugin in the neo4j-data volume (/data, U5, L-1)": {
                "FAKE_NEO4J_OTHER_FS": "/data/plugins/neo4j-fleet-management-plugin-1.2.0-v5.jar"},
            "a fleet-management file in /logs (U5, L-1)": {"FAKE_NEO4J_OTHER_FS": "/logs/fleet-management.log"},
            "the control path gone (an empty answer)": {"FAKE_NEO4J_DROP": "/var/lib/neo4j/LICENSE.txt"},
            "the check fails in neo4j": {"FAKE_DOCKER_HOOKS": json.dumps([{"on": FLEET_CHECK_RX, "exit": 1}])},
            # find exits non-zero when it could not read a directory, so a
            # clean-looking answer from an incomplete walk fails too.
            "the control path printed, then find exits 1": {"FAKE_DOCKER_HOOKS": json.dumps(
                [{"on": FLEET_CHECK_RX, "stdout": "/var/lib/neo4j/LICENSE.txt\n", "exit": 1}])},
            "the check exits 0 and prints nothing": {"FAKE_DOCKER_HOOKS": json.dumps(
                [{"on": FLEET_CHECK_RX, "stdout": "", "exit": 0}])},
            "the control, then a second line": {"FAKE_DOCKER_HOOKS": json.dumps(
                [{"on": FLEET_CHECK_RX, "stdout": f"/var/lib/neo4j/LICENSE.txt\n/{ns.FLEET_JAR}\n", "exit": 0}])},
        }
        for case, extra in failing.items():
            with self.subTest(case=case):
                self._assert_fails(case, extra)

    def test_smoke_never_evaluates_the_neo4j_output(self):
        for name, template in {"command substitution": "$(touch {m})", "backticks": "`touch {m}`",
                               "the control, then a command": "/var/lib/neo4j/LICENSE.txt;touch {m}"}.items():
            with self.subTest(case=name):
                marker = self.tmp / f"fleet-marker-{abs(hash(name))}"
                hooks = [{"on": FLEET_CHECK_RX, "stdout": template.format(m=marker.as_posix()) + "\n", "exit": 0}]
                self._assert_fails(name, {"FAKE_DOCKER_HOOKS": json.dumps(hooks)})
                self.assertFalse(marker.exists(), f"smoke ran a command from the neo4j output on the host: {marker}")


if __name__ == "__main__":
    unittest.main()
