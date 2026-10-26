import importlib.util, sys
spec = importlib.util.spec_from_file_location("sc", r"c:\repos\Knowledge-engine\scripts\sbom_check.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
H = "LicenseRef-" + "0123456789abcdef"*4
for e in ["Public Domain AND NOASSERTION", "MIT NOASSERTION", "(NOASSERTION) WITH x", "MIT WITH GPL-2.0-only",
          "MIT w\u0131th GPL-2.0-only", "  ", "MIT AND (NOASSERTION", "NOASSERTION NONE",
          "GPL-2.0-only WITH x OR MIT", "licenseref-"+"0"*64, "MIT OR LicenseRef-GPL-2.0-only"]:
    print(ascii(e), m.needs_source(e))
def pkg(d=None,c=None,files=None):
    p={"SPDXID":"SPDXRef-x","name":"x"}
    if d is not None: p["licenseDeclared"]=d
    if c is not None: p["licenseConcluded"]=c
    if files is not None: p["licenseInfoFromFiles"]=files
    return p
for p in [pkg("Public Domain","MIT AND NOASSERTION"), pkg("  "), pkg(files=["Public Domain","MIT AND NONE"])]:
    r=m.classify_package(p); j=m.needs_source(m.licence_input(p)) if m.licence_input(p) else None
    print(p, {k:r[k] for k in ("needs","unparsed","unidentified","expression")}, "joined:", j)
# which non-ascii chars upper into ASCII letters of AND/OR/WITH
print(ascii([ (hex(i), chr(i), chr(i).upper()) for i in range(128, 0x110000) if chr(i).upper() and all(ch in "ANDORWITH" for ch in chr(i).upper()) and chr(i).upper().isascii()]))
