"""platform-sbom U5: the licence classifier (PSC-15, PSC-22), and the escaping
and anchoring carry (security U4 L-5, review U4 R2).

Criteria: docs/requirements.md PSC-15 (the GPL-family list, "That list is
the minimum": AGPL, GPL-1.0 and LGPL-2.0 too), PSC-22 (*Hash-only licences*
and *Carried to the U5 classifier (security U4 L-4)*). Design:
docs/evidence/platform-sbom/design-notes.md N8, N8a (ruling 5), "N8
amendment, U5" (items 1, 2, 7) and N15's "U5's classifier table".
Orchestrator U5 rulings 1-5 (2026-10-24).

Interface pinned by these tests (names fixed by the orchestrator; tester, U5
RED, 2026-10-24). All in `scripts/sbom_check.py`, standard library, pure:
- `licence_input(pkg) -> str | None`: N8's input order with the
  classifier's "missing" (absent, null, wrong type, or exactly "", "NONE",
  "NOASSERTION"; a hash-only field is *set*): declared alone; concluded
  alone; `(<declared>) AND (<concluded>)` when both are set and differ (one
  copy when equal); else the set `licenseInfoFromFiles` entries in list
  order, one alone or each in parentheses joined with ` AND `; None when
  nothing is set (unlicensed).
- `is_gpl_id(id) -> bool`: lower-case, strip a leading `licenseref-`, then
  N8's anchored pattern or else the N8a token rule.
- `needs_source(expr) -> (bool, info)`: SPDX 2.3 grammar (WITH > AND > OR,
  operators any case); `info["unparsed"]` and `info["unidentified"]` are
  read with bool(), so a bool or a list of ids both do.
- `classify_package(pkg) -> dict` with keys needs, expression, unlicensed,
  unparsed, unidentified, purl, spdxid, name.
- `classify_document(image, doc, always) -> list[dict]`: one row per
  package but the DESCRIBES root, document order, each with `always`
  (bool); an `always` match forces needs.
Unparseable text needs source if the token rule hits anywhere in it, or it
holds a hash id (orchestrator U5 addition 3; it is then also unidentified).

Fixtures: tests/fixtures/sbom-u3/*.pkgs.tsv (real syft rows, U3) and the
real docker/source-policy.json `always`; never docs/evidence.
"""

from __future__ import annotations

import json
import re
import unittest
from typing import Any, Callable

from tests import sbom_support as ss
from tests.engine_support import ROOT
from tests.test_sbom_bundle import load_sbom_check

POLICY = ROOT / "docker" / "source-policy.json"
HASH = "LicenseRef-" + "0123456789abcdef" * 4
HASH2 = "LicenseRef-" + "fedcba9876543210" * 4
ABSENT = object()
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# Real ids from tests/fixtures/sbom-u3/neo4j.pkgs.tsv (syft folds a pom's
# licence URLs into one LicenseRef- id; N8a items 2-4).
JAXB = "LicenseRef-https---glassfish.java.net-public-CDDL-GPL-1-1.html--https---glassfish.java.net-public-CDDL-GPL-1-1.html"
JAVASSIST = ("LicenseRef-https---www.mozilla.org-en-US-MPL-1.1---https---www.gnu.org-licenses-lgpl-2.1.html--"
             "https---www.apache.org-licenses-LICENSE-2.0")
CLASSPATH = "LicenseRef-http---www.eclipse.org-legal-epl-2.0--https---www.gnu.org-software-classpath-license.html"


def fn(name: str) -> Callable[..., Any]:
    """A function of scripts/sbom_check.py, or a failure naming it."""
    got = getattr(load_sbom_check(), name, None)
    if not callable(got):
        raise AssertionError(f"scripts/sbom_check.py has no {name}() (U5 interface, PSC-15; design-notes "
                             "N8 amendment, U5, item 2; tests/test_sbom_classifier.py)")
    return got


def pkg(declared: Any = ABSENT, concluded: Any = ABSENT, files: Any = ABSENT, *, purl: str | None = None,
        spdxid: str = "SPDXRef-Package-x-1", name: str = "x") -> dict[str, Any]:
    p: dict[str, Any] = {"name": name, "SPDXID": spdxid, "downloadLocation": "NOASSERTION"}
    for key, value in (("licenseDeclared", declared), ("licenseConcluded", concluded),
                       ("licenseInfoFromFiles", files)):
        if value is not ABSENT:
            p[key] = value
    if purl:
        p["externalRefs"] = [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl",
                              "referenceLocator": purl}]
    return p


def verdict(expr: str) -> tuple[bool, bool, bool]:
    needs, info = fn("needs_source")(expr)
    if not isinstance(info, dict) or not {"unparsed", "unidentified"} <= set(info):
        raise AssertionError(f"needs_source({expr!r}) info {info!r} lacks the keys unparsed and unidentified")
    return bool(needs), bool(info["unparsed"]), bool(info["unidentified"])


class _Table(unittest.TestCase):
    def check(self, rows: list[tuple[str, bool, bool | None, bool | None]]) -> None:
        """rows: (expression, needs, unparsed, unidentified); None = not pinned."""
        for expr, needs, unparsed, unidentified in rows:
            with self.subTest(expr=expr):
                got = verdict(expr)
                self.assertEqual(got[0], needs, f"needs_source({expr!r}) needs {got[0]}, want {needs}")
                if unparsed is not None:
                    self.assertEqual(got[1], unparsed, f"needs_source({expr!r}) unparsed {got[1]}, want {unparsed}")
                if unidentified is not None:
                    self.assertEqual(got[2], unidentified,
                                     f"needs_source({expr!r}) unidentified {got[2]}, want {unidentified}")


# --------------------------------------------------------------------------
# is_gpl_id: N8's anchored pattern, then the N8a token rule
# --------------------------------------------------------------------------

class GplIdTest(unittest.TestCase):
    def test_is_gpl_id_pattern_and_token_rule(self):
        is_gpl = fn("is_gpl_id")
        family = ("GPL-2.0", "GPL-2.0-only", "GPL-2.0-or-later", "GPL-2.0+", "GPL-3.0-with-GCC-exception",
                  "LGPL-2.1", "LGPL-3.0-only", "LGPL-2.1-or-later", "GPL-2", "GPL-2+", "GPL-3+", "LGPL-2.1+",
                  "GPL", "LGPL", "AGPL-3.0-only", "AGPL-3.0-or-later", "GPL-1.0-or-later", "GPL-1.0-only",
                  "LGPL-2.0-only", "LGPL-2.0-or-later", "gpl-2.0-only", "GPLv2", "gplv3+",
                  # a token containing `gpl` (rework ruling 2, security L-1; was a miss in the U5 RED)
                  "GPLX",
                  # named LicenseRef rows (orchestrator U5 ruling 5; real fixture ids)
                  "LicenseRef-GPL", "LicenseRef-LGPL", "LicenseRef-GPL-2.0-only",
                  "LicenseRef-GPL-2.0-with-foo-exception", "LicenseRef-lgpl-custom",
                  "LicenseRef-GPL-3--WITH-BISON-EXCEPTION", "LicenseRef-GPL-2--with-link-exception",
                  "LicenseRef-LGPL-2.1--with-link-exception",
                  # lower-cased before `licenseref-` is stripped (N8 amendment, U5, item 2)
                  "LICENSEREF-GPL-2.0-only", "licenseref-lgpl-2.1",
                  # syft's URL-folded pom ids (N8a 2, 3), lower and mixed case
                  JAXB, JAXB.lower(), JAVASSIST, JAVASSIST.lower(), JAVASSIST.replace("lgpl", "LGpl"))
        other = ("MIT", "Apache-2.0", "BSD-3-Clause", "GFDL-1.3", "GFDL-1.3-only", "LicenseRef-GFDL-NIV-1.3",
                 "LicenseRef-scancode-public-domain", "LicenseRef-Public-Domain", "LicenseRef-Expat",
                 "EUPL-1.2", "MPL-2.0-no-copyleft-exception", CLASSPATH, CLASSPATH.upper())
        for i in family:
            with self.subTest(gpl=i):
                self.assertIs(bool(is_gpl(i)), True, f"is_gpl_id({i!r}) is false: GPL-family (N8, N8a)")
        for i in other:
            with self.subTest(other=i):
                self.assertIs(bool(is_gpl(i)), False, f"is_gpl_id({i!r}) is true: not GPL-family")


# --------------------------------------------------------------------------
# needs_source: the classifier table (N8, N8a, N15 U5 table, N8 amendment U5)
# --------------------------------------------------------------------------

