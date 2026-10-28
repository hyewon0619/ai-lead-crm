"""LLM 없이 데모를 돌리기 위한 키워드 기반 대체 구현.

실제 판단 품질과는 무관하다. 파이프라인 · 저장 · 화면이 끝까지 이어지는지
확인하는 용도로만 쓴다(LOCAL_LLM_URL=offline).
"""

import re

from pydantic import BaseModel

from .schema import Candidate, ExtractionResult, Verdict

KEYWORDS = {
    "노무": ("해고", "임금", "퇴직금", "근로", "산재"),
    "지식재산": ("특허", "상표", "저작권", "영업비밀"),
    "공정거래": ("하도급", "담합", "공정위", "갑질"),
    "세무": ("세무조사", "가산세", "추징", "부가세"),
    "부동산": ("임대차", "보증금", "명도", "등기"),
    "개인정보": ("개인정보", "유출", "해킹"),
    "기업분쟁": ("주주", "경영권", "대금", "손해배상"),
}
_COMPANY = re.compile(r"([가-힣A-Za-z]+(?:\(주\)|㈜| 주식회사))")


class OfflineLLM:
    name = "offline"

    def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        if schema is ExtractionResult:
            text = user.split("[사건 기록]", 1)[-1]
            out = []
            for sentence in re.split(r"(?<=[.다])\s+", text):
                for cat, words in KEYWORDS.items():
                    if any(w in sentence for w in words):
                        m = _COMPANY.search(text)
                        out.append(Candidate(category=cat, title=f"{cat} 관련 추가 자문 수요",
                                             quote=sentence.strip(), company_name=m.group(1) if m else None))
                        break
            return ExtractionResult(candidates=out)
        if schema is Verdict:
            quote = user.split("[근거 인용]", 1)[-1].split("[인용 주변 문맥]", 1)[0]
            return Verdict(quote_supports_issue=True, is_derivative=False,
                           is_hypothetical="우려" in quote, is_resolved="종결" in quote)
        raise ValueError(schema)
