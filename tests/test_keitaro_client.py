import httpx
import pytest

from app.config import Settings
from app.keitaro import KeitaroClient, KeitaroError


def make_client(handler, **kwargs):
    settings = Settings(keitaro_url="https://kt.test/", keitaro_api_key="secret-key")
    return KeitaroClient(settings, transport=httpx.MockTransport(handler), **kwargs)


def test_requests_carry_the_api_key_and_the_right_path():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=[])

    make_client(handler).list_groups()

    assert seen[0].url == "https://kt.test/admin_api/v1/groups?type=campaigns"
    assert seen[0].headers["Api-Key"] == "secret-key"


def test_offers_are_cached():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=[{"id": 1, "name": "One"}])

    client = make_client(handler)
    assert client.list_offers() == client.list_offers()
    assert len(calls) == 1


def test_offers_cache_can_be_switched_off():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=[])

    client = make_client(handler, offers_ttl=0)
    client.list_offers()
    client.list_offers()
    assert len(calls) == 2


def test_http_errors_become_keitaro_errors():
    client = make_client(lambda request: httpx.Response(404, json={"error": "Not found"}))
    with pytest.raises(KeitaroError) as info:
        client.get_offer(5)
    assert info.value.status_code == 404
    assert "Not found" in str(info.value)


def test_network_errors_become_keitaro_errors():
    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(KeitaroError) as info:
        make_client(handler).list_domains()
    assert info.value.status_code is None


def test_empty_answer_is_none():
    client = make_client(lambda request: httpx.Response(200))
    assert client.update_stream(1, {"offers": []}) is None
