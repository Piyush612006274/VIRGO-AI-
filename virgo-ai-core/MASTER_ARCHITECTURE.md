# VIRGO AI — MASTER ARCHITECTURE AND IMPLEMENTATION CONSTITUTION

**Document role:** Single source of truth
**Project name:** Virgo AI
**Implementation operator:** Codex
**Human role:** Requirements approval, testing, permissions and final acceptance
**Development model:** Stage-based, test-driven and evidence-based
**Primary operating model:** Local-first desktop personal AI

---

# 1. Core Mission

Virgo AI एक original, local-first, voice-enabled, multimodal और tool-capable personal AI system होगा।

Virgo को केवल किसी cloud AI API का graphical client नहीं बनाना है। System की अपनी application intelligence होगी, जिसमें शामिल होंगे:

* conversation orchestration
* voice interaction
* memory
* skills
* tool execution
* task planning
* model routing
* verification
* learning
* controlled self-improvement
* user permissions
* failure recovery

External APIs optional providers होंगे। वे Virgo की core identity या architecture नहीं होंगे।

---

# 2. Non-Negotiable Technology Stack

Virgo के production application stack में केवल दो primary programming languages होंगी:

## 2.1 Rust

Rust का प्रयोग performance-critical, security-sensitive और system-level functionality के लिए होगा।

Rust responsibilities:

* high-performance core runtime
* process management
* secure command execution
* operating-system integration
* file-system safety
* resource monitoring
* permission enforcement
* encryption helpers
* high-performance audio utilities
* hardware detection
* sandbox support
* rollback primitives
* critical validation

## 2.2 Python

Python मुख्य application और intelligence language होगी।

Python responsibilities:

* desktop UI
* AI orchestration
* voice pipeline
* model integration
* memory
* tools
* skills
* agents
* learning
* task planning
* prompt management
* document processing
* image and video workflows
* website development workflows
* defensive security workflows
* testing and verification orchestration

## 2.3 Desktop UI

Desktop interface के लिए:

* **PySide6**
* Qt-based native desktop application
* Python-controlled UI
* no React
* no Node.js
* no Electron
* no JavaScript frontend runtime
* no browser-dependent primary interface

Django और Flask primary desktop UI frameworks नहीं होंगे।

भविष्य में local API या browser dashboard की आवश्यकता होने पर FastAPI का उपयोग किया जा सकता है, लेकिन वह desktop interface का replacement नहीं होगा।

---

# 3. Architecture Principles

Virgo को modular monolith के रूप में शुरू किया जाएगा।

Stage 1 में microservices नहीं बनाए जाएंगे।

हर module की:

* एक स्पष्ट responsibility होगी
* public interface defined होगा
* internal implementation isolated होगी
* independent tests होंगे
* structured errors होंगे
* logging होगा
* dependency direction fixed होगी

कोई module दूसरे module की internal files directly import नहीं करेगा।

Communication केवल documented interfaces से होगी।

---

# 4. High-Level Architecture

```text
Virgo Desktop Application
│
├── Presentation Layer
│   └── PySide6 Desktop UI
│
├── Application Layer
│   ├── Session Controller
│   ├── Conversation Controller
│   ├── Voice Controller
│   ├── Task Controller
│   └── Permission Controller
│
├── Intelligence Layer
│   ├── AI Orchestrator
│   ├── Intent Router
│   ├── Planner
│   ├── Context Builder
│   ├── Model Router
│   ├── Response Verifier
│   └── Safety Policy Engine
│
├── Capability Layer
│   ├── Voice Engine
│   ├── Memory Engine
│   ├── Skills Engine
│   ├── Tools Engine
│   ├── Agent Engine
│   ├── Learning Engine
│   ├── Creation Engine
│   └── Security Analysis Engine
│
├── Provider Layer
│   ├── Local LLM Provider
│   ├── STT Providers
│   ├── TTS Providers
│   ├── Image Providers
│   ├── Video Providers
│   └── Optional Cloud Providers
│
├── Infrastructure Layer
│   ├── Configuration
│   ├── Storage
│   ├── Logging
│   ├── Events
│   ├── Background Jobs
│   ├── Recovery
│   └── Updates
│
└── Rust Core
    ├── Secure Execution
    ├── Process Control
    ├── OS Integration
    ├── Resource Monitoring
    ├── File Safety
    ├── Encryption
    ├── Audio Utilities
    ├── Sandbox
    └── Rollback Support
```

---

# 5. Required Repository Structure