class NeedsSourceTest(_Table):
    def test_classifier_table(self):
        self.check([
            ("GPL-2+", True, False, False), ("GPL-2.0-only", True, False, False), ("GPL-2.0+", True, False, False),
            ("GPL-3.0-with-GCC-exception", True, False, False), ("LGPL-2.1+", True, False, False),
            ("GPL", True, False, False), ("LGPL", True, False, False), ("AGPL-3.0-only", True, False, False),
            ("GPL-1.0-or-later", True, False, False), ("LGPL-2.0-only", True, False, False),
            ("GPL-3+", True, False, False),                                      # Debian (security u1 I-1)
            ("MIT AND GPL-3.0-or-later", True, False, False),
            ("GPL-2.0-only WITH Classpath-exception-2.0", True, False, False),
            ("LGPL-2.1-or-later OR Apache-2.0", False, False, False),          # permissive branch elected
            ("MIT", False, False, False), ("GFDL-1.3", False, False, False), ("Apache-2.0", False, False, False),
            ("GPL-2.0-only OR LGPL-2.1-only", True, False, False),
            ("Apache-2.0 WITH LLVM-exception", False, False, False),           # the exception id is not read
        ])

    def test_debian_with_autoconf_exception(self):
        # `with` lower-case is WITH; "Autoconf exception" is two leaves, so
        # the text does not parse, and the token rule over it fails closed.
        self.check([("GPL-2+ with Autoconf exception", True, True, None),
                    ("GPL-3+ with Libtool exception", True, True, None)])

    def test_precedence_and_parentheses(self):
        # SPDX 2.3 Annex D: WITH > AND > OR; parentheses override (N8 amendment, U5, item 1).
        self.check([
            ("MIT OR GPL-2.0-only AND Apache-2.0", False, False, False),
            ("GPL-2.0-only AND Apache-2.0 OR MIT", False, False, False),
            ("(MIT OR GPL-2.0-only) AND Apache-2.0", False, False, False),
            ("(MIT OR Apache-2.0) AND GPL-2.0-only", True, False, False),
            ("GPL-2.0-only AND (MIT OR Apache-2.0)", True, False, False),
            ("((GPL-2.0-only))", True, False, False),
            ("(MIT AND (Zlib OR (GPL-2.0-or-later AND LGPL-2.1-only))) OR BSD-3-Clause", False, False, False),
            ("(GPL-2.0-only OR LGPL-2.1-only) AND MIT", True, False, False),
            ("MIT AND (BSD-2-Clause OR (Apache-2.0 AND (LGPL-3.0-only OR GPL-3.0-only)))", False, False, False),
            ("MIT AND ((BSD-2-Clause AND GPL-2.0-only) OR (LGPL-3.0-only AND Zlib))", True, False, False),
            ("MIT OR GPL-2.0-only WITH Classpath-exception-2.0", False, False, False),
            ("Apache-2.0 AND GPL-2.0-only WITH Classpath-exception-2.0", True, False, False),
        ])

    def test_operators_any_case(self):
        self.check([("MIT and GPL-2.0-only", True, False, False),
                    ("LGPL-2.1-or-later Or Apache-2.0", False, False, False),
                    ("mit oR gpl-2.0-only", False, False, False),
                    ("GPL-2.0-only With Classpath-exception-2.0", True, False, False),
                    ("Apache-2.0 aNd LGPL-2.1-only", True, False, False)])

    def test_unknown_leaves_need_source_and_are_unidentified(self):
        # Hash ids (N8, security H-1) and NONE/NOASSERTION leaves (L-4; N8
        # amendment, U5, item 1) are unknown: needs, listed unidentified.
        self.check([
            (HASH, True, False, True),
            (f"Apache-2.0 AND {HASH}", True, False, True),
            (f"{HASH} AND {HASH2}", True, False, True),
            (f"MIT OR {HASH}", False, False, True),                             # MIT elected, still listed
            (f"{HASH} OR NOASSERTION", True, False, True),
            ("MIT AND NOASSERTION", True, False, True),
            ("MIT AND NONE", True, False, True),
            ("(NOASSERTION)", True, False, True),
            ("MIT OR NOASSERTION", False, False, True),
            (f"{HASH} WITH Classpath-exception-2.0", True, False, True),       # needs(X WITH e) = needs(X)
            ("NOASSERTION WITH Classpath-exception-2.0", True, False, True),
            (f"({HASH} OR MIT) AND GPL-2.0-only", True, False, True),
        ])
        with self.subTest(case="only syft's exact spelling is a hash id (case-sensitive, 64 hex)"):
            for near in ("LicenseRef-" + "0123456789ABCDEF" * 4, "LicenseRef-" + "0" * 63):
                self.assertFalse(verdict(near)[2], f"{near} is not a hash id")
        with self.subTest(case="NONE/NOASSERTION leaves under ASCII case-fold (rework ruling 1, review B2)"):
            # Was "exact and case-sensitive" (amendment item 1); superseded by
            # the N8 amendment's "Rework round 1" item 1 (CLAUDE.md Contradictions).
            self.assertTrue(verdict("MIT AND noassertion")[2], "`noassertion` is an unknown leaf")

    def test_named_licenseref_rows(self):
        # Orchestrator U5 ruling 5; N8 amendment, U5, first failing tests.
        self.check([
            ("LicenseRef-scancode-public-domain", False, False, False),
            ("LicenseRef-Public-Domain", False, False, False),
            ("LicenseRef-GPL-2.0-only", True, False, False),
            ("LICENSEREF-GPL-2.0-only", True, False, False),                  # lower-cased, then stripped
            ("LicenseRef-GPL-2.0-with-foo-exception", True, False, False),   # the pattern catches it
            ("LicenseRef-lgpl-custom", True, True, False),                    # only the token rule does
            ("LicenseRef-GPL-3--WITH-BISON-EXCEPTION", True, True, False),
            ("LicenseRef-DONT-CHANGE-THE-GPL", True, True, False),
            ("MIT AND LicenseRef-lgpl-custom", True, True, False),
            ("LicenseRef-GFDL-NIV-1.3", False, False, False),
        ])

    def test_url_folded_ids(self):
        # N8a items 2-4: jaxb-api and javassist need source and are listed
        # unparsed; every LicenseRef- id holding http is listed (any case).
        self.check([
            (JAXB, True, True, False), (JAXB.lower(), True, True, False),
            (JAVASSIST, True, True, False), (JAVASSIST.lower(), True, True, False),
            (JAVASSIST.replace("lgpl", "LGpl"), True, True, False),
            (CLASSPATH, False, True, False),
            ("LicenseRef-HTTPS---example.org-licence", False, True, False),
            (f"Apache-2.0 OR {JAXB}", False, True, False),
            (f"Apache-2.0 AND {JAXB}", True, True, False),
        ])

    def test_unparseable_text(self):
        # N8 "Unparseable text"; N8 amendment, U5, item 1 (the token rule
        # over the whole text); orchestrator U5 addition 3 (a hash id in it).
        self.check([
            ("see the GPL for details", True, True, False),
            ("GPL version 2 or later", True, True, False),
            ("GPL v2", True, True, False),
            ("the LGPL, version 2.1", True, True, False),
            ("distributed under GPLv2", True, True, False),
            ("see COPYING for details", False, True, False),
            ("Public Domain", False, True, False),
            (f"Public Domain OR {HASH}", True, True, True),
            ("GPL-2.0-only MIT", True, True, None),                          # two leaves adjacent
            ("MIT Apache-2.0", False, True, False),
            ("", False, True, False),
            ("(MIT OR GPL-2.0-only", True, True, None),                       # unbalanced
            ("MIT OR GPL-2.0-only)", True, True, None),
            ("MIT)", False, True, False), ("()", False, True, False), ("( )", False, True, False),
            ("MIT AND", False, True, False), ("AND GPL-2.0-only", True, True, None),
            ("OR", False, True, False), ("MIT AND OR Apache-2.0", False, True, False),
            ("MIT WITH", False, True, False), ("WITH Classpath-exception-2.0", False, True, False),
            ("GPL-2.0-only WITH", True, True, None),
            ("(MIT OR Apache-2.0) WITH Classpath-exception-2.0", False, True, False),
            ("MIT WITH (Classpath-exception-2.0)", False, True, False),
        ])

    def test_needs_source_never_raises(self):
        needs_source = fn("needs_source")
        deep = "(" * 3000 + "GPL-2.0-only" + ")" * 3000
        for expr in (deep, "(" * 5000, ")" * 5000, "AND " * 2000, "\x00\x1b[31m", "GPL\n2", "\t", "((((MIT))))"):
            with self.subTest(expr=expr[:30]):
                needs, info = needs_source(expr)
                self.assertIn("unparsed", info)
        self.assertTrue(verdict(deep)[0], "a deeply nested GPL id needs source (fail closed)")


# --------------------------------------------------------------------------
# licence_input: N8 input selection with the classifier's "missing" (L-4)
# --------------------------------------------------------------------------

