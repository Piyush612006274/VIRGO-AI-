# Step 9 real-world capabilities

`PersonalAIRuntime` remains the authoritative coordinator and now exposes two additional
existing local authorities through the Step 6 registry:

- `files.inspect` uses `SafeWorkspace` for bounded read-only inspection and UTF-8 reads
  inside an explicit workspace. Traversal, sensitive filenames, size limits, and
  sensitive-looking evidence are blocked.
- `code.validate` uses `ValidationProcessTool` for fixed allowlisted validation commands
  with exact task permission, separated arguments, an explicit workspace, timeout,
  cancellation, and bounded redacted output. It is not arbitrary shell access.

File creation, editing, deletion-with-backup, validation, rollback, and acceptance remain
owned by the existing permissioned Creation workflow. Diagnostics, security analysis,
sessions, voice, learning, and configured local/Ollama model selection reuse their
existing authorities. Executor success remains separate from independent verification,
and capability output is not automatically persisted as memory.

External web research remains `NOT_CONFIGURED_DEFERRED`: no approved configured research
provider exists. Controlled browser interaction and desktop interaction remain
`NOT_CONFIGURED_NOT_AVAILABLE`: the repository has registry placeholders but no bounded
provider. Image/video and absent personal-service providers are not built in Step 9.

Tier 0–4 remains `UNRESOLVED_DEFERRED`. Existing ActionRisk, ToolRiskLevel, permission,
safety, and user-selected Ollama/Qwen behavior are unchanged. There is no silent cloud
fallback, unrestricted shell, autonomous browser, desktop takeover, or automatic memory
write.
