"""Local, single-worker 48 kHz mono trials for the fixed Inworld realtime checkpoint."""
import copy
import math
import weakref
from functools import partial

import torch
from inworld.voice_isolation import model as modeling, scan, streaming

from engine_core import Candidate
import streaming_scan


class FixedSection:
    """Capture a pure, fixed-shape section once per layout on a single worker."""

    def __init__(self, function):
        self.function = function
        self.cache = {}
        self.side = torch.cuda.Stream()

    def __call__(self, *values):
        layout = tuple((v.shape, v.dtype, v.stride()) for v in values)
        if layout not in self.cache:
            inputs = tuple(v.detach().clone() for v in values)
            current = torch.cuda.current_stream()
            self.side.wait_stream(current)
            with torch.cuda.stream(self.side):
                for _ in range(3):
                    self.function(*inputs)
            current.wait_stream(self.side)
            graph = torch.cuda.CUDAGraph()
            with torch.cuda.graph(graph, stream=self.side):
                result = self.function(*inputs)
            self.cache[layout] = inputs, graph, result
        inputs, graph, result = self.cache[layout]
        for target, source in zip(inputs, values):
            target.copy_(source)
        graph.replay()
        # The caller copies results that must survive another replay.
        return result


def attention_input(block, rows):
    attention = block.time_transformer.attn
    return attention.qkv(block.time_transformer.norm1(rows)).view(
        rows.shape[0], 1, 3, attention.num_heads, attention.head_dim)


def finish_attention(block, rows, attended, value, bands):
    time_block = block.time_transformer
    if time_block.attn.exclusive:
        attended = modeling.exclusive(attended, value.transpose(1, 2))
    rows = rows + time_block.attn.proj(attended.transpose(1, 2).reshape_as(rows))
    rows = rows + time_block.ffn(time_block.norm2(rows))
    return block.band_transformer(rows.reshape(-1, bands, rows.shape[-1])).unsqueeze(2)


class NetworkSections:
    """Run each stretch between two variable-length attention reads as one graph."""

    def __init__(self, model, bands):
        assert tuple(model.config.block_types) == ("transformer", "mamba", "transformer", "mamba",
                                                    "transformer", "mamba", "transformer")
        self.bands = len(model.edges)
        blocks = model.blocks
        self.encode = FixedSection(lambda x: bands.encode(model, x))
        self.decode = FixedSection(bands.decode)
        self.first = FixedSection(lambda rows: attention_input(blocks[0], rows))
        self.middle = [FixedSection(self._middle(blocks[i], blocks[i+1], blocks[i+2])) for i in (0, 2, 4)]
        self.last = FixedSection(lambda rows, out, val: finish_attention(blocks[6], rows, out, val, self.bands))

    def _middle(self, attention, mamba, following):
        def run(rows, attended, val, history, recurrence):
            features = finish_attention(attention, rows, attended, val, self.bands)
            state = streaming._MambaState()
            state.carried = history, recurrence
            features = streaming._scan(mamba, features, [state])
            rows = features.reshape(-1, 1, features.shape[-1])
            return rows, attention_input(following, rows), *state.carried
        return run

    def attach(self, session):
        # The official session keeps ownership of its KV caches, lane switches,
        # rotary positions, Mamba history, FFT, overlap-add and end padding.
        original = type(session)._backbone
        current = weakref.proxy(session)
        raw_bands = session._bands
        local = copy.copy(raw_bands)
        local.encode = lambda model, x: self.encode(x) if x.shape[-1] == 1 else raw_bands.encode(model, x)
        local.decode = lambda x: self.decode(x).clone() if x.shape[2] == 1 else raw_bands.decode(x)
        session._bands = local

        def backbone(features, lanes, film):
            if features.shape[2] != 1 or film is not None or lanes[0][1].carried is None:
                return original(current, features, lanes, film)
            if len(lanes) > 1:
                features = features.repeat(len(lanes), 1, 1, 1)
            rows = features.reshape(-1, 1, features.shape[-1])
            qkv = self.first(rows)
            for index in range(4):
                query, key, value = qkv.unbind(2)
                outputs = []
                for lane, q, k, v in zip(lanes, query.chunk(len(lanes)), key.chunk(len(lanes)), value.chunk(len(lanes))):
                    outputs.append(streaming._attend_lane(lane[2*index], current._attention, q, k, v))
                attended = outputs[0] if len(lanes) == 1 else torch.cat(outputs)
                if index == len(self.middle):
                    return self.last(rows, attended, value)
                states = [lane[2*index + 1] for lane in lanes]
                carried = states[0].carried
                if len(lanes) > 1:
                    carried = tuple(torch.cat(parts) for parts in zip(*(s.carried for s in states)))
                rows, qkv, conv, ssm = self.middle[index](rows, attended, value, *carried)
                # Static graph outputs must not alias live states of either lane
                # or another session when the next frame replays the graph.
                for state, h, r in zip(states, conv.clone().chunk(len(lanes)), ssm.clone().chunk(len(lanes))):
                    state.carried = h, r

        session._backbone = backbone


