"""어댑터 G — 알리미 학과정보 (T6, pubinfo0081 JSON API).

UbiReport viewer 우회 / requests 기반.
충남대 학과 104개 × 8 통계 지표 일괄 수집.

API 매핑 (사용자 정찰 2026-05-26):
  selectMjrList.do        → 학과 메타 리스트
  selectFreshStudentRate  → 학과별 통계 (flag 파라미터로 통계 종류 결정)
    v1 = 신입생 경쟁률 (학사 D-통계)
    v2 = 재학생 수    (학사 D-통계)
    v4 = 입학 정원    (학사 D-통계)
    v5 = 학생 1인당 연간 장학금
    v6 = (추가 통계, val/val2/val3/val4 다중값)
    v7 = 취업률       (진로·취업 D-통계 핵심)
    v8 = 평균 등록금
    v3 = (추가 통계, val/val2 다중값)
"""
from __future__ import annotations

import sys
import time
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from crawler.schema import Chunk  # noqa: E402


# ============================================================================
# 상수
# ============================================================================
BASE = "https://www.academyinfo.go.kr"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

# flag → 통계 종류
STAT_FLAGS: dict[str, dict] = {
    "v1": {"name": "신입생 경쟁률", "unit": "대1", "category": "1.7", "domain": 1},
    "v2": {"name": "재학생 수",     "unit": "명",  "category": "1.7", "domain": 1},
    "v3": {"name": "통계 v3",       "unit": "",    "category": "1.7", "domain": 1},
    "v4": {"name": "입학 정원",     "unit": "명",  "category": "1.7", "domain": 1},
    "v5": {"name": "학생 1인당 연간 장학금", "unit": "천원", "category": "6.1", "domain": 6},
    "v6": {"name": "통계 v6",       "unit": "",    "category": "1.7", "domain": 1},
    "v7": {"name": "취업률",        "unit": "%",   "category": "7.5", "domain": 7},
    "v8": {"name": "평균 등록금",   "unit": "천원", "category": "6.2", "domain": 6},
}


@dataclass
class DeptMeta:
    """학과 1개 메타."""
    mjr_id: str
    schl_mjr_id: str
    schl_id: str
    mjr_nm: str         # 학과명
    clg_nm: str         # 단대학명
    schl_mjr_char_nm: str
    dght_div_nm: str
    kor_schl_nm: str
    srs_lclft_nm: str   # 계열 대분류 (자연과학 / 공학 / 인문ㆍ사회 등)
    srs_mclft_nm: str   # 계열 중분류
    srs_sclft_nm: str   # 계열 소분류
    raw: dict = field(default_factory=dict)


@dataclass
class DeptStat:
    """학과별 한 통계 (flag) 결과."""
    dept: DeptMeta
    flag: str            # v1~v8
    stat_name: str
    svy_yr: str
    entries: list[dict] = field(default_factory=list)  # [{"year": "2023", "val": "26.9"}, ...]
    raw_response: str = ""
    error: str = ""


