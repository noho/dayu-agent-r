# PR #42 Step 1 Fix Re-review

## Findings

### 001-未修复-[中]-跨 batch tool trace 配对会生成正常 trace 的假 position gap

- **入口/函数**: `ToolTraceObserver.process_non_transactional()` -> `_collect_tool_call()` -> `_emit_tool_call()`；`utils.analyze_tool_trace_host.analyze_trace_root()`
- **文件(行号)**: `dayu/host/_tool_trace_projection.py:211`, `dayu/host/_tool_trace_projection.py:251`, `dayu/host/_tool_trace_projection.py:258`, `dayu/host/_tool_trace_projection.py:328`, `utils/analyze_tool_trace_host.py:704`, `utils/analyze_tool_trace_host.py:714`
- **输入场景**: `TOOL_CALL_REQUESTED` 在 batch 1，`RUNNER_USAGE_RECORDED` 在 batch 2，匹配的 `TOOL_RESULT_ACCEPTED` 在 batch 3。这是 Step 1 要支持的正常跨 batch 配对场景。
- **实际分支**: batch 1 中 request 只进入 `_pending_tool_call_groups`，不写 JSONL；batch 2 的 usage 立即写出 `source_event_position=2`；batch 3 的 accepted 到达后才触发 `_emit_tool_call()`，但 `ToolCallRecord.source_event_position` 取 requested event 的 position，也就是 `1`。
- **预期行为**: 跨 batch 配对生成的 trace 应被 analyzer 视为正常、可用的 trace；不应因为 Step 1 的 pending 配对策略对合法事件序列报 `source_event_position_gaps`。
- **实际行为**: JSONL 写入顺序变成 `iteration_usage(position=2)` 后接 `tool_call(position=1)`；analyzer 按 JSONL 写入顺序检查同 run 的 `source_event_position` 单调性，于是报告 `PositionGap(prev_position=2, next_position=1)`。
- **直接证据**:
  - `_collect_tool_call()` 在 request 半边只暂存，accepted 半边到达后才 `pop` 并 `_emit_tool_call()`（`dayu/host/_tool_trace_projection.py:246-260`）。
  - `_emit_tool_call()` 将 `source_event_position` 固定为 `group.requested.position.value`（`dayu/host/_tool_trace_projection.py:327-345`）。
  - analyzer 明确保留 JSONL entries 顺序并把后一个 position 小于前一个 position 记为 gap（`utils/analyze_tool_trace_host.py:704-725`）。
  - 本次 re-review 用同一路径复现：三批依次处理 request(position 1)、usage(position 2)、accepted(position 3)，`analyze_trace_root()` 返回 `PositionGap(run_id='run-1', prev_position=2, next_position=1)`。
- **影响**: Step 1 修复了“跨 batch / fresh observer restart 丢 trace或 BLOCKED_FAILED”的主问题，但产生了新的分析语义回归：正常跨 batch trace 会被诊断为 source position 倒退，降低 trace analyzer 的可信度，也会干扰 PR #42 对 “ToolTrace request/result pairing checkpoint safety” 的验收。
- **建议改法和验证点**: 二选一固定语义并补端到端测试：
  - 让配对完成后生成的 `tool_call` record 使用 accepted event 的 `source_event_position`，表示该 record 的完成事实来源；或
  - 保持 requested position，但调整 analyzer 的 position gap 检测，使其理解延迟配对 record 的合法乱序，而不是把它当 trace 损坏。
  - 新增测试应走真实 `ToolTraceObserver -> JSONL -> analyze_trace_root()` 路径，覆盖 request / usage / accepted 分属不同 batch，断言无 `source_event_position_gaps`。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

## Conclusion

- conclusion: fail
- Step 1 暂不建议进入 Step 2。原因不是 Step 2 的 EngineWorker/schema projection ownership 未实现，而是 Step 1 自身的 trace pairing 修复引入了 analyzer 语义回归。

## Scope

- Mode: current workspace Step 1 fix re-review
- Branch or PR: `migration/host-p8-5-stabilization` / PR #42
- Base: `main`
- Output file: `docs/reviews/pr-42-step1-fix-rereview-20260511.md`
- Included scope: 仅审 Step 1 修复项与其测试 / README / analyzer 一致性。
- Excluded scope: schema_provider / engine_tool_schema_provider / `_engine_visible_request` ownership 重构；raw payload/chat history retention/delete policy；P8.6 recovery model；P15 hard-gate/watchdog；P16 interface freeze；cursor 持久化 SQLite store；repair TOCTOU；BEGIN IMMEDIATE scan redesign。
- Parallel review coverage: 无。

## Step 1 Checks

- start_run admission 半提交：schema conflict 已在 `USER_INPUT_ACCEPTED` 前预检；initial attempt acquire/admission failure 已在已接纳输入后写 Host-owned terminal。
- ToolTrace request/result pairing：跨 batch 与 fresh observer restart 不再永久丢 trace或 `BLOCKED_FAILED`，但见 Finding 001 的 analyzer position gap 回归。
- ProviderProtocolErrorData / RunFailedData credential scrub：EventLog serializer、event translation 与 trace projection 对显式凭证有清洗；普通 cursor、scope_token、普通 token 保留。
- `_resolve_ttl_seconds(float("inf"))`：已通过 finite 检查回落默认 TTL。
- `PartialToolCallSummary.tool_call_id`：已有 128 字符边界，并有测试覆盖。
- Host serializer `partial_tool_calls`：缺字段 fail-fast；显式空列表可用。
- compact retry snapshot failure：已写 terminal，并保留 owner-lost/fencing 路径。
- FrameworkToolSet fetch_more callable：直接调用 fail-fast。
- `ToolCallRecord` 旧 cursor/fetch_more forever-None 字段：生产 schema 已删除；analyzer 保留 legacy 字段忽略测试。
- Step 1 新增/修改测试：大多走真实入口；Finding 001 说明仍缺一个 observer 到 analyzer 的端到端断言。
- low-risk cleanup：`ToolValueSizeSummary` 删除、emit-before-pop、`extract_truncation_hint(has_more=False)`、`assert_never` 等均已落地。

## Open Questions

- 无。

## Residual Risk

- 本次未审 Step 2 controller-authored `docs/host/design.md` schema projection design 是否可实施；该项按用户指令不作为 Step 1 finding。
- 未重跑真实 provider smoke 或多进程 stress；本轮验证覆盖 Step 1 focused tests、pyright 与 `tests/host`。

## Validation

- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_protocol_error.py tests/host/test_phase2_tool_runtime_boundary.py tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase4_overflow_retry.py tests/host/test_phase6_run_event_serializer.py tests/host/test_phase7_tool_trace_projection.py tests/host/test_phase8_5_framework_tools.py tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_supervisor.py tests/utils/test_analyze_tool_trace_host.py -q`
  - Result: `159 passed in 0.71s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pytest tests/host -q`
  - Result: `418 passed in 2.70s`
- Reproduction for Finding 001: direct `ToolTraceObserver -> ToolTraceJsonlSink -> analyze_trace_root()` script with request(position 1), usage(position 2), accepted(position 3) returned `PositionGap(run_id='run-1', prev_position=2, next_position=1)`.
