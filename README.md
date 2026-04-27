# 🛡️ SophosLLM v2 — Consultor Técnico Sophos

Asistente de IA especializado en documentación técnica de **Sophos**. Responde preguntas sobre configuraciones, errores, permisos y procedimientos de todos los productos Sophos usando RAG (Retrieval-Augmented Generation).

---

## ¿Qué hace?

| Modo | Descripción |
|---|---|
| **Consultor IA** | Chat inteligente que busca en 1,695 artículos de documentación Sophos y responde con contexto, imágenes relevantes y links de descarga |
| **Biblioteca** | Acceso directo a documentación oficial por producto + buscador en la KB local indexada |

**Stack:**
- LLM: Groq API (llama-3.3-70b) — gratis, respuestas en 1–3 seg
- Vector DB: ChromaDB local (no necesita internet para búsquedas)
- Embeddings: `all-MiniLM-L6-v2` (local)
- Backend: Python / Flask
- Acceso público: Cloudflare Tunnel

---

## Requisitos

- Python 3.10 o superior
- 4 GB RAM disponibles mínimo (8 GB recomendado)
- ~600 MB de espacio libre (datos + modelos de embeddings)
- Conexión a internet para llamadas al API de Groq

---

## Instalación en MacBook Pro 2012 (Linux Mint)

### Paso 1 — Habilitar SSH (desde la Mac 2012 directamente)

```bash
sudo apt update
sudo apt install -y openssh-server
sudo systemctl enable ssh
sudo systemctl start ssh

# Anotar la IP local
ip addr show | grep "inet " | grep -v "127.0.0.1"
# Ejemplo: 192.168.1.105
```

### Paso 2 — Transferir el proyecto desde tu Mac principal

En tu **Mac con macOS**, abre Terminal y ejecuta:

```bash
# Reemplaza con tu IP y usuario de Linux Mint
rsync -avz --progress \
  --exclude='venv/' \
  --exclude='data/vectors/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  /Users/robb004/Desktop/MoneyPrinter/SophosLLM/ \
  tu_usuario@192.168.1.105:~/SophosLLM/
```

> ℹ️ El proyecto pesa ~286 MB. Tiempo estimado: 2–8 minutos en red local.  
> Si se interrumpe, vuelve a ejecutar — rsync retoma sin re-enviar lo ya transferido.

### Paso 3 — Instalar dependencias en la Mac 2012

Conéctate por SSH o usa el terminal directamente en la Mac 2012:

```bash
cd ~/SophosLLM

# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias (~10–20 min, descarga PyTorch)
pip install --upgrade pip
pip install -r requirements.txt
```

### Paso 4 — Ejecutar el pipeline de datos

> ⚠️ Este proceso solo se hace **una vez**. Los datos quedan guardados en `data/vectors/`.

```bash
cd ~/SophosLLM
source venv/bin/activate

# 1. Enriquecer datos: añade artículos relacionados y links de descarga faltantes
#    Tiempo: 30–60 minutos (1,695 páginas)
python agents/enricher_agent.py --workers 2

# 2. Vectorizar: crea la base de conocimientos en ChromaDB
#    Tiempo: 15–40 minutos
python agents/vectorizer_v2.py --mode index

# 3. Verificar que funciona
python agents/query_v2.py --q "¿Cómo configurar una política de firewall en Sophos?"
```

### Paso 5 — Iniciar el servicio

#### Modo temporal (para probar)

```bash
cd ~/SophosLLM
source venv/bin/activate
./start.sh
```

Abre en tu navegador: `http://192.168.1.105:3050`

#### Modo permanente con systemd (inicio automático)

```bash
sudo nano /etc/systemd/system/sophosllm.service
```

Pega el siguiente contenido (reemplaza `tu_usuario` con tu usuario real):

```ini
[Unit]
Description=SophosLLM v2 — Sophos Documentation AI
After=network.target

[Service]
Type=simple
User=tu_usuario
WorkingDirectory=/home/tu_usuario/SophosLLM
Environment="PATH=/home/tu_usuario/SophosLLM/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/tu_usuario/SophosLLM/venv/bin/gunicorn \
    -w 2 \
    -b 0.0.0.0:3050 \
    --timeout 120 \
    --log-level info \
    --access-logfile /home/tu_usuario/SophosLLM/access.log \
    --error-logfile /home/tu_usuario/SophosLLM/error.log \
    app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# Guardar: Ctrl+O → Enter → Ctrl+X

sudo systemctl daemon-reload
sudo systemctl enable sophosllm
sudo systemctl start sophosllm

# Verificar estado
sudo systemctl status sophosllm

# Ver logs en vivo
journalctl -u sophosllm -f
```

