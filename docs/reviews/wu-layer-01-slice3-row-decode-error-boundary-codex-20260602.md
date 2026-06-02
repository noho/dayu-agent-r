# WU-LAYER-01 Slice 3 Row Decode Error Boundary Implementation

## Changed Files

- `dayu/host/durable/errors.py`
- `dayu/host/durable/state.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_wait_record_state.py`
- `docs/reviews/wu-layer-01-slice3-row-decode-error-boundary-codex-20260602.md`

说明：`docs/host/host-core-followup-implementation-control.md` 在本 slice 开始前已处于 controller 修改状态，本次实现未修改该文件。

## Implemented Plan Items

- 新增 `HostRowDecodeError`，继承 `HostDurableError`，携带 `row_name` 与 `field_name`。
- 在 `state.py` 新增私有 row decode helpers，统一包装：
  - `HostRow.get(...)` 缺列 `KeyError`；
  - scalar helper 抛出的 `HostDurableError`；
  - enum deserializer 抛出的 `HostDurableError`；
  - Run / Attempt / WaitRecord 终态形状 validator 抛出的 `HostDurableError`。
- 替换以下 row conversion 函数中的直接 `row.get(...)`：
  - `session_row_from_host_row`
  - `session_slot_row_from_host_row`
  - `run_row_from_host_row`
  - `attempt_row_from_host_row`
  - `dispatch_record_row_from_host_row`
  - `wait_record_row_from_host_row`
- 为 Run / Attempt / WaitRecord row decode 增加 decode-time terminal shape 校验，复用 Slice 2 的 terminal shape helper 语义。
- 更新 focused tests，覆盖：
  - Run row 缺 `status` 列；
  - Run row `status` 为 integer；
  - terminal Run 缺 `terminal_at`；
  - terminal Attempt 缺 terminal refs；
  - WaitRecord 缺 `terminal_at` 列；
  - WaitRecord `waiting` 携带 `terminal_at`；
  - WaitRecord `resolved` 缺 `terminal_at`；
  - WaitRecord invalid status 断言具体 `HostRowDecodeError`。
- 更新 Slice 2 corrupted WaitRecord terminal CAS 测试，使其断言畸形 row 在读取边界触发 `HostRowDecodeError`，不再把畸形 row 解释成正常 mutation result。
- Docstring completion fix：补齐 Slice 3 新增/修改测试函数与 helper 的中文完整 docstring，覆盖 `:param`、`:returns` 与 `:raises`。

## Validation Output Summary

```text
source .venv/bin/activate && pytest tests/host/test_state_schema.py tests/host/test_wait_record_state.py
47 passed in 0.49s
```

Docstring completion fix 后复跑：

```text
source .venv/bin/activate && pytest tests/host/test_state_schema.py tests/host/test_wait_record_state.py
47 passed in 0.50s
```

```text
source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations
```

Docstring completion fix 后复跑：

```text
source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations
```

## Residual Risks / Uncovered Areas

- 本 slice 未修改 schema DDL、schema version、schema validation 或 `_validation.py` scalar helper 行为。
- 本 slice 未执行 README Slice 4；当前改动不改变用户入口、测试约定或 Host README 的稳定说明职责。
- Row decode boundary 只覆盖计划指定的 durable state row conversion 函数；其它计数类或辅助查询中的局部 `row.get(...)` 不属于本 slice row dataclass decode 边界。

## Completion Status

Slice 3 implementation complete. 指定测试与 pyright 均通过。未 commit、未 push、未进入 review gate。
