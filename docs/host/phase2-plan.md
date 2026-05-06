# Host P2 Handoff Plan：ToolRuntime truncate / fetch_more

## 目标

P2 目标是在 P1.5 `RunEventStore` 事实层之上，迁移 OLD `TruncationManager` 的工具结果截断、
cursor lifecycle、token、TTL、single-use、limit clamp 与 page structure 等底层可靠语义，并把它收束到
Host / ToolRuntime 边界。

本阶段必须产出：

- Host 内部最小 `ToolRuntime`：只覆盖工具执行代理、工具结果截断、`fetch_more`、cursor 生命周期与治理事实。
- Run 级 public `fetch_more_tool_result(...)` 入口：供持有 Host 受控 `ToolFetchMoreHandle` 的调用方或测试
  harness 按 run / tool call / cursor 补读截断结果。
- 非 EventLog 的受控 handle 读取契约：调用方只能通过 Host public 契约按 session / run / 原始
  tool_call / cursor fingerprint 换取 `ToolFetchMoreHandle`；`scope_token` 不进入 RunEvent 或 Engine
  projection。
- Engine 可消费的 `ToolExecutor` adapter：Engine 仍只调用 `ToolExecutor.execute`，不感知 ToolRuntime、cursor store
  或权限实现。
- 截断与补读事实进入 P1.5 `RunEventStore`：`result truncated`、`cursor issued`、
  `fetch_more requested / completed / failed`、`cursor expired / denied` 均为 canonical RunEvent。
- 最小 cursor 契约：run-scoped、single-use、TTL、scope token 校验、可选 `limit` 不超过原始截断上限。
- OLD / NEW 语义差异测试：尤其覆盖 OLD 中“旧 cursor 成功续读后失效、新 cursor 继续下一页”的 single-use
  行为，以及 NEW 当前只继承底层 cursor 可靠语义、不恢复 OLD LLM-facing `fetch_more` schema /
  `fetch_more_args` projection 的边界。

## 非目标

P2 不实现以下能力：

- 完整 ToolRegistry：工具发现、注册中心、schema 版本管理、display info、重复调用治理、middleware 链。
- 业务工具迁移：doc / web / fins 工具不在本阶段迁入；财报文档访问仍必须由业务工具通过
  `dayu.fins.storage` 保证，不把财报语义写进 Host。
- 完整权限系统：不实现用户 / workspace / doc ACL，不实现完整 path allowlist；P2 只做 cursor
  自身的 run scope、scope token、TTL 与 single-use 校验。
- P6 observer / projection：不实现 tool trace observer、audit observer、timeline projection 或 checkpoint。
- P7 lifecycle governance：不实现 `client_request_id` 幂等、同 Session active Run 仲裁、完整取消治理。
- 多进程 recovery：不实现持久 cursor store、lease、fencing、stale owner cleanup。
- RemoteProxy / RemoteStub wire protocol。
- 把 `fetch_more` 重新做成 Engine 内置工具或让 Engine 持有 cursor。
- OLD LLM-facing `fetch_more` 闭环：不注册 LLM 可调用 `fetch_more` schema，不向 Engine projection 投影
  `next_action` / `fetch_more_args`。这些体验后移到后续明确设计，不在 P2 半协议回流。

## 前置条件

- P1 PR #16 已合入 `main`。
- P1.5 PR #17 已合入 `main`，最小 `RunEventStore` / EventLog 已落地。
- 当前 `dayu.host` 已提供 `start_run`、`stream_run_events(run_id, after=cursor)`、
  `get_run_result(run_id)`，且 `RunEvent` 已有 canonical / preview 分层。
- 当前 `dayu.contracts.ToolTruncationInfo` 只含 `scope_token`、`scope_hash`、`has_more`、
  `ttl_seconds`；Engine 侧 LLM projection 当前不会泄漏 `truncation`、`scope_token`、`scope_hash`。
- OLD 直接证据：
  - `TruncationManager.apply_truncation` 按工具 schema 的 `ToolTruncateSpec` 截断 text chars、
    text lines、list items、binary bytes。
  - `execute_fetch_more` 校验 cursor、TTL、run scope、scope token，成功续读后旧 cursor 失效；
    若还有剩余内容，返回下一页新 cursor。
  - OLD `project_for_llm` 只投影 LLM 可执行字段 `next_action` 与 `fetch_more_args`。

## 架构边界

P2 后的执行边界：

