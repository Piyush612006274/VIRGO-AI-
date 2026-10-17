# VIRGO AI — Build Status

## Architecture
- Virgo SLM is the primary model target.
- Ollama remains an optional teacher/fallback provider.
- The SLM target is 102,981,120 parameters (~103M).
- FP32 weights are about 0.384 GiB; FP16 about 0.192 GiB, leaving substantial room under a 2 GiB model budget.
- The repository contains the model architecture, tokenizer, dataset, training, inference, evaluation, and export code.

## Important status
This package does **not** contain fake/random trained weights. A randomly initialized Transformer is not a useful assistant, so no file is presented as a trained Virgo SLM. The real trained artifact must be produced from an approved corpus, optionally using Qwen through Ollama as a teacher.

## Permanent identity
A deterministic identity layer answers creator/owner/master questions independently of model output, memory, prompts, and self-learning:

> Piyush is my creator and owner. Piyush is my master.

## Verification
- 202 Python files parsed on every verification loop.
- 50/50 repeated verification loops passed.
- 50x deterministic identity checks passed.
- Tiny Transformer forward + KV-cache check passed.
- 102,981,120 parameter count reproduced.
- No `.pyc`, `.pyo`, `__pycache__`, pytest, mypy, or ruff cache files are packaged.
