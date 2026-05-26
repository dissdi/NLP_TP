#!/usr/bin/env bash
# Sprint 2 master runner (Linux/macOS).
set -e
cd "$(dirname "$0")/.."

DAY="${1:-all}"

case "$DAY" in
  verify)
    python -m scripts.sprint2_verify
    ;;
  inspect)
    python -m crawler.adapters.e_rule_hwp inspect "https://plus.cnu.ac.kr/_prog/rule/?site_dvs_cd=kr&menu_dvs_cd=0703"
    python -m scripts.sprint2_dstat spike-alimi
    python -m scripts.sprint2_dept_grad discover --dept-list scripts/sprint2_dept_list.json
    ;;
  dept-grad)
    python -m scripts.sprint2_dept_grad discover --dept-list scripts/sprint2_dept_list.json
    python -m scripts.sprint2_dept_grad crawl --candidates data/sprint2/day1/dept_grad_candidates.jsonl
    ;;
  alimi)
    python -m scripts.sprint2_dstat spike-alimi
    ;;
  attachments)
    for d in day1 day2 day3; do
      echo "=== $d attachments ==="
      python -m scripts.sprint2_process_attachments "$d" --hwp-prefer hwp5txt --max 80
    done
    python -m scripts.sprint2_verify
    ;;
  all)
    python -m crawler.adapters.e_rule_hwp inspect "https://plus.cnu.ac.kr/_prog/rule/?site_dvs_cd=kr&menu_dvs_cd=0703"
    python -m scripts.sprint2_dstat spike-alimi
    python -m scripts.sprint2_dept_grad discover --dept-list scripts/sprint2_dept_list.json
    for d in day1 day2 day3; do python -m scripts.sprint2_runner "$d"; done
    python -m scripts.sprint2_dept_grad crawl --candidates data/sprint2/day1/dept_grad_candidates.jsonl
    python -m scripts.sprint2_cross_tag
    python -m scripts.sprint2_faq_seed
    python -m scripts.sprint2_dorm_js
    for d in day1 day2 day3; do python -m scripts.sprint2_process_attachments "$d" --hwp-prefer hwp5txt --max 80; done
    python -m scripts.sprint2_verify
    ;;
  day1|day2|day3)
    python -m scripts.sprint2_runner "$DAY"
    case "$DAY" in
      day1) python -m scripts.sprint2_dept_grad crawl --candidates data/sprint2/day1/dept_grad_candidates.jsonl ;;
      day3) python -m scripts.sprint2_cross_tag; python -m scripts.sprint2_faq_seed; python -m scripts.sprint2_dorm_js ;;
    esac
    python -m scripts.sprint2_process_attachments "$DAY" --hwp-prefer hwp5txt --max 80
    python -m scripts.sprint2_verify
    ;;
  *)
    echo "Unknown: $DAY"; exit 2
    ;;
esac
