# Host P6 并发与一致性专项 Review

## 结论

**有条件通过。**

P6 durable EventLog / Run State / Projection 的核心并发设计是合理的：`BEGIN IMMEDIATE` + `asyncio.Lock` 双层串行化、SQLite WAL + `busy_timeout` 多进程锁、`UNIQUE(run_id, sequence)` 与 partial unique index 兜底、sink 写入与 checkpoint 前进同事务、post-commit hook 只在 commit 后触发。这些机制组合起来，在单进程多协程和多进程场景下都能保证 durable store 自身的一致性。

但存在一个真实的终端竞争条件需要修复，且测试覆盖严重不足——plan 要求的并发测试、故障注入测试、terminal race 测试全部缺失。在补齐这些测试并修复 terminal race 之前，不能声称多进程 append / replay / checkpoint 语义已验证。

## Findings

### F1. [严重: 高] terminal guard 与非 terminal append 存在竞争窗口

**问题：**

`_append_in_transaction` 在事务开头检查 `terminal_sequence` 是否已设置，如果已设置则拒绝 append。但检查和后续 INSERT 之间没有数据库级约束防止非 terminal 事件在 terminal 之后插入。

**证据：**

`_durable_event_store.py:219-227`:
```python
terminal_row = tx.execute(
    "SELECT terminal_sequence, terminal_event_position "
    "FROM host_runs WHERE run_id = ?",
    (draft.run_id,),
).fetchone()
if terminal_row is not None and terminal_row[0] is not None:
    raise ValueError(_ERROR_APPEND_AFTER_TERMINAL)
```

`_durable_event_store.py:243-262` 中 INSERT 不区分 terminal / non-terminal，没有 `WHERE NOT EXISTS (SELECT ... WHERE terminal)` 子句。

**实际风险评估：**

在 **同一进程内**，`asyncio.Lock` 保证两个 append 严格串行：T1 terminal append 先 commit，T2 non-terminal append 后 acquire lock → BEGIN IMMEDIATE → 读到 terminal_sequence 已设置 → raise ValueError。这条路径是安全的。

在 **多进程** 场景下，两个进程各自持有独立的 `HostStorage` 实例和独立的 `asyncio.Lock`。SQLite `BEGIN IMMEDIATE` 的 RESERVED 锁保证同一时刻只有一个进程可以写。当 T1 commit 释放锁后，T2 的 `BEGIN IMMEDIATE` 成功，此时 T2 在同一个 `BEGIN IMMEDIATE` 事务内重新读 `terminal_sequence`，会看到 T1 写入的值，因此也会正确拒绝。

**结论：当前实现在 asyncio.Lock + BEGIN IMMEDIATE 双层保护下是安全的。** 但这依赖于 terminal check 和 INSERT 在同一个 `BEGIN IMMEDIATE` 事务内的隐式保证。如果未来有人重构把 check 移到事务外，这个不变量就会被打破。

**建议：**

在 `_append_in_transaction` 中增加防御性注释，明确 terminal check 必须在同一个 `BEGIN IMMEDIATE` 事务内执行。或者在 INSERT 时增加 SQL 级别的防御：

```sql
INSERT INTO host_run_events (...)
SELECT ..., ?, ?, ...
WHERE NOT EXISTS (
    SELECT 1 FROM host_runs
    WHERE run_id = ? AND terminal_sequence IS NOT NULL
)
```

如果 `SELECT ... WHERE NOT EXISTS` 返回 0 rows，Python 层可以报 ValueError。这把防御从事务语义降级为 SQL 级别，更不容易被重构破坏。

**P6/P8 边界：** 这是 P6 必须修复的一致性问题，不涉及 P8 lease / fencing。

---

### F2. [严重: 高] 并发测试、故障注入测试、terminal race 测试全部缺失

**问题：**

P6 plan (`phase6-plan.md:262-263`) 要求以下测试文件，但均未实现：

