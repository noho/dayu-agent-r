# Host P8.5 Handoff Plan：P8 Stabilization / ToolRuntime Event Model

## 0. 计划边界

- 当前 gate：`plan`。
- Work unit：P8.5 — P8 Stabilization / ToolRuntime Event Model。
- 当前分支必须保持为 `migration/host-p8-5-stabilization`，远端名为 `github`。
- 本计划只授权后续 implementation agent 修改代码、测试和相关 README；当前 planning agent 只维护本文件。
- 本计划不是 Gateflow controller 输出，不启动 `$gateflow` / `/gateflow`，不重排 gate，不 commit，不 push，不开 PR。

## 1. Goal / Motivation / Success Signal

### Goal

P8.5 在 P9 Session / Run Lifecycle Governance / Public Interface 之前，收口 P8 已落地的 Attempt Lease / Recovery / Multiprocessing、durable memory、trace 与 ToolRuntime 的稳定性尾巴。核心目标是把 `fetch_more` 从具体工具名 RunEventType 中移出，恢复为普通 Host built-in tool，并让 ToolRuntime cursor / truncation / denial 等事实停留在通用运行时机制层。

### Motivation

动机成立，且不是表面修复问题。当前代码把 `fetch_more` 这个具体 framework tool name 编码进 `RunEventType`、serializer、memory projection 和 trace projection：

- `dayu/host/contracts.py:73-75` 定义 `TOOL_FETCH_MORE_REQUESTED` / `TOOL_FETCH_MORE_COMPLETED` / `TOOL_FETCH_MORE_FAILED`。
- `dayu/host/_run_event_serializer.py:668-747` 和 `dayu/host/_run_event_serializer.py:1449-1485` 为这些具体事件维护封闭反序列化映射。
- `dayu/host/_tool_runtime.py:1279-1444` 在 `_append_fetch_requested()`、`_append_fetch_completed()`、`_fetch_failure()` 中追加具体 `fetch_more` RunEvent。
- `dayu/host/_conversation_memory.py:690-741` 和 `dayu/host/_tool_trace_projection.py:166-183` 消费 `ToolFetchMore*Data`，其中 memory projection 还用 `"unknown"` 填补 tool_name。

这与 Host 设计边界冲突：`docs/host/design.md:49-55` 要求 Host/Engine 不懂业务语义，ToolRuntime 治理不应和具体工具权限/业务权限混在一起；`docs/host/design.md:1077-1188` 将 `fetch_more` 定位为 LLM-facing framework tool，不是业务工具，也不进入完整 ToolRegistry。

### Success Signal

P8.5 完成后必须同时满足：

- `RunEventType` 中不再存在任何具体工具名事件，尤其不再存在 `TOOL_FETCH_MORE_REQUESTED` / `TOOL_FETCH_MORE_COMPLETED` / `TOOL_FETCH_MORE_FAILED`。
- `fetch_more` 的 request / result 真源是已有通用 tool-call facts：`TOOL_CALL_REQUESTED` 与 `TOOL_RESULT_ACCEPTED`；Host 不再追加专属 `fetch_more` lifecycle fact。
- `TOOL_RESULT_TRUNCATED` / `TOOL_CURSOR_ISSUED` / `TOOL_CURSOR_EXPIRED` / `TOOL_CURSOR_DENIED` 被明确裁决为通用 ToolRuntime mechanism facts，不并入通用 tool result fact。
- serializer、memory projection、tool trace projection、trace JSONL、测试和 README 均不再依赖 `ToolFetchMore*Data`。
- durable memory startup repair 不再对大库做每个缺失 session 一次全 EventLog 扫描；snapshot row 存在但 payload 损坏时有明确诊断和运维边界。
- ToolTraceObserver 的同步 JSONL / blob I/O 不再在 SQLite observer transaction 内长时间执行；但不引入 P15 required projection enforcement / watchdog / observer claim lease。
- compact / RunInput / trace 的事实语义明确：compact 诊断 fact 与 terminal fact 的非原子取舍有测试覆盖；compact retry 的 `attempt_index` / `iteration_index` 语义固定；RunInput raw payload 不再无界内联进 EventLog 热路径。
- P8 attempt lease / recovery adversarial gaps 有独立测试或明确代码修复，且不把 Host治理语义放入 `dayu.runtime`。
- P8.5 按全新起库处理；旧 `TOOL_FETCH_MORE_*` EventLog 行和测试库数据丢弃，不写兼容 reader、decoder 或 migration。

## 2. Authoritative Decisions

本节是 P8.5 的关键契约裁决。implementation agent 不得自行改选。

### 2.1 ToolRuntime Event Model

1. 删除具体工具名 RunEventType：
   - 删除 `TOOL_FETCH_MORE_REQUESTED`。
   - 删除 `TOOL_FETCH_MORE_COMPLETED`。
   - 删除 `TOOL_FETCH_MORE_FAILED`。
   - 删除对应 `ToolFetchMoreRequestedData` / `ToolFetchMoreCompletedData` / `ToolFetchMoreFailedData` 及 serializer 分支。
   - 不提供兼容 re-export、兼容 wrapper、兼容 decoder 分支。

2. `fetch_more` 作为普通 Host built-in tool 建模：
   - `FRAMEWORK_FETCH_MORE_TOOL_NAME = "fetch_more"` 继续只存在于 tool declaration / HostToolRuntime routing / tests 中。
   - `TOOL_CALL_REQUESTED` 表示 LLM 请求调用 `fetch_more`。
   - `TOOL_RESULT_ACCEPTED` 表示 `fetch_more` 返回成功或失败结果。
   - `_event_translation.py` 中对 `fetch_more` arguments 的 redaction 可以保留，因为它处理的是通用 tool-call fact 的敏感字段，不是具体 RunEventType。

3. ToolRuntime mechanism facts 保留为通用机制事实：
   - `TOOL_RESULT_TRUNCATED` 保留。它描述 Host 对任意 tool result 的截断机制，不是某个工具调用的业务结果。
   - `TOOL_CURSOR_ISSUED` 保留。它描述 Host 为任意 tool result 或 cursor continuation 签发 cursor。
   - `TOOL_CURSOR_EXPIRED` 保留。它描述 Host 拒绝使用过期 cursor。
   - `TOOL_CURSOR_DENIED` 保留。它描述 Host 因 scope / binding / fencing 拒绝 cursor。

4. 上述 cursor facts 必须区分两个 tool-call id：
   - `owner_tool_call_id`：被截断的原始业务 tool call id。
   - `emitting_tool_call_id`：触发本次机制事实的当前 tool call id。首次截断时与 `owner_tool_call_id` 相同；`fetch_more` 派生新 cursor、expired、denied 时为 `fetch_more` 的 tool call id。
   - 如现有字段名需要迁移，使用无兼容的新 schema 名称；不要保留旧字段别名。

5. 不把 mechanism facts 并入 `TOOL_RESULT_ACCEPTED`：
   - 直接原因：`TOOL_RESULT_ACCEPTED` 是 Engine / Host tool loop 接受结果的通用事实；cursor 签发、过期、拒绝、截断是 Host ToolRuntime 资源治理事实。
   - 并入会让 Engine tool result 协议承载 Host cursor lifecycle，反向泄漏 Host 实现细节。
   - P8.5 只修正具体工具名错层，不提前做 P10 ToolRegistry 或 P16 public/internal bundle freeze。

