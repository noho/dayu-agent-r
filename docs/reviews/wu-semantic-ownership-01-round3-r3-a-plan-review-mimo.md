# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A Plan Review (MiMo)

## Review Target

- **文件**: `docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md`
- **范围**: Host lifecycle, wait, admin, durable integrity, scheduler health — 5 implementation slices
- **风险级别**: production-high
- **审查姿态**: adversarial, evidence-backed

## Assumptions Tested

| Assumption | Verdict | Evidence |
|---|---|---|
| DR-006 runner-call hot payload unbounded | **CONFIRMED** | `run_input.py`/`engine_ingest.py` 的 `_projector_metadata_summary` 每条消息产生一个 5 字段 entry，`len == message_count`，payload 线性增长。stress 测试 11/12 复现。 |
| DR-007 session list/purge starts full Host | **CONFIRMED** | `session.py::_run_session_command_async()` 调用 `_prepare_session_runtime()` + `open_host()`，启动 scheduler/watchdog/recovery/poller。 |
| DR-008 wait deadline leaves WAITING forever | **CONFIRMED** | `wait_adapter.py:_release_expired_or_invalid_boundary` 只 release/backoff，`waiting.py:_resolve_in_transaction` EXPIRED 分支只写 diagnostic。Run 永远 WAITING。 |
| DR-009 scheduler fatal not propagated | **CONFIRMED** | `dispatch.py:_drain_loop` 设置 `self._closed=True`，但 `open_host.py:_PublicHostHandle._closed` 不变。public admission 继续接受 work，`wake_dispatch` 抛 `RuntimeError`。 |
| DR-011 async Host blocks event loop | **CONFIRMED** | 所有 `_PublicHostHandle` async 方法直接调用同步 SQLite。`HostTransactionRunner` 用 `time.sleep()` busy retry。 |
| DR-012 sync wait adapter hangs close | **CONFIRMED** | `WaitPollerSupervisor.close()` 允许 `close_drain_timeout_seconds=None` 无界 join；有 timeout 时第一次超时后仍第二次无界 join。 |
| DR-017 lifecycle commits before side effect | **MISDIAGNOSED** | 见 Finding F1。 |
| DR-025 compactor timeout contaminates parent | **CONFIRMED** | `_signal_timeout_cancellation` 直接写 parent Run 的 `_HostCancellationToken`，无 child token。 |
| DR-029 LaneController.close commits after partial failure | **MISDIAGNOSED** | 见 Finding F2。 |

## Findings

### F1-未修复-高-DR-017/DR-029 诊断与代码行为不一致，S5 修复方案引入不必要的复杂度并改变并发安全语义

- **位置**: Slice S5 "Runtime lifecycle completion"，§已冻结的实现契约 第 5 节
- **问题类型**: 动机不成立 / 非最优方案
- **当前写法**:
  - DR-017 描述: "`InterruptibleProcessHandle.start()` 在 `Process.start()` 前写 `_started=True`；`close()` 在 kill/join/process/queue cleanup 前写 `_closed=True`。异常或 caller cancellation 会让第二次调用永久短路。"
  - DR-029 描述: "`LaneController.close()` 即使 token release 失败，仍在抛首错前写 `_close_completed=True`；第二次 close 直接返回。"
  - S5 修复: 引入 5 状态机 `NEW/STARTING/RUNNING/CLOSING/CLOSED`、async lock、shielded cleanup task、部分步骤跟踪与重试。
- **反例/失败场景**:
  - **DR-017 实际代码行为**: `_started=True` 在 `Process.start()` 前设置是有意设计——如果 start 失败，close() 仍能清理可能部分初始化的 process 对象。`_closed=True` 在 cleanup 前设置是有意的并发保护——防止两个并发 close() 调用同时 kill/join 同一 process。当前设计是正确的。
  - **DR-029 实际代码行为**: `_close_completed=True` 在所有 token release 之后设置（lane.py:591），不是之前。release 循环捕获每个 `RuntimeLaneError`，继续释放剩余 token，最后才设置 `_close_completed`。当前设计是正确的。
  - **S5 修复引入的真实问题**: 如果移除 `_closed=True` 的前置设置，改为"只有全部 cleanup 成功才 commit CLOSED"，则第一次 close() 如果在 kill() 步骤失败，`_closed` 不会被设置，第二次 close() 会重新进入并尝试对已经 kill 过的 process 再次 kill/join——这不是幂等的。
  - **实际存在的真实问题**: 当前代码确实有一个问题，但不是计划描述的那个。如果 close() 在 kill() 之后、queue.close() 之前抛异常，`_closed=True` 已设置，第二次 close() 直接返回，queue feeder thread 永远泄漏（CPython multiprocessing.Queue 的 daemon=False feeder thread 会阻止进程退出）。这是一个资源泄漏，不是"state commit ordering"问题。
