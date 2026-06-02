# WU-LAYER-01 Durable Row Primitive / Type Owner Cleanup Plan

## 1. Goal / Motivation

本轮目标是完成 WU-LAYER-01 的 code-generation-ready implementation plan，只处理 durable row primitive、row decode 错误边界、schema invariant hardening 与 Run / Attempt / WaitRecord terminal shape 规则收口，不处理 WU-LAYER-02。

动机判断：成立，但范围必须收窄。直接证据显示 current-version DB 缺 required table / index 时 fail closed 已实现并已有测试覆盖，因此不能把“缺表 / 缺索引 opener 静默修复”当作未完成实现。真正剩余缺口是：

- schema validation 目前只验证 `PRAGMA user_version`、required tables 和 required indexes 存在，无法发现同名 table / index 的 DDL 定义错误。
- Run / Attempt / WaitRecord terminal shape 规则同时存在于 SQLite DDL CHECK、Python row validation / update validation、CAS `WHERE ... IS NULL` 条件中，状态值与 terminal refs 组合规则仍有漂移风险。
- row decode 通过 `HostRow.get(...)` 加 scalar helper 逐列读取；缺列会直接抛 `KeyError`，不是稳定 durable row decode 错误边界；malformed row decode 的 focused 测试不足。

第一性原理裁决：Host durable 是状态机治理数据库，不是 CRUD。保留显式 SQL、显式 transaction、typed row dataclass 是正确方向；本轮不引入 ORM，也不把 row dataclass 扩成 domain object。最小可维护方案是让 schema 定义、row decode、terminal shape validation 更同源，并以 focused tests 锁住已有行为边界。

## 2. Non-goals

- 不引入 ORM，不让 ORM 生成 schema、迁移或隐藏 CAS 条件。
- 不改变 `dayu.host` public contract、public exports、request / response dataclass 或 Service-facing behavior。
- 不创建兼容 re-export、wrapper 或 facade。
- 不把 durable row dataclass 扩展为承载业务行为的 domain object。
- 不改 Host durable canonical JSON、digest、timestamp truth owner。
- 不处理 WU-LAYER-02 的 shared helper consolidation，不把 Host durable 专用规则下沉到 `dayu.runtime`。
- 不修改 schema version，除非 implementation 直接证明 DDL 文本发生实际 schema 语义变更；本计划期望不改 `HOST_SCHEMA_VERSION`。
- 不为旧库兼容读取或迁移；schema 仍按当前 fresh version 起库。

## 3. Direct Evidence / Code References

总控与设计真源：

- `docs/host/host-core-followup-implementation-control.md:593` 定义 WU-LAYER-01。
- `docs/host/host-core-followup-implementation-control.md:597` 明确 Host durable 是状态机治理数据库，保留显式 SQL / 轻量 Data Mapper。
- `docs/host/host-core-followup-implementation-control.md:601` 到 `docs/host/host-core-followup-implementation-control.md:604` 要求保留显式 SQL、typed durable row dataclass，并收敛 row primitive / validation owner / schema CHECK / terminal CAS null-check。
- `docs/host/host-core-followup-implementation-control.md:608` 到 `docs/host/host-core-followup-implementation-control.md:611` 明确不引入 ORM、不改 public contract、不做兼容 re-export、不把 row dataclass 变成 domain object。
- `docs/host/host-core-followup-implementation-control.md:615` 到 `docs/host/host-core-followup-implementation-control.md:618` 是验收信号。
- `docs/host/design.md:45` 到 `docs/host/design.md:59` 固定 Host 内部 owner 边界；State Transition 是 Run / Attempt 索引原子更新 owner。
- `docs/host/design.md:1199` 到 `docs/host/design.md:1209` 固定 public API / internal API 分层，不暴露 durable row。
- `docs/host/design.md:2200` 到 `docs/host/design.md:2225` 定义 wait record 是 Host durable state index，字段必须是 typed refs，不能塞 metadata bag。
- `docs/host/design.md:2947` 到 `docs/host/design.md:2953` 定义 startup recovery 对 Run / Attempt 终态与 recovery 的状态机边界。

已覆盖项，不作为本轮 implementation 缺口：

