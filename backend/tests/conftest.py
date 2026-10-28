from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.index import InMemoryIndex
from app.models import Base, Customer, Role, User
from app.notify import Notifier

T0 = datetime(2026, 3, 2, 9)


class ScriptedLLM:
    """스키마별로 미리 정한 응답을 돌려주는 테스트용 LLM."""

    name = "scripted"

    def __init__(self, extraction, verdicts=None):
        self.extraction, self.verdicts, self.calls = extraction, list(verdicts or []), []

    def complete_json(self, system, user, schema):
        self.calls.append(schema.__name__)
        if schema.__name__ == "ExtractionResult":
            return schema.model_validate(self.extraction)
        return schema.model_validate(self.verdicts.pop(0))


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        s.add_all([
            User(id=1, name="관리자", department="경영지원", role=Role.ADMIN),
            User(id=10, name="검토자A", department="자문1팀", role=Role.REVIEWER, review_started_at=T0),
            User(id=11, name="검토자B", department="자문2팀", role=Role.REVIEWER),
            User(id=20, name="직원A", department="자문1팀", role=Role.MEMBER),
            User(id=21, name="직원B", department="자문1팀", role=Role.MEMBER),
            Customer(id=1, name="가온테크(주)", normalized_name="가온테크", business_number="1234567890"),
            Customer(id=2, name="누리물산 주식회사", normalized_name="누리물산"),
        ])
        s.commit()
        yield s


@pytest.fixture
def index():
    return InMemoryIndex()


@pytest.fixture
def notifier():
    return Notifier()
