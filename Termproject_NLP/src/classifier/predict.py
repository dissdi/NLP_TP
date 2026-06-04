"""T2.2 분류기 추론 스크립트.

Input:
  data/test_cls.json   (비공개 평가셋 — 우리는 같은 schema의 mock으로 테스트)
  model/model.bin
Output:
  outputs/cls_output.json

가이드라인의 정확한 schema 미공개. 다음 두 입력 형태를 모두 지원:
  Form A (list):  [{"id": "q001", "question": "..."}, ...]
  Form B (dict):  {"q001": "...", "q002": "..."}
  Form C (list with `text`): [{"id": "...", "text": "..."}]

Output schema (현재 가정, 평가셋 공개 시 조정):
  [{"id": "q001", "label": 0}, ...]
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

import torch
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_DIR = os.path.join(ROOT, "model")
DEFAULT_INPUT = os.path.join(ROOT, "data", "test_cls.json")
DEFAULT_OUTPUT = os.path.join(ROOT, "outputs", "cls_output.json")
NUM_LABELS = 5


def normalize_input(raw: Any) -> list[dict]:
    """Return list of {id, text} regardless of input form."""
    items = []
    if isinstance(raw, list):
        for i, x in enumerate(raw):
            if isinstance(x, dict):
                qid = x.get("id") or x.get("qa_id") or x.get("qid") or f"q{i:05d}"
                text = x.get("question") or x.get("text") or x.get("query") or ""
            elif isinstance(x, str):
                qid = f"q{i:05d}"
                text = x
            else:
                continue
            items.append({"id": str(qid), "text": text})
    elif isinstance(raw, dict):
        # Could be {"items": [...]} or {"q001": "..."}
        if "items" in raw and isinstance(raw["items"], list):
            return normalize_input(raw["items"])
        if "data" in raw and isinstance(raw["data"], list):
            return normalize_input(raw["data"])
        for qid, val in raw.items():
            if isinstance(val, dict):
                text = val.get("question") or val.get("text") or ""
            else:
                text = str(val)
            items.append({"id": str(qid), "text": text})
    return items


def load_model(model_dir: str, device: torch.device):
    """Load model from state_dict (model.bin) + config + tokenizer."""
    config = AutoConfig.from_pretrained(model_dir, num_labels=NUM_LABELS)
    # 저장된 config가 torchscript=True / return_dict=None이라
    # forward가 tuple을 반환해 .logits 접근이 깨진다. 강제 정상화.
    config.torchscript = False
    config.return_dict = True
    # base_model_name from label_map.json if present
    label_map_path = os.path.join(model_dir, "label_map.json")
    base_name = "klue/roberta-small"
    max_len = 64
    if os.path.exists(label_map_path):
        with open(label_map_path, "r", encoding="utf-8") as f:
            lm = json.load(f)
            base_name = lm.get("model_name", base_name)
            max_len = lm.get("max_len", max_len)
    # Try local tokenizer first, fall back to base
    tok_dir = os.path.join(model_dir, "tokenizer")
    tok_src = tok_dir if os.path.isdir(tok_dir) else base_name
    tokenizer = AutoTokenizer.from_pretrained(tok_src)
    model = AutoModelForSequenceClassification.from_pretrained(
        base_name, config=config,
    )
    state_path = os.path.join(model_dir, "model.bin")
    state = torch.load(state_path, map_location=device, weights_only=True) \
        if "weights_only" in torch.load.__code__.co_varnames \
        else torch.load(state_path, map_location=device)
    model.load_state_dict(state)
    model.to(device).eval()
    return model, tokenizer, max_len


@torch.no_grad()
def predict_batch(model, tokenizer, texts: list[str], device, max_len: int, batch_size: int = 64) -> list[int]:
    preds = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        enc = tokenizer(batch, truncation=True, max_length=max_len, padding=True, return_tensors="pt")
        ids = enc["input_ids"].to(device)
        mask = enc["attention_mask"].to(device)
        out = model(input_ids=ids, attention_mask=mask, return_dict=True)
        logits = out.logits if hasattr(out, "logits") else out[0]
        preds.extend(logits.argmax(-1).cpu().tolist())
    return preds


def run(input_path: str, output_path: str, model_dir: str) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[predict] device={device}")
    model, tokenizer, max_len = load_model(model_dir, device)

    with open(input_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    items = normalize_input(raw)
    print(f"[predict] {len(items)} items loaded from {input_path}")

    texts = [x["text"] for x in items]
    preds = predict_batch(model, tokenizer, texts, device, max_len)

    out = [{"id": items[i]["id"], "label": int(preds[i])} for i in range(len(items))]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[predict] wrote {len(out)} predictions -> {output_path}")


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    ap.add_argument("--model_dir", default=MODEL_DIR)
    return ap.parse_args()


if __name__ == "__main__":
    a = parse_args()
    run(a.input, a.output, a.model_dir)
