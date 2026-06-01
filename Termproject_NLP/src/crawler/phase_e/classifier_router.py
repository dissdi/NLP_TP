"""Phase E classifier router — light integration with the chatbot.

Loads the 5-way question classifier (KLUE-RoBERTa-small) once at process start
and exposes `classify(query) -> (label, label_name, confidence)` to the pipeline.

This is meta-only: the pipeline currently does NOT use the label to filter
retrieval. The label is surfaced in the response metadata for UI/debug.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
MODEL_DIR = os.environ.get("CLS_MODEL_DIR", os.path.join(ROOT, "model"))
LABEL_NAMES = {0: "졸업요건", 1: "공지", 2: "학사일정", 3: "식단", 4: "셔틀"}

_lock = threading.Lock()
_state: dict = {"loaded": False, "model": None, "tokenizer": None, "max_len": 64, "device": None}


@dataclass
class ClassifyResult:
    label: int
    label_name: str
    confidence: float
    all_probs: list[float]


def _load_once() -> None:
    if _state["loaded"]:
        return
    with _lock:
        if _state["loaded"]:
            return
        import torch
        from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

        label_map_path = os.path.join(MODEL_DIR, "label_map.json")
        base_name = "klue/roberta-small"
        max_len = 64
        if os.path.exists(label_map_path):
            with open(label_map_path, "r", encoding="utf-8") as f:
                lm = json.load(f)
                base_name = lm.get("model_name", base_name)
                max_len = lm.get("max_len", max_len)

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        config = AutoConfig.from_pretrained(MODEL_DIR, num_labels=len(LABEL_NAMES))
        tok_dir = os.path.join(MODEL_DIR, "tokenizer")
        tok_src = tok_dir if os.path.isdir(tok_dir) else base_name
        tokenizer = AutoTokenizer.from_pretrained(tok_src)
        model = AutoModelForSequenceClassification.from_pretrained(base_name, config=config)
        state_path = os.path.join(MODEL_DIR, "model.bin")
        try:
            state = __import__("torch").load(state_path, map_location=device, weights_only=True)
        except TypeError:
            state = __import__("torch").load(state_path, map_location=device)
        model.load_state_dict(state)
        model.to(device).eval()

        _state.update({
            "loaded": True, "model": model, "tokenizer": tokenizer,
            "max_len": max_len, "device": device,
        })


def is_available() -> bool:
    return os.path.exists(os.path.join(MODEL_DIR, "model.bin"))


def classify(query: str) -> Optional[ClassifyResult]:
    """Return ClassifyResult or None if model unavailable / load failed."""
    if not is_available():
        return None
    try:
        _load_once()
    except Exception as e:
        print(f"[classifier_router] load failed: {e}")
        return None

    import torch
    import torch.nn.functional as F

    model = _state["model"]
    tokenizer = _state["tokenizer"]
    device = _state["device"]
    max_len = _state["max_len"]
    with torch.no_grad():
        enc = tokenizer(query, truncation=True, max_length=max_len,
                        padding=True, return_tensors="pt").to(device)
        out = model(**enc)
        probs = F.softmax(out.logits, dim=-1).squeeze(0).cpu().tolist()
    label = int(max(range(len(probs)), key=probs.__getitem__))
    return ClassifyResult(
        label=label,
        label_name=LABEL_NAMES[label],
        confidence=float(probs[label]),
        all_probs=[float(p) for p in probs],
    )


if __name__ == "__main__":
    import sys
    qs = sys.argv[1:] or [
        "졸업학점 몇 학점이야?",
        "오늘 학식 뭐야?",
        "2학기 수강신청 언제부터야?",
        "셔틀버스 시간표 알려줘",
        "백마장학금 신청 자격이 뭐예요?",
        "도서관 운영시간이 어떻게 되나요?",
    ]
    for q in qs:
        r = classify(q)
        if r is None:
            print(f"  N/A  | {q}")
        else:
            print(f"  {r.label} {r.label_name:>5}  conf={r.confidence:.3f}  | {q}")
