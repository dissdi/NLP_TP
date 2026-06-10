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
#
# 주의: set -e 안 씀. Windows bash 호환을 위해 인라인 -c 대신 _summarize_me_phy.py 사용.
cd "$(dirname "$0")/../.."

LIST="scripts/sprint2/dept_list_me_phy.json"
OUT_DIR="data/sprint3/dept_grad_me_phy"
CAND="$OUT_DIR/candidates.jsonl"
CHUNKS="$OUT_DIR/chunks_raw.jsonl"

# python 명령 자동 감지 (Windows = python, Linux = python3)
if command -v python >/dev/null 2>&1; then
  PY=python
else
  PY=python3
fi

mkdir -p "$OUT_DIR"

MODE="${1:-all}"

if [ "$MODE" = "discover" ] || [ "$MODE" = "all" ]; then
  echo "=== [1/2] discover — me + physics ==="
  $PY -m scripts.sprint2.dept_grad discover \
    --dept-list "$LIST" \
    --out "$CAND"
  rc=$?
  if [ $rc -ne 0 ]; then
    echo "⚠ discover 실패 (rc=$rc). 중단."
    exit $rc
  fi
  echo ""
  echo "→ $CAND 결과 확인:"
  $PY scripts/sprint3/_summarize_me_phy.py candidates "$CAND"
  if [ "$MODE" = "discover" ]; then
    exit 0
  fi
fi

if [ "$MODE" = "crawl" ] || [ "$MODE" = "all" ]; then
  echo ""
  echo "=== [2/2] crawl — direct_url + 발견 후보 본문 추출 ==="
  # top-n 을 충분히 키워 direct_url 9개 전부 시도. 실패한 URL 은 fail 로 기록.
  $PY -m scripts.sprint2.dept_grad crawl \
    --candidates "$CAND" \
    --out "$CHUNKS" \
    --top-n 10
  rc=$?
  if [ $rc -ne 0 ]; then
    echo "⚠ crawl 실패 (rc=$rc)."
    exit $rc
  fi
  echo ""
  $PY scripts/sprint3/_summarize_me_phy.py chunks "$CHUNKS"
fi

echo ""
echo "✅ 완료. 다음:"
echo "  1) $CHUNKS 확인 — 둘 다 chunk 0건이면 direct_url 들이 전부 404. dept_list_me_phy.json 의 direct_url 을 사이트맵에서 직접 찾아 교체."
echo "  2) chunks_raw.jsonl 을 augment 스크립트로 정규화 → corpus append → BM25 재빌드."
echo "     python -m scripts.sprint3.augment_dept_grad_me_phy --dry-run"
echo "     python -m scripts.sprint3.augment_dept_grad_me_phy"
