# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S2 Code Review

## Scope

- Mode: current workspace changes, P3-D S2 related tracked modifications and S2 artifacts
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-D`
- Slice: `S2 - Fatal protocol error vs non-fatal provider diagnostic`
- Branch: `phaseflow/host-issues-control`
- Base context: accepted P3-D plan commit `c52519f0`; accepted S1 implementation commit `d009ad11`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-code-review-mimo.md`
- Included scope: S2 production code (13 files), S2 tests (14 files), S2 docs (4 files), S2 artifacts (2 files)
- Excluded scope: unrelated untracked files (`docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`); S3 typed error-code contract (out of S2 scope)
- Parallel review coverage: 无

## Findings

### S2-CR-01-未修复-低-Read API activity status 对 provider diagnostic 使用 COMPLETED 语义模糊

- **入口/函数**: `dayu/host/read_api.py` `_provider_diagnostic_activity()`
- **文件(行号)**: `dayu/host/read_api.py:1461`
- **输入场景**: Host Read API 投影 `PROVIDER_DIAGNOSTIC` EventLog row 为 `HostActivityView`
- **实际分支**: `row.event_type == _EVENT_TYPE_PROVIDER_DIAGNOSTIC` 命中 `_provider_diagnostic_activity`
- **预期行为**: provider 非致命诊断的 activity status 应表达「信息性观测事实」，不暗示操作完成
- **实际行为**: `status=HostActivityStatus.COMPLETED`、`severity=HostActivitySeverity.WARNING`。`COMPLETED` 在本系统中通常表达「某操作成功完成」（如 tool result completed、run succeeded），用于诊断事件时语义模糊：诊断不是一个「完成的操作」，而是一个「被观测到的事实」
- **直接证据**: `dayu/host/read_api.py:1461` 设置 `status=HostActivityStatus.COMPLETED`；对比 `PROVIDER_PROTOCOL_ERROR` 使用 `status=HostActivityStatus.FAILED`（line 1435），两者虽然 kind 相同（`PROVIDER_DIAGNOSTIC`），但 status 语义对比不直觉
- **影响**: 下游 UI 或 Service 层若基于 `COMPLETED` status 判断「操作成功」，可能误判诊断事件为正向结果。实际影响有限因为 `kind=PROVIDER_DIAGNOSTIC` 本身已区分
- **建议改法和验证点**: 当前 `HostActivityStatus` 枚举不含 `INFO` 级别；若不扩展枚举，可保持现状但在 summary 中增加「非致命」标识。此为 S3 枚举扩展的候选项。验证：确认下游消费者不依赖 `COMPLETED` status 语义做业务判断
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### S2-CR-02-未修复-低-context overflow detection=None 路径缺少显式测试覆盖

- **入口/函数**: `dayu/engine/agent.py` `_context_overflow_engine_events()`
- **文件(行号)**: `dayu/engine/agent.py:1617-1622`
- **输入场景**: Runner 发出 `CONTEXT_LENGTH_EXCEEDED` HTTP error，但 `context_overflow_detection` 为 `None`
- **实际分支**: `detection is None` → 返回 `(compaction_event,)`，不产出 diagnostic event
- **预期行为**: `detection=None` 时只产出 `CONTEXT_COMPACTION_REQUESTED`，不产出 `PROVIDER_DIAGNOSTIC`
- **实际行为**: 代码逻辑正确——`if detection is None or detection.kind is not ContextOverflowDetectionKind.MESSAGE_MARKER_FALLBACK` 短路后直接返回 `(compaction_event,)`
- **直接证据**: `dayu/engine/agent.py:1617-1622` 条件判断；`tests/engine/test_agent_phase2.py` 中 `test_context_overflow_marker_fallback_emits_nonfatal_diagnostic`（line 871）只覆盖 `MESSAGE_MARKER_FALLBACK` 路径；无测试显式覆盖 `detection=None` 路径
- **影响**: 若未来重构意外改变 `detection=None` 的行为，无回归测试捕获。当前行为正确
- **建议改法和验证点**: 增加测试用例：`RunnerHTTPErrorData(error_code=CONTEXT_LENGTH_EXCEEDED, context_overflow_detection=None)` → 只产出 `CONTEXT_COMPACTION_REQUESTED`，不产出 `PROVIDER_DIAGNOSTIC`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

- S3 typed Engine error-code contract 未实现，按本 gate non-goal 保留。S2 只承载 provider diagnostic provenance 并保留已有 fatal Engine error 语义
- `tests/engine tests/host` 全量测试包含 Host dispatch / resolve_wait / process-backed runtime 等无关失败，不在 S2 修复范围
- `PROVIDER_PROTOCOL_ERROR` 和 `PROVIDER_DIAGNOSTIC` 在 Read API 投影中共用 `HostActivityKind.PROVIDER_DIAGNOSTIC`，依赖 `status` 字段区分致命/非致命——下游消费者需理解此约定

