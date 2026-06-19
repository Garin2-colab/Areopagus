"""
sync_brain.py — Areopagus Second Brain Ingestion Pipeline

Scans the local brain/ folder for new or changed files,
analyzes them via Gemini, and uploads to the Modal volume.

Usage:
    python sync_brain.py                  # Sync all new/changed items
    python sync_brain.py --force          # Re-process everything
    python sync_brain.py --dry-run        # Show what would be synced
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Configuration ──────────────────────────────────────────────────────────────

BRAIN_DIR = Path(__file__).resolve().parent / "brain"
INDEX_PATH = BRAIN_DIR / ".brain-index.json"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
DOCUMENT_EXTENSIONS = {".md", ".txt", ".markdown"}
REFERENCE_EXTENSIONS = {".pdf"}

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODEL = "gemini-2.5-flash"

# ── Helpers ────────────────────────────────────────────────────────────────────


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def classify_file(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    if ext in REFERENCE_EXTENSIONS:
        return "reference"
    return None


def load_index() -> dict[str, Any]:
    if INDEX_PATH.exists():
        with INDEX_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {"version": 1, "items": []}


def save_index(index: dict[str, Any]) -> None:
    with INDEX_PATH.open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
        f.write("\n")


def get_api_key() -> str:
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not key:
        # Try loading from .env
        env_path = Path(__file__).resolve().parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("GOOGLE_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        print("ERROR: GOOGLE_API_KEY not found in environment or .env file.")
        sys.exit(1)
    return key


def get_mutate_url() -> str:
    """Resolve the Modal mutate-history endpoint URL."""
    env_path = Path(__file__).resolve().parent / "frontend" / ".env.local"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            for prefix in ("MODAL_SAVE_URL=", "MODAL_API_URL=", "MODAL_STATUS_URL=", "MODAL_HISTORY_URL="):
                if line.startswith(prefix):
                    ref_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if ref_url:
                        match = re.match(r"https://([a-zA-Z0-9-]+)--", ref_url)
                        if match:
                            username = match.group(1)
                            return f"https://{username}--areopagus-mutate-history-endpoint.modal.run"
    return "https://heebok-lee--areopagus-mutate-history-endpoint.modal.run"


# ── Gemini Analysis ───────────────────────────────────────────────────────────


def gemini_analyze_image(image_bytes: bytes, filename: str, api_key: str) -> dict[str, Any]:
    """Analyze an image via Gemini vision and return structured metadata."""
    prompt = (
        "You are a visual analysis engine for a creative design studio's Second Brain.\n\n"
        "Analyze this image thoroughly and return a JSON object with:\n"
        "1. \"keywords\": A list of 6-10 hashtag keywords. Each must start with '#', lowercase, no spaces. "
        "Be specific and descriptive (textures, materials, moods, movements, techniques). "
        "NEVER use generic words like #inspiration, #design, #image, #photo, #art, #aesthetic, #beautiful, #creative.\n"
        "2. \"summary\": A 2-3 sentence description of what the image depicts and its visual/conceptual significance for a design studio.\n"
        "3. \"mood\": A comma-separated string of 2-4 mood descriptors (e.g., 'austere, monumental, contemplative').\n"
        "4. \"color_palette\": A list of 3-5 hex color codes representing the dominant colors.\n"
        "5. \"title\": A short 2-5 word poetic title for this image.\n\n"
        f"Filename: {filename}\n\n"
        "Return ONLY the JSON object. No markdown fences, no commentary."
    )

    mime_type = "image/jpeg"
    ext = Path(filename).suffix.lower()
    if ext == ".png":
        mime_type = "image/png"
    elif ext == ".webp":
        mime_type = "image/webp"
    elif ext == ".gif":
        mime_type = "image/gif"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.5,
            "responseMimeType": "application/json",
        },
    }

    req = urllib.request.Request(
        url=f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={api_key}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode("utf-8"))

    text = ""
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            text += part.get("text", "")

    return _parse_json(text)


def gemini_analyze_document(text_content: str, filename: str, api_key: str) -> dict[str, Any]:
    """Analyze a text/markdown document via Gemini and return structured metadata."""
    # Truncate very long documents to ~8000 chars for the prompt
    truncated = text_content[:8000]

    prompt = (
        "You are a knowledge analysis engine for a creative design studio's Second Brain.\n\n"
        "Analyze this text document and return a JSON object with:\n"
        "1. \"keywords\": A list of 6-10 hashtag keywords. Each must start with '#', lowercase, no spaces. "
        "Extract the core concepts, themes, references, and design philosophies mentioned. "
        "NEVER use generic words like #inspiration, #design, #document, #text, #writing.\n"
        "2. \"summary\": A 2-3 sentence summary of the document's main ideas and creative significance.\n"
        "3. \"mood\": A comma-separated string of 2-4 conceptual descriptors (e.g., 'philosophical, provocative, introspective').\n"
        "4. \"title\": Extract or generate a concise 2-6 word title for this document.\n"
        "5. \"excerpt\": The first 200 characters of the most interesting/important passage.\n\n"
        f"Filename: {filename}\n\n"
        f"Content:\n{truncated}\n\n"
        "Return ONLY the JSON object. No markdown fences, no commentary."
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.5,
            "responseMimeType": "application/json",
        },
    }

    req = urllib.request.Request(
        url=f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={api_key}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode("utf-8"))

    text = ""
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            text += part.get("text", "")

    return _parse_json(text)


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


# ── Upload to Modal ───────────────────────────────────────────────────────────


def upload_brain_item(
    *,
    brain_id: str,
    item_type: str,
    source_file: str,
    image_base64: str | None,
    mime_type: str,
    analysis: dict[str, Any],
    full_text: str | None = None,
) -> dict[str, Any]:
    """Upload a brain item to the Modal mutate-history endpoint."""
    mutate_url = get_mutate_url()

    payload: dict[str, Any] = {
        "action": "upload_brain_item",
        "brain_id": brain_id,
        "type": item_type,
        "source_file": source_file,
        "keywords": analysis.get("keywords", []),
        "summary": analysis.get("summary", ""),
        "mood": analysis.get("mood", ""),
        "title": analysis.get("title", source_file),
        "color_palette": analysis.get("color_palette", []),
        "excerpt": analysis.get("excerpt", ""),
    }

    if image_base64:
        payload["image_base64"] = image_base64
        payload["mime_type"] = mime_type

    if full_text:
        payload["full_text"] = full_text

    req = urllib.request.Request(
        url=mutate_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"HTTP {exc.code} uploading brain item: {exc.reason}. {body}") from None


# ── Main Sync Logic ───────────────────────────────────────────────────────────


def scan_brain_folder() -> list[dict[str, Any]]:
    """Scan brain/ for all processable files."""
    files = []
    for root, _dirs, filenames in os.walk(BRAIN_DIR):
        root_path = Path(root)
        for fname in filenames:
            if fname.startswith("."):
                continue
            fpath = root_path / fname
            ftype = classify_file(fpath)
            if ftype is None:
                continue
            rel = fpath.relative_to(BRAIN_DIR).as_posix()
            files.append({
                "path": fpath,
                "relative": rel,
                "type": ftype,
                "hash": file_hash(fpath),
            })
    return files


def sync(*, force: bool = False, dry_run: bool = False) -> None:
    print("=" * 60)
    print("  AREOPAGUS SECOND BRAIN — Sync")
    print("=" * 60)

    api_key = get_api_key()
    index = load_index()
    existing = {item["local_path"]: item for item in index.get("items", [])}
    scanned = scan_brain_folder()

    to_process: list[dict[str, Any]] = []
    unchanged = 0

    for entry in scanned:
        rel = entry["relative"]
        prev = existing.get(rel)

        if force:
            to_process.append(entry)
        elif prev is None:
            to_process.append(entry)
        elif prev.get("hash") != entry["hash"]:
            to_process.append(entry)
        else:
            unchanged += 1

    print(f"\n  Scanned:   {len(scanned)} files")
    print(f"  New/Changed: {len(to_process)}")
    print(f"  Unchanged:   {unchanged}")
    print()

    if not to_process:
        print("  Nothing to sync. Brain is up to date.")
        return

    if dry_run:
        print("  DRY RUN — the following would be processed:")
        for entry in to_process:
            print(f"    [{entry['type']:>9}] {entry['relative']}")
        return

    synced = 0
    errors = 0

    for i, entry in enumerate(to_process, 1):
        rel = entry["relative"]
        ftype = entry["type"]
        fpath: Path = entry["path"]
        brain_id = f"brain_{int(time.time())}_{hashlib.md5(rel.encode()).hexdigest()[:6]}"

        print(f"  [{i}/{len(to_process)}] Processing {rel} ({ftype})...")

        try:
            analysis: dict[str, Any] = {}
            image_b64: str | None = None
            mime = "image/jpeg"
            full_text: str | None = None

            if ftype == "image":
                img_bytes = fpath.read_bytes()
                image_b64 = base64.b64encode(img_bytes).decode("ascii")
                ext = fpath.suffix.lower()
                if ext == ".png":
                    mime = "image/png"
                elif ext == ".webp":
                    mime = "image/webp"
                elif ext == ".gif":
                    mime = "image/gif"
                analysis = gemini_analyze_image(img_bytes, fpath.name, api_key)
                if "keywords" not in analysis or not isinstance(analysis["keywords"], list):
                    analysis["keywords"] = []
                if rel.startswith("references/"):
                    if "#reference" not in analysis["keywords"]:
                        analysis["keywords"].append("#reference")
                elif rel.startswith("images/"):
                    if "#image" not in analysis["keywords"]:
                        analysis["keywords"].append("#image")
                print(f"           -> Title: {analysis.get('title', '?')}")
                print(f"           -> Keywords: {', '.join(analysis.get('keywords', []))}")

            elif ftype == "document":
                text_content = fpath.read_text(encoding="utf-8", errors="replace")
                full_text = text_content
                analysis = gemini_analyze_document(text_content, fpath.name, api_key)
                print(f"           -> Title: {analysis.get('title', '?')}")
                print(f"           -> Keywords: {', '.join(analysis.get('keywords', []))}")

            elif ftype == "reference":
                # For PDFs — upload as binary, minimal analysis for now
                ref_bytes = fpath.read_bytes()
                image_b64 = base64.b64encode(ref_bytes).decode("ascii")
                mime = "application/pdf"
                analysis = {
                    "keywords": ["#reference", "#document"],
                    "summary": f"Reference document: {fpath.name}",
                    "mood": "reference",
                    "title": fpath.stem.replace("-", " ").replace("_", " ").title(),
                }
                print(f"           -> Title: {analysis.get('title', '?')}")

            # Determine logical type based on path for categorization/labeling
            if rel.startswith("references/"):
                item_type = "reference"
            elif rel.startswith("images/"):
                item_type = "image"
            elif rel.startswith("documents/"):
                item_type = "document"
            else:
                item_type = ftype

            # Upload to Modal
            result = upload_brain_item(
                brain_id=brain_id,
                item_type=item_type,
                source_file=rel,
                image_base64=image_b64,
                mime_type=mime,
                analysis=analysis,
                full_text=full_text,
            )

            if result.get("ok"):
                print(f"           [OK] Synced to Modal (brain_id: {brain_id})")
                # Update local index
                existing[rel] = {
                    "local_path": rel,
                    "brain_id": brain_id,
                    "type": item_type,
                    "status": "synced",
                    "synced_at": utc_now(),
                    "hash": entry["hash"],
                    "title": analysis.get("title", fpath.name),
                }
                synced += 1
            else:
                print(f"           [ERROR] Upload failed: {result.get('error', 'unknown')}")
                errors += 1

        except Exception as exc:
            print(f"           [ERROR] Error: {exc}")
            errors += 1

        # Small delay to avoid rate limits
        if i < len(to_process):
            time.sleep(1)

    # Save updated index
    index["items"] = list(existing.values())
    save_index(index)

    print()
    print(f"  Done. Synced: {synced}, Errors: {errors}")
    print("=" * 60)

    # Auto-synthesize Creative Briefs from clustered brain items
    if synced > 0:
        print()
        synthesize_briefs(api_key)


# ── Creative Brief Synthesis (Layer 2) ────────────────────────────────────────


def fetch_history_for_synthesis() -> dict[str, Any]:
    """Fetch current history from Modal to get all brain items."""
    env_path = Path(__file__).resolve().parent / "frontend" / ".env.local"
    api_url = ""
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("MODAL_API_URL="):
                api_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not api_url:
        print("  [briefs] WARNING: MODAL_API_URL not found, skipping synthesis.")
        return {}

    req = urllib.request.Request(
        url=api_url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"  [briefs] Failed to fetch history: {exc}")
        return {}


def cluster_brain_items(brain_items: list[dict[str, Any]], min_overlap: int = 2) -> list[list[dict[str, Any]]]:
    """
    Cluster brain items by keyword overlap.
    Two items belong in the same cluster if they share >= min_overlap keywords.
    Uses simple union-find/greedy clustering.
    """
    if not brain_items:
        return []

    # Build keyword sets per item
    item_keywords = []
    for item in brain_items:
        kws = {k.lower() for k in item.get("keywords", []) if isinstance(k, str)}
        item_keywords.append(kws)

    n = len(brain_items)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Merge items that share enough keywords
    for i in range(n):
        for j in range(i + 1, n):
            overlap = item_keywords[i].intersection(item_keywords[j])
            if len(overlap) >= min_overlap:
                union(i, j)

    # Group by root
    clusters: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        clusters.setdefault(root, []).append(i)

    # Return only clusters with 2+ items
    return [
        [brain_items[i] for i in indices]
        for indices in clusters.values()
        if len(indices) >= 2
    ]


def gemini_synthesize_brief(cluster: list[dict[str, Any]], api_key: str) -> dict[str, Any]:
    """Call Gemini to synthesize a Creative Brief from a cluster of brain items."""
    # Build context from the cluster
    items_context = []
    for item in cluster:
        entry = {
            "id": item.get("id", ""),
            "type": item.get("type", ""),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "mood": item.get("mood", ""),
            "keywords": item.get("keywords", []),
        }
        if item.get("excerpt"):
            entry["excerpt"] = item["excerpt"][:300]
        if item.get("color_palette"):
            entry["color_palette"] = item["color_palette"]
        items_context.append(entry)

    prompt = (
        "You are a creative synthesis engine for an autonomous design studio.\n\n"
        "Given these related brain items (images, notes, references), synthesize them into "
        "a single **Creative Brief** — an actionable design directive that AI agents will use "
        "to guide image generation.\n\n"
        "Brain items:\n"
        f"{json.dumps(items_context, indent=2, ensure_ascii=False)}\n\n"
        "Return a JSON object with:\n"
        "1. \"title\": A compelling 3-6 word title for this creative direction (e.g., 'Brutalist Textile Direction')\n"
        "2. \"thesis\": 2-3 sentences distilling the shared creative concept. Be specific and directorial — "
        "this will be injected into an image generation prompt.\n"
        "3. \"visual_rules\": An array of 3-6 concrete, actionable visual constraints "
        "(e.g., 'Monochrome palette: #2C2C2C, #8B8680', 'Harsh single-source directional lighting')\n"
        "4. \"mood\": Comma-separated mood descriptors (2-4 words)\n"
        "5. \"color_palette\": Array of 3-5 hex color codes representing the combined palette\n"
        "6. \"keywords\": 5-8 hashtag keywords that capture the synthesized direction\n\n"
        "The brief should feel like a creative director's written mandate — specific, opinionated, actionable.\n"
        "Return ONLY the JSON object. No markdown fences, no commentary."
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json",
        },
    }

    req = urllib.request.Request(
        url=f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={api_key}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode("utf-8"))

    text = ""
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            text += part.get("text", "")

    return _parse_json(text)


def upload_brief_to_modal(brief_id: str, synthesis: dict[str, Any], source_ids: list[str]) -> dict[str, Any]:
    """Upload a synthesized Creative Brief to Modal."""
    mutate_url = get_mutate_url()

    payload = {
        "action": "upload_brief",
        "brief_id": brief_id,
        "title": synthesis.get("title", ""),
        "thesis": synthesis.get("thesis", ""),
        "visual_rules": synthesis.get("visual_rules", []),
        "mood": synthesis.get("mood", ""),
        "color_palette": synthesis.get("color_palette", []),
        "source_items": source_ids,
        "keywords": synthesis.get("keywords", []),
    }

    req = urllib.request.Request(
        url=mutate_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"HTTP {exc.code} uploading brief: {exc.reason}. {body}") from None


def synthesize_briefs(api_key: str) -> None:
    """
    Layer 2 Synthesis: Cluster brain items by keyword overlap,
    synthesize Creative Briefs via Gemini, and upload to Modal.
    Fully automatic — no manual approval needed.
    """
    print("=" * 60)
    print("  LAYER 2 — Synthesizing Creative Briefs")
    print("=" * 60)

    history = fetch_history_for_synthesis()
    if not history:
        return

    brain_items = history.get("brain", [])
    existing_briefs = history.get("briefs", [])

    if len(brain_items) < 2:
        print("  Not enough brain items to synthesize (need at least 2).")
        return

    # Cluster brain items by keyword overlap
    clusters = cluster_brain_items(brain_items, min_overlap=2)
    print(f"  Found {len(clusters)} potential clusters from {len(brain_items)} brain items.")

    if not clusters:
        print("  No clusters with sufficient keyword overlap found.")
        return

    # Build a set of existing brief source combos to avoid re-synthesizing
    existing_source_sets = set()
    for brief in existing_briefs:
        source_key = frozenset(brief.get("source_items", []))
        existing_source_sets.add(source_key)

    synthesized = 0
    for i, cluster in enumerate(clusters, 1):
        source_ids = sorted([item["id"] for item in cluster])
        source_key = frozenset(source_ids)

        # Skip if we already have a brief for this exact cluster
        if source_key in existing_source_sets:
            print(f"  [{i}/{len(clusters)}] Cluster already has a brief, skipping.")
            continue

        print(f"  [{i}/{len(clusters)}] Synthesizing brief from {len(cluster)} items...")
        titles = [item.get("title", item.get("id", "?")) for item in cluster]
        print(f"           Sources: {', '.join(titles[:4])}")

        try:
            synthesis = gemini_synthesize_brief(cluster, api_key)
            brief_id = f"brief_{int(time.time())}_{hashlib.md5('_'.join(source_ids).encode()).hexdigest()[:6]}"

            print(f"           -> Title: {synthesis.get('title', '?')}")
            print(f"           -> Thesis: {synthesis.get('thesis', '?')[:80]}...")

            result = upload_brief_to_modal(brief_id, synthesis, source_ids)
            if result.get("ok"):
                print(f"           [OK] Brief uploaded: {brief_id}")
                synthesized += 1
                existing_source_sets.add(source_key)
            else:
                print(f"           [ERROR] Upload failed: {result.get('error', 'unknown')}")

        except Exception as exc:
            print(f"           [ERROR] Synthesis error: {exc}")

        # Rate limit
        if i < len(clusters):
            time.sleep(1)

    print()
    print(f"  Done. Synthesized {synthesized} new Creative Briefs.")
    print("=" * 60)


# ── CLI Entry Point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync local brain/ folder to Areopagus Second Brain")
    parser.add_argument("--force", action="store_true", help="Re-process all files, ignoring cache")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be synced without doing it")
    parser.add_argument("--briefs-only", action="store_true", help="Skip file sync, only re-synthesize briefs")
    args = parser.parse_args()

    if args.briefs_only:
        key = get_api_key()
        synthesize_briefs(key)
    else:
        sync(force=args.force, dry_run=args.dry_run)

