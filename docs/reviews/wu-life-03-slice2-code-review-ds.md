# Code Review — WU-LIFE-03 Slice 2 (AgentDS)

## Scope

- Mode: current changes
- Branch: `phase/host-engine-next`
- Base: `main` (Slice 1 commit `ef2d3644` is the accepted base; only uncommitted changes are reviewed)
- Output file: `docs/reviews/wu-life-03-slice2-code-review-ds.md`
- Included scope:
  - `dayu/host/api.py` — `OpenHostOptions.active_cancel_timeout_seconds`, `HostLocalExecutionOptions.active_cancel_timeout_seconds`, validation
  - `dayu/host/command.py` — `ActiveCancelWatchdogWakeupPort` Protocol, `HostCommandHandle` wiring, `_propagate_active_cancel_targets` / `_wake_active_cancel_watchdog`
  - `dayu/host/dispatch.py` — `HostDispatchScheduler` watchdog tick / loop / wakeup / close integration, candidate read helpers, event constants
  - `dayu/host/open_host.py` — `_OpenHostContextManager.__aenter__` startup ordering (tick → recovery scan), `_local_execution_options_from_open_host_options` wiring
  - `dayu/host/recovery.py` — `StartupRecoveryScanner` defer-to-watchdog policy, `_has_accepted_cancel_fact`, `StartupRecoveryDecision.DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG`
  - `dayu/host/README.md` — option list / cancel / dispatch / recovery section updates
  - `docs/host/design.md` — watchdog terminal policy / startup recovery ordering description updates
  - `docs/host/issues-implementation-control.md` — gate status update
  - `tests/host/test_active_cancel_dispatch.py` — 7 new watchdog tests + `_wait_for_attempt_status` helper + `_open_scheduler` parameterization
  - `tests/host/test_open_host_runtime.py` — 3 new reopen/public-watch tests + `_force_cancel_requested_at` / `_event_type_count` / `_cancel_request` helpers
  - `tests/host/test_recovery_scan.py` — 2 new recovery defer tests + `_append_accepted_cancel_facts` helper
- Excluded scope: Slice 1 committed files (`dayu/host/durable/run_transition.py`, `dayu/host/engine_ingest.py`, `tests/host/test_run_attempt_transitions.py`, `tests/host/test_engine_ingest_mapping.py`) — these are reviewed as the foundation but not re-reviewed in detail.
- Parallel review coverage: 无（单独 agent 全量走读）。

## Findings

### F01-未修复-中-`_has_accepted_cancel_fact` 未防御 malformed `RUN_CANCELLING` payload 导致的 `HostDurableError`，与 `_read_linked_cancel_requested_event` 不一致

- **入口/函数**: `StartupRecoveryScanner._classify_run` → `_has_accepted_cancel_fact`
- **文件(行号)**: `dayu/host/recovery.py:674-679`
- **输入场景**: durable store 中存在 `RUN_CANCELLING` event 但其 payload 无法被 `event_payload_object` 正常解析（例如 payload 列损坏、JSON 格式非法、或 payload_ref 指向不存在的 artifact）。
- **实际分支**: `_has_accepted_cancel_fact` 在 line 674-679 调用 `event_payload_object(transaction, cancelling, payload_label=_EVENT_TYPE_RUN_CANCELLING)` **未包裹 try/except**。若 payload 解析失败，`HostDurableError` 直接向上传播到 `_classify_run`（line 291-308），再传播到 `scan()` 内的 `operation` 闭包（line 196-222），导致整个 write transaction 失败回滚，**所有非终态 Run 的 startup 分类均被中断**。
- **预期行为**: malformed payload 应被安全跳过：`_has_accepted_cancel_fact` 返回 `False`，该 `CANCELLING` Run 回退到 `_classify_active_or_cancelling` 正常 recovery 分类路径。
- **实际行为**: `HostDurableError` 未被捕获，整个 `scan()` 抛出异常，Host opener 启动失败。
- **直接证据**:
  - `dayu/host/recovery.py:674-679` — `event_payload_object(...)` 调用无 try/except。
  - `dayu/host/dispatch.py:4141-4148` — 同一 payload 解析模式在 `_read_linked_cancel_requested_event` 中**正确包裹**了 `try: ... except HostDurableError: return None`。
