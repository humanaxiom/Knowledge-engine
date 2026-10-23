# platform-sbom U2 (PSC-20; design-notes "N1 amendment, U2" *Interim pull*):
# bundle.sh never pulls and refuses without the SBOM generator, so this check
# pulls it first, through its own compose file (the one place it is pinned).
# U8 replaces these lines with scripts/bundle_fetch.sh. The ${VAR:?} mounts get
# dummy values (pull reads no bind source); -f overrides COMPOSE_FILE.
echo "offline: pulling the SBOM generator (docker-compose.sbom.yml, service sbom)"
KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent \
  docker compose --env-file .env.example -f docker-compose.sbom.yml pull sbom \
  || die "pulling the SBOM generator failed (docker-compose.sbom.yml, service sbom); no retry"

