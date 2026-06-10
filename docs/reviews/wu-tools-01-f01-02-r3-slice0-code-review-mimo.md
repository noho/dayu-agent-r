# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-tools-r3-f08`
- Base: `main` (commit `7b465e19 gateflow: accept plan for WU-TOOLS-01-F01-02-R3`)
- Output file: `docs/reviews/wu-tools-01-f01-02-r3-slice0-code-review-mimo.md`
- Included scope: Slice 0 implementation only
  - `dayu/runtime/tool_call_projection.py` (新增)
  - `tests/runtime/test_tool_call_projection.py` (新增)
  - `docs/reviews/wu-tools-01-f01-02-r3-slice0-implementation-codex.md` (新增)
  - `docs/host/issues-implementation-control.md` (状态更新)
- Excluded scope: Doc / Web / Fins provider 迁移 (Slice 1/2/3)、adapter 删除 (Slice 4)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下为低严重度观察项，不影响 Slice 0 进入 fix gate 或 accepted slice commit。

### 编号-01-未修复-低-`ToolBusinessCancelled` 字段设计与 plan draft 偏差

- **入口/函数**: `ToolBusinessCancelled` dataclass 定义
- **文件(行号)**: `dayu/runtime/tool_call_projection.py:117-130`
- **输入场景**: 后续 Slice 1/2/3 同步业务 helper 返回取消信号时
- **实际分支**: 实现使用 `message: str | None` 和 `hint: str | None`
- **预期行为**: plan draft 草案为 `reason: Literal["host_cancelled"]`
- **实际行为**: 实现用 `message`/`hint` 替代了 `reason` 字段
- **直接证据**: plan `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md` Slice 0 API 草案第 318-320 行定义 `ToolBusinessCancelled(reason: Literal["host_cancelled"])`，实现第 117-130 行使用 `message`/`hint`
- **影响**: 无负面影响。`ToolBusinessCancelled` 类型名已隐含取消语义，`reason: Literal["host_cancelled"]` 不携带额外信息；`message`/`hint` 允许业务 helper 向 callable 传递上下文取消说明，更利于后续 `host_cancelled_outcome(message=..., hint=...)` 构造
- **建议改法和验证点**: 保持当前实现。plan 草案是初稿，实现的改进合理且不违反 plan 约束（"只允许作为同一工具业务 helper 返回值"语义不变）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Status candidate**: accepted（设计偏差但改进合理，plan 草案为初稿非硬约束）

### 编号-02-未修复-低-`ToolArgumentValidationFailure.error` 类型为 `str` 非 `Literal`

- **入口/函数**: `ToolArgumentValidationFailure` dataclass 定义
- **文件(行号)**: `dayu/runtime/tool_call_projection.py:80-94`
- **输入场景**: 所有参数校验失败路径
- **实际分支**: `error: str`
- **预期行为**: plan 草案建议 `error: Literal["invalid_argument"]`
- **实际行为**: 类型为 `str`，运行时值由 `_failure()` 固定为 `INVALID_ARGUMENT_ERROR`
- **直接证据**: plan 第 308 行定义 `error: Literal["invalid_argument"]`，实现第 92 行 `error: str`；`_failure()` 第 785 行固定赋值 `error=INVALID_ARGUMENT_ERROR`
- **影响**: 无运行时影响。`_failure()` 是唯一构造路径，值始终为 `"invalid_argument"`。`Literal` 类型可在 pyright 静态检查时阻止意外赋值
- **建议改法和验证点**: 可改为 `error: Literal["invalid_argument"]` 以增强类型约束，或保持 `str` 并补充行内注释说明值域约束。不阻塞 merge
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Status candidate**: deferred-with-owner（owner: Slice 0 fix gate，可选改进）

## Open Questions

无。

## Residual Risk

- 覆盖率 85% ≥ 80% 目标。未覆盖行主要是 provider schema 畸形时的错误路径（`_schema_bound_failure`、`_type_failure`、`_range_failure` 各子类型），以及 `_blank_to_none(None)` 分支。这些路径的输入来自 schema 声明而非用户参数，由 provider 实现正确性保证；当前测试已覆盖核心行为和关键边界。
- `additional_properties=None`（即 `ToolParametersSchema` 未显式声明时）正确拒绝未知字段（fail-closed），与 `additional_properties=False` 行为一致。该行为已通过代码路径验证，但无显式测试用例。
- Slice 0 不涉及 Doc / Web / Fins provider 迁移，不改变公共契约，不引入新的层间依赖。后续 Slice 1/2/3 的迁移风险由各自 slice 独立承担。

## Review 结论

**Status: pass**

Slice 0 实现与 plan 意图一致，无实质性缺陷：

1. **依赖边界**：`dayu.runtime.tool_call_projection` 只依赖标准库和 `dayu.contracts`，未导入 engine / host / service / ui / fins / 业务工具包。✓
2. **Helper API**：public API 与 plan 一致（`validate_and_project_arguments`、`completed_outcome`、`failed_outcome`、`host_cancelled_outcome`、typed result classes）。✓
3. **类型签名**：无 `Any` / `object` / 无类型参数 / 无类型返回值；无 lazy import；无兼容 facade。✓
4. **中文 docstring**：模块、所有类、所有函数（含私有函数）均提供完整中文 docstring，包含参数、返回值、异常。✓
5. **参数校验**：窄范围、需求驱动、对未支持 schema 关键字 fail-closed。✓
6. **`invalid_argument` 行为**：所有参数校验失败固定使用 `INVALID_ARGUMENT_ERROR`，无字段名魔法错误码。✓
7. **`host_cancelled_outcome`**：返回 `ToolCancelledOutcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED)`，message / hint 非空默认值，携带 `ToolResultMeta`，不泄漏 `run_id` / `session_id` / `correlation_id` / `cancellation_token` 等治理字段。✓
8. **completed / failed outcome**：均携带 `ToolResultMeta`。✓
9. **测试**：14 个测试覆盖核心行为和关键边界；pyright 0 errors；覆盖率 85%。✓
10. **隐藏行为回归**：未发现会影响后续 Doc / Web / Fins 迁移的隐藏行为回归。✓

Slice 0 可以进入 fix gate 或 accepted slice commit。
