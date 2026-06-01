"""T2.2 분류기 학습 스크립트.

KLUE-RoBERTa-small fine-tune for 5-way classification:
  0: 졸업요건, 1: 공지, 2: 학사일정, 3: 식단, 4: 셔틀

Input:
  data/classifier/train.jsonl
  data/classifier/valid_internal.jsonl
Output:
  model/model.bin               (state_dict only, for Colab portability)
  model/config.json             (HF config copy)
  model/tokenizer/              (HF tokenizer dump)
  data/classifier/reports/train_log.md
  data/classifier/reports/valid_metrics.json

Colab Free 15GB GPU 호환 (max_seq_len=64, batch=32, fp32).

사용:
    python src/classifier/train.py [--epochs 6] [--lr 2e-5]
"""
from __future__ import annotations

import argparse
import json
import os
import random
from collections import Counter
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "data", "classifier")
MODEL_DIR = os.path.join(ROOT, "model")
REPORT_DIR = os.path.join(DATA_DIR, "reports")
DEFAULT_MODEL = "klue/roberta-small"

LABEL_NAMES = {0: "졸업요건", 1: "공지", 2: "학사일정", 3: "식단", 4: "셔틀"}
NUM_LABELS = 5


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_jsonl(path: str) -> list[dict[str, Any]]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


class ClsDataset(Dataset):
    def __init__(self, items, tokenizer, max_len: int = 64):
        self.items = items
        self.tok = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        x = self.items[idx]
        enc = self.tok(
            x["text"],
            truncation=True,
            max_length=self.max_len,
            padding="max_length",
            return_tensors="pt",
        )
        return {
            "input_ids": enc["input_ids"].squeeze(0),
            "attention_mask": enc["attention_mask"].squeeze(0),
            "label": torch.tensor(int(x["label"]), dtype=torch.long),
        }


def compute_class_weights(train_items: list[dict]) -> torch.Tensor:
    """Inverse-frequency class weights. Cap at 3x to avoid over-correcting."""
    counts = Counter(int(x["label"]) for x in train_items)
    total = sum(counts.values())
    weights = []
    for lbl in range(NUM_LABELS):
        c = counts.get(lbl, 1)
        w = total / (NUM_LABELS * c)
        weights.append(min(w, 3.0))
    return torch.tensor(weights, dtype=torch.float)


@torch.no_grad()
def evaluate(model, loader, device, class_names=None) -> dict:
    model.eval()
    all_pred, all_true = [], []
    total_loss = 0.0
    for batch in loader:
        ids = batch["input_ids"].to(device)
        mask = batch["attention_mask"].to(device)
        labels = batch["label"].to(device)
        out = model(input_ids=ids, attention_mask=mask)
        logits = out.logits
        loss = F.cross_entropy(logits, labels)
        total_loss += loss.item() * ids.size(0)
        pred = logits.argmax(-1).cpu().tolist()
        all_pred.extend(pred)
        all_true.extend(labels.cpu().tolist())
    # macro F1
    per_class = {}
    for lbl in range(NUM_LABELS):
        tp = sum(1 for p, t in zip(all_pred, all_true) if p == lbl and t == lbl)
        fp = sum(1 for p, t in zip(all_pred, all_true) if p == lbl and t != lbl)
        fn = sum(1 for p, t in zip(all_pred, all_true) if p != lbl and t == lbl)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        per_class[lbl] = {"precision": prec, "recall": rec, "f1": f1,
                          "support": sum(1 for t in all_true if t == lbl)}
    macro_f1 = sum(per_class[l]["f1"] for l in range(NUM_LABELS)) / NUM_LABELS
    acc = sum(1 for p, t in zip(all_pred, all_true) if p == t) / max(len(all_true), 1)
    # confusion matrix
    cm = [[0] * NUM_LABELS for _ in range(NUM_LABELS)]
    for p, t in zip(all_pred, all_true):
        cm[t][p] += 1
    return {
        "loss": total_loss / max(len(all_true), 1),
        "accuracy": acc,
        "macro_f1": macro_f1,
        "per_class": per_class,
        "confusion_matrix": cm,
    }


