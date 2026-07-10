# WU-SEMANTIC-OWNERSHIP-01 P3-D Plan Review — AgentMiMo

## Scope

- Mode: adversarial plan review (plan artifact only, no code changes)
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-D`
- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-d-engine-provider-protocol-normalization-plan.md`
- Source adjudication: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md` P3-D
- Design docs: `docs/engine/design.md`, `docs/host/design.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Review date: 2026-07-10

## Verdict

**FINDINGS** — 3 High, 6 Medium, 3 Low. No blocking architectural contradictions, but several plan gaps must be resolved before implementation.

## Source Finding Disposition Verification

All 6 source findings confirmed as current code behavior with direct source evidence. None are obsolete.

| Source finding | Disposition | Direct evidence |
|---|---|---|
| AgentCodex 4: fatal/warning mix | accepted-current | `tool_call_aggregator.py:145-146` separates `_fatal_errors`/`_warnings`; `agent.py:1359-1392` unconditionally sets `failure_candidate(recoverable=False)` for all `RunnerProtocolErrorData` |
| AgentCodex 5: multi-choice asymmetry | accepted-current | `sse_parser.py:464-476` iterates all choices into shared buffer; `non_stream_parser.py:252-269` picks `choices[0]` only |
| AgentDS 2: bare string error codes | accepted-current | `runner_events.py:161` `error_code: str`; `engine_events.py:356,457` `error_code: str`; `agent_run.py:152` `error_code: str` |
| AgentDS 4: marker fallback | accepted-current | `error_classifier.py:91-116` two-tier: structured code then English substring match; provenance not persisted |
| AgentDS 21: unknown finish_reason → STOP | accepted-current | `sse_parser.py:538-547` logs warning, `_finish_reason` stays `None`; `sse_parser.py:707` `self._finish_reason or FinishReason.STOP`; `non_stream_parser.py:390-408` explicitly returns `STOP` |
| AgentMiMo BI-7: hardcoded markers | accepted-current | `error_classifier.py:35-42` module-level tuple, no runtime configurability |

**No obsolete findings missed.** All claims match current code.

## Owner Boundary Verification

The plan's owner boundary is correct:

- **Runner adapters** own first normalization (confirmed by `docs/engine/design.md:12,169-176` and `docs/host/design.md:51`).
- **Agent** owns RunnerEvent consumption and EngineEvent projection (confirmed by `docs/engine/design.md:14,254,268`).
- **Host** owns persistence and projection after EngineEvent ingest (confirmed by `docs/host/design.md:51,333`).
- **Host/Agent must not see raw provider wire payloads** (confirmed by design docs).

The propagation audit path is correctly specified and aligns with design truth.

## Findings

### P3-D-PR-001 — [高] — S2 缺少 Host 非致命诊断事件的 EventLog event_type 定义

- **入口/函数**: plan S2 `Required changes`
- **文件(行号)**: plan line 180-183
- **输入场景**: 实现 S2 时需要在 `engine_ingest.py` 中为非致命 provider 诊断定义 EventLog event_type 字符串
- **实际分支**: plan 只说 "Host EngineEvent ingest must persist the new provider diagnostic as `DIAGNOSTIC` only"，未指定 EventLog event_type
- **预期行为**: plan 应明确新事件的 EventLog event_type 字符串、EventClass 选择、以及是否需要更新 Host 设计真源的 canonical event matrix
- **实际行为**: plan 未定义。当前代码中 `PROVIDER_PROTOCOL_ERROR` 使用 `EventClass.DIAGNOSTIC` + event_type `"PROVIDER_PROTOCOL_ERROR"`（`engine_ingest.py:3291-3296`）。新非致命事件需要不同的 event_type 以区分致命/非致命
- **直接证据**: `engine_ingest.py:3291-3296` 使用 `EventClass.DIAGNOSTIC` + `_EVENT_TYPE_PROVIDER_PROTOCOL_ERROR`；`tool_trace.py:226` 有 `_DIAGNOSTIC_EVENT_TYPES` tuple 需要更新；`docs/host/design.md:1518` 的 canonical event matrix 没有通用 `DIAGNOSTIC` 行
- **影响**: 实现 agent 需要自行决定 event_type 命名，可能导致与现有 `PROVIDER_PROTOCOL_ERROR` 混淆或命名不一致
- **建议改法和验证点**: 在 S2 Required changes 中明确：(1) 新 EventLog event_type 字符串（如 `"PROVIDER_DIAGNOSTIC"`）；(2) EventClass 选择（`DIAGNOSTIC`）；(3) 是否需要在 `docs/host/design.md` 13.3 节 canonical event matrix 中新增行；(4) `tool_trace.py` 的 `_DIAGNOSTIC_EVENT_TYPES` 更新
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### P3-D-PR-002 — [高] — S3 范围过大，未说明为何不能按依赖边界拆分