- **为什么有问题**: 计划对 DR-017 和 DR-029 的诊断与代码直接证据不符。计划描述的"state commits before side effect completion"在当前代码中不存在——`_close_completed` 在 DR-029 中正确地在所有 release 之后设置，`_closed` 在 DR-017 中是有意的并发保护。计划的 S5 修复方案（5 状态机 + async lock + shielded task + 部分步骤跟踪）是为了解决一个不存在的问题而引入的过度设计，同时会移除现有的并发安全保护。
- **直接证据**:
  - `dayu/runtime/interruptible_process.py:284`: `self._started = True` 在 `self._process.start()` 之前——有意设计
  - `dayu/runtime/interruptible_process.py:388`: `self._closed = True` 在 cleanup 之前——并发保护
  - `dayu/runtime/lane.py:574-591`: `_closed=True` 在 line 574（gating），`_close_completed=True` 在 line 591（所有 release 和 heartbeat cancel 之后）
  - `dayu/runtime/lane.py:581-585`: release 失败被捕获、记录，循环继续——所有 token 都被尝试释放
- **影响**: 实施 Agent 会按计划实现一个过度复杂的状态机，移除现有的并发保护，并引入新的部分 cleanup 跟踪逻辑——这些都是为了解决一个不存在的"state commit ordering"问题。真实的问题（queue feeder thread 泄漏、non-RuntimeLaneError 异常导致 `_close_completed` 不被设置）不会被这个修复方案正确解决。
- **建议改法和验证点**:
  1. **DR-017 真实修复**: 保持 `_closed=True` 前置设置（并发保护）。在 close() 中用 try/finally 包裹 cleanup 步骤，确保 queue feeder thread 始终被清理。不需要 5 状态机。
  2. **DR-029 真实修复**: 保持 `_close_completed=True` 在所有 release 之后设置。在 release 循环外加 try/except 捕获非 `RuntimeLaneError` 异常（如 `asyncio.CancelledError`），确保 `_close_completed` 始终被设置。
  3. **验证**: 测试 close() 在 kill() 失败后 queue 仍被清理；测试 CancelledError 在 release 循环中传播后第二次 close() 仍能返回。
- **修复风险（低/中/高）**: 高——需要重新设计 S5 的修复方案
- **严重程度（高）**: S5 的两个 finding (DR-017, DR-029) 都基于错误诊断，整个 slice 需要重新评估

### F2-未修复-高-S2 范围过宽：admin opener + durable actor + health gate + recovery + watchdog + cancel race 应拆分

- **位置**: Slice S2 "Host Admin / Async Durable Boundary / Admission 与 Scheduler Health"
- **问题类型**: 切片过粗 / 过度耦合
- **当前写法**: S2 包含：(1) admin opener, (2) `_HostDurableActor` 新线程模型, (3) `HostExecutionHealthGate` 新状态机, (4) recovery 水印分页, (5) watchdog level-trigger, (6) cancel deferred race, (7) retry exhaustion backoff, (8) admission lease。计划承认"S2 内的 admin opener、durable actor、health gate、recovery 与 cancel race 保持同一 slice，是因为它们共同修改 `api.py/open_host.py/command.py/dispatch.py`，并且 admission lease 必须原子覆盖 actor commit 与 scheduler wake；拆开会制造一个会接受但不会可靠 dispatch 的中间 contract"。
- **反例/失败场景**:
  - S2 的 allowed production files 有 13 个文件（含 2 个新增），allowed tests 有 24 个文件（含 4 个新增）。这是一个巨大的变更集。
  - `_HostDurableActor` 引入全新的线程模型——专用线程 + 独立 SQLite connection + 消息队列 + request-response protocol。当前 `dayu/host/` 没有任何 actor 或 thread pool 模式。这是一个架构级变更，不是 bug fix。
  - `HostExecutionHealthGate` 引入新的状态机 `STARTING -> READY -> UNAVAILABLE -> CLOSING -> CLOSED`，影响所有 public admission 方法。这是一个新的公共契约。
  - 如果 durable actor 的线程安全有问题（例如 cross-thread asyncio 操作、connection 竞争），它会同时影响 admin opener、health gate、recovery 和所有 public API——整个 S2 失败，无法隔离问题来源。
  - **phaseflow-umbrella-optimization-control.md 的约束**: "生产 state machine / durable change：按真实 owner boundary 拆 2-4 个 slices"。S2 包含至少 3 个独立的 owner boundary 变更（admin opener contract、durable actor threading、health gate state machine），应该拆分。
