# P8-S4 Code Review

- **Review gate**: P8-S4 code review
- **Reviewed target**: `migration/host-p8-attempt-lease-recovery` branch, uncommitted diff against `c025d81 host: add p8 attempt supervisor`
- **Diff scope**: `dayu/host/_attempt_supervisor.py`, `dayu/host/_durable_event_store.py`, `dayu/host/_durable_harness.py`, `dayu/host/_run_harness.py`, `dayu/host/_run_state_store.py`, `dayu/host/README.md`, `tests/host/test_phase8_attempt_supervisor.py`, `tests/host/test_phase8_attempt_fencing.py`, `tests/README.md`
- **Artifact path**: `docs/host/phase8-s4-code-review.md`

## Conclusion

**有条件通过 (CONDITIONALLY PASSED)**

核心原子语义正确：`append_terminal_and_close` 在单一 `BEGIN IMMEDIATE` 事务内完成 `verify_owner` → `append_with_position_in_transaction` → `close_terminal`，任一 CAS 失败抛 `AttemptFencingError` 整事务回滚。`LocalRunHarness._run_to_store` 的 terminal 路由条件清晰，legacy 路径保持 P6/P7 行为。P8-S3 Low-3 已通过端到端 owner-lost 集成测试补齐。README 同步准确。无 P8-S5/S6/S7 提前实现。

存在 2 个 accepted findings 需修复后 re-review。

## 验证结果

| 验证项 | 结果 |
|--------|------|
| `pytest tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_supervisor.py -q` | 15 passed |
| `pytest tests/host -q` | 261 passed |
| `python -m pyright dayu/host tests/host` | 0 errors |
| `git diff --check` | exit 0 |

## Findings

### F1-accepted-[中]-attempt 终态映射函数重复定义
- **入口/函数**: `_attempt_state_from_terminal_event_type` / `_attempt_state_from_draft_type`
- **文件(行号)**: `_attempt_supervisor.py:793-821`, `_run_harness.py:2140-2164`
- **输入场景**: 所有 terminal event → attempt 终态映射路径
- **实际分支**: `_attempt_supervisor.py` 定义了 `_attempt_state_from_terminal_event_type`，`_run_harness.py` 定义了 `_attempt_state_from_draft_type`，两者 match 分支完全一致
- **预期行为**: 同一映射逻辑只存在一处定义，其它模块引用或委托
- **实际行为**: 两处独立定义，docstring 互相承认重复（`_attempt_supervisor.py:799` 写"与 `_run_harness._attempt_state_from_terminal` 同义"）
- **直接证据**: `_attempt_supervisor.py:808-821` 与 `_run_harness.py:2154-2164` 的 match 分支逐条一致
- **影响**: 维护风险——新增 terminal event type 时需同步两处；当前虽无行为差异，但违反 single source of truth
- **建议改法和验证点**: 删除 `_attempt_supervisor.py` 中的 `_attempt_state_from_terminal_event_type`，改为 import `_run_harness._attempt_state_from_draft_type`（或将其提升到 contracts / shared helper）。验证: pytest 全量通过 + pyright 0 errors
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **controller decision**: `accepted` — 已修复 (新增 `dayu/host/_attempt_state_mapping.py::attempt_state_from_terminal_event_type` 作为 single source of truth, `_attempt_supervisor.py` 与 `_run_harness.py` 均改为 import 该 helper, 删除原两处重复 match 分支; 不走 review 建议的"从 `_attempt_supervisor` import `_run_harness._attempt_state_from_draft_type`"以避免循环依赖)