class LicenceInputTest(unittest.TestCase):
    def test_licence_input_selection(self):
        li = fn("licence_input")
        rows = {
            "declared alone": (pkg("GPL-2.0-only"), "GPL-2.0-only"),
            "declared, concluded NOASSERTION": (pkg("MIT", "NOASSERTION"), "MIT"),
            "declared NOASSERTION falls through to concluded (N8a 1, jna)":
                (pkg("NOASSERTION", "Apache-2.0 AND LGPL-2.1-only"), "Apache-2.0 AND LGPL-2.1-only"),
            "declared NONE falls through": (pkg("NONE", "MIT"), "MIT"),
            "declared empty falls through": (pkg("", "MIT"), "MIT"),
            "declared absent falls through": (pkg(concluded="MIT"), "MIT"),
            "declared null falls through": (pkg(None, "MIT"), "MIT"),
            "both set and differ": (pkg("MIT", "GPL-2.0-only"), "(MIT) AND (GPL-2.0-only)"),
            "both set and equal: one copy": (pkg("MIT", "MIT"), "MIT"),
            "hash-only declared is set (L-4)": (pkg(HASH, "MIT"), f"({HASH}) AND (MIT)"),
            "hash-only declared alone is set": (pkg(HASH, "NOASSERTION"), HASH),
            "hash-only concluded is set": (pkg("NOASSERTION", HASH), HASH),
            "files when both are missing, one entry": (pkg("NOASSERTION", "NOASSERTION", ["MIT"]), "MIT"),
            "files: missing and wrong-type entries dropped, list order kept":
                (pkg("NOASSERTION", "NONE", ["GPL-2.0-only", "NOASSERTION", 7, None, "", "MIT"]),
                 "(GPL-2.0-only) AND (MIT)"),
            "files: compound entries parenthesised":
                (pkg(files=["MIT OR Apache-2.0", "GPL-2.0-only"]), "(MIT OR Apache-2.0) AND (GPL-2.0-only)"),
            "files: a hash-only entry is set": (pkg(files=[HASH]), HASH),
            "files not read when declared is set (N8 input order)": (pkg("MIT", files=["GPL-2.0-only"]), "MIT"),
            "missing is exact and case-sensitive: `noassertion` is set": (pkg("noassertion"), "noassertion"),
            "missing has no strip: ` NOASSERTION` is set": (pkg(" NOASSERTION"), " NOASSERTION"),
            "all missing": (pkg("NOASSERTION", "NONE", []), None),
            "all absent": (pkg(), None),
            "files all missing": (pkg("NOASSERTION", "NOASSERTION", ["NOASSERTION", "", None]), None),
        }
        for case, (p, want) in rows.items():
            with self.subTest(case=case):
                self.assertEqual(li(p), want, case)

    def test_licence_input_type_rule(self):
        # N8 type rule: a wrong-type value is missing, and never crashes.
        li = fn("licence_input")
        rows = {
            "non-string declared falls to concluded": (pkg(42, "MIT"), "MIT"),
            "list declared falls to concluded": (pkg(["GPL-2.0-only"], "MIT"), "MIT"),
            "dict declared, nothing else": (pkg({"id": "GPL-2.0-only"}), None),
            "non-string concluded": (pkg("NOASSERTION", ["MIT"]), None),
            "files a string, not a list": (pkg(files="GPL-2.0-only"), None),
            "files a dict": (pkg(files={"a": "GPL-2.0-only"}), None),
            "files with unhashable entries": (pkg(files=[["GPL"], {"a": 1}, "MIT"]), "MIT"),
            "bool declared": (pkg(True, "Apache-2.0"), "Apache-2.0"),
        }
        for case, (p, want) in rows.items():
            with self.subTest(case=case):
                self.assertEqual(li(p), want, case)


# --------------------------------------------------------------------------
# classify_package
# --------------------------------------------------------------------------

KEYS = {"needs", "expression", "unlicensed", "unparsed", "unidentified", "purl", "spdxid", "name"}


def classified(p: dict[str, Any]) -> dict[str, Any]:
    got = fn("classify_package")(p)
    missing = KEYS - set(got) if isinstance(got, dict) else KEYS
    if missing:
        raise AssertionError(f"classify_package returns {got!r}, lacking {sorted(missing)} (U5 ruling 2)")
    return got


class ClassifyPackageTest(unittest.TestCase):
    def assertRow(self, p: dict[str, Any], **want: Any) -> dict[str, Any]:
        got = classified(p)
        for key, value in want.items():
            have = got[key] if key in ("expression", "purl", "spdxid", "name") else bool(got[key])
            self.assertEqual(have, value, f"{key} is {got[key]!r}, want {value!r} for {p}")
        return got

    def test_classify_package_keys_and_raw_values(self):
        evil = "evil\x1b[31m"
        self.assertRow(pkg("GPL-2.0-only", purl="pkg:deb/debian/bash@5.2?arch=amd64", spdxid="SPDXRef-Package-bash",
                           name=evil),
                       needs=True, expression="GPL-2.0-only", unlicensed=False, unparsed=False, unidentified=False,
                       purl="pkg:deb/debian/bash@5.2?arch=amd64", spdxid="SPDXRef-Package-bash", name=evil)
        self.assertRow(pkg("MIT"), needs=False, unlicensed=False, purl=None)

    def test_both_fields_set(self):
        # N8 l.786 and the N8 amendment, U5, item 2: needs is any over the
        # parts, flags OR-ed; one junk part cannot hide a GPL or hash part.
        self.assertRow(pkg(HASH, "MIT"), needs=True, unidentified=True, unlicensed=False, unparsed=False,
                       expression=f"({HASH}) AND (MIT)")
        self.assertRow(pkg("MIT", HASH), needs=True, unidentified=True, unlicensed=False)
        self.assertRow(pkg("MIT", "GPL-2.0-only"), needs=True)
        self.assertRow(pkg("GPL-2.0-only", "MIT"), needs=True)
        self.assertRow(pkg("MIT OR GPL-2.0-only", "Apache-2.0"), needs=False)
        self.assertRow(pkg("see COPYING", "LGPL-2.1-only"), needs=True, unparsed=True)
        self.assertRow(pkg("Public Domain", HASH), needs=True, unparsed=True, unidentified=True)
        self.assertRow(pkg("MIT", CLASSPATH), needs=False, unparsed=True, unidentified=False)

    def test_jna_fall_through_is_literal(self):
        # N8a 1: syft's AND is kept literally (the exemption is U6's).
        self.assertRow(pkg("NOASSERTION", "Apache-2.0 AND LGPL-2.1-only"), needs=True, unparsed=False,
                       unidentified=False, unlicensed=False, expression="Apache-2.0 AND LGPL-2.1-only")

    def test_hash_only_package_is_classified_and_still_reported(self):
        # N8 amendment, U5, item 1: all fields hash-only -> in the U4 report
        # and classified needs, unidentified, not unlicensed.
        p = pkg(HASH, HASH2, purl="pkg:deb/debian/wget@1.25.0-2?arch=amd64")
        self.assertRow(p, needs=True, unidentified=True, unlicensed=False)
        doc = ss.spdx_doc("neo4j", [{"purl": "pkg:deb/debian/wget@1.25.0-2?arch=amd64", "declared": HASH,
                                      "concluded": HASH2}])
        report = load_sbom_check().unlicensed_report(doc)
        self.assertEqual(report["count"], 1, "the U4 report keeps hash-only rows (its rule is unchanged)")
        with self.subTest(case="declared <hash>, concluded MIT: classified, not in the U4 report (L-4)"):
            doc = ss.spdx_doc("neo4j", [{"purl": "pkg:deb/debian/x@1?arch=amd64", "declared": HASH,
                                          "concluded": "MIT"}])
            self.assertEqual(load_sbom_check().unlicensed_report(doc)["count"], 0)

    def test_files_list(self):
        self.assertRow(pkg("NOASSERTION", "NOASSERTION", ["MIT OR Apache-2.0", "GPL-2.0-only"]), needs=True)
        self.assertRow(pkg(files=["MIT", "NOASSERTION", "Apache-2.0"]), needs=False, unlicensed=False,
                       unidentified=False)
        self.assertRow(pkg(files=["MIT", HASH]), needs=True, unidentified=True)
        self.assertRow(pkg(files=["see COPYING", "LGPL-2.1-only"]), needs=True, unparsed=True)

    def test_unlicensed_packages(self):
        # Ruling 2: unlicensed -> needs false (unless `always`, at document
        # level), expression None, both flags false.
        for case, p in {"NOASSERTION both": pkg("NOASSERTION", "NOASSERTION"), "NONE both": pkg("NONE", "NONE"),
                        "all absent": pkg(), "files []": pkg("NOASSERTION", "NOASSERTION", []),
                        "files all missing": pkg(files=["NOASSERTION", None, 3]),
                        "wrong types everywhere": pkg(42, ["GPL"], "GPL-2.0-only"),
                        "empty strings": pkg("", "", [""])}.items():
            with self.subTest(case=case):
                self.assertRow(p, needs=False, unlicensed=True, unparsed=False, unidentified=False, expression=None)


