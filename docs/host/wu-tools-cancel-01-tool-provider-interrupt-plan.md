# WU-TOOLS-CANCEL-01 Tool/provider interrupt plan

## 1. Goal / Motivation / Success Signal

Work unit：`WU-TOOLS-CANCEL-01 Tool/provider blocking I/O cancellation hardening`。

类型：issue-backed Host follow-up / issue-87 umbrella final closeout work unit。

当前目标成立，且严重性没有被高估。第一性原理判断如下：

- 用户按 Esc 后，正确体验不是“等旧工具自然结束”，而是 Host 迅速回到可交互状态，新输入可以继续推进。
- 已完成的 WU-LIFE-03 / WU-LIFE-04 已解决 Host durable cancel terminal truth 和取消不延长工具预算的问题，但它们不证明工具、provider stream、线程或子进程已经物理停止。
- 当前代码中 ToolRuntime 只把业务 tool callable 包在 cancellation token 和 batch deadline 的 awaitable race 里；对 `asyncio.to_thread(...)`、同步 HTTP、browser fallback、provider stream 和子进程，这不足以提供统一 interrupt / escalation / cleanup 语义。
- 如果旧 worker stream 长时间卡住，dispatch consumer 的 `finally` 不会运行，active handle 和 lane token 可能继续占用本地资源；即使 Run 已 durable `CANCELLED`，新输入仍可能在本地执行资源上被旧执行拖住。

本 work unit 的第一验收信号是 Esc interrupt 用户体感：

- interactive CLI 运行态 Esc 触发 cancel 后，用户能迅速回到输入态。
- 同一 Session 中取消后的新输入可以继续推进，不被旧 tool/provider 阻塞。
- 旧 tool/provider 的完成、失败或 late terminal 不能污染已取消 Run。
- 取消不得新增或延长 `tool_execution_timeout_seconds` 预算；只能缩短或中止当前执行。

## 2. Non-goals / Scope Boundary

本 work unit 不做以下事项：

- 不重做 WU-LIFE-03：不重写 Host active cancel watchdog、Run / Attempt terminal truth、late terminal race 或 queued promotion 状态机。
- 不重做 WU-LIFE-04：不恢复 `active_cancel_timeout_seconds`，不引入第二套 cancel timeout，不把 cancel 解释为新的等待预算。
- 不重做 WU-WAIT-03：不改变 WAITING external job cancel / revoke / abandon lifecycle，不绕过 `resolve_wait(...)` 和 late-result rejection。
- 不修改 Engine 对工具内部治理的职责边界。Engine 仍只调用 `ToolExecutor.execute(BatchToolExecutionRequest)`，不拥有工具 registry、工具 kill、Host wait、dispatch 或 durable truth。
- 不把 provider-specific kill API 硬编码进 Host core。Host / ToolRuntime 只调用通用 typed interrupt boundary；具体 HTTP/browser/provider/subprocess 如何 abort 由 tool/provider adapter 或 execution capsule 实现。
- 不新增 durable schema、EventLog event type 或 public cancel command。
- 不把所有工具统一迁移到重型 sandbox 平台；只补齐当前生产路径需要的 interruptible execution capsule、adapter hook、cleanup 和测试。

## 3. Design Document Alignment

### Host design alignment

`docs/host/design.md` 规定：

- Host 是 Session / Run / Attempt / EventLog / cancel / dispatch / tool governance 的治理真源。
- ToolRuntime / TruncationManager 是工具执行治理、截断、等待与重复调用治理 owner。
- dispatch、sink、tool runtime 和 remote stub 不能直接写 Run / Attempt / EventLog，必须经过 Host state transition / ingest / accept barrier。
- `dayu.runtime` 只能承载层中立基础能力，不能依赖 Host / Engine / Service / UI / Fins，也不能承载 Host durable truth。

本 plan 对齐方式：

- 取消终态仍由 Host command + active cancel watchdog 写入 durable truth。
- Tool/provider interrupt 由 ToolRuntime / worker execution boundary 承担，不进入 admission 或 durable transition。
- late result 继续依赖 ToolRuntime accept barrier、EngineEvent ingest durable context 和 first-committer-wins / late rejection。
- 如需通用 process / thread / cancellation helper，放在 `dayu.runtime`，且只能依赖标准库与 `dayu.contracts`；Host-specific wiring 放在 `dayu.host`。

### Engine design alignment

`docs/engine/design.md` 规定：

- Engine 是 run-scoped，一次 `AgentRunRequest` 创建一次 Agent / Runner；取消和恢复都不复用旧 Agent / Runner。
- Engine 只通过 `ToolExecutor.execute(BatchToolExecutionRequest)` 做 bounded handshake。
- `AgentPolicy.tool_execution_timeout_seconds` 是 Engine 等待 `ToolExecutor.execute` 返回 outcome 的唯一工具 handshake timeout 真源。
- Runner 负责在 HTTP 建连、SSE chunk、body read、retry sleep 等边界观察取消并关闭底层资源。
- Engine 不负责工具注册、工具内部超时、后台任务治理、长事务监控或恢复调度。

本 plan 对齐方式：

- 不要求 Engine 理解 tool/provider kill；Engine contract 最多保持现有 `BatchToolExecutionContext` 的 token / timeout 投影。
- ToolRuntime 继续在同一个 `tool_execution_timeout_seconds` 内执行；interrupt 不新增 Engine timeout。
- provider stream abort 保持 Runner / provider adapter 自己关闭连接的职责；Host 不内嵌 provider API。
- 若实现发现必须扩展 Engine public contract，必须先停下进入设计真源更新；当前 plan 判定不需要。

## 4. First-principles Judgment and Direct Code Evidence

### 4.1 入口和 Host terminal 不是根因