6. EventLog multi-fact partial risk 的裁决：
   - 删除 `TOOL_FETCH_MORE_COMPLETED` 后，原 P8 residual 中“`TOOL_FETCH_MORE_COMPLETED` 成功但 `TOOL_CURSOR_ISSUED` 失败”的具体 partial 风险消失。
   - P8.5 不预设 `append_many` 必须实现。当前预期是：ToolRuntime 在返回给 Engine 前先 append required mechanism facts，因此 mechanism fact append failure 不应产生 successful `ToolCompletedOutcome`。
   - implementation 必须注入 mechanism fact append failure，断言 `HostToolRuntime.execute_tool_call()` 不返回 successful `ToolCompletedOutcome`。
   - 若测试证明 append failure 后仍返回 success，implementation 必须 stop and report；否则禁止实现 `append_many`。
   - compact diagnostic / terminal 的多 fact 风险是独立问题，在 Slice 4 处理，不得混同为 ToolRuntime event model root cause。

7. 类似 `fetch_more` 的特化全面检查：
   - P8.5 必须新增或更新测试，保证 `RunEventType` enum name/value、serializer data-class mapping、memory projection 和 trace projection 不含具体 framework tool name。
   - `FRAMEWORK_FETCH_MORE_TOOL_NAME` 在 tool declaration、schema、HostToolRuntime routing 中允许存在；它不得出现在 `RunEventType` 名称、event data class 名称或 projection 分支类型名中。

### 2.2 Durable Memory Repair

1. 自动修复边界：
   - snapshot row 缺失，且 EventLog 中存在该 session 的 canonical terminal run facts：允许 startup repair 自动重建。
   - snapshot row 存在但 payload JSON 损坏、schema version 不匹配或字段类型非法：startup repair 不得自动覆盖。必须捕获为强类型 diagnostic，例如 `MemoryRepairDiagnostic(kind=CORRUPT_SNAPSHOT, session_id=..., reason=...)`，让运维介入。

2. 运维介入边界：
   - corrupt snapshot row 的默认处理是 typed diagnostic + WARNING 级日志，不 silent ignore，不自动 delete / overwrite。
   - corrupt snapshot diagnostic 不得阻断其它 missing-row repair。
   - `repair_missing_session_snapshots()` 必须返回或暴露包含 repaired session 与 diagnostics 的强类型 report；`startup_reconcile()` 调用方必须能读取 diagnostics。若现有返回值需要调整，使用新强类型返回值，不用 extra payload。
   - 运维修复动作在 P8.5 仅定义为“备份后删除损坏 snapshot row，再由 startup repair 走缺失 row 自动重建”或后续专门 maintenance command。P8.5 不引入用户级 CLI。

3. 容量风险修复：
   - 当前 repair 不能继续按缺失 session 数量重复全 EventLog 扫描。
   - P8.5 必须在 `DurableRunEventStore` 新增 `fetch_events_by_session(...)` 或等价强类型 helper，并配套索引。
   - helper 的 SQL shape 必须是：`WHERE session_id = ? AND kind = ? AND event_position > ? ORDER BY event_position ASC LIMIT ?`。
   - repair missing session list 必须分页或有内部 batch limit，避免一次性收集全库 session id。

### 2.3 Tool Trace / Observer / Projection

1. `ToolTraceObserver.process` 的同步 I/O 边界：
   - 当前 async observer 协议内执行同步 JSONL / blob I/O 是 P8.5 范围内要修正的稳定性问题。
   - P8.5 必须让 non-required tool trace observer 的文件 I/O 不再发生在 SQLite observer checkpoint transaction 内。

2. P8.5 与 P15 的边界：
   - P8.5 做：non-required ToolTraceObserver best-effort decoupling 的最小边界调整；trace I/O 失败不得阻塞 run terminal；checkpoint 与 JSONL/blob 的非原子关系继续用 idempotency key 和 replay 去重承担。
   - P8.5 不做：required projection enforcement、hard-gate、watchdog、durable observer outbox、全局 buffered drain、observer claim lease。
   - observer claim lease 归 P15 / issue #28。P8.5 不引入 observer owner secret、fencing token 或多进程 observer claim 表。

3. Projection model：
   - Tool trace projection 必须从通用 `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` 表达 `fetch_more` 的 request/result。
   - Cursor / truncation facts 作为 annotations 加入 trace record，不再从 `ToolFetchMoreCompletedData` 汇总。
   - Projection 对 partial / missing pair 必须给出稳定 best-effort 记录或明确 skip reason，不得因一个普通 partial trace 破坏 required memory projection。

### 2.4 Compact / RunInput / Trace Semantic Cleanup

1. compact diagnostic fact 与 terminal fact：
   - `CONTEXT_COMPACT_FAILED` 后追加 terminal failure 是两步事实；P8.5 不先假设必须 batch append。
   - implementation 必须补测试覆盖 diagnostic fact 成功但 terminal close 被 fencing / CAS miss 拒绝的路径，并证明 owner / recovery 仍给出唯一 terminal truth。
   - success path 的 `CONTEXT_COMPACT_COMPLETED` 与 `CONTEXT_ATTEMPT_RETRYING` 也必须覆盖孤立 fact 风险；若无直接破坏 terminal truth 的证据，保持现有分步 append 但补充注释和测试。

2. compact retry 的 `RunInputContextSnapshotBuiltData` 语义：
   - `attempt_index` 表示 Host attempt index；compact retry 后递增。
   - `iteration_index` 表示当前 Host attempt 内的 Engine iteration index；每个新 attempt 的首轮 Engine 输入仍为 `0`。
   - `iteration_id` 继续由 `run_id + attempt_index` 派生；不得把 compact retry 伪装成同一 attempt 内连续 iteration。

3. RunInput raw payload 热冷分离：
   - `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 不得继续无界内联完整 raw messages / tool schemas 到 EventLog hot row。
   - P8.5 引入 Host-owned durable raw payload side store，EventLog fact 仅保留 summary、content hash、byte size 和 blob id。
   - writer 是 `LocalRunHarness._append_run_input_context_snapshot_fact` 所在 Host durable append 边界；`RunInputContextFactBuilder` 只构造 raw payload material 与 summary，不持有 storage、不写库。
   - side store write 与 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` EventLog append 必须使用同一个 `HostStorage.transaction()`；如果无法同事务实现，implementation 必须 stop and report。
   - reader 是 `ToolTraceObserver` / trace projection：通过 blob id 从 Host durable side store 读取 raw payload，再写 JSONL/blob。
   - 该 side store 不是 tool trace JSONL，也不是 P15 projection；它属于 Host durable state。
   - 因本项目按新 schema 起库处理，P8.5 不写旧 EventLog raw inline payload 兼容 reader。

4. SSE partial tool call trace：
   - P8.5 不做完整 P15 trace hard gate，但必须让中途失败的 partial tool call 不再表现为“无语义缺口”。
   - SSE partial diagnostic 是 Engine-owned diagnostic data，Host-owned persistence。
   - 不新增具体工具名 RunEventType，不新增 provider-specific RunEventType。
   - 方案固定为：扩展 Engine 现有 provider/protocol failure 事件的数据，加入 bounded `partial_tool_calls` summary；Host `_event_translation.py` 只透传为现有 `PROVIDER_PROTOCOL_ERROR` RunEvent data；`ToolTraceObserver` 从该 data 派生 trace diagnostic。
   - partial summary 只能含 bounded count / id / name fragment / argument size / hash / finish reason，不含 raw argument payload，不进入 memory，不驱动 tool execution。

### 2.5 Attempt Lease / Recovery Hardening

1. `_verify_run_id_matches()` 必须使用独立 reason：
   - 新增 `AttemptFencingReason.RUN_ID_MISMATCH` 或等价强类型枚举值。
   - 不再把 draft.run_id mismatch 归类为 `OWNER_MISMATCH`。

