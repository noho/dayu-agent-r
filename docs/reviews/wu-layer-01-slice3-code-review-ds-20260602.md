# WU-LAYER-01 Slice 3 Row Decode Error Boundary — Code Review (DS)

## Review Metadata

- **Reviewer**: AgentDS (DeepSeek)
- **Reviewed slice**: WU-LAYER-01 Slice 3 — Row Decode Error Boundary
- **Design source**: `docs/host/design.md`
- **Control doc**: `docs/host/host-core-followup-implementation-control.md`
- **Plan**: `docs/host/wu-layer-01-durable-row-primitive-cleanup-plan.md`
- **Implementation report**: `docs/reviews/wu-layer-01-slice3-row-decode-error-boundary-codex-20260602.md`
- **Date**: 2026-06-02
- **Scope**: Current workspace uncommitted changes on `refactor/host-layer-followup-wu-layer-01-02`

## Changed Files (Reviewed)

- `dayu/host/durable/errors.py` — new `HostRowDecodeError` class
- `dayu/host/durable/state.py` — new `_decode_*` private helpers, all 6 row conversion functions migrated
- `tests/host/test_state_schema.py` — new Run/Attempt decode error boundary tests + helper
- `tests/host/test_wait_record_state.py` — new WaitRecord decode error boundary tests + helper, updated corrupted CAS test
- `docs/host/host-core-followup-implementation-control.md` — controller status update only (out of review scope for findings)

## Review Criteria

Per review request, the following criteria are examined:

| # | Criterion | Verdict |
|---|-----------|---------|
| 1 | `HostRowDecodeError` stable error boundary, inherits `HostDurableError`, preserves `__cause__` | PASS |
| 2 | `_decode_*` helpers truly replace direct `row.get`; missing column, type error, enum deserialize, terminal shape errors uniformly wrapped | PASS |
| 3 | Run/Attempt/WaitRecord decode-time terminal shape checks reuse Slice 2 rule owner; consistent with DDL/CAS semantics | PASS |
| 4 | No scope creep into schema DDL, schema validation, public API, runtime helper, or WU-LAYER-02 | PASS |
| 5 | New tests cover missing column, invalid type, invalid enum, terminal shape, corrupted wait CAS read boundary; Chinese docstrings per AGENTS | PASS |
| 6 | Type boundaries strict; no `Any`/`object`/`getattr`/`hasattr`/lazy import/glue seam/compatibility wrapper introduced | PASS |

---

## Findings

### HIGH Severity

None.

### MEDIUM Severity

None.

### LOW Severity

#### FIND-01 [LOW] `_assert_host_row_decode_error` 在两个测试文件间重复定义

**位置**:
- `tests/host/test_state_schema.py:984-1008`
- `tests/host/test_wait_record_state.py:914-935`

**证据**: 两个文件各有一份逐字相同的 `_assert_host_row_decode_error` 私有测试辅助函数。

**分析**: 如果将来断言语义需要变更（例如新增 `__cause__` 类型断言或 row name format 检查），需要同时修改两处。当前不造成正确性风险。

**裁决**: 记录但不要求当前 Slice 3 fix。两份 helper 分别服务不同 row type（Run/Attempt vs WaitRecord）的 decode 测试，遵循各自文件 self-contained 的测试约定；不引入共享 test builder 以避免不必要的跨文件测试耦合。未来若出现第三处复制或断言语义变更，可考虑提取为 `tests/host/_row_decode_assertions.py` 公共 helper。

---

## Verification Items (Adversarial Pass)

### 1. `HostRowDecodeError` 错误边界稳定性

- **继承链**: `HostRowDecodeError` → `HostDurableError` → `Exception`。existing broad `except HostDurableError` 调用方仍能捕获，不破坏向后兼容。 ✓
- **`__cause__` 保留**: 所有 `raise HostRowDecodeError(...) from exc` 路径均保留原始异常。运行时验证确认 `__cause__` 为原始 `KeyError`。 ✓
- **属性携带**: `row_name: str` 与 `field_name: str | None` 在所有构造点正确赋值。 ✓
- **错误消息格式化**: `_format_row_decode_error` 对 field 级和 row 级错误分别产生稳定格式 `Host durable row decode failed: row=<name> field=<field>: <detail>` / `Host durable row decode failed: row=<name>: <detail>`。 ✓
- **未泄漏到 public API**: `dayu/host/durable/__init__.py` 未 re-export `HostRowDecodeError`。 ✓

