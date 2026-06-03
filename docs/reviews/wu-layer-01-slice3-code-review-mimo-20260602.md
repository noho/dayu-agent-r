# WU-LAYER-01 Slice 3 Code Review — Row Decode Error Boundary

**Reviewer**: MiMo (review specialist)
**Date**: 2026-06-02
**Scope**: workspace uncommitted changes for Slice 3 Row Decode Error Boundary
**Design truth**: `docs/host/design.md`
**Control doc**: `docs/host/host-core-followup-implementation-control.md`
**Plan**: `docs/host/wu-layer-01-durable-row-primitive-cleanup-plan.md`

---

## Findings Ordered by Severity

### P0 — None

No blocking issues found.

### P1 — None

No high-severity issues found.

### P2 — Observations (non-blocking)

#### F-1: 测试 helper `_assert_host_row_decode_error` 在两个测试文件中重复

**文件**: `tests/host/test_state_schema.py:984` 与 `tests/host/test_wait_record_state.py:914`

两个文件中的 `_assert_host_row_decode_error` 实现完全一致。AGENTS.md 编码硬约束要求"重复逻辑必须抽取"。

**裁决**: 非阻塞。测试 helper 的文件级复用是合理实践，且 AGENTS.md 该约束主要针对生产代码。若后续测试文件继续增长，可考虑抽取到 `tests/host/conftest.py` 或 `tests/host/_helpers.py`。

### P3 — Style / Nit (non-blocking)

None.

---

## Review Checklist

### C1: `HostRowDecodeError` 是否是稳定错误边界，是否继承 durable error 且保留 `__cause__`

**PASS**。

- `errors.py:38-62`: `HostRowDecodeError` 继承 `HostDurableError`，携带 `row_name: str` 与 `field_name: str | None`。
- 所有 `raise HostRowDecodeError(...) from exc` 均保留 `__cause__`，包括 `_decode_scalar`（`from exc` KeyError）、`_decode_required_text` 等 helper（`from exc` HostDurableError）、`run_row_from_host_row` 形状校验（`from exc`）、`wait_record_row_from_host_row` 各 typed ref 校验（`from exc`）。
- 现有调用方 catch `HostDurableError` 不需要修改，因为 `HostRowDecodeError` 是其子类。

### C2: 指定 row conversion 是否真正替换直接 `row.get`，缺列、类型错误、enum deserialize、terminal shape error 是否统一包装

**PASS**。

六个 row conversion 函数全部替换：
- `session_row_from_host_row` (`state.py:896-920`)
- `session_slot_row_from_host_row` (`state.py:923-940`)
- `run_row_from_host_row` (`state.py:943-999`)
- `attempt_row_from_host_row` (`state.py:1002-1038`)
- `dispatch_record_row_from_host_row` (`state.py:1041-1084`)
- `wait_record_row_from_host_row` (`state.py:1087-1164`)

包装层次：
1. **缺列**: `_decode_scalar` 捕获 `row.get()` 抛出的 `KeyError`，转为 `HostRowDecodeError(field_name=column)`。
2. **类型错误**: `_decode_required_text` / `_decode_required_int` 等调用 `_validation` helper，捕获 `HostDurableError` 转为 `HostRowDecodeError`。
3. **enum deserialize**: `_decode_enum` 调用 `deserializer(value)`，捕获 `HostDurableError` 转为 `HostRowDecodeError`。
4. **terminal shape**: `run_row_from_host_row` / `attempt_row_from_host_row` 调用 `validate_terminal_event_refs_shape`，`wait_record_row_from_host_row` 调用 `validate_wait_terminal_at_shape`，均捕获 `HostDurableError` 后通过 `_wrap_row_decode_shape_error` 转为 `HostRowDecodeError(field_name=None)`。

剩余的 `row.get(...)` 调用（`state.py:1598`、`state.py:5413`、`state.py:5579`、`state.py:5600`）均为计数类或辅助查询中的局部读取，不属于 row dataclass decode 边界范围，按计划 non-scope 正确保留。

### C3: Run / Attempt / WaitRecord decode-time terminal shape checks 是否复用 Slice 2 rule owner，是否和 DDL/CAS 语义一致

**PASS**。

- `run_row_from_host_row` 调用 `validate_terminal_event_refs_shape(is_terminal=_is_terminal_run_status(run_row.status), owner_label="Run")`。
- `attempt_row_from_host_row` 调用 `validate_terminal_event_refs_shape(is_terminal=attempt_row.status in _TERMINAL_ATTEMPT_STATUSES, owner_label="Attempt")`。
- `wait_record_row_from_host_row` 调用 `validate_wait_terminal_at_shape(status_value=wait_row.status.value, terminal_at=wait_row.terminal_at)`。