```text
Engine
  -> ToolExecutor.execute(request)
  -> Host-owned ToolRuntimeToolExecutor
  -> ToolRuntime.execute_tool_call(request)
      -> underlying business ToolExecutor
      -> truncate result and store cursor scope
      -> RunEventStore.append(canonical tool runtime facts)
  -> Engine receives ToolExecutionOutcome
```

补读边界：

```text
UI / Service / test harness
  -> dayu.host.get_tool_fetch_more_handle(request)
      (uses session / run / original tool_call / cursor fingerprint; not EventLog token)
  -> dayu.host.fetch_more_tool_result(request)
  -> ToolRuntime.fetch_more(request)
  -> RunEventStore.append(canonical fetch_more facts)
  -> returns ToolFetchMoreResult
```

边界规则：

- Host public surface 只新增 Run 级 handle 读取 / 补读入口与强类型请求 / 结果；不导出 `ToolRuntime`
  实现、cursor store、内部 executor adapter 或底层 business executor。
- `ToolRuntime` 是 Host 内部 capability，不是 `dayu.runtime` 能力，也不是 Engine 组件。
- Engine 只表达 tool call 语义：工具名、参数、tool_call_id、iteration_id、运行上下文与
  `ToolExecutionOutcome`。
- Host / ToolRuntime 负责截断、补读、cursor 生命周期与治理事实。
- `fetch_more` 在 P2 不作为 LLM 可见工具 schema 暴露给 Engine。原因是当前 Engine projection
  不投影可执行 `fetch_more_args`；P2 先固定 Host public 补读入口和事实层，避免半协议回流 Engine。
  若后续要让 LLM 主动调用 `fetch_more`，必须另行扩展 Engine LLM-facing projection 与 tool schema。
- P2 的真实补读调用方限定为同进程 Host UI / Service adapter 或测试 harness，且必须先通过
  `get_tool_fetch_more_handle(...)` 获取非 EventLog handle。远程客户端、跨进程补读、LLM 主动补读、
  以及从 timeline projection 直接发起补读均后移到 P6 / P7 / P10 / P11 相关设计。

## 文件级改动清单

计划新增：

- `dayu/host/_tool_runtime.py`
  - 定义内部 `ToolRuntime` protocol / `InMemoryToolRuntime`。
  - 定义内部 cursor store、truncate / fetch_more 算法与 `ToolRuntimeToolExecutor` adapter。
  - 所有 public 需要的强类型数据从 `dayu.host.contracts` 导入，不在内部模块临时造弱类型 dict。
- `tests/host/test_phase2_tool_runtime_truncation.py`
  - 验证截断策略、cursor 生成、TTL、scope token、single-use、limit clamp。
- `tests/host/test_phase2_tool_runtime_eventlog.py`
  - 验证截断与补读治理事实先 append 到 `RunEventStore`，再返回给调用方或 Engine。
- `tests/host/test_phase2_tool_runtime_boundary.py`
  - 验证 public boundary、Engine 不导入 Host ToolRuntime、Host 不导出内部实现。
- `utils/smoke_host_tool_runtime.py`
  - 参考既有 Host smoke 风格，提供可人工观察的单进程 smoke。
  - smoke 必须展示：工具执行触发 schema-driven truncate、EventLog 追加截断 / cursor issued facts、
    通过 `get_tool_fetch_more_handle(...)` 取得非 EventLog handle、`fetch_more_tool_result(...)`
    补读、旧 cursor single-use 失效、后续 RunEvent 可补读。
  - smoke 日志不得输出明文 `scope_token`、完整大结果或大块 delta；只输出 cursor fingerprint、
    fact type、has_more、chunk size、event cursor 等观察字段。

计划修改：

- `dayu/host/contracts.py`
  - 增加 `ToolRuntimeEventData` 封闭联合成员所需的数据类，例如
    `ToolResultTruncatedData`、`ToolFetchMoreRequestedData`、`ToolFetchMoreCompletedData`、
    `ToolFetchMoreFailedData`、`ToolCursorExpiredData`、`ToolCursorDeniedData`。
  - 增加 `ToolRuntimeCursor`、`ToolFetchMoreHandleRequest`、`ToolFetchMoreHandle`、
    `ToolFetchMoreHandleResult`、`ToolFetchMoreRequest`、`ToolFetchMoreSucceededResult`、
    `ToolFetchMoreFailedResult` 等 Run 级 public 契约。
  - 增加新的 `RunEventType`，使用中性 Host 运行事实命名，不复用业务工具错误码。
