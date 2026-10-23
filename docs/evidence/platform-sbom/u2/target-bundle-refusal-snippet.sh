# --- the SBOM generator (PSC-20, ADR-KE-016 point 1, design-notes N1) ------
# Its reference is read from its own compose file (the one place it is
# pinned) and the image must be on this daemon, or the bundle is refused here,
# before anything is written. This script never pulls it. Compose refuses to
# load the file while its ${VAR:?} mounts are unset, even for `config`, so
# they get dummy values here (N1 amendment, U2); the run that uses them is
# U3's. --env-file .env.example keeps the repo-root .env out of this file.
sbom_ref="$(KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent \
  docker compose --env-file .env.example -f docker-compose.sbom.yml config --images sbom)" \
  || die "docker compose config --images sbom failed for docker-compose.sbom.yml"
[ -n "$sbom_ref" ] || die "docker-compose.sbom.yml names no image for the sbom service"
[[ "$sbom_ref" != *$'\n'* ]] || die "docker-compose.sbom.yml names more than one image for the sbom service"
[[ "$sbom_ref" =~ $ref_re && "$sbom_ref" == *"@sha256:"* ]] \
  || die "the SBOM generator reference has no digest pin or fails its pattern: $(printf '%q' "$sbom_ref")"
docker image inspect --format '{{.Id}}' "$sbom_ref" > /dev/null 2>&1 \
  || die "the SBOM generator image is not present ($sbom_ref); pull it first with: docker pull $sbom_ref; this script never pulls"

