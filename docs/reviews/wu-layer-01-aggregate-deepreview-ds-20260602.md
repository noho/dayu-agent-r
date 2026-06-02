# WU-LAYER-01 Aggregate Deepreview — DS — 2026-06-02

## 概要

**Role**: Aggregate Review Specialist (DS)
**Scope**: WU-LAYER-01 全量 4 slices 跨 slice adversarial review
**Design source**: `docs/host/design.md`
**Control source**: `docs/host/host-core-followup-implementation-control.md`
**Plan source**: `docs/host/wu-layer-01-durable-row-primitive-cleanup-plan.md`
**Accepted commits**: Plan `278e5be`, Slice 1 `02396e5`, Slice 2 `ff64f0b`, Slice 3 `b4fc923`, Slice 4 `2397e72`

## Validation Results

```
pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_run_attempt_transitions.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py
============================= 136 passed in 1.27s ==============================
pyright: 0 errors, 0 warnings, 0 informations
```

## Findings Ordered by Severity

### HIGH

**None.**

### MEDIUM

**None.**

### LOW

#### F-01: `_assert_host_row_decode_error` helper duplicated between test files

- **File**: `tests/host/test_state_schema.py:984-1005`, `tests/host/test_wait_record_state.py:914-935`
- **Evidence**: 两个独立的测试文件各维护了一份完全相同的 `_assert_host_row_decode_error` 私有 helper，逻辑、签名、断言完全一致。
- **Assessment**: 不产生 correctness 风险。两个 tests 模块分别测试 `RunRow`/`AttemptRow` 与 `WaitRecordRow` 的 decode 边界，共享 helper 提取不是本轮 WU-LAYER-01 的 scope。WU-LAYER-02 可考虑把该 helper 提取到 `tests/host/` 共享测试 helper，但不在本轮要求强制合并。
- **Severity**: LOW (non-blocking; deferred to WU-LAYER-02)
- **Recommendation**: 记入 deferred note，不要求当前 gate 修复。

## Adversarial Checks

### AC-01: Schema expected SQL generation truly same-sourced with HOST_DURABLE_DDL

**PASS**

`_expected_schema_sql_by_name()` (`schema.py:1437-1463`) 创建内存 SQLite DB，执行当前 `HOST_DURABLE_DDL`，读取 `sqlite_master.sql` 作为 expected 定义。目标 DB 通过 `_read_schema_sql_by_name()` (`schema.py:1466-1495`) 读取同样的 `sqlite_master.sql`。两边的 SQL 都来自同一份 `HOST_DURABLE_DDL` 在不同 SQLite 实例中的生成结果——无手写 DDL expectation 字符串，无第二份 DDL 真源。

`test_host_durable_indexes_match_create_index_ddl` 和 `test_host_durable_tables_match_create_table_ddl` 确保 `HOST_DURABLE_TABLES`/`HOST_DURABLE_INDEXES` 集合与 DDL 文本中的 `CREATE TABLE`/`CREATE INDEX` 语句保持同源，防止常量列表与 DDL 文本漂移。

### AC-02: Current-version opener fail closed on wrong table/index definition, no repair; fresh bootstrap no false-positive

**PASS**

Fail closed 方向：
- `test_current_schema_wrong_index_definition_opener_raises_without_repair` (`test_durable_schema.py:520-568`): 同名的 `host_runs_one_active_per_session` index 定义被替换为缺失 `WHERE` 子句的普通 index，opener 抛 `HostSchemaMismatchError` matching `"definition mismatch: index host_runs_one_active_per_session"`，错误 index 定义未被修复。
- `test_current_schema_mutated_table_definition_opener_raises_without_repair` (`test_durable_schema.py:571-611`): `host_runs` table 的 `execution_target TEXT NOT NULL` 被改为 `TEXT NULL`，opener 抛 `"definition mismatch: table host_runs"`，变异后的 table 定义保持不变。
- `test_secondary_connection_definition_mismatch_raises_without_repair` (`test_durable_schema.py:666-701`): `store.connect()` secondary path 同样 fail closed 且不修复。

Fresh bootstrap no false-positive 方向：
- `test_fresh_bootstrapped_schema_matches_generated_expected_sql` (`test_durable_schema.py:729-749`): fresh bootstrap 后 `validate_host_durable_schema` 不抛错，且 `_read_schema_sql_by_name(connection) == _expected_schema_sql_by_name()` 直接同值断言。

Normalization 行为精确：
- `test_normalize_schema_sql_only_strips_and_collapses_whitespace` (`test_durable_schema.py:752-778`): 验证 `_normalize_schema_sql` 只去除首尾空白和折叠连续空白；大小写变化、标识符引号变化不会被静默归一化。

### AC-03: Slice 2 DDL CHECK modification re-covered by Slice 1 schema definition validation

