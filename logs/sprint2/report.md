# Sprint 2 Exit 리포트

- Sprint 1 청크: **704** / 582,653자
- Sprint 2 청크: **242** / 204,074자
- **합산: 946** / **786,727**자

## Sprint 2 source 파일별 산출
- `data/sprint2/day1/chunks.jsonl`: 0 청크 / 0자
- `data/sprint2/day1/attachments.jsonl`: 0 청크 / 0자
- `data/sprint2/day1/rule_chunks.jsonl`: 0 청크 / 0자
- `data/sprint2/day1/dept_grad_chunks.jsonl`: 0 청크 / 0자
- `data/sprint2/day1/dstat/dstat_chunks.jsonl`: 0 청크 / 0자
- `data/sprint2/day2/chunks.jsonl`: 0 청크 / 0자
- `data/sprint2/day2/attachments.jsonl`: 0 청크 / 0자
- `data/sprint2/day3/chunks.jsonl`: 0 청크 / 0자
- `data/sprint2/day3/attachments.jsonl`: 0 청크 / 0자
- `data/sprint2/day3/cross_tag.jsonl`: 242 청크 / 204,074자
- `data/sprint2/day3/faq_seeds.jsonl`: 0 청크 / 0자 (시드, corpus 미포함)
- `data/sprint2/day3/dorm_js.jsonl`: 0 청크 / 0자

## 합산 도메인별 분포
| 도메인 | 청크수 | 글자수 |
|---|---|---|
| 1 | 471 | 387,386 |
| 2 | 4 | 2,916 |
| 3 | 6 | 8,148 |
| 4 | 185 | 162,904 |
| 5 | 721 | 572,109 |
| 6 | 479 | 406,339 |
| 7 | 43 | 9,097 |
| 8 | 6 | 6,615 |
| 9 | 5 | 8,319 |

## 합산 source_type
- T3: 674건
- T2: 232건
- T1: 40건

## 합산 카테고리 상위 20
| 카테고리 | 글자수 |
|---|---|
| 5.4 | 572,109 |
| 6.3 | 384,278 |
| 1보조FAQ | 384,184 |
| 6.6 | 202,287 |
| 5.3 | 179,845 |
| 4.2 | 162,904 |
| 6.1 | 18,694 |
| 7.2 | 8,080 |
| 9.2 | 5,811 |
| 8.2 | 4,443 |
| 도서관FAQ | 4,403 |
| 3.1 | 2,453 |
| 1.1 | 2,166 |
| 장학FAQ | 1,765 |
| 2.1 | 1,542 |
| 8.1 | 1,514 |
| 2.4 | 1,458 |
| 2.2 | 1,374 |
| 9.1 | 1,316 |
| 9.5 | 1,316 |

## 평가셋 도메인 커버 (Sprint 1+2)
# Sprint 1+2 corpus 평가셋 매핑 점검표

| 도메인 | 명 | 평가합 | 청크수 | 글자수 | 비고 |
|---|---|---|---|---|---|
| 1 | 학사 | 30 | 471 | 387,386 | ✓ |
| 2 | 식생활 | 16 | 4 | 2,916 | · |
| 3 | 도서관 | 18 | 6 | 8,148 | · |
| 4 | 기숙사 | 21 | 185 | 162,904 | ✓ |
| 5 | 학생활동·공지 | 13 | 721 | 572,109 | ✓ |
| 6 | 장학금·등록금 | 20 | 479 | 406,339 | ✓ |
| 7 | 진로·취업 | 18 | 43 | 9,097 | · |
| 8 | 행정·증명서 | 20 | 6 | 6,615 | · |
| 9 | 캠퍼스·시설 | 15 | 5 | 8,319 | · |

## Exit 판정
- ✓ Sprint 2 신규 corpus 204,074자 (≥100k 목표 달성) — Phase C 진입 OK

## Phase C 핸드오프
- 입력: `data/sprint{1,2}/<day>/{chunks,attachments,rule_chunks,dept_grad_chunks,cross_tag,dorm_js}.jsonl`
- D-1 시드: `data/sprint2/day3/faq_seeds.jsonl`
- 청크 분할 정책 결정 권장 (T3 페이지=청크 매핑이 너무 큼 — Sprint 1 메모 참조)
