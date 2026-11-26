"""A one-frame dispatch for the validated Inworld FP32 selective scan."""
import torch
import triton
import triton.language as tl

import cuda_scan


@triton.jit
def _add_halves(x, rows: tl.constexpr, half: tl.constexpr):
    lo, hi = tl.split(tl.permute(tl.reshape(x, (rows, 2, half)), (0, 2, 1)))
    return lo + hi


@triton.jit
def _one_frame(U, DT, A, B, C, D, Z, STATE, OUT, LAST,
               SU0: tl.constexpr, SU2: tl.constexpr, SD0: tl.constexpr, SD2: tl.constexpr,
               SB0: tl.constexpr, SB2: tl.constexpr, SC0: tl.constexpr, SC2: tl.constexpr,
               SZ0: tl.constexpr, SZ2: tl.constexpr, SH0: tl.constexpr, SH1: tl.constexpr,
               DIM: tl.constexpr, N: tl.constexpr, CHANNELS: tl.constexpr,
               GATED: tl.constexpr, CARRIED: tl.constexpr, ORDERED: tl.constexpr):
    channels = tl.program_id(0) * CHANNELS + tl.arange(0, CHANNELS)
    row = tl.program_id(1)
    n = tl.arange(0, N)
    active = channels < DIM
    u = tl.load(U + row * SU0 + channels * SU2, active, 0).to(tl.float32)
    dt = tl.load(DT + row * SD0 + channels * SD2, active, 0).to(tl.float32)
    b = tl.load(B + row * SB0 + n * SB2).to(tl.float32)
    c = tl.load(C + row * SC0 + n * SC2).to(tl.float32)
    updated = (dt * u)[:, None] * b[None, :]
    if CARRIED:
        old = tl.load(STATE + row * SH0 + channels[:, None] * SH1 + n[None, :],
                      active[:, None], 0).to(tl.float32)
        a = tl.load(A + channels[:, None] * N + n[None, :], active[:, None], 0)
        updated = updated + tl.exp(dt[:, None] * a) * old
    skip = tl.load(D + channels, active, 0).to(tl.float32)
    products = updated * c[None, :]
    if ORDERED:
        # The previous one-channel CUDA kernel reduces the 16 coordinates
        # by shuffle distances 8, 4, 2, 1. Preserve its addition order
        # explicitly even when a CTA processes several channels at once.
        sums8 = _add_halves(products, CHANNELS, 8)
        sums4 = _add_halves(sums8, CHANNELS, 4)
        sums2 = _add_halves(sums4, CHANNELS, 2)
        left, right = tl.split(sums2)
        reduced = left + right
    else:
        reduced = tl.sum(products, axis=1)
    out = reduced + u * skip
    if GATED:
        z = tl.load(Z + row * SZ0 + channels * SZ2, active, 0).to(tl.float32)
        out = out * z / (1 + tl.exp(-z))
    block = row * DIM + channels
    tl.store(OUT + block, out, active)
    tl.store(LAST + block[:, None] * N + n[None, :], updated, active[:, None])


def selective_scan(u, delta, a, b, c, d, z=None, state=None, *, ordered=False):
    # Longer frequency sequences still use the previous parallel-prefix kernel.
    if (u.shape[1] != 1 or a.shape[-1] != 16 or not a.is_contiguous()
            or not d.is_contiguous() or (state is not None and state.stride(-1) != 1)):
        return cuda_scan.selective_scan(u, delta, a, b, c, d, z, state)
    rows, _, dim = u.shape
    out = torch.empty((rows, 1, dim), device=u.device, dtype=torch.float32)
    last = torch.empty((rows, dim, 16), device=u.device, dtype=torch.float32)
    gate = u if z is None else z
    carried = last if state is None else state
    width = 32
    _one_frame[(triton.cdiv(dim, width), rows)](
        u, delta, a, b, c, d, gate, carried, out, last, u.stride(0), u.stride(2),
        delta.stride(0), delta.stride(2), b.stride(0), b.stride(2), c.stride(0), c.stride(2),
        gate.stride(0), gate.stride(2), carried.stride(0), carried.stride(1),
        dim, 16, width, z is not None, state is not None, ordered, num_warps=4, enable_fp_fusion=False)
    return out, last
