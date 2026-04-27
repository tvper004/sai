#!/usr/bin/env python3
"""
Vectorizer v2
=============
Lee raw JSONs enriquecidos, los chunquea con chunker_v2, genera embeddings
y los almacena en ChromaDB con metadata mejorada.

Uso:
    python agents/vectorizer_v2.py --mode index
    python agents/vectorizer_v2.py --mode index --source /ruta/a/raw
    python agents/vectorizer_v2.py --mode query --q "cómo configurar VPN"
"""

import argparse
import json
import os
import hashlib
from pathlib import Path
from typing import Optional

from tqdm import tqdm

BASE_DIR = Path(__file__).parent.parent.absolute()
RAW_DIR = BASE_DIR / "data" / "raw"
IMAGES_DIR = BASE_DIR / "data" / "images"
VECTOR_DB_PATH = BASE_DIR / "data" / "vectors"
MANIFEST_FILE = IMAGES_DIR / "manifest.json"
COLLECTION_NAME = "documentation_v2"

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "400"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))


def get_collection():
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    embedding_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    VECTOR_DB_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(VECTOR_DB_PATH))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def doc_id(url_hash: str, chunk_idx: int) -> str:
    return f"{url_hash}__v2_{chunk_idx:04d}"


def is_indexed(collection, url_hash: str) -> bool:
    first_id = doc_id(url_hash, 0)
    results = collection.get(ids=[first_id])
    return len(results["ids"]) > 0


def load_manifest() -> dict:
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"images": {}}


def find_image_key_for_index(manifest: dict, images: list, img_index: Optional[int]) -> tuple[str, str]:
    """Find the manifest key for a raw image by its list index."""
    if img_index is None or not images:
        return "", ""
    if img_index >= len(images):
        return "", ""

    img = images[img_index]
    img_url = img.get("url", "")
    img_alt = img.get("alt", "")

    # Try to find in manifest by source_url match
    for key, record in manifest.get("images", {}).items():
        if record.get("source_url", "") == img_url or record.get("alt", "") == img_alt:
            return key, img_alt

    return "", img_alt


def run_index(raw_dir: Path = RAW_DIR):
    from agents.chunker_v2 import chunk_page

    collection = get_collection()
    manifest = load_manifest()

    raw_files = [f for f in raw_dir.glob("*.json") if not f.name.startswith(".")]
    if not raw_files:
        print(f"[VectorizerV2] No raw files found in {raw_dir}")
        return

    print(f"[VectorizerV2] Found {len(raw_files)} raw files. Collection: {COLLECTION_NAME}")

    total_chunks = 0
    skipped = 0
    new_docs = 0

    for raw_file in tqdm(raw_files, desc="Indexing", unit="page"):
        try:
            with open(raw_file, "r", encoding="utf-8") as f:
                page = json.load(f)
        except Exception:
            skipped += 1
            continue

        if page.get("error") or not page.get("text", "").strip():
            skipped += 1
            continue

        url_hash = page.get("url_hash", raw_file.stem)

        if is_indexed(collection, url_hash):
            skipped += 1
            continue

        chunks = chunk_page(page, max_words=CHUNK_SIZE, overlap_words=CHUNK_OVERLAP)
        if not chunks:
            skipped += 1
            continue

        images = page.get("images", [])
        downloads = page.get("downloads", [])
        related_links = page.get("related_links", [])
        url = page.get("url", "")
        title = page.get("title", "Sin título")

        ids = []
        documents = []
        metadatas = []

        for chunk in chunks:
            cid = doc_id(url_hash, chunk.chunk_index)
            img_key, img_alt = find_image_key_for_index(manifest, images, chunk.closest_image_index)

            # Include downloads only for download_section chunks or first chunk
            chunk_downloads = []
            if chunk.chunk_type == "download_section" or chunk.chunk_index == 0:
                chunk_downloads = downloads

            meta = {
                "url": url,
                "title": title,
                "url_hash": url_hash,
                "chunk_index": chunk.chunk_index,
                "chunk_type": chunk.chunk_type,
                "heading_context": chunk.heading_context or "",
                "image_key": img_key,
                "image_alt": img_alt,
                "downloads_json": json.dumps(chunk_downloads, ensure_ascii=False),
                "related_links_json": json.dumps(related_links[:10], ensure_ascii=False),
            }

            ids.append(cid)
            documents.append(chunk.text)
            metadatas.append(meta)

        # Batch insert
        batch_size = 100
        for b in range(0, len(ids), batch_size):
            collection.add(
                ids=ids[b:b + batch_size],
                documents=documents[b:b + batch_size],
                metadatas=metadatas[b:b + batch_size],
            )

        total_chunks += len(chunks)
        new_docs += 1

    print(f"\n[VectorizerV2] ✅ Done — new pages: {new_docs}, skipped: {skipped}, chunks: {total_chunks}")