2. `next_attempt_index` 必须有独立测试：
   - 覆盖无 attempt、已有 active attempt、已有 terminal attempt、gap / conflict 情况。
   - 测试直接面向 run state store，不通过 harness 间接覆盖。

3. `_renew_loop` 并发竞争测试：
   - 覆盖 renew 与 terminal close race。
   - 覆盖 owner-lost 已标记后 late renew / late event 不覆盖第一原因。
   - 覆盖 storage exception 分类为 `STORAGE_ERROR`，且不泄漏 background task exception。

4. recovery / fencing coverage：
   - recovery CAS miss 不得关闭新 owner。
   - owner-lost late event 不得追加 attempt-scoped event。
   - terminal override 不得覆盖既有 terminal。
   - expired / denied cursor facts 必须走 attempt-scoped appender fencing。

5. 诊断 / 防御边界：
   - `BUSY` reason 要细化到可诊断 attempt-index conflict，不能只给调用者一个空 reason。
   - BUSY reason 不复用 fencing reason；新增 `AttemptLeaseBusyReason.ATTEMPT_INDEX_CONFLICT = "attempt_index_conflict"`，并在 `AttemptLeaseResult` 中以独立字段表达，例如 `busy_reason`。
   - `lease_context` 参数必须校验：`run_id` 非空，`attempt_index >= 0`，`recovered_from_attempt_id` 非空时不得为空字符串。
   - 这些契约属于 `dayu.host`，不得迁入 `dayu.runtime`。

## 3. Direct Code Evidence

| Area | Direct evidence | Why it matters |
| --- | --- | --- |
| RunEventType concrete fetch_more | `dayu/host/contracts.py:71-78` | `TOOL_FETCH_MORE_*` 与 cursor/truncation facts 同列为 public RunEventType，说明具体工具名进入 EventLog contract。 |
| FetchMore data classes | `dayu/host/contracts.py:393-440` | `ToolFetchMoreCompletedData` / `ToolFetchMoreFailedData` 直接绑定具体工具名。 |
| ToolRuntime data union | `dayu/host/contracts.py:478-486` | `ToolRuntimeEventData` union 收纳 `ToolFetchMore*Data`，使 projection / serializer 被具体工具污染。 |
| Serializer closed mapping | `dayu/host/_run_event_serializer.py:668-747`、`dayu/host/_run_event_serializer.py:1449-1485` | decoder 和 data class mapping 都要同步删除 fetch_more-specific data。 |
| fetch_more ordinary tool route | `dayu/host/_tool_runtime.py:403-429`、`dayu/host/_tool_runtime.py:548-576` | `execute_tool_call()` 通过普通 tool call name 路由到 framework `fetch_more`，说明可用通用 tool-call facts 建模。 |
| fetch_more multi-fact append | `dayu/host/_tool_runtime.py:719-865` | `_fetch_more()` 当前追加 requested / completed / cursor facts；成功返回前 deferred commit 的顺序是判断是否需要 batch append 的直接依据。 |
| append helpers | `dayu/host/_tool_runtime.py:1188-1459` | 当前每类 ToolRuntime fact 各自 append，具体 `TOOL_FETCH_MORE_*` 在这里产生。 |
| Engine already records generic fetch_more call | `dayu/host/_event_translation.py:117-139` | translation 已对 `fetch_more` 的 `TOOL_CALL_REQUESTED` 做 redaction，说明通用 tool call fact 已存在。 |
| framework tool schema | `dayu/contracts/tool_declaration.py:29`、`dayu/contracts/tool_declaration.py:161-196` | `fetch_more` 是 LLM-facing tool schema，不是 RunEventType。 |
| no legacy public handle | `tests/host/test_host_public_api_surface.py:106-118` | 当前测试锁定 public surface 不暴露旧 `fetch_more` handle；P8.5 不恢复。 |
| memory projection polluted | `dayu/host/_conversation_memory.py:690-741` | memory projection 为 `ToolFetchMore*Data` 造 memory fact 且 tool_name 用 `"unknown"`，说明错层影响 durable memory。 |
| trace projection polluted | `dayu/host/_tool_trace_projection.py:93-112`、`dayu/host/_tool_trace_projection.py:166-183`、`dayu/host/_tool_trace_projection.py:670-691` | trace group 和 summary 只理解 `ToolFetchMoreCompletedData`，失败/partial 语义不完整。 |
| async observer sync I/O | `dayu/host/_tool_trace_projection.py:141-159` | `process` 是 async 协议，但 docstring 明确内部仍做同步 JSONL / 文件写入。 |
| sync JSONL / blob writes | `dayu/host/_tool_trace_jsonl_sink.py:149-209` | 每行 `flush+fsync`，raw blob `os.replace`，属于阻塞文件 I/O。 |
| observer transaction boundary | `dayu/host/_event_observer.py:216-271` | observer process 在 storage transaction 内执行后推进 checkpoint；非 required trace I/O 会拉长 SQLite transaction。 |
| durable repair startup | `dayu/host/_durable_harness.py:148-176` | startup reconcile 会自动调用 memory repair。 |
| durable repair missing row only | `dayu/host/_conversation_memory_durable.py:263-288` | docstring 明确只修 snapshot row 缺失，不修 row 存在但 payload 损坏。 |
| repair full scan risk | `dayu/host/_conversation_memory_durable.py:349-402` | 缺失 session 收集和 per-session event fetch 依赖全 EventLog 扫描，容量风险直接存在。 |
| corrupt snapshot invisible to repair | `dayu/host/_conversation_memory_durable.py:517-537`、`dayu/host/_conversation_memory_durable.py:628-684` | row 存在但 decode / schema error 会抛错；missing-row repair 看不到该类损坏。 |
| existing repair tests | `tests/host/test_phase8_durable_memory_recovery.py:642-855` | 当前覆盖 row 删除 repair 和 intentional empty snapshot；未覆盖 corrupt row startup 边界。 |
| compact failure split append | `dayu/host/_run_harness.py:1450-1638` | compact failed / terminal failed、completed / retrying 都是分步 append，需测试孤立 fact 取舍。 |
| RunInput context fact append | `dayu/host/_run_harness.py:2367-2455` | `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 按 attempt / iteration append，语义要固定。 |
| RunInput raw inline | `dayu/host/_run_input_context_fact.py:76-160`、`dayu/host/contracts.py:545-585` | raw messages / tool schemas 内联进 EventLog data TEXT，造成热冷混合和体积增长。 |
| SSE partial gap | `dayu/engine/runners/openai/sse_parser.py:284-329`、`dayu/engine/runners/openai/sse_parser.py:448-500`、`dayu/engine/runners/openai/runner.py:420-545` | parser 会先见到 tool call delta；byte stream 中途失败时 runner 产生 HTTP/protocol failure，但没有完整 tool-call completed 语义。 |
| run id mismatch reason | `dayu/host/_attempt_supervisor.py:383-418` | `_verify_run_id_matches()` 当前把 run_id mismatch 归入 `OWNER_MISMATCH`。 |
| next attempt index | `dayu/host/_run_state_store.py:928-951` | `next_attempt_index()` 是独立 store 能力，需要独立测试而不是只走 harness。 |
| renew loop | `dayu/host/_attempt_supervisor.py:935-1041` | `_renew_loop` 的 storage error、fenced、owner-lost race 都在这里发生。 |
| lease context validation gap | `dayu/host/_attempt_supervisor.py:511-600` | `lease_context` 当前入口缺少显式参数校验。 |

## 4. Non-goals

- 不恢复 legacy public `fetch_more` handle。
- 不提前实现完整 P10 ToolRegistry。
- 不把 ToolRuntime 业务语义放入 `dayu.runtime`。
- 不把具体工具名继续编码成 `RunEventType`。
- 不在缺少直接证据时断言 EventLog batch append 一定需要或一定不需要。
- 不做 P9 Session / Run lifecycle admission。
- 不做 P16 public/internal bundle interface freeze。
- 不做 P15 hard-gate / required projection enforcement / watchdog。
- 不引入 observer claim lease、observer owner secret、observer fencing token。
- 不为旧 schema / 旧 EventLog payload 写兼容 reader。
- 不把 durable memory corrupt snapshot 自动覆盖为“修复成功”。

## 5. Affected Files / Modules

### Host contracts / serializer

- `dayu/host/contracts.py`
- `dayu/host/__init__.py`
- `dayu/host/_run_event_serializer.py`
- `tests/host/test_phase6_run_event_serializer.py`
- `tests/host/test_phase7_contract_serializer.py`
- `tests/host/test_host_public_api_surface.py`

### ToolRuntime / projections

- `dayu/host/_tool_runtime.py`
- `dayu/host/_event_translation.py`
- `dayu/host/_conversation_memory.py`
- `dayu/host/_tool_trace_projection.py`
- `dayu/host/_tool_trace_jsonl_sink.py`
- `dayu/host/_event_observer.py`
- `tests/host/test_phase5_multiturn_no_governance_smoke.py`
- `tests/host/test_phase8_tool_runtime_fencing.py`
- `tests/host/test_phase2_tool_runtime_eventlog.py`
- `tests/host/test_phase2_tool_runtime_truncation.py`
- `tests/host/test_phase2_tool_runtime_boundary.py`
- `tests/host/test_phase3_conversation_memory_projection.py`
- `tests/host/test_phase7_tool_trace_projection.py`
- `tests/host/test_phase7_tool_trace_eventlog_source.py`
- `tests/host/test_phase7_tool_trace_jsonl_sink.py`

### Durable memory / storage schema

- `dayu/host/_conversation_memory_durable.py`
- `dayu/host/_durable_harness.py`
- `dayu/host/_durable_event_store.py`
- storage schema module located by `rg "host_run_events|host_conversation_memory_snapshots" dayu/host`
- `tests/host/test_phase8_durable_memory_recovery.py`

### Compact / RunInput / trace payload

- `dayu/host/_run_harness.py`
- `dayu/host/_run_input_context_fact.py`
- Host durable storage schema / transaction module
- RunInput context fact tests
- compact retry / failure tests

### Engine SSE partial diagnostic

- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/engine/agent.py`
- `tests/engine/contracts/test_runner_events.py`
- `tests/engine/runners/openai/test_sse_tool_call_stream.py`
- `tests/engine/runners/openai/test_stream_idle.py`
- `tests/engine/runners/openai/test_protocol_error.py`
- `tests/engine/runners/openai/test_http_error_event.py`
- `tests/host/test_phase7_tool_trace_projection.py`
- `tests/host/test_phase7_tool_trace_eventlog_source.py`

