"""권한 판정.

화면 API와 AI 비서의 도구 호출이 모두 이 함수 하나를 거친다.
경로마다 권한 로직을 따로 두면 언젠가 한쪽만 고쳐지고, AI 비서가
화면에서는 못 보는 리드를 읽어 주는 사고가 난다.
"""

from enum import StrEnum

from .models import Lead, LeadSource, Role, User


class Action(StrEnum):
    VIEW = "view"
    REPORT = "report"
    EDIT = "edit"
    CHANGE_STATUS = "change_status"
    ASSIGN = "assign"
    VIEW_REPORTS = "view_reports"


def can(user: User, action: Action, lead: Lead | None = None) -> bool:
    if user.role == Role.ADMIN:
        return True

    if action == Action.REPORT:
        return True

    if user.role == Role.REVIEWER:
        if action == Action.VIEW_REPORTS:
            return True
        if lead is None:
            return action == Action.VIEW
        # 검토자는 자기 부서 리드와 자기에게 배정된 리드만 다룬다.
        return lead.department == user.department or lead.reviewer_id == user.id

    # 일반 직원은 자기가 제보한 리드를 보는 것까지만.
    if action == Action.VIEW and lead is not None:
        return lead.reporter_id == user.id and lead.source != LeadSource.AUTO
    return False


def visible_filter(user: User) -> dict:
    """목록 조회용 필터. can(VIEW)과 같은 규칙을 인덱스 질의로 옮긴 것."""
    if user.role == Role.ADMIN:
        return {}
    if user.role == Role.REVIEWER:
        return {"any_of": {"department": user.department, "reviewer_id": user.id}}
    return {"reporter_id": user.id, "source_not": LeadSource.AUTO.value}
