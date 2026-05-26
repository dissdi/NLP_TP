# Sprint 2 Exit 리포트

- Sprint 1 청크: **704** / 582,653자
- Sprint 2 청크: **1,136** / 2,298,145자
- **합산: 1,840** / **2,880,798**자

## Sprint 2 source 파일별 산출
- `data/sprint2/day1\chunks.jsonl`: 71 청크 / 924,700자
- `data/sprint2/day1\attachments.jsonl`: 308 청크 / 303,776자
- `data/sprint2/day1\rule_chunks.jsonl`: 0 청크 / 0자
- `data/sprint2/day1\dept_grad_chunks.jsonl`: 85 청크 / 477,380자
- `data/sprint2/day1\dstat\dstat_chunks.jsonl`: 0 청크 / 0자
- `data/sprint2/day2\chunks.jsonl`: 72 청크 / 33,624자
- `data/sprint2/day2\attachments.jsonl`: 356 청크 / 354,134자
- `data/sprint2/day3\chunks.jsonl`: 2 청크 / 457자
- `data/sprint2/day3\attachments.jsonl`: 0 청크 / 0자
- `data/sprint2/day3\cross_tag.jsonl`: 242 청크 / 204,074자
- `data/sprint2/day3\faq_seeds.jsonl`: 1 청크 / 0자 (시드, corpus 미포함)
- `data/sprint2/day3\dorm_js.jsonl`: 0 청크 / 0자

## 합산 도메인별 분포
| 도메인 | 청크수 | 글자수 |
|---|---|---|
| 1 | 579 | 1,780,398 |
| 2 | 5 | 3,338 |
| 3 | 9 | 8,301 |
| 4 | 541 | 475,748 |
| 5 | 915 | 753,085 |
| 6 | 479 | 406,339 |
| 7 | 272 | 204,768 |
| 8 | 7 | 6,650 |
| 9 | 7 | 19,277 |

## 합산 source_type
- T3: 1349건
- T2: 356건
- T1: 135건

## 합산 카테고리 상위 20
| 카테고리 | 글자수 |
|---|---|
| 1.3 | 915,632 |
| 5.4 | 572,109 |
| 1.2 | 477,415 |
| 4.2 | 475,748 |
| 6.3 | 384,278 |
| 1보조FAQ | 384,184 |
| 5.3 | 360,499 |
| 4.1 | 312,844 |
| 4.7 | 312,844 |
| 7.2 | 203,356 |
| 6.6 | 202,287 |
| 6.1 | 18,694 |
| 9.3 | 10,923 |
| 9.2 | 5,811 |
| 8.2 | 4,443 |
| 도서관FAQ | 4,403 |
| 3.1 | 2,453 |
| 1.1 | 2,166 |
| 장학FAQ | 1,765 |
| 2.1 | 1,542 |

## 평가셋 도메인 커버 (Sprint 1+2)
# Sprint 1+2 corpus 평가셋 매핑 점검표

| 도메인 | 명 | 평가합 | 청크수 | 글자수 | 비고 |
|---|---|---|---|---|---|
| 1 | 학사 | 30 | 579 | 1,780,398 | ✓ |
| 2 | 식생활 | 16 | 5 | 3,338 | · |
| 3 | 도서관 | 18 | 9 | 8,301 | · |
| 4 | 기숙사 | 21 | 541 | 475,748 | ✓ |
| 5 | 학생활동·공지 | 13 | 915 | 753,085 | ✓ |
| 6 | 장학금·등록금 | 20 | 479 | 406,339 | ✓ |
| 7 | 진로·취업 | 18 | 272 | 204,768 | ✓ |
| 8 | 행정·증명서 | 20 | 7 | 6,650 | · |
| 9 | 캠퍼스·시설 | 15 | 7 | 19,277 | ✓ |

## Exit 판정
- ✓ Sprint 2 신규 corpus 2,298,145자 (≥100k 목표 달성) — Phase C 진입 OK

## Phase C 핸드오프
- 입력: `data/sprint{1,2}/<day>/{chunks,attachments,rule_chunks,dept_grad_chunks,cross_tag,dorm_js}.jsonl`
- D-1 시드: `data/sprint2/day3/faq_seeds.jsonl`
- 청크 분할 정책 결정 권장 (T3 페이지=청크 매핑이 너무 큼 — Sprint 1 메모 참조)
