# Phase D-1 평가셋 생성 요약

**생성 완료일:** 2026-05-28
**산출물:** `eval/eval-generated.jsonl` (170 QA)
**스키마 버전:** 16필드 v1.0 (eval-samples-notes.md §2-3)
**생성 모델:** Claude (chunk 기반 직접 생성, `gen_prompt_version: v1.0`)

---

## 1. 총괄

- **총 170문제** = 일반 155 + Fallback expected 15
- 도메인×타입 매트릭스 목표 달성 (전 도메인 일치)
- 16필드 스키마 정합: 100% (errors=0)
- qa_id 유일성: 170/170
- `expected_source_urls` corpus 정합: 100% (155/155 매칭)

## 2. 도메인×타입 매트릭스

| 도메인 | A | B | C | D | 일반계 | Fallback | 도메인계 |
|---|---|---|---|---|---|---|---|
| d1 학사 | 15 | 12 | 5 | 3 | 35 | 6 | 41 |
| d2 식생활 | 3 | 0 | 0 | 0 | 3 | 1 | 4 |
| d3 도서관 | 6 | 3 | 1 | 0 | 10 | 1 | 11 |
| d4 기숙사 | 10 | 4 | 3 | 3 | 20 | 1 | 21 |
| d5 학생활동 | 12 | 4 | 0 | 0 | 16 | 2 | 18 |
| d6 장학·등록금 | 13 | 5 | 5 | 0 | 23 | 2 | 25 |
| d7 진로·취업 | 12 | 4 | 0 | 6 | 22 | 1 | 23 |
| d8 행정·증명서 | 3 | 2 | 0 | 0 | 5 | 0 | 5 |
| d9 캠퍼스생활·시설 | 13 | 8 | 0 | 0 | 21 | 1 | 22 |
| **합계 (일반)** | **87** | **42** | **14** | **12** | **155** | **15** | **170** |

> 일반 155 / Fallback 15 = 170 (목표 100% 달성)
> 일반 카운트의 A는 분류 시 약간의 fallback 카테고리도 포함됨. 매트릭스 카운트는 question_type 기준.

## 3. Sparse 도메인 정책 적용

청크 부족 도메인은 phase-c-prep 메모리 기준 비례를 재조정:

- **d2 식생활**: 3문제 (corpus 청크 부족, 생협+편의시설 chunk 활용)
- **d3 도서관**: 10문제 (library.cnu.ac.kr 13청크에서 도출)
- **d8 행정·증명서**: 5문제 (학생증·국제학생증 위주)

부족분은 dense 도메인 증가 + Fallback expected 활용으로 보완.

## 4. Fallback Expected (15개) 카테고리

| 카테고리 | 개수 | 예시 |
|---|---|---|
| OOS - 개인 데이터 | 2 | 본인 학점 조회, 룸메 갈등 |
| OOS - 미래 예측 | 1 | 내년 등록금 인상률 |
| OOS - 비공개 개인정보 | 1 | 교수 휴대폰 번호 |
| OOS - 충남대 외 정보 | 1 | 서울대 졸업요건 |
| OOS - 주관적 평가 | 2 | 동아리 추천, 도서관 비교 |
| OOS - 미래 학사일정 | 1 | 2027학년도 수강신청 |
| OOS - 시스템 미보유 통계 | 1 | 평균 연봉 |
| Sparse 도메인 보완 | 3 | 동아리 임원, 식단, 보건 의료보험 |
| 모호한 질문 의도 | 3 | "그거 어떻게", "이거 처리해줘", "장학금 평점" |

## 5. Created_by 분포

- `llm-claude`: 155 (일반)
- `llm-claude-fallback`: 15 (fallback expected)

전 항목 `reviewed_by: null`, `reviewed_at: null` (D-2 검수 대기)

## 6. 데이터 품질 가드 결과

| 검증 항목 | 결과 |
|---|---|
| 16필드 스키마 정합 | PASS (0 errors) |
| qa_id 중복 | 0 (170/170 unique) |
| 비-fallback `expected_source_urls` 비어 있음 | 0 |
| `expected_source_urls`가 corpus에 존재 | 100% (URL 변형 9건 자동 수정) |
| 도메인 1~9 범위 | PASS |
| `question_type` A|B|C|D | PASS |
| `is_fallback_expected` bool | PASS |
| `tags` >=1 | PASS |

## 7. URL 수정 이력

URL 정합 검증 결과 9개 URL이 corpus와 다른 변형으로 작성되어 수정:

- `dorm.cnu.ac.kr/.../download.php?...atch_no=11` → `atch_no=1` (4건)
- `dorm.cnu.ac.kr/.../menu_dvs_cd=050106` → `menu_dvs_cd=030602` (5건)

수정 후 재검증: corpus 매칭 100%.

## 8. 청크 활용 통계

- 입력 corpus: `data/phase_c/03_enriched/corpus/all.jsonl` (3,615 청크)
- 도메인별 pool 생성: `eval/_workspace/pool_d{1..9}.jsonl`
  - d1:80, d2:53, d3:13, d4:80, d5:80, d6:80, d7:80, d8:80, d9:60
- 실제 활용 청크: 약 80~100개 (1 chunk → 1~3 QA 평균)

## 9. 다음 단계 (D-2 검수)

1. `eval/eval-review-template.xlsx`를 사본으로 만들어 검수 진행
2. `eval-rubric.md`의 3-way 의사결정 룰북(Accept/Edit/Reject) 적용
3. 검수 후 `reviewed_by`, `reviewed_at`, `notes` 필드 채워 jsonl 업데이트
4. R prefix qa_id로 final 산출 (`eval/eval-final.jsonl`)
5. D-3 export 스크립트(`eval/export_eval_set.py`) 작성 (xlsx ↔ JSON 매핑)

## 10. 알려진 한계 / 검수 시 점검 권장

- **d2 식생활 (3문제)**: 청크가 매우 sparse하여 생협 일반 정보 + 학생회관 식당 위치만 다룸. 실시간 식단·메뉴는 fallback으로 분리.
- **d1 학사 D 타입 (3문제)**: 학사 직접 통계 청크 부족으로 academyinfo 학과별 정원·경쟁률 활용. categories는 1.2(학과)로 라벨.
- **B 타입 일부**: chunk에 단계가 충분히 명시되지 않은 경우(예: 삼원장학재단 2차 심사)는 chunk 발췌 범위만 기재하고 `notes`에 메모.
- **C 타입 (14문제)**: 두 청크 cross-domain은 두 청크 모두 `expected_source_urls`에 포함. 한 청크 내 비교는 단일 URL.
- **첨부 PDF chunks (`download.php?atch_no=...`)**: 본문이 일부 추출 안 된 청크는 활용 안 함. `notes` 기록.

---

관련 파일:
- 생성된 평가셋: `eval/eval-generated.jsonl`
- 생성 작업 디렉토리: `eval/_workspace/` (pool, batch JSON, helper script)
- D-0 산출물: `eval/README.md` (D-0 핸드오프 인덱스)
