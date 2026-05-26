# Sprint 2 Runbook

Sprint 1과 동일한 패턴: 코드는 검증 완료, 사용자 로컬 cmd에서 실행.

## 0. 사전 준비

Sprint 1 환경 그대로. 추가 의존성 없음 (Playwright는 4.1 JS 시도 선택사항).

```cmd
cd C:\Users\iksdg\Documents\Claude\Projects\NLP_TP

:: (선택) 4.1 dorm JS 렌더 시도용
pip install playwright
playwright install chromium
```

Sprint 2 산출은 `data/sprint2/` 와 `logs/sprint2/` 로 분리됨 — Sprint 1 데이터는 안 건드림.

## 1. 추천 실행 순서

### 1-A. spike (URL 패턴 확인) — 약 1분

```cmd
scripts\run_sprint2.bat inspect
```

세 가지를 점검:

1. **학칙 리스트** (`e_rule_hwp inspect`) — onclick에서 `ntt_no` 추출되는지. `Rows: table=N, with_ntt_no=M` 행에서 `M > 0` 이어야 본 크롤 가능.
2. **알리미 spike** (`sprint2_dstat spike-alimi`) — 충남대 신입생수/취업률 PDF 직접 link가 보이는지. 못 찾으면 popup이 JS 후처리 → 브라우저로 직접 PDF URL 확보 후 `sprint2_dstat fetch-pdf <URL>` 실행.
3. **학과 졸업요건 discover** — 15개 학과 메뉴에서 졸업요건/교육과정 키워드 매칭. 학과별 `[score=N] 키워드 → URL` 출력. 후보 0건이면 학과 홈 URL이 잘못됐을 가능성 (`scripts/sprint2_dept_list.json` 수정).

### 1-B. Day별 본 크롤

```cmd
scripts\run_sprint2.bat day1     :: RULE_HWP + PDF + dept_grad crawl + attachments
scripts\run_sprint2.bat day2     :: A·B 어댑터 (학생활동·진로·도서관·캠퍼스)
scripts\run_sprint2.bat day3     :: A·B + cross_tag + faq_seed + dorm_js
```

또는 전체:
```cmd
scripts\run_sprint2.bat
```

### 1-C. 첨부 후처리 (HWP/PDF)

Sprint 1과 동일 패턴. 게시판 첨부 다수가 HWP라 본 크롤 후 별도 처리:
```cmd
scripts\run_sprint2.bat attachments
```

### 1-D. Exit 검증

```cmd
scripts\run_sprint2.bat verify
```

산출:
- `logs/sprint2/report.md` — Sprint 2 + Sprint 1 합산 통계
- `logs/sprint2/coverage.json` — Phase C 핸드오프
- `logs/sprint2/coverage_vs_eval.md` — 평가셋 168문제 매핑 점검표

## 2. 부분 실행 / 트러블슈팅

### 학칙 (1.3) 만 다시
```cmd
python -m scripts.sprint2_runner day1 --only 1.3_rule_list
```

### 특정 학과만 졸업요건
`scripts/sprint2_dept_list.json` 을 1개로 줄여서:
```cmd
python -m scripts.sprint2_dept_grad discover --dept-list scripts/sprint2_dept_list.json
python -m scripts.sprint2_dept_grad crawl --candidates data/sprint2/day1/dept_grad_candidates.jsonl
```

### 알리미 PDF URL 수동 입력
spike 결과로 PDF URL이 안 나오면 (JS 후처리), 사용자가 알리미 사이트에서 직접 다운로드 URL을 얻은 후:
```cmd
python -m scripts.sprint2_dstat fetch-pdf "https://www.academyinfo.go.kr/..."
```

### 4.1 dorm JS 실패해도 OK
Playwright 미설치 또는 페이지 변경으로 실패 시 fallback 메시지만 출력하고 종료 (평가 5문제 영향, Sprint 1 day3 4.2 공지로 부분 커버됨).

### Cross-tag (8.3 / 2.4 / 6.6) 재실행
```cmd
python -m scripts.sprint2_cross_tag
```
Sprint 1 chunks/attachments 의 categories에서 1.5/2.1/2.2/6.1~6.4 매칭하는 청크를 copy + tag 추가. Sprint 1 원본은 절대 안 건드림.

## 3. 산출물 구조

```
data/sprint2/
├── day1/
│   ├── chunks.jsonl                 :: runner 본 청크 (PDF/A어댑터)
│   ├── attachments.jsonl            :: 게시판 첨부 후처리 결과
│   ├── rule_chunks.jsonl            :: 1.3 학칙 (RULE_HWP)
│   ├── dept_grad_chunks.jsonl       :: 1.2 학과 졸업요건
│   ├── dept_grad_candidates.jsonl   :: 학과 메뉴 발견 결과
│   ├── alimi_spike.json             :: 알리미 PDF link 후보
│   ├── hwp/                         :: HWP 다운로드 캐시
│   ├── tables/                      :: PDF 표 CSV
│   └── dstat/dstat_chunks.jsonl     :: 1.7/7.5 D-통계
├── day2/
│   ├── chunks.jsonl
│   └── attachments.jsonl
└── day3/
    ├── chunks.jsonl
    ├── attachments.jsonl
    ├── cross_tag.jsonl              :: 8.3/2.4/6.6 cross-tag
    ├── faq_seeds.jsonl              :: Phase D-1 입력 (corpus 미포함)
    └── dorm_js.jsonl                :: 4.1 JS 렌더 결과 (실패 시 빈 파일)

logs/sprint2/
├── day1.log day2.log day3.log
├── report.md                        :: Sprint 1+2 합산 통계
├── coverage.json                    :: Phase C 입력
└── coverage_vs_eval.md              :: 평가셋 매핑
```

## 4. Exit 기준 (자동 점검)

`sprint2_verify.py` 가 다음을 자동 판정:

- Sprint 2 신규 corpus ≥ 100,000자 → "Phase C 진입 OK"
- sparse 도메인 (글자수 < 2,000) 자동 식별 → fallback 정책 점검 권장

평가셋 168문제와 도메인 매핑은 `coverage_vs_eval.md` 표로 출력.

## 5. 알려진 제약

- **학칙 onclick 형식 가설:** `e_rule_hwp.py` 의 ntt_no 추출 정규식은 5종 패턴(unit test 6/6 pass)을 가정. 실제 페이지가 다른 형식이면 `inspect` 결과의 onclick 샘플을 보고 `parse_ntt_no_from_onclick` 정규식 추가.
- **학과 홈 URL:** `sprint2_dept_list.json` 의 15개는 추정 — `index.do` 가 표준이라는 가정. 학과별 실제 URL이 다르면 `discover` 가 0건 후보로 끝나니 직접 수정.
- **알리미 PDF endpoint:** 공시 popup의 PDF/CSV link 패턴은 사이트마다 다름. spike 결과 보고 사용자 수동 입력.
- **4.1 dorm JS:** 실패 허용 (`평가 영향 5문제, 부분 fallback 가능`).
