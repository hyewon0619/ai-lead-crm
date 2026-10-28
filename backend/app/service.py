"""리드 생성·병합·상태 변경.

원칙
- 같은 입력은 몇 번 들어와도 한 건 (결정적 ID)
- 사람이 고친 필드는 AI 가 다시 덮어쓰지 않는다
- 동시 편집은 버전으로 비교하되, 서로 다른 필드를 고친 경우는 병합한다
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .customer_link import link_customer, link_manually
from .extraction.pipeline import CaseRecord, PipelineResult
from .ids import evidence_id, lead_id
from .index import LeadIndex, to_doc
from .models import Evidence, Lead, LeadSource, LeadStatus, Opportunity, OpportunityStage, Role, User
from .notify import Notifier
from .permissions import Action, can

AI_FIELDS = ("title", "summary", "company_name", "business_number")
EDITABLE_FIELDS = ("title", "summary", "company_name", "business_number", "status", "status_reason", "reviewer_id")
UNSIGNED_REASON = "미계약 상담"


class PermissionDenied(Exception):
    pass


class NotFound(Exception):
    pass


@dataclass
class Conflict(Exception):
    current: dict


def _default_reviewer(session: Session, department: str) -> int | None:
    return session.scalar(
        select(User.id).where(User.department == department, User.role == Role.REVIEWER).order_by(User.id)
    )


def _add_evidence(session: Session, lead: Lead, request_id: str, quote: str, source_ref: str, now: datetime) -> None:
    eid = evidence_id(request_id, quote)
    if session.get(Evidence, eid) is None:
        session.add(Evidence(id=eid, lead=lead, request_id=request_id, quote=quote, source_ref=source_ref, created_at=now))


def _sync(index: LeadIndex, *leads: Lead) -> None:
    for lead in leads:
        index.upsert(to_doc(lead))


def ingest_auto(session: Session, index: LeadIndex, record: CaseRecord, result: PipelineResult, now: datetime) -> list[Lead]:
    touched: list[Lead] = []
    for acc in result.accepted:
        c = acc.candidate
        lid = lead_id(record.case_id, c.category)
        lead = session.get(Lead, lid)
        incoming = {"title": c.title, "summary": "", "company_name": c.company_name, "business_number": c.business_number}

        if lead is None:
            lead = Lead(
                id=lid, case_id=record.case_id, category=c.category, source=LeadSource.AUTO,
                department=record.department, reviewer_id=_default_reviewer(session, record.department),
                status=LeadStatus.NEW, human_edited=[], version=1, created_at=now, updated_at=now, **incoming,
            )
            session.add(lead)
        else:
            changed = False
            for f in AI_FIELDS:
                if f in lead.human_edited or incoming[f] in (None, ""):
                    continue
                if getattr(lead, f) != incoming[f]:
                    setattr(lead, f, incoming[f])
                    changed = True
            if changed:
                lead.version += 1
                lead.updated_at = now

        # 계약으로 이어지지 않은 상담에서 나온 리드는 연락 대상이 아니다.
        if not record.contract_signed and "status" not in lead.human_edited and lead.status == LeadStatus.NEW:
            lead.status, lead.status_reason = LeadStatus.EXCLUDED, UNSIGNED_REASON

        _add_evidence(session, lead, record.request_id, c.quote, record.source_ref, now)
        link_customer(session, lead)
        touched.append(lead)

    session.commit()
    _sync(index, *touched)
    return touched


def report_lead(
    session: Session, index: LeadIndex, user: User, *, request_id: str, category: str, title: str, detail: str,
    case_id: str | None = None, company_name: str | None = None, business_number: str | None = None,
    via_assistant: bool = False, now: datetime,
) -> Lead:
    """직원 제보. 웹 폼과 AI 비서가 같은 함수를 부른다."""
    if not can(user, Action.REPORT):
        raise PermissionDenied
    key = case_id or f"report:{request_id}"
    lid = lead_id(key, category)
    lead = session.get(Lead, lid)
    if lead is None:
        lead = Lead(
            id=lid, case_id=key, category=category,
            source=LeadSource.REPORT_ASSISTANT if via_assistant else LeadSource.REPORT_FORM,
            title=title, summary=detail, company_name=company_name, business_number=business_number,
            department=user.department, reviewer_id=_default_reviewer(session, user.department),
            reporter_id=user.id, status=LeadStatus.NEW, human_edited=["title", "summary"],
            version=1, created_at=now, updated_at=now,
        )
        session.add(lead)
    _add_evidence(session, lead, request_id, detail, f"report:{user.id}", now)
    link_customer(session, lead)
    session.commit()
    _sync(index, lead)
    return lead


def get_lead(session: Session, user: User, lid: str) -> Lead:
    lead = session.get(Lead, lid)
    if lead is None:
        raise NotFound
    if not can(user, Action.VIEW, lead):
        raise PermissionDenied
    return lead


def update_lead(
    session: Session, index: LeadIndex, notifier: Notifier, user: User, lid: str, *,
    base_version: int, changes: dict, base_values: dict, now: datetime,
) -> Lead:
    lead = get_lead(session, user, lid)
    unknown = set(changes) - set(EDITABLE_FIELDS)
    if unknown:
        raise ValueError(f"not editable: {sorted(unknown)}")

    needed = {Action.EDIT}
    if "status" in changes:
        needed.add(Action.CHANGE_STATUS)
    if changes.get("status") == LeadStatus.ASSIGNED or "reviewer_id" in changes:
        needed.add(Action.ASSIGN)
    if not all(can(user, a, lead) for a in needed):
        raise PermissionDenied

    if lead.version != base_version:
        # 그 사이 다른 사람이 고쳤다. 내가 바꾸려는 필드가 내가 본 값 그대로면
        # 서로 다른 필드를 고친 것이므로 병합하고, 아니면 충돌로 돌려보낸다.
        stale = [f for f in changes if getattr(lead, f) != base_values.get(f)]
        if stale:
            raise Conflict(current=to_doc(lead))

    for f, v in changes.items():
        setattr(lead, f, v)
        if f not in lead.human_edited:
            lead.human_edited = [*lead.human_edited, f]
    lead.version += 1
    lead.updated_at = now

    if changes.get("status") == LeadStatus.ASSIGNED and lead.opportunity is None:
        session.add(Opportunity(lead=lead, stage=OpportunityStage.CALL, updated_at=now))
        if lead.reviewer_id:
            notifier.lead_assigned(lead.reviewer_id, lead.id)

    session.commit()
    _sync(index, lead)
    return lead


def set_customer(session: Session, index: LeadIndex, user: User, lid: str, customer_id: int, now: datetime) -> Lead:
    lead = get_lead(session, user, lid)
    if not can(user, Action.EDIT, lead):
        raise PermissionDenied
    link_manually(lead, customer_id)
    lead.version += 1
    lead.updated_at = now
    session.commit()
    _sync(index, lead)
    return lead


def advance_opportunity(
    session: Session, index: LeadIndex, user: User, lid: str, stage: OpportunityStage,
    *, lost_reason: str | None = None, amount: int | None = None, now: datetime,
) -> Opportunity:
    lead = get_lead(session, user, lid)
    if not can(user, Action.EDIT, lead) or lead.opportunity is None:
        raise PermissionDenied
    if stage == OpportunityStage.LOST and not lost_reason:
        raise ValueError("미선임은 사유가 필요하다")
    opp = lead.opportunity
    opp.stage, opp.lost_reason, opp.updated_at = stage, lost_reason, now
    if amount is not None:
        opp.amount = amount
    lead.updated_at = now
    session.commit()
    _sync(index, lead)
    return opp
