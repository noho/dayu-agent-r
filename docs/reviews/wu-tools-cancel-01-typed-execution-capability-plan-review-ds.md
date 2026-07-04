# WU-TOOLS-CANCEL-01 Typed Execution Capability Plan Review — AgentDS

## Artifact

- **Reviewer**: AgentDS (adversarial plan review)
- **Plan under review**: `docs/host/wu-tools-cancel-01-typed-execution-capability-plan.md`
- **Background artifacts**:
  - `docs/reviews/wu-tools-cancel-01-slice2-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-cancel-01-slice2-code-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-slice2-code-review-ds.md`
  - `docs/reviews/wu-tools-cancel-01-slice2-implementation-codex.md`
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`, `docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md`
- **Current baseline**: commit `29003541`，工作区只有 plan 文档新增。

## Review Scope

按给定的 7 个 review 维度对 plan 做 adversarial review。每条 finding 包含直接证据（文件:行号引用）、影响分析与建议改法。Findings 按严重度排序，最后给出综合 verdict。

---

## Findings

### F01 — 严重 — `ProcessBackedToolTarget` 返回 `ToolExecutionOutcome` 允许 `ToolAwaitingOutcome`，与 process-backed 语义冲突

- **Plan 章节**: Contract / API Shape 草案 → `ProcessBackedToolTarget` Protocol
- **直接证据**:
  - Plan 第 86-91 行：`ProcessBackedToolTarget.__call__() -> ToolExecutionOutcome`
  - `dayu/contracts/tool_outcome.py:137-141`：`ToolExecutionOutcome` 联合包含 `ToolAwaitingOutcome`
  - `docs/engine/design.md` Section 12：`ToolAwaitingOutcome` 语义是"工具进入长事务等待"，Engine 收到后产出 `run_suspended` 并结束本次 run；子进程不可能表达"我进入等待，请宿主稍后恢复我"
  - `docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md` Section 7.4: `process_backed` 语义是"非协作 blocking I/O 可隔离子进程执行"，子进程应返回 completed / failed，或被父进程 kill
- **分析**: 如果 process target 返回 `ToolAwaitingOutcome`，父进程 `ProcessBackedToolExecutionCapsule.run()` 必须处理这个无意义的结果。要么在 capsule 层 reject 为 failed，要么靠类型系统阻止。当前 plan 的 `-> ToolExecutionOutcome` 签名在类型层面允许了所有四种 outcome，没有给出子进程合法返回值的约束。
- **影响**: 实现者可能错误地在 process target 内返回 awaiting outcome，导致运行时错误或静默丢失等待语义。ToolRuntime 已在 await 路径上有 `wait_adapter_registry` / `wait_activation_registry` 治理；process target 不应绕过这套机制。
- **建议改法**:
  1. 定义 `ProcessBackedToolResult = ToolCompletedOutcome | ToolFailedOutcome` 作为 process target 的合法返回联合。
  2. 在 `ProcessBackedToolTarget` docstring 中明确禁止返回 `ToolAwaitingOutcome` 和 `ToolCancelledOutcome`（取消由父进程 govern）。
  3. 或保持 `-> ToolExecutionOutcome` 但在 `ProcessBackedToolExecutionCapsule.run()` 中对非 completed/failed outcome 做 fail-closed 投影，并记录 diagnostic。

### F02 — 严重 — Process target factory 接收完整 `BatchToolExecutionContext` 但无类型级 guard 防止捕获不可序列化字段

- **Plan 章节**: Contract / API Shape 草案 → `ProcessBackedToolTargetFactory.build_process_target`
- **直接证据**:
  - Plan 第 97-109 行：`build_process_target(call, context: BatchToolExecutionContext) -> ProcessBackedToolTarget`
  - `dayu/contracts/tool_call.py`：`BatchToolExecutionContext` 包含 `cancellation_token: CancellationToken`，该 token 不可 pickle
  - Plan 第 107 行 docstring 说"实现只能读取可序列化字段"，但这是文档约束，不是类型约束
  - S1 已有 `InterruptibleProcessTarget` Protocol（`dayu/runtime/interruptible_process.py:22-35`），其 `__call__() -> JsonValue` 不接收 context
- **分析**: factory 实现者可能在 `build_process_target` 内读取 `context.cancellation_token` 并闭包捕获到 `ProcessBackedToolTarget` 中。此时 multiprocessing spawn pickling 会在运行时失败，而不是在类型检查时被拦截。plan 的 docstring 提示是正确的但不足以防止此类错误。
- **影响**: 运行时 pickle 失败会导致工具执行 crash，且错误信息（`TypeError: can't pickle ...`）对调试不友好。
- **建议改法**:
  1. 定义专用的 `ProcessBackedToolContext` dataclass，只包含可序列化字段（`session_id: str`, `run_id: str`, `iteration_id: str`, `timeout_seconds: float | None`, `correlation_id: str`），明确排除 `cancellation_token`
  2. factory 签名改为 `build_process_target(call: ToolCallRequest, context: ProcessBackedToolContext) -> ProcessBackedToolTarget`
  3. 在 Host ToolRuntime 中从 `BatchToolExecutionContext` 投影到 `ProcessBackedToolContext` 后再调用 factory
  4. 或者在 `ProcessBackedToolTargetFactory` docstring 中列出禁止读取的字段清单（至少 `cancellation_token`），并在 S2A 测试中增加 pickle round-trip 验证