- `dayu/host/_run_harness.py`
  - 为内部 harness 注入 `ToolRuntime`。
  - 默认 `start_run` 使用 `ToolRuntimeToolExecutor` 代持底层 `_NoopToolExecutor` 或测试 fake executor。
  - 增加 public `get_tool_fetch_more_handle(request)` 与 `fetch_more_tool_result(request)` 到默认 harness。
- `dayu/host/__init__.py`
  - 只导出 Run 级 public handle 读取 / 补读入口与请求 / 结果类型。
  - 不导出 `_tool_runtime` 内部类、cursor store 或 adapter。
- `dayu/contracts/tool_result.py`
  - 仅当 P2 需要让 `ToolTruncationInfo` 承载可执行补读最小字段时修改。
  - 若修改，必须仍保持强类型封闭契约，不能加入 `dict[str, Any]` 或开放 payload。
- `dayu/host/README.md`
  - P2 代码落地后更新当前事实：Host 内部 ToolRuntime、Run 级 `fetch_more_tool_result`、未落地完整
    ToolRegistry / observer / 多进程。
- `docs/host/design.md`
  - P2 代码落地后写回 P2 后执行边界：
    `Engine -> ToolExecutor.execute -> Host ToolRuntime adapter -> business executor -> truncate / cursor
    facts -> RunEventStore`，以及 `get_tool_fetch_more_handle -> fetch_more_tool_result -> RunEventStore`
    的补读路径。
  - 明确 scope token 不进入 EventLog / Engine projection，LLM-facing `fetch_more` 后移。
- `tests/README.md`
  - P2 代码落地后补 Host ToolRuntime 测试分层与验证命令。

不计划修改：

- `dayu.engine.*` 生产代码。
- `dayu.runtime.*`。
- `dayu.fins.*`。

## 新增 / 修改契约

### Public Run 级接口

P2 public surface 最小新增：

```python
async def get_tool_fetch_more_handle(
    request: ToolFetchMoreHandleRequest,
) -> ToolFetchMoreHandleResult: ...
```

`ToolFetchMoreHandleRequest` 建议字段：

- `session_id: str`
- `run_id: str`
- `tool_call_id: str`
- `cursor_fingerprint: str`

`tool_call_id` 绑定产生截断 cursor 的原始工具调用，不绑定 `fetch_more` 请求自身。调用方从
canonical RunEvent 只能看到 cursor fingerprint、截断摘要与 has_more，不能看到 cursor 原文或
`scope_token`。Host 使用 request 中的 session / run / 原始 tool_call / cursor fingerprint 查找仍有效的
in-memory cursor record，并返回非 EventLog 的受控 `ToolFetchMoreHandle`。

`ToolFetchMoreHandleResult` 是封闭联合：

- 成功：包含 `run_id`、`session_id`、`tool_call_id`、`handle`、`expires_at`。
- 失败：包含 `run_id`、`session_id`、`tool_call_id`、`error_code`、`message`、`denied`。

`ToolFetchMoreHandle` 建议字段：

- `session_id: str`
- `run_id: str`
- `tool_call_id: str`
- `cursor: ToolRuntimeCursor`
- `scope_token: str`
- `expires_at: float`

`ToolFetchMoreHandle` 不写入 `RunEvent`、preview event、Engine message、timeline projection 或日志；它只能在
Host public 契约返回值内短期存在。P2 不提供从 EventLog 反推出 `scope_token` 的路径。

```python
async def fetch_more_tool_result(
    request: ToolFetchMoreRequest,
) -> ToolFetchMoreResult: ...
```

`ToolFetchMoreRequest` 建议字段：

- `session_id: str`
- `run_id: str`
- `tool_call_id: str`
- `cursor: ToolRuntimeCursor`
- `scope_token: str`
- `limit: int | None`

`ToolFetchMoreRequest` 必须由 `ToolFetchMoreHandle` 构造，不能要求调用方从 RunEvent 或 Engine projection
读取 `scope_token`。P2 测试必须证明：stream 出来的 RunEvent 不含明文 token，但同进程调用方可通过
`get_tool_fetch_more_handle(...)` 获得补读所需 handle。

`ToolFetchMoreResult` 是封闭联合：

- 成功：包含 `run_id`、`session_id`、`tool_call_id`、`value`、`truncation`、`event_cursor`。
- 失败：包含 `run_id`、`session_id`、`tool_call_id`、`error_code`、`message`、`denied`、
  `event_cursor`。

`event_cursor` 必须指向补读完成 / 失败对应的 canonical RunEvent cursor，使调用方可用
`stream_run_events(run_id, after=event_cursor)` 继续追踪后续事件。唯一例外是 run 已 terminal 的
post-terminal fetch_more：P1.5 terminal guard 禁止 terminal 后 append，因此 P2 必须返回 typed failure 且
`event_cursor` 为空或指向已知 terminal cursor，不追加新的 denied RunEvent。post-terminal audited
fetch_more 留给 P6 / P7 / P11 统一讨论。

