"""크롤러 공용 HTTP 헬퍼.

- 충남대 사이트는 대부분 UTF-8이지만 일부 EUC-KR 가능성 있음 → apparent_encoding 활용
- 학교 IP 차단 리스크 회피: User-Agent 명시, 요청 간 sleep, 429/5xx 백오프
- robots.txt는 Phase B 본격 진행 전 한 번 확인 (TODO)
"""

from __future__ import annotations

import time
from typing import Optional

import requests

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "NLP-TP-Sprint0/0.1 (Academic crawler; contact: cnunlp2023@gmail.com)"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

DEFAULT_TIMEOUT = 15
DEFAULT_SLEEP = 0.8  # 매 요청 후 (Sprint 0은 PoC라 보수적으로)


class HttpClient:
    def __init__(
        self,
        headers: Optional[dict] = None,
        timeout: int = DEFAULT_TIMEOUT,
        sleep_between: float = DEFAULT_SLEEP,
    ):
        self.session = requests.Session()
        self.session.headers.update(headers or DEFAULT_HEADERS)
        self.timeout = timeout
        self.sleep_between = sleep_between

    def get(self, url: str, *, params: Optional[dict] = None, retries: int = 3) -> requests.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(retries):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    raise requests.HTTPError(f"{resp.status_code} from {url}")
                # 인코딩 자동 보정 (한국 사이트 EUC-KR 흔함)
                if resp.encoding and resp.encoding.lower() == "iso-8859-1":
                    resp.encoding = resp.apparent_encoding
                time.sleep(self.sleep_between)
                return resp
            except (requests.RequestException, requests.HTTPError) as e:
                last_exc = e
                backoff = (2 ** attempt) * 1.0
                time.sleep(backoff)
        assert last_exc is not None
        raise last_exc

    def get_text(self, url: str, *, params: Optional[dict] = None) -> str:
        resp = self.get(url, params=params)
        return resp.text

    def get_bytes(self, url: str, *, params: Optional[dict] = None) -> bytes:
        resp = self.get(url, params=params)
        return resp.content