- `dayu/host/durable/schema.py:1253` 到 `dayu/host/durable/schema.py:1280`：`bootstrap_host_durable_store` 对 fresh DB bootstrap，current version 只 validate，不做 repair。
- `dayu/host/durable/schema.py:1283` 到 `dayu/host/durable/schema.py:1305`：`validate_host_durable_schema` 当前校验 user_version、required tables、required indexes。
- `dayu/host/durable/schema.py:1332` 到 `dayu/host/durable/schema.py:1372`：缺 table / index 时抛 `HostSchemaMismatchError`。
- `tests/host/test_durable_schema.py:376` 到 `tests/host/test_durable_schema.py:433`：opener 缺 required table / index fail closed 且不修复。
- `tests/host/test_durable_schema.py:436` 到 `tests/host/test_durable_schema.py:485`：secondary connection 缺 required table / index fail closed 且不修复。
- `tests/host/test_durable_schema.py:488` 到 `tests/host/test_durable_schema.py:510`：`HOST_DURABLE_TABLES` / `HOST_DURABLE_INDEXES` 与 `HOST_DURABLE_DDL` 中 CREATE TABLE / CREATE INDEX 名称保持同源。

真实剩余缺口证据：

- `dayu/host/durable/schema.py:1286` 当前 docstring 明确 validation 范围只有 version、required tables、required indexes。
- `dayu/host/durable/schema.py:1320` fresh bootstrap 执行 `HOST_DURABLE_DDL`；但 current-version validation 没有比较同名 object 的 `sqlite_master.sql` 定义。
- `dayu/host/durable/schema.py:347` 到 `dayu/host/durable/schema.py:439`：Run terminal CHECK 直接写在 DDL 文本中。
- `dayu/host/durable/schema.py:442` 到 `dayu/host/durable/schema.py:485`：Attempt terminal CHECK 直接写在 DDL 文本中。
- `dayu/host/durable/schema.py:635` 到 `dayu/host/durable/schema.py:667`：WaitRecord terminal_at CHECK 直接写在 DDL 文本中。
- `dayu/host/durable/state.py:4259` 到 `dayu/host/durable/state.py:4307`：Run insert validation 另行维护 terminal refs 规则。
- `dayu/host/durable/state.py:4310` 到 `dayu/host/durable/state.py:4332`：Attempt insert validation 另行维护 terminal refs 规则。
- `dayu/host/durable/state.py:4595` 到 `dayu/host/durable/state.py:4638`：Run / Attempt terminal update validation 只校验 terminal refs 输入非空。
- `dayu/host/durable/state.py:4951` 到 `dayu/host/durable/state.py:4955`：WaitRecord terminal_at Python validation 另行维护。
- `dayu/host/durable/state.py:1799` 到 `dayu/host/durable/state.py:1802`、`dayu/host/durable/state.py:2440` 到 `dayu/host/durable/state.py:2442` 等多处 CAS `WHERE` 条件重复写 terminal null-check。
- `dayu/host/durable/state.py:742` 到 `dayu/host/durable/state.py:774`、`dayu/host/durable/state.py:777` 到 `dayu/host/durable/state.py:797`、`dayu/host/durable/state.py:841` 到 `dayu/host/durable/state.py:894`：row decode 逐列 `row.get(...)`，缺列时 `HostRow.get` 会按 `dayu/host/durable/transaction.py:112` 到 `dayu/host/durable/transaction.py:123` 抛 `KeyError`。
- `tests/host/test_state_schema.py:514` 到 `tests/host/test_state_schema.py:590` 只覆盖 row codec round-trip。
- `tests/host/test_wait_record_state.py:670` 到 `tests/host/test_wait_record_state.py:737` 只覆盖 WaitRecord invalid status；缺列、错类型、terminal shape malformed row decode 边界不足。

## 4. Affected Files / Modules

Implementation allowed files by slice are listed in section 8. Expected affected modules:

- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/errors.py`
- Optional new durable-private module: `dayu/host/durable/_row_rules.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_wait_record_state.py`
- Possibly `tests/host/test_durable_validation.py` only if scalar helper behavior changes.
- `dayu/host/README.md` only if implementation changes stable durable foundation description; see section 11.

## 5. Contract / Schema / State-machine / Public-interface Changes

- Public interface: no change. No new `dayu.host` public export, no request / response change, no public error contract change.
- Durable schema version: expected no change. DDL text should remain semantically identical unless helper extraction changes formatting only; fresh SQLite `sqlite_master.sql` expected values must be generated from current `HOST_DURABLE_DDL`.
- Durable schema validation behavior: strengthened for current-version DB. It must still fail closed on version mismatch, missing table, and missing index; additionally fail closed when required table / index name exists but its SQLite object definition differs from the definition generated by current `HOST_DURABLE_DDL`.
- State machine: no semantic state transition change. Terminal Run / Attempt / WaitRecord rules remain:
  - terminal Run statuses require `terminal_event_id`, `terminal_event_sequence`, `terminal_at`; non-terminal Run statuses require all three unset.
  - terminal Attempt statuses require `terminal_event_id`, `terminal_event_sequence`, `terminal_at`; non-terminal Attempt statuses require all three unset.
  - `WAITING` wait record requires `terminal_at IS NULL`; `RESOLVED` / `FAILED` / `CANCELLED` / `LOST` require `terminal_at IS NOT NULL`.
- Error boundary: add durable-internal row decode error type if selected below. It remains a subclass of `HostDurableError`, so existing callers catching `HostDurableError` continue to work without compatibility wrapper.

## 6. Implementation Decisions

### 6.1 Schema Invariant Hardening

Use generated SQLite catalog SQL, not raw hand-written expected strings.

Implementation decision:

- Keep `HOST_DURABLE_DDL` as the single DDL truth.
- Add private schema helpers in `dayu/host/durable/schema.py`:
  - `_expected_schema_sql_by_name() -> dict[tuple[str, str], str]` or equivalent typed structure. It creates an in-memory SQLite DB, executes current `HOST_DURABLE_DDL`, reads `sqlite_master.sql` for required table / index objects, and returns normalized SQL keyed by object type and name.
  - `_read_schema_sql_by_name(connection: sqlite3.Connection) -> dict[tuple[str, str], str]`.
  - `_normalize_schema_sql(sql: str) -> str` using the minimal normalization spec below, not semantic parsing.
  - `_validate_required_object_definitions(connection: sqlite3.Connection) -> None`.
- `validate_host_durable_schema` calls `_validate_required_object_definitions` after table / index existence checks.
- Compare only required user tables and required named indexes in `HOST_DURABLE_TABLES` / `HOST_DURABLE_INDEXES`; ignore `sqlite_sequence` and SQLite autoindexes.
- Error message should be structured and specific: `Host durable schema definition mismatch: table host_runs` or `... index host_runs_one_active_per_session`.
- `_normalize_schema_sql` minimal spec:
  - strip leading and trailing whitespace;
  - collapse every consecutive whitespace run to a single ASCII space;
  - preserve letter case exactly as SQLite returned it;
  - preserve identifier quoting exactly as SQLite returned it;
  - do not reorder clauses, parse SQL, lower/upper-case keywords, remove quotes, or normalize punctuation.
- If implementation evidence shows current SQLite output needs a broader normalization rule, stop and report back to controller instead of inventing a wider SQL normalizer inside implementation.

Reasoning:

- Comparing raw `HOST_DURABLE_DDL` text is brittle because SQLite rewrites `CREATE TABLE IF NOT EXISTS` / whitespace / capitalization in `sqlite_master.sql`.
- Comparing SQLite-generated expected catalog SQL from the same `HOST_DURABLE_DDL` is same-source, catches missing CHECK / wrong partial index / wrong columns, and avoids a second hand-maintained DDL string set.
- This is not a migration system and does not repair. It only makes current-version validation fail closed when object names are correct but definitions are not.

### 6.2 Terminal Shape Rule Owner

Use durable-private terminal shape helpers, not a generic framework.

Preferred implementation:

- Add `dayu/host/durable/_row_rules.py` as a small durable-private owner for terminal row shape rules only. It may import typed public status enums from `dayu.host.api` and `HostDurableError`, but must not import `dayu.engine`, `dayu.service`, `dayu.ui`, `dayu.fins`, or higher-layer modules.
- `_row_rules.py` responsibility boundary:
  - owns only terminal status constants, terminal refs SQL fragments, wait terminal-at SQL fragments, and terminal shape validation helpers;
  - does not own scalar type validation, digest validation, timestamp formatting/parsing, canonical JSON, row decode, transaction behavior, schema bootstrap, or public API validation;
  - is durable-private and must not be re-exported from `dayu/host/durable/__init__.py`.
- `_validation.py` responsibility boundary:
  - owns only durable-private scalar validation and scalar conversion helpers such as required/optional text, integer and digest validation;
  - must not import `_row_rules.py` and must not learn Run / Attempt / WaitRecord state-machine terminal rules.
- Define typed constants:
  - `TERMINAL_RUN_STATUS_VALUES: tuple[str, ...]`
  - `TERMINAL_ATTEMPT_STATUS_VALUES: tuple[str, ...]`
  - `WAIT_RECORD_TERMINAL_STATUS_VALUES: tuple[str, ...]`
  - `WAIT_RECORD_WAITING_STATUS_VALUE: str`
- Define private helper functions with full Chinese docstrings:
  - `sql_string_list(values: tuple[str, ...]) -> str`
  - `terminal_event_refs_required_check_sql(...) -> str`
  - `terminal_event_refs_unset_check_sql(...) -> str`
  - `terminal_event_refs_unset_where_sql(...) -> str`
  - `validate_terminal_event_refs_shape(..., is_terminal: bool, owner_label: str) -> None`
  - `validate_wait_terminal_at_shape(status: WaitRecordStatus, terminal_at: str | None) -> None`
- `schema.py` uses the SQL helpers for Run / Attempt / WaitRecord DDL CHECK fragments. This keeps DDL CHECK generated from the same terminal status constants used by Python validation.
- `state.py` uses validation helpers for:
  - Run insert/decode terminal shape validation.
  - Attempt insert/decode terminal shape validation.
  - WaitRecord decode/insert/update terminal shape validation.
- `state.py` uses `terminal_event_refs_unset_where_sql(...)` constants for repeated CAS `WHERE terminal_event_id IS NULL AND terminal_event_sequence IS NULL AND terminal_at IS NULL` fragments. For WaitRecord terminal updates, include `AND terminal_at IS NULL` alongside `status = waiting` to make the null precondition explicit and aligned with DDL/Python validation.
- Slice dependency: Slice 2 changes DDL CHECK generation and therefore depends on Slice 1 schema definition validation. After Slice 2 modifies Run / Attempt / WaitRecord DDL CHECK fragments, implementation must rerun Slice 1 schema definition validation tests. If generated SQL text changes, the implementation report must prove fresh bootstrap and expected SQL are still same-source from `HOST_DURABLE_DDL`, and current-version opener does not false-positive on a freshly bootstrapped DB.

Alternative rejected:

- Do not introduce a generic validation framework or dataclass domain object. The helper module owns only terminal row shape constants and SQL fragments; it is not a repository-wide seam and does not abstract arbitrary validation.

### 6.3 Row Decode Error Stabilization

Add `HostRowDecodeError`, subclassing `HostDurableError`.

Decision:

- Add `HostRowDecodeError(HostDurableError)` in `dayu/host/durable/errors.py`.
- It should carry `row_name: str` and `field_name: str | None` properties and accept a diagnostic message. Keep it internal durable error, not public API.
- In `state.py`, add module-level private row decode helpers:
  - `_decode_scalar(row: HostRow, *, row_name: str, column: str) -> SQLiteScalar`
  - `_decode_required_text(...) -> str`
  - `_decode_optional_text(...) -> str | None`
  - `_decode_required_int(...) -> int`
  - `_decode_optional_int(...) -> int | None`
  - `_decode_enum(...)` only if it remains narrowly typed without `Any` / `object`; otherwise call existing enum deserializers inside a `try` block and wrap `HostDurableError`.
- `_decode_*` helper error wrapping requirements:
  - catch `KeyError` raised by `HostRow.get(...)` for missing columns and convert it to `HostRowDecodeError`;
  - catch `HostDurableError` raised by scalar helpers such as `_require_text`, `_optional_text`, `_require_int`, `_optional_int` and convert it to `HostRowDecodeError`;
  - catch `HostDurableError` raised by enum deserializers or terminal shape validators and convert it to `HostRowDecodeError`;
  - preserve `row_name` and `field_name` on the raised `HostRowDecodeError`; for row-level shape failures without one column owner, set `field_name=None` and include the affected row name in the message;
  - keep the original exception as `__cause__` with `raise ... from exc`.
- Replace direct `row.get(...)` inside `session_row_from_host_row`, `session_slot_row_from_host_row`, `run_row_from_host_row`, `attempt_row_from_host_row`, `dispatch_record_row_from_host_row`, and `wait_record_row_from_host_row`.
- Row decode failures that must become `HostRowDecodeError`:
  - missing required selected column;
  - required column stored as wrong SQLite scalar type;
  - unknown enum status value;
  - malformed terminal shape in decoded Run / Attempt / WaitRecord.

Reasoning:

- Reusing `HostDurableError` alone is too broad for the WU acceptance signal “row decode / encode 失败有稳定错误类型和测试”。
- A subclass preserves existing broad catch behavior while giving tests and diagnostics a stable row decode boundary.

## 7. Exact Change Rules

- All new/modified functions and classes must have complete Chinese docstrings including 参数、返回值、异常.
- Do not use `Any`, `object`, untyped params, or untyped returns.
- Do not use `hasattr` / `getattr` for row decode. Decode must go through typed `HostRow` / scalar helpers.
- Do not add lazy imports.
- Do not use stringly `extra payload`.
- SQL string constants are allowed where they are schema/CAS SQL; status value lists should be generated from typed enum values, not repeated manually.
- Keep module dependencies one-way:
  - `_row_rules.py` may depend on `dayu.host.api` and `dayu.host.durable.errors`.
  - `schema.py` and `state.py` may depend on `_row_rules.py`.
  - `_row_rules.py` must not import `schema.py` or `state.py`.
- Do not change canonical JSON / digest / timestamp helpers.

## 8. Small Implementation Slices

### Slice 1: Schema Definition Validation

Allowed files:

- `dayu/host/durable/schema.py`
- `tests/host/test_durable_schema.py`
- `dayu/host/README.md` only if README sync is required after implementation; otherwise leave unchanged and state reason in report.

Exact changes:

- Add generated expected SQLite catalog SQL helpers in `schema.py`.
- Extend `validate_host_durable_schema` docstring and implementation to validate required object definitions.
- Add tests:
  - current-version DB with same required index name but wrong index definition fails opener without repair.
  - current-version DB with same required table name but mutated `sqlite_master.sql` definition fails opener without repair.
  - secondary connection with definition mismatch fails without repair.
  - freshly bootstrapped DB validates cleanly against generated expected SQL and does not false-positive after normalization.
  - fresh bootstrap still succeeds and existing table/index existence tests still pass.
- Keep existing missing table/index tests unchanged except expected docstring wording if needed.

Expected assertions:

- Raised type is `HostSchemaMismatchError`.
- Error message names object type and object name.
- After failure, wrong object definition remains wrong; validation does not drop/recreate/repair.
- `_normalize_schema_sql` tests prove only leading/trailing whitespace and consecutive whitespace are normalized; case changes, identifier quote changes, clause changes, and punctuation changes are not silently normalized away.

### Slice 2: Terminal Shape Rule Owner

Allowed files:

- `dayu/host/durable/_row_rules.py`
- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_wait_record_state.py`
- `tests/host/test_run_attempt_transitions.py` only if CAS SQL behavior tests need adjustment.
- `dayu/host/README.md` only if README sync is required after implementation.

