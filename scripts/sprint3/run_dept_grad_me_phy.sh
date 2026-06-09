#!/usr/bin/env bash
# 기계공학부 + 물리학과 졸업요건/교육과정 corpus 재크롤 (정공법, 로컬 실행 전용)
# 워크스페이스는 cnu.ac.kr 네트워크 차단 → 사용자 PC / 랩실에서 직접 실행
#
# 사용:
#   bash scripts/sprint3/run_dept_grad_me_phy.sh discover     # 후보 URL 발견 (home 메뉴 스캔 + direct_url 통과)
#   bash scripts/sprint3/run_dept_grad_me_phy.sh crawl        # 후보 → 본문 크롤
#   bash scripts/sprint3/run_dept_grad_me_phy.sh all          # 둘 다
#
# 산출:
#   data/sprint3/dept_grad_me_phy/candidates.jsonl
#   data/sprint3/dept_grad_me_phy/chunks_raw.jsonl
set -e
cd "$(dirname "$0")/../.."

LIST="scripts/sprint2/dept_list_me_phy.json"
OUT_DIR="data/sprint3/dept_grad_me_phy"
CAND="$OUT_DIR/candidates.jsonl"
CHUNKS="$OUT_DIR/chunks_raw.jsonl"

mkdir -p "$OUT_DIR"

MODE="${1:-all}"

case "$MODE" in
  discover|all)
    echo "=== [1/2] discover — me + physics ==="
    python -m scripts.sprint2.dept_grad discover \
      --dept-list "$LIST" \
      --out "$CAND"
    echo ""
    echo "→ $CAND 결과 확인:"
    python3 -c "
import json
with open('$CAND', encoding='utf-8') as f:
    recs = [json.loads(l) for l in f if l.strip()]
for r in recs:
    print(f'  {r[\"dept_name\"]}  status={r[\"status\"]}  cand={len(r.get(\"candidates\",[]))}')
    for c in r.get('candidates', [])[:5]:
        print(f'    [{c[\"score\"]}] {c[\"text\"][:50]}  ->  {c[\"url\"]}')
"
    [ "$MODE" = "discover" ] && exit 0
    ;;
esac

case "$MODE" in
  crawl|all)
    echo ""
    echo "=== [2/2] crawl — direct_url + 발견 후보 본문 추출 ==="
    # top-n 을 충분히 키워 direct_url 9개 전부 시도. 실패한 URL 은 fail 로 기록.
    python -m scripts.sprint2.dept_grad crawl \
      --candidates "$CAND" \
      --out "$CHUNKS" \
      --top-n 10
    echo ""
    echo "=== 학과별 청크 분포 ==="
    python3 -c "
import json
from collections import Counter
c = Counter()
sz = Counter()
url_c = Counter()
with open('$CHUNKS', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        t = d.get('source_title','')
        dept = t.split(']')[0].lstrip('[') if ']' in t else 'UNKNOWN'
        c[dept] += 1
        sz[dept] += d.get('char_count', 0)
        url_c[d.get('source_url','')] += 1
for k in sorted(c):
    print(f'  {k}: {c[k]} chunks, {sz[k]} chars')
print(f'  TOTAL: {sum(c.values())} chunks, {sum(sz.values())} chars')
print()
print('=== source_url 분포 ===')
for u,n in url_c.most_common():
    print(f'  {n:>3}  {u}')
"
    ;;
esac

echo ""
echo "✅ 완료. 다음:"
echo "  1) $CHUNKS 확인 — 둘 다 chunk 0건이면 direct_url 들이 전부 404. dept_list_me_phy.json 의 direct_url 을 사이트맵에서 직접 찾아 교체."
echo "  2) chunks_raw.jsonl 을 augment 스크립트로 정규화 → corpus append → BM25 재빌드."
echo "     python -m scripts.sprint3.augment_dept_grad_me_phy"