# ============================================================================
# Adapter 본체
# ============================================================================
class DeptInfoAdapter:
    """알리미 pubinfo0081 학과정보 API 어댑터."""

    INIT_URL_1 = f"{BASE}/pubinfo/pubinfo1600/doInit.do"
    INIT_URL_2 = f"{BASE}/pubinfo/pubinfo0081/doInit.do"
    MJR_LIST_URL = f"{BASE}/pubinfo/pubinfo1600/selectMjrList.do"
    STATS_URL = f"{BASE}/pubinfo/pubinfo0081/selectFreshStudentRate.do"

    def __init__(self, schl_id: str = "0000029", sleep_between: float = 0.5) -> None:
        self.schl_id = schl_id
        self.sleep = sleep_between
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept-Language": "ko-KR,ko;q=0.7",
        })
        self._initialized = False

    def init_session(self) -> None:
        """JSESSIONID / WMONID 쿠키 발급."""
        self.session.get(self.INIT_URL_1, params={"schlId": self.schl_id}, timeout=20)
        self.session.get(self.INIT_URL_2, timeout=20)
        self._initialized = True

    def list_depts(self, svy_yr: str = "2025") -> list[DeptMeta]:
        """충남대 학과 메타 리스트 (104개)."""
        if not self._initialized:
            self.init_session()
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE,
            "Referer": f"{self.INIT_URL_1}?schlId={self.schl_id}",
        }
        data = {
            "svyYr": svy_yr, "schlId": self.schl_id, "pulYn": "true",
            "schl_div_cd": "02", "schl_knd_cd": "03",
            "schlMjrId": "", "mjrId": "", "mjrNm": "", "schNm": "",
            "stsCode": "", "pageIdx": "", "dgHtDivCdArr": "",
            "schMjrCharCdArr": "", "schTxt": "",
            "srsLclftCd": "", "srsMclftCd": "", "srsSclftCd": "",
        }
        r = self.session.post(self.MJR_LIST_URL, data=data, headers=headers, timeout=30)
        r.raise_for_status()
        rl = r.json().get("resultList", [])
        depts = []
        for d in rl:
            depts.append(DeptMeta(
                mjr_id=d.get("mjr_id", ""),
                schl_mjr_id=d.get("schl_mjr_id", ""),
                schl_id=self.schl_id,
                mjr_nm=d.get("mjr_nm", ""),
                clg_nm=d.get("clg_nm", "") or d.get("kor_cd_nm", ""),
                schl_mjr_char_nm=d.get("schl_mjr_char_nm", ""),
                dght_div_nm=d.get("dght_div_nm", ""),
                kor_schl_nm=d.get("kor_schl_nm", ""),
                srs_lclft_nm=d.get("srs_lclft_nm", ""),
                srs_mclft_nm=d.get("srs_mclft_nm", ""),
                srs_sclft_nm=d.get("srs_sclft_nm", ""),
                raw=d,
            ))
        return depts

    def fetch_stat(self, dept: DeptMeta, flag: str, svy_yr: str = "2026") -> DeptStat:
        """학과 1개 + flag 1개 → 시계열 통계."""
        if not self._initialized:
            self.init_session()
        meta = STAT_FLAGS.get(flag, {"name": flag, "unit": ""})
        stat = DeptStat(
            dept=dept, flag=flag,
            stat_name=meta["name"], svy_yr=svy_yr,
        )
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE,
            "Referer": self.INIT_URL_2,
        }
        data = {
            "svyYr": svy_yr,
            "schlMjrId": dept.schl_mjr_id, "schlId": dept.schl_id,
            "mjrId": dept.mjr_id,
            "flag": flag, "tabSelect": "d1",
            "schlMjrIdSe": dept.schl_mjr_id, "schlIdSe": dept.schl_id,
            "mjrIdSe": dept.mjr_id,
            "mjrIdDt": "", "mjrNm": "undefined", "schNm": dept.kor_schl_nm,
            "col1": "장학금", "col2": "등록금", "col3": "취업률",
            "col4": "교원 1인당 학생", "col5": "재정학생수",
            "title": "",
            **{f"header{i}": "" for i in range(1, 10)},
        }
        try:
            r = self.session.post(self.STATS_URL, data=data, headers=headers, timeout=20)
            if r.status_code != 200:
                stat.error = f"status {r.status_code}"
                return stat
            stat.raw_response = r.text[:5000]
            js = r.json()
            stat.entries = js.get("resultList", []) or []
        except Exception as e:
            stat.error = str(e)[:200]
        return stat

    def fetch_all_stats(
        self, dept: DeptMeta, flags: Optional[list[str]] = None, svy_yr: str = "2026"
    ) -> list[DeptStat]:
        """학과 1개 × 모든 flag (default v1~v8)."""
        if flags is None:
            flags = list(STAT_FLAGS.keys())
        stats = []
        for f in flags:
            s = self.fetch_stat(dept, f, svy_yr)
            stats.append(s)
            time.sleep(self.sleep)
        return stats


# ============================================================================
# Chunk 변환
# ============================================================================
def stat_to_sentence(stat: DeptStat) -> list[str]:
    """학과 + 통계 → 자연어 문장 리스트 (시계열 entry당 1문장)."""
    d = stat.dept
    dept_label = " ".join(x for x in [d.kor_schl_nm, d.clg_nm, d.mjr_nm] if x).strip()
    qualifiers = " ".join(x for x in [d.dght_div_nm, d.schl_mjr_char_nm] if x).strip()
    if qualifiers:
        dept_label = f"{dept_label} ({qualifiers})"

    meta = STAT_FLAGS.get(stat.flag, {})
    unit = meta.get("unit", "")
    sentences = []
    for e in stat.entries:
        year = e.get("year", "")
        # primary value
        val = str(e.get("val", "")).strip()
        if not val:
            continue
        parts = [dept_label]
        if year:
            parts.append(f"{year}년")
        parts.append(f"{stat.stat_name}")
        suffix = f"{val}{unit}".strip()
        # multi-value (val2, val3, val4)
        extras = []
        for k in ("val2", "val3", "val4"):
            v = e.get(k)
            if v not in (None, "", 0):
                extras.append(f"{k}={v}")
        if extras:
            suffix = f"{suffix} ({', '.join(extras)})"
        parts.append(suffix)
        # 출처
        sentences.append(
            " ".join(parts).strip()
            + f" [출처: 대학알리미 학과정보, flag={stat.flag}]"
        )
    return sentences


def stat_to_chunks(stat: DeptStat) -> list[Chunk]:
    """DeptStat → Chunk 리스트 (시계열 entry당 1 청크)."""
    if not stat.entries or stat.error:
        return []
    chunks = []
    meta = STAT_FLAGS.get(stat.flag, {})
    domain = meta.get("domain", 9)
    category = meta.get("category", "")
    d = stat.dept
    source_url = (
        f"https://www.academyinfo.go.kr/pubinfo/pubinfo0081/doInit.do"
        f"#schlId={d.schl_id}&schlMjrId={d.schl_mjr_id}&mjrId={d.mjr_id}&flag={stat.flag}"
    )
    sentences = stat_to_sentence(stat)
    for idx, sent in enumerate(sentences):
        chunks.append(Chunk(
            text=sent,
            source_type="T6",
            source_url=source_url,
            source_title=f"대학알리미 학과정보 - {d.mjr_nm} {stat.stat_name}",
            domains=[domain],
            chunk_index=idx,
            categories=[category] if category else [],
            freshness="dated",
            posted_at=f"{stat.svy_yr}-01-01",
            section_path=f"{d.clg_nm} > {d.mjr_nm} > {stat.stat_name}",
            notes=f"flag={stat.flag} schl_mjr_id={d.schl_mjr_id} mjr_id={d.mjr_id}",
        ))
    return chunks
