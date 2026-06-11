# WU-TOOLS-01-F01-02-R3 Slice 0 Code Review Controller Adjudication

## 基本信息

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: `Slice 0: Current ToolCallable Support`
- Gate: code review adjudication
- Implementation artifact: `docs/reviews/wu-tools-01-f01-02-r3-slice0-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r3-slice0-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-slice0-code-review-ds.md`
- Controller decision: enter Slice 0 fix gate

## 总体裁决

Slice 0 实现方向正确，依赖边界、类型签名、docstring、取消 outcome、meta 构造、focused pytest、pyright 和覆盖率均满足当前 gate 的基本要求。

当前不直接进入 accepted slice commit。原因是 DS 的中等 finding 指出 `ToolBusinessCancelled` 实现与 accepted plan 草案不一致：实现采用 `message` / `hint` 字段，这是合理增强，但 plan 模板仍描述为 `reason: Literal["host_cancelled"]`，后续 Slice 1/2/3 agent 若按 plan 模板实现，可能不会转发 message / hint。该问题应在 Slice 0 fix gate 关闭。

## Finding 裁决

| ID | 来源 | Finding | 裁决 | 理由 | Fix 要求 |
|---|---|---|---|---|---|
| S0-CR-01 | AgentDS Finding 1 / AgentMiMo Observation 1 | `ToolBusinessCancelled` 字段设计与 accepted plan 草案不一致 | accepted | 当前实现的 `message` / `hint` 设计优于纯 marker `reason`，但 plan 与后续 callable 模板必须同步，否则 Slice 1/2/3 会出现模板与代码不一致。 | 保留当前代码设计；更新 plan 中 `ToolBusinessCancelled` API 草案和 callable 模板，明确 later callable 将 `business_result.message` / `business_result.hint` 传给 `host_cancelled_outcome(...)`；在 fix artifact 记录该设计裁决。 |
| S0-CR-02 | AgentDS Finding 2 | `_validate_numeric_range` 越界失败路径缺少直接测试 | accepted | helper 是后续三类工具迁移的基础；数值 range 分支很小，但补测试成本低，可在当前 slice 关闭。 | 在 `tests/runtime/test_tool_call_projection.py` 增加 integer / number 越界直接测试。 |
| S0-CR-03 | AgentDS Finding 3 | boolean / object 类型失败与直接参数非有限 number 路径缺少测试 | accepted | 这些分支属于 Slice 0 helper 的核心 fail-closed 行为，不应等待业务 slice 偶然覆盖。 | 增加 targeted tests 覆盖 boolean 非 bool、object 非 mapping、直接 `float("inf")` number 参数。 |
| S0-CR-04 | AgentMiMo Observation 2 | `ToolArgumentValidationFailure.error` 类型为 `str`，不是 `Literal["invalid_argument"]` | deferred-with-owner | 运行时由 `_failure()` 唯一构造并固定为 `INVALID_ARGUMENT_ERROR`，当前无 correctness 风险。可由后续 typing cleanup 或 Slice 0 fix opportunistically 收窄，但不作为 blocking fix。 | 若本次 fix 顺手收窄且 pyright 通过，可以一并完成；否则保留为非阻塞类型强化建议。 |

## 下一步

进入 Slice 0 fix gate，由 AgentCodex：

- 更新 plan 文本以同步 `ToolBusinessCancelled(message, hint)` 设计。
- 补充 `tests/runtime/test_tool_call_projection.py` 的 targeted tests。
- 新增 `docs/reviews/wu-tools-01-f01-02-r3-slice0-fix-codex.md`。
- 运行 `pytest tests/runtime/test_tool_call_projection.py`、`pyright`、`git diff --check`。

修复完成后进入 Slice 0 re-review gate，聚焦 S0-CR-01 到 S0-CR-03。

## Residual Risk

当前无未分类 residual risk。S0-CR-04 为非阻塞类型强化建议，可在后续 cleanup 或当前 fix opportunistically 处理。
