#!/bin/bash
# ═══════════════════════════════════════════════════
#  SophosLLM v2 — Deploy SSH a Easypanel
#  Uso: ./deploy_ssh.sh [IP] [USUARIO] [PUERTO]
#  Ejemplo: ./deploy_ssh.sh 123.45.67.89 root 22
# ═══════════════════════════════════════════════════

set -e

# ── Parámetros ─────────────────────────────────────
SERVER_IP="${1:-}"
SERVER_USER="${2:-root}"
SERVER_PORT="${3:-22}"
REMOTE_PATH="${4:-/opt/sophosllm}"   # Ruta en el servidor (ajustar si Easypanel usa otra)
LOCAL_PATH="$(cd "$(dirname "$0")" && pwd)"

# ── Colores ────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[→]${NC} $1"; }
ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ── Validación ─────────────────────────────────────
echo ""
echo "╔════════════════════════════════════════╗"
echo "║   SophosLLM v2 — Deploy por SSH        ║"
echo "╚════════════════════════════════════════╝"
echo ""

if [ -z "$SERVER_IP" ]; then
  echo -e "${YELLOW}Uso:${NC} ./deploy_ssh.sh <IP_SERVIDOR> [usuario] [puerto] [ruta_remota]"
  echo ""
  echo "Ejemplos:"
  echo "  ./deploy_ssh.sh 123.45.67.89"
  echo "  ./deploy_ssh.sh 123.45.67.89 root 22"
  echo "  ./deploy_ssh.sh 123.45.67.89 root 22 /opt/sophosllm"
  exit 1
fi

SSH_TARGET="${SERVER_USER}@${SERVER_IP}"
SSH_OPTS="-p ${SERVER_PORT} -o StrictHostKeyChecking=no -o ConnectTimeout=10"

log "Destino: ${SSH_TARGET}:${REMOTE_PATH} (puerto ${SERVER_PORT})"
log "Fuente:  ${LOCAL_PATH}"
echo ""

# ── Test de conexión ────────────────────────────────
log "Verificando conexión SSH..."
ssh $SSH_OPTS "$SSH_TARGET" "echo OK" > /dev/null 2>&1 || err "No se puede conectar a ${SSH_TARGET}. Verifica IP, usuario y que SSH esté activo."
ok "Conexión SSH OK"

# ── Crear directorio remoto ─────────────────────────
log "Creando estructura de directorios en servidor..."
ssh $SSH_OPTS "$SSH_TARGET" "mkdir -p ${REMOTE_PATH}/data/raw ${REMOTE_PATH}/data/images ${REMOTE_PATH}/data/vectors"
ok "Directorios creados"

# ── Calcular tamaño ────────────────────────────────
CODE_SIZE=$(du -sh "${LOCAL_PATH}" --exclude="${LOCAL_PATH}/venv" --exclude="${LOCAL_PATH}/data" 2>/dev/null | cut -f1 || echo "?")
DATA_RAW_SIZE=$(du -sh "${LOCAL_PATH}/data/raw" 2>/dev/null | cut -f1 || echo "0")
DATA_IMG_SIZE=$(du -sh "${LOCAL_PATH}/data/images" 2>/dev/null | cut -f1 || echo "0")
DATA_VEC_SIZE=$(du -sh "${LOCAL_PATH}/data/vectors_legacy" 2>/dev/null | cut -f1 || echo "0")

echo ""
echo "  📁 Código y templates: ~${CODE_SIZE}"
echo "  📄 Raw JSONs:          ~${DATA_RAW_SIZE}"
echo "  🖼️  Imágenes:           ~${DATA_IMG_SIZE}"
echo "  🗃️  Vectores:           ~${DATA_VEC_SIZE}"
echo ""
warn "La transferencia puede tardar 5–20 min según la velocidad de subida."
echo ""
read -p "¿Continuar? [s/N]: " CONFIRM
[[ "$CONFIRM" =~ ^[sS]$ ]] || { echo "Cancelado."; exit 0; }
echo ""

# ── Paso 1: Código fuente ─────────────────────────
log "PASO 1/4 — Subiendo código fuente..."
rsync -avz --progress \
  -e "ssh $SSH_OPTS" \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='*.log' \
  --exclude='.DS_Store' \
  --exclude='data/' \
  --exclude='.git/' \
  "${LOCAL_PATH}/" "${SSH_TARGET}:${REMOTE_PATH}/"
ok "Código subido"

