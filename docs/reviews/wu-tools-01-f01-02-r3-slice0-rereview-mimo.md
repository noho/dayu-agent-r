# WU-TOOLS-01-F01-02-R3 Slice 0 Fix Re-Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-tools-r3-f08`
- Base: `main` (commit `7b465e19`)
- Output file: `docs/reviews/wu-tools-01-f01-02-r3-slice0-rereview-mimo.md`
- Included scope:
  - `dayu/runtime/tool_call_projection.py`
  - `tests/runtime/test_tool_call_projection.py`
  - `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-slice0-fix-codex.md`
- Excluded scope: Doc / Web / Fins provider 迁移 (Slice 1/2/3)、adapter 删除 (Slice 4)
- Prior artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r3-slice0-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-slice0-code-review-ds.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-slice0-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-slice0-implementation-codex.md`
- Parallel review coverage: 无

## Validation Pre-check

| 验证项 | 结果 |
|---|---|
| `pytest tests/runtime/test_tool_call_projection.py` | 19 passed (fix 前 14 passed，新增 5 个测试) |
| `pyright dayu/runtime/tool_call_projection.py tests/runtime/test_tool_call_projection.py` | 0 errors, 0 warnings, 0 informations |
| Coverage | 90% ≥ 80% 目标 (fix 前 85%) |
| `git diff --check` | PASS |

## Finding 验证

### S0-CR-01: plan 同步 ToolBusinessCancelled(message, hint)，callable 模板转发 message/hint

**裁决: 已修复**

验证证据：

1. **Plan API 草案已同步**：`docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md` 第 325-326 行，`ToolBusinessCancelled` 草案已从 `reason: Literal["host_cancelled"]` 更新为 `message: str | None` 和 `hint: str | None`，与实现一致。

2. **Callable 模板已同步**：plan callable 模板第 263-264 行新增 `message=business_result.message` 和 `hint=business_result.hint`，明确后续 Slice 1/2/3 callable 在消费 `ToolBusinessCancelled` 时转发 message/hint 给 `host_cancelled_outcome(...)`。

3. **Typed result 字段语义已更新**：plan 第 368-371 行明确 `ToolBusinessCancelled` 的 message/hint 语义——"业务 helper 对本次取消的可选说明，为空时由 `host_cancelled_outcome(...)` 使用默认说明与默认提示"。

4. **实现代码未变化**：`dayu/runtime/tool_call_projection.py` 第 117-130 行 `ToolBusinessCancelled` 保持 `message: str | None` 和 `hint: str | None` 设计不变，与更新后的 plan 一致。

5. **host_cancelled_outcome 已正确消费 message/hint**：第 290-319 行 `host_cancelled_outcome(...)` 接受 `message: str | None = None` 和 `hint: str | None = None`，通过 `_blank_to_default_optional` 处理空值默认化。设计链路完整：business helper → `ToolBusinessCancelled(message, hint)` → callable → `host_cancelled_outcome(message=..., hint=...)` → `ToolCancelledOutcome`。

### S0-CR-02: integer / number 数值范围越界的直接测试

**裁决: 已修复**

验证证据：

1. **integer maximum 越界测试**：`test_validate_arguments_integer_rejects_out_of_range_value` (第 161-176 行) — schema `maximum=5`，传入 `limit=10`，断言返回 `ToolArgumentValidationFailure(error=INVALID_ARGUMENT_ERROR)` 且 message 包含 `<= 5`。

2. **number minimum 越界测试**：`test_validate_arguments_number_rejects_out_of_range_value` (第 179-194 行) — schema `minimum=0.5, maximum=1.0`，传入 `score=0.25`，断言返回 `ToolArgumentValidationFailure(error=INVALID_ARGUMENT_ERROR)` 且 message 包含 `>= 0.5`。

3. **覆盖改善**：coverage 从 85% 提升至 90%。原 coverage report 中 `_validate_numeric_range` 相关的 missing 行 (679, 681, 686, 688) 现已被覆盖。

### S0-CR-03: boolean 非 bool、object 非 mapping、直接非有限 number 参数路径测试

**裁决: 已修复**

验证证据：

1. **boolean 非 bool 测试**：`test_validate_arguments_boolean_rejects_non_bool_value` (第 249-264 行) — 传入 `recursive="true"`（字符串），断言返回 `ToolArgumentValidationFailure` 且 message 包含 `must be boolean`。

2. **object 非 mapping 测试**：`test_validate_arguments_object_rejects_non_mapping_value` (第 267-282 行) — 传入 `filters=["region"]`（列表），断言返回 `ToolArgumentValidationFailure` 且 message 包含 `must be object`。

3. **直接非有限 number 参数测试**：`test_validate_arguments_rejects_non_finite_number_argument` (第 215-230 行) — 使用 `_call_with_unchecked_arguments` helper 将 `float("inf")` 直接注入 `call.arguments`，断言返回 `ToolArgumentValidationFailure` 且 message 包含 `finite number`。

4. **契约绕过 helper 的合理性**：`_call_with_unchecked_arguments` (第 487-498 行) 使用 `object.__setattr__` 绕过 `ToolCallRequest` 契约的 JSON 有限数校验。已验证正常 `ToolCallRequest` 构造确实拒绝 `float("inf")`（`ValueError: arguments.score must be finite JSON number`），因此该 helper 仅服务于防御性分支的回归保护。注释已说明意图（第 496 行）。

### S0-CR-04: ToolArgumentValidationFailure.error 收窄为 Literal["invalid_argument"]

**裁决: 已修复**

验证证据：

1. **类型已收窄**：`dayu/runtime/tool_call_projection.py` 第 91 行 `error: Literal["invalid_argument"]`。

2. **常量已同步标注**：第 36 行 `INVALID_ARGUMENT_ERROR: Final[Literal["invalid_argument"]] = "invalid_argument"`。

3. **pyright 通过**：0 errors, 0 warnings, 0 informations。

## Findings

未发现实质性问题。

以下为低严重度观察项，不阻塞 Slice 0 进入 accepted slice commit。

### 编号-01-已修复-低-coverage 缺口仍存在但已改善

- **入口/函数**: 多个私有 helper 的边界分支
- **文件(行号)**: `dayu/runtime/tool_call_projection.py` 第 336, 339, 366, 382, 388, 455, 464, 466, 497, 524, 534, 567, 571, 573, 580, 589, 591, 624, 646, 658, 679, 686, 702, 763, 851 行
- **输入场景**: provider schema 畸形（非法 bound 值、非法 items schema）、字符串 maxLength 越界、数组 minItems 不足、enum 类型非法等
- **实际分支**: 未覆盖
- **预期行为**: 返回 `ToolArgumentValidationFailure`
- **实际行为**: 代码逻辑正确，均为简单 isinstance 检查后调用失败 helper
- **直接证据**: coverage report 90% (240 stmts, 25 missing)
- **影响**: 低。未覆盖分支的输入来自 schema 声明而非用户参数，由 provider 实现正确性保证。S0-CR-02 / S0-CR-03 的修复已覆盖最关键的核心 fail-closed 行为
- **建议改法和验证点**: 后续 Slice 1/2/3 业务工具参数校验集成测试可自然覆盖部分；剩余 schema 畸形分支可选择性补充
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

- 本 fix 只同步 Slice 0 helper 与 plan 模板；Doc / Web / Fins provider 仍待后续 Slice 1/2/3 迁移时按更新后的模板接入。
- `_call_with_unchecked_arguments` helper 仅用于测试防御性分支，已验证正常契约会提前拒绝非有限 number。该 helper 不会在生产代码中使用。
- `ToolBusinessFailure` 和 `ToolBusinessCancelled` 的 message/hint 字段在后续 Slice 中如何消费尚未有集成测试；当前仅导出类型定义，未经 business helper → callable → outcome 完整链路验证。
- Coverage 90% (25 missing lines)。未覆盖行主要是 provider schema 畸形时的错误路径，以及少量边界条件分支。S0-CR-02 / S0-CR-03 修复已显著改善覆盖。

## Re-Review 结论

**Status: pass**

所有 accepted findings 已验证通过：

| Finding ID | 裁决 | 验证摘要 |
|---|---|---|
| S0-CR-01 | 已修复 | plan API 草案、callable 模板、typed result 字段语义三处同步；实现代码不变 |
| S0-CR-02 | 已修复 | 新增 integer maximum 越界和 number minimum 越界直接测试；coverage 改善 |
| S0-CR-03 | 已修复 | 新增 boolean 非 bool、object 非 mapping、直接非有限 number 参数测试；契约绕过 helper 有注释说明 |
| S0-CR-04 | 已修复 | `ToolArgumentValidationFailure.error` 收窄为 `Literal["invalid_argument"]`；pyright 通过 |

验证结果：

- 19 passed (fix 前 14 passed)
- pyright 0 errors, 0 warnings
- Coverage 90% ≥ 80% 目标
- 无新增 blocker
- test-only 契约绕过 (`_call_with_unchecked_arguments`) 已验证合理性

Slice 0 可以 proceed to accepted slice commit。