- **入口/函数**: plan S3 `Required changes` + `Candidate files`
- **文件(行号)**: plan line 218-261
- **输入场景**: 实现 S3 时需要同时修改 Engine contracts、Agent、Host ingest/read/outbox/tool-trace，并添加弱类型守卫和 propagation audit
- **实际分支**: S3 涵盖三个不同语义类别：(1) contract/enum 定义；(2) Agent/Host runtime 消费转换；(3) 弱类型守卫 + propagation audit + docs
- **预期行为**: 按 `issues-implementation-control.md` slice 切分原则，超过 3 个 slices 需要明确证据说明为何不能合并。S3 自身跨越 contract、behavior、docs 三个类别且涉及 14+ 文件，应说明为何这是同一个可验证闭环
- **实际行为**: plan 只在 Residual risk 中说 "update all in-repo callers/tests in the same slice and fail fast for old string construction"，但未正式论证 S3 不可拆
- **直接证据**: S3 candidate files 包含 `dayu/engine/contracts/agent_run.py`（`EngineRunOutcomeFailed.error_code: str` at line 152）、`dayu/engine/contracts/engine_events.py`、`dayu/engine/contracts/runner_events.py`、`dayu/engine/agent.py`、`dayu/host/engine_ingest.py`、`dayu/host/read_api.py`、`dayu/host/tool_trace.py`、`dayu/host/outbox.py`、以及 7+ test files。`issues-implementation-control.md:134-148` 要求 slice 沿依赖边界切分且形成可独立验证闭环
- **影响**: 如果 S3 不可拆，实现 agent 的上下文窗口可能无法稳定承载 contract 定义 + 全量 caller 转换 + 弱类型守卫 + propagation audit
- **建议改法和验证点**: 在 S3 中增加显式论证：(1) 为何 contract 定义和 caller 转换必须在同一 slice（项目禁止兼容 facade，所有 caller 必须原子更新）；(2) 弱类型守卫和 propagation audit 是否可以作为 S3 的验证步骤而非独立 slice；(3) 如果 S3 确实超过单个 agent 上下文容量，建议拆为 S3a（contract + enum + Engine/Agent 转换）和 S3b（Host consumer 转换 + 弱类型守卫 + propagation audit）
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### P3-D-PR-003 — [中] — 流式 multi-choice 拒绝时机未明确

- **入口/函数**: plan Contract Decisions 第 1 点
- **文件(行号)**: plan line 96
- **输入场景**: SSE 流式响应中，第一个 chunk 有 `choices[0]`，后续 chunk 有 `choices[1]`
- **实际分支**: plan 说 "If a provider returns more than one valid assistant choice... the adapter emits a fatal provider protocol error"，但未说明是在流式处理中逐 chunk 检测还是在 `_finalize_success()` 中最终检测
- **预期行为**: plan 应明确：(1) SSE parser 是否在 `_handle_chunk_object()` 中跟踪 choice index 并在看到第二个有效 assistant choice 时立即 yield 错误；(2) 还是在 `_finalize_success()` 中检查所有 seen choices
- **实际行为**: 当前代码 `sse_parser.py:464-476` 遍历所有 choices 并合并到同一个 buffer。plan 要求 exactly-one-choice 但未说明流式场景的拒绝时机
- **直接证据**: `sse_parser.py:464-476` iterates all choices; plan line 96 "If a provider returns more than one valid assistant choice... the adapter emits a fatal provider protocol error and `RunnerDoneData(ERROR)`"
- **影响**: 实现 agent 可能选择不同的拒绝策略（early reject vs late reject），导致行为不一致
- **建议改法和验证点**: 在 S1 Required changes 中明确流式 multi-choice 的拒绝时机。建议在 `_handle_chunk_object()` 中跟踪 seen choice indices，第二个有效 assistant choice 出现时 yield fatal error。非流式路径在 `_emit_from_dict()` 中检查 `len(choices) > 1`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### P3-D-PR-004 — [中] — S1 负面测试未覆盖非字符串 finish_reason 类型

