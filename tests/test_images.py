from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import main
from main import fetch_all_images, make_thumbnail_url


def _build_items(start_id: int, count: int) -> list[dict]:
    return [
        {
            "id": start_id + i,
            "title": f"image_{start_id + i}",
            "download_url": (
                f"https://d1pxeqjdb63hyy.cloudfront.net/media/"
                f"original_images/image{start_id + i}.png"
            ),
        }
        for i in range(count)
    ]


@pytest.fixture
def mock_api_response(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    pages = {
        0: {"meta": {"total_count": 50}, "items": _build_items(589, 20)},
        20: {"meta": {"total_count": 50}, "items": _build_items(609, 20)},
        40: {"meta": {"total_count": 50}, "items": _build_items(629, 10)},
    }

    async def mock_get(url: str, params: dict | None = None):
        params = params or {}
        offset = int(params.get("offset", 0))
        data = pages[offset]
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value=data)
        return response

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.aclose = AsyncMock()

    def _client_factory(*args, **kwargs):
        return mock_client

    monkeypatch.setattr(main, "WAGTAIL_API_BASE", "https://example.test/api/v2/images/")
    monkeypatch.setattr(httpx, "AsyncClient", _client_factory)
    return mock_client


@pytest.mark.asyncio
async def test_image_count(mock_api_response: MagicMock) -> None:
    images = await fetch_all_images()
    assert len(images) == 50


@pytest.mark.asyncio
async def test_last_image_id(mock_api_response: MagicMock) -> None:
    images = await fetch_all_images()
    assert images[-1]["id"] == 638


def test_thumbnail_url_transform() -> None:
    original = "https://d1pxeqjdb63hyy.cloudfront.net/media/original_images/image0.png"
    expected = "https://d1pxeqjdb63hyy.cloudfront.net/media/images/image0.max-165x165.png"
    assert make_thumbnail_url(original) == expected