### Attempt lease / recovery

- `dayu/host/_attempt_lease.py`
- `dayu/host/_attempt_supervisor.py`
- `dayu/host/_run_state_store.py`
- `tests/host/test_phase8_attempt_supervisor.py`
- `tests/host/test_phase8_attempt_fencing.py`
- `tests/host/test_phase8_attempt_recovery.py`
- `tests/host/test_phase8_multiprocess_stress.py`

### Docs

- `dayu/host/README.md`
- `tests/README.md`
- `docs/host/migration-plan.md`
- `docs/host/design.md` only if implementation changes stable Host design boundary, not for mere code detail。

## 6. Contract / Serializer / RunEventType / Projection / Test Impact

### Contract impact

- Remove `RunEventType.TOOL_FETCH_MORE_REQUESTED` / `TOOL_FETCH_MORE_COMPLETED` / `TOOL_FETCH_MORE_FAILED`。
- Remove `ToolFetchMoreRequestedData` / `ToolFetchMoreCompletedData` / `ToolFetchMoreFailedData`。
- Remove these types from `RunEventData` / `ToolRuntimeEventData` unions and package root exports。
- Keep `FRAMEWORK_FETCH_MORE_TOOL_NAME` and `framework_fetch_more_tool_schema()` in `dayu.contracts.tool_declaration`。
- Keep or reshape internal `ToolFetchMoreRequest` / `ToolFetchMoreResult` only if `_tool_runtime.py` still needs typed helper data；do not export them from `dayu.host.__all__` unless a direct public contract test justifies it。
- Reshape cursor data classes to include `owner_tool_call_id` and `emitting_tool_call_id`。
- SSE partial diagnostic uses Engine-owned diagnostic data and Host-owned persistence：extend existing Engine provider/protocol failure event data with bounded `partial_tool_calls` summary, then have Host `_event_translation.py` pass it through existing `PROVIDER_PROTOCOL_ERROR` RunEvent data. Do not add a new concrete-tool or provider-specific RunEventType.

### Serializer impact

- Delete decoder branches for removed fetch_more-specific event types。
- Delete mapping entries in `_DATA_CLASS_BY_TYPE`。
- Add serializer coverage for reshaped cursor facts and RunInput raw payload side-store references。
- Add negative tests ensuring `TOOL_FETCH_MORE_*` strings are absent from serialized event type values and enum names。

### Projection impact

- Memory projection must stop manufacturing memory facts from `ToolFetchMoreRequestedData` / `CompletedData` / `FailedData`。
- Memory projection may summarize `fetch_more` through generic `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` only when that is already part of normal tool-call conversation memory policy；cursor facts remain Host diagnostic mechanism facts。
- Tool trace projection must group by generic tool call id and annotate truncation / cursor facts via `owner_tool_call_id` and `emitting_tool_call_id`。
- Tool trace must represent `fetch_more` success and failure using generic tool result outcome, not `ToolFetchMoreCompletedData`。
- Required memory projection must remain isolated from non-required trace observer failures。

### Test impact

- Existing tests expecting `TOOL_FETCH_MORE_*` must be rewritten to assert generic tool-call facts plus mechanism facts。
- Public API surface tests must lock that legacy public `fetch_more` handle is still absent。
- Add guard tests for no concrete framework tool name in `RunEventType` / serializer mapping / projection type branches。
- Add durable repair capacity and corrupt-row tests。
- Add ToolTraceObserver transaction-boundary / best-effort failure tests。
- Add compact split append race tests。
- Add RunInput payload side-store tests。
- Add SSE partial tool-call diagnostic tests。
- Add attempt hardening adversarial tests.

## 7. Schema / Index Impact

P8.5 has schema impact. Because project policy says schema 变更按全新 schema 起库处理，本计划禁止旧库兼容读取。旧 `TOOL_FETCH_MORE_*` EventLog 行、旧 inline raw payload 行和 P8 测试库数据全部按 development branch schema 修正丢弃，不写兼容 reader、decoder 或 migration。

### Required schema/index changes

1. Durable memory repair index：
   - Add index supporting `session_id + canonical kind + event_position` lookup on `host_run_events`。
   - Required shape：`CREATE INDEX ... ON host_run_events(session_id, kind, event_position)`。
   - Add `DurableRunEventStore.fetch_events_by_session(...)` or an equivalent strongly typed helper whose SQL uses `WHERE session_id = ? AND kind = ? AND event_position > ? ORDER BY event_position ASC LIMIT ?`。
   - If existing schema has different column names, implementation must use actual schema names and keep the same access pattern.

