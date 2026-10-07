#!/usr/bin/env bash
# Run the budgeter container with Podman. All data (logins and every user's
# books) lives in the container's /data, which persists across
# restarts/rebuilds on either:
#   - a named Podman volume (the default, VOLUME_NAME), or
#   - a host directory of your choosing (DATA_DIR) -- e.g. a disk that your
#     backups already cover.
#
# Usage:
#   scripts/podman-run.sh
#   DATA_DIR=/mnt/backed-up/budgeter scripts/podman-run.sh
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
# A host directory to keep the data in, instead of the named volume.
DATA_DIR="${DATA_DIR:-}"

if [ -n "${DATA_DIR}" ]; then
  mkdir -p "${DATA_DIR}"
  # The app runs as uid 1000 inside the container. Mapping that uid onto the
  # user running this script makes the files in DATA_DIR that user's own on
  # the host -- writable by the app, and readable by ordinary backup tools.
  # Without it a rootless container can't write to a host directory at all.
  DATA_MOUNT=(--userns "keep-id:uid=1000,gid=1000" --volume "$(cd "${DATA_DIR}" && pwd):/data")
  echo "Data directory: ${DATA_DIR}"
else
  podman volume create "${VOLUME_NAME}" >/dev/null 2>&1 || true
  DATA_MOUNT=(--volume "${VOLUME_NAME}:/data")
  echo "Data volume: ${VOLUME_NAME}"
fi

CERTS_MOUNT=()
if [ -n "${CERTS_DIR}" ]; then
  CERTS_MOUNT=(--volume "${CERTS_DIR}:/certs:ro")
fi

echo "Starting ${CONTAINER_NAME} from ${IMAGE_NAME}:${IMAGE_TAG} on port ${HOST_PORT}"
podman run \
  --rm \
  --name "${CONTAINER_NAME}" \
  --publish "${HOST_PORT}:${CONTAINER_PORT}" \
  "${DATA_MOUNT[@]}" \
  ${CERTS_MOUNT[@]+"${CERTS_MOUNT[@]}"} \
  "${IMAGE_NAME}:${IMAGE_TAG}"
