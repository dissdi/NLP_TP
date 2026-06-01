# 충남대 학내 정보 RAG 챗봇 — Termproject 제출본

학생 대상 학내 정보 질의응답 시스템. 5-카테고리 분류기 + Hybrid RAG(BM25 + bge-m3 + bge-reranker-v2-m3-ko) + Qwen3-14B 4-bit.

## 디렉토리

```
Termproject_NLP/
├─ data/            평가 시 test_cls.json, test_chat.json 배치
├─ src/
│  ├─ classifier.ipynb       Task 1 학습 노트북 (Colab Free T4)
│  ├─ classifier/            학습/추론 패키지
│  │  ├─ train.py
│  │  ├─ predict.py
│  │  └─ build_dataset.py
│  ├─ chatbot_ui.py          Task 2 진입점 (UI + batch)
│  ├─ realtime_model.py      Task 3 진입점 (옵션 +30)
│  └─ crawler/               RAG 파이프라인 (phase_e/phase_f)
├─ model/
│  ├─ model.bin              분류기 가중치 (KLUE-RoBERTa-small, 272MB)
│  ├─ config.json
│  ├─ label_map.json
│  └─ tokenizer/
├─ assets/
│  └─ index/                 BM25 + (FAISS) RAG 인덱스
│     ├─ 03_enriched/        청크 jsonl
│     ├─ 04_index/           bm25/, faiss/, meta/
│     └─ reports/            dedup_aliases.jsonl 등
├─ outputs/                  cls_output.json, chat_output.json, realtime_output.json
├─ chatbot.sh                평가 진입점
├─ requirements.txt
└─ README.md
```

## 환경

- Python 3.10.12, torch 2.5.1
- GPU 권장(Colab Free T4 / 16GB VRAM 이상). CPU도 동작은 하지만 LLM 응답 매우 느림.
- 외부 다운로드: 첫 실행 시 HuggingFace에서 자동 캐싱
  - `BAAI/bge-m3` (~2GB)
  - `BAAI/bge-reranker-v2-m3-ko` (~600MB)
  - `Qwen/Qwen3-14B` 4-bit (~9GB)

## 설치

```bash
pip install -r requirements.txt
```

## 실행

### Task 1 — 분류기

```bash
# 학습은 src/classifier.ipynb 또는 src/classifier/train.py 참조
# 추론
bash chatbot.sh --classify \
    --input data/test_cls.json \
    --output outputs/cls_output.json
```

출력 스키마(가정, 평가 공지에 따라 조정):

```json
[{"id": "q001", "label": 0}, ...]
```

라벨: `0 졸업요건 / 1 공지 / 2 학사일정 / 3 식단 / 4 셔틀`.

### Task 2 — 챗봇

```bash
# (a) 인터랙티브 UI — 평가자가 직접 입력
bash chatbot.sh                       # http://localhost:7860

# (b) Batch — 평가셋 일괄 추론
bash chatbot.sh --batch \
    --input data/test_chat.json \
    --output outputs/chat_output.json
```

출력 스키마(`chat_output.json`):

```json
[{
  "id": "q001",
  "question": "...",
  "answer": "...",
  "predicted_category": 0,
  "predicted_category_name": "졸업요건",
  "classifier_confidence": 0.99,
  "sources": [{"chunk_id": "...", "title": "...", "source_url": "...", "rerank_score": 0.84}],
  "used_fallback": false,
  "used_tool": ""
}]
```

`--minimal` 플래그를 주면 `{id, answer}`만 출력.

### Task 3 — 실시간 반영

```bash
bash chatbot.sh --realtime \
    --input data/test_chat.json \
    --output outputs/realtime_output.json
```

PDF 평가축 3(실시간성)을 위해 카테고리 1·2·3·4 질의는 RAG 호출 전에 live tool을 강제 호출:
- **카테고리 1 공지 / 2 학사일정** → `notice.py`: 백마광장(`sub07_0701`) + 학사공지(`sub07_0702`) 게시판 상위 N건
- **카테고리 3 식단** → `cafeteria.py` + `dorm_cafeteria.py`
- **카테고리 4 셔틀** → `shuttle.py`: 정적 안내 페이지(`sub05_050403.html`) + 셔틀 관련 최근 공지

응답 JSON의 `realtime_meta`에 `{used, fetched_at, source}` 표기. `--no-refresh`로 디버그용 비활성.

## 데이터 / 모델 출처

- **학습 코퍼스**: 충남대 학칙·학사정보·공지·학과 홈페이지·학식·기숙사·셔틀 등 공개 페이지 자체 크롤링 + 위키피디아(CC BY-SA 4.0) 일부.
  - 알리미·인재개발원·보운관 등 5-카테고리 밖 도메인은 코퍼스에서 제외.
- **벤치마크**: 공식 평가 데이터셋(`test_cls.json`, `test_chat.json`)은 평가 시점에 배치. 자체 D-1 평가셋(170문제)은 분류기 학습에 합쳐 사용(test와 별개).
- **분류기 학습 데이터**: 템플릿 + slot fill + 격식/구어/동의어/줄임 paraphrase + D-1 합산 (외부 LLM API 호출 없음).
- **LLM**: `Qwen/Qwen3-14B` 4-bit, no fine-tuning. RAG context만 사용. (`enable_thinking=False`로 CoT 차단해 응답 속도 2-3배 단축)

## 주의

- `assets/index/04_index/faiss/`가 비어 있으면 BM25-only로 자동 폴백(코드는 `loader.py._load_faiss_safe` 참조). dense까지 사용하려면 `python scripts/build_faiss.py` 한 줄로 bge-m3 임베딩(1,151 청크) 생성 — GPU 약 30초, CPU 3~5분.
- 첫 실행은 모델 다운로드로 수 분 소요. 이후는 캐시 hit.
- `chatbot.sh`는 `RAG_INDEX_DIR`, `CLS_MODEL_DIR` 환경 변수로 경로 override 가능.

## 평가 진행 방법(권장)

```bash
# 1) 의존성
pip install -r requirements.txt

# 2) 분류기
bash chatbot.sh --classify

# 3) 챗봇 (둘 중 하나)
bash chatbot.sh                # UI 시연
bash chatbot.sh --batch        # 자동 채점

# 4) (옵션) 실시간
bash chatbot.sh --realtime
```

## 한계

- LLM은 양자화된 14B 모델로, 출력의 사실성은 retrieval context 품질에 직접 의존.
- 5-카테고리 외 질문은 분류기가 강제로 5개 중 하나로 매핑(범위 밖 라벨 없음). 챗봇 단의 retrieval-score fallback이 "정보 없음" 답변으로 안전판 역할.
- 답변 자연어 표현은 한국어 기본. 답변 길이는 모델 자율(평균 ~4문장).

## 라이선스 / 크레딧

- 자체 크롤링 데이터: 충남대학교 공개 페이지. 학내 사용/평가 용도 한정.
- 위키피디아 일부: CC BY-SA 4.0.
- 모델 가중치: 각 HF 리포지토리 라이선스(Apache 2.0 / 등) 준수.
