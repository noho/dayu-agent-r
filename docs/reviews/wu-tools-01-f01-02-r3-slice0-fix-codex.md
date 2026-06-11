# WU-TOOLS-01-F01-02-R3 Slice 0 Fix

## 基本信息

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: `Slice 0: Current ToolCallable Support`
- Gate: fix
- 修复范围：仅处理 controller accepted findings `S0-CR-01` 到 `S0-CR-03`
- 可选项：顺手完成 `S0-CR-04`

## Finding 状态

| ID | 状态 | 说明 |
|---|---|---|
| `S0-CR-01` | 已修复 | 保留当前 `ToolBusinessCancelled(message, hint)` 设计；更新 plan API 草案和 callable 模板，明确后续 Slice 1/2/3 callable 在消费业务取消结果时把 `business_result.message` / `business_result.hint` 传给 `host_cancelled_outcome(...)`。设计裁决：`ToolBusinessCancelled` 类型名已经表达 host-cancelled 映射语义，`reason: Literal["host_cancelled"]` 不携带额外业务上下文；`message` / `hint` 可保留业务 helper 对本次取消的可读说明，并由 outcome helper 在为空时填充默认文案。 |
| `S0-CR-02` | 已修复 | 新增 integer maximum 越界和 number minimum 越界的直接测试，断言返回固定 `invalid_argument` 与字段级 range message。 |
| `S0-CR-03` | 已修复 | 新增 boolean 非 bool、object 非 mapping、直接 `float("inf")` number 参数路径测试。直接非有限 number 参数会被 `ToolCallRequest` 正常构造期提前拒绝，因此测试使用局部 helper 绕过契约 JSON 有限数校验，只覆盖 `validate_and_project_arguments(...)` 的防御性分支。 |
| `S0-CR-04` | 已修复 | 将 `ToolArgumentValidationFailure.error` 收窄为 `Literal["invalid_argument"]`，并将 `INVALID_ARGUMENT_ERROR` 同步标注为该 literal。pyright 通过。 |

## Changed Files

- `dayu/runtime/tool_call_projection.py`
- `tests/runtime/test_tool_call_projection.py`
- `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`
- `docs/reviews/wu-tools-01-f01-02-r3-slice0-fix-codex.md`

未修改 Doc / Web / Fins provider、legacy adapter、Host、Engine、Service、ToolRuntime，也未修改 `docs/host/issues-implementation-control.md`。

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_tool_call_projection.py`
  - Result: passed, `19 passed`.
- `source .venv/bin/activate && pyright`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed, no output.

未运行 coverage。

## README Decision

- 已阅读 `tests/README.md` 的测试维护约束。
- 本次只在既有 `tests/runtime/` 分层内补 targeted tests，没有新增测试层级、运行方式或维护规则，因此不更新 README。

## Residual Risks

- 本 fix 只同步 Slice 0 helper 与 plan 模板；Doc / Web / Fins provider 仍待后续 Slice 1/2/3 迁移时按更新后的模板接入。
- 直接 `float("inf")` 参数路径是 helper 的防御性分支。正常生产入口会先由 `ToolCallRequest` 契约拒绝非有限 JSON number，因此该测试使用契约绕过 helper 只服务于分支回归保护。

## Next Recommended Gate

- Slice 0 re-review。
