# P8-S8 Gap Fix Code Review：Durable Memory Recovery Repair Path

## 结论

**PASSED**

P8-S8 gap（checkpoint CAUGHT_UP + snapshot row 缺失时 memory 无法恢复）已正确修复。`repair_missing_session_snapshots` 从 EventLog 事实真源重建缺失 snapshot，不引入新 public API，保持 P8 边界。intentional empty snapshot 不被误恢复。smoke S7 输出已改为 `memory_recovered=true recovery_mode=checkpoint_rebuild`。测试覆盖充足。无 blocker。

---

## 1. 审查范围确认

| 检查项 | 结果 |
| --- | --- |
| 新增生产代码 | `dayu/host/_conversation_memory_durable.py` (+180 行 repair 路径) |
| 修改生产代码 | `dayu/host/_durable_harness.py` (+15 行 startup_reconcile 联动) |
| 新增测试 | `tests/host/test_phase8_durable_memory_recovery.py` (+148 行 2 个新测试) |
| 修改 smoke | `utils/smoke_host_p8_attempt_lease.py` (S7 从 gap_confirmed 改为 recovery 成功) |
| 修改文档 | `dayu/host/README.md`、`docs/host/phase8-plan.md`、`docs/host/migration-plan.md` |
| pyright | 0 errors, 0 warnings, 0 informations |
| pytest | 293 passed |
| smoke | 7 行 summary 全部通过 |
| git diff --check | clean |

---

## 2. Root Cause 修复验证

### 2.1 问题根因

P8-S9 smoke 发现：`ProjectionCoordinator.startup_reconcile()` 在 checkpoint 已 CAUGHT_UP 且 EventLog 无新事件时直接返回；若 `host_conversation_memory_snapshots` 中某 session row 丢失，memory read model 无法从 EventLog 重建。

### 2.2 修复方案

`DurableConversationMemoryStore.repair_missing_session_snapshots()` 在 `DurableHarnessBundle.startup_reconcile()` 的 coordinator drain 之后调用：

1. `_collect_missing_session_ids()` 扫描 EventLog 中有 canonical 事件但 snapshot 表无对应 row 的 session。
2. 对缺失 session 分页读取 canonical events（`_fetch_canonical_events_for_session`）。
3. 若含 terminal 事件（`_has_terminal_event`），在事务内调用 `_project_in_tx` 重投。
4. 事务内二次检查 row 是否仍缺失，避免与并发 observer 竞争覆盖。

### 2.3 评估

✅ **Root cause 真正修复**。checkpoint CAUGHT_UP + snapshot row missing 时，`startup_reconcile()` 确实能通过 repair 路径重建 snapshot。修复只依赖 EventLog 事实真源（`host_run_events` 表），不引入新 public API。保持 P8 边界：显式 `DurableHarnessBundle.startup_reconcile()`，没有自动接入 P9 lifecycle/bootstrap。

---

## 3. Repair 语义审查

### 3.1 `_collect_missing_session_ids()` — 缺失 vs intentional empty 区分

```sql
SELECT DISTINCT e.session_id AS session_id
FROM host_run_events AS e
LEFT JOIN host_conversation_memory_snapshots AS s
    ON s.session_id = e.session_id
WHERE e.kind = ? AND s.session_id IS NULL
ORDER BY e.session_id ASC
```

✅ **准确区分**。`LEFT JOIN ... WHERE s.session_id IS NULL` 只返回 snapshot 表中无对应 row 的 session。`MemoryResetPatch` / `ScopeClearPatch(SESSION)` 通过 `apply_patch` 走 UPSERT 写入空 snapshot row，row 仍存在，不会被 `IS NULL` 匹配。测试 `test_startup_reconcile_does_not_overwrite_intentional_empty_snapshot` 覆盖了 MemoryResetPatch 与 ScopeClearPatch(SESSION) 两种场景。

### 3.2 `_fetch_canonical_events_for_session()` — 全局 position 顺序

通过 `event_store.fetch_events_by_position(after=after, limit=256)` 分页拉取，按 global position 升序遍历，过滤 `event.session_id == session_id and event.kind is RunEventKind.CANONICAL`。

