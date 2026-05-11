# Host P8.5 Handoff Plan：P8 Stabilization / ToolRuntime Event Model

## 0. Gate / Reset State

- 当前 gate：`plan`。
- Work unit：P8.5 — P8 Stabilization / ToolRuntime Event Model。
- 当前分支：`migration/host-p8-5-stabilization`。
- 当前 baseline：`f81197e docs: clarify host tool runtime boundaries`。
- 旧 accepted plan 与旧 Slice 1 implementation 已由 controller 判定失败；本文件完整 supersede 旧
  `docs/host/phase8.5-plan.md` 裁决。
- 设计优先级：`docs/host/design.md` §11 与本 plan 是 P8.5 当前实现真源；若旧 P2/P7/P8 文字仍把
  truncate / cursor / `fetch_more` 描述为专属 RunEvent fact、专属 projection 分支或 EventLog
  credential-scrub 对象，一律视为历史 current-code evidence，已被 §11 与本 plan supersede。
- planning agent 只维护本文件；不改生产代码、不改测试代码、不 commit、不 push、不进入 implementation。
- 后续 worker prompt 必须使用 Gateflow-governed handoff 口径：worker 不是 controller，不得启动
  `$gateflow` / `/gateflow`，不得重排 gate。

## 1. Goal / Motivation / Success Signal

### Goal

P8.5 在 P9 Session / Run Lifecycle Governance / Public Interface 前，收口 P8 已落地的 attempt
lease / recovery / multiprocessing、durable memory、tool trace 与 ToolRuntime 稳定性尾巴。

核心目标升级为：把 ToolRuntime / EventLog 修正为 **generic tool-calling-only EventLog**，并把
truncate / cursor / `fetch_more` 收回 Host 私有 tool runtime 组件边界：

- EventLog 只记录普通 tool calling：`TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED`。
- `truncate` 只是 Host 私有 `RuntimeTruncateManager` 改写普通 tool result 返回给 LLM 的数据。
- `fetch_more` 只是普通 tool name；它是 Host 私有 framework built-in tool，但 Engine 什么都看不到。
- cursor 是 truncate / `fetch_more` 的内部实现细节，只能作为普通 tool call 参数或普通 tool result
  payload 短期参与 LLM roundtrip。Dayu 是本地 Agent，EventLog / trace 只做窄 credential scrub；除
  `API_KEY` / 明确凭证外，不因字段名是 cursor、`scope_token`、tool args 或 tool result 而删除或遮蔽。

### Motivation

动机成立，而且旧 Slice 1 的失败不是单纯“删错 export”，而是 root cause 判断不够彻底。当前代码仍把
truncate / cursor / `fetch_more` 提升成 EventLog 特殊事实、public Host contract、serializer 分支、
memory projection 分支和 trace projection 分支。这与新版 `docs/host/design.md` 的边界冲突：

- `docs/host/design.md:1089-1103`：ToolRuntime 负责普通 tool dispatch；截断状态机和 cursor store
  属于 Host 私有 `RuntimeTruncateManager`。
- `docs/host/design.md:1114-1124`：`fetch_more` 对 Engine 只表现为普通
  `ToolExecutionRequest` / `ToolExecutionOutcome`，Engine 不知道 definition / callable / dispatch /
  cursor store。
- `docs/host/design.md:1137-1153`：Runtime 只通过闭包把最小补读 Protocol 传给 `fetch_more`
  callable；Runtime 不构造或消费 `ToolFetchMore*`，也不拥有 cursor / truncation 状态机。
- `docs/host/design.md:1177-1189`：EventLog 只看到普通 tool calling；不新增
  `TOOL_RESULT_TRUNCATED` / `TOOL_CURSOR_*` / `TOOL_FETCH_MORE_*`。

### Success Signal

P8.5 完成后必须同时满足：

- `RunEventType` 不再包含 `TOOL_RESULT_TRUNCATED`、`TOOL_CURSOR_ISSUED`、
  `TOOL_CURSOR_EXPIRED`、`TOOL_CURSOR_DENIED`、`TOOL_FETCH_MORE_REQUESTED`、
  `TOOL_FETCH_MORE_COMPLETED`、`TOOL_FETCH_MORE_FAILED`。
- `dayu.host` public surface 不再导出 `ToolResultTruncatedData`、`ToolCursor*Data`、
  `ToolFetchMore*Data`、`ToolRuntimeCursor`、`ToolFetchMoreRequest` 或 `ToolFetchMoreResult`。
- `fetch_more` schema 与 callable 由 Host 私有 `@tool(...)` `ToolDefinition` 同源声明；Engine 只收到
  `definition.to_tool_schema()`。
- `HostToolRuntime` 只做普通 dispatch、组合 `RuntimeTruncateManager`、在普通 tool result 返回前做可选截断；
  它不根据 `fetch_more` 私有返回类型分支。
- `RuntimeTruncateManager` 拥有截断状态机与 cursor store，并通过最小 Protocol 闭包供 `fetch_more`
  callable 补读。
- serializer、conversation memory、tool trace projection 和 README/tests 不再依赖 cursor / truncation /
  `fetch_more` 专属 RunEvent。
- EventLog / trace 中普通 tool call arguments 与 ordinary tool result payload 默认保留；只 scrub
  `API_KEY` / explicit credentials。cursor、`scope_token`、tool data 本身不是 credential scrub 触发条件。
- durable memory repair、trace observer I/O、RunInput raw payload、compact / SSE partial semantics、
  attempt lease hardening 均有切片覆盖、review gate 和验证命令。
- P8.5 按全新起库处理；旧 `TOOL_*TRUNCATED/CURSOR/FETCH_MORE*` EventLog 行丢弃，不写兼容 reader、
  decoder 或 migration。

## 2. Authoritative Decisions

### 2.1 ToolRuntime / EventLog

1. EventLog 只记录普通 tool calling：
   - 保留 `TOOL_CALL_REQUESTED`。
   - 保留 `TOOL_RESULT_ACCEPTED`。
   - 删除 cursor / truncation / `fetch_more` 专属 RunEventType 与 data class。

2. `truncate` 不再是 RunEvent fact：
   - `RuntimeTruncateManager` 在 `ToolCompletedOutcome` 返回给 Engine 前改写普通 tool result。
   - 截断后的 LLM-facing tool result 可以携带 `truncation.next_action="fetch_more"` 与
     `truncation.fetch_more_args`。
   - EventLog 中的 `TOOL_RESULT_ACCEPTED` 保存普通 tool result payload。除 `API_KEY` / explicit
     credentials 外，不因 payload 含 cursor、`scope_token` 或 tool data 而删除或遮蔽字段。

3. `fetch_more` 是 Host 私有 framework built-in tool：
   - Host 私有层使用 `@tool(...)` 构造 `ToolDefinition`，schema 与 callable 同源。
   - Host 只把 `definition.to_tool_schema()` 放入 Engine / Runner 可见 tool schema。
   - Engine 不 import、不接收、不保存、不分支判断 `ToolDefinition`、callable、executor、framework dispatch、
     manager 或 Host 私有 cursor 类型。
   - Runtime 只按普通 tool name dispatch 到 framework executor；执行细节由 `fetch_more` callable 使用闭包
     注入的 manager Protocol 完成。

4. `RuntimeTruncateManager` 是 Host 私有组件：
   - 负责 `ToolTruncateSpec` 驱动的截断、single-use cursor store、TTL、scope / binding 校验、chunk building。
   - 不进入 `dayu.runtime`。
   - 不进入 Engine。
   - 不进入 `dayu.host.__all__` 或 public Host contracts。
   - 暴露给 `fetch_more` callable 的只是一组最小补读 Protocol 能力，不暴露 Runtime 本体、EventLog、harness
     或 Engine。

