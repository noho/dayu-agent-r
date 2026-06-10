# WU-TOOLS-01-F01-02-R3 Retire Legacy Tool Adapter Plan

## 1. Work Unit / Gate / Goal

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Gate: planning
- Destination: GitHub Issue #130 Retire legacy tool adapter
- Goal: 将剩余 Doc / Web / Fins read tools 从 `dayu/tools/_legacy_adapter` 迁移到当前 `ToolDefinition` / `ToolCallable` 原生实现，并删除 legacy adapter。Host 提供的 `CancellationToken` 触发的语义取消必须返回 `ToolCancelledOutcome(reason="host_cancelled")`，不能继续返回 legacy `ToolFailedOutcome(error="tool_cancelled")`。

成功信号：

- 生产代码中 `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools|tool_cancelled"` 不再命中需要保留的 legacy adapter 依赖；`tool_cancelled` 只允许作为历史测试名或删除前临时中间态，最终不应作为 Host token 取消的 failed outcome 错误码存在。
- Doc / Web / Fins read providers 仍通过 `ToolsDiscoveryProviderOutput.definitions` 暴露同名工具与同一 LLM-facing 参数 schema，不暴露 `execution_context`、`cancellation_token`、`run_id`、`correlation_id` 等治理字段。
- 所有由 `BatchToolExecutionContext.cancellation_token` 导致的工具停止，在工具 callable 层返回 `ToolCancelledOutcome`，reason 为 `TOOL_CANCELLED_REASON_HOST_CANCELLED`。
- adapter 目录和 legacy adapter 专属测试删除后，受影响 pytest 子集和 pyright 通过。

## 2. Non-goals / Scope Boundary

非目标：

- 不实施 WU-TOOLS-01-F08；不重命名 documents processor registry，不处理 `build_engine_processor_registry(...)`。
- 不实施 WU-TOOLS-01-F04/F05/F06/F07；SEC/Fins 与 CN/HK Docling CI pipeline / smoke 已由 GitHub Issues #121 / #122 追踪。
- 不修改 Engine 工具调用状态机，不改变 `ToolExecutor.execute(BatchToolExecutionRequest)` 协议。
- 不改变 Host admission、dispatch、EventLog、ToolRuntime accept barrier 或 wait-resume 状态机。
- 不改变财报 storage 规则；Fins 文档读取仍必须通过 `dayu.fins.storage` 与 `DefaultFinsRuntime` / read runtime 边界。
- 不引入兼容 re-export、兼容 facade 或仅透传旧导入路径的 wrapper。
- 不做外部长事务物理取消设计；该类问题仍归 WU-WAIT-03 / GitHub Issue #92。

范围边界：

- 本 WU 可以新增最小层中立 runtime helper，用于 current `ToolCallable` 的参数校验和 outcome 构造；该 helper 只能依赖标准库与 `dayu.contracts`。
- 本 WU 可以重构 Doc / Web / Fins read 工具内部函数形状，以便原生实现 current async `ToolCallable`。
- 本 WU 必须删除所有生产代码对 `dayu.tools._legacy_adapter` 的依赖；若发现额外生产 import，必须纳入本 WU，而不是留下 adapter。

## 3. Design Source Alignment

直接设计对齐：

- `docs/engine/design.md:270` 到 `docs/engine/design.md:318`：Engine 只通过 `ToolExecutor` 进行 batch handshake；`ToolDefinition` / `ToolCallable` 由 Host / ToolRuntime 持有，工具声明与执行治理不属于 Engine。
- `docs/engine/design.md:320` 到 `docs/engine/design.md:329`：工具 outcome 是 `ToolCompletedOutcome`、`ToolFailedOutcome`、`ToolAwaitingOutcome`、`ToolCancelledOutcome` 的封闭联合；completed / failed / cancelled 都会进入普通 tool result accepted 路径。
- `docs/engine/design.md:393` 到 `docs/engine/design.md:421`：Engine 只观察 cancellation token，不持有取消治理真源；ToolExecutor 返回 cancelled outcome 后，Engine 先接受工具结果，再由后续取消检查决定是否进入下一轮。
- `docs/host/design.md:71`：`ToolsDiscovery` 位于 `dayu.runtime`，只加载显式 provider callable，聚合 provider 返回的 `ToolDefinition`，不 import Host / Engine / Service / UI / Fins 或具体业务工具包。
- `docs/host/design.md:2020` 到 `docs/host/design.md:2129`：ToolRuntime 是 Host-owned governance module，使用 effective `ToolBundle` 投影 schema 给 Engine，并执行 `ToolDefinition.callable`；工具事实必须走 Host accept barrier。
- `docs/host/issues-implementation-control.md:195` 到 `docs/host/issues-implementation-control.md:203`：R3 当前 owner 是 GitHub Issue #130，要求分阶段 native 化并消除 legacy `tool_cancelled` failed outcome bug。
- `docs/host/issues-implementation-control.md:223`：R3 是 active planning work unit；`docs/host/issues-implementation-control.md:227` 明确 F08 是后续 pending WU。

边界结论：

- 取消 outcome 修复属于工具 callable / ToolRuntime 输入侧行为，不需要 Engine 新契约。
- Host cancellation token 仍只通过 `BatchToolExecutionContext` 进入 callable；不得进入 LLM-facing schema。
- `ToolCancelledOutcome` 已存在且 reason 常量包含 `host_cancelled`，设计源足够，不触发 stop condition。

## 4. First-principles Judgment and Direct Evidence

动机成立，且不是表面清理：

- current contract 已经把工具级取消建模为非失败终态，见 `dayu/contracts/tool_outcome.py:93` 到 `dayu/contracts/tool_outcome.py:141`。
- legacy adapter 的 `_AdaptedLegacyCallable.__call__` 捕获所有异常并调用 `project_legacy_exception`，见 `dayu/tools/_legacy_adapter/definition_adapter.py:90` 到 `dayu/tools/_legacy_adapter/definition_adapter.py:137`。
- `project_legacy_exception` 对所有 `ToolBusinessError` 都构造 `ToolFailedOutcome`，见 `dayu/tools/_legacy_adapter/definition_adapter.py:358` 到 `dayu/tools/_legacy_adapter/definition_adapter.py:382`。因此 `ToolBusinessError(code="tool_cancelled")` 被投影为失败 outcome，根因与数据路径同源。
- Doc 工具在 cancellation checkpoint 抛出 `ToolBusinessError(code="tool_cancelled")`，见 `dayu/tools/doc_tools.py:135` 到 `dayu/tools/doc_tools.py:173`。
- Web 工具在 `_raise_fetch_cancelled` 中抛出 `ToolBusinessError(code="tool_cancelled")`，见 `dayu/tools/web/web_tools.py:478` 到 `dayu/tools/web/web_tools.py:497`。
- Fins read tests 证明当前 read tools 取消也被断言为 failed `tool_cancelled`，见 `tests/fins/test_fins_storage_provider.py:647` 到 `tests/fins/test_fins_storage_provider.py:834`。
- Doc / Web / Fins providers 均仍通过 legacy collector 和 adapter 输出 current definitions：`dayu/tools/doc_provider.py:22` 到 `dayu/tools/doc_provider.py:30`、`dayu/tools/web/provider.py:21` 到 `dayu/tools/web/provider.py:28`、`dayu/fins/tools/provider.py:16` 到 `dayu/fins/tools/provider.py:23`。

