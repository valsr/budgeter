#!/usr/bin/env bash
# Swap the running budgeter container over to whatever image is currently
# tagged locally (built with podman-build.sh, or otherwise made available
# on this host), without touching the data volume.
#
# This is a redeploy, not a build -- run podman-build.sh (or otherwise get
# a new image tagged locally) first, then this script.
#
# Usage:
#   scripts/podman-update.sh
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-com.valsr.budgeter}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
CONTAINER_NAME="${CONTAINER_NAME:-budgeter}"

if podman container exists "${CONTAINER_NAME}"; then
  echo "Removing existing ${CONTAINER_NAME} container (data volume is untouched)..."
  podman rm -f "${CONTAINER_NAME}" >/dev/null
fi

echo "Starting ${CONTAINER_NAME} from ${IMAGE_NAME}:${IMAGE_TAG}..."
exec "$(dirname "$0")/podman-run.sh"
