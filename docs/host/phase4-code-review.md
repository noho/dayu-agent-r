# Host P4 Code Review

## 结论

未通过，有 findings。

本次 review 只检查当前未提交 P4 实现，不修改生产代码。参考材料：

- `docs/host/phase4-plan.md`
- `docs/host/design.md`
- `docs/host/phase4-plan-review.md`
- `AGENTS.md`
- 当前 git diff

## Findings

### [P1] [已修复，待复查] 同一 Run 内 overflow 前已落库的工具事实没有进入 compacted attempt

位置：

- `dayu/host/_run_harness.py:337`
- `dayu/host/_run_harness.py:351`
- `dayu/host/_run_harness.py:362`
- `dayu/host/_run_harness.py:436`
- `dayu/host/_context_compaction.py:115`
- `dayu/host/_context_compaction.py:294`
- `dayu/host/_conversation_memory.py:630`

问题：

当前 `_run_to_store` 会在 overflow 之前正常 append Engine canonical 事件，包括 `TOOL_CALL_REQUESTED` /
`TOOL_RESULT_ACCEPTED` 等工具事实。但进入 `_compact_or_fail` 后，compact 输入只读取
`ConversationMemoryStore.get_snapshot()`、原始 `USER_INPUT_ACCEPTED` 与旧 `RunInputBuildTrace`，并没有从
`RunEventStore` 读取本 Run 已经 append 的 canonical tool facts。由于 `_project_run_events()` 只在最终
terminal 后执行，当前 Run 内 overflow 前产生的工具事实此时还没有进入 memory snapshot。

实际后果：

若 Agent 第一次 attempt 先完成工具调用，然后在下一轮 LLM 调用因工具结果导致 context overflow，Host 会生成
compacted `RunInput` 并重试，但这次重试只保留旧 snapshot 里的 tool facts，丢失本 Run 刚产生的
`TOOL_RESULT_ACCEPTED` / truncate / cursor facts。模型会在同一 Run 的新 internal attempt 中看不到刚查到的财报证据，
轻则重复工具调用，重则基于不完整证据回答。这违反 P4 要求的“compact 输入来自 `USER_INPUT_ACCEPTED`、canonical
terminal / tool facts、memory snapshot 与 trace 中可消费事实”，也和 README 中“保留 evidence anchors、source cursor 与
tool facts”的当前事实表述不一致。

当前测试 `tests/host/test_phase4_overflow_retry.py` 只覆盖“第一次 attempt 立刻 overflow，然后第二次成功”的 fake
路径，没有覆盖 overflow 前已经 append tool events 的场景，因此没有暴露该回归。

建议：

compact 前应读取本 Run 当前 EventLog 中已 append 的 canonical tool facts，并通过和 memory projection 同源的转换逻辑纳入
compact 输入；或者先抽出一个可复用的工具事实投影 helper，让 compact 与 memory projection 共享同一事实来源。随后补测试：
同一 Run 中 `TOOL_RESULT_ACCEPTED` 先落 EventLog，再出现 recoverable `context_compaction_required`，断言第二次
attempt 的 compact memory 保留该 tool fact 的 tool_call_id、source cursor 与摘要。

修复说明：

- 已新增 `snapshot_with_transient_tool_facts()`，compact 前从本 Run 当前 EventLog 读取 canonical tool facts，并复用 memory projection 的 tool fact / evidence anchor 转换逻辑临时合并进 compact snapshot。
- `_compact_or_fail()` 现在使用合并后的 snapshot 构造 compacted RunInput；同一 Run 内 overflow 前已 append 的 `TOOL_RESULT_ACCEPTED`、truncate/cursor/fetch 类工具事实可进入第二次 attempt。
- 已补 `tests/host/test_phase4_overflow_retry.py::test_same_run_tool_facts_enter_compacted_attempt`，覆盖 tool_call_id、source_event_cursor、cursor_fingerprint、has_more。

### [P2] [已修复，待复查] compact 路径异常会留下无终态 Run，订阅方可能永久等待

位置：

- `dayu/host/_run_harness.py:357`
- `dayu/host/_run_harness.py:362`
- `dayu/host/_run_harness.py:386`
- `dayu/host/_run_harness.py:437`
- `dayu/host/_run_harness.py:650`

问题：

`_run_to_store` 只把 proxy/worker 建流与取流异常转换为 Host-owned failure。进入 compact 分支后，
`_compact_or_fail()` 的异常会直接逃出后台 task；`finally` 中只有 `terminal_seen=True` 时才投影，且不会补
Host-owned terminal。一个直接触发点是 `previous_trace = self.last_run_input_build_trace_by_run[request.run_id]`：
trace 缓存是 FIFO 且有上限，多个 Run 并发启动并在旧 Run overflow 前超过 `run_input_trace_cache_limit` 时，旧 Run 的 trace
会被淘汰，随后这里抛 `KeyError`。此外 compact coordinator 或 event append 中的非预期异常也会走同一路径。

