# WU-TOOLS-01-F01-02-R3 Slice 0 Code Review

## Review Meta

- Reviewer: AgentDS
- Date: 2026-06-10 18:23 UTC
- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: `Slice 0: Current ToolCallable Support`
- Gate: code-review
- Plan: `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`
- Accepted plan commit: `7b465e19`
- Implementation artifact: `docs/reviews/wu-tools-01-f01-02-r3-slice0-implementation-codex.md`
- Control doc: `docs/host/issues-implementation-control.md`

## Scope

- Mode: current changes — Slice 0 implementation only
- Branch: `phaseflow/wu-tools-r3-f08`
- Included files:
  - `dayu/runtime/tool_call_projection.py` (new)
  - `tests/runtime/test_tool_call_projection.py` (new)
  - `docs/reviews/wu-tools-01-f01-02-r3-slice0-implementation-codex.md` (new, for reference)
- Excluded scope: Doc/Web/Fins providers, legacy adapter, Slice 1/2/3/4, committed changes not in Slice 0
- Parallel review coverage: 无

## Validation Pre-check

| 验证项 | 结果 |
|---|---|
| `pytest tests/runtime/test_tool_call_projection.py` | 14 passed |
| `pyright dayu/runtime/tool_call_projection.py tests/runtime/test_tool_call_projection.py` | 0 errors, 0 warnings |
| `grep -E 'import.*dayu\.(engine\|host\|service\|ui\|fins\|tools)'` on production file | 0 matches — PASS |
| Coverage | 85% (≥80% target met) |
| Git diff --check | PASS |

## Findings

### 1. 未修复-中-ToolBusinessCancelled 字段设计与 accepted plan 不一致

- **入口/函数**: `ToolBusinessCancelled` dataclass 定义
- **文件(行号)**: `dayu/runtime/tool_call_projection.py:117-131`
- **输入场景**: 后续 Slice 1/2/3 中 Doc/Web/Fins business helper 需要返回 typed cancelled result 时，按 plan 应使用 `reason: Literal["host_cancelled"]` 的 marker 类型。
- **实际分支**: 实现将 `ToolBusinessCancelled` 设计为携带 `message: str | None` 和 `hint: str | None` 的可选消息载体，无 `reason` 字段。
- **预期行为**: Accepted plan（`docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md:324-326`）明确草案为：
  ```python
  @dataclass(frozen=True, slots=True)
  class ToolBusinessCancelled:
      reason: Literal["host_cancelled"]
  ```
  这是一个 marker 类型，由 callable 识别后调用 `host_cancelled_outcome()` 构造最终 outcome。
- **实际行为**: `ToolBusinessCancelled` 字段为 `message: str | None` 和 `hint: str | None`，无 `reason` 字段。Docstring 说明 message/hint 为空时由 `host_cancelled_outcome` 填充默认值。这实际是合理的增强——允许 business helper 提供具体取消原因文本——但 plan 模板代码（plan:273）并未从 `ToolBusinessCancelled` 读取 message/hint 传给 `host_cancelled_outcome`。
- **直接证据**:
  - Plan line 324-326：`reason: Literal["host_cancelled"]`
  - 实现 line 129-130：`message: str | None`、`hint: str | None`
  - Plan 模板 line 261-266：`host_cancelled_outcome(...)` 调用未传 message/hint 参数，即模板不消费 `ToolBusinessCancelled` 的 message/hint 字段。
- **影响**: 后续 Slice 1/2/3 的 callable 在消费 `ToolBusinessCancelled` 时，如果按 plan 模板只做 `isinstance` 判断而不转发 message/hint，则 business helper 提供的取消说明将被丢弃。这不会造成 correctness bug（`host_cancelled_outcome` 会填充默认值），但会丢失 business helper 提供的领域取消上下文。若按实现的设计转发 message/hint，则 callable 模板需更新。
- **建议改法和验证点**:
  1. 在 implementation artifact 或 fix commit 中明确记录此次偏离 plan 的决策：**为何选择 message/hint 而非 reason field**，以及**后续 callable 模板如何消费 message/hint**。
  2. 若接受当前设计：需在 Slice 1/2/3 的 plan 中明确 callable 应将 `ToolBusinessCancelled.message` / `ToolBusinessCancelled.hint` 转发给 `host_cancelled_outcome(message=..., hint=...)`。
  3. 若恢复 plan 设计：将 `ToolBusinessCancelled` 改为纯 marker 类型，添加 `reason: Literal["host_cancelled"]` 字段，移除 message/hint。
- **修复风险（低）**: 两种方向都是纯类型/字段调整，不涉及运行时逻辑变更。当前 `ToolBusinessCancelled` 只在测试中被动存在（无直接构造测试），修改不影响已有测试。
- **严重程度（中）**: 非 correctness bug，但 plan-contract 偏离若不在 Slice 0 收口，会在 Slice 1/2/3 中扩散为 callable 模板不一致。
- **Adjudication-ready 候选**: accepted / rejected-with-reason（若裁决为设计优化则有理由拒绝）

### 2. 未修复-低-`_validate_numeric_range` 越界失败路径缺少直接测试