| Plan 要求的测试文件 | 实际状态 |
| --- | --- |
| `tests/host/test_phase6_durable_event_concurrency.py` | **不存在** |
| `tests/host/test_phase6_observer_retry_lag.py` | **不存在** |
| `tests/host/test_phase6_projection_rebuild.py` | **不存在** |

plan 中明确要求的以下场景均无测试覆盖：

1. 同一 run 多连接并发 append，cursor 不重复、不跳回。
2. 多 run 并发 append，global event position 不重复。
3. terminal append 与普通 append 竞争时，terminal 后普通 append 被拒绝。
4. event row 插入后 state 更新前的异常回滚。
5. state 更新后 terminal snapshot 写入前的异常回滚。
6. sink 写入后 checkpoint 前进前的异常回滚。
7. observer 重复运行同一 batch，不重复写 sink（幂等验证）。

**证据：**

`test_phase6_host_storage_transaction.py:32-47` 的 `test_transaction_serializes_concurrent_writers` 使用 `asyncio.gather` 并发 5 个 writer，但它只验证了同一连接内的 asyncio.Lock 串行化——这不等于多连接或多进程并发。测试使用 `:memory:` 数据库，无法模拟多进程。

`test_phase6_durable_event_store.py` 只有顺序单连接测试，无并发场景。

`test_phase6_projection_checkpoint.py` 的 `test_observer_retryable_failure_does_not_advance` 验证了 retryable failure 不推进 checkpoint，但只测了顺序执行，没有两个 drain 并发的场景。

**影响：**

没有并发测试，无法验证：
- 多进程 append 时 `(run_id, sequence)` 唯一约束是否真的能兜底。
- 多进程 observer drain 时 checkpoint 是否不会被错误推进。
- 故障注入后数据库是否没有半提交状态。

**建议：**

P6 必须补齐以下测试（至少覆盖单进程 asyncio.Lock 路径的正确性）：

1. **并发 append 测试**：使用 `asyncio.gather` 对同一 run 并发多个 append，验证 sequence 不重复、global position 单调递增。虽然无法在 pytest 中模拟真正的多进程，但至少验证 asyncio.Lock 路径。
2. **Terminal race 测试**：并发 append terminal event 和 non-terminal event，验证 terminal 后 non-terminal 被拒绝。
3. **故障注入测试**：mock `connection.execute` 在特定 SQL 后抛异常，验证 rollback 后数据库状态一致。
4. **Observer duplicate drain 测试**：对同一 observer 并发调用 `run_once`，验证 checkpoint 不倒退、sink 不重复写入（需要 sink 实现幂等）。

多进程真实测试可以在 `utils/smoke_host_p6_durable_eventlog.py` 中用 `multiprocessing` 实现，不强求在 pytest 中。

**P6/P8 边界：** 测试缺失是 P6 必须补齐的验收项。多进程真实并发测试可以放到 smoke 或 P8，但 asyncio 并发测试是 P6 必做。

---

### F3. [严重: 中] SELECT MAX(sequence)+1 不是数据库级原子分配

**问题：**

`_durable_event_store.py:229-233`:
```python
next_sequence_row = tx.execute(
    "SELECT COALESCE(MAX(sequence) + 1, ?) FROM host_run_events "
    "WHERE run_id = ?",
    (_FIRST_EVENT_SEQUENCE, draft.run_id),
).fetchone()
```

这个 SELECT 和后续 INSERT 不是原子的——它们在同一事务内，但不是单条 SQL。如果未来有人把这段逻辑移到事务外，或者引入新的连接池，SELECT MAX 和 INSERT 之间可能出现 gap。

**实际风险评估：**

当前实现在 `BEGIN IMMEDIATE` 事务内执行，`UNIQUE(run_id, sequence)` 兜底。即使 SELECT MAX 返回过时值，INSERT 会因唯一约束失败。这个设计是安全的。