✅ **按 global position 顺序取全该 session canonical events**。分页避免单次 SELECT 加载超大 EventLog。

### 3.3 `_has_terminal_event()` — 命名/注释准确性

当前实现只检查 `event.type in TERMINAL_RUN_EVENT_TYPES`。函数名已从 `_has_terminal_or_canonical_fact` 改为 `_has_terminal_event`，准确反映只检查 terminal 的语义。

**Finding 001 [Low]**：函数名暗示检查 terminal 或任意 canonical fact，但实际只检查 terminal。docstring 注释已正确说明"把 `TERMINAL_RUN_EVENT_TYPES` 视为'session 已落定的完整事实'信号"。建议将函数名改为 `_has_terminal_event` 以准确反映语义，或保持当前名但更新注释说明 "canonical_fact" 指 terminal canonical fact。

**影响**：不影响正确性。仅含 `USER_INPUT_ACCEPTED` 但无 terminal 的 session 不被修复是正确行为（session 仍在进行中，等待正常 projection 路径）。

### 3.4 `_project_in_tx()` — 跨 run 顺序 / pending state / terminal grouping

`_project_in_tx` 接收 `tuple[RunEvent, ...]`，内部过滤 canonical 后调用 `_project_canonical_events` 投影。`_project_canonical_events`（来自 `_conversation_memory.py`）是纯函数式投影，按 run_id 分组处理，不依赖外部 pending state。

✅ **适合一次性重投同一 session 多个 run 的 canonical events**。`_project_canonical_events` 内部按 run_id 分组累积，terminal 事件触发整批投影，语义与 `MemoryProjectionObserver.process` 一致。跨 run 顺序由 global position 保证（fetch_events_by_position 按 position 升序）。

### 3.5 并发竞争保护

repair 在 `_lock` 持有下执行；每个 session 的投影在独立事务内执行，事务开始时二次检查 `_snapshot_row_exists_in_tx`：

```python
async with self.storage.transaction() as tx:
    if self._snapshot_row_exists_in_tx(tx=tx, session_id=session_id):
        continue
    self._project_in_tx(tx=tx, events=canonical_events)
```

✅ **足够避免覆盖已写入 snapshot**。二次检查在同一事务内，SQLite `BEGIN IMMEDIATE` 保证事务隔离。与并发 observer 的竞争场景：observer 通过 `project_run_events_in_transaction` 写入 snapshot 时也走同一 SQLite 事务；repair 的二次检查在自己的事务内读取最新 committed state，若 observer 已写入则跳过。

### 3.6 reset/clear 后的 intentional empty snapshot 误恢复

`MemoryResetPatch` / `ScopeClearPatch(SESSION)` 通过 `_write_snapshot` UPSERT 写入空 snapshot row。row 仍存在于 `host_conversation_memory_snapshots` 表中，`_collect_missing_session_ids` 的 `LEFT JOIN ... IS NULL` 不会匹配。

✅ **不会误恢复**。测试 `test_startup_reconcile_does_not_overwrite_intentional_empty_snapshot` 覆盖了：
- drain → MemoryResetPatch → startup_reconcile → 仍为空
- drain → 新事件 → drain → ScopeClearPatch(SESSION) → startup_reconcile → 仍为空

---

## 4. 架构边界 / 类型约束

### 4.1 `DurableRunEventStore` 具体类型依赖

`repair_missing_session_snapshots(event_store: DurableRunEventStore)` 参数类型为具体类 `DurableRunEventStore`，而非 Protocol。

✅ **合理**。`DurableConversationMemoryStore` 本身就是 Host internal durable 实现，依赖 `DurableRunEventStore` 具体类型是自然的。不需要为 repair 路径单独抽 Protocol——repair 是 Host 内部治理能力，不是 public contract。按当前 S8 scope 判断，不过度设计。

### 4.2 `isinstance(self.memory_store, DurableConversationMemoryStore)` 类型检查

`DurableHarnessBundle.startup_reconcile()` 中：

