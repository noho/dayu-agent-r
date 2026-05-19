# DS Repo Review Accepted Findings 修复记录

## 任务范围

- 输入 artifact：`docs/reviews/repo-review-ds-20260519-154715.md`。
- 主控接受并要求修复：DS Finding 5、6、8、9、10、11、17、18、20、21、25。
- 主控明确不修 / 驳回 / deferred：DS Finding 1、2、3、4、7、12、13、14、15、16、19、22、23、24。
- 本次不修改 `AGENTS.md`、`CLAUDE.md`，不 stage、commit、push。
- 本记录只覆盖 DS accepted findings 的增量修复；工作区中既有 Host README 重写与上一轮 MiMo accepted findings 修复不归入本次 DS 修复范围。

## 事实核实与修复

- Finding 5：成立。`BatchToolExecutionContext.__post_init__` 只校验 timeout，未校验 `run_id`、`session_id`、`iteration_id`。已补非空 / 非空白校验，并更新契约测试。
- Finding 6：成立。`_cancel_task_and_wait` 使用 broad suppress 吞掉普通异常。已改为仅吞 `asyncio.CancelledError`，普通异常写 warning 诊断并收口，避免把 cleanup 编程错误静默丢弃。
- Finding 8：成立。`_await_task_after_outer_cancellation` 在外层重复 cancel 且 shielded task 未完成时直接 continue。已增加短 sleep 退避，避免紧循环。
- Finding 9：成立。`_prepare_database_parent` 的 `mkdir` OSError 会穿透。已包装为 `RuntimeLaneConfigError` 并保留异常链。
- Finding 10：成立。`RunnerContentCompletedData.finish_reason` 会被 `RunnerDoneData.finish_reason` 静默覆盖。已在不一致时写 warning，保留后续 done finish_reason 作为原有行为。
- Finding 11：成立。SSE 无法归属的 tool call delta 会回退到 index 0。已改为丢弃该条 delta 并写 warning，避免污染 index 0。
- Finding 17：成立。同步 accept retry 捕获 `TimeoutError` 是死代码且误导。已从普通 fact accept 与 awaiting accept 两处移除，只保留 `HostTransactionRetryExhaustedError` 的有限重试治理。
- Finding 18：成立，但直接调用 `resolve_wait` 不能把 `CANCELLED` wait 转终态；当前 `resolve_wait` 对 CANCELLED 是 late reject。已在 `WaitPoller` 实例内记录已 abandon 的 cancelled wait，确保同一 poller 不会无限重复调用 `abandon_wait`。
- Finding 20：成立。compactor proposal exception 的 diagnostic suffix 只包含异常类名。已加入 `str(exc)`，保留异常消息。
- Finding 21：成立。quality checker 未校验 `dropped_ranges` / `summarized_ranges` 是否来自 request 可摘要范围。已新增 `COMPACT_RANGE_OUTSIDE_REQUEST` 拒绝原因，并要求 range 起止 ref 属于 `request.older_raw_turn_refs`。
- Finding 25：成立。`SSEParser._finalize_success` 只在 `_terminated` 且 `finish_reason is ERROR` 时 no-op。已改为 `_terminated` 即 no-op，避免未来路径双重 emit Done。

## 不修 / 驳回 / Deferred

