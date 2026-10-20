"""platform-offline PS-3.8: `engine.notices` in-process (stdlib only).

`tests/test_offline_bundle.py` runs the generator end to end through bundle.sh
(a subprocess, so it adds nothing to coverage). These tests call it directly,
over test-built `*.dist-info` directories, so every licence layout and every
refusal is covered and counted.
"""

from __future__ import annotations

import importlib
import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib import metadata
from pathlib import Path
from unittest import mock

from engine import notices


def _dist(site: Path, name: str, headers: list[str], files: dict[str, str] | None = None,
          record: list[str] | None = None, version: str = "1.0") -> metadata.Distribution:
    """A distribution under `site`: METADATA with `headers`, plus `files` (site-relative)."""
    info = f"{name.replace('-', '_')}-{version}.dist-info"
    (site / info).mkdir(parents=True)
    head = ["Metadata-Version: 2.4", f"Name: {name}", f"Version: {version}", *headers]
    (site / info / "METADATA").write_text("\n".join(head) + "\n\n", encoding="utf-8")
    written = {f"{info}/{rel}": text for rel, text in (files or {}).items()}
    for rel, text in written.items():
        (site / rel).parent.mkdir(parents=True, exist_ok=True)
        (site / rel).write_text(text, encoding="utf-8")
    listed = record if record is not None else [f"{info}/METADATA", *written]
    (site / info / "RECORD").write_text("".join(f"{r},,\n" for r in listed), encoding="utf-8")
    return metadata.Distribution.at(site / info)


class NoticesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.site = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.site, True)

    def test_licence_label_order_and_fallbacks(self):
        cases = {
            "expr": (["License-Expression: MIT", "License: other"], "MIT"),
            "field": (["License: BSD-3-Clause"], "BSD-3-Clause"),
            "classifier": (["Classifier: License :: OSI Approved",
                            "Classifier: License :: OSI Approved :: BSD License"], "BSD License"),
            "longfield": (["License: " + "x" * 200, "Classifier: License :: OSI Approved :: MIT License"],
                          "MIT License"),
            "multiline": (["License: first line", "        second line"], "first line"),
            "none": ([], "not declared"),
            "pipe": (["License-Expression: A | B"], "A | B"),
        }
        for name, (headers, want) in cases.items():
            with self.subTest(name):
                dist = _dist(self.site, name, headers)
                self.assertIn(want, notices._licence(dist))
        self.assertEqual(notices._cell("a | b\n c"), "a / b c")

    def test_licence_files_across_layouts(self):
        modern = _dist(self.site, "modern", ["License-File: LICENSE"], {"licenses/LICENSE": "x"})
        legacy = _dist(self.site, "legacy", ["License-File: LICENSE"], {"LICENSE": "x"})
        bare = _dist(self.site, "bare", [], {"LICENSE": "x", "COPYING.txt": "x", "other.txt": "x"})
        header_only = _dist(self.site, "header", ["License-File: sub/MIT.txt"], {"licenses/sub/MIT.txt": "x"},
                            record=["header-1.0.dist-info/METADATA"])
        nested = _dist(self.site, "nested", [], {"licenses/vendor/llhttp/LICENSE": "x"})
        self.assertEqual(notices.licence_files(modern), ["modern-1.0.dist-info/licenses/LICENSE"])
        self.assertEqual(notices.licence_files(legacy), ["legacy-1.0.dist-info/LICENSE"])
        self.assertEqual(notices.licence_files(bare), ["bare-1.0.dist-info/COPYING.txt", "bare-1.0.dist-info/LICENSE"])
        self.assertEqual(notices.licence_files(header_only), ["header-1.0.dist-info/licenses/sub/MIT.txt"])
        self.assertEqual(notices.licence_files(nested), ["nested-1.0.dist-info/licenses/vendor/llhttp/LICENSE"])

    def test_missing_or_escaping_licence_file_is_not_found(self):
        gone = _dist(self.site, "gone", ["License-File: LICENSE"], {"licenses/LICENSE": "x"})
        (self.site / "gone-1.0.dist-info" / "licenses" / "LICENSE").unlink()
        escaping = _dist(self.site, "escape", ["License-File: ../../outside", "License-File: /etc/passwd"])
        (self.site / "outside").write_text("x", encoding="utf-8")
        no_metadata_in_record = _dist(self.site, "norecord", ["License-File: LICENSE"], {"licenses/LICENSE": "x"},
                                      record=[])
        self.assertEqual(notices.licence_files(gone), [])
        self.assertEqual(notices.licence_files(escaping), [])
        self.assertEqual(notices.licence_files(no_metadata_in_record), [])

    def test_rows_skip_the_project_and_duplicates_and_name_missing(self):
        mine = _dist(self.site, "Knowledge_Engine", [], {})
        a = _dist(self.site, "A-Pkg", ["License-Expression: MIT"], {"licenses/LICENSE": "x"})
        shadow_site = self.site / "shadow"
        shadow_site.mkdir()
        shadowed = _dist(shadow_site, "a.pkg", ["License-Expression: GPL-3.0"], {})
        nameless = metadata.Distribution.at(self.site / "A_Pkg-1.0.dist-info")
        bad = _dist(self.site, "zed", ["License-Expression: MIT"], {})
        table, missing = notices.rows([mine, a, shadowed, bad])
        self.assertEqual([r[0] for r in table], ["A-Pkg", "zed"])
        self.assertEqual(missing, ["zed"])
        self.assertIn("MIT", table[0][2])
        with mock.patch.object(type(nameless), "metadata", {"Name": ""}):
            self.assertEqual(notices.rows([nameless]), ([], []))

    def test_main_prints_the_table_or_refuses(self):
        _dist(self.site, "ok", ["License-Expression: MIT"], {"licenses/LICENSE": "x"})
        run = lambda *a: self._run(self.site, *a)  # noqa: E731
        code, out, err = run()
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[0], "| Package | Version | Licence | Licence files |")
        self.assertEqual(lines[2], "| ok | 1.0 | MIT | ok-1.0.dist-info/licenses/LICENSE |")
        _dist(self.site, "bare-pkg", ["License-Expression: MIT"], {})
        code, out, err = run()
        self.assertEqual((code, out), (1, ""))
        self.assertRegex(err, r"bare-pkg")
        self.assertRegex(err, r"licen[cs]e")
        code, out, err = run("--unexpected")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("usage", err)

    @staticmethod
    def _run(site: Path, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        importlib.invalidate_caches()  # the finder caches a directory by its mtime
        dists = metadata.distributions(path=[str(site)])
        with mock.patch.object(notices.metadata, "distributions", return_value=dists), \
                redirect_stdout(out), redirect_stderr(err):
            code = notices.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_main_reads_sys_argv_by_default(self):
        with mock.patch.object(notices.sys, "argv", ["notices", "extra"]), redirect_stderr(io.StringIO()):
            self.assertEqual(notices.main(), 2)


if __name__ == "__main__":
    unittest.main()
