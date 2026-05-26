# Sprint 0 PoC 결과 보고서

**기간:** 2026-05-26 (1일)
**범위:** 어댑터 4종 PoC + PDF/표 파이프라인 + 미결 결정사항 spike + §10-4 실측 보정
**결론:** **Sprint 0 PASS.** 모든 어댑터·파이프라인 검증 완료. 미결 결정사항 2건 확정. Sprint 1 진입 가능.

---

## 1. 검증 결과 요약

### 1.1 어댑터 4종 (Task 0.1~0.4)

| 어댑터 | 대상 | 결과 | 비고 |
|---|---|---|---|
| **A** plus 정적 (T1) | `plus.cnu.ac.kr/html/kr/sub05/sub05_05050101.html` | ✅ PASS | 본문 771자, 컨테이너 `#contents` |
| **B** 게시판 (T2) | `plus.cnu.ac.kr/_prog/_board/?code=sub07_0702` | ✅ PASS | 리스트→상세 2단계, 8개 표본 |
| **C** Spring .do (T1) | `job.cnu.ac.kr/job/intro/intro01.do` | ✅ PASS | 본문 404자, 컨테이너 `#jwxe_main_content` |
| **D** 도서관 webcontent (T1) | `library.cnu.ac.kr/webcontent/info/130` | ✅ PASS | 본문 728자, 컨테이너 `#divContent`, h2 분할 동작 |

### 1.2 PDF + T6 표 파이프라인 (Task 0.5/0.6)

| 항목 | 결과 |
|---|---|
| 대상 PDF | dorm 2026-1학기 합격자 유의사항 (7p, 499KB) |
| pdfplumber 텍스트 추출 | ✅ 6904자, 한글 정상 (utf-8) |
| pdfplumber.extract_tables() | ✅ 9개 표 추출, CSV 저장 정상 (utf-8-sig) |
| Magic number 가드 | ✅ 잘못된 응답(HTML 등) 명확한 에러로 차단 |
| 의미 있는 표 데이터 | ✅ `p1_t2` 대기 후보 인원, `p2_t1` 납부 일정 등 — D-통계 형식 확인 |
| 노이즈 표 | ⚠️ `p1_t1` 표지 빈 셀 표 — 정제 시 빈 셀 비율로 자동 필터링 가능 |

### 1.3 미결 결정사항 spike (Task 0.7/0.8)

| 항목 | 결정 |
|---|---|
| **§8-2 학칙 위치** | ✅ **찾음 (HWP 전용)**. URL: `plus.cnu.ac.kr/_prog/rule/?site_dvs_cd=kr&menu_dvs_cd=06050101&gubun=1`. fallback 불필요. P1 데이터로 인정. 처리 방식은 후속 결정 (§3 참조). |
| **§8-5 동아리연합회 사이트** | ✅ **부재 확정**. `cnustudent.cnu.ac.kr`는 총학생회 사이트. 동아리 5.1 sparse는 fallback 유지. 단 cnustudent는 **5.2 학생회 핵심 소스로 신규 발견 (+1)**. |

---

## 2. 사이트별 CMS 차이 — Sprint 1 적용 가이드

Sprint 0의 가장 큰 학습. 충남대 부속 사이트는 적어도 4가지 CMS를 혼용합니다.

| CMS 시그널 | 본문 컨테이너 (1순위) | 본문 h2/h3 분할 | 알려진 사이트 |
|---|---|---|---|
| **plus CMS** | `#contents` = `#container` = `.al_box` | h2 없음 → 단일 청크 | plus.cnu.ac.kr, dorm.cnu.ac.kr (게시판 공통) |
| **jwxe** | `#jwxe_main_content` = `.detail_con` | h2 없음 → 단일 청크 | job.cnu.ac.kr (dorm/gymn/health 가능성 큼 — Sprint 1 첫 inspect로 확인) |
| **도서관 자체** | `#divContent` = `.guideW` | **h2/h3 분할 동작** | library.cnu.ac.kr |
| **cnustudent 자체** | `.main_con_wrap` (link_ratio 높아 본문 자체가 짧음) | 메인은 짧음, 상세 페이지 분석 필요 | cnustudent.cnu.ac.kr |

