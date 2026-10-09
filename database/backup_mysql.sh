#!/usr/bin/env bash
# Nightly MySQL backup with retention. Cron example (02:15 every night):
#   15 2 * * * /path/to/savings_hub/database/backup_mysql.sh >> /var/log/savings_hub_backup.log 2>&1
# Credentials come from a protected file, never the command line:
#   /etc/savings_hub/backup.cnf   (chmod 600)    [client]\nuser=savings_hub_user\npassword=...
set -euo pipefail
DB_NAME="${DB_NAME:-savings_hub}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/savings_hub}"
CNF="${CNF:-/etc/savings_hub/backup.cnf}"
KEEP_DAYS="${KEEP_DAYS:-14}"

umask 077
mkdir -p "$BACKUP_DIR"
OUT="$BACKUP_DIR/${DB_NAME}_$(date +%Y%m%d_%H%M%S).sql.gz"
# --single-transaction = consistent snapshot without locking the live site (InnoDB).
mysqldump --defaults-extra-file="$CNF" --single-transaction --routines --triggers \
          --no-tablespaces --set-gtid-purged=OFF --default-character-set=utf8mb4 "$DB_NAME" | gzip -9 > "$OUT"
# A truncated dump is worse than none: verify it ends with the dump-complete marker.
gunzip -c "$OUT" | tail -n 1 | grep -q "Dump completed" || { echo "BACKUP FAILED: $OUT incomplete" >&2; rm -f "$OUT"; exit 1; }
find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -mtime +"$KEEP_DAYS" -delete
echo "$(date -Is) backup ok: $OUT ($(du -h "$OUT" | cut -f1))"
echo "REMINDER: also back up media/ and private_media/ (uploads are not in the database)."
