#!/usr/bin/env python3
"""
SophosLLM v2 — Flask App
"""
import json
import os
import re
import sys
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_from_directory
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.absolute()
load_dotenv(BASE_DIR / ".env")
sys.path.insert(0, str(BASE_DIR))

app = Flask(__name__)
IMAGES_DIR = BASE_DIR / "data" / "images"
RAW_DIR = BASE_DIR / "data" / "raw"

# ── Categorías por URL pattern ────────────────────────
PRODUCT_PATTERNS = {
    "firewall": re.compile(r'firewall|xgs|xg\b|sophos-sg|utm', re.I),
    "endpoint":  re.compile(r'endpoint|intercept|protect|central/customer', re.I),
    "server":    re.compile(r'server|server-protect', re.I),
    "email":     re.compile(r'email|mail|spam', re.I),
    "xdr":       re.compile(r'xdr|mdr|detect|threat', re.I),
    "ztna":      re.compile(r'ztna|zero.trust|vpn', re.I),
}

def detect_product(url: str, title: str = "") -> str:
    text = (url + " " + title).lower()
    for prod, pat in PRODUCT_PATTERNS.items():
        if pat.search(text):
            return prod
    return "general"


# ── Cache de artículos (cargado una vez) ─────────────
_articles_cache: list[dict] = []
_categories_cache: dict = {}

def _load_articles_cache():
    global _articles_cache, _categories_cache
    if _articles_cache:
        return

    raw_files = list(RAW_DIR.glob("*.json"))
    articles = []
    for f in raw_files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            if d.get("error") or not d.get("title"):
                continue
            raw_text = d.get("text", "")
            # Strip markdown links [text](url) → text, and clean noise
            import re as _re
            clean = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', raw_text)
            clean = _re.sub(r'!\[[^\]]*\]\([^)]+\)', '', clean)
            clean = _re.sub(r'[*#`>_~]+', '', clean).replace('\n', ' ').strip()
            snippet = (clean[:220] + "…") if clean else ""
            articles.append({
                "hash": d.get("url_hash", f.stem),
                "title": d.get("title", "Sin título"),
                "url": d.get("url", ""),
                "product": detect_product(d.get("url",""), d.get("title","")),
                "has_downloads": bool(d.get("downloads")),
                "has_images": bool(d.get("images")),
                "snippet": snippet,
            })
        except Exception:
            continue

    _articles_cache = articles

    # Build category counts
    cats: dict = {}
    for a in articles:
        p = a["product"]
        cats.setdefault(p, 0)
        cats[p] += 1
    _categories_cache = cats


# ── Routes ───────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    groq_ok = False
    kb_count = 0
    try:
        from groq import Groq
        key = os.getenv("GROQ_API_KEY_1", "")
        if key:
            client = Groq(api_key=key)
            client.models.list()
            groq_ok = True
    except Exception:
        groq_ok = bool(os.getenv("GROQ_API_KEY_1", ""))

    try:
        import chromadb
        v2_path = str(BASE_DIR / "data" / "vectors")
        client = chromadb.PersistentClient(path=v2_path)
        try:
            col = client.get_collection("documentation_v2")
            kb_count = col.count()
        except Exception:
            pass
        if kb_count == 0:
            leg_path = str(BASE_DIR / "data" / "vectors_legacy")
            if Path(leg_path).exists():
                lc = chromadb.PersistentClient(path=leg_path)
                try:
                    lc2 = lc.get_collection("documentation")
                    kb_count = lc2.count()
                except Exception:
                    pass
    except Exception:
        pass

    _load_articles_cache()
    return jsonify({
        "groq_ok": groq_ok,
        "kb_count": kb_count,
        "local_articles": len(_articles_cache),
        "status": "ok"
    })


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    image_b64 = data.get("image_b64")
    product = data.get("product") or None

    if not question:
        return jsonify({"error": "Pregunta vacía"}), 400

    try:
        from agents.query_v2 import query
        result = query(question, image_b64=image_b64, product_filter=product)
        return jsonify({
            "answer": result.answer,
            "sources": result.sources,
            "model": result.model_used,
            "response_time": result.response_time,
            "error": result.error,
        })
    except Exception as e:
        return jsonify({"error": str(e), "answer": f"Error interno: {e}"}), 500


@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(silent=True) or {}
    query_text = (data.get("query") or "").strip()
    top_k = min(int(data.get("top_k", 10)), 20)

    if not query_text:
        return jsonify({"results": []}), 400

    try:
        from agents.vectorizer_v2 import run_query
        results = run_query(query_text, top_k=top_k)
        simplified = [{
            "title": r.get("title", ""),
            "chunk": r.get("chunk", ""),
            "chunk_type": r.get("chunk_type", "text"),
            "heading": r.get("heading", ""),
            "score": r.get("score", 0),
            "url": r.get("url", ""),
            "url_hash": r.get("url", ""),
        } for r in results]
        return jsonify({"results": simplified, "count": len(simplified)})
    except Exception as e:
        return jsonify({"error": str(e), "results": []}), 500


@app.route("/api/library/categories")
def api_library_categories():
    """Returns product categories with article counts from local raw data."""
    _load_articles_cache()
    cats = [
        {"id": k, "count": v}
        for k, v in sorted(_categories_cache.items(), key=lambda x: -x[1])
    ]
    return jsonify({"categories": cats, "total": len(_articles_cache)})


@app.route("/api/library/articles")
def api_library_articles():
    """Returns paginated articles for a product category."""
    _load_articles_cache()
    product = request.args.get("product", "")
    page = max(1, int(request.args.get("page", 1)))
    per_page = 20

    if product:
        filtered = [a for a in _articles_cache if a["product"] == product]
    else:
        filtered = _articles_cache

    total = len(filtered)
    start = (page - 1) * per_page
    page_items = filtered[start:start + per_page]

    return jsonify({
        "articles": page_items,
        "total": total,
        "page": page,
        "pages": (total + per_page - 1) // per_page,
    })


@app.route("/api/library/article/<url_hash>")
def api_library_article(url_hash: str):
    """Returns full article content from local raw JSON."""
    raw_file = RAW_DIR / f"{url_hash}.json"
    if not raw_file.exists():
        # Try finding by url_hash field
        for f in RAW_DIR.glob("*.json"):
            try:
                with open(f) as fh:
                    d = json.load(fh)
                if d.get("url_hash") == url_hash:
                    raw_file = f
                    break
            except Exception:
                continue

    if not raw_file.exists():
        return jsonify({"error": "Artículo no encontrado"}), 404

    try:
        with open(raw_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return jsonify({
            "title": data.get("title", ""),
            "url": data.get("url", ""),
            "text": data.get("text", ""),
            "images": data.get("images", []),
            "downloads": data.get("downloads", []),
            "related_links": data.get("related_links", []),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGES_DIR, filename)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": "2.0"})


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 3050))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    print(f"[SophosLLM] Starting on http://0.0.0.0:{port}")
    _load_articles_cache()  # precarga en inicio
    app.run(host="0.0.0.0", port=port, debug=debug)
