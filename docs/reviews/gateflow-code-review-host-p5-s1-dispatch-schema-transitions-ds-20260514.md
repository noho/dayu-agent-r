# Host Phase 5 P5-S1 代码审查报告

- **审查对象**: Host Phase 5 P5-S1 (Dispatch Schema And Transition Primitives) 未提交实现 diff
- **审查分支**: `feat/host-phase5-local-dispatch`
- **审查日期**: 2026-05-15
- **审查角色**: 独立代码审查员 (review only, no production changes)
- **审查范围**: 仅限 P5-S1 slice 允许文件列表的未提交改动

## 审查方法

逐文件审查了全部 diff (88.4KB)，交叉验证了 schema CHECK 约束、state mutation CAS 条件、transition 前置检查与事件 payload、以及测试覆盖。审查基准: 正确性 > 稳定性 > 可维护性；不包含性能分析或安全性审查。

## 结论摘要

**未发现阻塞性 (blocking) 问题。** 此 slice 实现可以接受。

发现5个建议项: 0 个 Critical，0 个 High，3 个 Medium，2 个 Low。全部为非阻塞性建议。

---

## 发现项

### M1 (Medium) — `mark_dispatching_after_lane_row` 允许 PENDING → DISPATCHING 跳转但语义不一致

**文件**: `dayu/host/durable/state.py` — `mark_dispatching_after_lane_row()`

**证据**:
```sql
WHERE attempt_id = ?
  AND status IN (?, ?)    -- 'pending', 'waiting_for_lane'
```

`mark_dispatching_after_lane_row` 的 SQL WHERE 接受 `PENDING` 和 `WAITING_FOR_LANE` 两种源状态。但该函数的 SET 子句有:
```sql
waiting_for_lane_at = COALESCE(waiting_for_lane_at, ?),
```

当源状态为 `PENDING` 时，`waiting_for_lane_at` 为 NULL，COALESCE 将其设为 `dispatching_at` 值。这意味着 PENDING → DISPATCHING 跳转在 SQL 层面合法，且 `waiting_for_lane_at` 会被自动填充为 `dispatching_at`。

**影响**: 允许调用方跳过 `mark_dispatch_waiting_for_lane_row` 直接进入 `DISPATCHING`。这违反了状态机设计意图 (pending → waiting_for_lane → dispatching)，但不会产生数据损坏——CHECK 约束要求 `waiting_for_lane_at` 在 dispatching 时 NOT NULL，COALESCE 保证了这一点。产生的是一个诊断时间戳失真的 dispatching 记录 (`waiting_for_lane_at == dispatching_at`)。

**建议**: 如果状态机意图是必须经过 `waiting_for_lane`，应限制 WHERE 条件为 `status IN ('pending', 'waiting_for_lane')` 的同时，在应用层前置检查或调用规范中约束调用方必经 waiting 跳转。如果跳过 waiting 是允许的优化路径，应在函数 docstring 和 `_dispatch_record_mutation_result_for_dispatch_start` 的 CAS_LOST 逻辑中明确说明。

**是否阻塞**: 否。CHECK 约束保证了数据完整性，调用方使用 `mark_dispatching_after_lane_row` 函数名本身已有语义约束。COALESCE 的防御性处理是正确的。

---

### M2 (Medium) — `request_active_attempt_cancel_in_transaction` 的 `_run_cancelling_event_request` 未捕获返回值但无影响

**文件**: `dayu/host/durable/run_transition.py` — `request_active_attempt_cancel_in_transaction()`

**证据**:
```python
cancel_request_event = event_log_store.append_event(
    transaction, _cancel_requested_event_request(request, run)
).row
event_log_store.append_event(             # <-- 返回值未捕获
    transaction,
    _run_cancelling_event_request(
        request=request,
        run=run,
        attempt=attempt,
        cancel_request_event_id=cancel_request_event.event_id,
    ),
)
```

