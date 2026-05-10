# PR #40 ToolRuntime Durability 调查

**调查日期**: 2026-05-10
**调查范围**: `InMemoryToolRuntime` 在 P8 durable harness 中的生产治理口径
**结论**: 不是 P8 blocker；架构正确，命名误导；推荐 P8 内最小改名 + 文档澄清，不抽 durable cursor store

---

## 1. Executive Conclusion

`InMemoryToolRuntime` 在 `build_durable_harness()` 中装配时（`is_durable=True`），**所有 canonical fact 写入均通过 `AttemptScopedRunEventAppender` → `verify_owner` + SQLite `BEGIN IMMEDIATE` 事务原子落库**，fact 耐久性已由 P8-S5 完整覆盖。`InMemory` 仅指 cursor registry（`_records_by_cursor` / `_cursor_by_fingerprint`）是进程内 transient state，这是**有意设计**而非耐久性缺口。

**与 `InMemoryConversationMemoryStore` 不同类**：后者是 required projection read model，跨 Run 持久化是其正确性条件；前者 cursor registry 是单次 tool call 内的分页协调状态，TTL 限定（默认 300s），进程崩溃后 cursor 丢失是正常的 Run 终态路径，不等于 fact 丢失。

**不需要在 PR #40 merge 前修生产代码**。推荐方案：P8 内做最小改名（`InMemoryToolRuntime` → `HostToolRuntime`），消除"durable harness 装配 InMemory 实现"的字面矛盾；cursor registry 的 transient 设计在 docstring 中显式说明。不做兼容 alias，不抽 durable cursor store，不改变行为。

---

## 2. Code Evidence

### 2.1 durable harness 装配路径

`build_durable_harness()` (`_durable_harness.py:248-252`):

```python
runtime = InMemoryToolRuntime(
    is_durable=True,
    executor=actual_executor,
    event_store=event_store,
)
```

关键：`is_durable=True` 改变了 `_resolve_appender()` 的行为。

### 2.2 `_resolve_appender()` 的分派逻辑

`_tool_runtime.py:371-397`:

```python
def _resolve_appender(self) -> ToolRuntimeEventAppender:
    active = _ACTIVE_TOOL_RUNTIME_APPENDER.get()
    if self.is_durable:
        if active is None:
            raise RuntimeError(
                "durable runtime requires ToolRuntimeOwnerScope for "
                "attempt-scoped append"
            )
        return active
    if active is not None:
        return active
    return PlainRunEventAppender(event_store=self.event_store)
```

- `is_durable=True`: 必须从 ContextVar 中读到 `AttemptScopedRunEventAppender`；缺失 → `RuntimeError` fail fast，**永不退化为 PlainRunEventAppender**
- `is_durable=False` (test-only): ContextVar 缺失时退化为 `PlainRunEventAppender`（直接 `event_store.append`，无 owner 校验）

### 2.3 attempt-scoped append 覆盖

`_run_harness.py:895`:

```python
async with self._attempt_owner_scope(current_active_attempt):
    # 在此 scope 内，ToolRuntime 所有 fact append 都走
    # AttemptScopedRunEventAppender → verify_owner + BEGIN IMMEDIATE
```

`_attempt_owner_scope()` (`_run_harness.py:617-648`) 在有 supervisor + owner_context 时返回 `ToolRuntimeOwnerScope(scoped_appender)`，将绑定 owner 的 `AttemptScopedRunEventAppender` 注入 ContextVar。

### 2.4 7 个 fact append 方法全部走 `_resolve_appender()`

`_tool_runtime.py` 中所有 `_append_*` 方法（行 1154-1391）均通过 `self._resolve_appender().append(draft)` 写入：
- `_append_tool_result_truncated` (L1172)
- `_append_cursor_issued` (L1217)
- `_append_fetch_requested` (L1249)
- `_append_fetch_completed` (L1292)
- `_append_cursor_expired` (L1338)
- `_append_cursor_denied` (L1373)
- `_append_fetch_failure` → `_append_fetch_failed` (L1414)

**durable 路径下，这 7 种 fact 全部经过 owner fencing + SQLite 事务原子落库。**

---

## 3. In-Memory State Inventory

### 3.1 进程内状态字段

