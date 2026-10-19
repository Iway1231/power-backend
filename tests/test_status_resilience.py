import asyncio
import json
import os
import tempfile
import threading
import time

import httpx
import pytest

from app import api, image_loader, ocr
from app.models import PowerStatus


@pytest.fixture(autouse=True)
def clear_status_cache():
    api._status_cache = None
    api._status_cache_time = 0
    yield
    api._status_cache = None
    api._status_cache_time = 0


@pytest.mark.asyncio
async def test_health_remains_available_during_slow_ocr(monkeypatch, tmp_path, test_app):
    started = threading.Event()
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image")

    async def no_redis_get(_key):
        return None

    async def no_redis_set(_key, _value, _ttl):
        return False

    async def posts(**_kwargs):
        return [{"text": "", "image": "https://example.test/image.jpg"}]

    async def download(_url):
        return str(image_path)

    def slow_ocr(_path):
        started.set()
        time.sleep(0.35)
        return None

    monkeypatch.setattr(api._redis_store, "get_json", no_redis_get)
    monkeypatch.setattr(api._redis_store, "set_json", no_redis_set)
    monkeypatch.setattr(api, "fetch_latest_posts", posts)
    monkeypatch.setattr(api, "download_image", download)
    monkeypatch.setattr(api, "extract_schedule_from_image", slow_ocr)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as client:
        status_task = asyncio.create_task(api.refresh_power_status_once())
        assert await asyncio.wait_for(asyncio.to_thread(started.wait), timeout=1)
        health_response = await asyncio.wait_for(client.get("/api/v1/health"), timeout=0.2)
        refresh_result = await status_task

    assert health_response.status_code == 200
    assert refresh_result is False


@pytest.mark.asyncio
async def test_concurrent_status_requests_share_one_refresh(monkeypatch):
    calls = 0

    async def no_redis_get(_key):
        return None

    async def no_redis_set(_key, _value, _ttl):
        return False

    async def slow_posts(**_kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return [
            {
                "text": "Електроенергії немає з 23:00 по 23:30",
                "published_at": "2026-10-18T08:00:00+03:00",
            }
        ]

    monkeypatch.setattr(api._redis_store, "get_json", no_redis_get)
    monkeypatch.setattr(api._redis_store, "set_json", no_redis_set)
    monkeypatch.setattr(api, "fetch_latest_posts", slow_posts)

    assert await api.refresh_power_status_once()
    results = await asyncio.gather(*(api.get_power_status() for _ in range(8)))

    assert calls == 1
    assert all(isinstance(result, PowerStatus) for result in results)


@pytest.mark.asyncio
async def test_status_refresh_works_when_redis_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "FALLBACK_FILE", tmp_path / "last_status.json")

    async def unavailable_get(_key):
        return None

    async def unavailable_set(_key, _value, _ttl):
        return False

    async def no_posts(**_kwargs):
        return []

    monkeypatch.setattr(api._redis_store, "get_json", unavailable_get)
    monkeypatch.setattr(api._redis_store, "set_json", unavailable_set)
    monkeypatch.setattr(api, "fetch_latest_posts", no_posts)

    assert not await api.refresh_power_status_once()
    with pytest.raises(api.HTTPException) as error:
        await api.get_power_status()

    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_last_valid_status_file_is_not_overwritten_by_empty_refresh(monkeypatch, tmp_path):
    monkeypatch.setattr(api.config, "DATA_DIR", tmp_path)
    fallback_file = tmp_path / "last_status.json"
    monkeypatch.setattr(api, "FALLBACK_FILE", fallback_file)

    saved = api.save_status(
        {
            "city": api.config.CITY_NAME,
            "operator": api.config.OPERATOR,
            "type": "DAILY_STATUS",
            "date": "2026-10-14",
            "message": "Актуальний статус",
            "groups": {
                "1.1": {
                    "status": "OFF",
                    "outages": ["08:00-12:00"],
                },
            },
        }
    )

    original = fallback_file.read_text(encoding="utf-8")

    api._status_cache = None
    api._status_cache_time = 0

    async def no_redis_get(_key):
        return None

    async def no_redis_set(_key, _value, _ttl):
        return False

    async def no_posts(**_kwargs):
        return []

    monkeypatch.setattr(api._redis_store, "get_json", no_redis_get)
    monkeypatch.setattr(api._redis_store, "set_json", no_redis_set)
    monkeypatch.setattr(api, "fetch_latest_posts", no_posts)

    assert not await api.refresh_power_status_once()

    assert json.loads(original)["message"] == saved.message
    assert fallback_file.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_downloaded_image_is_removed_after_ocr(monkeypatch, tmp_path):
    image_path = tmp_path / "download.jpg"
    image_path.write_bytes(b"image")

    async def no_redis_get(_key):
        return None

    async def no_redis_set(_key, _value, _ttl):
        return False

    async def posts(**_kwargs):
        return [{"text": "", "image": "https://example.test/image.jpg"}]

    async def download(_url):
        return str(image_path)

    monkeypatch.setattr(api._redis_store, "get_json", no_redis_get)
    monkeypatch.setattr(api._redis_store, "set_json", no_redis_set)
    monkeypatch.setattr(api, "fetch_latest_posts", posts)
    monkeypatch.setattr(api, "download_image", download)
    monkeypatch.setattr(api, "extract_schedule_from_image", lambda _path: None)

    assert await api.refresh_power_status_once() is False

    assert not image_path.exists()


