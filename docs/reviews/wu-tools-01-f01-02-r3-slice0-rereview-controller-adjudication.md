# WU-TOOLS-01-F01-02-R3 Slice 0 Re-Review Controller Adjudication

## 基本信息

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: `Slice 0: Current ToolCallable Support`
- Gate: re-review adjudication
- Implementation artifact: `docs/reviews/wu-tools-01-f01-02-r3-slice0-implementation-codex.md`
- Fix artifact: `docs/reviews/wu-tools-01-f01-02-r3-slice0-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r3-slice0-rereview-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-slice0-rereview-ds.md`
- Controller decision: Slice 0 accepted; proceed to accepted slice commit

## Re-review 结论

AgentMiMo 与 AgentDS 均裁决 `pass`。S0-CR-01 到 S0-CR-04 均为 `已修复`，未引入新的 blocking finding。

## Finding 最终状态

| ID | 最终状态 | Controller 裁决 |
|---|---|---|
| S0-CR-01 `ToolBusinessCancelled(message, hint)` 与 plan / callable 模板同步 | 已修复 | accepted-fixed |
| S0-CR-02 integer / number 数值范围越界直接测试 | 已修复 | accepted-fixed |
| S0-CR-03 boolean / object 类型失败与直接非有限 number 参数测试 | 已修复 | accepted-fixed |
| S0-CR-04 `ToolArgumentValidationFailure.error` 收窄为 `Literal["invalid_argument"]` | 已修复 | accepted-fixed |

## 验证

Controller 本地复验：

- `source .venv/bin/activate && pytest tests/runtime/test_tool_call_projection.py` -> 19 passed
- `source .venv/bin/activate && pyright` -> 0 errors
- `git diff --check` -> passed

Agent re-review 额外确认 coverage 为 90%，超过单文件 80% 目标。

## Docs Decision

本 slice 新增 `tests/runtime/test_tool_call_projection.py`，仍属于既有 `tests/runtime/` 层级；未新增测试层级、维护规则或公共运行入口。`tests/README.md` 不需要更新。未修改 `dayu/fins/`、`dayu/engine/`、`dayu/host/` 包代码，因此不触发对应 README 更新。

## Residual Risk

当前没有未分类 residual risk。以下事项属于后续 approved slices 的自然验证范围：

- Doc / Web / Fins provider 尚未迁移，仍在 Slice 1/2/3 处理。
- `ToolBusinessFailure` 与 `ToolBusinessCancelled` 尚未接入业务 helper -> callable -> outcome 完整链路，后续 Slice 1/2/3 必须按 accepted plan 模板验证。
- `_call_with_unchecked_arguments` 是 tests-only helper，用于覆盖 defensive non-finite number 分支；生产 `ToolCallRequest` 构造仍会先拒绝非有限 JSON number。

## 下一步

创建 accepted slice commit，然后进入 Slice 1: Doc Native Tools implementation gate。
