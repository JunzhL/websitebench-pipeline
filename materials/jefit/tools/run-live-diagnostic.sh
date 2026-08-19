#!/bin/sh
# Run the Linux-gated live diagnostic section for materials/jefit.
#
# The live section requires Landlock + seccomp (see
# src/websitebench/runtime_isolation.py), so it cannot run on a macOS host.
# It also cannot run over a macOS bind mount: Landlock denies directory listing
# through virtiofs, which makes the candidate's own `app` module unimportable.
# This script therefore copies the tree onto the container's native filesystem
# before installing and verifying.
#
# Usage (from the repository root, with Docker running):
#   docker run --rm -v "$PWD":/repo:ro -v "$PWD/materials/jefit/tools":/probe:ro \
#     mcr.microsoft.com/playwright/python:v1.61.0-noble sh /probe/run-live-diagnostic.sh
#
# The image tag tracks the playwright pin in pyproject.toml.
set -e
mkdir -p /work
cd /repo
tar cf - --exclude=.git --exclude=materials/aspca-pet-insurance --exclude=deploy/eight-site-clones --exclude=node_modules . | (cd /work && tar xf -)
cd /work
echo "--- installing repo + clone deps ---"
pip install --break-system-packages -q . 2>&1 | tail -2
pip install --break-system-packages -q -r materials/jefit/clone/requirements.txt 2>&1 | tail -2
which websitebench-offline-clone || echo "CLI MISSING"
echo "--- verify (static + live) on native fs ---"
set +e
websitebench-offline-clone verify --site materials/jefit > /tmp/r.json 2>/tmp/e.txt
echo "EXIT=$?"
tail -4 /tmp/e.txt
python /probe/summarize-diagnostic-report.py /tmp/r.json
