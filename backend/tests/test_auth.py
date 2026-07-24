from fastapi import APIRouter, Depends

from app.auth import require_api_key
from app.main import app

_test_router = APIRouter()


@_test_router.get("/protected")
def protected() -> dict[str, bool]:
    return {"ok": True}


app.include_router(_test_router, dependencies=[Depends(require_api_key)])


def test_protected_requires_valid_key(client):
    resp = client.get("/protected")
    assert resp.status_code == 401

    resp = client.get("/protected", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401

    resp = client.get("/protected", headers={"Authorization": "Bearer test-api-key"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
