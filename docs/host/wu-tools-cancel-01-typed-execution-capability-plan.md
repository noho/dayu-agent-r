# WU-TOOLS-CANCEL-01 Typed Execution Capability Plan

## Goal

为 WU-TOOLS-CANCEL-01 增加最小 typed execution capability 声明，使生产 `ToolRuntime` 能从 `ToolDefinition` 同源声明选择 `async_direct`、`thread_backed` 或 `process_backed` 执行形态，并恢复 S2 对 Doc、Fins read、Web sync 生产路径的迁移。

目标成立。直接根因不是缺少 Host cancel API、Engine 状态、durable schema 或第二套 timeout，而是当前业务工具声明无法表达“这个工具必须用哪种可中断执行边界”。S1 已实现 Host 内部 capsule，但生产 dispatch 仍只能拿到普通 `ToolDefinition.callable`，没有 typed selector；继续推进会被迫使用 Host 工具名分支，或让业务工具 import Host internals，这两者都违反当前设计真源。

成功信号：

- `ToolDefinition` 携带层间公共、强类型 execution capability；未声明时默认 `async_direct`，保持纯 async 工具现状。
- Host `ToolRuntime` factory 从 effective `ToolDefinition` 读取 capability，选择对应 capsule；Host 不按工具名特判。
- Engine 仍只消费 `ToolSchema`、`ToolExecutor`、`BatchToolExecutionContext`，不读取 capability。
- Doc、Fins read、Web sync 生产路径迁移到 `process_backed` 或 request-abort-capable `async_direct`；不能满足时 fail closed，不允许标记 #87 closeout。
- 旧结果不得污染已取消 Run，且不延长 WU-LIFE-04 固定的单次工具执行 deadline。

## Non-goals

- 不修改 Host public cancel command、Run / Attempt 状态机、EventLog event type 或 durable schema。
- 不把 execution capability 投影给 LLM，不修改 LLM-facing tool schema 文案，除非业务工具自身参数说明已经不自足。
- 不让 Engine 消费 execution capability，也不把 capability 塞进 `BatchToolExecutionContext`。
- 不新增 `extra payload`、raw dict、profile lookup、兼容 wrapper / facade 或旧接口兼容读取。
- 不把 provider-specific kill API 写入 Host core。
- 不处理 Fins download / preprocess / upload WAITING external job lifecycle；该路径已由 WU-WAIT-03 / activation hook 管理。本 WU 只处理非 WAITING blocking tool execution。

## 当前 Root Cause 直接证据

- `dayu/contracts/tool_declaration.py:86-108`：`ToolDefinition` 当前字段只有 `name`、`schema`、`callable`、`truncate`、`display`、`tags`，没有 execution capability。
- `dayu/runtime/tools_discovery.py:229-270`：`ToolsDiscovery` 聚合 provider 输出的 `ToolDefinition` 并构造 `ToolBundle`，不会生成 Host-specific runtime selector。
- `dayu/host/dispatch.py:3316-3349`：生产 dispatch 用 `tooling_options.business_tool_bundle` 构造 `ToolRuntimeBuildRequest`，但没有传入按工具声明派生的 execution selector。
- `dayu/host/tool_runtime.py:2568-2608`：`ToolRuntimeBuildRequest.execution_capsule_factory` 是 Host 内部 factory；默认值是 `DefaultToolExecutionCapsuleFactory`。
- `dayu/host/tool_runtime.py:1488-1509`：默认 factory 恒定创建 `AsyncDirectToolExecutionCapsule`，不读取 `ToolDefinition`。
- `dayu/host/tool_runtime.py:356-361`、`1388-1721`：S1 已有 Host 内部 `ToolExecutionMode` 与 async / thread / process capsule，说明缺口在声明和 wiring，不在 interrupt primitive。
- `dayu/tools/doc_tools.py:702-733`：Doc 生产工具在 provider lock 内用 `asyncio.to_thread(business_call, token)` 执行同步业务。
- `dayu/fins/tools/fins_tools.py:746-778`：Fins read 生产工具同样在 provider lock 内用 `asyncio.to_thread(...)` 执行同步 read runtime。
- `dayu/tools/web/web_tools.py:1161-1182`、`1259-1276`：Web search / fetch 主路径仍用 `asyncio.to_thread(...)` 执行同步 requests 业务。
- `dayu/tools/web/web_http_session.py:235-258`：Web requests session 是进程内 session，timeout budget 已能限制请求预算，但不能中断已进入 OS thread 的同步请求。
- `dayu/tools/web/web_playwright_backend.py:480-525`、`1088-1111`：Playwright 已有局部子进程 terminate / timeout / fail-closed 证据，可作为 process-backed 迁移参考，但还不是 ToolRuntime typed declaration。
- `docs/reviews/wu-tools-cancel-01-slice2-code-review-controller-adjudication.md` F01 已裁决：缺少 typed execution capability 阻塞 S2 完成和 #87 closeout。

