# WU-SEMANTIC-OWNERSHIP-01 P3-D Plan Re-Review — AgentMiMo

## Scope

- Mode: adversarial plan re-review (plan-fix gate, no code changes)
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-D`
- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-d-engine-provider-protocol-normalization-plan.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-d-plan-review-controller-adjudication.md`
- Original reviews: `docs/reviews/wu-semantic-ownership-01-p3-d-plan-review-mimo.md`, `docs/reviews/wu-semantic-ownership-01-p3-d-plan-review-ds.md`
- Review date: 2026-07-10

## Verdict

**PASS** — All 12 plan-fix items (P3-D-PF-01 through P3-D-PF-12) are closed. The plan is code-generation-ready.

## PF Closure Verification

### P3-D-PF-01 — Host diagnostic event contract — CLOSED

Controller要求：命名 Host EventLog event type、选择 EventClass、决定是否复用 `_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC`、识别 engine_ingest.py dispatch、说明 Tool Trace / read API / outbox / memory projection 行为、说明 design doc 更新需求。

Plan修复证据：

- Line 107: S2 必须新增独立非致命 provider diagnostic dispatch，不复用 `_EVENT_TYPE_PROVIDER_PROTOCOL_ERROR`（致命）或 `_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC`（除非能证明 payload contract 可区分）。默认新增 `_EVENT_TYPE_PROVIDER_DIAGNOSTIC`。
- Line 108-111: Tool Trace 仅允许 diagnostic display、不转为 `failure_kind`；Read API 使用 `HostActivityKind.PROVIDER_DIAGNOSTIC`、title/summary 不暗示 run failure；outbox 不更新（`EventClass.DIAGNOSTIC` 被过滤）；Memory/final answer/evidence/compact 不消费 diagnostic payloads。
- Lines 220-226: 完整的 ingest payload 字段定义（`diagnostic_code`, `severity`, `message`, `provider_request_id`, `diagnostic_source`, `payload_ref`, `payload_digest`），不更新 Run/Attempt terminal state，不写 failure metadata。
- Lines 247-257: S2 section-specific design/doc decisions 覆盖 `docs/engine/design.md`、`docs/host/design.md`、`dayu/engine/README.md`、`dayu/host/README.md`、`tests/README.md`。

### P3-D-PF-02 — Context-overflow provenance cross-boundary — CLOSED

Controller要求：追踪 ContextOverflowDetection 从 error_classifier.py → runner.py → _AttemptFailedTerminal/RunnerHTTPErrorData → Agent → Engine diagnostic → Host diagnostic；runner.py 必须列为 candidate file；测试验证 marker fallback provenance。

Plan修复证据：

- Line 64: `error_classifier.py` 在 Owner Boundary 中明确列为 context-overflow 检测 owner。
- Line 120: Context overflow 设计决策明确 structured code 为 primary business signal，marker fallback 为 diagnostic provenance。
- Lines 193-203: S2 Required changes 中：
  - "Refactor context-overflow detection to return a typed result, for example `ContextOverflowDetection(kind=STRUCTURED_CODE | MESSAGE_MARKER_FALLBACK | NOT_OVERFLOW, diagnostic=...)`"
  - "Carry context-overflow provenance across the full boundary: `error_classifier.py` produces `ContextOverflowDetection`; `runner.py` stores it in `_AttemptFailedTerminal` or directly in `RunnerHTTPErrorData.context_overflow_detection`; Agent reads that field; Agent emits `context_compaction_requested` only from typed `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`; if provenance is `MESSAGE_MARKER_FALLBACK`, Agent also emits a non-fatal Engine diagnostic."
- Line 200: S2 candidate files 包含 `dayu/engine/runners/openai/runner.py`。
- Line 234: 测试要求 "marker-fallback provenance reaches Host diagnostic output without becoming business truth"。

### P3-D-PF-03 — Log-only vs RunnerProtocolErrorData warnings — CLOSED

Controller要求：拆分现有 RunnerProtocolErrorData warnings 和 log-only warnings；覆盖 streaming 和 non-streaming missing content type；包含 usage.py。

Plan修复证据：

- Line 100: 静态分析表明确区分 "Some tool-call warnings are currently stored as `RunnerProtocolErrorData`" 和 "usage malformed and missing content type are currently log-only warnings"。
- Lines 227-230: S2 Required changes 将 warning sources 拆分为两组：
  - (a) 现有 `RunnerProtocolErrorData` warnings（tool-call aggregation 中的 unknown provider namespace/key）
  - (b) 当前 log-only adapter warnings（malformed usage in `sse_parser.py`/`non_stream_parser.py`，missing `Content-Type` in `runner.py`）
- Line 230: "Missing `Content-Type` diagnostics must cover both streaming and non-streaming HTTP 200 responses."
- Line 208: S2 candidate files 包含 `dayu/engine/runners/openai/usage.py`。

### P3-D-PF-04 — Separate SSE/non-stream multi-choice semantics — CLOSED

