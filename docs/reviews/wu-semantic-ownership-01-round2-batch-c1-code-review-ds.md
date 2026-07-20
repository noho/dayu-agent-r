# Code Review — WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C1

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (workspace uncommitted changes)
- Review artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-code-review-ds.md`
- Included scope: `dayu/host/wait_boundary.py`, `dayu/host/waiting.py`, `dayu/host/wait_adapter.py`, `dayu/host/wait_callback.py`, `dayu/fins/ingestion/wait_adapter.py`, 以及对应测试文件的 Batch C1 diff
- Excluded scope: Batch C2 (dispatch/promotion/cancel predispatch/tool accept duplicate index/Engine retry), 与 Batch C1 无关的 workspace 文件
- Parallel review coverage: 无（由主 reviewer 独立完成全量 review）
- Reviewing agent: AgentDS

## Findings

### DS-C1-01-未修复-中-_release_expired_or_invalid_boundary 将 Host 边界拒绝错误归入 adapter_errors 计数器且持久化 RESOLVE_ERROR 语义不匹配

- **入口/函数**: `WaitPoller.poll_once()` → `_release_expired_or_invalid_boundary()` → `_release_with_backoff()`
- **文件(行号)**: `dayu/host/wait_adapter.py:914-920`, `dayu/host/wait_adapter.py:1174-1208`
- **输入场景**: wait record 的 `deadline_at` 或 `expires_at` 已过期或文本非法，poller 在执行 adapter observation 前检测到该边界。
- **实际分支**: `_release_expired_or_invalid_boundary` 调用 `classify_wait_time_boundary`，当 decision 非 ACTIVE 时调用 `_release_with_backoff(outcome=WaitPollLastOutcome.RESOLVE_ERROR, ...)`。返回非 None 后，`poll_once` 将返回值同时计入 `adapter_errors` 和 `claim_conflicts`。
- **预期行为**: 
  - 持久化 outcome 应表达"边界拒绝"语义而非"resolve 错误"，两者是不同失败阶段。当前 `WaitPollLastOutcome` 枚举没有 `BOUNDARY_EXPIRED` 或等价值，但至少不应复用 `RESOLVE_ERROR`——该值在 `poll_once:1004` 处用于真正的 resolve 阶段异常。
  - 计数器应区分"adapter 返回/抛出异常"与"Host 在调用 adapter 前主动拒绝"——操作者监控 `adapter_errors` 上升时无法判断是外部 provider 故障还是 Host 边界决策。
- **实际行为**: 
  - `poll_last_outcome` 被写为 `RESOLVE_ERROR`，`poll_last_error_code` 被正确写为 `"wait_expired"` 或 `"invalid_wait_time_boundary"`。下游如只读 error_code 可区分，但诊断面板和 durable record 的 outcome 字段语义漂移。
  - `adapter_errors` 计数器对每个过期/非法边界的 wait 递增 1，与真正的 adapter 异常混在一起。
- **直接证据**: 
  - `dayu/host/wait_adapter.py:1202-1207`：`outcome=WaitPollLastOutcome.RESOLVE_ERROR`
  - `dayu/host/wait_adapter.py:917-919`：`adapter_errors += 1` 和 `claim_conflicts += boundary_release`
  - 对比 `dayu/host/wait_adapter.py:1001-1007`：同一 `RESOLVE_ERROR` 值用于 resolve 阶段 `StateMutationStatus` 非 UPDATED/非 CAS_LOST 路径
  - `dayu/host/durable/state.py:196`：`WaitPollLastOutcome.RESOLVE_ERROR = "resolve_error"` 枚举语义明确指向 resolve 阶段
- **影响**: 诊断/可观测性层面——操作者无法从 `adapter_errors` 或 `poll_last_outcome` 区分 Host 边界拒绝与真实 adapter/resolve 故障。不影响 wait 状态正确性（wait 保持 WAITING + backoff，claim 正确释放）。
- **建议改法和验证点**:
  1. 在 `WaitPollLastOutcome` 新增 `BOUNDARY_EXPIRED` / `BOUNDARY_INVALID`（或合并为一个 `BOUNDARY_REJECTED`）枚举值，需同步更新 schema CHECK 约束。
  2. `poll_once` 中新增独立计数器（如 `boundary_rejected`）或在 `_release_expired_or_invalid_boundary` 调用处不递增 `adapter_errors`。
  3. 验证：更新 `test_expired_poll_wait_is_released_before_provider_observation` 和 `test_invalid_poll_deadline_fails_closed_without_business_lost` 的断言，校验新的 outcome/counter。
- **修复风险（低）**: 新增枚举值 + schema CHECK 变更影响持久化兼容性，需确认无历史数据用裸字符串读取该列。计数器拆分仅影响测试断言。
- **严重程度（中）**:

### DS-C1-02-未修复-低-自关闭检测依赖异常消息字符串匹配

- **入口/函数**: `WaitPollerSupervisor._run_loop()`
- **文件(行号)**: `dayu/host/wait_adapter.py:1524-1526`
- **输入场景**: supervisor 自己的线程调用 `close()`，触发 `RuntimeError(_WAIT_POLLER_SELF_CLOSE_ERROR)`，该异常在 `_run_loop` 的 try/except 中被捕获。
- **实际分支**: `isinstance(exc, RuntimeError) and str(exc) == _WAIT_POLLER_SELF_CLOSE_ERROR` 通过字符串值区分子自关闭和普通 transient 异常。
- **预期行为**: 应使用自定义异常类型（如 `class _WaitPollerSelfCloseError(RuntimeError): ...`）做类型分发，不依赖异常消息字符串。
- **实际行为**: 依赖模块级常量 `_WAIT_POLLER_SELF_CLOSE_ERROR` 在 raise 点和 catch 点保持同一字符串。当前两处使用同一常量，行为正确；但任何其他代码路径抛出相同消息的 `RuntimeError` 会被错误路由到 fatal 分支。
- **直接证据**: `dayu/host/wait_adapter.py:73` 定义常量，`:1453` raise，`:1524-1526` catch。
- **影响**: 低概率——当前代码中只有 `close()` 产生该消息。若未来重构引入其他同名 RuntimeError，supervisor 会错误将 transient 异常当作 fatal 自关闭，永久终止 poll loop。
- **建议改法和验证点**: 定义 `class _WaitPollerSelfCloseError(RuntimeError): ...`，在 `close()` 中 raise 该类型，在 `_run_loop` 中 `except _WaitPollerSelfCloseError`。验证 `test_close_from_supervisor_thread_marks_failed_diagnostics` 仍通过。
- **修复风险（低）**: 仅影响异常类型层次，不改变控制流。
- **严重程度（低）**:

### DS-C1-03-未修复-低-_diagnostics_with_round_error 将可恢复轮次异常计入 fatal_errors 字段

- **入口/函数**: `WaitPollerSupervisor._run_loop()` → `_diagnostics_with_round_error()`
- **文件(行号)**: `dayu/host/wait_adapter.py:1545-1548`, `dayu/host/wait_adapter.py:1880-1898`
- **输入场景**: `_poll_once()` 或 `_record_poll_result()` 或 `_sleep_until_next_poll()` 抛出非自关闭异常。
- **实际分支**: `_diagnostics_with_round_error` 将 `fatal_errors` 递增 1，但 supervisor 状态保持 `RUNNING` 并继续下一轮。
- **预期行为**: 可恢复轮次异常应使用独立计数器（如 `round_errors`），`fatal_errors` 仅用于 `_diagnostics_with_fatal_error` 中导致 loop 终止的异常。
- **实际行为**: `fatal_errors` 同时包含真正 fatal（自关闭）和可恢复轮次异常。操作者需结合 `status` 字段（RUNNING vs FAILED）才能区分。
- **直接证据**: `dayu/host/wait_adapter.py:1894`：`fatal_errors=diagnostics.fatal_errors + 1`；对比 `:1888`：`status=diagnostics.status`（保持 RUNNING）。
- **影响**: 仅影响可观测性——诊断面板上 `fatal_errors > 0` 且 `status == RUNNING` 时需额外解释。Batch C1 实现文档已将此列为 residual risk。
- **建议改法和验证点**: 在 `WaitPollerDiagnosticsSnapshot` 新增 `round_errors: int` 字段，`_diagnostics_with_round_error` 递增该字段而非 `fatal_errors`。更新 `test_single_round_exception_is_diagnosed_and_next_round_continues` 断言。
- **修复风险（低）**: diagnostics dataclass 新增字段，需同步更新所有构造点。
- **严重程度（低）**:

## Verified Correct — Review Focus Areas

以下逐项对照 review focus 验证结果：

### 1. Host wait owner 是 deadline/expires 解析和 expired/invalid 边界决策的唯一 owner

**通过。** `dayu/host/wait_boundary.py:classify_wait_time_boundary()` 是 `deadline_at` / `expires_at` 解析的唯一真源。三个消费点均通过该函数获取 typed 判定：

- `dayu/host/waiting.py:773-788`：`resolve_wait` 在 status 检查后、run terminal 检查前调用，INVALID raise HostApiError，EXPIRED 走 `_reject_late_result(WAIT_EXPIRED)`
- `dayu/host/wait_adapter.py:1185`：`_release_expired_or_invalid_boundary` 在 adapter 调用前检查，ACTIVE 返回 None 让流程继续
- 旧 owner 漂移代码已移除：`dayu/fins/ingestion/wait_adapter.py:_wait_boundary_lost`（26 行）删除，`dayu/host/wait_callback.py:_stale_status_or_none`（36 行）删除

### 2. callback 和 Fins provider adapter 不再修复/猜测/转换 Host wait 边界语义

**通过。** 
- `dayu/host/wait_callback.py`：`_stale_status_or_none` 完全删除，`resolve_callback` 不再在 authenticate → read state → digest check 链路中插入 deadline 检查。过期/非法边界由下游 `resolve_wait` 统一处理。
- `dayu/fins/ingestion/wait_adapter.py`：`_wait_boundary_lost` 完全删除，`_poll_error_result` 中 `TRANSIENT_UNAVAILABLE` 分支不再查询 `wait_record.deadline_at` / `expires_at`，直接返回 `WaitPollNotReady()`。import `parse_utc_timestamp` 已移除。
- `dayu/fins/ingestion/wait_adapter.py:6`：不再 import `parse_utc_timestamp`。

### 3. expired/invalid wait outcomes 在 callback 和 poll 路径一致，不产生错误终态

**通过，有一条诊断层面的已报告 finding（DS-C1-01）。**

- Poll 路径：`_release_expired_or_invalid_boundary` 在 `poll_once` 中于 adapter 调用前拦截 → `_release_with_backoff` 写 backoff，claim 释放，wait 保持 WAITING。
- Callback 路径：`resolve_wait` 中 `classify_wait_time_boundary` → EXPIRED 走 `_reject_late_result(WAIT_EXPIRED)` 追加 `WAIT_LATE_RESULT_REJECTED` event，wait 保持 WAITING；INVALID raise `HostApiError(INVALID_STATE)` → callback adapter 映射为 `INVALID_WAIT_STATE`，不追加 EventLog。
- 两个路径均不将过期/非法边界转换为 RESOLVED/FAILED/LOST 终态，也不调用 provider adapter。
- 测试验证：
  - `test_expired_poll_wait_is_released_before_provider_observation`：用 ready/not-ready/error 三种 adapter 参数化，验证 `adapter.poll_count == 0` 或 `adapter.polled == []`
  - `test_invalid_poll_deadline_fails_closed_without_business_lost`：验证 `result.lost == 0`，`poll_last_error_code == "invalid_wait_time_boundary"`
  - `test_resolve_wait_rejects_expired_wait_from_common_owner`：验证 `HostApiError(INVALID_STATE)` + wait 保持 WAITING + `WAIT_LATE_RESULT_REJECTED` event
  - `test_resolve_wait_invalid_deadline_fails_closed_without_lost`：验证 EventLog 无变化 + wait 保持 WAITING

### 4. supervisor transient round exception isolation 不隐藏不可恢复的自关闭/编程错误

**通过，有一条 string-matching 脆弱性 finding（DS-C1-02）。**

- `_run_loop` 中 while 循环内的 try/except 覆盖 `_poll_once` + `_record_poll_result` + `_sleep_until_next_poll`。非自关闭异常记录诊断、backoff 等待、继续循环。
- 自关闭异常（`RuntimeError` with `_WAIT_POLLER_SELF_CLOSE_ERROR`）仍走 fatal 路径：log exception、`_diagnostics_with_fatal_error`、设置 close_event/wakeup_event、break。
- `_close_event.is_set()` 在 except 块内 break 前检查，避免 close 信号后多余的 backoff 等待。
- 测试验证：`test_single_round_exception_is_diagnosed_and_next_round_continues`：`_FailingOncePoller` 第一次抛异常 → supervisor 记录诊断并继续 → 第二次正常返回 → `diagnostics.status is RUNNING` + `fatal_errors == 1` + `"wait poller round failed; retrying"` in log。
- 旧行为验证：`test_close_from_supervisor_thread_marks_failed_diagnostics` 保持不变，自关闭仍标记 FAILED。

### 5. _resolve_claimed_wait recovery path 在 secondary read 失败后不泄漏 claim 也不崩溃 supervisor

**通过。**

- `_resolve_claimed_wait` 中 `resolver.resolve_wait` 异常后，read-back 包裹在独立 try/except 中（`:1238-1250`）。
- read-back 失败时返回 `StateMutationStatus.INVALID_STATE`，不 raise。
- 调用方 `poll_once` 对 `INVALID_STATE` 的处理（`:997-1007`）：`adapter_errors += 1`，然后走 `_release_with_backoff` 释放 claim。
- 任何情况下异常不会冒泡到 `_run_loop`，supervisor 不会因单个 wait 的 resolve/recovery 失败而终止。
- 测试验证：`test_resolve_wait_exception_readback_failure_isolated`：通过 monkeypatch 让 read-back 抛异常 → 验证 `result.adapter_errors == 1`、`wait_record.poll_claim_id is None`（claim 已释放）、`"wait poll resolve recovery read failed; continuing"` in caplog、wait 保持 WAITING。

### 6. cancelled abandon CAS_LOST 仅安全时释放当前 claim

**通过。**

- `_abandon_cancelled_wait` 中 `_MarkWaitRecordAbandonedOperation` 返回非 UPDATED 时（`:1166-1172`），调用 `_release_with_backoff` 尝试释放当前 claim。
- `_release_with_backoff` 内部使用 `_ReleaseWaitRecordClaimOperation`，该操作 CAS 校验 claim_id——只有当前 poller 仍持有 claim 时才能成功释放；若其他 poller 已抢占则返回 CAS_LOST（计为 claim_conflicts=1）。
- 旧代码（已替换）仅 `return 0, 0, 1, 0`——claim_conflicts 递增但不尝试释放 claim，导致 orphan claim 等待 TTL 过期。
- 测试验证：`test_abandon_cas_lost_releases_current_claim`：`_AbandonAlreadyMarkedAdapter` 在 abandon 调用中写入 `poll_abandoned_at`（模拟 CAS 竞争）→ poller `_MarkWaitRecordAbandonedOperation` 返回 CAS_LOST → 新代码调用 `_release_with_backoff` → 验证 `wait_record.poll_claim_id is None`（claim 已释放）、`wait_record.poll_abandoned_at is not None`、`result.claim_conflicts == 0`（释放成功）。
- 未覆盖场景：当 claim 已被其他 poller 抢占时，`_release_with_backoff` 也会返回 CAS_LOST——该路径受 `_ReleaseWaitRecordClaimOperation` 的 CAS 保护，不会错误释放他人 claim。

### 7. waiting.py request atom 校验使用注入的 EventLogStore

**通过。**

- `_wait_tool_call_requested_event` 新增 `event_log_store` 参数（`:1531`），替换 `EventLogStore()` 临时构造（旧 `:1520`）。
- `_validate_wait_request_arguments_digest` 新增 `event_log_store` 参数（`:1580`），替换 `EventLogStore()` 临时构造（旧 `:1556`）。
- `_tool_result_resolution_payload` 新增 `event_log_store` 参数（`:1450`），透传给上述两个函数。
- `resolve_wait` 中三个 `_tool_result_resolution_payload` 调用点（`:1004`, `:1074`, `:1142`）均传入 `self._event_log_store`。
- 测试验证：`test_resolve_wait_uses_injected_event_log_store_for_request_atom`：构造 `_CountingEventLogStore`（继承默认 EventLogStore 并记录 `read_event_by_id` 调用）→ 注入 `DefaultHostResolveWaitService` → 验证两个预期 event_id（`event-tool-call-requested-awaiting-*` 和 `event-tool-awaiting-*`）均在 `read_event_ids` 中。

### 8. 测试断言 owner-level contract 而非 adapter-specific fallback

**通过。**

- Fins 测试 `test_fins_wait_poll_adapter_transient_unavailable_does_not_read_host_boundaries`：重命名并重写断言——所有边界场景（future/past/invalid deadline/expires、无边界）均断言 `WaitPollNotReady`，不再断言 `WaitPollLost`。验证 adapter 不消费 Host 边界。
- Callback 测试 `test_expired_callback_is_rejected_by_resolve_owner`：从断言 `STALE_CALLBACK` + EventLog 不变改为断言 `INVALID_WAIT_STATE` + `WAIT_LATE_RESULT_REJECTED` event。验证行为迁移到 resolve owner。
- Callback 测试 `test_invalid_stored_deadline_is_failed_closed_by_resolve_owner`：从 mock-only 单元测试（`_FailIfCalledResolver` + `_FakeStateReader`）改为真实 Host 集成测试——直接写入非法 deadline 文本到 SQLite，调用 `_real_adapter(host).resolve_callback`，断言 `INVALID_WAIT_STATE` + wait 保持 WAITING + EventLog 不变。
- Resolve wait 测试新增 `test_resolve_wait_rejects_expired_wait_from_common_owner` 和 `test_resolve_wait_invalid_deadline_fails_closed_without_lost`，直接测试 `resolve_wait` 公共入口的边界行为。
- Poll 测试 `test_expired_poll_wait_is_released_before_provider_observation` 参数化覆盖 ready/not-ready/adapter-error，均验证 adapter 未被调用。

### 9. 无 broad compatibility shim、无 weak typing/docstring 违规、无 Batch C2 scope creep

**通过。**

- 所有新增代码有完整中文 docstring（参数、返回值、异常）。
- 无 `hasattr`/`getattr` 使用。
- 无 `Any`/`object` 类型引入。
- 无兼容性 re-export 或 wrapper。
- `dayu/host/wait_boundary.py` 全部使用 frozen dataclass + slots + StrEnum，`classify_wait_time_boundary` 有严格的输入类型校验（TypeError/ValueError）。
- `_WAIT_POLLER_SELF_CLOSE_ERROR` 常量仅在两处使用（raise + catch），无扩散。
- `_POLL_ERROR_CODE_WAIT_EXPIRED` / `_POLL_ERROR_CODE_INVALID_TIME_BOUNDARY` 常量仅在一处使用。
- Batch C1 未触及 Batch C2 范围（dispatch、promotion、cancel predispatch、tool accept duplicate index、Engine retry）。diff 范围与 implementation codex 声明的 scope 一致。
- `dayu/host/durable/codec.py` 中 `parse_utc_timestamp` 未被删除——它仍被 `wait_boundary.py` 合法引用。

## Open Questions

1. **过期 wait 的 backoff 上界**：`_release_with_backoff` 对过期 wait 写入递增的 `poll_backoff_attempt`，backoff 延迟按指数增长。过期 wait 永远不会变成 active，因此 backoff 会无限增长。当前无上界保护——极长 backoff 后该 wait 实际上被"遗忘"但状态仍为 WAITING。是否为预期行为？建议确认产品策略是否需要过期 wait 自动过渡到终态或定期清理。

2. **`WaitPollLastOutcome` 枚举扩展**：新增 `BOUNDARY_EXPIRED` 枚举值需要同步更新 schema CHECK 约束（`dayu/host/durable/schema.py:856-858`）。这个变更是否计划在 Batch C2 或后续 batch 中处理？当前实现用 error_code 做 disambiguation 是可行的过渡方案。

## Residual Risk

1. **过期 wait 无限 WAITING**：过期 wait 永不自动进入终态。如果大量 wait 过期（例如 provider 长时间不可用后的恢复期），poller 会在每轮 poll 中对所有过期 wait 执行 claim → classify → release 循环，浪费 claim 竞争和数据库写入。当前无机制跳过或批量处理已知过期的 wait。建议后续增加 `next_observe_at` 上限或过期后跳过 claim 的快速路径。

2. **`_AbandonAlreadyMarkedAdapter` 测试覆盖 gap**：`test_abandon_cas_lost_releases_current_claim` 仅覆盖 abandon marker CAS_LOST 但 claim 仍属于当前 poller 的场景。未覆盖 claim 已被其他 poller 抢占的并发场景（此时 `_release_with_backoff` 也会返回 CAS_LOST）。该场景受 `_ReleaseWaitRecordClaimOperation` 的 CAS 自然保护，但缺少显式回归测试。

3. **`WaitPollLastOutcome.RESOLVE_ERROR` 语义漂移**：如 DS-C1-01 所述，该枚举值现在同时表示真实 resolve 错误和边界拒绝。不阻塞 merge，但建议在下一次涉及 `WaitPollLastOutcome` 枚举的 change 中一并修正。

4. **`WaitPollerDiagnosticsSnapshot.fatal_errors` 语义漂移**：如 DS-C1-03 所述，该字段现包含可恢复轮次异常。不阻塞 merge，已在实现文档中记录。

## Conclusion

- **conclusion**: Batch C1 实现正确地将 wait deadline/expiry 语义所有权收束到 Host wait owner（`wait_boundary.py:classify_wait_time_boundary`），成功移除了 callback adapter 和 Fins provider adapter 中的重复边界解析。supervisor 单轮异常隔离、resolve recovery read-back 保护、cancelled abandon CAS_LOST claim 释放、EventLogStore DI 均正确实现且测试覆盖充分。发现 3 个 finding：1 个中等严重度（诊断计数器与持久化 outcome 语义漂移）、2 个低严重度（string-matching 异常分发、fatal_errors 计数器语义漂移）。无阻塞性 correctness 问题，无安全或数据丢失风险。
- **findings count**: 3（1 中 + 2 低）
- **artifact**: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-code-review-ds.md`
- **residual risk**: 过期 wait 无限 WAITING 的长期运维成本、abandon CAS_LOST 并发场景测试 gap、diagnostics 字段语义漂移
- **no code changes confirmation**: 本次 review 未修改任何代码。仅产出 review artifact。
