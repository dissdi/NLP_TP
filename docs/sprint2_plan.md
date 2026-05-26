# Sprint 2 작업 계획

**기간:** 3~4일 (Day 1~3 크롤 + Day 4 Exit 검증)
**목표:** P1 24개 항목 + Sprint 1 이월 3건(1.2 학과 졸업요건·1.3 학칙·4.1 dorm JS) 처리
**예상 산출:** Sprint 1(582,653자) + Sprint 2(~118k~268k자) = 700~850k자, 평가셋 ~168문제 커버

## 결정사항 (Sprint 2 시작 시)

1. **범위:** 원안(§9 Sprint 2) + 이월 3건 통합 — 평가 영향 큰 학과 졸업요건(8문제)·학칙(4문제) 동시 해결
2. **D-통계(1.7/7.5/4.7)·학칙 HWP:** raw 추출까지만. 표 → 자연어 변환은 Task 3 (RAG 파이프라인)으로 위임
3. **dorm JS:** 시도 → 실패 허용 (평가 5문제 중 4.2 공지로 부분 커버)

## Day 분할 (24 tasks, sprint2_targets.json)

### Day 1 — 이월 + D-통계 (4 task)
| id | 어댑터 | 카테고리 | 비고 |
|---|---|---|---|
| 1.3_rule_list | RULE_HWP | 1.3 | **신규 어댑터.** `javascript:void(0)` onclick → ntt_no 파싱 → download.php HWP |
| 1.7_alimi_freshman | ALIMI_PDF | 1.7, 7.5 | 대학알리미 PDF (URL spike 필요) — raw CSV |
| 4.7_dorm_competition | PDF | 4.7 | 기숙사 알림마당 선발결과 첨부 PDF — raw CSV |
| 1.2_dept_grad_spike | DEPT_GRAD | 1.2 | 공통 졸업요건 재확인 + 학과 URL 패턴 spike (Sprint 1 intro01.do 실패) |

### Day 2 — 학생활동·진로·도서관·캠퍼스 (11 task)
| id | 어댑터 | 카테고리 |
|---|---|---|
| 5.1_clubs / 5.2_student_council / 5.3_events | A·A·B | 5.1, 5.2, 5.3 |
| 7.2_career_board / 7.4_career_counsel | B·A | 7.2, 7.4 |
| 3.3_seat_reservation / 3.5_loan_rules / 3.5_loan_board / 3.6_branch_compare | A·A·B·A | 3.3, 3.5, 3.6 |
| 9.1_map_transport / 9.3_gym_reserve | A·A | 9.1, 9.3 |

### Day 3 — 행정·식당·장학 cross + dorm JS + FAQ 시드 (9 task)
| id | 어댑터 | 카테고리 |
|---|---|---|
| 8.3_record_cross | CROSS_TAG | 8.3 (1.5 청크 재태깅) |
| 8.4_admin_directory / 8.5_mail_docs | A·B | 8.4, 8.5 |
| 2.3_meal_ticket / 2.4_food_compare | A·CROSS_TAG | 2.3, 2.4 |
| 6.5_kosaf_loan / 6.6_scholar_compare | A·CROSS_TAG | 6.5, 6.6 |
| 4.1_dorm_main_js | JS_FALLBACK | 4.1 (이월, 실패 허용) |
| 5.4_faq_seed | FAQ_SEED | faq_seed (Phase D-1 입력) |

### Day 4 — Exit 검증
- `sprint2_verify.py` 실행 → `logs/sprint2/report.md` + `coverage.json`
- Sprint 1 + Sprint 2 합산 통계
- Phase C 핸드오프 노트

## 신규 어댑터 / 처리 모드

| 이름 | 위치 | 역할 |
|---|---|---|
| RULE_HWP | `crawler/adapters/e_rule_hwp.py` (신규) | `_prog/rule/` 리스트 + onclick ntt_no 파싱 + HWP 다운로드 |
| ALIMI_PDF | `crawler/adapters/f_alimi.py` (신규) | 대학알리미 PDF endpoint 처리 (재사용성 낮으므로 wrapper만) |
| CROSS_TAG | `scripts/sprint2_cross_tag.py` | 신규 크롤 없이 기존 청크의 categories/domains 확장 |
| JS_FALLBACK | `scripts/sprint2_dorm_js.py` | Playwright 시도 → 실패 시 4.2 공지로 fallback documenting |
| FAQ_SEED | `scripts/sprint2_faq_seed.py` | 백마광장 청크에서 FAQ 패턴 추출 |
| DEPT_GRAD | `scripts/sprint2_dept_grad.py` | 학과 메뉴 spike → 졸업요건 URL 후보 → 어댑터 A 호출 |

## Exit 기준

- [ ] P1 24개 + 이월 3건 = 27 task 시도 (실패 허용 항목: 4.1 dorm JS, 1.7 alimi PDF)
- [ ] Sprint 2 신규 corpus ≥ 100,000자 (학칙 HWP 제외 시 목표치)
- [ ] 평가셋 168문제 중 P0+P1 커버 가능 매핑 점검 (logs/sprint2/coverage_vs_eval.md)
- [ ] errors.json·skip 사유 명시 → Phase C 진입 가능 판정

## 사용자 실행 명령 (사용자 로컬 cmd)

```cmd
:: 사전 spike (학과 졸업요건 URL · 학칙 onclick · 알리미 PDF endpoint)
scripts\run_sprint2.bat inspect

:: Day별 본 크롤
scripts\run_sprint2.bat day1
scripts\run_sprint2.bat day2
scripts\run_sprint2.bat day3

:: 첨부 후처리 (PDF/HWP)
scripts\run_sprint2.bat attachments

:: Exit 검증
scripts\run_sprint2.bat verify
```

## 관련 문서

- crawling-targets.md §9 — 원본 Sprint 분할
- logs/sprint1/report.md — Sprint 1 결과 (119% 달성)
- Sprint 1 이월 메모: `[[project-nlp-tp-sprint1]]`
