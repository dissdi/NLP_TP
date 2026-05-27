# Phase C 진입 계획 (정제·청킹·임베딩 사전 결정사항)

작성일: 2026-05-27
입력 인벤토리: [phase_c_inputs.md](phase_c_inputs.md)

## 0. 참고: 사용 안 하는 디렉토리

- `data/_archive/` — Sprint 0 PoC, UbiReport spike 산출. **읽기만** (회귀 비교용 보존)
- `scripts/_spike/` — 알리미 flag 매핑 근거 진단 코드 3종 (spike_almi_ubireport, spike_ubireport_parser, test_dept_flags_wide). Phase C에서 안 씀, 추후 재크롤링 시 참고용.

## 1. Phase C 범위

원래 Phase B(크롤러) → **Phase C(정제·청킹)** → Phase D(평가셋) → Phase E(RAG+LLM).
크롤러가 이미 chunk 단위 출력을 만들었으므로 Phase C는 다음 4단계로 한정:

1. **Pre-processing (정제)** — 노이즈 제거, 중복 제거, 텍스트 정규화
2. **Re-chunking (재청크)** — 거대 청크 분할, 초소형 청크 병합
3. **Enrichment (메타 강화)** — 누락 도메인/카테고리 태그 보완, freshness 결정값 계산
4. **Embedding & Index** — 벡터화 → FAISS/Chroma 인덱스 구축

→ 이후 Phase E (검색 전략·LLM·프롬프트) 로 넘어감.

## 2. 출력 디렉토리 구조 (제안)

```
data/
  sprint{1,2,3}/        ← 원본 (touch X, read-only로 취급)
  phase_c/
    01_clean/           ← 정제 후 jsonl (스키마 유지)
    02_rechunked/       ← 재청크 결과
    03_enriched/        ← 메타 보완 결과 (최종 청크 = 임베딩 입력)
    04_index/
      faiss/
      bm25/             ← hybrid 검색용
      meta.parquet      ← chunk_id ↔ metadata lookup
    reports/
      duplicate_report.md
      rechunk_report.md
      domain_recover_report.md
```

## 3. 핵심 정책 결정

### 3.1 재청크 정책 (★ 가장 중요)

| 조건 | 정책 |
|---|---|
| `char_count` > 2,000 | **분할**. 의미 단위(빈 줄 / `===` / 1.~10. 번호 / HWP 페이지 break) 우선, 없으면 1,500자 sliding window (overlap 200) |
| `char_count` < 50 | **병합 후보**. 같은 `parent_post_id` + 인접 `chunk_index` 끼리 누적. 단, 알리미 셀(`source_type=T6`)은 학과 단위로 별도 병합 룰 적용 |
| 50 ≤ `char_count` ≤ 2,000 | **유지** |

**예외:**
- 학칙 HWP (sprint2/day1/chunks.jsonl, max 81,437자): 페이지=청크 매핑 깨고 조문(제○조) 단위 분할 시도. 실패 시 1,500자 window.
- 알리미 dept_info (sprint3, avg 77자): "{학과}의 {지표} = {값}" 단순 셀이라 BM25에는 그대로, dense vector는 학과 단위로 묶어서 별도 인덱스 검토.

### 3.2 정규화 정책

**공통:**
- 공백 정규화: 연속 whitespace → 1개, BOM/zwj 제거
- 연속 빈 줄 `\n{3,}` → `\n\n` 으로 압축
- 한자 병기 `한글(漢字)` 유지 (전공/학칙 식별자)
- URL 정규화 (clrCd 등 추적 파라미터 제거 — 단, `mng_no`/`ntt_no`/`seq_no` 같은 식별 ID는 **보존**, 평가셋 expected_source_urls 매칭에 필요)

**HWP 추출 노이즈 (실측 기반, 2026-05-27 sprint1·2 스캔):**

| 패턴 | 등장 | 처리 |
|---|---:|---|
| `<표>` | 1,144 | **제거** (의미 없는 placeholder, hwp5txt가 표 영역만 표시) |
| `<그림>` | 11 | **제거** (그림 placeholder) |
| `<도형>`, `<수식>` | 0 | 패턴만 등록, 등장 시 제거 |
| `(개정 YYYY.M.D.)` | 825 | **보존** (학칙 조문 유효 시점, high-stakes 정확성에 중요) |
| `(신설 YYYY.M.D.)` | 716 | **보존** |
| `(삭제 YYYY.M.D.)` | 121 | **보존** (단 본문이 삭제 표시 단독인 조문은 청크 자체 제외) |
| 페이지 번호 라인 `\n - N - \n` | 0 | 패턴 등록 (PDF 출처에서 미래 등장 대비) |

