# WU-SEMANTIC-OWNERSHIP-01 P3-A Aggregate Re-Review (AgentDS)

## Gate / scope

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-A — Host lifecycle, run status, and terminal event source of truth`。
- Gate：aggregate re-review（对 aggregate fix 做独立验证）。
- Reviewer：AgentDS。
- Review base：`2400a04c`（accepted plan bookkeeping commit）。
- Review head：working tree（`3649c9ea` + uncommitted fix for P3-A-AGG-F01/F02）。
- Review target：`git diff 2400a04c..HEAD` 的全部已提交变更 + `git diff HEAD` 的 uncommitted fix。
- Controller accepted findings 真源：`docs/reviews/wu-semantic-ownership-01-p3-a-aggregate-deepreview-controller-adjudication.md`（F01/F02 accepted，F03 deferred to P3-J）。
- Fix artifact：`docs/reviews/wu-semantic-ownership-01-p3-a-aggregate-fix-codex.md`。
- 只 review，不修改生产代码/测试/README/control doc/其他 review artifact，不 commit/push/PR。

## Re-review 范围与方法

本 re-review 不会只看最后改动两个文件，而是从第一性原理出发做全链路验证：

1. **逐项验证 F01/F02 closure**：确认 `_read_active_run_id` 与四条 start-transition CAS guard 动态消费 `START_BLOCKING_RUN_STATUSES` 的 owner-generated SQL material。
2. **测试质量验证**：确认新增测试以真实 SQLite 行为证明 owner set 演进时 read/snapshot 与 write guards 同源。
3. **Schema partial unique index 边界审查**：只报告当前 P3-A correctness 缺陷的直接证据；否则归入 residual/non-goal。
4. **Full propagation audit**：确认 `START_BLOCKING_RUN_STATUSES` 从定义 → SQL material → read/snapshot → write CAS guard 全链路闭合。
5. **Adversarial failure pass**：empty set、frozenset 顺序、schema DDL drift、新增 RunStatus 自动传播、test guard 触发等。
6. **P3-A-AGG-F03 非误判检查**：确认非 terminal EventLog taxonomy 确实是 deferred 边界，不是当前 blocker。

## Validation 执行结果

```text
# Full P3-A affected + aggregate fix test matrix
pytest tests/host/test_state_schema.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_public_run_api.py \
  tests/host/test_recovery_dispatch.py \
  tests/host/test_active_cancel_dispatch.py \
  tests/host/test_lifecycle_events.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_public_cancel_session_runs.py \
  tests/host/test_phase5_local_execution_integration.py \
  tests/host/test_dispatch_scheduler.py -q
337 passed in 3.76s
```

```text
# pyright
0 errors, 0 warnings, 0 informations
```

```text
# git diff --check
clean
```

```text
# Import cycle validation
python -c "from dayu.host.lifecycle_events import ...; import dayu.host.durable.state; \
  import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"
