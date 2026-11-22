"""Black-box API checks for access control and error bodies (QR-09, QR-10, QR-16).

SE431 verification tests, owned by Waleed Tariq (black-box design lead at M2).
"""

import pytest
from fastapi.testclient import TestClient

from hisaab.api.app import create_app


@pytest.fixture
def client(sqlite_app):
    with TestClient(create_app(sqlite_app)) as c:
        yield c


def h(user_id, **extra):
    return {"X-User-Id": str(user_id), **extra}


@pytest.fixture
def flat(client):
    ids = [
        client.post("/users", json={"name": n, "email": f"{n.lower()}@example.com"}).json()["id"]
        for n in ("Ali", "Sara", "Bilal")
    ]
    gid = client.post("/groups", json={"name": "Flat 4B"}, headers=h(ids[0])).json()["id"]
    for uid in ids[1:]:
        client.post(f"/groups/{gid}/members", json={"user_id": uid}, headers=h(ids[0]))
    return gid, ids


def spend(client, gid, payer, amount="300.00", **body):
    payload = {"payer_id": payer, "amount": amount, "split_type": "equal",
               "participants": body.pop("participants", None) or [1, 2, 3], **body}
    return client.post(f"/groups/{gid}/expenses", json=payload, headers=h(payer))


# --- QR-09: every group endpoint returns 403 for a non-member ---------------------
GROUP_ENDPOINTS = [
    ("get", "/groups/{g}/members", None),
    ("post", "/groups/{g}/members", {"user_id": 1}),
    ("delete", "/groups/{g}/members/2", None),
    ("post", "/groups/{g}/expenses",
     {"payer_id": 1, "amount": "1.00", "split_type": "equal", "participants": [1]}),
    ("get", "/groups/{g}/expenses", None),
    ("get", "/expenses/1", None),
    ("post", "/expenses/1/void", None),
    ("get", "/groups/{g}/balances", None),
    ("get", "/groups/{g}/settlement-plan", None),
    ("post", "/groups/{g}/settlements", {"from_user_id": 2, "to_user_id": 1, "amount": "1.00"}),
    ("post", "/groups/{g}/settle-up", None),
    ("post", "/groups/{g}/reports", {"period": "2026-11", "format": "csv"}),
    ("get", "/reports/1", None),
]


@pytest.mark.parametrize(("method", "path", "body"), GROUP_ENDPOINTS,
                         ids=[f"{m} {p}" for m, p, _ in GROUP_ENDPOINTS])
def test_qr09_non_member_gets_403(client, flat, method, path, body):
    gid, (ali, *_rest) = flat
    spend(client, gid, ali)
    client.post(f"/groups/{gid}/reports", json={"period": "2026-11"}, headers=h(ali))
    outsider = client.post("/users", json={"name": "Out", "email": "out@example.com"}).json()["id"]
    kwargs = {"headers": h(outsider)}
    if body is not None:
        kwargs["json"] = body
    r = getattr(client, method)(path.format(g=gid), **kwargs)
    assert r.status_code == 403, r.text


# --- QR-10 and QR-16: error bodies -------------------------------------------------
def test_qr16_validation_error_names_field_and_rule(client, flat):
    gid, (ali, *_rest) = flat
    r = spend(client, gid, ali, split_type="percent",
              percentages={"1": "50", "2": "25", "3": "24.99"})
    assert r.status_code == 422
    body = r.json()
    assert body["field"] == "percentages"
    assert "100.00" in body["rule"]
    assert body["request_id"]


def test_qr10_internal_errors_do_not_leak_details(client, flat, monkeypatch):
    from hisaab.domain.errors import PersistenceError

    def broken(*_a, **_k):
        try:
            raise OSError("/home/secret/path/hisaab.db: SELECT * FROM users")
        except OSError as exc:
            raise PersistenceError("database read failed") from exc

    monkeypatch.setattr(client.app.state.container.users, "get", broken)
    r = client.get("/users/1")
    assert r.status_code == 500
    text = r.text.lower()
    for leak in ("select", "/home", "traceback", "hisaab.db"):
        assert leak not in text


def test_missing_or_bad_identity_header(client, flat):
    gid, _ids = flat
    assert client.get(f"/groups/{gid}/balances").status_code == 422
    assert client.get(f"/groups/{gid}/balances", headers={"X-User-Id": "0"}).status_code == 422


def test_request_body_validation(client, flat):
    gid, (ali, *_rest) = flat
    assert spend(client, gid, ali, amount="10.005").status_code == 422
    assert spend(client, gid, ali, amount="-5").status_code == 422
    assert client.post("/users", json={"name": "X", "email": "x@example.com",
                                       "admin": True}).status_code == 422
    assert client.get("/users/999").status_code == 404
    r = client.post("/users", json={"name": "Ali", "email": "ali@example.com"})
    assert r.status_code == 409