# --------------------------------------------------------------------------
# classify_document
# --------------------------------------------------------------------------

def real_always() -> list[dict[str, Any]]:
    return json.loads(POLICY.read_text(encoding="utf-8"))["always"]


def rows_by_purl(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.get("purl"):
            out.setdefault(str(r["purl"]).split("@", 1)[0], r)
    return out


class ClassifyDocumentTest(unittest.TestCase):
    def test_classify_document_skips_root_and_applies_always(self):
        classify = fn("classify_document")
        doc = ss.spdx_doc("valkey", [
            {"purl": "pkg:apk/alpine/busybox@1.37.0-r19?arch=x86_64", "declared": "NOASSERTION"},
            {"purl": "pkg:apk/alpine/musl@1.2.5-r10?arch=x86_64", "declared": "MIT"},
            {"purl": "pkg:apk/alpine/apk-tools@2.14.9-r2?arch=x86_64", "declared": "MIT"},
            {"purl": "pkg:apk/alpine/readline@8.2-r1?arch=x86_64", "declared": "GPL-3.0-or-later"},
        ], root_licence="GPL-2.0-only")
        always = [{"image": "valkey", "match": "pkg:apk/alpine/busybox", "why": "t"},
                  {"image": "valkey", "match": "pkg:apk/alpine/apk-tools", "why": "t"},
                  {"image": "ke-gateway", "match": "pkg:apk/alpine/musl", "why": "another image's entry"}]
        rows = classify("valkey", doc, always)
        root = doc["relationships"][0]["relatedSpdxElement"]
        self.assertNotIn(root, [r["spdxid"] for r in rows], "the DESCRIBES root is classified (N8a 4)")
        self.assertEqual([r["spdxid"] for r in rows], [p["SPDXID"] for p in doc["packages"][1:]],
                         "one row per package, document order")
        by = rows_by_purl(rows)
        want = {"pkg:apk/alpine/busybox": (True, True, True), "pkg:apk/alpine/musl": (False, False, False),
                "pkg:apk/alpine/apk-tools": (True, True, False), "pkg:apk/alpine/readline": (True, False, False)}
        for purl, (needs, always_flag, unlicensed) in want.items():
            with self.subTest(purl=purl):
                r = by[purl]
                self.assertIs(r.get("always"), always_flag, f"{purl}: always is {r.get('always')!r}")
                self.assertEqual(bool(r["needs"]), needs, f"{purl}: needs")
                self.assertEqual(bool(r["unlicensed"]), unlicensed, f"{purl}: unlicensed")
        with self.subTest(case="no always entries: unlicensed busybox needs no source"):
            self.assertFalse(rows_by_purl(classify("valkey", doc, []))["pkg:apk/alpine/busybox"]["needs"])

    def test_classify_document_real_neo4j_rows(self):
        # N8a items 1-4 on syft's real neo4j rows, with the real `always`
        # (the image is ke-neo4j since U4b; same packages, N16).
        rows = fn("classify_document")("ke-neo4j", ss.spdx_doc("ke-neo4j", ss.u3_rows("neo4j")), real_always())
        self.assertEqual(len(rows), len(ss.u3_rows("neo4j")))
        by = rows_by_purl(rows)
        want = {  # purl: needs, unparsed, unidentified, unlicensed, always
            "pkg:maven/com.sun.jna/jna": (True, False, False, False, False),
            "pkg:maven/javax.xml.bind/jaxb-api": (True, True, False, False, False),
            "pkg:maven/org.javassist/javassist": (True, True, False, False, False),
            "pkg:maven/org.glassfish.hk2/hk2-api": (False, True, False, False, False),
            "pkg:generic/oracle/openjdk": (True, False, False, True, True),
            "pkg:maven/jrt-fs/jrt-fs": (True, False, False, True, True),
            "pkg:maven/org.neo4j/neo4j": (True, None, None, False, True),
            "pkg:deb/debian/wget": (True, False, True, False, False),
            "pkg:deb/debian/gcc-14-base": (True, False, True, False, True),
        }
        names = ("needs", "unparsed", "unidentified", "unlicensed", "always")
        for purl, values in want.items():
            with self.subTest(purl=purl):
                self.assertIn(purl, by, f"the neo4j fixture has no {purl}")
                for key, value in zip(names, values):
                    if value is not None:
                        self.assertEqual(bool(by[purl][key]), value, f"{purl}: {key} is {by[purl][key]!r}")
        self.assertEqual(by["pkg:maven/com.sun.jna/jna"]["expression"], "Apache-2.0 AND LGPL-2.1-only")

    def test_classify_document_real_rows_every_image(self):
        classify = fn("classify_document")
        always = real_always()
        report_of = load_sbom_check().unlicensed_report
        for image in ss.U3_IMAGES:
            name = "ke-neo4j" if image == "neo4j" else image
            with self.subTest(image=image):
                doc = ss.spdx_doc(name, ss.u3_rows(image))
                rows = classify(name, doc, always)
                self.assertEqual(len(rows), len(ss.u3_rows(image)), "one row per package but the root")
                by_sid = {r["spdxid"]: r for r in rows}
                for r in rows:
                    if r["unlicensed"]:
                        self.assertEqual(bool(r["needs"]), bool(r["always"]),
                                         f"{r['purl']}: unlicensed needs source only by `always`")
                    if r["always"]:
                        self.assertTrue(r["needs"], f"{r['purl']}: an `always` match needs source")
                for row in report_of(doc)["packages"]:
                    if row.get("unidentified"):
                        r = by_sid[row["spdxid"]]
                        self.assertTrue(r["needs"] and r["unidentified"] and not r["unlicensed"],
                                        f"{row['purl']}: a hash-only row needs source, unidentified (L-4)")
        with self.subTest(case="ke-app: psycopg and the openldap rows by `always`"):
            by = rows_by_purl(classify("ke-app", ss.spdx_doc("ke-app", ss.u3_rows("ke-app")), always))
            self.assertTrue(by["pkg:pypi/psycopg"]["always"] and by["pkg:pypi/psycopg"]["needs"])
            ldap = [r for r in classify("ke-app", ss.spdx_doc("ke-app", ss.u3_rows("ke-app")), always)
                    if "upstream=openldap" in str(r["purl"])]
            self.assertTrue(ldap and all(r["always"] and r["needs"] for r in ldap), "openldap rows")


# --------------------------------------------------------------------------
# Escaping and anchors (security U4 L-5, review U4 R2; N8 amendment, U5, item 7)
# --------------------------------------------------------------------------

def raw_controls(lines: list[str]) -> list[str]:
    return [ln for ln in lines if CONTROL.search(ln)]


class EscapingTest(unittest.TestCase):
    def _doc(self) -> dict[str, Any]:
        return ss.spdx_doc("x", [{"purl": "pkg:pypi/a@1", "declared": "MIT"}])

    def test_validate_rejects_trailing_newline_spdxid_and_prints_escaped(self):
        validate = load_sbom_check().validate
        for sid in ("SPDXRef-Package-a\n", "SPDXRef-\x1b[2J", "SPDXRef-a\x85"):
            with self.subTest(sid=sid):
                doc = self._doc()
                doc["packages"][1]["SPDXID"] = sid
                doc["packages"][1]["name"] = ""
                problems = validate(doc)
                self.assertTrue([p for p in problems if "SPDXRef-" in p and "SPDXID" in p],
                                f"validate accepts the SPDXID {sid!r} (`$` matches before a final newline; "
                                f"use fullmatch): {problems}")
                self.assertEqual(raw_controls(problems), [], "validate prints SBOM text raw (L-5: _clean)")

    def test_validate_rejects_created_with_trailing_newline(self):
        doc = self._doc()
        doc["creationInfo"]["created"] = "2026-10-23T10:00:00Z\n"
        problems = load_sbom_check().validate(doc)
        self.assertTrue([p for p in problems if "created" in p], f"created with a trailing newline accepted: {problems}")
        self.assertEqual(raw_controls(problems), [])

    def test_drift_problems_escape_debian_name_and_cpython_version(self):
        drift = load_sbom_check().drift_problems
        base, added, texts = ss.fake_base_doc(), ss.added_packages(), ss.licence_texts()
        for name in ("evil%1b%5b31m", "evil%0a"):
            with self.subTest(debian=name):
                app = ss.ke_app_doc(extra=({"purl": f"pkg:deb/debian/{name}@1.0?arch=amd64", "declared": "MIT"},))
                problems = drift(app, base, added, texts)
                self.assertEqual(len(problems), 1, problems)
                self.assertEqual(raw_controls(problems), [], f"a Debian name printed raw (L-5, R2): {problems!r}")
                self.assertIn("evil\\x", problems[0], "the name is printed escaped (\\xNN)")
        with self.subTest(case="CPython version with an ESC"):
            app = ss.ke_app_doc(cpython=ss.licence_version() + "%1b")
            problems = drift(app, base, added, texts)
            self.assertTrue(problems, "a CPython version with an ESC matched the licence files")
            self.assertEqual(raw_controls(problems), [], f"the CPython version printed raw: {problems!r}")

    def test_psycopg_problems_escape(self):
        check = load_sbom_check().psycopg_problems
        app = ss.ke_app_doc(libpq=ss.libpq_pin() + "\x1b", extra=(
            {"purl": ss.pypi("psycopg-binary", "3.2.0\x1b"), "declared": "LGPL-3.0-only"},))
        problems = check(app, ss.libpq_pin(), ss.locked_version("psycopg-c"))
        self.assertGreaterEqual(len(problems), 2, problems)
        self.assertEqual(raw_controls(problems), [], f"psycopg problems printed raw: {problems!r}")

    def test_finish_argv_patterns_fullmatch(self):
        # N8 amendment, U5, item 7: NAME_RE and SHA_RE with fullmatch, so a
        # trailing newline is a bad argument (exit 2) before any read.
        main = load_sbom_check().main
        good = {"--name": "ke-app", "--git-sha": "a" * 40}
        for key, bad in (("--name", "ke-app\n"), ("--git-sha", "a" * 40 + "\n")):
            with self.subTest(arg=key):
                args = dict(good, **{key: bad})
                argv = ["finish", "--name", args["--name"], "--ref", "ke-app:bundle-x", "--arch", "amd64",
                        "--git-sha", args["--git-sha"], "--raw", "/nonexistent/raw.json", "--tar", "/nonexistent/t.tar"]
                import contextlib
                import io
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(argv), 2, f"{key} {bad!r} is not refused as a bad argument")


