#!/usr/bin/env python3
"""
Query Agent v2
==============
RAG pipeline mejorado con:
  - Detección de intención (download vs texto)
  - Imágenes asignadas por chunk (no por página)
  - Links relacionados en respuesta
  - Análisis de imagen adjunta (visión)
  - Rotación automática de Groq keys
"""

import json
import os
import time
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent.absolute()
load_dotenv(BASE_DIR / ".env")
sys.path.insert(0, str(BASE_DIR))

# ── Config ────────────────────────────────────────────────────────
TOP_K = int(os.getenv("TOP_K_RESULTS", "15"))
GROQ_KEYS = [os.getenv(f"GROQ_API_KEY_{i}", "") for i in range(1, 7)]
GROQ_KEYS = [k for k in GROQ_KEYS if k]
PRIMARY_MODEL = os.getenv("GROQ_PRIMARY_MODEL", "llama-3.3-70b-versatile")
FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
VISION_MODEL = "llama-3.2-90b-vision-preview"

DOWNLOAD_INTENT_RE = re.compile(
    r'(descargar|download|instalar|install|\.exe|\.msi|\.bat|\.pkg|\.dmg|'
    r'agente|agent|cliente|client|setup|installer|firmware|actualizar|update)',
    re.IGNORECASE
)

# Detecta URLs de descarga embebidas en texto de chunks
DL_URL_RE = re.compile(
    r'https?://\S+\.(?:exe|msi|bat|cmd|sh|pkg|dmg|deb|rpm|zip|tgz|gz|iso)(?:\?\S*)?',
    re.IGNORECASE
)
DL_INLINE_RE = re.compile(
    r'\[([^\]]{3,60})\]\((https?://[^)]+\.(?:exe|msi|bat|cmd|sh|pkg|dmg|deb|rpm|zip))[^)]*\)',
    re.IGNORECASE
)

PRODUCT_MAP = {
    "firewall": "Sophos Firewall",
    "endpoint": "Sophos Endpoint",
    "server": "Sophos Server",
    "email": "Sophos Email",
    "xdr": "Sophos XDR",
    "mdr": "Sophos MDR",
    "ztna": "Sophos ZTNA",
    "intercept": "Sophos Intercept X",
}

SYSTEM_PROMPT = """Eres un experto senior en Sophos con 15 años de experiencia en seguridad de redes, firewalls, endpoints y servidores.
Tu misión es resolver dudas técnicas de forma precisa, clara y accionable.

REGLAS CRÍTICAS:
1. IDIOMA: Responde SIEMPRE en ESPAÑOL técnico. Sin excepciones.
2. MARCA: Usa SOLO los nombres oficiales de productos (Sophos Firewall, Sophos Endpoint, Sophos Intercept X, etc.). NUNCA digas "UTM".
3. ESTRUCTURA: Usa markdown. Para procedimientos usa pasos numerados. Para configuraciones usa bloques de código o tablas.
4. IMÁGENES: Si el contexto incluye una imagen (![alt](url)), inclúyela SOLO si es directamente relevante al paso que explicas. Añade una breve descripción de qué muestra.
5. DESCARGAS: Si hay archivos descargables en el contexto, preséntalos en una sección "📥 Archivos Disponibles" con botones/links claros.
6. ARTÍCULOS RELACIONADOS: Si el contexto incluye artículos relacionados, añade una sección "🔗 Artículos Relacionados" al final.
7. HONESTIDAD: Si el contexto no tiene suficiente información, dilo claramente y sugiere qué términos buscar.
8. PROHIBIDO: No menciones fuentes con números ([1], [2]). La información debe fluir naturalmente."""


@dataclass
class QueryResult:
    answer: str
    sources: list[dict]
    model_used: str
    error: Optional[str] = None
    response_time: float = 0.0


_key_idx = 0


def get_next_key(offset: int = 0) -> str:
    global _key_idx
    if not GROQ_KEYS:
        return ""
    key = GROQ_KEYS[(_key_idx + offset) % len(GROQ_KEYS)]
    _key_idx = (_key_idx + 1) % len(GROQ_KEYS)
    return key