### Internal ToolRuntime

内部 `ToolRuntime` protocol 建议：

```python
class ToolRuntime(Protocol):
    async def execute_tool_call(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome: ...

    async def fetch_more(
        self,
        request: ToolFetchMoreRequest,
    ) -> ToolFetchMoreResult: ...
```

`ToolRuntimeToolExecutor` 仅实现 `dayu.contracts.ToolExecutor`，供 `EngineWorker` 代持给 Engine。
它必须保持内部符号，不进入 `dayu.host.__all__`。

### Cursor / scope token / TTL / 权限校验

P2 最小契约：

- cursor 由 Host ToolRuntime 生成，不由 Engine sequence、RunEvent cursor 或工具返回值决定。
- cursor record 至少绑定：`run_id`、`session_id`、`tool_call_id`、`tool_name`、`scope_hash`、
  `offset`、`limit`、`total`、`expires_at`、`created_at`。
- `scope_hash` 由工具名与规范化参数生成，用于审计 / 追踪，不作为唯一权限凭证。
- `scope_token` 由 cursor、scope_hash、session_id、run_id、tool_call_id、created_at 等记录字段生成并校验。
- `fetch_more` 必须校验 run / session / tool_call 与 scope token；跨 run / session / tool_call 使用 cursor
  必须 denied。
- `tool_call_id` 校验的是产生截断 cursor 的原始工具调用。P2 public fetch_more 不引入 Engine
  iteration 校验，也不把后续 caller turn 或 fetch_more 请求自身当作新的绑定对象。
- cursor 过期返回 typed failure，并追加 `cursor expired` canonical RunEvent。
- cursor 不存在、旧 cursor 复用、scope token 不匹配均返回 typed failure，并追加 denied / failed
  canonical RunEvent。
- `limit` 为正整数时使用 `min(requested, original_limit)`；否则使用原始截断 limit。
- 成功续读后旧 cursor 必须失效；如果还有更多内容，生成新 cursor 与新 scope token。
- 创建新 cursor 前必须 opportunistic 清理已过期 cursor，避免无人访问的过期大 payload 长期滞留。
- P2 in-memory TTL 使用 monotonic clock；持久化时间语义留给 P6 / P8。

### 截断策略

P2 只迁移 OLD 已证明的通用策略：

- `text_chars`
- `text_lines`
- `list_items`
- `binary_bytes`

截断触发与目标选择采用严格 NEW 规则：

- 截断必须由工具 schema / tool metadata 上的显式 truncate spec 驱动；这是唯一触发条件。
- 没有显式 truncate spec、spec 未启用、strategy 未知或 limit 非正整数时，一律不截断。
- 原始 `value` 本身是 `str`、`list`、`bytes` / `bytearray` 时，可按策略直接截断整个 value。
- 原始 `value` 是 wrapper dict 时，必须有显式 `target_field` 或 `field_path` 指向截断目标；否则不截断。
- P2 不继承 OLD longest text / largest nested list 启发式，避免 Host 过度理解业务 payload。

如果实施 Agent 认为必须保留 OLD 启发式字段选择，必须先停止并提交 plan 修订；不能在 P2 code review
阶段临时引入启发式。

### 事实进入 RunEventStore 的选择

P2 选择把 ToolRuntime 最小事实全部写入 canonical RunEvent，而不是另建 ToolRuntime 内部 fact store。

原因：

- P1.5 已固定 P2-P5 共同事实层，P2 若另起 fact store 会形成第二套 tool result 真源。
- P6 observer 要从 EventLog 派生 tool trace / audit / timeline；P2 先写 canonical RunEvent，可保证 P6
  不需要倒查进程内 cursor store。
- cursor store 只保存补读所需的临时数据引用和 offset，不承担审计真源职责。

新增 RunEvent data 需能表达：

- tool result truncated：原始 tool_call、截断策略、limit、unit、total estimate、cursor fingerprint、TTL、
  has_more。
- cursor issued：scope_hash、ttl_seconds、expires_at、单次有效语义。
- fetch_more requested：调用方请求、limit、cursor fingerprint。
- fetch_more completed：返回 chunk 摘要、新 cursor 是否生成、has_more、value size summary。
- fetch_more failed：错误码、是否 denied、是否 expired。
- cursor expired / denied：失败原因与关联 cursor fingerprint。

