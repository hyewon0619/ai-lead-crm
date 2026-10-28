"""리드 ↔ 고객 연결.

1순위 사업자번호, 2순위 정규화한 법인명. 사람이 수동으로 연결한 건은
자동 연결이 다시 건드리지 않는다.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Customer, Lead

_CORP_MARKERS = re.compile(
    r"\(주\)|㈜|\(유\)|\(재\)|\(사\)|주식회사|유한회사|유한책임회사|합자회사|합명회사|재단법인|사단법인"
    r"|\bco\.?,?\s*ltd\.?|\binc\.?|\bcorp\.?|\bltd\.?",
    re.IGNORECASE,
)


def normalize_business_number(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    return digits if len(digits) == 10 else None


def normalize_company_name(raw: str | None) -> str:
    if not raw:
        return ""
    name = _CORP_MARKERS.sub("", raw)
    name = re.sub(r"[\s\-_.,·&()\[\]]", "", name)
    return name.lower()


def link_customer(session: Session, lead: Lead) -> Customer | None:
    if lead.customer_link == "manual":
        return session.get(Customer, lead.customer_id) if lead.customer_id else None

    bn = normalize_business_number(lead.business_number)
    if bn:
        customer = session.scalar(select(Customer).where(Customer.business_number == bn))
        if customer:
            lead.customer_id, lead.customer_link = customer.id, "auto_bn"
            return customer

    norm = normalize_company_name(lead.company_name)
    if norm:
        matches = session.scalars(select(Customer).where(Customer.normalized_name == norm)).all()
        # 같은 정규화 이름이 둘 이상이면 잘못 붙이느니 연결하지 않는다.
        if len(matches) == 1:
            lead.customer_id, lead.customer_link = matches[0].id, "auto_name"
            return matches[0]

    lead.customer_id, lead.customer_link = None, None
    return None


def link_manually(lead: Lead, customer_id: int) -> None:
    lead.customer_id, lead.customer_link = customer_id, "manual"
