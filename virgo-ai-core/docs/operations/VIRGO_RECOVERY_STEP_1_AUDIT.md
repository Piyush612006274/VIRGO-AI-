# Virgo recovery — Step 1 forensic audit and recovery lock

**Date:** 2026-08-16  
**Mode:** audit and recovery planning only. No production code, dependency, model,
provider, data, or Git-history changes were made by this audit.

## 1. Repository and preservation status

| Item | Finding |
|---|---|
| Repository | `D:\Virgo AI`, accessible |
| Branch / HEAD | `feat/stage-5-production-finalization` / `a4881d308b310e9e44d45bc765e23f1e5a18c8c1` |
| Working tree | Five modified, uncommitted files; no files were reset, stashed, checked out, or overwritten. |
| Preserved repair work | `apps/desktop/controller.py`, `apps/desktop/views/stage_one.py`, `virgo/capabilities/agents/runtime.py`, and two unit-test files. The diff adds bounded prompt grounding and a Voice mode toggle. Preserve it as the starting point for Step 2, but it is not sufficient evidence that continuous voice works. |

The two persistent databases were inspected read-only: `data/sessions/virgo.sqlite3`
contains 2 sessions, 4 messages, and 1 settings row; `data/memory/knowledge.sqlite3`
contains its schema but no claims, preferences, learning assets, or audit entries.

## 2. Actual architecture map

```text
PySide6 shell / StageOneScreens
  -> DesktopApplicationController
     -> ConversationUnderstandingService + SessionLifecycleService
     -> ConversationOrchestrator -> OllamaLLMProvider -> selected local model
     -> WindowsSpeechTTSProvider -> AudioPlaybackService
     -> MicrophoneCaptureService -> MicrophoneSTTIntegrationService -> FasterWhisper
     -> PersonalAIRuntime -> capability registry / ResponseVerifier / bounded agents
     -> SQLiteSessionRepository + SQLiteKnowledgeRepository
```

This is a recoverable modular monolith and retains the authorities named in the
constitution: `PersonalAIRuntime`, `ConversationOrchestrator`, capability evidence,
`ResponseVerifier`, the controlled-learning repository, session persistence, and
selected-model-first Ollama routing. Evidence: `apps/desktop/controller.py`,
`virgo/application/conversation/orchestrator.py`, `virgo/capabilities/agents/runtime.py`,
`virgo/intelligence/verification.py`, and the two SQLite repositories.

Important limits: the Rust module is an approved workspace mutation and validation
boundary (`rust-core/src/lib.rs`), not a Windows desktop-control implementation. The
desktop UI is a broad multi-workspace shell rather than a voice-first conversation
surface (`apps/desktop/views/stage_one.py`).

## 3. Capability reality matrix

