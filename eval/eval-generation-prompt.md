# LLM Q&A 자동 생성 프롬프트 v1 (Phase D-1)

버전: v1.0 (2026-05-26, Phase D-0 작성)
대상 LLM: **Claude (이 채팅에서 직접 호출)** — 채팅 W에서 corpus chunk를 입력해 사용
출력 스키마: `eval-samples-notes.md` §2-3 (§12-5 + D-0 확장 = 16 필드)

---

## 0. 사용 방법

D-1 채팅에서 corpus chunk 1건 또는 묶음을 input으로 주고 아래 **§1 시스템 프롬프트**를 system 메시지로, **§2 사용자 메시지 템플릿**을 user 메시지로 사용. 출력 JSON을 파싱하여 `eval-generated.jsonl`에 append.

배치 처리: 도메인별로 chunk 묶음 → 도메인별 jsonl → 도메인별 검수.

`gen_prompt_version` 필드는 출력 JSON에 자동 포함되므로, 프롬프트 개정 시 v1.1, v2 등으로 버전 올리고 LLM에 명시.

---

## 1. 시스템 프롬프트 (그대로 복사하여 사용)

```
당신은 충남대학교 학생을 위한 학내 정보 RAG QA 시스템의 평가셋을 만들고 있습니다.
주어진 corpus chunk(학교 사이트에서 크롤링한 문서 일부)를 읽고, 학생이 실제로 물어볼 만한 질문과 chunk 본문에 근거한 정답을 만듭니다.

## 절대 규칙

1. **chunk 본문에 명시되어 있지 않은 사실은 절대 생성하지 않는다.** 일반 지식·외부 추론·"보통은 ~합니다" 같은 표현 금지.
2. **숫자·날짜·금액·이름·URL은 chunk에서 그대로 발췌만 한다.** 한 자라도 다르면 안 됨.
3. **answer_gold는 chunk 본문에서 발췌·요약한 내용만으로 구성**한다. 외부 사이트 안내는 chunk에 적혀 있을 때만.
4. **expected_source_urls는 입력으로 받은 chunk의 source_url만 사용**한다. 다른 URL을 추가하지 말 것.
5. **정답을 만들 근거가 chunk에 부족하면 빈 결과 `{"qa_pairs": []}`를 반환**한다. 억지로 채우지 말 것.
6. 출력은 반드시 JSON 1개. 마크다운 코드블록·설명·인사말 모두 없이 raw JSON만.

## 타입별 생성 규칙

- **타입 A (사실)**: chunk에 명시된 단일 사실 1개에 대해 질문. 답은 1~3문장. 숫자·이름·날짜는 chunk에서 그대로.
- **타입 B (절차)**: chunk에 단계가 명시되어 있을 때만 생성. 답은 단계별 list 형태. chunk에 없는 단계 추가 금지.
- **타입 C (비교)**: chunk(들) 안에 비교 대상 2개 이상이 모두 있을 때만 생성. 한쪽이 chunk에 없으면 type C 생성 skip, 대신 type A 1개 생성.
- **타입 D (통계)**: chunk가 T6(표 데이터)이고 정확한 숫자가 명시되어 있을 때만 생성. placeholder("XX.X%") 절대 금지. 단위·기준연도 반드시 명시.

## 추가 규칙

- question은 한국어 자연어로, 학생이 실제 쓸 법한 말투. "~인가요?" "~어떻게 해요?" 등.
- question은 **단답 가능한 구체성** 보장. "학사에 대해 알려주세요" 같은 광범위 질문 금지.
- question에 학기·연도가 관련되면 명시("2026학년도 1학기" 등) — 시점 고정.
- answer_gold는 학생에게 안내하는 친절한 어조이되 군더더기 없이. 핵심 사실 → 부가 안내 → (필요시) 출처 안내 순.
- tags는 검색 키워드 기준 최소 3개. 카테고리명·핵심 명사 위주.

## 출력 스키마 (JSON)

다음 16필드 모두 채워서 `qa_pairs` 배열에 담아 반환:

{
  "qa_pairs": [
    {
      "qa_id": "G{timestamp}{idx} 형식 (예: G260526001)",
      "question": "string (한국어)",
      "answer_gold": "string (한국어, chunk 발췌·요약만)",
      "domain": <integer 1~9>,
      "categories": ["string"],
      "question_type": "A|B|C|D",
      "expected_source_urls": ["string (chunk source_url 그대로)"],
      "is_fallback_expected": false,
      "tags": ["string", ...],
      "created_by": "llm-claude",
      "reviewed_by": null,
      "created_at": "ISO 8601 timestamp",
      "reviewed_at": null,
      "gen_prompt_version": "v1.0",
      "notes": "string|null (모호한 부분 있으면 검수자에게 메모)"
    }
  ]
}

근거 부족 시: {"qa_pairs": []} 만 반환. 이유 설명·코드블록 없이.
```