2. RunInput raw payload side store：
   - Add Host-owned durable table for RunInput context raw payload blobs.
   - Required columns：`run_id`、`attempt_index`、`iteration_id`、`blob_role`、`blob_id`、`content_hash`、`byte_size`、`payload_json`、created ordering column。
   - Required uniqueness：`blob_id` unique；`run_id + attempt_index + iteration_id + blob_role` unique。
   - EventLog fact stores only `blob_id` / `content_hash` / `byte_size` and summary fields.
   - Writer：`LocalRunHarness._append_run_input_context_snapshot_fact` in the Host durable append boundary.
   - Builder：`RunInputContextFactBuilder` only returns raw payload material / summary and never receives storage.
   - Transaction：side-store write and `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` EventLog append must share the same `HostStorage.transaction()`。
   - Reader：`ToolTraceObserver` / trace projection reads payload by blob id from the Host durable side store before writing JSONL/blob.

### No schema changes for P8.5

- No observer claim lease table。
- No required projection policy table。
- No P9 run lifecycle admission table。
- No P10 ToolRegistry table。
- No public/internal bundle interface freeze table。

## 8. Implementation Slices

### Slice 1 — ToolRuntime generic fetch_more event model

**Purpose**

一次性完成 `fetch_more` event model 的纵向 contract migration。该 slice 同时删除具体工具名 RunEvent contract、迁移 HostToolRuntime runtime 行为、同步 serializer / projections / tests，保证 slice 完成后系统可运行、pyright 和 affected tests 可通过。禁止把 contract removal 拆成会制造不可运行中间态的临时兼容层。

**Implementation prompt**

```text
你是 Dayu Host P8.5 implementation agent。只实现 Slice 1：ToolRuntime generic fetch_more event model。

必须先读取 AGENTS.md、CLAUDE.md、docs/host/phase8.5-plan.md，并遵守中文 docstring、严格类型、分层约束。

这是一个完整 contract migration slice。完成后必须让 pyright 与 affected tests 可通过；不允许临时 compatibility reader、wrapper、re-export、bridge event 或“先删 contract、后续 slice 再修 runtime/projection”的中间态。

目标：
1. 从 dayu/host/contracts.py 删除 RunEventType.TOOL_FETCH_MORE_REQUESTED / TOOL_FETCH_MORE_COMPLETED / TOOL_FETCH_MORE_FAILED。
2. 删除 ToolFetchMoreRequestedData / ToolFetchMoreCompletedData / ToolFetchMoreFailedData，以及它们在 RunEventData / ToolRuntimeEventData union 中的成员。
3. 从 dayu/host/_run_event_serializer.py 删除这些 data 的 decoder、encoder mapping 和 _DATA_CLASS_BY_TYPE 条目。
4. 从 dayu/host/__init__.py 删除这些 event data 的 public export；不要添加兼容 re-export。
5. 保留 dayu.contracts.tool_declaration.FRAMEWORK_FETCH_MORE_TOOL_NAME 和 framework_fetch_more_tool_schema()。
6. 保留或调整内部 ToolFetchMoreRequest / ToolFetchMoreResult 的使用，但不得恢复 legacy public fetch_more handle。
7. 修改 dayu/host/_tool_runtime.py，删除 _append_fetch_requested、_append_fetch_completed、_fetch_failure 对专属 RunEventType 的依赖；HostToolRuntime 不再追加 fetch_more-specific RunEvent。
8. HostToolRuntime 仍通过 execute_tool_call() 接收普通 tool call；当 request.call.name == FRAMEWORK_FETCH_MORE_TOOL_NAME 时执行 framework fetch_more。
9. fetch_more request/result 的持久化真源必须是 Engine/Host tool loop 已有的 generic TOOL_CALL_REQUESTED 和 TOOL_RESULT_ACCEPTED。
10. cursor / truncation facts 保留为 generic ToolRuntime mechanism facts：TOOL_RESULT_TRUNCATED、TOOL_CURSOR_ISSUED、TOOL_CURSOR_EXPIRED、TOOL_CURSOR_DENIED。
11. reshape TOOL_CURSOR_ISSUED / TOOL_CURSOR_EXPIRED / TOOL_CURSOR_DENIED data，使其同时包含 owner_tool_call_id 与 emitting_tool_call_id。首次截断两者相同；fetch_more 派生/拒绝/过期时 emitting_tool_call_id 是 fetch_more call id。
12. TOOL_RESULT_TRUNCATED 保持通用 mechanism fact；如字段名需要同步，使用无兼容新字段。
13. 修复 dayu/host/_conversation_memory.py：不得再引用 ToolFetchMore*Data；不得再用 tool_name="unknown" 表示 fetch_more 专属 memory fact。
14. 修复 dayu/host/_tool_trace_projection.py：fetch_more trace 用 generic tool-call request/result 生成；cursor / truncation annotations 来自 generic mechanism facts。
15. 更新 tests/host/test_phase6_run_event_serializer.py、tests/host/test_phase7_contract_serializer.py 和 tests/host/test_host_public_api_surface.py：RunEventType enum name/value 和 serializer mapping 中不得包含 TOOL_FETCH_MORE 或 tool_fetch_more。
16. 更新 ToolRuntime / memory projection / tool trace projection / P5 smoke / P8 fencing 相关测试：fetch_more 成功、失败、expired、denied、next cursor 四类路径都用 generic tool-call facts + generic mechanism facts 断言。
17. 增加回归测试：注入 mechanism fact append failure，断言 HostToolRuntime.execute_tool_call() 不返回 successful ToolCompletedOutcome。当前预期是 ToolRuntime 在返回给 Engine 前先 append required mechanism facts，因此不需要 append_many。
18. 若测试证明 append failure 后仍返回 success，立即 stop and report；否则禁止实现 append_many。
19. 增加 guard test：RunEventType / serializer / projections 不包含具体 framework tool name 分支。
20. P8.5 按全新起库处理；旧 TOOL_FETCH_MORE_* EventLog 行和旧测试库数据丢弃，不写兼容 reader、decoder 或 migration。

禁止：
- 不实现 append_many，除非第 18 条 stop condition 被直接测试证据触发并由 controller 重新裁决。
- 不提前实现 P10 ToolRegistry。
- 不恢复 legacy fetch_more public handle。
- 不把 ToolRuntime 语义放入 dayu.runtime。
- 不新增 compatibility reader / wrapper / re-export。

完成后必须运行受影响 tests、grep guards 和 pyright，报告命令与结果。
```

**Acceptance**

- `rg "TOOL_FETCH_MORE|ToolFetchMore(Requested|Completed|Failed)" dayu/host tests/host` 只允许出现在迁移计划文档或负向测试字符串中。
- Serializer tests 证明新 contract 可 round-trip。
- `fetch_more` 成功、失败、expired、denied、next cursor 四类路径都有 generic tool-call facts 和 mechanism facts 测试。
- Trace JSONL 中 `fetch_more` 是普通 tool call record；cursor annotations 来自 mechanism facts。
- Memory projection 不再生成 tool_name `"unknown"` 的 fetch_more 专属 memory fact。
- mechanism fact append failure 注入后，`HostToolRuntime.execute_tool_call()` 不返回 successful `ToolCompletedOutcome`。

### Slice 2 — Durable memory repair stabilization

**Purpose**

修复 startup repair 的容量风险，并定义 corrupt snapshot row 的自动修复 / 运维介入边界。

**Implementation prompt**