```text
virgo-ai/
│
├── MASTER_ARCHITECTURE.md
├── README.md
├── pyproject.toml
├── Cargo.toml
├── .env.example
├── .gitignore
├── LICENSE
│
├── apps/
│   └── desktop/
│       ├── main.py
│       ├── bootstrap.py
│       ├── windows/
│       ├── widgets/
│       ├── views/
│       ├── viewmodels/
│       ├── themes/
│       └── assets/
│
├── virgo/
│   ├── application/
│   │   ├── sessions/
│   │   ├── conversation/
│   │   ├── voice/
│   │   ├── tasks/
│   │   └── permissions/
│   │
│   ├── intelligence/
│   │   ├── orchestrator/
│   │   ├── intent/
│   │   ├── planner/
│   │   ├── context/
│   │   ├── routing/
│   │   ├── verification/
│   │   └── safety/
│   │
│   ├── capabilities/
│   │   ├── voice/
│   │   ├── memory/
│   │   ├── skills/
│   │   ├── tools/
│   │   ├── agents/
│   │   ├── learning/
│   │   ├── creation/
│   │   └── security/
│   │
│   ├── providers/
│   │   ├── llm/
│   │   ├── stt/
│   │   ├── tts/
│   │   ├── image/
│   │   ├── video/
│   │   └── cloud/
│   │
│   ├── infrastructure/
│   │   ├── config/
│   │   ├── storage/
│   │   ├── logging/
│   │   ├── events/
│   │   ├── jobs/
│   │   ├── recovery/
│   │   └── updates/
│   │
│   └── contracts/
│       ├── models/
│       ├── protocols/
│       ├── events/
│       └── errors/
│
├── rust-core/
│   ├── Cargo.toml
│   ├── src/
│   │   ├── lib.rs
│   │   ├── execution/
│   │   ├── process/
│   │   ├── filesystem/
│   │   ├── permissions/
│   │   ├── security/
│   │   ├── resources/
│   │   ├── audio/
│   │   ├── sandbox/
│   │   └── rollback/
│   └── tests/
│
├── data/
│   ├── runtime/
│   ├── memory/
│   ├── sessions/
│   ├── skills/
│   ├── models/
│   ├── generated/
│   └── backups/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── end_to_end/
│   ├── security/
│   ├── performance/
│   └── acceptance/
│
├── scripts/
│   ├── bootstrap/
│   ├── development/
│   ├── verification/
│   └── packaging/
│
└── docs/
    ├── decisions/
    ├── interfaces/
    ├── testing/
    └── operations/
```

`MASTER_ARCHITECTURE.md` project authority होगा।

README केवल setup, run और current status बताएगा।

Architecture संबंधी conflicting instructions मिलने पर Master Architecture को follow किया जाएगा।

---

# 6. Rust–Python Integration

Rust core को Python से expose करने के लिए PyO3 और maturin का प्रयोग किया जाएगा।

```text
Python Application
        │
        ▼
Typed Python Wrapper
        │
        ▼
PyO3 Interface
        │
        ▼
Rust Core
        │
        ▼
Operating System
```

Rules:

* UI सीधे Rust functions call नहीं करेगी।
* Python application services typed wrapper के माध्यम से Rust access करेंगी।
* Rust errors structured error codes में return होंगे।
* Python wrapper errors को application exceptions में convert करेगा।
* Long operations UI thread block नहीं करेंगी।
* Rust boundary पर input validation mandatory होगी।
* Unsafe Rust केवल documented technical necessity पर allowed होगा।
* हर unsafe block के साथ justification और tests आवश्यक होंगे।

---

# 7. Desktop UI Architecture

Virgo UI original होगी।

किसी existing AI interface की:

* exact layout copy नहीं होगी
* branding copy नहीं होगी
* orb copy नहीं होगी
* animation copy नहीं होगी
* color system copy नहीं होगा
* assets copy नहीं होंगे

UI qualities:

* clean
* futuristic
* calm
* voice-focused
* responsive
* accessible
* hardware-efficient
* keyboard-friendly
* visually original

## 7.1 Primary Screens

Stage 1 में:

* onboarding
* main conversation screen
* voice interaction state
* text chat
* session history
* provider health
* settings
* permissions
* logs and diagnostics
* model selection
* microphone and speaker selection

Future stages में:

* task workspace
* creation studio
* agent dashboard
* security workspace
* learning center
* self-improvement review
* automation manager

## 7.2 UI States

Voice interface में स्पष्ट states होंगे:

```text
IDLE
LISTENING
PROCESSING_SPEECH
THINKING
RESPONDING
SPEAKING
INTERRUPTED
RECOVERING
ERROR
OFFLINE
```

UI state अनुमान से नहीं, application events से update होगी।

---

