# WU-LAYER-01 Aggregate Deepreview

## 审查范围

跨 Slice 1-4 adversarial review，覆盖 WU-LAYER-01 全部 accepted commits：

- Slice 1 (02396e5): Schema Definition Validation
- Slice 2 (ff64f0b): Terminal Shape Rule Owner
- Slice 3 (b4fc923): Row Decode Error Boundary
- Slice 4 (2397e72): Integration Verification / README Sync

## Findings Ordered by Severity

### No blocking findings.

## Adversarial Checks

### AC-01: Schema expected SQL generation 是否真正同源于 `HOST_DURABLE_DDL`

**结论: PASS**

`_expected_schema_sql_by_name()` (schema.py:1437) 创建内存 fresh SQLite DB，执行当前 `HOST_DURABLE_DDL`，从 `sqlite_master.sql` 读取 catalog SQL。expected SQL 唯一真源是 `HOST_DURABLE_DDL`；没有手写 DDL expectation。

`_normalize_schema_sql()` 只做最小归一化：strip leading/trailing whitespace、collapse consecutive whitespace runs。不重排 clause、不改 case、不去引号。归一化范围由 `_WHITESPACE_RUN_PATTERN` 控制。

`_validate_required_object_definitions()` (schema.py:1412) 比较 `HOST_DURABLE_TABLES` 与 `HOST_DURABLE_INDEXES` 指定的对象，忽略 `sqlite_sequence` 和 SQLite autoindexes。

无 DDL expectation drift 风险。

### AC-02: Current-version opener 对缺表、缺索引、同名错误 table/index definition 都 fail closed 且不 repair

**结论: PASS**

测试覆盖：

- `test_current_schema_missing_table_opener_raises_without_repair` (test_durable_schema.py): 缺 required table 时抛 `HostSchemaMismatchError`，不修复。
- `test_current_schema_missing_index_opener_raises_without_repair` (test_durable_schema.py): 缺 required index 时抛 `HostSchemaMismatchError`，不修复。
- `test_current_schema_wrong_index_definition_opener_raises_without_repair` (test_durable_schema.py): 同名 index 定义错误时抛 `HostSchemaMismatchError`，不修复。
- `test_current_schema_mutated_table_definition_opener_raises_without_repair` (test_durable_schema.py): 同名 table catalog SQL 变异时抛 `HostSchemaMismatchError`，不修复。

Fresh bootstrap 不 false-positive：`test_fresh_bootstrap_validates_cleanly_against_generated_expected_sql` 证明 freshly bootstrapped DB 通过 schema definition validation。

### AC-03: Slice 2 修改 DDL CHECK 后是否重新覆盖 Slice 1 schema definition validation

**结论: PASS**

Slice 2 将 Run / Attempt / WaitRecord DDL CHECK 片段改为从 `_row_rules.py` 生成。DDL CHECK SQL 常量定义在 schema.py:173-198，引用 `_row_rules.py` 的 `terminal_event_refs_required_check_sql`、`terminal_event_refs_unset_check_sql`、`wait_terminal_at_check_sql`。

Slice 1 的 schema definition validation 测试在 Slice 2 后仍然通过（aggregate pytest 136 passed），证明 DDL CHECK helper 提取后 generated SQL 与 fresh bootstrap 仍同源。

### AC-04: Terminal Run/Attempt/WaitRecord 的 DDL CHECK、Python validation、CAS WHERE、decode-time validation 是否同源一致

**结论: PASS**

同源机制：

- `TERMINAL_RUN_STATUS_VALUES` / `TERMINAL_ATTEMPT_STATUS_VALUES` / `WAIT_RECORD_TERMINAL_STATUS_VALUES` 定义在 `_row_rules.py`。
- `schema.py` 从 `_row_rules.py` import 这些常量生成 DDL CHECK SQL。
- `state.py` 从 `_row_rules.py` import 同一组常量构建 `TERMINAL_RUN_STATUSES` / `_TERMINAL_ATTEMPT_STATUSES`。
- `validate_terminal_event_refs_shape()` 定义在 `_row_rules.py`，同时被 `state.py` 的 insert validation 和 row decode validation 使用。
- `validate_wait_terminal_at_shape()` 定义在 `_row_rules.py`，被 `state.py` 的 WaitRecord decode validation 使用。
- CAS WHERE 使用 `wait_terminal_at_unset_where_sql()` 生成 `AND terminal_at IS NULL`，与 DDL CHECK `wait_terminal_at_check_sql` 和 Python `validate_wait_terminal_at_shape` 一致。

四处规则均从同一组 typed constants 和 helper functions 生成，无漂移空间。

### AC-05: `_row_rules.py` 是否 durable-private，未 re-export，未成为 generic validation framework

**结论: PASS**

- `dayu/host/durable/__init__.py` 不含 `_row_rules` 或 `row_rules` 引用（已 grep 确认）。
- `_row_rules.py` 只 import `dayu.host.api`（typed status enums）和 `dayu.host.durable.errors`（`HostDurableError`）。
- `_row_rules.py` 不 import `schema.py`、`state.py`、`_validation.py` 或任何上层模块。
- `_validation.py` 不 import `_row_rules.py`（已 grep 确认）。
- `_row_rules.py` 职责边界明确：只承载 terminal status constants、terminal refs SQL fragments、wait terminal-at SQL fragments 和 terminal shape validation helpers。不承载 scalar type validation、digest validation、timestamp formatting、row decode、schema bootstrap 或 public API validation。

未成为 generic validation framework，未污染 `_validation.py` 或 runtime。

### AC-06: Corrupted WaitRecord/Run CAS 场景是否 test-only，是否证明 CAS 不覆盖 corrupted row

