# Virgo AI

Virgo AI 1.0.0 supports Python 3.12 through Python 3.14.

## Personal AI Runtime (Stage 5 Step 1)

Virgo now provides one instance-owned orchestration boundary for conversation,
voice-originated tasks, bounded specialized agents, independent verification,
deterministic budgets, exact task permissions, cancellation, and explicit
personal preferences stored separately from verified knowledge. Existing
Creation, Security, Learning, evaluation, permission, state, and rollback
systems remain authoritative.

Browser, internet research, desktop automation, image generation, and video
generation expose typed boundaries and truthful `NOT_CONFIGURED` status when no
provider is configured. There is no silent cloud fallback, arbitrary shell or
desktop automation, agent recursion, model training, automatic deployment, or
self-authorization. Credentials are not stored by the current product, so no
credential encryption facility is exposed. Provider credentials must not be
entered into Virgo data.

## Production launch and recovery

Prerequisites are Windows, Python 3.12–3.14, the Rust stable toolchain, the
installed project environment, and Ollama plus a configured local model for
conversation. Local STT and Windows speech health are shown in Virgo;
unavailable providers fail safely. Browser, internet research, desktop
automation, application updates, accelerator routing, image generation, and
video generation remain `NOT_CONFIGURED`. Virgo never silently switches to a
cloud provider.

Launch the installed desktop application with:

```powershell
.\.venv\Scripts\virgo-ai.exe
```

Build the production wheel with the existing maturin toolchain:

```powershell
.\scripts\packaging\build_windows.ps1
```

Desktop diagnostics show provider health, application/Rust versions, runtime
state, platform, CPU, memory availability, accelerator status, and update
status. Backup/restore is an explicit service for closed Virgo data. It includes
only bounded session and memory databases, validates versioned hashes before
restore, and preserves the prior directory until replacement succeeds. Store
backup archives securely outside Virgo's data directory: archives are not
encrypted and must be protected like the underlying personal data.


## Virgo SLM runtime

The repository now contains an explicit local Virgo SLM inference path in addition to the Ollama provider. After you train a model, export it as a portable artifact with `virgo_slm.inference.save_artifact(...)` or the SLM export tooling, then place the artifact at `data/models/virgo-slm`. The desktop model selector advertises the SLM only when the artifact passes manifest/hash validation.

The runtime is local-only and does not download weights, call a cloud service, execute tools, or bypass Virgo permissions. Tool requests are structured data consumed by Virgo's authoritative tool/permission layer.

Install the SLM runtime dependencies separately because normal desktop startup does not require PyTorch/tokenizers. The standalone sibling package must also be installed so the desktop provider can import the SLM runtime:

```powershell
.\.venv\Scripts\python -m pip install -e ".[slm]"
.\.venv\Scripts\python -m pip install -e "..\virgo_slm[runtime]"
```

After you have trained and exported the real artifact, verify the complete conversation path with:

```powershell
.\.venv\Scripts\python scripts\verification\verify_slm_integration.py
```

The verification script returns non-zero when the trained artifact is missing or invalid; it does not simulate a successful model response.

Training is intentionally not run automatically. This repository provides the training/inference/export/evaluation code; actual production corpus selection and the long training run remain explicit operator actions.

## Python development

The development toolchain uses maturin for the mixed Rust/Python package build,
Black for required formatting, Ruff for linting, mypy for static type checking,
pytest for tests, and PyPA Build as an isolated PEP 517 frontend. These tools are
development-only. Runtime dependencies are PySide6, sounddevice, numpy, and
faster-whisper, as declared in `pyproject.toml`.

Create an isolated environment:

```powershell
python -m venv .venv
```

Install the project and its development tools:

