# Virgo SLM Integration

This document describes the current non-training handoff between the standalone
`virgo_slm` stack and the desktop Virgo application.

## Architecture

```text
User
  ↓
Virgo Desktop / ConversationOrchestrator
  ↓
RoutedLLMProvider
  ↓
ModelRouter
  ├── OllamaLLMProvider
  └── VirgoSLMProvider
          ↓
     SLMRuntime
          ↓
       artifact
          ├── model.pt
          ├── model_config.json
          ├── artifact.json
          └── tokenizer/
```

`VirgoSLMProvider` implements the existing `LLMProviderProtocol`. The model
router resolves an explicit model identifier to the provider that advertises
that model. The SLM package has no permission or tool-execution authority.

## Desktop installation

From `virgo-ai-core`:

```powershell
.\.venv\Scripts\python -m pip install -e ".[slm]"
.\.venv\Scripts\python -m pip install -e "..\virgo_slm[runtime]"
```

The first command installs the desktop application's optional SLM runtime
libraries. The second installs the sibling `virgo_slm` source package. The standalone
package is configured so its repository root installs as the `virgo_slm`
import package; no extra `PYTHONPATH` manipulation is required.
Normal desktop startup still works without these packages; the SLM is simply
not advertised until its runtime is available.

## Model handoff after training

The operator owns model training. Once a checkpoint and matching production
tokenizer exist:

```powershell
cd ..\virgo_slm
python -m virgo_slm.export.cli export `
  --checkpoint <CHECKPOINT> `
  --tokenizer-dir <TOKENIZER_DIR> `
  --output ..\virgo-ai-core\data\models\virgo-slm `
  --overwrite
```

The export creates and validates:

- `artifact.json`
- `model_config.json`
- `model.pt`
- `tokenizer/`

The desktop provider advertises `virgo-slm-103m` only after these files pass
hash validation and the runtime dependencies are available.

## Optional CPU INT8 artifact

```powershell
python -m virgo_slm.export.cli quantize-int8 `
  --input ..\virgo-ai-core\data\models\virgo-slm `
  --output ..\virgo-ai-core\data\models\virgo-slm-int8
```

Keep the source artifact untouched. The quantized artifact carries
`quantization = "dynamic-int8"` in its manifest.

## Safety boundary

The model may emit a structured tool request, but it cannot execute the tool.
Virgo remains responsible for:

```text
model proposal
→ capability lookup
→ input validation
→ permission gate
→ execution
→ independent verification
→ user-visible result
```

Memory authority likewise remains in the existing Virgo memory layer; the SLM
cannot write memory directly.

## Current verification

The repository contains tests for:

- model architecture and KV-cache behavior
- artifact validation and bounded inference
- provider contract + cancellation
- model routing
- tool-call parsing and argument validation
- instruction dataset serialization/deduplication
- evaluation reporting
- export/INT8 artifact generation
- checkpoint/resume exactness on a tiny CPU fixture

Actual production-model quality, benchmark scores, and a long training run are
not claimed here because those require operator-supplied corpus and compute.