- **影响**: 单个 malformed `RUN_CANCELLING` payload 可阻止 Host 启动（所有非终态 Run 分类中断）。虽然正常写入路径不会产生 malformed payload，但防御性编程要求 startup recovery 不能因单条 corrupt data 而整体崩溃。
- **建议改法和验证点**:
  ```python
  # dayu/host/recovery.py:674-679
  try:
      payload = event_payload_object(
          transaction,
          cancelling,
          payload_label=_EVENT_TYPE_RUN_CANCELLING,
      )
  except HostDurableError:
      return False
  ```
  验证点：新增 recovery scan 测试，seed 一个 payload 列非法的 `RUN_CANCELLING` event，断言 scan 不崩溃且该 Run 进入正常 `_classify_active_or_cancelling` 分支而非 `DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG`。
- **修复风险（低）**: 仅增加防御性 try/except，不改变正常路径行为。
- **严重程度（中）**: 虽需 corrupt data 触发，但影响面是整个 Host 启动失败，且同一模式在 `dispatch.py` 中已有正确防御写法。

### F02-未修复-低-`ActiveCancelWatchdogWakeupPort` Protocol 定义在 `command.py` 中，但其实现 `HostDispatchScheduler` 在 `dispatch.py` 中，形成 command → dispatch 的隐式类型依赖

- **入口/函数**: `HostCommandHandle.__init__` → `ActiveCancelWatchdogWakeupPort` Protocol
- **文件(行号)**: `dayu/host/command.py:161-172`（Protocol 定义）, `dayu/host/dispatch.py:1054`（实现）
- **输入场景**: 任何低层组装 `HostCommandHandle` 的场景。如果调用方传入非 `HostDispatchScheduler` 的 `wakeup_port` 实现，Protocol 定义只要求 `wake_active_cancel_watchdog() -> None` 方法签名，但无法约束实现语义（例如实现可能不检查 `_closed`、不防御 queue full、忽略 `active_cancel_timeout_seconds is None` 时的语义差异）。
- **实际分支**: `command.py` 中的 Protocol 是一个纯 structural interface，而 `_wake_active_cancel_watchdog` 在 `command.py:1644-1652` 使用该 port 时只捕获 `RuntimeError`。如果 Protocol 的替代实现有不同异常签名或不同 close 语义，`command.py` 中的调用方无法通过类型系统发现差异。
- **预期行为**: Protocol 语义应包含至少对 close 状态和 disable 状态的行为约束，或 port 定义应迁移到更中立的公共契约层。
- **实际行为**: 当前只有 `HostDispatchScheduler` 实现了该 Protocol，且只在一处组装（`open_host.py:914`）。短期内不会出错，但 Protocol 定义位置暗示 command 层定义了 dispatch 层的依赖契约，而非公共契约层定义。
- **直接证据**: `dayu/host/command.py:161-172` — Protocol 定义在 command 模块。`dayu/host/dispatch.py:1054-1067` — 唯一的实现。
- **影响**: 仅影响未来替代实现的正确性，当前无实际 bug。
- **建议改法和验证点**: 将 `ActiveCancelWatchdogWakeupPort` 移至 `dayu/host/api.py` 或独立的公共契约模块，与 `AdmissionWakeupPort` 等同级 port 放在一起。当前可不修，但应在 WU-LIFE-03 后续或 #87 重构时处理。
- **修复风险（低）**: 纯移动，无行为变化。
- **严重程度（低）**: 无当前 bug，仅架构 debt。不阻塞 merge。

### F03-未修复-低-`tick_active_cancel_watchdog` 内重复了 `_read_active_cancel_watchdog_candidates` 中的部分前置校验，watchdog 候选筛选与 `_invalid_active_cancel_timeout_closeout_precondition` 存在三重 overlapping check

- **入口/函数**: `HostDispatchScheduler.tick_active_cancel_watchdog` → `_read_active_cancel_watchdog_candidates` → `active_cancel_timeout_closeout_in_transaction` → `_invalid_active_cancel_timeout_closeout_precondition`
- **文件(行号)**:
  - `dayu/host/dispatch.py:4062-4098` — candidate 筛选（check 1: attempt RUNNING, dispatch accepted, cancel fact exists）
  - `dayu/host/dispatch.py:440-500` — tick 内调用 closeout
  - `dayu/host/durable/run_transition.py:5063-5120` — closeout 内部 precondition（check 2: 更全面的 CAS 前置）
