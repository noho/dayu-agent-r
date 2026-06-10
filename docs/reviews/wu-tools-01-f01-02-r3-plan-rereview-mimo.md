# WU-TOOLS-01-F01-02-R3 Plan Re-Review — AgentMiMo

- **Reviewed target**: `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`
- **Fix artifact**: `docs/reviews/wu-tools-01-f01-02-r3-plan-fix-codex.md`
- **Prior reviews**: `docs/reviews/wu-tools-01-f01-02-r3-plan-review-mimo.md`, `docs/reviews/wu-tools-01-f01-02-r3-plan-review-ds.md`
- **Controller adjudication**: `docs/reviews/wu-tools-01-f01-02-r3-plan-review-controller-adjudication.md`
- **Work unit**: WU-TOOLS-01-F01-02-R3
- **Gate**: plan re-review
- **Reviewer**: AgentMiMo
- **Timestamp**: 20260610-180314

---

## 1. Review Scope

本次 re-review 聚焦 controller 裁决接受的 PF-01 到 PF-09 九条 finding 的修复状态，以及 fix 是否引入新的具体阻塞问题。不重新审视已接受的 plan 方向。

---

## 2. PF Status Table

| PF | 描述 | 状态 | 证据 |
|---|---|---|---|
| PF-01 | 错误类型迁移表和目标模块 | **已修复** | §7 决策 5 增加完整迁移表（8 行），覆盖 `ToolArgumentError` → `ToolArgumentValidationFailure`、通用 `ToolBusinessError` → `ToolBusinessFailure`、取消 → 直接 `host_cancelled_outcome`、`FileAccessError` → `DocPathFailure`、Web 子类 → `WebToolFailure`（保留 `url`/`next_action`/`http_status`/`internal_diagnostics`）、Fins 参数 → runtime helper、Fins 业务 → `FinsReadFailure`。新位置全部明确：通用类型在 `dayu.runtime.tool_call_projection`，领域类型在各自领域模块。与代码事实核对：`ToolBusinessError` 有 `code`/`message`/`hint`/`extra` 四字段，Web 子类额外打包 `url`/`next_action`/`http_status`/`internal_diagnostics` 到 `extra` dict，`ToolArgumentError` 有 `tool_name`/`arg_name`/`arg_value`/`details`。迁移表的字段映射与实际代码使用模式一致。 |
| PF-02 | 取消策略收敛 | **已修复** | §7 决策 4 明确选择"直接返回 `ToolCancelledOutcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED)`"作为 native callable 主路径。明确排除私有 cancellation exception 作为跨 helper / callable / ToolRuntime 边界主路径。明确深层同步 helper 返回 typed cancelled result（`ToolBusinessCancelled`），由 callable 调用 `host_cancelled_outcome(...)`。§7 callable 模板展示了 `isinstance(business_result, ToolBusinessCancelled)` → `host_cancelled_outcome(...)` 的具体映射。与代码事实核对：当前三类工具（Doc/Web/Fins）全部通过 `ToolBusinessError(code="tool_cancelled")` 异常路径取消，被 legacy adapter 归一为 `ToolFailedOutcome`；plan 的直接返回策略是正确的修复方向，避免了 ToolRuntime 异常归一化路径的误转风险。 |
| PF-03 | per-provider asyncio.Lock 创建/共享/获取时机 | **已修复** | §7 决策 3 明确：每个 `build_*_tool_definitions(...)` 在函数体内创建一把 `asyncio.Lock()`，同 provider 返回的所有 callable 通过闭包共享。明确 lock 获取时机：参数校验、路径/URL/workspace 校验和 pre-cancel checkpoint 之后，阻塞业务或 `asyncio.to_thread(...)` 之前。明确不得在参数非法时排队等待 lock。§7 callable 模板展示 `async with provider_lock:` 在参数校验和路径校验之后。§8 Slice 1/2/3 各自重复确认。与代码事实核对：当前 `_AdaptedLegacyCallable` 使用 `LegacyToolConcurrencyPolicy.SERIAL_PER_PROVIDER`，`test_serial_per_provider_shares_lock_across_tool_names`（line 548）验证跨工具共享 lock。plan 的闭包共享模式保持了相同语义。 |
| PF-04 | 代表性 native callable 模板 | **已修复** | §7 增加完整 async callable 模板（约 85 行），覆盖：闭包捕获 config（`limits`, `allowed_roots`）、`validate_and_project_arguments`、`context.cancellation_token` 读取、pre-cancel checkpoint、`project_doc_path` 路径校验、`DocPathFailure` 处理、`async with provider_lock`、lock 内 pre-cancel、`asyncio.to_thread` 阻塞业务、`ToolBusinessFailure` / `ToolBusinessCancelled` / 成功到 outcome 的映射。模板后明确说明"该模板是实现约束，不要求逐字复制"，并列出必须保持的 8 个不变量。 |
| PF-05 | Slice 0 helper API 签名、typed result、invalid_argument、有限校验范围 | **已修复** | §8 Slice 0 增加 helper API 草案（约 60 行），包含：`ToolArgumentValidationResult` 类型别名、`ValidatedToolArguments` / `ToolArgumentValidationFailure` / `ToolBusinessFailure` / `ToolBusinessCancelled` 四个 frozen dataclass、`validate_and_project_arguments` / `completed_outcome` / `failed_outcome` / `host_cancelled_outcome` 四个函数签名。参数校验范围明确从 legacy adapter 和 Doc/Web/Fins 实际 schema 倒推，显式排除 `pattern`/`format`/`uniqueItems`/`multipleOf`/`oneOf`/`anyOf`/`allOf`/`not`/`if-then-else`/`$ref`/`$defs`/深层嵌套校验。`ToolArgumentValidationFailure.error` 固定为 `Literal["invalid_argument"]`。 |
| PF-06 | legacy adapter 测试行为迁移覆盖 | **已修复** | §8 Slice 4 增加 `tests/tools/test_legacy_tool_adapter.py 行为迁移清单`（8 行表格），逐项映射 legacy 测试行为到 Slice 0/1/2/3 的覆盖目标和删除条件。§8 Slice 1/2/3 各自增加等价覆盖要求：path projection、concurrency、truncate/display/tags/schema。与代码事实核对：legacy adapter 测试有 14 个函数，覆盖参数校验、路径投影、concurrency、outcome 投影、truncate spec、import boundary。plan 的迁移表完整覆盖了所有 current 行为测试；adapter-only 测试（如 `test_fetch_more_is_not_emitted_as_business_tool`、`test_collector_and_adapter_create_async_current_tool_callable`）标记为可直接删除。 |
| PF-07 | Fins fixture 迁移路径 | **已修复** | §8 Slice 3 Exact changes 增加明确要求：`tests/fins/test_fins_storage_provider.py` 的 `_discover_definitions(...)` / `_definitions_by_name(...)` 或同等 helper 不再依赖 `LegacyToolDeclarationCollector` / `adapt_collected_tools`，改为通过 provider `discover_tools(...)` 的 native output 或直接调用 `build_fins_read_tool_definitions(...)` 获取 definitions。Completion signal 增加：Fins 测试 fixture helper 不再调用 legacy collector / adapter。仍通过 `DefaultFinsRuntime.create(workspace_root=...)` / read runtime 构造，不得绕过 `dayu.fins.storage`。 |
| PF-08 | Web live smoke 残余追踪 | **已修复** | §8 Slice 2 Completion signal 增加：未运行真实网络 / Playwright smoke 时必须记录未验证场景、未验证原因、owner / destination。Stop condition 增加：live smoke 失败且指向 native callable 行为回归时不得关闭。§11 residual risk closeout expectation 增加明确要求。 |
| PF-09 | ToolCancelledOutcome.meta 构造和测试 | **已修复** | §6 Outcome 明确 cancelled outcome 必须携带 `ToolResultMeta(tool_name, started_at, finished_at)`，`meta` 不承载治理字段。§8 Slice 0 `host_cancelled_outcome` 签名草案包含 `tool_name`、`started_at`、`finished_at` 参数。§8 Slice 1/2/3 Tests 均要求"取消 outcome 的 `meta.tool_name`、`started_at`、`finished_at` 存在且不暴露 governance 字段"。§9 validation matrix 增加 meta 非空断言。与代码事实核对：`ToolCancelledOutcome` 定义于 `dayu/contracts/tool_outcome.py:93-135`，`meta` 类型为 `ToolResultMeta | None`；`ToolResultMeta` 定义于 `dayu/contracts/tool_result.py:26-60`，包含 `tool_name: str`、`started_at: datetime`、`finished_at: datetime`，构造期校验非空和时间一致性。 |