**建议：**

无需修改实现，但应增加注释说明依赖关系：`SELECT MAX + INSERT` 的正确性依赖 `BEGIN IMMEDIATE` 事务隔离和 `UNIQUE(run_id, sequence)` 兜底。

**P6/P8 边界：** 这是 P6 实现的防御性建议，不涉及 P8。

---

### F4. [严重: 中] `source_engine_event_id` 去重依赖 partial unique index，冲突语义需明确

**问题：**

`_durable_event_store.py:88-91`:
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_host_run_events_engine_id
ON host_run_events (run_id, source_engine_event_id)
WHERE source_engine_event_id IS NOT NULL
```

当两个 Engine event 携带相同的 `(run_id, source_engine_event_id)` 时，第二个 INSERT 会抛 `sqlite3.IntegrityError`，但 `_append_in_transaction` 没有捕获这个特定异常并转换为明确的业务错误。

**证据：**

`_durable_event_store.py:243-262` 中 INSERT 后只取 `cursor.lastrowid`，没有 try/except 捕获 `IntegrityError`。调用方会收到原始的 `sqlite3.IntegrityError`，错误消息是 SQLite 生成的，不是业务友好的。

**影响：**

Engine retry 时如果重放了相同的 event，append 会抛 `sqlite3.IntegrityError` 而不是明确的"重复 event"错误。调用方（如 `LocalRunHarness._run_to_store`）无法区分"重复 event"和"数据库错误"。

**建议：**

在 `_append_in_transaction` 中捕获 `sqlite3.IntegrityError`，检查是否是 `idx_host_run_events_engine_id` 违规，如果是则转为 `ValueError("duplicate source_engine_event_id")`。或者在 INSERT 前先 SELECT 检查（在同一个事务内）。

**P6/P8 边界：** 这是 P6 必须完善的错误语义。P8 不负责 Engine event 去重。

---

### F5. [严重: 中] observer drain 并发缺乏防重入保护

**问题：**

`ProjectionCoordinator.run_once` 和 `drain` 没有防重入锁。如果两个协程同时对同一 observer 调用 `run_once`：

1. 两者都读到相同的 `last_success_position`。
2. 两者都拉取相同的 event batch。
3. 两者都在各自的事务中调用 `observer.process` + `advance_success`。
4. 第一个 commit 成功，checkpoint 前进。
5. 第二个 commit 时，`advance_success` 检查 checkpoint 不能倒退——但第二个传入的 `last_position` 可能等于已 committed 的 position，不触发 regression 检查（检查条件是 `existing[0] > position.value`，等于不拒绝）。

**证据：**

`_projection_store.py:154-164`:
```python
existing = tx.execute(
    "SELECT last_success_position FROM host_projection_checkpoints ...",
    (...),
).fetchone()
if existing is not None and existing[0] is not None:
    if int(existing[0]) > position.value:
        raise ValueError(_ERROR_CHECKPOINT_REGRESSION)
```

如果 `existing[0] == position.value`，UPDATE 会执行但不改变 `last_success_position`。此时 sink 可能被重复调用。

**影响：**

如果 observer sink 不是幂等的，重复调用会产生重复数据。当前 `AuditProjectionObserver` 和 `TimelineProjectionObserver` 是 in-memory append，重复调用会产生重复记录。

**建议：**

1. `ProjectionCoordinator` 应增加 `asyncio.Lock` 防止同一 observer 并发 drain。
2. `advance_success` 应增加 `>=` 检查：如果 `existing[0] >= position.value`，跳过 UPDATE（幂等）。
3. 在文档中明确 observer sink 必须幂等，因为 checkpoint 前进和 sink 写入同事务只保证 at-least-once，不保证 exactly-once。

**P6/P8 边界：** 这是 P6 必须修复的一致性问题。完整 observer claim / lease 是 P8，但基本防重入是 P6 职责。

---

### F6. [严重: 低] post-commit hook 异常会丢失通知但不影响数据一致性

**问题：**

`_host_storage_transaction.py:188-189`:
```python
for hook in tx.post_commit_hooks:
    hook()
