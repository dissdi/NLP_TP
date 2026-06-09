"""GPU 메모리 시뮬레이션·측정 가드.

Colab Free T4(15GB) 환경을 서버 GPU에서 모사하기 위한 헬퍼.

환경변수:
  GPU_MEM_LIMIT_GB     # 예: "15" — torch caching allocator 한계를 15GB로 강제
                       #   (이 fraction 초과 할당 시 CUDA OOM 발생)
  GPU_MEM_LOG=1        # 1이면 매 측정마다 peak/현재 사용량을 stderr에 출력

사용 (app.py 부팅 훅 또는 명시 호출):
    from crawler.phase_e.gpu_guard import apply_limit, log_peak
    apply_limit()                          # 환경변수 보고 한계 설정
    ... 모델 로드/추론 ...
    log_peak("after warmup")
"""
from __future__ import annotations

import os
import sys
from typing import Optional


def _gb(bytes_: int) -> float:
    return bytes_ / (1024 ** 3)


def apply_limit(default_gb: Optional[float] = None) -> Optional[float]:
    """`GPU_MEM_LIMIT_GB` 환경변수 또는 인자 값으로 caching allocator fraction 제한.

    Returns:
        실제 적용된 한계 (GB), 적용 안되면 None.
    """
    limit_env = os.environ.get("GPU_MEM_LIMIT_GB")
    limit = float(limit_env) if limit_env else default_gb
    if not limit:
        return None

    try:
        import torch
    except ImportError:
        print("[gpu-guard] torch unavailable — skip", file=sys.stderr, flush=True)
        return None

    if not torch.cuda.is_available():
        print("[gpu-guard] CUDA unavailable — skip", file=sys.stderr, flush=True)
        return None

    device = 0  # CUDA_VISIBLE_DEVICES 적용 후 인덱스
    props = torch.cuda.get_device_properties(device)
    total_gb = _gb(props.total_memory)
    if limit >= total_gb:
        print(
            f"[gpu-guard] requested {limit:.1f}GB ≥ device total {total_gb:.1f}GB "
            f"on {props.name} — 한계 적용 안함",
            file=sys.stderr, flush=True,
        )
        return None

    fraction = limit / total_gb
    torch.cuda.set_per_process_memory_fraction(fraction, device)
    print(
        f"[gpu-guard] {props.name} ({total_gb:.1f}GB) → 한계 {limit:.1f}GB "
        f"(fraction={fraction:.3f}). 초과 할당 시 CUDA OOM 발생.",
        file=sys.stderr, flush=True,
    )
    return limit


def log_peak(tag: str = "") -> dict:
    """현재/peak 메모리 (allocated, reserved) GB로 stderr 출력 + dict 반환.

    `GPU_MEM_LOG=0` 이면 출력 생략 (반환은 그대로).
    """
    out = {"tag": tag, "ok": False}
    try:
        import torch
    except ImportError:
        return out
    if not torch.cuda.is_available():
        return out
    device = 0
    alloc = _gb(torch.cuda.memory_allocated(device))
    peak = _gb(torch.cuda.max_memory_allocated(device))
    reserved = _gb(torch.cuda.memory_reserved(device))
    peak_reserved = _gb(torch.cuda.max_memory_reserved(device))
    out.update({
        "ok": True,
        "alloc_gb": round(alloc, 3),
        "peak_alloc_gb": round(peak, 3),
        "reserved_gb": round(reserved, 3),
        "peak_reserved_gb": round(peak_reserved, 3),
    })
    if os.environ.get("GPU_MEM_LOG", "1") != "0":
        tag_s = f" [{tag}]" if tag else ""
        print(
            f"[gpu-mem]{tag_s} alloc={alloc:.2f}GB (peak {peak:.2f}GB)  "
            f"reserved={reserved:.2f}GB (peak {peak_reserved:.2f}GB)",
            file=sys.stderr, flush=True,
        )
    return out


def reset_peak() -> None:
    """다음 측정 구간을 위해 peak counter 리셋."""
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats(0)
    except Exception:
        pass