## 方案选择

选择：在 `dayu.contracts` 增加最小 execution capability 契约，并把它作为 `ToolDefinition` 字段。

理由：

- `ToolDefinition` / `ToolBundle` 已是 Host、runtime discovery、业务 provider 共同理解的公共契约。
- `ToolsDiscovery` 只能依赖标准库与 `dayu.contracts`；它聚合 capability 时不需要理解 Host capsule。
- Host `ToolRuntime` 是 capability 的主要消费者，但 capability 不是 Host durable truth，也不是 Host-only internals；业务工具 provider 必须能声明它。
- `dayu.runtime` 可以继续承载 `interruptible_process` 这类层中立执行 helper；但 execution declaration 若放在 `dayu.runtime`，`ToolDefinition` 会被迫 import runtime，或在 contracts / runtime 间复制 enum，都会制造公共语义漂移。

`dayu.runtime` 取舍：

- 可放：`InterruptibleProcessHandle`、spawn / terminate / kill / queue cleanup 这类层中立 runtime primitive。
- 不应放：`ToolExecutionCapability` / `ToolExecutionMode` 声明真源。它们是 `ToolDefinition` 的一部分，必须跟工具公共契约同源。
- `dayu.runtime.interruptible_process` 必须保持当前层中立 `JsonValue` 契约；不得扩展为 `JsonValue | ToolExecutionOutcome`。工具语义只允许在 Host capsule 层解释：process target 返回 JSON 信封，Host capsule 将 `completed` / `failed` 信封映射为对应 tool outcome，并由父进程独占映射 cancel / timeout。

## 被拒绝方案

- Host tool-name branch：拒绝。它把业务工具名写入 Host core，违反 Host 不理解业务工具包和不写 provider-specific 分支的边界。
- 业务工具 import `dayu.host.tool_runtime` capsule：拒绝。业务工具会依赖 Host internals，破坏 `UI -> Service -> Host -> Engine` 分层。
- 把 mode 放进 `BatchToolExecutionContext`：拒绝。context 是批式执行时 Host/Engine handshake 输入，不是工具声明；Engine 不应消费或传递 per-tool capability。
- 放入 tool schema / LLM-facing description：拒绝。execution mode 是运行期治理语义，不是模型决策事实。
- `extra payload` / raw dict / string metadata：拒绝。显式参数必须有 typed field，不能用无结构 payload 逃避类型检查。
- 继续只强化 thread cancellation：拒绝。`thread_backed` 不承诺停止 OS thread，不能满足 #87 closeout 的非协作 blocking interrupt。
- 为 Doc/Fins/Web 各自做私有 process helper 但不接 ToolRuntime capability：拒绝。会形成业务局部修复，ToolRuntime 生产 dispatch 仍不知道如何统一治理。

## Contract / API Shape 草案

新增文件：`dayu/contracts/tool_execution.py`。

草案：