**结论: PASS**

`test_wait_record_terminal_cas_rejects_corrupted_waiting_terminal_at` (test_wait_record_state.py:763)：

- 使用 `PRAGMA ignore_check_constraints=ON` 绕过 DDL CHECK 构造 `status='waiting'` + `terminal_at IS NOT NULL` 的 corrupted row。
- 执行 `mark_wait_record_resolved_row`，该函数的 CAS WHERE 包含 `AND terminal_at IS NULL`（来自 `_WAIT_TERMINAL_AT_UNSET_WHERE_SQL`）。
- Corrupted row 不匹配 CAS WHERE，CAS 未更新任何行。
- `mark_wait_record_resolved_row` 读取最终状态时触发 decode-time `validate_wait_terminal_at_shape`，抛出 `HostRowDecodeError`。
- 测试断言 `HostRowDecodeError` 且 `match="waiting wait record terminal_at"`。

Corruption 构造严格 test-only（`PRAGMA ignore_check_constraints`），production 代码无 repair 分支。CAS 不覆盖 corrupted row，与 `HostRowDecodeError` read boundary 一致。

### AC-07: `HostRowDecodeError` 是否未 leak 到 public API docs/exports

**结论: PASS**

- `HostRowDecodeError` 定义在 `dayu/host/durable/errors.py`。
- 仅被 `dayu/host/durable/state.py` import 使用。
- `dayu/host/__init__.py` 不含 `HostRowDecodeError`（已 grep 确认）。
- `dayu/host/durable/__init__.py` 不含任何 re-export（包 docstring 说明 "不属于 dayu.host 包根公共导出面"）。
- `dayu/host/README.md` public contract 列表不含 `HostRowDecodeError`。

`HostRowDecodeError` 是 `HostDurableError` 子类，existing callers catching `HostDurableError` 继续工作，无需兼容 wrapper。

### AC-08: Row decode helpers 是否 wrap both `KeyError` and scalar-helper `HostDurableError`

**结论: PASS**

`_decode_scalar()` (state.py:725): catch `KeyError` from `row.get()` → wrap to `HostRowDecodeError` with `__cause__`。

`_decode_required_text()` / `_decode_optional_text()` / `_decode_required_int()` / `_decode_optional_int()` (state.py:745-830): catch `HostRowDecodeError` (re-raise), catch `HostDurableError` (wrap to `HostRowDecodeError` with `__cause__`）。

`_decode_enum()` (state.py:833): catch `HostDurableError` from deserializer → wrap to `HostRowDecodeError` with `__cause__`。

`_wrap_row_decode_shape_error()` (state.py:861): row-level shape failures → `HostRowDecodeError` with `field_name=None`。

所有 decode helpers 正确保留 cause chain（`from exc`），`row_name` 和 `field_name` 在 raised error 上设置。

### AC-09: README sync 是否准确且职责不越界

**结论: PASS**

`dayu/host/README.md:297` 已写："主连接与 secondary durable connections 都会执行当前 schema validation，校验 schema version、required object 存在性与 required object 定义一致性。"

这准确反映了 Slice 1 加入的 schema definition validation 行为。未写实现细节、未写未来计划。根 README 和 `dayu/README.md` 未触及（符合触发规则：`dayu/host/` 修改只触发 `dayu/host/README.md`）。

### AC-10: 无 WU-LAYER-02 helper consolidation 越界

**结论: PASS**

- `_row_rules.py` 只承载 terminal shape rules，不是 shared validation / redaction / JSON helper。
- `_validation.py` 未被修改，未 import `_row_rules.py`。
- 无 Host durable 专用规则下沉到 `dayu.runtime`。
- 无 `dayu.runtime` import 变更。

### AC-11: 无 public contract change

**结论: PASS**

- 无新增 `dayu.host` public export。
- 无 request / response dataclass 变更。
- `HostRowDecodeError` 是 `HostDurableError` 子类，不改变 public error contract。
- DDL text 语义未变（只改变了 CHECK SQL 片段的生成方式，generated SQL 内容不变）。

### AC-12: 无 layer violation

**结论: PASS**

- `_row_rules.py` 只 import `dayu.host.api` 和 `dayu.host.durable.errors`。
- `schema.py` 和 `state.py` import `_row_rules.py`。
- 无反向依赖。
- 无 `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins` import。

### AC-13: 无 Any/object/getattr/hasattr/lazy import/glue seam/compat wrapper

**结论: PASS**

- `state.py` 中 `object` 出现仅在 docstring（"adapter object"），非类型注解。
- `schema.py` 中 `object` 出现仅在变量名 `_SchemaObjectKey` 和 docstring（"object type" / "object key"），非类型注解。
- `_row_rules.py` 无 `Any`、`object`、`getattr`、`hasattr`。
- 无 lazy import。
- 无 glue seam。
- 无 compat wrapper / facade / re-export。

## Validation

### Aggregate pytest

```bash
pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_run_attempt_transitions.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py -v
```

**Result: 136 passed in 1.16s**

### pyright

```bash
pyright
```

**Result: 0 errors, 0 warnings, 0 informations**

## Open Questions

None.

## Verdict

**PASS**

WU-LAYER-01 全部 4 slices 通过 aggregate deepreview。Schema definition validation 同源于 `HOST_DURABLE_DDL`；terminal shape rules 在 DDL CHECK、Python validation、CAS WHERE 和 decode-time validation 四处同源一致；`_row_rules.py` 保持 durable-private；`HostRowDecodeError` 未 leak 到 public API；corrupted WaitRecord CAS 场景 test-only 且 fail-closed；无 layer violation、无 public contract change、无编码硬约束违反。
