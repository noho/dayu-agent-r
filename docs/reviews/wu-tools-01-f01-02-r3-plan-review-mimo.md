# WU-TOOLS-01-F01-02-R3 Plan Review — AgentMiMo

- **Reviewed target**: `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`
- **Work unit**: WU-TOOLS-01-F01-02-R3
- **Owner / destination**: GitHub Issue #130
- **Gate**: plan review
- **Reviewer**: AgentMiMo
- **Timestamp**: 20260610-174730

---

## 1. Assumptions Tested

| # | Assumption | Verdict | Evidence |
|---|-----------|---------|----------|
| A1 | Legacy adapter's `project_legacy_exception` projects `ToolBusinessError(code="tool_cancelled")` as `ToolFailedOutcome`, not `ToolCancelledOutcome` | **Confirmed** | `dayu/tools/_legacy_adapter/definition_adapter.py:358-382`: generic `ToolBusinessError` → `ToolFailedOutcome(error=error.code)`. No special handling for `tool_cancelled` code. |
| A2 | `ToolCancelledOutcome` exists as contract type with `host_cancelled` reason | **Confirmed** | `dayu/contracts/tool_outcome.py:45`: `TOOL_CANCELLED_REASON_HOST_CANCELLED: Final[ToolCancelledReason] = "host_cancelled"`. Already used in production: `dayu/host/run_input.py:1598`, `dayu/fins/tools/download_tools.py:132`, etc. |
| A3 | All three providers (Doc/Web/Fins) use legacy adapter pattern | **Confirmed** | `dayu/tools/doc_provider.py`, `dayu/tools/web/provider.py`, `dayu/fins/tools/provider.py` all import `LegacyToolDeclarationCollector`, `adapt_collected_tools`. |
| A4 | Cancellation tests currently assert `ToolFailedOutcome(error="tool_cancelled")` | **Confirmed** | All cancellation tests in `tests/tools/test_doc_tools_provider.py`, `tests/tools/web/test_web_tools_provider.py`, `tests/fins/test_fins_storage_provider.py` assert `ToolFailedOutcome` with `error == "tool_cancelled"`. Zero tests assert `ToolCancelledOutcome`. |
| A5 | `dayu.runtime` can depend on `dayu.contracts` | **Confirmed** | Existing modules already do: `dayu/runtime/cancellation.py` imports `CancellationToken`, `dayu/runtime/tools_discovery.py` imports `ToolDefinition` / `ToolBundle`. |
| A6 | `tool_call_projection.py` does not yet exist | **Confirmed** | File does not exist in `dayu/runtime/`. |
| A7 | Plan scope matches controller expectation (Doc/Web/Fins read only, not F08/F04-F07) | **Confirmed** | Non-goals §2 explicitly exclude F08 and F04-F07. |
| A8 | `ToolBusinessError` and `ToolArgumentError` are imported across all three tool domains | **Confirmed** | 10 production modules import from `_legacy_adapter`. See import boundary summary below. |

---

## 2. Import Boundary Summary (Direct Evidence)

| Module | Imports from `_legacy_adapter` |
|---|---|
| `dayu/tools/doc_provider.py` | `definition_adapter`, `registry_collector` |
| `dayu/tools/doc_tools.py` | `exceptions`, `registry_collector`, `tool_decorator`, `tool_errors` |
| `dayu/tools/web/provider.py` | `definition_adapter`, `registry_collector` |
| `dayu/tools/web/web_tools.py` | `registry_collector`, `tool_decorator`, `tool_errors` |
| `dayu/tools/web/web_search_providers.py` | `tool_errors.ToolBusinessError` |
| `dayu/fins/tools/provider.py` | `definition_adapter`, `registry_collector` |
| `dayu/fins/tools/fins_tools.py` | `registry_collector`, `tool_decorator` |
| `dayu/fins/tools/read_runtime.py` | `exceptions.ToolArgumentError`, `tool_errors.ToolBusinessError` |
| `dayu/fins/tools/read_runtime_helpers.py` | `exceptions.ToolArgumentError` |
| `dayu/fins/tools/search_engine.py` | `exceptions.ToolArgumentError`, `tool_errors.ToolBusinessError` |

---

## 3. Findings

### 01-未修复-高-Error type hierarchy for ToolBusinessError replacement not defined

