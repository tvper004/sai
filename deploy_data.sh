#!/bin/bash
# ═══════════════════════════════════════════════════
#  SophosLLM v2 — Deploy Data (SSH) a Easypanel
# ═══════════════════════════════════════════════════

set -e

# ── Configuración ──────────────────────────────────
SERVER_IP="192.168.1.200"
SERVER_USER="rleon"
SERVER_PASS="12345."

# Ruta del volumen de la data en Easypanel. 
# Modifica 'desarrollo' y 'sophosv2' si el proyecto/app tienen otros nombres.
# Modifica 'sophos-data' por el nombre del volumen que crees en Easypanel.
VOLUME_PATH="/etc/easypanel/projects/desarrollo/sophosv2/volumes/sophos-data" 

# Carpeta temporal para la subida
BACKUP_PATH="/home/rleon/sophos_data_upload"

LOCAL_PATH="$(cd "$(dirname "$0")" && pwd)"

# ── Colores ────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[→]${NC} $1"; }
ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║   SophosLLM v2 — Sincronizando solo Data   ║"
echo "║   Destino: Volumen Easypanel               ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# ── Test de conexión ────────────────────────────────
log "Probando conexión con ${SERVER_USER}@${SERVER_IP}..."
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" "echo Conexión OK" || err "Fallo de conexión."

# ── Sincronización a carpeta temporal ────────────────
log "Subiendo archivos a carpeta temporal en el servidor..."
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" "mkdir -p ${BACKUP_PATH}"

# Subimos solo las carpetas raw, images y vectors
for dir in "raw" "images" "vectors"; do
    if [ -d "${LOCAL_PATH}/data/$dir" ]; then
        log "Subiendo data/$dir..."
        sshpass -p "$SERVER_PASS" rsync -avz --progress --ignore-existing \
            "${LOCAL_PATH}/data/$dir/" "$SERVER_USER@$SERVER_IP:$BACKUP_PATH/$dir/"
    fi
done

# ── Mover a Easypanel (Requiere Root) ────────────────
log "Moviendo la data al volumen de Easypanel..."
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no -t "$SERVER_USER@$SERVER_IP" << REMOTE_EOF
  echo "$SERVER_PASS" | sudo -S mkdir -p ${VOLUME_PATH} 2>/dev/null || true
  echo "$SERVER_PASS" | sudo -S cp -r ${BACKUP_PATH}/* ${VOLUME_PATH}/ 2>/dev/null
  echo "$SERVER_PASS" | sudo -S chown -R root:root ${VOLUME_PATH} 2>/dev/null
  
  echo "Data sincronizada en el volumen."
REMOTE_EOF

echo ""
ok "Archivos transferidos al servidor de forma exitosa."
warn "Recuerda que para que la aplicación en Easypanel tome los cambios debes tener el volumen montado en '/app/data'."
echo ""
