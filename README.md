# NLP_TP — 충남대학교 학내 정보 RAG QA 시스템

충남대학교 학부생을 대상으로 한 **RAG 기반 학내 정보 질의응답 시스템**.
학사·기숙사·도서관·장학·진로 등 9개 도메인의 공개 학내 정보를 자동 수집·청킹·임베딩하고,
LLM과 결합해 자연어 질문에 답한다.

> 충남대학교 자연어처리(NLP) 강의 학기말 프로젝트. Colab Free (15 GB GPU) 환경에서 동작 가능하도록 설계.

---

## 1. 시스템 개요

### 1-1. 사용자 / 사용 시나리오

- **사용자**: 충남대 학부생
- **질문 예시**:
  - "졸업 학점은 몇 학점이에요?"
  - "기숙사 입사 신청 어떻게 해요?"
  - "충남대 컴퓨터공학과 작년 취업률은?"
  - "중앙도서관 평일 운영시간은?"

### 1-2. 도메인 (9개)

| # | 도메인 | 범위 |
|---|---|---|
| 1 | 학사 | 학사일정, 수강신청, 학적, 졸업요건, 학칙 |
| 2 | 식생활 | 학식 메뉴, 식당 위치·운영시간 |
| 3 | 도서관 | 운영시간, 대출, 좌석예약, 자료검색 |
| 4 | 기숙사 | 입사신청, 사생 규정, 공지 |
| 5 | 학생활동·공지 | 백마광장, 동아리, 공지사항 |
| 6 | 장학금·등록금 | 장학금 종류, 등록금 일정 |
| 7 | 진로·취업 | 진로상담센터, 채용공고, 학과별 취업률 |
| 8 | 행정·증명서 | 증명서 발급, 학생증 |
| 9 | 캠퍼스 생활·시설 | 셔틀버스, 체육시설, 보건진료소 |

자세한 in/out scope·평가 기준은 [`coverage-plan.md`](coverage-plan.md) 참조.

### 1-3. 질문 타입 (6개)

`A.사실 / B.절차 / C.비교 / D.통계 / E.추천 / F.시점` — 평가 대상은 A~D, 시연용 E·F.

---

## 2. 아키텍처

```
[학내 사이트 N개]                   [LLM]
  plus.cnu.ac.kr           ┌──────────────┐
  library.cnu.ac.kr        │  Phase D-2   │
  dorm.cnu.ac.kr           │  답변 생성    │
  academyinfo.go.kr  ──→   │              │ ──→  답변
  ...                      └──────▲───────┘
        │                         │
        │ Phase B                 │ Phase C
        ▼                         │ retrieval
  crawler/adapters/         ┌─────┴────────┐
   a_plus  b_board          │  벡터 인덱스  │
   c_dotdo d_library        │  (FAISS 등)  │
   e_rule_hwp               └─────▲────────┘
   f_ubireport ★                  │
   g_dept_info ★             청크 임베딩
        │
        ▼
  data/sprint{1,2,3}/
   chunks.jsonl  ─────────────────┘
   (16-field schema, T1~T6 source types)
```

T1~T6는 source type 분류 ([`crawling-targets.md`](crawling-targets.md)):
- T1 plus.cnu.ac.kr 정적 페이지 / T2 game 게시판 / T3 학칙·규정 첨부 / T4 동적 페이지 / T5 로그인 후 페이지 (사용 X) / T6 대학알리미

---

## 3. Phase 구성

| Phase | 단계 | 산출물 |
|---|---|---|
| A | 커버리지·평가 기획 | `coverage-plan.md`, `crawling-targets.md` |
| **B** | **데이터 수집 (Sprint 0~3)** | `data/sprint*/chunks.jsonl` |
| C | 청킹·임베딩 | 벡터 인덱스 (FAISS 등) |
| D-0 | 평가셋 설계 | `eval/eval-{samples,rubric,generation-prompt,review-template}` |
| D-1 | LLM Q&A 생성 | `eval/G*.jsonl` (Generated) |
| D-2 | 평가셋 수동 검수 | `eval/R*.jsonl` (Reviewed final) |
| E | 웹앱 + 평가 | demo 인터페이스, 자동 평가 스크립트 |

