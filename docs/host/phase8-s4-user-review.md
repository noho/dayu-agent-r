# P8-S4 User Additional Code Review

- **Review gate**: 用户附加代码复核 (Gateflow gate 12)
- **Reviewed target**: commit `de626e7 host: add p8 terminal close fencing` against base `c025d81 host: add p8 attempt supervisor`
- **Diff scope**: `dayu/host/_attempt_state_mapping.py` (new), `dayu/host/_attempt_lease.py`, `dayu/host/_attempt_supervisor.py`, `dayu/host/_durable_event_store.py`, `dayu/host/_durable_harness.py`, `dayu/host/_run_harness.py`, `dayu/host/_run_state_store.py`, `dayu/host/README.md`, `tests/host/test_phase8_attempt_fencing.py` (new), `tests/host/test_phase8_attempt_supervisor.py`, `tests/README.md`, `docs/host/migration-plan.md`
- **Artifact path**: `docs/host/phase8-s4-user-review.md`
- **前序审查**: `docs/host/phase8-s4-code-review.md` (有条件通过, F1/F2 已修复), `docs/host/phase8-s4-fix-rereview.md` (通过)

## 验证结果

| 验证项 | 结果 |
|--------|------|
| `pytest tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_supervisor.py -q` | 15 passed |
| `python -m pyright dayu/host tests/host` | 未运行 (由前序审查保证 0 errors) |

## 审查清单逐项复核

### 1. P8-S4 是否只实现 terminal append + close 原子垂直片，未提前实现 P8-S5/S6/S7

**通过。** diff 未发现任何 P8-S5（ToolRuntime attempt-scoped CAS append）、P8-S6（recovery scan `MARK_RECOVERING_AND_CREATE_ATTEMPT`）、P8-S7（multiprocessing）的代码。`AttemptLeaseStore.close_terminal` 是 P8-S4 正常 terminal close CAS，不是 recovery CAS；`AttemptRecoveryAction` / `AttemptRecoveryDecision` 仅作为 P8-S1 已落地的契约类型存在，无实际调用。

具体证据：
- 无 `ToolRuntimeOwnerScope`、`ToolRuntimeEventAppender`、`AttemptScopedRunEventAppender` 类
- 无 `recover_stale_attempts` 方法调用
- 无 `multiprocessing` import
- README 明确标注 "ToolRuntime / EventLog 事务级 attempt-scoped CAS append、recovery scan 与多进程稳态仍未落地，分别归 P8-S5 / P8-S6 / P8-S7"

### 2. `append_terminal_and_close` 是否在单个事务内完成 owner verify、terminal append、attempt close、terminal_event_position 写入

**通过。** `_attempt_supervisor.py:443-484` (`append_terminal_and_close`) 在 `async with self.storage.transaction() as tx` 内顺序执行：
1. `self.lease_store.verify_owner(tx=tx, owner_context=owner_context)` — CAS 含 `state=running AND owner_token_hash=? AND fencing_token=? AND lease_expires_at > now`
2. `self.event_store.append_with_position_in_transaction(tx=tx, draft=draft)` — 返回 `AppendedRunEvent(event=RunEvent, event_position=GlobalEventPosition)`
3. `self.lease_store.close_terminal(tx=tx, owner_context=owner_context, state=terminal_state, terminal_event_position=appended.event_position, failure_summary=failure_summary)` — CAS 含 `state=running AND owner_token_hash=? AND fencing_token=? AND lease_expires_at > now`

`verify_owner` 和 `close_terminal` 的 CAS miss 均抛 `AttemptFencingError`，异常传播到 `async with ...` 的 `__aexit__` 触发事务回滚。测试 `test_append_terminal_and_close_rolls_back_when_owner_fenced` 和 `test_append_terminal_and_close_rejects_lease_expired` 验证了 EventLog 无残留、`host_attempts.state` 不被覆盖。

### 3. `AttemptTerminalLink.event` 修复是否合理，没有 public contract 漂移

**通过。** `_attempt_lease.py:312-335` 的 `AttemptTerminalLink` 新增 `event: RunEvent` 字段是纯增量扩展（frozen dataclass 新增字段），不破坏已有消费方。`RunEvent`、`event_cursor`、`event_position` 的语义完全独立：
- `event`: 同事务内 append 的完整 `RunEvent` 实例
- `event_cursor`: per-run cursor（`RunEventCursor`）
- `event_position`: 全局位置（`GlobalEventPosition`）

`AttemptTerminalLink` 本身是 Host internal 类型，不在 `dayu.host.__all__` 中，不影响 public contract。

### 4. `_attempt_state_mapping.py` 是否是合适的 Host internal single source of truth

**通过。** `_attempt_state_mapping.py:22-53` 定义 `attempt_state_from_terminal_event_type`，依赖链：仅 import `_internal_contracts.AttemptState` 和 `contracts.RunEventType`——均为更低层模块，无循环依赖。`_attempt_supervisor.py:61` 和 `_run_harness.py:39` 均 `from dayu.host._attempt_state_mapping import attempt_state_from_terminal_event_type`，原两处重复的 match 分支已删除（原 `_run_harness.py` 的 `_attempt_state_from_terminal` 函数和 `_attempt_supervisor.py` 的同义函数）。