- CLI Esc 映射已经存在：`dayu/cli/run_keys.py:20-33` 定义 `_ESC=b"\x1b"` 和 `RunningKeyAction.CANCEL_RUN`；`tests/cli/test_interactive_command.py:1181` 覆盖 interactive 运行态 Esc 请求 cancel。
- public Host cancel 入口已经存在：`dayu/host/open_host.py:627` 的 `cancel_run(...)` 调用 command path；`dayu/host/command.py:628-676` 在 durable cancel commit 后传播 active cancel target。
- active cancel 会唤醒 watchdog：`dayu/host/command.py:1619-1648` 先 `_wake_active_cancel_watchdog(host)`，再通过 active registry cancel worker。
- watchdog 已能在 accepted cancel 后写 terminal：`dayu/host/durable/run_transition.py:2248-2352` 的 `active_cancel_watchdog_closeout_in_transaction(...)` 写 `ATTEMPT_CANCELLED` 与 `RUN_CANCELLED`；`tests/host/test_active_cancel_dispatch.py:454-483` 覆盖第一轮 tick 即关闭 cancelled。

结论：问题不在按键入口，也不在 Host Run / Attempt 终态。

### 4.2 ToolRuntime 当前治理边界不足

- `ToolDefinition.callable` 是 async single-tool callable，公共契约不允许同步实现阻塞事件循环：`dayu/contracts/tool_declaration.py:38-64`。
- 默认 dispatcher 直接 `await definition.callable(call, context)`：`dayu/host/tool_runtime.py:1254-1273`。
- ToolRuntime 批次执行只计算 batch deadline 并逐个 `_execute_one(...)`：`dayu/host/tool_runtime.py:2258-2293`。
- `_dispatch_tool_call_with_bounds(...)` 只用 `await_or_cancel(...)` / `await_or_cancel_or_timeout(...)` race callable awaitable、`context.cancellation_token` 和剩余 batch timeout：`dayu/host/tool_runtime.py:2590-2630`。
- 该 race 可以取消协程 task，但不能保证已经进入 `asyncio.to_thread(...)` 的同步 I/O、HTTP socket、browser worker 或子进程已停止。

### 4.3 生产工具存在 blocking I/O 形态

- Doc 工具在 provider lock 内调用 `asyncio.to_thread(business_call, token)`：`dayu/tools/doc_tools.py:702-733`。
- Fins 工具在 provider lock 内调用 `asyncio.to_thread(business_call, cancellation_token)`：`dayu/fins/tools/fins_tools.py:770-778`。
- Web 工具主路径调用 `asyncio.to_thread(...)` 执行同步 search/fetch 业务：`dayu/tools/web/web_tools.py:1161-1174` 和 `dayu/tools/web/web_tools.py:1260-1275`。
- Web HTTP session 当前有 deadline helper，但部分主路径仍传入 `timeout_budget=None`；`dayu/tools/web/web_http_session.py:200-232` 说明 deadline helper 只在调用方传入预算时生效。
- SEC downloader 已使用 `httpx.AsyncClient`：`dayu/fins/downloaders/sec_downloader.py:837-856`，但 Host / ToolRuntime 没有统一 request abort / stream close capsule。
- Playwright backend 已有局部子进程 terminate / kill：`dayu/tools/web/web_playwright_backend.py:418-428`；`_run_playwright_worker_process(...)` 在 token 取消时 terminate 进程并抛取消：`dayu/tools/web/web_playwright_backend.py:480-525`。这是可复用的模式证据，但当前只属于 Web Playwright 局部实现，不是通用 ToolRuntime / worker-owned interrupt boundary。

### 4.4 Worker stream / lane cleanup 与新输入推进直接相关

- Active worker registry 只做 best-effort cancel propagation，durable truth 仍由 EventLog / Run state 决定：`dayu/host/dispatch.py:593-657`。
- `_propagate_active_worker_cancel(...)` 写入 Host 注入 Engine 的 cancellation token，并调用 handle `on_cancel(...)`：`dayu/host/dispatch.py:694-710`。
- 默认 local worker handle 的 `on_cancel(...)` 当前为空实现，只依赖 Engine/ToolRuntime 观察 token：`dayu/host/local_proxy.py:136-146`。
- dispatch 启动 worker 后把 handle 放入 active registry，并启动 `_consume_worker_events(...)`：`dayu/host/dispatch.py:3036-3221`。
- `_consume_worker_events(...)` 只有在 worker events 结束、异常、terminal closeout 或 stop signal 后才进入 `finally`，在 finally 中注销 active handle、关闭 handle 并释放 lane token：`dayu/host/dispatch.py:3738-3920`。
- 因此，若 old worker stream 卡在 provider/tool 执行边界，Host durable `CANCELLED` 可以已成立，但本地 lane token 和 active handle 仍可能被旧 worker 持有，影响取消后新输入推进。

### 4.5 Late result quarantine 已有基础，但必须纳入验证矩阵

- ToolRuntime accept barrier 会校验 run / attempt / execution / dispatch 同源，并要求 Run/Attempt 仍为 running：`dayu/host/tool_runtime.py:3491-3544`。已取消或 stale execution 的工具结果应被拒绝，而不是 accepted 为 canonical tool fact。
- Engine ingest 会校验 durable context 同源：`dayu/host/engine_ingest.py:994-1027`。
- Engine ingest 对 terminal 后迟到事件和 active cancel 后的 late final / failed terminal 有拒绝原因：`dayu/host/engine_ingest.py:3283-3308`。

结论：stale quarantine 的根基存在；本 work unit 需要把它和 interrupt cleanup 一起做成 public cancel smoke 与 focused tests，而不是重写状态机。

## 5. Affected Files / Modules Estimate

### Host