Controller要求：定义 stream chunk rejection timing、"valid assistant choice"、usage-only empty-choice semantics、non-stream response semantics separately。

Plan修复证据：

- Line 115: SSE policy — 定义 "valid assistant choice" 为 delta 包含至少一个非 null semantic field（`role`, `content`, `reasoning_content`, `tool_calls`, `finish_reason`）；`choices=[]` + valid usage 仅对 SSE chunk 合法；多 valid assistant choice 为 fatal；valid choice with explicit non-zero `index` 为 fatal。
- Line 116: Non-stream policy — 必须恰好一个 assistant choice；`choices=[]`/missing/non-list/multi-choice/non-zero index 均为 fatal；无 usage-only chunk 例外。
- Lines 146-148: SSE 验证时机在 `_handle_chunk_object()` 中立即拒绝。
- Lines 157-162: Testing matrix 包含 non-stream multi-choice、SSE multi-choice chunk、usage-only chunk、empty delta + valid delta、conflicting content/tool-call choices。

### P3-D-PF-05 — Finish_reason negative boundary coverage — CLOSED

Controller要求：定义 unknown non-empty strings, non-string values, empty strings, null/missing, cross-chunk conflicting 的行为；明确负向测试。

Plan修复证据：

- Line 117: "Unknown non-empty strings, non-string non-null values, empty strings, arrays, objects, and booleans are fatal provider protocol errors... `null` and missing `finish_reason` are treated as absent, not as `STOP`... Cross-chunk conflicting terminal finish reasons are fatal."
- Lines 149-150: S1 Required changes 重申相同规则，要求 SSE 和 non-stream 一致实现。
- Lines 163-167: Testing matrix 包含 10 个明确的正向/负向用例：unknown non-empty → fatal、non-string (int/bool/array/object) → fatal、empty string → fatal、null/missing → absent（独立于 unknown strings 测试）、cross-chunk conflicting → fatal。

### P3-D-PF-06 — S1/S2 dependency and intermediate fatal state — CLOSED

Controller要求：明确 S2 depends on S1；描述中间状态。

Plan修复证据：

- Lines 183-185: "S2 depends on S1. After S1 and before S2, invalid/unknown `finish_reason` is already fatal but still travels through the existing fatal provider-protocol error path. S2 only splits remaining non-fatal diagnostics from fatal protocol errors; it must not reclassify invalid `finish_reason` back into a warning."

### P3-D-PF-07 — S3 atomicity justification — CLOSED

Controller要求：拆分 S3 或论证为何必须原子。

Plan修复证据：

- Lines 267-269: "Keep S3 as one atomic slice. The public dataclass field type change touches Engine contracts, Agent constructors, Engine run outcomes, Host ingest, Host read projections, Tool Trace, outbox/public events, tests, docs, and source-scan guard in one semantic contract. The project forbids compatibility facades, old aliases, and old string-only constructors; splitting contract typing from all in-repo callers would require either a compatibility layer or a temporarily broken main branch. Weak-typing guard and propagation audit are validation steps for the same type contract, not separate runtime behavior."

论证充分：项目禁止兼容 facade → 原子更新所有 caller 是唯一合规路径。

### P3-D-PF-08 — Error-code propagation matrix and complete scans — CLOSED

Controller要求：当前静态 propagation matrix；扩展 scans 覆盖所有 constructors 和 Host consumers。

Plan修复证据：

- Lines 95-111: "Current static propagation analysis for implementation" 表格覆盖 5 个语义类别（fatal protocol code、non-fatal diagnostic、context-overflow classification、Engine-owned run failure code、provider/runner extension code），每行列出 current producer/durable consumer/required P3-D treatment。
- Lines 314-327: S3 "Current error-code propagation matrix to preserve while typing" 覆盖 10 个站点：`RunnerProtocolErrorData.error_code`、`ProviderProtocolErrorData.error_code`、`RunFailedData.error_code`、`EngineRunOutcomeFailed.error_code`、Agent `_ERROR_*` constants、Host `engine_ingest.py`、Host `read_api.py`、Host `tool_trace.py`、Host outbox/public events、Memory/compact/evidence exclusion。
- Lines 337-341: Source scans 包含 `EngineRunOutcomeFailed(`、Host consumer files（`engine_ingest.py`, `read_api.py`, `tool_trace.py`, `outbox.py`）、`provider_error_code`、`failure_metadata`。

### P3-D-PF-09 — Concrete weak-typing guard — CLOSED

Controller要求：命名具体 guard 机制；包括 exact failure condition。

Plan修复证据：

- Lines 308-311: "Minimum acceptable mechanism: a checked-in pytest or validation script invoked by tests/CI that scans Engine contract and Agent/Host construction sites. It must fail if any of these patterns remain outside explicitly allowed durable-serialization helpers:
  - `error_code: str` in `dayu/engine/contracts/`;
  - `RunFailedData(`, `EngineRunOutcomeFailed(`, `ProviderProtocolErrorData(`, or `RunnerProtocolErrorData(` with literal string `error_code="..."`;
  - Host consumers reading typed Engine error-code objects without calling the serializer at ingest/public projection boundary."

