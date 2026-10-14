#!/usr/bin/env bash
# prepare-node.sh -- Generic Linux/POSIX node pre-backup export hook.
#
# Executed via SSH before the storage hub pulls via rclone SFTP.
#   1. Creates atomic SQLite snapshots (<db>.bak-nightly) for active databases.
#   2. Dumps database containers (e.g. Postgres / MySQL) to compressed SQL dumps.
#   3. Stages configuration and state trees into an export directory with secure permissions.
#
# Deploy:
#   sudo install -o root -g root -m 0750 prepare-node.sh /usr/local/sbin/prepare-node.sh

set -euo pipefail
umask 0077

BACKUP_USER="backup-operator"
EXPORT_ROOT="/srv/backup-export"

log() {
  printf '%s  [prepare-node] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

log "Starting pre-backup preparation..."

# 1. Initialize export root
install -d -o "${BACKUP_USER}" -g "${BACKUP_USER}" -m 0700 \
  "${EXPORT_ROOT}" \
  "${EXPORT_ROOT}/databases" \
  "${EXPORT_ROOT}/etc" \
  "${EXPORT_ROOT}/state"

# 2. SQLite Snapshots (example)
log "Snapshotting active SQLite databases..."
find /var/lib /srv /opt -maxdepth 4 -name '*.db' 2>/dev/null | while read -r db_file; do
  case "${db_file}" in
    *cache*|*venv*|*node_modules*) continue ;;
  esac
  bak_file="${db_file}.bak-nightly"
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "${db_file}" ".timeout 5000" ".backup '${bak_file}'" 2>/dev/null || true
    chmod 0600 "${bak_file}" 2>/dev/null || true
  fi
done

# 3. Container Database Dump (Postgres example)
if command -v docker >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' | grep -q 'postgres'; then
    log "Dumping PostgreSQL container..."
    docker exec -t postgres-db pg_dumpall -U postgres | gzip -9 > "${EXPORT_ROOT}/databases/postgres.sql.gz.tmp" || true
    if [[ -f "${EXPORT_ROOT}/databases/postgres.sql.gz.tmp" ]]; then
      mv -f "${EXPORT_ROOT}/databases/postgres.sql.gz.tmp" "${EXPORT_ROOT}/databases/postgres.sql.gz"
      chown "${BACKUP_USER}:${BACKUP_USER}" "${EXPORT_ROOT}/databases/postgres.sql.gz"
    fi
  fi
fi

# 4. Stage critical /etc configurations
log "Staging /etc configurations..."
rsync -a --delete --relative \
  /etc/systemd/system \
  /etc/ufw \
  /etc/ssh \
  "${EXPORT_ROOT}/etc/" 2>/dev/null || true

# 5. Fix permissions for SFTP pull user
chown -R "${BACKUP_USER}:${BACKUP_USER}" "${EXPORT_ROOT}"
chmod -R u=rwX,go= "${EXPORT_ROOT}"

log "Preparation complete. Ready for remote pull."