Exact changes:

- Add durable-private terminal status / terminal refs helper module.
- Generate Run / Attempt / WaitRecord DDL CHECK fragments from helper constants.
- Replace repeated Run / Attempt terminal shape Python validation with helper calls.
- Replace repeated CAS terminal null-check SQL fragments with helper-generated constants.
- Add explicit `terminal_at IS NULL` CAS predicate to wait record terminal update paths where the source status is `waiting`.
- Add tests:
  - DDL CHECK still rejects terminal Run missing one terminal ref and non-terminal Run carrying any terminal ref.
  - DDL CHECK still rejects terminal Attempt missing one terminal ref and non-terminal Attempt carrying any terminal ref.
  - WaitRecord DDL/Python/CAS agree on waiting vs terminal `terminal_at`.
  - Corrupted wait record scenario: construct a test-only row with `status='waiting'` and `terminal_at IS NOT NULL`, then invoke a wait terminal CAS path and assert the CAS is rejected and classified as `CAS_LOST` or `INVALID_STATE`. The corruption setup must be explicitly test-only, for example via direct SQLite mutation under test control or `PRAGMA writable_schema` / constraint bypass if needed; production code must not add repair logic or a special corruption branch.
  - Existing transition tests still pass.
  - Slice 1 schema definition validation tests are rerun after Slice 2 DDL CHECK helper extraction.