不得把完整未截断原始结果、scope token 明文或大块二进制直接写入 RunEvent。需要可追溯时写 fingerprint、
size、unit、tool_call_id 与 cursor lineage。

## 状态机变化

P2 不修改 Run terminal 状态机。ToolRuntime 事实是 Run 内部 canonical 中间事实：

```text
tool completed
  -> result not truncated
  -> result truncated -> cursor issued
      -> fetch_more requested
          -> fetch_more completed -> cursor consumed -> optional next cursor issued
          -> fetch_more failed
          -> cursor expired
          -> cursor denied
```

状态规则：

- 截断 / 补读失败不自动导致 Run `FAILED`；它是工具补读请求失败事实。
- 工具原始执行失败仍按 Engine 当前 tool outcome 语义处理，不在 P2 改 Run terminal。
- 若 ToolRuntime adapter 自身在 Engine tool execution 路径发生未封装异常，必须返回失败 `ToolExecutionOutcome`
  或让既有 Host-owned failure 路径产生 RunEvent；不得让异常绕过 EventLog。
- terminal RunEvent 后不再接受新的 `fetch_more`，P2 返回 typed failure，不追加新的 denied RunEvent。
  这是为了遵守 P1.5 terminal guard：terminal 后不能 append。post-terminal fetch_more 的审计事实、
  外部请求日志或 outbox 语义留给 P6 / P7 / P11 统一设计，P2 不破坏 terminal semantics。

## 数据持久化 / schema 变化

P2 不引入持久化 schema，不修改 workspace schema，不新增 migration。

原因：

- P2 的 cursor store 是 P2-P5 smoke 所需的 in-memory adapter，只声明单进程有效。
- 可审计事实进入 `RunEventStore`；当前 `RunEventStore` 仍是 P1.5 in-memory 实现，P6 会落地持久化。
- P6 持久 EventLog 时必须保留 P2 canonical RunEvent 子集语义；不能把截断 / 补读事实改成只存在于
  tool trace sink。

若后续 P6 / P8 引入持久 cursor schema，则按全新 schema 起库处理，不做旧库兼容读取；是否进入
`workspace_migrations` 留到对应 phase plan 决定。

## 多进程并发影响

P2 只保证单进程内 cursor store 正确：

- in-memory store 可用 `asyncio.Lock` 或等价机制保护 cursor record。
- single-use 消费必须在同一锁内完成校验、删除旧 cursor、生成下一 cursor。
- 不宣称跨进程 cursor 唯一、过期清理、owner fencing 或 recovery 正确。

P2 必须在 README / tests 中明确：

- 多进程下另一个进程无法补读当前进程内 cursor，属于未落地能力。
- P6 / P8 需要持久 cursor store、owner token、lease / fencing 与 recovery。
- P2 的 RunEvent 事实可追溯，但 cursor payload 数据本身可能随进程退出丢失。

## ToolRuntime / EngineWorker / Engine 边界影响

- Engine 不新增对 Host / ToolRuntime 的 import。
- Engine 不新增 `fetch_more` 内置协议，不持有 cursor，不管理 TTL。
- `ToolExecutor.execute` 仍是 Engine 唯一工具执行入口。
- `EngineWorker` 只代持 ToolRuntime adapter；不把 ToolRuntime public 化。
- `LocalRunHarness` 可装配 fake business executor 供测试；这不代表 public API 接收 `ToolExecutor`。
- ToolRuntime 不直接等同于 tool trace；它只产生运行事实，P6 observer 再派生 trace / audit。

## EventLog / RunEventStore / projection 影响

- P2 新增的 ToolRuntime facts 必须是 `RunEventKind.CANONICAL`。
- 所有 ToolRuntime facts 必须通过 `RunEventStore.append(RunEventDraft)` 获得 Host cursor。
- `fetch_more_tool_result` 返回前必须至少 append requested 和 terminal-like fetch_more completed / failed
  事实；如果 requested append 成功但执行失败，必须 append failed 事实。
- 若 run 已 terminal，`fetch_more_tool_result` 必须在 append 前检查并返回 typed failure；不得为了记录 denied
  事实绕过或削弱 P1.5 terminal guard。
- `RunEvent.data` 只保存中性事实摘要，不保存大结果原文或 scope token 明文。
- P6 observer 可按 `RunEventType` 与 tool_call_id 派生 tool trace、audit 与 timeline；P2 不实现 observer。
- preview event 不参与 ToolRuntime 事实。

## 可接受临时实现 / 不可接受临时实现

可接受：

