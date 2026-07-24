import httpx

from config import settings


class BudgeterApiError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Budgeter API error {status_code}: {detail}")


class BudgeterClient:
    """Thin HTTP wrapper around the Budgeter REST API.

    No business logic lives here — every method is a direct pass-through
    to one REST endpoint, per docs/requirements.md §6 ("the core app does
    not speak MCP natively").
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self._base_url = (base_url or settings.api_base_url).rstrip("/")
        self._api_key = api_key or settings.api_key

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
            resp = await client.request(
                method, path, headers={"Authorization": f"Bearer {self._api_key}"}, **kwargs
            )
        if resp.status_code >= 400:
            raise BudgeterApiError(resp.status_code, resp.text)
        return resp

    async def get(self, path: str, params: dict | None = None) -> dict | list:
        resp = await self._request("GET", path, params=params)
        return resp.json() if resp.content else None

    async def post(self, path: str, json: dict | None = None) -> dict | list:
        resp = await self._request("POST", path, json=json)
        return resp.json() if resp.content else None