---

## 3. New Finding Introduced by Fix

### NF-01-低-host_cancelled_outcome 签草案中 message 参数与 ToolCancelledOutcome 契约不一致

- **位置**: §8 Slice 0 `host_cancelled_outcome` 签名草案（plan line 357）
- **问题类型**: 契约不一致
- **当前写法**: `host_cancelled_outcome(*, tool_name, started_at, finished_at, message: str | None = None, hint: str | None = None) -> ToolCancelledOutcome`
- **反例/失败场景**: `ToolCancelledOutcome.__post_init__` 校验 `self.message.strip() == ""` 时抛出 `ValueError`。若 implementation agent 传入 `message=None`，构造 `ToolCancelledOutcome(message=None, ...)` 时 `None.strip()` 会抛 `AttributeError`；若传入 `message=""`，`"".strip() == ""` 会抛 `ValueError`。
- **为什么有问题**: 签名草案允许 `None`，但底层契约要求非空字符串。Implementation agent 若不阅读 `ToolCancelledOutcome` 源码，可能直接传 `None` 导致运行时失败。
- **直接证据**: `dayu/contracts/tool_outcome.py:131-132`: `if self.message.strip() == "": raise ValueError(...)`。Plan line 357: `message: str | None = None`。
- **影响**: Implementation agent 在 Slice 0 测试或 Slice 1/2/3 集成时发现运行时错误 → 小范围返工。
- **建议改法和验证点**: `host_cancelled_outcome` 的 `message` 参数应改为 `str` 且提供合理默认值（如 `"工具调用已被取消。"`），或在 helper 内部将 `None` 映射为默认消息。Slice 0 测试增加 `message=None` 和 `message=""` 的边界断言。
- **修复风险（低/中/高）**: 低 — 只需改一个参数默认值。
- **严重程度（低）**: 不阻塞 plan 方向，implementation agent 在 pyright 或测试中会自然发现并修复。