- **位置**: §7 决策 5 "错误类型迁移但不兼容"
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: "将 `ToolBusinessError`、`ToolArgumentError`、`FileAccessError` 等从 legacy adapter 内部类型替换为 current helper 或领域本地私有类型。"
- **反例/失败场景**: Implementation agent 面对 `read_runtime.py`（十几处 `ToolBusinessError` 用法）、`search_engine.py`（7 个 cancellation checkpoint + 参数校验）、`web_tools.py`（有自定义 `ToolBusinessError` 子类带 `url`/`next_action`/`http_status` 字段）、`web_search_providers.py` 等模块时，必须自行决定：(a) 是否在 Slice 0 helper 中定义通用 `ToolValidationError` / `ToolBusinessCancelledError`？(b) Web 的 `ToolBusinessError` 子类的额外字段（`url`, `next_action`, `http_status`, `internal_diagnostics`）如何迁移？是保留子类还是扁平化到 outcome？(c) `ToolArgumentError` 是由 Slice 0 helper 提供还是各领域自定义？如果 agent 自行决定，三类工具的错误类型可能不一致，或与 outcome 构造逻辑不匹配。
- **为什么有问题**: 项目的编码硬约束要求"禁止魔法数字、魔法字符串"、"数据处理、存储、工具调用职责必须分离，重复逻辑必须抽取"。错误类型是工具 callable 的核心契约，若不预先定义，implementation agent 必须在迁移每个 slice 时重新设计，容易产生不一致的错误层级。
- **直接证据**:
  - `dayu/tools/web/web_tools.py:235-290`: Web 自定义 `ToolBusinessError` 子类带 `url`, `next_action`, `http_status`, `internal_diagnostics` 额外字段。
  - `dayu/fins/tools/read_runtime.py:119`: 定义 `_TOOL_CANCELLED_ERROR_CODE: Final = "tool_cancelled"` 常量。
  - `dayu/fins/tools/search_engine.py:59`: `_raise_if_search_cancelled` 使用 `ToolBusinessError(code="tool_cancelled")`。
  - `dayu/tools/_legacy_adapter/exceptions.py:52-87`: `ToolArgumentError` 构造含 `tool_name`, `arg_name`, `arg_value`, `details`。
- **影响**: Implementation agent 自行设计错误层级 → 三类工具错误类型不一致 → 后续返工 / review 不可验收。
- **建议改法和验证点**:
  1. 在 §7 决策 5 中明确 Slice 0 helper 提供哪些错误类型（建议：一个通用 `ToolValidationError` 替代 `ToolArgumentError`，以及 `host_cancelled_outcome(...)` 直接构造 `ToolCancelledOutcome`，不再需要 cancellation 专用异常）。
  2. 明确 Web 的 `ToolBusinessError` 子类迁移策略：额外字段是否进入 `ToolFailedOutcome.meta` / `ToolResultMeta`？还是保留在 Web 本地错误类型中由 callable 转为 outcome？
  3. 明确 Fins/Doc 的 `ToolBusinessError` 使用点如何替换：是改为直接 `return failed_outcome(...)` 还是抛领域本地异常由 callable 统一捕获？
- **修复风险（低/中/高）**: 中 — 决策本身不难，但必须在 plan 中明确，否则 implementation agent 需要跨 10 个模块自行设计。
- **严重程度（高）**: 阻塞 code-generation-ready。

### 02-未修复-高-Concurrency / lock migration strategy underspecified

