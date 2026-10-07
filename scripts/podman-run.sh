#!/usr/bin/env bash
# Run the budgeter container with Podman. All data (logins and every user's
# books) persists on a named volume across restarts/rebuilds.
#
# Usage:
#   scripts/podman-run.sh
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-com.valsr.budgeter}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
CONTAINER_NAME="${CONTAINER_NAME:-budgeter}"
HOST_PORT="${HOST_PORT:-8000}"
# The port the app listens on inside the container: 8000 unless changed in
# Settings → Server. Keep the two in step, or the app becomes unreachable.
CONTAINER_PORT="${CONTAINER_PORT:-8000}"
# Optional: a host directory with the SSL certificate and key, mounted
# read-only at /certs (then use /certs/<file> in Settings → Server).
CERTS_DIR="${CERTS_DIR:-}"
VOLUME_NAME="${VOLUME_NAME:-budgeter-data}"

podman volume create "${VOLUME_NAME}" >/dev/null 2>&1 || true

CERTS_MOUNT=()
if [ -n "${CERTS_DIR}" ]; then
  CERTS_MOUNT=(--volume "${CERTS_DIR}:/certs:ro")
fi

echo "Starting ${CONTAINER_NAME} from ${IMAGE_NAME}:${IMAGE_TAG} on port ${HOST_PORT}"
podman run \
  --rm \
  --name "${CONTAINER_NAME}" \
  --publish "${HOST_PORT}:${CONTAINER_PORT}" \
  --volume "${VOLUME_NAME}:/data" \
  ${CERTS_MOUNT[@]+"${CERTS_MOUNT[@]}"} \
  "${IMAGE_NAME}:${IMAGE_TAG}"