import-ok
```

Source scans：

| Scan | 目标 | 结果 |
|---|---|---|
| `status IN (?, ?, ?, ?, ?)` in `state.py` | F01/F02 残留硬编码 | **0 匹配** |
| `run_status_in_clause(START_BLOCKING_RUN_STATUSES)` in `state.py` | 全部 consumer 使用 owner helper | **6 处**（公开 read + snapshot + 4 CAS guards） |
| `_EVENT_TYPE_(RUN\|ATTEMPT)_(SUCCEEDED\|FAILED\|CANCELLED\|LOST)` in run_transition/engine_ingest | terminal event 常量重复 | **0 匹配** |
| `EngineEvent(` / `RunFailedData(` in engine_ingest（非 Engine-origin 路径） | synthetic EngineEvent | **0 匹配** |
| `hasattr` / `getattr` in engine_ingest/state/command | 逃逸类型边界 | **0 匹配** |
| `terminal_event_id is None` / `is not None` in engine_ingest（非 row validation） | terminal refs 代理 status | **0 匹配** |
| `worker_accepted_at` / `worker_accept_event_id` / `worker_accept_event_sequence` in command.py | command 直接读 dispatch 内部字段 | **0 匹配** |

---

## F01 逐项验证：`_read_active_run_id` 动态消费 owner material

### 修复位置

`dayu/host/durable/state.py:6469`：

```python
status_clause, status_params = run_status_in_clause(START_BLOCKING_RUN_STATUSES)
```

旧实现（已删除）：
```python
# 旧：5 个硬编码 placeholder + 5 个 serialize_run_status 参数
AND status IN (?, ?, ?, ?, ?)
(session_id,
 serialize_run_status(RunStatus.ACCEPTED),
 serialize_run_status(RunStatus.RUNNING),
 serialize_run_status(RunStatus.WAITING),
 serialize_run_status(RunStatus.CANCELLING),
 serialize_run_status(RunStatus.RECOVERING))
```

### 证据链

1. `_read_active_run_id` 在函数体内调用 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`，每次执行时从模块全局读取 owner set（非缓存）。
2. 同一 owner set 也被公开 `read_active_run_for_session`（line 1663）使用，`SessionSnapshot.active_run_id` 与公开 API 读同一 durable fact 时同源。
3. 测试 `test_session_snapshot_active_run_matches_owner_derived_public_read`：
   - 使用 `monkeypatch.setattr(state_module, "START_BLOCKING_RUN_STATUSES", frozenset({RunStatus.QUEUED}))`。
   - 写入 queued Run。
   - 断言 `read_active_run_for_session(...).run_id == session_snapshot_from_rows(...).active_run_id == "run-owner-read-queued"`。
   - 旧五状态硬编码实现会返回 `None`（因 `QUEUED` 不在旧列表中），证明两条消费者动态从 owner material 派生。

### Verdict：**已关闭**

`_read_active_run_id` 不再拥有独立 status 集合；placeholder 数量、参数数量与顺序全部由 `START_BLOCKING_RUN_STATUSES` 通过 `run_status_in_clause` 派生。测试以真实 SQLite 行为证明了 owner set 演化时 read 与 snapshot projection 同源。

---

## F02 逐项验证：四条 start-transition CAS guard 动态消费 owner material

### 修复位置

| 函数 | 行号 | 旧状态 |
|---|---|---|
| `promote_queued_run_row` | 3202 | 5 个硬编码 status placeholder + 5 个 params |
| `start_unstarted_run_row` | 3281 | 同上 |
| `resume_waiting_run_row` | 3747 | 同上 |
| `start_recovering_run_row` | 4023 | 同上 |

每条 guard 的修复模式一致：

```python
# 修复前
AND active_run.status IN (?, ?, ?, ?, ?)
# + 5 个 serialize_run_status(...) 参数

# 修复后
status_clause, status_params = run_status_in_clause(START_BLOCKING_RUN_STATUSES)
AND active_run.status {status_clause}
# + *status_params
```

### 证据链

1. 四条 guard 各自在函数体内调用 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`，动态消费 owner set。
2. 未复制 tuple、模块常量、状态字符串或兼容 wrapper。所有 `NOT EXISTS` 子查询使用了同一个 owner-generated clause。
3. 既有目标状态、current attempt、terminal ref 与 CAS 条件保持不变。
4. 测试 `test_start_transition_guards_derive_blocking_material_from_owner_set`：
   - Parametrized 覆盖全部 4 种 transition（`promote_queued`、`start_unstarted`、`resume_waiting`、`start_recovering`）。
   - 使用 `monkeypatch.setattr(state_module, "START_BLOCKING_RUN_STATUSES", frozenset({RunStatus.QUEUED}))`。
   - 为每条 transition 放置 target Run + queued sibling blocker。
   - 第一轮 transition：返回 `CAS_LOST`（因 queued sibling 被 owner set 识别为 blocker）。
   - 删除 blocker → 第二轮 transition：返回 `UPDATED`，target Run 进入 `RUNNING`。
   - 旧五状态硬编码不会把 queued sibling 作为 blocker（`QUEUED` 不在旧列表中），因此测试能证明 SQL status material 动态来自 owner set。
   - 同时证明 owner 化没有改变无冲突 happy path。

### Verdict：**已关闭**

四条 start-transition `NOT EXISTS` CAS guard 全部从 `START_BLOCKING_RUN_STATUSES` 的 owner-generated SQL material 派生。新增非终态 `RunStatus` 时，四条 guard 的阻塞判定自动同步，不再与 read/admission 产生并发 Run 判定分歧。测试覆盖了全部 4 种 transition 的 CAS 阻塞与无冲突成功路径。

---

## Schema partial unique index 边界审查

### 直接证据

`dayu/host/durable/schema.py:1149-1153`：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS host_runs_one_active_per_session
ON host_runs(session_id)
WHERE status IN ('accepted', 'running', 'waiting', 'cancelling', 'recovering')
```

该 DDL 的 `WHERE` 子句以**静态字符串**硬编码了与 `START_BLOCKING_RUN_STATUSES` 相同的五个状态。它与 state.py 中的 owner set 语义等同，但位于 DDL 层，不是运行时查询。

### 判定

**已归属 residual/non-goal，不构成 current P3-A correctness finding。**

理由：

1. **DDL 与 runtime helper 不在同一抽象层**：`run_status_in_clause` 是运行时 Python 函数，无法在 `CREATE UNIQUE INDEX` DDL 中使用。将 DDL 的 `WHERE` 子句改为运行时动态构造需要完全重构 schema migration 机制，远超 P3-A scope。
2. **P3-A 不新增 RunStatus 成员**：plan 明确 non-goal："不引入 RunStatus 新成员，不新增 `RUN_REJECTED`，不改 durable schema version"。因此当前 DDL 不会因 P3-A 而变得不一致。
3. **P3-A 有测试守卫**：`test_start_blocking_run_statuses_are_explicit_current_assumption` 锁定当前 5 成员的精确集合；新增非终态 `RunStatus` 时该测试会失败，迫使开发者同时审查 DDL。
4. **Index 是安全网而非 consumer**：partial unique index 作为数据库完整性约束（safety net），即使应用层 guard 有 bug，index 也可防止同一 session 出现两个 active run。它不是 query/read/admission consumer。

### Residual note

若未来 WU 需要新增 `RunStatus` 成员，schema migration 必须同步更新 `_HOST_RUNS_ONE_ACTIVE_PER_SESSION_INDEX_DDL` 的 `WHERE` 子句。建议记录到 P3-J / schema hardening owner。此风险已在 aggregate deepreview R2 中以更低粒度（CAS mutation helper 内联 status）记录；本次补充 DDL 层 note。

---

## Propagation audit：`START_BLOCKING_RUN_STATUSES` 全链路

```text
RunStatus enum + durable terminal row rules
  → TERMINAL_RUN_STATUSES（从 _row_rules.TERMINAL_RUN_STATUS_VALUES 派生）
  → NON_TERMINAL_RUN_STATUSES = RunStatus - TERMINAL_RUN_STATUSES（自动派生）
  → START_BLOCKING_RUN_STATUSES = NON_TERMINAL_RUN_STATUSES - {QUEUED}（自动派生）
  → serialized_run_status_values（frozenset 按 RunStatus 定义顺序序列化）
  → run_status_in_clause（生成 IN (?, ...) 与 params；空集合 fail-fast）
  → 6 个 consumer 动态消费：
      ├─ read_active_run_for_session（公开 active Run 读）
      ├─ _read_active_run_id → session_snapshot_from_rows → SessionSnapshot.active_run_id（用户可见 projection）
      ├─ promote_queued_run_row NOT EXISTS guard（CAS：QUEUED → RUNNING）
      ├─ start_unstarted_run_row NOT EXISTS guard（CAS：ACCEPTED → RUNNING）
      ├─ resume_waiting_run_row NOT EXISTS guard（CAS：WAITING → RUNNING）
      └─ start_recovering_run_row NOT EXISTS guard（CAS：RECOVERING → RUNNING）
  → DDL safety net（schema.py 静态索引，不在 runtime helper 传播链内）
```

### 一致性验证

| 维度 | 状态 | 证据 |
|---|---|---|
| owner set 定义 | 单一真源 | `START_BLOCKING_RUN_STATUSES = NON_TERMINAL_RUN_STATUSES - {QUEUED}`（state.py:77-79） |
| SQL material | 单一派生路径 | 全部 6 个 consumer 使用 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)` |
| read/snapshot 同源 | 已证明 | `test_session_snapshot_active_run_matches_owner_derived_public_read` |
| write guard 同源 | 已证明 | `test_start_transition_guards_derive_blocking_material_from_owner_set`（参数化 4 路） |
| owner set 演进 | 自动传播 + test guard | `test_start_blocking_run_statuses_are_explicit_current_assumption` 锁定精确成员；新增非终态时强制失败 |
| 空集合 fail-fast | 安全 | `run_status_in_clause` 空集合抛 `HostDurableError`（state.py:598-599） |
| frozenset 顺序 | 确定性 | `serialized_run_status_values` 对 frozenset 按 RunStatus 定义顺序输出（state.py:579-580） |

无"显示正确但持久化错误"、"read 正确但 write guard 错误"的语义分裂。

---

## Adversarial failure pass

### 1. Empty owner set

`run_status_in_clause(frozenset())` → `HostDurableError("Run status IN clause statuses must not be empty")`。fail-closed，不生成非法 SQL `IN ()`。

### 2. Frozenset ordering determinism

`serialized_run_status_values` 对 `frozenset` 按 `RunStatus` 定义顺序输出；对 `tuple` 保留调用方顺序。SQL 参数稳定，不会因为 hash 随机化导致 query plan 不稳定。

### 3. 新增 RunStatus 的自动传播验证

假设新增 `RunStatus.PREPARING`（非终态）：
- `NON_TERMINAL_RUN_STATUSES` 自动包含 `PREPARING`
- `START_BLOCKING_RUN_STATUSES` 自动包含 `PREPARING`
- `test_start_blocking_run_statuses_are_explicit_current_assumption` **必然失败**（精确成员集合不再匹配），迫使开发者显式审查 admission 语义
- 6 个 consumer 的 SQL `IN` clause **自动**包含 `PREPARING`（无需独立修改）
- `_HOST_RUNS_ONE_ACTIVE_PER_SESSION_INDEX_DDL` **不会**自动包含（DDL 静态字符串），需人工审查

### 4. CANCELLING + active cancel decision table（回归验证）

全部 CANCELLING 路径通过现有 test matrix 覆盖，本次 fix 未改变任何 active cancel / late rejection / worker lifecycle 行为：

| Run 状态 | Incoming fact | 行为 | 测试 |
|---|---|---|---|
| `CANCELLING` | Engine `FINAL_ANSWER` | late terminal rejected | `test_late_run_failed_after_run_cancelling_is_rejected_with_diagnostic` |
| `CANCELLING` | Engine `RUN_FAILED` | late terminal rejected | 同上 |
| `CANCELLING` | Host lifecycle clean EOF | diagnostic only | `test_host_lifecycle_after_run_cancelling_is_diagnostic_only` |
| `CANCELLING` | Host lifecycle worker lost | diagnostic only | 同上（parametrized） |

### 5. CAS guard 重复调用幂等

四条 guard 的 `status_clause, status_params` 在函数体内每次调用时重新计算。同一事务内连续两次调用同一 guard 时，`status_params` 展开稳定；`*status_params` 在 SQL params tuple 中位置固定。`NOT EXISTS` 子查询本身已是幂等——第二次调用只是再次检查 blocking run 不存在。

### 6. Engine-origin vs Host-lifecycle identity namespace 隔离

`event-engine-` 与 `event-host-lifecycle-` namespace 不相交。本次 fix 未改动 `engine_ingest.py` 的任何 identity 逻辑。duplicate detection 按 final event ids 查重，不会因 namespace 碰撞互相吞掉。

### 7. Partial unique index 与 CAS guard 双重保护

即使四条 CAS guard 因某种原因失效（允许了两个 active run），schema 的 `host_runs_one_active_per_session` partial unique index 会在 `INSERT`/`UPDATE` 时触发 SQLite constraint violation，阻止第二笔 active run 写入。这是 defense-in-depth：应用层 guard + 数据库层 constraint。

### 8. 未触及文件检查

本次 fix 仅修改：
- `dayu/host/durable/state.py`
- `tests/host/test_state_schema.py`

未触碰 `docs/host/issues-implementation-control.md`、`docs/cli_ci.md`、其他 review artifact、P3-B/P3-J 代码。

---

## P3-A-AGG-F03 非误判检查

P3-A-AGG-F03（非 terminal EventLog taxonomy 残留）已由 controller 明确 deferred to P3-J。本次 re-review 确认：

- 非 terminal 常量（`_EVENT_TYPE_RUN_ACCEPTED`、`_EVENT_TYPE_CANCEL_REQUESTED` 等）仍分散在 `run_transition.py` 与 `engine_ingest.py`。
- 这些常量不参与 terminal closeout、late rejection、active cancel 或 status predicate 判定。
- P3-A plan 明确："不处理非 terminal Host EventLog 常量的全局 owner 化。P3-A 只收敛 terminal event source-of-truth；非 terminal 常量作为 P3-J / future EventLog schema hardening 输入留痕。"

**Verdict：F03 正确 deferred，不构成当前 blocker。**

---

## Findings

### 未发现实质性问题

本次 re-review 在 P3-A-AGG-F01/F02 fix 及全量 P3-A S1/S2/S3 代码中未发现新的 correctness、stability 或 semantic ownership 缺陷。

---

## Aggregate finding summary

| ID | Severity | Status | 描述 |
|---|---|---|---|
| P3-A-AGG-F01 | Medium | **CLOSED** | `_read_active_run_id` 已动态消费 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`；测试证明 read/snapshot 同源 |
| P3-A-AGG-F02 | Low | **CLOSED** | 四条 start-transition CAS guard 已动态消费 owner-generated SQL material；参数化测试覆盖全部 4 路 |
| P3-A-AGG-F03 | Informational | **DEFERRED (P3-J)** | 非 terminal EventLog taxonomy 按 plan 归 P3-J；当前不阻塞 |

## Residual risks

| ID | 描述 | Owner/destination |
|---|---|---|
| P3-A-RR-R1 | `schema.py` `_HOST_RUNS_ONE_ACTIVE_PER_SESSION_INDEX_DDL` WHERE 子句硬编码 status 文本，无法使用 `run_status_in_clause`。新增 `RunStatus` 时需人工同步。 | P3-J / schema hardening |
| P3-A-RR-R2 | 非 terminal EventLog 常量统一 | P3-J |
| P3-A-RR-R3 | P3-B final answer / outbox continuity | P3-B |
| P3-A-RR-R4 | 跨进程 Engine/Host lifecycle 并发 terminal stress | production stress / EventLog hardening |
| P3-A-RR-R5 | Admission `allowed_pairs` 与 `CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES` 语义重叠（AgentDS aggregate review R5） | 后续 WU |

## Open Questions

无。

---

## Verdict

**PASS — F01/F02 fully closed，0 new material defect findings。**

P3-A-AGG-F01 与 P3-A-AGG-F02 均已在 working tree 中修复。`_read_active_run_id` 与四条 start-transition CAS guard 全部动态消费 `START_BLOCKING_RUN_STATUSES` 的 owner-generated SQL material。新增测试以真实 SQLite 行为证明：

1. Owner set 替换为 `{QUEUED}` 时，公开 read 与 session snapshot projection 返回同一 active run — 旧硬编码会遗漏。
2. Owner set 替换为 `{QUEUED}` 时，四条 CAS guard 全部将 queued sibling 识别为 blocker（CAS_LOST）— 旧硬编码不会。
3. 删除 blocker 后四条 guard 全部走通 happy path（UPDATED → RUNNING）— owner 化未破坏正常行为。

Full P3-A test matrix（337 tests）全部通过。pyright 零错误。全部 source scan clean。Propagation audit 确认 `START_BLOCKING_RUN_STATUSES` 从定义到全部 6 个 consumer 全链路闭合。Schema partial unique index 硬编码已作为 residual note 记录，不构成当前 P3-A correctness finding。

P3-A 生命周期 event/status 语义所有权修复跨 S1/S2/S3 + aggregate fix 已完全闭合。建议 controller 接受本次 fix 并推进 P3-A final closeout。

---

## Completion

- **F01 final status**：CLOSED
- **F02 final status**：CLOSED
- **New material findings**：0
- **Residual risks recorded**：5（全部已有后续 owner）
- **Verdict**：PASS
- **Artifact path**：`docs/reviews/wu-semantic-ownership-01-p3-a-aggregate-rereview-ds.md`