| Capability | Classification | Evidence and truth |
|---|---|---|
| Text conversation, streaming, session persistence | REAL_AND_WORKING (automated path) | `ConversationOrchestrator.run()` streams and appends both messages; `SQLiteSessionRepository` persists them. Physical model output was not manually re-accepted in this audit. |
| Conversation understanding / bounded recent context | PARTIALLY_IMPLEMENTED | `ConversationUnderstandingService` resolves limited references; preserved controller diff injects five history entries and three user memories. It does not establish durable task context or an authoritative owner profile. |
| Voice push-to-talk | IMPLEMENTED_BUT_NOT_REAL_WORLD_VERIFIED | Capture, STT, TTS, and playback classes are wired in `DesktopApplicationController.start_push_to_talk()` / `finish_push_to_talk()`. STT is CPU `base.en`; no physical microphone, full playback, Hindi, or Hinglish acceptance was observed in this audit. |
| Persistent voice mode | PARTIALLY_IMPLEMENTED | The uncommitted checkbox only changes state and enables TTS (`set_voice_mode()`); it never opens continuous capture, runs VAD/silence turn detection, or begins the next listening turn. Each turn still requires Push to talk. |
| Barge-in | IMPLEMENTED_BUT_BROKEN_FOR_VOICE_BARGE_IN | `BargeInCoordinator` can cancel generation/playback only after an explicit `stop_active()` UI action. No microphone speech detector calls it while TTS is speaking. |
| TTS profiles / custom clone | REAL_INSTALLED_SELECTION / MISSING_PROVIDER | `WindowsSpeechTTSProvider` enumerates installed System.Speech voices and `VoiceIdentityService` persists selection. It cannot characterize voice demographics, clone samples, or retain samples; custom voice is deliberately `UNSUPPORTED`. |
| Owner profile and creator grounding | MISSING_EXECUTION_PATH | Identity instruction explicitly says no creator/owner is configured (`VIRGO_IDENTITY_SYSTEM_INSTRUCTION`); preferences are generic key/value facts, not verified owner records. |
| Approved memory / controlled learning | REAL_AND_WORKING (bounded local path) | `SQLiteKnowledgeRepository.store()` admits only verified claims; `LearningEngine.learn_documents()` uses explicit permission then proposal/acceptance. External research is `NOT_CONFIGURED`. |
| Screen learning / screen observation | DECLARED_ONLY | No capture module, visual-input contract, vision provider, explicit Screen Learning Mode, or learning-summary path exists. `STEP_11_VISION_UX_PREVIEW.md` confirms this. |
| Desktop control | NOT_CONFIGURED / MISSING_PROVIDER | Registry has only unavailable `desktop.inspect`; `PersonalAIRuntime.resolve_capability()` returns NOT_AVAILABLE. No launcher, UI Automation, observation, or verifier exists. |
| Internet research | NOT_CONFIGURED | `KnowledgeOnDemandService` defaults to `UnconfiguredKnowledgeProvider`; `LearningEngine` uses `UnconfiguredResearchProvider`. |
| Browser navigation / interaction | NOT_CONFIGURED / MISSING_PROVIDER | Only unavailable `browser.read` registry metadata exists; no adapter or UI path. |
| Vision | NOT_CONFIGURED / MISSING_PROVIDER | No visual contract/provider. Installed Ollama models advertise completion/tools, thinking, or embeddings—not vision. |
| Image generation / editing | DECLARED_ONLY | `CreationCapabilityRouter` and `ModelSelector` classify image work but `UnconfiguredExternalProvider` has no execution provider; `image.generate` is NOT_CONFIGURED. |
| Video generation / editing | DECLARED_ONLY / MISSING_EXECUTION_PATH | A generation status exists, but no video editor route, provider, playable output, or verification. |
| Website/basic code creation | PARTIALLY_IMPLEMENTED | `ControlledCreationWorkflow`, `CreationCoordinator`, SafeWorkspace, staging/rollback, static templates, and one-file LLM proposal exist. It is an explicit workspace workflow, but requests from ordinary chat are not routed into it and it cannot plan/build/run/repair a multi-file app or agent. |
| Safe file inspection and fixed validation | REAL_AND_WORKING (bounded) | `files.inspect` and `code.validate` are available in `_tools()` and use `SafeWorkspace` / allowlisted validation. They are not general desktop/shell control. |
| Evidence / independent verification | PARTIALLY_IMPLEMENTED | `ResponseVerifier` correctly refuses verification without independent read-back. Most unavailable external capabilities therefore have no real verifier. |
| Backup/restore and storage measurement | REAL_AND_WORKING (bounded) | `DataBackupService` backs up only session/memory databases; repositories expose database sizes. UI only identifies archive candidates; cleanup implementation is limited to session deletion. |

## 4. Root-cause report

1. **Voice is not primary.** `ConversationView` presents a text field, Send button,
   Voice mode checkbox, and Push-to-talk together. Voice mode is state/TTS policy,
   not a capture loop. `FasterWhisperSTTProvider` hard-codes CPU/int8 and controller
   hard-codes `base.en`; no language routing, VAD, wake word, echo guard, or turn
   listener exists.
2. **Barge-in is a manual Stop button.** `BargeInCoordinator` is sound as an explicit
   cancellation primitive, but no capture/VAD event invokes it during `SPEAKING`.
3. **Conversation reset/generic identity.** Recent history is now passed in the
   preserved diff, but the system identity has no owner facts by design and the final
   prompt still depends on the selected model. There is no authoritative profile object
   or profile approval lifecycle.
4. **Viewport jumps.** `ConversationView.append_message()` and
   `append_assistant_chunk()` always call `ensureCursorVisible()`. This forces the
   bottom and can steal an intentional upward scroll; loading a session uses
   `setPlainText()` without an explicit bottom policy. The reported movement toward
   the beginning is not reproduced automatically, but the current code has no
   bottom-distance/user-scroll state and is therefore incapable of correct behavior.
5. **Desktop commands cannot execute.** Routing recognizes VS Code text only in the
   preserved diff, then maps it to unavailable `desktop.inspect`. Registry metadata
   does not invoke `ShellExecute`, Windows UI Automation, screen capture, or any
   observed postcondition.
6. **Screen learning does not exist.** There is no capture consent state, capture
   service, vision inference, action timeline, proposed lesson, or admission handoff.
7. **External capability claims are contracts, not providers.** Browser, research,
   image, and video use honest NOT_CONFIGURED paths; media routing stops before output.