- in-memory cursor store。
- in-memory truncate spec registry 或测试注入的 per-tool truncate spec map。
- 单进程 lock 保护 cursor single-use。
- 使用标准库 hash / token 生成；测试中固定 clock / token generator 以验证 TTL 与 single-use。
- 只支持显式 truncate spec，不做完整 ToolRegistry schema 发现。

不可接受：

- 在 Engine 中实现 `TruncationManager`、`fetch_more` 或 cursor store。
- 把 `ToolRuntime`、cursor store、`ToolRuntimeToolExecutor` 导出为 Host public API。
- 只在工具结果 envelope 中带 `truncation`，但不写 canonical RunEvent。
- 另建 transcript / tool result 真源，绕过 P1.5 `RunEventStore`。
- 向 LLM 投影 `has_more` 这类不可执行半协议，或泄漏 scope token / scope hash。
- 把 scope token 明文写入 canonical / preview RunEvent，或要求调用方从 EventLog 推导 token。
- 在 wrapper dict 上使用 OLD longest text / largest nested list 启发式选择截断目标。
- 使用 `Any`、`object`、开放 `dict` payload 表达契约。
- 通过兼容 wrapper / facade 保留 OLD Engine 导入路径。
- 在 P2 偷做完整 ToolRegistry 权限、P6 observer、P7 lifecycle governance、多进程 recovery。

## runtime dependency

P2 不涉及 lane，不新增 `dayu.runtime` 能力。

理由：

- cursor TTL、scope token、single-use 是 Host ToolRuntime 运行事实，不是层中立 runtime helper。
- 单进程 lock 只服务 P2 in-memory adapter，不应抽入 `dayu.runtime`。
- 若后续 P8 需要跨进程 lane / lease / fencing，应复用或扩展 `dayu.runtime` 的层中立能力；
  P2 不提前设计 lane。

`dayu.runtime` 仍不得 import `dayu.host`、`dayu.engine`、`dayu.service`、`dayu.ui` 或 `dayu.fins`。

## 测试清单

新增 / 修改测试必须覆盖：

- Public boundary：`dayu.host.__all__` 只包含 Run 级补读入口和契约类型，不包含内部 ToolRuntime、
  cursor store、adapter、EngineWorker、ToolExecutor。
- Import boundary：`dayu.engine` 不 import `dayu.host` / ToolRuntime；`dayu.runtime` 不 import Host。
- Truncation strategy：text chars、text lines、list items、binary bytes 分别截断并生成 cursor。
- No spec no truncate：无显式 truncate spec 时不截断。
- Explicit target only：wrapper dict 只有显式 `target_field` / `field_path` 时才截断；没有显式目标时不使用
  OLD longest text / largest nested list 启发式。
- Execute-time cursor facts：fake business executor 返回超限结果后，`ToolRuntimeToolExecutor.execute` 返回前
  已完成截断、cursor 生成、TTL 起算、canonical `tool_result_truncated` / `tool_cursor_issued` append；
  不调用 fetch_more 也能通过 `stream_run_events` 观察到这些事实。
- Cursor issued fact：截断后 append canonical `tool_result_truncated` / `tool_cursor_issued`。
- Fetch_more handle delivery：RunEvent / stream / Engine projection 不含明文 `scope_token`；同进程调用方可通过
  `get_tool_fetch_more_handle(...)` 按 session / run / 原始 tool_call / cursor fingerprint 获得 handle。
- Scope token：token 生成材料包含 session_id；缺失或错误 token 返回 denied，append canonical denied /
  failed fact。
- Run scope：跨 run / session / 原始 tool_call 使用 cursor 被拒绝；同一 run / session / 原始 tool_call 在
  后续 caller turn 仍可补读，不引入 Engine iteration 校验。
- TTL：过期 cursor 返回 expired，cursor 被清理，append canonical expired fact。
- TTL opportunistic cleanup：创建新 cursor 时清理此前已过期 cursor，避免只截断不补读时 payload 滞留。
- Single-use：成功 `fetch_more` 后旧 cursor 失效；has_more 时返回新 cursor，新 cursor 可继续补读。
- Limit clamp：请求 limit 大于原始 limit 时按原始 limit 读取。
- Fetch_more event ordering：requested 先 append，completed / failed 后 append，返回结果携带 completed /
  failed event cursor。
- EventLog truth：`stream_run_events` 能补读到截断与补读事实；不得只能从内部 cursor store 观察。
- Terminal guard：Run terminal 后 `fetch_more` typed failure；不得 append terminal 后 denied RunEvent，不破坏
  P1.5 terminal semantics。
