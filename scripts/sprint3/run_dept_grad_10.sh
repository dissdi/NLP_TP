#!/usr/bin/env bash
# 학과 졸업요건 corpus 보강 — 10개 학과 풀세트 (로컬 실행 전용)
# 워크스페이스는 cnu.ac.kr 네트워크 차단 → 사용자 PC에서 직접 실행
#
# 사용:
#   bash scripts/sprint3/run_dept_grad_10.sh discover     # 후보 URL 발견
#   bash scripts/sprint3/run_dept_grad_10.sh crawl        # 후보 → 본문 크롤
#   bash scripts/sprint3/run_dept_grad_10.sh all          # 둘 다
set -e
cd "$(dirname "$0")/../.."

LIST="scripts/sprint2/dept_list_10.json"
OUT_DIR="data/sprint3/dept_grad_10"
CAND="$OUT_DIR/candidates.jsonl"
CHUNKS="$OUT_DIR/chunks_raw.jsonl"

mkdir -p "$OUT_DIR"

MODE="${1:-all}"

case "$MODE" in
  discover|all)
    echo "=== [1/2] discover — 10개 학과 메뉴 키워드 스캔 ==="
    python -m scripts.sprint2.dept_grad discover \
      --dept-list "$LIST" \
      --out "$CAND"
    echo ""
    echo "→ $CAND 결과 확인:"
    python3 -c "
import json
with open('$CAND', encoding='utf-8') as f:
    recs = [json.loads(l) for l in f if l.strip()]
ok = [r for r in recs if r['status'] in ('ok','ok_direct')]
miss = [r for r in recs if r['status'] == 'no_candidate']
print(f'  ok: {len(ok)}/{len(recs)}')
for r in miss:
    print(f'  ⚠ no_candidate: {r[\"dept_name\"]}  {r[\"home\"]}')
"
    [ "$MODE" = "discover" ] && exit 0
    ;;
esac

case "$MODE" in
  crawl|all)
    echo ""
    echo "=== [2/2] crawl — 후보 URL을 어댑터 A로 본문 추출 ==="
    python -m scripts.sprint2.dept_grad crawl \
      --candidates "$CAND" \
      --out "$CHUNKS" \
      --top-n 3
    echo ""
    echo "=== 학과별 청크 분포 ==="
    python3 -c "
import json
from collections import Counter
c = Counter()
sz = Counter()
with open('$CHUNKS', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        t = d.get('source_title','')
        dept = t.split(']')[0].lstrip('[') if ']' in t else 'UNKNOWN'
        c[dept] += 1
        sz[dept] += d.get('char_count', 0)
for k in sorted(c):
    print(f'  {k}: {c[k]} chunks, {sz[k]} chars')
print(f'  TOTAL: {sum(c.values())} chunks, {sum(sz.values())} chars')
"
    ;;
esac

echo ""
echo "✅ 완료. 다음 단계:"
echo "  - $CHUNKS 를 워크스페이스에 업로드 → Claude가 스키마 정규화·append·BM25 진행"