```text
你是 Dayu Host P8.5 implementation agent。只实现 Slice 2：Durable memory repair stabilization。

目标：
1. 定位 host_run_events schema 真源，新增支持按 session_id + kind + event_position 查询 canonical events 的索引，索引 shape 必须是 (session_id, kind, event_position)。
2. 在 DurableRunEventStore 新增 fetch_events_by_session(...) 或等价强类型 helper，SQL shape 必须是 WHERE session_id = ? AND kind = ? AND event_position > ? ORDER BY event_position ASC LIMIT ?。
3. 用该 helper 替换 _fetch_canonical_events_for_session() 对全 EventLog 的 per-session 扫描。
4. _collect_missing_session_ids() 必须分页或使用 batch limit；不得一次性收集全库 session id。
5. startup repair 继续只自动修复 snapshot row 缺失。
6. snapshot row 存在但 payload JSON 损坏、schema version 不匹配或字段类型非法时，不得自动 overwrite。必须捕获为强类型 diagnostic，例如 MemoryRepairDiagnostic(kind=CORRUPT_SNAPSHOT, session_id=..., reason=...)。
7. repair_missing_session_snapshots() 必须返回或暴露包含 repaired session 与 diagnostics 的强类型 report；startup_reconcile() 调用方必须能读取 diagnostics。corrupt diagnostic 记录 WARNING 级日志，且不得阻断其它 missing-row repair。
8. 测试覆盖：
   - missing row 自动 repair。
   - 多 session repair 不做 per-session 全库扫描；可通过 fake store 调用计数或 SQL helper 单测证明。
   - corrupt payload row 在 startup_reconcile 中被诊断出来且不会被自动覆盖。
   - corrupt payload row 不阻断其它 missing-row repair。
   - intentional empty snapshot row 不被误判为缺失或 corrupt。

禁止：
- 不新增用户级 CLI。
- 不为旧 schema 写兼容读取。
- 不 silent delete / overwrite corrupt snapshot。

完成后运行 durable memory 相关 tests 和 pyright，报告命令与结果。
```

**Acceptance**

- repair 对缺失 row 是自动恢复。
- corrupt row 是 repair required，不是假成功。
- 大库扫描路径被索引化 / session-filter helper 替代。

### Slice 3 — Tool trace observer I/O boundary

**Purpose**

把 non-required tool trace 的同步文件 I/O 从 observer checkpoint SQLite transaction 中移出，限定 P8.5 与 P15 边界。

**Implementation prompt**

```text
你是 Dayu Host P8.5 implementation agent。只实现 Slice 3：Tool trace observer I/O boundary。

目标：
1. 阅读 dayu/host/_event_observer.py、_tool_trace_projection.py、_tool_trace_jsonl_sink.py，确认 ProjectionCoordinator 当前在 storage transaction 内 await observer.process()。
2. 修改 observer drain 边界：required observer 保持事务语义；non-required ToolTraceObserver 的 JSONL / blob I/O 不得在 SQLite transaction 内执行。
3. 如需使用 executor，只允许最小使用 asyncio.to_thread 或等价标准库方式隔离阻塞文件 I/O；不得引入 durable outbox、claim lease、watchdog、required projection enforcement。
4. checkpoint 与 JSONL/blob 仍允许非原子，但必须依赖 existing idempotency_key / replay 去重；在 docstring 中说明该取舍。
5. ToolTraceObserver I/O 失败必须让 observer checkpoint 标记为 best-effort failure 或保留可重试状态；不得阻塞 run terminal，也不得影响 required memory projection。
6. 测试覆盖：
   - trace sink fsync/write failure 不影响 run terminal。
   - required observer 仍在事务内推进 checkpoint。
   - non-required trace observer 不在同一个 SQLite transaction 内执行阻塞 sink 调用，可用 fake storage transaction marker 验证。

禁止：
- 不实现 P15 observer claim lease。
- 不实现 required projection hard gate。
- 不实现 watchdog 或全局 buffered drain。

完成后运行 observer / trace projection 相关 tests 和 pyright，报告命令与结果。
```

**Acceptance**

- ToolTraceObserver 仍是 best-effort observer。
- 文件 I/O 与 SQLite checkpoint transaction 的边界清晰。
- P15 residual 明确保留为 observer claim / outbox / hard-gate，而不是被 P8.5 半实现。

### Slice 4 — Compact / RunInput payload / semantic cleanup

**Purpose**

固定 compact retry 语义，处理 RunInput raw payload 热冷混合，并测试 compact split append 的原子性取舍。

**Implementation prompt**

```text
你是 Dayu Host P8.5 implementation agent。只实现 Slice 4：Compact / RunInput payload / semantic cleanup。

目标：
1. 修改 RunInputContextSnapshotBuiltData：EventLog fact 不再内联完整 raw messages / raw tool schemas；只保留 summary、blob id、content hash、byte size 等热字段。
2. 新增 Host-owned durable RunInput raw payload side store。writer 必须是 LocalRunHarness._append_run_input_context_snapshot_fact 所在 Host durable append 边界。
3. RunInputContextFactBuilder 只构造 raw payload material / summary，不持有 storage、不写库；fact 只携带 blob id / content hash / byte size / summary。
4. side store write 与 RUN_INPUT_CONTEXT_SNAPSHOT_BUILT EventLog append 必须使用同一个 HostStorage.transaction()；如果无法同事务实现，立即 stop and report。
5. reader 必须是 ToolTraceObserver / trace projection：通过 blob id 从 Host durable side store 读取 raw payload，再写 JSONL/blob。
6. 固定 compact retry 语义：
   - attempt_index 是 Host attempt index，compact retry 后递增。
   - iteration_index 是当前 attempt 内 Engine iteration index，新 attempt 首轮为 0。
   - iteration_id 继续由 run_id + attempt_index 派生。
7. 为 compact failure/success split append 增加 adversarial tests：
   - CONTEXT_COMPACT_FAILED 已 append 但 terminal close 被 fencing/CAS miss 拒绝。
   - CONTEXT_COMPACT_COMPLETED 已 append 但 CONTEXT_ATTEMPT_RETRYING append 失败。
   - recovery 后仍只有唯一 terminal truth。
8. 如果测试证明 split append 会产生错误 terminal truth，停下回报，需要重新裁决最小事务边界；否则保持分步 append 并补充中文 docstring / 注释说明取舍。

禁止：
- 不写旧 inline raw payload 兼容 reader。
- 不把 raw payload 放进 tool trace JSONL 作为唯一真源。
- 不提前做 P9 Session lifecycle。

完成后运行 compact / RunInput / serializer / storage 相关 tests 和 pyright，报告命令与结果。
```

**Acceptance**

- EventLog 中 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` row 不含完整 raw messages / raw tool schemas。
- raw payload side store 可按 blob id 读取并校验 hash / byte size。
- compact retry attempt / iteration 语义有测试锁定。

### Slice 5 — SSE partial tool-call trace diagnostic

**Purpose**

让 provider stream 中途失败后的 partial tool-call 具备可追踪诊断语义，但不驱动 tool execution，不进入 memory。

**Implementation prompt**

```text
你是 Dayu Host P8.5 implementation agent。只实现 Slice 5：SSE partial tool-call trace diagnostic。

目标：
1. 阅读 dayu/engine/runners/openai/sse_parser.py、runner.py、dayu/engine/agent.py，定位 tool call delta 已出现但 RunnerToolCallsCompletedData 尚未产生时的失败路径。
2. diagnostic ownership 固定为 Engine-owned diagnostic data + Host-owned persistence。
3. 扩展 Engine 现有 provider/protocol failure 事件的数据，加入 bounded partial_tool_calls summary；不要新增具体工具名 RunEventType，不要新增 provider-specific RunEventType。
4. partial summary 只能含 bounded count / id / name fragment / argument size / hash / finish reason；不得含 raw argument payload。
5. Host _event_translation.py 只透传为现有 PROVIDER_PROTOCOL_ERROR RunEvent data；ToolTraceObserver 从该 data 派生 trace diagnostic，使 trace 中明确显示“partial tool call observed then stream failed”。
6. 测试覆盖：
   - SSE 在 tool_call_delta 后网络读失败。
   - SSE 在 partial arguments 后 provider protocol error。
   - 没有 completed tool call 时不会生成 TOOL_CALL_REQUESTED。
   - trace 有 partial diagnostic，memory 无 partial tool call。