- **位置**: §7 决策 3 "并发策略从 legacy adapter 的 per-provider lock 迁移"
- **问题类型**: 契约缺失 / 过度耦合风险
- **当前写法**: "并发策略从 legacy adapter 的 per-provider lock 迁移为 provider / builder 创建的 `asyncio.Lock`，由 native callable 显式共享。不得把 lock 藏在兼容 adapter。"
- **反例/失败场景**: 当前 `_AdaptedLegacyCallable` 使用 `SERIAL_PER_PROVIDER` 策略（一个 provider 内所有工具共享一把锁，串行执行）。三个 provider 都使用此策略。Native migration 后：(a) lock 放在哪里？在 `build_*_tool_definitions(...)` 函数内创建闭包共享？(b) 如果是闭包共享，callable 如何引用同一把 lock？(c) sync 业务逻辑通过 `asyncio.to_thread()` 执行时，lock 应该在 `to_thread` 之前还是之后获取？如果 agent 自行决定，可能产生：lock 不共享导致并发进入 sync 业务逻辑（数据竞争）、lock 放错位置导致死锁、或 lock 获取时机不对导致事件循环阻塞。
- **为什么有问题**: 当前 `SERIAL_PER_PROVIDER` 是生产行为。Native migration 必须保持此并发语义，否则是行为回归。且"不得把 lock 藏在兼容 adapter"只说了不该做什么，没说该怎么做。
- **直接证据**:
  - `dayu/tools/_legacy_adapter/definition_adapter.py`: `_AdaptedLegacyCallable` 使用 `LegacyToolConcurrencyPolicy.SERIAL_PER_PROVIDER`。
  - `tests/tools/test_legacy_tool_adapter.py`: `test_default_per_tool_serialization_prevents_concurrent_entry` 和 `test_serial_per_provider_shares_lock_across_tool_names` 测试并发行为。
- **影响**: 并发行为回归 / 死锁 / 事件循环阻塞 → 生产工具执行异常。
- **建议改法和验证点**:
  1. 在 §7 决策 3 中明确：每个 `build_*_tool_definitions(...)` 在函数体内创建一把 `asyncio.Lock()`，所有返回的 `ToolDefinition.callable` 闭包共享该 lock。
  2. 明确 lock 获取时机：在 callable 入口、参数校验之后、进入 `asyncio.to_thread()` 之前获取 lock。
  3. 明确测试要求：至少一个测试证明同一 provider 的两个工具不能并发进入业务逻辑。
- **修复风险（低/中/高）**: 低 — 实现模式简单，但必须写进 plan。
- **严重程度（高）**: 阻塞 code-generation-ready。

### 03-未修复-中-Execution context injection mechanism not described for native callables

- **位置**: §7 决策 2 "每个工具 callable 是 async `ToolCallable`，入参固定为 `(ToolCallRequest, BatchToolExecutionContext)`"
- **问题类型**: 不可直接实施
- **当前写法**: "每个工具 callable 是 async `ToolCallable`，入参固定为 `(ToolCallRequest, BatchToolExecutionContext)`，不再使用动态 `**keyword_arguments` adapter。"
- **反例/失败场景**: 当前 legacy adapter 通过 `execution_context_param_name="execution_context"` 机制将 `BatchToolExecutionContext` 注入到 sync 函数的命名参数中。Native callable 的签名是固定的 `(call, context)`，但业务函数（如 `read_file(path, ...)` ）需要从 `context` 中提取 `cancellation_token`、`allowed_roots`、`limits` 等配置。Plan 描述了目标签名但没有描述闭包如何捕获配置参数、callable 如何从 `context` 提取 token、以及 sync 业务函数如何被调用（直接调用 vs `asyncio.to_thread`）。
- **为什么有问题**: 每个工具的 callable 实现都需要：(1) 闭包捕获配置（`limits`, `allowed_roots`, `config` 等），(2) 从 `context.cancellation_token` 提取 token，(3) 调用 sync 业务函数（可能通过 `asyncio.to_thread`），(4) 处理异常转 outcome。这个模式必须在 plan 中明确，否则 16+ 个 callable 的实现方式可能不一致。
- **直接证据**:
  - `dayu/tools/doc_tools.py`: 5 个工具函数，每个都通过 `_resolve_doc_cancellation_token(execution_context)` 提取 token。
  - `dayu/fins/tools/fins_tools.py`: 9 个工具工厂函数，每个都通过 `_resolve_fins_cancellation_token(execution_context)` 提取 token。
  - `dayu/tools/web/web_tools.py`: 2 个工具函数，通过 `_resolve_execution_cancellation_token(execution_context)` 提取 token。
- **影响**: Implementation agent 自行决定闭包/提取/调用模式 → 16+ callable 实现风格不一致 → review 不可验收。
- **建议改法和验证点**:
  1. 在 §7 决策 2 或 §8 Slice 0 中补充 callable 实现模板：闭包捕获配置 → 从 `context` 提取 token → 参数校验 → 调用 sync 业务函数（通过 `asyncio.to_thread`）→ 异常转 outcome。
  2. 给出一个代表性 callable 的伪代码。
- **修复风险（低/中/高）**: 低 — 模式简单，但 plan 应给出模板。
- **严重程度（中）**: 增加 implementation agent 不一致风险。

