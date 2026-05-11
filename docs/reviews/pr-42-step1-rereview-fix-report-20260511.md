# PR #42 Step 1 Re-review Fix Report - 2026-05-11

## 执行边界

- 角色：PR #42 Step 1 re-review fix Agent。
- 范围：只修复 re-review 唯一 finding，即跨 batch ToolTrace 延迟配对导致 analyzer 假 `source_event_position` gap。
- 明确未执行：未进入 Step 2 schema projection，未实现或删除 `schema_provider`、`engine_tool_schema_provider`、`_engine_visible_request` ownership，未修改 controller-authored `docs/host/design.md`，未 commit、push 或更新 PR。

## 根因判断

- finding 成立。`TOOL_CALL_REQUESTED(position=1)` 先被 pending，不写 JSONL；`RUNNER_USAGE_RECORDED(position=2)` 立即写出；`TOOL_RESULT_ACCEPTED(position=3)` 到达后才完成 `tool_call` record。
- 原实现把完成后写出的 `tool_call` record 标记为 requested event 的 `source_event_position=1`，导致 JSONL 写出序为 `2 -> 1`，`analyze_trace_root()` 正常按同 run 写出顺序检测到假 `PositionGap(prev_position=2, next_position=1)`。
- 该 record 的完成事实来源是 accepted/result event，因此生产侧改为使用 accepted/result event position；没有放宽 analyzer 的全局乱序规则。

## 变更内容

- `dayu/host/_tool_trace_projection.py`
  - `tool_call` record 的 `source_event_position` 改为 `TOOL_RESULT_ACCEPTED` envelope position。
  - 更新模块说明与局部注释，明确延迟配对 record 的完成事实来源。
- `tests/host/test_phase7_tool_trace_projection.py`
  - 更新跨 batch pending 测试，断言延迟写出的 `tool_call` 使用 accepted position。
  - 新增端到端测试：分三次处理 request(position 1)、usage(position 2)、accepted(position 3)，走真实 `ToolTraceObserver -> ToolTraceJsonlSink(JSONL) -> analyze_trace_root()` 路径，断言 `source_event_position_gaps == ()`。
- `dayu/host/README.md`
  - 同步 ToolTraceObserver 当前语义：`tool_call` record 在 accepted/result 到达后完成，`source_event_position` 使用 accepted/result position。
- `tests/README.md`
  - 同步 P7 tool trace projection 测试覆盖范围，记录跨 batch 延迟配对经真实 JSONL 后由 analyzer 验证无 position 倒退。

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_phase7_tool_trace_projection.py tests/utils/test_analyze_tool_trace_host.py -q`
  - 结果：`38 passed in 0.17s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check -- dayu/host/_tool_trace_projection.py tests/host/test_phase7_tool_trace_projection.py dayu/host/README.md tests/README.md`
  - 结果：通过，无输出。

## 残余风险

- 本轮没有修改 analyzer gap 规则；正常延迟配对由生产 record position 语义保证单调，真实乱序仍会被 analyzer 报告。
- 本轮没有审查或实现 Step 2 schema projection ownership。
- 工作区进入本轮前已有大量 Step 1 dirty changes，包括 `docs/host/design.md`；本轮未回滚、未整理、未提交这些既有改动。