# --------------------------------------------------------------------------
# U5 rework round 1 (review B1-B3, security L-1..L-4, L-5a; orchestrator
# rulings 1-7 and additions a-b; design-notes "N8 amendment, U5", "Rework
# round 1", l.1083 on). Every rule fails closed.
# --------------------------------------------------------------------------

NBSP, ZWJ, CYR_ER, DOTLESS_I = "\u00a0", "\u200d", "\u0420", "\u0131"


class ReworkR1UnknownLeavesTest(_Table):
    """Ruling 1 (review B2, security L-2): NONE/NOASSERTION leaves under
    ASCII case-fold are unknown; in unparseable text a separated run equal
    to either (any case) counts like a hash id. The whole-field predicate
    and the U4 report stay exact. Addition b: the same ids, or a hash id,
    in the WITH exception slot are unknown."""

    def test_unknown_leaves_any_case(self):
        self.check([
            ("noassertion", True, False, True), ("NoAssertion AND MIT", True, False, True),
            ("MIT AND none", True, False, True), ("MIT OR nOnE", False, False, True),
            ("(noassertion)", True, False, True), ("NOASSERTIONS", False, False, False),
            ("LicenseRef-NONE", False, False, False),
        ])
        with self.subTest(case="the whole-field predicate stays exact: `none` is set, its leaf unknown"):
            self.assertEqual(fn("licence_input")(pkg("none")), "none")
            got = classified(pkg("none"))
            self.assertTrue(got["needs"] and got["unidentified"] and not got["unlicensed"], got)
        with self.subTest(case="the U4 report rule is unchanged: a field `none` is licensed there"):
            doc = ss.spdx_doc("x", [{"purl": "pkg:deb/debian/y@1?arch=amd64", "declared": "none", "concluded": "none"}])
            self.assertEqual(load_sbom_check().unlicensed_report(doc)["count"], 0)

    def test_unknown_runs_in_unparseable_text(self):
        self.check([
            ("Public Domain AND NOASSERTION", True, True, True), ("MIT NOASSERTION", True, True, True),
            ("MIT AND (NOASSERTION", True, True, True), ("(NOASSERTION) WITH x", True, True, True),
            ("NOASSERTION NONE", True, True, True), ("MIT AND AND NOASSERTION", True, True, True),
            ("public domain and none", True, True, True), ("see (noassertion) here", True, True, True),
            # near misses: a run that only contains the word
            # `see NONE.txt here` moved to U6SegmentRuleTest: it needs source
            # under U6 ruling 5 (segment rule; CLAUDE.md Contradictions).
            ("NOASSERTIONS apply", False, True, False),
            ("Public Domain", False, True, False),
        ])

    def test_unknown_exception_ids(self):
        # Addition b: a hash id or NONE/NOASSERTION (any case) after WITH.
        self.check([
            (f"MIT WITH {HASH}", True, None, True), ("MIT WITH NOASSERTION", True, None, True),
            ("MIT WITH none", True, None, True), ("Apache-2.0 WITH NoAssertion", True, None, True),
            (f"MIT OR (Apache-2.0 WITH {HASH})", False, None, True),
            ("Apache-2.0 WITH LLVM-exception", False, False, False),
            (f"MIT WITH LicenseRef-{'0' * 63}", False, False, False),
        ])


class ReworkR1TokenRuleTest(_Table):
    """Ruling 2 (security L-1) and addition a: a token containing `gpl`, the
    consecutive tokens `general public licen[cs]e[s]` (`lesser` optional
    and not enough alone), or the token `affero` hit; a hit only by the
    token rule is listed unparsed."""

    def test_wider_token_rule_ids(self):
        is_gpl = fn("is_gpl_id")
        hits = ("LicenseRef-GNU-General-Public-License-v2", "LicenseRef-GNU-Affero-General-Public-License",
                "GPLv2orlater", "LicenseRef-libgpl-helper", "GPLX", "LicenseRef-General-Public-Licence-v3",
                "LicenseRef-GNU-General-Public-Licenses", "LicenseRef-Affero", "LicenseRef-GNU-Lesser-General-Public-License",
                "LicenseRef-gnu-general-public-licences")
        misses = ("LicenseRef-https---www.gnu.org-copyleft-lesser.html", "LicenseRef-General-Public",
                  "LicenseRef-Public-License", "LicenseRef-General-Public-Domain-License", "LicenseRef-Lesser",
                  "LicenseRef-GNU", CLASSPATH, "MIT", "EUPL-1.2")
        for i in hits:
            with self.subTest(hit=i):
                self.assertIs(bool(is_gpl(i)), True, f"is_gpl_id({i!r}) is false (ruling 2)")
        for i in misses:
            with self.subTest(miss=i):
                self.assertIs(bool(is_gpl(i)), False, f"is_gpl_id({i!r}) is true")

    def test_wider_token_rule_expressions(self):
        self.check([
            ("LicenseRef-GNU-General-Public-License-v2", True, True, False),
            ("LicenseRef-GNU-Affero-General-Public-License", True, True, False),
            ("GNU General Public License v2", True, True, False),
            ("GNU Lesser General Public License", True, True, False),
            ("the GNU General Public Licenses", True, True, False),
            ("General Public Licence, version 3", True, True, False),
            ("GPLv2orlater", True, True, False),
            ("MIT AND LicenseRef-libgpl-helper", True, True, False),
            ("Affero terms", True, True, False),
            # ruled row: `lesser` alone is not a hit; listed via http
            ("LicenseRef-https---www.gnu.org-copyleft-lesser.html", False, True, False),
            ("General Public", False, True, False), ("public license", False, True, False),
            ("LGPL2", True, False, False),                                   # the anchored pattern, not the token rule
            ("MIT OR LicenseRef-GNU-General-Public-License-v2", False, True, False),
        ])


class ReworkR1NonAsciiTest(_Table):
    """Ruling 3 (security L-3, review N2): any non-ASCII character in an
    expression needs source and is listed unparsed; AND/OR/WITH are ASCII
    letters only (dotless i is not an operator)."""

    def test_non_ascii_expressions(self):
        self.check([
            (f"G{CYR_ER}L-3.0-only", True, True, None), ("\uff27\uff30\uff2c-3.0", True, True, None),
            (f"G{ZWJ}PL-2.0", True, True, None), (f"MIT w{DOTLESS_I}th GPL-2.0-only", True, True, None),
            (f"MIT w{DOTLESS_I}th Classpath-exception-2.0", True, True, None),
            (f"MIT AND Apache-2.0{NBSP}", True, True, None), ("Zlib OR caf\u00e9", True, True, None),
            (f"MIT {NBSP}OR Apache-2.0", True, True, None), ("MIT \uff21\uff2e\uff24 Zlib", True, True, None),
            ("MIT", False, False, False), ("Zlib OR MIT", False, False, False),
        ])

    def test_non_ascii_package(self):
        got = classified(pkg(f"G{CYR_ER}L-3.0-only", "MIT"))
        self.assertTrue(got["needs"] and got["unparsed"], got)
        got = classified(pkg(files=["MIT", f"BSD-3-Clause{ZWJ}"]))
        self.assertTrue(got["needs"] and got["unparsed"], got)


