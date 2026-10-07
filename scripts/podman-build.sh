#!/usr/bin/env bash
# Build the budgeter container image with Podman.
#
# Usage:
#   scripts/podman-build.sh
set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE_NAME="${IMAGE_NAME:-com.valsr.budgeter}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Stamp the image with the commit it is built from (see backend/app/version.py).
# GitHub Actions provides GITHUB_SHA; anywhere else, ask git. A tree with
# uncommitted changes is still stamped with HEAD -- commit first for an
# image whose version says exactly what is in it.
GIT_SHA="${GITHUB_SHA:-$(git rev-parse HEAD 2>/dev/null || echo unknown)}"
GIT_COMMIT_DATE="$(git log -1 --format=%cI 2>/dev/null || echo unknown)"
BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "Building ${IMAGE_NAME}:${IMAGE_TAG} from ${GIT_SHA}"
podman build \
  --file Containerfile \
  --build-arg "GIT_SHA=${GIT_SHA}" \
  --build-arg "GIT_COMMIT_DATE=${GIT_COMMIT_DATE}" \
  --build-arg "BUILD_DATE=${BUILD_DATE}" \
  --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
  .

echo "Built ${IMAGE_NAME}:${IMAGE_TAG}"