---

## 4. Residual Risk 检查

| 风险 | 状态 | 说明 |
|---|---|---|
| Web `next_action` 字段迁移 | **已覆盖** | 迁移表明确 `WebToolFailure` 保留 `next_action` 字段，由 Web callable 投影到 cancelled outcome 的 `hint` 或作为领域本地字段保留。`internal_diagnostics` 不进入 LLM-facing outcome。 |
| `ToolCancelledOutcome` 签名草案 message 默认值 | **NF-01 已识别** | 见上。 |
| Slice 0 校验范围与实际 schema 匹配 | **已覆盖** | plan 明确从 legacy adapter 和三类工具实际 schema 倒推，排除未使用特性。Stop condition 要求发现 schema 使用未列入范围的关键字时停下补充。 |
| Web live smoke 未运行 | **已覆盖** | PF-08 修复后，Slice 2 completion signal 和 §11 均要求记录未验证场景和 owner。 |
| Fins fixture 迁移遗漏 | **已覆盖** | PF-07 修复后，Slice 3 Exact changes 和 Completion signal 均明确。 |
| 删除 adapter 后暴露额外生产 imports | **已覆盖** | §11 风险表和 Slice 4 validation commands 的全局 `rg` 验证。 |

---

## 5. Plan Code-Generation-Readiness 评估

| 维度 | 状态 | 说明 |
|---|---|---|
| Helper API 签名 | ✅ | Slice 0 给出完整类型定义和函数签名草案 |
| 取消策略 | ✅ | 直接返回 `ToolCancelledOutcome`，不抛异常 |
| 并发模型 | ✅ | per-builder `asyncio.Lock()` 闭包共享，获取时机明确 |
| 错误类型迁移 | ✅ | 8 行迁移表覆盖所有 legacy 类型到新类型/位置/outcome 投影 |
| Callable 模板 | ✅ | 85 行代表性模板，列出 8 个必须保持的不变量 |
| 测试迁移 | ✅ | 8 行行为迁移清单，逐项映射到 Slice 0/1/2/3 |
| Fins fixture | ✅ | 迁移路径和 completion signal 明确 |
| Web smoke | ✅ | 残余追踪要求和 owner 记录明确 |
| Meta 构造 | ✅ | 签名和测试要求明确 |
| Slice 独立性 | ✅ | Slice 0 → 1/2/3 → 4 依赖链清晰，每个 slice 有独立 completion signal 和 stop condition |

---

## 6. Open Questions

无 blocking open questions。

---

## 7. Overall Verdict

**pass**

PF-01 到 PF-09 全部已修复。Fix 引入的一条新 finding（NF-01）严重程度为低，不阻塞 implementation gate。Plan 已具备 code-generation-ready 条件：helper API 签名具体化、取消策略收敛、并发模型明确、错误类型迁移表完整、callable 模板可用、测试迁移路径清晰。

**Plan 可以进入 accepted plan gate。**