class ReworkR1WithExceptionTest(_Table):
    """Ruling 4 (security L-4, review N1): a GPL-family exception id (pattern
    or token rule) makes the leaf need source, listed unparsed."""

    def test_gpl_family_exception_id(self):
        self.check([
            ("MIT WITH GPL-3.0-only", True, True, False), ("MIT WITH LicenseRef-lgpl-exception", True, True, False),
            ("Apache-2.0 with gpl-2.0-or-later", True, True, False),
            ("MIT WITH LicenseRef-GNU-General-Public-License", True, True, False),
            ("MIT OR Apache-2.0 WITH GPL-3.0-only", False, True, False),       # MIT elected, still listed
            ("GPL-2.0-only WITH Classpath-exception-2.0", True, False, False),
            ("Apache-2.0 WITH LLVM-exception", False, False, False),
            ("MIT WITH Bison-exception-2.2", False, False, False),
        ])


class ReworkR1PerPartTest(unittest.TestCase):
    """Ruling 6 (review B1): needs and the flags are taken per part
    (licence_input's parts), so an unparseable part never hides an unknown
    leaf in a parseable part beside it."""

    def test_unparseable_part_does_not_hide_an_unknown_leaf(self):
        # The review's B1 rows (ruling 6).
        for case, p in {"declared + concluded": pkg("Public Domain", "MIT AND NOASSERTION"),
                        "licenseInfoFromFiles": pkg(files=["Public Domain", "MIT AND NONE"]),
                        "a hash leaf beside junk": pkg("see COPYING", f"MIT AND {HASH}")}.items():
            with self.subTest(case=case):
                got = classified(p)
                self.assertTrue(got["needs"], f"{case}: needs is {got['needs']!r} (per-part rule, B1)")
                self.assertTrue(got["unidentified"], f"{case}: unidentified is {got['unidentified']!r}")
                self.assertTrue(got["unparsed"], f"{case}: unparsed is {got['unparsed']!r}")

    def test_each_part_is_classified_alone(self):
        # needs = any(needs_source(part)) (amendment item 2 precision), not
        # needs_source of the joined text: an OR election in one part stays
        # elected beside an unparseable part. Under rework ruling 1 the B1
        # rows alone no longer separate the two (the joined text does not
        # parse, and its NOASSERTION run now counts), so these rows do.
        rows = {"election beside junk": (pkg("MIT OR GPL-2.0-only", "Public Domain"), False, True, False),
                "unknown branch not elected, beside junk": (pkg("BSD-2-Clause OR NONE", "Public Domain"),
                                                            False, True, True),
                "files: election beside junk": (pkg(files=["Apache-2.0 OR LGPL-2.1-only", "see COPYING"]),
                                                False, True, False),
                "a GPL part beside an election": (pkg("MIT OR Apache-2.0", "GPL-2.0-only"), True, False, False)}
        for case, (p, needs, unparsed, unidentified) in rows.items():
            with self.subTest(case=case):
                got = classified(p)
                self.assertEqual((bool(got["needs"]), bool(got["unparsed"]), bool(got["unidentified"])),
                                 (needs, unparsed, unidentified), f"{case}: {got}")


class ReworkR1DriftLineTest(unittest.TestCase):
    """Ruling 5 (review B3, security L-5a): drift's success line takes CPython
    from the non-namespaced pkg:generic/python set and prints it through
    _clean."""

    def _cli(self, app: dict[str, Any]) -> tuple[Any, str, str]:
        import contextlib
        import io
        import shutil
        import tempfile
        from pathlib import Path
        work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, work, True)
        app_p = ss.write_json(work / "app.json", app)
        base_p = ss.write_json(work / "base.json", ss.fake_base_doc())
        argv = ["drift", "--sbom", str(app_p), "--base", str(base_p),
                "--added-from", str(ROOT / "tests" / "test_notice_ke_app.py"), "--libpq", ss.libpq_pin(),
                "--lock", str(ROOT / "uv.lock")]
        for rel in ss.LICENCE_FILES:
            argv += ["--licence", str(ROOT / rel)]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = load_sbom_check().main(argv)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_drift_success_line_is_clean_and_non_namespaced(self):
        version = ss.licence_version()
        for case, purl in {"the reviewer's probe row": "pkg:generic/x/python@3.12.15%1b%5b2J",
                           "security's probe row": "pkg:generic/x/python@3.12.15%1b%5d0%3bOWNED%07%1b%5b2J",
                           "a namespaced row with a plain version": "pkg:generic/x/python@9.9.9"}.items():
            with self.subTest(case=case):
                app = ss.ke_app_doc(extra=({"purl": purl, "declared": "MIT"},))
                code, out, err = self._cli(app)
                self.assertEqual(code, 0, f"drift failed on a namespaced python row it does not check: {err}")
                self.assertEqual(raw_controls(out.splitlines() + err.splitlines()), [],
                                 f"drift's success line prints SBOM text raw (B3, L-5a): {out!r}")
                self.assertIn(f"CPython {version} (", out, "the success line names the checked CPython only")
                self.assertNotIn("9.9.9", out, "the success line lists a namespaced pkg:generic/<ns>/python")
                self.assertNotIn("[2J", out)


# --------------------------------------------------------------------------
# U5 rework round 2 (review R1-B1, R1-N1, R1-N2; orchestrator rulings a-e;
# design-notes "N8 amendment, U5", "Rework round 2"). Every rule fails closed.
# --------------------------------------------------------------------------

# Ruling a: an SPDX 2.3 idstring leaf, optional DocumentRef-<id>: and `+`.
IDSTRING = re.compile(r"(DocumentRef-[A-Za-z0-9.-]+:)?[A-Za-z0-9.-]+\+?")


class ReworkR2LeafCharsetTest(_Table):
    """Rulings a and b (review R1-B1): a leaf that is not an idstring makes
    the text unparseable; the fallback splits runs on any character outside
    [A-Za-z0-9.+:-], so an unknown id joined by punctuation fails closed."""

    def test_unknown_id_joined_by_punctuation(self):
        self.check([
            ("MIT/NOASSERTION", True, True, True), ('"NOASSERTION"', True, True, True),
            ("NOASSERTION,", True, True, True), ("MIT,NOASSERTION", True, True, True),
            ("NOASSERTION;MIT", True, True, True), ("MIT\x00NOASSERTION", True, True, True),
            (f"{HASH};", True, True, True), (f"MIT,{HASH}", True, True, True),
            ("MIT AND Apache-2.0,none", True, True, True), ("[NONE]", True, True, True),
        ])

    def test_hash_anywhere_in_unparseable_text(self):
        # Orchestrator U5 addition 3 ("holds a hash id"): found inside a run
        # too, not only as a whole run (`:` is an idstring character).
        self.check([(f"Public Domain OR see:{HASH}", True, True, True),
                    (f"MIT, X{HASH}", True, True, True)])

    def test_odd_leaves_are_unparsed(self):
        self.check([
            ("MIT/Apache-2.0", False, True, False), ("GPL-2.0-only;MIT", True, True, False),
            ("MIT_X11", False, True, False), ("MIT AND Zlib,", False, True, False),
            ("MIT WITH Classpath-exception-2.0;NOASSERTION", True, True, True),   # the exception slot too
            ("MIT WITH Classpath-exception-2.0,", False, True, False),
        ])

    def test_idstring_leaves_still_parse(self):
        self.check([
            ("GPL-2.0+", True, False, False), ("LGPL-2.1+ OR MIT", False, False, False),
            ("MIT", False, False, False), ("LicenseRef-scancode-public-domain", False, False, False),
            ("GPL-2.0-only WITH Classpath-exception-2.0", True, False, False),
            ("BSD-3-Clause AND (MIT OR Apache-2.0)", False, False, False),
        ])


class ReworkR2DocumentRefTest(_Table):
    """Ruling c: a DocumentRef-<id>: prefix is accepted on hash ids and on
    NONE/NOASSERTION; `DocumentRef-x:MIT` is an ordinary leaf."""

    def test_document_ref_prefix(self):
        self.check([
            (f"DocumentRef-spdx:{HASH}", True, False, True),
            (f"MIT AND DocumentRef-x:{HASH}", True, False, True),
            ("MIT AND DocumentRef-x:NOASSERTION", True, False, True),
            ("MIT OR DocumentRef-x:none", False, False, True),
            ("DocumentRef-x:MIT", False, False, False),
            ("DocumentRef-x:GPL-2.0-only", True, None, False),
            # the http listing reads through the prefix (beyond the brief; fail closed)
            ("DocumentRef-x:LicenseRef-https---example.org-x", False, True, False),
        ])

    def test_document_ref_prefix_in_unparseable_text(self):
        self.check([("see DocumentRef-x:NOASSERTION here", True, True, True),
                    (f"MIT,DocumentRef-spdx:{HASH}", True, True, True)])