实际后果：

EventLog 会停在 `USER_INPUT_ACCEPTED`、可能还有 `context_compaction_requested` / `context_overflow_observed` 等非终态事实；
不会 append `RUN_FAILED`，`RunStream.events` 订阅因没有 terminal 可能一直等待，`get_run_result()` 也一直返回 `None`。
这破坏 P4 “compact 失败必须 Host failed terminal 收口”与“真正 terminal 唯一且最后”的可恢复语义。P3 对 Host 内部错误不伪装
为 worker failure 的原则仍成立，但 compact governance 自身的可预期失败应被收口为 Host-owned terminal，而不是让 Run 悬挂。

建议：

把 compact 分支的可预期失败纳入显式 `HostContextCompactFailedData` + Host-owned `RUN_FAILED` 收口，例如缺少 trace 时使用新的
强类型 failure reason，或在 compact 前保证 trace 是 per-run 生命周期状态而不是可淘汰调试缓存。补测试：设置
`run_input_trace_cache_limit=1`，启动两个 Run 淘汰第一个 trace，再让第一个 Run overflow，断言最终得到 Host-owned failed
terminal 且订阅流结束。

修复说明：

- 已新增 `ContextCompactFailureReason.TRACE_MISSING` / `INTERNAL_ERROR` 与 `ContextCompactCoordinator.exception_failed()`。
- `_compact_or_fail()` 对 trace 缓存缺失显式追加 `context_compact_failed` 与 Host-owned `RUN_FAILED`；compact 分支其它异常也会由 `_append_compact_exception_failure()` 收口，避免订阅永久等待。
- 已补 `tests/host/test_phase4_overflow_retry.py::test_missing_trace_cache_compact_failure_gets_host_terminal`，覆盖 trace cache limit 很小时旧 Run overflow 的 Host-owned failed terminal。

## 通过项

- recoverable `RUN_FAILED(error_code="context_compaction_required")` 当前不会被 append 成 Engine terminal；Host 会转成
  `context_overflow_observed` 后进入 compact / retry，因此不会直接污染 `get_run_result()` 或 memory terminal projection。
- compact success gate 同时检查 token 与 char 都严格变短，并检查当前用户、pinned state、evidence anchors、source cursor 与
  tool facts 的保真标志；no-op 路径会收口为 Host-owned failed terminal。
- same Run / new internal attempt 当前没有再次 append `USER_INPUT_ACCEPTED`；已有测试覆盖一次成功 retry 与 retry limit failure。
- RunInputBuilder 与 CompactCoordinator 已共用 `dayu.host._token_estimator`，pyright 当前未发现类型错误。
- README/docs 基本写的是当前已落地能力，并明确 fake smoke 不代表真实 provider overflow 覆盖。

## 验证

- `source .venv/bin/activate && pytest tests/host`：通过，105 passed。
- `source .venv/bin/activate && pytest tests/engine`：通过，297 passed。
- `source .venv/bin/activate && pyright`：通过，0 errors。

## 残余风险

当前 review 未运行真实 provider overflow smoke；仓库提供的是 fake overflow smoke。真实 provider 的错误 payload 与多轮工具后
overflow 行为仍建议在 P5 前补手工验证。

## 复审结论

复审通过，无 findings。

- P1 已真实修复：compact 前会读取同一 Run 当前 EventLog，并通过 `snapshot_with_transient_tool_facts()` 复用 memory projection 的工具事实 / evidence anchor 投影逻辑，第二次 compacted attempt 保留 `tool_call_id`、`source_event_cursor`、`cursor_fingerprint`、`has_more` 等事实；对应测试为 `tests/host/test_phase4_overflow_retry.py::test_same_run_tool_facts_enter_compacted_attempt`。
- P2 已真实修复：trace 缓存缺失会落 `context_compact_failed` 与 Host-owned `RUN_FAILED`；compact 分支其它异常由 `_append_compact_exception_failure()` 收口为 Host failed terminal，订阅流能看到终态并结束；对应测试为 `tests/host/test_phase4_overflow_retry.py::test_missing_trace_cache_compact_failure_gets_host_terminal`。
- EventLog 仍满足 append-before-stream；同一 run 终态由 `InMemoryRunEventStore` guard 保证唯一且最后，terminal 后 append 会被拒绝；订阅在 replay / follow 路径均以 cursor predicate 与 terminal cursor 结束条件避免 lost wakeup 或终态后等待。
- trace 缓存缺失与 compact 异常路径均由 Host failed terminal 收口，未发现引入新的 Host P4 回归。

复审验证：

- `source .venv/bin/activate && pytest tests/host`：通过，117 passed。
- `source .venv/bin/activate && pyright`：通过，0 errors。
