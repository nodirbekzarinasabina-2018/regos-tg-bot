#!/usr/bin/env bash
set -euo pipefail

container_id="$(docker ps -q --filter label=coolify.resourceName=chust-optom-1-regos-bot | head -n 1)"
if [ -z "${container_id}" ]; then
  exit 0
fi

docker exec "${container_id}" python /app/recover_recent_docs.py \
  --hours 4 \
  --sale-start 10600 \
  --sale-end 13000 \
  --payment-start 11200 \
  --payment-end 13000 \
  --step 250