```python
@dataclass(frozen=True, slots=True)
class ProcessBackedToolContext:
    """子进程工具目标构造所需的可序列化上下文。

    本类型由 Host 从 BatchToolExecutionContext 投影而来，只包含
    multiprocessing spawn 可序列化的标量字段。

    :param run_id: Agent run 唯一 id。
    :param session_id: 会话 id。
    :param iteration_id: 当前 LLM 迭代 id。
    :param timeout_seconds: 当前工具批次剩余超时预算；None 表示未提供。
    :param correlation_id: 批级中性关联标识；None 表示调用方未提供。
    """

    run_id: str
    session_id: str
    iteration_id: str
    timeout_seconds: float | None
    correlation_id: str | None


class ToolExecutionMode(StrEnum):
    """工具运行时执行形态。"""

    ASYNC_DIRECT = "async_direct"
    THREAD_BACKED = "thread_backed"
    PROCESS_BACKED = "process_backed"


class ProcessBackedToolTarget(Protocol):
    """可在独立子进程内执行的工具目标。"""

    def __call__(self) -> JsonValue:
        """执行子进程工具目标并返回 JSON 信封。

        :returns: JSON 信封，合法形态仅为
            {"status": "completed", "value": JsonValue} 或
            {"status": "failed", "error_type": str, "message": str}。
            子进程不得返回 awaiting / cancelled 语义；等待、取消和超时只能由
            Host / Engine 治理层产生。
        :raises Exception: 未捕获异常由 process capsule 转为结构化工具失败。
        """


class ProcessBackedToolTargetFactory(Protocol):
    """根据工具调用构造 process-backed 目标。"""

    def build_process_target(
        self,
        call: ToolCallRequest,
        context: ProcessBackedToolContext,
    ) -> ProcessBackedToolTarget:
        """构造可序列化子进程目标。

        :param call: 单次工具调用请求。
        :param context: 已从批式执行上下文投影出的可序列化上下文；不包含
            cancellation_token、lock、runtime、repository、session 或 Host internals。
        :returns: 可被 multiprocessing spawn 序列化的目标。
        :raises Exception: 目标无法构造时抛出，ToolRuntime 转为工具失败。
        """


@dataclass(frozen=True, slots=True)
class AsyncDirectToolExecutionCapability:
    """直接 async 执行能力声明。

    :param request_abort_capable: 取消 async task 时，工具实现是否能关闭底层
        request / stream / client 等资源。
    """

    request_abort_capable: bool = False


@dataclass(frozen=True, slots=True)
class ThreadBackedToolExecutionCapability:
    """线程托管执行能力声明。

    该模式只表示可取消 wrapper awaitable，不承诺停止 OS thread。

    :param production_safe_non_cooperative_cancel: 永远为 False 的显式
        guard 字段；用于让声明和测试能证明 thread_backed 不能作为
        非协作 blocking 生产 closeout 证据。
    """

    production_safe_non_cooperative_cancel: Literal[False] = False


@dataclass(frozen=True, slots=True)
class ProcessBackedToolExecutionCapability:
    """子进程托管执行能力声明。

    :param target_factory: 根据工具调用构造可序列化 process target 的 factory。
    """

    target_factory: ProcessBackedToolTargetFactory


ToolExecutionCapability = (
    AsyncDirectToolExecutionCapability
    | ThreadBackedToolExecutionCapability
    | ProcessBackedToolExecutionCapability
)
```

`ToolDefinition` 变更：

- 增加字段 `execution: ToolExecutionCapability`。
- `tool(...)` decorator 增加显式参数 `execution: ToolExecutionCapability | None = None`。
- 直接构造 `ToolDefinition` 的业务工具 helper 必须显式传入 `execution`；若参数为 `None`，由 helper / decorator 默认成 `AsyncDirectToolExecutionCapability(request_abort_capable=False)`。
- `ToolBundle` digest 需要包含稳定 capability mode 和 `request_abort_capable`；不得 hash callable 或 process target factory 对象。对于 process-backed，digest 只记录 mode 与业务工具声明内容，不用 callable identity 作为稳定事实。
- `_tool_definition_json_value` 中 `execution` 的稳定 JSON shape 固定为：
  - `async_direct`: `{"mode": "async_direct", "request_abort_capable": true | false}`
  - `thread_backed`: `{"mode": "thread_backed", "production_safe_non_cooperative_cancel": false}`
  - `process_backed`: `{"mode": "process_backed"}`
