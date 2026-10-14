import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

MAX_VIDEO_BYTES = 49_000_000
VIDEO_PLATFORMS = {
    "youtube",
    "tiktok",
    "instagram",
    "instagram-standalone",
    "facebook",
}


def _configuration() -> tuple[str, str]:
    base_url = os.environ.get("POSTIZ_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("POSTIZ_API_KEY", "")
    if not base_url or not api_key:
        raise RuntimeError("POSTIZ_BASE_URL y POSTIZ_API_KEY son obligatorios")
    return base_url, api_key


def _storage_video_url(video_url: str) -> None:
    public_base_url = os.environ.get("STORAGE_PUBLIC_BASE_URL", "")
    source = urlsplit(video_url)
    trusted = urlsplit(public_base_url)
    if (
        source.scheme != "https"
        or not source.hostname
        or source.username is not None
        or source.password is not None
        or source.port not in (None, 443)
        or trusted.scheme != "https"
        or not trusted.hostname
        or source.hostname.lower() != trusted.hostname.lower()
    ):
        raise ValueError(
            "video_url debe ser HTTPS y pertenecer al host de STORAGE_PUBLIC_BASE_URL"
        )


async def list_integrations() -> list[dict]:
    base_url, api_key = _configuration()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{base_url}/integrations",
            headers={"Authorization": api_key},
        )
        response.raise_for_status()
        integrations = response.json()
    if not isinstance(integrations, list):
        raise RuntimeError("Postiz devolvio una lista de integraciones invalida")
    return [
        item
        for item in integrations
        if isinstance(item, dict)
        and item.get("identifier") in VIDEO_PLATFORMS
        and isinstance(item.get("id"), str)
        and not item.get("disabled", False)
    ]


async def _upload_video(
    client: httpx.AsyncClient, base_url: str, api_key: str, video_url: str
) -> dict[str, str]:
    _storage_video_url(video_url)
    chunks = []
    size = 0
    async with client.stream("GET", video_url) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_VIDEO_BYTES:
                raise ValueError("El MP4 excede el limite de 49 MB de Postiz")
            chunks.append(chunk)
    video = b"".join(chunks)
    if len(video) < 12 or video[4:8] != b"ftyp":
        raise ValueError("video_url no contiene un archivo MP4 valido")

    response = await client.post(
        f"{base_url}/upload",
        headers={"Authorization": api_key},
        files={"file": ("video.mp4", video, "video/mp4")},
    )
    response.raise_for_status()
    uploaded = response.json()
    if (
        not isinstance(uploaded, dict)
        or not isinstance(uploaded.get("id"), str)
        or not isinstance(uploaded.get("path"), str)
    ):
        raise RuntimeError("Postiz devolvio datos de subida invalidos")
    return {"id": uploaded["id"], "path": uploaded["path"]}


def _default_settings(platform: str, title: str) -> dict:
    defaults = {
        "youtube": {
            "title": title,
            "type": "public",
            "selfDeclaredMadeForKids": False,
            "tags": [],
        },
        "tiktok": {
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "duet": False,
            "stitch": False,
            "comment": False,
            "autoAddMusic": False,
            "brand_content_toggle": False,
            "brand_organic_toggle": False,
            "content_posting_method": "DIRECT_POST",
        },
        "instagram": {"post_type": "reel", "collaborators": []},
        "instagram-standalone": {"post_type": "reel", "collaborators": []},
        "facebook": {},
    }
    return defaults[platform]


async def create_post(post: dict) -> dict:
    base_url, api_key = _configuration()
    platform = post["platform"]
    if platform not in VIDEO_PLATFORMS:
        raise ValueError(f"Publicacion de video no soportada para {platform}")

    metadata = post.get("metadata") or {}
    custom_settings = metadata.get("settings", {})
    if not isinstance(custom_settings, dict):
        raise ValueError("metadata.settings debe ser un objeto")
    settings = {**_default_settings(platform, post["title"]), **custom_settings}
    settings["__type"] = platform

    async with httpx.AsyncClient(timeout=120) as client:
        media = await _upload_video(
            client, base_url, api_key, str(post["video_url"])
        )
        publish_at = post.get("publish_at")
        payload = {
            "type": "schedule" if publish_at else "now",
            "date": publish_at or datetime.now(timezone.utc).isoformat(),
            "shortLink": False,
            "tags": metadata.get("tags", []),
            "posts": [
                {
                    "integration": {"id": post["integration_id"]},
                    "value": [
                        {
                            "content": metadata.get("content", post["title"]),
                            "image": [media],
                        }
                    ],
                    "settings": settings,
                }
            ],
        }
        response = await client.post(
            f"{base_url}/posts",
            json=payload,
            headers={"Authorization": api_key},
        )
        response.raise_for_status()
        result = response.json()
    if not isinstance(result, dict):
        raise RuntimeError("Postiz devolvio una respuesta con formato inesperado")
    return result