def shorten_synthesis(session, hops):
    """Asymmetric synthesis test. The trained analysis window and model stay fixed."""
    if session._limits is not None:
        raise ValueError("This test uses one mono stream without padded batch lengths.")
    advance = round(hops * session.hop)
    if not 0 < advance < session.n_fft // 2:
        raise ValueError("The advance must be shorter than half the analysis window.")
    # Remove the first 'advance' samples of every synthesis window and fade
    # it in over half a hop. Normalize by analysis * synthesis, including EOS.
    analysis = session.model.window.float()
    t = torch.arange(session.n_fft, device=analysis.device, dtype=torch.float32)
    taper = torch.sin(((t - advance) / (session.hop / 2)).clamp(0, 1) * (math.pi / 2)).square()
    synthesis = analysis * taper
    envelope = analysis * synthesis
    s = weakref.proxy(session)

    def synthesize(count):
        if count <= 0:
            return
        first = s._emitted
        spectra = torch.stack(s._spectra[first - s._pending_base:first - s._pending_base + count])
        raw = torch.stack([s._raw[min(i + s.lookahead, s._frames - 1) - s._pending_base]
                           for i in range(first, first + count)])
        frames = torch.fft.irfft(s.model.correction(raw, spectra), n=s.n_fft) * synthesis
        offset = first * s.hop - s._ola_base
        needed = offset + (count - 1) * s.hop + s.n_fft
        if needed > s._ola.shape[1]:
            grow = needed - s._ola.shape[1]
            s._ola = torch.nn.functional.pad(s._ola, (0, grow))
            s._envelope = torch.nn.functional.pad(s._envelope, (0, grow))
        for i in range(count):
            begin = offset + i * s.hop
            s._ola[:, begin:begin + s.n_fft] += frames[i]
            s._envelope[:, begin:begin + s.n_fft] += envelope
        s._emitted += count

    release = type(session)._release
    session._synthesize_ready = lambda: synthesize(s._frames - s.lookahead - s._emitted)
    session._synthesize = lambda: synthesize(1)
    session._release = lambda upto: release(s, upto + advance)


def reserve_attention(session):
    """Preallocate both window lanes and reuse the one-frame mask and rotary tables."""
    cache = session._attention
    capacity = cache.capacity
    # The pinned 600-frame windows and 200-frame crossfade fit in the
    # trained 1200-frame bound. Neither lane ever needs to discard a slot.
    if not session.window_frames or session.window_frames + session.crossfade_frames > cache.frames:
        raise ValueError("Preallocation needs the bounded dual-lane configuration.")
    dtype = session.autocast_dtype
    size = session.model.config.width // session.model.config.num_heads
    shape = (len(session.model.edges), session.model.config.num_heads, capacity, size)
    options = dict(device=cache.cos.device, dtype=dtype)
    for index, state in enumerate(session.states):
        if isinstance(state, streaming._AttentionState):
            state.keys, state.values = torch.empty(shape, **options), torch.empty(shape, **options)
            session._spare[index] = torch.empty(shape, **options), torch.empty(shape, **options)
    cos, sin = cache.cos.to(dtype), cache.sin.to(dtype)
    allowed = torch.ones(1, capacity, device=cache.cos.device, dtype=torch.bool)
    current = weakref.proxy(cache)

    def tables(start, stop, requested):
        if requested == dtype:
            return cos[start:stop], sin[start:stop]
        return streaming._AttentionCache.tables(current, start, stop, requested)

    def mask(frames, past):
        if frames == 1 and (not current.window or past < current.window):
            return allowed[:, :past + 1]
        return streaming._AttentionCache.mask(current, frames, past)

    cache.tables, cache.mask = tables, mask


class ComparisonModel(Candidate):
    def __init__(self, lookahead, variant, advance_hops=0):
        if variant not in ("previous", "sections", "combined", "reserved", "ordered"):
            raise ValueError(variant)
        super().__init__(lookahead, prepack=True, graphs=variant == "previous")
        self.advance_hops = advance_hops
        self.preallocate = variant in ("reserved", "ordered")
        self.scan_impl = scan.selective_scan
        if variant in ("combined", "ordered"):
            self.scan_impl = partial(streaming_scan.selective_scan, ordered=variant == "ordered")
        self.sections = None
        if variant != "previous":
            self.sections = NetworkSections(self.base.vi.model, self.optimized_bands)

    def stream(self):
        scan.selective_scan = self.scan_impl
        session = super().stream()
        if self.sections is not None:
            self.sections.attach(session)
        if self.preallocate:
            reserve_attention(session)
        if self.advance_hops:
            shorten_synthesis(session, self.advance_hops)
        return session
