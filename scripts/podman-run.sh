#!/usr/bin/env bash
# Run the budgeter container with Podman. SQLite data persists on a named
# volume across restarts/rebuilds.
#
# Usage:
#   scripts/podman-run.sh                          # default dev API key
#   API_KEY=my-secret scripts/podman-run.sh         # must match whatever key
#                                                    # podman-build.sh baked
#                                                    # into the frontend
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-com.valsr.budgeter}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
CONTAINER_NAME="${CONTAINER_NAME:-budgeter}"
HOST_PORT="${HOST_PORT:-8000}"
API_KEY="${API_KEY:-dev-local-api-key}"
VOLUME_NAME="${VOLUME_NAME:-budgeter-data}"

podman volume create "${VOLUME_NAME}" >/dev/null 2>&1 || true

echo "Starting ${CONTAINER_NAME} from ${IMAGE_NAME}:${IMAGE_TAG} on http://localhost:${HOST_PORT}"
podman run \
  --rm \
  --name "${CONTAINER_NAME}" \
  --publish "${HOST_PORT}:8000" \
  --env "BUDGETER_API_KEY=${API_KEY}" \
  --volume "${VOLUME_NAME}:/data" \
  "${IMAGE_NAME}:${IMAGE_TAG}"
