# WU-SEMANTIC-OWNERSHIP-01 P3-A Aggregate Re-Review

## Scope

- **Mode**: current changes (aggregate re-review)
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `2400a04c` (accepted plan bookkeeping commit)
- **Output file**: `docs/reviews/wu-semantic-ownership-01-p3-a-aggregate-rereview-mimo.md`
- **Review date**: 2026-07-10
- **Included scope**: commit `2400a04c` 至当前 working tree 的完整 P3-A S1/S2/S3 + aggregate fix（含 uncommitted working tree changes）
- **Excluded scope**: `docs/cli_ci.md`（untracked，按指令不触碰）
- **Parallel review coverage**: 无

## 审查依据

- `AGENTS.md` / `CLAUDE.md`（项目约束）
- `docs/host/design.md`、`docs/engine/design.md`
- `docs/host/issues-implementation-control.md`（gate controller）
- 已接受 plan：`docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md`

## F01/F02 Verification Summary

### P3-A-AGG-F01: `_read_active_run_id` 与 `read_active_run_for_session` 动态消费 owner material

**Status: CLOSED**

**证据链：**

1. `state.py:77-86` 定义 `START_BLOCKING_RUN_STATUSES` 为 `NON_TERMINAL_RUN_STATUSES - {QUEUED}`，是 `RunStatus` 全集派生的 module-level frozenset。
2. `state.py:1663` — `read_active_run_for_session` 调用 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)` 动态生成 SQL `IN` 谓词与参数。
3. `state.py:6469` — `_read_active_run_id`（`session_snapshot_from_rows` 的内部调用）同样调用 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`。
4. `state.py:5057` — `session_snapshot_from_rows` 通过 `_read_active_run_id(transaction, session.session_id)` 调用，snapshot 与公开 read 同源。
5. 测试 `test_session_snapshot_active_run_matches_owner_derived_public_read`（`test_state_schema.py:514-576`）通过 `monkeypatch.setattr(state_module, "START_BLOCKING_RUN_STATUSES", frozenset((RunStatus.QUEUED,)))` 替换 owner set，证明 snapshot 与 `read_active_run_for_session` 在 owner set 演进时返回相同结果（`"run-owner-read-queued"`）。
6. 测试 `test_run_status_in_clause_matches_durable_read_queries`（`test_state_schema.py:354-511`）使用真实 SQLite，证明 helper SQL 与 durable read helper 结果等价。

### P3-A-AGG-F02: 四条 start-transition active-run CAS guard 动态消费 owner material

**Status: CLOSED**

**证据链：**

1. **`promote_queued_run_row`**（`state.py:3170-3243`）：已从 committed code 的硬编码 `IN (?, ?, ?, ?, ?)` + 5 个 `serialize_run_status(...)` 参数，迁移到 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)` + `*status_params`。Working tree diff 确认。
2. **`start_unstarted_run_row`**（`state.py:3246-3326`）：同上迁移到 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`。
3. **`resume_waiting_run_row`**（`state.py:3713-3791`）：同上迁移到 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`。
4. **`start_recovering_run_row`**（`state.py:3989-4067`）：同上迁移到 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`。
5. 测试 `test_start_transition_guards_derive_blocking_material_from_owner_set`（`test_state_schema.py:579-699`）使用 `@pytest.mark.parametrize` 覆盖四条 transition，通过 `monkeypatch.setattr` 将 `START_BLOCKING_RUN_STATUSES` 替换为 `frozenset((RunStatus.QUEUED,))`，以真实 SQLite 证明：
   - 被替换后的 owner set 包含的状态（QUEUED）会阻塞 transition（`CAS_LOST`）
   - 删除 blocker 后 happy path 成功（`UPDATED`，最终状态 `RUNNING`）
   - `serialized_run_status_values(owner_statuses)` 与 `serialize_run_status(RunStatus.QUEUED)` 一致

### P3-A-AGG-F03: 非终态 EventLog taxonomy

**Status: DEFERRED to P3-J**

Plan 已明确：P3-A 只收敛 terminal event source-of-truth；非 terminal 常量作为 P3-J / future EventLog schema hardening 输入留痕。当前不作为 blocker。

## Findings

未发现实质性问题。

## Propagation Audit

Run terminal status / event type 语义从产生到消费的完整路径：

```
_row_rules.TERMINAL_RUN_STATUS_VALUES (enum.value tuple)
  -> state.TERMINAL_RUN_STATUSES (frozenset[RunStatus], derive from _row_rules)
  -> state.NON_TERMINAL_RUN_STATUSES (RunStatus全集 - TERMINAL)
  -> state.START_BLOCKING_RUN_STATUSES (NON_TERMINAL - {QUEUED})
  -> state.run_status_in_clause() 生成 SQL IN predicate + params
  -> 5 个 read/mutation helper 消费同一 material:
     - _read_active_run_id (line 6469)
     - read_active_run_for_session (line 1663)
     - promote_queued_run_row (line 3202, working tree)
     - start_unstarted_run_row (line 3281, working tree)
     - resume_waiting_run_row (line 3747, working tree)
     - start_recovering_run_row (line 4023, working tree)
  -> session_snapshot_from_rows 调用 _read_active_run_id (line 5057)
  -> test_state_schema 验证 owner set 演进时 read/guard/snapshot 同源
```