- **入口/函数**: `_validate_numeric_range` 及 `_project_integer` / `_project_number` 中 range_failure 消费路径
- **文件(行号)**: `dayu/runtime/tool_call_projection.py:497, 504, 679-688`
- **输入场景**: integer 字段传入超出 minimum/maximum 的值（如 schema `minimum=1, maximum=5`，传入 `limit=10`），或 number 字段传入越界有限浮点值。
- **实际分支**: `_project_integer` 行 498-503 调用 `_validate_numeric_range`；`_validate_numeric_range` 行 680-681（value < minimum）、行 687-688（value > maximum）分别返回 range_failure。这些分支均未被任何测试覆盖（coverage report 证实行 497, 504, 679, 681, 686, 688 missing）。
- **预期行为**: 越界数值应返回 `ToolArgumentValidationFailure(error="invalid_argument")` 带 range detail。
- **实际行为**: 代码逻辑正确（直接与边界比较后返回 `_range_failure`），但未被测试证明。
- **直接证据**: Coverage report：行 497 (`_project_integer` 中的 `return range_failure` 分支）、504 (`_project_number` 中的 `return range_failure` 分支）、679 (`if _is_invalid_number_bound(minimum)` 的 true 分支）、681 (`return _schema_bound_failure`）、686 (`if _is_invalid_number_bound(maximum)` 的 true 分支）、688 (`return _schema_bound_failure`) 均 missing。当前 integer 测试只用 `limit=3.0`（在 1-5 范围内）和 `limit=True`（在范围校验前被类型校验拒绝）；number 测试只用 `float("inf")` 作为默认值（在范围校验前被非有限拒绝）。
- **影响**: 低。越界校验是简单的数值比较，逻辑正确性可通过代码阅读确认。但如果后续修改范围校验逻辑（如增加 exclusiveMinimum/exclusiveMaximum），缺少回归测试。
- **建议改法和验证点**: 增加 `integer` 字段 `limit=10` 且 schema 声明 `maximum=5` 的测试，断言返回 `ToolArgumentValidationFailure` 且 message 包含 `<= 5`；同样增加 `number` 字段越界测试。
- **修复风险（低）**: 新增纯测试，不涉及生产代码变更。
- **严重程度（低）**: 逻辑正确但缺少直接测试证据；85% 覆盖率已达标，不阻塞 Slice 0 推进。
- **Adjudication-ready 候选**: accepted / deferred-with-owner（可推迟到 Slice 1 前补齐）

### 3. 未修复-低-`_project_boolean` / `_project_object` 类型失败与 `_project_number` 直接参数非有限路径缺少测试

- **入口/函数**: `_project_boolean`、`_project_object`、`_project_number`
- **文件(行号)**: `dayu/runtime/tool_call_projection.py:547, 622-624, 527-534`
- **输入场景**:
  - boolean schema 字段传入非 bool 值（如字符串 `"true"`）
  - object schema 字段传入非 Mapping 值（如字符串或列表）
  - number schema 字段在 call.arguments 中直接传入 `float("inf")`（当前仅覆盖 default 路径）
- **实际分支**: 三个分支均未被任何测试覆盖（coverage report 行 547, 622-624, 527-534 missing）。
- **预期行为**: 均应返回 `ToolArgumentValidationFailure`。
- **实际行为**: 代码逻辑正确——均为简单 isinstance 检查后调用 `_type_failure` 或 `_range_failure`，但未被测试直接证明。
- **直接证据**: Coverage report missing lines 547 (`_project_boolean` 中 `isinstance(value, bool)` 的 false 分支）、622-624 (`_project_object` 中 `isinstance(value, Mapping)` 的 false 分支及 return 行）、527-534 (`_project_number` 中非有限检查后的 `_validate_numeric_range` 调用与 result 检查——仅当直接参数为有限浮点且触发范围检查时才覆盖）。
- **影响**: 低。均是简单类型检查，逻辑正确性可代码阅读确认。
- **建议改法和验证点**: 增加三个针对性测试；这些可随 Slice 1 业务工具参数校验集成测试自然覆盖，不必在 Slice 0 补齐。
- **修复风险（低）**: 纯测试补充。
- **严重程度（低）**: 当前 85% 覆盖率达标；类型检查逻辑简单，回归风险极低。
- **Adjudication-ready 候选**: deferred-with-owner（Slate 1/2/3 业务工具测试可自然覆盖）

## Review Focus Verification

### dayu.runtime dependency boundary

- ✅ 零 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` / `dayu.tools` import
- ✅ 仅依赖标准库 + `dayu.contracts`
- ✅ 无 lazy import、无兼容 facade

### Helper API matches accepted plan

- ✅ `validate_and_project_arguments` 签名与 plan 一致（call, tool_name, schema → typed result）
- ✅ `completed_outcome` / `failed_outcome` / `host_cancelled_outcome` 签名与 plan 一致（参数顺序有调整，不影响语义）
- ✅ `INVALID_ARGUMENT_ERROR` 固定为 `"invalid_argument"`
- ⚠️ `ToolBusinessCancelled` 字段与 plan 草案不同（见 Finding 1）

### No Any/object/untyped signatures

- ✅ 所有函数参数、返回值有完整类型标注
- ✅ 无 `Any`、`object`、无类型参数
- ✅ `ToolArgumentValidationResult` 联合类型通过 `TypeAlias` 明确

### Chinese docstrings

- ✅ 模块有中文概览 docstring
- ✅ 所有 public dataclass 有中文 docstring 含 params/returns/raises
- ✅ 所有 public 函数有中文 docstring 含 params/returns/raises
- ✅ 所有 private helper 有中文 docstring

### Parameter validation narrow, demand-driven, fail-closed

- ✅ `_SUPPORTED_FIELD_SCHEMA_KEYS` 白名单只含当前工具实际使用的关键字
- ✅ 未支持关键字（如 `oneOf`）fail-closed 返回 `invalid_argument`
- ✅ 非法 type 值 fail-closed
- ✅ 数组 items 仅支持标量类型
- ✅ schema 自身错误（非法 bound 值、非法 items schema）fail-closed 并提示 provider 修复

### invalid_argument behavior

- ✅ 错误码固定为 `INVALID_ARGUMENT_ERROR = "invalid_argument"`
- ✅ 不按字段名生成动态错误码
- ✅ `field_name` 为 unknown field key 或 `None`（规则一致）
- ✅ 所有 failure path 通过 `_failure()` 统一构造，确保错误码一致性

### host_cancelled_outcome

- ✅ reason 固定为 `TOOL_CANCELLED_REASON_HOST_CANCELLED`
- ✅ message 为 None 或空白时使用非空默认说明
- ✅ hint 为 None 或空白时使用非空默认提示
- ✅ 包含 `ToolResultMeta(tool_name, started_at, finished_at)`
- ✅ 无 governance 泄漏：message/hint/reason 不含 `run_id`、`session_id`、`correlation_id`、`cancellation_token`、`BatchToolExecutionContext` — 有直接测试证明（line 340-351）

### completed/failed outcomes include ToolResultMeta

- ✅ `completed_outcome` 通过 `_meta()` 构造 `ToolResultMeta`
- ✅ `failed_outcome` 通过 `_meta()` 构造 `ToolResultMeta`
- ✅ 三类 outcome 共享相同 `_meta()` helper，确保 meta 结构一致 — 有直接测试证明（line 300-308）

### Tests sufficient and coverage target

- ✅ 14 个测试覆盖核心验证路径
- ✅ 85% 覆盖率 ≥ 80% 目标
- ⚠️ Finding 2、3 指出的测试缺口在 15% missing 范围内，不影响达标判定

### Hidden behavior regressions

- ✅ 无 legacy adapter 修改，不会引入回归
- ✅ 公共契约无变更
- ✅ `dayu/runtime/__init__.py` 未修改，不破坏既有 runtime 导出
- ✅ `ToolBusinessFailure` / `ToolBusinessCancelled` 只导出类型，未接入任何 production 数据流，不改变运行时行为

## Open Questions

1. `ToolBusinessCancelled` 字段偏离 plan 的决策是 Codex 有意优化还是疏忽？若是优化，需在 implementation artifact 或 Slice 0 fix commit 中记录设计理由，并同步更新 Slice 1 callable 模板的 message/hint 转发路径。
2. Coverage missing 行中的 numeric range failure（行 497, 504, 679-688）是否应在本 Slice 0 fix gate 补齐，还是推迟到 Slice 1 由业务工具参数校验集成测试自然覆盖？

## Residual Risk

| 风险 | 严重程度 | Owner | 说明 |
|---|---|---|---|
| `ToolBusinessFailure` / `ToolBusinessCancelled` 的 message/hint 字段在后续 Slice 中如何消费尚未有集成测试 | 低 | Slice 1/2/3 | 当前仅导出类型定义，未经业务 helper → callable → outcome 完整链路验证 |
| `_FieldProjection.changed` 字段当前未被公共 API 暴露 | 低 | 后续 Slice | 若后续 slice 需要感知值转换（如 3.0→3），需扩展 API；当前无需处理 |
| 数组 items 的 `items.enum` 校验通过 `_project_field` → `_validate_enum` 间接覆盖，但无独立测试 | 低 | Slice 1 | enum 校验逻辑与顶层字段共享，逻辑正确；业务工具 schema 中暂无数组 items enum 的实际使用案例 |

## Final Status

**pass-with-findings**

Finding 1（ToolBusinessCancelled 字段偏离 plan）为中等严重度，需在 Slice 0 fix gate 或 controller adjudication 中裁决：接受当前设计并更新 plan 模板，或恢复 plan 设计。此 finding 不阻塞 Slice 0 进入 accepted slice commit，但必须在 Slice 1 开始前关闭——否则 callable 模板不一致会在 Slice 1 扩散。

Finding 2、3 为低严重度测试缺口，85% 覆盖率已达标，可推迟补齐。

Slice 0 可以 proceed to fix gate（针对 Finding 1 裁决和 plan 同步），或在 controller 接受 plan 偏离并记录为设计优化后直接进入 accepted slice commit。