需要挑战的过窄路径：

- 只改 `project_legacy_exception` 把 `tool_cancelled` 特判为 `ToolCancelledOutcome` 不是合格路径。它会保留 adapter、保留 OLD decorator / collector、保留同步 callable 投影，并与 Issue #130 “retire legacy adapter” 目标冲突。
- 只在 provider 本地复制一份 `adapt_collected_tools` 也不是合格路径。这样会把 legacy projection 行为复制到新名字里，且继续让 current callable 依赖 OLD 声明 metadata。
- 直接一次性迁移 Doc + Web + Fins read + 删除 adapter 过大。三类工具各自有不同业务 IO、路径安全、网络 fallback、Fins runtime / storage 边界和测试矩阵，应切成小 slice。

额外证据和范围修正：

- 除 controller 已观察到的三个 provider 外，生产代码还存在其它 legacy adapter import：`dayu/tools/doc_tools.py`、`dayu/tools/web/web_tools.py`、`dayu/tools/web/web_search_providers.py`、`dayu/fins/tools/fins_tools.py`、`dayu/fins/tools/read_runtime.py`、`dayu/fins/tools/read_runtime_helpers.py`、`dayu/fins/tools/search_engine.py`。删除 adapter 前必须一起迁移这些错误类型、decorator、collector 依赖。

## 5. Affected Files / Modules

生产代码预期涉及：

- 新增或修改 `dayu/runtime/tool_call_projection.py` 或等价最小 runtime helper。
- `dayu/tools/doc_provider.py`
- `dayu/tools/doc_tools.py`
- `dayu/tools/web/provider.py`
- `dayu/tools/web/web_tools.py`
- `dayu/tools/web/web_search_providers.py`
- `dayu/fins/tools/provider.py`
- `dayu/fins/tools/fins_tools.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/read_runtime_helpers.py`
- `dayu/fins/tools/search_engine.py`
- 删除 `dayu/tools/_legacy_adapter/**`

测试预期涉及：

- `tests/runtime/test_tool_call_projection.py` 或等价新增 runtime helper 测试。
- `tests/tools/test_doc_tools_provider.py`
- `tests/tools/web/test_web_tools_provider.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/tools/test_combined_tools_acceptance.py`
- 删除或迁移 `tests/tools/test_legacy_tool_adapter.py`
- `tests/host/test_import_boundary.py`
- `tests/runtime/test_tools_discovery.py` / `tests/runtime/test_tools_discovery_digest.py` 仅在 provider output digest 受声明字段变化影响时更新。

README / docs 后续触发：

- 修改 `dayu/fins/` 时，后续 implementation gate 必须先检查 `dayu/fins/README.md` 的 Agent 更新约束，并按职责判断是否更新。
- 修改 `tests/` 时，后续 implementation gate 必须按 `tests/README.md` 的 README 更新边界判断是否更新。当前 `tests/README.md:134` 到 `tests/README.md:138` 仍描述 legacy adapter 测试，adapter 删除后大概率需要更新。
- 若新增 `dayu/runtime` helper 且改变跨包工具声明/执行边界摘要，需检查 `dayu/README.md`；若只是内部 helper 且总览边界不变，可不改。
- 本 plan gate 不编辑 README。

## 6. Contract / Schema / State-machine / Public-interface Changes

Tool schema：

- 不改变工具名称。
- 不改变 LLM-facing 参数字段、required、enum、默认值、description、truncate spec、display name 或 tags，除非实现核对发现当前 schema 与实际 callable 已不一致；若必须改，implementation agent 必须先停下并给出 schema change 证据。
- 明确不新增 `execution_context`、`cancellation_token`、`run_id`、`session_id`、`iteration_id`、`timeout_seconds`、`correlation_id` 等治理字段。

Outcome：

- 成功仍为 `ToolCompletedOutcome(ToolResultSuccess)`.
- 参数错误、权限错误、文件不存在、Web 业务失败、Fins read 业务失败仍为 `ToolFailedOutcome(ToolResultFailure)`。
- Host cancellation token 导致的语义取消从 `ToolFailedOutcome(error="tool_cancelled")` 改为 `ToolCancelledOutcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED, ...)`。
- cancelled outcome 必须和 completed / failed outcome 一样携带 `ToolResultMeta(tool_name, started_at, finished_at)`；`meta` 只承载中性执行元信息，不承载 `run_id`、`session_id`、`correlation_id`、`cancellation_token` 或其它 Host governance 字段。
- 该 outcome change 是本 WU 的目标行为修复，不是 LLM-facing tool schema change。

Public interface：

- `dayu.tools._legacy_adapter` 删除；不提供旧路径兼容 re-export。
- `register_doc_tools(registry, ...)`、`register_web_tools(registry, ...)`、`register_fins_read_tools(registry, ...)` 这类 legacy collector 入口不作为兼容接口保留。若生产代码不再使用，测试应迁移到 provider / native definition builder。
- `ToolsDiscoveryProviderOutput`、`ToolDefinition`、`ToolCallable`、`BatchToolExecutionContext` 等公共契约不变。

State machine：

- 不改 Host / Engine 状态机。
- Engine 现有 cancelled outcome 分支继续接受工具结果；R3 只让工具 callable 返回正确 outcome。

## 7. Implementation Decisions and Native Tool Architecture

决策 1：先抽最小 current helper，再迁移具体工具。

- 建立层中立 helper 承担 current `ToolCallable` 共同需求：按 `ToolParametersSchema` 校验 `ToolCallRequest.arguments`、填充 schema default、构造 completed / failed / cancelled outcomes、表达工具内部业务错误和语义取消。
- helper 不依赖 Doc / Web / Fins，不读取配置，不做工具发现，不执行工具，不引入 Host / Engine import。
- helper 不能保存或解释 Host governance 字段，只消费 callable 已收到的 `BatchToolExecutionContext`。

决策 2：每个 provider 输出原生 `ToolDefinition`。

