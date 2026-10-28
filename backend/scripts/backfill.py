"""원장(DB) → 검색 인덱스 백필.

배포 순서: 1) 인덱스 매핑 반영  2) 코드 배포  3) 이 스크립트로 백필
매핑이 strict 라서, 새 필드를 쓰는 코드가 매핑보다 먼저 나가면 색인이 실패한다.

    ES_URL=http://localhost:9200 python -m scripts.backfill
"""

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.index import ElasticsearchIndex, to_doc
from app.models import Lead


def main(batch: int = 500) -> None:
    if not settings.es_url:
        raise SystemExit("ES_URL 이 필요하다")
    index = ElasticsearchIndex(settings.es_url, settings.es_index)
    n = 0
    with SessionLocal() as s:
        for lead in s.scalars(select(Lead).execution_options(yield_per=batch)):
            index.upsert(to_doc(lead))
            n += 1
    print(f"backfilled {n}")


if __name__ == "__main__":
    main()