- **为什么有问题**: S2 把"公共接口变更"（admin opener）、"并发模型变更"（durable actor）、"状态机变更"（health gate）和"事务/恢复变更"（recovery batching、cancel race）捆绑在一起。这些变更的失败模式不同、验证矩阵不同、review 专长不同。一个 actor 线程安全问题会淹没 health gate 的正确性验证。一个 health gate 状态机错误会掩盖 admin opener 的边界测试。
- **直接证据**:
  - `docs/phaseflow-umbrella-optimization-control.md:117`: "生产 state machine / durable change：按真实 owner boundary 拆 2-4 个 slices。超过 3 个 slices 时，plan 必须说明为什么不能合并。"
  - S2 allowed production files: 13 个文件（含 2 个新增模块）
  - S2 必须测试的反例: 12 个
  - S2 验证命令涉及 24 个测试文件
  - `_HostDurableActor` 是全新基础设施——`dayu/host/` 当前无 actor/thread pool 模式（grep 确认）
- **影响**: 实施 Agent 面对一个巨大的 slice，难以隔离失败来源。reviewer 难以在一次 review 中覆盖所有变更。如果 actor 线程模型有问题，整个 S2 需要回滚，包括已经正确实现的 admin opener 和 health gate。
- **建议改法和验证点**:
  1. **S2a: Admin opener + public contract**: `OpenHostAdminOptions`、`HostAdmin`、`open_host_admin()`、`_HostDurableActor`（最小版本，只支持 admin 操作）、CLI session routing。验证: admin list/purge 在无 runner secret 时成功。
  2. **S2b: Health gate + scheduler recovery + concurrency**: `HostExecutionHealthGate`、admission lease、recovery batching、watchdog level-trigger、cancel race、retry exhaustion backoff。验证: fatal/admission race、recovery batching、watchdog level trigger。
  3. 拆分后每个 slice 的 allowed files 约 7-8 个，tests 约 12-15 个，可独立验证。
- **修复风险（低/中/高）**: 中——需要重新划分 S2，但不改变整体计划结构
- **严重程度（高）**: S2 是整个计划中最大、最复杂的 slice，拆分对可实施性和可审查性至关重要

### F3-未修复-中-S1 的 `projector_metadata_summary` 字段形状不一致需要显式统一契约

- **位置**: Slice S1 "Durable Integrity 与 Bounded Runner-call Provenance"，§已冻结的实现契约 第 1 节
- **问题类型**: 契约缺失
- **当前写法**: 计划说"三个 producer 只提供 typed atoms，不再各自实现 hot JSON builder"，但没有说明如何统一三个 producer 当前不一致的 `projector_metadata_summary` 字段形状。
- **反例/失败场景**:
  - `run_input.py` 和 `engine_ingest.py` 的 `_projector_metadata_summary` 提取 5 个字段：`projector_metadata_id`, `projector_id`, `projector_schema_version`, `projector_digest`, `purpose`
  - `compaction_operation.py` 的 `_projector_metadata_summary` 提取 4 个字段：`metadata_id`（不是 `projector_metadata_id`）, `projector_id`, `purpose`, `projector_digest`（顺序也不同）
  - `tool_trace.py` 的 consumer 期望 5 个字段，包括 `projector_metadata_id` 和 `projector_schema_version`
  - 如果共享 `RunnerCallHotAtoms` 只定义 4 个字段（compactor 的形状），tool_trace consumer 会失败。如果定义 5 个字段，compactor producer 需要补齐 `projector_schema_version`。
  - 计划没有明确说明共享契约使用哪个字段集，实施 Agent 需要自行决定——这违反了"no hidden redesign left to implementer"要求。
