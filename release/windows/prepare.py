"""Install the locked wheels into this interpreter and exercise one CUDA stream."""
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "inworld"))


def precheck(destination, scratch_bytes=14_000_000_000, install_bytes=10_000_000_000):
    if Path(sys.prefix).resolve() != ROOT / "python":
        raise RuntimeError("The private Python runtime is required.")
    # During setup the wheels, staged engine, and installed copy can coexist.
    if ROOT.drive.casefold() == destination.drive.casefold():
        needed = [(ROOT, scratch_bytes + install_bytes)]
    else:
        needed = [(ROOT, scratch_bytes), (Path(destination.anchor), install_bytes)]
    for path, size in needed:
        if shutil.disk_usage(path).free < size:
            raise RuntimeError(f"Setup needs {size / 1e9:.1f} GB free on {path.drive}.")
    for name in ("msvcp140.dll", "vcruntime140_1.dll"):
        try:
            ctypes.WinDLL(name, winmode=0x800)  # LOAD_LIBRARY_SEARCH_SYSTEM32
        except OSError as exc:
            raise RuntimeError("Install Microsoft Visual C++ v14 Redistributable x64 and retry.") from exc
    driver = ctypes.WinDLL("nvcuda.dll", winmode=0x800)
    def call(name, *args):
        status = getattr(driver, name)(*args)
        if status:
            raise RuntimeError(f"NVIDIA driver {name} returned {status}. Update the NVIDIA display driver.")
    call("cuInit", 0)
    count, driver_version = ctypes.c_int(), ctypes.c_int()
    call("cuDriverGetVersion", ctypes.byref(driver_version))
    call("cuDeviceGetCount", ctypes.byref(count))
    print("CUDA driver API:", driver_version.value)
    for index in range(count.value):
        dev, major, minor = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
        call("cuDeviceGet", ctypes.byref(dev), index)
        call("cuDeviceGetAttribute", ctypes.byref(major), 75, dev)
        call("cuDeviceGetAttribute", ctypes.byref(minor), 76, dev)
        if major.value >= 8:
            print(f"Compatible CUDA device {index}: compute capability {major.value}.{minor.value}")
            return
    raise RuntimeError("A CUDA GPU with native BF16 (RTX 30 series or newer) is required.")


def install(downloads):
    assets = json.loads((ROOT / "assets.lock.json").read_text(encoding="utf-8"))
    model = assets["model"]
    checkpoint = downloads / model["filename"]
    with checkpoint.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != model["sha256"]:
            raise RuntimeError("Downloaded model checksum mismatch.")
    model_dir = ROOT / "inworld/models"
    model_dir.mkdir(exist_ok=True)
    shutil.copyfile(checkpoint, model_dir / checkpoint.name)
    reqs = ROOT / "requirements.lock"
    reqs.write_text("".join(f"{w['package']}=={w['version']} --hash=sha256:{w['sha256']}\n"
                             for w in assets["wheels"]), encoding="ascii")
    env = dict(os.environ, PIP_CONFIG_FILE=os.devnull)
    subprocess.run([sys.executable, "-I", "-B", "-m", "pip", "--isolated", "--disable-pip-version-check",
                    "install", "--no-index", "--no-deps", "--no-cache-dir", "--no-compile",
                    "--no-warn-script-location", "--require-hashes", "--find-links", str(downloads),
                    "-r", str(reqs)], check=True, stdout=sys.stdout, stderr=sys.stderr, env=env)


def smoke():
    import rtx_platform
    rtx_platform.configure(ROOT)
    import numpy as np
    import torch
    index = rtx_platform.select_device(torch)
    from engine_core import render
    from streaming_v2 import ComparisonModel
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    source = np.random.default_rng(4070).normal(0, .03, 12000).astype(np.float32)
    with torch.inference_mode():
        result = render(ComparisonModel(0, "ordered", 1), source, 1)
        torch.cuda.synchronize()
    if (result.shape != source.shape or not np.isfinite(result).all() or
            np.max(np.abs(result)) == 0 or np.array_equal(result, source)):
        raise RuntimeError("GPU audio verification failed.")
    print(json.dumps(dict(device=torch.cuda.get_device_name(index), torch=str(torch.__version__),
                          cuda=torch.version.cuda, samples=len(result),
                          output_peak=float(np.max(np.abs(result))), python=sys.executable)))


if __name__ == "__main__":
    action, location, log = sys.argv[1:]
    with open(log, "a", encoding="utf-8", buffering=1) as stream:
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            try:
                if action == "precheck":
                    precheck(Path(location))
                elif action == "install":
                    install(Path(location))
                    smoke()
                elif action == "diagnose":
                    smoke()
                else:
                    raise ValueError(action)
            except Exception:
                traceback.print_exc()
                sys.exit(1)
