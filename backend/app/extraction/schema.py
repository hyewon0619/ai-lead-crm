"""LLM 출력 스키마.

모델에는 JSON Schema 를 그대로 넘겨 형식을 강제하고, 돌아온 응답은
같은 Pydantic 모델로 다시 검증한다. 형식이 틀린 응답은 버린다.
"""

from typing import Literal

from pydantic import BaseModel, Field

CATEGORIES = ("노무", "지식재산", "공정거래", "세무", "부동산", "개인정보", "기업분쟁", "형사")

Category = Literal["노무", "지식재산", "공정거래", "세무", "부동산", "개인정보", "기업분쟁", "형사"]


class Candidate(BaseModel):
    """1단계 추출 결과 한 건."""

    category: Category
    title: str = Field(max_length=80)
    quote: str = Field(description="근거가 되는 원문 문장. 반드시 원문 그대로 옮긴다.")
    company_name: str | None = None
    business_number: str | None = None


class ExtractionResult(BaseModel):
    candidates: list[Candidate]


class Verdict(BaseModel):
    """2단계 검증 결과. 하나라도 걸리면 버린다."""

    quote_supports_issue: bool
    is_derivative: bool = Field(description="현재 수임 사건 자체이거나 거기서 당연히 파생되는 쟁점인가")
    is_hypothetical: bool = Field(description="실제 발생한 일이 아니라 가정·우려·가능성인가")
    is_resolved: bool = Field(description="이미 합의·종결되어 다툼이 끝났는가")
    reason: str = ""


def json_schema(model: type[BaseModel]) -> dict:
    return model.model_json_schema()
