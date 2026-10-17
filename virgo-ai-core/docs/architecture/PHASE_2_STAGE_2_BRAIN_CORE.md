# Phase 2 Stage 2 Brain Core

The authoritative path is:

1. User input and session identity enter conversation understanding.
2. `PersonalAIRuntime` builds bounded approved user context and selects an advisory
   cognitive strategy.
3. The configured-model router may select the user-selected available Ollama model.
   Models, including Qwen variants, remain reasoning providers without authorization.
4. Current-knowledge needs use Knowledge-on-Demand; capability needs use the registered
   Tool/Agent boundary with environment and existing permission/safety preflight.
5. Execution produces immutable structured evidence. `ResponseVerifier` separately
   evaluates observable postconditions and truthfully returns non-verified states when
   independent proof is unavailable.
6. Eligible verified outcomes may create controlled-learning candidates. The existing
   Section 10 memory admission authority alone controls persistence.
7. The desktop UI presents typed operational state and does not own intelligence.

The former PersonalAIRuntime self-verification path remains neutralized: executor or audit
success alone cannot produce `VERIFIED`. User-scoped approved preferences and sessions
survive repository reconstruction; transient interaction state is not persistent memory.

The selected local/Ollama model is placed first for cognitive routing, with no silent cloud
fallback. An unavailable model remains unavailable. Tier 0–4 authorization remains
`UNRESOLVED_DEFERRED` and has no authorization role.

External internet retrieval, unrestricted browser control, unrestricted desktop control,
image generation, and video generation remain deferred or not configured. Physical
microphone, speaker, audible voice quality, and human visual acceptance were not claimed
by automated acceptance.