### 2. `_decode_*` 覆盖全部 row.get 替换

逐文件核对 6 个 row conversion 函数：

| Function | Direct `row.get` residues | Verdict |
|----------|---------------------------|---------|
| `session_row_from_host_row` | None | ✓ |
| `session_slot_row_from_host_row` | None | ✓ |
| `run_row_from_host_row` | None | ✓ |
| `attempt_row_from_host_row` | None | ✓ |
| `dispatch_record_row_from_host_row` | None | ✓ |
| `wait_record_row_from_host_row` | None | ✓ |

错误包装链验证：

- `KeyError` from `HostRow.get(column)` → `_decode_scalar` → `HostRowDecodeError` with `from exc` ✓
- `HostDurableError` from `_require_text`/`_require_int`/`_optional_text`/`_optional_int` → `_decode_required_text` etc → `HostRowDecodeError` with `from exc` ✓
- `HostDurableError` from `deserialize_*_status()` → `_decode_enum` → `HostRowDecodeError` with `from exc` ✓
- `HostDurableError` from `validate_terminal_event_refs_shape`/`validate_wait_terminal_at_shape` → `_wrap_row_decode_shape_error` → `HostRowDecodeError` with `field_name=None` ✗ (see below)
- `HostDurableError` from `_optional_source_run_relation`/`_wait_adapter_key_from_text`/`deserialize_external_job_ref`/`deserialize_wait_snapshot_ref` → manual `HostRowDecodeError` with `from exc` ✓

关于 `_wrap_row_decode_shape_error` 的 `from exc` 保留：检查调用点（Run line 998、Attempt line 1037、WaitRecord line 1162），均使用 `raise _wrap_row_decode_shape_error(...) from exc`。`_wrap_row_decode_shape_error` 返回 `HostRowDecodeError` 实例但不 `raise` 它——返回后由调用方 `raise ... from exc`。因此 `__cause__` 在调用方正确设置，而非在 `_wrap_row_decode_shape_error` 内部丢失。 ✓

### 3. Slice 2 Rule Owner 复用

- `state.py:44-45` 从 `dayu/host/durable/_row_rules` import `validate_terminal_event_refs_shape` 和 `validate_wait_terminal_at_shape`。 ✓
- `run_row_from_host_row:994` 使用 `_is_terminal_run_status(run_row.status)` 判断终态——该函数定义在 `state.py:5499-5506`，使用 Slice 2 `_row_rules` 的 `TERMINAL_RUN_STATUSES` 常量。 ✓
- `attempt_row_from_host_row:1033` 使用 `attempt_row.status in _TERMINAL_ATTEMPT_STATUSES`——该常量在 `state.py:76` 从 Slice 2 `TERMINAL_ATTEMPT_STATUS_VALUES` 构造。 ✓
- `wait_record_row_from_host_row:1161` 使用 `validate_wait_terminal_at_shape` 直接调用。 ✓
- DDL/CAS 一致性：`validate_terminal_event_refs_shape` 要求 terminal Run/Attempt 同时具有 terminal_event_id + terminal_event_sequence + terminal_at，非 terminal 三者全空——与 DDL CHECK 和 CAS `WHERE IS NULL` 条件语义一致。`validate_wait_terminal_at_shape` 要求 waiting 时 terminal_at=None，terminal 时 terminal_at≠None——与 DDL CHECK 和 CAS 条件一致。 ✓

### 4. Scope Boundary 检查

