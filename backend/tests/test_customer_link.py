from app.customer_link import link_customer, normalize_business_number, normalize_company_name
from app.models import Customer, Lead


def test_normalize_company_name():
    for raw in ["가온테크(주)", "㈜가온테크", "주식회사 가온 테크", "가온테크 주식회사", "(주) 가온-테크"]:
        assert normalize_company_name(raw) == "가온테크"
    assert normalize_company_name("Acme Co., Ltd.") == normalize_company_name("ACME Inc.") == "acme"


def test_normalize_business_number():
    assert normalize_business_number("123-45-67890") == "1234567890"
    assert normalize_business_number("123-45-6789") is None


def _lead(**kw):
    return Lead(id="x", case_id="c", category="노무", source="auto", title="t", department="d", human_edited=[], **kw)


def test_business_number_wins_over_name(session):
    lead = _lead(company_name="누리물산", business_number="123-45-67890")
    assert link_customer(session, lead).id == 1 and lead.customer_link == "auto_bn"


def test_name_fallback(session):
    lead = _lead(company_name="누리 물산(주)")
    assert link_customer(session, lead).id == 2 and lead.customer_link == "auto_name"


def test_ambiguous_name_is_not_linked(session):
    session.add(Customer(id=3, name="누리물산(유)", normalized_name="누리물산"))
    session.commit()
    lead = _lead(company_name="누리물산")
    assert link_customer(session, lead) is None and lead.customer_id is None


def test_manual_link_is_protected(session):
    lead = _lead(company_name="가온테크", customer_id=2, customer_link="manual")
    assert link_customer(session, lead).id == 2 and lead.customer_link == "manual"
