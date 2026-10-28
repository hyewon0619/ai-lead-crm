"""리드 검색 인덱스.

운영에서는 Elasticsearch 단일 인덱스(strict 매핑)를 쓴다. 매핑에 없는
필드가 들어오면 색인 자체가 실패하므로, 스키마가 조용히 불어나는 일이 없다.
배포 순서는 매핑 → 코드 배포 → 백필 이다(scripts/backfill.py).

로컬 실행과 테스트는 같은 인터페이스의 메모리 구현을 쓴다.
"""

import json
from pathlib import Path
from typing import Protocol

import httpx

from .models import Lead

MAPPING_PATH = Path(__file__).resolve().parent.parent / "es" / "leads_mapping.json"


def to_doc(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "case_id": lead.case_id,
        "category": lead.category,
        "source": lead.source,
        "title": lead.title,
        "summary": lead.summary,
        "company_name": lead.company_name,
        "customer_id": lead.customer_id,
        "department": lead.department,
        "status": lead.status,
        "reviewer_id": lead.reviewer_id,
        "reporter_id": lead.reporter_id,
        "stage": lead.opportunity.stage if lead.opportunity else None,
        "version": lead.version,
        "created_at": lead.created_at.isoformat(),
        "updated_at": lead.updated_at.isoformat(),
    }


class LeadIndex(Protocol):
    def upsert(self, doc: dict) -> None: ...
    def search(self, visibility: dict, status: str | None = None, q: str | None = None, limit: int = 50) -> list[dict]: ...


def _visible(doc: dict, visibility: dict) -> bool:
    if "any_of" in visibility:
        return any(doc.get(k) == v for k, v in visibility["any_of"].items())
    if "reporter_id" in visibility and doc.get("reporter_id") != visibility["reporter_id"]:
        return False
    if "source_not" in visibility and doc.get("source") == visibility["source_not"]:
        return False
    return True


class InMemoryIndex:
    def __init__(self):
        self.allowed = set(json.loads(MAPPING_PATH.read_text())["mappings"]["properties"])
        self.docs: dict[str, dict] = {}

    def upsert(self, doc: dict) -> None:
        unknown = set(doc) - self.allowed
        if unknown:  # ES strict 매핑과 같은 동작
            raise ValueError(f"strict mapping: unknown fields {sorted(unknown)}")
        self.docs[doc["id"]] = doc

    def search(self, visibility: dict, status: str | None = None, q: str | None = None, limit: int = 50) -> list[dict]:
        hits = [
            d for d in self.docs.values()
            if _visible(d, visibility)
            and (status is None or d["status"] == status)
            and (not q or q in d["title"] or q in (d["summary"] or "") or q in (d["company_name"] or ""))
        ]
        return sorted(hits, key=lambda d: d["updated_at"], reverse=True)[:limit]


class ElasticsearchIndex:
    def __init__(self, url: str, index: str):
        self.base, self.index = url.rstrip("/"), index

    def create(self) -> None:
        mapping = json.loads(MAPPING_PATH.read_text())
        httpx.put(f"{self.base}/{self.index}", json=mapping).raise_for_status()

    def upsert(self, doc: dict) -> None:
        httpx.put(f"{self.base}/{self.index}/_doc/{doc['id']}", json=doc).raise_for_status()

    def search(self, visibility: dict, status: str | None = None, q: str | None = None, limit: int = 50) -> list[dict]:
        must: list[dict] = []
        must_not: list[dict] = []
        if "any_of" in visibility:
            should = [{"term": {k: v}} for k, v in visibility["any_of"].items()]
            must.append({"bool": {"should": should, "minimum_should_match": 1}})
        if "reporter_id" in visibility:
            must.append({"term": {"reporter_id": visibility["reporter_id"]}})
        if "source_not" in visibility:
            must_not.append({"term": {"source": visibility["source_not"]}})
        if status:
            must.append({"term": {"status": status}})
        if q:
            must.append({"multi_match": {"query": q, "fields": ["title", "summary", "company_name"]}})
        body = {"size": limit, "query": {"bool": {"must": must, "must_not": must_not}}, "sort": [{"updated_at": "desc"}]}
        res = httpx.post(f"{self.base}/{self.index}/_search", json=body)
        res.raise_for_status()
        return [h["_source"] for h in res.json()["hits"]["hits"]]