**규칙:**
```python
# clean 단계 의사코드
text = re.sub(r'<(?:표|그림|도형|수식)>', '', text)
text = re.sub(r'\n\s*-\s*\d+\s*-\s*\n', '\n', text)
text = re.sub(r'\n{3,}', '\n\n', text)
text = re.sub(r'\s+', lambda m: ' ' if '\n' not in m.group() else m.group(), text)
# (개정/신설/삭제 ...) 는 보존
```

**보존되는 학칙 메타의 영향:** dense vector 임베딩에 약간의 노이즈 추가 — 그러나 "그럴듯한데 틀린 답"보다 "사실+시기"가 high-stakes 챗봇에 안전 ([[project-nlp-tp-design-principles]]). 필요시 Phase E에서 source_title/section_path로 재정렬해서 보완.

### 3.3 중복 제거

- **완전 중복**: text의 SHA1 동일하면 하나만 유지. 우선순위: source_type 등급 (T1 > T2 > T3 > T6) → freshness 신선도.
- **준중복**: cross_tag.jsonl는 의도된 multi-domain 태깅이므로 dedup 대상에서 제외. parent_post_id+chunk_index 가 cross_tag와 sprint{1,2}/chunks에 동시 존재할 수 있음 — `chunk_id` 기준으로 1차 dedup.

### 3.4 Sparse 도메인 처리

도메인 2 (학생활동, 5건) / 3 (식생활, 9건) / 8 (도서관, 7건) / 9 (캠퍼스, 7건) — 보강 없이 Phase C 통과.

**Phase E 단계 정책:**
- 평가셋 `is_fallback_expected=true` 인 문항은 retrieval recall 임계점 미달 시 정중 거절 응답.
- Retrieval top-k=8, 도메인 일치 청크가 0이면 "정보 없음" fallback.

## 4. 임베딩 모델 선정 (Phase C → E 전환 직전 결정)

후보:
- `BAAI/bge-m3` (다국어 dense, Colab Free OK)
- `intfloat/multilingual-e5-large` (한국어 강함, 2.2G)
- `jhgan/ko-sroberta-multitask` (한국어 특화, 가볍지만 도메인 일반화 약함)

Sprint 0~3에서 검증 안 한 부분 → Phase C 마지막 단계에서 top-3 후보 ablation (sample 100문항).

## 5. Phase C 진입 체크리스트 (✅ 2026-05-27 confirmed)

- [x] 출력 디렉토리 `data/phase_c/` 신설 — `data/sprint{1,2,3}/`은 read-only로 보존 (재실행 시 회귀 비교 가능)
- [x] 재청크 임계값: **상한 2,000자 / 하한 50자**로 진행
- [x] 학칙 HWP 분할: **조문 단위 우선 → 1,500자 sliding window fallback**
- [x] 알리미 dept_info: BM25에는 셀 단위 그대로, dense는 학과 단위 병합 (2개 인덱스)
- [x] Sparse 4 도메인 (2/3/8/9): Phase C는 통과만, Phase E fallback에서 처리
- [x] 임베딩 모델: Phase C 마지막에 3-way ablation 결정

## 6. 추정 작업량

| 단계 | 산출 | 추정 |
|---|---|---|
| 01_clean | 정제 jsonl + 중복 보고서 | 0.5일 |
| 02_rechunked | 재청크 jsonl + 분할 보고서 | 1일 |
| 03_enriched | 최종 청크 (5,000~6,000건 예상) | 0.5일 |
| 04_index | FAISS+BM25 인덱스 | 0.5일 (임베딩 모델 확정 후) |
| ablation | 3-way 임베딩 비교 | 0.5일 |

**예상 총 3일.** Phase D(평가셋 확장)와 병렬 가능.

관련 메모리: project-nlp-tp-sprint2, project-nlp-tp-almi-ubireport, project-nlp-tp-eval-d0
