# Step 7 verification and controlled learning

`PersonalAIRuntime` remains the authoritative coordinator. Execution produces immutable
Step 6 evidence; `ResponseVerifier` separately evaluates a scoped claim. Executor,
planner, agent, provider, audit text, absence of errors, and Step 5 retrieval sufficiency
cannot alone produce `VERIFIED`.

The supported results are `VERIFIED`, `PARTIALLY_VERIFIED`, `UNVERIFIED`,
`CONFLICTING`, `FAILED`, `NOT_VERIFIABLE`, and `CANCELLED`. The deterministic success
path requires an independently invoked postcondition read-back matching the expected
postcondition. Missing read-back truthfully returns `NOT_VERIFIABLE`.

The former legacy runtime path no longer turns its own completion audit into passing
verification. It reports task completion separately from `NOT_VERIFIABLE` verification.

Eligible verified outcomes may create an unpersisted preference candidate. The candidate
has no authority and still requires the existing explicit user acceptance path, including
sensitivity and storage checks. Unverified and failed outcomes cannot create successful
learning candidates. No transient state, psychological inference, permission, safety
policy, tool registration, or model-selection authority is learned.

The existing Section 10 memory admission pipeline remains authoritative. Ollama/Qwen are
selectable reasoning providers, not Brain authority. Tier 0–4 authorization, external
retrieval, browser control, and desktop control remain deferred or not configured.