### 04-未修复-中-Slice 0 argument validation scope vs current adapter behavior gap

- **位置**: §8 Slice 0 "覆盖 object 顶层 schema、unknown field、missing required、default、string/integer/number/boolean/array/object、enum、min/max、minLength/maxLength、minItems/maxItems"
- **问题类型**: 契约缺失
- **当前写法**: 列举了 JSON Schema 关键字覆盖范围，但未说明：(a) `ToolParametersSchema` 的 JSON 结构（`{"type": "object", "properties": {...}}`）如何与 `ToolCallRequest.arguments`（`dict[str, JsonValue]`）对齐？(b) 是否支持 `pattern`、`format`、`uniqueItems` 等 JSON Schema 关键字？(c) 校验失败时的 `ToolFailedOutcome` error code 是固定 `"invalid_argument"` 还是可配置？
- **反例/失败场景**: 当前 `argument_validator.py` 的 `validate_tool_arguments()` 处理了特定的 JSON Schema 子集。如果 Slice 0 helper 的校验范围不同（更宽或更窄），可能导致：参数校验行为回归（之前拒绝的参数现在通过）、或参数校验行为收紧（之前通过的参数现在拒绝）。
- **为什么有问题**: 参数校验是工具 callable 的第一道防线。行为变化直接影响工具可用性。
- **直接证据**:
  - `dayu/tools/_legacy_adapter/argument_validator.py`: 当前校验实现。
  - `tests/tools/test_legacy_tool_adapter.py:test_projection_coerces_defaults_and_rejects_invalid_arguments`: 测试当前校验行为。
- **影响**: 参数校验行为回归 → 工具调用失败或接受非法参数。
- **建议改法和验证点**:
  1. 明确 Slice 0 helper 的校验范围必须至少覆盖当前 `argument_validator.py` 的所有校验 case。
  2. 明确校验失败的 error code 固定为 `"invalid_argument"`。
  3. 明确 `ToolCallRequest.arguments` 顶层必须是 `{"type": "object"}` schema，helper 不处理非 object 顶层 schema。
- **修复风险（低/中/高）**: 低 — 范围明确即可。
- **严重程度（中）**: 可能在实施中暴露，但不会导致结构性失败。

### 05-未修复-低-Legacy adapter test behavior migration scope unclear

- **位置**: §8 Slice 4 "删除 `tests/tools/test_legacy_tool_adapter.py`，不迁移其'adapter 行为'测试；只将仍有 current 价值的参数校验 / outcome helper 测试保留在 Slice 0"
- **问题类型**: 测试缺口
- **当前写法**: 说明不迁移 adapter 行为测试，只保留参数校验和 outcome helper 测试。
- **反例/失败场景**: 当前 `test_legacy_tool_adapter.py` 有 805 行测试，覆盖：argument validation、path projection、exception-to-outcome mapping、concurrency serialization、`fetch_more` fail-fast、truncate spec conversion、import boundary。其中 path projection 和 concurrency serialization 是生产行为，不只是 adapter 内部测试。如果这些测试被删除但 native callable 没有等价测试覆盖，生产行为可能回归。
- **为什么有问题**: Path projection（`ToolPathValidationPolicy` with `must_exist=True`）和 concurrency（`SERIAL_PER_PROVIDER`）是 Doc tools 的生产行为。删除覆盖这些行为的测试而不补充等价测试，违反 CLAUDE.md 的"测试必须跟着实现边界迁移"约束。
- **直接证据**:
  - `tests/tools/test_legacy_tool_adapter.py`: `test_path_projection_uses_explicit_policy_not_collector_allowed_paths`、`test_incomplete_path_policy_coverage_fails_before_calling_migrated_function`、`test_default_per_tool_serialization_prevents_concurrent_entry`、`test_serial_per_provider_shares_lock_across_tool_names`。
- **影响**: 删除行为覆盖测试 → 生产行为回归无法被发现。
- **建议改法和验证点**:
  1. 在 Slice 1/2/3 的测试要求中明确：path projection 行为和 concurrency 行为必须有等价测试覆盖。
  2. 在 Slice 4 中明确：`test_legacy_tool_adapter.py` 中哪些测试的行为已被 Slice 0/1/2/3 等价覆盖，哪些可以安全删除。