- Provider 继续负责 config 解析、provider id / version / source ref 和工具集合顺序校验。
- 具体工具模块暴露 `build_*_tool_definitions(...) -> tuple[ToolDefinition, ...]`，内部使用 current `dayu.contracts.tool_declaration.tool(...)` 或直接构造 `ToolDefinition`。
- 每个工具 callable 是 async `ToolCallable`，入参固定为 `(ToolCallRequest, BatchToolExecutionContext)`，不再使用动态 `**keyword_arguments` adapter。

决策 3：业务逻辑和 current callable 分层。

- 可保留或抽取现有同步业务 helper，但 callable 入口必须显式完成参数校验、路径校验、cancellation checkpoint、错误到 outcome 的投影。
- 阻塞文件 IO / 网络 IO 可继续通过 `asyncio.to_thread` 或既有异步边界执行，但必须在进入慢操作前和关键循环中检查 token。
- 并发策略从 legacy adapter 的 per-provider lock 迁移为每个 `build_*_tool_definitions(...)` 函数内部创建一把 `asyncio.Lock()`；该 builder 返回的所有 `ToolDefinition.callable` 通过闭包或显式参数共享同一个 lock 实例。
- lock 获取时机固定为：完成 schema 参数校验、路径 / URL / workspace 基础校验和 pre-cancel checkpoint 之后，进入阻塞业务逻辑或 `asyncio.to_thread(...)` 之前。不得在参数非法时排队等待 lock，也不得在持有 lock 前启动会触发业务副作用的慢操作。
- lock 释放由 `async with provider_lock:` 保证；不得把 lock 放入模块级全局单例，不得给同一 provider 内每个 callable 单独创建 lock。

决策 4：取消用专门语义表达。

- 不再抛 `ToolBusinessError(code="tool_cancelled")`。
- 本 WU 选择直接返回 `ToolCancelledOutcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED)` 作为 native callable 的主路径；不得把私有 cancellation exception 作为跨 helper、跨 callable 或 ToolRuntime 边界的主路径。
- 深层同步业务 helper 若确实需要从循环中提前退出，应返回 typed cancelled result 给同一 callable 边界，由 callable 调用 `host_cancelled_outcome(...)`；不得让 cancellation exception 逃逸到 ToolRuntime 的通用异常归一化路径。
- Web Playwright / `asyncio.CancelledError`、Fins read runtime checkpoint 和 Doc scan/read checkpoint 都必须在各自 callable 内转换为 `ToolCancelledOutcome(host_cancelled)`，且该转换发生在任何通用 `Exception` catch 或业务失败 catch 之前。

决策 5：错误类型迁移但不兼容。

- 将 `ToolBusinessError`、`ToolArgumentError`、`FileAccessError` 等从 legacy adapter 内部类型替换为 current helper 的 typed result 或领域本地私有错误类型。
- 不从 `dayu.tools._legacy_adapter` re-export 新类型。
- Web/Fins 业务模块需要的领域错误类型必须放在本领域模块内，不能从 `dayu.tools` 跨包导入到 `dayu.fins`。
- 最终 `rg "_legacy_adapter"` 为零。

旧错误类型迁移表：

| legacy 类型 / 用法 | 新类型 / 表达 | 新位置 | outcome 投影 |
|---|---|---|---|
| `ToolArgumentError`，以及 adapter 参数校验失败 | `ToolArgumentValidationFailure(error="invalid_argument", field_name, message, hint)` typed failure result | `dayu.runtime.tool_call_projection` | callable 调用 `failed_outcome(error="invalid_argument", ...)`；不进入业务逻辑 |
| 普通 `ToolBusinessError(code, message, hint)`，无领域额外字段 | `ToolBusinessFailure(error, message, hint)` typed failure result；仅用于 native callable 和同步业务 helper 之间的通用业务失败传递 | `dayu.runtime.tool_call_projection` | callable 调用 `failed_outcome(error=business.error, message=business.message, hint=business.hint, ...)` |
| `ToolBusinessError(code="tool_cancelled")` / `_TOOL_CANCELLED_ERROR_CODE` | 不设置替代异常；改为 token checkpoint 直接返回 typed cancelled result 或直接返回 cancelled outcome | `dayu.runtime.tool_call_projection.host_cancelled_outcome(...)` 负责构造 outcome | `ToolCancelledOutcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED, meta=ToolResultMeta(...))` |
| `FileAccessError` / Doc path 访问失败 | Doc-local `DocPathFailure(error, message, hint)` 或等价 frozen dataclass；不得放入 runtime helper | `dayu.tools.doc_tools` | `permission_denied`、`file_not_found` 或现有 Doc 业务错误码的 `ToolFailedOutcome` |
| Web `ToolBusinessError` 子类，含 `url`、`next_action`、`http_status`、`internal_diagnostics` | Web-local `WebToolFailure(error, message, hint, url, next_action, http_status, internal_diagnostics)` 或等价 frozen dataclass | `dayu.tools.web.web_tools` / `dayu.tools.web.web_search_providers` | `error` / `message` / `hint` 保持现有 LLM-readable 语义；`ToolResultMeta` 不扩展 arbitrary payload，`internal_diagnostics` 不进入 LLM-facing outcome |
| Fins read runtime / search engine 的 `ToolArgumentError` | 参数解析 helper 返回 typed validation failure，或 callable 先用 runtime helper 校验后再调用 Fins runtime | `dayu.runtime.tool_call_projection` 和 `dayu.fins.tools.read_runtime_helpers` | `ToolFailedOutcome(error="invalid_argument")` |
| Fins read runtime / search engine 的普通 `ToolBusinessError` | Fins-local `FinsReadFailure(error, message, hint)` 或通用 `ToolBusinessFailure`，取决于是否需要 storage / search 领域字段 | `dayu.fins.tools.read_runtime` / `dayu.fins.tools.search_engine` | 保持现有 Fins 业务错误码和 LLM-readable message / hint 的 `ToolFailedOutcome` |

代表性 native callable 模板：