### F03 — 严重 — `ProcessBackedToolTarget` 返回值类型与 S1 `InterruptibleProcessHandle` 的 `JsonValue` 契约不一致，plan 未给出精确迁移路径

- **Plan 章节**: Contract / API Shape 草案；Process-backed Entrypoint 形状
- **直接证据**:
  - Plan 第 86-91 行：`ProcessBackedToolTarget.__call__() -> ToolExecutionOutcome`
  - `dayu/runtime/interruptible_process.py:22-35`：`InterruptibleProcessTarget.__call__() -> JsonValue`
  - `dayu/host/tool_runtime.py:1615-1620`：`ProcessBackedToolExecutionCapsule.__init__(target: InterruptibleProcessTarget)` — S1 capsule 接收的是 runtime 层的 `InterruptibleProcessTarget`，不是 contracts 层的 `ProcessBackedToolTarget`
  - Plan 第 56 行提到"允许扩展 `dayu.runtime.interruptible_process` 的返回联合到 `JsonValue | ToolExecutionOutcome`"，但 `InterruptibleProcessCompleted.value` 的类型是 `JsonValue`（`interruptible_process.py:46`），改变这个类型会影响所有现有 consumer
- **分析**: 这里有三种可能的实现路径，plan 没有明确选择：
  - (A) 在 contracts 层定义 `ProcessBackedToolTarget`，Host capsule 接收它，内部适配为 `InterruptibleProcessHandle` 可接受的 target
  - (B) 修改 `InterruptibleProcessTarget` 和 `InterruptibleProcessCompleted` 支持 `ToolExecutionOutcome`
  - (C) 让 `ProcessBackedToolTarget` 返回 `JsonValue`，由 capsule 负责映射为 `ToolExecutionOutcome`

  方案 (B) 会把 `ToolExecutionOutcome` 类型泄漏到 `dayu.runtime.interruptible_process`，虽然 runtime 可以 import contracts，但这会让层中立的 process helper 携带工具语义。方案 (C) 保留了 runtime 的层中立性但放弃了子进程直接返回 failed/cancelled outcome 的能力。方案 (A) 是折中但 plan 没有给出 adapter 设计。
- **影响**: 实现者在 S2A 会面临未预期的设计决策，可能被迫在实现中做 ad-hoc 选择，增加返工风险。
- **建议改法**:
  1. 在 plan 中明确选择方案并给出 adapter/映射逻辑。
  2. 推荐方案 (C)：`ProcessBackedToolTarget.__call__() -> JsonValue`，让 `ProcessBackedToolExecutionCapsule.run()` 负责把 `JsonValue` 包装为 `ToolCompletedOutcome`，把子进程异常映射为 `ToolFailedOutcome`。这与 S1 capsule 的当前行为一致（`tool_runtime.py:1648-1667`），且不需要修改 `dayu.runtime.interruptible_process`。
  3. 如果确实需要子进程返回 failed outcome（带结构化 error/message/hint），可以定义专用的 `ProcessBackedToolResult` JSON 信封，在 capsule 中解析。但不应把完整的 `ToolExecutionOutcome` 联合类型压入 runtime 层。

### F04 — 中 — S2A slice 范围过大：contract + runtime + Host + test 四层联动，单 slice 实现/审查风险高

