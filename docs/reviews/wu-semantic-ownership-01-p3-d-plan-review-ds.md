# P3-D Plan Review — AgentDS Adversarial Review

## Scope

- **Review type**: Adversarial plan review (gate: plan → implementation-ready)
- **Work unit**: `WU-SEMANTIC-OWNERSHIP-01 / P3-D`
- **Plan artifact**: `docs/host/wu-semantic-ownership-01-p3-d-engine-provider-protocol-normalization-plan.md`
- **Source adjudication**: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md` P3-D
- **Reviewer**: AgentDS
- **Date**: 2026-07-10
- **Output file**: `docs/reviews/wu-semantic-ownership-01-p3-d-plan-review-ds.md`
- **Included scope**: Plan text, all referenced source files (SSE parser, non-stream parser, tool call aggregator, error classifier, runner.py, agent.py, runner_events.py, engine_events.py, engine_ingest.py, tool_trace.py, read_api.py), controller adjudication P3-D findings
- **Excluded scope**: Other P3 sub-work-units, implementation code changes, test file contents
- **Verification method**: Source-code-level evidence from `dayu/engine/`, `dayu/host/` production files, referenced at specific line numbers

## Verdict

**FINDINGS** — 9 findings: 1 严重 (blocker), 4 高, 3 中, 1 低. Plan is directionally correct and well-aligned with controller adjudication, but contains blocking gaps in context-overflow provenance data flow specification and propagation audit deferral.

---

## Findings

### F-1-未修复-严重-context-overflow 检测 provenance 在 Runner→Agent 边界的传递机制缺失

- **入口/函数**: `AsyncOpenAIRunner._call_attempt()` → `detect_context_overflow()` → `_AttemptFailedTerminal` → `Agent._consume_runner_event()`
- **文件(行号)**:
  - `dayu/engine/runners/openai/runner.py:690-701`（`detect_context_overflow()` 返回 bool，provenance 在此丢失）
  - `dayu/engine/runners/openai/error_classifier.py:91-116`（`detect_context_overflow` 返回裸 `bool`）
  - `dayu/engine/agent.py:1406-1440`（Agent 仅检查 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`，无法区分 structured_code vs marker_fallback）
- **输入场景**: provider 返回 HTTP 400 且 `error.code != "context_length_exceeded"`，但错误消息文本命中 `_CONTEXT_OVERFLOW_MESSAGE_MARKERS` 中的某个 marker（如 "maximum context length is"）。
- **实际分支**: `detect_context_overflow()` 返回 `True`（通过 marker fallback 命中）→ `_AttemptFailedTerminal(error_code=CONTEXT_LENGTH_EXCEEDED)` → Agent 收到 `RunnerHTTPErrorData(error_code=CONTEXT_LENGTH_EXCEEDED)` → Agent 产出 `context_compaction_requested`后以 `run_failed(context_compaction_required, recoverable=True)` 收口。
- **预期行为**: Plan Contract Decision #5 要求 "emitted Engine/Host diagnostic must say detection source was `message_marker_fallback`"。当前 `RunnerHTTPErrorData` 没有 provenance 字段，`_AttemptFailedTerminal` 异常不携带 provenance，Agent 无法区分检测来源。
- **实际行为**: 无论 structured code 还是 marker fallback 触发，最终产出完全相同的 `RunnerHTTPErrorData(error_code=CONTEXT_LENGTH_EXCEEDED)` 和 `context_compaction_requested`，provenance 信息在 runner.py:694 处彻底丢失。
- **直接证据**:
  - `error_classifier.py:116`: `return any(marker in lowered for marker in _CONTEXT_OVERFLOW_MESSAGE_MARKERS)` — 返回 `bool`，不是 typed result。
  - `runner.py:694`: `raise _AttemptFailedTerminal(error_code=RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED, ...)` — 异常类签名没有 provenance 字段，只有 error_code/http_status/message_text/provider_request_id/raw_payload。
  - `agent.py:1406`: `if data.error_code is RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED:` — 仅以枚举值判定，无 provenance 可读取。