현재 위치: **Phase B 종료 / Phase C 진입 대기**.

---

## 4. 디렉터리 구조

```
NLP_TP/
├─ coverage-plan.md          9도메인 × 6타입 커버리지 매트릭스, 평가 전략
├─ crawling-targets.md       크롤링 대상 사이트 / T1~T6 source type 정의
├─ requirements.txt          / environment.yml
│
├─ crawler/                  크롤러 코드
│  ├─ schema.py              16-field Chunk dataclass
│  ├─ adapters/              사이트별 어댑터
│  │   ├─ a_plus.py          plus.cnu.ac.kr 정적 (T1)
│  │   ├─ b_board.py         게시판 (T2)
│  │   ├─ c_dotdo.py         Spring .do 페이지
│  │   ├─ d_library.py       도서관 webcontent
│  │   ├─ e_rule_hwp.py      학칙·규정 HWP (T3)
│  │   ├─ f_ubireport.py     ★ 대학알리미 UbiReport viewer (T6, Playwright XHR)
│  │   ├─ f_multipage.py     UbiReport multi-page helper
│  │   └─ g_dept_info.py     ★ 알리미 학과정보 JSON API (T6, requests)
│  └─ ...
│
├─ scripts/                  실행 진입점
│  ├─ _common.py             DayRunner 공통 유틸
│  ├─ _spike/                PoC·진단 reproducer (보관)
│  ├─ sprint1/               1차 메인 수집 — Day 1~5
│  ├─ sprint2/               이월 + 보강 — Day 1~3
│  ├─ sprint3/               알리미 회수 — dept_collect / dstat_collect
│  └─ run_sprint{1,2}.{bat,sh}   마스터 실행기
│
├─ data/                     수집 결과 (jsonl)
│  ├─ sprint1/day{1..5}/
│  ├─ sprint2/day{1..3}/
│  └─ sprint3/{dept_info,dstat}/
│
├─ eval/                     평가셋 (Phase D-0 완료)
│  ├─ eval-samples.jsonl     골드 샘플 5건 (수작업)
│  ├─ eval-rubric.md         3-way 검수 룰북 (Accept/Edit/Reject)
│  ├─ eval-generation-prompt.md  Claude/GPT 시스템 프롬프트 v1.0
│  └─ eval-review-template.xlsx  검수 워크북
│
├─ docs/                     sprint 계획·런북
├─ logs/                     Sprint exit 검증 리포트
└─ notebooks/                실험 노트북
```

---

## 5. 데이터 통계 (Phase B 종료 시점)

| Sprint | 청크 | 글자 수 | 비고 |
|---|---:|---:|---|
| Sprint 1 (Day 1~5) | 704 | 582 k | 도서관·학사·장학·기숙사 공지·백마광장 |
| Sprint 2 (Day 1~3) | 1,136 | 2,298 k | 학칙 HWP·학과 졸업요건(93)·기숙사 추가 |
| **Sprint 1+2 합산** | **1,840** | **2,881 k** | |
| Sprint 3 dept_info | 2,235 | — | 알리미 학과정보 (101 학과 × 8 통계) |
| Sprint 3 dstat | — | — | 알리미 공시정보 학교 단위 (보류) |

평가 도메인 ✅ 6/9: 학사·기숙사·학생활동·장학·진로·캠퍼스
⚠ sparse 3/9: 식생활·도서관·행정·증명서 (보강 필요 시 별도 sprint)

---

## 6. 사용 방법

### 6-1. 환경 설치

```bash
# conda
conda env create -f environment.yml
conda activate nlp-tp

# 또는 pip
pip install -r requirements.txt
# 추가 (필요 시)
pip install playwright
playwright install chromium
```

### 6-2. Sprint 실행 (데이터 수집)