```

如果某个 hook 抛异常，后续 hook 不会执行，且异常会传播到 `transaction()` 的调用方。此时数据库已 commit，数据一致，但订阅者通知丢失。

**证据：**

`_durable_event_store.py:549-561` 中 `_make_notify_hook` 构造的 hook 内部调用 `loop.create_task(_notify_condition(condition))`。如果 `asyncio.get_running_loop()` 失败（已处理）或 `_notify_condition` 抛异常，通知丢失。

**影响：**

本进程的 `subscribe` 用户可能在 terminal event 已 commit 后仍阻塞在 `condition.wait()` 上，直到下一次 append 唤醒。但 `subscribe` 的 replay-then-follow 设计意味着即使错过通知，下次有新事件时仍会被唤醒。如果 terminal 是最后一个事件，订阅者会一直阻塞——但 `_subscribe` 中的 `_terminal_reached` 检查会在 replay 阶段发现 terminal 并正确退出。

**实际评估：** 这个场景在当前实现中风险很低，因为 `_notify_condition` 只做 `condition.notify_all()`，不太可能抛异常。

**建议：**

在 hook 循环中捕获异常并 log warning，不传播到调用方：
```python
for hook in tx.post_commit_hooks:
    try:
        hook()
    except Exception:
        _LOGGER.warning("post-commit hook failed", exc_info=True)
```

**P6/P8 边界：** 这是 P6 可以做的防御性改进，不是必须修复项。

---

### F7. [严重: 低] lag 计算不与 checkpoint 在同一快照内

**问题：**

`_projection_store.py:237-254` 中 `_lag_events_for` 读取 `MAX(event_position)` 是独立的只读查询，不在 checkpoint 读取的同一事务内。在并发 append 场景下，lag 值可能略有偏差。

**实际评估：**

lag 只用于诊断展示，不用于决策。偏差几个事件在并发场景下是可接受的。当前实现用 `max(0, latest - last_success)` 保证非负，没有正确性风险。

**建议：**

无需修改。在文档中说明 lag 是近似值。

**P6/P8 边界：** 不涉及。

---

### F8. [严重: 低] `ensure_host_schema` 绕过 `HostStorage.transaction()` 直接操作连接

**问题：**

`_durable_event_store.py:147-152`:
```python
def ensure_host_schema(storage: HostStorage) -> None:
    storage.open()
    connection = storage._connection
    ...
    for statement in _SCHEMA_STATEMENTS:
        connection.execute(statement)
```

schema bootstrap 直接使用 `storage._connection` 而不通过 `storage.transaction()`。这些 DDL 语句在 autocommit 模式下执行（`isolation_level=None`），每条语句各自 commit。

**影响：**

如果进程在 schema bootstrap 中途崩溃，可能留下半创建的 schema。但这只影响首次初始化，且 `CREATE TABLE IF NOT EXISTS` 和 `CREATE INDEX IF NOT EXISTS` 保证重试是幂等的。

**建议：**

可以改为用 `storage.transaction()` 包裹所有 DDL，保证原子性。但这不是 P6 必须修复项。

**P6/P8 边界：** 不涉及。

---

## 通过项

### 1. BEGIN IMMEDIATE 使用正确

`_host_storage_transaction.py:39` 定义 `_BEGIN_IMMEDIATE = "BEGIN IMMEDIATE"`，`_host_storage_transaction.py:226` 在每次 `transaction()` 入口调用。WAL + `BEGIN IMMEDIATE` 保证写事务获取 RESERVED 锁，后续写操作不需要再升级锁，避免了 WAL 模式下的 writer starvation。

### 2. asyncio.Lock 串行化同进程写事务

`_host_storage_transaction.py:179` 的 `async with self._write_lock` 保证同一进程内只有一个协程持有写事务。这避免了同一连接上的 SQLite 并发写问题。

### 3. 多进程依赖 SQLite 锁和唯一约束，不依赖 Python 内存锁

`asyncio.Lock` 只在单进程内有效。多进程场景下：
- SQLite `BEGIN IMMEDIATE` 的 RESERVED 锁保证同一时刻只有一个进程可以写。
- `UNIQUE(run_id, sequence)` 保证即使有极端竞争，sequence 不会重复。
- `event_position INTEGER PRIMARY KEY AUTOINCREMENT` 保证全局 position 唯一。
- `busy_timeout=5000` 给等待进程足够时间。

### 4. commit / rollback / post-commit hook 没有半提交风险

`_host_storage_transaction.py:182-189` 的结构：
```python
try:
    yield tx