# 8. Voice System

Stage 1 का मुख्य acceptance feature real voice conversation है।

Required flow:

```text
Microphone Input
→ Audio Capture
→ Voice Activity Detection
→ Speech-to-Text
→ Intent and Context Processing
→ Local AI Response
→ Streaming Text
→ Text-to-Speech
→ Audio Playback
→ Continuous Listening
```

Required capabilities:

* microphone selection
* speaker selection
* push-to-talk
* optional wake word
* continuous listening
* silence detection
* partial transcription
* final transcription
* streaming response
* streaming or sentence-based TTS
* playback cancellation
* barge-in
* echo prevention
* reconnect
* offline error reporting
* provider health checks

## 8.1 Barge-In

जब user Virgo के बोलते समय बोलना शुरू करे:

1. playback तुरंत stop हो
2. current TTS job cancel हो
3. remaining response marked interrupted हो
4. microphone capture active हो
5. new speech transcribe हो
6. conversation context interruption को record करे
7. नया response generate हो

---

# 9. Model Strategy

## 9.1 Local-First Rule

Local models primary होंगे।

Initial provider priorities:

* local LLM through Ollama
* local STT
* local or operating-system TTS
* local embeddings
* local reranking where practical

Cloud providers optional fallbacks होंगे।

Cloud provider बिना user configuration और consent के activate नहीं होगा।

## 9.2 Model Router

Model Router निम्न factors के आधार पर model चुनेगा:

* task type
* available hardware
* model availability
* latency
* context size
* privacy
* cost
* quality requirement
* offline status
* user preference

## 9.3 Fallback Policy

Fallback का अर्थ silent cloud switching नहीं होगा।

```text
Primary provider fails
→ retry policy
→ health recheck
→ compatible local fallback
→ request permission for cloud fallback
→ execute only after consent
→ report provider used
```

---

# 10. Memory Architecture

Memory केवल complete chat history नहीं होगी।

Memory types:

* current working context
* session memory
* user-approved long-term memory
* preferences
* task memory
* project memory
* learned skills
* tool outcomes
* failure history

Memory pipeline:

```text
New Information
→ Sensitivity Check
→ Relevance Check
→ Duplicate Check
→ User Permission when required
→ Structured Storage
→ Embedding
→ Retrieval Index
```

Rules:

* sensitive information automatically store नहीं होगी
* memory inspectable होगी
* memory editable होगी
* memory deletable होगी
* source traceable होगा
* low-confidence facts clearly marked होंगे
* retrieval result context limits के अनुसार filtered होगा

---

# 11. Skills System

Skill एक structured reusable capability होगी।

हर skill में:

* unique identifier
* name
* description
* input schema
* output schema
* required tools
* required permissions
* execution instructions
* validation rules
* failure handling
* version
* source
* tests

Skill execution सीधे arbitrary prompt से नहीं होगी।

```text
Intent
→ Skill Match
→ Input Validation
→ Permission Check
→ Execution
→ Output Validation
→ Result
```

---

# 12. Tools System

हर external action एक registered tool के माध्यम से होगी।

Tool contract:

```text
Tool Name
Description
Input Schema
Output Schema
Permission Level
Risk Level
Timeout
Cancellation Support
Validation
Audit Logging
Rollback Support
```

Tool risk categories:

* read-only
* low-risk write
* reversible write
* high-impact action
* prohibited action

High-impact actions हमेशा explicit approval मांगेंगी।

Examples:

* file modification
* process execution
* package installation
* system settings changes
* account operations
* deployment
* publishing
* sending external requests
* deleting data
* security testing

---

# 13. Permission System

Permission decisions UI में clear language में दिखेंगे।

Permission request बताएगा:

* Virgo क्या करना चाहता है
* क्यों करना चाहता है
* कौन-से files या systems प्रभावित होंगे
* action reversible है या नहीं
* expected result क्या है
* rollback available है या नहीं

Permission options:

* allow once
* allow for current task
* deny
* inspect plan
* modify scope

Permanent blanket permission sensitive tools के लिए allowed नहीं होगी।

---

# 14. Five-Stage Development Plan

# Stage 1 — Voice Foundation

Goal: Virgo user से natural voice और text conversation कर सके।

Required deliverables:

* PySide6 desktop application
* original conversation UI
* Rust core skeleton
* Python–Rust integration
* configuration system
* structured logging
* local model provider
* real microphone input
* speech-to-text
* AI response
* text-to-speech
* audio playback
* continuous listening
* barge-in
* text chat
* session history
* persisted settings
* provider health
* recovery and reconnect
* model selection
* basic conversation memory
* unit tests
* integration tests
* live end-to-end tests
* installation instructions
* packaging proof

