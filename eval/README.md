# Phase D — 평가셋 구축

Phase D는 RAG QA 시스템 평가용 ~170문제 Q&A 셋을 만드는 트랙. Phase B(크롤러)와 병렬 진행.

분할:
- **D-0 설계** ← 본 채팅에서 완료 (2026-05-26)
- D-1 생성 — Claude로 corpus chunk → Q&A 자동 생성 (Sprint 1 Day 3 이후)
- D-2 수동 검수 — 룰북 + xlsx 템플릿 활용
- D-3 최종 확정 — `eval_set.jsonl` 잠금

---

## D-0 산출물 (4종)

| 파일 | 역할 | 다음 단계에서 사용 |
|---|---|---|
| `eval-samples.jsonl` | 수작업 골드 샘플 5건. 스키마·룰북 검증용 | D-1 few-shot, 검수자 캘리브레이션 |
| `eval-samples-notes.md` | 샘플 작성 노트, §12-5 스키마 갭 발견 정리 | D-1·D-2 작업자 참고. 16-필드 확장 스키마 정의 |
| `eval-rubric.md` | D-2 검수 의사결정 룰북 (3-way: Accept/Edit/Reject) | D-2 검수자가 매 행마다 참조 |
| `eval-generation-prompt.md` | D-1에서 Claude에 줄 시스템 프롬프트 v1 + 사용자 메시지 템플릿 | D-1 채팅에서 그대로 복붙 |
| `eval-review-template.xlsx` | D-2 검수 워크시트 (4 시트: 워크시트·가이드·Enum·대시보드) | D-2 검수자가 사본 만들어 작업 |

---

## 평가셋 스키마 (D-0 확장본, 16 필드)

§12-5 원안(11 필드) → D-0에서 5필드 추가. 자세한 사유는 `eval-samples-notes.md` §2-2 참조.

```json
{
  "qa_id": "S/G/R + 식별자",
  "question": "string",
  "answer_gold": "string (chunk 발췌·요약만)",
  "domain": 1-9,
  "categories": ["1.4", ...],
  "question_type": "A|B|C|D|E|F",
  "expected_source_urls": ["..."],
  "is_fallback_expected": false,
  "tags": [...],
  "created_by": "human|llm-claude|llm-claude-fallback",
  "reviewed_by": "human-{이니셜}|null",
  "created_at": "ISO 8601|null",
  "reviewed_at": "ISO 8601|null",
  "gen_prompt_version": "v1.0|null",
  "notes": "string|null"
}
```

`qa_id` prefix:
- `S` = D-0 수작업 Sample
- `G` = D-1 LLM Generated (검수 전)
- `R` = D-2 통과 후 final eval_set 진입

---

## xlsx ↔ JSON 필드 매핑 (D-2 export 시 참고)

xlsx 검수 시트는 워크플로우 편의로 일부 컬럼명이 JSON과 다름. D-2 → D-3 export 시 변환:

| xlsx 컬럼 | JSON 필드 | 비고 |
|---|---|---|
| `qa_id`·`question`·`answer_gold`·`domain`·`categories`·`question_type`·`expected_source_urls`·`is_fallback_expected`·`tags`·`created_by`·`gen_prompt_version`·`created_at` | (동명) | 그대로 export |
| `decision=Accept` | (그대로) → final set 포함 | — |
| `decision=Edit` + `edited_question`·`edited_answer` | `question`·`answer_gold` overwrite | edit_note는 notes로 |
| `decision=Reject` | (final set 미포함) | `eval_review_log.md`에만 |
| `reviewer` | `reviewed_by` | — |
| `reviewed_at` | `reviewed_at` | — |
| `edit_note` | `notes` | Accept/Reject 케이스에선 빈 값 가능 |

D-3에서 export 스크립트(`eval/export_eval_set.py`) 작성 — 본 채팅 범위 외.

---

## D-0 검증 결과

- 샘플 5건 모두 JSON 파싱 통과 (`python3 -m json.tool` 통과)
- 5건이 §12-5 스키마 11개 필수 필드 모두 채움 (S003은 created_by/reviewed_by 누락하여 optional 동작 확인)
- xlsx 88 formulas, 0 errors (LibreOffice 재계산 검증)
- xlsx 진행률 대시보드가 샘플 3행으로 정확히 집계 (Accept 2/Reject 1, 도메인별·타입별 카운트 정합)
- 룰북·프롬프트가 동일 스키마(16 필드) 참조 확인
- 룰북의 9 체크리스트 ↔ 프롬프트의 6 절대 규칙 ↔ xlsx의 18 컬럼 정합 확인

---

## D-1로 넘기는 컨텍스트 (다음 채팅에 전달)

다음 채팅(채팅 W, Phase D-1)을 열 때 반드시 짚을 것:

1. **시작 트리거:** Phase B Sprint 1 Day 3에 도서관 FAQ 크롤링 완료 후 (가장 정답쌍 자동 생성 효율 높은 시드)
2. **첫 배치 도메인 권장 순서:** 도서관 → 장학 → 보건 (FAQ 보유) → 학사·기숙사·식생활 (정적 페이지) → 진로·행정 → 학생활동·캠퍼스시설 (sparse)
3. **`gen_prompt_version` v1.0으로 시작.** 첫 배치(~20 QA) 결과 보고 v1.1 개정 여부 결정
4. **fallback expected는 별도 배치.** 일반 chunk 기반 프롬프트와 분리 (프롬프트 §5 참조)
5. **batch 단위:** 1 batch = 동일 도메인 chunk 5~10개 → ~15~30 QA → 1 jsonl 파일 (예: `eval-generated-domain3-batch1.jsonl`)
6. **D-1 ↔ D-2 핸드오프:** 한 batch jsonl 생성 즉시 검수자가 xlsx import → 검수 → 결과 피드백을 v1.1 프롬프트 개정에 반영하는 fast loop

### ⚠️ 알아둘 정합성 이슈

- `crawler/schema.py`의 corpus chunk `freshness` 필드 enum이 `"static"/"dated"/"rolling"`이라 §12 원안(`S|Q|M|W`)과 다름. D-1 단계에서는 chunk의 freshness 필드를 그대로 사용. eval_set 스키마와는 무관함 (eval엔 freshness 없음).
- `crawler/schema.py`의 `chunk_id`는 16-hex 해시(UUID 아님). eval_set의 `expected_source_urls`는 URL 기반이라 영향 없음.

---

## 운영 흐름 (D-0 이후)

```
D-1: Claude 채팅에서 batch별 생성
       ↓ (eval-generated-{domain}-batch{N}.jsonl)
D-2: xlsx 사본에 import → 검수 → decision 입력
       ↓ (eval-review-{YYYY-MM-DD}.xlsx + eval_review_log.md)
D-3: 통과 행 export → eval_set.jsonl 잠금
       ↓
Task 3 (RAG 파이프라인)에서 평가셋 사용
```

---

관련 문서:
- crawling-targets.md §14: 12일 Phase B·D 병렬 일정
- crawling-targets.md §12-5: 평가셋 스키마 원안
- coverage-plan.md: 평가 매트릭스 ~170문제 분배