- **影响**: S2 的 context-overflow provenance 改造无法闭合。Plan 在 S2 中声明 "Refactor context-overflow detection to return a typed result... rather than a bare bool"，但这个 typed result 必须在 runner.py 的异常抛出点被**打包进异常对象**，然后在 Agent 端从 `RunnerHTTPErrorData` 中**解包**，才能最终流向 Host diagnostic event。当前 plan 没有说明这一打包/解包机制。
- **Root cause**: Plan 识别到了 `detect_context_overflow()` 需要改返回类型，但没有追踪到该返回值在当前代码中的消费路径被 `_AttemptFailedTerminal` 异常擦除这一事实。
- **Owner boundary**: Runner adapter (`error_classifier.py` + `runner.py`) 拥有 provenance 的产生和传递；Agent 拥有从 `RunnerHTTPErrorData` 中读取 provenance 并投影到 Engine diagnostic event 的职责。
- **建议修复 plan 位置**:
  1. S2 Required Changes 中需要新增一条：在 `RunnerHTTPErrorData` 中增加可选 `context_overflow_provenance: ContextOverflowProvenance | None` 字段（或等价机制），使 runner.py 在构造 `_AttemptFailedTerminal`（或直接构造 `RunnerHTTPErrorData`）时携带 provenance。
  2. S2 Required Changes 中需要新增一条：Agent 在 `RunnerHTTPErrorData.error_code == CONTEXT_LENGTH_EXCEEDED` 路径上，若 provenance 存在且为 `MESSAGE_MARKER_FALLBACK`，则先 emit diagnostic event 再 emit `context_compaction_requested`。
  3. S2 Candidate files 应明确列出 `runner.py`（不仅是 `error_classifier.py`）作为 context-overflow 改造的变更文件。
- **需要补充的测试/验证**: 测试 `detect_context_overflow()` 返回 `MESSAGE_MARKER_FALLBACK` 时，最终 `RunnerHTTPErrorData` 携带正确的 provenance，且 Agent 正确转换为 diagnostic + context_compaction_requested 双事件序列。
- **修复风险**: 中 — `RunnerHTTPErrorData` 是 frozen dataclass，增加字段需要更新所有构造点（runner.py 中至少 3 处 `_AttemptFailedTerminal` raise site）。但 runner_events.py 在 S2 candidate files 中，风险可控。
- **严重程度**: 严重

---

### F-2-未修复-高-usage_field_malformed 当前为 log-only 而非 RunnerProtocolErrorData，plan 对其迁移路径描述不准确

- **入口/函数**: `SSEParser._handle_usage()` / `parse_non_stream_response()`
- **文件(行号)**:
  - `dayu/engine/runners/openai/sse_parser.py:641-654`（`coerce_usage()` 返回 `None` 时仅 `_LOGGER.warning`，不 emit 任何 `RunnerEvent`）
  - `dayu/engine/runners/openai/non_stream_parser.py:340-353`（同上，仅 log warning）
- **输入场景**: provider 返回 `usage` 字段但字段类型不合法（如 `prompt_tokens` 为 string）。
- **实际分支**: `coerce_usage()` 返回 `None` → `_LOGGER.warning("...usage_field_malformed...")` → 函数 `return`，不产出任何事件。usage 静默丢失，Agent/Host 永远不知道 provider 返回了格式异常的 usage 数据。
- **预期行为**: Plan S2 说 "Migrate known non-fatal cases away from RunnerProtocolErrorData: ... usage malformed"。但 usage malformed **当前不是** `RunnerProtocolErrorData` ——它是纯 log line，从未作为事件产出。正确的描述应为 "Make currently log-only adapter warnings (usage malformed, missing content type) into typed non-fatal diagnostic events."
- **实际行为**: Plan 把 usage malformed 归入 "从 RunnerProtocolErrorData 迁移" 的类别，这会误导实现者以为只需要改事件类型映射，而实际上需要从零构造事件产出路径。
- **直接证据**:
  - `sse_parser.py:646-653`: warning via `_LOGGER.warning(...)` only, then `return` — zero event emission.
  - `non_stream_parser.py:346-353`: same pattern, `_LOGGER.warning(...)` only.
  - 对比 tool_call_aggregator.py:306-311 的 `self._warnings.append(RunnerProtocolErrorData(...))` — 这才是真正的 RunnerProtocolErrorData 迁移源。
- **影响**: 实现者可能只修改 tool_call_aggregator 的 warning→diagnostic 映射，而遗漏 SSE/non-stream parser 中需从零构造事件产出路径的 usage_field_malformed 和 missing_content_type 警告。这些警告会继续保持 log-only，sink 到日志中而无法被 Host 持久化或展示。
- **Root cause**: Plan 的 First-Principles Finding Check 表只覆盖了 AgentCodex 4（tool_call_aggregator 的 warnings），但没有独立检查 usage malformed 和 missing content type 的实际事件产出状态。
- **Owner boundary**: Runner adapter 负责从 provider wire response 中提取所有可观测事实并归一为 typed RunnerEvent。log-only 诊断不是 typed RunnerEvent，违反 owner boundary。
- **建议修复 plan 位置**:
  1. S2 Required Changes 中 "Migrate known non-fatal cases" 应拆分为两类：(a) 从 `RunnerProtocolErrorData` 改为 diagnostic event 的 case（tool_call_aggregator warnings）；(b) 从 log-only 改为 diagnostic event 的 case（usage malformed, missing content type）。
  2. S2 Candidate files 应补充 `dayu/engine/runners/openai/usage.py`（`coerce_usage` 返回 `None` 时的调用点需要改为产出 diagnostic）。
