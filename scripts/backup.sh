#!/usr/bin/env bash
# backup.sh — Backup automático de la base de datos Datero
#
# Uso:
#   DATABASE_URL="postgresql://..." ./backup.sh
#   # O configurar CRON:
#   0 3 * * * /ruta/a/datero/scripts/backup.sh
#
# Requiere:
#   - pg_dump (cliente PostgreSQL)
#   - rclone (opcional, para subir a Google Drive / S3)
#
# Variables de entorno:
#   DATABASE_URL  (obligatorio) — URL de conexión a PostgreSQL
#   BACKUP_DIR    (opcional)    — directorio local de backups (def: ./backups)
#   RCLONE_REMOTE (opcional)    — nombre del remote de rclone para subir
#   RETENTION_DAYS (opcional)   — días a conservar backups locales (def: 7)

set -euo pipefail

# ─── Configuración ───────────────────────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="datero_${TIMESTAMP}.sql.gz"
FILEPATH="${BACKUP_DIR}/${FILENAME}"

# ─── Validar DATABASE_URL ───────────────────────────────────────────────────
if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERROR: DATABASE_URL no está definida"
    echo "Uso: DATABASE_URL='postgresql://...' $0"
    exit 1
fi

# ─── Crear directorio de backups ────────────────────────────────────────────
mkdir -p "${BACKUP_DIR}"

# ─── Ejecutar pg_dump ───────────────────────────────────────────────────────
echo "📦 Iniciando backup: ${FILENAME}"
pg_dump "${DATABASE_URL}" --no-owner --no-acl | gzip > "${FILEPATH}"
echo "✅ Backup completado: $(du -h "${FILEPATH}" | cut -f1)"

# ─── Subir a cloud (opcional) ───────────────────────────────────────────────
if [ -n "${RCLONE_REMOTE:-}" ]; then
    if command -v rclone &> /dev/null; then
        echo "☁️  Subiendo a ${RCLONE_REMOTE}..."
        rclone copy "${FILEPATH}" "${RCLONE_REMOTE}:datero-backups/" --progress
        echo "✅ Subida completada"
    else
        echo "⚠️  rclone no instalado. Omitiendo subida a cloud."
    fi
fi

# ─── Limpiar backups antiguos ───────────────────────────────────────────────
echo "🧹 Limpiando backups con más de ${RETENTION_DAYS} días..."
find "${BACKUP_DIR}" -name "datero_*.sql.gz" -type f -mtime "+${RETENTION_DAYS}" -delete
echo "✅ Limpieza completada"

echo ""
echo "📋 Resumen:"
echo "   Archivo: ${FILEPATH}"
echo "   Fecha:   ${TIMESTAMP}"
