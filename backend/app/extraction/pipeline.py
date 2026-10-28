"""사건 기록 → 리드 후보 2단계 추출·검증.

정밀도 우선. 1단계가 후보를 넓게 뽑고, 아래 순서로 걸러낸다.
  1) 인용문이 원문에 실제로 있는가 (결정적 검사 - LLM 을 믿지 않는다)
  2) 2단계 LLM 검증: 파생 쟁점 / 가정 / 이미 종결 이면 폐기
  3) 규칙 백업: 가정·종결 표현이 인용문에 있으면 LLM 판정과 무관하게 폐기
버린 후보도 사유와 함께 남겨 프롬프트 개선에 쓴다.
"""

import re
from dataclasses import dataclass, field

from .llm import LLMClient, LLMError
from .prompts import EXTRACT_SYSTEM, EXTRACT_USER, VERIFY_SYSTEM, VERIFY_USER
from .schema import Candidate, ExtractionResult, Verdict

_HYPOTHETICAL = re.compile(r"만약|할\s*수도|될\s*수도|우려|가능성|예정이라면|혹시")
_RESOLVED = re.compile(r"합의\s*완료|합의했|취하했|취하됨|종결됐|종결되었|해결됐|해결되었")
_CONTEXT_CHARS = 300


@dataclass
class CaseRecord:
    case_id: str
    case_category: str
    text: str
    request_id: str
    source_ref: str
    department: str
    contract_signed: bool = True


@dataclass
class Accepted:
    candidate: Candidate


@dataclass
class Rejected:
    candidate: Candidate
    reason: str


@dataclass
class PipelineResult:
    accepted: list[Accepted] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)
    error: str | None = None


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def quote_in_source(quote: str, text: str) -> bool:
    """공백·줄바꿈 차이만 허용한 원문 포함 검사."""
    q = _squash(quote)
    return len(q) >= 8 and q in _squash(text)


def context_around(quote: str, text: str) -> str:
    q = _squash(quote)
    flat = _squash(text)
    i = flat.find(q)
    if i < 0:
        return ""
    return flat[max(0, i - _CONTEXT_CHARS) : i + len(q) + _CONTEXT_CHARS]


def run(record: CaseRecord, llm: LLMClient) -> PipelineResult:
    result = PipelineResult()
    try:
        extracted = llm.complete_json(
            EXTRACT_SYSTEM,
            EXTRACT_USER.format(case_category=record.case_category, text=record.text),
            ExtractionResult,
        )
    except LLMError as e:
        result.error = str(e)
        return result

    seen: set[str] = set()
    for c in extracted.candidates:
        if c.category in seen:
            result.rejected.append(Rejected(c, "duplicate_category"))
            continue
        if c.category == record.case_category:
            result.rejected.append(Rejected(c, "same_as_current_case"))
            continue
        if not quote_in_source(c.quote, record.text):
            result.rejected.append(Rejected(c, "quote_not_in_source"))
            continue
        if _HYPOTHETICAL.search(c.quote):
            result.rejected.append(Rejected(c, "hypothetical_rule"))
            continue
        if _RESOLVED.search(c.quote):
            result.rejected.append(Rejected(c, "resolved_rule"))
            continue

        try:
            v = llm.complete_json(
                VERIFY_SYSTEM,
                VERIFY_USER.format(
                    case_category=record.case_category,
                    category=c.category,
                    title=c.title,
                    quote=c.quote,
                    context=context_around(c.quote, record.text),
                ),
                Verdict,
            )
        except LLMError:
            # 검증을 못 했으면 통과시키지 않는다.
            result.rejected.append(Rejected(c, "verify_failed"))
            continue

        assert isinstance(v, Verdict)
        reason = (
            "quote_not_supporting" if not v.quote_supports_issue
            else "derivative" if v.is_derivative
            else "hypothetical" if v.is_hypothetical
            else "resolved" if v.is_resolved
            else None
        )
        if reason:
            result.rejected.append(Rejected(c, reason))
        else:
            seen.add(c.category)
            result.accepted.append(Accepted(c))
    return result