Stage 1 explicitly excludes:

* website generation
* image generation
* video generation
* security tools
* autonomous learning
* self-modification
* browser automation
* desktop automation
* multi-agent workflows

Stage 1 acceptance test:

```text
User starts Virgo
→ selects local providers
→ speaks a question
→ speech is transcribed
→ local model answers
→ answer appears incrementally
→ Virgo speaks the answer
→ user interrupts
→ playback stops
→ Virgo listens again
→ session persists after restart
```

---

# Stage 2 — Creation and Development Engine

Goal: Virgo practical digital creation tasks perform कर सके।

Capabilities:

* task planning
* task decomposition
* website development
* frontend generation
* backend generation
* application development support
* file editing
* project analysis
* coding assistance
* code testing
* website analytics
* SEO analysis
* WordPress workflows
* Shopify workflows
* image generation
* image editing
* image enhancement
* video generation
* prompt enrichment
* model selection
* output verification
* preview
* rollback
* approval before file writes or deployment

Creation workflow:

```text
Understand Intent
→ Ask Missing Requirements
→ Create Plan
→ Select Skills and Tools
→ Ask Permission
→ Generate
→ Validate
→ Test
→ Preview
→ Accept or Rollback
→ Report
```

Generated output को केवल API response receive होने के कारण successful नहीं माना जाएगा।

Verification आवश्यक होगी।

---

# Stage 3 — Defensive Cybersecurity and System Intelligence

Goal: Virgo authorized defensive security assistant बने।

Allowed areas:

* system diagnostics
* log analysis
* network visibility
* vulnerability assessment
* configuration auditing
* secure code review
* malware indicators analysis
* dependency scanning
* defensive Linux administration
* defensive Windows administration
* lab-based tool assistance
* authorized penetration-testing workflows
* report generation
* remediation guidance

Potential tools may include:

* Wireshark
* Nmap
* approved vulnerability scanners
* password auditing tools
* security testing frameworks
* system-native diagnostics

Rules:

* only authorized systems
* scope must be explicit
* target ownership must be confirmed
* destructive actions prohibited by default
* credential attacks cannot run without strict authorization
* public-target attacks prohibited
* stealth, persistence or evasion behavior prohibited
* all execution audited
* safe mode default
* dry run preferred
* remediation included

Security workflow:

```text
Define Authorized Scope
→ Select Defensive Objective
→ Build Plan
→ Risk Review
→ Ask Permission
→ Execute Safely
→ Collect Evidence
→ Analyze
→ Recommend Fixes
→ Verify Fixes
→ Produce Report
```

---

# Stage 4 — Controlled Learning and Self-Improvement

Goal: Virgo information, outcomes और approved sources से improve कर सके।

Learning sources:

* user-provided documents
* approved websites
* approved GitHub repositories
* technical documentation
* task outcomes
* corrected responses
* validated skills
* approved educational media transcripts

Learning does not mean uncontrolled model weight modification.

Learning outputs may include:

* indexed knowledge
* structured notes
* reusable skills
* updated tool guidance
* memory entries
* evaluation datasets
* improvement proposals

## 14.4.1 Self-Inspection

Virgo अपने codebase का:

* static analysis
* dependency review
* architecture compliance review
* performance review
* security review
* test coverage review
* failure analysis

कर सकता है।

## 14.4.2 Self-Modification Workflow

Mandatory loop:

```text
Inspect
→ Identify Problem
→ Research
→ Prepare Proposal
→ Estimate Risk
→ Ask Permission
→ Create Backup or Branch
→ Modify Limited Scope
→ Run Tests
→ Run Security Checks
→ Verify Behavior
→ Compare Before and After
→ Accept or Rollback
→ Report Everything
```

Virgo स्वयं production code silently modify नहीं करेगा।

Virgo अपने safety, permission, audit, rollback या verification systems को disable नहीं कर सकता।

---

# Stage 5 — Production Personal AI Platform

Goal: Virgo reliable daily-use personal AI system बने।

Capabilities:

* production desktop application
* local/private operation
* voice, text, image and video interaction
* long-term personal memory
* personalization
* specialized agents
* research workflows
* coding workflows
* productivity workflows
* controlled browser tools
* controlled desktop tools
* safe file and application control
* automation
* hardware-aware execution
* offline operation where possible
* provider routing
* privacy controls
* encrypted storage
* diagnostics
* updates
* backup and restore
* deployment-ready packaging
* outcome-based verification
* failure tracking

---

# 15. Agent Architecture

Agents Stage 4 से पहले independently autonomous नहीं होंगे।

