#!/usr/bin/env bash
# Sprint 1 마스터 러너 (Linux/macOS/WSL).
#
# 사용자가 본인 환경에서 Sprint 1 전체를 한 번에 돌리고 싶을 때 사용.
# Day별 분리 실행이 권장(중간 점검 가능)이지만 이 스크립트는 자동화 옵션.
#
# 실행:
#   bash scripts/run_sprint1.sh             # 사전 inspect + day1~day5 + 첨부후처리 + 검증
#   bash scripts/run_sprint1.sh day1        # Day 1만
#   bash scripts/run_sprint1.sh verify-only # 검증만

set -euo pipefail
cd "$(dirname "$0")/.."

DAY="${1:-all}"

if [[ "$DAY" == "verify-only" ]]; then
  python -m scripts.sprint1_verify
  exit 0
fi

echo "=== 0. 사전 inspect ==="
python -m scripts.sprint1_pre_inspect || echo "(사전 inspect 경고 — Day 진행 가능)"

run_day() {
  local d="$1"
  echo ""
  echo "=== ${d} 시작 ==="
  python -m scripts.sprint1_runner "${d}"
  if [[ "${d}" == "day4" ]]; then
    echo ""
    echo "=== ${d} 첨부 후처리 (HWP/PDF) ==="
    python -m scripts.sprint1_process_attachments "${d}" \
      --hwp-prefer hwp5txt --max 30 || true
  fi
}

if [[ "$DAY" == "all" ]]; then
  for d in day1 day2 day3 day4 day5; do
    run_day "$d"
  done
else
  run_day "$DAY"
fi

echo ""
echo "=== 검증 ==="
python -m scripts.sprint1_verify