---

## Acceso desde Internet con Cloudflare Tunnel

### Instalación de cloudflared

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb \
  -o cloudflared.deb
sudo dpkg -i cloudflared.deb
```

### Configuración

```bash
# 1. Autenticar (genera un link — ábrelo en el navegador)
cloudflared tunnel login

# 2. Crear tunnel
cloudflared tunnel create sophosllm
# Anota el TUNNEL_ID que aparece

# 3. Crear configuración
mkdir -p ~/.cloudflared
nano ~/.cloudflared/config.yml
```

Contenido del `config.yml`:

```yaml
tunnel: TU_TUNNEL_ID_AQUI
credentials-file: /home/tu_usuario/.cloudflared/TU_TUNNEL_ID.json

ingress:
  - hostname: sophos.tudominio.com
    service: http://localhost:3050
  - service: http_status:404
```

```bash
# 4. Apuntar dominio al tunnel
cloudflared tunnel route dns sophosllm sophos.tudominio.com

# 5. Probar
cloudflared tunnel run sophosllm

# 6. Instalar como servicio permanente
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

> 💡 **Sin dominio propio?** Usa Quick Tunnel para probar gratis:
> ```bash
> cloudflared tunnel --url http://localhost:3050
> ```
> Genera una URL temporal tipo `https://random-name.cfargotunnel.com`

---

## URLs de acceso

| Acceso | URL |
|---|---|
| Red local | `http://192.168.1.XXX:3050` |
| Cloudflare (producción) | `https://sophos.tudominio.com` |
| Estado del sistema | `http://localhost:3050/api/status` |
| Health check | `http://localhost:3050/health` |

---

## Comandos útiles

```bash
# Activar entorno virtual
cd ~/SophosLLM && source venv/bin/activate

# Iniciar servicio
sudo systemctl start sophosllm

# Detener servicio
sudo systemctl stop sophosllm

# Reiniciar servicio
sudo systemctl restart sophosllm

# Ver logs en tiempo real
journalctl -u sophosllm -f

# Test de query desde terminal
python agents/query_v2.py --q "error VPN Sophos Firewall"

# Re-indexar si se añaden nuevos documentos
python agents/vectorizer_v2.py --mode index
```

---

## Estructura del proyecto

```
SophosLLM/
├── agents/
│   ├── enricher_agent.py   # Enriquece raw JSON con links relacionados
│   ├── chunker_v2.py       # Chunking semántico por secciones
│   ├── vectorizer_v2.py    # Genera embeddings y almacena en ChromaDB
│   └── query_v2.py         # Motor RAG con detección de intención
├── data/
│   ├── raw/                # 1,695 artículos Sophos en JSON
│   ├── images/             # Imágenes de la documentación
│   └── vectors/            # ChromaDB (generado en el Paso 4)
├── static/
│   ├── css/style.css       # UI mobile-first
│   └── js/app.js           # Frontend con markdown y lightbox
├── templates/
│   └── index.html          # Chat + Biblioteca
├── app.py                  # Flask backend
├── requirements.txt        # Dependencias Python
├── start.sh                # Script de inicio
└── .env                    # Configuración y API keys
```

---

## Variables de entorno (.env)

| Variable | Descripción |
|---|---|
| `GROQ_API_KEY_1..5` | Claves API de Groq (rotación automática) |
| `GROQ_PRIMARY_MODEL` | Modelo principal (llama-3.3-70b-versatile) |
| `FLASK_PORT` | Puerto del servidor (3050) |
| `TOP_K_RESULTS` | Resultados por consulta (15) |

---

## Solución de problemas

**La app inicia pero no responde preguntas:**
→ El pipeline no se ha ejecutado aún. Corre los pasos 4.1 y 4.2.

**Error: `No module named 'chromadb'`:**
→ Activa el venv: `source venv/bin/activate`

**Error de Groq API rate limit:**
→ El sistema rota automáticamente entre las 5 claves configuradas.

**La transferencia rsync falla:**
→ Verifica que SSH está activo en la Mac 2012: `sudo systemctl status ssh`