8. **Creation falls back to chat/basic templates.** The conversation controller never
   converts a chat request into a creation workspace/task. The Creation UI selects
   only `static_landing_page_proposals()`, `stdlib_python_module_proposal()`, or a
   single approved operation; there is no project planner/executor loop.

## 5. Owner identity and persistence findings

The authoritative product identity is Virgo AI, correctly protected by
`build_virgo_system_instruction()`. Owner identity is absent by design: the same
instruction explicitly prevents invented creator claims. `personal_preferences` can
persist a preference under the literal scope key `user`, but it has no profile ID,
fact confidence/verification, source approval, correction history, or dedicated UI.
It must not be populated from arbitrary conversation text.

**Step 2 lock:** introduce one `OwnerProfile` authority with a stable local profile ID,
explicit owner approval, provenance, correction/forget actions, and safe prompt
projection. Keep it separate from untrusted session text and from Section 10's
verified-knowledge admissions; owner self-declared profile facts require their own
explicit consent, not model inference.

## 6. Voice-first findings

Preserve the existing capture/STT/orchestration/TTS/playback primitives. Replace only
the missing coordinator layer in Step 2: continuously owned microphone lifecycle,
speech/silence segmentation, cancellation-safe TTS completion, barge-in detector,
state transitions, and a language policy. `base.en` is not evidence of Hindi or
Hinglish support. Windows System.Speech only supports installed voices; no supplied
voice is presently known to meet the requested voice characterization.

## 7. Desktop and Screen Learning findings

Minimum bounded Windows desktop architecture: a provider interface for approved app
launch by registered executable/AppUserModelID, an explicit permission request,
foreground/window observation via Windows UI Automation, narrowly allowlisted input
actions, execution evidence, and an independent UIA/process read-back verifier. Do
not expose arbitrary shell execution.

Screen Learning must be a separate, visibly ON/OFF, owner-controlled session: select
scope/window -> capture frames only while ON -> vision interpretation as untrusted
data -> timeline/summary -> explicit proposal -> existing learning admission. No code
currently supports any part after the permission UI.

## 8. Memory, database, and learning findings

Persistent stores are limited to `sessions/virgo.sqlite3` (sessions, messages,
settings) and `memory/knowledge.sqlite3` (claims, evidence metadata, learning assets,
preferences). There is no capability registry database, owner profile store, screen
learning store, audit/evidence store, voice-sample store, or media/project store.
`DataBackupService` intentionally covers only the two databases. This is good privacy
scope, but Step 4 must extend persistence deliberately and update backup/restore,
storage reporting, inspection, retention, and deletion controls together.

## 9. Provider requirements

Observed local runtime: Ollama server is live; installed `qwen3:4b-instruct`,
`qwen3:4b`, `llama3.2`, and `embeddinggemma:300m-qat-q4_0` have no vision capability.
NVIDIA reports an RTX 2050 with 4096 MiB VRAM (driver 610.74). No model was downloaded.

| Step 5 feature | Required before a PASS claim |
|---|---|
| Vision/screen understanding | A typed image/frame provider, an explicitly installed vision-capable model tested on this 4-GB GPU or an owner-approved cloud provider, frame retention policy, and output/evidence verifier. |
| Research | Approved search/fetch provider, source allow/deny policy, freshness metadata, citation/provenance store, injection filtering, and independent factual verification. |
| Browser | Explicit browser automation runtime, owner-scoped profile, navigation/action policy, cancellation, screenshots/action evidence, and postcondition verifier. |
| Image generation | An explicitly selected local/remote image provider compatible with the 4-GB GPU or consented cloud budget, artifact staging, image file validation, preview, provenance, and no safety conflation for unavailable service. |
| Video generation/editing | Separate provider/adapters: generation produces an artifact; editing consumes a user-selected input and emits a distinct playable artifact. Both need codec/file validation, preview, provenance, cancellation, disk budget, and verification. Local video generation is not a realistic default on the observed 4-GB GPU; choose an owner-approved remote provider or defer. |

## 10. Creation findings

The existing bounded file workflow is valuable and must remain. It has explicit
workspace scope, preview, approval, atomic mutation/rollback, and validation hooks.
It does not produce a real multi-file project from chat. Step 6 should add a project
task authority above—not instead of—this workflow: approved workspace creation,
requirements plan, project manifest, file plan, iterative generator, bounded run/test
commands, preview, repair loop, artifact inventory, and final acceptance. Agent creation
must create and execute a real project artifact, never merely return agent prose.

## 11. UI information architecture and scroll findings

