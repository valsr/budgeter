#!/usr/bin/env bash
# Build the budgeter container image with Podman.
#
# Usage:
#   scripts/podman-build.sh                    # default dev API key
#   API_KEY=my-secret scripts/podman-build.sh   # custom key, baked into the
#                                                # frontend bundle at build time
#                                                # (must match BUDGETER_API_KEY
#                                                # passed to podman-run.sh)
set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE_NAME="${IMAGE_NAME:-budgeter}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
API_KEY="${API_KEY:-dev-local-api-key}"

echo "Building ${IMAGE_NAME}:${IMAGE_TAG} (frontend API key: ${API_KEY})"
podman build \
  --file Containerfile \
  --build-arg "API_KEY=${API_KEY}" \
  --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
  .

echo "Built ${IMAGE_NAME}:${IMAGE_TAG}"
