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
NOTE_EXTENSIONS = {".md", ".txt", ".markdown"}
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
    if ext in NOTE_EXTENSIONS:
        return "note"
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


def gemini_analyze_note(text_content: str, filename: str, api_key: str) -> dict[str, Any]:
    """Analyze a text/markdown note via Gemini and return structured metadata."""
    # Truncate very long notes to ~8000 chars for the prompt
    truncated = text_content[:8000]

    prompt = (
        "You are a knowledge analysis engine for a creative design studio's Second Brain.\n\n"
        "Analyze this text note and return a JSON object with:\n"
        "1. \"keywords\": A list of 6-10 hashtag keywords. Each must start with '#', lowercase, no spaces. "
        "Extract the core concepts, themes, references, and design philosophies mentioned. "
        "NEVER use generic words like #inspiration, #design, #note, #text, #writing.\n"
        "2. \"summary\": A 2-3 sentence summary of the note's main ideas and creative significance.\n"
        "3. \"mood\": A comma-separated string of 2-4 conceptual descriptors (e.g., 'philosophical, provocative, introspective').\n"
        "4. \"title\": Extract or generate a concise 2-6 word title for this note.\n"
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
                print(f"           → Title: {analysis.get('title', '?')}")
                print(f"           → Keywords: {', '.join(analysis.get('keywords', []))}")

            elif ftype == "note":
                text_content = fpath.read_text(encoding="utf-8", errors="replace")
                full_text = text_content
                analysis = gemini_analyze_note(text_content, fpath.name, api_key)
                print(f"           → Title: {analysis.get('title', '?')}")
                print(f"           → Keywords: {', '.join(analysis.get('keywords', []))}")

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
                print(f"           → Title: {analysis.get('title', '?')}")

            # Upload to Modal
            result = upload_brain_item(
                brain_id=brain_id,
                item_type=ftype,
                source_file=rel,
                image_base64=image_b64,
                mime_type=mime,
                analysis=analysis,
                full_text=full_text,
            )

            if result.get("ok"):
                print(f"           ✓ Synced to Modal (brain_id: {brain_id})")
                # Update local index
                existing[rel] = {
                    "local_path": rel,
                    "brain_id": brain_id,
                    "type": ftype,
                    "status": "synced",
                    "synced_at": utc_now(),
                    "hash": entry["hash"],
                    "title": analysis.get("title", fpath.name),
                }
                synced += 1
            else:
                print(f"           ✗ Upload failed: {result.get('error', 'unknown')}")
                errors += 1

        except Exception as exc:
            print(f"           ✗ Error: {exc}")
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


# ── CLI Entry Point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync local brain/ folder to Areopagus Second Brain")
    parser.add_argument("--force", action="store_true", help="Re-process all files, ignoring cache")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be synced without doing it")
    args = parser.parse_args()
    sync(force=args.force, dry_run=args.dry_run)