- `dayu/host/tool_runtime.py`：ToolRuntime execution capsule integration、tool callable execution ownership、cancel / timeout / escalation result mapping、diagnostic emission、stale accept barrier tests.
- `dayu/host/local_proxy.py`：default local worker handle 的 cancel hook / event stream close / active anext cancellation / generator close。
- `dayu/host/dispatch.py`：active worker cleanup 与 lane token release 的 cancel-triggered behavior；避免 worker stream 卡住时阻塞新输入。
- `dayu/host/api.py`：如需扩展 `LocalWorkerHandle` internal semantics，只更新 docstring / internal protocol，不新增 public cancel command。
- `dayu/host/tooling.py` 或邻近 Host tooling module：如需要 Host construction-time interrupt policy，必须保持 typed、最小字段、非 durable。

### Engine contract

- 默认不修改 `dayu.engine` public contract。
- 默认不修改 `BatchToolExecutionContext` 字段；继续使用现有 `cancellation_token` 与 `timeout_seconds`。
- 若实现中证明工具 provider 必须从 context 获得新的 interrupt handle，必须停下并先更新 `docs/engine/design.md` / `docs/host/design.md`，再继续。

### Runtime / contracts

- 可能新增层中立 helper，例如 `dayu.runtime.process_interrupt` 或 `dayu.runtime.interruptible`，用于 process terminate / kill、deadline race、bounded close。该 helper 不得 import Host / Engine / Service / UI / Fins。
- 默认不修改 `dayu.contracts`。Execution mode 优先作为 Host / runtime internal typed contract；如果直接证据证明 provider 必须在 shared tool declaration 中声明 mode / interrupt capability，implementation 必须停止并返回 design / contract gate。

### Tools / providers

- `dayu/tools/doc_tools.py`：迁移同步 business body 到 interruptible capsule 或声明其必须走 process-backed blocking execution。
- `dayu/fins/tools/fins_tools.py`：同上；必须继续遵守财报文档存取只能通过 `dayu.fins.storage`。
- `dayu/tools/web/web_tools.py`、`dayu/tools/web/web_http_session.py`、`dayu/tools/web/web_playwright_backend.py`：HTTP request / stream abort、deadline propagation、Playwright process terminate / hard kill 统一到 tool-owned adapter。
- Fins download / preprocess / upload awaiting path已由 WU-WAIT-03 管理 external job lifecycle；本 WU 只处理非 WAITING tool/provider blocking execution。

### Tests

- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_public_cancel_smoke.py`
- `tests/host/test_public_lifecycle_smoke.py` 或新增 focused public Esc/cancel smoke
- `tests/tools/test_doc_tools_provider.py`
- `tests/fins/test_fins_ingestion_tools.py` / Fins focused read tools tests
- `tests/tools/web/test_web_tools_provider.py`
- `tests/runtime/test_*` for process interrupt helper if added
- `tests/README.md` 只在测试入口职责变化时按约束检查

### Docs

- Implementation gate 修改 Host / Engine / tools 后，按 AGENTS README 触发规则检查：
  - `dayu/host/README.md`：若 Host ToolRuntime / worker cancel semantics 落地，需要更新当前代码已实现的 Host 开发说明。
  - `dayu/engine/README.md`：若 Engine contract 未变，一般不更新；若更改 Engine tool execution contract，必须更新。
  - `dayu/fins/README.md`：若 Fins tool execution / cancellation 行为对开发者稳定边界有变化，需要更新。
  - `tests/README.md`：若新增或调整稳定测试入口，需要检查。
  - 根 `README.md`：只有 CLI / Web / 用户可见取消工作流说明变化才检查；当前实现若只改善 Esc 体感且命令不变，通常无需更新。
  - `dayu/README.md`：若分层关系或 Host / Engine / Tool boundary 文字变化，需检查。
- 本 plan gate 不实际修改任何 README / design / control doc。

## 6. Contract / Schema / State-machine / Public Interface Changes

### Required

- 需要新增或明确一个 typed interruptible execution capsule contract。默认这是 Host / runtime internal contract，不修改 `dayu.contracts`。
- S1 必须先证明 internal typed execution mode 足够表达当前工具迁移；如果实现直接证据证明 provider 必须在 `ToolDefinition` / `dayu.contracts` 中声明 execution mode 或 interrupt capability，implementation 必须停止并返回 design / contract gate，不得用 magic string、tool name branch 或 `extra payload` 绕过。
- internal contract 必须表达：
  - execution identity：run id、attempt id、execution id、tool call id、tool name；
  - existing cooperative token；
  - remaining deadline derived from `BatchToolExecutionContext.timeout_seconds`；
  - typed execution mode：`async_direct`、`thread_backed`、`process_backed` 至少三类；
  - graceful interrupt；
  - hard kill；
  - bounded diagnostic closeout；
  - stale result handling owner。

### Not required

- 不新增 durable schema。
- 不新增 EventLog event type。
- 不新增 public Host cancel API。
- 不新增 Engine public run state。
- 不新增第二套 timeout。
- 默认不新增 `dayu.contracts` 字段。

理由：取消请求、Run/Attempt terminal、late event rejection、tool accept barrier 已有 durable truth；当前缺口是 runtime execution ownership 和 cleanup，不是事实模型缺失。

## 7. Implementation Decisions

### 7.1 Interruptible execution capsule

引入 ToolRuntime-owned execution capsule，包住单个 tool call 的真实执行形态。capsule 的职责不是写 Host truth，而是拥有执行资源并在 cancel / timeout / worker close 时完成 cleanup。

最小语义：

- `run(...)`：启动工具执行，返回 `ToolExecutionOutcome` 或结构化 capsule failure。
- `request_interrupt(reason)`：cooperative cancel，通知 token / request / stream / subprocess。
- `terminate(reason)`：graceful termination，例如关闭 HTTP response/session、关闭 async generator、terminate process。
- `kill(reason)`：hard kill，例如 process kill；仅用于 terminate 未在 bounded grace 内结束。
- `close()`：幂等释放本地资源。

Execution mode 必须是 typed value，不能用裸字符串、tool name 分支或 `extra payload` 表达。S1 至少定义以下模式和语义：

| Mode | 适用执行形态 | `request_interrupt` | `terminate` | `kill` | 是否满足 production-grade non-cooperative blocking cancel |
|---|---|---|---|---|---|
| `async_direct` | 直接在 event loop 中运行的 async tool / async HTTP / async stream | 设置 cooperative token，取消正在等待的 task；adapter 必须关闭已打开的 response / stream / client handle | 幂等调用 adapter close / stream close；不得杀进程 | 不适用，必须是 no-op diagnostic | 仅当 adapter 能在 task cancel 时关闭底层 request / stream 资源时满足；否则必须补 adapter abort hook 或停止 |
| `thread_backed` | 仍在 `asyncio.to_thread(...)` 或 executor thread 中运行的同步 callable | 设置 cooperative token；取消 wrapper awaitable | 不承诺停止 OS thread；最多关闭 adapter 暴露的 socket / session / stream handle | 不承诺 hard kill OS thread，必须记录 unsupported diagnostic | 不满足非协作 blocking 生产级取消；只能用于明确 cooperative、短耗时、read-only 且 late side effect 可接受的路径，不能用于 #87 closeout 的关键生产 blocking 路径 |
| `process_backed` | 非协作 blocking I/O、同步 HTTP/search/fetch、CPU/IO worker、可隔离子进程执行 | 设置 cooperative token 并停止接收 late result | terminate process / process group，并关闭队列 / pipe 写端 | bounded grace 后 kill process / process group，随后 join / close queue / pipe | 满足，前提是入口、参数和结果可序列化，且 business side effect 可被 late quarantine 或 idempotency 治理 |

生产级非协作 blocking cancel 只能由 `process_backed` 或 request-abort-capable 的 `async_direct` 满足。`thread_backed` 不是 hard interrupt 机制，implementation 不得把 thread cancel 包装成 terminate / kill 成功。

ToolRuntime 仍负责：

- duplicate governance；
- policy decision；
- accept barrier；
- awaiting accept；
- truncation；
- cancelled / timed-out / killed outcome 的治理映射；
- stale result 不进入 Host accepted fact。

### 7.2 Cooperative token

保留现有 `BatchToolExecutionContext.cancellation_token`，所有工具仍必须在可检查边界观察 token。cooperative token 是第一层，不足以作为唯一 interrupt 机制。

### 7.3 Request / stream abort

HTTP / provider stream 类执行必须在 adapter 内实现 abort：

- async provider / httpx path：按 `async_direct` capsule 语义执行，取消 pending task，并通过 adapter hook 关闭 response / stream / client；测试必须证明 cancel 后 response/client 被关闭或释放。
- requests / synchronous HTTP path：不能只等待 thread 自然结束；必须迁移到 `process_backed` capsule，或在 adapter 内提供可验证的 socket/session abort hook。仅关闭 thread wrapper 不满足生产级取消。
- provider SSE stream：继续由 Runner / provider adapter 关闭连接，Host 不写 provider-specific API。

### 7.4 Subprocess / process group / sandbox termination

对非协作 blocking I/O，生产级路径优先使用 process-backed capsule：

- graceful phase：terminate process / process group。
- hard phase：bounded grace 后 kill process / process group。
- cleanup phase：join、close queue/pipe、丢弃 late result。
- diagnostic：记录 terminate / kill / exit code / timeout，不把 killed result accepted 成业务事实。

Playwright 当前局部 terminate / kill 逻辑作为 adapter 参考模式，但不要复制成 Host web-specific 分支。

### 7.4.1 Process-backed feasibility and migration matrix

S1 / S2 进入生产工具迁移前必须按下表核对；S2 implementation report 必须逐项记录结果、选择的执行模式、验证用例和未覆盖项。

| Tool family / path | 当前阻塞形态 | 首选生产级策略 | Picklability / migration risk | Fallback strategy | Stop condition |
|---|---|---|---|---|---|
| Doc tools | `asyncio.to_thread(business_call, token)` 包装同步文档处理 / HTTP / 文件读取 | `process_backed`，把 process 入口改成模块级函数，只传可序列化 path、参数、tool call identity 和必要 config；结果通过结构化 value 回传 | 当前 `business_call` 可能是 closure / partial，processor / runtime 对象未必 picklable | 重构为模块级 process entrypoint；不可序列化对象在子进程内重新构造；如果某 processor 只能同进程运行，必须证明它有 request-abort hook 或从 production-grade cancel path 排除 | 关键 Doc 生产路径不能 process-backed 且不能 request-abort-capable 时，返回 design gate，不得标记 #87 closeout |
| Fins read tools | `asyncio.to_thread(business_call, cancellation_token)` 包装仓储读 / 文件 I/O / 解析 | `process_backed`，只传 workspace / repository locator、查询参数和 typed request；子进程内通过 `dayu.fins.storage` 仓储协议重新打开资源 | repository / runtime 实例不可 picklable；必须避免把仓储对象直接跨进程传递 | entrypoint 内重新构造只读 repository；若涉及 write / awaiting start path，确认不属于本 WU 或停下重新裁决 | 任何财报文档存取绕过 `dayu.fins.storage`、或关键 Fins read path 不能 process-backed / abort-capable 时，返回 design gate |
| Web sync HTTP / search / fetch | `asyncio.to_thread(...)` 调同步 search/fetch，且可能依赖共享 `requests.Session` | 优先迁移为 `process_backed` 同步 worker；或改为 request-abort-capable async HTTP adapter | 全局 `requests.Session` 不可 picklable；session 不能作为 process 参数传递 | 子进程内创建短生命周期 session；或将该路径迁移到 `httpx.AsyncClient` / async adapter，并按 `async_direct` cleanup 验证 | 同步 Web 主路径仍只能 thread-backed 且不能关闭底层 socket/session 时，返回 design gate |
| Async HTTP / httpx | 直接 async request / stream，例如 SEC downloader `httpx.AsyncClient` | `async_direct`，task cancel + response/client close hook；保留剩余 tool deadline 到 request timeout | 不需要 pickling；风险是 cancel 后 response/client 未释放或 stream 未关闭 | adapter 暴露 abort/close hook；必要时收窄 client lifetime 到单次 tool call或显式 context manager | 无法验证 response/client cleanup，且路径会影响 Esc 后资源释放时，返回 S2/S1 修正；若需新 public contract，返回 design gate |
| Playwright | 已有 `multiprocessing` worker 与 terminate / kill 局部实现 | 保持 `process_backed`，把既有 terminate -> kill 语义挂到 typed capsule / adapter 边界 | worker callable 已有 picklability 检查；浏览器对象、Playwright runtime 不能跨进程传递 | 子进程内初始化 / 获取 Playwright runtime；不可 picklable worker fallback 必须 fail closed，不回落为不可抢占 thread | Playwright fallback 不能维持 process-backed terminate/kill 且仍作为 production cancel path 时，返回 design gate |

全局 stop condition：如果 doc、Fins read、Web sync 主路径或 Playwright 这类关键生产路径不能迁移到 `process_backed`，也不能提供 request-abort-capable `async_direct` adapter，且修复需要改变 Host / Engine public contract、工具声明公共契约或业务存储架构，本 work unit 必须返回 design gate，不得进入 #87 closeout。

### 7.5 Hard-kill diagnostic closeout

hard kill 是 runtime cleanup fact，不是 Host Run terminal truth。若 Run 已由 watchdog 关闭，hard-kill diagnostic 只进入 bounded log / tool trace diagnostic 可用通道，不新增 EventLog canonical fact。

若 hard kill 在 Run 仍 running 且工具 batch 尚未 terminal 时发生，ToolRuntime 返回 governed cancelled / failed outcome，并经过现有 accept barrier；若 accept barrier 因 Run 已取消而拒绝，返回给旧 Engine 的结果不得污染 Host。

### 7.6 Stale / late result quarantine

必须保留两道 barrier：

- ToolRuntime accept barrier：Run / Attempt / dispatch 不再 running 或 execution stale 时拒绝 tool fact。
- Engine ingest barrier：late final / failed / cancelled terminal 不覆盖已 terminal Run。

实现不得用“先 kill 所以不会 late result”作为 correctness 依据。kill 是资源治理；stale quarantine 是 correctness 依据。

### 7.7 Lane token / active worker cleanup

取消后的可交互恢复依赖 active worker cleanup：

- Host cancel commit 后 active registry 继续写 cancellation token。
- default local worker `on_cancel(...)` 必须调用 event stream close path，而不是只设置 flag 或只取消裸 task。
- event stream close path 必须取消 active `anext` task、等待并吞掉该 task 的 `CancelledError`、调用底层 async generator `aclose()`，且 close 必须幂等。
- active `anext` 被 close 取消时，`_consume_worker_events(...)` 可以走 `CancelledError` re-raise 或 clean EOF 路径；两者都必须容忍，关键要求是外层消费 task 进入 `finally`。
- `_consume_worker_events(...)` 的 `finally` 必须注销 active handle、关闭 handle、release lane token；`CancelledError` 可以向 dispatch owner task 传播，但不得跳过 finally，不得作为 Host durable terminal truth。
- worker handle close 使用内部小型 cleanup grace，例如命名常量或 typed internal option `local_worker_close_grace_seconds = 3.0`。这是 cleanup grace，不是 cancel timeout，不是 public API，不得从 `tool_execution_timeout_seconds` 派生更长等待，也不得把用户可见 input-ready 体验延后到工具 deadline。
- close grace 到期后记录 bounded diagnostic 并继续释放 lane token；旧 worker 若后续产出 late result，仍由 accept / ingest barrier 拒绝。

### 7.8 New input progress after cancel

验收必须覆盖：

- Run A 被 Esc/cancel 后进入 `CANCELLED`。
- Run B 同 Session 后续输入能获得 dispatch lane 并产生 terminal。
- Run A 的 late tool result / terminal event 不会追加 canonical tool fact 或覆盖 Run A terminal。

## 8. Implementation Slices

本 work unit 是中型跨 ToolRuntime / dispatch / tools / tests work。按控制文档 Slice 原则，采用 3 个 implementation slices。3 个 slice 的切分依据是语义闭环、依赖顺序、失败/回滚风险和验证矩阵，而不是文件或 owner：

- Slice 1 建立 interrupt capsule 和 Host worker cleanup 闭环，先用 fixture 证明非协作 blocking 执行可被中止，且 late result 被 quarantine。
- Slice 2 把生产 doc / fins / web 工具迁移到该执行边界，处理真实 HTTP/browser/subprocess 风险。
- Slice 3 做 public Esc/cancel smoke、new input progress、docs sync 和完整验证矩阵。

不超过 3 个 slices 的原因：状态机、durable schema、Engine contract 均不重做；核心风险可以在上述三个行为闭环中覆盖。继续按 Host / Engine / tools / tests 拆分会增加 gate 成本，但不会提高验证质量。

### Slice S1: ToolRuntime interrupt capsule and worker cleanup

ID / name：`WU-TOOLS-CANCEL-01-S1 interrupt capsule + local worker cleanup`

Objective：

- 在 ToolRuntime / local worker boundary 增加最小 typed interruptible execution capsule。
- 让 cancel 后默认 local worker stream 能被打断并释放 active handle / lane token。
- 用 non-cooperative blocking fixture 证明 cancel 不等待工具自然结束，late result 不进入 cancelled Run。

Allowed files/modules：

- `dayu/host/tool_runtime.py`
- `dayu/host/local_proxy.py`
- `dayu/host/dispatch.py`
- `dayu/host/api.py` docstring / protocol semantics only if required
- `dayu/runtime/*` only for layer-neutral process / bounded close helper
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_public_cancel_smoke.py` or focused equivalent
- `tests/runtime/test_*` if runtime helper is added

Exact allowed changes：

- Add typed capsule abstraction with cooperative cancel, terminate, kill, close semantics and explicit execution mode enum covering at least `async_direct`, `thread_backed`, and `process_backed`.
- Integrate capsule into `ToolRuntimeExecutor._dispatch_tool_call_with_bounds(...)`; continue deriving deadline from existing `BatchToolExecutionContext.timeout_seconds`.
- Add a process-backed capsule path for test fixture / declared blocking execution.
- Keep default cooperative async callable path for pure async tools and prove behavior does not regress.
- Update default local worker handle so `on_cancel(...)` calls event stream `close()`, cancelling active `anext`, closing the async generator, and letting dispatch consumer reach `finally`.
- Add bounded close behavior for worker stream cleanup using a small internal cleanup grace such as `local_worker_close_grace_seconds = 3.0`; log diagnostic on close timeout and proceed to lane release.
- Preserve ToolRuntime accept barrier and Engine ingest late rejection.

State transitions：

- `RUNNING + cancel_run -> CANCELLING` remains unchanged.
- Active cancel watchdog may close `CANCELLING -> CANCELLED` independent of tool cooperation.
- Worker cleanup after cancel must not append new terminal facts if watchdog already committed terminal.
- Tool result after `CANCELLED` must be rejected by accept / ingest barrier.

Error handling：

- Capsule cooperative cancel returns governed cancelled outcome when still acceptable.
- Capsule timeout returns existing tool runtime timeout governed outcome; no new timeout source.
- `thread_backed` terminate / kill must not report OS-level stop success; it may only report unsupported or adapter-close diagnostic.
- `process_backed` terminate failure escalates to kill after bounded grace.
- kill failure records bounded diagnostic and returns governed failure/cancelled if still in ToolRuntime path; otherwise only logs.
- Runtime helper cleanup failures must not prevent Host durable cancel terminal.

Invariants：

- No public Host cancel API change.
- No durable schema / EventLog event type change.
- No post-cancel time budget.
- No provider-specific code in Host core.
- `tool_execution_timeout_seconds` remains the single tool handshake deadline.
- active worker registry entries and lane tokens are eventually released after cancel-triggered worker interruption.
- `thread_backed` mode is not allowed to satisfy non-cooperative production cancel requirements.

Tests / validation commands：

```bash
source .venv/bin/activate
pytest tests/host/test_toolruntime_executor.py tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_smoke.py -q
pytest tests/runtime/test_interruptible_process.py -q  # if runtime helper file is added
pyright
git diff --check
```

Expected assertions：

- non-cooperative blocking fixture is interrupted without waiting for natural completion.
- process-backed fixture proves terminate and hard kill can stop a non-cooperative blocking worker.
- thread-backed fixture proves cancel does not claim OS thread termination and is not marked production-grade for non-cooperative blocking.
- cooperative async fixture preserves existing success, exception, timeout and cancellation outcome behavior.
- cancel-triggered worker cleanup releases lane and active handle.
- default local worker `on_cancel(...)` calls the stream close path; active `anext` cancellation / generator close is idempotent and `_consume_worker_events(...)` reaches `finally`.
- `CancelledError` from active `anext` is contained or tolerated by the dispatch owner path and does not skip lane release.
- late result after cancelled Run is rejected / not accepted as canonical tool fact.
- terminate path succeeds before kill when worker cooperates.
- hard kill path is exercised when terminate does not exit.

Completion signal：

- Focused Host tests prove cancel -> cleanup -> lane release -> stale quarantine.

Stop condition：

- If implementation requires adding durable Run/Attempt/EventLog state, stop and return to design gate.
- If process-backed capsule cannot safely carry current tool callable shape without public contract change, stop and update this plan/design before migrating tools.
- If S1 direct evidence proves provider declarations are required in `dayu.contracts`, stop and return to design / contract gate before editing shared contracts.

### Slice S2: Production tool/provider migration

ID / name：`WU-TOOLS-CANCEL-01-S2 production tools interrupt adapters`

Objective：

- Migrate current production blocking tool/provider paths to the interrupt boundary from S1.
- Ensure doc / fins / web synchronous I/O, HTTP request / stream, Playwright fallback and subprocess-like work are either interruptible or explicitly fail closed from production cancel path.
- Produce a per-tool-family migration assessment before changing each family, using the matrix in Section 7.4.1.

Allowed files/modules：

- `dayu/tools/doc_tools.py`
- `dayu/fins/tools/fins_tools.py`
- `dayu/tools/web/web_tools.py`
- `dayu/tools/web/web_http_session.py`
- `dayu/tools/web/web_playwright_backend.py`
- narrowly required `dayu/fins/*` helper modules that currently own blocking provider calls
- tool declaration / provider files only if typed execution capability must be declared
- `tests/tools/test_doc_tools_provider.py`
- `tests/fins/test_fins_ingestion_tools.py` and focused Fins tool tests
- `tests/tools/web/test_web_tools_provider.py`

Exact allowed changes：

- For each tool family, record chosen mode and feasibility result in the S2 implementation artifact: direct process-backed, request-abort-capable async direct, cooperative-only / non-production, or design-stop.
- Replace naked `asyncio.to_thread(...)` production blocking boundaries with S1 interruptible execution path, or declare the tool as process-backed blocking execution.
- Thread/process migration must preserve existing business outputs and cancellation outcome shape.
- Web HTTP paths must pass remaining tool deadline into request timeout budget where currently omitted.
- Async HTTP / httpx paths must use `async_direct` semantics or an explicit adapter abort hook; tests must validate response / client cleanup after cancel.
- Playwright fallback should reuse / adapt its existing terminate -> kill behavior behind the typed adapter boundary.
- External WAITING job lifecycle remains untouched except where non-WAITING start path shares helper code.

State transitions：

- Ordinary completed tool call: unchanged `TOOL_RESULT_ACCEPTED` path.
- Tool cancelled before accepted result: returns governed cancelled outcome or is rejected by accept barrier if Run already cancelled.
- Awaiting tools: unchanged accepted wait path from WU-WAIT-03 / WU-TOOLS-01-F01-02-R1.

Error handling：

- Tool business exceptions remain projected to existing failed outcomes.
- Cancellation is projected to existing cancelled outcome/hint text where tool already has one.
- HTTP timeout vs Host cancel must remain distinguishable in tool result error / cancelled metadata.
- Hard-kill diagnostic must not be LLM-facing business fact.

Invariants：

- Fins document storage continues only through `dayu.fins.storage` repositories.
- No provider-specific kill branch in Host core.
- No magic tool-name branch for production behavior; use typed declaration or adapter wiring.
- No `extra payload` for explicit execution fields.
- LLM-facing tool schema text must remain self-explanatory; do not expose internal interrupt ids as business facts.

Tests / validation commands：

```bash
source .venv/bin/activate
pytest tests/tools/test_doc_tools_provider.py -q
pytest tests/fins/test_fins_ingestion_tools.py -q
pytest tests/tools/web/test_web_tools_provider.py -q
pytest tests/host/test_toolruntime_executor.py -q
pyright
git diff --check
```

Expected assertions：

- doc / fins / web blocking business fixtures do not continue to publish accepted results after cancel.
- S2 implementation artifact includes doc / fins / web sync HTTP / async HTTP / Playwright migration assessment and chosen fallback/stop classification.
- web request budget is bounded by tool execution deadline.
- async HTTP / httpx cancellation closes or releases response/client resources.
- Playwright terminate path and hard kill path are both covered.
- cancelled outcome remains compatible with existing tool result projection.

Completion signal：

- Production tool families that currently use `asyncio.to_thread(...)` or Playwright process execution are covered by interrupt boundary tests.

Stop condition：

- If a production tool cannot be made interruptible without changing business storage / download architecture, stop and classify that residual to a dedicated issue before claiming #87 closeout.
- If key production paths cannot be made `process_backed` or request-abort-capable `async_direct` without architecture/public contract change, return to design gate; do not mark issue-87 closeout.

### Slice S3: Public Esc/cancel smoke, stale quarantine, docs sync

ID / name：`WU-TOOLS-CANCEL-01-S3 public interrupt UX and closeout validation`

Objective：

- Validate public Esc/cancel user experience end to end.
- Prove new input progresses after cancelled blocking tool/provider execution.
- Complete README/design docs decision required by AGENTS after implementation.

Allowed files/modules：

- `tests/cli/test_interactive_command.py`
- `tests/host/test_public_cancel_smoke.py`
- `tests/host/test_public_lifecycle_smoke.py`
- `tests/host/public_smoke_support.py`
- `utils/smoke_host_public_multiturn.py` only if public smoke needs fixture wiring
- README files only if their Agent update constraints say implemented behavior belongs there
- `docs/host/design.md` / `docs/engine/design.md` only if implementation introduced a stable design boundary not already covered by current truth

Exact allowed changes：

- Add public or Host-public smoke where Run A uses a non-cooperative blocking fixture, interactive Esc / cancel returns user to input-ready state, and Run B in the same Session advances to terminal.
- Add focused stale late-result test: old tool/provider result after Run cancelled does not create accepted tool fact, final answer, failed terminal overwrite, or memory/evidence pollution.
- Add lane cleanup assertion: cancelled old worker releases active worker handle / lane so next run can dispatch.
- Update README/design only when code has landed and constraints require current implemented behavior documentation.

State transitions：

- Run A: `RUNNING -> CANCELLING -> CANCELLED`.
- Run B after cancel: `QUEUED/STARTING -> RUNNING -> SUCCEEDED` or expected test terminal.
- Late Run A result: rejected diagnostic or no-op; no Run A terminal overwrite.

Error handling：

- Public smoke must avoid private manual resolve or test-only wait id shortcuts.
- If public CLI smoke cannot run in non-TTY CI, use existing key monitor fake at command boundary plus Host public lifecycle smoke for behavior.

Invariants：

- Esc still maps to `CancelMode.GRACEFUL`.
- User-visible command/API surface unchanged.
- No README claims about future remote sandbox unless code implements it.

Tests / validation commands：

```bash
source .venv/bin/activate
pytest tests/cli/test_interactive_command.py tests/host/test_public_cancel_smoke.py tests/host/test_public_lifecycle_smoke.py -q
pytest tests/host/test_toolruntime_executor.py tests/host/test_active_cancel_dispatch.py -q
pytest tests/tools/test_doc_tools_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/web/test_web_tools_provider.py -q
pyright
git diff --check
```

Expected assertions：

- public Esc/cancel smoke or Host-public lifecycle smoke uses a non-cooperative blocking fixture for Run A, then proves Run B advances in the same Session.
- public Esc/cancel smoke returns to input-ready flow and follow-up run advances.
- cancelled Run receives no accepted late tool result.
- active lane / worker cleanup does not block follow-up dispatch.
- docs sync follows README constraints.

Completion signal：

- Public UX smoke plus focused Host/tool tests pass; README/design decision is recorded in implementation closeout.

Stop condition：

- If public smoke shows Host still waits for old worker lane after watchdog terminal, return to S1 cleanup; do not paper over with longer test timeout.

## 9. Implementation Validation Matrix

Required validation after implementation:

```bash
source .venv/bin/activate
pytest tests/host/test_toolruntime_executor.py tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_smoke.py tests/host/test_public_lifecycle_smoke.py -q
pytest tests/cli/test_interactive_command.py -q
pytest tests/tools/test_doc_tools_provider.py -q
pytest tests/fins/test_fins_ingestion_tools.py -q
pytest tests/tools/web/test_web_tools_provider.py -q
pyright
git diff --check
```

If runtime helper is added:

```bash
source .venv/bin/activate
pytest tests/runtime/test_interruptible_process.py -q
```

Expected assertion categories:

- non-cooperative blocking fixture：cancel 不等待自然结束，fixture late result 不进入 Host accepted facts。
- cooperative async regression：现有纯 async tool 在 capsule integration 后 success / exception / timeout / cancel outcome 不变。
- execution mode semantics：`async_direct`、`thread_backed`、`process_backed` 的 terminate / kill 能力按 mode 断言，thread 不承诺 hard interrupt，process 覆盖 terminate 与 kill。
- async HTTP abort：`httpx` / async stream cancel 后 response/client cleanup 可验证。
- public Esc/cancel smoke：Esc 触发 cancel，用户可继续输入，新 Run 可推进。
- public non-cooperative smoke：Run A 使用非协作 blocking fixture 被取消，Run B 在同一 Session 推进到 terminal。
- late result quarantine：cancelled Run 不被旧 tool result / Engine terminal 污染。
- subprocess/process termination：至少覆盖 graceful terminate 和 hard kill 两级。
- lane / active worker cleanup：cancel 后 release lane token，follow-up dispatch 不被旧 worker 卡住。
- type safety：`pyright` 无新增或扩散错误。
- formatting：`git diff --check` 通过。

## 10. Docs Decision

本 plan gate 不修改 README、design docs 或 control doc。

Implementation gate 后按实际改动判断：

- 修改 `dayu/host/`：必须先读 `dayu/host/README.md` 的 Agent 更新约束；若实现改变 ToolRuntime / local worker cancel 的稳定开发语义，应更新。
- 修改 `dayu/engine/` 或 Engine public contract：必须检查 `dayu/engine/README.md`，并且先同步 `docs/engine/design.md`。当前 plan 默认不修改 Engine。
- 修改 `dayu/fins/` 工具 cancellation 行为：必须检查 `dayu/fins/README.md` 是否需要记录当前已实现的 Fins package 开发边界。
- 修改 `tests/`：检查 `tests/README.md`，只有测试入口职责变化才更新。
- 用户可见 CLI / workflow 文案变化：检查根 `README.md`。当前 plan 不要求命令或 API 变化。
- 分层边界变化：检查 `dayu/README.md`。当前 plan 保持既有边界，通常无需更新。

若 implementation 发现需要新增 public contract 或改变 Host/Engine design truth，必须先停下更新设计真源，再继续实现；不能只在 README 中记录架构变更。

## 11. Risks / Open Questions

所有 residual risk 必须有 owner / destination：

- Risk R1：部分现有 tool callable 或 provider closure 可能不可 picklable，无法直接进入 process-backed capsule。
  - Owner / destination：S1/S2 implementation。先按 Section 7.4.1 重构为模块级 process entrypoint 或改为 request-abort-capable `async_direct` adapter；若关键生产路径仍无法满足且需要 public contract / 架构变更，返回 design gate，不允许把不可抢占路径标为 production-grade 或关闭 #87。
- Risk R2：`asyncio.to_thread(...)` 取消后底层线程可能继续运行并产生外部副作用。
  - Owner / destination：S2 implementation。生产 blocking I/O 必须迁移到 process-backed 或 request-abort-capable adapter；保留纯 thread path 只能用于明确 cooperative / read-only 且可接受 late side effect 的工具，并需测试说明。
- Risk R3：关闭 worker stream 释放 lane 与接受 cooperative `run_cancelled` 之间可能存在 race。
  - Owner / destination：S1 tests。以 Host terminal first-committer-wins 和 late rejection 为 correctness，不依赖事件顺序。
- Risk R4：hard kill diagnostic 如果进入 LLM-facing tool result，可能被误解为业务事实。
  - Owner / destination：S1/S2 implementation。diagnostic 必须作为 bounded runtime/tool trace diagnostic，不伪装成财报事实。
- Risk R5：public smoke 在非 TTY CI 中无法真实按 Esc。
  - Owner / destination：S3 tests。用现有 key monitor fake 覆盖 CLI command boundary，并用 Host public lifecycle smoke 覆盖真实 cancel/new input progression。

Open questions：无 blocking open question。若实现中出现需要 durable schema、Engine public contract 或 issue scope 扩张的证据，即刻停止并回到 design / issue discussion。

## 12. Completion Report Format

Implementation / review closeout 必须按以下格式报告：

```text
artifact path:
plan verdict:
what changed:
direct evidence used:
slice completed:
validation run:
docs decision:
open questions / residual risks:
```

本 plan gate 的 completion report 格式：

```text
artifact path: docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md
plan verdict: ready | blocked
direct evidence summary:
slice count and rationale:
validation run:
open questions / residual risks:
```

## 13. Why This Is Not Over-designed

本方案没有把局部取消问题扩大成新平台：

- 不重写 Host cancel 状态机，不新增 durable schema，不新增 EventLog 语义。
- 不改变 Engine tool loop 职责，仍让 Engine 只观察 token 和等待 `ToolExecutor.execute`。
- 不引入第二套 cancel timeout；所有 deadline 继续来自 `tool_execution_timeout_seconds`。
- 不在 Host core 写 web / Playwright / provider 私有 kill 分支，只定义通用 interrupt boundary。
- Slice 数保持 3 个，每个都是可验证行为闭环：runtime boundary、生产工具迁移、public UX closeout。
- 已有 Playwright terminate / kill 作为模式证据，已有 Host accept / ingest stale barriers 作为 correctness 基础；本 work unit 只补缺少的 execution ownership 和 cleanup。