**Sprint 1 보강 항목:**
- `crawler/adapters/a_plus.py`의 `CONTENT_CONTAINER_CANDIDATES`에 `#jwxe_main_content`·`.detail_con`·`#divContent`·`.guideW` 추가 → 자동 1순위 매칭으로 다른 사이트 첫 inspect 비용 절감.

---

## 3. Cross-cutting 이슈 — HWP 처리

Sprint 0에서 발견된 두 가지 HWP 신호:

1. **백마광장 게시판 첨부 다수가 HWP** (어댑터 B 검증 시): "출석인정 신청 안내문.hwp", "휴학원 작성서식.hwp" 등
2. **학칙·규정 전체가 HWP 전용** (Task 0.7 탐색 결과): `plus.cnu.ac.kr/_prog/rule/download.php?atch_path=...hwp`

§1 T 분류에 PDF만 있고 HWP가 빠져 있던 게 드러남. **Task 3(RAG 파이프라인) 또는 Sprint 1 도입 직전에 정책 결정 필요.**

### HWP 처리 후보 정책

| 옵션 | 방식 | 신뢰성 | 비용 |
|---|---|---|---|
| (a) LibreOffice CLI 자동 변환 | `soffice --convert-to pdf *.hwp` → 기존 PDF 파이프라인 | ~70% (표 손실 가능) | 셋업 1회, 자동화 OK |
| (b) hwp5txt 텍스트 추출 | `pyhwp` 패키지 | ~80% (텍스트만, 표 구조 잃음) | pip 설치만 |
| (c) 학칙은 수동 변환 | 학생이 한글 오피스로 1회 PDF export | 100% | 1회성, 권장 |
| (d) 무시 | HWP 포함 데이터 포기 | — | 평가 손실 |

**권장:**
- **학칙·규정**: (c) 수동 변환 — 1회성 데이터, 100% 신뢰
- **게시판 첨부 HWP**: (a) 또는 (b) — Sprint 1 시작 직전 spike 한 번 더 필요

---

## 4. §10-4 실측 보정 — Conf L 7개 항목 갱신 근거

| 항목 | Sprint 0 측정치 | §10-2 표 갱신 권고 |
|---|---|---|
| **1.2 학과 PDF** | 미측정 (HWP일 가능성) | Sprint 1에서 학과 1개 샘플 측정 |
| **4.4 기숙사 생활수칙 PDF** | 미측정 (직접 대상 PDF 미접근) | dorm 알림마당 게시판 진입 후 측정 |
| **5.4 백마광장 카테고리별** ★ | **페이지당 ~10 게시물, 평균 ~817자/게시물, bimodal 분포** | §10-2 5.4 추정 갱신: 게시물당 평균 800자 적용 (분포 ½ 인라인본문형 ~2500자 / ½ 첨부의존형 ~150자) |
| **9.1 셔틀 운영계획 PDF** | 미측정 | Sprint 1 어댑터 PoC 시점에 측정 |
| **1.3 학칙 PDF** | HWP 발견. 약 N건 (HWP 다수, 미수개) | 수동 변환 1건 기준 약 5,000~30,000자 추정 (학칙 일반 분량) |
| **도서관 FAQ** | 미측정 (FAQ 페이지 직접 접근 안 함) | Sprint 1 어댑터 D로 측정 — FAQ 시드 가치 산정 |
| **장학 FAQ** | 미측정 | 동일 |

**총량 시나리오 재계산 권고**:
- 5.4 백마광장 백본이 §10-3에서 전체 33~50%를 차지한다고 했음
- 신규 추정: 페이지당 10개 × 800자 = 8000자/페이지. 페이지 수 9+ 확인 → 최소 72,000자. 카테고리별 1~2년치라면 수십 페이지 → 백본 ~200,000~500,000자 범위
- bimodal 분포의 첨부 의존형 25%가 HWP/PDF 별도 처리 필요 → corpus 양이 §10 가정보다 ~25% 적을 가능성

---

## 5. 신규 발견 — Sprint 1에 즉시 활용

### 5.1 게시판 첨부 다운로드 URL 패턴

```
{사이트}/_prog/_board/common/download.php?code={게시판코드}&ntt_no={게시물ID}&atch_no={첨부번호}
```

