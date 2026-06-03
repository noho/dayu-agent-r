# WU-LAYER-01 Slice 2 Code Review

## 基本信息

- Reviewer: AgentMiMo
- Gate: code review
- Scope: Slice 2 Terminal Shape Rule Owner
- Implementation artifact: `docs/reviews/wu-layer-01-slice2-terminal-shape-rules-codex-20260602.md`
- Plan: `docs/host/wu-layer-01-durable-row-primitive-cleanup-plan.md`
- Review target: 工作树相对 HEAD 的 Slice 2 diff

## 结论

**PASS**

无 blocking finding。

## Findings

### F1 [INFO] Attempt Python validation 不再显式拒绝 STARTING Attempt 携带 terminal refs

- 文件: `dayu/host/durable/state.py:4306-4321`
- 问题: Slice 1 的 `_validate_attempt_for_insert` 对 STARTING Attempt 有三个显式 `if` 拒绝 terminal_event_id / terminal_event_sequence / terminal_at。Slice 2 改为调用 `validate_terminal_event_refs_shape(is_terminal=attempt.status in _TERMINAL_ATTEMPT_STATUSES)`，STARTING 不在终态集合中，因此走 `is_terminal=False` 分支，仍然会拒绝非终态携带 terminal refs。行为等价，但依赖 `_TERMINAL_ATTEMPT_STATUSES` 的正确性而非硬编码。
- 影响: 无功能影响。行为一致，但测试只覆盖 DDL CHECK 路径（`test_attempt_terminal_shape_check_rejects_non_terminal_ref`），未直接测试 Python validation 拒绝 STARTING Attempt 携带 terminal refs 的路径。DDL CHECK 是安全网，Python validation 是 early fail，两者共同覆盖。
- 建议: 无需修改。后续 Slice 3 补 row decode 测试时可顺便补充 Python validation path 覆盖。

### F2 [INFO] `validate_wait_terminal_at_shape` 未覆盖非 waiting、非 terminal 的 status 文本

- 文件: `dayu/host/durable/_row_rules.py:207-224`
- 问题: `validate_wait_terminal_at_shape` 只检查 `status_value == "waiting"` 和 `status_value in WAIT_RECORD_TERMINAL_STATUS_VALUES`。如果传入一个既不是 `"waiting"` 也不在终态集合中的非法 status 文本，函数不抛异常。调用方 `_validate_wait_record_for_insert` 已在上方验证 `isinstance(row.status, WaitRecordStatus)`，所以不会传入非法文本。
- 影响: 无。调用方有 guard。
- 建议: 无需修改。

### F3 [INFO] `_row_rules.py` 导入 `dayu.host.api.AttemptStatus` / `RunStatus` 用于 `.value` 取值

- 文件: `dayu/host/durable/_row_rules.py:10`
- 问题: `_row_rules.py` 导入 `dayu.host.api` 的 `AttemptStatus` 和 `RunStatus`，只用于构建 `TERMINAL_RUN_STATUS_VALUES` / `TERMINAL_ATTEMPT_STATUS_VALUES` 的 `.value` 取值。这是 durable-private 模块对 host public API 的单向依赖，方向正确。
- 影响: 无。依赖方向符合 `_row_rules.py -> dayu.host.api` 和 `dayu.host.durable.errors`。
- 建议: 无需修改。

## Checklist 逐项审查

### 1. `_row_rules.py` 是否 durable-private、职责边界清晰、不 re-export、不 import state/schema/runtime

**通过。** `_row_rules.py` 未被 `dayu/host/durable/__init__.py` re-export（grep 确认无匹配）。只导入 `dayu.host.api`（`AttemptStatus`, `RunStatus`）和 `dayu.host.durable.errors`（`HostDurableError`）。不导入 `schema.py`、`state.py`、`dayu.runtime`、`dayu.engine`、`dayu.service`、`dayu.ui`、`dayu.fins`。

### 2. schema.py DDL CHECK 生成是否仍进入 HOST_DURABLE_DDL，且不破坏 Slice 1 definition validation

**通过。** `_HOST_RUN_TERMINAL_REFS_REQUIRED_CHECK_SQL` 等常量在模块加载时由 `_row_rules.py` helper 生成，直接嵌入 `_HOST_RUNS_DDL` / `_HOST_ATTEMPTS_DDL` / `_HOST_WAIT_RECORDS_DDL` f-string，这些 DDL 仍通过 `PHASE3_STATE_DDL` 进入 `HOST_DURABLE_DDL`。Slice 1 schema definition validation 测试 `test_durable_schema.py` 33 passed，`test_fresh_bootstrapped_schema_matches_generated_expected_sql` 通过，说明 fresh bootstrap 和 expected SQL 仍同源于 `HOST_DURABLE_DDL`。

### 3. state.py CAS terminal refs SQL replacement 是否只命中 terminal mutation path