- **Plan 章节**: S2 Resume Slices → S2A: contract + factory wiring
- **直接证据**:
  - Plan 第 271-277 行：S2A 覆盖 `dayu/contracts/tool_execution.py`（新增）、`tool_declaration.py`（修改）、`tools_discovery.py`（修改）、`tool_runtime.py`（修改）、`dispatch.py`（修改），五类测试文件
  - Plan 第 227-231 行："不允许修改 Host cancel public API / Engine public contract / durable schema"
  - Plan 第 268 行：plan 自身承认"虽然超过小型 cleanup 默认上限 3"
- **分析**: S2A 是基础设施层变更，一旦出错会影响所有后续 slice。当前 S2A 范围同时包含 contract 定义、ToolDefinition 扩展、digest 更新、capsule factory 新建、dispatch wiring，横跨 contracts → runtime → Host 三层。在单 slice 中完成这些变更意味着：
  - 实现 report 需要覆盖 ~5 个文件的实质性变更
  - review 需要同时验证 contract 正确性、digest 稳定性、factory wiring 正确性、Engine 隔离性
  - 如果 S2A 有问题被 review 打回，S2B/C/D 都无法开始
- **影响**: 实现和 review 周期变长，一旦有 blocking finding，整个 S2 都阻塞。
- **建议改法**:
  1. 将 S2A 拆为 S2A1（contract + ToolDefinition + decorator + digest）和 S2A2（Host factory wiring + dispatch + integration tests）。S2A1 只涉及 contracts/runtime 层，可以独立 review；S2A2 依赖 S2A1 但可以做 focused Host 层 review。
  2. 如果坚持单 slice，至少在 plan 中明确 S2A 的 fail-fast 策略：如果 contract shape 在 review 中需要修改，哪些后续工作可以并行推进（如 Doc/Fins process target 的纯业务逻辑重构）。

### F05 — 中 — Provider lock 语义在 process-backed 模式下未定义

- **Plan 章节**: Process-backed Entrypoint 形状 → Doc；Fins read
- **直接证据**:
  - `dayu/tools/doc_tools.py:729`：`async with provider_lock:` 包裹 `asyncio.to_thread(business_call, token)`
  - `dayu/fins/tools/fins_tools.py:773`：`async with provider_lock:` 包裹 `asyncio.to_thread(business_call, cancellation_token)`
  - Plan 第 243-248 行（Doc process target）和第 251-256 行（Fins process target）：均未提及 provider lock
  - Plan 第 198-200 行（Doc slice）和第 205-208 行（Fins slice）：修改范围包含 `doc_tools.py` 和 `fins_tools.py` 但不包含 provider lock 相关变更
- **分析**: 当前 `_invoke_doc_business` / `_invoke_fins_read_business` 在 provider lock 内执行 `asyncio.to_thread(...)` 。process-backed 迁移有两种可能：
  - (a) 保持 provider lock 但 lock 在父进程 asyncio 层，子进程执行期间 lock 一直被持有。这意味着 process-backed 模式下 provider 级串行化变得更重（lock 持有时间 = 子进程完整生命周期），可能比当前 `asyncio.to_thread` 的并发性更差
  - (b) 移除 provider lock，信任子进程隔离。但 provider lock 的原始目的可能是保护共享资源（如全局 requests session、processor 状态）

  plan 没有讨论这个取舍，也没有在 Doc/Fins slice 的"修改范围"中列入 provider lock 相关变更。
- **影响**: 实现时可能默认保留 provider lock → process-backed 的并发性退化。或者移除 lock 但引入未预期的资源竞争。
- **建议改法**:
  1. 在 plan 中明确：process-backed 工具是否绕过 provider lock。如果绕过，需要在子进程内自行保证资源隔离。
  2. 如果要绕过，在 Doc/Fins slice 的"Exact allowed changes" 中列出 provider lock 相关变更。
  3. 推荐方案：process-backed 路径绕过 provider lock；子进程内各自创建独立的 processor / runtime / session；provider lock 文档说明仅对 async_direct 同进程路径生效。

### F06 — 中 — `thread_backed` capability 保留但仅靠 review 防止生产误用，类型系统不提供 guard