| 字段 | 类型 | 用途 | 跨进程必需？ | 丢失影响 | EventLog 可重建？ |
|------|------|------|-------------|---------|------------------|
| `_records_by_cursor` | `dict[str, _CursorRecord]` | cursor→record 主索引 | 否 | fetch_more 不可继续 | 不可——data 是原始工具结果全文，不入 EventLog |
| `_cursor_by_fingerprint` | `dict[str, str]` | fingerprint→cursor 辅助索引 | 否 | 同 _records_by_cursor | 不可——fingerprint→cursor 映射不入 EventLog |
| `_fetch_lock` | `asyncio.Lock` | 单实例内串行化 fetch_more | 否 | 无影响（新实例新锁） | 不适用 |
| `executor` | `ToolExecutor` | 底层业务工具调用 | 否 | 工具不可执行 | 不适用——装配注入 |
| `truncate_specs` | `Mapping[str, ToolTruncateSpec]` | 按工具名截断声明 | 否 | 截断不生效 | 不适用——装配注入 |
| `event_store` | `RunEventStore` | terminal cursor 检测 + PlainRunEventAppender fallback | 否 | durable 路径不用 fallback | 不适用——装配注入 |
| `clock` | `_Clock` | monotonic clock | 否 | TTL 计算失效 | 不适用——注入 |
| `token_generator` | `_TokenGenerator` | cursor 原文生成 | 否 | 新 cursor 无法创建 | 不适用——注入 |

### 3.2 `_CursorRecord` 内容分析

| 字段 | 跨进程必需？ | 说明 |
|------|-------------|------|
| `cursor`, `cursor_fingerprint`, `scope_token`, `scope_hash` | 否 | 单次 tool call 内的临时凭证，TTL ≤ 300s |
| `session_id`, `run_id`, `tool_call_id`, `tool_name` | 可从 EventLog 重建 | EventLog fact 中包含 tool_call_id / cursor_fingerprint / scope_hash |
| `strategy`, `unit`, `limit`, `total` | 可从 EventLog 重建 | `TOOL_CURSOR_ISSUED` / `TOOL_RESULT_TRUNCATED` 包含这些字段 |
| `data` | **不可重建** | 原始工具结果全文（可能超大——正是截断的原因） |
| `offset` | 可从 EventLog 推导 | `TOOL_CURSOR_ISSUED.offset` |
| `template`, `field_path` | **不可重建** | wrapper 模板和字段路径，不入 EventLog |
| `created_at_monotonic`, `expires_at_monotonic`, `ttl_seconds` | 可从 EventLog 推导 | `TOOL_CURSOR_ISSUED` 包含 `expires_at_monotonic` / `ttl_seconds` |
| `parent_cursor_fingerprint` | 可从 EventLog 推导 | `TOOL_CURSOR_ISSUED.parent_cursor_fingerprint` |

**核心发现**：`data`（原始工具结果全文）和 `template`（wrapper 模板）不可从 EventLog 重建，这是 cursor registry 无法被 EventLog replay 替代的根本原因。将 `data` 持久化意味着把可能超大的工具结果原文写入 SQLite——这正是截断机制试图避免的事情。

---

## 4. Failure Modes

### 4.1 进程崩溃时间窗口分析

#### 窗口 A：cursor 已创建，ToolRuntime facts 未 append
- 状态：`_CursorRecord` 在内存，`TOOL_RESULT_TRUNCATED` / `TOOL_CURSOR_ISSUED` 未写
- 影响：Run 无截断事实，Engine 未收到 truncated tool result
- 恢复：Run 进入 terminal（LOST/FAILED via owner lease expiry recovery scan），Service 层新 `StartRunRequest` 重新执行

#### 窗口 B：`TOOL_RESULT_TRUNCATED` / `TOOL_CURSOR_ISSUED` 已写，模型已收到 scope_token/cursor
- 状态：EventLog 有截断事实，cursor 在内存
- 影响：模型可能发起 `fetch_more(cursor, scope_token)` 
- **如果在 fetch_more 之前崩溃**：重启后 cursor 丢失，模型调用 `fetch_more` → `cursor_not_found` → 不写 EventLog → 模型收到 typed failure
- 恢复：当前 attempt 因 owner lease 过期被 recovery scan 收为 LOST；Service 层新 Run 重新执行

#### 窗口 C：`TOOL_FETCH_MORE_REQUESTED` 已写，`TOOL_FETCH_MORE_COMPLETED` 未写
- 状态：EventLog 有 "requested"，cursor record 在内存（尚未被 `_remove_cursor`）
- **崩溃**：cursor record 丢失
- 影响：EventLog 有 "requested" 但没有 "completed"，是一个悬空事实
- 恢复：同窗口 B，Run 终态后悬空 "requested" 不影响 replay

