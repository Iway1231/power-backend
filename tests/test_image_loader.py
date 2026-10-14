import asyncio

import httpx
import numpy as np
import pytest

from app import api, image_loader, ocr


class FakeStreamResponse:
    def __init__(self, chunks, content_length=None, status_code=200):
        self.status_code = status_code
        self.headers = {}
        if content_length is not None:
            self.headers["content-length"] = str(content_length)
        self._chunks = chunks
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "upstream error",
                request=httpx.Request("GET", "https://example.test"),
                response=httpx.Response(self.status_code),
            )

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


class FakeAsyncClient:
    response = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def build_request(self, method, url):
        return httpx.Request(method, url)

    async def send(self, request, stream=True):
        return self.response


@pytest.mark.asyncio
async def test_download_image_streams_and_closes_response(monkeypatch, tmp_path):
    response = FakeStreamResponse([b"abc", b"def"])
    FakeAsyncClient.response = response
    monkeypatch.setattr(image_loader.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.chdir(tmp_path)

    path = await image_loader.download_image("https://example.test/image.jpg")

    assert (tmp_path / path).read_bytes() == b"abcdef"
    assert response.closed


@pytest.mark.asyncio
async def test_download_image_removes_file_when_size_limit_is_exceeded(monkeypatch, tmp_path):
    response = FakeStreamResponse([b"abc"], content_length=image_loader.MAX_IMAGE_BYTES + 1)
    FakeAsyncClient.response = response
    monkeypatch.setattr(image_loader.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="maximum allowed size"):
        await image_loader.download_image("https://example.test/large.jpg")

    assert list((tmp_path / "images").iterdir()) == []
    assert response.closed


def test_ocr_passes_timeout_to_tesseract(monkeypatch):
    calls = []

    def fake_image_to_string(*args, **kwargs):
        calls.append(kwargs)
        return "08:00 по 12:00"

    monkeypatch.setattr(ocr.pytesseract, "image_to_string", fake_image_to_string)

    result = ocr.ocr_tile(np.zeros((20, 20, 3), dtype=np.uint8))

    assert result == "08:00 по 12:00"
    assert calls == [
        {
            "lang": "ukr+eng",
            "config": "--psm 6",
            "timeout": ocr.TESSERACT_TIMEOUT_SECONDS,
        }
    ]


@pytest.mark.asyncio
async def test_api_removes_downloaded_image_after_ocr_error(monkeypatch, tmp_path):
    image_path = tmp_path / "downloaded.jpg"
    image_path.write_bytes(b"image")
    monkeypatch.setattr(api, "download_image", lambda url: asyncio.sleep(0, result=str(image_path)))
    monkeypatch.setattr(
        api.asyncio,
        "to_thread",
        lambda function, *args: asyncio.sleep(0, result=_raise_runtime_error()),
    )
    monkeypatch.setattr(api, "_status_cache", None)
    monkeypatch.setattr(api, "_status_cache_time", 0)
    monkeypatch.setattr(
        api,
        "fetch_latest_posts",
        lambda limit=20: asyncio.sleep(
            0,
            result=[{"text": "", "image": "https://example.test/image.jpg"}],
        ),
    )
    monkeypatch.setattr(api, "parse_power_text", lambda text: None)

    with pytest.raises(api.StatusRefreshUnavailable):
        await api._fetch_power_status()

    assert not image_path.exists()


def _raise_runtime_error():
    raise RuntimeError("ocr failed")