Agent types:

* research agent
* coding agent
* creation agent
* system diagnostic agent
* defensive security agent
* productivity agent
* verification agent

Every agent must have:

* objective
* scope
* budget
* time limit
* tool allowlist
* permission boundary
* stop conditions
* verifier
* audit trail

Agents user-defined scope से बाहर नहीं जाएंगे।

---

# 16. Error and Recovery Model

हर error structured होगा।

Required fields:

* error code
* category
* message
* technical detail
* user-safe explanation
* recoverable status
* retry advice
* source module
* correlation ID

Failure categories:

* configuration
* provider unavailable
* model unavailable
* audio device failure
* timeout
* permission denied
* validation failure
* tool failure
* storage failure
* Rust-core failure
* security violation
* unknown internal failure

Recovery order:

```text
Detect
→ Contain
→ Cancel Unsafe Work
→ Preserve State
→ Retry if Safe
→ Use Approved Fallback
→ Restore Last Stable State
→ Inform User
→ Record Diagnostic Evidence
```

---

# 17. Logging and Audit

Logging must be structured.

Log levels:

* debug
* info
* warning
* error
* critical
* audit

Logs must never expose:

* passwords
* API keys
* authentication tokens
* private audio by default
* private memory contents
* full sensitive documents

Every tool execution records:

* requester
* task
* tool
* inputs summary
* permission
* start time
* end time
* result
* files changed
* rollback status

---

# 18. Storage

Initial local storage:

* SQLite for structured application data
* local files for generated artifacts
* vector storage selected through an abstraction
* encrypted secret storage
* versioned schemas
* migration support

No storage implementation may be hardcoded directly into UI or intelligence modules.

---

# 19. Performance Rules

React हटाना अकेले performance guarantee नहीं है।

Performance control must include:

* no blocking work on UI thread
* async background jobs
* bounded queues
* model warm-up
* streaming
* cancellation
* memory limits
* context limits
* lazy loading
* hardware detection
* quantized local models
* cache management
* process supervision
* provider timeouts
* CPU/GPU monitoring

Performance metrics:

* startup time
* microphone activation latency
* transcription latency
* first-token latency
* full-response latency
* TTS start latency
* interruption latency
* memory usage
* CPU usage
* GPU usage
* crash rate

---

# 20. Security Boundaries

Mandatory protections:

* least privilege
* input validation
* path validation
* command allowlisting
* argument-safe process execution
* no shell interpolation by default
* secrets isolation
* encrypted credentials
* sandbox where practical
* explicit permission
* audit logs
* timeouts
* cancellation
* backups
* rollback
* dependency scanning
* signed release strategy

Virgo must never:

* silently execute dangerous actions
* hide actions from user
* disable permission controls
* remove audit evidence
* modify its own safety policy
* claim a task succeeded without verification
* fabricate tool results
* store secrets in source control
* execute untrusted code outside an approved sandbox
* attack systems without explicit authorization

---

# 21. Testing Strategy

Every feature must include tests.

Required test layers:

## Unit Tests

Single class, function or module behavior.

## Contract Tests

Python interfaces, providers and Rust boundary compatibility.

## Integration Tests

Multiple modules working together.

## End-to-End Tests

Real user flow through UI, voice, model and playback.

## Security Tests

Permissions, validation, path traversal, command injection and secret handling.

## Performance Tests

Latency, memory, cancellation and sustained operation.

## Acceptance Tests

Stage requirements verified against observable evidence.

Mocks may test failure behavior, but mocks cannot prove a real provider works.

Real microphone, STT, LLM and TTS acceptance requires live testing.

---

# 22. Definition of Done

A task is complete only when all applicable conditions are satisfied:

```text
Requirement understood
→ Architecture respected
→ Code implemented
→ Types and contracts defined
→ Errors handled
→ Tests written
→ Tests passed
→ Security checked
→ Live behavior verified
→ Documentation updated
→ Evidence recorded
→ Git commit created
```

A stage is not complete because:

* files exist
* UI looks complete
* mocked tests pass
* placeholders exist
* provider interfaces exist
* code compiles
* Codex reports success

A stage is complete only when its real acceptance tests pass.

---

# 23. Codex Operating Rules

Codex must follow these rules on every task.

## Before Coding

1. Read `MASTER_ARCHITECTURE.md`.
2. Inspect current repository state.
3. Identify current stage.
4. Confirm task belongs to current stage.
5. Inspect relevant existing modules.
6. Reuse valid code.
7. Prepare a limited implementation plan.
8. Identify tests before modification.

## During Coding