#### 窗口 D：`TOOL_FETCH_MORE_COMPLETED` 已写（含 `next_cursor_fingerprint`），新 cursor 已入 registry
- 状态：EventLog 完整，新 cursor 在内存，旧 cursor 已删除
- **崩溃**：新 cursor record 丢失
- 影响：模型拿到 `has_more=True` + 新 cursor/scope_token，但 cursor 已丢失；下次 `fetch_more` → `cursor_not_found`
- 恢复：同窗口 B

#### 窗口 E：`_fetch_more` 中 EventLog append 成功，但 `_remove_cursor(record.cursor)` 之前崩溃
- `_tool_runtime.py:847-853` 有 fencing error 回滚逻辑：
  ```python
  except AttemptFencingError:
      if pending_cursor_creation is not None:
          self._remove_cursor(pending_cursor_creation.record.cursor)
      raise
  ```
- 注意：**只有 `AttemptFencingError` 会回滚内存状态，普通崩溃不会**
- 影响：旧 cursor 未被 `_remove_cursor`，新 cursor 丢失；重启后旧 cursor 可能仍可用（如果有某种方式恢复内存）

### 4.2 与 EventLog 的原子性分析

**fetch_more 不是 EventLog 原子操作**：

```text
append TOOL_FETCH_MORE_REQUESTED   ← EventLog fact 1
compute chunk                      ← 纯内存
append TOOL_FETCH_MORE_COMPLETED   ← EventLog fact 2
  (可能) append TOOL_CURSOR_ISSUED ← EventLog fact 3 (has_more 时)
remove old cursor                  ← 纯内存 (仅在 append 成功后)
```

在 fact 1 和 fact 2 之间崩溃 → EventLog 有悬空 "requested"。这是 **已知设计取舍**，不是 bug。cursor 的 TTL 机制保证了悬空状态是临时的。

### 4.3 与 P8 fencing 的交互

`_fetch_more` 中的关键保护 (`_tool_runtime.py:847-853`)：

```python
try:
    completed_event = await self._append_fetch_completed(...)
    if next_issued_event is not None:
        await self._append_cursor_issued(...)
except AttemptFencingError:
    if pending_cursor_creation is not None:
        self._remove_cursor(pending_cursor_creation.record.cursor)
    raise
```

- Owner fencing 保护了：不会向已 fenced 的 attempt 写入 fact
- 回滚了：fencing error 时移除已创建但未写入 fact 的新 cursor
- **未保护**：`_append_fetch_completed` 成功但 `_append_cursor_issued` 失败时的中间状态（两者在独立事务中，不在同一 `BEGIN IMMEDIATE`）

这实际上是一个比 cursor registry 耐久性更实际的 gap：**fetch_more 的 completed fact 和 next cursor issued fact 不在同一事务中**。但这不改变结论——在一个 attempt 内，这两个 fact 都由同一 owner 在同一 lease 内写入，且 cursor 的 TTL 提供了时间窗口保护。

---

## 5. 与 `InMemoryConversationMemoryStore` 对比

| 维度 | `InMemoryConversationMemoryStore` (P8-S8 前) | `InMemoryToolRuntime` (当前) |
|------|---------------------------------------------|---------------------------|
| 职责 | Session memory read model projection | Tool call cursor coordination |
| 生命周期 | 跨 Run，Session 级 | 单 tool call 内，≤ TTL (300s) |
| 数据量 | 所有 session canonical facts 的聚合视图 | 单个工具调用的原始结果数据 |
| 持久化需求 | **必须**——进程重启后 memory 必须恢复 | **不必**——cursor 丢失=Run 终态，新 Run 重新执行 |
| 丢失影响 | Session 连续性问题，用户看到"失忆" | 单次 `fetch_more` 不可用，Run 终态 |
| EventLog 可重建？ | **是**——canonical facts 全在 EventLog | **部分**——原始数据 `data` 和 `template` 不在 EventLog |
| P8 替换方案 | `DurableConversationMemoryStore` (SQLite) | 无等效 durable 替换（cursor data 太大，入 SQLite 不合理） |

**结论**：两者不同类。`InMemoryConversationMemoryStore` 是 read model 应该 durable；`InMemoryToolRuntime` 的 cursor registry 是 transient coordination state，无需 durable。

---

## 6. Phase Ownership

### 6.1 P8 不是必须关闭这个问题

P8 的 scope 是 attempt lease / fencing / recovery / terminal atomic close / attempt-scoped append。ToolRuntime fact 的 durable append 已由 P8-S5 完整覆盖。Cursor registry 的 transient 设计不违反 P8 的验收条件。

### 6.2 Residual Risk 归属