```python
def build_doc_tool_definitions(
    limits: DocToolLimits,
    allowed_roots: tuple[Path, ...],
) -> tuple[ToolDefinition, ...]:
    provider_lock = asyncio.Lock()

    async def read_file_callable(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        started_at = datetime.now(UTC)
        validation = validate_and_project_arguments(
            call=call,
            tool_name=DOC_READ_FILE_TOOL_NAME,
            schema=DOC_READ_FILE_PARAMETERS,
        )
        if isinstance(validation, ToolArgumentValidationFailure):
            return failed_outcome(
                tool_name=DOC_READ_FILE_TOOL_NAME,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                error="invalid_argument",
                message=validation.message,
                hint=validation.hint,
            )

        token = context.cancellation_token
        if token.is_cancelled():
            return host_cancelled_outcome(
                tool_name=DOC_READ_FILE_TOOL_NAME,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )

        path_projection = project_doc_path(
            validation.arguments,
            allowed_roots=allowed_roots,
            must_exist=True,
        )
        if isinstance(path_projection, DocPathFailure):
            return failed_outcome(
                tool_name=DOC_READ_FILE_TOOL_NAME,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                error=path_projection.error,
                message=path_projection.message,
                hint=path_projection.hint,
            )

        async with provider_lock:
            if token.is_cancelled():
                return host_cancelled_outcome(
                    tool_name=DOC_READ_FILE_TOOL_NAME,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
            business_result = await asyncio.to_thread(
                read_file_business,
                path_projection.path,
                limits,
                token,
            )

        finished_at = datetime.now(UTC)
        if isinstance(business_result, ToolBusinessFailure):
            return failed_outcome(
                tool_name=DOC_READ_FILE_TOOL_NAME,
                started_at=started_at,
                finished_at=finished_at,
                error=business_result.error,
                message=business_result.message,
                hint=business_result.hint,
            )
        if isinstance(business_result, ToolBusinessCancelled):
            return host_cancelled_outcome(
                tool_name=DOC_READ_FILE_TOOL_NAME,
                started_at=started_at,
                finished_at=finished_at,
                message=business_result.message,
                hint=business_result.hint,
            )
        return completed_outcome(
            tool_name=DOC_READ_FILE_TOOL_NAME,
            started_at=started_at,
            finished_at=finished_at,
            value=business_result.value,
        )
```

该模板是实现约束，不要求逐字复制。implementation agent 可以用模块级私有 helper 去消除重复，但必须保持：闭包捕获 provider config、先校验参数、读取 `context.cancellation_token`、pre-cancel checkpoint、参数 / 路径失败不占用 lock、所有 provider 内 callable 共享同一 lock、阻塞业务通过 `asyncio.to_thread` 或既有 async 边界执行、取消直接返回 `ToolCancelledOutcome`。

## 8. Implementation Slices

### Slice 0: Current ToolCallable Support

Objective:

- 为 Doc / Web / Fins native callable 提供最小共享 current helper，避免三处复制参数校验和 outcome 构造。

Allowed files/modules:

- `dayu/runtime/tool_call_projection.py` 或同名新增 runtime helper。
- `tests/runtime/test_tool_call_projection.py`。
- 仅在 export 真有必要时修改 `dayu/runtime/__init__.py`；默认不导出，保持私有模块使用。

Exact changes:

- 新增参数校验函数，输入为 `ToolCallRequest`、工具名、`ToolParametersSchema`，输出 typed success/failure 联合；失败码固定为 `invalid_argument`。
- 新增 outcome helper：`completed_outcome(...)`、`failed_outcome(...)`、`host_cancelled_outcome(...)`。
- 新增 current typed result 类型，用于参数校验、通用业务失败和同步业务 helper 内部取消信号；不新增跨 callable 的 cancellation exception。
- 所有函数、类、模块提供完整中文 docstring。

Slice 0 helper API 草案：

```python
INVALID_ARGUMENT_ERROR_CODE: Final = "invalid_argument"

@dataclass(frozen=True, slots=True)
class ValidatedToolArguments:
    arguments: Mapping[str, JsonValue]

@dataclass(frozen=True, slots=True)
class ToolArgumentValidationFailure:
    error: Literal["invalid_argument"]
    field_name: str | None
    message: str
    hint: str | None

ToolArgumentValidationResult: TypeAlias = (
    ValidatedToolArguments | ToolArgumentValidationFailure
)

@dataclass(frozen=True, slots=True)
class ToolBusinessFailure:
    error: str
    message: str
    hint: str | None

@dataclass(frozen=True, slots=True)
class ToolBusinessCancelled:
    message: str | None
    hint: str | None

def validate_and_project_arguments(
    call: ToolCallRequest,
    tool_name: str,
    schema: ToolParametersSchema,
) -> ToolArgumentValidationResult: ...

def completed_outcome(
    *,
    tool_name: str,
    started_at: datetime,
    finished_at: datetime,
    value: JsonValue,
) -> ToolCompletedOutcome: ...

def failed_outcome(
    *,
    tool_name: str,
    started_at: datetime,
    finished_at: datetime,
    error: str,
    message: str,
    hint: str | None,
) -> ToolFailedOutcome: ...

def host_cancelled_outcome(
    *,
    tool_name: str,
    started_at: datetime,
    finished_at: datetime,
    message: str | None = None,
    hint: str | None = None,
) -> ToolCancelledOutcome: ...
```

Typed result 字段语义：

- `ValidatedToolArguments.arguments` 是应用 default 后的参数映射；字段名与 LLM-facing schema 同名，不包含治理字段。
- `ToolArgumentValidationFailure.error` 固定为 `invalid_argument`，不得根据字段名生成新错误码。
- `ToolArgumentValidationFailure.field_name` 是失败字段名；unknown field 使用该 unknown key，顶层结构错误使用 `None`。
- `ToolBusinessFailure` 只表达 native callable 与同步业务 helper 之间的通用失败传递；领域额外字段必须使用领域本地类型。
- `ToolBusinessCancelled` 只允许作为同一工具业务 helper 返回值，供 callable 立刻映射为 `host_cancelled_outcome(message=business_result.message, hint=business_result.hint, ...)`；不得跨 ToolRuntime 边界传播。`message` / `hint` 是业务 helper 对本次取消的可选说明，为空时由 `host_cancelled_outcome(...)` 使用默认说明与默认提示。

参数校验范围：

- 范围从当前 legacy adapter `argument_validator.py` 行为、Doc / Web / Fins read 工具实际 schema 倒推，不实现完整 JSON Schema validator。
- 必须覆盖：顶层 `ToolParametersSchema(type="object")`、`required`、unknown field、`additional_properties=False`、default 填充、`type` 为 `string` / `integer` / `number` / `boolean` / `array` / `object` 的当前使用形态、`enum`、`minimum` / `maximum`、`minLength` / `maxLength`、`minItems` / `maxItems`、数组 `items.type` 和 `items.enum`。
- `integer` 必须拒绝 `bool`；`number` 必须拒绝非有限浮点；`array` 的 item 校验只支持当前工具实际使用的标量 item schema。
- 未使用且本 WU 明确排除的 JSON Schema 高级特性：`pattern`、`format`、`uniqueItems`、`multipleOf`、`oneOf`、`anyOf`、`allOf`、`not`、`if` / `then` / `else`、`$ref`、`$defs`、深层 required / nested object validation。未来工具确有需求时，由该工具对应 WU 扩展 helper。
- helper 自身配置错误可以抛 `ValueError`，因为这是 provider / schema 实现错误；用户参数错误必须返回 `ToolArgumentValidationFailure`。