- **需要补充的测试/验证**: 测试 malformed usage 输入的 SSE 和非流式路径均产出 typed diagnostic event，且该 event 被 Agent 透传为 Engine diagnostic（不设置 failure_candidate），被 Host 持久化为 `DIAGNOSTIC` 类型。
- **修复风险**: 低 — 改动在 adapter 内部，不改变 Agent/Host 核心状态机，只需在现有 `_handle_usage()` 和 `parse_non_stream_response()` 的 `coerce_usage() is None` 分支内增加 event yield。
- **严重程度**: 高

---

### F-3-未修复-高-missing_content_type 诊断仅对 stream=True 生效，非流式缺失 Content-Type 无诊断

- **入口/函数**: `AsyncOpenAIRunner._call_attempt()` / `_is_sse_response()`
- **文件(行号)**:
  - `dayu/engine/runners/openai/runner.py:720-728`（仅当 `options.stream and content_type.strip() == ""` 时记录 warning）
  - `dayu/engine/runners/openai/runner.py:190-203`（`_is_sse_response()` 对空 Content-Type 且 stream=True 返回 True，fallback SSE；非流式空 Content-Type 正常走非流式 JSON 解析）
- **输入场景**: `options.stream=False`，provider 返回 HTTP 200 但 Content-Type header 为空字符串。
- **实际分支**: `_is_sse_response(content_type="", stream=False)` → `not stream` → `return False` → 走非流式 JSON 解析路径。302 redirect 不触发，200+空 Content-Type 不触发任何诊断。
- **预期行为**: 非流式请求收到空 Content-Type 同样是一个 provider 行为偏差，应产出 non-fatal diagnostic 而不是静默继续。
- **实际行为**: 非流式空 Content-Type 被静默接受，JSON 解析成功就正常产出内容，解析失败才触发 `_INVALID_JSON_CODE` 协议错误。但 provider 不发送 Content-Type 本身就是诊断信号。
- **直接证据**:
  - `runner.py:723`: `if options.stream and content_type.strip() == "":` — 条件中显式包含 `options.stream`，非流式被排除。
  - `runner.py:198-199`: `if not stream: return False` — `_is_sse_response` 对非流式直接返回 False，不做 Content-Type 诊断。
- **影响**: Plan 对 missing_content_type 的改造如果只关注流式路径，非流式路径的 Content-Type 缺失会继续静默。不影响 correctness（JSON 解析仍然工作），但违反 "provider diagnostics 应被 typed event 表达" 的 plan 原则。
- **Root cause**: Plan 引用的 source finding 只提到流式 missing Content-Type，且 `_is_sse_response()` 对非流式的处理是合理的（非流式不应 fallback SSE），但缺失诊断是 plan 设计上的不完全。
- **Owner boundary**: Runner adapter 拥有对所有 provider HTTP response metadata 的观测和诊断职责。
- **建议修复 plan 位置**: S2 或 S3 中增加一条：非流式空/异常 Content-Type 也产出 non-fatal diagnostic event（不影响解析路径选择）。
- **需要补充的测试/验证**: 非流式空 Content-Type 响应产出 diagnostic event 的测试。
- **修复风险**: 低 — 增加一个条件分支和 event yield，不改变解析路径。
- **严重程度**: 中

---

### F-4-未修复-高-S2/S3 propagation audit 完全推迟到实现阶段，plan 未包含任何当前传播路径的静态审计

- **入口/函数**: 不适用（plan-level gap）
- **文件(行号)**: Plan 第 81-90 行（propagation audit target）与 S3 Required Changes 第 249 行（"Complete propagation audit in the implementation artifact"）
- **输入场景**: 不适用
- **实际分支**: Plan 声明了 propagation audit target（provider wire → adapter → RunnerEvent → Agent → EngineEvent → Host ingest → EventLog → read model / tool trace / outbox / memory），但未在 plan 中执行任何一项审计。
- **预期行为**: "Code-generation-ready" plan 应至少包含：
  1. 当前每个 error_code 字符串在 Host 层各消费者（engine_ingest, tool_trace, read_api, outbox, public event projection）中的消费方式矩阵。
  2. 识别哪些消费者直接访问 `error_code: str`（会在 S3 改类型后编译/类型检查失败）。
  3. 确认新 diagnostic event 不会被 tool_trace 当作 failure_kind、不会被 memory projection 摄入、不会被 outbox 当作 terminal item。
