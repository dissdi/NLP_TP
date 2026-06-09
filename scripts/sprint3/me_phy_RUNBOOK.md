# me + physics 재크롤 RUNBOOK

기계공학부(me.cnu.ac.kr) + 물리학과(physics.cnu.ac.kr) corpus 보강 절차.

전제: 워크스페이스는 cnu.ac.kr 차단 → **랩실 서버 또는 dev PC에서 실행**.

---

## 1) discover + crawl (랩실 또는 dev PC, 네트워크 cnu 가능)

```bash
cd ~/NLP_TP   # 또는 C:\Users\iksdg\Documents\Claude\Projects\NLP_TP
bash scripts/sprint3/run_dept_grad_me_phy.sh all
```

산출:
- `data/sprint3/dept_grad_me_phy/candidates.jsonl`
- `data/sprint3/dept_grad_me_phy/chunks_raw.jsonl`

확인 포인트:
- `me.cnu.ac.kr` chunks ≥ 1, `physics.cnu.ac.kr` chunks ≥ 1
- "졸업학점" / "총 130학점" / 표(table) 본문이 포함된 chunk 가 있는지

**만약 chunks 0건** → dept_list_me_phy.json 의 direct_url 들이 전부 404.
  → 브라우저로 `me.cnu.ac.kr`, `physics.cnu.ac.kr` 학부 → 학사 → 졸업요건 메뉴 클릭해 실제 URL 확보 → dept_list_me_phy.json 의 `direct_url` 배열에 교체 → 재실행.

---

## 2) augment + corpus append (dev PC, 워크스페이스)

```bash
cd C:\Users\iksdg\Documents\Claude\Projects\NLP_TP
python -m scripts.sprint3.augment_dept_grad_me_phy --dry-run
# 분포 확인 후
python -m scripts.sprint3.augment_dept_grad_me_phy --no-bm25
```

산출 (덮어쓰기 + .bak 백업):
- `Termproject_NLP/assets/index/03_enriched/general/chunks.jsonl`
- `Termproject_NLP/assets/index/04_index/meta/chunks.jsonl`

확인 포인트:
- `me.cnu.ac.kr chunks: X -> Y` (Y > X 여야 함)
- `physics.cnu.ac.kr chunks: 0 -> N` (N ≥ 1)

---

## 3) BM25 재빌드 (dev PC면 그대로, 빠름)

옵션 A: augment 에서 `--no-bm25` 빼고 한 번에:
```bash
python -m scripts.sprint3.augment_dept_grad_me_phy
```

옵션 B: 따로 돌리고 싶을 때 — augment 의 `build_bm25(final_enr)` 가 재실행되도록 dry-run 결과 보고 결정. 보통 옵션 A 권장. ≈ 20초.

산출 (덮어쓰기 + .bak 백업):
- `Termproject_NLP/assets/index/04_index/bm25/general/bm25.pkl`
- `Termproject_NLP/assets/index/04_index/bm25/general/chunk_ids.json`
- `Termproject_NLP/assets/index/04_index/bm25/general/tokens.jsonl`

---

## 4) FAISS 재빌드 (랩실 GPU, ≈ 1분)

```bash
# 랩실 서버에서
cd ~/NLP_TP
python -m scripts.sprint3.build_faiss_assets
```

산출 (덮어쓰기):
- `Termproject_NLP/assets/index/04_index/faiss/general/index.faiss`
- 동반 메타파일

---

## 5) 검증 — 회수 + 회귀 (UI 또는 batch eval)

회수 쿼리 (반드시 PASS):
- `기계공학부 졸업요건` → 답에 `me.cnu.ac.kr` 출처 + "130학점"(또는 학과 실제 수치) 포함
- `물리학과 졸업요건` → 답에 `physics.cnu.ac.kr` 출처 + 학과 실제 학점 수치 포함
- `기계공학부 교육과정` → me 본문 인용
- `물리학과 교육과정` → physics 본문 인용

회귀 쿼리 (변화 없어야 함, 다른 8학과):
- `컴퓨터인공지능학부 졸업학점` → 130, computer.cnu.ac.kr
- `의예과 졸업요건` → 72, medicine.cnu.ac.kr
- `약학과 졸업요건` → pharm
- `간호학과 졸업요건` → nursing
- `전자공학과 졸업요건` → ee
- `응용화학공학과 졸업요건` → ceac
- `수학과 졸업요건` → math
- `정보통계학과 졸업요건` → stat

회귀 쿼리 (cross-cutting):
- 학식, 기숙사, 셔틀, 공지 — tool 라우팅 정상

GPU peak ≤ 12GB / OOM 0 확인.

---

## 6) 만약 me/physics 회수 실패 (corpus 들어왔는데 답 안 나옴)

원인 분류:
- **BM25 #1~#10 안에 학과 본문 없음** → BM25 토큰 누락 (`기계공학부`, `물리학과` 토큰화 확인)
- **dense top-k 에 들어왔으나 reranker 가 학칙으로 밀어냄** → `dept_rescue.py` 의 regex 에 me/physics 이미 포함되어 있는지 확인 ([[project-nlp-tp-dept-grad-followup]] 참조)
- **reranker 통과했으나 fallback** → `_dept_rescued=True` 마킹이 동작했는지 확인

BM25 trace:
```bash
python -m scripts.eval.bm25_trace --q "기계공학부 졸업요건" --topk 30
python -m scripts.eval.bm25_trace --q "물리학과 졸업요건" --topk 30
```

---

## 결론 — 한 줄 흐름

```
랩실: bash scripts/sprint3/run_dept_grad_me_phy.sh all
dev:  python -m scripts.sprint3.augment_dept_grad_me_phy --dry-run
dev:  python -m scripts.sprint3.augment_dept_grad_me_phy
랩실: python -m scripts.sprint3.build_faiss_assets
검증: UI 회수 4 + 회귀 8 + cross-cutting 4
```