禁止：
- 不实现 P15 hard-gate。
- 不把 partial delta 当成可执行 tool call。
- 不把 provider-specific raw payload 无界写入 EventLog。
- 不新增具体工具名或 provider-specific RunEventType。

完成后运行 engine openai runner/parser tests、host translation/trace tests 和 pyright，报告命令与结果。
```

**Acceptance**

- partial tool-call failure 不再是 trace 语义空洞。
- diagnostic 是通用、typed、bounded 的 trace/debug fact。

### Slice 6a — Attempt lease contract hardening

**Purpose**

收口 attempt lease 的小型契约修正：run_id mismatch reason、BUSY reason 与入口参数校验。

**Implementation prompt**

```text
你是 Dayu Host P8.5 implementation agent。只实现 Slice 6a：Attempt lease contract hardening。

目标：
1. 在 dayu/host/_attempt_lease.py 新增独立 RUN_ID_MISMATCH reason；修改 _verify_run_id_matches()，不再用 OWNER_MISMATCH 表达 draft.run_id mismatch。
2. BUSY reason 不复用 fencing reason；新增 AttemptLeaseBusyReason.ATTEMPT_INDEX_CONFLICT = "attempt_index_conflict"，并在 AttemptLeaseResult 中以独立字段表达，例如 busy_reason。
3. acquire_new_attempt / lease_context 的 attempt-index conflict 路径必须填充 busy_reason。
4. 为 lease_context 增加参数校验：run_id 非空，attempt_index >= 0，recovered_from_attempt_id 非空时不得为空字符串。
5. 更新 contract / acquire_new_attempt / lease_context 相关测试，断言 RUN_ID_MISMATCH、busy_reason、参数校验错误。

禁止：
- 不把 BUSY reason 塞进 AttemptFencingReason。
- 不把 attempt lease contracts 移到 dayu.runtime。
- 不做 P9 run lifecycle admission。
- 不改 recovery / renew_loop adversarial coverage；这些属于 Slice 6b。

完成后运行 phase8 attempt lease / supervisor / fencing 相关 tests 和 pyright，报告命令与结果。
```

**Acceptance**

- run_id mismatch 有独立 reason。
- BUSY attempt-index conflict 通过 AttemptLeaseBusyReason.ATTEMPT_INDEX_CONFLICT 表达。
- lease_context 参数校验有确定性测试。

### Slice 6b — Attempt adversarial coverage

**Purpose**

补齐 P8 attempt lease / recovery 的 adversarial tests，不混入新的 lease contract 设计。

**Implementation prompt**

```text
你是 Dayu Host P8.5 implementation agent。只实现 Slice 6b：Attempt adversarial coverage。

前置：Slice 6a 已完成。

目标：
1. 为 _run_state_store.next_attempt_index() 增加独立 tests：无 attempt、active attempt、terminal attempt、gap/conflict。
2. 为 _renew_loop 增加并发竞争 tests：
   - renew 与 terminal close race。
   - owner-lost 后 late renew / late event 不覆盖第一原因。
   - storage exception 分类 STORAGE_ERROR，不泄漏 background task exception。
3. 补齐 recovery CAS miss、owner-lost late event、terminal override、expired/denied cursor fencing 的直接测试。

禁止：
- 不把 attempt lease contracts 移到 dayu.runtime。
- 不做 P9 run lifecycle admission。
- 不用 sleep-heavy flaky stress test 替代确定性 race test；优先 fake clock / fake store / barrier。
- 不再修改 BUSY reason 或 RUN_ID_MISMATCH contract；若 Slice 6a contract 不足，stop and report。

完成后运行 phase8 attempt / fencing / recovery / tool runtime fencing tests 和 pyright，报告命令与结果。
```

**Acceptance**

- 关键 race 和 fencing gap 有确定性测试。
- attempt-scoped ToolRuntime cursor facts 均受 owner fencing 保护。

### Slice 7 — Docs, migration notes, final validation

**Purpose**

同步 P8.5 后的稳定契约，避免 README 残留旧术语和旧事件模型。

**Implementation prompt**

```text
你是 Dayu Host P8.5 implementation agent。只实现 Slice 7：Docs, migration notes, final validation。

前置：Slice 1-6b 已完成。

目标：
1. 更新 dayu/host/README.md：
   - 删除 TOOL_FETCH_MORE_REQUESTED / COMPLETED / FAILED。
   - 说明 fetch_more 是普通 Host built-in tool，request/result 由通用 tool-call facts 表达。
   - 说明 cursor/truncation facts 是通用 ToolRuntime mechanism facts。
   - 说明 durable memory repair 的自动/运维边界。
   - 说明 ToolTraceObserver best-effort I/O 边界。
2. 更新 tests/README.md：
   - 只在测试分层或运行方式变化时更新；不要罗列实现细节。
3. 更新 docs/host/migration-plan.md：
   - 将 P8.5 状态、residual risk owner 变化和 non-goals 同步为当前事实。
   - 明确 P8.5 按全新 schema 起库处理，旧 TOOL_FETCH_MORE_* EventLog 行和测试库数据丢弃，不写兼容 reader / decoder / migration。
4. 仅当 Host 设计稳定边界发生变化时，更新 docs/host/design.md；不要把源码说明书搬进 design。
5. 运行完整受影响测试、pyright 和 grep guard。

禁止：
- 不维护时间敏感“近期更新”。
- 不写未来设计。
- 不新增旧术语兼容说明。

