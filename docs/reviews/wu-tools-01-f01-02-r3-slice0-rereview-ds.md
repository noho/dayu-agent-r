# WU-TOOLS-01-F01-02-R3 Slice 0 Fix Re-review

## Review Meta

- Reviewer: AgentDS
- Date: 2026-06-10 18:35 UTC
- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: `Slice 0: Current ToolCallable Support`
- Gate: re-review (fix verification)
- Prior code review: `docs/reviews/wu-tools-01-f01-02-r3-slice0-code-review-ds.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f01-02-r3-slice0-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-tools-01-f01-02-r3-slice0-fix-codex.md`
- Plan: `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`

## Scope

- Review target: Slice 0 fix only — verify S0-CR-01 through S0-CR-04 resolution
- Included files:
  - `dayu/runtime/tool_call_projection.py` (production helper)
  - `tests/runtime/test_tool_call_projection.py` (19 tests)
  - `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md` (plan fix)
  - `docs/reviews/wu-tools-01-f01-02-r3-slice0-fix-codex.md` (fix artifact, for reference)
- Excluded scope: Doc / Web / Fins provider migration (Slice 1/2/3), adapter deletion (Slice 4)

## Validation Pre-check

| 验证项 | 结果 |
|---|---|
| `pytest tests/runtime/test_tool_call_projection.py` | **19 passed** (up from 14 in impl) |
| `pyright` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | PASS (no output) |
| Plan diff scope | Only expected plan text changes (template + API draft + semantics) |

## Finding Verification

### S0-CR-01: Plan synchronized with ToolBusinessCancelled(message, hint), callable template forwards message/hint

**裁决: 已修复**

三条直接证据分布在 plan 文件的三个位置，形成完整闭合：

1. **API 草案已同步** — `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md:327-329`：
   ```python
   class ToolBusinessCancelled:
       message: str | None
       hint: str | None
   ```
   原草案 `reason: Literal["host_cancelled"]` 已替换为 `message`/`hint`，与实现 `dayu/runtime/tool_call_projection.py:129-130` 一致。

2. **Callable 模板已更新** — plan:261-268，`host_cancelled_outcome(...)` 调用新增：
   ```python
   message=business_result.message,
   hint=business_result.hint,
   ```
   后续 Slice 1/2/3 agent 按模板实现时，会自动将业务 helper 提供的取消说明转发到 outcome。

3. **Typed result 字段语义已更新** — plan:371：
   > `ToolBusinessCancelled` 只允许作为同一工具业务 helper 返回值，供 callable 立刻映射为 `host_cancelled_outcome(message=business_result.message, hint=business_result.hint, ...)`

4. **实现侧已就位** — `host_cancelled_outcome()` 签名（`tool_call_projection.py:295-296`）接受 `message: str | None = None` 和 `hint: str | None = None`，并在 None/空白时填充非空默认值（`tool_call_projection.py:310-318`）。

Plan ↔ implementation 同步闭环完整，无需进一步调整。

### S0-CR-02: Direct tests for integer and number numeric range failure paths

**裁决: 已修复**

两条新增测试均通过，直接覆盖越界失败分支：

1. **integer maximum 越界** — `test_validate_arguments_integer_rejects_out_of_range_value`（测试文件:161-176）：
   - 输入：`limit=10`，schema `minimum=1, maximum=5`
   - 断言：返回 `ToolArgumentValidationFailure`，`error == INVALID_ARGUMENT_ERROR`，`field_name == "limit"`，message 含 `"<= 5"`
   - 覆盖：`_validate_numeric_range` 行 687-688 的 `value > maximum` 分支

2. **number minimum 越界** — `test_validate_arguments_number_rejects_out_of_range_value`（测试文件:179-194）：
   - 输入：`score=0.25`，schema `minimum=0.5, maximum=1.0`
   - 断言：返回 `ToolArgumentValidationFailure`，`error == INVALID_ARGUMENT_ERROR`，`field_name == "score"`，message 含 `">= 0.5"`
   - 覆盖：`_validate_numeric_range` 行 680-681 的 `value < minimum` 分支

两个测试在 pytest 输出中分别为第 7 和第 8 个，均 PASSED。

### S0-CR-03: Targeted tests for boolean non-bool, object non-mapping, and direct non-finite number argument path

**裁决: 已修复**

三条新增测试均通过，直接覆盖三个此前缺失的 fail-closed 分支：