- **实际行为**: Plan 只有声明性的 propagation audit target 和 S3 的一句话 "Complete propagation audit in the implementation artifact"，没有任何当前路径的静态分析。这意味着 S3 实现者需要从零开始做审计，可能在实现过程中发现遗漏的消费者站点，导致 S3 scope 超出预期。
- **直接证据**:
  - Plan 第 80-90 行：列出了 propagation audit target 但没有执行。
  - Plan 第 249 行："Complete propagation audit in the implementation artifact" — 审计被 deferred。
  - 当前 Host 消费者实际分布（来自源码扫描）：
    - `engine_ingest.py:462-475`: `_HostStreamFailureContext.error_code: str | None`, `stream_error_code: str | None`
    - `engine_ingest.py:1099-1102`: `PROVIDER_PROTOCOL_ERROR` 事件的 ingest handler
    - `tool_trace.py:1722-1793`: `failure_kind` closed set 校验，`provider_error_code` 字段
    - `read_api.py:132-134`: `_PAYLOAD_FIELD_ERROR_CODE`, `_PAYLOAD_FIELD_PROVIDER_ERROR_CODE`，用于从 durable payload 中读取
    - `engine_ingest.py:6857-6863`: `_provider_protocol_failure_metadata()` 构造 `"provider_error_code": data.error_code` — 直接读取 `data.error_code: str`
- **影响**: S3 实现可能发现新的 consumer site 需要修改，导致 scope creep。最坏情况下，遗漏的 consumer 仍然用裸 `str` 访问 error_code，S3 的类型改造不完整。
- **Root cause**: Plan 把 propagation audit 视为实现期活动而非计划期活动。但根据 AGENTS.md 的 semantic ownership 要求，"修复完成前必须做一次 propagation audit"，这说明 audit 需要提前规划范围和识别触及文件——这正是 plan 的职责。
- **Owner boundary**: Plan 的 owner（AgentCodex）应在 plan 阶段完成最少 propagation audit 的静态分析，而非完全推迟到 S3 实现。
- **建议修复 plan 位置**: 在 plan 的 Propagation Audit 节（第 80-90 行之后）增加一个 "Current Propagation Path Static Analysis" 子节，列出：每个 error_code 从 agent.py 常量 → RunFailedData 构造 → EngineEvent → Host ingest → tool_trace failure_metadata / read_api / outbox / memory 的完整路径，标记哪些站点当前以裸 `str` 访问，哪些以 typed 字段访问。
- **需要补充的测试/验证**: 无需额外测试（这是 plan 分析活动）。
- **修复风险**: 低 — 不涉及代码变更，只增加 plan 文档内容。
- **严重程度**: 高

---

### F-5-未修复-高-S1 multi-choice 策略未区分 SSE chunk 与非流式响应的 semantics，可能导致非流式 usage 携带 responses 被误判为多 choice

- **入口/函数**: `SSEParser._handle_chunk_object()` / `parse_non_stream_response()`
- **文件(行号)**:
  - `dayu/engine/runners/openai/sse_parser.py:464-505`（SSE chunk 内遍历所有 choice）
  - `dayu/engine/runners/openai/non_stream_parser.py:269`（非流式取 `choices[0]`，其余 choice 静默丢弃）
- **输入场景**: 非流式 provider 返回 `choices: [{message: ..., finish_reason: "stop"}, {message: ..., finish_reason: "stop"}]`（两个 assistant choice）。
- **实际分支**: 当前代码 `choice = choices[0]`（line 269）— 仅处理第一个 choice，第二个被静默忽略。Plan 要求改为 fatal protocol error。
- **预期行为**: Plan Contract Decision #1 说 "A usage-only chunk with empty choices remains valid"——这只对 SSE chunk 适用。对于非流式响应，不存在 "usage-only chunk" 的概念，多 choice 应始终是 fatal error。
- **实际行为**: Plan 的 multi-choice policy 描述将 SSE chunk 语义和非流式响应语义混在一起说。实现者可能：
  - 在非流式场景也允许 "usage-only"（但非流式没有 chunk 概念）；
  - 在 SSE 场景过于严格（例如某个 chunk 有 2 个 choice 但其中一个是 `delta: {}` 的空 choice，应否触发 fatal？）。