- **Plan 章节**: Contract / API Shape 草案 → `ThreadBackedToolExecutionCapability`; Host ToolRuntime 变更草案; Residual Risks
- **直接证据**:
  - Plan 第 124-128 行：`ThreadBackedToolExecutionCapability` 存在且为空 dataclass（无字段约束其使用范围）
  - Plan 第 160 行："`thread_backed`：只允许用于明确 cooperative / non-production 或测试路径；生产关键路径的 review 必须拒绝它作为 #87 closeout 证据"
  - Plan 第 343 行（Residual Risks）："plan review 和 code review 必须把 thread_backed 不满足非协作 blocking cancel 列为强检查项"
  - `docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md` Section 7.1：thread_backed "不满足非协作 blocking 生产级取消"
- **分析**: `ThreadBackedToolExecutionCapability` 是一个空 dataclass — 它不携带任何字段（如 `production_allowed: bool = False` 或 `require_review_waiver: bool = True`）来在类型或运行时层面表达"此模式不满足生产 closeout"。当前设计把防御完全放在 code review 流程上，而类型系统、测试断言、CI 检查均不参与。这与 plan 自身的编码硬约束"显式参数必须有 typed field"不一致。
- **影响**: 未来开发者可能给生产工具标记 `thread_backed` 并声称"已经声明了 execution capability"。code review 可能漏掉（尤其是非本 WU 上下文的修改）。一旦 thread_backed 进入生产路径，cancel 仍是 cooperative-only。
- **建议改法**:
  1. 给 `ThreadBackedToolExecutionCapability` 增加一个不可覆盖的 flag，例如 `production_safe_non_cooperative_cancel: bool = False`（frozen，永远 False），让类型系统参与防御
  2. 或者在 `ToolDefinition.execution` 的 post_init 校验中，如果 capability 是 thread_backed 且工具名在生产工具集合中，发出 warning（但不阻止构造，因为测试需要用）
  3. 至少在 plan 的 Stop Conditions 中增加一条："生产工具声明为 thread_backed 且试图标记 #87 closeout 时，停止"

### F07 — 中 — 直接构造 `ToolDefinition` 的站点未完全枚举

- **Plan 章节**: 精确修改范围 → Contract + factory wiring slice; S2B/S2C/S2D
- **直接证据**:
  - `dayu/contracts/tool_declaration.py:217`：`_ToolDecorator.__call__` 构造 `ToolDefinition(...)` — plan 已覆盖（decorator 增加 `execution` 参数）
  - `dayu/tools/doc_tools.py:1696`：`_make_doc_tool_definition(...)` 直接构造 `ToolDefinition(...)` — plan Doc slice 覆盖
  - `dayu/fins/tools/download_tools.py:158`：直接构造 — plan 未列入修改范围
  - `dayu/fins/tools/upload_tools.py:146`：直接构造 — plan 未列入修改范围
  - `dayu/fins/tools/preprocess_tools.py:157`：直接构造 — plan 未列入修改范围
  - `dayu/host/tool_runtime.py:5808`：framework `fetch_more` 工具直接构造 `ToolDefinition(...)` — plan S2A 覆盖 Host tool_runtime
- **分析**: plan 的 Doc/Fins/Web slice 列出了 `doc_tools.py`、`fins_tools.py`、`web_tools.py`，但没有列出 `download_tools.py`、`upload_tools.py`、`preprocess_tools.py`。虽然这些是 download/upload/preprocess 工具（非 read 路径），但它们也直接构造 `ToolDefinition`。当 `ToolDefinition` 新增必填字段 `execution` 后，这些站点会直接 **类型错误**。
- **影响**: 如果 `execution` 字段有默认值，这些站点可以编译通过但语义不正确（默认 async_direct 对 download/upload/preprocess 可能不合适）。如果没有默认值，这些站点会直接 break。
- **建议改法**:
  1. 扫描所有 `ToolDefinition(` 直接构造站点并列入修改范围
  2. Plan 已说明 `execution` 默认 `None` → helper 默认成 `AsyncDirectToolExecutionCapability`，这对 download/upload/preprocess 工具可能是正确的（它们使用 awaiting 语义，不走 blocking I/O），但需要显式确认
  3. 在 plan 的精确修改范围中增加 `dayu/fins/tools/download_tools.py`、`upload_tools.py`、`preprocess_tools.py`

### F08 — 中 — Fins process target 子进程内重建 `DefaultFinsRuntime` 的可行性未充分验证

