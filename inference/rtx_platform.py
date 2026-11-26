"""Private Windows worker environment, applied before torch or Triton imports."""
import os
from pathlib import Path


def configure(root):
    triton = root / "python/Lib/site-packages/triton"
    os.environ.update({
        "CC": str(triton / "runtime/tcc/tcc.exe"),
        "CUDA_PATH": str(triton / "backends/nvidia"),
        "TRITON_CACHE_DIR": str(root / "cache/triton"),
        "TORCHINDUCTOR_CACHE_DIR": str(root / "cache/torchinductor"),
        "CUDA_CACHE_PATH": str(root / "cache/nvidia"),
        "HF_HUB_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
    })
    # Let the wheel pick ptxas or its Blackwell variant for the current GPU.
    for name in ("TRITON_PTXAS_PATH", "TRITON_PTXAS_BLACKWELL_PATH", "TRITON_LIBCUDA_PATH"):
        os.environ.pop(name, None)
    Path(os.environ["CUDA_CACHE_PATH"]).mkdir(parents=True, exist_ok=True)


def select_device(torch):
    for index in range(torch.cuda.device_count()):
        if torch.cuda.get_device_capability(index)[0] < 8:
            continue
        with torch.cuda.device(index):
            supported = torch.cuda.is_bf16_supported(including_emulation=False)
        if supported:
            torch.cuda.set_device(index)
            return index
    raise RuntimeError("No visible CUDA GPU supports native BF16. This release targets RTX 30-series or newer.")
