import json

import httpx
import pytest
import respx

from client import BudgeterApiError, BudgeterClient


@pytest.fixture()
def client():
    return BudgeterClient(base_url="http://testserver", api_key="test-key")


@respx.mock
async def test_get_sends_bearer_auth_header(client):
    route = respx.get("http://testserver/api/accounts").mock(
        return_value=httpx.Response(200, json=[{"id": 1}])
    )
    result = await client.get("/api/accounts")
    assert result == [{"id": 1}]
    assert route.calls.last.request.headers["authorization"] == "Bearer test-key"


@respx.mock
async def test_get_passes_query_params(client):
    route = respx.get("http://testserver/api/transactions", params={"page": "2"}).mock(
        return_value=httpx.Response(200, json={"items": [], "total": 0})
    )
    await client.get("/api/transactions", params={"page": 2})
    assert route.called


@respx.mock
async def test_post_sends_json_body(client):
    route = respx.post("http://testserver/api/ai/suggest").mock(
        return_value=httpx.Response(200, json={"applied": 1, "skipped": []})
    )
    result = await client.post("/api/ai/suggest", json={"suggestions": [{"transaction_id": 1}]})
    assert result == {"applied": 1, "skipped": []}
    assert json.loads(route.calls.last.request.content) == {"suggestions": [{"transaction_id": 1}]}


@respx.mock
async def test_error_status_raises(client):
    respx.get("http://testserver/api/accounts/999").mock(
        return_value=httpx.Response(404, text="Account 999 not found")
    )
    with pytest.raises(BudgeterApiError) as exc_info:
        await client.get("/api/accounts/999")
    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail


@respx.mock
async def test_204_response_returns_none(client):
    respx.post("http://testserver/api/rules/reorder").mock(return_value=httpx.Response(204))
    result = await client.post("/api/rules/reorder", json={"ordered_ids": []})
    assert result is None
