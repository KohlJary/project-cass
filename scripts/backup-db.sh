#!/bin/bash
# Hourly backup of cass.db
# Keeps last 24 hourly backups

BACKUP_DIR="/home/jaryk/cass/cass-vessel/data/backups/hourly"
DB_PATH="/home/jaryk/cass/cass-vessel/data/cass.db"
TIMESTAMP=$(date +%Y%m%d_%H%M)
BACKUP_FILE="$BACKUP_DIR/cass_db_$TIMESTAMP.db"

# Create backup using sqlite3's backup command for consistency
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

if [ $? -eq 0 ]; then
    echo "Backup created: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

    # Keep only last 24 backups
    cd "$BACKUP_DIR"
    ls -t cass_db_*.db 2>/dev/null | tail -n +25 | xargs -r rm -f

    BACKUP_COUNT=$(ls cass_db_*.db 2>/dev/null | wc -l)
    echo "Retained $BACKUP_COUNT hourly backups"
else
    echo "ERROR: Backup failed!" >&2
    exit 1
fi
