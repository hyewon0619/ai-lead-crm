"""HTTP API.

인증은 공개본 범위 밖이라 X-User-Id 헤더로 대신한다. 운영에서는 사내 SSO
토큰에서 사용자를 풀어 같은 자리에 넣는다.
"""

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import assistant_tools, reports, service
from .config import settings
from .db import SessionLocal, get_session, init_db
from .extraction.llm import LLMClient, default_client
from .extraction.offline_llm import OfflineLLM
from .extraction.pipeline import CaseRecord, run
from .index import ElasticsearchIndex, InMemoryIndex, LeadIndex, to_doc
from .models import Lead, OpportunityStage, Role, User
from .notify import notifier
from .permissions import Action, can, visible_filter

_index: LeadIndex = ElasticsearchIndex(settings.es_url, settings.es_index) if settings.es_url else InMemoryIndex()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if isinstance(_index, InMemoryIndex):  # 로컬 실행: 원장에서 메모리 인덱스를 채운다
        with SessionLocal() as s:
            for lead in s.scalars(select(Lead)):
                _index.upsert(to_doc(lead))
    yield


app = FastAPI(title="AI Lead CRM", lifespan=lifespan)


def get_index() -> LeadIndex:
    return _index


def get_llm() -> LLMClient:
    if settings.local_llm_url == "offline":
        return OfflineLLM()
    return default_client()


def now() -> datetime:
    return datetime.now()


def current_user(x_user_id: int = Header(...), session: Session = Depends(get_session)) -> User:
    user = session.get(User, x_user_id)
    if user is None:
        raise HTTPException(401)
    return user


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.NotFound:
        raise HTTPException(404) from None
    except service.PermissionDenied:
        raise HTTPException(403) from None
    except service.Conflict as e:
        raise HTTPException(409, detail={"current": e.current}) from None
    except ValueError as e:
        raise HTTPException(422, detail=str(e)) from None


class ReportIn(BaseModel):
    request_id: str
    category: str
    title: str
    detail: str
    case_id: str | None = None
    company_name: str | None = None
    business_number: str | None = None


class PatchIn(BaseModel):
    base_version: int
    changes: dict
    base_values: dict = {}


class CustomerIn(BaseModel):
    customer_id: int


class StageIn(BaseModel):
    stage: OpportunityStage
    lost_reason: str | None = None
    amount: int | None = None


class RecordIn(BaseModel):
    case_id: str
    case_category: str
    text: str
    request_id: str
    source_ref: str
    department: str
    contract_signed: bool = True


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "role": user.role, "department": user.department}


@app.get("/api/leads")
def list_leads(
    status: str | None = None, q: str | None = None, limit: int = Query(50, le=200),
    user: User = Depends(current_user), index: LeadIndex = Depends(get_index),
):
    return {"items": index.search(visible_filter(user), status=status, q=q, limit=limit)}


@app.get("/api/leads/{lid}")
def read_lead(lid: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    lead = _guard(service.get_lead, session, user, lid)
    return {**to_doc(lead), "human_edited": lead.human_edited,
            "evidence": [{"id": e.id, "quote": e.quote, "source_ref": e.source_ref} for e in lead.evidence]}


@app.post("/api/leads", status_code=201)
def create_report(body: ReportIn, user: User = Depends(current_user), session: Session = Depends(get_session),
                  index: LeadIndex = Depends(get_index)):
    lead = _guard(service.report_lead, session, index, user, **body.model_dump(), now=now())
    return to_doc(lead)


@app.patch("/api/leads/{lid}")
def patch_lead(lid: str, body: PatchIn, user: User = Depends(current_user), session: Session = Depends(get_session),
               index: LeadIndex = Depends(get_index)):
    lead = _guard(service.update_lead, session, index, notifier, user, lid, **body.model_dump(), now=now())
    return to_doc(lead)


@app.put("/api/leads/{lid}/customer")
def put_customer(lid: str, body: CustomerIn, user: User = Depends(current_user),
                 session: Session = Depends(get_session), index: LeadIndex = Depends(get_index)):
    return to_doc(_guard(service.set_customer, session, index, user, lid, body.customer_id, now()))


@app.post("/api/leads/{lid}/opportunity")
def post_stage(lid: str, body: StageIn, user: User = Depends(current_user),
               session: Session = Depends(get_session), index: LeadIndex = Depends(get_index)):
    opp = _guard(service.advance_opportunity, session, index, user, lid, body.stage,
                 lost_reason=body.lost_reason, amount=body.amount, now=now())
    return {"stage": opp.stage, "lost_reason": opp.lost_reason, "amount": opp.amount}


@app.get("/api/reports/{name}")
def get_report(name: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    if not can(user, Action.VIEW_REPORTS):
        raise HTTPException(403)
    fn = {"departments": reports.department_summary, "reviewers": reports.reviewer_confirmation,
          "lost-reasons": reports.lost_reasons}.get(name)
    if fn is None:
        raise HTTPException(404)
    return fn(session)


@app.post("/api/assistant/tools/{name}")
def assistant_call(name: str, args: dict, user: User = Depends(current_user),
                   session: Session = Depends(get_session), index: LeadIndex = Depends(get_index)):
    return _guard(assistant_tools.call, session, index, user, name, args, now())


@app.post("/api/ingest")
def ingest(body: RecordIn, user: User = Depends(current_user), session: Session = Depends(get_session),
           index: LeadIndex = Depends(get_index), llm: LLMClient = Depends(get_llm)):
    """분석 플랫폼이 단방향으로 발행한 사건 기록을 받아 리드를 발굴한다."""
    if user.role != Role.ADMIN:
        raise HTTPException(403)
    record = CaseRecord(**body.model_dump())
    result = run(record, llm)
    leads = service.ingest_auto(session, index, record, result, now())
    return {
        "accepted": [lead.id for lead in leads],
        "rejected": [{"category": r.candidate.category, "reason": r.reason} for r in result.rejected],
        "error": result.error,
    }