5. 不做 EventLog batch append：
   - 旧 partial 风险来自专属 multi-fact 模型；删除专属 facts 后该风险消失。
   - 截断 cursor 注册必须和 tool outcome 构造保持一致：如果 manager 无法安全创建/登记 cursor，则返回普通
     failed outcome 或不截断，不能产生需要 EventLog 额外 fact 才能解释的状态。
   - P8.5 不实现 `append_many`，除非实现中发现新的、非 cursor 专属 facts 的直接证据；发现后必须 stop and
     report。

6. `dayu.contracts` 边界：
   - `ToolTruncateSpec`、`@tool`、`ToolDefinition`、`ToolBundle` 仍是公共工具声明契约。
   - `fetch_more` 作为 Host framework built-in，不应继续以 public schema helper 形态要求调用方手工加入
     `RunOptions.tool_schemas`。
   - `framework_fetch_more_tool_schema()` / `FRAMEWORK_FETCH_MORE_TOOL_NAME` 若仍留在 `dayu.contracts`，
     只能作为实现期短暂停留的旧事实；P8.5 最终状态应把 `fetch_more` 名称与 schema source 收回 Host 私有层。
     若实现发现移除这两个 public exports 会破坏 P8.5 以外的大范围 public contract，必须 stop and report。

7. Host 私有 framework schema 投影 owner：
   - schema 投影 owner 是 Host runtime assembly，不是 Engine，也不是普通调用方。
   - P8.5 推荐新增 Host-private schema provider / protocol，例如 `EngineToolSchemaProvider` 或等价命名：
     `engine_visible_tool_schemas(user_tool_schemas: tuple[ToolSchema, ...]) -> tuple[ToolSchema, ...]`。
   - `HostToolRuntime` 通过 Host 私有 `@tool(...)` framework definition 提供 `fetch_more` schema projection；
     provider 只返回 `definition.to_tool_schema()`，不泄漏 `ToolDefinition`、callable、executor 或 manager。
   - `EngineWorker` 或 Host harness 内部必须在构造 `AgentRunRequest` 前调用 provider，生成真正传给 Engine 的
     enhanced tool schemas。调用方仍只传业务 schemas；不得要求调用方 import
     `framework_fetch_more_tool_schema()`。
   - `StartRunRequest.options.tool_schemas` 和 `RunOptions` public object 不做 in-place mutation；Host 可以在内部
     创建 engine-visible request/options copy。
   - `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 必须记录真正传给 Engine 的 enhanced tool schemas，而不是调用方原始
     schemas。
   - 如果实现需要改 Engine public contract 或让 Engine 接收 `ToolDefinition` / callable / manager，必须 stop and
     report。

8. Memory / RunInput capability ingestion policy：
   - EventLog / trace ordinary tool payload 默认保留；cursor、`scope_token`、tool args/result 不因字段名被
     credential scrub。
   - Conversation Memory / RunInput 是 ingestion policy，不是 EventLog credential scrub。短期 runtime capability
     不进入长期 memory 或下一轮 RunInput。
   - memory projection 对 ordinary `TOOL_RESULT_ACCEPTED` 中的 `truncation.fetch_more_args`、raw cursor、
     raw `scope_token` 只生成安全摘要，例如 `truncated=true`、`has_more=true`、`fetch_more_available=true`、
     size / strategy / fingerprint；不得输出原文 cursor 或 scope token。
   - RunInputBuilder rendered tool facts 不包含 raw cursor、raw `scope_token` 或可复用的
     `truncation.fetch_more_args`。
   - 这不是字段级 credential scrub，而是短期 capability 不跨 run 持久复用的 ingestion rule。

### 2.2 Durable Memory Repair

- missing snapshot row 自动修复仍是 P8.5 范围。
- corrupt snapshot row 不自动覆盖；返回 typed diagnostic 并记录 WARNING，运维决定是否删除损坏 row 后让 repair
  重建。
- corrupt snapshot row 的根因研究与“为什么会产生需要运维介入的损坏 row”不在本轮直接裁决；已由
  GitHub issue #41 跟踪。P8.5 只固定保守行为：不静默覆盖、不合成假 snapshot、输出 typed diagnostic +
  WARNING，并保留后续 issue 的 evidence。
- repair 不得按 session 重复全 EventLog 扫描；新增按 session / kind / event_position 分页读取的 durable helper
  和必要索引。

### 2.3 Tool Trace / Observer

- 删除 cursor / truncation 专属 facts 后，ToolTraceProjection 只从普通
  `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` 产出 tool call record。
- `fetch_more` 在 trace 中只是 `tool_name="fetch_more"` 的普通 tool call。
- 截断观察信息若需要保留，只能来自普通 accepted result payload 或其安全摘要，例如 `truncated=true`、
  strategy、chunk size、has_more、cursor / `scope_token`；不得依赖专属 RunEventType。
- Trace 默认保留 ordinary tool call args / result payload；只 scrub API key / explicit credentials，不因字段名
  是 cursor 或 `scope_token` 做遮蔽。
- `ToolTraceObserver` 的 JSONL/blob I/O 不应发生在 SQLite checkpoint transaction 内。
- 非 required trace JSONL/blob sink 采用 at-least-once 语义：JSONL/blob 写入成功但 checkpoint 前 crash 或
  checkpoint 失败时，重放可能产生重复行；reader / analyzer 必须按 `idempotency_key` 去重。
- checkpoint 只能在 sink success 后推进；sink failure 记录 non-required observer failure 且不推进 checkpoint；
  checkpoint failure 不得被报告为 success，下一轮允许 replay。
- required observer 与 non-required observer 的失败边界必须保持分离：non-required trace I/O failure 不阻塞
  required memory observer 追平。
- `utils/analyze_tool_trace_host.py` 必须随 trace schema 调整同步更新。删除专属 facts 后，truncate /
  `fetch_more` 的错误诊断仍是核心验收信号：analyzer 应能从 ordinary tool payload / trace record 中识别
  truncation 未续读、`fetch_more` unknown cursor / wrong scope、重复 `fetch_more`、失败 outcome 与
  provider partial 诊断。
- P8.5 不做 P15 hard-gate / required projection enforcement / watchdog / observer claim lease / durable observer
  outbox。

### 2.4 Compact / RunInput / SSE Partial

- compact diagnostic 与 terminal fact 的分步 append 是独立风险，不与 ToolRuntime event model 混同。
- `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 不再无界内联 raw messages / tool schemas 到 EventLog hot row；P8.5 引入
  Host durable raw payload side store。
- raw payload side store schema 在本 plan 固定，不留给 implementation agent 自行设计：
  - 表名：`run_input_raw_payloads`。
  - columns：`blob_id TEXT PRIMARY KEY`、`session_id TEXT NOT NULL`、`run_id TEXT NOT NULL`、
    `attempt_index INTEGER NOT NULL`、`iteration_index INTEGER NOT NULL`、`iteration_id TEXT NOT NULL`、
    `payload_kind TEXT NOT NULL`、`content_sha256 TEXT NOT NULL`、`byte_size INTEGER NOT NULL`、
    `payload_json TEXT NOT NULL`、`created_at TEXT NOT NULL`。
  - `payload_kind` allowed values：`input_messages`、`tool_schemas`。
  - UNIQUE `(run_id, attempt_index, iteration_index, payload_kind)`。
  - Index：`(session_id, run_id)`；若 implementation 证据显示 trace/debug reader 需要按 iteration 查找，可加
    `(run_id, iteration_id)`。
  - `RunInputContextSnapshotBuiltData` 删除 inline raw json 字段，改为保存两个 payload 的 blob id、hash 与
    byte size。
  - writer owner：Host durable run input context fact append boundary；side store rows 与 EventLog fact append
    必须在同一个 `HostStorage.transaction()` 内提交。
  - reader owner：Tool trace projection / debug reader。
  - missing / corrupt / hash mismatch side-store row：required read path 返回 typed projection failure，例如
    `ProjectionSchemaError` 或等价类型，checkpoint 不推进；禁止合成 fake raw payload。