```powershell
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

Format Python files:

```powershell
.\.venv\Scripts\python -m black .
```

Run formatting, linting, type-checking, and tests:

```powershell
.\.venv\Scripts\python -m black --check .
.\.venv\Scripts\ruff check .
.\.venv\Scripts\python -m mypy
.\.venv\Scripts\python -m pytest
```

Build the Python package:

```powershell
.\.venv\Scripts\python -m build
```

## Rust and Python binding development

Install the stable Rust toolchain and ensure `rustc`, Cargo, and a compatible
native linker are available. Then run the Rust checks from the repository root:

```powershell
cargo fmt --all --check
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo test --workspace --all-targets --all-features
cargo build --workspace
```

Build and install the native extension into the active development environment:

```powershell
.\.venv\Scripts\python -m maturin develop
.\.venv\Scripts\python -c "from virgo import _rust_core; print(_rust_core.rust_core_status())"
```

Run the complete Python checks after building the extension:

```powershell
.\.venv\Scripts\python -m black --check .
.\.venv\Scripts\ruff check .
.\.venv\Scripts\python -m mypy
.\.venv\Scripts\python -m pytest
```

Build a distributable wheel through maturin:

```powershell
.\.venv\Scripts\python -m maturin build --release
```

## Configuration and logging foundation

Configuration is loaded only when `load_settings()` is called. Precedence is
defaults, then an optional JSON file, then explicit `VIRGO_` environment
variables. The returned `AppSettings` value is immutable and validated.

Logging is initialized only when `configure_logging()` is called. It supports a
readable console handler and an optional rotating JSON-line file handler. Keep
the returned `LoggingRuntime` and call `shutdown()` during explicit application
cleanup.

## Minimal desktop shell

PySide6 is the architecture-required Qt binding. The community packages use
LGPLv3/GPLv3 licensing; commercial distribution may instead require the Qt
commercial edition. Review the selected license before redistribution.

Start the minimal desktop shell explicitly:

```powershell
.\.venv\Scripts\python -m apps.desktop.main
```

The Stage 1 shell uses the installed local Ollama models, Windows WASAPI audio
devices, the local `base.en` speech model, and installed Windows voices. Text
messages send with Enter or Send. Hold Push to talk while speaking and release
to transcribe, generate, speak, and persist the turn. Stop interrupts active
generation or playback. Sessions, settings, health, and safe diagnostics are
available from the native tabs.

The shell uses three reusable presentation areas: an application header, a
central foundation-content area, and a bottom status area. Styling uses Qt
palette roles so the structure remains compatible with light and dark palettes
without introducing a theme engine.

## In-process events

Typed immutable event contracts and `EventDispatcher` provide explicit,
synchronous in-process publish/subscribe behavior. Dispatchers are created by
callers as needed; importing the event packages creates no global dispatcher or
background processing.

## Application state

Stage 1 application state is represented by immutable snapshots held by an
instance-owned store. Actual changes publish typed in-process events. A small
explicit desktop binding translates those events into status text and an
accessible visual-state indicator without placing state logic in the window.

## Audio-device discovery

Audio input and output devices are enumerated only through an explicit discovery
service call. On Windows, discovery prefers the native WASAPI default input over
legacy compatibility host APIs when available. Results are immutable
backend-neutral metadata; discovery does not open streams, record, play audio,
poll devices, or persist a device choice.

## Microphone capture

Microphone capture uses an explicit open/start/stop/close lifecycle and immutable
raw PCM chunks. A bounded in-memory queue preserves order and drops the oldest
chunk on overflow. Capture performs no file writes, playback, transcription,
voice-activity detection, or continuous-listening orchestration.

## Local speech-to-text

The synchronous faster-whisper provider accepts supplied in-memory `int16` PCM,
converts it to 16 kHz mono samples, and returns immutable transcription results.
The CPU `int8` model is loaded only through an explicit `load()` call. The
default `tiny` model is the lightweight option; `base.en` is the recommended
Stage 1 model for live English commands. Models may be downloaded into the
normal Hugging Face cache on first explicit load; model and cache files are
never part of this repository.

## Microphone-to-STT bridge

One synchronous integration service accepts ordered microphone `AudioChunk`
values, bounds the accumulated PCM bytes, and creates one local transcription
request on explicit flush. It owns neither the microphone nor the STT provider,
and resets its in-memory buffer after both successful and failed transcription.

## Local LLM provider

The Step 9 provider uses Python's standard library to call an explicitly
configured loopback Ollama endpoint. It lists already-installed models,
validates explicit model selection, supports completed and provider-level
streaming generation, and never pulls a model or falls back to a cloud service.

## Streaming conversation orchestration

Step 10 coordinates one in-memory turn from typed text or an existing STT
result through the local LLM streaming interface. It publishes typed lifecycle
events, updates application state, supports cooperative cancellation, and does
not persist history or invoke TTS, tools, memory, agents, or UI code.

## Local speech synthesis and playback

Step 11 uses the installed Windows `System.Speech` runtime through a hidden,
argument-safe Windows PowerShell process to synthesize bounded text directly
to in-memory PCM. Playback is explicit and synchronous through the existing
`sounddevice` stack; neither synthesis nor playback occurs during import, and
no generated audio is persisted automatically.

## Barge-in and cancellation

Step 12 adds one explicit interruption API that coordinates existing
conversation cancellation and playback stop behavior. Active generation emits
no further application chunks or completion after cancellation; active playback
is written in bounded chunks so unplayed PCM can be discarded, then the state
passes through `INTERRUPTED` to `IDLE`. Starting microphone capture may supply
the explicit interruption request, but no VAD, wake word, or continuous
listening is implemented here. Windows speech synthesis itself remains a
synchronous pre-playback operation and cannot yet be interrupted.

## Sessions and persisted settings

Step 13 stores explicitly created sessions, ordered user/assistant history, and
selected microphone, speaker, local-model, and TTS-voice preferences in one
local SQLite database under the configured data directory. Initialization and
all reads/writes are explicit; imports create no files or connections. Static
and environment configuration remain separate and authoritative. Cancelled
partial assistant responses and failed assistant generations are not persisted.

## Provider health, recovery, and diagnostics

Step 14 wraps existing local providers with explicit health checks and a
bounded, cancellation-aware retry policy. Diagnostics are collected in memory
and contain only safe runtime, state, readiness, and provider metadata; they do
not include conversations, audio, secrets, environment dumps, or automatic
file/telemetry output. Recovery uses the existing `RECOVERING`, `IDLE`, and
`ERROR` states and never downloads models or selects cloud fallbacks.

## Controlled creation workflows

The native Creation tab can analyze a bounded local workspace, prepare exact
file proposals and unified-diff previews, request explicit per-operation
approval, apply approved text-file creation or edits, validate the result, and
either accept or roll back the task. Planning and preview do not mutate user
files. Applied changes use Rust-backed containment and staged writes, retain a
task-scoped mutation journal and backup until acceptance, and verify SHA-256
content before and after rollback.

Validation commands are registered and allowlisted, receive executable and
arguments separately, have timeouts and cancellation, and never invoke a shell
string. The existing local Ollama provider may produce untrusted typed content
proposals, but deterministic verification and the central permission gate
remain authoritative. The final Creation Engine adds typed capability routing,
bounded prompt enrichment, explainable local-first model selection, richer
HTML/CSS/JavaScript website generation, frontend/backend/application and coding
routes, local project/SEO/website analysis, unified previews, and structured
task reports. It never installs missing frameworks, starts servers, deploys, or
publishes automatically.

WordPress, Shopify, image generation/editing/enhancement, and video generation
use provider-neutral contracts with staged artifacts, verification, preview,
permission, acceptance, cleanup, and honest failure states. They show
`NOT_CONFIGURED` until an explicit provider is configured; Virgo neither
downloads a model nor silently falls back to cloud. External account mutation
is not performed during Stage 2 acceptance.

Run the real temporary-workspace backend proof with:

```powershell
.\.venv\Scripts\python scripts\verification\verify_controlled_creation.py
```

Run the visible native UI proof with a screenshot directory outside the source
tree:

```powershell
.\.venv\Scripts\python scripts\verification\verify_creation_ui.py <output-directory>
```

## Stage 3 defensive security assessment

The existing desktop application now includes a Security workspace for explicit,
authorized local-project analysis. Stage 3 Step 1 is read-only and local-only:
network access is denied by contract, traversal is bounded through the existing
Rust-backed path boundary, oversized/binary/generated content is skipped, and
findings separate canonical severity from confidence. Step 2 extends the same
registry with high-signal observations for shell and dynamic execution, risky
deserialization, weak temporary files, constructed SQL, unvalidated-looking path
inputs, disabled TLS verification, broad host/origin/permission configuration,
debug settings, and secret-like assignments. Python, Rust, JavaScript, HTML/CSS,
and common text configuration are inspected only as bounded text; Python-specific
checks use the standard-library syntax tree rather than universal parsing.

Local manifest inspection supports `pyproject.toml`, `requirements*.txt`,
`package.json`, and `Cargo.toml`. It reports constraints, direct sources, install
hooks, malformed manifests, and meaningful missing lockfiles without inventing
CVEs, CVSS values, vulnerable versions, or upgrade versions. Vulnerability
intelligence is explicitly `NOT_CONFIGURED` until a separately authorized provider
exists. Explicitly selected `.log` files can be checked for repeated authentication,
permission-denied, and blocked-action patterns; unrelated logs are skipped. Evidence,
events, UI details, and serialized reports redact candidate credentials and omit
complete source/log contents. Recommendations never modify files.

Run the real disposable-project, redaction, and no-mutation proof with:

```powershell
.\.venv\Scripts\python scripts\verification\verify_security_analysis.py
```

The Security UI shows the authorized scope, selected assessment/logs, filters,
severity, category, confidence, evidence location, recommendations, skipped checks,
and unavailable intelligence status. Network access remains contractually disabled.
The final Stage 3 layer adds safe platform metadata diagnostics, potential malware
indicator triage (never a malware verdict), explicit lab objectives, and optional
tool health declarations that remain `NOT_CONFIGURED` when unavailable. One active
network operation is supported: after ownership confirmation and a separate visible
approval, Virgo may check TCP reachability for one exact `127.0.0.1` port. Public
addresses, ranges, discovery, payloads, authentication, and exploitation are rejected.

Selected deterministic configuration findings can be previewed and remediated only
through the existing Stage 2 permission and controlled-mutation workflow. Virgo then
re-runs the real assessment and reports whether the finding was resolved; the exact
original content remains rollback-capable. It performs no credential attack,
persistence, upload, telemetry, cloud-provider call, or autonomous broad remediation.

## Stage 4 controlled learning foundation

The Learning screen provides explicit, reviewable local learning from approved
text documents. Virgo detects scoped knowledge gaps, requests task-bound research
permission, extracts evidence-backed candidate claims, explains deterministic
quality decisions, records provenance and confidence, and stores only explicitly
accepted verified knowledge in the existing local data root. Project-scoped
retrieval, user corrections with preserved supersession history, and explicit
forget/delete are supported. Candidate skills and evaluation examples are typed
non-executable metadata and cannot alter tool permissions.

Internet research remains disabled and its provider reports `NOT_CONFIGURED`.
Website and GitHub source types are contract boundaries only in Step 1. There is
no background crawling, silent learning, model-weight modification, autonomous
self-modification, or Stage 5 browser automation. Step 2 extends this foundation
below; Step 3 remains pending separate approval.

Stage 4 Step 2 adds bounded experience learning and read-only self-inspection.
Structured task outcomes and failures can produce evidence-backed reusable lessons;
validated lessons may produce versioned, non-executable structured skills and
deterministic evaluation examples. Baseline/candidate evaluation reports improved,
unchanged, regressed, or inconclusive outcomes and exposes mixed regressions.

Authorized self-inspection covers static syntax, dependency manifests,
architecture rules, bounded performance evidence, Stage 3 security-analysis reuse,
test-gap evidence, and failure-analysis boundaries. It can create risk-estimated
improvement proposals, but Step 2 cannot request or apply production-code changes.
Coverage percentages remain unavailable without a configured coverage provider,
and historically stopped before the separately approved Step 3 mutation boundary.

Stage 4 Step 3 completes the controlled software self-improvement workflow. An
existing evidence-backed proposal is bound to an exact clean Git baseline,
canonical repository, explicit file set, deterministic risk, predefined tests,
Stage 3 security review, Step 2 evaluations, and an exact diff preview. Nothing
changes until a project owner grants task-, baseline-, scope-, and content-bound
approval. Accepted low-scope candidates use a dedicated `self-improve/*` branch,
the existing Stage 2 atomic mutation journal and rollback, allowlisted validation
processes, before/after hashes, regression blocking, and an explicit final Accept
or Rollback decision. Protected permission, audit, rollback, verification,
security, path-safety, provider-safety, architecture, and self-improvement policy
targets return `PROTECTED_TARGET / HUMAN_REVIEW_REQUIRED`.

The Learning screen visibly shows the problem, evidence, risk, exact files,
preview, branch, tests, security result, evaluation comparison, and rollback
state. Long preparation, testing, security, and evaluation work runs off the Qt
UI thread and supports cancellation at safe process boundaries. This capability
does not train model weights, install dependencies, recursively improve itself,
merge, deploy, or silently modify production code. Stage 5 remains pending a
separate architecture review.

## Phase 2 Stage 2 user intelligence and memory integration

Virgo derives bounded user context from explicit scoped preferences and verified
knowledge already owned by the existing knowledge repository. Relevant-memory
retrieval is limited to the requested scope plus global verified knowledge,
preserves provenance, and never persists retrieved content. Typed memory
candidates are proposals; only explicitly accepted preference candidates enter
the existing preference admission path.

The existing session repository now supports a versioned lifecycle for create,
rename, bounded search, archive, restore, and explicit delete. Archiving or
deleting an active session safely selects or creates another active session.
Session deletion cascades only to that session's messages and does not delete
independently accepted long-term memory. Storage awareness reports only the
known Virgo session and memory databases and recommends archived sessions for
review; it performs no cleanup. Session export is intentionally deferred.

The existing Personal AI Runtime self-produced verification pass remains a
tracked trust gap and is not fixed by this step. Numeric Tier 0-4 authorization
semantics remain unresolved and have no effect on runtime authorization.

### Voice identity and conversation understanding

Virgo's voice profiles are a typed view of voices reported by the configured
local TTS provider. The saved provider voice remains active when available; if
it is missing, Virgo falls back to the first voice actually reported by that
provider. No particular locale, gender, or personality is claimed unless the
provider supplies that metadata. Selection continues to persist through the
existing session settings authority.

The current Windows speech provider supports installed voice selection only.
Custom voice cloning is therefore reported as `UNSUPPORTED` (or
`NOT_CONFIGURED` when no voice is available); Virgo does not record, upload, or
retain voice samples and does not silently download a voice model.

Conversation understanding is a deterministic collaborator beneath the
existing orchestration boundary. It uses at most five recent supplied
references to identify corrections, references, repeated requests, urgency,
frustration, hesitation, and response-style hints. Ambiguous references cause
a clarification request. Interaction signals are ephemeral and cannot grant
permission, execute tools, reduce verification, or create psychological
profiles. Only explicit stable language or response-style requests become
memory candidates, and those candidates still require the existing memory
admission authority before persistence.

The Personal AI Runtime verification trust gap remains `TRACKED_NOT_FIXED`.
Tier 0-4 authorization remains `UNRESOLVED_DEFERRED`; no Step 5 or later Brain
capability is implemented here.

### Cognitive preparation

The existing `PersonalAIRuntime` remains Virgo's authoritative orchestration
boundary. It now consumes typed conversation understanding and builds the
smallest active cognitive context from at most five recent items, five supplied
evidence items, bounded approved memory, scoped preferences, task/session
metadata, and model identifiers reported by existing configuration. This
attention budget does not mutate or persist memory.

Cognitive preparation records evidence-category uncertainty as `KNOWN`,
`LIKELY`, `UNKNOWN`, `CONFLICTING`, `OUTDATED`, or `NEEDS_VERIFICATION`.
Materially unknown or conflicting requests wait for clarification. Outdated or
verification-dependent requests return `REQUIRE_CURRENT_KNOWLEDGE` for Step 5;
requests needing tools or external effects return `REQUIRE_CAPABILITY` for Step
6. Neither boundary performs the deferred work.

Simple requests retain a direct fast path. Non-trivial requests may produce at
most five advisory steps containing a purpose, expected outcome, preconditions,
and stop conditions. The planner cannot execute tools, authorize permissions,
or certify success. Configured-model routing selects only an identifier supplied
by the existing provider configuration and has no cloud fallback. Operational
UI text exposes strategy/status metadata, never hidden reasoning or
chain-of-thought.

The Personal AI Runtime verification trust gap remains `TRACKED_NOT_FIXED`, and
Tier 0-4 authorization remains `UNRESOLVED_DEFERRED`. Tool/agent execution and
later Brain steps are not implemented by this layer.

### Knowledge on demand

`PersonalAIRuntime` converts only `REQUIRE_CURRENT_KNOWLEDGE` decisions into a
bounded `KnowledgeNeed`. A need retains the task/session identity, exact
question, knowledge type and scope, no more than five known-context items,
one-to-five sources, a maximum 60-second timeout, and at most one retry.

The pipeline checks existing verified scoped knowledge first. Stable or local
project evidence can satisfy a need without a provider call. Current and
time-sensitive questions require dated current/recent evidence; undated or
stale local knowledge is retained as incomplete evidence rather than presented
as current truth.

External internet retrieval is `NOT_CONFIGURED`: the repository has no approved
search provider, and browser/research tools remain unavailable. The pipeline
does not add a network adapter, cloud fallback, browser agent, or Step 6
execution path. Its provider boundary is typed, source-count/time/retry bounded,
and cancellable for a future separately approved provider.

Temporary `KnowledgeEvidencePackage` values preserve source identity,
provenance, derived freshness (`CURRENT`, `RECENT`, `STALE`, or `UNKNOWN`),
conflicts, remaining unknowns, retrieval status, and the need for independent
verification. Duplicate results and authority-shaped prompt-injection content
are rejected deterministically. Evidence entering cognition is explicitly
marked `UNTRUSTED_SOURCE`; it cannot grant permission or change task authority,
and it is never automatically persisted to memory.

Retrieval success is not verification success. The Personal AI Runtime trust
gap remains `TRACKED_NOT_FIXED`, Tier 0-4 remains `UNRESOLVED_DEFERRED`, and no
Step 7 or later Brain capability is implemented here.

### Bounded capability execution

`PersonalAIRuntime` remains the sole orchestration boundary for Step 4
`REQUIRE_CAPABILITY` decisions. Its capability view is a metadata adapter over
the existing registered tools and bounded agents; it does not merge or replace
their execution authorities. Descriptors expose typed input/output contracts,
existing `ActionRisk`, permission requirements, timeout, cancellation, audit,
rollback, environment requirements, and truthful availability.

Environment selection is a local preflight using the current platform,
working directory, task filesystem scope, registered runtime and explicit
network-unavailable state. It cannot install software, broaden scope, or grant
authorization. Unknown, unconfigured and incompatible capabilities stop before
execution. Existing scoped permission identifiers remain authoritative;
numeric Tier 0-4 values are not used.

The actual safe read-only capability integrated with the Personal AI path is
the existing local diagnostics collector. Registered bounded agents retain
their fixed objective, scope, budget, time limit, empty tool allowlist and stop
conditions. Creation remains subject to its existing workspace and permission
workflow. Browser, desktop, image and video capabilities remain
`NOT_CONFIGURED` and no shell, browser automation or desktop-control subsystem
is added.

Capability execution validates text inputs, rejects secret-like values, uses a
registered handler or agent only, enforces cooperative cancellation and a
declared timeout, and validates non-empty structured output. Its evidence
records task/execution identity, safe input and environment summaries,
permission reference, observed operation, output/error state, cancellation,
timeout, rollback metadata and audit references. Rollback is `NOT_REQUIRED` for
read-only diagnostics, `SUPPORTED` only for the existing creation workflow, and
otherwise `NOT_SUPPORTED`.

Executor output always remains `verified=false`; evidence is input to the
separate Response Verifier and audit strings are not proof of correctness. The
verification trust gap remains `TRACKED_NOT_FIXED`, Step 5 external retrieval
remains `NOT_CONFIGURED_DEFERRED`, Tier 0-4 remains `UNRESOLVED_DEFERRED`, and
no Step 7 or later Brain capability is implemented here.

## Stage 1 acceptance status

Stage 1 closure evidence includes a real WASAPI microphone transcript, local
Ollama streaming response, Windows speech synthesis, physical playback, and
interruption back to idle. The desktop shell exposes all architecture-required
Stage 1 surfaces through lightweight native tabs, and deterministic end-to-end
and acceptance regression tests cover the local application boundaries.