- OLD / NEW 差异：当前 Engine LLM projection 仍不泄漏 `scope_token`、`scope_hash`、不可执行
  `has_more`；P2 不把半协议塞回 Engine；P2 只继承 OLD cursor lifecycle 等底层可靠语义，不误称完整
  OLD LLM-facing fetch_more 闭环。
- Weak typing guard：新增契约不得引入 `Any`、`object`、无类型参数或无类型返回值。

单文件测试覆盖率目标仍按项目规则 >= 80%。`dayu/render/` 与 `utils/` 默认无覆盖率要求。

## 验证命令

P2 实施完成后必须运行：

```bash
source .venv/bin/activate
python -m pytest tests/host/test_phase2_tool_runtime_truncation.py
python -m pytest tests/host/test_phase2_tool_runtime_eventlog.py
python -m pytest tests/host/test_phase2_tool_runtime_boundary.py
python -m pytest tests/host tests/contracts
python utils/smoke_host_tool_runtime.py --log-level DEBUG
python -m pyright
```

本 plan 阶段只新增文档，不跑 pytest / pyright；文档校验命令：

```bash
sed -n '1,80p' docs/host/phase2-plan.md
rg -n "ToolRuntime|fetch_more|scope token|RunEventStore|review gate" docs/host/phase2-plan.md
```

## README / docs 触发判断

本 plan 阶段只新增 `docs/host/phase2-plan.md`，不更新 README。

P2 代码实施阶段触发：

- 修改 `dayu/host/`：需要更新 `dayu/host/README.md`，只写当前已落地的 ToolRuntime / fetch_more
  事实、P2 后执行边界、smoke 命令和未落地能力。
- 修改 Host 执行边界：需要更新 `docs/host/design.md`，写回 P2 后的 ToolRuntime 执行路径、
  fetch_more handle / 补读路径、EventLog 事实边界与仍后移的 LLM-facing `fetch_more`。
- 修改 `tests/host/`：需要更新 `tests/README.md` 的 Host 测试分层。
- 新增 `utils/smoke_host_tool_runtime.py`：若 smoke 运行方式成为项目级常用入口，再检查根
  `README.md` 是否需要导航；否则只在 `dayu/host/README.md` 记录 Host 开发手工验证命令。
- 若修改 `dayu/contracts/` 的工具结果契约：检查根 `README.md` 是否涉及用户可见工具结果或 CLI 行为；
  不属于则不机械更新。
- 不更新 `dayu/engine/README.md`，除非 Engine 当前事实被代码修改；P2 不应修改 Engine 事实。
- 不更新 `docs/code_review.md`，直到 P2 代码 review 通过且用户确认事实已经落地。

## review gate

Plan review gate 必须检查：

- 是否明确 ToolRuntime 最小 Host 边界、public / internal 符号。
- 是否选择 canonical RunEvent 作为截断 / 补读事实真源，并说明不另建旁路事实。
- 是否覆盖 cursor、scope token、TTL、single-use、run scope、limit clamp。
- 是否闭合初始 `scope_token` 的非 EventLog 交付通道，并证明真实 P2 调用方限定清楚。
- 是否明确 P2 只继承 OLD 底层 cursor 可靠语义，OLD LLM-facing schema / projection 后移。
- 是否明确 session / 原始 tool_call 绑定、token 生成材料与不引入 Engine iteration 校验。
- 是否明确截断由工具 schema / tool metadata 的显式 truncate spec 唯一驱动；无声明、未启用或 limit
  非法时不得截断。
- 是否明确截断目标选择采用严格显式 target，不继承 OLD 启发式。
- 是否明确 terminal 后 fetch_more 返回 typed failure without new RunEvent，遵守 P1.5 terminal guard。
- 是否保持 EngineWorker / ToolExecutor 边界：Engine 只表达 tool call，Host / ToolRuntime 负责治理。
- 是否明确不提前实现完整 ToolRegistry、P6 observer、P7 lifecycle、多进程 recovery。

Code review gate 必须增加：

- OLD / NEW 语义差异 review：P2 代码 review 必须额外派 OLD / NEW 对比 review Agent，对照 OLD
  `TruncationManager`、OLD `fetch_more` schema、OLD
  `project_for_llm` 与 OLD 测试，确认 NEW 没有丢失 single-use / TTL / scope token / limit clamp /
  page structure 等底层可靠语义，也没有误恢复 OLD LLM-facing fetch_more 或把 OLD Engine 归属机械迁回
  Engine。