# ── Paso 2: Raw JSONs ─────────────────────────────
log "PASO 2/4 — Subiendo documentación raw (${DATA_RAW_SIZE})..."
rsync -avz --progress \
  -e "ssh $SSH_OPTS" \
  --ignore-existing \
  "${LOCAL_PATH}/data/raw/" "${SSH_TARGET}:${REMOTE_PATH}/data/raw/"
ok "Raw JSONs subidos"

# ── Paso 3: Imágenes ──────────────────────────────
log "PASO 3/4 — Subiendo imágenes (${DATA_IMG_SIZE}) — puede tardar varios minutos..."
rsync -avz --progress \
  -e "ssh $SSH_OPTS" \
  --ignore-existing \
  "${LOCAL_PATH}/data/images/" "${SSH_TARGET}:${REMOTE_PATH}/data/images/"
ok "Imágenes subidas"

# ── Paso 4: Vectores ──────────────────────────────
# Sube vectores legacy como base (hasta que el nuevo indexado complete)
VECTORS_SRC="${LOCAL_PATH}/data/vectors"
if [ -d "${LOCAL_PATH}/data/vectors_legacy" ]; then
  VECTORS_SRC="${LOCAL_PATH}/data/vectors_legacy"
  warn "Subiendo vectores legacy como base (el nuevo indexado completará en servidor)"
fi
log "PASO 4/4 — Subiendo base de vectores ChromaDB (${DATA_VEC_SIZE})..."
rsync -avz --progress \
  -e "ssh $SSH_OPTS" \
  "${VECTORS_SRC}/" "${SSH_TARGET}:${REMOTE_PATH}/data/vectors/"
ok "Vectores subidos"

# ── Setup en servidor ─────────────────────────────
echo ""
log "Configurando entorno Python en servidor..."
ssh $SSH_OPTS "$SSH_TARGET" bash << REMOTE_EOF
  set -e
  cd ${REMOTE_PATH}

  echo "[1/3] Creando venv..."
  python3 -m venv venv 2>/dev/null || true

  echo "[2/3] Instalando dependencias..."
  ./venv/bin/pip install --upgrade pip --quiet
  ./venv/bin/pip install -r requirements.txt --quiet

  echo "[3/3] Verificando ChromaDB..."
  ./venv/bin/python3 -c "
import chromadb, json
from pathlib import Path
p = Path('data/vectors')
if p.exists():
    c = chromadb.PersistentClient(path=str(p))
    cols = c.list_collections()
    for col in cols:
        print(f'  DB: {col.name} — {c.get_collection(col.name).count()} docs')
else:
    print('  Sin vectores aún')
" 2>/dev/null || echo "  ChromaDB check omitido"

  echo "[OK] Setup completo"
REMOTE_EOF
ok "Entorno configurado"

# ── Restart del servicio ─────────────────────────
echo ""
log "Reiniciando servicio SophosLLM..."
ssh $SSH_OPTS "$SSH_TARGET" bash << REMOTE_EOF
  # Detener proceso anterior si existe
  pkill -f "gunicorn.*app:app" 2>/dev/null || true
  pkill -f "python.*app.py" 2>/dev/null || true
  sleep 2

  cd ${REMOTE_PATH}
  source venv/bin/activate

  # Iniciar con gunicorn en background
  nohup gunicorn -w 2 -b 0.0.0.0:3050 --timeout 120 \
    --log-level info \
    --access-logfile ${REMOTE_PATH}/access.log \
    --error-logfile ${REMOTE_PATH}/error.log \
    app:app > /dev/null 2>&1 &

  sleep 3
  # Verificar que levantó
  curl -sf http://localhost:3050/health > /dev/null && echo "✅ Servicio activo en :3050" || echo "⚠️  Health check falló"
REMOTE_EOF

# ── Resultado final ───────────────────────────────
echo ""
echo "╔════════════════════════════════════════╗"
echo "║   ✅  Deploy completado                 ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "  🌐 URL local en servidor:  http://${SERVER_IP}:3050"
echo "  🔧 Health check:           http://${SERVER_IP}:3050/health"
echo "  📊 API status:             http://${SERVER_IP}:3050/api/status"
echo ""
echo "  📄 Logs:"
echo "    ssh ${SSH_TARGET} 'tail -f ${REMOTE_PATH}/error.log'"
echo ""
warn "Si usas Cloudflare Tunnel, el servicio ya debería ser accesible por tu dominio."
echo ""