- **为什么有问题**: 三个 producer 的字段不一致是 DR-006 的一部分（三个各自复制 summary），但计划只说了"统一"，没有给出统一后的字段定义。实施 Agent 可能选择错误的字段集，导致 consumer 失败或丢失信息。
- **直接证据**:
  - `run_input.py:4431-4455`: 5 字段，key 为 `projector_metadata_id`
  - `compaction_operation.py:1351-1375`: 4 字段，key 为 `metadata_id`
  - `tool_trace.py:815-840`: consumer 期望 5 字段，key 为 `projector_metadata_id`
- **影响**: 实施 Agent 可能选择与 consumer 不兼容的字段形状，导致 tool_trace 查询失败或需要额外修复循环。
- **建议改法和验证点**:
  1. 在 S1 的"已冻结的实现契约"中显式定义 `RunnerCallHotAtoms` 的 `projector_metadata_summary` 字段集：使用 5 字段形状（`projector_metadata_id`, `projector_id`, `projector_schema_version`, `projector_digest`, `purpose`），与 `run_input.py`/`engine_ingest.py`/`tool_trace.py` 对齐。
  2. compactor producer 需要补齐 `projector_schema_version`（可从 compactor manifest 的 schema version 获取）。
  3. 验证: tool_trace 查询在统一后仍能正确解析 projector metadata。
- **修复风险（低/中/高）**: 低——只需在计划中明确字段定义
- **严重程度（中）**: 不会阻止实施，但会导致实施中返工

### F4-未修复-中-S2 的 `_HostDurableActor` 引入全新并发模型，需要更详细的线程安全规范

- **位置**: Slice S2，§已冻结的实现契约 第 2 节，第 3-4 条
- **问题类型**: 不可直接实施 / 契约缺失
- **当前写法**:
  - "新建私有 `_HostDurableActor`：单个 `ThreadPoolExecutor(max_workers=1)` 创建、使用、关闭其私有 `HostCommandHandle`；`invoke()` 接收严格 typed callable，按提交顺序串行。"
  - "actor thread 的 scheduler wakeup 使用现有 thread-safe loop bridge；active worker cancel 也新增 thread-safe bridge，确保 `LocalWorkerHandle.on_cancel()` 只在 opener event loop 执行。"
  - "scheduler runtime 继续持有自己在 opener event loop 创建的独立 store/connection，不与 command actor 共享 connection。"
- **反例/失败场景**:
  - 计划说 scheduler 和 actor 不共享 connection，但当前代码中 scheduler 和 command handle 共享同一个 `HostDurableStore` 和 `HostTransactionRunner`（`open_host.py:858-907`）。计划需要明确：scheduler 的 connection 从哪里来？是新建一个独立的 `HostDurableStore` 吗？
  - 如果 scheduler 和 actor 各自有独立的 SQLite connection，它们可以并发写同一个 SQLite 文件。SQLite 的 WAL 模式允许并发读写，但 `BEGIN IMMEDIATE` 仍然会竞争写锁。如果 actor 持有写锁，scheduler 的 `drain_once` 会阻塞在 busy timeout——这正是 DR-011 要解决的问题的另一面。
  - 计划说"public handle 使用 module-level callable 或 `functools.partial`，不创建无类型 lambda/god command bag"，但没有定义 actor 的 callable 类型签名。实施 Agent 需要自行设计 `invoke()` 的类型协议。
  - `_ThreadsafeSchedulerWakeupPort` 使用 `call_soon_threadsafe` + `concurrent.futures.Future` 模式，但 `Future.result()` 会阻塞调用线程。如果 actor thread 调用 `wake_dispatch` 并阻塞在 `Future.result()`，actor 的串行处理会被阻塞——这可能不是预期行为。
- **为什么有问题**: `_HostDurableActor` 是一个全新的并发模型，当前 `dayu/host/` 没有任何类似模式。计划的描述不够详细，无法让实施 Agent 直接实现。特别是：(1) scheduler 的新 connection 来源，(2) actor callable 的类型签名，(3) actor thread 与 event loop 的交互协议，(4) actor close 时的 connection 关闭顺序。
- **直接证据**:
  - 当前 `open_host.py:858-907`: scheduler 和 command handle 共享同一个 `HostDurableStore`
  - 当前 `open_host.py:262-310`: `_ThreadsafeSchedulerWakeupPort` 使用 `call_soon_threadsafe` + `Future` 模式
  - 当前 `dayu/host/` 无 actor/thread pool 模式（grep 确认）