- EventLog truth review：所有治理事实是否可由 `RunEventStore` 补读，是否存在内部 cursor store 黑盒。
- Boundary review：public exports、import graph、README 是否泄漏内部机制。
- Type review：无 `Any` / `object` / untyped signature / extra payload。
- Test review：测试必须覆盖“语义和实际实现逻辑的差异”，不能只测字段存在。
- Smoke review：`utils/smoke_host_tool_runtime.py` 必须能通过日志观察 P2 后执行边界，且不得泄漏
  明文 scope token 或大结果。

## 停止条件

实施 Agent 遇到以下情况必须停止并回报：

- 需要修改 Engine 才能实现 P2 基础能力。
- 需要把 `ToolRuntime` 或 `ToolExecutor` 作为 Host public API 暴露给 UI / Service。
- P1.5 `RunEventStore` 无法表达 ToolRuntime canonical facts，且需要重写 EventLog 契约。
- 代码实施尝试在 terminal RunEvent 后追加 fetch_more denied / expired RunEvent，或需要削弱 P1.5 terminal
  guard 才能让测试通过。
- 无法通过非 EventLog Host handle 契约交付初始 `scope_token`，导致 public fetch_more 只能依赖 RunEvent
  泄漏 token 或测试私有状态。
- 需要在没有工具 schema / tool metadata 显式 truncate spec 的情况下启发式截断工具结果。
- 需要继承 OLD longest text / largest nested list 启发式才能让当前工具可用。
- 需要持久化 cursor schema 或多进程 recovery 才能让测试通过。
- 需要完整 ToolRegistry 权限、业务工具迁移、P6 observer 或 P7 governance 才能继续。
- 新增契约只能靠 `Any` / `object` / dict bag 表达。

## 风险与回滚

主要风险：

- P2 若只实现 cursor store 而不写 canonical RunEvent，会让 P6 observer 无可靠输入。
- P2 若把 `fetch_more` 暴露给 Engine / LLM，但 projection 未同步可执行协议，会重现 Phase 3 已避免的半协议问题。
- in-memory cursor store 在多进程和进程退出后丢失；这是 P2 明确限制，必须文档化。
- cursor record 持有原始大结果会增加内存压力；P2 需测试 TTL 清理，并避免把大结果写入 EventLog。
- scope token 若明文进入 RunEvent / logs，会形成治理凭证泄漏。
- 真实远程 UI 直接补读体验在 P2 仍受限；P2 只支持同进程 Host UI / Service adapter 或测试 harness 通过
  受控 handle 补读，远程和 LLM 主动补读后移。

回滚策略：

- P2 代码应集中在 `_tool_runtime.py`、Host contracts、harness 装配与测试；若失败，可回滚这些文件和
  README / tests 更新，不影响 P1.5 EventLog。
- 不修改 Engine 可降低回滚半径。
- 若 `dayu/contracts/tool_result.py` 被修改，回滚时必须同步回滚相关 tests/contracts，避免契约漂移。

## 待用户确认项

- P2 是否只提供 Run 级 public `fetch_more_tool_result`，暂不把 `fetch_more` 注册为 LLM 可调用工具。
- P2 是否接受新增受控 `get_tool_fetch_more_handle(...)` 作为初始 token 非 EventLog 交付通道，真实调用方
  限定为同进程 Host UI / Service adapter 或测试 harness。
- P2 是否选择所有 ToolRuntime 最小事实进入 canonical RunEvent，而不另建 ToolRuntime fact store。
- terminal Run 后的 `fetch_more`：P2 计划采用 typed failure without new RunEvent，以遵守 P1.5 terminal
  guard；post-terminal audited fetch_more 是否进入 P6 / P7 / P11 设计。
- P2 是否修改 `dayu.contracts.ToolTruncationInfo` 增加可执行补读字段，还是保持当前 envelope 只承载
  内部中性截断信息，public 补读结果另用 Host 契约表达。
- P2 截断策略是否仅支持显式 truncate spec，不保留 OLD 启发式字段选择。

## 迁移 Agent 实施完成汇报格式

实施完成后按以下格式汇报：

```text
修改文件：
- ...

关键实现：
- ToolRuntime public / internal 边界：
- 截断与 fetch_more 事实进入 RunEventStore 的方式：
- cursor / scope token / TTL / single-use 契约：
- EngineWorker / ToolExecutor 边界：

验证：
- pytest ...
- pyright ...

README / docs：
- design 执行边界更新：
- ...

Smoke：
- python utils/smoke_host_tool_runtime.py --log-level DEBUG

未覆盖风险：
- ...

待用户确认：
- ...
```