三个校验函数均定义于 `_row_rules.py`（Slice 2），与 DDL CHECK 和 CAS `WHERE` 条件共享同一套状态常量与规则逻辑：
- `TERMINAL_RUN_STATUS_VALUES` / `TERMINAL_ATTEMPT_STATUS_VALUES` / `WAIT_RECORD_TERMINAL_STATUS_VALUES`
- `validate_terminal_event_refs_shape` / `validate_wait_terminal_at_shape`

状态值与 terminal refs 组合规则在 DDL CHECK、Python validation、CAS WHERE、row decode 四处完全同源。

### C4: 是否未越界修改 schema DDL、schema validation、public API、runtime helper 或 WU-LAYER-02 范围

**PASS**。

- 未修改 `schema.py`、`_validation.py`、`transaction.py`、`_row_rules.py`。
- 未新增 `dayu.host` public export。`HostRowDecodeError` 是 `dayu.host.durable.errors` 内部类型，不是 public API。
- 未修改 `dayu.runtime`。
- 未触碰 WU-LAYER-02 范围（shared helper consolidation）。
- 未修改 schema version。

### C5: 新增测试是否覆盖缺列、非法类型、invalid enum、terminal shape、corrupted wait CAS 读取边界，并且中文 docstring 满足 AGENTS

**PASS**。

新增/更新测试清单：

| 测试 | 文件 | 覆盖场景 |
|------|------|----------|
| `test_run_row_decode_missing_status_column_raises_row_decode_error` | test_state_schema.py | Run 缺 `status` 列 |
| `test_run_row_decode_integer_status_raises_row_decode_error` | test_state_schema.py | Run `status` 为 integer |
| `test_run_row_decode_terminal_missing_terminal_at_raises_row_decode_error` | test_state_schema.py | terminal Run 缺 `terminal_at` |
| `test_attempt_row_decode_terminal_missing_refs_raises_row_decode_error` | test_state_schema.py | terminal Attempt 缺 terminal refs |
| `test_wait_record_row_from_host_row_rejects_invalid_status` | test_wait_record_state.py | WaitRecord invalid status enum |
| `test_wait_record_row_decode_missing_terminal_at_column_raises_row_decode_error` | test_wait_record_state.py | WaitRecord 缺 `terminal_at` 列 |
| `test_wait_record_row_decode_terminal_at_shape_raises_row_decode_error` | test_wait_record_state.py | WaitRecord waiting+terminal_at / resolved-terminal_at |
| `test_wait_record_terminal_cas_rejects_corrupted_waiting_terminal_at` (更新) | test_wait_record_state.py | corrupted wait CAS 读取边界，断言 `HostRowDecodeError` |

所有测试函数和 helper 函数均提供完整中文 docstring，包含 `:param`、`:returns` 与 `:raises`。

### C6: 类型边界是否严格，是否新增 Any/object/getattr/hasattr/lazy import/glue seam/兼容 wrapper

**PASS**。

- 无 `Any`、`object`（代码引用）、`getattr`、`hasattr` 使用。
- 无 lazy import。
- 无 glue seam。
- 无兼容 wrapper / facade / re-export。
- 新增 `Callable` import 仅用于 `_decode_enum` 的 `deserializer` 参数类型签名。
- 新增 `SQLiteScalar` import 用于 `_decode_scalar` 返回类型。
- `_StatusT = TypeVar("_StatusT", bound=StrEnum)` 用于 `_decode_enum` 泛型约束，类型安全。

---

## Validation

```text
source .venv/bin/activate && pytest tests/host/test_state_schema.py tests/host/test_wait_record_state.py
47 passed in 0.48s
```

```text
source .venv/bin/activate && pyright dayu/host/durable/errors.py dayu/host/durable/state.py
0 errors, 0 warnings, 0 informations
```

全部 47 测试通过，pyright 零报错。

---

## Open Questions

None.

---

## Verdict

**PASS**。

Slice 3 实现完整、边界清晰、测试充分。`HostRowDecodeError` 作为稳定 row decode 错误边界，正确继承 `HostDurableError` 并保留 `__cause__`；六个 row conversion 函数全部替换为 `_decode_*` helper 统一包装；Run / Attempt / WaitRecord terminal shape 校验复用 Slice 2 `_row_rules.py` 规则，与 DDL/CAS 语义同源；未越界修改 schema、public API、runtime 或 WU-LAYER-02 范围；类型严格，无 AGENTS.md 编码硬约束违反。
