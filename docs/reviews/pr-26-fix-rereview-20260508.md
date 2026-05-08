# PR #26 P6 Review Fixes 复审报告

- **复审日期**: 2026-05-08
- **复审范围**: `docs/reviews/pr-26-review-20260508-1717.md` 与 `docs/reviews/pr-26-review-20260508-1804.md` 所列 finding 的本轮修复
- **分支**: `migration/host-p6-durable-eventlog`

---

## 结论：有条件通过

所有 P0 / P1 / P2(P4) / P3(P7) 修复均已验证通过，测试覆盖充分，pyright / pytest / smoke 均绿。存在 1 项元数据修正需求（1804 review 文档 Scope 中 output file 路径错误），不影响代码正确性但影响迁移审计记录一致性。

---

## P0 修复核验

**Finding 1717-F1：Memory observer `process()` sink 失败导致 `_pending_by_run` 状态不可恢复**

修复方式：将 `_pending_by_run.pop` 移到 sink 成功之后。`_memory_projection.py:92-116` 采用 staged 副本策略：

1. L92-95：从 `_pending_by_run` 深拷贝到 `staged`。
2. L97-110：逐事件累积到 `staged`，遇到 terminal 时调用 `_run_async(memory_store.project_run_events(...))`。
3. L114：全部 sink 成功后才把 `staged` 写回 `_pending_by_run`。
4. L115-116：terminal 成功投影后才 pop 对应 run 条目。

关键不变量成立：若 `_run_async` 抛异常，控制流不达 L114，`_pending_by_run` 维持调用前的累积视图，checkpoint 不前进，下次 drain 重放同一 batch 时 observer 能重新累积并投影。

**测试覆盖**：`test_memory_observer_sink_failure_preserves_pending_for_replay`（L538-666）使用 `_FlakyMemoryStore(fail_times=1)` 验证：
- 第一次 sink 失败后 `other_run` 仍在 `_pending_by_run` 中（L653）。
- 第二次重放成功，projected 包含 `USER_INPUT_ACCEPTED` + `FINAL_ANSWER`（L660-662）。
- terminal 投影成功后 `rX` 从 `_pending_by_run` 清除（L664）。

**结论：P0 修复通过。**

---

## P1 修复核验

**Finding 1717-F2：进程崩溃后 read model 无法自动恢复**

修复方式：`DurableHarnessBundle.startup_reconcile()`（`_durable_harness.py:76-90`）委派 `ProjectionCoordinator.startup_reconcile()`（`_event_observer.py:146-161`），后者直接调用 `self.drain()`。

Docstring 语义准确：
- `DurableHarnessBundle.startup_reconcile` L77-88：明确说明"Host durable 装配在构造完成时调用本方法"，"调用方负责在自己的 async 上下文内 `await bundle.startup_reconcile()`"。
- `ProjectionCoordinator.startup_reconcile` L146-161：明确说明"Host durable 装配（`build_durable_harness`）在构造完成时调用本方法"。

**没有暗示 `build_durable_harness()` 自动调用**。`build_durable_harness` 是同步函数，不 await；`startup_reconcile` 是独立显式入口，由调用方在 async 上下文中调用。

**README 已同步**（`dayu/host/README.md` L282-286）：明确写出"重启后调用方需要在自己的 async 上下文内 `await bundle.startup_reconcile()`"。

**migration-plan 已登记残余风险**（L288-293）：`deferred-with-owner: P9`：`startup_reconcile` 进入 Host 启动流程，P9 落地时收进 bootstrap。

**测试覆盖**：`test_durable_bundle_startup_reconcile_catches_up_after_crash`（L670-708）模拟"写入 terminal run 但不 drain"场景，验证 `startup_reconcile` 后 memory snapshot 非空。

**结论：P1 修复通过。**

---

## HostStorage 封装核验

**Finding 1717-F4 / 1804-F1：`storage._connection` 直接访问**

修复方式：
- `ensure_host_schema`（`_durable_event_store.py:148-159`）改为 `storage.apply_schema(_SCHEMA_STATEMENTS)`。
- `open_durable_event_store`（`_durable_event_store.py:771-780`）改为 `storage.open()` + 构造 store。
- `HostStorage.open()`（`_host_storage_transaction.py:133-154`）内部统一配置 `row_factory = sqlite3.Row`。
- `HostStorage.apply_schema()`（`_host_storage_transaction.py:233-260`）在 `_connection_lock` 内串行执行 DDL。

**生产代码中不再有 `storage._connection` 或 `noqa: SLF001`**。grep 确认：`_durable_event_store.py`、`_run_harness.py`、`_memory_projection.py`、`_event_observer.py`、`_host_storage_transaction.py` 均无 `storage._connection` 或 `noqa: SLF001`。测试文件中的 `noqa: SLF001` 用于访问 observer 内部状态以验证不变量，属于合理测试用法。

**结论：HostStorage 封装修复通过。**

---

## `_finish_attempt_if_durable` 参数互斥核验

**Finding 1717-F7：声称参数互斥但不校验**

修复方式：`_run_harness.py:1120-1124` 增加显式校验：
```python
if terminal_event is not None and state is not None:
    raise ValueError(
        "_finish_attempt_if_durable 不允许同时传入 terminal_event "
        "与 state；二者互斥，调用方需明确终态来源。"
    )
```

