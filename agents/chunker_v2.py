#!/usr/bin/env python3
"""
Chunker v2 — Semantic Chunking
================================
Divides Sophos documentation pages into semantic chunks:
  - Splits by H2/H3 headings (##, ###)
  - Detects numbered steps (1., Step 1, Paso 1)
  - Detects download sections
  - Assigns the CLOSEST image to each chunk (not all images to all chunks)

Each chunk includes: text, chunk_type, heading_context, char_start, char_end,
                     closest_image_index (for proximity mapping).
"""

import re
from dataclasses import dataclass, field
from typing import Optional


DOWNLOAD_KEYWORDS = re.compile(
    r'(download|descargar|install(er)?|\.exe|\.msi|\.bat|\.pkg|\.dmg|\.sh|\.deb|\.rpm)',
    re.IGNORECASE
)
HEADING_RE = re.compile(r'^(#{1,3})\s+(.+)$', re.MULTILINE)
STEP_RE = re.compile(r'^(\d+[\.\)]\s+|step\s+\d+|paso\s+\d+)', re.IGNORECASE | re.MULTILINE)


@dataclass
class Chunk:
    text: str
    chunk_type: str          # "text" | "step_block" | "download_section"
    heading_context: str     # Parent heading for this chunk
    char_start: int          # Character offset in original page text
    char_end: int
    chunk_index: int = 0

    # Assigned after proximity analysis
    closest_image_index: Optional[int] = None  # index into page's images list
    closest_image_alt: str = ""


def classify_chunk(text: str) -> str:
    """Determine chunk type from content."""
    if DOWNLOAD_KEYWORDS.search(text) and ('.exe' in text.lower() or
       '.msi' in text.lower() or 'download' in text.lower() or
       'descargar' in text.lower()):
        return "download_section"
    if STEP_RE.match(text.strip()):
        return "step_block"
    return "text"


def split_by_headings(text: str) -> list[tuple[str, str, int, int]]:
    """
    Split text into sections by H1/H2/H3 headings.
    Returns list of (heading_context, section_text, char_start, char_end).
    """
    sections = []
    heading_positions = [(m.start(), m.group(2), m.end()) for m in HEADING_RE.finditer(text)]

    if not heading_positions:
        # No headings found — return whole text as single section
        return [("", text, 0, len(text))]

    # Text before first heading
    if heading_positions[0][0] > 0:
        pre = text[:heading_positions[0][0]].strip()
        if pre:
            sections.append(("", pre, 0, heading_positions[0][0]))

    for i, (start, heading, content_start) in enumerate(heading_positions):
        end = heading_positions[i + 1][0] if i + 1 < len(heading_positions) else len(text)
        section_text = text[content_start:end].strip()
        if section_text:
            sections.append((heading, section_text, content_start, end))

    return sections


def split_section_into_chunks(
    section_text: str,
    heading: str,
    section_start: int,
    max_words: int = 400,
    overlap_words: int = 40
) -> list[tuple[str, int, int]]:
    """
    Split a section into word-bounded chunks with overlap.
    Returns list of (chunk_text, char_start, char_end).
    """
    words = section_text.split()
    if not words:
        return []

    chunks = []
    word_positions = []
    pos = 0
    for word in words:
        idx = section_text.find(word, pos)
        word_positions.append(idx)
        pos = idx + len(word)

    start_word = 0
    while start_word < len(words):
        end_word = min(start_word + max_words, len(words))
        chunk_words = words[start_word:end_word]
        chunk_text = " ".join(chunk_words)

        # Absolute char positions
        abs_start = section_start + word_positions[start_word]
        abs_end = section_start + word_positions[end_word - 1] + len(words[end_word - 1])

        if chunk_text.strip():
            chunks.append((chunk_text, abs_start, abs_end))

        start_word += max_words - overlap_words

    return chunks


def assign_image_proximity(chunks: list[Chunk], images: list[dict]) -> list[Chunk]:
    """
    For each image in the page, find the closest chunk by char position.
    Each chunk gets at most ONE image (the closest one).
    """
    if not images or not chunks:
        return chunks

    # Estimate image position by scanning text for image alt text patterns
    # Since crawl4ai gives images with scores (position proxy), use score as proxy
    # Higher-index images tend to appear later in the page
    total_images = len(images)
    total_chunks = len(chunks)

    if total_images == 0:
        return chunks

    # Map image index → estimated char position in text
    # (linear approximation: image i is at position i/total * text_length)
    text_length = chunks[-1].char_end if chunks else 1

    image_positions = []
    for i, img in enumerate(images):
        est_pos = int((i / max(total_images - 1, 1)) * text_length)
        image_positions.append(est_pos)

    # For each image, find the nearest chunk
    for img_idx, img_pos in enumerate(image_positions):
        best_chunk_idx = min(
            range(len(chunks)),
            key=lambda ci: abs(((chunks[ci].char_start + chunks[ci].char_end) // 2) - img_pos)
        )
        # Only assign if chunk doesn't already have a closer image
        chunk = chunks[best_chunk_idx]
        if chunk.closest_image_index is None:
            chunk.closest_image_index = img_idx
            chunk.closest_image_alt = images[img_idx].get("alt", "")

    return chunks


def chunk_page(page: dict, max_words: int = 400, overlap_words: int = 40) -> list[Chunk]:
    """
    Main function: chunk a raw Sophos page JSON into semantic Chunk objects.
    """
    text = page.get("text", "").strip()
    images = page.get("images", [])

    if not text:
        return []

    sections = split_by_headings(text)
    all_chunks: list[Chunk] = []
    chunk_idx = 0

    for heading, section_text, sec_start, sec_end in sections:
        sub_chunks = split_section_into_chunks(
            section_text, heading, sec_start, max_words, overlap_words
        )
        for chunk_text, cs, ce in sub_chunks:
            ctype = classify_chunk(chunk_text)
            all_chunks.append(Chunk(
                text=chunk_text,
                chunk_type=ctype,
                heading_context=heading,
                char_start=cs,
                char_end=ce,
                chunk_index=chunk_idx,
            ))
            chunk_idx += 1

    # Assign images by proximity
    all_chunks = assign_image_proximity(all_chunks, images)

    return all_chunks


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            page = json.load(f)
        chunks = chunk_page(page)
        print(f"Total chunks: {len(chunks)}")
        for c in chunks[:5]:
            print(f"\n[{c.chunk_type}] heading='{c.heading_context}' img={c.closest_image_index}")
            print(c.text[:200], "...")
    else:
        print("Usage: python chunker_v2.py <raw_json_file>")