- SSE partial tool-call diagnostic 属于 Engine-owned diagnostic data、Host-owned persistence；不新增具体工具名
  或 provider-specific RunEventType。
- SSE partial tool-call diagnostic 的主要验收入口是 `utils/analyze_tool_trace_host.py`：当 SSE 中途失败且存在
  已解析但未完成的 tool call delta 时，trace/analyzer 必须能显示 bounded partial tool-call summary，帮助定位
  provider stream failure 前模型正在构造的工具调用；该 summary 不驱动 tool execution，不进入 memory。

### 2.5 Attempt Lease / Recovery

- `_verify_run_id_matches()` 使用独立 `RUN_ID_MISMATCH` reason。
- `next_attempt_index`、renew / terminal race、recovery CAS miss、owner-lost late event、terminal override、
  owner-lost classification、BUSY reason、`lease_context` 参数校验均进入 P8.5。
- attempt lease 语义不进入 `dayu.runtime`。

## 3. Direct Code Evidence

| Area | Direct evidence | Conflict / implication |
| --- | --- | --- |
| Event enum still specialized | `dayu/host/contracts.py:71-77` | `TOOL_RESULT_TRUNCATED`、`TOOL_CURSOR_*`、`TOOL_FETCH_MORE_*` 仍是 public RunEventType。 |
| Public data classes still specialized | `dayu/host/contracts.py:309-462` | ToolRuntime facts 与 fetch_more lifecycle 被建成 public Host data class。 |
| Public fetch_more contract remains | `dayu/host/contracts.py:845-911`、`dayu/host/__init__.py:43-101` | `ToolRuntimeCursor` / `ToolFetchMore*` 仍被当作 Host public contract。 |
| Serializer closed mapping | `dayu/host/_run_event_serializer.py:397-462`、`:668-740`、`:1474-1480` | encoder / decoder / type map 都依赖专属 facts，必须删除而非兼容。 |
| Runtime owns cursor store | `dayu/host/_tool_runtime.py:362-369`、`:904-1114` | `HostToolRuntime` 直接维护 cursor maps，和 design 中 `RuntimeTruncateManager` ownership 冲突。 |
| Runtime branches on fetch_more result | `dayu/host/_tool_runtime.py:548-664`、`:667-865` | Runtime 构造/消费 `ToolFetchMoreRequest/Result`，与闭包注入后 tool 自执行边界冲突。 |
| Runtime appends special facts | `dayu/host/_tool_runtime.py:1188-1459` | 截断、cursor、fetch_more 都由 Runtime 追加 Host-owned RunEvent。 |
| Engine schema path uses caller schemas | `dayu/host/_worker.py:42-52`、`dayu/host/_run_harness.py:2416-2422` | 当前 Engine request 与 RunInput context fact 直接使用 `request.options.tool_schemas`，缺 Host 私有 framework schema 投影层。 |
| Current credential scrub is too broad | `dayu/host/_event_translation.py:101-154` | 当前会移除 `fetch_more` cursor / `scope_token` 和 truncation roundtrip fields；新 durable rule 要求 ordinary tool payload 默认保留，只 scrub API key / explicit credentials。 |
| Trace projection specialized | `dayu/host/_tool_trace_projection.py:141-198`、`:220-231` | projection 按 cursor/fetch_more 专属 event 分支聚合。 |
| Trace sync I/O in async observer | `dayu/host/_tool_trace_projection.py:141-159`、`dayu/host/_tool_trace_jsonl_sink.py:149-209` | async observer 内执行 `flush/fsync/os.replace`。 |
| Trace analyzer expects old truncation/fetch_more fields | `utils/analyze_tool_trace_host.py:1-35`、`:460-490`、`:907-985`、`tests/utils/test_analyze_tool_trace_host.py:241-293` | analyzer 的 truncation / fetch_more diagnostics 是用户调试入口，必须随 generic tool payload trace 更新，而不是丢失错误诊断能力。 |
| Observer transaction wraps process | `dayu/host/_event_observer.py:261-271` | observer `process` 在 SQLite transaction 内执行，然后推进 checkpoint。 |
| Memory projection specialized | `dayu/host/_conversation_memory.py:651-758` | memory projection 把 cursor / fetch_more 专属 facts 投成 memory tool facts。 |
| README locks old public facts | `dayu/host/README.md:13`、`:233-237`、`:396` | README 仍说包根暴露 fetch_more contracts 和 ToolRuntime fact data。 |
| Tests lock old model | `tests/host/test_phase2_tool_runtime_eventlog.py:250-372`、`tests/host/test_phase8_tool_runtime_fencing.py:659-1147` | 测试仍期待专属 facts 和私有 `_fetch_more` 调用。 |
| Public contracts expose schema helper | `dayu/contracts/tool_declaration.py:161-207`、`dayu/contracts/__init__.py:49-111` | `fetch_more` schema helper 仍是 contracts public export，和 Host 私有 framework tool definition 存在张力。 |
| Smoke manually injects fetch_more schema | `utils/smoke_host_multiturn_no_governance.py:708-718` | 当前调用方手工把 `fetch_more` schema 加给 Engine；新 design 应由 Host 投影私有 definition schema。 |
| Durable repair missing-row only | `dayu/host/_conversation_memory_durable.py:263-288` | repair docstring 只覆盖缺 row，不覆盖 corrupt row diagnostic。 |
| Durable repair full-scan shape | `dayu/host/_conversation_memory_durable.py:349-402` | repair 存在容量风险，需要按 session / event_position 的 SQL helper。 |
| Raw RunInput inline | `dayu/host/contracts.py:545-582`、`dayu/host/_run_input_context_fact.py:115-157` | raw messages / schemas 直接进入 EventLog data。 |
| Shared truncation contract still old | `dayu/contracts/tool_result.py:27-45` | `ToolTruncationInfo` docstring 仍禁止 cursor 写入 Host RunEvent / memory / 日志，需要改成 EventLog/trace ordinary payload + memory ingestion policy。 |
| Compact split append | `dayu/host/_run_harness.py:1450-1638` | compact diagnostic、completed、retry、terminal 是分步 append。 |
| SSE partial gap | `dayu/engine/runners/openai/sse_parser.py:284-329`、`:448-500`、`dayu/engine/runners/openai/runner.py:420-545` | parser 可见 tool call delta，但 protocol failure 缺 bounded partial tool-call summary。 |
| RUN_ID_MISMATCH absent | `dayu/host/_attempt_supervisor.py:383-418` | run_id mismatch 被归为 `OWNER_MISMATCH`。 |
| lease_context validation gap | `dayu/host/_attempt_supervisor.py:511-600` | `run_id`、`attempt_index`、`recovered_from_attempt_id` 缺显式参数校验。 |
| next_attempt_index needs direct tests | `dayu/host/_run_state_store.py:928-951` | 独立 store 能力当前主要由 harness 间接覆盖。 |

## 4. Non-goals