- S2A1 implementation 必须用 `rg -n "ToolDefinition\\(" dayu tests` 扫描直接构造站点并逐个裁决。生产站点至少包含 `dayu/contracts/tool_declaration.py` decorator、`dayu/tools/doc_tools.py`、`dayu/fins/tools/download_tools.py`、`dayu/fins/tools/upload_tools.py`、`dayu/fins/tools/preprocess_tools.py`、`dayu/host/tool_runtime.py` framework `fetch_more`；测试 helper 也必须随 contract 迁移，不能靠兼容 wrapper 保旧签名。

Host ToolRuntime 变更草案：

- 删除或收敛 Host 内部重复的 `ToolExecutionMode` 真源，改用 `dayu.contracts.ToolExecutionMode` 或从 capability type 映射 mode。
- 新增 `DeclaredToolExecutionCapsuleFactory`，持有 `EffectiveToolBundle`，根据 `call.name` 找到 `ToolDefinition.execution` 并创建 capsule。
- `async_direct`：创建当前 `AsyncDirectToolExecutionCapsule`。
- `thread_backed`：只允许用于明确 cooperative / non-production 或测试路径；生产关键路径的 review 必须拒绝它作为 #87 closeout 证据，并断言 `production_safe_non_cooperative_cancel is False`。
- `process_backed`：先把 `BatchToolExecutionContext` 投影为 `ProcessBackedToolContext`，再调用 `target_factory.build_process_target(call, process_context)`，创建 `ProcessBackedToolExecutionCapsule`。
- `ProcessBackedToolExecutionCapsule` 继续使用 S1 `InterruptibleProcessTarget.__call__() -> JsonValue`。Host capsule 解析 process target JSON 信封：`completed` 映射为 `ToolCompletedOutcome`，`failed` 映射为 `ToolFailedOutcome`，未知或非 JSON 信封 fail closed 为 `ToolFailedOutcome`。父进程 cancel / timeout 后 terminate / kill process，并独占返回 Host-governed cancelled / timeout outcome；子进程不得自报 `host_cancelled`、`timeout`、`awaiting` 或 approval 语义。
- `ToolRuntimeBuildRequest.execution_capsule_factory` 保留测试注入用途时，必须明确优先级：生产默认使用 declaration-backed factory；测试可注入专用 factory。不得在 production dispatch 中按工具名构造 factory。

中文 docstring 要求：

- 所有新增模块、类、Protocol、dataclass、函数、方法必须有完整中文 docstring，至少包含参数、返回值、异常。
- 所有新增字段 docstring 必须说明该字段是否进入 LLM-facing schema、是否进入 stable digest、是否可作为业务事实。
- 所有 process target / factory docstring 必须说明“目标必须可序列化，不得捕获 repository/runtime/session 对象”。

## Engine 边界

Engine 应保持不消费该 capability。

原因：

- `docs/engine/design.md` 明确 Engine 只执行单次 run、只通过 `ToolExecutor.execute(BatchToolExecutionRequest)` 与工具环境 handshake。
- `tool_schemas` 是 Engine / Runner 可见工具快照；`ToolDefinition` / `ToolBundle` 不进入 Engine。
- capability 只决定 Host-owned ToolRuntime 如何执行工具 callable 或 process target，不改变 Runner、Agent loop、tool call schema、batch context、timeout 真源或 cancellation token 契约。
- 若 Engine 也消费 capability，会把 ToolRuntime execution ownership 泄漏到 Engine，增加双真源。

## 精确修改范围

Contract + factory wiring slice：