- **直接证据**:
  - Plan Contract Decision #1: "使用仅含 usage 的空 choices chunk 仍然合法" — 未标注此规则仅适用于 SSE path。
  - `non_stream_parser.py:269`: `choice = choices[0]` — 多 choice 当前被静默丢弃而非报错。
  - SSE parser line 466: `for index, choice in enumerate(choices)` — 遍历所有 choice，但当前没有 len(choices) > 1 的检查。
- **影响**: 实现者可能需要对非流式多 choice 的边界条件自行解释，导致行为偏差。特别是，如果非流式返回 `choices: [{delta: {}, ...}, {delta: {content: "hello"}, ...}]`（第一个 choice 为 "空"），当前实现取 `choices[0]` 得到空内容，可能触发 `runner_empty_final_content` 而 plan 想要的是 fatal multi-choice error。
- **Root cause**: Plan 的 Contract Decision #1 是为 SSE parser 设计的（chunk-level semantics），但未为非流式 parser 单独描述 choice 策略。
- **Owner boundary**: Runner adapter 拥有 choice policy。
- **建议修复 plan 位置**: Contract Decision #1 应拆分为两条：(1a) SSE chunk choice policy — 单 choice 合法，零 choice+usage 合法，多 choice 为 fatal；(1b) Non-stream response choice policy — choices 必须存在，单 choice 合法，零 choice 或多 choice 均为 fatal。
- **需要补充的测试/验证**: 非流式多 choice 响应的 fatal error 测试；SSE 多 choice chunk（含空 choice）的 fatal error 测试；SSE usage-only chunk 的合法测试。
- **修复风险**: 低 — 拆分描述不影响实现路径，只是更精确地指导测试矩阵。
- **严重程度**: 中

---

### F-6-未修复-中-S3 weak-typing guard 机制未指定具体实现方式

- **入口/函数**: 不适用（plan specification gap）
- **文件(行号)**: Plan 第 248 行
- **输入场景**: S3 实现完成后，未来某次修改将新的 `error_code` 字段声明为裸 `str` 而非 typed enum/wrapper。
- **预期行为**: Plan 说 "Add weak-typing/source-scan checks to prevent new Engine error-code fields from regressing to bare str."
- **实际行为**: Plan 未指定 check 的具体形式：
  - 是 CI 中的 `rg` 扫描脚本？
  - 是 pyright 的类型检查（通过不允许 `error_code: str` 的 lint 规则）？
  - 是测试中的运行时 assert？
  - 是 pre-commit hook？
- **直接证据**: Plan 第 248 行："Add weak-typing/source-scan checks to prevent new Engine error-code fields from regressing to bare str." — 只有意图声明，没有机制描述。
- **影响**: 没有明确的 guard 机制，S3 实现者可能选择最小实现（如仅在 plan artifact 中写一条注意事项），导致 regression 防护为纸面防护。根据 AGENTS.md 编码硬约束 "禁止魔法字符串"，error_code: str 本身就是魔法字符串的变体——但 AGENTS.md 没有要求 lint-level 防护，所以 plan 需要明确防护级别。
- **Root cause**: Plan 识别到了回归风险但没有给出可操作的防护设计。
- **Owner boundary**: Engine contracts 拥有 error_code 的类型定义；防护机制可以在 contracts/__init__.py 导出层面或 CI 脚本层面。
- **建议修复 plan 位置**: S3 Required Changes 中，将 "Add weak-typing/source-scan checks" 细化为至少一项具体检查，例如："在 CI validation 脚本中添加 `rg -n 'error_code: str' dayu/engine/contracts/` 扫描，确保 contracts 层没有裸 `str` error_code 字段；如 rg 返回非空则 CI fail"。
- **需要补充的测试/验证**: 如果选择 CI 脚本方案，需要验证脚本在发现裸 `str` error_code 时确实返回非零 exit code。
- **修复风险**: 低 — 只涉及 CI 脚本或 lint 配置，不影响生产代码。
- **严重程度**: 中

---

### F-7-未修复-中-S1 测试矩阵缺少 unknown finish_reason 的负向测试描述

- **入口/函数**: SSE parser `_handle_choice()` / non-stream parser `_resolve_finish_reason()`
- **文件(行号)**:
  - `dayu/engine/runners/openai/sse_parser.py:538-547`（SSE unknown finish_reason → log warning, `_finish_reason` 保持 `None`）
  - `dayu/engine/runners/openai/non_stream_parser.py:390-408`（non-stream unknown finish_reason → log warning, return `FinishReason.STOP`）
