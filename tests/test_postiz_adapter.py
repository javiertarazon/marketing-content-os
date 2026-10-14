import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(
    0, str(Path(__file__).parents[1] / "apps" / "publisher-service")
)
from adapters import postiz_adapter


def _mock_client(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    async_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        postiz_adapter.httpx,
        "AsyncClient",
        lambda **kwargs: async_client(transport=transport, **kwargs),
    )


def test_create_post_uploads_video_and_uses_postiz_public_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTIZ_BASE_URL", "https://postiz.example/public/v1")
    monkeypatch.setenv("POSTIZ_API_KEY", "test-postiz-key")
    monkeypatch.setenv("STORAGE_PUBLIC_BASE_URL", "https://cdn.example")
    mp4 = b"\x00\x00\x00\x18ftypisomfake-video"
    observed: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "postiz.example":
            assert request.headers["Authorization"] == "test-postiz-key"
        else:
            assert "Authorization" not in request.headers
        if request.url.path.endswith("/upload"):
            assert b"filename=\"video.mp4\"" in request.content
            assert mp4 in request.content
            return httpx.Response(
                200,
                json={"id": "uploaded-id", "path": "https://uploads.example/video.mp4"},
            )
        if request.url.path.endswith("/posts"):
            observed["payload"] = json.loads(request.content)
            return httpx.Response(200, json={"postIds": ["post-1"]})
        if request.url.path.endswith(".mp4"):
            return httpx.Response(200, content=mp4)
        raise AssertionError(f"Unexpected Postiz request: {request.url}")

    _mock_client(monkeypatch, handler)

    result = asyncio.run(
        postiz_adapter.create_post(
            {
                "video_url": "https://cdn.example/renders/video.mp4",
                "title": "Tema de prueba",
                "platform": "youtube",
                "integration_id": "youtube-channel",
                "publish_at": None,
                "metadata": {"content": "Descripción de prueba"},
            }
        )
    )

    assert result == {"postIds": ["post-1"]}
    payload = observed["payload"]
    assert payload["type"] == "now"
    assert payload["posts"][0]["integration"]["id"] == "youtube-channel"
    assert payload["posts"][0]["value"][0]["content"] == "Descripción de prueba"
    assert payload["posts"][0]["value"][0]["image"][0]["id"] == "uploaded-id"
    assert payload["posts"][0]["settings"]["__type"] == "youtube"
    assert payload["posts"][0]["settings"]["title"] == "Tema de prueba"


def test_create_post_rejects_video_outside_configured_storage_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTIZ_BASE_URL", "https://postiz.example/public/v1")
    monkeypatch.setenv("POSTIZ_API_KEY", "test-postiz-key")
    monkeypatch.setenv("STORAGE_PUBLIC_BASE_URL", "https://cdn.example")
    _mock_client(
        monkeypatch,
        lambda request: (_ for _ in ()).throw(
            AssertionError("No se debe descargar una URL fuera del almacenamiento")
        ),
    )

    with pytest.raises(ValueError, match="STORAGE_PUBLIC_BASE_URL"):
        asyncio.run(
            postiz_adapter.create_post(
                {
                    "video_url": "https://127.0.0.1/private.mp4",
                    "title": "No permitido",
                    "platform": "youtube",
                    "integration_id": "youtube-channel",
                    "metadata": {},
                }
            )
        )
