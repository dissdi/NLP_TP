"""T2.1 분류기 학습 데이터 빌더.

5-way 분류기(0:졸업요건, 1:공지, 2:학사일정, 3:식단, 4:셔틀) 학습용
train.jsonl / valid_internal.jsonl / d1_eval.jsonl 생성.

외부 LLM API 호출 없이 template + slot fill + 변형 규칙으로 자체 paraphrase.
라벨러 룰(crawler/phase_c_5cat/label_5cat.py)로 사후 재검증해 라벨 drift 차단.

산출물:
    data/classifier/train.jsonl
    data/classifier/valid_internal.jsonl
    data/classifier/d1_eval.jsonl
    data/classifier/reports/class_dist.md
    data/classifier/reports/paraphrase_sample.md
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from collections import Counter
from typing import Iterable

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "data", "classifier")
REPORT_DIR = os.path.join(DATA_DIR, "reports")
D1_LABELS = os.path.join(ROOT, "docs", "scope-rev", "d1-5way-labels.json")
D1_QA = os.path.join(ROOT, "data", "eval", "d1", "eval_v1_2.jsonl")  # fallback resolved later

# Import label rules for post-verification (lightweight version inline)
GRAD_KW = ["졸업학점", "졸업요건", "졸업이수", "학위수여", "전공필수", "교양필수",
           "졸업기준", "졸업사정", "졸업논문", "전공이수학점", "졸업유예",
           "이수구분", "졸업학년", "졸업이수학점"]
SHUTTLE_KW = ["셔틀", "셔틀버스", "통학버스", "교내순환", "캠퍼스버스"]
MEAL_KW = ["식단", "메뉴", "학식", "학생회관 식당", "학생회관식당", "생협 식당",
           "생협식당", "오늘 점심", "오늘 저녁", "오늘 학식", "이번 주 식단",
           "주간 메뉴", "천원의 아침밥", "천원 아침밥", "조식 운영", "식권",
           "교내 식당", "학생식당"]
SCHEDULE_STRONG = ["수강신청", "수강 신청", "수강정정", "수강 정정", "시험기간",
                   "시험 기간", "학사일정", "개강일", "종강일"]
OUT_KW = ["도서관", "스터디룸 예약", "도서 대출", "기숙사", "생활관",
          "재학증명서", "성적증명서", "체육관", "수영장", "응급처치"]


# ---------- 학과 풀 (코퍼스에서 추출 + 수동 보강) ----------
DEPTS = [
    # 인문대학
    "국어국문학과", "국사학과", "사학과", "언어학과", "영어영문학과", "독어독문학과",
    "불어불문학과", "중어중문학과", "일어일문학과", "한문학과", "철학과", "고고학과",
    # 사회과학
    "사회학과", "심리학과", "정치외교학과", "행정학과", "지역개발학과", "언론정보학과",
    "문헌정보학과", "고고미술사학과",
    # 자연과학
    "수학과", "물리학과", "화학과", "생물과학과", "지질환경과학과", "해양환경과학과",
    "천체우주과학과", "정보통계학과",
    # 공학
    "건축학과", "건축공학과", "토목공학과", "환경공학과", "기계공학과", "메카트로닉스공학과",
    "전기공학과", "전자공학과", "컴퓨터공학과", "컴퓨터인공지능학부", "신소재공학과",
    "화학공학과", "응용화학공학과", "유기소재공학과",
    # 농생명과학
    "농업경제학과", "식품공학과", "식품영양학과", "축산학과", "원예학과", "응용생물학과",
    "생물환경화학과", "지역환경토목학과", "동물자원학부", "산림환경자원학과",
    # 경상
    "경영학부", "경제학과", "무역학과",
    # 사범
    "교육학과", "국어교육과", "영어교육과", "수학교육과", "체육교육과", "교육공학과",
    # 의약/약학
    "의예과", "의학과", "약학과", "수의예과", "수의학과", "간호학과",
    # 예술
    "음악과", "관현악과", "회화과", "조소과", "디자인창의학과",
    # 생활과학
    "의류학과", "식품영양학과", "소비자학과",
    # 국제/자율
    "국제학부", "자율전공학부",
]

COLLEGES = ["인문대학", "사회과학대학", "자연과학대학", "공과대학", "농업생명과학대학",
            "경상대학", "사범대학", "의과대학", "약학대학", "예술대학", "생활과학대학",
            "수의과대학", "국제문화학부"]

YEARS = ["2024학년도", "2025학년도", "2026학년도", "2027학년도"]
SEMESTERS = ["1학기", "2학기", "제1학기", "제2학기", "여름학기", "겨울학기"]
SEMESTERS_SHORT = ["1학기", "2학기"]

RESTAURANTS = ["제1학생회관 식당", "제2학생회관 식당", "학생식당", "교직원식당",
               "생협 식당", "학생회관 식당", "인재개발원 식당", "보운관 식당",
               "3학생회관 식당", "1학 식당", "2학 식당", "3학 식당"]

SHUTTLE_ROUTES = ["교내순환", "대덕↔보운", "대덕캠퍼스 셔틀", "보운캠퍼스 셔틀",
                  "셔틀버스", "통학버스", "캠퍼스 셔틀"]

SCHOLARSHIPS = ["국가장학금", "성적우수장학금", "백마장학금", "근로장학금", "교내장학금",
                "복지장학금", "특별장학금", "삼원장학재단 장학금"]


# ---------- 종결어미/구어체 변형 ----------
POLITE_END = ["인가요?", "은가요?", "입니까?", "알려주세요.", "안내해주세요.",
              "확인하고 싶어요.", "궁금합니다."]
INFORMAL_END = ["야?", "임?", "임?ㅋ", "알려줘", "뭐야?", "어디서 봐?", "어떻게 돼?",
                "언제야?", "몇 학점이야?", "어디서 타?"]
NEUTRAL_END = ["?", "은 무엇인가요?", "는 언제인가요?", "어떻게 되나요?"]


def _hash_id(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


# ---------- 클래스별 template 생성 ----------

def gen_grad(rng: random.Random, n: int) -> list[dict]:
    """0 졸업요건"""
    out = []
    templates = [
        "{dept} 졸업학점은 몇 학점인가요?",
        "{dept} 졸업하려면 몇 학점 들어야 해?",
        "{dept} 졸업요건 알려주세요.",
        "{dept} 전공 필수 학점이 얼마예요?",
        "{dept} 전공이수학점 얼마야?",
        "{dept} 교양 필수 학점은요?",
        "{dept} 졸업기준 안내해주세요.",
        "{dept} 졸업논문 의무인가요?",
        "{dept} 학위수여 기준이 어떻게 돼?",
        "{dept} 이수구분별 졸업학점 알려줘.",
        "{college} 졸업요건이 어떻게 되나요?",
        "전공필수 몇 학점 들어야 졸업해요?",
        "교양필수 학점 기준 알려줘.",
        "졸업학점 미달이면 어떻게 되나요?",
        "졸업이수학점 부족할 때 처리는?",
        "충남대학교 졸업학점 총 몇 학점이야?",
        "{dept} 복수전공 졸업요건이 따로 있나요?",
        "{dept} 부전공 인정 학점은요?",
        "졸업유예 신청 가능한가요?",
        "{year} {dept} 졸업이수기준 변경됐어요?",
        "{dept} 학사학위 수여 자격은?",
        "{dept} 졸업사정 어떻게 진행되나요?",
        "전공필수 미이수면 졸업 못해?",
        "{dept} 졸업요건에 영어 시험 포함되나요?",
        "{dept} 졸업하려면 토익 몇 점 필요해?",
    ]
    while len(out) < n:
        t = rng.choice(templates)
        q = t.format(
            dept=rng.choice(DEPTS),
            college=rng.choice(COLLEGES),
            year=rng.choice(YEARS),
        )
        out.append({"text": q, "label": 0, "source": "tpl:grad"})
    return out


def gen_notice(rng: random.Random, n: int) -> list[dict]:
    """1 공지"""
    out = []
    templates = [
        "{year} {sem} {scholar} 신청 자격은 어떻게 되나요?",
        "{scholar} 1인당 금액은 얼마예요?",
        "{scholar} 모집 인원이 어떻게 되나요?",
        "{year} {sem} 등록금 일람표 알려주세요.",
        "등록금 분할납부 신청 방법 알려줘.",
        "{year} 신입생 장학금 종류가 뭐가 있나요?",
        "{dept} 학과 공지 어디서 봐?",
        "충남대학교 채용 공고 어디서 확인해요?",
        "{year} {sem} 봉사활동 모집 안내 있어요?",
        "{year} {sem} 교환학생 파견 프로그램 안내해주세요.",
        "{year} 파란사다리 사업 신청은 어떻게?",
        "한국영상대 교환 프로그램 참여 자격은?",
        "근로장학생 모집 시기가 언제예요?",
        "교내 행사 공지 어디서 보나요?",
        "{year} 학생활동 지원 사업 안내 있어요?",
        "삼원장학재단 장학금 신청 자격이 어떻게 되나요?",
        "백마장학회 장학생 선발 기준이 뭐예요?",
        "통영시 대학생 등록금 지원 사업 신청 기간 알려주세요.",
        "{dept} 학과 공지사항 새로 올라온 거 있어?",
        "충남대 학생증 분실 신고 어떻게 해요?",
        "재무과에서 등록금 환불 받는 방법 알려줘.",
        "교내 학과 공지 받아보는 방법 있나요?",
        "{year} 인턴십 모집 공고 어디 있어요?",
        "외부 장학재단 장학금 정보 어디서 봐요?",
        "학자금 대출 한도 얼마까지인가요?",
        "{year} {sem} 등록금 액수 알려주세요.",
        "수업료 분납 신청 기간 빼고 어떻게 진행되는지 알려줘.",  # tricky: 신청기간 빼고 → 금액·절차는 공지
        "{dept} 학과 사무실 위치 알려주세요.",
        "{dept} 행정실 연락처가 어떻게 되나요?",
        "충남대학교 공지사항 RSS 있어요?",
        "{year} 동아리 신규 등록 절차 알려줘.",
        "{year} 학생회 선거 일정 공지 있나요?",
        "교내 봉사활동 점수 인정 받으려면?",
        "{year} 글로벌 프로그램 신청 가능한가요?",
        "학생증 재발급 방법 안내해주세요.",
        "{dept} 학사학위과정 안내 받고 싶어요.",
        "{year} 신입생 오리엔테이션 안내 어디에?",
    ]
    while len(out) < n:
        t = rng.choice(templates)
        q = t.format(
            year=rng.choice(YEARS),
            sem=rng.choice(SEMESTERS_SHORT),
            scholar=rng.choice(SCHOLARSHIPS),
            dept=rng.choice(DEPTS),
        )
        out.append({"text": q, "label": 1, "source": "tpl:notice"})
    return out


def gen_schedule(rng: random.Random, n: int) -> list[dict]:
    """2 학사일정"""
    out = []
    templates = [
        "{year} {sem} 개강일은 언제인가요?",
        "{year} {sem} 종강일이 언제야?",
        "{year} {sem} 수강신청 기간은 언제인가요?",
        "{year} {sem} 수강 정정 기간 알려주세요.",
        "{year} {sem} 시험 기간이 언제예요?",
        "{year} {sem} 휴학 신청 기간 알려줘.",
        "{year} {sem} 복학 신청 언제부터인가요?",
        "{year} {sem} 등록금 납부 기간 언제예요?",
        "{year} {sem} 폐강 결정일이 언제인가요?",
        "{year} 동기(겨울) 계절학기 수강신청 언제까지?",
        "{year} 하기(여름) 계절학기 수강신청 기간은?",
        "{year} 졸업식 일정 어떻게 돼?",
        "{year} {sem} 성적 발표일 언제야?",
        "{year} {sem} 강의 평가 기간은 언제인가요?",
        "{year} 봄학기 등록 기간 알려주세요.",
        "{year} 가을학기 휴학 신청 마감 언제인가요?",
        "수강신청 정정 며칠까지 가능해요?",
        "{year} {sem} 보강일이 언제예요?",
        "{year} 추가 수강신청 기간 알려줘.",
        "예비 수강신청 일정 어떻게 되나요?",
        "{year} 학사일정 어디서 확인해요?",
        "수강신청 변경 기간이 며칠인가요?",
        "{year} 1학기 등록금 분할납부 신청 기간은요?",
        "장학금 신청 기간이 언제예요?",
        "{year} 일반대학원 폐강 일정 알려줘.",
        "수강신청 클릭이 언제부터 가능한가요?",
        "{year} 신편입생 수강신청 일정 알려주세요.",
        "{year} {sem} 수업일수 며칠인가요?",
        "{year} {sem} 수업 개시일이 언제예요?",
        "{year} 학기 마지막 수업일 언제야?",
    ]
    while len(out) < n:
        t = rng.choice(templates)
        q = t.format(year=rng.choice(YEARS), sem=rng.choice(SEMESTERS_SHORT))
        out.append({"text": q, "label": 2, "source": "tpl:sched"})
    return out


def gen_meal(rng: random.Random, n: int) -> list[dict]:
    """3 식단"""
    out = []
    templates = [
        "오늘 학식 뭐야?",
        "오늘 점심 메뉴 알려줘.",
        "오늘 저녁 학식 메뉴가 뭐예요?",
        "이번 주 식단 알려주세요.",
        "{restaurant} 메뉴 알려줘.",
        "{restaurant} 운영시간 어떻게 돼?",
        "{restaurant} 가격이 얼마예요?",
        "{restaurant} 어디에 있어?",
        "충남대 학식 운영시간 알려주세요.",
        "주간 학식 메뉴 어디서 볼 수 있어요?",
        "천원의 아침밥 운영시간은 어떻게 되나요?",
        "천원의 아침밥 어디서 먹어요?",
        "천원의 아침밥 운영 기간은 언제까지인가요?",
        "조식 운영 어디서 해요?",
        "오늘 생협 식당 메뉴 알려줘.",
        "학생회관 식당 영업시간이 어떻게 돼?",
        "{restaurant} 휴무일이 언제인가요?",
        "교내 식당 종류 어떻게 되나요?",
        "충남대 식권 가격이 얼마예요?",
        "오늘 1학 식당 메뉴 뭐야?",
        "오늘 2학 식당 메뉴는?",
        "오늘 3학 식당 식단 알려줘.",
        "교직원 식당 일반인도 이용 가능해요?",
        "충남대 학식 가격 평균 얼마예요?",
        "충남대 식당 위치 알려주세요.",
        "주간 메뉴표 어디서 받아요?",
        "이번 주 학식 메뉴표 PDF 어디 있어?",
        "이번 주 학식 별로면 어디서 먹어요?",
        "충남대 캠퍼스 안에 식당 몇 개 있어?",
        "충남대 생협 식당 결제 카드 가능?",
    ]
    while len(out) < n:
        t = rng.choice(templates)
        q = t.format(restaurant=rng.choice(RESTAURANTS))
        out.append({"text": q, "label": 3, "source": "tpl:meal"})
    return out


def gen_shuttle(rng: random.Random, n: int) -> list[dict]:
    """4 셔틀"""
    out = []
    templates = [
        "충남대 셔틀버스 시간표 알려주세요.",
        "셔틀버스 정류장 어디에 있어요?",
        "셔틀 운행 시간이 어떻게 돼?",
        "{route} 첫차 시각이 언제인가요?",
        "{route} 막차가 몇 시예요?",
        "{route} 노선이 어떻게 돼요?",
        "{route} 운행 간격이 얼마야?",
        "셔틀버스 어디서 타?",
        "충남대학교 통학버스 시간표 알려줘.",
        "교내순환 셔틀 어디서 타요?",
        "셔틀버스 방학 중에도 운행해요?",
        "셔틀버스 주말에 다녀?",
        "{route} 운행 여부 알려주세요.",
        "셔틀버스 임시 휴차 일정 있나요?",
        "교내순환 첫차 막차 시각 알려주세요.",
        "대덕↔보운 셔틀 운행 시간이 어떻게 돼요?",
        "셔틀 노선도 어디서 봐요?",
        "충남대 캠퍼스 셔틀 무료인가요?",
        "셔틀 운행 중단 안내 어디서 봐요?",
        "{year} 1학기 셔틀버스 일부 구간 통제 있어요?",
        "셔틀 정류장 위치 PDF 있어?",
        "교내 셔틀 버스 몇 분 간격이야?",
        "캠퍼스 순환 셔틀 하루 몇 회 다녀요?",
        "셔틀 환승 가능한가요?",
        "충남대 셔틀 어플 있어요?",
    ]
    while len(out) < n:
        t = rng.choice(templates)
        q = t.format(route=rng.choice(SHUTTLE_ROUTES), year=rng.choice(YEARS))
        out.append({"text": q, "label": 4, "source": "tpl:shuttle"})
    return out


def gen_out_like(rng: random.Random, n: int) -> list[dict]:
    """OUT-like questions, forced label 1 per disambiguation rule."""
    out = []
    templates = [
        # 도서관
        "충남대 도서관 운영시간 알려주세요.",
        "도서관 자료 대출 며칠까지 가능해요?",
        "도서관 그룹스터디룸 예약 어떻게 해요?",
        "의학도서관 위치 어디예요?",
        "도서관 외부인 출입 가능해요?",
        # 기숙사
        "기숙사 입주 신청 어떻게 해요?",
        "기숙사 방 배정 언제 발표돼?",
        "기숙사 식당 메뉴 알려줘.",
        "기숙사 퇴사 절차가 어떻게 되나요?",
        "생활관 호실 변경 가능해요?",
        # 행정/증명서
        "재학증명서 발급 어떻게 해요?",
        "성적증명서 인터넷으로 뽑을 수 있나요?",
        "학생증 분실하면 어떻게 해야 해요?",
        "학생증 사진 변경 가능한가요?",
        "휴학증명서 영문으로 발급 가능해요?",
        # 체육/시설
        "충남대 수영장 이용 시간 알려줘.",
        "체육관 사용료 얼마인가요?",
        "응급처치교육 신청 방법 알려주세요.",
        "정관헌 예약 어떻게 해요?",
        "충남대 주차장 요금 얼마야?",
        # 개인 데이터
        "내 학점 평균 얼마인가요?",
        "내 수강 신청 내역 어디서 봐요?",
    ]
    while len(out) < n:
        t = rng.choice(templates)
        out.append({"text": t, "label": 1, "source": "tpl:out_like"})
    return out


# ---------- Paraphrase 변형 (격식/구어/줄임) ----------

INFORMAL_MAP = [
    ("인가요?", "야?"),
    ("입니까?", "이야?"),
    ("어떻게 되나요?", "어떻게 돼?"),
    ("알려주세요.", "알려줘."),
    ("알려주세요", "알려줘"),
    ("안내해주세요.", "알려줘."),
    ("입니까", "이야"),
    ("언제인가요?", "언제야?"),
    ("얼마인가요?", "얼마야?"),
    ("몇 학점인가요?", "몇 학점이야?"),
    ("어디에 있어요?", "어디 있어?"),
    ("궁금합니다.", "궁금해."),
    ("확인하고 싶어요.", "확인하고 싶어."),
    ("가능한가요?", "돼?"),
    ("가능해요?", "돼?"),
]

SYNONYM_MAP = [
    ("식단", "메뉴"),
    ("학식", "교내 식당"),
    ("셔틀", "셔틀버스"),
    ("통학버스", "교내 셔틀"),
    ("개강일", "수업 시작일"),
    ("종강일", "수업 종료일"),
    ("졸업학점", "졸업 이수 학점"),
    ("학사일정", "학기 일정"),
]


def paraphrase_informal(q: str, rng: random.Random) -> str:
    s = q
    for a, b in INFORMAL_MAP:
        if a in s and rng.random() < 0.6:
            s = s.replace(a, b)
    return s


def paraphrase_synonym(q: str, rng: random.Random) -> str:
    s = q
    for a, b in SYNONYM_MAP:
        if a in s and rng.random() < 0.4:
            s = s.replace(a, b)
    return s


def paraphrase_short(q: str, rng: random.Random) -> str:
    s = q.strip().rstrip(".?")
    # truncate trailing polite suffix
    for suf in ["인가요", "입니까", "알려주세요", "안내해주세요", "어떻게 되나요"]:
        if s.endswith(suf):
            s = s[:-len(suf)].rstrip()
            break
    if rng.random() < 0.5:
        s += "?"
    return s


def apply_variants(items: list[dict], rng: random.Random, factor: int = 2) -> list[dict]:
    """Expand each item with factor-1 variants. Re-verify label after each variant."""
    out = []
    seen = set()
    for it in items:
        for _ in range(factor):
            q = it["text"]
            mode = rng.choice(["base", "informal", "synonym", "short", "informal+syn"])
            if mode == "informal":
                q = paraphrase_informal(q, rng)
            elif mode == "synonym":
                q = paraphrase_synonym(q, rng)
            elif mode == "short":
                q = paraphrase_short(q, rng)
            elif mode == "informal+syn":
                q = paraphrase_informal(paraphrase_synonym(q, rng), rng)
            # else base
            key = q.strip()
            if key in seen or not key:
                continue
            seen.add(key)
            # Label drift check (skip variant if it now hits another class strongly)
            verified = verify_label(q, it["label"])
            if not verified:
                continue
            out.append({"text": q, "label": it["label"], "source": it["source"] + ":" + mode})
    return out


_LABEL_KW = {
    0: ["졸업", "전공필수", "교양필수", "학위수여", "이수구분", "이수 구분",
        "전공이수", "전공 이수", "졸업학점", "졸업이수", "졸업 이수", "졸업요건"],
    2: ["수강신청", "수강 신청", "수강정정", "수강 정정", "시험기간", "시험 기간",
        "학사일정", "개강", "종강", "휴학", "복학", "성적 발표", "성적발표",
        "졸업식", "납부 기간", "납부기간", "분할납부", "계절학기", "수강 변경",
        "예비 수강신청", "예비수강신청", "보강", "수업일", "학기 일정",
        "수업 시작", "수업 종료"],
    3: ["식단", "메뉴", "학식", "식당", "생협", "천원", "조식", "식권", "식대",
        "오늘 점심", "오늘 저녁", "주간 메뉴", "주간메뉴", "운영시간",
        "교내 식당"],
    4: ["셔틀", "셔틀버스", "통학버스", "교내순환", "캠퍼스버스", "캠퍼스 버스",
        "순환버스", "정류장", "노선", "첫차", "막차", "운행 시간", "운행시간",
        "통학"],
}


def verify_label(q: str, label: int) -> bool:
    """Drift check: variant must keep at least one label-specific keyword."""
    has_grad = any(k in q for k in GRAD_KW)
    has_shuttle = any(k in q for k in SHUTTLE_KW)
    has_meal = any(k in q for k in MEAL_KW)
    has_sched = any(k in q for k in SCHEDULE_STRONG)

    if label in (0, 2, 3, 4):
        if not any(k in q for k in _LABEL_KW[label]):
            return False
        # cross-class hard conflict (drift to *another* specific class)
        if label != 0 and has_grad:
            return False
        if label != 4 and has_shuttle:
            return False
        if label != 3 and has_meal:
            return False
        if label != 2 and has_sched and label not in (0,):
            return False
        return True

    # label 1 (notice): reject only if variant strongly looks like 0/2/3/4
    if label == 1:
        if has_grad or has_shuttle or has_meal:
            return False
        if has_sched and not any(k in q for k in ["장학", "신청", "공지", "안내", "모집"]):
            return False
        return True
    return True


# ---------- Stratified split ----------

def stratified_split(items: list[dict], valid_ratio: float, rng: random.Random) -> tuple[list, list]:
    by_label: dict[int, list[dict]] = {}
    for it in items:
        by_label.setdefault(it["label"], []).append(it)
    train, valid = [], []
    for lbl, arr in by_label.items():
        rng.shuffle(arr)
        k = max(1, int(len(arr) * valid_ratio))
        valid.extend(arr[:k])
        train.extend(arr[k:])
    rng.shuffle(train)
    rng.shuffle(valid)
    return train, valid


def dedup(items: Iterable[dict]) -> list[dict]:
    seen = set()
    out = []
    for it in items:
        k = it["text"].strip()
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


# ---------- D-1 eval set ----------

def build_d1_eval() -> list[dict]:
    """Convert D-1 5-way label file into eval jsonl."""
    with open(D1_LABELS, "r", encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for x in data["items"]:
        lbl = x["new_label_5way"]
        # OUT -> forced 1 (per scope decision); track is_out separately
        is_out = lbl == "OUT"
        final_label = 1 if is_out else int(lbl)
        out.append({
            "qa_id": x["qa_id"],
            "text": x["question"],
            "label": final_label,
            "is_out": is_out,
            "source": "d1",
        })
    return out


# ---------- main ----------

def main():
    rng = random.Random(2026)
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(REPORT_DIR, exist_ok=True)

    # 1) Generate base templates per class
    base_n = {0: 200, 1: 220, 2: 200, 3: 180, 4: 180}
    out_like_n = 60
    base = []
    base += gen_grad(rng, base_n[0])
    base += gen_notice(rng, base_n[1])
    base += gen_schedule(rng, base_n[2])
    base += gen_meal(rng, base_n[3])
    base += gen_shuttle(rng, base_n[4])
    base += gen_out_like(rng, out_like_n)
    base = dedup(base)

    # 2) Apply variants (×4)
    variants = apply_variants(base, rng, factor=5)
    all_items = dedup(base + variants)

    # 3) Per-class downsample to target N (균형)
    target = {0: 250, 1: 300, 2: 250, 3: 200, 4: 200}
    by_label: dict[int, list[dict]] = {}
    for it in all_items:
        by_label.setdefault(it["label"], []).append(it)
    final = []
    actual = {}
    for lbl, arr in by_label.items():
        rng.shuffle(arr)
        keep = arr[:target.get(lbl, 200)]
        final.extend(keep)
        actual[lbl] = len(keep)

    # 4) Stratified split
    train, valid = stratified_split(final, valid_ratio=0.10, rng=rng)

    # 5) D-1 eval
    d1 = build_d1_eval()

    # 6) Write
    def write_jsonl(path, items):
        with open(path, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")

    write_jsonl(os.path.join(DATA_DIR, "train.jsonl"), train)
    write_jsonl(os.path.join(DATA_DIR, "valid_internal.jsonl"), valid)
    write_jsonl(os.path.join(DATA_DIR, "d1_eval.jsonl"), d1)

    # 7) Report
    rp = os.path.join(REPORT_DIR, "class_dist.md")
    train_dist = Counter(x["label"] for x in train)
    valid_dist = Counter(x["label"] for x in valid)
    d1_dist = Counter(x["label"] for x in d1)
    d1_out_n = sum(1 for x in d1 if x.get("is_out"))
    names = {0: "졸업요건", 1: "공지", 2: "학사일정", 3: "식단", 4: "셔틀"}

    lines = ["# T2 분류기 데이터셋 분포 리포트", ""]
    lines.append(f"- 생성일: 2026-06-01")
    lines.append(f"- train.jsonl: **{len(train)}**")
    lines.append(f"- valid_internal.jsonl: **{len(valid)}**")
    lines.append(f"- d1_eval.jsonl: **{len(d1)}** (OUT 강제 1: {d1_out_n})")
    lines.append("")
    lines.append("## 클래스별 분포")
    lines.append("| 라벨 | name | train | valid | d1 |")
    lines.append("|---:|---|---:|---:|---:|")
    for lbl in [0, 1, 2, 3, 4]:
        lines.append(f"| {lbl} | {names[lbl]} | {train_dist.get(lbl,0)} | {valid_dist.get(lbl,0)} | {d1_dist.get(lbl,0)} |")
    lines.append("")
    lines.append("## 샘플 (label별 3개)")
    by_label_train: dict[int, list[dict]] = {}
    for it in train:
        by_label_train.setdefault(it["label"], []).append(it)
    for lbl in [0, 1, 2, 3, 4]:
        lines.append(f"### {lbl} ({names[lbl]})")
        for it in by_label_train.get(lbl, [])[:3]:
            lines.append(f"- {it['text']}  <- `{it['source']}`")
        lines.append("")
    with open(rp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[build_dataset] train={len(train)} valid={len(valid)} d1={len(d1)}")
    print("[build_dataset] train dist:", dict(train_dist))
    print("[build_dataset] valid dist:", dict(valid_dist))
    print("[build_dataset] d1 dist:", dict(d1_dist), "(out forced 1:", d1_out_n, ")")
    print(f"[build_dataset] report: {rp}")


if __name__ == "__main__":
    main()