1. Make the smallest coherent change.
2. Maintain module boundaries.
3. Do not create duplicate implementations.
4. Do not silently change public interfaces.
5. Do not replace working components without evidence.
6. Do not add a new framework without architectural need.
7. Do not add React, Node.js, Electron or JavaScript UI.
8. Keep UI thread non-blocking.
9. Use typed models and interfaces.
10. Add structured errors.
11. Add cancellation and timeout for long operations.
12. Add tests with implementation.
13. Never fabricate completion.

## After Coding

1. Run formatting.
2. Run static analysis.
3. Run unit tests.
4. Run integration tests.
5. Run applicable live verification.
6. Run security checks.
7. Record changed files.
8. Record test commands and results.
9. Record limitations.
10. Update documentation only where needed.
11. Commit one logical responsibility per commit.

---

# 24. Codex Prohibited Behaviors

Codex must not:

* rewrite the whole repository unnecessarily
* generate duplicate folders
* create alternate project roots
* introduce unrelated workspaces
* bypass the Master Architecture
* declare a stage complete without evidence
* use mocks as proof of real functionality
* install random dependencies
* leave dead code
* leave placeholder production methods
* swallow exceptions silently
* hardcode credentials
* mix UI, domain logic and infrastructure
* directly execute model-generated shell strings
* continue after failed verification
* remove failing tests to obtain a green result
* modify past migrations destructively
* implement future-stage features early
* create uncontrolled self-modification

---

# 25. Git Rules

Git is the canonical version-control system.

MASTER_ARCHITECTURE.md is the architectural source of truth.

If repository code conflicts with MASTER_ARCHITECTURE.md, implementation must stop until the conflict is resolved.

Rules:

* one repository
* one valid project root
* no duplicate extracted copies
* protected main branch
* feature branches
* small logical commits
* meaningful commit messages
* no secrets
* no generated model files
* no runtime memory database
* no personal data
* tests before merge
* rollback through Git plus application backups

Suggested commit format:

```text
type(scope): concise description
```

Types:

* feat
* fix
* refactor
* test
* docs
* build
* security
* perf
* chore

---

# 26. Dependency Rules

A dependency may be added only when:

* existing standard library is insufficient
* project does not already provide equivalent functionality
* dependency is actively maintained
* license is acceptable
* security risk is reviewed
* package size is justified
* purpose is documented
* dependency is pinned appropriately

Heavy frameworks must not be added for small features.

---

# 27. Decision Priority

When instructions conflict, use this priority:

1. User safety and legal boundaries
2. Approved Master Architecture
3. Explicit current user instruction that does not conflict with the architecture
4. Current-stage acceptance criteria
5. Module contracts
6. Existing implementation
7. Convenience

Architectural changes require explicit approval and an Architecture Decision Record.

---

# 28. Initial Implementation Sequence

Codex must begin in this order:

## Step 1

Create clean repository structure.

## Step 2

Set up Python project, dependency management, formatting, linting and tests.

## Step 3

Set up Rust workspace, tests and Python binding build.

## Step 4

Create shared contracts, errors, configuration and logging.

## Step 5

Create minimal PySide6 application shell.

## Step 6

Create application event and state system.

## Step 7

Create audio device discovery and microphone capture.

## Step 8

Integrate real STT provider.

## Step 9

Integrate local Ollama-compatible LLM provider.

## Step 10

Implement conversation orchestration and streaming.

## Step 11

Integrate real TTS and playback.

## Step 12

Implement barge-in and cancellation.

## Step 13

Implement sessions, history and persisted settings.

## Step 14

Implement provider health, recovery and diagnostics.

## Step 15

Complete Stage 1 acceptance tests.

Codex must not begin Stage 2 before Stage 1 acceptance evidence is approved.

---

# 29. Stage 1 Completion Evidence

Codex must produce:

* repository tree
* setup commands
* run commands
* dependency list
* Rust build result
* Python–Rust integration result
* unit-test report
* integration-test report
* end-to-end test report
* provider health output
* microphone test
* STT transcript proof
* local model response proof
* TTS playback proof
* interruption proof
* restart persistence proof
* known limitations
* final commit hash

Without this evidence, Stage 1 remains incomplete.

---

# 30. Final Product Definition

Virgo AI का final product:

* original होगा
* local-first होगा
* desktop-native होगा
* Rust और Python आधारित होगा
* voice-first लेकिन text-capable होगा
* multimodal होगा
* memory-driven होगा
* tool-capable होगा
* permission-controlled होगा
* defensive-security aware होगा
* controlled learning करेगा
* controlled self-improvement करेगा
* failures verify और recover करेगा
* user के अधिकार और privacy के अंदर काम करेगा