```python
if isinstance(self.memory_store, DurableConversationMemoryStore):
    await self.memory_store.repair_missing_session_snapshots(
        event_store=self.event_store
    )
```

✅ **合理**。当装配的 memory store 不是 `DurableConversationMemoryStore` 时不触发 repair（自定义 store 的恢复语义由 store 自己负责）。这是显式类型守卫，不是逃避类型设计。按当前 S8 scope，不需要抽 `RepairableMemoryStore` Protocol——repair 是 `DurableConversationMemoryStore` 的内部能力，不是通用协议。

### 4.3 AGENTS.md 编码约束合规

| 检查项 | 结果 |
| --- | --- |
| `Any` / `object` / 无类型签名 | 未发现 |
| lazy import / glue seam | 未发现 |
| `hasattr` / `getattr` | 未发现 |
| 兼容 wrapper / re-export | 未发现 |
| 魔法字符串/数字 | `_REPAIR_FETCH_BATCH_LIMIT: int = 256` 为模块级常量，合理 |
| 中文 docstring | ✅ 所有新增函数均有完整中文 docstring，包含参数、返回值、异常 |
| 模块级私有辅助函数 | ✅ `_collect_missing_session_ids`、`_fetch_canonical_events_for_session`、`_has_terminal_event`、`_snapshot_row_exists_in_tx` 均为模块级私有方法 |

---

## 5. 性能与可观测风险

### 5.1 repair 全表扫描 / O(S*N) 成本

`_collect_missing_session_ids` 执行 `SELECT DISTINCT ... FROM host_run_events LEFT JOIN host_conversation_memory_snapshots`，对 EventLog 全表扫描。`_fetch_canonical_events_for_session` 对每个缺失 session 分页遍历全量 EventLog（`fetch_events_by_position` 按 global position 分页，非按 session_id 索引）。

**成本分析**：若有 S 个缺失 session、EventLog 共 N 条事件，repair 复杂度为 O(N) 扫描 + O(S*N) 分页读取。在 EventLog 规模小（P8 阶段典型场景）时可接受；大规模生产环境可能需要 `host_run_events.session_id` 索引优化。

✅ **可接受 residual risk**。文档已记录 owner：P9 / 容量评估。

### 5.2 敏感信息泄露

DEBUG 日志输出：
- `host.conversation_memory.durable_repaired session_id=smoke_p8_session canonical_count=2` — session_id 为诊断信息，不构成安全风险。
- 不打印 prompt、tool result、owner token、scope token。

✅ **安全**。

### 5.3 smoke 输出安全

S7 输出：`[s7] checkpoint_caught_up=True snapshot_deleted=True memory_recovered=True recovery_mode=checkpoint_rebuild`

✅ **无敏感信息**。session_id 在 summary 中未出现（只在 DEBUG log 中出现）。

---

## 6. 测试覆盖

### 6.1 `test_startup_reconcile_repairs_snapshot_when_checkpoint_caught_up_and_row_missing`

场景：文件 SQLite → append USER_INPUT_ACCEPTED + FINAL_ANSWER → drain（checkpoint CAUGHT_UP + snapshot 已写入）→ DELETE snapshot row → 重新装配 → startup_reconcile → 验证 snapshot 恢复 → 重复 startup_reconcile 幂等。

✅ **真实复现旧 gap**。直接删除 snapshot row 模拟 read model 丢失，checkpoint 已 CAUGHT_UP 使普通 drain 不再重投。验证 repair 路径从 EventLog 重建，且幂等不破坏已恢复 snapshot。

### 6.2 `test_startup_reconcile_does_not_overwrite_intentional_empty_snapshot`

场景：文件 SQLite → append + drain → MemoryResetPatch → startup_reconcile → 仍为空 → 再 append + drain → ScopeClearPatch(SESSION) → startup_reconcile → 仍为空。

✅ **覆盖 MemoryResetPatch 与 ScopeClearPatch(SESSION)**。两种 patch 写入的空 snapshot row 不被 repair 误恢复。

### 6.3 是否还需要额外覆盖