- **输入场景**: provider 返回 `finish_reason: "new_provider_specific_reason"`（非标准原因字符串）
- **实际分支（当前）**: SSE: `_finish_reason` 保持 `None`，在 `_finalize_success()` 中 `self._finish_reason or FinishReason.STOP` → `STOP`。Non-stream: 直接返回 `FinishReason.STOP`。
- **预期行为（Plan S1）**: 改为 fatal protocol error + `RunnerDoneData(ERROR)`。
- **直接证据**:
  - Plan S1 Testing matrix 列出的测试命令没有显式包含 `test_unknown_finish_reason` 的负向测试。
  - Plan S1 Source scan: `rg -n "unknown_finish_reason|FinishReason\.STOP|finish_reason or FinishReason\.STOP"` — 这是当前代码的扫描，用于确认改动已完成。但 plan 没有列出需要**新增**的测试 fixture（如构造 `finish_reason: "unknown_custom"` 的 mock provider response）。
- **影响**: 实现者可能复用现有 "unknown finish_reason → STOP" 测试并改为断言 fatal error，但遗漏以下负向边界：
  - empty string `finish_reason: ""` 应如何处理？
  - `finish_reason: null` 应如何处理？
  - SSE chunk 中 first chunk 有 finish_reason="stop"，second chunk 有 finish_reason="tool_calls"——这是否为协议错误？
- **Root cause**: Plan 的 testing matrix 按已有测试文件名组织，没有按照新行为的负向边界组织测试用例。
- **Owner boundary**: Runner adapter 拥有 finish reason 归一化。
- **建议修复 plan 位置**: S1 Testing matrix 中增加显式负向测试场景列表：unknown non-empty finish_reason → fatal error；empty string finish_reason → 按协议规范处理（或 fatal 或视为缺失）；null finish_reason → 视为缺失；SSE 跨 chunk finish_reason 冲突 → 明确行为。
- **需要补充的测试/验证**: 按上述场景逐一增加测试。
- **修复风险**: 低 — 仅增加测试，不改变 plan 的设计方向。
- **严重程度**: 中

---

### F-8-未修复-低-SSE 多 choice chunk 中的内容/tool-call 冲突未在 multi-choice policy 中显式覆盖

- **入口/函数**: `SSEParser._handle_chunk_object()`
- **文件(行号)**: `dayu/engine/runners/openai/sse_parser.py:464-505`
- **输入场景**: 同一 SSE chunk 中有 2 个 choice：`choices[0].delta.content = "A"`, `choices[1].delta.content = "B"`，两者都非空。
- **实际分支**: 当前代码 `for index, choice in enumerate(choices):` 遍历并处理所有 choice——两个 content delta 都被产出，content_buffer 会包含 "AB"。
- **预期行为**: Plan 说多 choice → fatal protocol error。但当前 check 在 chunk 级别而非 choice 级别——需要显式说明：当 `len(choices) > 1` 且不止一个 choice 有有效 delta 时，整个 chunk 为 fatal error。
- **直接证据**:
  - SSE parser line 466: `for index, choice in enumerate(choices):` — 没有 pre-check `len(choices) > 1`。
  - Plan Contract Decision #1 未显式覆盖 "choices 有多个但其中某些 delta 为空" 的场景。
- **影响**: 边缘场景——大多数 provider 不会在单个 SSE chunk 中发多个 choice。但是 defensive design 要求 plan 明确：是只要 `len(choices) > 1`（不管每个 choice 的 delta 是否为空）就 fatal，还是只对有效非空 delta 的多 choice fatal。
- **Root cause**: Plan 的 multi-choice policy 描述粒度不足，仅覆盖了 "valid assistant choice" 这个未定义的术语。
- **Owner boundary**: Runner adapter 拥有 SSE choice policy。
- **建议修复 plan 位置**: Contract Decision #1 中明确定义 "valid assistant choice"：`choice.delta` 非空（即 `delta` 中存在至少一个非 null 字段如 content/tool_calls/role）的 choice 为 valid choice；同一 chunk 中出现 >1 个 valid choice 为 fatal。
- **需要补充的测试/验证**: SSE chunk 含 2 个 choice（一个空 delta 一个有内容 delta）→ fatal error 测试。
- **修复风险**: 低 — plan 文本澄清。
- **严重程度**: 低

---

### F-9-未修复-高-Plan 对 EngineEventType 新增 PROVIDER_DIAGNOSTIC 的 Host ingest 影响描述不足

