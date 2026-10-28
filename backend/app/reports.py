"""경영진 보고용 집계: 부서별 현황, 검토자 확인율, 선임 전환율."""

from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Lead, LeadStatus, OpportunityStage, Role, User


def department_summary(session: Session) -> list[dict]:
    rows: dict[str, Counter] = defaultdict(Counter)
    for lead in session.scalars(select(Lead)):
        rows[lead.department][lead.status] += 1
        if lead.opportunity and lead.opportunity.stage == OpportunityStage.WON:
            rows[lead.department]["won"] += 1

    out = []
    for dept, c in sorted(rows.items()):
        total = sum(c[s] for s in LeadStatus)
        assigned = c[LeadStatus.ASSIGNED]
        out.append({
            "department": dept,
            "total": total,
            "by_status": {s.value: c[s] for s in LeadStatus},
            "assigned": assigned,
            "won": c["won"],
            "conversion_rate": round(c["won"] / assigned, 3) if assigned else None,
        })
    return out


def reviewer_confirmation(session: Session) -> list[dict]:
    """검토자별 확인율 = 미확인 상태를 벗어난 리드 / 검토 시작 이후 배정된 리드.

    검토 시작 전에 쌓여 있던 리드까지 분모에 넣으면, 늦게 합류한 검토자가
    시작부터 낮은 확인율로 보고된다.
    """
    out = []
    for r in session.scalars(select(User).where(User.role == Role.REVIEWER).order_by(User.id)):
        q = select(Lead).where(Lead.reviewer_id == r.id)
        if r.review_started_at:
            q = q.where(Lead.created_at >= r.review_started_at)
        leads = session.scalars(q).all()
        confirmed = sum(1 for lead in leads if lead.status != LeadStatus.NEW)
        out.append({
            "reviewer_id": r.id,
            "name": r.name,
            "department": r.department,
            "review_started_at": r.review_started_at.isoformat() if r.review_started_at else None,
            "assigned": len(leads),
            "confirmed": confirmed,
            "confirmation_rate": round(confirmed / len(leads), 3) if leads else None,
        })
    return out


def lost_reasons(session: Session) -> dict[str, int]:
    c: Counter = Counter()
    for lead in session.scalars(select(Lead).where(Lead.status == LeadStatus.ASSIGNED)):
        if lead.opportunity and lead.opportunity.stage == OpportunityStage.LOST:
            c[lead.opportunity.lost_reason or "미기재"] += 1
    return dict(c.most_common())
