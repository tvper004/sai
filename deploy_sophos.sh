#!/bin/bash
# ═══════════════════════════════════════════════════
#  SophosLLM v2 — Deploy SSH a Easypanel (Puerto 3040)
# ═══════════════════════════════════════════════════

set -e

# ── Configuración ──────────────────────────────────
SERVER_IP="192.168.1.200"
SERVER_USER="rleon"
SERVER_PASS="12345."
# Ruta probable de Easypanel (ajustar si es diferente)
REMOTE_PATH="/etc/easypanel/projects/desarrollo/sophosv2/volumes/code" 
# Si no existe esa ruta, usaremos una temporal y luego la movemos
BACKUP_PATH="/home/rleon/sophos_update"

LOCAL_PATH="$(cd "$(dirname "$0")" && pwd)"

# ── Colores ────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[→]${NC} $1"; }
ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║   SophosLLM v2 — Actualizando Easypanel    ║"
echo "║   Puerto: 3040 | IP: 192.168.1.200         ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# ── Test de conexión ────────────────────────────────
log "Probando conexión con ${SERVER_USER}@${SERVER_IP}..."
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" "echo Conexión OK" || err "Fallo de conexión."

# ── Sincronización a carpeta temporal ────────────────
# Subimos a /home/rleon primero porque rleon no tiene permiso directo en /etc
log "Subiendo archivos a carpeta temporal en el servidor..."
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" "mkdir -p ${BACKUP_PATH}/data"

sshpass -p "$SERVER_PASS" rsync -avz --progress \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='*.log' \
  --exclude='.DS_Store' \
  --exclude='data/' \
  --exclude='.git/' \
  "${LOCAL_PATH}/" "$SERVER_USER@$SERVER_IP:$BACKUP_PATH/"

# Data (Raw, Imágenes, Vectores)
for dir in "raw" "images" "vectors"; do
    if [ -d "${LOCAL_PATH}/data/$dir" ]; then
        log "Subiendo data/$dir..."
        sshpass -p "$SERVER_PASS" rsync -avz --progress --ignore-existing \
            "${LOCAL_PATH}/data/$dir/" "$SERVER_USER@$SERVER_IP:$BACKUP_PATH/data/$dir/"
    fi
done

# ── Mover a Easypanel (Requiere Root) ────────────────
log "Moviendo archivos a la ruta de Easypanel y reiniciando..."
# Usamos sudo con la misma contraseña (asumiendo que rleon tiene sudo)
# Si rleon no tiene sudo, tendremos que pedir al usuario que lo mueva manualmente
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no -t "$SERVER_USER@$SERVER_IP" << REMOTE_EOF
  echo "$SERVER_PASS" | sudo -S mkdir -p /etc/easypanel/projects/desarrollo/sophosv2/code 2>/dev/null || true
  echo "$SERVER_PASS" | sudo -S cp -r ${BACKUP_PATH}/* /etc/easypanel/projects/desarrollo/sophosv2/code/ 2>/dev/null || \
  echo "$SERVER_PASS" | sudo -S cp -r ${BACKUP_PATH}/* /home/rleon/sophosv2_live/ 2>/dev/null || true
  
  echo "Cambios aplicados. Por favor, reinicia el servicio desde el panel de Easypanel para aplicar los cambios de puerto y código."
REMOTE_EOF

echo ""
ok "Archivos transferidos al servidor."
warn "IMPORTANTE: Como el servicio corre dentro de Easypanel (Docker), debes darle a 'Implementar' o 'Reiniciar' en tu panel web de Easypanel."
echo ""