def _get_legacy_collection():
    """Fallback: usa la DB del proyecto anterior si la v2 está vacía."""
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    legacy_path = BASE_DIR / "data" / "vectors_legacy"
    if not legacy_path.exists():
        return None
    try:
        embedding_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        client = chromadb.PersistentClient(path=str(legacy_path))
        col = client.get_collection("documentation", embedding_function=embedding_fn)
        return col if col.count() > 0 else None
    except Exception:
        return None


def run_query(query: str, top_k: int = 15, chunk_type_filter: Optional[str] = None) -> list[dict]:
    from sentence_transformers import SentenceTransformer

    manifest = load_manifest()
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embedding = model.encode([query]).tolist()

    # Decide qué colección usar
    collection = get_collection()
    using_legacy = False
    if collection.count() == 0:
        legacy = _get_legacy_collection()
        if legacy:
            collection = legacy
            using_legacy = True

    try:
        query_kwargs = dict(
            query_embeddings=embedding,
            n_results=min(top_k * 2, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        # where filter solo aplica a v2 (legacy no tiene chunk_type)
        if chunk_type_filter and not using_legacy:
            query_kwargs["where"] = {"chunk_type": chunk_type_filter}

        results = collection.query(**query_kwargs)
    except Exception as e:
        return []

    output = []
    if not results or not results["documents"]:
        return []

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    for doc, meta, dist in zip(docs, metas, dists):
        score = round(1 - dist, 4)

        # Imagen — schema v2 usa image_key; legacy usa image_keys (lista JSON)
        img_info = None
        if using_legacy:
            raw_keys = meta.get("image_keys", "[]")
            try:
                keys_list = json.loads(raw_keys) if isinstance(raw_keys, str) else raw_keys
            except Exception:
                keys_list = []
            if keys_list:
                img_key = keys_list[0]
                record = manifest.get("images", {}).get(img_key)
                if record:
                    fn = record.get("local_filename", record.get("filename", ""))
                    img_info = {"url": f"/api/images/{fn}", "alt": record.get("alt", "")}
        else:
            img_key = meta.get("image_key", "")
            if img_key:
                record = manifest.get("images", {}).get(img_key)
                if record:
                    img_info = {
                        "url": f"/api/images/{record['local_filename']}",
                        "alt": meta.get("image_alt", record.get("alt", "")),
                    }

        # Downloads — legacy guarda como string JSON en 'downloads'
        downloads = []
        try:
            raw_dl = meta.get("downloads_json", meta.get("downloads", "[]"))
            downloads = json.loads(raw_dl) if isinstance(raw_dl, str) else (raw_dl or [])
        except Exception:
            downloads = []

        output.append({
            "score": score,
            "url": meta.get("url", ""),
            "title": meta.get("title", ""),
            "chunk": doc,
            "chunk_type": meta.get("chunk_type", "text"),
            "heading": meta.get("heading_context", ""),
            "image": img_info,
            "downloads": downloads,
            "related_links": json.loads(meta.get("related_links_json", "[]"))
                if not using_legacy else [],
            "_source": "legacy" if using_legacy else "v2",
        })

    output.sort(key=lambda x: x["score"], reverse=True)
    return output[:top_k]


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(BASE_DIR))

    parser = argparse.ArgumentParser(description="Vectorizer v2")
    parser.add_argument("--mode", choices=["index", "query"], default="index")
    parser.add_argument("--source", type=Path, default=RAW_DIR)
    parser.add_argument("--q", type=str, help="Query string (query mode)")
    parser.add_argument("--top-k", type=int, default=15)
    parser.add_argument("--filter-type", type=str, choices=["text", "step_block", "download_section"],
                        help="Filter by chunk type")
    args = parser.parse_args()

    if args.mode == "index":
        run_index(raw_dir=args.source)
    elif args.mode == "query":
        if not args.q:
            print("Error: --q required in query mode")
            sys.exit(1)
        results = run_query(args.q, top_k=args.top_k, chunk_type_filter=args.filter_type)
        for i, r in enumerate(results, 1):
            print(f"\n{'─'*60}")
            print(f"[{i}] Score: {r['score']} | Type: {r['chunk_type']} | {r['title']}")
            print(f"    Heading: {r['heading']}")
            print(f"    Image: {r['image']}")
            print(f"    Downloads: {len(r['downloads'])}")
            print(f"    Related: {len(r['related_links'])}")
            print(f"    Text: {r['chunk'][:200]}...")