| Risk | Owner | 原因 |
|------|-------|------|
| `InMemoryToolRuntime` 命名误导 | **P8（推荐）** 或 P16 | 纯改名，P8 内可完成；若 P8 不修，P16 interface freeze 必须收口 |
| fetch_more 中 `TOOL_FETCH_MORE_COMPLETED` 和 `TOOL_CURSOR_ISSUED` 不在同一事务 | P10 或 P16 | 当前被 cursor TTL 保护；若 P10 引入长 TTL cursor，需要评估 |
| cursor data (`_CursorRecord.data`) 无法从 EventLog 重建 | **无需修** | 原始数据太大，不应该入 SQLite；cursor TTL 已提供保护 |
| 进程崩溃后 cursor 丢失导致模型 `fetch_more` 失败 | **无需修** | 这是已知的 transient failure mode，Run 终态 + Service 重试是正确恢复路径 |
| `_fetch_more` 中 `_append_fetch_completed` 成功但 `_remove_cursor` 前崩溃 | **无需修** | 旧 cursor 的 TTL 会自动清理；旧 cursor 被"重复消费"是安全操作（at-least-once 语义） |

### 6.3 为什么 P10 比 P9 更适合

- P9 是 Session/Run lifecycle governance——不涉及 tool 内部机制
- P10 是 ToolRegistry governance——届时可能需要重新审视 cursor 的超时、scope、audit
- P10 引入长时运行工具时，cursor TTL 可能需要延长，届时再评估是否抽 durable cursor store
- P16 interface freeze 时最终确认命名和契约

---

## 7. Recommended Path

### 方案 A（推荐）：P8 内最小改名 `InMemoryToolRuntime` → `HostToolRuntime`

**改动范围**：
- `dayu/host/_tool_runtime.py`：类名 `InMemoryToolRuntime` → `HostToolRuntime`，更新 docstring 显式说明 cursor registry 是 transient state
- `dayu/host/_run_harness.py`：import 和类型标注更新（4 处）
- `dayu/host/_durable_harness.py`：import 更新（3 处）
- `dayu/host/README.md`：术语刷新（约 8 处提及 `InMemoryToolRuntime`）
- 测试文件：import 更新（约 10 处）
- **不做**兼容 alias、wrapper、re-export

**测试范围**：无需新增测试——纯改名，现有测试验证行为不变

**风险**：极低——不改行为，只改名字

**说明**：`HostToolRuntime` 表达了"这是 Host 拥有的 ToolRuntime"，与 `ToolRuntimeToolExecutor` 的 Host-owned 语义对齐。`InMemory` 前缀被移除因为：
1. durable 路径下 fact append 是耐久化的，不是 in-memory
2. cursor registry 的 transient 性是设计特性，不是实现缺陷
3. "InMemory" 在 durable context 中制造了不必要的认知负担

### 方案 B：P8 内抽 `ToolCursorStore`，实现 durable cursor store

**不推荐**。原因：

1. **data 持久化问题**：`_CursorRecord.data` 是原始工具结果全文，可能数 MB 级别，写入 SQLite 会极大膨胀 EventLog 体积，且违反截断机制的设计初衷（避免大结果占用存储）
2. **schema 设计**：需要 cursor TTL 清理、过期索引、跨进程并发控制——这是非平凡的新 schema
3. **事务原子性**：cursor store 写与 EventLog fact append 需要同事务——把大 blob 写入放在同一 `BEGIN IMMEDIATE` 事务中会增加锁竞争
4. **提前实现 P10**：durable cursor store 暗示了 ToolRegistry 级的状态管理，会提前扩大 P8 scope
5. **ROI 低**：cursor 丢失的恢复路径已是明确的（Run 终态 → Service 重试），durable cursor 增加的恢复能力有限

### 方案 C：保持 P8 不改生产代码，仅文档明确

**仅在以下条件成立时可选**：
- PR #40 需要立即 merge，不允许任何附加改动
- P16 interface freeze 承诺收口命名问题

**风险**：
- `InMemoryToolRuntime` 继续在 durable harness 中出现，造成持续的认知负担
- P16 时间线不确定，可能长期残留

### 方案 D（不推荐）：仅文档澄清，不改名

在 `dayu/host/README.md` 和 `_tool_runtime.py` docstring 中说明 cursor registry 是 transient，事实耐久性不受影响。不做代码改动。

**风险**：文档澄清是合理的，但名字仍是误导的，"durable harness 装配 InMemory 实现"的字面矛盾不解决，未来贡献者和 reviewer 会反复质疑同一问题。

---

## 8. 如果采纳方案 A，handoff-ready implementation prompt