**测试覆盖**：`test_finish_attempt_if_durable_rejects_terminal_event_and_state_together`（L712-742）验证同时传入时抛 `ValueError`。

**现有调用方未被误伤**：`_run_to_store` 中所有调用点要么传 `terminal_event`（L488-491），要么传 `state`（L525-529, L536-541），要么两者都不传（L566-579），不存在同时传入的路径。

**结论：参数互斥修复通过。**

---

## Review 文档标注状态复核

### `docs/reviews/pr-26-review-20260508-1717.md`

| Finding | 标题 | 标注状态 | 复核 |
|---------|------|----------|------|
| F1 | P0：Memory observer `process()` sink 失败导致 `_pending_by_run` 状态不可恢复 | [已修复] | 正确 |
| F2 | P1：进程崩溃后 read model 无法自动恢复 | [已修复] | 正确 |
| F3 | P2：`_run_async` sync-async bridge | [后移-P7/P8] | 正确 |
| F4 | P2：`storage._connection` 直接访问 | [已修复] | 正确 |
| F5 | P3：isinstance chain | [后移-P7] | 正确 |
| F6 | P3：sink 失败路径无测试覆盖 | [已修复] | 正确 |
| F7 | P3：`_finish_attempt_if_durable` 参数不校验 | [已修复] | 正确 |

### `docs/reviews/pr-26-review-20260508-1804.md`

| Finding | 标题 | 标注状态 | 复核 |
|---------|------|----------|------|
| F1 | `ensure_host_schema` / `_configure_row_factory` 绕过封装 | [已修复] | 正确 |
| F2 | `_begin_attempt_if_durable` INSERT + UPDATE 两步 | [无需修复-说明] | 正确 |
| F3 | `_upsert_run_state` 首条 terminal 两步 | [无需修复-说明] | 正确 |
| F4 | observer 无事件时跳过 CAUGHT_UP | [后移-P15 deferred-with-owner] | 正确 |

**1804 文档 Scope 元数据问题**：L8 写 `Output file: docs/reviews/pr-26-review-20260508-1630.md`，但实际文件名为 `pr-26-review-20260508-1804.md`。这是元数据错误，会导致迁移审计记录中 review 输出路径与实际文件不一致。**需要修正为 `docs/reviews/pr-26-review-20260508-1804.md`**。

---

## 残余风险 owner 复核

| 残余风险 | migration-plan 登记 | owner | 状态 |
|----------|---------------------|-------|------|
| `_run_async` sync-async bridge | L282-287 | P7/P8 | 已登记 |
| observer 空 EventLog `CAUGHT_UP` | L276-281 | P15 | 已登记 |
| 多进程 stress / lease / fencing | L266-272 | P8 | 已登记 |
| `startup_reconcile` 进入 Host 启动流程 | L288-293 | P9 | 已登记 |
| schema bootstrap 半失败治理 | L273-275 | P15 | 已登记 |
| `InMemoryRunEventStore` 收口 | L305-308 | P16 | 已登记 |

本轮修复没有偷做或误称完成 P8 / P15 / P16 范围的能力。

---

## 新发现问题

### N1 — 低 — 1804 review 文档 Scope output file 元数据错误

- **文件**: `docs/reviews/pr-26-review-20260508-1804.md:8`
- **问题**: Scope 中 `Output file` 写 `docs/reviews/pr-26-review-20260508-1630.md`，但实际文件名是 `pr-26-review-20260508-1804.md`。推测是 review Agent 复制了上一轮 review 的 output file 模板未更新。
- **影响**: 迁移审计记录中 review 输出路径与实际文件不一致，不影响代码正确性。
- **建议**: 修正为 `docs/reviews/pr-26-review-20260508-1804.md`。

---

## 验证命令结果

| 命令 | 结果 |
|------|------|
| `pyright dayu/host tests/host utils/smoke_host_p6_durable_eventlog.py` | 0 errors, 0 warnings, 0 informations |
| `pytest tests/host` | 192 passed in 0.50s |
| `python utils/smoke_host_p6_durable_eventlog.py` | 正常输出，所有 observer caught_up，memory/timeline/read model 正确 |
| `git diff --check` | 无输出（无 whitespace 错误） |

---

## 总结

本轮 PR review fixes 修复了全部标记为 [已修复] 的 finding（1717-F1/F2/F4/F6/F7，1804-F1），修复语义正确、测试覆盖充分、README 与 migration-plan 同步到位。唯一待修正项是 1804 review 文档 Scope 中的 output file 元数据路径。

## 总控补充

复审后总控核对发现 `ProjectionCoordinator.startup_reconcile()` docstring 仍有一句容易误读为
`build_durable_harness()` 构造完成时自动调用恢复入口。该表述与 P6 固定口径不一致：P6 只提供
显式 `await bundle.startup_reconcile()` 入口，P9 再把它收进 Host 启动 / bootstrap。总控已将该
docstring 修正为“Host durable 装配完成后，调用方必须在自己的 async 上下文中显式 await 本方法”，
不涉及运行逻辑变化。
