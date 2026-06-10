"""Local LLM wrapper.

Default: Qwen/Qwen2.5-14B-Instruct in 4-bit NF4 (~8GB VRAM, Colab Free OK).
For pure-speed alt: DEFAULT_LLM = Qwen/Qwen3-4B-Instruct-2507, DEFAULT_4BIT=False.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

DEFAULT_LLM = "Qwen/Qwen3-14B"
DEFAULT_4BIT = True


@lru_cache(maxsize=2)
def _load(model_id: str, load_in_4bit: bool):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_id)
    kwargs = {"device_map": "auto"}
    if load_in_4bit:
        from transformers import BitsAndBytesConfig
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
    else:
        kwargs["torch_dtype"] = torch.float16
    model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    model.eval()
    return tok, model


def chat(
    user_msg: str,
    system_msg: str = "",
    model_id: str = DEFAULT_LLM,
    load_in_4bit: bool = DEFAULT_4BIT,
    max_new_tokens: int = 256,
    temperature: float = 0.0,
    return_meta: bool = False,
):
    """Generate a chat response.

    If return_meta=False (default, backward-compatible): returns the text string.
    If return_meta=True: returns (text, eos_reached: bool) — eos_reached is False
    when generation hit max_new_tokens without emitting eos_token (i.e. truncated).
    """
    import torch
    tok, model = _load(model_id, load_in_4bit)
    messages = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg})
    messages.append({"role": "user", "content": user_msg})
    template_kwargs: dict = {"tokenize": False, "add_generation_prompt": True}
    if "Qwen3" in model_id:
        template_kwargs["enable_thinking"] = False  # disable CoT; saves 2-3x latency
    prompt = tok.apply_chat_template(messages, **template_kwargs)
    inputs = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=temperature > 0,
            temperature=max(temperature, 1e-5),
            pad_token_id=tok.eos_token_id,
        )
    gen_tokens = out[0][inputs["input_ids"].shape[1]:]
    text = tok.decode(gen_tokens, skip_special_tokens=True)
    # EOS-reached check: last generated token is any registered stop token.
    # Qwen3 has multiple EOS ids (<|im_end|>=151645, <|endoftext|>=151643),
    # so we collect every candidate from tokenizer + model config + generation
    # config. Length-cap stops (max_new_tokens) leave a non-EOS final token.
    eos_ids: set[int] = set()

    def _collect(v):
        if v is None:
            return
        if isinstance(v, int):
            eos_ids.add(v)
        else:
            try:
                for x in v:
                    if isinstance(x, int):
                        eos_ids.add(x)
            except TypeError:
                pass

    _collect(getattr(tok, "eos_token_id", None))
    _collect(getattr(model.config, "eos_token_id", None))
    gen_cfg = getattr(model, "generation_config", None)
    if gen_cfg is not None:
        _collect(getattr(gen_cfg, "eos_token_id", None))
    last_id = int(gen_tokens[-1].item()) if gen_tokens.numel() > 0 else -1
    eos_reached = last_id in eos_ids
    # Free KV cache + intermediate tensors so peak doesn't accumulate across calls
    del inputs, out, gen_tokens
    torch.cuda.empty_cache()
    text = text.strip()
    if return_meta:
        return text, eos_reached
    return text