Data flow:

`ToolCallRequest.arguments` -> schema validation / default projection -> typed mapping -> concrete native callable business helper -> outcome helper -> `ToolExecutionOutcome`.

Cancellation semantics:

- Slice 0 只提供 cancelled outcome 构造，不主动观察 token。
- `host_cancelled_outcome` reason 固定为 `TOOL_CANCELLED_REASON_HOST_CANCELLED`，message / hint 不暴露 Host 内部字段。
- `host_cancelled_outcome` 必须构造 `ToolResultMeta(tool_name, started_at, finished_at)` 并放入 `ToolCancelledOutcome.meta`；`meta` 不允许为取消原因增加 arbitrary payload。

Error handling:

- 参数校验失败不抛业务异常，返回 typed failure projection，由 callable 转成 `ToolFailedOutcome(error="invalid_argument")`。
- helper 自身配置错误可以抛 `ValueError`，因为这是 provider / schema 实现错误。

Tests:

- 参数合法、unknown、missing、default、枚举、数组 item、数字边界。
- cancelled outcome reason / message / hint 非空，且不包含 `cancellation_token`、`BatchToolExecutionContext`、`run_id` 等治理词。
- cancelled outcome meta 非空，`tool_name` / `started_at` / `finished_at` 与输入一致。
- 参数校验失败 outcome 投影固定使用 `invalid_argument`。
- 不支持的 JSON Schema 高级特性不进入测试矩阵；若当前 Doc / Web / Fins schema 使用到未列入范围的关键字，Slice 0 必须先停下并补充需求证据。
- pyright 覆盖新增联合类型的消费。

Validation commands:

- `source .venv/bin/activate && pytest tests/runtime/test_tool_call_projection.py`
- `source .venv/bin/activate && pyright`

Completion signal:

- helper 测试通过，且无业务工具迁移依赖 legacy adapter 新增使用。

Stop condition:

- 若需要改变 `ToolCallRequest`、`ToolParametersSchema` 或 `ToolExecutionOutcome` 公共契约，停止并进入 design decision，不在本 slice 偷改契约。

### Slice 1: Doc Native Tools

Objective:

- 将五个 Doc tools 原生化，移除 `dayu/tools/doc_provider.py` 与 `dayu/tools/doc_tools.py` 对 legacy adapter 的依赖。

Allowed files/modules:

- `dayu/tools/doc_provider.py`
- `dayu/tools/doc_tools.py`
- `tests/tools/test_doc_tools_provider.py`
- 必要时 `tests/tools/test_combined_tools_acceptance.py`

Exact changes:

- 用 `build_doc_tool_definitions(limits: DocToolLimits, allowed_roots: tuple[Path, ...]) -> tuple[ToolDefinition, ...]` 替换 legacy collector 注册路径。
- `build_doc_tool_definitions(...)` 在函数体内创建一把 `asyncio.Lock()`；五个 Doc callable 共享该 lock。
- `discover_tools` 保持 provider id、version、source ref、allowed_paths fail closed 行为不变。
- 每个 Doc tool 定义 current `ToolDefinition`，工具名顺序保持 `list_files`、`get_file_sections`、`search_files`、`read_file`、`read_file_section`。
- 将 legacy decorator metadata 中的 schema / tags / display / truncate 转为 current declaration 常量或 builder 函数。
- 把路径校验从 adapter `_project_paths` 迁入 Doc native callable：路径参数必须在 `allowed_roots` 下，`must_exist=True`，进入业务逻辑前投影为绝对路径。
- 保留 list/search 返回路径可直接链到 read tools 的行为，在 Doc 业务输出处显式投影绝对路径。
- 移除 `register_doc_tools(registry, ...)` 或改为不再存在的 native builder；不得保留只为旧 tests 服务的 collector 入口。

Data flow:

`ToolsDiscoveryProviderSpec.config` -> `DocToolLimits` / `allowed_roots` -> `build_doc_tool_definitions` -> `ToolDefinition.callable` -> 参数校验 -> 路径校验 -> cancellation checkpoint -> Doc business helper -> completed / failed / cancelled outcome.

Cancellation semantics:

- callable 从 `context.cancellation_token` 读取 token。
- 进入工具、遍历目录、创建 processor、搜索循环、编码 fallback、章节读取前后继续保留 checkpoint。
- token 已取消或 checkpoint 发现取消时返回 `ToolCancelledOutcome(reason="host_cancelled")`。
- 不再生成 `ToolFailedOutcome(error="tool_cancelled")`。

Error handling:

- 参数 schema 错误: `ToolFailedOutcome(error="invalid_argument")`。
- 白名单外路径: `ToolFailedOutcome(error="permission_denied")`。
- 文件不存在: `ToolFailedOutcome(error="file_not_found")`。
- Doc business validation: 保持原错误码和 LLM-readable message / hint，但通过 current error type 或直接 failed outcome 构造。
- 未预期异常: `ToolFailedOutcome(error="execution_error")`，不泄露内部 traceback。

Tests:

- 现有 provider discovery 精确五工具。
- schema 不暴露 `execution_context` / `cancellation_token`。
- 预取消、搜索中取消、编码 fallback 中取消全部断言 `ToolCancelledOutcome` 且 reason 为 host_cancelled。
- 取消 outcome 的 `meta.tool_name`、`started_at`、`finished_at` 存在且不暴露 governance 字段。
- 白名单外路径不进入业务体。
- list/search 返回 path 可链到 read tools。
- path projection 等价覆盖 `tests/tools/test_legacy_tool_adapter.py` 中的显式 path policy、`must_exist=True`、白名单外路径拒绝行为。
- concurrency 等价覆盖 legacy `SERIAL_PER_PROVIDER` 行为：同一 provider 的两个不同 Doc tool 并发调用时，不得并发进入同步业务体。
- success / failure 不含 OLD ok/value envelope。
- AST / source 测试改为断言没有 `_legacy_adapter`、`LegacyToolDeclarationCollector`、`adapt_collected_tools`。
- ToolRuntime accept barrier 集成仍通过。

Validation commands:

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py`
- `source .venv/bin/activate && pytest tests/tools/test_combined_tools_acceptance.py -k doc`
- `source .venv/bin/activate && pyright`

Completion signal:

- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu/tools/doc_provider.py dayu/tools/doc_tools.py tests/tools/test_doc_tools_provider.py` 无命中。

Stop condition:

- 若迁移中发现必须改变 Doc tool 名称、参数或返回 shape 才能通过测试，停止并报告 schema / contract change 需求。