完成后输出 implementation completion report，格式见本计划末尾。
```

**Acceptance**

- README 不再宣称 `tool_fetch_more_requested/completed/failed` 是 canonical facts。
- migration-plan residual risk registry 中 P8.5 项被关闭或转交明确 owner。

## 9. Review Gates

Implementation 完成后必须经过以下 review gates：

1. Contract gate：
   - `RunEventType` 没有具体工具名。
   - serializer 没有 `ToolFetchMore*Data` 映射。
   - package root 没有兼容 re-export。
   - 该 gate 与 ToolRuntime / Projection gate 同属 Slice 1，必须在同一 slice review 中一起验证，不允许只删除 contract 后留下 runtime/projection 断裂。

2. ToolRuntime gate：
   - `fetch_more` request/result 只通过 generic tool-call facts 表示。
   - cursor / truncation mechanism facts 有 `owner_tool_call_id` 与 `emitting_tool_call_id`。
   - 没有无证据引入 `append_many`。

3. Projection gate：
   - memory projection 不使用 `"unknown"` 伪 tool_name 表示 fetch_more。
   - trace projection 成功、失败、expired、denied、partial 都有稳定语义。
   - non-required trace observer failure 不影响 required memory projection。

4. Durable memory gate：
   - missing row 自动 repair。
   - corrupt row 不自动 overwrite，诊断明确。
   - repair 不再 per missing session 全库扫描。

5. Compact / RunInput gate：
   - EventLog hot fact 不内联 raw payload。
   - compact retry attempt / iteration 语义测试固定。
   - split append failure / fencing 测试证明 terminal truth 唯一。

6. Attempt gate：
   - `RUN_ID_MISMATCH` 独立 reason。
   - BUSY attempt-index conflict 通过 `AttemptLeaseBusyReason.ATTEMPT_INDEX_CONFLICT` / `AttemptLeaseResult.busy_reason` 表达，不复用 fencing reason。
   - renew/terminal/recovery/cursor fencing adversarial tests 覆盖。
   - lease_context 参数校验覆盖。

7. Docs gate：
   - `dayu/host/README.md` 与代码事实一致。
   - `tests/README.md` 只在职责范围内更新。
   - `docs/host/migration-plan.md` residual owner 更新。

## 10. Validation Commands

所有命令都必须先激活虚拟环境：

```bash
source .venv/bin/activate
```

Recommended targeted validation：

Slice 1 必须把 contract、serializer、ToolRuntime、memory projection、tool trace projection 与 public surface 相关测试作为同一组运行，不能只运行 contract tests：

```bash
pytest tests/host/test_host_public_api_surface.py
pytest tests/host/test_phase6_run_event_serializer.py tests/host/test_phase7_contract_serializer.py
pytest tests/host/test_phase2_tool_runtime_eventlog.py tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase2_tool_runtime_boundary.py
pytest tests/host/test_phase3_conversation_memory_projection.py
pytest tests/host/test_phase7_tool_trace_projection.py tests/host/test_phase7_tool_trace_eventlog_source.py tests/host/test_phase7_tool_trace_jsonl_sink.py
pytest tests/host/test_phase5_multiturn_no_governance_smoke.py tests/host/test_phase8_tool_runtime_fencing.py
pytest tests/host/test_phase8_durable_memory_recovery.py
pytest tests/host/test_phase8_attempt_lease_store.py tests/host/test_phase8_attempt_supervisor.py tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_recovery.py
pytest tests/host/test_phase8_multiprocess_stress.py
pytest tests/engine/contracts/test_runner_events.py
pytest tests/engine/runners/openai/test_sse_tool_call_stream.py tests/engine/runners/openai/test_stream_idle.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_http_error_event.py
pytest tests/engine
pyright
```

Required grep guards：

```bash
rg "TOOL_FETCH_MORE|tool_fetch_more|ToolFetchMore(Requested|Completed|Failed)" dayu tests
rg "RunEventType\\..*FETCH_MORE" dayu tests
rg "unknown" dayu/host/_conversation_memory.py dayu/host/_tool_trace_projection.py
```

Expected grep result：

- 第一条只允许命中文档、负向测试字符串或仍被批准保留的 internal request/result helper；不得命中 `RunEventType`、serializer mapping、projection implementation。
- 第二条不得命中生产代码。
- 第三条不得命中用于填补 fetch_more tool_name 的实现分支。

## 11. Residual Risk Owner Changes

| Risk | Before P8.5 | P8.5 target owner/status |
| --- | --- | --- |
| fetch_more concrete RunEventType | P8 residual, Host ToolRuntime event model | Closed by Slice 1；owner Host ToolRuntime contract。 |
| fetch_more multi-fact partial completed/issued | P8 residual, suspected EventLog batch issue | Reclassified：after model fix, require direct regression evidence before batch append；owner Host ToolRuntime tests。 |
| cursor/truncation fact placement | Open model question | Decided：generic ToolRuntime mechanism facts；owner Host contracts/projection。 |
| durable repair full scan | P8 residual | Closed or reduced by session-filter index/helper；owner durable memory store。 |
| corrupt snapshot row invisible to repair | P8 residual | Reclassified as typed `MemoryRepairDiagnostic(kind=CORRUPT_SNAPSHOT, ...)` + WARNING log；owner durable memory startup reconcile。 |
| ToolTraceObserver sync I/O in async protocol | P8 residual / P15 candidate | P8.5 handles non-required trace I/O transaction boundary；durable outbox/claim lease remains P15。 |
| observer claim lease | P15 / issue #28 | Explicitly not P8.5。 |
| compact split diagnostic/terminal append | P8.5 semantic cleanup | Covered by adversarial tests；batch append only if direct evidence。 |
| RunInput raw payload hot row growth | P7 tradeoff / P8.5 cleanup | Closed by raw payload side store written from `LocalRunHarness._append_run_input_context_snapshot_fact` in the same `HostStorage.transaction()`；owner Host durable storage。 |
| SSE partial tool call trace gap | Engine runner / Host trace | Reduced by Engine-owned `partial_tool_calls` summary on existing provider/protocol failure data + Host-owned `PROVIDER_PROTOCOL_ERROR` persistence；owner Engine runner + Host trace translation。 |
| attempt lease contract gaps | P8 residual | Closed by Slice 6a；owner Host attempt lease/supervisor。 |
| attempt lease adversarial gaps | P8 residual | Closed by Slice 6b tests；owner Host attempt supervisor/store。 |
| old `TOOL_FETCH_MORE_*` EventLog rows | P8 development branch data | Explicitly discarded under fresh schema；no compatibility reader / decoder / migration。 |

## 12. Docs Update Decision

P8.5 implementation must update docs because code changes hit documented Host contracts and tests:

- `dayu/host/README.md`：必须更新。P8.5 修改 Host ToolRuntime facts、durable memory repair、ToolTraceObserver boundary、attempt lease diagnostics。
- `tests/README.md`：仅当新增测试分层、命令或维护约定变化时更新；不要机械罗列文件。
- `docs/host/migration-plan.md`：必须更新 P8.5 状态与 residual risk owner。
- `docs/host/design.md`：只有当 implementation 改变设计级稳定边界时更新；若只是实现现有 P8.5 裁决，不展开源码细节。
- 根目录 `README.md`：默认不更新，除非新增或改变用户可见 CLI / 配置 / trace render 入口。

## 13. Stop Conditions

implementation agent 遇到以下任一情况必须停止并回报，不得自行选择关键契约：

- mechanism fact append failure 注入后，`HostToolRuntime.execute_tool_call()` 仍返回 successful `ToolCompletedOutcome`。
- Durable memory corrupt snapshot 自动覆盖与 typed diagnostic / WARNING log / non-blocking repair report 之间出现不可兼容需求。
- RunInput raw payload side store 无法与 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` EventLog append 共用同一个 `HostStorage.transaction()`。
- SSE partial diagnostic 需要把 partial delta 当成可执行 `TOOL_CALL_REQUESTED` 才能实现。
- Non-required ToolTraceObserver decoupling 需要引入 P15 claim lease / watchdog / required projection policy。
- Attempt lease hardening 需要把 Host owner / fencing contracts 移入 `dayu.runtime`。
- BUSY attempt-index conflict 只能通过复用 `AttemptFencingReason` 才能表达，无法使用独立 `AttemptLeaseBusyReason` / `busy_reason`。
- pyright 需要通过 `Any`、`object`、无类型签名或忽略注释才能通过。
- 受影响测试必须靠兼容旧 schema / 旧 event type 才能通过。

## 14. Implementation Completion Report Format

Implementation agent 完成后必须按以下格式报告：

```text
P8.5 implementation report

Changed:
- <按 slice 列出生产代码变更>

Contracts:
- <RunEventType / serializer / data class / projection contract 变化>

Schema/index:
- <新增或修改的 table/index，或说明无>

Tests:
- <新增/更新测试文件>

Validation:
- source .venv/bin/activate
- <pytest command>: <pass/fail>
- pyright: <pass/fail>
- grep guards: <pass/fail>

Docs:
- <更新的 README / design / migration docs>

Residual risks:
- <仍保留的 P15/P9/P16 风险及 owner>

Stop conditions hit:
- <none 或具体项>
```