- **Plan 章节**: Process-backed Entrypoint 形状 → Fins read
- **直接证据**:
  - Plan 第 253 行："子进程：调用 `DefaultFinsRuntime.create(workspace_root=Path(...))`"
  - `dayu/fins/tools/fins_tools.py` 和 `dayu/fins/tools/read_runtime.py`：当前 Fins read runtime 的构造路径
  - Plan 第 255 行："仓储边界：禁止把 repository / runtime 实例跨进程传递；禁止绕过 `dayu.fins.storage` 直接读财报文件"
  - Plan 第 257 行测试边界："九个 read tools 至少覆盖一条 fast path、一条 processor path、一条 XBRL / table path"
- **分析**: `DefaultFinsRuntime.create(workspace_root=Path(...))` 是否可以在子进程中无副作用地调用？需要考虑：
  - `DefaultFinsRuntime.create` 是否会尝试读取父进程的全局状态、环境变量、或配置文件？
  - Fins storage 仓储实现（如 SQLite/文件系统）是否支持多进程并发只读访问？
  - workspace 下的索引/缓存文件是否会被子进程的读取操作意外修改？

  plan 只说了"可以"，但没有给出可行性证据（如"当前 Fins storage 已支持 multi-process read" 或 "已验证 `DefaultFinsRuntime.create` 不依赖进程级单例"）。
- **影响**: 如果 S2C 实现时发现 `DefaultFinsRuntime.create` 不能在子进程安全调用，需要额外重构 Fins runtime 或 storage，超出当前 plan 范围。
- **建议改法**:
  1. 在 S2C 前增加一个 pre-check：验证 `DefaultFinsRuntime.create(workspace_root)` 在子进程中可成功创建并执行只读查询
  2. 在 plan 的 Residual Risks 中记录：如果 Fins storage 不支持多进程并发读，process-backed Fins read 可能需要文件锁或退化为 async_direct
  3. 在 Fins slice 的 stop condition 中增加："如果 `DefaultFinsRuntime.create` 在子进程中失败且无法在不改变 storage 架构的前提下修复，停止"

### F09 — 低 — `_tool_definition_json_value` digest 新增 capability 字段的具体 JSON shape 未定义

- **Plan 章节**: Contract / API Shape 草案 → ToolBundle digest
- **直接证据**:
  - Plan 第 153 行："`ToolBundle` digest 需要包含稳定 capability mode 和 `request_abort_capable`；不得 hash callable 或 process target factory 对象"
  - `dayu/runtime/tools_discovery.py:440-455`：`_tool_definition_json_value` 当前覆盖 `name`, `schema`, `truncate`, `tags`, `display`，不含 execution 字段
  - Plan 没有给出 digest 中 execution 字段的 JSON shape 示例
- **分析**: 对于三种 capability 类型，digest 应有不同的投影：
  - `async_direct`: `{"mode": "async_direct", "request_abort_capable": true/false}`
  - `thread_backed`: `{"mode": "thread_backed"}`
  - `process_backed`: `{"mode": "process_backed"}` （不包含 factory 身份）

  但 plan 没有明确这个 shape，实现者可能做出不同选择（如把 mode 放在顶层字段 vs 嵌套在 execution 对象中），导致后续 digest 不稳定。
- **影响**: 低。实现时只要不 hash callable/factory，具体 shape 可以在 code review 中统一。但 plan 如果不指定 shape，可能造成实现与 review 之间的往返。
- **建议改法**: 在 plan 的 Contract / API Shape 草案中增加 digest JSON shape 示例。

### F10 — 低 — Web `async_direct` 替代路径的 `request_abort_capable` 验证标准不够具体

- **Plan 章节**: Process-backed Entrypoint 形状 → Web sync
- **直接证据**:
  - Plan 第 263 行："request-abort-capable async_direct 替代路径：如果某 Web path 改为 async HTTP adapter，必须测试取消时 response / client / stream 被关闭"
  - Plan 第 292 行（S2D）："Web search / fetch 同步 requests 路径迁移到 process-backed，或改成有关闭验证的 async direct adapter"
  - Plan 第 341 行（Residual Risks）："Web async_direct 改造若被选中，必须证明 response / client / stream close"
- **分析**: "测试取消时 response / client / stream 被关闭" 是正确的方向，但 plan 没有给出什么是"可接受的关闭验证"的标准。例如：
  - 是否需要检查 socket fd 已关闭？
  - 是否需要检查 httpx client 的 connection pool 已释放？
  - 是否需要 mock 或 wiretap 来验证没有泄漏？

  没有标准可能导致 S2D 实现和 review 之间对"已验证"的理解不一致。
