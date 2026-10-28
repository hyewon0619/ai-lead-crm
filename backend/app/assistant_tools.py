"""AI 비서가 호출하는 도구.

비서는 사용자를 대신해 행동할 뿐이므로, 권한 판정은 화면과 똑같이
permissions.can() 을 거친다. 비서 전용 우회 경로는 두지 않는다.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from . import service
from .index import LeadIndex
from .models import User
from .permissions import visible_filter

TOOLS = [
    {
        "name": "list_my_leads",
        "description": "내가 볼 수 있는 리드를 상태별로 조회한다.",
        "parameters": {"type": "object", "properties": {"status": {"type": "string"}}, "additionalProperties": False},
    },
    {
        "name": "report_lead",
        "description": "대화에서 들은 고객의 새 법률 수요를 리드로 제보한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "title": {"type": "string"},
                "detail": {"type": "string"},
                "company_name": {"type": "string"},
                "case_id": {"type": "string"},
            },
            "required": ["category", "title", "detail"],
            "additionalProperties": False,
        },
    },
]


def call(session: Session, index: LeadIndex, user: User, name: str, args: dict, now: datetime) -> dict:
    if name == "list_my_leads":
        hits = index.search(visible_filter(user), status=args.get("status"))
        return {"leads": [{"id": h["id"], "title": h["title"], "status": h["status"]} for h in hits]}
    if name == "report_lead":
        lead = service.report_lead(
            session, index, user, request_id=args.get("request_id") or uuid.uuid4().hex,
            category=args["category"], title=args["title"], detail=args["detail"],
            case_id=args.get("case_id"), company_name=args.get("company_name"), via_assistant=True, now=now,
        )
        return {"id": lead.id, "status": lead.status}
    raise ValueError(f"unknown tool: {name}")