---

# 31. One-Line Goal

**Virgo AI एक original, local-first, Rust-and-Python-based personal desktop intelligence system होगा, जो voice, memory, creation tools, defensive security, multimodal generation और controlled self-learning को सुरक्षित, testable और user-controlled architecture में एकीकृत करेगा।**

---

# 32. Codex Start Command

Codex को project शुरू करते समय यह instruction दिया जाए:

```text
Read MASTER_ARCHITECTURE.md completely before modifying the repository.

Start from a clean repository and implement only Stage 1.

Do not add React, Node.js, Electron or a JavaScript UI.

Use Rust for the secure performance-critical core, Python for intelligence and orchestration, and PySide6 for the desktop interface.

Work in the exact Initial Implementation Sequence defined in the Master Architecture.

For each step:
1. inspect the repository,
2. state the limited plan,
3. implement the smallest valid change,
4. add tests,
5. run verification,
6. report evidence,
7. create one logical Git commit.
```

# 33. Project Vision
## 33.1 Vision

Virgo AI का उद्देश्य केवल एक AI chatbot बनाना नहीं है।

Virgo AI एक complete, local-first, desktop-native intelligent operating companion होगा जो user के साथ natural voice conversation कर सके, tasks समझ सके, create कर सके, सीख सके, सुरक्षित तरीके से system के साथ interact कर सके और समय के साथ controlled तरीके से बेहतर होता जाए।

Virgo किसी existing AI की copy नहीं होगा।

Virgo का हर component original architecture पर आधारित होगा।

## 33.2 Long-Term Goals

Virgo eventually should become capable of:

Natural real-time voice conversation
Long-term memory
Personalization
Website development
Application development
Image generation
Video generation
Document understanding
Coding assistance
Research assistance
Defensive cybersecurity
Local automation
Desktop automation
Browser automation
Self-analysis
Controlled self-improvement
Offline-first execution
Hardware-aware optimization
## 33.3 Design Philosophy

Virgo follows these principles:

Local First
Privacy First
Voice First
User Control First
Modular Design
Test Before Claim
Permission Before Action
Verification Before Completion
Recovery Before Failure
Simplicity Over Complexity
# 34. Coding Standards
Every source file must follow consistent standards.

## 34.1 General Rules
Small focused classes
Small focused functions
Single Responsibility Principle
Type hints everywhere
Clear naming
No magic numbers
No duplicated logic
Structured errors
Logging where required
No commented dead code
## 34.2 Python Standards
PEP 8
Black formatting
Ruff linting
mypy typing
dataclasses or Pydantic where appropriate
async only when needed
## 34.3 Rust Standards
Rust stable channel
Clippy clean
rustfmt clean
No unnecessary unsafe
Document every unsafe block
# 35. Naming Convention
Folders

snake_case

Python

snake_case.py

Rust

snake_case.rs

Classes

PascalCase

Functions

snake_case()

Constants

UPPER_CASE

Enums

PascalCase

Interfaces / Protocols

DescriptiveNameProtocol
# 36. Dependency Policy
No dependency may be added without justification.

Before adding any package Codex must verify:

actively maintained
acceptable license
low security risk
justified package size
no existing duplicate functionality
architecture compatible

Large frameworks must never be added for a small feature.

# 37. Architecture Decision Records (ADR)
Any architectural change requires an ADR.

Each ADR must contain:

Title

Problem

Current Architecture

Proposed Change

Alternatives Considered

Pros

Cons

Migration Plan

Rollback Plan

Decision

Approval Status

No architectural change may occur without approval.

# 38. Codex Development Rules
Before every task Codex must:

Read MASTER_ARCHITECTURE.md
Identify current stage
Verify task belongs to current stage
Inspect existing implementation
Avoid duplicate work
Produce a small implementation plan

During development:

Never skip tests
Never skip verification
Never ignore failures
Never modify unrelated modules
Never refactor without reason
Never change architecture silently

After development:

Run formatter
Run linter
Run tests
Verify manually if required
Report changed files
Report limitations
Create one logical commit
# 39. Commit Policy
Every commit must represent exactly one logical change.

Allowed commit prefixes:

feat
fix
refactor
docs
test
build
perf
security
style
chore

Example:

feat(voice): add microphone device detection

Never combine multiple unrelated changes in one commit.

# 40. Repository Rules
The repository must always remain production quality.

Never allow:

duplicate folders
temporary workspaces
extracted repositories
copied projects
unused files
abandoned modules
placeholder production code
broken imports

Every file in the repository must have a purpose.

# 41. Final Constitution
This document is the official constitution of Virgo AI.