- **影响**: 低。S2D 是最后一个业务 slice，有一些时间在实现中细化标准。但 plan 至少应给出验证方向。
- **建议改法**: 在 S2D 或 aggregate validation slice 中增加一个具体验证点，例如"取消后 httpx.AsyncClient.aclose() 被调用且无未关闭的 TCP 连接"。

### F11 — 低 — Plan 声称 `dayu.runtime` "允许扩展" 返回值联合，但未区分 "允许" 与 "推荐"

- **Plan 章节**: 方案选择 → `dayu.runtime` 取舍
- **直接证据**:
  - Plan 第 56 行："若 process target 需要返回 `ToolExecutionOutcome` 而不是裸 `JsonValue`，允许扩展 `dayu.runtime.interruptible_process` 的返回联合到 `JsonValue | ToolExecutionOutcome`，因为 runtime 依赖 `dayu.contracts` 是允许的"
  - Plan 第 54-55 行列举了 runtime **可放**和**不应放**的内容
  - `dayu/runtime/__init__.py:12-14`：架构硬约束 "dayu.runtime.* 不得 import dayu.engine / dayu.host / dayu.service / dayu.ui / dayu.fins"
- **分析**: 架构上 runtime 可以 import contracts，但 `interruptible_process` 的定位是"层中立 runtime primitive"。把 `ToolExecutionOutcome` 放进去会让它携带工具执行语义，不再是纯 runtime primitive。Plan 说的是"允许"而不是"推荐"，且没有给出这种扩展的取舍分析。
- **影响**: 如果实现者直接修改 `InterruptibleProcessCompleted.value: JsonValue` → `JsonValue | ToolExecutionOutcome`，日后其他非工具场景的 interruptible process 消费者也需要理解 `ToolExecutionOutcome` 分支。
- **建议改法**: 在 plan 中明确推荐方案：保持 `interruptible_process` 返回 `JsonValue`（层中立）；在 Host capsule 层做 `JsonValue → ToolExecutionOutcome` 映射（见 F03 建议）。

---

## 逐维度 Review 结论

### 1. `ToolDefinition.execution` 放在 `dayu.contracts` 是否是最小正确契约？

**结论：方向正确，但 ProcessBackedToolTarget/Factory Protocol 包含未解决的设计张力（F01, F02, F03）。**

- 正确的部分：execution capability 必须在 contracts 层，因为 tool provider → ToolsDiscovery → Host ToolRuntime 三者都需要消费它，而 contracts 是唯一共享依赖。
- 有问题的部分：`ProcessBackedToolTarget` 和 `ProcessBackedToolTargetFactory` 这两个 Protocol 的签名与现有 S1 `InterruptibleProcessHandle` 的契约存在类型不匹配（F03），且缺少对不可序列化字段的类型级 guard（F02）。
- 合约膨胀评估：新增一个 `tool_execution.py` 模块、一个 enum、两个 Protocol、三个 dataclass — 这是合理的增量。但如果按 F03 建议让 process target 返回 `JsonValue`，可以进一步缩小 contracts 新增类型的范围。

### 2. 分层边界是否清楚？

**结论：大体清楚，但 Fins storage 重建和 provider lock 语义有两处模糊。**

- Contracts / runtime / Host / tools / Fins / Engine 边界在 plan 中有明确声明。
- `dayu.runtime.interruptible_process` 的返回类型扩展存在层中立性退化风险（F03, F11）。
- Doc/Fins/WEB 工具层 process entrypoint 的重建路径在 Doc 和 Web 上较具体，在 Fins 上依赖未验证的 `DefaultFinsRuntime.create` 可行性（F08）。
- Engine 边界保持正确：plan 明确 Engine 不消费 capability，`ToolSchema` 不含 capability。

### 3. ProcessBackedToolTarget/Factory 草案是否自洽？

**结论：类型、pickling、context 使用、Outcome 返回存在三处不自洽（F01, F02, F03）。**

详见 F01-F03。总结：
- 类型不自洽：`-> ToolExecutionOutcome` 允许 `ToolAwaitingOutcome`（F01）
- Pickling / context 不自洽：`BatchToolExecutionContext` 包含不可序列化的 `cancellation_token`（F02）
- Outcome 返回不自洽：与 S1 `InterruptibleProcessHandle` 的 `JsonValue` 契约不一致（F03）
- Deadline/cancel 语义：plan 对父进程 govern 的描述是正确的（"父进程 cancel / timeout 后 terminate / kill process"），但子进程 cooperative cancel 返回 `ToolCancelledOutcome` 与父进程 kill 的 race 未讨论

