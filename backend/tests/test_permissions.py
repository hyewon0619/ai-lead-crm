"""화면 API 와 AI 비서가 같은 권한 규칙을 따르는지 확인한다."""

import pytest
from fastapi.testclient import TestClient

from app import main
from app.db import get_session
from app.models import LeadSource
from app.permissions import Action, can
from tests.conftest import T0


@pytest.fixture
def c(session, index, monkeypatch):
    main.app.dependency_overrides[get_session] = lambda: session
    main.app.dependency_overrides[main.get_index] = lambda: index
    monkeypatch.setattr(main, "now", lambda: T0)
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def report(c, uid, rid, **kw):
    body = {"request_id": rid, "category": "노무", "title": "임금 체불", "detail": "직원 임금 체불 진정이 들어왔다고 함", **kw}
    return c.post("/api/leads", json=body, headers={"X-User-Id": str(uid)})


def test_member_sees_only_own_reports(c):
    mine = report(c, 20, "a").json()
    other = report(c, 21, "b").json()
    expected = {20: {mine["id"]}, 10: {mine["id"], other["id"]}, 11: set()}  # 10 = 같은 부서 검토자
    for uid, ids in expected.items():
        assert {d["id"] for d in c.get("/api/leads", headers={"X-User-Id": str(uid)}).json()["items"]} == ids
    assert c.get(f"/api/leads/{mine['id']}", headers={"X-User-Id": "21"}).status_code == 403
    assert c.get(f"/api/leads/{mine['id']}", headers={"X-User-Id": "11"}).status_code == 403  # 다른 부서 검토자


def test_member_cannot_change_status(c):
    lead = report(c, 20, "a").json()
    res = c.patch(f"/api/leads/{lead['id']}", headers={"X-User-Id": "20"},
                  json={"base_version": lead["version"], "changes": {"status": "배당"}})
    assert res.status_code == 403


def test_report_is_idempotent_per_request(c):
    assert report(c, 20, "same").json()["id"] == report(c, 20, "same").json()["id"]


def test_assistant_uses_same_visibility(c):
    report(c, 20, "a")
    via_bot = c.post("/api/assistant/tools/report_lead", headers={"X-User-Id": "21"},
                     json={"category": "세무", "title": "세무조사", "detail": "세무조사 통지를 받았다고 함"}).json()
    screen = {d["id"] for d in c.get("/api/leads", headers={"X-User-Id": "21"}).json()["items"]}
    bot = {d["id"] for d in c.post("/api/assistant/tools/list_my_leads", headers={"X-User-Id": "21"}, json={}).json()["leads"]}
    assert screen == bot == {via_bot["id"]}


def test_auto_leads_hidden_from_members(session):
    from app.models import Lead, User

    member = session.get(User, 20)
    lead = Lead(id="x", case_id="c", category="노무", source=LeadSource.AUTO, title="t", department="자문1팀",
                reporter_id=20, human_edited=[])
    assert not can(member, Action.VIEW, lead)


def test_reports_require_reviewer(c):
    assert c.get("/api/reports/departments", headers={"X-User-Id": "20"}).status_code == 403
    assert c.get("/api/reports/departments", headers={"X-User-Id": "10"}).status_code == 200


def test_strict_mapping_rejects_unknown_field(index):
    with pytest.raises(ValueError):
        index.upsert({"id": "x", "secret_field": 1})