1. **boolean 非 bool** — `test_validate_arguments_boolean_rejects_non_bool_value`（测试文件:249-264）：
   - 输入：`recursive="true"`（字符串而非布尔），schema `type=boolean`
   - 断言：`failure.error == INVALID_ARGUMENT_ERROR`，`failure.field_name == "recursive"`，message 含 `"must be boolean"`
   - 覆盖：`_project_boolean` 行 546-547 的 `not isinstance(value, bool)` 分支

2. **object 非 mapping** — `test_validate_arguments_object_rejects_non_mapping_value`（测试文件:267-282）：
   - 输入：`filters=["region"]`（列表而非映射），schema `type=object`
   - 断言：`failure.error == INVALID_ARGUMENT_ERROR`，`failure.field_name == "filters"`，message 含 `"must be object"`
   - 覆盖：`_project_object` 行 622-623 的 `not isinstance(value, Mapping)` 分支

3. **直接非有限 number 参数** — `test_validate_arguments_rejects_non_finite_number_argument`（测试文件:215-230）：
   - 输入：`score=float("inf")` 作为直接 `call.arguments` 参数（通过 `_call_with_unchecked_arguments` 绕过 `ToolCallRequest` 构造期校验），schema `type=number`
   - 断言：`failure.error == INVALID_ARGUMENT_ERROR`，`failure.field_name == "score"`，message 含 `"finite number"`
   - 覆盖：`_project_number` 行 525-526 的 `not math.isfinite(value)` 分支

三个测试在 pytest 输出中分别为第 12、第 13、第 10 个，均 PASSED。

### S0-CR-04 (Optional): ToolArgumentValidationFailure.error narrowed to Literal["invalid_argument"]

**裁决: 已修复**

- 实现 `dayu/runtime/tool_call_projection.py:91`：`error: Literal["invalid_argument"]`（已从 `str` 收窄）
- 常量 `dayu/runtime/tool_call_projection.py:36`：`INVALID_ARGUMENT_ERROR: Final[Literal["invalid_argument"]] = "invalid_argument"`（同步收窄）
- pyright 0 errors——类型收窄未引入新的类型冲突

## New Blocker Check

### 测试契约绕过检查

`_call_with_unchecked_arguments`（测试文件:487-498）使用 `object.__setattr__` 绕过 `ToolCallRequest` 的正常构造期 JSON number 校验，以覆盖 `_project_number` 中 `not math.isfinite(value)` 的防御性分支。

判定：**非 blocker**。理由：

- 该 helper 仅用于 `test_validate_arguments_rejects_non_finite_number_argument` 一个测试。
- docstring 明确说明用途（"仅用于覆盖 helper 的防御性非有限 number 分支；正常契约构造会更早拒绝"）。
- 不会泄漏到生产代码——`object.__setattr__` 是 tests-only 私有 helper，生产 `ToolCallRequest` 仍通过正常 dataclass 构造路径。
- 该测试只验证 helper 的防御性分支不会静默通过畸形输入；正常生产路径由 `ToolCallRequest` 构造期拒绝非有限 number，两者不冲突。

### 其他检查

- 无 Doc / Web / Fins provider 修改，无 contract 变更，无新依赖引入。
- `dayu/runtime/tool_call_projection.py` 仍仅依赖 `dayu.contracts` + 标准库，边界无退化。
- 19 个测试无 skip、无 xfail、无 flaky。
- pyright 0 errors——`Literal["invalid_argument"]` 类型收窄未触发下游类型错误。

## Open Questions

无。

## Residual Risk

| 风险 | 严重程度 | Owner | 说明 |
|---|---|---|---|
| `_call_with_unchecked_arguments` 绕过契约构造 | 低 | Slice 0 | 仅 test-only，作用域明确。若未来 `ToolCallRequest` 改为 non-frozen 或增加 `__post_init__` 以外的校验钩子，该绕过可能需更新 |
| 直接非有限 number 参数路径是防御性分支 | 低 | 运行时 | 正常生产中 `ToolCallRequest` 构造期就会拒绝 `float("inf")`，该分支仅作为 defense-in-depth |

## Final Status

**pass**

S0-CR-01 到 S0-CR-04 全部已修复：
- Plan ↔ implementation 同步闭环完整（API 草案、callable 模板、字段语义三处一致）
- 5 个新增 targeted tests 覆盖 integer/number range、boolean non-bool、object non-mapping、direct non-finite number 路径
- `ToolArgumentValidationFailure.error` 已收窄为 `Literal["invalid_argument"]`
- pyright 0 errors，pytest 19 passed，git diff --check clean
- 无新 blocker 引入

**Slice 0 可以 proceed to accepted slice commit。**