class ReworkR2WithUrlTest(_Table):
    """Ruling d (review R1-N1): an http LicenseRef in the WITH exception slot
    is listed unparsed; it is not read as a licence."""

    def test_http_exception_id_listed(self):
        self.check([("MIT WITH LicenseRef-https---example.org-x", False, True, False),
                    ("GPL-2.0-only WITH LicenseRef-http---example.org-y", True, True, False),
                    ("MIT WITH LicenseRef-Example-exception", False, False, False)])


class ReworkR2RealRowsTest(unittest.TestCase):
    """The leaf rule changes no real row: every run syft wrote in the six U3
    fixtures is an idstring (review R1-B1: 0 of 7572), and the classification
    of the real rows is the round-1 one (snapshot with no `always`, taken on
    the round-1 checker, 2026-10-24)."""

    SNAPSHOT = {  # image: (rows, needs, unparsed, unidentified, unlicensed)
        "ke-app": (153, 102, 3, 18, 1), "ke-gateway": (71, 17, 0, 0, 0), "neo4j": (341, 164, 52, 9, 19),
        "phoenix": (277, 30, 4, 10, 25), "postgres": (149, 130, 6, 22, 3), "valkey": (24, 12, 0, 0, 1)}

    def test_every_real_run_is_an_idstring(self):
        runs, outside = 0, []
        for image in ss.U3_IMAGES:
            for line in (ss.U3_FIXTURES / f"{image}.pkgs.tsv").read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                for field in line.split("\t")[2].split("|"):
                    for run in re.findall(r"[^\s()]+", field):
                        runs += 1
                        if not IDSTRING.fullmatch(run):
                            outside.append(run)
        self.assertEqual(runs, 7572, "the U3 fixtures changed (review R1-B1 counted 7572 runs)")
        self.assertEqual(outside, [], "a real run is not an SPDX idstring")

    def test_real_rows_unchanged_by_the_leaf_rule(self):
        classify = fn("classify_document")
        for image, want in self.SNAPSHOT.items():
            with self.subTest(image=image):
                rows = classify(image, ss.spdx_doc(image, ss.u3_rows(image)), [])
                got = (len(rows),) + tuple(sum(bool(r[k]) for r in rows)
                                           for k in ("needs", "unparsed", "unidentified", "unlicensed"))
                self.assertEqual(got, want, f"{image}: the classification of the real rows moved")


class ReworkR2SourceTest(unittest.TestCase):
    """Ruling e (review R1-N2): the non-ASCII test characters are written as
    escapes, so this file is ASCII."""

    def test_classifier_tests_are_ascii(self):
        from pathlib import Path
        text = Path(__file__).read_text(encoding="utf-8")
        bad = [(n, ascii(line)[:80]) for n, line in enumerate(text.splitlines(), 1) if not line.isascii()]
        self.assertEqual(bad, [], "tests/test_sbom_classifier.py holds literal non-ASCII characters")


# --------------------------------------------------------------------------
# U5 rework round 3 (review R2-B1, R2-B2, security R2-L1; orchestrator
# rulings 1-5; design-notes "N8 amendment, U5", "Rework round 3"). Every
# rule fails closed; the real-row snapshot (ReworkR2RealRowsTest) holds.
# --------------------------------------------------------------------------

HASH65 = HASH + "0"


class ReworkR3DecoratedIdsTest(_Table):
    """Rulings 2 and 3 (R2-B1, R2-L1): the bare id, after the DocumentRef
    prefix and leading/trailing `.`, `-`, `+` are removed, is tested; a hash
    found anywhere in a leaf is unknown. Unparsed is pinned only where the
    text cannot parse."""

    def test_trimmed_unknown_leaves(self):
        self.check([
            ("NOASSERTION+", True, None, True), ("none+", True, None, True),
            ("DocumentRef-x:NONE+", True, None, True), ("NOASSERTION.", True, None, True),
            ("MIT AND -NONE", True, None, True), ("MIT WITH NOASSERTION+", True, None, True),
            ("MIT OR NOASSERTION+", False, None, True),
        ])

    def test_hash_anywhere_in_a_leaf(self):
        self.check([
            (f"{HASH}+", True, None, True), (f"MIT AND {HASH}+", True, None, True),
            (f"DocumentRef-x:{HASH}+", True, None, True), (f"MIT WITH {HASH}+", True, None, True),
            (f"{HASH}.x", True, None, True), (f"x{HASH}", True, None, True),
        ])

    def test_hash_search_in_unparseable_text_unchanged(self):
        # Ruling 4 "unchanged": the round-0 search over the whole unparseable
        # text (orchestrator U5 addition 3) still counts a 65-hex id there.
        self.check([(f"Public Domain {HASH65}", True, True, True)])

    def test_near_misses_stay_ordinary(self):
        # Ruling 5 (pinned near-misses) and ruling 4 (65 hex is not a hash).
        self.check([
            # U6 ruling 5 (segment rule) flips `see NONE.txt here` and
            # `MIT-NOASSERTION` to unknown; they moved to U6SegmentRuleTest.
            ("NOASSERTIONS apply", False, True, False), ("LicenseRef-NONE", False, False, False),
            (HASH65, False, False, False), (f"MIT AND {HASH65}", False, False, False),
            ("LicenseRef-" + "0123456789ABCDEF" * 4 + "+", False, False, False),
        ])


class ReworkR3RunSplitTest(_Table):
    """Ruling 1 (R2-B2): runs of unparseable text split on `+` and `:` too."""

    def test_joiners_split_runs(self):
        self.check([
            ("MIT:NOASSERTION", True, True, True), ("MIT+NOASSERTION", True, True, True),
            ("NOASSERTION+MIT", True, True, True), ("NOASSERTION:", True, True, True),
            ("DocumentRef-:NONE", True, True, True), ("Public Domain MIT:NOASSERTION", True, True, True),
            ("MIT OR (x:none)", True, True, True),
        ])


# --------------------------------------------------------------------------
# platform-sbom U6: `exempt` (N10; N8a items 1 and 3; orchestrator U6
# rulings 1, 4, 5). Tester, U6 RED, 2026-10-25.
# --------------------------------------------------------------------------

JNA_PURL = "pkg:maven/com.sun.jna/jna@5.15.0"
JAVASSIST_PURL = "pkg:maven/org.javassist/javassist@3.30.2-GA"


def u6_exempt(package: str, image: str = "ke-neo4j") -> dict[str, str]:
    return {"image": image, "package": package, "reason": "Apache-2.0 elected (test)", "reviewed": "security 2026-10-25"}


def u6_doc(purls: list[str], image: str = "ke-neo4j") -> dict[str, Any]:
    return ss.spdx_doc(image, [{"purl": p, "declared": "NOASSERTION", "concluded": "Apache-2.0 AND LGPL-2.1-only"}
                               for p in purls])


def u6_fn(name: str) -> Callable[..., Any]:
    got = getattr(load_sbom_check(), name, None)
    if not callable(got):
        raise AssertionError(f"scripts/sbom_check.py has no {name}() (U6 interface, orchestrator U6 ruling 1; "
                             "tests/test_sbom_classifier.py)")
    return got


def u6_classify(*args: Any) -> list[dict[str, Any]]:
    """classify_document with the U6 `exempt` argument, or a failure naming it."""
    try:
        return fn("classify_document")(*args)
    except TypeError as exc:
        raise AssertionError(f"classify_document has no `exempt` parameter (U6 ruling 1): {exc}") from None


def real_exempt() -> list[dict[str, Any]]:
    data = json.loads(POLICY.read_text(encoding="utf-8"))
    if not isinstance(data.get("exempt"), list):
        raise AssertionError("docker/source-policy.json has no `exempt` list (U6, N10)")
    return data["exempt"]


