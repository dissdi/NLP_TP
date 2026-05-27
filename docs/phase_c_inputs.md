# Phase C 입력 인벤토리

생성일: 2026-05-27
원본 데이터: `data/sprint{1,2,3}/`
스캔 스크립트 산출: `docs/_phase_c_inventory.json`

## 1. 요약 (정리 후 기준, 2026-05-27 D-통계 변환 반영)

| 구분 | 값 |
|---|---|
| 총 입력 파일 (non-empty jsonl) | 19개 |
| 총 청크 수 (raw, Phase C 입력 전) | **4,094** (4,075 + 19 기숙사 D-통계) |
| 총 텍스트 크기 | 약 3.06M 자 |
| 스키마 통일성 | 16개 표준 필드 일치 (faq_seeds.jsonl, dept_grad_candidates.jsonl 제외) |
| 빈 파일 (입력 제외) | 3개 (`sprint1/day4/attachments`, `sprint2/day3/attachments`, `sprint2/day3/dorm_js`) |
| 신규 추가 | `data/sprint3/dstat/chunks.jsonl` (19 chunks, pid193·266·262·278) |

## 2. 파일별 인벤토리

| 파일 | 청크 | 총 자수 | 평균 | 최대 | 비고 |
|---|---:|---:|---:|---:|---|
| sprint1/day1/attachments.jsonl | 161 | 158,792 | 986 | 1,620 | T3 (PDF/HWP 첨부) |
| sprint1/day1/chunks.jsonl | 29 | 8,408 | 289 | 2,166 | T2·T1 |
| sprint1/day2/attachments.jsonl | 344 | 329,264 | 957 | 1,620 | T3 |
| sprint1/day2/chunks.jsonl | 154 | 66,905 | 434 | 7,063 | T2·T1 |
| sprint1/day3/chunks.jsonl | 13 | 16,168 | 1,243 | 4,648 | T1 |
| sprint1/day4/chunks.jsonl | 2 | 3,081 | 1,540 | 1,765 | T1 |
| sprint1/day5/chunks.jsonl | 1 | 35 | 35 | 35 | T1 (sparse) |
| sprint2/day1/attachments.jsonl | 308 | 303,776 | 986 | 1,620 | T3 |
| **sprint2/day1/chunks.jsonl** | **71** | **924,700** | **13,023** | **81,437** | ★ 학칙 HWP — 재청크 필수 |
| sprint2/day1/dept_grad_chunks.jsonl | 85 | 477,380 | 5,616 | 17,479 | 학과 졸업요건 (재청크 후보) |
| sprint2/day2/attachments.jsonl | 356 | 354,134 | 994 | 1,620 | T3 (기숙사) |
| sprint2/day2/chunks.jsonl | 72 | 33,624 | 467 | 10,923 | T2·T1 |
| sprint2/day3/chunks.jsonl | 2 | 457 | 228 | 422 | T1 |
| sprint2/day3/cross_tag.jsonl | 242 | 204,074 | 843 | 7,063 | cross-domain 태깅 (6.6 등) |
| sprint3/dept_info/chunks.jsonl | 2,235 | 173,761 | 77 | 111 | T6 알리미 (작은 셀 단위) — 병합 검토 |
| sprint3/dstat/chunks.jsonl ★신규 | 19 | ~4,000 | ~210 | ~580 | T6 알리미 D-통계 기숙사 (pid193·266·262·278) |

## 3. 스키마 (16 필드, 표준)

```
chunk_id, chunk_index, parent_post_id,
source_url, source_title, source_type,
section_path, text, char_count, lang,
posted_at, crawled_at, freshness,
domains, categories, notes
```

- `domains`/`categories` 는 **list**(다중 태깅 가능)
- `source_type` 값: T1, T2, T3, T6 (T4·T5 미수집)

## 4. Domain 분포 (chunk 개수 기준)

