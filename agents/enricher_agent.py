#!/usr/bin/env python3
"""
Enricher Agent v2
=================
Lee los raw JSONs existentes y los enriquece con:
  1. related_links: artículos relacionados extraídos de la página
  2. downloads completados: si faltaban archivos descargables

Usa requests + BeautifulSoup (liviano, sin crawl4ai/JavaScript).
Solo hace GET simple — suficiente para extraer links del HTML estático.

Uso:
    python agents/enricher_agent.py
    python agents/enricher_agent.py --source /ruta/a/raw --workers 3
"""

import argparse
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

BASE_DIR = Path(__file__).parent.parent.absolute()
DEFAULT_RAW_DIR = BASE_DIR / "data" / "raw"

DOWNLOAD_EXTS = {".exe", ".msi", ".bat", ".cmd", ".sh", ".zip",
                 ".iso", ".tgz", ".gz", ".pkg", ".dmg", ".deb", ".rpm"}

SOPHOS_DOMAINS = {"docs.sophos.com", "support.sophos.com", "community.sophos.com"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SophosDocBot/2.0)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def is_download_url(url: str) -> bool:
    path = url.lower().split("?")[0]
    return any(path.endswith(ext) for ext in DOWNLOAD_EXTS)


def extract_sophos_links(soup: BeautifulSoup, base_url: str) -> tuple[list, list]:
    """Returns (related_links, downloads) from parsed HTML."""
    from urllib.parse import urljoin, urlparse

    related_links = []
    downloads = []
    seen_urls = set()

    # Extract all links
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue

        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        text = a.get_text(strip=True) or a.get("title", "") or "Enlace"
        text = text[:120]

        # Classify as download
        if is_download_url(full_url):
            downloads.append({"text": text, "url": full_url})

        # Classify as related Sophos article
        elif parsed.netloc in SOPHOS_DOMAINS and len(parsed.path) > 5:
            # Skip navigation/menu links (too short text or generic)
            if len(text) > 5 and text.lower() not in {
                "next", "previous", "back", "home", "top", "menu",
                "siguiente", "anterior", "inicio"
            }:
                related_links.append({"text": text, "url": full_url})

    # Limit to avoid noise
    return related_links[:20], downloads[:15]


def enrich_file(json_path: Path, delay: float = 0.5) -> dict:
    """Process a single raw JSON file. Returns status dict."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"file": json_path.name, "status": "error", "reason": f"Read error: {e}"}

    # Skip error pages
    if data.get("error") or not data.get("url"):
        return {"file": json_path.name, "status": "skipped", "reason": "error page"}

    # Skip if already enriched
    if data.get("enriched_at"):
        return {"file": json_path.name, "status": "already_done"}

    url = data["url"]

    try:
        resp = SESSION.get(url, timeout=10, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        related_links, new_downloads = extract_sophos_links(soup, url)
    except requests.RequestException as e:
        # Still mark as enriched (with empty data) to avoid retrying broken URLs
        data["related_links"] = []
        data["enriched_at"] = datetime.utcnow().isoformat() + "Z"
        data["enrich_error"] = str(e)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return {"file": json_path.name, "status": "fetch_error", "reason": str(e)}

    # Merge downloads (keep existing + new)
    existing_dl_urls = {d["url"] for d in data.get("downloads", [])}
    for dl in new_downloads:
        if dl["url"] not in existing_dl_urls:
            data.setdefault("downloads", []).append(dl)
            existing_dl_urls.add(dl["url"])

    data["related_links"] = related_links
    data["enriched_at"] = datetime.utcnow().isoformat() + "Z"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    time.sleep(delay)
    return {
        "file": json_path.name,
        "status": "ok",
        "related": len(related_links),
        "downloads": len(data.get("downloads", []))
    }


def run(raw_dir: Path = DEFAULT_RAW_DIR, workers: int = 3, delay: float = 0.8):
    raw_dir.mkdir(parents=True, exist_ok=True)
    files = [f for f in raw_dir.glob("*.json") if not f.name.startswith(".")]

    if not files:
        print(f"[EnricherAgent] No JSON files found in {raw_dir}")
        return

    # Filter: skip already enriched
    to_process = []
    already_done = 0
    for f in files:
        try:
            with open(f, "r") as fh:
                d = json.load(fh)
            if d.get("enriched_at"):
                already_done += 1
            else:
                to_process.append(f)
        except Exception:
            to_process.append(f)

    print(f"[EnricherAgent] Total: {len(files)} | Already enriched: {already_done} | To process: {len(to_process)}")

    if not to_process:
        print("[EnricherAgent] ✅ All files already enriched!")
        return

    stats = {"ok": 0, "error": 0, "skipped": 0, "fetch_error": 0}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(enrich_file, f, delay): f for f in to_process}
        with tqdm(total=len(to_process), desc="Enriching", unit="page") as pbar:
            for future in as_completed(futures):
                result = future.result()
                status = result.get("status", "error")
                stats[status if status in stats else "error"] += 1
                pbar.set_postfix(stats)
                pbar.update(1)

    print(f"\n[EnricherAgent] Done → {stats}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich raw Sophos JSON files")
    parser.add_argument("--source", type=Path, default=DEFAULT_RAW_DIR,
                        help="Directory with raw JSON files")
    parser.add_argument("--workers", type=int, default=3,
                        help="Parallel workers (be polite with Sophos servers)")
    parser.add_argument("--delay", type=float, default=0.8,
                        help="Delay in seconds between requests per worker")
    args = parser.parse_args()
    run(raw_dir=args.source, workers=args.workers, delay=args.delay)