def detect_intent(query: str) -> str:
    """Returns 'download' or 'text'."""
    if DOWNLOAD_INTENT_RE.search(query):
        return "download"
    return "text"


def detect_product(query: str) -> Optional[str]:
    """Returns detected Sophos product filter or None."""
    q_lower = query.lower()
    for key, product in PRODUCT_MAP.items():
        if key in q_lower:
            return key
    return None


def extract_downloads_from_text(chunk_text: str) -> list[dict]:
    """Extract download links embedded in chunk text when metadata is empty."""
    downloads = []
    seen = set()
    # Match [label](url.ext)
    for m in DL_INLINE_RE.finditer(chunk_text):
        label, url = m.group(1), m.group(2)
        if url not in seen:
            seen.add(url)
            downloads.append({"text": label.strip(), "url": url})
    # Match bare URLs ending in download extension
    for url in DL_URL_RE.findall(chunk_text):
        if url not in seen:
            seen.add(url)
            ext = url.split('.')[-1].upper()[:5]
            downloads.append({"text": f"Archivo .{ext.lower()}", "url": url})
    return downloads


def retrieve(query: str, top_k: int = TOP_K, intent: str = "text") -> list[dict]:
    """Query ChromaDB — always fetches download_section chunks in parallel."""
    try:
        from agents.vectorizer_v2 import run_query

        # Always get regular results
        results = run_query(query, top_k=top_k, chunk_type_filter=None)

        # Additionally, always fetch download_section chunks for this query
        dl_results = run_query(query, top_k=6, chunk_type_filter="download_section")

        # Merge: deduplicate by (url, chunk[:80])
        seen = {(r["url"], r["chunk"][:80]) for r in results}
        for r in dl_results:
            k = (r["url"], r["chunk"][:80])
            if k not in seen:
                seen.add(k)
                results.append(r)

        return results[:top_k + 6]
    except Exception:
        return []


