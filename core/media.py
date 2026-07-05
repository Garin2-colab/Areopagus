import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any, Tuple
from PIL import Image

from core.config import (
    IMAGE_DIR,
    WEBP_QUALITY,
)

def fetch_image_bytes(image_url: str) -> tuple[bytes, str]:
    if "id=" in image_url:
        try:
            parsed = urllib.parse.urlparse(image_url)
            query = urllib.parse.parse_qs(parsed.query)
            image_id = query.get("id", [None])[0]
            if image_id:
                if image_id.endswith(".webp") or image_id.endswith(".mp4"):
                    image_id = image_id.rsplit(".", 1)[0]
                mp4_path = IMAGE_DIR / f"{image_id}.mp4"
                if mp4_path.exists():
                    return mp4_path.read_bytes(), "video/mp4"
                local_path = IMAGE_DIR / f"{image_id}.webp"
                if local_path.exists():
                    return local_path.read_bytes(), "image/webp"
        except Exception as err:
            print(f"[fetch_image_bytes] local path check failed: {err}", flush=True)

    try:
        req = urllib.request.Request(
            image_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        from core.utils import urlopen_with_retry
        with urlopen_with_retry(req) as response:
            content_type = response.headers.get_content_type() or "image/png"
            return response.read(), content_type
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(
            f"HTTP {exc.code} fetching image {image_url}: {exc.reason}. Response: {body or '<empty>'}"
        ) from None


def save_mp4_video(video_url: str, image_id: str, aspect_ratio: str = "16:9") -> dict[str, Any]:
    video_bytes, source_mime_type = fetch_image_bytes(video_url)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    mp4_path = IMAGE_DIR / f"{image_id}.mp4"

    with open(mp4_path, "wb") as f:
        f.write(video_bytes)

    # Extract first frame as a companion webp thumbnail for image-based downstream tasks
    webp_path = IMAGE_DIR / f"{image_id}.webp"
    try:
        import subprocess
        subprocess.run([
            "ffmpeg", "-y", "-i", str(mp4_path),
            "-vframes", "1", "-f", "image2", str(webp_path)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        print(f"[save_mp4_video] Successfully extracted first frame to {webp_path}", flush=True)
    except Exception as exc:
        print(f"[save_mp4_video] Warning: Failed to extract first frame via ffmpeg: {exc}", flush=True)

    ratios = {
        "1:1": (480, 480),
        "4:3": (640, 480),
        "3:4": (360, 480),
        "16:9": (854, 480),
        "9:16": (270, 480),
        "21:9": (1120, 480),
    }
    width, height = ratios.get(aspect_ratio, (854, 480))

    try:
        from orchestrator import get_image
        web_url = get_image.get_web_url()
    except Exception:
        web_url = None

    if not web_url:
        web_url = "https://heebok-lee--areopagus-get-image.modal.run"

    web_url = web_url.rstrip("/")

    return {
        "path": str(mp4_path),
        "url": f"{web_url}/?id={image_id}",
        "format": "mp4",
        "source_mime_type": source_mime_type or "video/mp4",
        "size_bytes": mp4_path.stat().st_size,
        "dimensions": {
            "width": width,
            "height": height,
        },
    }


def save_webp_image(image_url: str, image_id: str) -> dict[str, Any]:
    image_bytes, source_mime_type = fetch_image_bytes(image_url)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    webp_path = IMAGE_DIR / f"{image_id}.webp"

    with Image.open(BytesIO(image_bytes)) as source:
        # Preserve original aspect ratio but scale down so the maximum dimension is 1080
        w, h = source.size
        if w > h:
            target_w = 1080
            target_h = int(1080 * (h / w))
        else:
            target_h = 1080
            target_w = int(1080 * (w / h))
        converted = source.convert("RGB").resize((target_w, target_h), Image.Resampling.LANCZOS)
        converted.save(webp_path, "WEBP", quality=WEBP_QUALITY, method=6)
        width, height = converted.size

    # Try to resolve get_image URL dynamically to make the app portable
    try:
        from orchestrator import get_image
        web_url = get_image.get_web_url()
    except Exception:
        web_url = None

    if not web_url:
        web_url = "https://heebok-lee--areopagus-get-image.modal.run"

    web_url = web_url.rstrip("/")

    return {
        "path": str(webp_path),
        "url": f"{web_url}/?id={image_id}",
        "format": "webp",
        "quality": WEBP_QUALITY,
        "source_mime_type": source_mime_type,
        "size_bytes": webp_path.stat().st_size,
        "dimensions": {
            "width": width,
            "height": height,
        },
    }