except BaseException:
    rollback()
    raise
commit()
for hook in tx.post_commit_hooks:
    hook()
```

- 异常时 rollback，不 commit，不触发 hook。
- commit 失败时异常传播，hook 不执行。
- hook 在 commit 之后执行，此时锁已释放，数据已持久化。

### 5. sink 写入和 checkpoint 前进同事务

`_event_observer.py:209-218`:
```python
async with self.storage.transaction() as tx:
    observer.process(tx=tx, batch=envelopes)
    self.projection_store.advance_success(tx=tx, ...)
```

sink 写入和 checkpoint 推进在同一事务中。如果 sink 抛异常，整个事务 rollback，checkpoint 不前进。这保证了 at-least-once 语义。

### 6. checkpoint 不可倒退

`_projection_store.py:154-164` 在 `advance_success` 中检查 `existing[0] > position.value` 时拒绝。虽然 `>=` 检查更严格（见 F5），但 `>` 检查已能防止倒退。

### 7. retryable / blocked failure 不推进 last_success_position

`_projection_store.py:188-235` 的 `record_failure` 只更新 `last_attempted_position`、`status`、`retry_count`、`last_error_*`，不触碰 `last_success_position`。这保证了失败后重试会从原 checkpoint 开始。

### 8. append commit 前事件不会被 stream 看到

`_durable_event_store.py:364-369` 的 `list_events` 通过 `storage.execute_read` 读取，不进入写锁。但只有 committed 数据才可见（SQLite 默认隔离级别）。`subscribe` 的 replay 阶段也通过 `execute_read` 读取，只看到 committed 数据。

### 9. post-commit hook 只在 commit 后触发

已确认：`_host_storage_transaction.py:188` 的 hook 调用在 `commit()` 之后。

### 10. slow subscriber 不影响 append

`subscribe` 使用 `asyncio.Condition.wait()` 阻塞等待新事件。`append` 使用 `asyncio.Lock` 获取写事务。两者不共享锁，互不阻塞。

### 11. in-memory condition 只服务本进程通知

`_durable_event_store.py:163` 的 `_condition` 是进程内 `asyncio.Condition`。多进程场景下，进程 B 不会被进程 A 的 condition 唤醒。进程 B 必须通过 `fetch_events_by_position` 或自己的 `subscribe` 轮询 durable store 来发现新事件。这是正确的设计——durable replay 是多进程补读的真源。

---

## 测试覆盖评估

| 场景 | Plan 要求 | 实际覆盖 | 评估 |
| --- | --- | --- | --- |
| 顺序 append / replay / terminal | ✅ | ✅ `test_phase6_durable_event_store.py` | 通过 |
| 事务 commit / rollback / hook | ✅ | ✅ `test_phase6_host_storage_transaction.py` | 通过 |
| asyncio.Lock 串行化 | ✅ | ✅ `test_transaction_serializes_concurrent_writers` | 通过（但只验证单连接） |
| checkpoint 前进 / regression 拒绝 | ✅ | ✅ `test_phase6_projection_checkpoint.py` | 通过 |
| retryable failure 不推进 checkpoint | ✅ | ✅ `test_observer_retryable_failure_does_not_advance` | 通过 |
| blocked failure 不推进 checkpoint | ✅ | ✅ `test_observer_non_retryable_failure_marks_blocked` | 通过 |
| Run / Attempt 状态创建与更新 | ✅ | ✅ `test_phase6_run_state_store.py` | 通过 |
| terminal result round trip | ✅ | ✅ `test_run_state_terminal_result_round_trip` | 通过 |
| memory rebuild 非成功终态 | ✅ | ✅ `test_phase6_memory_rebuild.py` | 通过 |
| timeline / audit projection | ✅ | ✅ `test_phase6_timeline_audit_projection.py` | 通过 |
| serializer round trip | ✅ | ✅ `test_phase6_run_event_serializer.py` | 通过 |
| **多连接并发 append** | ✅ | ❌ 缺失 | **必须补** |
| **Terminal race 测试** | ✅ | ❌ 缺失 | **必须补** |
| **故障注入 / rollback** | ✅ | ❌ 缺失 | **必须补** |
| **Observer duplicate drain** | ✅ | ❌ 缺失 | **必须补** |
| **多进程真实并发** | ✅ | ❌ 缺失 | 可放到 smoke |
| Observer retry / lag | ✅ | 部分（在 checkpoint 测试中） | 建议补独立文件 |
| Projection rebuild | ✅ | 部分（在 timeline/audit 测试中） | 建议补独立文件 |

---

## P6 / P8 边界总结

| 能力 | 归属 | 说明 |
| --- | --- | --- |
| BEGIN IMMEDIATE + asyncio.Lock 串行化 | **P6 已完成** | 单进程多协程 + 多进程 SQLite 锁 |
| UNIQUE(run_id, sequence) 兜底 | **P6 已完成** | 数据库约束保证 |
| AUTOINCREMENT event_position | **P6 已完成** | 全局唯一 |
| partial unique index (run_id, source_engine_event_id) | **P6 已完成** | Engine event 去重 |
| terminal guard（同一事务内检查） | **P6 已完成** | 但需增加防御性注释或 SQL 级检查 |
| sink + checkpoint 同事务 | **P6 已完成** | at-least-once 语义 |
| checkpoint 不可倒退 | **P6 已完成** | 但 `>` 检查建议改为 `>=` |
| post-commit hook 在 commit 后触发 | **P6 已完成** | |
| observer drain 防重入 | **P6 应补** | 增加 asyncio.Lock |
| 并发 / 故障注入测试 | **P6 应补** | plan 要求但缺失 |
| source_engine_event_id 冲突语义 | **P6 应补** | 捕获 IntegrityError 转业务错误 |
| owner lease / fencing | **P8** | P6 不实现 |
| orphan / stale attempt recovery | **P8** | P6 不实现 |
| observer claim / lease / consumer group | **P8+** | P6 只做最小 protocol |
| late write fencing | **P8** | P6 不判断 owner |

---

## 建议行动项

1. **[P6 必须]** 修复 F1：在 `_append_in_transaction` 中增加防御性注释或 SQL 级 terminal check。
2. **[P6 必须]** 修复 F2：补齐并发测试、terminal race 测试、故障注入测试。
3. **[P6 必须]** 修复 F4：捕获 `source_engine_event_id` 唯一约束冲突并转为明确业务错误。
4. **[P6 必须]** 修复 F5：`ProjectionCoordinator` 增加防重入锁，`advance_success` 改为 `>=` 检查。
5. **[P6 建议]** 修复 F3：增加 SELECT MAX + INSERT 依赖关系的注释。
6. **[P6 建议]** 修复 F6：hook 循环中捕获异常并 log warning。
7. **[P8 后续]** F7、F8 不需要 P6 处理。