### F2-accepted-[中]-`_append_terminal_and_close` 事务提交后额外 DB round-trip 取回 RunEvent
- **入口/函数**: `LocalRunHarness._append_terminal_and_close`
- **文件(行号)**: `_run_harness.py:1574-1588`
- **输入场景**: 所有走 atomic terminal close 路径的正常 owner terminal event
- **实际分支**: `append_terminal_and_close` 在事务内 append RunEvent → 事务提交 → `list_events` 再查询 DB 取回同一 RunEvent
- **预期行为**: 事务内已有 `AppendedRunEvent`（含完整 `RunEvent`），应直接传递给 caller，避免事务提交后的额外 round-trip
- **实际行为**: `append_terminal_and_close` 仅返回 `AttemptTerminalLink`（cursor + position），caller 无法拿到 `RunEvent`，被迫在事务外做 `list_events` 查询。引入一个 "append 后立即可查" 的隐含不变量，且查询失败时抛 `RuntimeError("atomic close invariant broken")`
- **直接证据**: `_run_harness.py:1574-1588`（`list_events` 循环查找匹配 sequence 的 RunEvent）
- **影响**: 性能开销（额外一次 SQLite 查询）；不变量依赖隐含假设（事务提交后 DB 立即可读），虽然 SQLite WAL 下成立但无显式保证；`RunEvent` 对象被构造两次（事务内一次、查询一次）
- **建议改法和验证点**: 方案 A: 扩展 `AttemptTerminalLink` 或新增 `AttemptTerminalResult` 包含 `RunEvent`，让 `append_terminal_and_close` 在事务内直接返回完整 `RunEvent`。方案 B: 在 `_append_terminal_and_close` 内从 `draft` 构造一个等价的 `RunEvent`（不推荐，需猜测 cursor/position）。验证: pytest 全量通过 + 消除 `_run_harness.py:1574-1588` 的 `list_events` 查询
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **controller decision**: `accepted` — 已修复 (扩展 `AttemptTerminalLink` 增加 `event: RunEvent` 字段, `AttemptSupervisor.append_terminal_and_close` 在事务内直接把 append 的 `RunEvent` 通过 link 返回; `LocalRunHarness._append_terminal_and_close` 改为 `return link.event`, 删除事务提交后的 `event_store.list_events` 查询与 "atomic close invariant broken" 兜底分支; terminal_event_position / event_cursor / event_position 语义保持不变)

### F3-deferred-with-owner-[低]-集成测试通过 `supervisor._sessions` 访问内部状态
- **入口/函数**: `test_run_to_store_owner_lost_drops_late_engine_event_and_writes_host_failure`
- **文件(行号)**: `test_phase8_attempt_supervisor.py:1026-1030`
- **输入场景**: owner-lost 端到端集成测试
- **实际分支**: 测试直接访问 `recording.inner._sessions`（`noqa: SLF001`）获取 `attempt_id` 和 `owner_context`
- **预期行为**: 测试通过公开 API 获取 attempt 信息，不依赖内部 `_sessions` 结构
- **实际行为**: `_LeaseSession` 是 module-private dataclass，`_sessions` 是 `dict[str, _LeaseSession]`；测试需要 `attempt_id` 和 `owner_context` 来做外部 fence 和 owner-active 轮询，当前无公开 API 暴露这些
- **直接证据**: `test_phase8_attempt_supervisor.py:1026` `recording.inner._sessions[next(iter(recording.inner._sessions))]`
- **影响**: 测试与内部结构耦合；若 `_sessions` 结构变化测试会 break。但当前 slice 内可接受——`_RecordingDiagnosticSupervisor` 已经是测试专用 wrapper
- **建议改法和验证点**: P8-S5 或后续 slice 可考虑在 `AttemptSupervisor` 暴露 `get_active_attempt_id(run_id) -> str | None` 或在 `lease_context` 返回的 `AttemptOwnerContext` 上挂载更完整的测试 hook。当前 slice 不阻塞
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **controller decision**: `deferred-with-owner` — P16 / issue #28

### F4-rejected-with-reason-[低]-`failure_summary` 使用 event type value 而非实际错误内容
- **入口/函数**: `LocalRunHarness._append_terminal_and_close`
- **文件(行号)**: `_run_harness.py:1560-1568`
- **输入场景**: terminal event 为 RUN_FAILED / RUN_CANCELLED / RUN_SUSPENDED
- **实际分支**: `failure_summary = draft.type.value`（例如 `"run_failed"`）
- **预期行为**: `failure_summary` 应携带诊断有意义的错误摘要
- **实际行为**: 当前 `failure_summary` 仅为 event type 的字符串值，与 `state` 字段冗余
- **直接证据**: `_run_harness.py:1560-1568` 条件分支
- **影响**: `host_attempts.failure_summary` 字段诊断价值有限，不包含实际错误信息。但 P8-S4 的承诺是"同事务原子写入"，`failure_summary` 内容丰富度不在本 slice scope 内；P6/P7 legacy 路径的 `_finish_attempt_if_durable` 也只传 `event.type.value`
- **建议改法和验证点**: 后续 slice（P8-S5 或 P9）可从 `RunEvent.data`（如 `HostRunFailedData.error_message`）提取更有意义的 summary。当前与 P6/P7 行为一致，不构成回归
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **controller decision**: `rejected-with-reason` — 当前行为与 P6/P7 legacy 路径一致，`failure_summary` 内容丰富化属于后续优化，不在 P8-S4 scope 内

## 审查清单逐项结论

### 1. terminal RunEvent append、owner fencing、attempt close、terminal_event_position 写入是否在同一 BEGIN IMMEDIATE 事务内

**通过。** `_attempt_supervisor.py:443-460`: `async with self.storage.transaction() as tx` 内顺序调用 `verify_owner` → `append_with_position_in_transaction` → `close_terminal`，三步共享同一 `tx`。