- `dayu/contracts/tool_execution.py`
- `dayu/contracts/tool_declaration.py`
- `dayu/contracts/__init__.py`
- `dayu/runtime/tools_discovery.py`（仅更新 digest / validation，禁止新增业务 import）
- `dayu/host/tool_runtime.py`
- `dayu/host/dispatch.py`（仅保证 production 使用 declaration-backed factory）
- `dayu/fins/tools/download_tools.py`（直接构造 `ToolDefinition`，显式声明默认 async_direct 或等待型工具当前语义）
- `dayu/fins/tools/upload_tools.py`（直接构造 `ToolDefinition`，显式声明默认 async_direct 或等待型工具当前语义）
- `dayu/fins/tools/preprocess_tools.py`（直接构造 `ToolDefinition`，显式声明默认 async_direct 或等待型工具当前语义）
- `tests/contracts/` 或现有 contracts 测试文件
- `tests/runtime/test_tools_discovery.py`
- `tests/runtime/test_tools_discovery_digest.py`
- `tests/host/test_toolruntime_executor.py`
- 其它 `rg -n "ToolDefinition\\(" dayu tests` 命中的构造站点，按 contract 迁移；若某站点不应迁移，必须在 implementation artifact 中给出原因
- `docs/host/design.md`、`docs/engine/design.md`、`dayu/host/README.md`、`tests/README.md` 按 README 触发规则检查并按需更新

Doc slice：

- `dayu/tools/doc_tools.py`
- `dayu/tools/doc_provider.py`（仅当 provider config 需要把 serializable config 显式传入 process target factory）
- `tests/tools/test_doc_tools_provider.py`
- 必要时新增 focused Doc process target 测试文件

Fins slice：

- `dayu/fins/tools/fins_tools.py`
- `dayu/fins/tools/provider.py`
- `dayu/fins/tools/read_runtime.py` 或更窄 helper（仅当 process entrypoint 需要提取公共只读路由）
- `tests/fins/test_fins_ingestion_tools.py` 与现有 Fins read focused tests
- `dayu/fins/README.md` 按约束检查

Web slice：

- `dayu/tools/web/web_tools.py`
- `dayu/tools/web/web_http_session.py`
- `dayu/tools/web/web_playwright_backend.py`
- `dayu/tools/web/provider.py`
- `tests/tools/web/test_web_tools_provider.py`

Aggregate validation slice：

- `tests/host/test_toolruntime_executor.py`
- `tests/tools/test_doc_tools_provider.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/tools/web/test_web_tools_provider.py`
- 必要的 smoke / README / design sync

不允许修改：

- Host cancel public API。
- Engine public request / event / runner contract。
- durable schema / migration。
- 总控文档 `docs/host/issues-implementation-control.md`，除非 phaseflow controller 在后续 gate 另行处理。

## Process-backed Entrypoint 形状

通用规则：

- process target 必须是模块级 class 或模块级函数包装的 frozen dataclass，能被 `multiprocessing` spawn 序列化。
- 父进程只传 tool call arguments、timeout scalar、workspace / allowed path / config 的可序列化 locator；不得传 repository、runtime、requests session、browser、processor、lock、Host token 或 Host internals。
- 子进程返回 JSON 信封；只允许表达 completed 或 failed。`awaiting`、`cancelled`、`host_cancelled`、approval、timeout 均不由子进程返回。
- 父进程 cancel / timeout 后 terminate / kill process，并返回 Host governed cancelled / timeout outcome；late child result 不得进入 accept barrier。timeout 归属完全在父进程 capsule，子进程内部不得再引入第二套 timeout outcome。
- process-backed 路径默认绕过父进程 provider lock；子进程内重新创建 processor / runtime / session，依赖进程隔离而不是父进程共享 lock。若某工具仍必须依赖父进程 provider lock 保护共享状态，说明它不满足当前 process-backed 入口条件，必须停止该 slice 并回到设计裁决。

Doc：

