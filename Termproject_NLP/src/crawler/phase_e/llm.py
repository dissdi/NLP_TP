"""Local LLM wrapper.

Default: Qwen3-4B-Instruct FP16 (~8GB VRAM). Colab Free T4(15GB)에 안전히 들어가고
RAG 컨텍스트(rerank_top_k=4, ~2K 토큰) + KV 캐시까지 충분.
14B는 T4 한계에서 attention 버퍼가 OOM (q001 졸업학점 같은 RAG 풀패스에서 재현).
서버급 GPU(24GB+) 환경이면 아래를 "Qwen/Qwen3-14B"+ DEFAULT_4BIT=True로 되돌리면 됨.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

DEFAULT_LLM = "Qwen/Qwen3-4B-Instruct-2507"
DEFAULT_4BIT = False


@lru_cache(maxsize=2)
def _load(model_id: str, load_in_4bit: bool):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_id)
    kwargs = {"device_map": "auto"}
    # T4 15GB에서 긴 컨텍스트(>2K) 시 vanilla attention이 quadratic 버퍼를 잡아
    # 10GB+ 할당 시도 → OOM. SDPA는 메모리 효율 path. 생성 품질 동일.
    kwargs["attn_implementation"] = "sdpa"
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
) -> str:
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
    # Free KV cache + intermediate tensors so peak doesn't accumulate across calls
    del inputs, out, gen_tokens
    torch.cuda.empty_cache()
    return text.strip()