### 2. owner verify / close_terminal CAS 失败时是否整事务回滚

**通过。** `verify_owner`（`_run_state_store.py:673`）和 `close_terminal`（`_run_state_store.py:660`）在 CAS miss 时抛 `AttemptFencingError`，异常向上传播到 `async with self.storage.transaction() as tx` 的 `__aexit__`，触发事务回滚。测试 `test_append_terminal_and_close_rolls_back_when_owner_fenced` 和 `test_append_terminal_and_close_rejects_lease_expired` 验证了 EventLog 无残留。

### 3. `append_with_position_in_position` 是否没有改变 public RunEventCursor 语义

**通过。** `_durable_event_store.py:371-390`: `append_with_position_in_transaction` 是新方法，返回 `AppendedRunEvent`（含 `GlobalEventPosition`）。既有的 `append` / `append_in_transaction` 仍返回 `RunEvent`，签名未变。`AppendedRunEvent` 在 `__all__` 中导出，但仅 `AttemptSupervisor` 消费，不进入 public RunEventCursor。

### 4. `_run_to_store` terminal 路由条件是否正确

**通过。** `_run_harness.py:651-660`: atomic 路径条件为 `draft.type in TERMINAL_RUN_EVENT_TYPES and current_active_attempt is not None and self._can_atomic_terminal_close(current_active_attempt)`。`_can_atomic_terminal_close`（`_run_harness.py:1516-1521`）要求 `active_attempt is not None and owner_context is not None and lease_exit_stack is not None and attempt_supervisor is not None`。legacy 路径在 `atomic_attempt is None` 时走 `event_store.append` + `_finish_attempt_if_durable`，与 P6/P7 一致。

### 5. P8-S3 Low-3 是否真正补齐 `_run_to_store` 端到端路径

**通过。** `test_run_to_store_owner_lost_drops_late_engine_event_and_writes_host_failure`（`test_phase8_attempt_supervisor.py:991-1359`）覆盖完整路径: `build_durable_harness` → fake proxy yield preview → 外部 fence → supervisor renew CAS miss → `_handle_owner_lost` → Host `RUN_FAILED(error_code=attempt_lease_lost)` → late Engine event 不进 EventLog → diagnostic close CAS miss 返回 `False` → `host_attempts.state` 仍为 `running`。不只测 helper race。

### 6. owner-lost 测试依赖 `supervisor._sessions` 的同步方式

**可接受，标记为 deferred。** 见 F3。当前 slice 内无更好方案（`_RecordingDiagnosticSupervisor` 已是 test-only wrapper），后续 slice 可暴露公开 API。

### 7. README 同步是否准确

**通过。** `dayu/host/README.md` 更新了 P8-S4 已落地的 terminal atomic close 语义描述，将 P8-S4 从未落地列表移除，保留 P8-S5/S6/S7。`tests/README.md` 补充了 P8-S4 fencing 原子 close 测试和 owner-lost 端到端集成测试的描述。无提前声明 P8-S5/S6/S7 已实现。

### 8. 是否出现提前实现 P8-S5/S6/S7

**未发现。** diff 中无 ToolRuntime attempt-scoped append（P8-S5）、recovery scan（P8-S6）、multiprocessing（P8-S7）相关代码。

### 9. 类型签名、中文 docstring、无 Any/object、无 type ignore 扩散、无 magic string/number

**基本通过。** 所有新增函数/方法有完整中文 docstring。无 `Any`/`object` 类型签名。`type: ignore` 仅在 `test_phase8_attempt_fencing.py:412` 出现一次（`data=None, # type: ignore[arg-type]`），为验证测试故意传入非法值，有充分理由。`_run_state_store.py` 中的 `type: ignore[index]` 为 P8-S1 已有代码（sqlite3.Row 索引访问），非本次新增。magic string/number: `10_000_000`（`test_phase8_attempt_supervisor.py:1035`）为测试用 fencing token 值，可接受。

### 10. residual risks 是否落到文档

**通过。** F1（duplicate mapping）和 F2（extra DB round-trip）已修复并经 re-review 通过（见 `docs/host/phase8-s4-fix-rereview.md`）。F3（`_sessions` 访问）deferred 到后续 slice。

## Residual Risk 分类

| 风险 | 分类 | Owner |
|------|------|-------|
| F1: duplicate mapping function | accepted → 已修复 | 当前 slice |
| F2: extra DB round-trip | accepted → 已修复 | 当前 slice |
| F3: test `_sessions` access | deferred-with-owner | P16 / issue #28 |
| P8-S5 ToolRuntime attempt-scoped CAS append | 未实现 | P8-S5 |
| P8-S6 recovery scan | 未实现 | P8-S6 |
| P8-S7 multiprocessing | 未实现 | P8-S7 |