- **修复风险（低/中/高）**: 低 — 只需明确覆盖要求。
- **严重程度（低）**: 不阻塞 plan，但实施时需注意。

---

## 4. Open Questions

| # | Question | Why it matters | Suggested resolution |
|---|---------|---------------|---------------------|
| Q1 | Web 的 `ToolBusinessError` 子类（`web_tools.py:235-290`，含 `url`/`next_action`/`http_status`/`internal_diagnostics`）迁移到哪里？ | 决定 Web 错误信息的 LLM-facing 可见性和诊断能力 | 建议：额外字段进入 `ToolFailedOutcome.meta`（`ToolResultMeta`），`error` code 保持业务语义（`fetch_failed`/`search_failed`/`permission_denied` 等），`message`/`hint` 保持 LLM-readable。 |
| Q2 | Fins `read_runtime.py` 定义的 `_TOOL_CANCELLED_ERROR_CODE: Final = "tool_cancelled"` 常量是否随 adapter 一起删除？ | 该常量只在 Fins 内部使用，删除 adapter 后不再需要 | 建议：随 adapter 一起删除，native callable 直接返回 `ToolCancelledOutcome`，不再需要 error code 常量。 |
| Q3 | Slice 0 helper 是否需要支持 `ToolAwaitingOutcome` 构造？ | F01-03 已有 download/upload/preprocess awaiting tools 使用 `ToolAwaitingOutcome` | 建议：不在本 WU scope 内。Slice 0 只提供 completed/failed/cancelled outcome helper。Awaiting 由 F01-03 已完成的工具自行构造。 |
| Q4 | `read_runtime_helpers.py` 导入 `ToolArgumentError` 用于参数校验。该模块的 `ToolArgumentError` 使用点是否应改为直接返回 `ToolFailedOutcome(error="invalid_argument")`？ | 决定 Fins 辅助函数是否需要依赖 runtime helper | 建议：`read_runtime_helpers.py` 的参数校验函数应改为返回 typed result（success/failure union），由上层 callable 转为 outcome。这样 helper 不依赖任何 error 类型。 |

---

## 5. Residual Risks / Uncovered Areas

| # | Risk | Severity | Owner / Destination |
|---|------|----------|---------------------|
| R1 | Tool schema digest 可能因 declaration 构造顺序或 dict ordering 变化 | Low | Plan §11 已识别，缓解方案合理 |
| R2 | 删除 adapter 后可能暴露额外 production imports（plan §11 已识别） | Medium | Slice 4 的 `rg` 验证 |
| R3 | Fins read runtime 错误类型迁移可能误伤 storage 边界 | Medium | Slice 3 stop condition |
| R4 | `dayu/fins/README.md` 和 `tests/README.md` 更新时机 | Low | Plan §10 已识别 |
| R5 | `web_search_providers.py` 的 `ToolBusinessError` 使用可能影响搜索 provider 错误传播 | Medium | Finding 01 的子问题 |

---

## 6. Plan Review Conclusion

**Overall verdict: pass-with-findings**

**理由**:

1. **动机成立**: `ToolBusinessError(code="tool_cancelled")` 被 legacy adapter 投影为 `ToolFailedOutcome(error="tool_cancelled")` 的 bug 已由直接代码证据确认。`ToolCancelledOutcome(reason="host_cancelled")` 已存在于 contracts 且已在 F01-03 的 download/upload/preprocess tools 中使用，R3 只需让 Doc/Web/Fins read tools 也走正确路径。

2. **范围正确**: Non-goals 清晰排除 F08/F04-F07，scope 边界明确。三类工具 + adapter deletion 的切分合理。

3. **设计对齐充分**: Plan 对 Host/Engine/runtime/tools 分层、Fins storage 边界、LLM-facing schema 不暴露治理字段、cancellation 语义等方面的设计对齐完整且有直接证据。

4. **需要修复的 finding**: 2 条高严重度（error type hierarchy、concurrency strategy）和 2 条中严重度（callable template、validation scope）finding 阻塞 code-generation-ready。这些 finding 不是架构问题，而是 plan 描述精度不足，修复成本低。

**Blocking open questions**: 无架构级阻塞。4 条 finding 都可以通过补充 plan 描述解决。

**能否进入 fix gate**: 是。Findings 都是 plan 描述层面的补全，不需要重新设计。