- **影响**: 实施 Agent 需要自行设计 actor 的类型协议、线程安全交互和 connection 管理——这些是架构决策，不应留给实施阶段。
- **建议改法和验证点**:
  1. 在 S2 的"已冻结的实现契约"中补充：(a) actor callable 的类型签名（例如 `Callable[[HostCommandHandle], T]` 或更具体的 Protocol），(b) scheduler 新 connection 的来源（新建 `HostDurableStore` 还是复用），(c) actor thread 与 event loop 的交互协议（`call_soon_threadsafe` 还是 `asyncio.Queue`），(d) actor close 的 connection 关闭顺序。
  2. 验证: actor 在外部 connection 持锁时 event loop ticker 仍前进（计划已有此测试），但需要明确 actor 的 busy timeout 与 scheduler 的 busy timeout 是否独立。
- **修复风险（低/中/高）**: 中——需要补充规范，不改变整体方向
- **严重程度（中）**: 会增加实施中的设计决策负担

### F5-未修复-低-S3 的 `_expire_wait_in_transaction` 与 `fail_run_from_waiting_in_transaction` 的关系需要明确

- **位置**: Slice S3，§已冻结的实现契约 第 3 节，第 1-2 条
- **问题类型**: 契约缺失
- **当前写法**:
  - "新增 Host-internal `ExpireWaitInput` 与 common `_expire_wait_in_transaction()`。deadline expiry 产生确定性 failed tool outcome：`error/reason_code = wait_deadline_expired`..."
  - "expiry 与 `TOOL_RESULT_ACCEPTED` failure fact、`RUN_FAILED`、Wait `FAILED`、Attempt terminal、session active-slot release 在一个 write transaction 完成，复用 `fail_run_from_waiting_in_transaction()`；不新增含义重复的 durable 状态。"
- **反例/失败场景**:
  - 计说"复用 `fail_run_from_waiting_in_transaction()`"，但 `fail_run_from_waiting_in_transaction` 期望一个 `ResolveWaitFailedOutcome` 作为输入。`_expire_wait_in_transaction` 需要构造一个等价的 outcome——计划没有说明这个 outcome 的具体字段。
  - `fail_run_from_waiting_in_transaction` 会写 `TOOL_RESULT_ACCEPTED` failure fact、`RUN_FAILED`、Wait `FAILED`、Attempt terminal、session active-slot release。这些操作的顺序和事务边界需要与现有的 `resolve_wait` 路径一致。计划说"在一个 write transaction 完成"，但没有说明是否复用 `resolve_wait` 的事务逻辑还是新建事务。
  - poller 路径和 direct/callback 路径都需要调用 `_expire_wait_in_transaction`，但它们的事务上下文不同（poller 在自己的 command handle 事务中，direct/callback 在 public API 事务中）。计划需要说明 `_expire_wait_in_transaction` 是否接受外部事务还是创建自己的事务。
- **为什么有问题**: `_expire_wait_in_transaction` 是 S3 的核心新函数，但其与现有 `fail_run_from_waiting_in_transaction` 的关系不够明确。实施 Agent 需要自行决定 outcome 构造和事务边界。
- **直接证据**:
  - `dayu/host/durable/run_transition.py:1861`: `fail_run_from_waiting_in_transaction` 存在并接受 `ResolveWaitFailedOutcome`
  - `dayu/host/waiting.py:703`: `_resolve_in_transaction` 在 EXPIRED 分支只调用 `_reject_late_result`，不调用 `fail_run_from_waiting_in_transaction`
- **影响**: 小——实施 Agent 大概率能正确推导，但增加设计决策负担。
- **建议改法和验证点**: 在 S3 契约中补充 `_expire_wait_in_transaction` 的输入类型（构造 `ResolveWaitFailedOutcome(error_reason_code="wait_deadline_expired", ...)`）和事务边界（接受外部事务参数还是创建新事务）。
- **修复风险（低/中/高）**: 低
- **严重程度（低）**: 实施 Agent 大概率能自行推导