Expected assertions:

- No behavior change for valid transitions.
- Invalid terminal shapes fail before commit through either Python validation or SQLite CHECK, depending on path.
- CAS-lost classification remains unchanged except where a corrupted row with `status=waiting` and non-null `terminal_at` is now explicitly excluded by CAS predicate.
- If Slice 2 changes generated SQL text, the Slice 2 implementation report must show fresh bootstrap and expected SQL remain same-source from `HOST_DURABLE_DDL`, and `open_host_durable_store` does not raise schema mismatch on a fresh DB.

### Slice 3: Row Decode Error Boundary

Allowed files:

- `dayu/host/durable/errors.py`
- `dayu/host/durable/state.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_wait_record_state.py`
- `tests/host/test_durable_validation.py` only if scalar helper tests are affected.

Exact changes:

- Add `HostRowDecodeError`.
- Add row decode private helpers in `state.py`.
- Replace direct `row.get(...)` in durable state row conversion functions.
- Add decode-time terminal shape checks for Run / Attempt / WaitRecord.
- Add tests:
  - `run_row_from_host_row` missing `status` column raises `HostRowDecodeError`, not `KeyError`.
  - `run_row_from_host_row` status stored as integer raises `HostRowDecodeError`.
  - `run_row_from_host_row` terminal status missing `terminal_at` raises `HostRowDecodeError`.
  - `attempt_row_from_host_row` terminal status missing terminal refs raises `HostRowDecodeError`.
  - `wait_record_row_from_host_row` missing `terminal_at` column raises `HostRowDecodeError`.
  - `wait_record_row_from_host_row` `waiting` with terminal_at or `resolved` without terminal_at raises `HostRowDecodeError`.
  - Existing invalid status tests either assert `HostRowDecodeError` specifically or continue to pass via subclass of `HostDurableError`; prefer specific assertion for new row decode boundary.

