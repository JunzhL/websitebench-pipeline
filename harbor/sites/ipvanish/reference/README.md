# Reference sidecar — site `ipvanish`

The reference **is** the frozen offline clone at `materials/ipvanish/clone/`.
Both entrypoints here run that tree directly, so `reference/` holds no second
copy of the served documents or the mirrored assets:

- `Dockerfile` — build from the repository root; copies the clone into the image
  and runs `python app.py` with the runtime the deployment descriptor pins
  (FastAPI 0.141.1, Uvicorn 0.52.3, python-multipart 0.0.32).
- `run.sh` — runs the same clone in place, for a local sidecar without Docker.

Why no copy: duplicating ~60 MB of mirrored assets would create two sources of
truth that can drift while both still look green, and the site contract forbids
resolving that with a link (visibility roots may contain no symlinks, junctions,
reparse points or hard links). Keeping one tree makes the acceptance check
("`reference/` content is same-origin with `<site>/clone/`") true by
construction rather than by periodic syncing.

Health and ABI are the clone's own, which is what the contract declares:
`/__websitebench/health` returns exactly `{"status":"ok"}`, `/healthz` returns
`{"ok":true,"site_id":"ipvanish"}`, the process stays in the foreground and
exits cleanly on SIGTERM, and it reads only `HOST`, `PORT`, `DATA_DIR`, `SEED`
and `TZ`.
