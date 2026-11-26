"""Shared inference and streaming code for benchmarks and the Windows VST3 worker."""
import copy
import hashlib
import math
from pathlib import Path

import numpy as np
import torch
from inworld import voice_isolation

import cuda_scan

HERE = Path(__file__).resolve().parent
HOST_BLOCK = 128


def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


class InworldAdapter:
    def __init__(self,backend,ahead):
        self.backend=backend
        cuda_scan.set_backend(backend)
        self.vi=voice_isolation.VoiceIsolator(str(HERE/'models/denoiser_realtime.safetensors'),
            device='cuda',precision='auto',mode='streaming',lookahead_frames=ahead)
        self.key=f'inworld_{backend}_A{ahead}'
        self.buffer_ms=self.vi.latency_samples()/48
        self.description=dict(model='Inworld voice-isolator-v1-realtime',backend=backend,
            precision=self.vi.precision,lookahead_ms=ahead*10,algorithmic_buffer_ms=self.buffer_ms,
            parameters=sum(p.numel() for p in self.vi.model.parameters()),
            weights_sha256=digest(HERE/'models/denoiser_realtime.safetensors'))

    def reset(self):
        cuda_scan.set_backend(self.backend)
        self.session=self.vi.stream()

    def push(self,x):
        return self.session.push(x)

    def flush(self):
        return self.session.flush(as_numpy=True)


class Candidate:
    def __init__(self, lookahead, prepack, graphs=False):
        self.base = InworldAdapter("triton", lookahead)
        self.optimized_bands = None
        if prepack:
            self._prepare_weights()
        if graphs:
            self._capture_blocks()

    @torch.no_grad()
    def _prepare_weights(self):
        """Store exactly the casts used by BF16 matmuls of this frozen model."""
        model = self.base.vi.model
        assert self.base.vi.precision == "bf16"
        for name, mod in model.named_modules():
            if not (name.startswith("blocks.") or name == "denoise_decoder.condition"):
                continue
            if isinstance(mod, (torch.nn.Linear, torch.nn.Conv1d, torch.nn.MultiheadAttention)):
                for field, value in list(mod.named_parameters(recurse=False)):
                    # Mamba adds this particular bias in float32 after the matmul.
                    if field == "bias" and name.endswith(".dt_proj"):
                        continue
                    setattr(mod, field, torch.nn.Parameter(value.to(torch.bfloat16), requires_grad=False))
        bands = copy.copy(self.base.vi.stream()._bands)
        for field in ("encoder_weight", "encoder_bias", "head_weight", "head_bias",
                      "out_weight", "out_bias"):
            setattr(bands, field, getattr(bands, field).to(torch.bfloat16))
        self.optimized_bands = bands

    def _capture_blocks(self):
        # The attention history is variable-length and stays in the official
        # streaming path. Only pure calculations with fixed-shaped inputs
        # are replayed. Each model instance here is served by one worker.
        for block in self.base.vi.model.blocks:
            if hasattr(block, "band_transformer"):
                block.band_transformer.forward = fixed_graph(block.band_transformer.forward)
            else:
                time_mamba = block.time_mamba.forward_blocks
                time_mamba.forward = fixed_graph(time_mamba.forward)
                block.freq_mamba.forward = fixed_graph(block.freq_mamba.forward)

    def stream(self):
        session = self.base.vi.stream()
        if self.optimized_bands is not None:
            session._bands = self.optimized_bands
        return session


def fixed_graph(forward):
    """Return a single-worker CUDA replay of a pure band or carried-time block."""
    cache = {}
    side = torch.cuda.Stream()

    def replay(x, *args):
        # A time Mamba's very first step has no carried state.
        if args and args[0] is None:
            return forward(x, *args)
        tensors = (x, *args[0]) if args else (x,)
        key = tuple((t.shape, t.stride(), t.dtype) for t in tensors)
        if key not in cache:
            inputs = tuple(t.detach().clone() for t in tensors)
            arguments = (inputs[0], inputs[1:]) if args else inputs
            current = torch.cuda.current_stream()
            side.wait_stream(current)
            with torch.cuda.stream(side):
                for _ in range(3):
                    forward(*arguments)
            current.wait_stream(side)
            graph = torch.cuda.CUDAGraph()
            with torch.cuda.graph(graph, stream=side):
                value = forward(*arguments)
            cache[key] = inputs, graph, value
        inputs, graph, value = cache[key]
        for fixed, new in zip(inputs, tensors):
            fixed.copy_(new)
        graph.replay()
        if args:
            # The official stream owns the returned state, including across
            # lane changes and before another session reuses this graph.
            result, carried = value
            return result.clone(), tuple(t.clone() for t in carried)
        return value.clone()

    return replay


def input_ends(length, group, session):
    """Exclusive sample counts the worker may read, including any final tail."""
    if group == 0:  # Previous benchmark: exactly 960 new samples per push.
        yield from range(960, length, 960)
    else:
        target = session.n_fft // 2 + (group - 1) * session.hop
        while True:
            delivered = math.ceil(target / HOST_BLOCK) * HOST_BLOCK
            if delivered >= length:
                break
            yield delivered
            target += group * session.hop
    yield length


def render(model, source, group):
    session = model.stream()
    output = []
    start = 0
    for stop in input_ends(len(source), group, session):
        output.append(session.push(source[start:stop]))
        start = stop
    output.append(session.flush(as_numpy=True))
    result = np.concatenate(output)
    assert result.shape == source.shape and np.isfinite(result).all()
    return result