```bash
# Sprint 1 전체 (Day 1~5 + verify)
scripts/run_sprint1.bat            # Windows
scripts/run_sprint1.sh             # Unix

# Day 단위
scripts/run_sprint1.bat day2
scripts/run_sprint2.bat day1

# Sprint 3 — 알리미 학과정보 일괄 수집
python -m scripts.sprint3.dept_collect             # 전체 (학과 101 × 8 flag)
python -m scripts.sprint3.dept_collect --limit 3 --flags v1,v7   # 디버그
python -m scripts.sprint3.dept_collect --svy-yr 2025             # 다른 연도
```

### 6-3. 단일 어댑터 사용

```python
from crawler.adapters.g_dept_info import DeptInfoAdapter, STAT_FLAGS, stat_to_chunks

adapter = DeptInfoAdapter(schl_id="0000029", sleep_between=0.5)
depts = adapter.list_depts(svy_yr="2025")       # 101 학과 메타
for dept in depts:
    for flag, meta in STAT_FLAGS.items():       # v1~v8
        stat = adapter.fetch_stat(dept, flag, svy_yr="2026")
        chunks = stat_to_chunks(stat)           # RAG-ready chunks
        ...
```

### 6-4. 결과 확인

```bash
# Sprint별 검증 리포트
cat logs/sprint1/report.md
cat logs/sprint2/report.md

# Sprint 3 결과
cat data/sprint3/dept_info/manifest.json
head -3 data/sprint3/dept_info/chunks.jsonl
```

---

## 7. 평가 (Phase D)

두 갈래 평가 운영:

| 항목 | 자체 평가셋 (우리) | 공식 평가 (교수님) |
|---|---|---|
| 문제 수 | ~170 (9도메인 × A·B·C·D 타입) | ~100 (블라인드) |
| 출제자 | LLM 생성 + 수동 검수 | 담당 교수 |
| 판정 | 자동 + 수동 | LLM-as-judge 50% + TA 50% |
| 목적 | 개발 중 회귀 방지 | 성적 평가 |

자세한 룰북·체크리스트는 [`eval/eval-rubric.md`](eval/eval-rubric.md), [`eval/README.md`](eval/README.md) 참조.

---

## 8. 제약 사항 / Out of Scope

**환경 제약:**
- Colab Free 15 GB GPU 메모리 (Phase C·D 인퍼런스)
- 한국어 모델 기본 (다국어 모델은 옵션)
- LLM 추론은 Claude/GPT API 또는 경량 오픈모델 (Llama 8B 이하 권장)

**Out of Scope (의도적으로 답하지 않음):**
| # | 항목 | 대응 |
|---|---|---|
| 1 | 개인 데이터 (내 학점·시간표) | "개인 데이터는 답할 수 없음" |
| 2 | 실시간 동적 데이터 (빈 좌석, 셔틀 위치) | "실시간 미지원" |
| 3 | 민감 정보 (정신건강·신고) | 상담센터 핫라인 fallback |
| 4 | 주관적 평가 (교수·학식 평가) | 답 안 함 |
| 5 | 미래 예측 (내년 행사) | 크롤링 시점 이후 답 안 함 |
| 6 | 비공개 정보 (입시 합격선) | 답 안 함 |
| 7 | 타 대학·정부 일반 정책 | "충남대 정보만 다룸" |

---

## 9. 주요 의사결정 / 기술 노트

- **북극성**: **정확성 > 자연스러움 > 표현**. "그럴듯한데 틀린 답"보다 "모른다"가 낫다.
- **크롤링 정책**: 비로그인 페이지 우선. 로그인 후 개인 데이터는 사용 X.
- **데이터셋**: 기존 벤치마크 사용 금지, 자체 구축 필수 (강의 요구사항).
- **알리미 데이터**: viewer는 UbiReport(좌표 기반 XML), 학과 단위는 JSON API. 어댑터 2개로 분리 처리 (`f_ubireport.py`, `g_dept_info.py`).

---

## 10. 라이선스 / 출처

- 학내 자료는 충남대학교 공식 홈페이지·게시판·대학알리미(공시정보)에서 수집한 공개 정보.
- 본 코드는 교육 목적의 학기말 프로젝트.
