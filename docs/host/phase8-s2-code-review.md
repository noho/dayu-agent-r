# P8-S2 Code Review：Async ObserverSink 协议迁移

## 结论：通过

P8-S2 目标完整达成：`ObserverSink.process` 已升级为 async 协议，`_run_async` bridge 已彻底删除，所有 observer 实现与测试均已迁移，同事务语义未被破坏，scope 边界未被超越。

## 总控 Finding 状态

| Finding | Gateflow 状态 | 总控结论 |
|---|---|---|
| Low-1：`MemoryProjectionObserver` 移除 `ObserverSink` import 后无编译期协议一致性强制 | `rejected-with-reason` | 这是 P6 已有的 structural Protocol 使用模式，不是 P8-S2 回归；如需显式继承所有 observer，可在 P16 interface freeze / contract guard 阶段统一评估。 |
| Info-1：`test_phase6_timeline_audit_projection.py` 未被修改 | `rejected-with-reason` | 该文件没有 direct `observer.process(...)` 调用，间接 `coord.drain()` 路径已覆盖 async 调用，不需要修改。 |
| Info-2：`test_phase7_tool_trace_projection.py` 中 `type: ignore[arg-type]` 为 P7 遗留 | `deferred-with-owner: P16` | 属于既有测试 helper 类型边界；若 P16 做接口冻结和契约守护，可统一评估是否引入 typed fake transaction 消除 `type: ignore`。 |

## 验证结果

| 命令 | 结果 |
|---|---|
| `pytest tests/host/test_phase6_projection_checkpoint.py tests/host/test_phase6_review_fixes.py tests/host/test_phase6_timeline_audit_projection.py tests/host/test_phase7_tool_trace_projection.py -q` | 39 passed |
| `pytest tests/host -q` | 246 passed |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 无 whitespace 问题 |
| `grep -rn "_run_async" dayu/host/ tests/host/` | 无残留 |

## Findings

### Low-1 [rejected-with-reason]：`MemoryProjectionObserver` 移除 `ObserverSink` import 后无编译期协议一致性强制

- **证据路径**：`dayu/host/_memory_projection.py` diff — 移除了 `from dayu.host._event_observer import ObserverSink`。
- **语义影响**：`MemoryProjectionObserver` 通过 structural subtyping 满足 `ObserverSink` 协议，没有显式标注。这意味着如果未来 `ObserverSink` 新增方法，`MemoryProjectionObserver` 不会在 import / type check 阶段报错，只会在 `ProjectionCoordinator` 运行时调用时失败。
- **是否阻断 P8-S3**：否。`TimelineProjectionObserver` 和 `AuditProjectionObserver` 也从未 import `ObserverSink`，这是 P6 已有的模式，不是 P8-S2 引入的回归。
- **建议修复方式**：不修。如果需要编译期强制，可以给 observer 类加 `ObserverSink` 显式标注，但这超出 P8-S2 scope。后续 P9/P16 接口冻结时可统一评估。
- **Owner**：无，保持现状。
- **总控结论**：不修。当前 observer 统一通过 structural Protocol 接入，pyright 已覆盖调用点；显式继承不是 S2 root-cause 修复。

### Info-1 [rejected-with-reason]：`test_phase6_timeline_audit_projection.py` 未被修改

- **证据路径**：`git diff tests/host/test_phase6_timeline_audit_projection.py` 无输出。
- **语义影响**：该文件通过 `coord.drain()` 间接调用 `await observer.process(...)`，不存在直接 `observer.process(...)` 调用，因此无需修改。行为正确。
- **是否阻断**：否。
- **总控结论**：不修，无实际 finding。

### Info-2 [deferred-with-owner: P16]：`test_phase7_tool_trace_projection.py` 中 `type: ignore[arg-type]` 为 P7 遗留

- **证据路径**：`tests/host/test_phase7_tool_trace_projection.py` 中 16 处 `cast(object, None)  # type: ignore[arg-type]`。
- **语义影响**：这些 `type: ignore` 在 P7 就已存在，用于向不使用 `tx` 参数的 `ToolTraceObserver.process` 传入 `None`。P8-S2 只把它们从同步调用改为 `await` 调用，未新增 `type: ignore`。
- **是否阻断**：否。这些是 pre-existing test convention，不是 P8-S2 引入的协议掩盖。
- **总控结论**：后移 P16。若接口冻结阶段要求 tests 也具备更强协议守护，可引入 typed fake transaction 统一替代 `cast(object, None)  # type: ignore[arg-type]`。