def test_download_image_uses_timeout_and_removes_file_on_http_error(monkeypatch):
    received_timeout = None

    class FakeResponse:
        status_code = 500
        headers = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def raise_for_status(self):
            raise httpx.HTTPStatusError("bad status", request=None, response=None)

        async def aiter_bytes(self):
            yield b"unused"

    class FakeClient:
        def __init__(self, **kwargs):
            nonlocal received_timeout
            received_timeout = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def build_request(self, method, url):
            return httpx.Request(method, url)

        async def send(self, request, stream=True):
            return FakeResponse()

    monkeypatch.setattr(image_loader.httpx, "AsyncClient", FakeClient)

    with tempfile.TemporaryDirectory() as workdir:
        monkeypatch.chdir(workdir)
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(image_loader.download_image("https://example.test/image.jpg"))
        assert not os.listdir("images")

    assert received_timeout is not None


def test_download_image_rejects_oversized_body_and_cleans_temp_file(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def aclose(self):
            return None

        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            yield b"x" * (image_loader.MAX_IMAGE_BYTES + 1)

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def build_request(self, method, url):
            return httpx.Request(method, url)

        async def send(self, request, stream=True):
            return FakeResponse()

    monkeypatch.setattr(image_loader.httpx, "AsyncClient", FakeClient)

    with tempfile.TemporaryDirectory() as workdir:
        monkeypatch.chdir(workdir)
        with pytest.raises(ValueError, match="maximum allowed size"):
            asyncio.run(image_loader.download_image("https://example.test/large.jpg"))
        assert not os.listdir("images")


def test_download_image_timeout_removes_partial_file(monkeypatch, tmp_path):
    class FakeResponse:
        status_code = 200
        headers = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def aclose(self):
            return None

        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            yield b"partial"
            raise httpx.ReadTimeout("timed out")

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def build_request(self, method, url):
            return httpx.Request(method, url)

        async def send(self, request, stream=True):
            return FakeResponse()

    monkeypatch.setattr(image_loader.httpx, "AsyncClient", FakeClient)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(image_loader.download_image("https://example.test/slow.jpg"))

    assert not os.listdir("images")


def test_tesseract_calls_have_process_timeout(monkeypatch):
    import numpy as np

    passed = {}

    def fake_image_to_string(_image, **kwargs):
        passed.update(kwargs)
        return ""

    monkeypatch.setattr(ocr.pytesseract, "image_to_string", fake_image_to_string)
    ocr.ocr_tile(np.zeros((8, 8, 3), dtype=np.uint8))

    assert passed["timeout"] == ocr.TESSERACT_TIMEOUT_SECONDS