| 场景 | 是否需要 | 理由 |
| --- | --- | --- |
| 多 session 同时缺失 | 可选 | `_collect_missing_session_ids` 返回所有缺失 session，逻辑对多 session 天然支持 |
| active run only（无 terminal） | ✅ 已隐含覆盖 | `_has_terminal_event` 检查 terminal，无 terminal 的 session 不被修复 |
| no terminal session 不被误修复 | ✅ 已隐含覆盖 | 同上 |

当前测试覆盖足够。

---

## 7. 文档同步审查

### 7.1 `dayu/host/README.md`

✅ 已更新。新增段落描述 `startup_reconcile` 在 coordinator drain 后调用 `repair_missing_session_snapshots`，说明 checkpoint CAUGHT_UP + snapshot row 缺失时的 repair 路径、intentional empty snapshot 不被误恢复、EventLog 仍是事实真源。只写当前已落地事实，未写 P9 lifecycle / public memory API。

### 7.2 `docs/host/phase8-plan.md`

✅ 已更新。§15 场景 7 文案改为 `checkpoint_caught_up=true snapshot_deleted=true memory_recovered=true recovery_mode=checkpoint_rebuild`，匹配 smoke 实现。

### 7.3 `docs/host/migration-plan.md`

✅ 已更新。§4.4 P8 残余风险追踪中 P8-S8 状态从 `deferred` 改为 `resolved: P8-S8`，描述 durable memory repair 路径已落地。

### 7.4 `docs/host/phase8-s9-code-review.md`

⚠️ **Finding 002 [Low]**：Finding 003 的修复状态当前写为 `accepted (re-reviewed after P8-S8 gap fix)`，但正文描述仍保留 "gap demonstrated" 措辞。建议更新 Finding 003 标题为 `fixed`，正文描述对齐当前 repair 路径已落地的事实。不阻塞 commit，可在 P8-S10 文档收口时一并更新。**已修复**：Finding 003 标题/状态/措辞已对齐为 `fixed`，正文反映 gap 已修复事实。

---

## 8. Residual Risks 与 Owner

| 风险 | Owner | 状态 |
| --- | --- | --- |
| repair 全表扫描 / 大 EventLog 延迟 | P9 / 容量评估 | `deferred` |
| `AttemptSupervisor.recover_stale_attempts` 自动 wire 进 production startup lifecycle | P9 / Session lifecycle | `deferred` |
| 多进程同时 `startup_reconcile` stress | GitHub issue #38 | `deferred` |
| 自定义 non-durable memory store 恢复语义 | 调用方 | N/A（isinstance 守卫明确跳过） |
| `phase8-s9-code-review.md` Finding 003 标题/措辞对齐 | P8-S8 cleanup | `fixed` |

---

## 9. Gate 建议

**允许 commit**。P8-S8 gap 已正确修复：

- Root cause 真正修复：checkpoint CAUGHT_UP + snapshot row missing 时，`startup_reconcile()` 通过 repair 路径从 EventLog 重建 snapshot。
- Repair 语义正确：intentional empty snapshot 不被误恢复；事务内二次检查避免并发竞争；按 global position 顺序重投。
- 架构边界清晰：不引入新 public API；`isinstance` 类型守卫合理；保持 P8 边界。
- 测试覆盖充足：2 个新测试覆盖 repair 重建与 intentional empty 不误恢复。
- 文档同步：README、phase plan、migration plan 均已更新为当前事实。
- 性能 residual risk 已记录 owner。

建议后续进入 fix / re-review / user confirmation gate。

---

## 10. Findings Summary

| # | 严重度 | 文件 | 描述 | 状态 |
| --- | --- | --- | --- | --- |
| 001 | Low | `_conversation_memory_durable.py:363` | ~~`_has_terminal_or_canonical_fact` 函数名暗示检查 terminal 或任意 canonical fact，实际只检查 terminal~~ 已重命名为 `_has_terminal_event` | `fixed` |
| 002 | Low | `phase8-s9-code-review.md` | ~~Finding 003 标题/措辞未对齐 repair 已落地的事实~~ 已对齐 | `fixed` |