**通过。** `_TERMINAL_REFS_UNSET_WHERE_SQL` 只用于 Run / Attempt 的 CAS `WHERE` 子句，出现在 `set_new_run_source_relation_row`、`start_unstarted_run_row`、`terminal_unstarted_run_row`、`cancel_queued_run_row`、`cancel_running_run_row`、`cancel_cancelling_run_row`、`mark_run_cancelling_row`、`mark_run_waiting_row`、`resume_waiting_run_row`、`steer_active_run_row`、`mark_running_run_recovering_row`、`start_recovering_run_row`、`terminal_recovering_run_row`、`cancel_recovering_run_row`、`cancel_waiting_run_row`、`terminal_orphaned_run_lost_row`、`terminal_recovering_run_lost_row`、`cancel_running_attempt_row`、`mark_attempt_running_row`、`mark_attempt_suspended_row`。这些都是 terminal mutation 或 non-terminal → non-terminal 的 CAS 路径，无普通 read path 插入。`_WAIT_TERMINAL_AT_UNSET_WHERE_SQL` 只用于 `_mark_wait_record_terminal_row` 和 `cancel_active_wait_records_for_run`，都是 terminal CAS 路径。

### 4. WaitRecord terminal_at IS NULL 是否加入所有 terminal CAS 源 status waiting 的路径

**通过。** `_mark_wait_record_terminal_row`（line 5047）和 `cancel_active_wait_records_for_run`（line 2221）都添加了 `{_WAIT_TERMINAL_AT_UNSET_WHERE_SQL}`。无 production repair branch。

### 5. Python validation 与 DDL/CAS terminal shape 语义是否一致

**通过。** `_row_rules.py` 的 `TERMINAL_RUN_STATUS_VALUES` / `TERMINAL_ATTEMPT_STATUS_VALUES` / `WAIT_RECORD_TERMINAL_STATUS_VALUES` 同时用于 DDL CHECK SQL 生成和 Python validation。`validate_terminal_event_refs_shape` / `validate_wait_terminal_at_shape` 的逻辑与 DDL CHECK 等价。

### 6. tests 是否覆盖 plan 要求

**通过。** 逐项核对：

- DDL CHECK 拒绝 terminal Run 缺少 terminal ref: `test_run_terminal_shape_check_rejects_terminal_missing_ref`（4 终态参数化）
- DDL CHECK 拒绝非终态 Run 携带 terminal ref: `test_run_terminal_shape_check_rejects_non_terminal_ref`（4 非终态参数化）
- DDL CHECK 拒绝 terminal Attempt 缺少 terminal ref: `test_attempt_terminal_shape_check_rejects_terminal_missing_ref`
- DDL CHECK 拒绝非终态 Attempt 携带 terminal ref: `test_attempt_terminal_shape_check_rejects_non_terminal_ref`
- WaitRecord DDL 拒绝 waiting + terminal_at: `test_wait_record_ddl_rejects_waiting_terminal_at`
- WaitRecord DDL 拒绝 terminal 缺少 terminal_at: `test_wait_record_ddl_rejects_terminal_missing_terminal_at`
- WaitRecord Python insert validation 与 DDL 一致: `test_wait_record_python_validation_rejects_terminal_at_shape`
- Corrupted wait row terminal CAS 拒绝: `test_wait_record_terminal_cas_rejects_corrupted_waiting_terminal_at`（使用 `PRAGMA ignore_check_constraints=ON` 绕过 CHECK 构造 corrupted row，CAS 结果为 `CAS_LOST` 或 `INVALID_STATE`）
- Slice 1 rerun: `test_durable_schema.py` 33 passed
- Existing transition tests: `test_run_attempt_transitions.py` 未在本次 diff 中修改，implementation artifact 报告 115 passed

### 7. 是否越界实现 Slice 3 HostRowDecodeError 或 WU-LAYER-02

**通过。** 未修改 `dayu/host/durable/errors.py`，未添加 `HostRowDecodeError`。未修改 `dayu/runtime` 或任何非 durable 模块。

### 8. docstring/type/signature 是否违反 AGENTS.md

**通过。** 所有新增/修改函数有完整中文 docstring，包含参数、返回值、异常。未使用 `Any`、`object`、无类型参数、无类型返回值。`_row_rules.py` 的 `sql_string_list` 对 `values: tuple[str, ...]` 有类型标注。`validate_terminal_event_refs_shape` 和 `validate_wait_terminal_at_shape` 参数全部 typed。`_validate_sql_identifier` 参数 typed。

### 9. control doc 状态记录

**通过。** `docs/host/host-core-followup-implementation-control.md` 的 implementation status / Slice 2 status / current slice / validation / next entry point 已更新为 Slice 2 implementation complete / code review pending。无明显记录错误。

## Open Questions

无。

## Residual Risks

- Slice 3 未实现：row decode malformed terminal shape 的稳定错误类型仍由后续 Slice 3 负责。
- Attempt Python validation path（STARTING Attempt 携带 terminal refs 被 Python validation 拒绝）无直接测试覆盖，DDL CHECK 提供安全网。
- `PRAGMA ignore_check_constraints` 在 corrupted wait row 测试中使用，这是 SQLite 3.x 特定行为，测试 setup 明确标注 test-only。

## 验证结果

```
tests/host/test_state_schema.py: 26 passed
tests/host/test_wait_record_state.py: 15 passed
tests/host/test_durable_schema.py: 33 passed (Slice 1 rerun)
```