Expected assertions:

- `isinstance(error, HostDurableError)` remains true.
- `isinstance(error, HostRowDecodeError)` is true for malformed row decode.
- Error message includes row name and field name where applicable.

### Slice 4: Integration Verification / README Sync

Allowed files:

- `dayu/host/README.md` only if stable durable foundation description is now incomplete.
- No source changes unless verification exposes a slice regression; fixes must stay in files owned by Slice 1 to 3.

Exact changes:

- Inspect `dayu/host/README.md` durable foundation section after code changes.
- If it still says “主连接与 secondary durable connections 都会执行完整当前 schema validation” and remains accurate enough, do not edit README.
- If implementation adds stable behavior worth documenting, update only the durable foundation bullet to say current schema validation checks version、required object existence and required object definitions, without implementation details.
- Do not update root README, `dayu/README.md`, or `tests/README.md` unless implementation unexpectedly changes public usage, layering, or test conventions.

## 9. Tests / Validation Commands

Run from repository root:

```bash
source .venv/bin/activate
pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_run_attempt_transitions.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py
pyright
```

Minimum expected assertions:

- All listed pytest files pass.
- `pyright` reports 0 errors and no new warnings/errors.
- Existing missing table/index fail-closed tests continue to pass.
- New same-name wrong table/index definition tests fail closed and do not repair.
- Slice 2 reruns Slice 1 schema definition validation tests after DDL CHECK helper extraction; freshly bootstrapped DB must not trigger schema definition mismatch.
- Corrupted wait record with `status=waiting` and non-null `terminal_at` is rejected by terminal CAS and classified as `CAS_LOST` or `INVALID_STATE` through a test-only setup.
- New malformed row tests raise `HostRowDecodeError`.
- Existing Run / Attempt / WaitRecord valid transition tests continue to pass.

