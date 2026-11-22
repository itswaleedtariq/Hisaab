"""End-to-end API tests against a temporary SQLite file (FastAPI TestClient)."""

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
        assert client.post(f"/groups/{gid}/members", json={"user_id": uid},
                           headers=h(ids[0])).status_code == 204
    return gid, ids


def spend(client, gid, payer, amount="300.00", **body):
    payload = {"payer_id": payer, "amount": amount, "split_type": "equal",
               "participants": body.pop("participants", None) or [1, 2, 3], **body}
    return client.post(f"/groups/{gid}/expenses", json=payload, headers=h(payer))


def test_full_flow_expense_balances_plan_settle(client, flat):
    gid, (ali, sara, bilal) = flat
    r = spend(client, gid, ali, "300.00")
    assert r.status_code == 201
    assert [s["amount"] for s in r.json()["shares"]] == ["100.00", "100.00", "100.00"]
    r = spend(client, gid, sara, "90.00", split_type="percent",
              percentages={str(ali): "50", str(sara): "25", str(bilal): "25"})
    assert r.status_code == 201

    balances = {b["user_id"]: b["balance"] for b in
                client.get(f"/groups/{gid}/balances", headers=h(bilal)).json()}
    assert balances == {ali: "155.00", sara: "-32.50", bilal: "-122.50"}

    plan = client.get(f"/groups/{gid}/settlement-plan", headers=h(bilal)).json()
    assert len(plan) <= 2

    r = client.post(f"/groups/{gid}/settlements",
                    json={"from_user_id": bilal, "to_user_id": ali, "amount": "122.50"},
                    headers=h(bilal))
    assert r.status_code == 201
    assert client.post(f"/groups/{gid}/settle-up", headers=h(ali)).status_code == 200
    balances = client.get(f"/groups/{gid}/balances", headers=h(ali)).json()
    assert {b["balance"] for b in balances} == {"0.00"}


def test_void_and_list(client, flat):
    gid, (ali, sara, _b) = flat
    eid = spend(client, gid, sara).json()["id"]
    assert client.post(f"/expenses/{eid}/void", headers=h(ali)).json()["status"] == "voided"
    assert client.post(f"/expenses/{eid}/void", headers=h(ali)).status_code == 409
    assert client.get(f"/expenses/{eid}", headers=h(sara)).json()["status"] == "voided"
    assert len(client.get(f"/groups/{gid}/expenses", headers=h(sara)).json()) == 1


def test_idempotency_key_header(client, flat):
    gid, (ali, *_rest) = flat
    headers = h(ali, **{"Idempotency-Key": "tap-1"})
    payload = {"payer_id": ali, "amount": "60.00", "split_type": "equal", "participants": [1, 2, 3]}
    a = client.post(f"/groups/{gid}/expenses", json=payload, headers=headers)
    b = client.post(f"/groups/{gid}/expenses", json=payload, headers=headers)
    assert (a.status_code, b.status_code) == (201, 201)
    assert a.json()["id"] == b.json()["id"]
    assert len(client.get(f"/groups/{gid}/expenses", headers=h(ali)).json()) == 1


def test_report_endpoint_runs_job(client, flat):
    gid, (ali, *_rest) = flat
    spend(client, gid, ali)
    job = client.post(f"/groups/{gid}/reports", json={"period": "2026-11"}, headers=h(ali))
    assert job.status_code == 202
    client.app.state.container.reports.last_future.result(timeout=5)
    status = client.get(f"/reports/{job.json()['id']}", headers=h(ali)).json()
    assert status["status"] == "done"


def test_remove_member_endpoint(client, flat):
    gid, (ali, sara, bilal) = flat
    assert client.delete(f"/groups/{gid}/members/{bilal}", headers=h(ali)).status_code == 204
    spend(client, gid, ali, participants=[ali, sara])
    assert client.delete(f"/groups/{gid}/members/{sara}", headers=h(ali)).status_code == 409


def test_request_id_header_is_returned(client):
    r = client.get("/users/1", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
