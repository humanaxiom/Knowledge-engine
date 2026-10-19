## 2026-10-19 — architect: §2.2 L-5 correction (review B2, security rulings)
- Corrected: `coverage erase` removes `/tmp/.coverage.*` only with `parallel = true` (coverage 7.16), which is now set. The per-container `/tmp` tmpfs is the second guarantee. A real-erase fast test is named.
- Added: `user: "10001:10001"` and image chown `10001:10001` (L-1); `cap_drop: [ALL]` and `no-new-privileges:true` on `gates` and `gates-it` (L-2).
- Added: the mask overlay holds only the `/work/.env` read-only bind, and a test pins it (B1). Fast mode always exports COMPOSE_FILE and COMPOSE_PATH_SEPARATOR, so a caller's COMPOSE_FILE and an override file are ignored (M-1, N7).
- Only docs/architecture.md §2.2 (L-5 block) was edited. Verify was not run, per the orchestrator; the developer's full run covers it.
