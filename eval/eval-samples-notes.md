# 평가셋 샘플 5개 작성 노트 (Phase D-0)

작성일: 2026-05-26
작성자: human (D-0 설계자)
목적: §12-5 평가셋 스키마 검증 + LLM 생성 프롬프트·룰북 작성을 위한 골드 시드

---

## 1. 샘플 분포

5개로 도메인·타입·source_type 골고루 커버.

| qa_id | 도메인 | 카테고리 | 타입 | source_type 가정 | 의도 |
|---|---|---|---|---|---|
| S001 | 1. 학사 | 1.4 수강신청 | A. 사실 | T1 정적 페이지 | 가장 기본형 — 단일 사실, 단일 source |
| S002 | 4. 기숙사 | 4.2 신청 | B. 절차 | T1 + T2 게시판 | 다단계 절차, multi-source |
| S003 | 6. 장학금 | 6.1 종류 | C. 비교 | T1 정적 | 비교형, 외부 한국장학재단 참조 |
| S004 | 7. 진로 | 7.5 D-통계 | D. 통계 | T6 표 데이터 | 표 파싱 후 채워야 함 → answer_gold placeholder |
| S005 | 3. 도서관 | 3.5 대출규정 | A. 사실 | T1 FAQ | FAQ 시드 직접 변환 (D-1에서 자동 생성 핵심 경로) |

5개로 9도메인 다 못 커버하지만, **타입 A/B/C/D 4종 + source_type T1/T2/T6 + multi-URL + placeholder 케이스**를 한 번씩 밟음. 스키마 검증 목적엔 충분.

---

## 2. §12-5 스키마 검증 결과

### 2-1. 모든 필드 채워봄