### Slice 2: Web Native Tools

Objective:

- 将 `search_web` 和 `fetch_web_page` 原生化，移除 Web provider / Web tools / search providers 对 legacy adapter 的依赖。

Allowed files/modules:

- `dayu/tools/web/provider.py`
- `dayu/tools/web/web_tools.py`
- `dayu/tools/web/web_search_providers.py`
- `tests/tools/web/test_web_tools_provider.py`
- 必要时 `tests/tools/web/test_smoke_web_ci.py`

Exact changes:

- 用 `build_web_tool_definitions(config: WebToolsConfig) -> tuple[ToolDefinition, ...]` 替换 legacy collector。
- `build_web_tool_definitions(...)` 在函数体内创建一把 `asyncio.Lock()`；`search_web` 与 `fetch_web_page` callable 共享该 lock。
- `discover_tools` 保持 config 解析、provider id、version、source ref 和工具顺序不变。
- 将 `ToolBusinessError` 改为 current Web domain error 或 runtime helper error，不再继承 legacy adapter error。
- `search_web` / `fetch_web_page` callable 直接消费 `ToolCallRequest` 与 `BatchToolExecutionContext`。
- 保留 provider config 闭包投影：provider、request timeout、max search results、fetch truncate chars、private URL policy、Playwright channel / storage state。
- 保留 Web truncate specs、tags、display name 和 deterministic fallback 行为。

Data flow:

`ToolsDiscoveryProviderSpec.config` -> `WebToolsConfig` -> native definitions -> argument validation -> cancellation checkpoint -> search/fetch orchestrator -> completed / failed / cancelled outcome.

Cancellation semantics:

- pre-cancel 不调用 provider。
- provider attempt 间取消停止 fallback。
- Playwright fallback 抛出的 cancellation 映射为 `ToolCancelledOutcome(host_cancelled)`。
- 网络业务失败仍是 failed outcome，不与 semantic cancellation 混淆。

Error handling:

- URL 类型 / schema 参数错误在进入 Web 逻辑前 failed `invalid_argument`。
- private/local URL 未启用时仍 failed `permission_denied` 或现有等价业务错误码。
- 搜索 provider 业务失败、fetch 失败保持现有 LLM-readable message / hint。
- 未预期异常 failed `execution_error`。

Tests:

- Web schema 不暴露 governance fields。
- default 拒绝 private/local URL，显式配置后允许。
- provider config 投影、fetch truncate、Playwright channel/storage state 保持。
- pre-cancel、attempt 间 cancel、Playwright cancel 改断言 `ToolCancelledOutcome(host_cancelled)`。
- 取消 outcome 的 `meta.tool_name`、`started_at`、`finished_at` 存在且不暴露 governance 字段。
- 搜索业务失败仍是 `ToolFailedOutcome`。
- concurrency 等价覆盖 legacy `SERIAL_PER_PROVIDER` 行为：同一 Web provider 的 `search_web` 与 `fetch_web_page` 不得并发进入 provider / fetch 业务体。
- AST import 断言无 `_legacy_adapter`。

Validation commands:

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py`
- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py`
- `source .venv/bin/activate && pyright`

Completion signal:

- `rg "_legacy_adapter|LegacyToolDeclarationCollector|LegacySyncToolCallable|adapt_collected_tools" dayu/tools/web tests/tools/web/test_web_tools_provider.py` 无生产依赖命中。
- 若没有运行真实网络 / Playwright live smoke，Slice 2 closeout 必须记录未验证场景、未验证原因、owner / destination。至少记录：真实网络搜索 provider fallback、Playwright browser 启动后取消、真实页面 fetch truncate 与 storage state / channel 组合。
- 若存在本地 fixture / offline 模式，优先运行 `utils/smoke_web_ci.py --external-limit 0` 或项目实际支持的等价命令，并在 closeout 中记录结果。

Stop condition:

- 若 deterministic pytest 无法覆盖 provider config / cancellation，先补测试替身再继续。
- 若 live smoke 失败且失败原因指向 native callable 行为回归，本 slice 不得关闭；若只是环境缺失或外网不可用，按上方 residual tracking 要求记录 owner 后继续。

### Slice 3: Fins Read Native Tools

Objective:

- 将九个 Fins read tools 原生化，移除 Fins read provider / read runtime / search engine 对 legacy adapter 的依赖，同时保持 `dayu.fins.storage` 边界。

Allowed files/modules:

- `dayu/fins/tools/provider.py`
- `dayu/fins/tools/fins_tools.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/read_runtime_helpers.py`
- `dayu/fins/tools/search_engine.py`
- `tests/fins/test_fins_storage_provider.py`

Exact changes:

- 用 `build_fins_read_tool_definitions(read_runtime: FinsReadRuntime, limits: FinsToolLimits) -> tuple[ToolDefinition, ...]` 替换 legacy collector。
- `build_fins_read_tool_definitions(...)` 在函数体内创建一把 `asyncio.Lock()`；九个 Fins read callable 共享该 lock。
- `discover_tools` 保持 `include_read_tools=false` 返回空集合且不解析 workspace root；启用时仍要求绝对 `workspace_root`。
- Fins read provider 继续通过 `DefaultFinsRuntime.create(workspace_root=...)` 获取 read runtime；不得绕过 storage 直接拼路径读取财报文件。
- 将 read runtime / search engine 的 legacy `ToolArgumentError` / `ToolBusinessError` 替换为 current helper或 Fins-local typed error。
- 保持九工具顺序：`list_documents`、`get_document_sections`、`read_section`、`search_document`、`list_tables`、`get_table`、`get_page_content`、`get_financial_statement`、`query_xbrl_facts`。
- 保留 tags、display name、truncate specs、limits 解析和返回 shape。
- 更新 `tests/fins/test_fins_storage_provider.py` 中的 fixture helper：`_discover_definitions(...)`、`_definitions_by_name(...)` 或同等 helper 不再依赖 `LegacyToolDeclarationCollector` / `adapt_collected_tools`，改为通过 provider `discover_tools(...)` 的 native output 或直接调用 `build_fins_read_tool_definitions(...)` 获取 definitions。
- Fins fixture 仍必须通过 `DefaultFinsRuntime.create(workspace_root=...)` / read runtime 构造，不得绕过 `dayu.fins.storage` 直接拼路径读取 fixture 文件。

Data flow:

`ToolsDiscoveryProviderSpec.config` -> `workspace_root` / `FinsToolLimits` -> `DefaultFinsRuntime` -> `FinsReadRuntime` -> native definitions -> argument validation -> cancellation checkpoint -> read runtime / search engine -> completed / failed / cancelled outcome.

Cancellation semantics:

