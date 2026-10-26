# U0 lock regeneration: base image note (developer, L-2)
`python:3.12-slim-bookworm` (unpinned tag, id 6a0e06f5ba0b, created 2026-10-21) was pulled once, during the U0 `uv.lock` regeneration, to run `uv lock` in a throwaway container with network. Nothing from it is in the repo or in the images: every `FROM` is digest-pinned to `sha256:34386ef0cb08...` (a different image, kept). Removed 2026-10-23:

```
$ docker ps -a --filter ancestor=python:3.12-slim-bookworm   # no container uses it (empty)
$ docker image rm python:3.12-slim-bookworm
Untagged: python:3.12-slim-bookworm
Deleted: sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70
$ docker image inspect sha256:34386ef0cb08... (pinned) -f {{.Id}}
sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
```
