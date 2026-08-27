# Reference sidecar for site `deleteme`.
#
# The reference is the frozen offline clone itself, not a reimplementation of
# it: this image runs `materials/deleteme/clone/app.py` unchanged, against the
# same mirrored assets and the same pinned runtime the deployment descriptor
# pins. Anything else would let the reference and the candidate contract drift
# apart while both still looked green.
#
# Build context is the repository root, so the clone tree is reachable:
#
#   docker build -f harbor/sites/deleteme/reference/Dockerfile -t wb-deleteme-reference .
#
# `reference/` deliberately holds no copy of the clone. Duplicating the mirrored
# assets into a second tree would create two sources of truth, and the site
# contract forbids linking them (visibility roots may contain no symlinks).
FROM python:3.12-slim

WORKDIR /srv/reference

# Pinned to match deploy/generic-offline-clone/deployment.deleteme.v2.json.
RUN pip install --no-cache-dir \
      fastapi==0.141.1 \
      python-multipart==0.0.32 \
      uvicorn==0.52.3

COPY materials/deleteme/clone/ /srv/reference/

# The clone's ABI: HOST/PORT/DATA_DIR/SEED/TZ, foreground, clean SIGTERM.
ENV HOST=0.0.0.0 \
    PORT=8080 \
    DATA_DIR=/srv/reference/data \
    SEED=1 \
    TZ=Etc/UTC

HEALTHCHECK --interval=2s --timeout=3s --retries=30 CMD python -c \
  "import urllib.request,json,sys; \
   r=json.load(urllib.request.urlopen('http://127.0.0.1:8080/__websitebench/health', timeout=2)); \
   sys.exit(0 if r=={'status':'ok'} else 1)"

CMD ["python", "app.py"]