- pre-cancel 不进入 durable read work。
- search loop、semantic enrichment、processor 创建后读取前、父标题查询、XBRL facts filtering 等现有 checkpoint 继续保留。
- cancellation checkpoint 返回 `ToolCancelledOutcome(host_cancelled)`。
- 不吞掉 cancellation；不得在 semantic enrichment 降级块把 cancellation 当普通失败或空结果处理。

Error handling:

- 参数错误 failed `invalid_argument`。
- storage / processor / section / table / facts 业务错误保持现有错误码和 LLM-readable message / hint。
- cancellation 专用路径优先于业务错误 catch。
- Fins storage 访问继续由仓储协议 / read runtime 负责。

Tests:

- provider 发现九个带 `fins` tag 的 read tools。
- schema 不暴露 governance fields。
- `include_read_tools=false` 行为不变。
- `list_documents` 与 `search_document` 通过 current ToolRuntime accept path 执行。
- pre-cancel、search loop cancel、semantic enrichment cancel、read before processor cancel、parent title lookup cancel、XBRL filtering cancel 改断言 `ToolCancelledOutcome(host_cancelled)`。
- 取消 outcome 的 `meta.tool_name`、`started_at`、`finished_at` 存在且不暴露 governance 字段。
- 参数错误、失败 outcome、truncate spec、workspace overlay 行为保持。
- Fins fixture helper 不再调用 legacy collector / adapter；测试 source 或 AST 断言无 `_legacy_adapter`。
- concurrency 等价覆盖 legacy `SERIAL_PER_PROVIDER` 行为：同一 Fins read provider 的两个 read tools 不得并发进入 read runtime 业务体。
- AST import boundary 断言 Fins / Engine / runtime 边界不反向依赖，且无 `_legacy_adapter`。

Validation commands:

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py`
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -k cancellation`
- `source .venv/bin/activate && pyright`

Completion signal:

- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools|ToolBusinessError\\(.*tool_cancelled" dayu/fins/tools tests/fins/test_fins_storage_provider.py` 无生产依赖命中。
- `tests/fins/test_fins_storage_provider.py` 的 definitions fixture 已迁移到 native provider / builder，且仍通过 `dayu.fins.storage` 仓储边界准备财报材料。

Stop condition:

- 若 native migration 需要改变 Fins read runtime 或 storage public contract，停止并进入 design discussion；不得为了删除 adapter 绕过 `dayu.fins.storage`。

### Slice 4: Adapter Deletion and Boundary Closeout

Objective:

- 删除 legacy adapter 目录和 legacy adapter 专属测试，更新 import boundary / combined acceptance / README 事实，完成 R3。

Allowed files/modules:

- `dayu/tools/_legacy_adapter/**`
- `tests/tools/test_legacy_tool_adapter.py`
- `tests/tools/test_combined_tools_acceptance.py`
- `tests/host/test_import_boundary.py`
- `tests/README.md`
- 按 README 触发规则必要时 `dayu/README.md`、`dayu/fins/README.md`

Exact changes:

- 删除 `dayu/tools/_legacy_adapter` 整个目录。
- 删除 `tests/tools/test_legacy_tool_adapter.py` 前，必须确认其中仍有 current 价值的行为已在 Slice 0/1/2/3 等价覆盖；adapter-only decorator / collector / OLD projection 测试可直接删除。
- 更新 combined acceptance 中允许 `_legacy_adapter` 存在的断言。
- 更新 host import boundary 中对 `_legacy_adapter` reserved-name 防御性引用的例外。
- 更新 `tests/README.md`：业务工具测试不再描述 legacy adapter；改为描述 current native Doc / Web provider 与 Fins read provider。
- 若 `dayu/fins/README.md` 中 Fins read provider 描述仍准确，可不改；若提到迁移 / OLD adapter，则必须更新。

`tests/tools/test_legacy_tool_adapter.py` 行为迁移清单：

| legacy adapter 测试行为 | 迁移目标 | 删除条件 |
|---|---|---|
| 参数 schema validation、default projection、unknown / missing / enum / range / array item | Slice 0 `tests/runtime/test_tool_call_projection.py` | Slice 0 helper tests 覆盖固定 `invalid_argument` 和 projected arguments 后删除 |
| exception-to-outcome mapping 的普通业务失败 | Slice 0 outcome helper tests 加 Doc/Web/Fins provider failure tests | completed / failed helper 与各领域业务失败测试均通过后删除 |
| legacy `ToolBusinessError(code="tool_cancelled")` 投影为 failed outcome | 不迁移；这是本 WU 要删除的错误行为 | Doc/Web/Fins cancellation tests 全部改断言 `ToolCancelledOutcome(host_cancelled)` 后删除 |
| path projection、allowed roots、`must_exist=True` | Slice 1 Doc provider tests | Doc 白名单、文件不存在、list/search path 可链 read tools 覆盖后删除 |
| per-tool / per-provider serialization | Slice 1 Doc、Slice 2 Web、Slice 3 Fins concurrency tests | 三个 provider 都证明同一 provider 内共享 lock 后删除 |
| truncate spec / display / tags / schema conversion | Slice 1/2/3 provider discovery tests 与 combined acceptance | native `ToolDefinition` 的 truncate / display / tags / schema 与旧期望等价后删除 |
| `fetch_more` fail-fast 或 adapter reserved-name 防御 | Slice 4 combined acceptance / import boundary tests | 当前 native tools 不再依赖 adapter reserved behavior，boundary tests 更新后删除 |
| collector / decorator OLD metadata 组装细节 | 不迁移；adapter-only 实现细节 | 所有生产 provider 已使用 native builder 后删除 |

Data flow:

无运行时新 data flow；本 slice 是删除旧路径和测试 / 文档事实收口。

Cancellation semantics:

- 用全局 rg 和测试证明不再有 legacy `tool_cancelled` failed outcome 路径。

Error handling:

- 删除后 import error 应由测试暴露；不得新增旧路径 facade。

Tests:

- `rg "_legacy_adapter" dayu tests` 仅允许历史文档或本 plan artifact 命中；生产和测试代码不得命中。
- `pytest` 子集覆盖 tools / fins / runtime / service import boundary。
- pyright 全量通过。
- Slice 4 closeout 必须确认 PF-06 的行为迁移清单已逐项关闭，不能用“adapter 测试已删除”替代等价行为覆盖证据。

Validation commands:

- `source .venv/bin/activate && pytest tests/runtime/test_tool_call_projection.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py tests/fins/test_fins_storage_provider.py tests/tools/test_combined_tools_acceptance.py tests/host/test_import_boundary.py tests/service/test_import_boundary.py`
- `source .venv/bin/activate && pyright`
- `git diff --check`
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests`

Completion signal:

- adapter 目录不存在。
- 所有 production provider 输出 current native `ToolDefinition`。
- 所有 R3 受影响测试和 pyright 通过。

Stop condition:

- 若删除 adapter 后发现仍有非 Doc / Web / Fins read 生产工具依赖 adapter，必须停下并重新裁决 scope；不能留下半删除状态。

## 9. Tests / Validation Matrix

每个 implementation slice 后必须运行：

- `source .venv/bin/activate && pytest <affected test files>`
- `source .venv/bin/activate && pyright`

最终 R3 closeout 必须运行：

- `source .venv/bin/activate && pytest tests/runtime/test_tool_call_projection.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py tests/fins/test_fins_storage_provider.py tests/tools/test_combined_tools_acceptance.py tests/host/test_import_boundary.py tests/service/test_import_boundary.py`
- `source .venv/bin/activate && pyright`
- `git diff --check`
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests`

预期断言：

- Doc/Web/Fins read tool schemas 不包含 governance fields。
- Doc/Web/Fins read cancellation tests 返回 `ToolCancelledOutcome`，reason 为 `TOOL_CANCELLED_REASON_HOST_CANCELLED`。
- Doc/Web/Fins read cancellation outcome 均携带 `ToolResultMeta`，且 `meta` 不含 Host governance 字段。
- 非取消业务错误仍为 `ToolFailedOutcome`。
- Fins read storage 相关测试继续通过，证明仍走 Fins runtime / storage 边界。
- ToolRuntime accept barrier 集成测试继续通过，证明 native definitions 可被 Host ToolRuntime 执行。
- 删除 adapter 后无生产 / 测试代码 import legacy adapter。
- legacy adapter 测试中 current 行为已迁移到 Slice 0/1/2/3；adapter-only 行为已明确删除。

覆盖率要求：

- 新增 runtime helper 文件需要单文件测试覆盖率 >= 80%。
- 大幅改写的 Doc / Web / Fins read tool 文件应优先以现有 provider tests 覆盖主要 public callable 路径；若覆盖率低于目标，补窄测试而不是保留兼容代码。

## 10. Docs Decision

Plan gate：

- 只新增本 plan artifact。
- 不编辑 README。

Implementation gate 后续：

- `dayu/fins/` 修改触发 `dayu/fins/README.md` 检查。该 README 的约束要求只描述 Fins 包内部稳定边界，不写测试清单或 work unit 流水账；若 Fins read provider 从 legacy 改为 native 且现有描述仍只说 current `ToolDefinition`，可不改。
- `tests/` 修改触发 `tests/README.md` 检查。现有 README 明确提到 legacy adapter 测试和业务工具 provider 适配测试，最终删除 adapter 后应更新。
- 若新增 `dayu/runtime` helper 只是内部实现，不改变总览边界，`dayu/README.md` 可不改；若 README 当前关于 `dayu.tools` 输出 current `ToolDefinition` 的描述需要从“迁移”更新为“原生”，再按其 Agent 更新约束最小修改。
- 不需要更新 `docs/engine/design.md` 或 `docs/host/design.md`，因为本 WU 不改变 Host / Engine 架构契约。

## 11. Risks / Open Questions / Residual Risk

Blocking open questions: none.

风险分类：

- High: 迁移 Doc/Web/Fins read 一次性实施容易漏掉参数默认值、路径投影、truncate spec 或 cancellation checkpoint。缓解：按四个 slice 推进，每个 provider 单独验收。
- High: 将 legacy `tool_cancelled` catch 复制到 provider-local wrapper 会保留 bug。缓解：测试必须断言 `ToolCancelledOutcome`，并全局 rg 禁止 `ToolBusinessError(code="tool_cancelled")`。
- Medium: 抽 runtime helper 过宽可能演化成新的工具框架。缓解：helper 只做参数校验和 outcome 构造，不做 provider discovery、dispatch、权限、IO 或 policy。
- Medium: 删除 adapter 可能暴露额外 production imports。缓解：Slice 4 前后运行 `rg "_legacy_adapter" dayu tests`，发现额外生产 import 则纳入 R3。
- Medium: Fins read runtime 错误类型迁移可能误伤 storage 边界。缓解：Fins tests 继续通过仓储 public API 构造 fixture，并保留 read runtime / storage assertions。
- Low: Tool schema digest 可能因 declaration 构造顺序或 dict ordering 发生变化。缓解：保持 schema 常量内容与顺序；如 digest 测试失败，先 diff schema JSON，只有完全等价时更新 expected digest。

Residual risk closeout expectation：

- R3 完成后，`WU-TOOLS-01-F01-02-R3` 可从 active residual risk 标为 closed 或在 Issue #130 closeout 中关闭。
- F08 命名清理仍保持 deferred owner，不因 R3 自动实施。
- CI / smoke pipeline owner 仍是 Issues #121 / #122，不因 R3 closeout 改变。
- Web live smoke 若未运行，R3 closeout 必须保留有 owner 的 residual tracking，至少列明未验证网络 / Playwright 场景、未运行原因、下一步 owner；不得以 deterministic pytest 通过替代真实网络 / browser fallback 的覆盖声明。

## 12. Completion Report Format

Implementation agent 完成 R3 时，最终报告必须包含：

- 改了什么：按 Slice 0 到 Slice 4 列出生产代码、测试、README / docs 变化。
- schema 结论：明确说明 Doc / Web / Fins read tool 名称和 LLM-facing 参数是否改变；预期为未改变。
- cancellation 结论：明确说明 Host token cancellation 现在返回 `ToolCancelledOutcome(host_cancelled)`，并列出覆盖测试。
- adapter 删除证据：给出 `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests` 结果摘要。
- 验证：列出实际运行的 pytest、pyright、`git diff --check`。
- 风险 / 未覆盖项：列出未运行的长耗时 smoke 或外部网络 smoke，并说明原因。
- 下一 gate 建议：R3 implementation review；review 通过后才进入 closeout / 后续 F08 goal confirmation。

## 13. Why This Avoids Over-design

- 不新增工具注册框架，只复用现有 `ToolsDiscoveryProviderOutput`、`ToolDefinition`、`ToolCallable` 和 outcome 契约。
- 不改 Host / Engine state machine，不引入新 public contract。
- runtime helper 的边界很窄，只解决三类工具都会重复需要的 current callable 参数校验和 outcome 构造。
- 每个 provider 仍是显式 provider callable，不扫描包、不动态发现函数、不引入 service locator。
- 不保留旧导入兼容层，避免双路径长期维护。
- slice 按可验证闭环拆分：helper、Doc、Web、Fins read、adapter deletion；每个 slice 都有独立测试和 stop condition。