机制明确（pytest 或 validation script）、触发条件明确（三个具体 pattern）、执行时机明确（tests/CI）。

### P3-D-PF-10 — RunnerSpecificErrorCode empty/serialization semantics — CLOSED

Controller要求：定义空 provider error codes 处理；wrapper shape, bounded validation, source field；single durable/public serialization format。

Plan修复证据：

- Line 121: "Provider/runner-specific codes use a deliberate typed wrapper such as `RunnerSpecificErrorCode(value=..., source=...)`. The wrapper validates trimmed non-empty bounded text, for example 1-128 characters, and a closed source enum such as `RUNNER_PROTOCOL`, `HTTP_PROVIDER`, or `ADAPTER`. Explicit empty or whitespace-only provider/runner codes fail closed at the producer; missing provider detail uses an Engine-owned fallback such as `RUNNER_ERROR_DONE_WITHOUT_DETAIL` instead of fabricating a provider-specific value. Serialization to Host durable JSON uses one helper, for example `serialize_engine_error_code(code) -> str`, not ad hoc `.value` or raw strings scattered through consumers."
- Lines 303-305: S3 Required changes 重申相同规则。
- Line 335: Required wrapper tests 覆盖 valid value、empty string、whitespace-only、missing provider detail fallback、overly long values、Host durable JSON serializer output。

### P3-D-PF-11 — Section-specific design/README updates — CLOSED

Controller要求：列出 exact docs sections。

Plan修复证据：

- Lines 247-257: S2 section-specific decisions：
  - `docs/engine/design.md` RunnerEvent/EngineEvent tables/sections
  - `docs/host/design.md` EngineEvent ingest 和 diagnostic/canonical matrix sections
  - `dayu/engine/README.md`（若文档化 Runner/Engine events 或 provider adapter 行为）
  - `dayu/host/README.md`（若 Agent update constraints 要求 diagnostic projection 或 EventLog mapping）
  - `tests/README.md`（若新 contract tests、Host projection tests、source-scan validation rules 成为 test organization 一部分）
- Lines 343-353: S3 section-specific decisions 覆盖相同文档集。

### P3-D-PF-12 — No LLM-facing diagnostic leakage — CLOSED

Controller要求：validation scan/test 确保 diagnostics 不进入 memory, final answer, evidence, compact, LLM-facing prompts。

Plan修复证据：

- Line 35: Non-Goals 明确 "Do not expose provider diagnostic internals to LLM-facing messages."
- Line 79: Owner Boundary 明确 "LLM-facing messages must not contain provider diagnostic internals."
- Line 111: Host consumer notes 明确 "Memory, final answer, accepted evidence material, compact material, and prompt assembly must not consume provider diagnostic payloads."
- Line 234: S2 测试要求 "no raw marker text in memory/final answer/evidence/compact prompt material, and no diagnostic-driven status transition."
- Line 327: S3 propagation matrix 明确 memory/compact/evidence exclusion。
- Lines 369-373: Validation Summary 要求 "implementation must add a focused test or source scan proving `PROVIDER_DIAGNOSTIC`, provider raw diagnostic text, `message_marker_fallback`, and provider diagnostic payload refs do not enter memory, final answer, accepted evidence material, compact material, or LLM-facing prompt messages"，并给出 suggested scan set。
- Line 391: Explicit Prohibitions 明确 "Do not put provider diagnostics into memory, final answer, evidence material, or LLM-facing prompt text."

## Residual Risk

无。所有 PF 项已关闭，plan 无 blocking gap。实现阶段的风险由各 slice 的 testing matrix、source scans、propagation audit 和 coverage gate 覆盖。

## Verification Status

| 验证项 | 状态 |
|---|---|
| P3-D-PF-01 closure | ✅ 已验证 |
| P3-D-PF-02 closure | ✅ 已验证 |
| P3-D-PF-03 closure | ✅ 已验证 |
| P3-D-PF-04 closure | ✅ 已验证 |
| P3-D-PF-05 closure | ✅ 已验证 |
| P3-D-PF-06 closure | ✅ 已验证 |
| P3-D-PF-07 closure | ✅ 已验证 |
| P3-D-PF-08 closure | ✅ 已验证 |
| P3-D-PF-09 closure | ✅ 已验证 |
| P3-D-PF-10 closure | ✅ 已验证 |
| P3-D-PF-11 closure | ✅ 已验证 |
| P3-D-PF-12 closure | ✅ 已验证 |
| Source finding disposition (6/6 accepted-current) | ✅ 与原 review 一致 |
| Owner boundary alignment | ✅ 与原 review 一致 |
| Contract decisions completeness | ✅ 已验证 |
| Slice dependency declaration | ✅ S2 depends on S1 已声明 |
| Cross-verification vs original MiMo findings | ✅ 12/12 覆盖 |
| Cross-verification vs original DS findings | ✅ 9/9 覆盖 |
| Cross-verification vs controller adjudication | ✅ 12/12 覆盖 |