- **入口/函数**: plan S1 `Testing matrix`
- **文件(行号)**: plan line 134-136
- **输入场景**: provider 返回 `finish_reason: 123`（int）、`finish_reason: null`、`finish_reason: true`（bool）
- **实际分支**: plan 要求 "unknown non-empty string is a fatal provider protocol error"，但未明确非字符串类型如何处理
- **预期行为**: plan 应要求测试覆盖非字符串 finish_reason 类型：int、null、bool、array、object
- **实际行为**: 现有测试 `test_non_stream_response.py` 有 `test_non_stream_unknown_finish_reason_logs_diagnostic` 但未覆盖非字符串类型。plan 的 source scan `rg -n "unknown_finish_reason|FinishReason\\.STOP|finish_reason or FinishReason\\.STOP"` 不覆盖非字符串场景
- **直接证据**: `non_stream_parser.py:390-408` `_resolve_finish_reason()` 检查 `isinstance(raw, str)`；如果不是 str，直接返回 `STOP`（无 log、无 error）。`sse_parser.py:538-547` 同样检查 `isinstance(finish_reason, str)`
- **影响**: 非字符串 finish_reason 会被静默忽略并 fallback 到 STOP，与 plan 的 fail-closed 原则矛盾
- **建议改法和验证点**: 在 S1 Testing matrix 中增加负面测试：(1) `finish_reason: 123` → 应为 fatal protocol error（非 str 且非 null）；(2) `finish_reason: null` → 明确是否允许（当前代码允许）；(3) `finish_reason: true` → 应为 fatal protocol error
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### P3-D-PR-005 — [中] — S3 source scan 不覆盖 `EngineRunOutcomeFailed` 构造和 Host 消费端

- **入口/函数**: plan S3 `Source scans`
- **文件(行号)**: plan line 259-260
- **输入场景**: 实现 S3 后需要验证所有 error_code 字段已从 bare str 转为 typed enum/wrapper
- **实际分支**: source scan 只覆盖 `error_code: str|error_code="|error_code=data.error_code` 和 `RunFailedData(|ProviderProtocolErrorData(|RunnerProtocolErrorData(`
- **预期行为**: scan 应覆盖所有 error_code 字段的构造和消费端
- **实际行为**: 缺少：(1) `EngineRunOutcomeFailed(error_code=...)` 构造（`agent_run.py:152`）；(2) Host 消费端读取 error_code 的模式（`engine_ingest.py` 中 `data.error_code` 的使用、`read_api.py` 中 `error_code` 的读取）；(3) `_append_terminal_diagnostic_suffix` 中 error_code 的使用
- **直接证据**: `agent_run.py:135-157` 定义 `EngineRunOutcomeFailed` 有 `error_code: str`；`engine_ingest.py:1099-1103` 读取 `data.error_code`；`read_api.py:1415-1426` 读取 `error_code` 和 `provider_error_code`
- **影响**: S3 完成后可能遗漏未转换的 error_code 字段，导致 typed/bare string 混用
- **建议改法和验证点**: 扩展 S3 source scan：(1) 增加 `rg -n "EngineRunOutcomeFailed\\(" dayu/engine tests/engine`；(2) 增加 `rg -n "error_code" dayu/host/engine_ingest.py dayu/host/read_api.py dayu/host/tool_trace.py`；(3) 增加 `rg -n "failure_metadata.*error_code|provider_error_code" dayu/host`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### P3-D-PR-006 — [中] — S2 未列出 `runner.py` 为 context-overflow 返回值重构的 candidate file