| domain | chunks | 평가셋 매핑 | sparse 여부 |
|---|---:|---|---|
| 1 학사 | 1,974 | ✅ | dense |
| 6 진로 | 1,045 | ✅ | dense |
| 5 장학 | 915 | ✅ | dense |
| 7 행정·증명서 | 547 | ✅ | 메모리상 sparse → 실측 medium (T6 dept_info 흡수) |
| 4 기숙사 | 560 | ✅ | dense (D-통계 19 청크 포함) |
| 3 식생활 | 9 | ⚠ | **sparse** (16문제 cover 어려움) |
| 8 도서관 | 7 | ⚠ | **sparse** (18문제 cover 어려움) |
| 9 캠퍼스 | 7 | ⚠ | sparse |
| 2 학생활동 | 5 | ⚠ | sparse |

**Sprint 2 메모와 차이:** 메모에는 "식생활/도서관/행정" 3 sparse 였으나, T6 알리미 dept_info 2,235 chunks가 도메인 7(행정)을 채워 행정은 medium-density로 격상됨. 반대로 학생활동(2)·캠퍼스(9)가 새로운 sparse로 부상.

## 5. 카테고리 Top 15

```
1.7 일반학사       1,395
5.4 백마광장         721
4.2 기숙사 공지      541
6.3 진로 6.3         468
1보조FAQ            466
5.3 장학 5.3         407
4.1 기숙사 일반      356
4.7 기숙사 4.7       356
6.2 진로 6.2         292
6.1 진로 6.1         281
7.5 행정 7.5         275
7.2 행정 7.2         268
6.6 진로 cross       239
1.2 학과 졸업요건     86
1.3 학칙              23
```

## 6. Phase C 입력으로 사용할 파일 (final)

**포함:**
- 모든 `chunks.jsonl`, `attachments.jsonl`, `dept_grad_chunks.jsonl`, `cross_tag.jsonl` (non-empty)
- `sprint3/dept_info/chunks.jsonl`

**제외:**
- `sprint2/day1/dept_grad_candidates.jsonl` — Phase B 진단용 (text 없음)
- `sprint2/day3/faq_seeds.jsonl` — Phase D-1 시드 (다른 스키마)
- 빈 파일 4개
- `data/_archive/` (Sprint 0 PoC, UbiReport spike)

## 7. 평가셋 ↔ 청크 스키마 매핑

평가셋 (`eval/eval-samples.jsonl`) 12 필드 → 청크 16 필드 연결:

| eval 필드 | 청크 필드 | 용도 |
|---|---|---|
| `qa_id` | — | (평가용 ID, 청크에는 없음) |
| `question` | — | retrieval query 입력 |
| `answer_gold` | — | LLM 출력 정답 비교 |
| `expected_source_urls` | `source_url` | ★ retrieval 성능 측정 (recall) |
| `domain` | `domains` | ★ domain filter (1~9) |
| `category` | `categories` | category filter (1.7, 4.2 등) |
| `question_type` | — | 평가 분류 (지식·통계·절차 등) |
| `tags` | — | 추가 grouping |
| `is_fallback_expected` | — | sparse 도메인 fallback 판정 |
| `notes`, `created_by`, `reviewed_by` | — | 메타 |

**Phase C에서 보존 필수 필드:** `chunk_id`, `source_url`, `domains`, `categories`, `text` — retrieval 평가와 직접 연결.

## 8. 알려진 이상치

1. **거대 청크**: `sprint2/day1/chunks.jsonl` 학칙 HWP 1 page = 1 chunk → max 81,437자, avg 13,023자. Phase C에서 **재청크 필수**.
2. **초소형 청크**: `sprint3/dept_info/chunks.jsonl` avg 77자. JSON API 학과×지표 셀 단위라 단독으로는 검색 후 답변 생성에 컨텍스트 부족 — **학과 단위로 병합** 또는 query-time aggregation 검토.
3. **sparse 도메인 4종** (2/3/8/9) — Phase C에서는 그대로 통과시키되, Phase D-2(RAG 평가) 단계에서 fallback 응답 정책 적용.