**PASS**

Slice 2 将 Run/Attempt/WaitRecord DDL CHECK 从手写 SQL 字符串改为从 `_row_rules.py` 常量生成的 helper 调用。这意味着 DDL CHECK 的文本由 `terminal_event_refs_required_check_sql`、`terminal_event_refs_unset_check_sql`、`wait_terminal_at_check_sql` 生成。

Slice 1 的 `_expected_schema_sql_by_name()` 通过执行完整 `HOST_DURABLE_DDL` → 读取 `sqlite_master.sql` 来生成 expected 定义。因为 `HOST_DURABLE_DDL` 在 Slice 2 后仍然包含完整的 DDL f-string（内联了 helper 生成的 CHECK 片段），所以 `sqlite_master.sql` 会捕获最终生成的 CHECK 文本。

`test_fresh_bootstrapped_schema_matches_generated_expected_sql` 验证 fresh bootstrap 后 expected SQL 与 actual SQL 完全一致，这等价于证明：helper 生成的 CHECK 文本在 fresh bootstrap 和 expected generation 中是同一份 SQLite 产物。如果 Slice 2 的 CHECK helper 产生与 fresh bootstrap 不同的 SQL 文本，该测试会失败。

### AC-04: Terminal Run/Attempt/WaitRecord DDL CHECK, Python validation, CAS WHERE, decode-time validation are same-source consistent

**PASS**

多路径规则同源分析：

| 路径 | Run terminal refs | Attempt terminal refs | WaitRecord terminal_at |
|------|-------------------|-----------------------|------------------------|
| DDL CHECK | `_row_rules.py` → `terminal_event_refs_required_check_sql` / `unset_check_sql` → `schema.py:173-183` | `_row_rules.py` → `terminal_event_refs_required_check_sql` / `unset_check_sql` → `schema.py:185-195` | `_row_rules.py` → `wait_terminal_at_check_sql` → `schema.py:197` |
| Python insert validation | `state.py:990` → `validate_terminal_event_refs_shape` | `state.py:1029` → `validate_terminal_event_refs_shape` | `state.py:5189` → `validate_wait_terminal_at_shape` |
| CAS WHERE | `state.py:79` → `_TERMINAL_REFS_UNSET_WHERE_SQL` → `terminal_event_refs_unset_where_sql` | Same as Run | `state.py:82` → `_WAIT_TERMINAL_AT_UNSET_WHERE_SQL` → `wait_terminal_at_unset_where_sql` |
| Decode-time validation | `state.py:990` → same `validate_terminal_event_refs_shape` | `state.py:1029` → same `validate_terminal_event_refs_shape` | `state.py:1161` → same `validate_wait_terminal_at_shape` |

所有路径的终态状态集合都直接或间接来自 `_row_rules.py` 的 `TERMINAL_RUN_STATUS_VALUES`、`TERMINAL_ATTEMPT_STATUS_VALUES`、`WAIT_RECORD_WAITING_STATUS_VALUE`、`WAIT_RECORD_TERMINAL_STATUS_VALUES` 常量：
- DDL CHECK：直接引用常量
- Python validate_terminal_event_refs_shape：接受 `is_terminal` 参数，调用方通过 `_is_terminal_run_status()` (`state.py:5499-5506`) 判断，该函数使用 `TERMINAL_RUN_STATUSES`（由 `TERMINAL_RUN_STATUS_VALUES` 派生）
- Python validate_wait_terminal_at_shape：直接比较 `status_value` 与 `WAIT_RECORD_WAITING_STATUS_VALUE` / `WAIT_RECORD_TERMINAL_STATUS_VALUES`
- CAS WHERE：使用 `terminal_event_refs_unset_where_sql` / `wait_terminal_at_unset_where_sql` 生成的固定 SQL 片段

CAS WHERE 在 `state.py` 中的使用：
- `_TERMINAL_REFS_UNSET_WHERE_SQL` (line 79) 被 22 处 Run/Attempt terminal CAS 路径引用（如 `attach_source_run` line 2070、`mark_attempt_running_row` line 2624 等）
- `_WAIT_TERMINAL_AT_UNSET_WHERE_SQL` (line 82) 被 2 处 WaitRecord terminal CAS 路径引用（`cancel_active_wait_records_for_run` line 2469、`mark_wait_record_resolved_row` line 5295）

### AC-05: `_row_rules.py` is durable-private, not re-exported, not imported by `_validation.py`, not a generic validation framework

**PASS**