- 不恢复 legacy public `fetch_more` handle。
- 不把 `ToolFetchMore*` 或 cursor/truncation 专属 contract 改名后继续公开。
- 不提前实现完整 P10 ToolRegistry。
- 不把 Host tool runtime 语义放入 `dayu.runtime`。
- 不把具体工具名、cursor、truncation 继续编码成 `RunEventType`。
- 不为旧 schema / 旧 EventLog payload 写兼容 reader、decoder 或 migration。
- 不做 P9 Session / Run lifecycle admission。
- 不做 P15 hard-gate / required projection enforcement / watchdog / observer claim lease。
- 不做 P16 public/internal bundle interface freeze。
- 不引入用户级 memory repair CLI。

## 5. Affected Files / Modules

### ToolRuntime / contracts / serializer

- `dayu/host/contracts.py`
- `dayu/host/__init__.py`
- `dayu/host/_run_event_serializer.py`
- `dayu/host/_tool_runtime.py`
- 新增 `dayu/host/_runtime_truncate_manager.py` 或等价 Host 私有模块
- 新增 `dayu/host/_framework_tools.py` 或等价 Host 私有模块
- 新增 Host 私有 schema provider module / protocol，例如 `dayu/host/_engine_tool_schema_provider.py` 或等价位置
- `dayu/host/_worker.py`
- `dayu/host/_run_harness.py`
- `dayu/host/_durable_harness.py`
- `dayu/host/_event_translation.py`
- `dayu/contracts/tool_declaration.py`
- `dayu/contracts/tool_result.py`
- `dayu/contracts/__init__.py`

### Projections / trace / memory

- `dayu/host/_conversation_memory.py`
- `dayu/host/_tool_trace_projection.py`
- `dayu/host/_tool_trace_jsonl_sink.py`
- `dayu/host/_event_observer.py`
- `utils/analyze_tool_trace_host.py`
- `tests/utils/test_analyze_tool_trace_host.py`

### Durable memory / storage / RunInput

- `dayu/host/_conversation_memory_durable.py`
- `dayu/host/_durable_event_store.py`
- `dayu/host/_host_storage.py` / schema bootstrap owner located by implementation
- `dayu/host/_durable_harness.py`
- `dayu/host/_run_input_context_fact.py`
- `dayu/host/_run_harness.py`
- 新增 Host raw payload side-store module if needed

### Engine partial diagnostics

- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/engine/agent.py`
- `dayu/host/_event_translation.py`
- `utils/analyze_tool_trace_host.py`
- `tests/utils/test_analyze_tool_trace_host.py`

### Attempt lease / recovery

- `dayu/host/_attempt_supervisor.py`
- `dayu/host/_attempt_lease_store.py`
- `dayu/host/_run_state_store.py`
- existing P8 test files under `tests/host/test_phase8_*.py`

### Tests / docs / smokes

- `tests/contracts/test_tool_declaration.py`
- `tests/contracts/test_tool_result_envelope.py` 或现有 tool result contract tests
- `tests/contracts/test_package_exports.py`
- `tests/host/test_phase1_public_boundary.py`
- `tests/host/test_host_public_api_surface.py`
- `tests/host/test_phase2_tool_runtime_boundary.py`
- `tests/host/test_phase2_tool_runtime_truncation.py`
- `tests/host/test_phase2_tool_runtime_eventlog.py`
- `tests/host/test_phase3_conversation_memory_projection.py`
- `tests/host/test_phase5_multiturn_no_governance_smoke.py`
- `tests/host/test_phase6_run_event_serializer.py`
- `tests/host/test_phase7_tool_trace_projection.py`
- `tests/host/test_phase7_contract_serializer.py`
- `tests/host/test_phase7_run_input_context_fact.py`
- `tests/host/test_phase8_tool_runtime_fencing.py`
- `tests/host/test_phase8_durable_memory_recovery.py`
- `tests/utils/test_analyze_tool_trace_host.py`
- `utils/smoke_host_multiturn_no_governance.py`
- `utils/smoke_host_tool_runtime.py`
- `utils/analyze_tool_trace_host.py`
- `dayu/host/README.md`
- `tests/README.md`
- root `README.md` only if user-facing smoke/tool schema instructions change.

## 6. Contract / Serializer / Projection / Schema Impact

- Public Host contract impact：删除 ToolRuntime cursor/truncation/fetch_more event data 与 fetch_more request/result
  contracts from Host public surface。
- Public shared contract impact：`ToolTruncateSpec` 和 `@tool` 保留；`ToolTruncationInfo` 是 ordinary
  LLM-facing tool result payload 的一部分，可进入 EventLog / trace；不得进入 Conversation Memory、下一轮
  RunInput、普通日志或 README 大块输出。`framework_fetch_more_tool_schema()` /
  `FRAMEWORK_FETCH_MORE_TOOL_NAME` 最终应不再作为 caller-facing public helper 使用。实现若无法安全移除，必须
  stop and report。
- Serializer impact：删除 cursor/truncation/fetch_more 专属 encode/decode 分支和 closed mapping；不兼容旧 rows。
- EventLog schema/index impact：
  - Slice 1 不需要新增 EventLog table；是 event type/data 收缩。
  - Slice 2 需要新增或确认 `host_run_events(session_id, kind, event_position)` 方向的索引 / helper。
  - Slice 4 新增 Host durable raw payload side store：
    `run_input_raw_payloads(blob_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, run_id TEXT NOT NULL,
    attempt_index INTEGER NOT NULL, iteration_index INTEGER NOT NULL, iteration_id TEXT NOT NULL,
    payload_kind TEXT NOT NULL, content_sha256 TEXT NOT NULL, byte_size INTEGER NOT NULL,
    payload_json TEXT NOT NULL, created_at TEXT NOT NULL)`；`payload_kind IN ('input_messages','tool_schemas')`；
    UNIQUE `(run_id, attempt_index, iteration_index, payload_kind)`；Index `(session_id, run_id)`，可选
    `(run_id, iteration_id)`；不支持旧 inline payload compatibility。
- Projection impact：memory / trace 不再消费 cursor/truncation/fetch_more 专属 facts；trace I/O 与 checkpoint
  transaction 解耦。
- Payload policy impact：EventLog / trace 普通 tool payload 默认保留；serializer 与 projection 测试必须断言
  cursor / `scope_token` 可作为 ordinary tool args/result payload 存在，且 API key / explicit credentials
  仍被 scrub。不要把 cursor / `scope_token` 描述为敏感字段；它们只受 memory / RunInput
  ingestion policy 限制。
- Test impact：大量旧 P2/P5/P7/P8 测试需要跟随边界迁移，禁止为旧测试堆兼容代码。

## 7. Implementation Slices

### Slice 1 — Generic Tool-Calling EventLog + RuntimeTruncateManager

**Objective**

一次性完成 ToolRuntime event model root cause 修复：删除 cursor/truncation/`fetch_more` 专属 RunEvent 与 public
contracts，抽出 `RuntimeTruncateManager`，将 `fetch_more` 改为 Host 私有 `@tool` framework tool。

**Allowed files/modules**

`dayu/host/contracts.py`、`dayu/host/__init__.py`、`dayu/host/_run_event_serializer.py`、
`dayu/host/_tool_runtime.py`、Host 私有新增模块、`dayu/host/_worker.py`、`dayu/host/_run_harness.py`、
`dayu/host/_durable_harness.py`、`dayu/host/_conversation_memory.py`、`dayu/host/_event_translation.py`、
`dayu/contracts/tool_declaration.py`、`dayu/contracts/tool_result.py`、`dayu/contracts/__init__.py`、
相关 tests / utils smoke / README。

**Implementation instructions**

- 删除 `RunEventType.TOOL_RESULT_TRUNCATED`、`TOOL_CURSOR_ISSUED`、`TOOL_CURSOR_EXPIRED`、
  `TOOL_CURSOR_DENIED`、`TOOL_FETCH_MORE_REQUESTED`、`TOOL_FETCH_MORE_COMPLETED`、
  `TOOL_FETCH_MORE_FAILED`。
- 删除对应 Host data class、`ToolRuntimeEventData` union、Host package exports、serializer mapping。
- 删除 `ToolRuntimeCursor`、`ToolFetchMoreRequest`、`ToolFetchMoreSucceededResult`、
  `ToolFetchMoreFailedResult`、`ToolFetchMoreResult`；如内部仍需要 cursor handle，用 Host 私有 manager 类型。
- 新增 Host 私有 `RuntimeTruncateManager`，迁移 cursor maps、TTL、scope / binding 校验、limit clamp、
  chunk building、single-use consume / next cursor issue。
- `HostToolRuntime.execute_tool_call()` 对业务 tool：
  1. 调用底层 business executor。
  2. 对 successful `ToolCompletedOutcome` 调用 manager 可选截断。
  3. 返回普通 `ToolExecutionOutcome`。
  4. 不追加截断 / cursor RunEvent。
- 在 Host 私有层用 `@tool(...)` 构造 `fetch_more` `ToolDefinition`；callable 通过闭包拿到 manager 最小补读
  Protocol，自己执行补读并返回普通 `ToolCompletedOutcome` / `ToolFailedOutcome`。
- 新增 Host 私有 schema provider / protocol，例如 `EngineToolSchemaProvider`：
  - `HostToolRuntime` 或 Host runtime assembly 拥有 provider。
  - provider 从私有 framework `ToolDefinition` 投影 `definition.to_tool_schema()`。
  - `_run_harness.py` / `_worker.py` / durable assembly 在构造 `AgentRunRequest` 前把调用方业务 schemas 与
    framework schemas 合成为 engine-visible schemas。
  - 不修改 `StartRunRequest.options.tool_schemas` / `RunOptions` public object；必要时创建内部 enhanced request
    或 options copy。
  - `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 使用 enhanced tool schemas，保证 trace 记录的是 Engine 实际看到的 schema。
  - Engine 不接收 `ToolDefinition`、callable、executor 或 manager。