- **入口/函数**: plan S2 `Required changes` 第 6 点
- **文件(行号)**: plan line 185-186
- **输入场景**: `detect_context_overflow()` 返回值从 `bool` 改为 `ContextOverflowDetection` typed result
- **实际分支**: plan 说 "Refactor context-overflow detection to return a typed result"，S2 candidate files 包含 `error_classifier.py`，但未包含 `runner.py`
- **预期行为**: `runner.py` 调用 `detect_context_overflow()` 并使用返回值判断是否设置 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`。返回值类型变化需要更新 `runner.py` 的调用代码
- **实际行为**: S2 candidate files 列表不包含 `dayu/engine/runners/openai/runner.py`
- **直接证据**: `runner.py` 是 `detect_context_overflow()` 的调用方（通过 `classify_http_status()` 间接调用或直接调用）。返回值从 `bool` 改为 `ContextOverflowDetection` 需要更新消费端
- **影响**: 实现 agent 可能遗漏 `runner.py` 的更新，导致类型不匹配
- **建议改法和验证点**: 在 S2 Candidate files 中增加 `dayu/engine/runners/openai/runner.py`。明确 `ContextOverflowDetection` 的消费路径：`error_classifier.py` → `runner.py` → `agent.py`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### P3-D-PR-007 — [中] — `RunnerSpecificErrorCode` wrapper 空字符串处理未明确

- **入口/函数**: plan Contract Decisions 第 6 点
- **文件(行号)**: plan line 101
- **输入场景**: provider 返回 error_code 为空字符串 `""`
- **实际分支**: plan 说 "The wrapper must validate non-empty bounded text"，但未明确空字符串是否应该 fail-closed
- **预期行为**: plan 应明确空字符串 error_code 的处理策略
- **实际行为**: 只说了 "non-empty bounded text"，未说明空字符串是 reject 还是 fallback 到某个默认值
- **直接证据**: plan line 101 "The wrapper must validate non-empty bounded text and should make the source explicit"
- **影响**: 实现 agent 可能对空字符串采取不同策略（raise vs fallback vs 默认值）
- **建议改法和验证点**: 明确空字符串 error_code 应为 fatal protocol error（fail-closed），并在 S3 Testing matrix 中增加空字符串负面测试
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### P3-D-PR-008 — [低] — S2 未分析新诊断事件对 outbox 的影响

- **入口/函数**: plan S2 `Candidate files` + `Required changes`
- **文件(行号)**: plan line 158-206
- **输入场景**: 新增非致命 provider diagnostic EngineEvent 后，Host outbox 是否需要感知
- **实际分支**: S2 candidate files 不包含 `dayu/host/outbox.py`
- **预期行为**: plan 应明确 outbox 是否需要变更（即使结论是"不需要"）
- **实际行为**: `outbox.py:140-147` 的 `event_filter` 只接受 `EventClass.CANONICAL_FACT` + terminal event types。新诊断事件使用 `EventClass.DIAGNOSTIC` 会被自动过滤。plan 未说明这一点
- **直接证据**: `outbox.py:82` `_HOST_TERMINAL_EVENT_TYPE_VALUES`；`outbox.py:140-147` `ProjectionEventClassFilter`
- **影响**: 低。outbox 不需要变更，但 plan 应明确说明以避免实现 agent 误改
- **建议改法和验证点**: 在 S2 Required changes 或 Residual risk 中明确："outbox 不需要变更，因为诊断事件使用 EventClass.DIAGNOSTIC 而非 CANONICAL_FACT，会被 outbox event_filter 自动过滤"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### P3-D-PR-009 — [低] — S1/S2 之间依赖未显式说明

- **入口/函数**: plan Implementation Slices
- **文件(行号)**: plan line 103-206
- **输入场景**: 实现 agent 需要知道 S1 完成后才能开始 S2
- **实际分支**: S1 修改 adapter 的 choice/finish-reason policy；S2 新增诊断事件类型并迁移非致命 cases
- **预期行为**: plan 应显式说明 S2 depends on S1（因为 S2 迁移的非致命 cases 中有些可能受 S1 的 finish-reason policy 影响）
- **实际行为**: plan 未显式声明 slice 间依赖
- **直接证据**: S1 修改 unknown finish_reason 行为（从 fallback STOP 改为 fatal error）；S2 需要迁移 `unknown_finish_reason` 的 warning 到非致命诊断事件。如果 S1 先将 unknown finish_reason 改为 fatal error，S2 的迁移目标可能不同
- **影响**: 低。实现 agent 按顺序执行 S1→S2→S3，但缺少显式依赖可能导致跳 slice
- **建议改法和验证点**: 在 S2 Non-goals 或开头增加 "S2 depends on S1: S1 establishes the fatal finish_reason policy; S2 migrates remaining non-fatal cases to diagnostic events"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### P3-D-PR-010 — [低] — S2 未明确 `read_api.py` 对新诊断事件的 activity projection 行为

- **入口/函数**: plan S2 `Candidate files`
- **文件(行号)**: plan line 168
- **输入场景**: Host read_api 需要将新的非致命 provider diagnostic 事件投影为用户可见的 activity
- **实际分支**: S2 candidate files 包含 `dayu/host/read_api.py`，但 Required changes 未说明 read_api 需要什么变更
- **预期行为**: plan 应明确 read_api 是否需要新增 activity projection 分支、新 `HostActivityKind`、以及 title/summary 格式
- **实际行为**: `read_api.py:1060-1095` 的 `_activity_from_row` 使用 allowlist dispatch；`PROVIDER_PROTOCOL_ERROR` 映射到 `_provider_protocol_error_activity`（line 1407-1437）生成 `HostActivityKind.PROVIDER_DIAGNOSTIC`。新诊断事件需要新分支
- **直接证据**: `read_api.py:1093-1094` 处理 `PROVIDER_PROTOCOL_ERROR`；`read_api.py:1429` 使用 `HostActivityKind.PROVIDER_DIAGNOSTIC`
- **影响**: 低。实现 agent 可能遗漏 read_api 更新，导致新诊断事件不可见
- **建议改法和验证点**: 在 S2 Required changes 中增加 "read_api.py 需要新增非致命诊断事件的 activity projection 分支，复用或扩展 `HostActivityKind.PROVIDER_DIAGNOSTIC`"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- **Host 设计真源是否需要为非致命 provider 诊断新增 canonical event matrix 行？** `docs/host/design.md:1533` 的 canonical event matrix 没有通用 `DIAGNOSTIC` 行。当前 `PROVIDER_PROTOCOL_ERROR` 使用 `EventClass.DIAGNOSTIC`（`engine_ingest.py:3295`），但不在 canonical event matrix 中。新非致命诊断事件是否应进入 canonical event matrix？这影响 Host 设计真源是否需要在 S2 之前更新。
- **S3 是否需要拆分？** plan 的 "update all in-repo callers/tests in the same slice" 论证对于 type-change 是合理的（项目禁止兼容 facade），但 S3 涉及 14+ 文件跨 Engine/Host 两个包。需要实现 agent 的实际上下文容量来判断。如果拆分，建议 S3a（contract + enum + Engine/Agent）+ S3b（Host consumers + weak-typing guard + propagation audit）。

## Residual Risk

- **S2 对 `docs/engine/design.md` 和 `docs/host/design.md` 的更新范围未量化。** plan 列出了 README/docs trigger，但未明确需要更新哪些具体 section。Engine design doc 的 RunnerEvent table（section 9）需要新增诊断事件类型；Host design doc 的 EngineEvent mapping（section 13.4）需要新增映射行。
- **S3 的 weak-typing guard 具体机制未指定。** plan 说 "Add weak-typing/source-scan checks to prevent new Engine error-code fields from regressing to bare `str`"，但未说明是 pyright 配置、import guard、CI check、还是测试断言。需要在 plan 中明确。
- **`detect_context_overflow()` 返回值重构影响链未完整追踪。** 从 `error_classifier.py` → `runner.py` → `agent.py` → `engine_ingest.py` 的完整调用链中，返回值类型变化的影响需要逐层确认。S2 candidate files 已包含 `error_classifier.py` 和 `agent.py`，但缺少 `runner.py`（见 P3-D-PR-006）。

## Verification Status

| Verification | Status |
|---|---|
| Source finding direct evidence check | ✅ 已运行 — 6/6 确认为当前代码行为 |
| Owner boundary alignment with design docs | ✅ 已运行 — 对齐 |
| Slice independence and closure check | ⚠️ 已运行 — S3 需要显式论证 |
| Contract decisions best-practice check | ✅ 已运行 — 无过度设计 |
| Propagation audit completeness check | ⚠️ 已运行 — S2 新诊断事件的 propagation 路径需补充 |
| Test coverage for existing test files | ✅ 已运行 — 10 个 candidate test files 均存在且实质性覆盖 |
| Negative test coverage gap check | ⚠️ 已运行 — 非字符串 finish_reason 类型未覆盖 |
| Source scan completeness check | ⚠️ 已运行 — S3 scan 不覆盖 `EngineRunOutcomeFailed` 构造和 Host 消费端 |
| AGENTS.md violation check | ✅ 已运行 — 无兼容 wrapper/facade、Any/object、extra payload、hasattr/getattr、反向依赖、魔法字符串、下游补丁 |
| README trigger check | ✅ 已运行 — S2/S3 正确列出 `dayu/engine/README.md`、`docs/engine/design.md`、`dayu/host/README.md`、`tests/README.md` |
| pyright / coverage / git diff --check | ✅ Validation Summary 中已列出 |
| Design doc update scope quantification | ⚠️ 未运行 — S2/S3 的 design doc 更新范围未量化 |