plus·dorm 동일 endpoint 확인. Sprint 1 어댑터 B 보강 시 게시물 상세 페이지에서 첨부 링크 자동 추출 가능 → PDF/HWP 자동 다운로드.

### 5.2 백마광장 게시물 본문 bimodal 분포

| 패턴 | 점유율(표본 8개) | 평균 길이 | 처리 권고 |
|---|---|---|---|
| 인라인 본문형 | ~50% | ~2500자 | 그대로 청크화 |
| 첨부파일 의존형 | ~50% | ~150자 (메타+파일명만) | 첨부 PDF/HWP 다운로드·파싱 → 별도 청크. 본문은 RAG 약신호로 유지 |

### 5.3 어댑터 B에 게시물 ID 키 패턴

plus 게시판은 `?no={id}` 사용. 다른 사이트는 `seq`/`board_seq` 가능성 — 이미 `_extract_post_id_from_url`에서 둘 다 지원.

---

## 6. Sprint 0 산출물 (`crawler/` + `data/sprint0/` + `logs/sprint0/`)

### 코드
- `crawler/http.py` — HTTP 클라이언트 (재시도·인코딩 보정·UA 명시)
- `crawler/schema.py` — Chunk dataclass (메타데이터 16필드 §12)
- `crawler/adapters/a_plus.py` — 어댑터 A (정적 HTML, inspect/crawl 2모드)
- `crawler/adapters/b_board.py` — 어댑터 B (게시판, inspect-list/crawl)
- `crawler/adapters/c_dotdo.py` — 어댑터 C (Spring .do, a_plus wrapper)
- `crawler/adapters/d_library.py` — 어댑터 D (도서관 webcontent, a_plus wrapper)
- `crawler/pdf_pipeline.py` — PDF 파이프라인 (T3 텍스트 + T6 표 CSV, magic number 가드)

### 데이터 (PoC 표본)
- `data/sprint0/a_plus_chunks.jsonl` — 어댑터 A 청크 1건 (편의시설 안내 771자)
- `data/sprint0/b_board_chunks.jsonl` — 어댑터 B 청크 8건 (백마광장 게시물 8개)
- `data/sprint0/c_dotdo_chunks.jsonl` — 어댑터 C 청크 1건 (인재개발원 404자)
- `data/sprint0/d_library_chunks.jsonl` — 어댑터 D 청크 2건 (도서관 이용안내 766자)
- `data/sprint0/pdf_chunks.jsonl` — PDF 청크 7건 (dorm 합격자 유의사항)
- `data/sprint0/tables/*.csv` — T6 표 9개 CSV

### 환경
- `environment.yml` — conda nlp-tp env (Python 3.11, Colab Free 정합)
- `requirements.txt` — pip 백업

---

## 7. Sprint 1 진입 체크리스트

- [x] 어댑터 4종 + PDF/표 파이프라인 검증
- [x] 게시판 첨부 다운로드 URL 패턴 식별
- [x] §8-2 학칙 위치 확정 (HWP)
- [x] §8-5 동아리연합회 부재 확정 + cnustudent 5.2 학생회 추가 발견
- [x] 5.4 백마광장 페이지당 게시물 수·본문 길이 분포 1차 측정
- [ ] **Sprint 1 진입 직전 추가 spike**:
  - [ ] dorm/gymn/health 첫 페이지 inspect 1회 → jwxe 여부 확정
  - [ ] HWP 처리 정책 결정 (a/b/c/d 중 게시판 첨부용)
  - [ ] 어댑터 A의 `CONTENT_CONTAINER_CANDIDATES`에 신규 셀렉터 추가
  - [ ] 어댑터 B에 첨부 다운로드 링크 자동 추출 추가

---

## 8. §9 작업표 보정 사항

| 원래 작업 | 보정 |
|---|---|
| 0.1 어댑터 A 검증 = `sub05_05020101_01.html` | sub05_05020101_01.html은 학사일정 캘린더 UI → 어댑터 A 대표 부적합. **편의시설 안내 sub05_05050101.html로 교체**. 학사일정은 Sprint 1 Day 1 작업 1.1에서 별도 캘린더 어댑터로 처리. |
| 0.7 §8-2 학칙 PDF | "PDF" 가정이 깨짐 — HWP. Sprint 1 들어가기 전 HWP 정책 결정 필요. |