- 输入：`DocProcessToolRequest(tool_name, arguments, allowed_roots: tuple[str, ...], limits: DocToolLimits serializable fields, timeout_seconds: float | None)`。
- 子进程：重新解析 `Path`，重新执行 path containment，按 tool kind 调用现有同步 business helper；processor 在子进程内由 `create_doc_file_processor(path)` 创建。
- 输出：Doc completed / failed JSON 信封。process kill 后由 parent 返回 Host cancel / timeout outcome。
- 测试边界：验证 process target 不捕获 `DocumentProcessor` / lock；取消后不会返回 accepted result；路径白名单仍生效；输出与 async_direct baseline 等价。

Fins read：

- 输入：`FinsReadProcessToolRequest(workspace_root: str, tool_name, arguments, limits serializable fields, timeout_seconds: float | None)`。
- 子进程：调用 `DefaultFinsRuntime.create(workspace_root=Path(...))`，通过 `dayu.fins.storage` 下仓储协议重新打开只读 repository，再构造 `FinsReadRuntime`。
- S2C 开始前必须先做 focused pre-check：在 spawned child 中用真实临时 workspace 调用 `DefaultFinsRuntime.create(workspace_root)` 并执行一条只读查询，验证不依赖父进程 singleton、不可序列化 repository 或写入型缓存。
- 输出：Fins read completed / failed JSON 信封。
- 仓储边界：禁止把 repository / runtime 实例跨进程传递；禁止绕过 `dayu.fins.storage` 直接读财报文件。
- 测试边界：验证 workspace root 必须绝对路径；process target 内通过 Fins runtime / storage 路由；取消后无 accepted late result；九个 read tools 至少覆盖一条 fast path、一条 processor path、一条 XBRL / table path。

Web sync：

- 输入：`WebProcessToolRequest(tool_name, arguments, WebToolsConfig serializable fields, timeout_seconds: float | None)`。
- 子进程：创建短生命周期 requests session 或使用子进程内 session；不传父进程全局 `requests.Session`。Playwright fallback 在子进程内初始化 browser runtime，或沿用现有 worker process fail-closed 逻辑。
- 输出：Web completed / failed JSON 信封。
- request-abort-capable async_direct 替代路径：如果某 Web path 改为 async HTTP adapter，必须测试取消时 response / client / stream 被关闭；可接受验证至少包括 fake / instrumented async client 的 `aclose()` 或 response close 被调用、stream 被退出、无 unclosed-resource warning，并证明 cancelled task 不再持有连接池资源。
- 测试边界：验证同步 requests 主路径不再只靠 `asyncio.to_thread`；timeout budget 仍传入 request timeout；不可序列化 Playwright worker fail closed；取消后不会有 late accepted result。

## S2 Resume Slices

本轮建议 6 个 implementation slices。虽然超过小型 cleanup 默认上限 3，但这里不是按模块机械拆分：contract declaration、Host wiring、Doc、Fins、Web、aggregate validation 的失败 / 回滚风险、业务依赖和测试矩阵独立。尤其 Fins 有强 storage 边界，Web 有 requests / Playwright 两套执行形态，合并会让一个 implementation / review 上下文过大。

### S2A1: contract / declaration / digest

- 增加 `dayu.contracts` capability shape。
- 扩展 `ToolDefinition` / decorator / direct construction helper。
- 更新 ToolsDiscovery digest / tests。
- 补全所有 `ToolDefinition(` 直接构造站点，至少包括 Doc helper、Fins download / upload / preprocess helpers、Host framework `fetch_more` 和 tests helper。
- 增加 JSON 信封 shape、`ProcessBackedToolContext`、thread_backed guard、digest shape 和 pickle round-trip 测试。
- Stop condition：如果 contract shape、digest shape 或 pickle round-trip 失败，停止，不进入 Host wiring。

### S2A2: Host factory wiring