- 调用方不应再手工 import public `framework_fetch_more_tool_schema()`；旧 smoke 需要改为只传业务 schemas。
- `ToolTruncationInfo` 文档改为 ordinary LLM-facing tool result payload：可进入 EventLog / trace；不得进入
  memory / 下一轮 RunInput / 普通日志 / README 大块输出。
- `_event_translation.py` 的 scrub 规则改为 credential-only：普通 `fetch_more` arguments 中 raw cursor /
  `scope_token` 可进入 EventLog，accepted result 中 cursor / `scope_token` 也可作为普通 payload 保留；
  只有 `API_KEY` / explicit credentials 被 scrub。
- `_conversation_memory.py` 的普通 tool result ingestion 必须摘要化短期 capability：raw cursor、
  raw `scope_token`、`truncation.fetch_more_args` 不进入 Conversation Memory tool fact 文本或下一轮 RunInput；
  允许保留 `truncated=true`、strategy、size、has_more、cursor fingerprint 等不可复用摘要。
- 更新 tests：public surface 负向锁定 `ToolFetchMore*`、`ToolCursor*Data`、`ToolResultTruncatedData`、
  `TOOL_CURSOR_*`、`TOOL_RESULT_TRUNCATED` 不存在；P2/P5/P8 测试改为断言普通 tool call/request/result。
- 更新 tests：新增 ordinary payload retention 断言，覆盖 `fetch_more` tool call args 中 cursor /
  `scope_token`、truncated ordinary tool result 中 `truncation.fetch_more_args` 可以进入 EventLog / trace；同时保留
  API key / explicit credential scrub 断言。
- 更新 tests：调用方只传业务 `ToolSchema` 时，Engine request 仍包含 `fetch_more` schema；`RunOptions.tool_schemas`
  不被污染；Engine 不接收 `ToolDefinition` / callable / manager；RunInput context fact 记录 enhanced schemas。
- 更新 tests：EventLog / trace 可见 cursor / `scope_token` ordinary payload；memory snapshot / RunInput rendered
  tool facts 不包含 raw cursor / raw `scope_token`。
- grep guard（production/current-doc）：`rg "TOOL_FETCH_MORE|TOOL_CURSOR_|TOOL_RESULT_TRUNCATED|ToolFetchMore|ToolCursor.*Data|ToolResultTruncatedData" dayu tests dayu/host/README.md tests/README.md`
  生产代码不得命中；负向 forbidden-name 测试常量允许命中但必须注释为 forbidden names。

**Non-goals**

- 不引入 P10 ToolRegistry。
- 不实现 EventLog `append_many`。
- 不把 manager 放入 `dayu.runtime`。

**Validation**

```bash
source .venv/bin/activate
python -m pyright dayu/host/ dayu/contracts/ tests/host/ tests/contracts/
pytest tests/contracts/test_tool_declaration.py tests/contracts/test_tool_result_envelope.py tests/contracts/test_package_exports.py -q
pytest tests/host/test_phase1_public_boundary.py tests/host/test_host_public_api_surface.py -q
pytest tests/host/test_phase2_tool_runtime_boundary.py tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase2_tool_runtime_eventlog.py -q
pytest tests/host/test_phase3_conversation_memory_projection.py tests/host/test_phase5_multiturn_no_governance_smoke.py tests/host/test_phase8_tool_runtime_fencing.py -q
```

**Completion signal**

No dedicated cursor/truncation/fetch_more RunEvent remains; `fetch_more` works through ordinary tool call path and Host-private
framework tool callable.

**Stop conditions**

- Need to expose `ToolDefinition` / manager / cursor type to Engine, `StartRunRequest`, `RunOptions`, or Host public API.
- Need complete P10 ToolRegistry to finish.
- Need compatibility reader for old cursor/fetch_more EventLog rows.

**Implementation prompt**

```text
这是 Gateflow-governed implementation handoff，但你不是 Gateflow controller。不要启动 $gateflow / /gateflow；
不要重新写 plan、不要做 plan review、不要 commit/PR/closeout。current gate: implementation。

Assigned slice: P8.5 Slice 1 — Generic Tool-Calling EventLog + RuntimeTruncateManager。
Approved plan path: docs/host/phase8.5-plan.md。

严格按 Slice 1 scope 实施。核心边界：EventLog 只记录 TOOL_CALL_REQUESTED / TOOL_RESULT_ACCEPTED；
truncate/cursor/fetch_more 都是 Host 私有 RuntimeTruncateManager / framework tool 实现细节；Engine 什么都看不到。
Host runtime assembly 必须自动把私有 fetch_more schema 投影到 Engine-visible schemas，调用方只传业务 schema，
且 RunOptions public object 不被污染。EventLog / trace 保留普通 payload；memory / RunInput 不保留 raw
cursor、raw scope_token 或可复用 fetch_more_args。

完成后写 durable implementation artifact:
docs/host/phase8.5-s1-implementation-report.md
报告 changed files、plan items implemented、validation results、docs decision、residual risks、stop condition status。
```

### Slice 2 — Durable Memory Repair Stabilization

**Objective**

修复 durable memory repair 的容量风险与 corrupt snapshot row 策略边界。

**Allowed files/modules**

`dayu/host/_conversation_memory_durable.py`、`dayu/host/_durable_event_store.py`、schema bootstrap owner、
`dayu/host/_durable_harness.py`、`tests/host/test_phase8_durable_memory_recovery.py`、README。

**Implementation instructions**

