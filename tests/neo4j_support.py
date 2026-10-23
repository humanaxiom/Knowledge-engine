"""platform-sbom U4b (PSC-26, human ruling Q67; design-notes N16): shared
facts and stand-ins for the ke-neo4j tests (tests/test_neo4j_image.py and
the offline check harness in tests/test_offline_check.py).

- OFFICIAL_REF: the official image PSC-26 *Build* pins, by its full digest.
- OFFICIAL_CONFIG: its `docker image inspect --format '{{json .Config}}'`
  (amd64), recorded by the tester on 2026-10-23 in
  docs/evidence/platform-sbom/u4b/official-config.txt; N16's list. Re-read
  it on every digest bump (N16), and OFFICIAL_CONFIG_DIGEST with it.
- ke_neo4j_doc(): a syft-shaped SBOM of ke-neo4j: the real U3 neo4j package
  list (tests/fixtures/sbom-u3/neo4j.pkgs.tsv) without the two products/
  plugins (N16 *SBOM*: "the plugin rows go, and nothing else changes").
- save_tar(): a `docker save` tar (docker 25+ `oci` or `legacy` layout)
  whose layers hold the given entries, for the saved-tar check.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path
from typing import Any

from tests import sbom_support as ss

ROOT = Path(__file__).resolve().parent.parent
NEO4J_DOCKERFILE = ROOT / "docker" / "neo4j.Dockerfile"
OFFICIAL_REF = "neo4j:5-community@sha256:0a6e7aedf54a531f76286032d4365ead65b11cca05e4a15cdf23b8e53d6db02b"
OFFICIAL_CONFIG_DIGEST = OFFICIAL_REF.rsplit("@", 1)[1]
KE_NEO4J_TAG = "${KE_IMAGE_TAG:-local}"
KE_NEO4J_IMAGE = "ke-neo4j:" + KE_NEO4J_TAG
FLEET_JAR = "var/lib/neo4j/products/neo4j-fleet-management-plugin-1.2.0-v5.jar"
GENAI_JAR = "var/lib/neo4j/products/neo4j-genai-plugin-5.26.32.jar"
FLEET_PURL = "pkg:maven/com.neo4j/neo4j-fleet-management-plugin@1.2.0"
GENAI_PURL = "pkg:maven/org.neo4j/neo4j-genai-plugin@5.26.32"

OFFICIAL_ENV = [
    "PATH=/var/lib/neo4j/bin:/opt/java/openjdk/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "JAVA_HOME=/opt/java/openjdk",
    "NEO4J_SHA256=d279ae6a9b38034280681a558b0cd222dce89f87cc3d9867f1f7bd28ef5ebc30",
    "NEO4J_TARBALL=neo4j-community-5.26.32-unix.tar.gz",
    "NEO4J_EDITION=community",
    "NEO4J_HOME=/var/lib/neo4j",
    "LANG=C.UTF-8",
]
OFFICIAL_CONFIG: dict[str, Any] = {
    "ExposedPorts": {"7473/tcp": {}, "7474/tcp": {}, "7687/tcp": {}},
    "Env": OFFICIAL_ENV,
    "Entrypoint": ["tini", "-g", "--", "/startup/docker-entrypoint.sh"],
    "Cmd": ["neo4j"],
    "Volumes": {"/data": {}, "/logs": {}},
    "WorkingDir": "/var/lib/neo4j",
}
# Fields the official image leaves unset; ke-neo4j must leave them unset (N16).
OFFICIAL_UNSET = ("User", "Healthcheck", "StopSignal", "OnBuild", "Shell", "Labels")
# What compose adds to every image it builds (ke-app carries them too).
COMPOSE_LABELS = {"com.docker.compose.project": "ke-verify-1234", "com.docker.compose.service": "neo4j",
                  "com.docker.compose.version": "2.29.7"}


def dockerfile_base_ref(path: Path = NEO4J_DOCKERFILE) -> str | None:
    """The `FROM <ref> AS <stage>` reference of the first stage, or None."""
    if not path.is_file():
        return None
    m = re.search(r"^FROM\s+(\S+)\s+AS\s+\S+\s*$", path.read_text(encoding="utf-8"), re.M | re.I)
    return m.group(1) if m else None


def ke_neo4j_rows(*, keep_plugins: bool = False) -> list[dict[str, Any]]:
    rows = ss.u3_rows("neo4j")
    if keep_plugins:
        return rows
    return [r for r in rows if (r.get("purl") or "").split("@", 1)[0] not in
            (FLEET_PURL.split("@", 1)[0], GENAI_PURL.split("@", 1)[0])]


def ke_neo4j_doc(*, keep_plugins: bool = False, extra: tuple[dict[str, Any], ...] = ()) -> dict[str, Any]:
    return ss.spdx_doc("ke-neo4j", ke_neo4j_rows(keep_plugins=keep_plugins) + list(extra))


# (name, kind) entries of a layer: kind "file" | "dir" | "symlink:<target>".
CLEAN_LAYER: list[tuple[str, str]] = [
    ("var/", "dir"), ("var/lib/", "dir"), ("var/lib/neo4j/", "dir"), ("var/lib/neo4j/LICENSE.txt", "file"),
    ("var/lib/neo4j/lib/", "dir"), ("var/lib/neo4j/lib/neo4j-kernel-5.26.32.jar", "file"),
    ("var/lib/neo4j/labs/", "dir"), ("var/lib/neo4j/labs/apoc-5.26.32-core.jar", "file"),
    ("var/lib/neo4j/data", "symlink:/data"), ("startup/", "dir"), ("startup/neo4j-plugins.json", "file"),
]


def _layer_bytes(entries: list[tuple[str, str]], compress: bool = False) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, kind in entries:
            info = tarfile.TarInfo(name)
            info.mtime = 0
            data = b""
            if kind == "dir":
                info.type, info.mode = tarfile.DIRTYPE, 0o777
            elif kind.startswith("symlink:"):
                info.type, info.linkname = tarfile.SYMTYPE, kind.split(":", 1)[1]
            else:
                data = f"{name}\n".encode("utf-8")
                info.size, info.mode = len(data), 0o644
            tar.addfile(info, io.BytesIO(data) if data else None)
    raw = buf.getvalue()
    return gzip.compress(raw, mtime=0) if compress else raw


def save_tar(path: Path, layers: list[list[tuple[str, str]]], *, form: str = "oci",
             extra_images: list[list[list[tuple[str, str]]]] | None = None,
             compress: tuple[int, ...] = (), drop_blob: int | None = None) -> Path:
    """A `docker save` tar. `layers`: the image's layers, bottom first;
    `extra_images`: more manifest.json entries (their layers); `compress`:
    indexes of layers stored gzip-compressed; `drop_blob`: index of a layer
    listed in manifest.json but left out of the tar."""
    blobs: dict[str, bytes] = {}
    entries = []
    n = 0
    for image_layers in [layers] + list(extra_images or []):
        names = []
        for entry_list in image_layers:
            data = _layer_bytes(entry_list, n in compress)
            hex_ = hashlib.sha256(data).hexdigest()
            name = f"{hex_}/layer.tar" if form == "legacy" else f"blobs/sha256/{hex_}"
            if n != drop_blob:
                blobs[name] = data
            names.append(name)
            n += 1
        config = json.dumps({"architecture": "amd64", "os": "linux", "config": OFFICIAL_CONFIG,
                             "rootfs": {"type": "layers", "diff_ids": []}}, sort_keys=True).encode("utf-8")
        cfg_hex = hashlib.sha256(config + str(len(entries)).encode()).hexdigest()
        cfg_name = f"{cfg_hex}.json" if form == "legacy" else f"blobs/sha256/{cfg_hex}"
        blobs[cfg_name] = config
        entries.append({"Config": cfg_name, "RepoTags": [f"ke-neo4j:bundle-{'0' * 12}"], "Layers": names})
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w") as tar:
        def add(name: str, data: bytes) -> None:
            info = tarfile.TarInfo(name)
            info.size, info.mtime = len(data), 0
            tar.addfile(info, io.BytesIO(data))
        for name, data in blobs.items():
            add(name, data)
        if form != "legacy":
            add("oci-layout", b'{"imageLayoutVersion": "1.0.0"}')
            add("index.json", json.dumps({"schemaVersion": 2, "manifests": []}).encode("utf-8"))
        add("manifest.json", json.dumps(entries).encode("utf-8"))
    return path