```
Task: 在 P8 内将 InMemoryToolRuntime 改名为 HostToolRuntime

背景：
build_durable_harness() 中装配 InMemoryToolRuntime(is_durable=True)，
所有 canonical fact 写入已在 P8-S5 通过 AttemptScopedRunEventAppender 耐久化。
InMemory 仅指 cursor registry 是 transient state（TTL 限定，单 tool call 内有效），
但类名在 durable context 中造成"生产路径依赖 in-memory 实现"的误解。

改动：
1. dayu/host/_tool_runtime.py:
   - class InMemoryToolRuntime → class HostToolRuntime
   - 更新类 docstring：显式说明 cursor registry 是 transient coordination state，
     fact durability 由 ToolRuntimeEventAppender 保证
   - 更新模块 docstring 中的引用
2. dayu/host/_run_harness.py:
   - 所有 InMemoryToolRuntime import 和类型标注 → HostToolRuntime
3. dayu/host/_durable_harness.py:
   - 所有 InMemoryToolRuntime import → HostToolRuntime
4. dayu/host/README.md:
   - 所有 InMemoryToolRuntime 引用 → HostToolRuntime
5. 测试文件（tests/host/ 下所有引用 InMemoryToolRuntime 的文件）:
   - 更新 import 和类型标注

不做：
- 兼容 alias / re-export / wrapper / facade
- cursor registry 持久化
- 行为变更
- schema 变更

验证：
- pytest tests/host/ -x -q
- pyright dayu/host/ tests/host/
- 确认没有新增或扩散类型错误
```

---

## 9. 对其他 Phase 的影响

- **P9 lifecycle governance**: 无影响——cursor 生命周期是 P2 已固定的语义
- **P10 ToolRegistry**: 如果引入长 TTL cursor（如 > 1h），需评估 cursor store 持久化需求
- **P10.5 web tools**: 无影响——web tool 结果同样走截断 + cursor 机制
- **P16 interface freeze**: 如果 P8 未改名，P16 必须收口

---

## 附录：关键代码位置索引

| 文件 | 行号 | 内容 |
|------|------|------|
| `_tool_runtime.py` | 335-370 | `InMemoryToolRuntime` 类定义与字段 |
| `_tool_runtime.py` | 371-397 | `_resolve_appender()` durable/test 分派 |
| `_tool_runtime.py` | 543-861 | `_execute_framework_fetch_more()` + `_fetch_more()` |
| `_tool_runtime.py` | 1154-1391 | 7 个 `_append_*` 方法 |
| `_tool_runtime.py` | 188-255 | `ToolRuntimeOwnerScope` + ContextVar 机制 |
| `_durable_harness.py` | 248-252 | durable harness 装配 `InMemoryToolRuntime(is_durable=True)` |
| `_run_harness.py` | 440-443 | `LocalRunHarness.tool_runtime` 字段 |
| `_run_harness.py` | 516-526 | durable invariant 校验 `tool_runtime.is_durable` |
| `_run_harness.py` | 617-648 | `_attempt_owner_scope()` 注入 ToolRuntimeOwnerScope |
| `_run_harness.py` | 895 | `async with self._attempt_owner_scope(...)` 包裹 event loop |
| `contracts.py` | 478-487 | `ToolRuntimeEventData` 封闭联合 |

---

## 10. Controller Decision / Fix Status

**Decision**: 采纳方案 A — P8 内最小改名 `InMemoryToolRuntime` → `HostToolRuntime`。

**Fix date**: 2026-05-10

**Fix scope**:
- `dayu/host/_tool_runtime.py`: 类名 `InMemoryToolRuntime` → `HostToolRuntime`，更新类 docstring 显式说明 cursor registry 是 transient coordination state、fact durability 由 `ToolRuntimeEventAppender` 保证
- `dayu/host/_durable_harness.py`: import + usage 更新
- `dayu/host/_run_harness.py`: import + type hint + docstring 更新
- `dayu/host/README.md`: 所有 `InMemoryToolRuntime` 引用 → `HostToolRuntime`
- `tests/README.md`: 所有 `InMemoryToolRuntime` 引用 → `HostToolRuntime`
- `docs/host/design.md`: 执行路径图更新
- 8 个测试文件 + 2 个 utils smoke 脚本: import + 类型标注更新

**Not done**:
- 未保留兼容 alias / wrapper / re-export
- 未改变行为
- 未抽 durable cursor store
- 历史 review / 调查 artifact 中的旧名保留为审计上下文
| `migration-plan.md` | 71 | P8 状态与目标摘要 |