- 新增强类型 repair report，例如 `MemoryRepairReport(repaired_session_ids, diagnostics)`。
- 新增 typed diagnostic，例如 `MemoryRepairDiagnostic(kind=CORRUPT_SNAPSHOT, session_id, reason)`。
- `repair_missing_session_snapshots()` 返回 report；`startup_reconcile()` 暴露或记录 diagnostics。
- snapshot row 缺失且 EventLog 有 terminal canonical facts：自动重建。
- snapshot row 存在但 payload corrupt / schema mismatch / type invalid：不覆盖，返回 typed diagnostic，记录 WARNING，
  继续其它 session repair；运维是否删除损坏 row 后让 repair 重建由人工决定。
- corrupt snapshot row 的产生原因、是否应该存在运维手工介入、是否需要 quarantine / operator command /
  自动覆盖策略，均不在 P8.5 Slice 2 直接研究或裁决；由 GitHub issue #41 跟踪。implementation 若发现直接
  代码证据说明 corrupt row 可由当前写路径正常产生，必须 stop and report。
- 新增 durable event helper，SQL shape 必须是
  `WHERE session_id = ? AND kind = ? AND event_position > ? ORDER BY event_position ASC LIMIT ?`。
- 新增或确认索引支持上述 helper。
- missing session scan 分页或 batch limit，避免一次性收集全库。

**Validation**

```bash
source .venv/bin/activate
python -m pyright dayu/host/ tests/host/
pytest tests/host/test_phase8_durable_memory_recovery.py -q
pytest tests/host/test_phase8_multiprocess_stress.py -q
```

**Stop conditions**

- Need user-facing repair CLI.
- Need old database migration / compatibility reader.

**Implementation prompt**

```text
这是 Gateflow-governed implementation handoff，但你不是 Gateflow controller。不要启动 $gateflow / /gateflow；
不要进入其它 slice、不要 commit/PR。current gate: implementation。

Assigned slice: P8.5 Slice 2 — Durable Memory Repair Stabilization。
只修改 durable memory repair、EventLog helper/index、相关 tests/README。不要修改 ToolRuntime event model。

完成后写 docs/host/phase8.5-s2-implementation-report.md。
```

### Slice 3 — Tool Trace / Observer Projection Stability

**Objective**

让 trace projection 适配 generic tool-calling-only EventLog，并把非 required ToolTraceObserver 文件 I/O 移出 SQLite
checkpoint transaction。

**Allowed files/modules**

`dayu/host/_tool_trace_projection.py`、`dayu/host/_tool_trace_jsonl_sink.py`、`dayu/host/_event_observer.py`、
`utils/analyze_tool_trace_host.py`、`tests/host/test_phase7_tool_trace_projection.py`、
`tests/host/test_phase7_tool_trace_jsonl_sink.py`、`tests/utils/test_analyze_tool_trace_host.py`、README。

**Implementation instructions**

- trace tool_call record 只从 `TOOL_CALL_REQUESTED` + `TOOL_RESULT_ACCEPTED` 配对产生。
- `fetch_more` 是普通 `tool_name`，不得有特殊 trace branch。
- 截断信息只从 ordinary accepted result payload / summary 派生；没有 payload / summary 时 trace 不得反推
  cursor store。
- 删除 `ToolFetchMoreCompletedData` / cursor fact summarizer。
- 更新 `utils/analyze_tool_trace_host.py` 以适配新的 generic tool-call trace schema：
  - truncate / `fetch_more` 诊断不得依赖 `TOOL_RESULT_TRUNCATED`、`TOOL_CURSOR_*` 或旧专属字段。
  - analyzer 必须继续报告 truncation 后未续读、`fetch_more` unknown cursor / wrong scope、重复
    `fetch_more`、tool failure patterns 与 provider protocol failure。
  - analyzer 去重仍以 `idempotency_key` 为真源，适配 non-required trace at-least-once replay。
  - `tests/utils/test_analyze_tool_trace_host.py` 必须随 schema 更新，覆盖新的 ordinary payload 输入。
- 为非 required observer 增加非事务处理路径，例如 protocol `NonTransactionalObserverSink`：
  - required observer 仍在 transaction 内 `process(tx,batch)`。
  - non-required trace observer 先在 transaction 外执行 JSONL/blob I/O；成功后用短 transaction 推进 checkpoint。
  - I/O 失败时记录 non-required observer failure，不推进 checkpoint，不阻塞 memory required projection。
  - JSONL/blob sink 是 at-least-once；I/O 成功但 checkpoint 前 crash 或 checkpoint 失败时，下一次 drain 允许
    replay 并产生重复 JSONL/blob record，reader/analyzer 必须按 `idempotency_key` 去重。
  - checkpoint 只能在 sink success 后推进；checkpoint 推进失败必须记录为 checkpoint failure / blocked or
    retryable failure，不得标记 success。
  - required observer failure 与 non-required observer failure 分开记录；non-required trace failure 不得把 required
    memory observer 状态拖成 failed。
- `ToolTraceObserver` 可用 `asyncio.to_thread` 包裹同步 JSONL/blob 写入，避免阻塞 event loop；不做 durable outbox。

**Validation**

```bash
source .venv/bin/activate
python -m pyright dayu/host/ tests/host/
pytest tests/host/test_phase7_tool_trace_projection.py tests/host/test_phase7_tool_trace_jsonl_sink.py -q
pytest tests/host/test_phase6_projection_checkpoint.py tests/host/test_phase8_multiprocess_stress.py -q
pytest tests/utils/test_analyze_tool_trace_host.py -q
```

Expected assertions include：

- I/O success + checkpoint failure 后 replay 会产生相同 `idempotency_key` 的重复 row，analyzer / reader 去重后只保留一条逻辑记录。
- I/O failure 不推进 trace checkpoint，记录 failure，且不阻塞 required memory observer 成功推进。
- checkpoint failure 不得被报告为 success。
- analyzer 在新 trace schema 下仍能输出 truncation / `fetch_more` 错误诊断，且重复 row 被
  `idempotency_key` 去重。

**Stop conditions**

- Need observer claim lease / watchdog / hard-gate.
- Need durable observer outbox.

**Implementation prompt**

```text
这是 Gateflow-governed implementation handoff，但你不是 Gateflow controller。不要启动 $gateflow / /gateflow；
不要进入其它 slice、不要 commit/PR。current gate: implementation。

Assigned slice: P8.5 Slice 3 — Tool Trace / Observer Projection Stability。
只处理 trace projection generic tool-call 模型与 non-required observer I/O transaction 边界。

完成后写 docs/host/phase8.5-s3-implementation-report.md。
```

### Slice 4 — Compact / RunInput / SSE Partial Semantic Cleanup

**Objective**

收口 compact 分步事实、RunInput raw payload 热冷分离、compact retry iteration/attempt 语义，以及 SSE partial
tool-call diagnostic。

**Allowed files/modules**

`dayu/host/contracts.py`、`dayu/host/_run_event_serializer.py`、`dayu/host/_run_input_context_fact.py`、
`dayu/host/_run_harness.py`、Host raw payload side-store module/schema、`dayu/host/_tool_trace_projection.py`、
`dayu/engine/contracts/*`、`dayu/engine/runners/openai/*`、`dayu/engine/agent.py`、
`utils/analyze_tool_trace_host.py`、相关 tests / README。

**Implementation instructions**