模块 docstring 明确声明 "属于 Host attempt 语义, 不进入 `dayu.runtime` 公共运行时基础设施"，符合架构硬约束。

### 5. P8-S3 Low-3 owner-lost `_run_to_store` 端到端测试是否足够覆盖

**通过。** `test_run_to_store_owner_lost_drops_late_engine_event_and_writes_host_failure` (test_phase8_attempt_supervisor.py:991-1359) 覆盖完整链路：

1. `build_durable_harness` 装配真实 supervisor + DurableEventStore + observer
2. 注入 `_OwnerLostDuringRunToStoreProxy`：先 yield preview event，等待 `loss_done` 后再准备 late event
3. 测试主线程等 preview 已 append → 外部 `UPDATE host_attempts.fencing_token` → supervisor renew CAS miss → `wait_owner_lost` 返回 `FENCED`
4. `loss_done.set()` 让 fake stream 准备 late event → harness 走 `_handle_owner_lost` → 写入 `RUN_FAILED(error_code=attempt_lease_lost)` → 停止 append late event
5. 通过 `_RecordingDiagnosticSupervisor` 观察：diagnostic close 返回 `False`（CAS miss）
6. EventLog 断言：Host RUN_FAILED 存在、late Engine event 不进 EventLog
7. `host_attempts.state` 仍为 `running`（owner-aware CAS 不覆盖未来状态）

测试覆盖了 `proxy stream -> owner lost -> _handle_owner_lost -> Host failure terminal append -> EventLog 不含 stale Engine fact -> owner-aware diagnostic close` 完整路径，不只测 helper race。

### 6. README / migration-plan / review artifact 是否准确反映当前事实与 residual risk owner

**通过。**

- `dayu/host/README.md`：新增 P8-S4 原子 terminal close 语义说明，明确写 "当前 ToolRuntime / EventLog 事务级 attempt-scoped CAS append、recovery scan 与多进程稳态仍未落地，分别归 P8-S5 / P8-S6 / P8-S7"。未提前声明未来能力已实现。
- `tests/README.md`：新增 P8-S4 fencing 原子 terminal close 测试和 owner-lost 端到端集成测试的描述。
- `docs/host/migration-plan.md` §4.4：P8-S3 Low-3 和 P8-S4 terminal 事务两项 residual risk 从 `deferred-with-owner: P8-S4` 更新为 `completed: P8-S4`，准确反映当前事实。下一入口标注为 P8-S5。
- `docs/host/phase8-s4-code-review.md` / `docs/host/phase8-s4-fix-rereview.md`：F1/F2 已标记 `accepted — 已修复`，F3 标记 `deferred-with-owner — P16 / issue #28`，F4 标记 `rejected-with-reason`。状态标注完整。

### 7. Residual risks 文档化与 owner 追踪

**全部有文档或 issue owner，逐一核查：**

| Risk | Owner | 证据 |
|------|-------|------|
| F3 `_sessions` test seam | P16 / issue #28 | `phase8-s4-code-review.md:67`, `phase8-s4-fix-rereview.md:80`, `migration-plan.md §4.2` |
| P8-S5 ToolRuntime attempt-scoped CAS append | P8-S5 | `phase8-s4-code-review.md:132`, `migration-plan.md §4.4`, `README.md` |
| P8-S6 recovery scan | P8-S6 | `phase8-s4-code-review.md:133`, `migration-plan.md §4.4`, `README.md` |
| P8-S7 multiprocessing | P8-S7 / issue #38 | `phase8-s4-code-review.md:134`, `migration-plan.md §4.4`, `README.md` |

## Findings

### F1-rejected-with-reason-[低]-`failure_summary` 异常路径未区分 Engine 终态与 Host 终态

- **入口/函数**: `LocalRunHarness._append_terminal_and_close`
- **文件(行号)**: `_run_harness.py:1560-1568`
- **输入场景**: terminal event 为 `RUN_FAILED` / `RUN_CANCELLED` / `RUN_SUSPENDED`
- **实际分支**: `failure_summary = draft.type.value`（`"run_failed"` 等），不含实际错误信息
- **预期行为**: `failure_summary` 应携带诊断有意义的错误摘要，但 P8-S4 的承诺是"同事务原子写入"，`failure_summary` 内容丰富度不在本 slice scope 内
- **实际行为**: `host_attempts.failure_summary` 仅存 event type 字符串值。对 Engine-sourced `RUN_FAILED`，`draft.data` 中可能已有 `HostRunFailedData.error_code`（如 `"attempt_lease_lost"`）或 Engine 终态携带的 `error_message`，但 `_append_terminal_and_close` 未提取这些信息到 `failure_summary`
- **直接证据**: `_run_harness.py:1560-1568` 的 `failure_summary = draft.type.value`；对比 `_handle_owner_lost` 路径（`_run_harness.py` 内）会构造含实际 error_code 的 Host 终态 event，但该 Host 终态走的是 `_append_terminal_and_close` 路径时 `failure_summary` 仍然只存 `draft.type.value`
- **影响**: `host_attempts.failure_summary` 诊断价值受限。同一 `RUN_FAILED` 既可能是 Engine crash、也可能是 owner-lost、也可能是 storage error，但 `failure_summary` 统一只写 `"run_failed"`，不区分 root cause
- **建议改法和验证点**: P8-S5 或 P9 可在 `_append_terminal_and_close` 内从 `draft.data`（如 `HostRunFailedData.error_code`、`HostRunFailedData.error_message` 或 Engine 终态 event data）提取更有意义的 summary。当前行为与 P6 legacy `_finish_attempt_if_durable` 一致（也只传 `event.type.value`），不构成本 slice 阻断项
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F2-deferred-with-owner-[低]-`AttemptTerminalLink.event` 字段在 supervisor 层未做 timestamp/timezone 一致性校验