def translate_to_english(text: str) -> str:
    """Translate query to English for bilingual search."""
    try:
        from groq import Groq
        client = Groq(api_key=get_next_key(offset=2))
        resp = client.chat.completions.create(
            model=FALLBACK_MODEL,
            messages=[
                {"role": "system", "content": "Translate to English technical terms only. Return ONLY the translation, no explanation."},
                {"role": "user", "content": text}
            ],
            temperature=0,
            max_tokens=60
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return text


def analyze_image(image_b64: str, question: str) -> str:
    """Analyze uploaded screenshot with vision model."""
    try:
        from groq import Groq
        client = Groq(api_key=get_next_key(offset=len(GROQ_KEYS) - 1))
        resp = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Analiza esta captura de pantalla de Sophos en ESPAÑOL. Describe errores, configuraciones o interfaces visibles. La pregunta del usuario es: '{question}'."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }],
            temperature=0.1
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[No se pudo analizar la imagen: {e}]"


def build_context(results: list[dict], max_chars: int = 22000) -> str:
    """Build LLM context from retrieved chunks."""
    parts = []
    current_chars = 0

    for i, r in enumerate(results, 1):
        chunk_text = r["chunk"]
        heading = r.get("heading", "")

        entry_parts = [f"[CHUNK {i}]"]
        if heading:
            entry_parts.append(f"Sección: {heading}")
        entry_parts.append(chunk_text)

        # Embed image if available
        if r.get("image"):
            img = r["image"]
            entry_parts.append(f"![{img['alt']}]({img['url']})")

        # Downloads from metadata, or extracted from chunk text as fallback
        downloads = r.get("downloads") or extract_downloads_from_text(chunk_text)
        if downloads:
            dl_lines = ["Archivos disponibles:"]
            for dl in downloads[:5]:
                dl_lines.append(f"- [{dl['text']}]({dl['url']})")
            entry_parts.append("\n".join(dl_lines))
            # Persist back to result so frontend can render buttons
            r["downloads"] = downloads

        entry = "\n".join(entry_parts) + "\n"

        if current_chars + len(entry) > max_chars:
            break

        parts.append(entry)
        current_chars += len(entry)

    return "\n---\n".join(parts)


def build_related_links(results: list[dict]) -> list[dict]:
    """Collect unique related links from all results."""
    seen = set()
    links = []
    for r in results:
        for link in r.get("related_links", []):
            url = link.get("url", "")
            if url and url not in seen:
                seen.add(url)
                links.append(link)
    return links[:8]


def query(
    question: str,
    top_k: int = TOP_K,
    image_b64: Optional[str] = None,
    product_filter: Optional[str] = None
) -> QueryResult:
    """Main RAG query function."""
    t_start = time.time()

    # 1. Vision analysis if image provided
    vision_context = ""
    if image_b64:
        vision_context = analyze_image(image_b64, question)
        if vision_context and not vision_context.startswith("[No se pudo"):
            question = f"{question}\n[Análisis de captura: {vision_context}]"

    # 2. Detect intent and product
    intent = detect_intent(question)
    detected_product = product_filter or detect_product(question)

    # 3. Search in Spanish
    results_es = retrieve(question, top_k=top_k, intent=intent)

    # 4. Search in English (bilingual)
    eng_query = translate_to_english(question)
    results_en = retrieve(eng_query, top_k=top_k, intent=intent) if eng_query != question else []

    # 5. Merge and deduplicate
    combined = {}
    for r in (results_es + results_en):
        key = (r["url"], r["chunk"][:100])
        if key not in combined or r["score"] > combined[key]["score"]:
            combined[key] = r

    final_results = sorted(combined.values(), key=lambda x: x["score"], reverse=True)[:top_k]

    if not final_results:
        return QueryResult(
            answer="No encontré información específica en la base de conocimientos de Sophos para esta consulta. "
                   "¿Podrías ser más específico sobre el producto o error que estás viendo?",
            sources=[],
            model_used=PRIMARY_MODEL,
        )

    # 6. Build context
    context = build_context(final_results)
    related_links = build_related_links(final_results)

    # 7. Prepare user message
    related_section = ""
    if related_links:
        related_section = "\n\nARTÍCULOS RELACIONADOS DISPONIBLES:\n" + \
            "\n".join(f"- [{l['text']}]({l['url']})" for l in related_links)

    user_content = (
        f"Contexto de la documentación Sophos:\n{context}{related_section}\n\n"
        f"Pregunta: {question}\n\n"
        f"Instrucción: Responde en ESPAÑOL. Incluye imágenes solo si son relevantes. "
        f"Muestra archivos descargables si los hay. Incluye artículos relacionados al final si existen."
    )

    # 8. Call Groq with retry/fallback
    models_to_try = [(PRIMARY_MODEL, get_next_key()), (FALLBACK_MODEL, get_next_key(offset=1))]

    for model, api_key in models_to_try:
        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.15,
                max_tokens=2048,
            )
            answer = resp.choices[0].message.content
            elapsed = round(time.time() - t_start, 2)
            return QueryResult(
                answer=answer,
                sources=final_results,
                model_used=model,
                response_time=elapsed,
            )
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                continue
            return QueryResult(
                answer=f"Error al procesar la consulta: {e}",
                sources=final_results,
                model_used=model,
                error=str(e),
            )

    return QueryResult(
        answer="Se alcanzó el límite de consultas. Por favor espera un momento e intenta nuevamente.",
        sources=final_results,
        model_used=PRIMARY_MODEL,
        error="rate_limit_all_keys",
    )


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--q", required=True, help="Pregunta a consultar")
    p.add_argument("--product", type=str, help="Filtro de producto (firewall, endpoint, etc.)")
    args = p.parse_args()
    result = query(args.q, product_filter=args.product)
    print(f"\nModelo: {result.model_used} | Tiempo: {result.response_time}s")
    print("─" * 60)
    print(result.answer)