If implementation touches only Slice 1 and no state files, `test_durable_schema.py` plus `pyright` is the smallest local loop, but final validation must run the full command above.

## 10. Review Gates

- Plan review gate: reviewers must verify this plan does not reimplement already-covered missing table/index fail-closed behavior and does not expand into WU-LAYER-02.
- Slice review gate: each implementation slice must include exact changed files, test command output, and whether README sync was checked.
- Aggregate review gate: require independent review focused on:
  - schema expected SQL generation is actually same-source with `HOST_DURABLE_DDL`;
  - Slice 2 reran Slice 1 definition validation coverage after DDL CHECK extraction;
  - no raw hand-written DDL expectation drift;
  - terminal rules are not hidden behind overbroad abstraction;
  - corrupted wait record CAS scenario exists and is test-only;
  - `_row_rules.py` remains durable-private and is not re-exported from `dayu/host/durable/__init__.py`;
  - `HostRowDecodeError` does not leak into public API docs or exports;
  - row decode helpers wrap both `KeyError` and scalar-helper `HostDurableError` into `HostRowDecodeError`;
  - no layer violation or runtime helper migration.

## 11. README / Doc Sync Decision

Because implementation will touch `dayu/host/durable/*`, the implementation agent must check `dayu/host/README.md`.

Current evidence: `dayu/host/README.md` durable foundation section says schema uses current fresh version and both primary / secondary durable connections execute full current schema validation. If schema validation is strengthened to include required object definitions, this statement remains directionally true. README update is required only if the implementation makes that stable behavior materially more specific in a way the Host developer manual should expose.

Expected decision: likely update one durable foundation bullet to mention “required object existence and definition validation” if reviewers consider the stronger validation a stable durable foundation guarantee. Do not update root README or `dayu/README.md`.

This plan file itself is the only document written in the current planning gate.

## 12. Stop Conditions

Stop implementation and return to controller/user if any condition appears:

- Comparing generated `sqlite_master.sql` proves unstable across the same process / same SQLite version in normal tests.
- Schema definition validation requires schema migration, compatibility reads, or changing `HOST_SCHEMA_VERSION`.
- Terminal rule helper starts becoming generic validation framework or requires moving Host durable semantics to `dayu.runtime`.
- Row decode stabilization requires changing public Host API errors or public exports.
- Existing transition tests reveal a real behavior mismatch between DDL CHECK and state.py that cannot be resolved without state-machine design change.
- Any change would require handling WU-LAYER-02 helper consolidation.

## 13. Risks / Open Questions

- `sqlite_master.sql` comparison relies on SQLite catalog SQL generated by the same interpreter/runtime. This should be stable within a process, but tests must prove it for current Python 3.11 sqlite3.
- Table definition mismatch test may need `PRAGMA writable_schema=ON` to simulate corrupted same-name table DDL without writing a full alternate schema. This is acceptable for validator tests but should be clearly scoped to tests.
- Adding explicit `terminal_at IS NULL` to WaitRecord CAS predicates should be behavior-preserving for valid rows; if a corrupted row violates DDL invariant, CAS classification may shift from updated to CAS lost / invalid. That is acceptable fail-closed behavior but must be recorded in implementation report.
- `HostRowDecodeError` subclasses `HostDurableError`; tests that currently expect broad `HostDurableError` should remain valid, but focused row decode tests should assert the specific subtype.

Blocking open questions: none.

## 14. Completion Report Format

Implementation agent final report must include:

```text
改了什么：
- Slice N: <files> <behavior>

验证了什么：
- <pytest command>: <passed count / result>
- pyright: <0 errors or exact result>

README/doc sync：
- dayu/host/README.md: updated / checked-no-change, with reason

风险或未覆盖项：
- <remaining risk or none>
```
