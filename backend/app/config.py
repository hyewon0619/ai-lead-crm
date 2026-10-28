"""환경 설정. 공개 저장소이므로 조직 고유 값은 모두 환경변수로 주입한다."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/leads.db")
    # 설정하지 않으면 메모리 인덱스를 쓴다. 로컬 실행·테스트용.
    es_url: str | None = os.getenv("ES_URL")
    es_index: str = os.getenv("ES_INDEX", "leads")
    local_llm_url: str = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")
    local_llm_model: str = os.getenv("LOCAL_LLM_MODEL", "local-model")
    external_llm_url: str | None = os.getenv("EXTERNAL_LLM_URL")
    external_llm_key: str | None = os.getenv("EXTERNAL_LLM_KEY")
    external_llm_model: str = os.getenv("EXTERNAL_LLM_MODEL", "external-model")
    # 로컬 모델 컨텍스트를 넘기는 긴 입력만 외부 API로 보낸다.
    local_max_chars: int = int(os.getenv("LOCAL_MAX_CHARS", "12000"))


settings = Settings()
