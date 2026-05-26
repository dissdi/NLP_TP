# 평가셋 검수 룰북 (Phase D-2 의사결정 기준)

버전: v1.0 (2026-05-26, Phase D-0 작성)
적용 범위: D-1에서 LLM이 생성한 Q&A의 D-2 수동 검수, D-3 최종 확정까지

---

## 0. North Star

**"학교 챗봇은 친절한 안내직원이지, 달변가 영업사원이 아니다."**

우선순위 (절대 양보 없음): **정확성 > 자연스러움 > 표현**

평가셋은 RAG 시스템의 **기준선**이다. 평가셋 자체에 오류·환각이 있으면 시스템 평가가 망가지므로, 검수자는 **"이 정답이 100% 맞는지"** 를 기준으로 본다. 애매하면 Reject.

---

## 1. 검수 의사결정 (3-way enum)

| Decision | 적용 조건 | 후속 |
|---|---|---|
| **Accept** | answer·source·type·tags 모두 OK. 변경 없이 그대로 final set 포함 | `eval_set.jsonl`에 그대로 작성. `reviewed_by`·`reviewed_at` 채움 |
| **Edit** | 정답 사실은 맞으나 표현·길이·tag·source 일부 보정 필요. 핵심 사실은 그대로 | `edit_note`에 무엇을 고쳤는지 명시. `eval_set.jsonl`에 수정본 포함 |
| **Reject** | 정답이 틀림 / 모호함 / chunk에 근거 없음 / 질문 자체가 부적절 | `edit_note`에 reject 사유. `eval_set.jsonl`에 **포함 안 함**. 별도 `eval_review_log.md`에만 기록 |

**원칙: 애매하면 Reject.** Edit로 살리려고 시간 쓰지 말 것. D-1에서 LLM이 더 많이 생성하면 됨.

---

## 2. 타입별 정답 판정 기준

### 2-A. 타입 A (사실 Factual)

**Accept 기준:**
- 단일 사실 1개가 chunk 본문에 명시되어 있음
- answer_gold가 그 사실을 정확히 반영 (숫자·날짜·이름 일치)
- 1~3문장으로 간결

**Reject 시그널:**
- 숫자·날짜가 chunk와 다름 → 환각
- chunk에 "~할 수 있다" 정도만 적혀 있는데 answer가 "반드시 ~한다"로 단정
- "약 50%" vs "정확히 50%" 같은 정도 표현 임의 변경

**Edit 허용:**
- 답변 문체만 어색 → 자연스럽게 다듬기
- 출처 표현 추가("도서관 안내에 따르면 …")

### 2-B. 타입 B (절차 Procedural)

**Accept 기준:**
- 단계가 chunk에 명시된 순서대로 (또는 명확히 추론 가능한 순서)
- 누락된 필수 단계 없음
- 각 단계가 실행 가능한 수준의 구체성

**Reject 시그널:**
- chunk엔 3단계인데 answer가 5단계로 늘림 → 환각
- "온라인 신청" 단계만 있는데 "방문 신청도 가능"이라고 임의 추가
- 단계 순서가 chunk와 모순

**Edit 허용:**
- 단계 번호 매김 보강 (1, 2, 3...)
- 마지막에 "자세한 일정은 공지 확인하세요" 같은 보조 안내 추가

### 2-C. 타입 C (비교 Comparative)

**Accept 기준:**
- 비교 대상 2개 이상이 chunk(들)에 모두 명시
- 비교 축(금액·기간·자격 등)이 명확
- "어느 것이 더 크다"가 chunk 정보로 직접 도출 가능

**Reject 시그널:**
- 비교 대상 중 하나만 chunk에 있고 나머지는 LLM이 일반 지식으로 채움
- 비교 결론이 chunk와 반대 (예: chunk엔 A>B, answer엔 B>A)
- 비교 기준이 모호 ("더 좋다" 같은 주관적 비교)