### 4. ToolBundle digest / ToolsDiscovery / direct ToolDefinition construction 是否有遗漏？

**结论：digest shape 未指定（F09），直接构造站点未完全枚举（F07）。**

- Digest 变更方向正确（只 hash mode + request_abort_capable，不 hash callable/factory），但 JSON shape 不明确。
- `tool()` decorator 的变更是完整的（增加 `execution` 参数）。
- 直接构造 `ToolDefinition(...)` 的站点有 6 处，plan 只覆盖了其中 4 处（遗漏 download_tools.py、upload_tools.py、preprocess_tools.py）。
- `ToolsDiscovery._tool_definitions_digest` 和 `_tool_definition_json_value` 需要更新，plan 已提及但未给出 shape。

### 5. Doc/Fins/Web process-backed slices 是否足够具体、可测试，是否保留 Fins storage 边界？

**结论：Doc 和 Web 足够具体；Fins 有一个可行性未验证项（F08）；storage 边界明确保留；provider lock 语义缺失（F05）。**

- Doc slice：input shape 具体（`DocProcessToolRequest`），测试边界覆盖 path containment、processor 重建、cancel 后 late result rejection。
- Fins slice：storage 边界正确保留（"禁止绕过 `dayu.fins.storage`"），但 `DefaultFinsRuntime.create` 的子进程可行性未验证。
- Web slice：两种策略都有测试约束，Playwright 路径已有 S2 partial 基础。
- 共性问题：所有三个 slice 都未讨论 provider lock 的处理（F05）。

### 6. Implementation sequencing 风险

**结论：S2A 范围过大是主要风险（F04）；thread_backed 误用是次要风险（F06）。**

- S2A 同时改 contracts + runtime + Host + tests，单 slice 实现/review 风险高。
- S2B-S2D 可以并行（互不依赖），但都依赖 S2A 完成。S2A 的合入速度是关键路径瓶颈。
- `async_direct` 默认确保向后兼容，方向正确。
- `thread_backed` 仅靠 review 防御，类型系统不参与（F06）。

### 7. Tests / README / design 验证矩阵是否足够？

**结论：基本足够，但 process target pickle 验证和 Fins 子进程可行性验证缺失。**

- 每 slice 的测试文件、pyright、README 检查项已列出。
- 缺失：S2A 应该有 `ProcessBackedToolTarget` 的 pickle round-trip 测试（确保 factory 产出的 target 可序列化）。
- 缺失：S2C 应该有 `DefaultFinsRuntime.create` 的子进程可行性验证（可以是 smoke 级别的脚本验证，不必是 CI 测试）。
- README 触发规则是按 CLAUDE.md 约束列出的，方向正确但未逐项确认目标 README 的 `Agent更新约束` 章节是否仍准确。

---

## Verdict

**NEEDS_PLAN_FIX**

Plan 的核心方向（在 `dayu.contracts` 增加 typed execution capability、Host 从 `ToolDefinition.execution` 选择 capsule、Engine 不消费 capability）是正确的，且所有三点均被 S2 review 的直接证据充分支持。

但 plan 在 process-backed 的类型契约设计上有三处不自洽（F01, F02, F03），不修复会导致 S2A 实现中遇到未预期的设计决策，增加返工风险。此外，S2A slice 范围过大（F04）、直接构造站点未完全枚举（F07）、Fins 子进程可行性未验证（F08）是阻塞级以下但需要在 plan 中回应的遗漏。

**建议修复优先级**：

1. **必须在 plan accept 前修复**：F01（`ToolExecutionOutcome` vs 合法 process outcome）、F02（`BatchToolExecutionContext` 的可序列化 guard）、F03（`ProcessBackedToolTarget` 与 `InterruptibleProcessHandle` 的类型对齐）。这三条决定了 S2A 的 contract shape 是否正确。
2. **建议在 plan accept 前修复**：F04（S2A 拆分或明确 fail-fast 策略）、F07（补全直接构造站点）。
3. **可在 S2 实现中验证后修复**：F05（provider lock）、F06（thread_backed guard）、F08（Fins 可行性）、F09（digest shape）、F10（Web 验证标准）、F11（runtime 扩展策略）。

修复后 plan 可以 `PASS`，不需要 `REDESIGN`。