## 逐项审查确认

### 1. Protocol 迁移完整性 ✅

| 检查项 | 结果 |
|---|---|
| `ObserverSink.process` 为 async 协议 | ✅ `_event_observer.py:93` — `async def process(...)` |
| `ProjectionCoordinator` 在同一事务内 await observer | ✅ `_event_observer.py:262-271` — `async with self.storage.transaction() as tx: await observer.process(tx=tx, ...) + advance_success(...)` |
| `startup_reconcile` 语义保持 | ✅ 直接委托 `drain()`，未改变 |
| `drain` / `retry` / `blocked` / `caught_up` 语义保持 | ✅ 错误处理路径（`RetryableProjectionError` → `RETRYABLE_FAILED`，其它 → `BLOCKED_FAILED`）未改变 |

### 2. `_run_async` bridge 删除 ✅

| 检查项 | 结果 |
|---|---|
| `_run_async` 函数已删除 | ✅ `_memory_projection.py` diff 显示完整删除（含 thread + new event loop 逻辑） |
| `dayu/host/` 无 `_run_async` 残留 | ✅ grep 确认 |
| `tests/host/` 无 `_run_async` 残留 | ✅ grep 确认 |
| 无 thread + new event loop 桥接 | ✅ `import threading` 和 `asyncio.new_event_loop()` 均已删除 |
| memory observer 直接 await | ✅ `_memory_projection.py:107` — `await self.memory_store.project_run_events(events)` |

### 3. 同事务语义 ✅

| 检查项 | 结果 |
|---|---|
| sink 写入与 checkpoint advance 同事务 | ✅ `_run_once_locked` 中同一 `tx` |
| observer process 抛异常时 checkpoint 不前进 | ✅ 异常路径走 `except` 分支，用独立事务记录 failure，checkpoint 的 `last_success_position` 不变 |
| required observer blocked / retry 语义不变 | ✅ `BLOCKED_FAILED` / `RETRYABLE_FAILED` 路径未改变 |

### 4. Scope 边界 ✅

| 检查项 | 结果 |
|---|---|
| 未引入 observer claim / lease | ✅ |
| 未引入后台 worker / queue | ✅ |
| 未混入 attempt ownership | ✅ |
| 未改 ToolRuntime / AttemptLeaseStore / Engine | ✅ `git diff --name-only` 只涉及 observer、projection、test 和 migration-plan |

### 5. 测试质量 ✅

| 检查项 | 结果 |
|---|---|
| direct `observer.process` 调用全部 await | ✅ `test_phase6_review_fixes.py:651,657` 均为 `await observer.process(...)` |
| projection checkpoint / retry / blocked 测试覆盖 | ✅ `test_phase6_projection_checkpoint.py` — `test_observer_retryable_failure_does_not_advance`, `test_observer_non_retryable_failure_marks_blocked` |
| startup_reconcile 测试 | ✅ `test_phase6_review_fixes.py:test_durable_bundle_startup_reconcile_catches_up_after_crash` |
| tool trace projection 测试 | ✅ `test_phase7_tool_trace_projection.py` — 16 个测试全部从 sync 改为 `async` + `await` |
| memory rebuild 测试 | ✅ `test_phase6_memory_rebuild.py` — 5 个测试从 `asyncio.to_thread(observer.rebuild_from_events, ...)` 改为 `await observer.rebuild_from_events(...)` |
| 无新增 type: ignore / cast 掩盖协议错误 | ✅ 所有 `type: ignore[arg-type]` 均为 P7 遗留 |

### 6. 文档同步 ✅

| 检查项 | 结果 |
|---|---|
| `dayu/host/README.md` 未更新 | ✅ 合理 — README 描述行为契约，不描述 sync/async 签名细节 |
| `docs/host/migration-plan.md` residual tracking | ✅ 已更新为 `accepted: P8-S2 completed / deferred-with-owner: #28/P15`，准确记录 async 升级完成、bridge 删除、observer claim/lease 归 #28/P15 |

## 非阻断残余风险

| 风险 | Owner | 说明 |
|---|---|---|
| async observer IO 在同一 storage transaction 内 await，tool trace JSONL flush 等 sink IO 计入 transaction 持有时间 | issue #28 / P15 | 这是 P8 plan §11 / §20 明确接受的 trade-off，用于删除 `_run_async` bridge。后续 buffered drain / best-effort observer 从 terminal 主路径解耦归 #28 / P15 |
| observer claim / lease 未实现 | #28 / P15 | P8-S2 非目标，plan §11 明确后移 |