**Edit 허용:**
- 비교 결론에 단서 추가 ("일반적으로 …하나, 개인 자격에 따라 다름")
- 외부 사이트 참고 안내 추가 (한국장학재단 등)

### 2-D. 타입 D (통계 Statistical)

**Accept 기준:**
- 정확한 수치가 chunk(T6 표 데이터)에 있음
- 수치 단위·분모·기준연도가 answer에 명시
- 출처(대학알리미 등) 명시

**Reject 시그널:**
- 수치 placeholder("XX.X%")가 남아있음 → **자동 Reject**
- 수치는 있으나 단위가 다름 (취업률 60% vs 60명)
- 기준연도 누락 ("취업률은 70%" — 어느 해?)
- chunk의 학과 분류와 question의 학과 분류 미스매치

**Edit 허용:**
- 단위·연도 보강
- "(대학알리미 2024년 공시 기준)" 같은 출처 명시 추가

---

## 3. 공통 검수 체크리스트 (모든 타입)

행마다 다음 9개 항목을 통과해야 Accept.

| # | 항목 | 통과 기준 |
|---|---|---|
| 1 | question이 한국어 자연어로 문제없이 읽힘 | 어색하면 Edit, 의미 안 통하면 Reject |
| 2 | question이 단답 가능한 구체성 | "장학금에 대해 알려주세요" 같은 광범위 질문은 Reject |
| 3 | answer_gold가 chunk 본문에 근거 있음 | 근거 없으면 Reject (환각) |
| 4 | answer_gold에 외부 일반 지식 없음 | LLM이 "보통 ~합니다" 추가했으면 그 문장만 Edit로 삭제 |
| 5 | expected_source_urls 모두 corpus에 존재 | 없는 URL은 Reject 또는 Edit (URL 교체) |
| 6 | domain·categories가 답 내용과 일치 | 불일치면 Edit (재분류) |
| 7 | question_type이 답변 형태와 일치 | A인데 절차 list면 Edit (type B로) |
| 8 | tags ≥ 2개, 검색 키워드 포함 | 부족하면 Edit (tag 추가) |
| 9 | is_fallback_expected 플래그 정확 | §4 참조 |

---

## 4. Fallback Expected 케이스 (특수 처리)

`is_fallback_expected=true`인 QA는 **시스템이 "정보 없음" 또는 fallback 응답을 내야 정답**인 경우.

### 4-1. 어떤 때 fallback expected인가

- **Out of Scope 7가지** ([[project-nlp-tp-decisions]] §스코프) 영역 질문 — 개인 데이터, 민감 정보, 미래 예측, 주관적 평가 등
- **Sparse 도메인** — 5.1·5.5 동아리, 5.3 일부 행사 (§8-5 결정)
- **검색·생성 한계 의도 테스트** — "○○동아리 회장 연락처는?" 같은 비공개 정보

### 4-2. 이 경우의 answer_gold 형식

answer_gold는 **시스템이 내야 할 fallback 메시지의 핵심 의미**를 한 문장으로 적는다. 예:

- "해당 정보는 데이터셋에 포함되어 있지 않습니다. 학생생활관 또는 해당 부서에 직접 문의해주세요."
- "민감 정보입니다. 학생상담센터(042-XXX-XXXX)로 문의해주세요."

### 4-3. Accept 기준

- question이 진짜 Out of Scope거나 sparse임 (커버리지 매트릭스 "—" 셀, 또는 [[project-nlp-tp-coverage]] §평가 매트릭스 외 도메인)
- expected_source_urls는 빈 배열 `[]` 또는 안내 페이지 URL
- 시스템이 잘못 답하면 안 되는 high-stakes 영역

### 4-4. 비율 가이드

전체 ~170문제 중 fallback expected는 **10~20문제(6~12%)** 를 목표. 너무 많으면 평가 변별력 떨어짐, 너무 적으면 hallucination 방지 테스트 부족.

---

## 5. expected_source_urls 검증 규칙