- **入口/函数**: `EngineIngestor._ingest_validated()` → Host event dispatch
- **文件(行号)**:
  - `dayu/host/engine_ingest.py:1099-1102`（当前 `PROVIDER_PROTOCOL_ERROR` 事件的 ingest 处理入口）
  - `dayu/host/tool_trace.py:1722-1793`（failure_kind closed set）
- **输入场景**: S2 完成后，Agent 产出新的 `EngineEventType.PROVIDER_DIAGNOSTIC` 事件，携带 `ProviderDiagnosticData`。
- **预期行为**: Host 将 diagnostic event 持久化为 `DIAGNOSTIC` 类型，不触发 Run/Attempt 状态迁移，不写入 tool_trace failure_metadata，不进入 memory projection，不进入 outbox terminal item。
- **实际行为**: Plan S2 声明 "Host EngineEvent ingest must persist the new provider diagnostic as DIAGNOSTIC only, with no Run/Attempt status transition" 和 "Host 持久化 diagnostic event"。但没有描述：
  - `engine_ingest.py` 中的 event type dispatch 如何路由新的 diagnostic event。
  - `tool_trace.py` 的 `_FAILURE_METADATA_ALLOWED_KINDS` closed set 为何不需要新增 diagnostic kind（因为 diagnostic 不是 failure，所以确实不需要——但 plan 应显式声明这一点）。
  - Host EventLog 的 `_EVENT_TYPE_*` 常量命名和 EventLog row shape。
  - diagnostic event 的 durable payload 中必须排除 LLM-facing 字段的显式声明。
- **直接证据**:
  - `engine_ingest.py:1099`: `if event.type == EngineEventType.PROVIDER_PROTOCOL_ERROR and isinstance(event.data, ProviderProtocolErrorData):` — 新 diagnostic 需要一个类似的 handler。
  - `engine_ingest.py:237`: `_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC = "ENGINE_EVENT_DIAGNOSTIC"` 已存在！这意味着 Host 已经有 diagnostic 事件类型的字符串常量，plan 可以复用此常量。
- **影响**: S2 实现者在写 Host ingest 变更时可能遗漏 tool_trace 的排除逻辑验证、memory projection 的 filter 逻辑验证、outbox terminal item 的 filter 逻辑验证。
- **Root cause**: Plan 对 Host 侧的变更描述停留在 "must persist as DIAGNOSTIC only"，没有展开到具体模块的变更点。
- **Owner boundary**: Host engine_ingest 拥有 EngineEvent → Host event 的映射；tool_trace/memory/outbox 各自拥有对 Host event 的消费 filter。
- **建议修复 plan 位置**: S2 Required Changes 中增加一条：验证 `tool_trace.py` 的 `_FAILURE_METADATA_ALLOWED_KINDS` closed set 不需要为 diagnostic 事件新增 kind（因为 diagnostic ≠ failure）；验证 memory projection event filter 排除 `DIAGNOSTIC` 类型；验证 outbox terminal item projection 排除 `DIAGNOSTIC` 类型。
- **需要补充的测试/验证**: S2 测试矩阵已包含 `tests/host/test_engine_ingest_mapping.py`，需要在该文件中增加 diagnostic event 的 ingest 映射测试、tool_trace 排除测试、memory snapshot 不包含 diagnostic 的测试。
- **修复风险**: 低 — 补充描述和验证点，不改变 plan 设计。
- **严重程度**: 高

---

## Open Questions

1. **`_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC` 在 engine_ingest.py:237 已存在**——这个常量是 Phase 2 引入的，但当前没有 EngineEventType 与之对应。Plan S2 引入 `PROVIDER_DIAGNOSTIC` Engine event 后，是否应该直接映射到这个已存在的 Host event type？还是应该新建一个 `PROVIDER_DIAGNOSTIC` 特定类型？

2. **SSE parser 的 `_finish_reason` 为 None 时 `_finalize_success()` 使用 `or FinishReason.STOP`**——这是对 SSE 协议未发送 finish_reason 的隐式补丁。Plan 说 "content success without a finish reason must be explicitly reviewed in S1 tests and documented"。这个审查应在 plan 阶段完成还是在 S1 实现中完成？如果在 S1 实现中完成，发现需要改设计怎么办？

3. **Non-stream `_resolve_finish_reason()` 返回 `FinishReason.STOP` 作为缺失 finish_reason 的默认值**——Plan S1 只提 unknown → fatal error，没有提缺失 finish_reason 的处理。缺失 finish_reason 在非流式场景是否也应 fail closed，还是因为某些 provider 不发送 finish_reason 而需要继续 fallback 为 STOP？

