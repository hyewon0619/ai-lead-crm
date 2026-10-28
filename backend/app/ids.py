"""결정적(idempotent) ID.

발굴 배치는 재시도·재실행이 잦다. ID를 입력값에서 결정적으로 만들어
같은 입력이 몇 번 들어와도 결과가 한 건으로 수렴하게 한다.
"""

import hashlib
import re


def _digest(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:24]


def lead_id(case_id: str, category: str) -> str:
    return _digest("lead", case_id.strip(), category.strip())


def evidence_id(request_id: str, quote: str) -> str:
    # 공백 차이만 있는 같은 인용은 같은 근거로 본다.
    return _digest("evidence", request_id, re.sub(r"\s+", " ", quote).strip())