- **Schema DDL**: 未修改 `schema.py`。 ✓
- **Schema version**: 未修改 `HOST_SCHEMA_VERSION`。 ✓
- **Schema validation**: 未修改 `validate_host_durable_schema`。 ✓
- **Public API**: 未修改 `dayu/host/__init__.py`、`dayu/host/api.py` 或任何 public export。 ✓
- **Runtime helper**: 未修改 `dayu/runtime/` 下任何文件。 ✓
- **WU-LAYER-02**: 未触及 shared helper consolidation。 ✓
- **`_validation.py`**: 未修改 scalar helper 签名或行为。 ✓
- **`_row_rules.py`**: 未修改（Slice 2 artifact）。 ✓

### 5. 测试覆盖矩阵

| 场景 | 测试函数 | 文件 | 断言类型 | 覆盖 |
|------|---------|------|---------|------|
| Run 缺 status 列 | `test_run_row_decode_missing_status_column_raises_row_decode_error` | test_state_schema.py | `HostRowDecodeError`, `field_name="status"` | ✓ |
| Run status 为 integer | `test_run_row_decode_integer_status_raises_row_decode_error` | test_state_schema.py | `HostRowDecodeError`, `field_name="status"` | ✓ |
| Run 终态缺 terminal_at | `test_run_row_decode_terminal_missing_terminal_at_raises_row_decode_error` | test_state_schema.py | `HostRowDecodeError`, `field_name=None` | ✓ |
| Attempt 终态缺 refs | `test_attempt_row_decode_terminal_missing_refs_raises_row_decode_error` | test_state_schema.py | `HostRowDecodeError`, `field_name=None` | ✓ |
| WaitRecord invalid status | `test_wait_record_row_from_host_row_rejects_invalid_status` | test_wait_record_state.py | `HostRowDecodeError`, `field_name="status"`, `match="WaitRecordStatus"` | ✓ |
| WaitRecord 缺 terminal_at 列 | `test_wait_record_row_decode_missing_terminal_at_column_raises_row_decode_error` | test_wait_record_state.py | `HostRowDecodeError`, `field_name="terminal_at"` | ✓ |
| WaitRecord waiting 有 terminal_at | `test_wait_record_row_decode_terminal_at_shape_raises_row_decode_error` | test_wait_record_state.py | `HostRowDecodeError`, `field_name=None`, `match="waiting wait record terminal_at"` | ✓ |
| WaitRecord resolved 缺 terminal_at | `test_wait_record_row_decode_terminal_at_shape_raises_row_decode_error` | test_wait_record_state.py | `HostRowDecodeError`, `field_name=None`, `match="terminal wait record requires terminal_at"` | ✓ |
| Corrupted wait CAS 读边界 | `test_wait_record_terminal_cas_rejects_corrupted_waiting_terminal_at` | test_wait_record_state.py | `HostRowDecodeError`, `field_name=None` | ✓ |

所有新增/更新测试的中文 docstring 均包含 `:param`、`:returns`、`:raises`，符合 AGENTS.md 要求。测试 helper `_run_host_row`、`_attempt_host_row`、`_wait_record_host_row` 均具备完整中文 docstring。 ✓

### 6. 类型边界

- 无 `Any` 类型。所有函数返回类型均为具体类型或 `str | None` / `int | None`。 ✓
- 无 `object` 类型。 ✓
- 无 `hasattr` / `getattr` 调用。 ✓
- 无 lazy import。新增 `Callable` import 来自 `collections.abc`，是标准库常规导入。 ✓
- 无胶水 seam、兼容 re-export 或 wrapper。 ✓
- `_decode_enum` 使用 `Callable[[str], _StatusT]` 泛型约束 deserializer，类型安全。 ✓

### Adversarial Failure Pass

以下 adversarial scenarios 已检查：

1. **`_decode_scalar` 在 `row.get` 抛 `KeyError` 之外的其他异常时** → `KeyError` 是 `HostRow.get` 唯一文档化异常，不处理 → 不捕获不存在的异常是正确的。

2. **Scalar helper 抛非 `HostDurableError` 异常** → `_decode_required_text` 等只 catch `HostDurableError`，其他异常（如内存错误）会被正确传播 → 符合设计意图，不静默吞异常。

3. **Enum deserializer 抛非 `HostDurableError`** → `_decode_enum` 只 catch `HostDurableError`。所有现有 deserializer（`deserialize_run_status` 等）均通过 `_require_enum_value` 抛 `HostDurableError` → 安全。

