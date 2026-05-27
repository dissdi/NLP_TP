# Phase C — 04_index FAISS dense 빌드 실행 가이드

작성: 2026-05-27
대상: 연구실 서버 또는 로컬 conda nlp-tp env

## 0. 사전 조건

- 입력 청크 (이미 sandbox에서 빌드됨): `data/phase_c/03_enriched/{general,almi_dept}/chunks.jsonl`
- 모델: `BAAI/bge-m3` (default, 약 2.3GB)
- 디스크: 모델+인덱스 약 3GB 여유

## 1. 환경 준비 (연구실 서버 / 로컬 둘 다 동일)

```bash
# repo clone 또는 sync
cd /path/to/NLP_TP

# conda env 갱신 (Phase C 의존성 반영)
conda env update -n nlp-tp -f environment.yml
conda activate nlp-tp

# GPU 사용 시 (서버) — PyTorch CUDA 빌드
# (CPU도 가능, 1,380 청크면 수 분 내 끝남)
conda install -c pytorch -c nvidia pytorch pytorch-cuda=12.1
# 또는 서버 환경에 맞는 cuda 버전
```

## 2. 빌드 실행

```bash
# default: BAAI/bge-m3
python -m crawler.phase_c.index_faiss

# 다른 모델로 빌드 (ablation 용)
python -m crawler.phase_c.index_faiss intfloat/multilingual-e5-large
python -m crawler.phase_c.index_faiss jhgan/ko-sroberta-multitask
```

빌드 시간 (참고):
- bge-m3 + CPU only: 약 3~8분 (1,380 청크)
- bge-m3 + GPU: 30초 이내
- 첫 실행 시 모델 다운로드 시간 별도 (bge-m3 ≈ 2.3GB)

## 3. 산출물

```
data/phase_c/04_index/faiss/bge-m3/
  general/
    index.faiss         ← FAISS IndexFlatIP (L2-normalized, cosine sim)
    chunk_ids.json      ← row index → chunk_id 매핑
    embeddings.npy      ← (1279, dim) float32, 재빌드용
  almi_dept/
    index.faiss
    chunk_ids.json
    embeddings.npy
  build_meta.json       ← 모델/시간/통계
data/phase_c/reports/index_faiss_report.md
```

## 4. 검증 (빌드 후)

```python
import faiss, json, numpy as np
from sentence_transformers import SentenceTransformer

# load
idx = faiss.read_index("data/phase_c/04_index/faiss/bge-m3/general/index.faiss")
cids = json.load(open("data/phase_c/04_index/faiss/bge-m3/general/chunk_ids.json"))
meta = {json.loads(l)["chunk_id"]: json.loads(l)
        for l in open("data/phase_c/04_index/meta/chunks.jsonl")}

# encode query (bge-m3는 prefix 불필요)
model = SentenceTransformer("BAAI/bge-m3")
q_emb = model.encode(["기숙사 입소 시기"], normalize_embeddings=True).astype("float32")

# search top-5
D, I = idx.search(q_emb, 5)
for rank, (s, i) in enumerate(zip(D[0], I[0]), 1):
    cid = cids[i]
    m = meta[cid]
    print(f"{rank}. {s:.3f}  dom={m['domains']}  {m['source_title'][:60]}")
```

## 5. 산출물 회수 (서버 → 로컬)

```bash
# 서버에서 빌드 후 압축
cd /path/to/NLP_TP
tar czf phase_c_faiss.tar.gz data/phase_c/04_index/faiss/

# 로컬 (Windows)에서
scp user@server:/path/to/NLP_TP/phase_c_faiss.tar.gz .
# 압축 풀어서 data/phase_c/04_index/faiss/ 에 배치
```

## 6. ablation (3-way 임베딩 비교) — Phase C 마지막 단계

`phase_c_plan.md §4` 정책대로 3개 모델 모두 빌드 후 평가셋(D-1 170문항)으로 retrieval 성능 비교. 빌드 단계만 3번 반복하면 되고, ablation 비교 코드는 Phase E 진입 직전 별도 task로.

## 알려진 주의사항

- **Windows + conda + sentence-transformers**: 모델 다운로드 캐시 위치가 `%USERPROFILE%\.cache\huggingface\hub`. 디스크 부족 시 `HF_HOME` 환경변수로 위치 변경
- **bge-m3 GPU 메모리**: 약 2GB VRAM. Colab T4 (15GB)에서도 여유롭게 동작
- **passage prefix**: bge-m3는 query/passage 동일. e5는 `passage: ` / `query: ` 구분 (index_faiss.py의 `MODEL_PASSAGE_PREFIX` 자동 적용)
- **재현성**: `embeddings.npy`가 남아있으면 FAISS 인덱스 재빌드 시 모델 재인코딩 없이 즉시 (1초 내)

관련:
- 코드: `crawler/phase_c/index_faiss.py`
- 입력: `crawler/phase_c/enrich.py` (03_enriched 빌드)
- BM25 트랙: `crawler/phase_c/index_bm25.py` (이미 빌드 완료)