- 增加 declaration-backed capsule factory，生产默认从 `ToolDefinition.execution` 选择 capsule。
- 保持 Engine 不变，并增加 import-boundary / projection 测试证明 `ToolSchema` 不含 capability。
- 验证 `BatchToolExecutionContext -> ProcessBackedToolContext` 投影不携带 `cancellation_token`，且 process target 只以 `JsonValue` 信封进入 S1 `InterruptibleProcessTarget`。
- Stop condition：如果 Host wiring 需要工具名分支、需要修改 Engine contract，或需要修改 `dayu.runtime.interruptible_process` 返回类型，停止。

### S2B: Doc process-backed

- 为五个 Doc tools 增加 process-backed target factory。
- 消除生产关键路径的裸 `asyncio.to_thread(...)` closeout 依赖。
- 保持现有参数校验、路径白名单、truncate spec、结果 shape。

### S2C: Fins read process-backed

- 为九个 Fins read tools 增加 process-backed target factory。
- 子进程内通过 `DefaultFinsRuntime` 和 `dayu.fins.storage` 重新打开只读仓储。
- 严禁跨进程序列化 Fins runtime / repository / processor cache。

### S2D: Web sync process-backed or abort-capable async_direct

- Web search / fetch 同步 requests 路径迁移到 process-backed，或改成有关闭验证的 async direct adapter。
- Playwright 路径保持 process-backed / fail-closed 语义，不回落到不可抢占同进程路径。
- timeout budget 继续传入 HTTP / browser 阶段。

### S2E: aggregate validation

- 跑通 contract、Host ToolRuntime、Doc、Fins、Web focused tests 与 pyright。
- 增加 aggregate interrupt test：同一 Run cancel / timeout 后 process-backed late result 不进入 accept barrier。
- 汇总 provider lock、thread_backed guard、Fins 子进程可行性、digest JSON shape、Web async_direct close、timeout 归属、pickle round-trip 的验证结果。
- 按 README 触发规则补齐设计 / README 同步。
- 更新 S2 implementation artifact，逐工具族记录 mode、验证、未覆盖项和 stop condition 是否关闭。

## Tests / Pyright / README 验证矩阵

| Slice | 测试 | Pyright | README / design |
|---|---|---|---|
| S2A1 | contracts tool execution tests；`tests/runtime/test_tools_discovery.py`；`tests/runtime/test_tools_discovery_digest.py`；直接 `ToolDefinition` 构造站点迁移测试；process target/context/envelope pickle round-trip | 必跑 `pyright` | 检查 `docs/host/design.md`、`docs/engine/design.md`、`tests/README.md` |
| S2A2 | `tests/host/test_toolruntime_executor.py`；Host declaration-backed factory wiring；`BatchToolExecutionContext -> ProcessBackedToolContext` 投影测试；Engine projection 不含 capability | 必跑 `pyright` | 检查 `dayu/host/README.md`、`tests/README.md` |
| S2B | `pytest tests/tools/test_doc_tools_provider.py -q`；Doc process target cancel / timeout focused tests | 必跑 `pyright` | 通常不需根 README；如 Doc 工具开发边界变化，检查相关 README |
| S2C | `pytest tests/fins/test_fins_ingestion_tools.py -q`；Fins read focused tests；spawned-child `DefaultFinsRuntime.create` 可行性 pre-check | 必跑 `pyright` | 检查 `dayu/fins/README.md` 与 `tests/README.md` |
| S2D | `pytest tests/tools/web/test_web_tools_provider.py -q`；若选择 async_direct，必须验证 async client / response / stream close | 必跑 `pyright` | 如 Web tool cancellation 行为成为开发者稳定边界，检查相关 README |
| S2E | 合并运行 Doc / Fins / Web / Host focused tests；必要 smoke；`git diff --check` | 必跑 `pyright` 且 0 errors | 按触发规则确认所有 README / design 已同步或明确无需更新 |

推荐 aggregate 命令：

```bash
source .venv/bin/activate
pytest tests/host/test_toolruntime_executor.py -q
pytest tests/runtime/test_tools_discovery.py -q
pytest tests/runtime/test_tools_discovery_digest.py -q
pytest tests/tools/test_doc_tools_provider.py -q
pytest tests/fins/test_fins_ingestion_tools.py -q
pytest tests/tools/web/test_web_tools_provider.py -q
pyright
git diff --check
```