## Review Evidence Summary

Review emphasis 验证结果：

1. **Provider diagnostics must be non-fatal and never set Agent failure_candidate** ✅
   - `agent.py:1375-1395` `_consume_runner_event` 中 `RunnerProviderDiagnosticData` 分支调用 `_provider_diagnostic_event`，不写 `failure_candidate`
   - `test_provider_diagnostic_does_not_create_failure_candidate` (test_agent_phase2.py:729) 证明诊断后 run 以 `FINAL_ANSWER` 终止

2. **Fatal provider protocol errors must still use RunnerProtocolErrorData / ProviderProtocolErrorData and terminal error behavior** ✅
   - `agent.py:1396-1431` `RunnerProtocolErrorData` 分支设置 `state.failure_candidate = RunFailedData(...)` 并产出 `PROVIDER_PROTOCOL_ERROR` EngineEvent
   - `test_protocol_error_and_error_done_maps_to_run_failed` (test_agent_phase2.py:692) 证明致命协议错误映射到 `RUN_FAILED` terminal

3. **Host PROVIDER_DIAGNOSTIC must be EventClass.DIAGNOSTIC, must not mutate Run/Attempt terminal state or failure metadata** ✅
   - `engine_ingest.py:3362-3366` 设置 `event_class=EventClass.DIAGNOSTIC`
   - `_single_event_result` 返回 `terminal_closeout=False`
   - `test_provider_diagnostic_is_nonfatal_diagnostic_without_failure_metadata` (test_engine_ingest_mapping.py:2253) 证明 payload 不含 `failure_metadata`、Run 状态保持 `RUNNING`

4. **Excluded from Outbox/memory/final answer/evidence/compact/LLM-facing prompts** ✅
   - Outbox: `outbox.py:142-143` filter 只接受 `EventClass.CANONICAL_FACT`，`DIAGNOSTIC` 自动排除
   - `test_provider_diagnostic_is_excluded_from_outbox_terminal_projection` (test_outbox_projection.py:279) 证明 `SKIPPED`
   - LLM-facing leakage: implementation artifact source scan 确认 `dayu/config`、`memory`、`evidence`、`compact`、`terminal_answer` 路径无 `PROVIDER_DIAGNOSTIC` 命中

5. **Tool Trace and Read API may show diagnostics only as non-fatal diagnostic display** ✅
   - `test_tool_trace_projects_provider_diagnostic_without_failure_metadata` (test_tool_trace_projection.py:934) 证明 trace 无 `failure_metadata`、有 `diagnostic_refs`
   - `test_provider_diagnostic_activity_is_nonfatal` (test_host_activity_event_projection.py:611) 证明 activity 为 `COMPLETED/WARNING`、title 为「模型非致命诊断」

6. **Context overflow marker fallback may carry diagnostic provenance, but canonical context_compaction_requested must remain driven by typed RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED** ✅
   - `agent.py:1445-1472` 只在 `error_code is RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 时进入 context overflow 路径
   - `agent.py:1616-1646` `_context_overflow_engine_events` 对 `MESSAGE_MARKER_FALLBACK` 产出 diagnostic + compaction；对 `STRUCTURED_CODE` 只产出 compaction
   - `test_context_overflow_marker_fallback_emits_nonfatal_diagnostic` (test_agent_phase2.py:871) 证明 fallback 路径 diagnostic 使用 `CONTEXT_OVERFLOW_CLASSIFIER` source

7. **Semantic ownership drift, overcoupling, branch ordering, protocol boundary, malformed payload behavior, tests proving negative paths, doc/README alignment, and AGENTS.md constraints** ✅
   - semantic ownership: Runner adapter 是 diagnostic 事实真源 → Agent 同源投影 → Host ingest 持久化，无下游重建语义
   - protocol boundary: `RunnerProviderDiagnosticData` vs `RunnerProtocolErrorData` 类型分离，`assert_never` 守护
   - malformed payload: Host ingest `_append_provider_diagnostic` 用 `_write_raw_payload` 有界持久化，payload 字段有界
   - docs: `docs/engine/design.md`、`docs/host/design.md`、`dayu/engine/README.md`、`dayu/host/README.md` 均已更新
   - AGENTS.md 约束：无反向依赖、无兼容性代码、无 God object、函数有完整 docstring、pyright 0 errors

S2 code review complete.