def train_loop(args):
    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[train] device={device}, model={args.model_name}")

    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(REPORT_DIR, exist_ok=True)

    train_items = load_jsonl(os.path.join(DATA_DIR, "train.jsonl"))
    valid_items = load_jsonl(os.path.join(DATA_DIR, "valid_internal.jsonl"))
    print(f"[train] train={len(train_items)} valid={len(valid_items)}")

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name, num_labels=NUM_LABELS,
    ).to(device)

    train_ds = ClsDataset(train_items, tokenizer, args.max_len)
    valid_ds = ClsDataset(valid_items, tokenizer, args.max_len)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=0)
    valid_loader = DataLoader(valid_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)

    class_w = compute_class_weights(train_items).to(device)
    print(f"[train] class weights: {class_w.cpu().tolist()}")

    no_decay = ["bias", "LayerNorm.weight"]
    grouped = [
        {"params": [p for n, p in model.named_parameters() if not any(nd in n for nd in no_decay)], "weight_decay": 0.01},
        {"params": [p for n, p in model.named_parameters() if any(nd in n for nd in no_decay)], "weight_decay": 0.0},
    ]
    optim = torch.optim.AdamW(grouped, lr=args.lr)
    total_steps = len(train_loader) * args.epochs
    sched = get_linear_schedule_with_warmup(optim, num_warmup_steps=int(0.1 * total_steps), num_training_steps=total_steps)

    best_f1 = -1.0
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss = 0.0
        for step, batch in enumerate(train_loader):
            ids = batch["input_ids"].to(device)
            mask = batch["attention_mask"].to(device)
            labels = batch["label"].to(device)
            out = model(input_ids=ids, attention_mask=mask)
            loss = F.cross_entropy(out.logits, labels, weight=class_w)
            optim.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optim.step()
            sched.step()
            epoch_loss += loss.item() * ids.size(0)
        train_loss = epoch_loss / len(train_ds)
        metrics = evaluate(model, valid_loader, device)
        print(f"[epoch {epoch}] train_loss={train_loss:.4f} valid_loss={metrics['loss']:.4f} "
              f"acc={metrics['accuracy']:.4f} macroF1={metrics['macro_f1']:.4f}")
        for lbl in range(NUM_LABELS):
            pc = metrics["per_class"][lbl]
            print(f"           label {lbl} ({LABEL_NAMES[lbl]}): P={pc['precision']:.3f} R={pc['recall']:.3f} F1={pc['f1']:.3f} (n={pc['support']})")
        history.append({"epoch": epoch, "train_loss": train_loss, **metrics})
        if metrics["macro_f1"] > best_f1:
            best_f1 = metrics["macro_f1"]
            # Save state_dict + tokenizer
            torch.save(model.state_dict(), os.path.join(MODEL_DIR, "model.bin"))
            model.config.save_pretrained(MODEL_DIR)
            tokenizer.save_pretrained(os.path.join(MODEL_DIR, "tokenizer"))
            with open(os.path.join(MODEL_DIR, "label_map.json"), "w", encoding="utf-8") as f:
                json.dump({"id2label": {str(k): v for k, v in LABEL_NAMES.items()},
                          "num_labels": NUM_LABELS, "model_name": args.model_name,
                          "max_len": args.max_len}, f, ensure_ascii=False, indent=2)
            print(f"[epoch {epoch}] saved best (macro_f1={best_f1:.4f})")

    # Final report
    final = history[-1]
    with open(os.path.join(REPORT_DIR, "valid_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2, default=lambda o: float(o) if isinstance(o, (np.floating,)) else o)

    md = ["# T2 분류기 학습 로그", "",
          f"- model: `{args.model_name}`",
          f"- epochs: {args.epochs}",
          f"- best macro F1 (valid_internal): **{best_f1:.4f}**",
          f"- last accuracy: {final['accuracy']:.4f}",
          ""]
    md.append("## 마지막 epoch per-class F1 (valid_internal)")
    md.append("| label | name | P | R | F1 | support |")
    md.append("|---:|---|---:|---:|---:|---:|")
    for lbl in range(NUM_LABELS):
        pc = final["per_class"][lbl]
        md.append(f"| {lbl} | {LABEL_NAMES[lbl]} | {pc['precision']:.3f} | {pc['recall']:.3f} | {pc['f1']:.3f} | {pc['support']} |")
    md.append("")
    md.append("## Confusion Matrix (rows=true, cols=pred)")
    md.append("| | " + " | ".join(LABEL_NAMES[c] for c in range(NUM_LABELS)) + " |")
    md.append("|---|" + "---|" * NUM_LABELS)
    for r in range(NUM_LABELS):
        row = " | ".join(str(final["confusion_matrix"][r][c]) for c in range(NUM_LABELS))
        md.append(f"| **{LABEL_NAMES[r]}** | {row} |")
    with open(os.path.join(REPORT_DIR, "train_log.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(f"[train] done. best macro F1 = {best_f1:.4f}")


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_name", default=DEFAULT_MODEL)
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--batch_size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max_len", type=int, default=64)
    ap.add_argument("--seed", type=int, default=2026)
    return ap.parse_args()


if __name__ == "__main__":
    train_loop(parse_args())