§12-5 정의 11개 필드(`qa_id`·`question`·`answer_gold`·`domain`·`category`·`question_type`·`expected_source_urls`·`is_fallback_expected`·`tags`·`created_by`·`reviewed_by`) 전부 채워봄. S003은 `created_by`·`reviewed_by` 일부러 빠뜨려 optional 동작 확인용. S004는 추가로 `notes` 필드를 즉흥 추가했음 → **스키마에 `notes` 필드 추가 필요** (D-0 발견사항 #1).

### 2-2. 발견된 스키마 갭

| # | 갭 | 권장 처리 |
|---|---|---|
| 1 | `notes` 필드 없음. S004처럼 "값은 placeholder, 나중에 보정" 같은 메타 정보 적을 곳 필요. | §12-5 스키마에 `notes: string\|null` 추가. corpus chunk 스키마(§12-1)와 일관 |
| 2 | `created_at` / `reviewed_at` 타임스탬프 없음. corpus chunk엔 `crawled_at` 있음. | `created_at`·`reviewed_at` ISO 8601 추가. 검수 이력 추적용 |
| 3 | `generation_prompt_version` 없음. D-1 프롬프트 v1/v2 비교·재현성 추적 필요. | `gen_prompt_version: string\|null` 추가. human 작성은 null |
| 4 | `category` 단일 string인데, cross-domain은 다중 category 가능(예: S004는 7.5+1.7 둘 다). | `categories: string[]`로 변경 (corpus chunk와 동일 형태) |
| 5 | `question_type` 단일 enum인데, 복합형 가능(예: "비교+절차"). 현 매트릭스는 단일이라 OK이나 D-1에서 발견 가능. | 일단 단일 유지, 복합형 발견 시 룰북에서 "더 dominant한 쪽" 선택 규칙 명시 |
| 6 | `difficulty` 없음. RAG가 풀기 쉬운·어려운 문제 구분 필요할 수 있음. | 보류 — Sprint 3 평가 분석 시 필요하면 추가 |
| 7 | `is_fallback_expected=true` 케이스가 샘플에 없음 → 룰북에서 별도 예시로 명시 필요. | 룰북 §4에 fallback 케이스 가이드 작성 |

### 2-3. 수정 권장 §12-5 스키마 (D-0 버전)

```json
{
  "qa_id": "string (S001, G0001 등 prefix로 source 구분)",
  "question": "string",
  "answer_gold": "string",
  "domain": "integer (1~9, primary)",
  "categories": "string[] (예: ['1.4','8.3'] — cross 가능)",
  "question_type": "string (A|B|C|D|E|F, single dominant)",
  "expected_source_urls": "string[] (정답 근거 URL, 다중 가능)",
  "is_fallback_expected": "boolean",
  "tags": "string[]",
  "created_by": "string (human|llm-claude|llm-gpt4o-mini 등)",
  "reviewed_by": "string|null (human-{이니셜} 등)",
  "created_at": "string|null (ISO 8601)",
  "reviewed_at": "string|null (ISO 8601)",
  "gen_prompt_version": "string|null (예: 'v1')",
  "notes": "string|null"
}
```

총 16필드 (기존 11 + 추가 5). corpus chunk(§12-1)도 16필드라 우연히 일치.

`qa_id` prefix 규약: **S=Sample(D-0 수작업), G=Generated(D-1 LLM), R=Reviewed-only(D-1 LLM + D-2 통과)**. R prefix는 final eval_set에 쓰임.

---

## 3. 작성하며 발견한 의사결정 포인트 (룰북에 반영)

| 결정 포인트 | D-0 잠정 결정 |
|---|---|
| 정답이 시점·학기 의존(S001 "2026-1학기 3월 6일") → 매학기 갱신 필요한가? | 평가셋은 **시점 고정 snapshot**. 학기 정보를 question에 명시("2026-1학기")해서 정답 불변하도록 작성. F.시점 도메인은 평가 제외이므로 일관 |
| Cross-domain(S004 7.5는 1.7과도 cross) → `domain` 단일 vs `domains[]` | **primary domain만 단일**, cross 정보는 `categories[]`·`tags`로 표현. 검색·통계 단순화 |
| answer_gold 길이 — 한 문장 vs 여러 문장 | **핵심 사실 1문장 + 부가 설명 2-3문장**. 절차형(B)은 단계 list형 허용. 너무 길면 LLM judge가 부분 일치 판정 모호 |
| 외부 사이트(한국장학재단·대학알리미) URL을 expected_source_urls에 넣어도 되나? | **OK**. 단 corpus crawling 대상이 아니어도 정답 근거가 거기에 있으면 인용. 답변에선 cnu 사이트 우선 인용 권장 (룰북) |
| answer_gold에 placeholder("XX.X%") 허용 시점 | **D-0 수작업 샘플은 허용**, D-1 LLM 생성·D-2 검수 통과시점부터는 placeholder 금지 — 실제 값으로 채워야 함 |

---

## 4. D-1 LLM 프롬프트에 반영해야 할 사항 (cheatsheet)

D-0 샘플 작성 경험에서 LLM에 시킬 때 명시할 가드:

1. **chunk에 명확히 적히지 않은 사실은 생성 금지** (hallucination 방지) — 학기 숫자·날짜·금액 등은 chunk에서 발췌만
2. **answer_gold는 chunk 본문에서 발췌·요약만**. 외부 지식 주입 금지
3. **expected_source_urls는 입력으로 받은 chunk의 source_url만 사용**. LLM이 임의로 URL 생성 금지
4. **타입 D(통계)는 정확한 숫자가 chunk에 없으면 생성 skip** ("XX.X%" placeholder 금지)
5. **타입 C(비교)는 비교 대상 2개 이상의 정보가 chunk 안에 있어야만 생성**. 한쪽이 chunk에 없으면 type A로 fallback
6. **fallback expected 케이스는 별도 프롬프트로 생성**. corpus에 답이 없는 질문을 의도적으로 생성 (Out of Scope, sparse 영역)

---

## 5. 작업물 위치

- 샘플 JSONL: `eval/eval-samples.jsonl` (5건)
- 본 노트: `eval/eval-samples-notes.md`
- 다음 산출물: `eval/eval-rubric.md`, `eval/eval-generation-prompt.md`, `eval/eval-review-template.xlsx`

다음 단계: 룰북 작성 (Task #2). 이 노트의 §3·§4가 룰북에 반영됨.
