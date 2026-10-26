# PSC-25 (N0): the api runs psycopg-c on Debian's libpq5, not a vendored libpq.
# bookworm is merged-usr: ldd may print /lib/<triplet>/ or /usr/lib/<triplet>/.
# U0 rework round 1 (tester scratch target, not production): review B1 (no
# psycopg_binary* in the venv; dpkg libpq5 owns the loaded libpq), security
# M-1 and review N3 (the libpq5 version is validated before any arithmetic).
echo "== smoke: psycopg =="
pq_out="$(compose exec -T api python -I -c 'import importlib.util as u, os, sys, psycopg
p = psycopg.pq
s = u.find_spec("psycopg_c.pq") if u.find_spec("psycopg_c") else None
b = sorted(os.path.relpath(os.path.join(d, n), sys.prefix) for d, ds, fs in os.walk(sys.prefix)
           for n in ds + fs if n.startswith("psycopg_binary"))
if u.find_spec("psycopg_binary") and not b:
    b = ["psycopg_binary (importable)"]
print(p.__impl__, p.version(), p.__build_version__, s.origin if s else "-", ",".join(b).replace(" ", "_") or "-")')" || {
  echo "smoke: FAIL (psycopg: the check in api failed)" >&2
  exit 1
}
read -r pq_impl pq_version pq_build pq_ext pq_bin <<< "$pq_out"
if [ "$pq_impl" != c ]; then
  echo "smoke: FAIL (psycopg: api uses the '$pq_impl' implementation, want c)" >&2
  exit 1
fi
if [ "${pq_bin:--}" != - ]; then
  echo "smoke: FAIL (psycopg: psycopg_binary is installed in api beside psycopg-c: $pq_bin)" >&2
  exit 1
fi
# shellcheck disable=SC2016  # dpkg-query expands ${Version}
deb="$(compose exec -T api dpkg-query -W -f='${Version}' libpq5)" || {
  echo "smoke: FAIL (libpq: dpkg-query libpq5 failed in api)" >&2
  exit 1
}
# M-1: container output never reaches $(( )) unvalidated.
if ! [[ "$deb" =~ ^([0-9]+)\.([0-9]+)-[0-9A-Za-z.+~]+$ ]]; then
  echo "smoke: FAIL (libpq: libpq5 version in api is '$deb', not <major>.<minor>-<revision>)" >&2
  exit 1
fi
want=$((10#${BASH_REMATCH[1]} * 10000 + 10#${BASH_REMATCH[2]}))
if [ "$pq_version" != "$want" ] || [ "$pq_build" != "$want" ]; then
  echo "smoke: FAIL (psycopg: libpq version() $pq_version, __build_version__ $pq_build; libpq5 $deb is $want)" >&2
  exit 1
fi
ldd_out="$(compose exec -T api ldd "$pq_ext")" || {
  echo "smoke: FAIL (libpq: ldd $pq_ext failed in api)" >&2
  exit 1
}
libpq="$(printf '%s\n' "$ldd_out" | sed -n 's/^[[:space:]]*libpq\.so\.5 => \([^ ]*\).*/\1/p')"
if ! [[ "$libpq" =~ ^(/usr)?/lib/(x86_64|aarch64)-linux-gnu/libpq\.so\.5(\.[0-9]+)*$ ]] || [[ "$ldd_out" == *psycopg_binary* ]]; then
  echo "smoke: FAIL (libpq: the psycopg_c extension loads '${libpq:-nothing}', not Debian's libpq5)" >&2
  exit 1
fi
libpq_real="$(compose exec -T api realpath -e "$libpq")" || {
  echo "smoke: FAIL (libpq: realpath $libpq failed in api)" >&2
  exit 1
}
libpq_owner="$(compose exec -T api dpkg-query -S "$libpq_real")" || {
  echo "smoke: FAIL (libpq: dpkg owns no file $libpq_real in api, so it is not Debian's libpq5)" >&2
  exit 1
}
if ! [[ "$libpq_owner" =~ ^libpq5(:[a-z0-9]+)?:\ (.+)$ ]] || [ "${BASH_REMATCH[2]}" != "$libpq_real" ]; then
  echo "smoke: FAIL (libpq: $libpq_real belongs to '${libpq_owner%%: *}', not libpq5)" >&2
  exit 1
fi
echo "smoke: psycopg c on Debian libpq5 $deb ($libpq -> $libpq_real)"