- `_row_rules.py` 仅被 `dayu/host/durable/schema.py` (line 15) 和 `dayu/host/durable/state.py` (line 35) 导入。
- `dayu/host/durable/__init__.py` 不包含 `_row_rules` 符号。
- `dayu/host/durable/_validation.py` 不导入 `_row_rules`。
- 所有测试文件不直接导入 `_row_rules`。
- `_row_rules.py` 职责边界明确：仅承载终态状态常量、终态引用 SQL 片段和终态形状校验函数。不涉及 scalar 类型校验、digest 校验、timestamp 格式化、row decode、schema bootstrap、transaction 或 public API validation。
- 无 `Any`/`object`/`hasattr`/`getattr` 使用；无 lazy import；无 magic 数字或字符串（SQL 列名使用模块级常量）；无嵌套函数。

### AC-06: Corrupted WaitRecord/Run CAS scenarios are test-only; CAS does not cover corrupted rows; behavior aligns with HostRowDecodeError read boundary

**PASS**

Corrupted WaitRecord CAS 测试：
- `test_wait_record_terminal_cas_rejects_corrupted_waiting_terminal_at` (`test_wait_record_state.py:763-809`): 通过 `PRAGMA ignore_check_constraints=ON` 在测试中构造 `status='waiting'` 且 `terminal_at IS NOT NULL` 的 corrupted row，然后执行 `mark_wait_record_resolved_row`。CAS 因 `_WAIT_TERMINAL_AT_UNSET_WHERE_SQL` 中的 `AND terminal_at IS NULL` 谓词不匹配而拒绝更新（CAS_LOST），后续 re-read 触发 decode-time `validate_wait_terminal_at_shape` 抛出 `HostRowDecodeError`。

Corrupted Run CAS 测试：
- `test_cancel_queued_run_row_requires_empty_terminal_refs` (`test_run_attempt_transitions.py:1494-1567`): 通过 `PRAGMA ignore_check_constraints=ON` 构造 `status='queued'` 但携带着 terminal refs 的 corrupted row，然后执行 `cancel_queued_run_row`。CAS 因 `_TERMINAL_REFS_UNSET_WHERE_SQL` 中的 terminal refs 全空谓词不匹配而拒绝更新，后续 re-read 触发 decode-time `validate_terminal_event_refs_shape` 抛出 `HostRowDecodeError`。
- `test_cancel_running_run_row_requires_empty_terminal_refs` (`test_run_attempt_transitions.py:1570-1627`): 同上方向，针对 `status='running'` 的 corrupted row。

所有场景均为 test-only 构造（`PRAGMA ignore_check_constraints`），生产代码不包含 repair 逻辑或特殊 corruption 分支。CAS 通过 terminal refs/terminal_at 空值谓词拒绝 corrupted row，与 DDL CHECK 和 decode-time Python validation 的 fail-closed 语义一致。

### AC-07: HostRowDecodeError not leaked to public API docs/exports; stably wraps row decode failures preserving cause

**PASS**

- `HostRowDecodeError` 仅定义在 `dayu/host/durable/errors.py:38-62`，被 `dayu/host/durable/state.py` 使用。
- 未被 `dayu/host/durable/__init__.py` 或 `dayu/host/__init__.py` 导出。
- `dayu/host/README.md` public contract section (line 62) 的 public error types 列表不包含 `HostRowDecodeError`。
- `docs/host/design.md` 不将其列为 public API error。

Error wrapping 行为验证：
- Missing column: `_decode_scalar` (`state.py:725-742`) catches `KeyError` from `HostRow.get()`, raises `HostRowDecodeError` with `row_name`/`field_name`/`detail="missing column"` and `from exc` (line 738-742).
- Wrong scalar type: `_decode_required_text` (`state.py:745-764`) catches `HostDurableError` from `_require_text`, converts to `HostRowDecodeError` with `row_name`/`field_name`/`detail=str(exc)` and `from exc` (line 760-764). Same pattern for `_decode_optional_text`, `_decode_required_int`, `_decode_optional_int`.
- Unknown enum value: `_decode_enum` (`state.py:833-858`) catches `HostDurableError` from `deserializer()`, converts to `HostRowDecodeError`.
- Malformed terminal shape at decode time: `run_row_from_host_row` (`state.py:989-998`), `attempt_row_from_host_row` (`state.py:1028-1037`), `wait_record_row_from_host_row` (`state.py:1160-1163`) catch `HostDurableError` from `validate_terminal_event_refs_shape`/`validate_wait_terminal_at_shape`, convert via `_wrap_row_decode_shape_error` (field_name=None for row-level shape errors).

Test assertions confirm:
- `isinstance(error, HostDurableError)` — subclass compatibility preserved.
- `isinstance(error, HostRowDecodeError)` — specific type asserted.
- `error.row_name` / `error.field_name` — properties validated.
- `row_name` and (if applicable) `field_name` appear in error message.

### AC-08: README sync accurate and within scope

**PASS**

`dayu/host/README.md:297` durable foundation section:
> schema 按当前 fresh version 起库，版本不匹配时要求重建 durable DB；主连接与 secondary durable connections 都会执行当前 schema validation，校验 schema version、required object 存在性与 required object 定义一致性。

