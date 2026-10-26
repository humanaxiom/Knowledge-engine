# platform-sbom U1 round 3: TARGET smoke block (tester, 2026-10-23), from
# design-notes N10a "Smoke `no pip`" (round 3, B6/I-6) in smoke.sh's FAIL
# convention. Not a script: the developer replaces scripts/smoke.sh's no-pip
# step (from its `# PSC-14 (N10a, human 2026-10-23)` comment through
# `echo "smoke: no pip in api"`) with the lines below the marker. It sits right
# after the psycopg step's last line
#   echo "smoke: psycopg c on Debian libpq5 $deb ($libpq -> $libpq_real)"
# and before the `# ci/offline (PS-3.3, ...` comment. The whole captured output
# is compared with `-`: no `read`, no default. Empty output fails (orchestrator
# ruling 2026-10-23), and so does `-` followed by a second line (I-6). `$(...)`
# strips trailing newlines only. It passes tests/test_ke_app_no_pip.py
# SmokeNoPipTest and every other smoke test when spliced there
# (u1_controls.py --reach; recorded in r3-red-mutants.txt).
# ---- insert below this line ----
# PSC-14 (N10a, human 2026-10-23): ke-app ships no pip. The base interpreter,
# since the venv's sys.path omits the system site-packages. The whole container
# output is compared only as a string with `-` (M-1, I-6): never evaluated.
echo "== smoke: no pip =="
pip_out="$(compose exec -T api /usr/local/bin/python3 -I -c 'import importlib.util as u, os, re
h = sorted(os.path.join(d, n) for r in ("/usr", "/opt") for d, ds, fs in os.walk(r)
           for n in ds + fs if re.fullmatch(r"pip(3(\.[0-9]+)?)?|pip-.+\.(dist-info|whl)", n))
if u.find_spec("pip") and not h:
    h = ["pip (importable)"]
print(",".join(h).replace(" ", "_") or "-")')" || {
  echo "smoke: FAIL (no pip: the check in api failed)" >&2
  exit 1
}
[ "$pip_out" = - ] || {
  echo "smoke: FAIL (no pip: the check in api printed '$pip_out', want '-' (pip in api, or no answer))" >&2
  exit 1
}
echo "smoke: no pip in api"