---

## 2. 사용자 메시지 템플릿

```
입력 chunk(들):

<chunks>
{여기에 corpus.jsonl의 chunk 1개 또는 여러 개를 JSON 리스트로 붙여넣기}
</chunks>

목표 타입: {A 또는 B 또는 C 또는 D, 혹은 "혼합" — 혼합이면 LLM이 chunk 성격에 맞게 선택}
목표 개수: {정수, 예: 3 — chunk 정보가 부족하면 더 적게 반환해도 됨}
도메인 힌트: {1~9 중 1개 — chunk 메타와 다르면 chunk 메타 우선}

위 chunk(들)을 근거로 학생 평가용 Q&A를 §1 시스템 프롬프트 규칙에 따라 생성하세요.
```

---

## 3. Few-shot 참조 (시스템 프롬프트에 첨부할 좋은 예시)

LLM 응답 품질이 낮을 경우 시스템 프롬프트 끝에 다음 예시를 첨부하면 도움됨. (Phase D-1 첫 배치 결과 보고 추가 여부 결정.)

### 예시 1: 단순 타입 A

**입력 chunk:**
```json
{"text":"수강신청 정정 기간은 2026학년도 1학기 기준 2026년 3월 6일(금)까지입니다.","source_type":"T1","source_url":"https://plus.cnu.ac.kr/html/kr/sub05/sub05_05020101_01.html","source_title":"학사안내 - 수강신청","domains":[1],"categories":["1.4"],...}
```

**입력 메시지:** 목표 타입: A, 목표 개수: 1, 도메인 힌트: 1

**기대 출력:**
```json
{"qa_pairs":[{"qa_id":"G260526001","question":"2026학년도 1학기 수강신청 정정 기간은 언제까지인가요?","answer_gold":"2026학년도 1학기 수강신청 정정 기간은 2026년 3월 6일(금)까지입니다.","domain":1,"categories":["1.4"],"question_type":"A","expected_source_urls":["https://plus.cnu.ac.kr/html/kr/sub05/sub05_05020101_01.html"],"is_fallback_expected":false,"tags":["수강신청","학사일정","정정기간"],"created_by":"llm-claude","reviewed_by":null,"created_at":"2026-05-26T14:30:00+09:00","reviewed_at":null,"gen_prompt_version":"v1.0","notes":null}]}
```

### 예시 2: 정보 부족으로 거부

**입력 chunk:**
```json
{"text":"본 학과는 우수한 교수진과 시설을 갖추고 있습니다.","source_type":"T1","source_url":"https://...","domains":[1],...}
```

**입력 메시지:** 목표 타입: D, 목표 개수: 1

**기대 출력:**
```json
{"qa_pairs":[]}
```

(설명·사유 없음. 통계 데이터가 chunk에 없으므로 type D 생성 불가.)

### 예시 3: 타입 C — 비교 대상 2개 필요

**입력 chunk:** 국가장학금 1유형·2유형 금액·자격이 둘 다 있는 페이지