- **输入场景**: 任何 candidate 通过 check 1 但 check 2 失败的场景（例如 tick 事务内另一个并发事务修改了 Run/Attempt 状态）。
- **实际分支**: check 1（dispatch.py 中的 `_read_active_cancel_watchdog_candidates`）在**写事务开始前**的可变快照中筛选 candidate；进入写事务后 `active_cancel_timeout_closeout_in_transaction` 再做一次更严格的 CAS precondition check。如果 check 1 通过但 check 2 失败，candidate 被计入 `ignored`（dispatch.py:482-483）。
- **预期行为**: 两阶段筛选是正确且必要的（check 1 减少无效 closeout 调用，check 2 是 CAS 最终防线）。但 check 1 和 check 2 的筛选条件存在大量重叠（`attempt.status is RUNNING`、`dispatch_record.worker_accept_event_id is not None`、`dispatch_record.cancelled_event_id is None` 等），修改一边时另一边容易忘记同步。
- **实际行为**: 当前两处筛选一致，无行为错误。但存在 maintenance risk。
- **直接证据**: 对比 `dayu/host/dispatch.py:4076-4098` 与 `dayu/host/durable/run_transition.py:5100-5113`。
- **影响**: 无当前 bug，但后续若修改 dispatch/attempt/cancel precondition 规则，两处需同步修改。
- **建议改法和验证点**: 在 `_invalid_active_cancel_timeout_closeout_precondition` 的 docstring 中增加注释，标明 candidate 筛选函数 `_active_cancel_watchdog_candidate_from_run` 中存在重叠的前置检查，提醒修改者同步。当前不强制要求代码合并。
- **修复风险（低）**: 仅文档改善。
- **严重程度（低）**: 无当前 bug。不阻塞 merge。

## Open Questions

- **OQ1**: `read_non_terminal_runs` 返回所有非终态 Run（含 ACCEPTED / QUEUED / WAITING / RECOVERING / RUNNING / CANCELLING），而 watchdog 仅关心 `CANCELLING`。当前通过 Python 层 for-loop 过滤，在非终态 Run 数量很大的场景下存在不必要的 row materialization 开销。需要在 #87 性能调优时评估是否添加仅返回 `CANCELLING` 的专用 query？（当前讨论优先级：不阻塞 merge，非终态 Run 数量受 lane capacity 约束通常很小。）

## Residual Risk

- **RR1**: Provider/tool 物理 kill 不在本 Slice scope 内，timeout closeout 只声明 Host durable truth，不保证 side effect 停止。Owner: WU-TOOLS-CANCEL-01。
- **RR2**: Timeout 默认值 300s 可能需要在不同 provider/backend 下单独调优。Owner: #87 Host lifecycle watchdog runtime tuning。
- **RR3**: Reopen 后 timeout 判定基于 durable UTC timestamp vs 当前 Host UTC clock；跨实例时钟偏移可能使检测偏早或偏晚。Owner: #87。
- **RR4**: `active_cancel_timeout_seconds=None` 是显式 opt-out，此时 recovery orphan policy 仍可将 `CANCELLING` 标记为 `LOST`。Owner: #87 Host runtime assembly policy。
- **RR5**: 以下边缘场景无独立测试覆盖（但在现有测试中通过空扫描 / multiple runs 测试隐式覆盖）：
  - `CANCELLING` Run 的 `current_attempt_id` 为 None（状态机正常不应出现）
  - Attempt 存在但状态非 `RUNNING`（如 `STARTING`）
  - Dispatch record 存在但 `worker_accept_event_id` 为 None
  - `CANCEL_REQUESTED` event 存在但 `run_id` 与 Run 不一致
  以上场景在候选筛选函数中均返回 `None`（被忽略），无静默错误风险。建议在 #87 中按需补充 focused edge case test。

## Conclusion

**PASS** — 无 BLOCKING FINDINGS。

F01（中）是唯一的实质性问题：`_has_accepted_cancel_fact` 缺少 malformed payload 防御，可能导致单个 corrupt `RUN_CANCELLING` payload 阻止 Host 启动。修复简单（加 try/except），风险低。F02、F03 为低严重度架构/维护性建议，不阻塞 merge。

核心正确性验证通过：
- Watchdog tick / cancel wakeup / periodic scan / promotion / projection catch-up 满足 plan。
- Startup ordering: `open_host` 先执行 watchdog startup tick，再 `StartupRecoveryScanner.scan()`；accepted-cancel `CANCELLING` 正确 defer。
- Late terminal first-committer-wins: Slice 1 的 `_late_rejection_reason` + `active_cancel_timeout_closeout_in_transaction` CAS 正确防护 `final_answer` / `run_failed` / `run_suspended` / `tool_awaiting` after `CANCELLING`。
- Scheduler close 不写 timeout terminal；cancel replay/session cancel replay 不重复追加 facts。
- 架构不违反 UI → Service → Host → Engine 分层、`dayu.runtime` 边界；未引入第二套 watchdog runtime。
- 测试覆盖新增行为：172 passed / pyright 0 errors。
- README/design 更新在职责范围内，未把未来能力写成已实现。
