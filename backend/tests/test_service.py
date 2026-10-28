from datetime import timedelta

import pytest

from app import service
from app.extraction.pipeline import Accepted, CaseRecord, PipelineResult
from app.extraction.schema import Candidate
from app.ids import evidence_id, lead_id
from app.models import Lead, LeadStatus, User
from tests.conftest import T0

QUOTE = "지난달 퇴사한 직원이 미지급 퇴직금으로 노동청 진정을 냈다."


def ingest(session, index, *, title="퇴직금 분쟁", request_id="r1", signed=True, company="가온테크 주식회사", bn=None,
           quote=QUOTE):
    rec = CaseRecord(case_id="C-1", case_category="기업분쟁", text=quote, request_id=request_id,
                     source_ref="note:1", department="자문1팀", contract_signed=signed)
    res = PipelineResult(accepted=[Accepted(Candidate(category="노무", title=title, quote=quote,
                                                       company_name=company, business_number=bn))])
    return service.ingest_auto(session, index, rec, res, T0)


def test_ids_are_deterministic():
    assert lead_id("C-1", "노무") == lead_id(" C-1 ", "노무")
    assert lead_id("C-1", "노무") != lead_id("C-1", "세무")
    assert evidence_id("r1", "a  b\nc") == evidence_id("r1", "a b c")


def test_reingest_is_idempotent(session, index):
    ingest(session, index)
    ingest(session, index)
    leads = session.query(Lead).all()
    assert len(leads) == 1 and len(leads[0].evidence) == 1
    ingest(session, index, request_id="r2")  # 다른 요청에서 같은 근거가 또 나오면 근거만 늘어난다
    assert len(session.query(Lead).one().evidence) == 2


def test_ai_never_overwrites_human_edits(session, index, notifier):
    lead = ingest(session, index)[0]
    admin = session.get(User, 1)
    service.update_lead(session, index, notifier, admin, lead.id, base_version=lead.version,
                        changes={"title": "사람이 고친 제목"}, base_values={}, now=T0)
    ingest(session, index, title="AI 가 새로 뽑은 제목", company="가온테크(주)")
    lead = session.get(Lead, lead.id)
    assert lead.title == "사람이 고친 제목"
    assert lead.company_name == "가온테크(주)"  # 사람이 안 건드린 필드는 갱신된다


def test_unsigned_consultation_is_excluded(session, index):
    lead = ingest(session, index, signed=False)[0]
    assert lead.status == LeadStatus.EXCLUDED and lead.status_reason == service.UNSIGNED_REASON


def test_concurrent_edit_merge_and_conflict(session, index, notifier):
    lead = ingest(session, index)[0]
    a, v = session.get(User, 10), lead.version
    # 검토자 두 명이 같은 버전을 보고 서로 다른 필드를 고친다 → 둘 다 반영
    service.update_lead(session, index, notifier, a, lead.id, base_version=v,
                        changes={"summary": "통화 메모"}, base_values={"summary": ""}, now=T0)
    service.update_lead(session, index, notifier, a, lead.id, base_version=v,
                        changes={"status": LeadStatus.CONTACTED}, base_values={"status": LeadStatus.NEW}, now=T0)
    lead = session.get(Lead, lead.id)
    assert (lead.summary, lead.status) == ("통화 메모", LeadStatus.CONTACTED)
    # 같은 필드를 옛 버전 기준으로 고치면 충돌
    with pytest.raises(service.Conflict) as e:
        service.update_lead(session, index, notifier, a, lead.id, base_version=v,
                            changes={"summary": "다른 메모"}, base_values={"summary": ""}, now=T0)
    assert e.value.current["summary"] == "통화 메모"


def test_assign_creates_opportunity_and_bodyless_push(session, index, notifier):
    lead = ingest(session, index)[0]
    admin = session.get(User, 1)
    service.update_lead(session, index, notifier, admin, lead.id, base_version=lead.version,
                        changes={"status": LeadStatus.ASSIGNED}, base_values={}, now=T0)
    assert session.get(Lead, lead.id).opportunity is not None
    [msg] = notifier.sent
    assert msg.user_id == 10 and msg.lead_id == lead.id and msg.body == ""
    assert "퇴직금" not in msg.title


def test_lost_requires_reason(session, index, notifier):
    from app.models import OpportunityStage

    lead = ingest(session, index)[0]
    admin = session.get(User, 1)
    service.update_lead(session, index, notifier, admin, lead.id, base_version=lead.version,
                        changes={"status": LeadStatus.ASSIGNED}, base_values={}, now=T0)
    with pytest.raises(ValueError):
        service.advance_opportunity(session, index, admin, lead.id, OpportunityStage.LOST, now=T0)


def test_reviewer_rate_ignores_leads_before_start(session, index):
    from app import reports

    old = ingest(session, index)[0]
    old.created_at = T0 - timedelta(days=30)  # 검토 시작 전 리드
    session.commit()
    row = next(r for r in reports.reviewer_confirmation(session) if r["reviewer_id"] == 10)
    assert row["assigned"] == 0 and row["confirmation_rate"] is None