`CANCEL_REQUESTED` 的 event row 被捕获并用于后续 `RUN_CANCELLING` event payload 中的 `cancel_request_event_id`。但 `RUN_CANCELLING` event 的 append 返回值未被捕获。

**影响**: 无功能影响。`RUN_CANCELLING` event row 不在当前 slice 的下游使用（后续 Phase 5 slices 的 cancel propagation 可能需要它）。对比 `cancel_queued_in_transaction` 路径捕获了 `run_cancelled_event` 的 event_id 和 event_sequence 用于 `cancel_queued_run_row`，此处不需要因为 `mark_run_cancelling_row` 不依赖 event refs。

**建议**: 可以加一行注释说明返回值不需要在此 slice 使用，避免后续维护者困惑为什么不捕获。

**是否阻塞**: 否。当前 slice 不需要该返回值。

---

### M3 (Medium) — `_validate_cancel_active_input` 向 `_validate_common_cancel_input` 传参时参数语义名不匹配

**文件**: `dayu/host/durable/run_transition.py` — `_validate_cancel_active_input()`

**证据**:
```python
def _validate_cancel_active_input(request: CancelActiveAttemptInput) -> None:
    _validate_common_cancel_input(
        run_id=request.run_id,
        cancel_request_event_id=request.cancel_request_event_id,
        run_cancelled_event_id=request.run_cancelling_event_id,  # <-- 语义不匹配
        ...
    )
```

`_validate_common_cancel_input` 的形参名是 `run_cancelled_event_id`，而 `CancelActiveAttemptInput` 的字段名是 `run_cancelling_event_id`（注意 `cancelled` vs `cancelling`）。两个值语义不同: `run_cancelling_event_id` 是 RUN_CANCELLING 事件（非终态），而 `run_cancelled_event_id` 是 RUN_CANCELLED 事件（终态）。

**影响**: 无运行时影响（两者都是 `_require_non_empty_text` 校验的 str 类型）。但代码可读性受损——阅读 `_validate_common_cancel_input` 时难以判断某个调用方传入的是 cancelling 还是 cancelled event id。

**建议**: 考虑重命名 `_validate_common_cancel_input` 的形参为更通用的名称（如 `run_control_event_id`），或为该参数添加 docstring 说明不同调用方传入不同语义的 event id。这属于重构范畴，不阻塞当前 slice。

**是否阻塞**: 否。仅影响可读性。

---

### L1 (Low) — `accept_worker_running_in_transaction` 和 `request_active_attempt_cancel_in_transaction` 的负面路径测试不完整

**文件**: `tests/host/test_run_attempt_transitions.py`

**证据**:
- `test_accept_worker_running_in_transaction` 仅覆盖了一条 happy path（完整的 waiting → dispatching → worker accept）
- `test_active_attempt_cancel_appends_run_cancelling_once` 仅覆盖了 happy path + idempotent double-cancel
- 未被测试的路径:
  - `accept_worker_running_in_transaction` 的 NOT_FOUND（run/attempt/dispatch 任一项缺失）、INVALID_STATE（非 RUNNING run、非 STARTING attempt、非 DISPATCHING dispatch、worker 已接受）
  - `request_active_attempt_cancel_in_transaction` 的 NOT_FOUND（run 不存在）、INVALID_STATE（非 RUNNING run、run.current_attempt_id 为 None、attempt 不存在或非 RUNNING）

**影响**: 这些负面路径的代码逻辑虽然简单直白（直接返回 `RunTransitionResult`），但缺少测试意味着回归不会被自动捕获。

**建议**: 在后续 slice 中补充负面参数化测试（例如 `test_accept_worker_running_rejects_invalid_precondition`）。

**是否阻塞**: 否。正面路径和 schema 级验证测试充分（33 passed）。当前覆盖率为实现边界提供了基本保障。

---

### L2 (Low) — `_ensure_host_instance_tx` 在测试文件间重复定义

**文件**:
- `tests/host/test_state_schema.py:1300`
- `tests/host/test_run_attempt_transitions.py:1458`

