"""Local LLM wrapper.

Default: Qwen/Qwen2.5-7B-Instruct (fp16, ~15GB VRAM, Apache 2.0, strong Korean).
For lower VRAM, pass model_id="Qwen/Qwen2.5-3B-Instruct" or enable load_in_4bit=True.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional


DEFAULT_LLM = "Qwen/Qwen2.5-7B-Instruct"


@lru_cache(maxsize=2)
def _load(model_id: str, load_in_4bit: bool = False):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_id)
    kwargs = {"torch_dtype": torch.float16, "device_map": "auto"}
    if load_in_4bit:
        from transformers import BitsAndBytesConfig
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16
        )
        kwargs.pop("torch_dtype", None)
    model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    model.eval()
    return tok, model


def chat(
    user_msg: str,
    system_msg: str = "",
    model_id: str = DEFAULT_LLM,
    load_in_4bit: bool = False,
    max_new_tokens: int = 256,
    temperature: float = 0.0,
) -> str:
    """Single-turn chat. Greedy by default (temperature=0)."""
    import torch
    tok, model = _load(model_id, load_in_4bit=load_in_4bit)
    messages = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg})
    messages.append({"role": "user", "content": user_msg})
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=temperature > 0,
            temperature=max(temperature, 1e-5),
            pad_token_id=tok.eos_token_id,
        )
    # decode only the newly generated tokens
    gen = out[0][inputs["input_ids"].shape[1]:]
    text = tok.decode(gen, skip_special_tokens=True)
    return text.strip()
