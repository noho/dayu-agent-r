# WU-SEMANTIC-OWNERSHIP-01 P3-D Plan Review Controller Adjudication

## Verdict

Plan fix gate required. AgentMiMo and AgentDS both confirm P3-D source findings are current, but the plan is not yet implementation-ready.

- AgentMiMo plan review: `docs/reviews/wu-semantic-ownership-01-p3-d-plan-review-mimo.md`
- AgentDS plan review: `docs/reviews/wu-semantic-ownership-01-p3-d-plan-review-ds.md`

## Accepted Plan Fixes

### P3-D-PF-01 - S2 Host diagnostic event contract must be explicit

Merge of AgentMiMo `P3-D-PR-001`, `P3-D-PR-008`, `P3-D-PR-010`, and AgentDS `F-9`.

Plan must name the Host EventLog event type for non-fatal provider diagnostics, choose EventClass, decide whether to reuse existing `_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC`, identify required `engine_ingest.py` dispatch, and state Tool Trace / read API / outbox / memory projection behavior. It must also state whether `docs/host/design.md` canonical event matrix or EngineEvent mapping sections need updates.

### P3-D-PF-02 - S2 context-overflow provenance must cross Runner -> Agent -> Engine -> Host

Merge of AgentDS `F-1` and AgentMiMo `P3-D-PR-006`.

Plan must trace typed `ContextOverflowDetection` from `error_classifier.py` through `runner.py`, `_AttemptFailedTerminal` or `RunnerHTTPErrorData`, Agent EngineEvent projection, Host diagnostic persistence, and `context_compaction_requested`. `runner.py` must be listed as a candidate file, and tests must verify marker-fallback provenance reaches diagnostic output without becoming business truth.

### P3-D-PF-03 - S2 must distinguish log-only adapter warnings from RunnerProtocolErrorData warnings

Accepted from AgentDS `F-2` and `F-3`.

Plan must split current sources into: warnings already stored as `RunnerProtocolErrorData` in tool-call aggregation, and log-only warnings such as malformed usage and missing content type. It must explicitly cover both streaming and non-streaming missing content type diagnostics and include `usage.py` or the exact parser call sites as candidate files.

### P3-D-PF-04 - S1 multi-choice policy must define SSE and non-stream semantics separately

Merge of AgentMiMo `P3-D-PR-003`, AgentDS `F-5`, and AgentDS `F-8`.

Plan must define stream chunk rejection timing, "valid assistant choice", usage-only empty-choice semantics, and non-stream response semantics separately. Required tests must include non-stream multi-choice, SSE multi-choice chunk, empty-choice usage-only chunk, empty delta + valid delta cases, and conflicting content/tool-call choices.

### P3-D-PF-05 - S1 finish_reason policy must cover non-string, empty, null, missing, and conflicting values

Merge of AgentMiMo `P3-D-PR-004` and AgentDS `F-7`.

Plan must state behavior for unknown non-empty strings, non-string values, empty strings, null/missing values, and cross-chunk conflicting finish reasons. It must add explicit negative tests rather than only source scans.

### P3-D-PF-06 - S2 depends on S1 and must describe the intermediate fatal state

Accepted from AgentMiMo `P3-D-PR-009` and AgentDS residual risk.

Plan must explicitly state that S2 depends on S1. It must describe that after S1 and before S2, unknown finish_reason is fatal and still uses the existing provider-protocol error path until diagnostics are split.

### P3-D-PF-07 - S3 scope must be split or justified with an atomicity argument

Accepted from AgentMiMo `P3-D-PR-002`.

Plan must either split S3 into smaller slices or explicitly justify why contract typing, all Engine/Agent callers, all Host consumers, weak-typing guard, docs, and propagation audit must be one atomic slice due to no-compatibility constraints. If split, each subslice must remain reviewable and not require compatibility facades.

### P3-D-PF-08 - S3 error-code source scans and propagation audit must cover all constructors and Host consumers

Merge of AgentMiMo `P3-D-PR-005` and AgentDS `F-4`.

Plan must include a current static propagation matrix for error-code flow and extend scans to `EngineRunOutcomeFailed(...)`, `RunFailedData(...)`, `ProviderProtocolErrorData(...)`, `RunnerProtocolErrorData(...)`, `engine_ingest.py`, `read_api.py`, `tool_trace.py`, outbox/public events, and failure metadata fields such as `provider_error_code`.

### P3-D-PF-09 - Weak typing guard mechanism must be concrete

Accepted from AgentDS `F-6`.

Plan must name the guard mechanism: test, script, source scan, or CI command, including exact failure condition. A vague "add weak-typing/source-scan checks" is insufficient.

### P3-D-PF-10 - Runner-specific error-code wrapper must define empty-value and serialization semantics

Merge of AgentMiMo `P3-D-PR-007` and AgentDS open question / residual.

Plan must define whether empty provider error codes fail closed or fall back to a typed unknown, define wrapper shape, bounded validation, source field, and the single durable/public serialization format used by Host consumers.

### P3-D-PF-11 - Design/README update scope must be section-specific

Merge of MiMo residual and DS findings.

Plan must list exact docs sections likely touched: `docs/engine/design.md` Runner/EngineEvent tables, `docs/host/design.md` EngineEvent ingest / canonical or diagnostic matrix, `dayu/engine/README.md`, `dayu/host/README.md`, and `tests/README.md` decisions.

### P3-D-PF-12 - Completion validation must include no-LLM-facing diagnostic leakage

Controller addition based on both reviewers' propagation concerns.

Plan must add a validation scan/test ensuring provider diagnostics do not enter memory, final answer, accepted evidence material, compact material, or LLM-facing prompts. This is required by AGENTS.md LLM-facing text constraints and the P3-D owner boundary.

## Rejected / Non-Blocking Items

None of the reviewer findings are rejected at this stage. Open questions are converted into the required plan fixes above.

## Required Next Gate

AgentCodex must update `docs/host/wu-semantic-ownership-01-p3-d-engine-provider-protocol-normalization-plan.md` and write a plan-fix artifact. No production or test code changes are allowed in this gate.
