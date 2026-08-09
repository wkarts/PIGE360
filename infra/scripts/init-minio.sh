#!/bin/sh
set -eu
access_key="$(cat "$MINIO_ACCESS_KEY_FILE")"
secret_key="$(cat "$MINIO_SECRET_KEY_FILE")"
mc alias set local "$MINIO_ENDPOINT" "$access_key" "$secret_key"
mc mb --ignore-existing local/pige360-platform
mc version enable local/pige360-platform || true
mc anonymous set none local/pige360-platform
printf '%s
' "MinIO inicializado de forma idempotente."
