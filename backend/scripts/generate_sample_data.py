"""합성 데이터 생성기.

공개 저장소이므로 실제 사건·고객 데이터는 담지 않는다. 등장하는 회사명·
사건번호·인물은 모두 시드 고정 난수로 조합한 가짜다.

    python -m scripts.generate_sample_data   # backend/ 에서 실행
"""

import random
from datetime import datetime, timedelta

from app import service
from app.customer_link import normalize_company_name
from app.db import SessionLocal, engine
from app.extraction.offline_llm import OfflineLLM
from app.extraction.pipeline import CaseRecord, run
from app.index import InMemoryIndex
from app.models import Base, Customer, LeadStatus, OpportunityStage, Role, User
from app.notify import notifier

SEED = 7
DEPARTMENTS = ["기업자문1팀", "기업자문2팀", "분쟁해결팀"]
PREFIX = ["가온", "누리", "다솜", "라온", "마루", "바름", "새솔", "아라", "온새", "한빛"]
SUFFIX = ["테크", "물산", "푸드", "바이오", "로지스", "건설", "미디어", "소프트"]
SENTENCES = {
    "노무": "최근 퇴사한 직원이 미지급 퇴직금 문제로 노동청 진정을 제기했다고 한다.",
    "지식재산": "경쟁사가 자사 제품 디자인과 유사한 상표를 출원한 사실을 확인했다.",
    "공정거래": "원청으로부터 하도급 대금 감액 요구를 서면으로 받았다.",
    "세무": "지난달 관할 세무서에서 세무조사 사전통지를 받았다.",
    "부동산": "본사 사옥 임대차 계약 만료를 앞두고 보증금 반환을 거절당했다.",
    "개인정보": "고객 개인정보 유출 정황이 내부 점검에서 발견됐다.",
}
NOISE = {
    "hypothetical": "향후 노동청 진정이 들어올 우려가 있다는 정도로만 언급했다.",
    "resolved": "작년 상표 분쟁은 상대방과 합의 완료되어 종결됐다.",
}


def company(rng: random.Random) -> str:
    name = rng.choice(PREFIX) + rng.choice(SUFFIX)
    return rng.choice([f"{name}(주)", f"㈜{name}", f"{name} 주식회사"])


def main(n_records: int = 120) -> None:
    rng = random.Random(SEED)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    start = datetime(2026, 1, 5, 9)

    with SessionLocal() as s:
        s.add(User(id=1, name="관리자", department="경영지원", role=Role.ADMIN))
        for i, dept in enumerate(DEPARTMENTS):
            s.add(User(id=10 + i, name=f"검토자{i + 1}", department=dept, role=Role.REVIEWER,
                       review_started_at=start + timedelta(days=14 * i)))
            s.add(User(id=20 + i, name=f"직원{i + 1}", department=dept, role=Role.MEMBER))
        seen = set()
        for i in range(40):
            name = company(rng)
            norm = normalize_company_name(name)
            if norm in seen:
                continue
            seen.add(norm)
            bn = f"{rng.randint(100, 999)}{rng.randint(10, 99)}{rng.randint(10000, 99999)}" if rng.random() < 0.6 else None
            s.add(Customer(id=i + 1, name=name, normalized_name=norm, business_number=bn))
        s.commit()

        index, llm = InMemoryIndex(), OfflineLLM()
        for i in range(n_records):
            cats = rng.sample(list(SENTENCES), k=rng.randint(1, 2))
            body = [f"의뢰회사 {company(rng)} 담당자와 기업분쟁 사건 진행 상황을 점검했다."]
            body += [SENTENCES[c] for c in cats]
            if rng.random() < 0.3:
                body.append(rng.choice(list(NOISE.values())))
            record = CaseRecord(
                case_id=f"2026-C-{1000 + i}", case_category="기업분쟁", text=" ".join(body),
                request_id=f"pub-{i}", source_ref=f"case-note:{i}", department=rng.choice(DEPARTMENTS),
                contract_signed=rng.random() > 0.15,
            )
            when = start + timedelta(hours=8 * i)
            leads = service.ingest_auto(s, index, record, run(record, llm), when)
            admin = s.get(User, 1)
            for lead in leads:
                if lead.status != LeadStatus.NEW or rng.random() < 0.35:
                    continue
                status = rng.choice([LeadStatus.CONTACTED, LeadStatus.INTERESTED, LeadStatus.ASSIGNED,
                                     LeadStatus.ASSIGNED, LeadStatus.ON_HOLD])
                service.update_lead(s, index, notifier, admin, lead.id, base_version=lead.version,
                                    changes={"status": status}, base_values={}, now=when + timedelta(days=1))
                if status == LeadStatus.ASSIGNED:
                    stage = rng.choice(list(OpportunityStage))
                    service.advance_opportunity(
                        s, index, admin, lead.id, stage, now=when + timedelta(days=3),
                        lost_reason=rng.choice(["비용", "타 법인 선임", "자체 해결"]) if stage == OpportunityStage.LOST else None,
                        amount=rng.randrange(300, 3000, 100) * 10000 if stage == OpportunityStage.WON else None,
                    )
        print(f"leads: {len(index.docs)}")


if __name__ == "__main__":
    main()