| 케이스 | 처리 |
|---|---|
| URL이 corpus crawled 페이지에 정확히 매치 | OK |
| URL은 다르나 같은 페이지(쿼리 파라미터 차이 등) | Edit로 정규화 |
| URL이 외부 사이트(한국장학재단, 대학알리미 등) | OK — 단 답변에선 cnu 사이트 우선 인용해야 |
| URL이 죽은 링크(404) | Reject 또는 Edit로 교체 |
| URL은 맞으나 그 페이지에 정답 근거 없음 | Reject (LLM이 임의로 URL 붙임) |
| `is_fallback_expected=true`이면서 URL 다수 | Edit로 빈 배열 `[]` 또는 안내 페이지 1개로 줄임 |

---

## 6. 검수 워크플로우 (D-2 운영)

1. **준비**
   - `eval/eval-review-template.xlsx` 사본 열기 (예: `eval-review-2026-06-XX.xlsx`)
   - D-1에서 생성된 `eval/eval-generated.jsonl` 행을 시트에 import (xlsx 템플릿에 import 매크로/안내 포함)
   - 도메인별로 정렬 (도메인별 일관성 확보 위함)

2. **행 단위 검수**
   - question·answer·expected_source_urls 읽고 §3 체크리스트 9개 통과 여부 판정
   - decision 셀에 Accept/Edit/Reject 입력 (드롭다운)
   - Edit인 경우: `edited_question`·`edited_answer`·`edit_note` 컬럼 채움
   - Reject인 경우: `edit_note`에 사유 1줄

3. **검수 진행률 관리**
   - 도메인별로 검수 → 한 도메인 끝나면 잠깐 쉼 (피로 누적 방지)
   - Phase D 12일 plan 기준 D-2는 Day 6·Day 8·Day 10 분산 진행
   - 평가 가중치 큰 학사·도서관·장학 먼저 (§14-4 리스크 완화책)

4. **최종 export**
   - 검수 완료된 시트에서 Accept + Edit 행만 추출
   - `eval/eval_set.jsonl`로 export (§12-5 + D-0 추가필드 스키마)
   - Reject 행은 `eval/eval_review_log.md`에 사유와 함께 보존

5. **품질 지표 (목표)**
   - 도메인별 Accept rate ≥ 60% (너무 낮으면 D-1 프롬프트 개선 필요)
   - 도메인별 최종 통과 문제 수가 §평가 매트릭스 목표치(170 중 분배)의 80% 이상

---

## 7. 명확히 하지 않는 케이스 (검수자 재량)

다음은 룰북에 강제 규칙 두지 않음. 검수자가 일관성 있게 판단.

- 답변 길이의 적정선 (1문장 vs 5문장)
- "약 X" vs "정확히 X" 표기
- 어미 정중함 수준 ("입니다" vs "해주세요")
- tag 개수 (최소 2개만 강제)

→ 일관성 위해 검수 첫날 20문제 정도는 보수적으로(Reject 많이) 진행 후, 자기 기준 굳어지면 속도 올림.

---

## 8. 검수 결과의 추적 가능성

검수 결과는 다음 3 파일에 남김:
- `eval/eval_set.jsonl` — 최종 통과(Accept + Edit) 데이터
- `eval/eval_review_log.md` — Reject 사유, 모호 케이스 의사결정, 도메인별 통과율
- `eval/eval-review-2026-XX-XX.xlsx` — 작업 시트 원본 (감사 추적)

→ 평가 결과 분석 시 "이 문제는 검수자가 어떤 근거로 Accept했나" 역추적 가능해야 함.

---

관련 문서:
- 샘플 5개: `eval/eval-samples.jsonl` + `eval/eval-samples-notes.md`
- LLM 생성 프롬프트: `eval/eval-generation-prompt.md`
- 수동 검수 템플릿: `eval/eval-review-template.xlsx`
- 커버리지 매트릭스: `coverage-plan.md`
- crawling-targets: `crawling-targets.md` (§12-5)