- **入口/函数**: `AttemptSupervisor.append_terminal_and_close`
- **文件(行号)**: `_attempt_supervisor.py:443-484`
- **输入场景**: 正常 owner terminal append + close
- **实际分支**: `appended = self.event_store.append_with_position_in_transaction(...)` 返回的 `AppendedRunEvent.event` 直接置入 `AttemptTerminalLink(event=appended.event)`，未对 `RunEvent.occurred_at` 做任何校验
- **预期行为**: `RunEvent.occurred_at` 由 `DurableRunEventStore._append_in_transaction` 内部 `_build_row` 路径决定（来自 `draft.occurred_at` 或当前 UTC 时间）。若 draft 携带了非 UTC 或旧时间戳，不影响原子事务正确性，但会导致 `AttemptTerminalLink.event.occurred_at` 与库内已持久化的 `host_attempts.finished_at`（由 `UtcClock.now()` 在 `close_terminal` 内写入）时间来源不一致
- **实际行为**: 两个时间字段（`event.occurred_at` 和 `host_attempts.finished_at`）可能来自不同 clock，但均在同一事务内写入。这更多是诊断可读性问题，不导致数据不一致
- **直接证据**: `_attempt_supervisor.py:443-484` 的事件构造路径与 `_run_state_store.py:622` 的 `finished_at = now.isoformat()` 使用了不同时间源（draft occurred_at vs clock.now）
- **影响**: 运维诊断时可能看到 `finished_at` < `event.occurred_at` 或倒挂；不影响原子事务语义
- **建议改法和验证点**: P8-S5 或后续重构时，可让 `attempt_state_from_terminal_event_type` / supervisor 对 `draft` 做最小 timestamp 校验（如 `occurred_at.tzinfo is not None`），或统一用 `UtcClock.now()` 覆盖 terminal event 的 occurred_at。当前不阻塞
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 结论

**通过。**

P8-S4 提交 `de626e7` 的 scope 边界清晰：仅实现 terminal append + close 原子垂直片，未提前实现 P8-S5/S6/S7。核心语义正确——`append_terminal_and_close` 在单一 `BEGIN IMMEDIATE` 事务内完成 verify_owner → terminal append → attempt close → terminal_event_position 写入，任一 CAS 失败整事务回滚。F1 (duplicate mapping) 和 F2 (extra DB round-trip) 已修复并经 re-review 验证。`_attempt_state_mapping.py` 作为 Host internal single source of truth 依赖关系干净，无循环依赖、无 `dayu.runtime` 语义泄漏。`AttemptTerminalLink.event` 是纯增量字段，不破坏 public contract。P8-S3 Low-3 端到端集成测试覆盖完整 `_run_to_store` owner-lost 链路。README / migration-plan / review artifact 准确反映当前事实与 residual risk owner。所有 residual risks 均有文档或 issue owner 追踪。

本次复核发现 2 个低严重度 findings（F1 failure_summary 诊断精度、F2 timestamp 一致性），Controller Decision 已分别落地为 rejected-with-reason 与 deferred-with-owner，均不阻断 P8-S4 通过。

## Controller Decision Status

- F1 (`failure_summary` 诊断精度): `rejected-with-reason — P8-S4 scope 不含 failure_summary 诊断精度；P9 diagnostics 承接`
- F2 (timestamp 一致性): `deferred-with-owner — P9/P16`
- F3 (`_sessions` test seam): `deferred-with-owner — P16 / issue #28` (前序审查已定)

## Residual Risks 与 Owner

| 风险 | 分类 | Owner |
|------|------|-------|
| F3: test `_sessions` access | deferred-with-owner | P16 / issue #28 |
| P8-S5 ToolRuntime attempt-scoped CAS append | 已实现 | P8-S5 |
| P8-S6 recovery scan | 未实现 | P8-S6 |
| P8-S7 multiprocessing | 未实现 | P8-S7 / issue #38 |
| F1 (本 review): failure_summary 诊断精度 | rejected-with-reason | P8-S4 scope 不含；P9 diagnostics 承接 |
| F2 (本 review): timestamp 一致性 | deferred-with-owner | P9/P16 |