## Stop Conditions

- `ToolDefinition` capability 无法以强类型字段表达，或需要 raw dict / extra payload 承载显式参数：停止，返回 design gate。
- `dayu.runtime` 需要 import Host / Engine / Service / UI / Fins 才能完成 capability：停止，重新划分 contracts/runtime 边界。
- Host 只能靠工具名分支选择 process-backed：停止。
- 业务工具必须 import Host internals 才能声明或执行 process-backed：停止。
- `dayu.runtime.interruptible_process` 必须改成返回 `ToolExecutionOutcome` 才能完成 S2A1 / S2A2：停止，回到 design gate；当前 plan 已选择 Host capsule JSON 信封映射方案。
- `ProcessBackedToolTarget`、`ProcessBackedToolContext` 或 JSON 信封不能通过 multiprocessing pickle round-trip：停止。
- 子进程 target 试图返回 awaiting / cancelled / timeout / host_cancelled 语义：停止，改为 Host capsule 父进程治理。
- 生产关键路径把 `thread_backed` 当作非协作 blocking cancel closeout 证据，或未显式保留 `production_safe_non_cooperative_cancel is False` guard：停止。
- process-backed 迁移必须持有父进程 provider lock 保护共享 runtime / repository / session 状态：停止，改为子进程内重建资源或回到设计裁决。
- Doc / Fins read / Web sync 关键生产路径不能 process-backed，且不能提供 request-abort-capable async_direct：停止，不得标记 S2 完成或 #87 closeout。
- Fins read 子进程无法通过 `DefaultFinsRuntime.create(workspace_root)` spawned-child pre-check，或需要绕过 `dayu.fins.storage` / 跨进程序列化 repository/runtime：停止。
- Web 若选择 request-abort-capable `async_direct`，但无法证明 response / client / stream 关闭且无未关闭资源：停止，改用 process-backed 或回到设计裁决。
- Process target 无法序列化且没有 fail-closed 路径：停止。
- Engine 需要新增 capability 字段才能完成本 WU：停止，重新做 Engine / Host contract design。
- 新增 pyright 错误、测试失败、README 触发项未裁决：停止，不进入下一 gate。

## Residual Risks

- Process-backed 会增加子进程启动成本；当前 #87 目标优先级是取消可抢占性与 late-result 隔离，性能优化可后续在不改变 contract 的前提下评估 worker pool。
- `ToolDefinition` digest 不 hash target factory identity，意味着 digest 解释的是声明语义而不是 callable bytecode；这与现有 callable 不入 digest 的原则一致，但需要在 diagnostics 文案中明确。
- Process target 返回 JSON 信封而不是完整 `ToolExecutionOutcome`；剩余风险是业务工具现有 completed / failed shape 的映射可能遗漏字段。S2A2 必须用 Host capsule focused tests 覆盖 completed / failed / malformed envelope 三类映射。
- Fins storage 多进程只读可行性尚待实现验证；S2C 前置 pre-check 失败时不得把 Fins read 标记为 process-backed 完成。
- Web async_direct 改造若被选中，必须证明 response / client / stream close；否则同步主路径应优先 process-backed。
- Thread-backed 能力保留会被误用为生产 closeout 证据；contract guard、plan review 和 code review 必须把“thread_backed 不满足非协作 blocking cancel”列为强检查项。
- process-backed 绕过父进程 provider lock 的取舍依赖子进程内资源重建；若发现某工具真实共享状态无法在子进程内重建，该工具不能进入本 WU closeout。

## Verdict

Verdict：`READY_FOR_RE_REVIEW`。

已完成 plan fix，等待 re-review。原因是本计划修改 `dayu.contracts.ToolDefinition` 公共契约，并要求 Host production ToolRuntime 从该契约选择 execution capsule；这属于 design/contract gate，不应直接进入 implementation。