- `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` data 移除无界 raw inline payload；保留 summary、hash、byte size、blob id。
- 新增 Host durable raw payload side store，schema 固定为：
  - table：`run_input_raw_payloads`。
  - columns：`blob_id TEXT PRIMARY KEY`、`session_id TEXT NOT NULL`、`run_id TEXT NOT NULL`、
    `attempt_index INTEGER NOT NULL`、`iteration_index INTEGER NOT NULL`、`iteration_id TEXT NOT NULL`、
    `payload_kind TEXT NOT NULL`、`content_sha256 TEXT NOT NULL`、`byte_size INTEGER NOT NULL`、
    `payload_json TEXT NOT NULL`、`created_at TEXT NOT NULL`。
  - `payload_kind` allowed values：`input_messages`、`tool_schemas`。
  - UNIQUE `(run_id, attempt_index, iteration_index, payload_kind)`。
  - Index `(session_id, run_id)`；可选 Index `(run_id, iteration_id)` 仅在 reader 直接需要时增加。
- 新增 side-store API 或等价 repository：
  - writer：`put_run_input_raw_payloads(tx, session_id, run_id, attempt_index, iteration_index, iteration_id, payloads)`
    或等价强类型 API，在同一 transaction 内写入两类 payload 并返回 blob id / hash / byte size。
  - reader：`get_run_input_raw_payload(tx_or_conn, blob_id)` 或按 snapshot fact 引用批量读取，校验
    `content_sha256` 与 `byte_size`。
  - missing row、hash mismatch、invalid JSON、kind mismatch 必须抛 typed projection failure，例如
    `ProjectionSchemaError`；required read path checkpoint 不推进；不得合成 fake raw payload。
- writer 是 Host durable run input context fact append boundary；reader 是 trace projection / debug reader。
- side store write 与 EventLog append 必须处于同一个 `HostStorage.transaction()`；做不到则 stop and report。
- `RunInputContextSnapshotBuiltData` 删除 inline `raw_input_messages_json` / `raw_tool_schemas_json`，保留：
  `raw_input_messages_blob_id`、`raw_input_messages_sha256`、`raw_input_messages_byte_size`、
  `raw_tool_schemas_blob_id`、`raw_tool_schemas_sha256`、`raw_tool_schemas_byte_size`。
- compact retry 语义固定：
  - `attempt_index` 是 Host attempt index，retry 后递增。
  - `iteration_index` 是当前 attempt 内 Engine iteration，retry attempt 首轮为 `0`。
  - `iteration_id` 由 `run_id + attempt_index` 派生。
- 补测试覆盖 compact diagnostic success 但 terminal close CAS/fencing miss 的路径，证明唯一 terminal truth 不破坏。
- 扩展 Engine provider/protocol failure data，加入 bounded `partial_tool_calls` summary；Host 继续用
  `PROVIDER_PROTOCOL_ERROR` RunEvent，trace projection 派生 diagnostic。
- partial summary 不含 raw argument payload，不进入 memory，不驱动 tool execution。
- 更新 `utils/analyze_tool_trace_host.py`：`provider_protocol_error` 报告中必须展示 bounded
  `partial_tool_calls` summary，使 SSE 中途失败时能看到模型已开始构造但未完成的 tool call；该诊断是
  SSE partial feature 的主要人工观察入口。

**Validation**

```bash
source .venv/bin/activate
python -m pyright dayu/engine/ dayu/host/ tests/engine/ tests/host/
pytest tests/host/test_phase4_overflow_retry.py tests/host/test_phase7_run_input_context_fact.py tests/host/test_phase7_contract_serializer.py -q
pytest tests/host/test_phase7_tool_trace_projection.py -q
pytest tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_event_flow_ordering.py -q
pytest tests/utils/test_analyze_tool_trace_host.py -q
```

Expected assertions include：

- transaction rollback 后没有 orphan side-store row。
- EventLog fact 引用的 blob id 可读，hash / byte size 校验通过。
- missing side-store row、hash mismatch 或 corrupt JSON 导致 typed projection failure，checkpoint 不推进。
- SSE partial tool-call diagnostic 能在 `utils/analyze_tool_trace_host.py` 输出中看见 bounded partial
  tool-call summary。

**Stop conditions**

- Need provider-specific RunEventType.
- Need raw payload compatibility reader for old EventLog rows.
- Cannot make raw side store and EventLog append atomic in P8.5 scope.

**Implementation prompt**

```text
这是 Gateflow-governed implementation handoff，但你不是 Gateflow controller。不要启动 $gateflow / /gateflow；
不要进入其它 slice、不要 commit/PR。current gate: implementation。

Assigned slice: P8.5 Slice 4 — Compact / RunInput / SSE Partial Semantic Cleanup。
只处理 compact、RunInput raw side store、SSE partial diagnostic 与相关 trace/readme/tests。

完成后写 docs/host/phase8.5-s4-implementation-report.md。
```

### Slice 5a — Attempt Lease Diagnostic Corrections

**Objective**

修复 attempt lease 诊断与防御性边界：独立 `RUN_ID_MISMATCH`、BUSY reason、`lease_context` 参数校验、
`next_attempt_index` 独立测试。

**Allowed files/modules**

`dayu/host/_attempt_supervisor.py`、`dayu/host/_attempt_lease_store.py`、`dayu/host/_run_state_store.py`、
P8 attempt tests、README。

**Implementation instructions**

- 新增 `AttemptFencingReason.RUN_ID_MISMATCH`；`_verify_run_id_matches()` 使用该 reason。
- BUSY reason 不复用 fencing reason；新增 `AttemptLeaseBusyReason.ATTEMPT_INDEX_CONFLICT` 或等价强类型枚举。
- `AttemptLeaseResult` 以独立字段表达 busy reason。
- `lease_context` 显式校验 `run_id` 非空、`attempt_index >= 0`、`recovered_from_attempt_id` 非空时不能是空串。
- 为 `RunStateStore.next_attempt_index()` 补独立测试：无 attempt、active、terminal、gap/conflict。

**Validation**

```bash
source .venv/bin/activate
python -m pyright dayu/host/ tests/host/
pytest tests/host/test_phase8_attempt_supervisor.py tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_recovery.py -q
```

**Stop conditions**

- Need change public Host API.
- Need move attempt semantics into `dayu.runtime`。

**Implementation prompt**

```text
这是 Gateflow-governed implementation handoff，但你不是 Gateflow controller。不要启动 $gateflow / /gateflow；
不要进入其它 slice、不要 commit/PR。current gate: implementation。

Assigned slice: P8.5 Slice 5a — Attempt Lease Diagnostic Corrections。
只处理 attempt lease 诊断、防御校验和 next_attempt_index 独立测试。

完成后写 docs/host/phase8.5-s5a-implementation-report.md。
```

### Slice 5b — Attempt Lease / Recovery Adversarial Hardening

**Objective**

补齐 P8 adversarial coverage：renew/terminal race、recovery CAS miss、owner-lost late event、terminal override、
expired/denied fencing 等。

**Allowed files/modules**

`dayu/host/_attempt_supervisor.py`、`dayu/host/_attempt_lease_store.py`、`dayu/host/_run_harness.py`、
P8 tests、README。

**Implementation instructions**

- 覆盖 `_renew_loop` 并发竞争：renew 与 terminal close race、owner-lost 第一原因不被 late renew 覆盖、
  storage exception 分类为 `STORAGE_ERROR` 且不泄漏 background task exception。
- recovery CAS miss 不得关闭新 owner。
- owner-lost late event 不得追加 attempt-scoped EventLog。
- terminal override 不得覆盖既有 terminal。
- Slice 1 后不再存在 cursor facts；expired/denied fencing 改为 `fetch_more` 普通 failed outcome 与
  attempt-scoped generic tool call path的 fencing 覆盖。

**Validation**

```bash
source .venv/bin/activate
python -m pyright dayu/host/ tests/host/
pytest tests/host/test_phase8_attempt_supervisor.py tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_recovery.py tests/host/test_phase8_tool_runtime_fencing.py -q
pytest tests/host/test_phase8_multiprocess_stress.py -q
```

