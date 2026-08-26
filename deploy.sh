#!/bin/bash
set -e
set -o pipefail

# Deploy script for Yandex Food Map
# Pulls latest code from GitHub and restarts the server

cd /opt/yandex_food
LOG_FILE="/opt/yandex_food/deploy.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Deploy started ==="

# Save current DB path before any changes
DB_PATH="/opt/yandex_food/orders.db"

# Stash local changes (if any) and pull
if ! git stash --include-untracked 2>>"$LOG_FILE" || ! git pull origin main 2>>"$LOG_FILE"; then
    log "ERROR: git pull failed"
    exit 1
fi

log "Git pull OK: $(git rev-parse --short HEAD)"

# Restart the service
if systemctl is-active --quiet yandex-food; then
    systemctl restart yandex-food 2>>"$LOG_FILE"
    log "Service restarted"
else
    # Try starting if service exists
    systemctl start yandex-food 2>>"$LOG_FILE" || true
    log "Service started (or attempted)"
fi

sleep 1

# Health check - verify server is up
if curl -sf http://localhost:8081/api/health > /dev/null 2>&1; then
    log "Health check passed"
else
    log "WARNING: Health check failed — server may not be running"
fi

log "=== Deploy completed ==="