class U6ExemptMatchesTest(unittest.TestCase):
    """`exempt_matches(image, doc, exempt) -> (flagged SPDXIDs, problems)`:
    exact type, namespace, name and version; qualifiers ignored; no match in
    its image is a problem (a version bump voids the exemption)."""

    def test_exempt_matches_exact_versioned_purl(self):
        matches = u6_fn("exempt_matches")
        doc = u6_doc([JNA_PURL + "?type=jar", JAVASSIST_PURL, "pkg:maven/com.sun.jna/jna-platform@5.15.0",
                      "pkg:maven/net.java.dev.jna/jna@5.15.0", "pkg:generic/com.sun.jna/jna@5.15.0"])
        sid = {pkg_purl_of(p): p["SPDXID"] for p in doc["packages"][1:]}
        flagged, problems = matches("ke-neo4j", doc, [u6_exempt(JNA_PURL), u6_exempt(JAVASSIST_PURL)])
        self.assertEqual(sorted(flagged), sorted([sid[JNA_PURL + "?type=jar"], sid[JAVASSIST_PURL]]),
                         "only jna and javassist at those versions (qualifiers ignored)")
        self.assertEqual(problems, [])
        with self.subTest(case="an entry carrying qualifiers or a subpath is a problem and matches nothing (N10 am. U6)"):
            for bad in (JNA_PURL + "?classifier=x", JNA_PURL + "#sub"):
                flagged, problems = matches("ke-neo4j", doc, [u6_exempt(bad)])
                self.assertEqual(flagged, [], bad)
                self.assertTrue(problems, f"no problem for the entry {bad}")
        with self.subTest(case="literal compare: no case fold"):
            self.assertEqual(matches("ke-neo4j", doc, [u6_exempt("pkg:maven/com.sun.jna/JNA@5.15.0")])[0], [])
        with self.subTest(case="the root (DESCRIBES) is never flagged"):
            root = doc["relationships"][0]["relatedSpdxElement"]
            self.assertNotIn(root, matches("ke-neo4j", doc, [u6_exempt(JNA_PURL)])[0])
        with self.subTest(case="another image's entry does not apply, and is not this image's problem"):
            self.assertEqual(matches("ke-neo4j", doc, [u6_exempt(JNA_PURL, image="phoenix")]), ([], []))

    def test_exempt_void_on_version_bump(self):
        matches = u6_fn("exempt_matches")
        for case, purl in {"a bumped version": "pkg:maven/com.sun.jna/jna@5.16.0",
                           "a version prefix": "pkg:maven/com.sun.jna/jna@5.15",
                           "a version suffix": "pkg:maven/com.sun.jna/jna@5.15.0.1"}.items():
            with self.subTest(case=case):
                flagged, problems = matches("ke-neo4j", u6_doc([purl]), [u6_exempt(JNA_PURL)])
                self.assertEqual(flagged, [], f"{case}: the exemption still applies")
                self.assertTrue(problems and any("ke-neo4j" in m and "jna" in m for m in problems),
                                f"{case}: no problem names the image and the package: {problems}")
        with self.subTest(case="a versionless entry matches nothing"):
            flagged, problems = matches("ke-neo4j", u6_doc([JNA_PURL]), [u6_exempt("pkg:maven/com.sun.jna/jna")])
            self.assertEqual(flagged, [])
            self.assertTrue(problems)


def pkg_purl_of(pkg: dict[str, Any]) -> str:
    return pkg["externalRefs"][0]["referenceLocator"]


class U6ClassifyDocumentExemptTest(unittest.TestCase):
    """classify_document(image, doc, always, exempt=()): an exempt row gets
    exempt True and needs False, also when `always` matches it (both flags
    set; orchestrator correction to U6 ruling 1)."""

    def test_exempt_clears_needs_also_under_always(self):
        classify = u6_classify
        doc = u6_doc([JNA_PURL, JAVASSIST_PURL, "pkg:maven/javax.xml.bind/jaxb-api@2.2.12"])
        by = rows_by_purl(classify("ke-neo4j", doc, [], [u6_exempt(JNA_PURL)]))
        self.assertIs(by["pkg:maven/com.sun.jna/jna"].get("exempt"), True)
        self.assertFalse(by["pkg:maven/com.sun.jna/jna"]["needs"], "an exempt row needs no source")
        self.assertIs(by["pkg:maven/org.javassist/javassist"].get("exempt"), False)
        self.assertTrue(by["pkg:maven/org.javassist/javassist"]["needs"], "a row not exempt keeps its needs")
        with self.subTest(case="exempt and always both match: the reviewed exemption clears it"):
            # Orchestrator correction to U6 ruling 1: `always` overrides only
            # the classifier; a reviewed exemption at the exact versioned purl
            # still clears the package (PSC-22, N10's GCC fallback). U9 lists
            # it as "always, cleared by exemption".
            always = [{"image": "ke-neo4j", "match": "pkg:maven/com.sun.jna/jna", "why": "t"}]
            row = rows_by_purl(classify("ke-neo4j", doc, always, [u6_exempt(JNA_PURL)]))["pkg:maven/com.sun.jna/jna"]
            self.assertTrue(row["always"] is True and row["exempt"] is True and row["needs"] is False, row)
        with self.subTest(case="always alone still forces needs"):
            always = [{"image": "ke-neo4j", "match": "pkg:maven/org.javassist/javassist", "why": "t"}]
            mit = ss.spdx_doc("ke-neo4j", [{"purl": JAVASSIST_PURL, "declared": "MIT"}])  # no source by licence
            row = rows_by_purl(classify("ke-neo4j", mit, always, [u6_exempt(JNA_PURL)]))["pkg:maven/org.javassist/javassist"]
            self.assertTrue(row["always"] is True and row["exempt"] is False and row["needs"] is True, row)
        with self.subTest(case="exempt defaults to none: every row carries exempt False"):
            rows = classify("ke-neo4j", doc, [])
            self.assertTrue(all(r.get("exempt") is False for r in rows), rows)
        with self.subTest(case="a bumped exempt entry clears nothing"):
            row = rows_by_purl(classify("ke-neo4j", u6_doc(["pkg:maven/com.sun.jna/jna@5.16.0"]), [],
                                        [u6_exempt(JNA_PURL)]))["pkg:maven/com.sun.jna/jna"]
            self.assertTrue(row["needs"] and row["exempt"] is False, row)

    def test_real_rows_with_the_committed_exempt(self):
        # Ruling 4, N10 am. U6 item 4: exactly jna and javassist (ke-neo4j)
        # become exempt with needs False; every other row of every image and
        # every other key is as without `exempt` (the U5 result).
        classify = u6_classify
        always, exempt = real_always(), real_exempt()
        changed = {}
        for fixture in ss.U3_IMAGES:
            image = "ke-neo4j" if fixture == "neo4j" else fixture
            doc = ss.spdx_doc(image, ss.u3_rows(fixture))
            before = classify(image, doc, always)
            after = classify(image, doc, always, exempt)
            self.assertEqual(len(before), len(after))
            for b, a in zip(before, after):
                self.assertEqual(a["spdxid"], b["spdxid"])
                diff = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
                if diff:
                    changed[(image, str(a["purl"]).split("?", 1)[0])] = diff
                self.assertFalse(a["always"] and a["exempt"], f"{image}: {a['purl']} is flagged by always and exempt")
        self.assertEqual(changed, {("ke-neo4j", JNA_PURL): {"exempt", "needs"},
                                   ("ke-neo4j", JAVASSIST_PURL): {"exempt", "needs"}})
        doc = ss.spdx_doc("ke-neo4j", ss.u3_rows("neo4j"))
        after = classify("ke-neo4j", doc, always, exempt)
        for r in after:
            if str(r["purl"]).split("?", 1)[0] in (JNA_PURL, JAVASSIST_PURL):
                self.assertTrue(r["exempt"] is True and r["needs"] is False and r["always"] is False, r)
        javassist = [r for r in after if str(r["purl"]).startswith(JAVASSIST_PURL)]
        self.assertTrue(javassist and javassist[0]["unparsed"], "javassist stays listed unparsed (N8a 3)")
        self.assertEqual(u6_fn("exempt_matches")("ke-neo4j", doc, exempt)[1], [],
                         "a committed exemption matches no package in the real list")


class U6SegmentRuleTest(_Table):
    """Ruling 5 (review I-r3-1, security I-9): outside a LicenseRef- id, a
    `.`- or `-`-separated segment equal to NONE/NOASSERTION (any case) is
    unknown."""

    def test_segment_rule(self):
        self.check([
            ("NOASSERTION.NONE", True, False, True), ("NOASSERTION-2.0", True, False, True),
            ("MIT-NOASSERTION", True, False, True), ("mit-none", True, False, True),
            ("DocumentRef-x:MIT-NONE", True, False, True), ("MIT OR Apache-NONE", False, False, True),
            ("LicenseRef-NONE", False, False, False), ("LicenseRef-NOASSERTION", False, False, False),
            ("DocumentRef-x:LicenseRef-NONE", False, False, False), ("licenseref-none", False, False, False),
            ("NOASSERTIONS-2.0", False, False, False), ("MIT-NONEX", False, False, False),
            # N10 am. U6 item 5 rows
            ("MIT AND NONE.NONE", True, False, True), ("none-mit", True, False, True),
            ("DocumentRef-x:NONE-1", True, False, True), ("NOASSERTIONS", False, False, False),
            ("NONEX-1", False, False, False), ("DocumentRef-NONE:MIT", False, False, False),
            ("MIT WITH NONE-exception", True, False, True),
        ])

    def test_segment_rule_in_runs(self):
        # The same rule on runs of unparseable text (it lives in _unknown_id):
        # `see NONE.txt here` now needs source (was a pinned near-miss).
        self.check([("see NONE.txt here", True, True, True), ("Public Domain MIT-NOASSERTION", True, True, True),
                    ("NOASSERTIONS apply", False, True, False)])


if __name__ == "__main__":
    unittest.main()
