"""Virgo SLM decoder-only Transformer.

A LLaMA-family architecture (pre-norm, RMSNorm, RoPE, grouped-query
attention, SwiGLU MLP, tied embeddings) chosen because every piece of it is
well-understood, CPU-friendly at small scale, quantization-friendly (no
architectural elements — e.g. learned absolute position embeddings — that
resist INT8/INT4 quantization well), and scales cleanly from ~100M to 1B+
parameters by changing only the numbers in a :class:`VirgoSLMConfig`.

Design choices directly serving later phases:

* KV cache is threaded through ``forward`` as an explicit, inspectable
  argument/return value (not framework-hidden) so Phase 13 (inference) and
  Phase 16 (C++ runtime) have an unambiguous contract to reimplement.
* Attention accepts an explicit boolean/additive mask rather than assuming
  causal-only, so instruction tuning (Phase 8, padded batches) and
  tool-calling fine-tuning (Phase 9) don't require touching this file.
* Precision (fp32/fp16/bf16) is a config value, not hardcoded, so
  mixed-precision training (Phase 4) and quantization (Phase 15) build on
  top rather than around this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import torch
import torch.nn.functional as F
from torch import Tensor, nn

from virgo_slm.model.config import VirgoSLMConfig

_PRECISION_DTYPES: dict[str, torch.dtype] = {
    "fp32": torch.float32,
    "fp16": torch.float16,
    "bf16": torch.bfloat16,
}


def resolve_dtype(precision: str) -> torch.dtype:
    try:
        return _PRECISION_DTYPES[precision]
    except KeyError as error:
        raise ValueError(f"Unknown precision {precision!r}") from error


@dataclass
class LayerKVCache:
    """Per-layer cached key/value tensors, shape (batch, kv_heads, seq, head_dim)."""

    key: Tensor
    value: Tensor


class RMSNorm(nn.Module):
    def __init__(self, hidden_size: int, eps: float) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.ones(hidden_size))
        self.eps = eps

    def forward(self, x: Tensor) -> Tensor:
        variance = x.pow(2).mean(dim=-1, keepdim=True)
        x = x * torch.rsqrt(variance + self.eps)
        return x * self.weight


def build_norm(config: VirgoSLMConfig) -> nn.Module:
    if config.norm_type == "rmsnorm":
        return RMSNorm(config.hidden_size, config.norm_eps)
    return nn.LayerNorm(config.hidden_size, eps=config.norm_eps)


class RotaryEmbedding(nn.Module):
    """Precomputed rotary position embedding cos/sin tables."""

    def __init__(self, head_dim: int, max_position_embeddings: int, theta: float) -> None:
        super().__init__()
        inv_freq = 1.0 / (
            theta ** (torch.arange(0, head_dim, 2, dtype=torch.float32) / head_dim)
        )
        positions = torch.arange(max_position_embeddings, dtype=torch.float32)
        freqs = torch.outer(positions, inv_freq)  # (max_pos, head_dim/2)
        emb = torch.cat((freqs, freqs), dim=-1)  # (max_pos, head_dim)
        self.register_buffer("cos_cached", emb.cos(), persistent=False)
        self.register_buffer("sin_cached", emb.sin(), persistent=False)

    def forward(self, position_ids: Tensor) -> tuple[Tensor, Tensor]:
        cos_cached = cast(Tensor, self.cos_cached)
        sin_cached = cast(Tensor, self.sin_cached)
        cos = cos_cached[position_ids]  # (batch, seq, head_dim)
        sin = sin_cached[position_ids]
        return cos, sin


def _rotate_half(x: Tensor) -> Tensor:
    x1, x2 = x.chunk(2, dim=-1)
    return torch.cat((-x2, x1), dim=-1)


def apply_rotary_pos_emb(q: Tensor, k: Tensor, cos: Tensor, sin: Tensor) -> tuple[Tensor, Tensor]:
    # q, k: (batch, heads, seq, head_dim); cos/sin: (batch, seq, head_dim)
    cos = cos.unsqueeze(1)
    sin = sin.unsqueeze(1)
    q_rot = (q * cos) + (_rotate_half(q) * sin)
    k_rot = (k * cos) + (_rotate_half(k) * sin)
    return q_rot, k_rot


def repeat_kv(x: Tensor, n_rep: int) -> Tensor:
    """Expand (batch, kv_heads, seq, head_dim) -> (batch, kv_heads*n_rep, seq, head_dim)."""
    if n_rep == 1:
        return x
    batch, kv_heads, seq, head_dim = x.shape
    x = x[:, :, None, :, :].expand(batch, kv_heads, n_rep, seq, head_dim)
    return x.reshape(batch, kv_heads * n_rep, seq, head_dim)


class CausalSelfAttention(nn.Module):
    def __init__(self, config: VirgoSLMConfig) -> None:
        super().__init__()
        self.num_heads = config.num_heads
        self.num_kv_heads = config.effective_num_kv_heads
        self.head_dim = config.head_dim
        self.n_rep = self.num_heads // self.num_kv_heads
        self.attention_dropout = config.attention_dropout

        h = config.hidden_size
        self.q_proj = nn.Linear(h, self.num_heads * self.head_dim, bias=False)
        self.k_proj = nn.Linear(h, self.num_kv_heads * self.head_dim, bias=False)
        self.v_proj = nn.Linear(h, self.num_kv_heads * self.head_dim, bias=False)
        self.o_proj = nn.Linear(self.num_heads * self.head_dim, h, bias=False)

    def forward(
        self,
        x: Tensor,
        cos: Tensor,
        sin: Tensor,
        attn_mask: Tensor | None,
        kv_cache: LayerKVCache | None,
    ) -> tuple[Tensor, LayerKVCache | None]:
        batch, seq_len, _ = x.shape

        q = self.q_proj(x).view(batch, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(batch, seq_len, self.num_kv_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(batch, seq_len, self.num_kv_heads, self.head_dim).transpose(1, 2)

        q, k = apply_rotary_pos_emb(q, k, cos, sin)

        new_cache: LayerKVCache | None = None
        if kv_cache is not None:
            k = torch.cat([kv_cache.key, k], dim=2)
            v = torch.cat([kv_cache.value, v], dim=2)
        if kv_cache is not None or attn_mask is None:
            # Inference path: cache is being used, so persist the growing
            # cache for the next step.
            new_cache = LayerKVCache(key=k, value=v)

        k = repeat_kv(k, self.n_rep)
        v = repeat_kv(v, self.n_rep)

        is_causal = attn_mask is None and kv_cache is None
        out = F.scaled_dot_product_attention(
            q,
            k,
            v,
            attn_mask=attn_mask,
            dropout_p=self.attention_dropout if self.training else 0.0,
            is_causal=is_causal,
        )
        out = out.transpose(1, 2).contiguous().view(batch, seq_len, -1)
        return self.o_proj(out), new_cache


class SwiGLUMLP(nn.Module):
    def __init__(self, config: VirgoSLMConfig) -> None:
        super().__init__()
        h, ffn = config.hidden_size, config.ffn_hidden_size
        self.gate_proj = nn.Linear(h, ffn, bias=False)
        self.up_proj = nn.Linear(h, ffn, bias=False)
        self.down_proj = nn.Linear(ffn, h, bias=False)

    def forward(self, x: Tensor) -> Tensor:
        return cast(Tensor, self.down_proj(F.silu(self.gate_proj(x)) * self.up_proj(x)))


class GELUMLP(nn.Module):
    def __init__(self, config: VirgoSLMConfig) -> None:
        super().__init__()
        h, ffn = config.hidden_size, config.ffn_hidden_size
        self.fc1 = nn.Linear(h, ffn, bias=True)
        self.fc2 = nn.Linear(ffn, h, bias=True)

    def forward(self, x: Tensor) -> Tensor:
        return cast(Tensor, self.fc2(F.gelu(self.fc1(x))))


def build_mlp(config: VirgoSLMConfig) -> nn.Module:
    return SwiGLUMLP(config) if config.activation == "swiglu" else GELUMLP(config)


class TransformerBlock(nn.Module):
    def __init__(self, config: VirgoSLMConfig) -> None:
        super().__init__()
        self.input_norm = build_norm(config)
        self.attention = CausalSelfAttention(config)
        self.post_attention_norm = build_norm(config)
        self.mlp = build_mlp(config)
        self.dropout = nn.Dropout(config.dropout)

    def forward(
        self,
        x: Tensor,
        cos: Tensor,
        sin: Tensor,
        attn_mask: Tensor | None,
        kv_cache: LayerKVCache | None,
    ) -> tuple[Tensor, LayerKVCache | None]:
        attn_out, new_cache = self.attention(
            self.input_norm(x), cos, sin, attn_mask, kv_cache
        )
        x = x + self.dropout(attn_out)
        x = x + self.dropout(self.mlp(self.post_attention_norm(x)))
        return x, new_cache


@dataclass
class VirgoSLMOutput:
    logits: Tensor
    loss: Tensor | None
    kv_caches: list[LayerKVCache | None] | None


class VirgoSLMForCausalLM(nn.Module):
    """Configurable decoder-only Transformer for causal language modeling."""

    def __init__(self, config: VirgoSLMConfig) -> None:
        super().__init__()
        self.config = config

        self.token_embeddings = nn.Embedding(
            config.vocab_size, config.hidden_size, padding_idx=config.pad_token_id
        )
        self.rotary_emb = RotaryEmbedding(
            config.head_dim, config.max_position_embeddings, config.rope_theta
        )
        self.layers = nn.ModuleList(
            TransformerBlock(config) for _ in range(config.num_layers)
        )
        self.final_norm = build_norm(config)

        if config.tie_word_embeddings:
            self.lm_head: nn.Linear | None = None
        else:
            self.lm_head = nn.Linear(config.hidden_size, config.vocab_size, bias=False)

        self.apply(self._init_weights)

    def _init_weights(self, module: nn.Module) -> None:
        std = self.config.initializer_range
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=std)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=std)
            if module.padding_idx is not None:
                with torch.no_grad():
                    module.weight[module.padding_idx].fill_(0.0)

    def _compute_logits(self, hidden_states: Tensor) -> Tensor:
        if self.lm_head is not None:
            return cast(Tensor, self.lm_head(hidden_states))
        return F.linear(hidden_states, self.token_embeddings.weight)

    def forward(
        self,
        input_ids: Tensor,
        *,
        attention_mask: Tensor | None = None,
        labels: Tensor | None = None,
        kv_caches: list[LayerKVCache | None] | None = None,
        use_cache: bool = False,
    ) -> VirgoSLMOutput:
        """Run the model.

        Args:
            input_ids: (batch, seq_len) token ids.
            attention_mask: optional (batch, seq_len) 1/0 padding mask.
                Combined with an implicit causal mask. If ``None`` and no
                ``kv_caches`` are supplied, a fast fused causal path is used.
            labels: optional (batch, seq_len) target ids for computing loss;
                -100 entries are ignored, matching the standard PyTorch
                convention.
            kv_caches: optional per-layer cache from a previous call, for
                incremental decoding.
            use_cache: if True, return updated per-layer caches.
        """
        batch, seq_len = input_ids.shape
        device = input_ids.device

        if kv_caches is not None and kv_caches[0] is not None:
            past_len = kv_caches[0].key.shape[2]
        else:
            past_len = 0
        position_ids = torch.arange(
            past_len, past_len + seq_len, device=device
        ).unsqueeze(0).expand(batch, -1)

        cos, sin = self.rotary_emb(position_ids)

        combined_mask = self._build_attention_mask(
            attention_mask, seq_len, past_len, device
        )

        x = self.token_embeddings(input_ids)
        new_caches: list[LayerKVCache | None] = []
        layer_caches = kv_caches or [None] * len(self.layers)
        for layer, layer_cache in zip(self.layers, layer_caches, strict=True):
            x, updated_cache = layer(x, cos, sin, combined_mask, layer_cache)
            if use_cache:
                new_caches.append(updated_cache)

        x = self.final_norm(x)
        logits = self._compute_logits(x)

        loss = None
        if labels is not None:
            loss = F.cross_entropy(
                logits[:, :-1, :].reshape(-1, logits.size(-1)),
                labels[:, 1:].reshape(-1),
                ignore_index=-100,
            )

        return VirgoSLMOutput(
            logits=logits,
            loss=loss,
            kv_caches=new_caches if use_cache else None,
        )

    @staticmethod
    def _build_attention_mask(
        attention_mask: Tensor | None,
        seq_len: int,
        past_len: int,
        device: torch.device,
    ) -> Tensor | None:
        """Build an additive float mask, or None to use the fused causal fast path."""
        if attention_mask is None and past_len == 0:
            return None  # fused SDPA causal path

        total_len = past_len + seq_len
        causal = torch.ones(seq_len, total_len, dtype=torch.bool, device=device).tril(
            diagonal=past_len
        )
        mask = causal.unsqueeze(0).unsqueeze(0)  # (1, 1, seq, total)
        if attention_mask is not None:
            pad = attention_mask.bool().unsqueeze(1).unsqueeze(1)  # (batch,1,1,total)
            mask = mask & pad
        additive = torch.zeros(mask.shape, dtype=torch.float32, device=device)
        additive = additive.masked_fill(~mask, float("-inf"))
        return additive


def count_parameters(model: nn.Module, *, trainable_only: bool = True) -> int:
    """Exact instantiated parameter count — the authoritative figure.

    This sums ``numel()`` over real ``nn.Parameter`` tensors in a built
    model, so (unlike :func:`virgo_slm.model.config.estimate_parameter_count`)
    it is exact by construction, not an approximation.
    """
    return sum(
        p.numel()
        for p in model.parameters()
        if (p.requires_grad or not trainable_only)
    )