`StageOneScreens.SCREEN_NAMES` exposes Onboarding, Conversation, Sessions, Health,
Settings, Permissions, Diagnostics, Creation, Security, Learning, and Personal AI.
The navigation labels Personal AI as “Task context,” but ordinary use still leads into
many internal workspaces. The Conversation screen devotes equal structural prominence
to transcript, core orb, and live activity. No supplied Ghost/Virgo reference asset is
present in the repository, so visual comparison cannot be completed.

**Step 7 map:** make Conversation/Home the default and voice state/control primary;
make activity contextual and collapsed by default; move Health, Diagnostics, provider
status, and advanced task internals behind Settings/Advanced; keep Sessions accessible
but secondary; retain Creation/Security/Learning as explicit contextual workspaces.
Implement bottom-follow only when the scrollbar is within a small threshold of bottom;
set an “user reviewing history” flag on upward scroll; show a “new response” affordance
instead of moving the viewport; retain manual jump-to-latest.

## 12. Expected implementation surface, Steps 2–8

| Step | Primary modules expected to change/add |
|---|---|
| 2 | `apps/desktop/controller.py`, `apps/desktop/views/stage_one.py`, voice capture/transcription/playback, new voice-turn coordinator, conversation contracts/orchestrator, session/profile storage and tests. |
| 3 | New `virgo/providers/desktop/*`, contracts/models/events, capability registry/runtime, permission gate, controller/UI contextual approval, Windows verification tests. |
| 4 | New screen-capture/vision-learning contracts and provider boundary; `learning/engine.py`, `experience.py`, knowledge repository/schema, backup/storage services, controller/Learning view. |
| 5 | New provider packages/contracts for vision, research, browser, image, video/editing; capability registry/runtime, artifact staging, media verification, Settings/creation UI. |
| 6 | Creation planner/generation/workspace/validation/workflow, controller and Creation view, controlled process tooling, project artifact tests. |
| 7 | `stage_one.py`, `widgets/phase_two.py`, theme, controller view bindings, native UI tests; no intelligence authority moves into UI. |
| 8 | Acceptance/e2e/integration/security suites, live-provider evidence tooling, diagnostics and repair only where exercised failures prove need. |

## 13. Decisions requiring owner approval

1. Choose the authoritative owner-profile fields and the initial explicit onboarding
   approval flow; the repository has none.
2. Approve concrete providers, credentials/budget, data retention, and local-versus-
   cloud policy for vision, research/browser, image, video, and custom voice cloning.
3. Approve the bounded desktop-control action allowlist and whether UI Automation is
   permitted after app launch.
4. Provide or add the Ghost/Virgo visual reference to the repository before Step 7.
5. Reconcile the constitution's Stage 1 “continuous listening/barge-in” target with
   the historical closure docs claiming acceptance despite code that only provides PTT
   and manual Stop. This audit treats code as authoritative reality.

## 14. Recovery plan, Steps 2–8

1. **Step 2:** complete owner profile, current-turn/session context, voice-turn loop,
   language handling, TTS lifecycle, speech-triggered barge-in, and scroll policy;
   prove with native multi-turn voice acceptance.
2. **Step 3:** implement permissioned Windows launcher/observation/input provider;
   prove launch and verified bounded interaction with VS Code or another approved app.
3. **Step 4:** add explicit Screen Learning sessions and durable proposal/admission;
   prove ON/OFF, summary, approval, restart persistence, and cleanup.
4. **Step 5:** select/configure each provider one at a time; prove actual image,
   video generation, edited video, vision result, sourced research, and browser action.
5. **Step 6:** route creation intent to actual project workspaces; prove files,
   runnable preview, validation/repair, and an executable agent artifact.
6. **Step 7:** apply the conversation-first native redesign and scroll behavior after
   the voice and creation paths exist; verify against owner reference.
7. **Step 8:** run end-to-end acceptance against every advertised capability, retain
   evidence, correct failures, perform privacy/security regression, and obtain manual
   owner approval.

## 15. Risks and dependencies

- No feature may be marked complete from contracts, registry status, mocked tests, or
  UI controls alone.
- Physical audio, native UI, desktop control, browser, media, and provider tests need
  an owner-run/manual acceptance component in addition to automation.
- The current test environment initially denied pytest access to the default user Temp
  directory. Re-running with a workspace `--basetemp` began normally; do not interpret
  the initial 30 fixture errors as product failures.
- Provider/model downloads, cloud credentials, generated media, screenshots, and
  voice samples require their own consent, storage, cleanup, and backup policies.

## 16. STEP 1 COMPLETE: YES

## 17. READY FOR STEP 2: YES

Ready means architecture and gaps are locked for implementation. It does **not** mean
the requested Step 2 voice-first capability is already complete.
