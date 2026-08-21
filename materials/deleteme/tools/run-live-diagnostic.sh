#!/bin/sh
# Run the Linux-gated static + live diagnostic for materials/deleteme.
#
# Landlock/seccomp cannot run on macOS, and the sandbox cannot traverse the
# macOS bind mount through virtiofs. Copy the checkout onto the container's
# native filesystem before installing and verifying.
#
# Usage from repository root:
#   docker run --rm -v "$PWD":/repo:ro \
#     -v "$PWD/materials/deleteme/tools":/probe:ro \
#     mcr.microsoft.com/playwright/python:v1.61.0-noble \
#     sh /probe/run-live-diagnostic.sh
set -e
mkdir -p /work
cd /repo
tar cf - --exclude=.git --exclude=node_modules \
  --exclude=materials/aspca-pet-insurance --exclude=materials/jefit \
  --exclude=materials/ipvanish --exclude=deploy/eight-site-clones . \
  | (cd /work && tar xf -)
cd /work
echo "--- installing repo + clone deps ---"
pip install --break-system-packages -q . 2>&1 | tail -2
pip install --break-system-packages -q \
  -r materials/deleteme/clone/requirements.txt 2>&1 | tail -2
echo "--- verify (static + live) on native fs ---"
set +e
websitebench-offline-clone verify --site materials/deleteme \
  > /tmp/deleteme-diagnostic.json 2>/tmp/deleteme-diagnostic.err
code=$?
set -e
echo "EXIT=$code"
tail -4 /tmp/deleteme-diagnostic.err
python /probe/summarize-diagnostic-report.py /tmp/deleteme-diagnostic.json
exit "$code"
