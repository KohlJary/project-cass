#!/bin/bash
# Automated backup script for Cass data
# Can be run via cron or systemd timer

set -e

BACKUP_DIR="${BACKUP_DIR:-/home/jaryk/cass/cass-vessel/data/backups}"
DATA_DIR="${DATA_DIR:-/home/jaryk/cass/cass-vessel/data}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="backup_${TIMESTAMP}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}.zip"

# Create backup directory if needed
mkdir -p "${BACKUP_DIR}"

echo "$(date): Starting Cass backup..."

# Create backup via API if server is running
if curl -s "http://localhost:8000/health" > /dev/null 2>&1; then
    echo "Using API for backup..."
    RESULT=$(curl -s -X POST "http://localhost:8000/export/backup")
    echo "API backup result: ${RESULT}"
else
    # Manual backup if server not running
    echo "Server not running, creating manual backup..."

    cd "${DATA_DIR}"
    zip -r "${BACKUP_PATH}" \
        wiki/ \
        conversations/ \
        users/ \
        cass/ \
        roadmap/ \
        -x "*.pyc" -x "__pycache__/*" -x "chroma/*"

    SIZE=$(du -h "${BACKUP_PATH}" | cut -f1)
    echo "Backup created: ${BACKUP_PATH} (${SIZE})"
fi

# Clean up old backups
echo "Cleaning up backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "backup_*.zip" -mtime +${RETENTION_DAYS} -delete

# List current backups
echo "Current backups:"
ls -lh "${BACKUP_DIR}"/backup_*.zip 2>/dev/null || echo "No backups found"

echo "$(date): Backup complete"
