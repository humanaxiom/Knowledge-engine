# platform-sbom U1 round 2: TARGET smoke block (tester, 2026-10-23), from
# design-notes N10a "Smoke `no pip`" in smoke.sh's FAIL convention. Not a
# script: the developer inserts the lines below the marker into
# scripts/smoke.sh, right after the psycopg step's last line
#   echo "smoke: psycopg c on Debian libpq5 $deb ($libpq -> $libpq_real)"
# and before the `# ci/offline (PS-3.3, ...` comment. It passes
# tests/test_ke_app_no_pip.py SmokeNoPipTest and every other smoke test when
# spliced there (u1_controls.py --reach; record in r2-red-mutants.txt).
# Orchestrator ruling 2026-10-23: empty output FAILS (fail closed, as M-1), so
# the token is compared to `-` exactly, with no `${pip_hits:--}` default
# (supersedes N10a's spelling).
# ---- insert below this line ----
# PSC-14 (N10a, human 2026-10-23): ke-app ships no pip. The base interpreter,
# since the venv's sys.path omits the system site-packages. Container output
# is one token compared only as a string (M-1): never evaluated.
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
read -r pip_hits pip_rest <<< "$pip_out"
if [ "$pip_hits" != - ] || [ -n "$pip_rest" ]; then
  echo "smoke: FAIL (no pip: the check in api printed '$pip_hits${pip_rest:+ $pip_rest}', want '-' (pip in api, or no answer))" >&2
  exit 1
fi
echo "smoke: no pip in api"