关键变更：将原来的 "校验 schema version、required object 存在性" 扩展为 "校验 schema version、required object 存在性与 required object 定义一致性"。这准确反映了 Slice 1 新增的 `_validate_required_object_definitions` 行为，且不包含实现细节（如 `sqlite_master.sql` 比较、normalization 策略等）。

未触发更新的文档：
- 根目录 `README.md`：无 public usage 变化
- `dayu/README.md`：无分层关系或边界变化
- `tests/README.md`：无测试约定变化
- 其他包 README：无受影响模块

### AC-09: No WU-LAYER-02 helper consolidation leakage, no public contract change, no layer violation, no Any/object/getattr/hasattr/lazy import/glue seam/compat wrapper

**PASS**

逐项验证：
- WU-LAYER-02 leakage: `_row_rules.py` 是 durable-private terminal shape rules，不是层中立 validation/redaction/JSON helper。`_validation.py` 不导入 `_row_rules.py`。无 Host durable 专用规则下沉到 `dayu.runtime`。
- Public contract: `dayu/host/__init__.py` 和 `dayu/host/api.py` 无新增导出。`HostRowDecodeError` 是 `dayu.host.durable` 内部类型。`_row_rules` 符号未出现在 durable `__init__.py`。
- Layer violation: `dayu/host/durable/` 不导入 `dayu.engine`、`dayu.service`、`dayu.ui`、`dayu.fins`。`_row_rules.py` 只导入 `dayu.host.api`（status enum）和 `dayu.host.durable.errors`。
- Any/object: `_row_rules.py` 无 `Any`/`object` 类型使用；`schema.py` 新增代码无 `Any`/`object`。
- hasattr/getattr: 无新增使用。
- Lazy import: 无。
- Glue seam: 无。
- Compat wrapper: 无。旧 `row.get(...)` 已替换为 `_decode_*` helper，不保留兼容分支。
- `HostRowDecodeError.__cause__`: 通过 `raise ... from exc` 保留原始异常链。

### AC-10: Row decode helpers preserve KeyError and HostDurableError cause chains

**PASS**

`_decode_scalar` (`state.py:735-742`):
```python
try:
    return row.get(column)
except KeyError as exc:
    raise HostRowDecodeError(...) from exc
```

`_decode_required_text` (`state.py:755-764`):
```python
try:
    return _require_text(...)
except HostRowDecodeError:
    raise  # 不解包已有 HostRowDecodeError
except HostDurableError as exc:
    raise HostRowDecodeError(...) from exc
```

`HostRowDecodeError` 穿透保持不变（标量 decode 失败已在上层被 wrap），其他 `HostDurableError`（如类型错误）被重新 wrap 为 `HostRowDecodeError` 并保留 cause。`_decode_enum` 中的 `HostDurableError` 来自 enum deserializer，同样被 wrap 并保留 cause。

## Open Questions

无阻塞性问题。

**OQ-01**: `_assert_host_row_decode_error` helper 在 `tests/host/test_state_schema.py` 和 `tests/host/test_wait_record_state.py` 中重复定义（F-01）。后续 WU-LAYER-02 shared helper consolidation 可考虑提取，但不要求当前 gate 修复。

## Verdict

**PASS** — 无 HIGH 或 MEDIUM 阻塞性 finding。

所有 adversarial checks 通过：
- Schema expected SQL 真源唯一（`HOST_DURABLE_DDL` → SQLite catalog SQL），无手写 DDL expectation drift。
- Current-version opener 对缺表/缺索引/同名错误定义均 fail closed 且不 repair；fresh bootstrap 不 false-positive。
- Slice 2 DDL CHECK 修改后在 Slice 1 schema definition validation 下同源一致，fresh bootstrap 不触发 mismatch。
- Terminal Run/Attempt/WaitRecord 的 DDL CHECK、Python validation、CAS WHERE、decode-time validation 规则同源于 `_row_rules.py` 常量。
- `_row_rules.py` durable-private，未 re-export，未污染 `_validation.py`，未成为 generic validation framework。
- Corrupted WaitRecord/Run CAS 场景均为 test-only 构造；CAS 不覆盖 corrupted row；行为与 `HostRowDecodeError` read boundary 一致。
- `HostRowDecodeError` 未 leak 到 public API docs/exports；稳定 wrap missing column/type/enum/terminal shape 并保留 cause。
- README sync 准确反映 schema validation 范围扩展，职责不越界。
- 无 WU-LAYER-02 helper consolidation 越界、无 public contract change、无 layer violation、无 Any/object/getattr/hasattr/lazy import/glue seam/compat wrapper。

验证基准：`pytest` 136 passed；`pyright` 0 errors, 0 warnings, 0 informations。