→ 타입 C 생성 OK. answer는 두 유형 모두 명시된 정보만 비교.

비교 대상 중 하나만 있으면 → type A로 fallback (시스템 프롬프트 규칙 #3).

---

## 4. 운영 가드 (D-1 채팅에서 지켜야 할 것)

| 가드 | 이유 |
|---|---|
| 1 chunk → 최대 3 QA | 한 chunk에서 너무 많이 짜내면 비슷한 질문 반복. 3개로 제한 |
| 1 배치 = 동일 도메인 chunk만 | 도메인 일관성 + 검수 효율. cross 청크는 별도 배치 |
| 배치당 chunk 5~10개 | LLM 컨텍스트 부담 적절 + 결과 검토 가능 단위 |
| FAQ chunk는 별도 배치·별도 프롬프트 변형 가능 | Q&A 쌍이 이미 있으므로 거의 직역. 보조 프롬프트 변형은 D-1에서 결정 |
| Fallback expected 케이스는 다른 프롬프트로 별도 생성 | 일반 프롬프트는 chunk 기반 — fallback은 corpus 외 질문이므로 별개 |
| 출력 JSON 파싱 실패 시 1회 재시도 + skip | LLM이 가끔 코드블록 붙임. 재시도해도 실패면 그 chunk skip 후 로그 |
| 매 배치 종료 시 빠른 sanity check | URL이 chunk source_url과 일치하는지, 숫자가 chunk 발췌인지 |

---

## 5. Fallback Expected 별도 프롬프트 (v1)

`is_fallback_expected=true` 케이스는 일반 프롬프트로 생성 불가 (chunk 기반이 아니므로). 별도 생성 흐름:

```
당신은 충남대학교 학생용 RAG QA 시스템의 평가셋을 만들고 있습니다.
이번에는 **시스템이 "정보 없음" 또는 fallback 응답을 내야 정답인 질문**을 생성합니다.

다음 4가지 카테고리에서 골고루 생성하세요:
1. Out of Scope (개인 데이터·민감 정보·미래 예측·주관적 평가·비공개 정보·충남대 외 정보)
2. Sparse 도메인 (5.1·5.5 동아리 상세, 5.3 일부 행사)
3. 검색 한계 의도 테스트 (특정 인물 연락처 등 비공개)
4. 모호한 질문 의도 (시스템이 되묻거나 거부해야)

각 질문에 대해:
- answer_gold는 시스템이 내야 할 fallback 메시지의 핵심 의미를 한 문장으로
- expected_source_urls는 [] (없음) 또는 안내 페이지(상담센터 등) 1개
- is_fallback_expected: true
- created_by: "llm-claude-fallback"
- 나머지 스키마 동일

목표 개수: {정수, 예: 5}
출력: 위 16필드 JSON 배열.
```

---

## 6. 다음 버전(v1.1)에 반영 검토

D-1 첫 배치 결과를 보고 v1.1로 개정할 가능성 있는 항목:

- 도메인 5(학생활동) sparse 보정 — fallback 비율 자동 조정
- 타입 C에서 비교 대상이 다른 chunk에 분산된 경우 처리 (현 v1: 한 chunk 안에 둘 다 있어야)
- 첨부 PDF chunk(`parent_post_id` 있음)의 경우 게시물 본문 chunk와 묶어서 입력하는 옵션
- few-shot 예시 추가 (예시 1~3 부족하다 판단되면)

→ 개정 시 `gen_prompt_version` 필드 v1.1로 올리고, eval-generated.jsonl 분석 시 버전별 품질 비교.

---

관련 문서:
- 룰북: `eval/eval-rubric.md`
- 샘플 5개: `eval/eval-samples.jsonl` + `eval/eval-samples-notes.md`
- 스키마: `eval/eval-samples-notes.md` §2-3 (§12-5 확장본)
- 검수 템플릿: `eval/eval-review-template.xlsx`
