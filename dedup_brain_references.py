"""
dedup_brain_references.py — Remove duplicate brain_* files from references/

The sync_brain pull mechanism re-downloaded brain item .webp files back into
brain/references/, creating duplicates alongside the original named files.

This script:
1. Identifies brain_* prefix files in references/ that are copies of originals
2. Deletes them from the remote Modal database
3. Removes the local files
4. Updates .brain-index.json
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BRAIN_DIR = Path(__file__).resolve().parent / "brain"
INDEX_PATH = BRAIN_DIR / ".brain-index.json"
REFERENCES_DIR = BRAIN_DIR / "references"


def get_areopagus_api_key() -> str:
    key = os.environ.get("AREOPAGUS_API_KEY", "").strip()
    if not key:
        env_path = Path(__file__).resolve().parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("AREOPAGUS_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return key


def get_mutate_url() -> str:
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


def delete_remote_brain_item(brain_id: str) -> bool:
    mutate_url = get_mutate_url()
    payload = {"action": "delete_brain_item", "id": brain_id}
    key = get_areopagus_api_key()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-API-Key"] = key

    req = urllib.request.Request(
        url=mutate_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("ok", False)
    except Exception as exc:
        print(f"  [ERROR] Failed to delete {brain_id}: {exc}")
        return False


def main(dry_run: bool = False):
    print("=" * 60)
    print("  BRAIN DEDUP — Removing duplicate brain_* reference files")
    print("=" * 60)

    if not INDEX_PATH.exists():
        print("  [ERROR] No .brain-index.json found.")
        return

    with INDEX_PATH.open("r", encoding="utf-8") as f:
        index = json.load(f)

    items = index.get("items", [])

    # Find all brain_* files in references/ that are duplicates of originals
    # Pattern: references/brain_XXXXXXXXXX_XXXXXX.webp
    brain_prefix_pattern = re.compile(r"^references/brain_\d+_[a-f0-9]+\.webp$")

    # Also find brain_* files that match original image brain IDs
    # e.g., references/brain_1781861367_3e8b1a.webp is a copy of the item
    #        originally synced from references/cho_reference_01.webp
    # The brain_id in the filename tells us which original it came from
    
    # Collect original items (non-brain_* prefix) and their brain_ids
    originals_by_brain_id: dict[str, dict] = {}
    duplicates: list[dict] = []

    for item in items:
        local_path = item.get("local_path", "")
        if not local_path.startswith("references/"):
            continue
        
        filename = local_path.split("/", 1)[1] if "/" in local_path else local_path
        if brain_prefix_pattern.match(local_path):
            duplicates.append(item)
        else:
            brain_id = item.get("brain_id", "")
            if brain_id:
                originals_by_brain_id[brain_id] = item

    # Also check: some insp_* files in references/ are similarly duplicated
    insp_prefix_pattern = re.compile(r"^references/insp_\d+\.webp$")
    insp_items = [item for item in items if insp_prefix_pattern.match(item.get("local_path", ""))]
    
    # These insp_* files were the ORIGINALS that got re-synced as brain_* duplicates.
    # The brain_* copies in references/ ARE the actual duplicates.

    if not duplicates:
        print("  No duplicate brain_* files found in references/. All clean!")
        return

    print(f"\n  Found {len(duplicates)} duplicate brain_* files in references/:")
    for dup in duplicates:
        print(f"    - {dup['local_path']}  (brain_id: {dup.get('brain_id', '?')})")

    if dry_run:
        print("\n  [DRY RUN] No changes made.")
        return

    # Delete from remote and remove local files
    deleted_count = 0
    for dup in duplicates:
        brain_id = dup.get("brain_id", "")
        local_path = dup.get("local_path", "")
        full_path = BRAIN_DIR / local_path

        # Delete from remote DB
        if brain_id:
            print(f"  Deleting remote: {brain_id} ({local_path})...")
            success = delete_remote_brain_item(brain_id)
            if success:
                print(f"    [OK] Deleted from remote.")
            else:
                print(f"    [WARN] Remote delete may have failed.")

        # Delete local file
        if full_path.exists():
            full_path.unlink()
            print(f"    [OK] Deleted local file: {local_path}")
        
        deleted_count += 1

    # Update index — remove deleted items
    dup_paths = {dup.get("local_path") for dup in duplicates}
    index["items"] = [item for item in items if item.get("local_path") not in dup_paths]

    with INDEX_PATH.open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\n  Done. Removed {deleted_count} duplicate items.")
    print(f"  Index updated: {len(index['items'])} items remaining.")
    print("=" * 60)


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
