from app.api import get_cache_status, get_health
from app.loe_api import clear_loe_cache, get_loe_cache_status, set_cached_loe_collection


def test_health_endpoint():
    result = get_health()

    assert result["status"] == "ok"
    assert result["service"] == "power-backend"
    assert result["time"]


def test_loe_cache_status():
    clear_loe_cache()
    set_cached_loe_collection(
        "pw_cities",
        {"pagination": "false"},
        {"hydra:member": [{"id": 1}, {"id": 2}]},
        now=100,
    )

    result = get_loe_cache_status(now=130)

    assert result == {
        "ttl_seconds": 300,
        "entries_count": 1,
        "expired_entries_count": 0,
        "entries": [
            {
                "path": "pw_cities",
                "params": {"pagination": "false"},
                "age_seconds": 30,
                "expires_in_seconds": 270,
                "items": 2,
            }
        ],
    }


def test_cache_status_endpoint():
    clear_loe_cache()

    assert get_cache_status()["loe"]["entries_count"] == 0
