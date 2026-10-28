from app.extraction.pipeline import CaseRecord, quote_in_source, run
from tests.conftest import ScriptedLLM

TEXT = (
    "의뢰회사 가온테크(주) 대표와 대금 소송 진행 상황을 점검했다. "
    "대표는 지난달 퇴사한 직원이 미지급 퇴직금으로   노동청 진정을 냈다고 말했다. "
    "향후 상표 분쟁이 생길 우려가 있다고도 했다. "
    "작년 하도급 분쟁은 합의 완료되어 끝났다."
)
OK = {"quote_supports_issue": True, "is_derivative": False, "is_hypothetical": False, "is_resolved": False}


def record(**kw):
    base = dict(case_id="C-1", case_category="기업분쟁", text=TEXT, request_id="r1", source_ref="note:1", department="자문1팀")
    return CaseRecord(**{**base, **kw})


def cand(category, quote, title="t"):
    return {"category": category, "title": title, "quote": quote}


def test_quote_match_ignores_whitespace_only():
    assert quote_in_source("미지급 퇴직금으로 노동청 진정을 냈다고", TEXT)
    assert not quote_in_source("미지급 임금으로 노동청 진정을 냈다고", TEXT)  # 한 단어라도 바뀌면 탈락
    assert not quote_in_source("퇴직금", TEXT)  # 너무 짧은 인용은 근거로 인정하지 않는다


def test_precision_filters():
    llm = ScriptedLLM(
        {"candidates": [
            cand("노무", "지난달 퇴사한 직원이 미지급 퇴직금으로 노동청 진정을 냈다고 말했다."),
            cand("세무", "세무조사 사전통지를 받았다고 말했다."),  # 원문에 없는 인용 (환각)
            cand("지식재산", "향후 상표 분쟁이 생길 우려가 있다고도 했다."),  # 가정
            cand("공정거래", "작년 하도급 분쟁은 합의 완료되어 끝났다."),  # 종결
            cand("기업분쟁", "대금 소송 진행 상황을 점검했다."),  # 현재 사건 그 자체
        ]},
        verdicts=[OK],
    )
    res = run(record(), llm)
    assert [a.candidate.category for a in res.accepted] == ["노무"]
    assert {r.candidate.category: r.reason for r in res.rejected} == {
        "세무": "quote_not_in_source",
        "지식재산": "hypothetical_rule",
        "공정거래": "resolved_rule",
        "기업분쟁": "same_as_current_case",
    }
    # 결정적 검사에서 걸러진 후보는 검증 LLM 을 부르지 않는다.
    assert llm.calls == ["ExtractionResult", "Verdict"]


def test_verifier_can_reject():
    q = "지난달 퇴사한 직원이 미지급 퇴직금으로 노동청 진정을 냈다고 말했다."
    res = run(record(), ScriptedLLM({"candidates": [cand("노무", q)]}, [{**OK, "is_derivative": True}]))
    assert res.accepted == [] and res.rejected[0].reason == "derivative"


def test_verifier_failure_rejects():
    class Broken(ScriptedLLM):
        def complete_json(self, system, user, schema):
            if schema.__name__ == "Verdict":
                from app.extraction.llm import LLMError
                raise LLMError("timeout")
            return super().complete_json(system, user, schema)

    q = "지난달 퇴사한 직원이 미지급 퇴직금으로 노동청 진정을 냈다고 말했다."
    res = run(record(), Broken({"candidates": [cand("노무", q)]}))
    assert res.accepted == [] and res.rejected[0].reason == "verify_failed"


def test_routing_by_length():
    from app.extraction.llm import RoutingClient

    local, external = object(), object()
    r = RoutingClient(local, external, local_max_chars=100)
    assert r.pick("a" * 100) is local
    assert r.pick("a" * 101) is external
    assert RoutingClient(local, None, 100).pick("a" * 101) is local
