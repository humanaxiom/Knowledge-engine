import importlib.util
spec = importlib.util.spec_from_file_location("sc", r"c:\repos\Knowledge-engine\scripts\sbom_check.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
H = "LicenseRef-" + "0123456789abcdef"*4
rows = ["MIT/NOASSERTION", '"NOASSERTION"', "NOASSERTION,", "MIT,NOASSERTION", "NOASSERTION;MIT",
        f"{H};", f"MIT,{H}", f"DocumentRef-spdx:{H}", f"MIT AND DocumentRef-x:{H}", "MIT\x00NOASSERTION",
        f"MIT WITH {H}x", "MIT WITH LicenseRef-https---example.org-x", "MIT WITH LicenseRef-https---gnu.org-gpl",
        "MIT WITH none-exception", "NONE-2.0", "MIT AND GNU-General-Public-License", "general public license",
        "GENERAL PUBLIC LICENSE", "MIT AND (Apache-2.0 WITH GPL-3.0-only) OR Zlib", "a" * 10]
for e in rows:
    print(ascii(e), m.needs_source(e))
print("deep with", m.needs_source("(" * 400 + "MIT WITH GPL-2.0-only" + ")" * 400))
