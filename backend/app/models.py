"""원장(ledger) 테이블.

검색·목록은 인덱스가 담당하고, 상태 변경의 기준은 항상 이 원장이다.
인덱스가 깨져도 원장에서 백필로 다시 만들 수 있어야 한다.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(StrEnum):
    ADMIN = "admin"
    REVIEWER = "reviewer"  # 리드를 확인하고 배당하는 검토자
    MEMBER = "member"  # 제보만 하는 일반 직원


class LeadStatus(StrEnum):
    NEW = "미확인"
    CONTACTED = "연락함"
    INTERESTED = "관심있음"
    ON_HOLD = "보류"
    EXCLUDED = "제외"
    ASSIGNED = "배당"


class OpportunityStage(StrEnum):
    CALL = "콜"
    BOOKED = "예약"
    VISITED = "방문"
    WON = "선임"
    LOST = "미선임"


class LeadSource(StrEnum):
    REPORT_FORM = "report_form"  # 직원 제보 - 웹 폼
    REPORT_ASSISTANT = "report_assistant"  # 직원 제보 - AI 비서 자연어
    AUTO = "auto"  # 사건 기록 자동 발굴


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    department: Mapped[str] = mapped_column(String(50))
    role: Mapped[Role] = mapped_column(String(20))
    # 검토자별 검토 시작 시점. 이 이전에 들어온 리드는 확인율 분모에서 뺀다.
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    normalized_name: Mapped[str] = mapped_column(String(100), index=True)
    business_number: Mapped[str | None] = mapped_column(String(10), unique=True, nullable=True)


class Lead(Base):
    __tablename__ = "leads"

    # case_id + category 로 만든 결정적 ID. 같은 사건에서 같은 범주가
    # 다시 발굴돼도 새 리드가 생기지 않는다.
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(50), index=True)
    category: Mapped[str] = mapped_column(String(30))
    source: Mapped[LeadSource] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    company_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_number: Mapped[str | None] = mapped_column(String(10), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    customer_link: Mapped[str | None] = mapped_column(String(20), nullable=True)  # auto_bn / auto_name / manual
    department: Mapped[str] = mapped_column(String(50))
    status: Mapped[LeadStatus] = mapped_column(String(10), default=LeadStatus.NEW)
    status_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reporter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # 사람이 한 번이라도 고친 필드. AI 재발굴은 이 필드를 덮어쓰지 않는다.
    human_edited: Mapped[list[str]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    evidence: Mapped[list["Evidence"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    opportunity: Mapped["Opportunity | None"] = relationship(back_populates="lead", uselist=False)


class Evidence(Base):
    __tablename__ = "evidence"

    # request_id + 내용 해시. 같은 요청을 재시도해도 근거가 중복 저장되지 않는다.
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    request_id: Mapped[str] = mapped_column(String(64))
    quote: Mapped[str] = mapped_column(Text)
    source_ref: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime)

    lead: Mapped[Lead] = relationship(back_populates="evidence")


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (UniqueConstraint("lead_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    stage: Mapped[OpportunityStage] = mapped_column(String(10), default=OpportunityStage.CALL)
    lost_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    lead: Mapped[Lead] = relationship(back_populates="opportunity")