4. **S3 `RunnerSpecificErrorCode` wrapper 的序列化格式**——Plan 说 "Serialization to Host durable JSON uses one helper, not ad hoc .value or raw strings scattered through consumers." 这个 helper 的序列化格式是什么？例如 `RunnerSpecificErrorCode(value="gemini_internal_error")` 序列化为 `"runner_specific:gemini_internal_error"` 还是 `{"kind": "runner_specific", "value": "gemini_internal_error"}`？格式选择会影响 Host read_api 和 tool_trace 的解析逻辑，应在 plan 中明确。

## Residual Risk

1. **S1 与 S2 的边界依赖**: S1 承诺 "不拆分 warning events"，但 S1 改变了 finish_reason → fatal error 的映射后，原本只是 log warning 的 unknown finish_reason 现在会触发 `RunnerProtocolErrorData` + `RunnerDoneData(ERROR)` 的完整 fatal 流程。如果 Agent 的 `RunnerProtocolErrorData` → `failure_candidate` 路径在 S1 时仍然把所有 `RunnerProtocolErrorData` 视为 `PROVIDER_PROTOCOL_ERROR`（这是 S2 才改的），那么 S1 之后的 unknown finish_reason 行为是：emit `RunnerProtocolErrorData` → Agent 设置 `failure_candidate` → Agent emit `PROVIDER_PROTOCOL_ERROR` → Agent 在 iteration 分类时可能 return `RunFailedData`。这个行为是正确的（fail closed），但 `PROVIDER_PROTOCOL_ERROR` 事件仍包含 non-fatal 语义的 unknown finish_reason。这不影响正确性，但在 S1→S2 之间的中间状态中，unknown finish_reason 被分类为 protocol error（fatal），而 diagnostic event 尚未拆分。**风险可控**，但 S1 completion report 应显式记录此中间状态。

2. **SSE parser 和 non-stream parser 的重构共享代码风险**: Plan 说 "preferably in a small adapter-owned helper module only if it removes duplication without creating a seam." 当前 SSE parser 和 non-stream parser 各自有独立的 `_FINISH_REASON_MAP` (完全相同的 dict) 和 finish reason 处理逻辑。如果 S1 引入共享 helper，必须注意不创建胶水 seam（AGENTS.md 禁止）。建议在 plan 中明确共享 helper 的归属模块（如 `dayu/engine/runners/openai/finish_reason_policy.py`），避免两个 parser 交叉依赖。

3. **非流式 parser 的 `_resolve_finish_reason()` 是模块级函数而非 parser 方法**——这与 SSE parser 的 finish_reason 处理（`_handle_choice()` 方法内的内联逻辑）不一致。S1 统一策略时，可能需要将两者归一为同一 helper 或至少同一调用模式。

4. **S3 错误码枚举的 StrEnum 基类选择**: `RunnerHTTPErrorCode` 已经用了 `StrEnum`。S3 的 `EngineRunErrorCode` 和 `RunnerSpecificErrorCode` wrapper 也应使用 `StrEnum` 和一致的序列化模式。但 `RunnerSpecificErrorCode` 是一个 wrapper（不限定值集合），不是 enum。Plan 应明确它使用 `dataclass(frozen=True, slots=True)` 还是 `NewType` 还是其他形式，确保它与 `EngineRunErrorCode` 的联合类型在 `isinstance` 检查和 `match` 语句中可用。

5. **未运行的验证**: 本 review 验证了 plan 中所有 source findings 引用的源码位置，确认了实际代码行为与 plan 描述的差距。以下验证**已运行**：
   - `rg` 扫描所有 referenced 源码的 finish_reason、choice、error_code、context_overflow、warnings 路径
   - 逐行阅读 SSE parser (`_handle_chunk_object`, `_handle_choice`, `_finalize_success`)、non-stream parser (`parse_non_stream_response`, `_resolve_finish_reason`)、tool_call_aggregator (`feed`, `finalize`)、error_classifier (`detect_context_overflow`)、runner (`_call_attempt`)、agent (`_consume_runner_event`)、engine_ingest (`_append_provider_protocol_error`, event dispatch) 的关键路径
   - Agent error_code 常量全集 vs plan S3 列表逐项比对
   - Host 消费者（tool_trace, read_api, engine_ingest）error_code 访问点扫描
   - 已存在 `_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC` 常量的发现

   以下验证**未运行**（非本 gate 范围）：
   - 测试文件的覆盖率验证
   - pyright 运行
   - 实际代码修改和测试执行