```
lifecycle_events.run_terminal_event_type_for_status(status) -> HostRunEventType
  -> run_transition._run_terminal_event_request (line 5539)
  -> engine_ingest._run_terminal_event_type_for_status (line 4741)
  -> 不再存在内联 terminal event string
```

```
lifecycle_events.closeout_attempt_terminal_event_type_for_status(status) -> HostAttemptEventType
  -> run_transition._attempt_terminal_event_request (line 5550)
  -> engine_ingest._attempt_terminal_event_type_for_status (line 4730)
  -> 不再存在内联 terminal event string
```

Import graph 验证：`python -c "from dayu.host.lifecycle_events import ...; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"` → `import-ok`。无循环依赖。

## Schema.py Partial Unique Index 边界

`schema.py:1149-1153` 的 partial unique index DDL 硬编码 `WHERE status IN ('accepted', 'running', 'waiting', 'cancelling', 'recovering')`。该值集与 `START_BLOCKING_RUN_STATUSES` 当前成员一一对应：

| DDL 硬编码值 | 对应 RunStatus | 属于 START_BLOCKING? |
|---|---|---|
| `accepted` | `ACCEPTED` | Yes |
| `running` | `RUNNING` | Yes |
| `waiting` | `WAITING` | Yes |
| `cancelling` | `CANCELLING` | Yes |
| `recovering` | `RECOVERING` | Yes |

DDL 硬编码是 SQLite DDL 的结构性限制——partial unique index 的 `WHERE` 子句只能使用字面量，无法引用 Python 运行时 material。`test_active_run_partial_unique_index_shape`（`test_state_schema.py:303-330`）验证了 DDL 中的 status 值与预期一致。`test_start_blocking_run_statuses_are_explicit_current_assumption`（`test_state_schema.py:234-252`）断言 `START_BLOCKING_RUN_STATUSES` 与枚举全集减 `QUEUED` 等价，新增非终态 RunStatus 时该测试会失败，迫使开发者审查。

**结论**：这是 P3-A non-goal 范围内的已知 residual。DDL 硬编码与 Python owner set 的同步通过测试保证。新增 `RunStatus` 成员时开发者必须同时审查 index DDL 和 `START_BLOCKING_RUN_STATUSES`，测试会强制提醒。不构成当前 P3-A correctness 缺陷。

## Tests & CI

| 验证项 | 结果 |
|---|---|
| `tests/host/test_state_schema.py` | 52 passed |
| `tests/host/test_lifecycle_events.py` | 13 passed |
| `tests/host/test_run_attempt_transitions.py` + `test_engine_ingest_mapping.py` + `test_public_run_api.py` + `test_active_cancel_dispatch.py` | 173 passed |
| pyright (`state.py`, `lifecycle_events.py`, `run_transition.py`) | 0 errors, 0 warnings |
| Import cycle 验证 | OK |

## Residual Risk

1. **DDL 与 Python owner set 手动同步**：partial unique index 的 status 集合硬编码在 DDL 中，新增 `RunStatus` 非终态成员时需要手动更新 DDL + Python owner set。测试 `test_start_blocking_run_statuses_are_explicit_current_assumption` 在新增非终态成员时会失败，但不会自动提示需要同步 DDL。建议后续在该测试中断言 DDL 字面量集合。

2. **`_row_rules.TERMINAL_RUN_STATUS_VALUES` 与 `state.TERMINAL_RUN_STATUSES` 间接同源**：`_row_rules` 使用 `enum.value` tuple，`state` 使用 `frozenset(RunStatus(value) for value in ...)`。两者都从 `RunStatus` enum 派生，但绕了两层。`test_terminal_run_statuses_derive_from_row_rules` 验证一致性。

## Verdict

- **F01 final status**: CLOSED — `_read_active_run_id` 和 `read_active_run_for_session` 动态消费 `START_BLOCKING_RUN_STATUSES`，测试以真实 SQLite 行为证明 owner set 演进时 snapshot 与 read 同源。
- **F02 final status**: CLOSED — 四条 start-transition CAS guard 全部迁移到 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`，测试以真实 SQLite 行为证明 owner set 演进时 guard 阻塞与 happy path 正确。
- **New material findings**: 0
- **Overall verdict**: P3-A S1/S2/S3 + aggregate fix 已正确关闭 F01/F02，无新 correctness/stability/semantic ownership 缺陷。DDL 硬编码与 Python owner set 的同步通过测试保证，属于已归属 residual。建议 ship。
