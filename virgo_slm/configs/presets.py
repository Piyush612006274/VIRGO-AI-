"""Pinned, named model-size presets.

``search_config_for_target_params`` is how a preset like ``VIRGO_SLM_103M``
below was *discovered*; once discovered it is pinned here as a literal
config so future runs and checkpoints don't depend on the search grid ever
producing the same answer again (the grid may change as more presets are
added). This is the versioned-configuration artifact called for by Phase 5.

Only ``VIRGO_SLM_103M`` (the initial ~100M-150M target) is populated so
far. 300M / 500M / 1B presets are placeholders for when scaling is
actually needed (Phase 1 explicitly requires the architecture to scale
without redesign — it does, see
``virgo_slm/tests/test_model_architecture.py::test_search_finds_100m_to_150m_config_for_planned_vocab``
plus the estimator being exact — but no larger preset has been picked or
trained yet, so none is claimed here).
"""

from __future__ import annotations

from virgo_slm.model.config import VirgoSLMConfig

# Vocab size is provisional: Phase 2 (tokenizer) has not been trained yet.
# 48,000 is a placeholder sized for the stated multilingual + code target
# (Hindi/English/Hinglish/Russian/Chinese/Japanese/Korean/Arabic + code +
# JSON + URLs). This MUST be revisited once the real tokenizer is trained;
# changing it changes the parameter count and invalidates any checkpoint.
PROVISIONAL_VOCAB_SIZE = 48_000

VIRGO_SLM_103M = VirgoSLMConfig(
    vocab_size=PROVISIONAL_VOCAB_SIZE,
    hidden_size=512,
    num_layers=23,
    num_heads=4,
    num_kv_heads=4,
    ffn_multiple_of=256,
    max_position_embeddings=2048,
    tie_word_embeddings=True,
    name="virgo-slm-103m",
    version="0.1.0",
)
"""~103M parameters (exact, verified against an instantiated model in
virgo_slm/tests/test_model_architecture.py). The initial pretraining
target for Phase 1-19. NOT yet trained — see virgo_slm/PROGRESS.md."""


# Production student target: about 103M parameters, comfortably below a 2 GB
# fp32 weight budget (~0.4 GB) and far below 2 GB when exported/quantized.
# This is the main Virgo SLM target; it is not a pretrained checkpoint.
VIRGO_SLM_MAIN = VIRGO_SLM_103M

PRESETS: dict[str, VirgoSLMConfig] = {
    "virgo-slm-103m": VIRGO_SLM_103M,
    "virgo-slm-main": VIRGO_SLM_MAIN,
}
