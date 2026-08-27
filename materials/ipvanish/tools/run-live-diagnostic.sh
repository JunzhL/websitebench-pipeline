#!/bin/sh
# Run the Linux-gated live diagnostic section for materials/ipvanish.
#
# The live section needs Landlock + seccomp (see
# src/websitebench/runtime_isolation.py), so it cannot run on a macOS host: the
# section reports `candidate sandbox requires Linux` and stops. It also cannot
# run over a macOS bind mount, because Landlock denies directory listing through
# virtiofs and the candidate's own `app` module then becomes unimportable. This
# script therefore copies the tree onto the container's native filesystem before
# installing and verifying.
#
# Usage (from the repository root, with Docker running):
#   docker run --rm -v "$PWD":/repo:ro -v "$PWD/materials/ipvanish/tools":/probe:ro \
#     mcr.microsoft.com/playwright/python:v1.61.0-noble sh /probe/run-live-diagnostic.sh
#
# The image tag tracks the playwright pin in pyproject.toml.
set -e
mkdir -p /work
cd /repo
tar cf - --exclude=.git --exclude=node_modules \
  --exclude=materials/aspca-pet-insurance --exclude=materials/jefit \
  --exclude=deploy/eight-site-clones . | (cd /work && tar xf -)
cd /work
echo "--- installing repo + clone deps ---"
pip install --break-system-packages -q . 2>&1 | tail -2
pip install --break-system-packages -q -r materials/ipvanish/clone/requirements.txt 2>&1 | tail -2
which websitebench-offline-clone || echo "CLI MISSING"
echo "--- verify (static + live) on native fs ---"
set +e
websitebench-offline-clone verify --site materials/ipvanish > /tmp/r.json 2>/tmp/e.txt
echo "EXIT=$?"
tail -4 /tmp/e.txt
python /probe/summarize-diagnostic-report.py /tmp/r.json
