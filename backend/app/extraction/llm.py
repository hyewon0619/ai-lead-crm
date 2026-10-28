"""LLM 호출 계층.

기본은 사내(로컬) 모델이다. 입력이 로컬 모델 컨텍스트를 넘을 때만
외부 API 로 넘긴다. 둘 다 OpenAI 호환 chat/completions 형식을 가정한다.
"""

import json
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError

from ..config import settings


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    name: str

    def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel: ...


class OpenAICompatibleClient:
    def __init__(self, name: str, base_url: str, model: str, api_key: str | None = None, timeout: float = 60):
        self.name, self.base_url, self.model = name, base_url.rstrip("/"), model
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.timeout = timeout

    def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema(), "strict": True},
            },
        }
        try:
            res = httpx.post(f"{self.base_url}/chat/completions", json=payload, headers=self.headers, timeout=self.timeout)
            res.raise_for_status()
            content = res.json()["choices"][0]["message"]["content"]
            return schema.model_validate(json.loads(content))
        except (httpx.HTTPError, KeyError, json.JSONDecodeError, ValidationError) as e:
            raise LLMError(f"{self.name}: {e}") from e


class RoutingClient:
    """입력 길이로 로컬/외부 모델을 고른다."""

    name = "routing"

    def __init__(self, local: LLMClient, external: LLMClient | None, local_max_chars: int):
        self.local, self.external, self.local_max_chars = local, external, local_max_chars

    def pick(self, user: str) -> LLMClient:
        if len(user) > self.local_max_chars and self.external is not None:
            return self.external
        return self.local

    def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        return self.pick(user).complete_json(system, user, schema)


def default_client() -> LLMClient:
    local = OpenAICompatibleClient("local", settings.local_llm_url, settings.local_llm_model)
    external = (
        OpenAICompatibleClient("external", settings.external_llm_url, settings.external_llm_model, settings.external_llm_key)
        if settings.external_llm_url
        else None
    )
    return RoutingClient(local, external, settings.local_max_chars)
