# --- scratch TARGET for SmokePsycopgTest (platform-sbom U0 RED); not product code ---
# PSC-25: psycopg-c on Debian's libpq, in the live api.
pq_out="$(compose exec -T api python -I -c 'import importlib.util as u, psycopg
p = psycopg.pq
s = u.find_spec("psycopg_c.pq") if u.find_spec("psycopg_c") else None
print(p.__impl__, p.version(), p.__build_version__, s.origin if s else "-")')" || {
  echo "smoke: FAIL (psycopg: the check in api failed)" >&2
  exit 1
}
read -r pq_impl pq_version pq_build pq_ext <<< "$pq_out"
if [ "$pq_impl" != c ]; then
  echo "smoke: FAIL (psycopg: api uses the '$pq_impl' implementation, want c)" >&2
  exit 1
fi
# shellcheck disable=SC2016  # dpkg-query expands ${Version}
deb="$(compose exec -T api dpkg-query -W -f='${Version}' libpq5)" || {
  echo "smoke: FAIL (libpq: dpkg-query libpq5 failed in api)" >&2
  exit 1
}
deb_major="${deb%%.*}"
deb_minor="$(printf '%s' "$deb" | sed -E 's/^[0-9]+\.([0-9]+).*/\1/')"
want=$((10#$deb_major * 10000 + 10#$deb_minor))
if [ "$pq_version" != "$want" ] || [ "$pq_build" != "$want" ]; then
  echo "smoke: FAIL (psycopg: libpq version() $pq_version, __build_version__ $pq_build; libpq5 $deb is $want)" >&2
  exit 1
fi
ldd_out="$(compose exec -T api ldd "$pq_ext")" || {
  echo "smoke: FAIL (libpq: ldd $pq_ext failed in api)" >&2
  exit 1
}
libpq="$(printf '%s\n' "$ldd_out" | sed -n 's/^[[:space:]]*libpq\.so\.5 => \([^ ]*\).*/\1/p')"
if ! [[ "$libpq" =~ ^(/usr)?/lib/(x86_64|aarch64)-linux-gnu/libpq\.so\.5 ]] || [[ "$ldd_out" == *psycopg_binary* ]]; then
  echo "smoke: FAIL (libpq: the psycopg_c extension loads '${libpq:-nothing}', not Debian's libpq5)" >&2
  exit 1
fi
echo "smoke: psycopg c on Debian libpq5 $deb ($libpq)"