### F6-未修复-低-DR-017 的真实问题（queue feeder thread 泄漏）不会被 S5 的修复方案解决

- **位置**: Slice S5，DR-017
- **问题类型**: 非最优方案
- **当前写法**: S5 引入 5 状态机 + async lock + shielded cleanup task 来解决"state commits before side effect completion"。
- **反例/失败场景**:
  - DR-017 的真实问题是：如果 `close()` 在 `kill()` 之后、`queue.close()` 之前抛异常，`_closed=True` 已设置，第二次 `close()` 直接返回，queue feeder thread 永远泄漏。
  - S5 的修复方案引入状态机和 async lock，但核心问题（cleanup 步骤部分失败时资源泄漏）需要的是 try/finally 保护，不是状态机。
  - 当前代码的 `close()` 没有任何 try/except/finally——任何异常都会导致后续 cleanup 步骤被跳过。
- **为什么有问题**: S5 的修复方案过度设计（5 状态机 + async lock + shielded task），但没有直接解决真实问题（cleanup 步骤的部分失败保护）。简单的 try/finally 就能解决 queue feeder thread 泄漏。
- **直接证据**:
  - `dayu/runtime/interruptible_process.py:369-395`: close() 没有 try/except/finally
  - `dayu/runtime/interruptible_process.py:394`: `self._result_queue.close()` 在 kill()/join() 之后，如果前面抛异常则永远不执行
- **影响**: S5 的实施会引入不必要的复杂度，同时可能没有解决真实的资源泄漏问题。
- **建议改法和验证点**: 用 try/finally 包裹 close() 的 cleanup 步骤，确保 queue.close() 和 queue.join_thread() 始终执行。不需要 5 状态机。
- **修复风险（低/中/高）**: 低
- **严重程度（低）**: 真实问题存在但触发条件罕见（kill() 失败）

## Open Questions

1. **S2 拆分后 admission lease 的原子性**: 计划说 admission lease 必须"原子覆盖 actor commit 与 scheduler wake"。如果拆分 S2，admin opener (S2a) 和 health gate (S2b) 的 admission lease 如何保证原子性？需要在拆分方案中明确。
2. **S1 对现有数据的影响**: 计划说"不存在旧数据 compatibility branch"。如果部署时 EventLog 中已有不符合新 descriptor schema 的数据，这些数据会 fail closed。这是否需要部署前的数据审计工具？
3. **S2 scheduler 新 connection 的 WAL 模式**: 如果 scheduler 和 actor 各自有独立的 SQLite connection，它们是否都使用 WAL 模式？WAL 模式下并发写是否会产生 `SQLITE_BUSY`？busy timeout 策略是什么？

## Residual Risks

| 风险 | Owner | 目的地 |
|---|---|---|
| `dayu/fins/ingestion/wait_adapter.py` 的 Host 反向依赖在本轮后仍存在 | R3-D | controller 已明确的 R3-D/R3-A boundary split |
| bounded sync adapter timeout 后 provider daemon thread 可能仍运行 | R3-D | provider 协作式 cancel 由 R3-D half 继续消除 |
| fresh-schema 政策意味着既有 tampered descriptor 会 fail closed | 运维 | 部署前坏数据审计属于运维动作 |
| health gate fatal 后已 commit durable pending work 依赖下次 healthy opener/recovery | Host recovery | public error 必须明确 retryable |

## Plan Review Conclusion

**pass-with-risks**

计划整体架构方向正确，对 DR-006/007/008/009/010/011/012/025 的诊断和修复方案基于直接代码证据。5-slice 结构在 phaseflow 约束的上限，但每个 slice 的 owner boundary 和验证矩阵确实不同。

主要风险：
1. **S5 (DR-017/DR-029) 诊断错误**: 代码行为与计划描述不符，修复方案过度设计。需要重新评估 S5 的修复方案，保留并发保护，用 try/finally 解决真实的资源泄漏。
2. **S2 范围过宽**: 13 个 production files、24 个 test files、全新 actor 线程模型、新状态机——应拆分为 S2a (admin opener) 和 S2b (health gate + scheduler)。
3. **S1 字段形状不一致**: `projector_metadata_summary` 的 3 个 producer 使用不同的字段名和数量，需要在计划中显式定义共享契约。

修复上述 3 个问题后，计划可以进入 implementation gate。