4. **`_wrap_row_decode_shape_error` 被调用但 `raise` 时未用 `from exc`** → 检查所有 3 处调用点，均使用 `raise _wrap_row_decode_shape_error(...) from exc` → `__cause__` 正确保留。

5. **重复 `row.get` 遗漏** → 使用 `rg 'row\.get\(' dayu/host/durable/state.py` 验证：6 个 row conversion 函数中无残留直接 `row.get`。其他函数中的 `row.get` 属于 non-decode paths（如计数查询、辅助投影），不在 Slice 3 scope。 → 不越界。

6. **错误消息注入** → `_format_row_decode_error` 使用固定前缀 + row_name/field_name（来自代码内 TABLE_* 常量，非用户输入）+ detail（来自内部错误消息）。不存在用户输入注入路径。 ✓

---

## Open Questions

无阻断性开放问题。

| # | Question | Status |
|---|----------|--------|
| OQ-01 | `_is_terminal_run_status` 定义在 `state.py:5499` 而非 `_row_rules.py`——是否应在后续 slice 将其与 `_row_rules` 其他 terminal status helper 统一 owner？ | Not blocking for Slice 3。该函数依赖 `TERMINAL_RUN_STATUSES`（来自 `_row_rules`），当前 owner 是 state.py 内部逻辑，不影响 correctness。可作为 WU-LAYER-02 或后续维护的 low-priority cleanup item。 |
| OQ-02 | `docs/host/host-core-followup-implementation-control.md` 有未提交的 controller 状态更新——是否需要 commit 前先确认 controller 已同步？ | Not blocking for review。控制文档状态更新是 controller 职责，不影响代码 correctness。 |

---

## Validation

### Test Execution

```text
source .venv/bin/activate && pytest tests/host/test_state_schema.py tests/host/test_wait_record_state.py -v
============================== 47 passed in 0.48s ==============================
```

### pyright

```text
source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations
```

### Manual Verification

- `__cause__` chain preservation: confirmed — original `KeyError` retained through `from exc`.
- `HostRowDecodeError` type hierarchy: `HostRowDecodeError` → `HostDurableError` → `Exception`.
- `__init__.py` re-export boundary: clean — no `HostRowDecodeError` or `_row_rules` re-export.
- `_row_rules.py` import boundary: only `state.py` imports from `_row_rules` — no leakage.

### README / Doc Sync

- `dayu/host/durable/` was modified → check `dayu/host/README.md`: Row decode error boundary is an internal durable implementation detail. The stable durable foundation description in `dayu/host/README.md` (primary/secondary connections execute current schema validation, fresh bootstrap, typed row dataclass, CAS/transaction semantics) does not need updating. → Checked, no change required.

---

## Verdict

**PASS**

Slice 3 implementation correctly delivers:

1. Stable `HostRowDecodeError` error boundary with proper `__cause__` preservation and `row_name`/`field_name` context.
2. Complete replacement of direct `row.get` in all 6 row conversion functions with typed `_decode_*` helpers.
3. Decode-time terminal shape checks in Run/Attempt/WaitRecord via Slice 2 `_row_rules` validators, consistent with DDL/CAS semantics.
4. Clean scope boundary — no schema DDL, schema validation, public API, runtime helper, or WU-LAYER-02 changes.
5. Comprehensive test coverage for missing column, invalid type, invalid enum, terminal shape errors, and corrupted wait CAS read boundary.
6. Clean type boundaries with no `Any`/`object`/`hasattr`/`getattr`/lazy import/glue seam/compatibility wrapper.

No blocking findings. FIND-01 (test helper duplication) is low-severity maintainability note, does not require fix.

### Residual Risks

- Other `row.get(...)` calls in `state.py` that exist outside the 6 row conversion functions (e.g., in counting queries, auxiliary projections) are explicitly out of Slice 3 scope per the plan. These paths do not construct typed row dataclasses and are not part of the row decode error boundary.
- `_is_terminal_run_status` owner inconsistency (state.py vs `_row_rules.py`) is cosmetic and deferred.
