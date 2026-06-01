#!/usr/bin/env bash
# Termproject 평가자 진입점.
#
# 모드:
#   bash chatbot.sh                # 인터랙티브 Gradio UI (기본)
#   bash chatbot.sh --batch        # data/test_chat.json → outputs/chat_output.json
#   bash chatbot.sh --realtime     # Task 3 optional: outputs/realtime_output.json
#   bash chatbot.sh --classify     # Task 1 추론: data/test_cls.json → outputs/cls_output.json
#
# 환경:
#   Python 3.10.12 / torch 2.5.1 가정. requirements.txt 참조.
#   GPU 권장(Colab Free T4 이상). bge-m3 + Qwen3-14B 4-bit이 HF에서 자동 다운로드됨.
#   FAISS 인덱스가 없으면 BM25-only 모드로 자동 폴백 (recall ~88.5%).
#   FAISS 빌드: python scripts/build_faiss.py (bge-m3 다운로드 ~2.3GB, GPU ~30s).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# Index dir override (assets/index에 BM25 + (옵션) FAISS).
export RAG_INDEX_DIR="${RAG_INDEX_DIR:-$HERE/assets/index/04_index}"
export RAG_REPORT_DIR="${RAG_REPORT_DIR:-$HERE/assets/index/reports}"
export CLS_MODEL_DIR="${CLS_MODEL_DIR:-$HERE/model}"
export PYTHONPATH="$HERE/src:${PYTHONPATH:-}"

MODE="${1:-ui}"

case "$MODE" in
  --batch|batch)
    shift || true
    python -m chatbot_ui --batch "$@"
    ;;
  --realtime|realtime)
    shift || true
    python -m realtime_model "$@"
    ;;
  --classify|classify)
    shift || true
    python -m classifier.predict "$@"
    ;;
  ui|--ui|"")
    python -m chatbot_ui "$@"
    ;;
  *)
    # default: pass through to chatbot_ui (UI mode + flags)
    python -m chatbot_ui "$@"
    ;;
esac