**证据**: 两个文件各自定义了一个 `_ensure_host_instance_tx` 函数，功能相同（INSERT OR IGNORE 一条 host instance row），但签名不同:
- `test_state_schema.py` 版本接收 `host_instance_id: str` 参数
- `test_run_attempt_transitions.py` 版本接收 `transaction: HostTransaction` 参数，硬编码 host_instance_id 为 `"host-instance-1"`

**影响**: 轻微维护负担。两个版本已有细微差异，后续可能进一步分化。

**建议**: 抽取到共享测试 fixture 模块。不在本 slice 范围内。

**是否阻塞**: 否。测试辅助代码重复是可接受的。

---

## 架构约束检查

- [x] 分层架构: 所有改动均在 `dayu/host/durable/` 层，未跨越 `UI/Service/Engine` 边界
- [x] 反向依赖: 无 `dayu.runtime` / `dayu.engine` / `dayu.service` / `dayu.ui` 的新增依赖
- [x] 类型签名: 无 `object`、`Any`、无类型参数或返回值
- [x] 中文 docstring: 所有新增函数均有完整中文 docstring，包含参数、返回值、异常
- [x] 无胶水 seam / lazy import / hasattr-getattr 滥用
- [x] 无 God object / God function: 职责分解清晰（state.py = 单行 mutation，run_transition.py = 组合 mutation + event 写入）
- [x] 无兼容性代码: 所有改动为 fresh schema v3 全新设计
- [x] `test_weak_typing_guard.py` 未改动且继续通过

## 计划对标检查

- [x] Schema 版本升至 3
- [x] dispatch record status 扩展为 pending / waiting_for_lane / dispatching / cancelled
- [x] 新增 9 个 dispatch 诊断列，含 nullability 规则
- [x] CHECK 约束覆盖所有四种状态的字段组合要求
- [x] `DispatchRecordRow` 扩展 9 个诊断字段，row codec 更新
- [x] 状态 helpers: `mark_dispatch_waiting_for_lane_row`、`mark_dispatching_after_lane_row`、`mark_dispatch_worker_accepted_row`、`cancel_starting_dispatch_record_row`、`mark_attempt_running_row`、`mark_run_cancelling_row`
- [x] transition helpers: `accept_worker_running_in_transaction`、`request_active_attempt_cancel_in_transaction`
- [x] `cancel_predispatch_starting_in_transaction` 泛化为 pending / waiting_for_lane / pre-accept dispatching 均可 direct cancel
- [x] dispatching 已有 worker accept refs 时拒绝 pre-worker direct cancel
- [x] `ATTEMPT_RUNNING` 事件 append 和 CAS STARTING → RUNNING
- [x] `RUN_CANCELLING` 事件首次写入且仅写入一次
- [x] 无 lease/fencing/owner 语义
- [x] 无旧 schema 兼容代码
- [x] 无 scheduler、RunInputBuilder、LocalProxy、Engine ingest、README、implementation-control 改动

## 非目标检查

- [x] 未引入 lease/fencing/ownership 语义: dispatch record 状态、lane diagnostics、owner_id 均为本地诊断/重复派发抑制，非 active worker truth
- [x] 未修改 `test_weak_typing_guard.py`
- [x] 未修改 scheduler / LocalProxy / WorkerProxy / Engine / command facade
- [x] 未引入旧 schema 兼容读取或迁移逻辑

## 验证确认

- 33 tests passed (0.27s)
- pyright: 0 errors, 0 warnings
- git diff --check: no whitespace errors

## 裁决

**接受此 slice。** 无阻塞性发现。3 个 Medium 建议项为非阻塞性改进机会（PENDING→DISPATCHING 跳转语义、未使用的返回值、参数命名不一致），2 个 Low 建议项为测试覆盖和测试辅助代码风格优化。核心 schema constraint、CAS 条件、transition 前置检查和事件 payload 的代码审查均通过。
