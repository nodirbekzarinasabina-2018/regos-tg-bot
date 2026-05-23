#!/usr/bin/env bash
set -euo pipefail

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

crontab -l 2>/dev/null | grep -v 'chust-optom-1-regos-bot' > "$tmp_file" || true
echo '*/10 * * * * /bin/bash /home/codexadmin/work/chust-optom-1-regos-bot/cron_backfill.sh >> /var/log/chust-optom-1-regos-backfill.log 2>&1' >> "$tmp_file"
crontab "$tmp_file"
crontab -l