- Finding 1：按主控裁决驳回。`_ensure_heartbeat_task` 内无 await，单 event loop 下 check+assignment 不会并发交错；本次未发现多线程共用同一 controller 的直接证据。
- Finding 2：按主控裁决驳回。主控已验证本机 Python 3.11 native coroutine 有 `close`。
- Finding 3：按主控裁决不修。Host `engine_ingest` 有 reactive recovery，后续旧 execution terminal 应 stale；本次未发现反证。
- Finding 4：按主控裁决不修。`budget_after_compact` 是 token estimate，低值不等于 overflow；本次未证明存在压缩循环条件。
- Finding 7：deferred。runtime lane 瞬态 SQLite 错误重试策略涉及错误分类语义。
- Finding 12：deferred。stream / non-stream usage ordering 统一属于事件顺序语义调整。
- Finding 13：deferred。aiohttp streaming total timeout 调整需确认其他超时机制覆盖。
- Finding 14：按 AGENTS schema 全新起库约束不做旧库迁移。
- Finding 15：按主控裁决先不修；本次未证明 write transaction 内 read-then-insert 仍会并发穿透。
- Finding 16：deferred。dispatch drain loop 持久错误分类 / 升级策略需单独设计。
- Finding 19：deferred。duplicate index 与持久化重建机制涉及恢复语义。
- Finding 22：已由上一轮 MiMo accepted findings 修复，本次不重复处理。
- Finding 23：deferred。多个 dataclass 空字符串校验属于更宽契约收紧。
- Finding 24：deferred。`RunResumeHint` 填充涉及 resume 语义设计。

## 本次 DS 增量改动文件

代码文件：

- `dayu/contracts/tool_call.py`
- `dayu/engine/agent.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/host/compaction.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/context_governance.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/wait_adapter.py`
- `dayu/runtime/cancellation.py`
- `dayu/runtime/lane.py`

测试文件：

- `tests/contracts/test_tool_call.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/runners/openai/test_sse_done.py`
- `tests/engine/runners/openai/test_sse_tool_call_stream.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_wait_adapter_polling.py`
- `tests/runtime/test_cancellation.py`
- `tests/runtime/test_lane.py`

记录文件：

- `docs/reviews/repo-review-ds-fix-codex-20260519.md`

## 验证命令与结果

- `source .venv/bin/activate && pytest tests/contracts/test_tool_call.py tests/runtime/test_cancellation.py tests/runtime/test_lane.py tests/engine/test_agent_phase2.py tests/engine/runners/openai/test_sse_tool_call_stream.py tests/engine/runners/openai/test_sse_done.py tests/host/test_wait_adapter_polling.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_toolruntime_executor.py -q`
  - 结果：通过，`151 passed in 1.06s`。
- `source .venv/bin/activate && pyright dayu/contracts dayu/runtime dayu/engine dayu/host tests/contracts/test_tool_call.py tests/runtime/test_cancellation.py tests/runtime/test_lane.py tests/engine/test_agent_phase2.py tests/engine/runners/openai/test_sse_tool_call_stream.py tests/engine/runners/openai/test_sse_done.py tests/host/test_wait_adapter_polling.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_toolruntime_executor.py`
  - 结果：通过，`0 errors, 0 warnings, 0 informations`。
- `rg -n "except \\(HostTransactionRetryExhaustedError, TimeoutError\\)|TimeoutError" dayu/host/tool_runtime.py`
  - 结果：无输出，命令退出码 1，表示目标残留不存在。
- `git diff --check`
  - 结果：通过，无输出。

## 剩余风险

- Finding 18 的修复是同一 `WaitPoller` 实例内去重；若进程重启或重新创建 poller，durable 中的 CANCELLED poll wait 仍可能再次触发 abandon。直接把 CANCELLED 交给 `resolve_wait` 当前只会 late reject，不会改变 wait 状态；durable 级一次性 abandon 需要单独设计标记或状态迁移。
- Finding 10 当前只新增 warning，不改变 `RunnerDoneData.finish_reason` 作为最终分类输入的既有行为；若要把 mismatch 视为协议错误，需要独立语义裁决。
- Finding 11 对无法归属的 delta 采取丢弃策略；aggregator 仍会在 finalize 时产出 protocol warning，但只有完全无法归属的片段会被跳过。
- Finding 21 新增 `COMPACT_RANGE_OUTSIDE_REQUEST` public quality issue 值；下游若对 enum 值做穷尽展示，需要同步识别该拒绝原因。
- 未运行全仓测试；本次已覆盖 accepted findings 触达的 contracts、runtime、engine、host 代码与相关测试，并运行 pyright 覆盖对应生产包。