**Stop conditions**

- Need production process supervisor.
- Need P9 lifecycle admission.

**Implementation prompt**

```text
这是 Gateflow-governed implementation handoff，但你不是 Gateflow controller。不要启动 $gateflow / /gateflow；
不要进入其它 slice、不要 commit/PR。current gate: implementation。

Assigned slice: P8.5 Slice 5b — Attempt Lease / Recovery Adversarial Hardening。
只处理 approved adversarial coverage 和直接必要的 root-cause fixes。

完成后写 docs/host/phase8.5-s5b-implementation-report.md。
```

### Slice 6 — Documentation / Migration Registry Closeout

**Objective**

把 P8.5 后的真实代码事实同步到 docs / README / migration residual registry，准备 controller 进入 PR gate。

**Allowed files/modules**

`docs/host/migration-plan.md`、`docs/host/design.md`（仅修正与实现事实冲突的少量文字）、
`dayu/host/README.md`、`tests/README.md`、root `README.md` if triggered。

**Implementation instructions**

- Host README 删除旧 public `ToolFetchMore*`、ToolRuntime fact data、cursor fact EventLog 描述。
- Tests README 更新 P8.5 后测试分层与命令。
- migration-plan residual risk registry 更新：哪些 fixed、哪些 deferred to P9/P15/P16/issue。
- `docs/host/design.md` 只保留 current design；旧 P7/P8 段落若仍提到 cursor / truncation /
  `fetch_more` 专属 facts 或 observer sink 与 checkpoint 同事务，必须改成 historical pre-P8.5 wording 或明确
  superseded by §11，不得作为 normative current fact 留存。
- 不把 future design 写成已落地事实。

**Validation**

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
pytest tests/host -q
pytest tests/contracts tests/engine -q
rg "TOOL_FETCH_MORE|TOOL_CURSOR_|TOOL_RESULT_TRUNCATED|ToolFetchMore|ToolCursor.*Data|ToolResultTruncatedData" dayu tests dayu/host/README.md tests/README.md
rg "TOOL_FETCH_MORE|TOOL_CURSOR_|TOOL_RESULT_TRUNCATED|ToolFetchMore|ToolCursor.*Data|ToolResultTruncatedData" docs/host/migration-plan.md docs/host/phase8.5-plan.md
```

Expected grep semantics：

- production/current-doc guard：`dayu`、`tests`、`dayu/host/README.md`、`tests/README.md` 不应存在当前用法；
  仅允许 negative forbidden-name tests 命中，且测试注释必须说明这些名字被禁止。
- historical-doc audit guard：`docs/host/migration-plan.md`、旧 review artifacts 和本 plan 可作为历史 /
  residual context 命中旧名字；不得为了零命中删除审计上下文。

**Stop conditions**

- Any docs claim cannot be supported by code/tests.

**Implementation prompt**

```text
这是 Gateflow-governed implementation handoff，但你不是 Gateflow controller。不要启动 $gateflow / /gateflow；
不要进入 commit/PR。current gate: implementation。

Assigned slice: P8.5 Slice 6 — Documentation / Migration Registry Closeout。
只同步 P8.5 已完成代码事实与 residual risk owner。

完成后写 docs/host/phase8.5-s6-implementation-report.md。
```

## 8. Review Gates

### Plan review

- 必须 adversarial review 本 plan 是否真正遵守 `docs/host/design.md` §11；§11 与本 plan supersede 旧 P2/P7/P8
  历史 wording。
- 必须挑战 Slice 1 是否过大；若 reviewer 认为过大，必须提出不会诱导临时兼容层的替代切片。
- 必须检查 public contract removal 是否写清楚，尤其 `dayu.contracts.framework_fetch_more_tool_schema` /
  `FRAMEWORK_FETCH_MORE_TOOL_NAME` 的最终归属。
- 必须检查所有 blocking open questions 是否已收敛。
- Artifact：`docs/host/phase8.5-plan-review.md`。

### Plan fix / re-review

- Fix artifact：`docs/host/phase8.5-plan-fix-report.md`。
- Re-review artifact：`docs/host/phase8.5-plan-rereview.md`。
- re-review pass 后必须等 user confirmation；确认后 controller 才能创建新的 accepted plan commit。

### Code review per slice

- 每个 slice implementation artifact 落盘后才能进入 code review。
- Code review 只 review assigned slice diff，不重审未开始 slice。
- accepted findings 必须 fix + re-review；code re-review pass 后等 user confirmation 才能 accepted slice commit。

## 9. Validation Matrix

全 P8.5 closeout 前至少运行：

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
pytest tests/contracts tests/engine -q
pytest tests/host -q
pytest tests/host/test_phase8_multiprocess_stress.py -q
python utils/smoke_host_tool_runtime.py
python utils/smoke_host_multiturn_no_governance.py --fake-provider
git diff --check
```

如真实 provider smoke 需要外部 key，不作为必跑项；若运行则记录环境与结果。

## 10. Residual Risk Owner Changes

| Residual risk | New owner / destination |
| --- | --- |
| ToolRuntime event model root cause | P8.5 Slice 1 |
| `TOOL_FETCH_MORE_*` concrete tool RunEventType | P8.5 Slice 1 |
| `TOOL_RESULT_TRUNCATED` / `TOOL_CURSOR_*` as EventLog facts | P8.5 Slice 1 |
| EventLog multi-fact partial risk from old fetch_more completed + cursor issued | Closed by Slice 1 if no dedicated facts remain; `append_many` remains non-goal unless new evidence |
| Durable memory repair capacity / corrupt row immediate behavior | P8.5 Slice 2：capacity helper + typed diagnostic + WARNING; no automatic overwrite |
| Corrupt durable memory snapshot row root-cause / long-term repair policy | GitHub issue #41 |
| ToolTraceObserver sync I/O inside transaction | P8.5 Slice 3 |
| `analyze_tool_trace_host.py` generic trace diagnostics for truncation / fetch_more | P8.5 Slice 3 |
| Observer claim lease / hard-gate / watchdog | P15 / issue #28 |
| Compact diagnostic / terminal split append | P8.5 Slice 4 |
| RunInput raw payload hot/cold mixing | P8.5 Slice 4 |
| SSE partial tool-call semantic gap / analyzer visibility | P8.5 Slice 4 |
| `_verify_run_id_matches()` reason | P8.5 Slice 5a |
| `next_attempt_index` independent tests | P8.5 Slice 5a |
| `_renew_loop` race / storage error / owner-lost coverage | P8.5 Slice 5b |
| recovery CAS miss / owner-lost late event / terminal override | P8.5 Slice 5b |
| P9 lifecycle admission / recovery auto wire | P9 |
| P16 public/internal bundle freeze | P16 |

## 11. Open Questions

No blocking open question for plan handoff.

Non-blocking watch item：API key / explicit credentials 的识别边界必须保持窄定义。implementation agent 不得
把普通业务字段、cursor、`scope_token`、tool args 或 tool result 扩大解释为 credentials；若发现具体 provider
payload 内存在新的明确凭证字段，应在 slice report 中列证据并收敛到 credential scrub 测试。

## 12. Implementation Completion Report Format

每个 slice implementation report 必须包含：

- work gate name：`implementation`。
- work-unit name and assigned slice id。
- approved plan path。
- assigned scope / explicit non-goals / allowed files。
- changed files。
- plan items implemented。
- plan items not implemented and reason。
- validation commands and results。
- documentation update decision and result。
- plan gaps or controller questions。
- residual risks and uncovered areas, classified as current-slice fix / later slice / later phase / existing issue /
  new issue or user decision。
- completion signal。
- stop condition status。
- artifact path。
