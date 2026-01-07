#!/usr/bin/env bash
# Script simple para respaldar la base de datos SQLite
# Crea copias en `backups/` con timestamp.

set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="$BASE_DIR/backups/sqlite"
DB_PATH="$BASE_DIR/ARCHIVOS/control_papelerias.db"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%dT%H%M%S")
DEST="$BACKUP_DIR/control_papelerias.db.$TIMESTAMP"

if [ ! -f "$DB_PATH" ]; then
  echo "[backup] DB no encontrada en $DB_PATH" >&2
  exit 1
fi

echo "[backup] Creando copia de $DB_PATH -> $DEST"
cp -f "$DB_PATH" "$DEST"
chown --reference="$DB_PATH" "$DEST" || true
chmod 640 "$DEST" || true
echo "[backup] Backup creado correctamente"

# Borrar backups antiguos (mantener los últimos 30)
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'control_papelerias.db.*' -printf '%T@ %p\n' | sort -n | awk '{print $2}' | head -n -30 | xargs -r rm -f || true

exit 0
