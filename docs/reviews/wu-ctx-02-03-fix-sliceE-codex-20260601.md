# WU-CTX-02 + WU-CTX-03 Slice E code review fix artifact

## Scope

- Accepted finding: DS F-1 MEDIUM，`tests/host/test_dispatch_scheduler.py` 中 `_soft_compact_policy` 的 `max_reactive_compactions_per_run` 默认值写死为 `2`，会与 `dayu.host.context_policy.DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN` 形成双重真源。
- 本次只修复该测试 helper 的默认值来源，不扩大 Slice E 行为范围，不提交 commit。

## Changes

- `tests/host/test_dispatch_scheduler.py`
  - 从 `dayu.host.context_policy` 导入 `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN`。
  - 将 `_soft_compact_policy` 的 `max_reactive_compactions_per_run` 默认值改为该常量。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -q`
  - result: `57 passed in 1.11s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - result: `0 errors, 0 warnings, 0 informations`

## Deferred / Not Handled

- MiMo F-01: `actual_attempt_count <= expected_attempt_count` 在 `==` 后冗余，但 approved plan 明确要求同时断言 Attempt 数等于且不超过上限，本 Slice 保留。
- DS INFO findings F-2/F-3/F-4：本次不处理。
- 未修改 README；本次只调整测试 helper 的默认值来源与 review artifact，不改变用户手册、开发手册或测试手册职责范围内的稳定说明。
- 未提交 commit。
