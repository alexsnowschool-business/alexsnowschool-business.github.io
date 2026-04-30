import hashlib
from pathlib import Path

import httpx


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_CONTENT_TYPE_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
    "image/gif": "gif",
}


async def download_image(url: str, dest_dir: Path, client: httpx.AsyncClient) -> Path | None:
    try:
        resp = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=20)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "").split(";")[0].strip()
        ext = _CONTENT_TYPE_EXT.get(content_type)
        if not ext:
            suffix = url.split("?")[0].rsplit(".", 1)[-1].lower()
            ext = suffix if suffix in {"jpg", "jpeg", "png", "webp", "avif"} else "jpg"
        if ext == "jpeg":
            ext = "jpg"

        name = hashlib.md5(url.encode()).hexdigest() + f".{ext}"
        path = dest_dir / name
        path.write_bytes(resp.content)
        return path
    except Exception:
        return None