Every implementation, refactor, feature, test, architectural decision, and future development must comply with this document.

If any instruction conflicts with this document, work must stop until the conflict is resolved.

No implementation is considered complete unless it satisfies the architecture, testing, verification, security, and approval requirements defined in this constitution.

Do not declare Stage 1 complete until every Stage 1 acceptance test and evidence requirement passes with real providers.

# 42. Architecture Versioning

**Architecture Version:** 1.0.0

**Status:** Approved

**Architecture Owner:** Project Owner

**Final Approver:** Project Owner

**Implementation Authority:** Codex

**Codex may modify this document:** No, unless explicitly instructed by the Project Owner.

**Review Required:** Before every major stage

**Next Review:** Before Stage 2 begins

**Last Updated:** 2026-08-01

---

## 42.1 Approval Recording

Every approved architecture change must record:

- Architecture version
- Approval date
- Approved by
- Change summary
- Reason for change
- Related ADR reference

---

## 42.2 Version History

| Version | Date | Status | Summary |
|---------|------|--------|---------|
| 1.0.0 | 2026-08-01 | Approved | Initial Virgo AI Master Architecture Constitution |

---

## 42.3 Architecture Status

This document is frozen as Version 1.0.0.

No architectural changes may be made unless explicitly approved by the Project Owner.

Implementation must follow this document exactly.

Any deviation requires:
1. An Architecture Decision Record (ADR)
2. Project Owner approval
3. Version history update
4. Approval recording update

# 43. AI Personality Specification

## 43.1 Personality

### Tone

- Professional
- Calm
- Natural
- Helpful
- Honest
- Never fabricate information
- Never pretend success
- Always admit uncertainty
- Always ask permission before dangerous actions
- Never overwhelm the user
- Voice should feel conversational instead of robotic

# 44. Configuration Policy

The following settings may be configurable within approved safe limits:

- Providers
- Models
- Voice
- Wake Word
- Memory Limits
- Context Size
- GPU Usage
- CPU Usage
- Theme
- Logging Levels
- Feature Flags
- Permission Preferences for low-risk actions
- Security strictness within approved minimum safety limits

The following are NOT runtime configurable:

- Core architecture
- Constitutional rules
- Mandatory permission checks for dangerous actions
- Audit logging requirements
- Safety boundaries
- Rollback requirements
- Verification requirements
- Prohibited-action rules
- Security minimums

# 45. Change Management Policy

## 45.1 Purpose

This policy defines how changes to the Virgo AI architecture, implementation rules, and constitutional documents must be proposed, reviewed, approved, implemented, and recorded.

No architectural change may bypass this process.

---

## 45.2 Types of Changes

### Patch Change (x.x.1)

Used for:

- Typographical corrections
- Documentation improvements
- Clarifications
- Non-functional updates

Patch changes must not alter the architecture.

Example:

1.0.0 → 1.0.1

---

### Minor Change (x.1.0)

Used for:

- New architectural capability
- New module
- New subsystem
- Additional implementation rules
- New coding standards

Minor changes must remain backward compatible.

Example:

1.0.0 → 1.1.0

---

### Major Change (2.0.0)

Used only when:

- Core architecture changes
- Technology stack changes
- Repository restructuring
- Module boundary changes
- Breaking implementation changes

Major changes require a complete architecture review.

Example:

1.0.0 → 2.0.0

---

## 45.3 Architecture Change Workflow

Every architecture change must follow this workflow:

1. Identify the problem.
2. Create an Architecture Decision Record (ADR).
3. Evaluate alternatives.
4. Assess risks.
5. Obtain Project Owner approval.
6. Update MASTER_ARCHITECTURE.md.
7. Update Version History.
8. Update Approval Recording.
9. Commit the change.
10. Revalidate the complete architecture.

---

## 45.4 Emergency Changes

Emergency changes are permitted only when:

- A critical security issue exists.
- A data-loss risk exists.
- The application cannot continue development safely.

Emergency changes must still be documented after implementation.

---

## 45.5 Change Restrictions

The following items may NOT be changed without a Major Architecture Review:

- Primary programming languages
- Repository structure
- Module boundaries
- Security model
- Permission model
- Memory architecture
- Rust–Python integration model
- Desktop UI framework
- Core architectural principles

---

## 45.6 Semantic Versioning

Virgo AI follows Semantic Versioning.

Major.Minor.Patch

Examples:

1.0.0
1.0.1
1.1.0
2.0.0

---

## 45.7 Final Rule

No implementation may diverge from the approved architecture.

If implementation and architecture differ, implementation must stop until the difference is reviewed and approved.