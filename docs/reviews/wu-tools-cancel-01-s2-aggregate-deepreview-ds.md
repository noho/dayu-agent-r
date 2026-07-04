# WU-TOOLS-CANCEL-01 S2 Aggregate Deepreview — AgentDS

## Scope

- **Mode**: current changes
- **Branch**: `phase/wu-tools-cancel-01`
- **Base**: `main`
- **Review gate**: S2 aggregate deepreview gate（S2A1–S2D 已通过单 slice review，S2E aggregate validation 已完成；本轮对合并结果做 adversarial deepreview）
- **Output file**: `docs/reviews/wu-tools-cancel-01-s2-aggregate-deepreview-ds.md`
- **Included scope**: `dayu/contracts/tool_execution.py`、`dayu/contracts/tool_declaration.py`、`dayu/runtime/interruptible_process.py`、`dayu/runtime/tools_discovery.py`（digest 段）、`dayu/host/tool_runtime.py`（declaration-backed factory / process capsule / accept barrier）、`dayu/host/dispatch.py`（production wiring）、`dayu/tools/doc_tools.py`（process target）、`dayu/fins/tools/fins_tools.py`（read process target）、`dayu/fins/tools/download_tools.py`、`dayu/fins/tools/upload_tools.py`、`dayu/fins/tools/preprocess_tools.py`（awaiting async_direct 声明）、`dayu/tools/web/web_tools.py`（process target）、`dayu/tools/web/web_playwright_backend.py`（Playwright worker boundary）、`tests/contracts/test_tool_declaration.py`、`tests/contracts/test_package_exports.py`、`tests/runtime/test_tools_discovery.py`、`tests/runtime/test_tools_discovery_digest.py`、`tests/runtime/test_interruptible_process.py`、`tests/host/test_toolruntime_executor.py`、`tests/host/test_active_cancel_dispatch.py`、`tests/tools/test_doc_tools_provider.py`、`tests/fins/test_fins_storage_provider.py`、`tests/fins/test_fins_ingestion_tools.py`、`tests/tools/web/test_web_tools_provider.py`、`dayu/README.md`、`dayu/host/README.md`、`dayu/fins/README.md`、`tests/README.md`
- **Excluded scope**: `docs/reviews/*`（review artifact 不审自身）、`docs/host/issues-implementation-control.md`（控制文档不修改）、Engine 内部实现（不涉及 capability）、WU-WAIT-03 / activation hook（不在本 WU scope）
- **Parallel review coverage**: 无；本轮由 AgentDS 单人逐链路走读，未使用 subagent 并行

## 真源对齐

本轮对齐以下设计真源与已接受裁决：

- `docs/host/design.md`：Host ToolRuntime 是工具执行治理 owner；Engine 只消费 `ToolExecutor`、`ToolSchema`、`BatchToolExecutionContext`。
- `docs/engine/design.md`：Engine 不拥有工具注册表、不消费 `ToolDefinition`、不执行工具级治理；`tool_execution_timeout_seconds` 是唯一 Engine 工具超时真源。
- `docs/host/wu-tools-cancel-01-typed-execution-capability-plan.md`：S2 切片设计、process-backed envelope shape、stop conditions、residual risks。
- `docs/reviews/wu-tools-cancel-01-s2e-aggregate-validation-codex.md`：S2E validation 结果、production execution mode matrix、residual risk adjudication、stop condition status。
- Accepted commits：S2A1 `32030ca9`、S2A2 `0fea8da0`、S2B `03e546f5`、S2C `834b0df6`、S2D `94b3c196`。

## Review Method

本轮沿以下七条审查维度逐一走读，每维独立给出 PASS / NEEDS_FIX 裁决与直接证据：

1. typed execution closed loop（无 Engine / LLM-facing schema 泄漏）
2. 生产关键路径阻塞 I/O 消除（direct callable 仅为测试/非生产 fallback）
3. cancel / timeout / late-result accept barrier 跨工具族证据
4. residual risk 分类与归属完整性
5. README / design sync
6. AGENTS.md 分层、类型、docstring 约束
7. 验证矩阵完整性

每条维度均基于直接代码路径走读，不作间接推断。

---

## 1. Typed Execution Closed Loop

**裁决：PASS**

### 1.1 ToolDefinition.execution → DeclaredToolExecutionCapsuleFactory → ProcessBackedToolExecutionCapsule

直接证据链：

1. `dayu/contracts/tool_execution.py:100-143`：`AsyncDirectToolExecutionCapability`、`ThreadBackedToolExecutionCapability`、`ProcessBackedToolExecutionCapability` 三者构成 `ToolExecutionCapability` 封闭联合。所有字段均为强类型，无 `Any`/`object`/`dict`/raw extra payload。

2. `dayu/contracts/tool_declaration.py:90-116`：`ToolDefinition.execution` 是 `ToolExecutionCapability` 类型字段，`default_factory=AsyncDirectToolExecutionCapability`。`@tool(...)` decorator 中 `execution=None` 时默认 `AsyncDirectToolExecutionCapability()`。

3. `dayu/host/tool_runtime.py:1544-1581`：`DeclaredToolExecutionCapsuleFactory` 从 `effective_bundle.definitions_by_name` 按 `call.name` 查找 `ToolDefinition`，调用 `_declared_capsule_for_execution(definition.execution, ...)`。

4. `dayu/host/tool_runtime.py:1590-1624`：`_declared_capsule_for_execution` 按 `isinstance` 分发：`AsyncDirectToolExecutionCapability` → `AsyncDirectToolExecutionCapsule`，`ThreadBackedToolExecutionCapability` → `ThreadBackedToolExecutionCapsule`，`ProcessBackedToolExecutionCapability` → `ProcessBackedToolExecutionCapsule(target)`（其中 `target = execution.target_factory.build_process_target(call, _process_backed_context_from_batch_context(context))`），未知类型 → `TypeError` fail closed。

5. `dayu/host/tool_runtime.py:1753-1857`：`ProcessBackedToolExecutionCapsule` 持有 `InterruptibleProcessHandle`，子进程返回 JSON 信封 → `_tool_outcome_from_process_envelope(envelope)` 映射为 `ToolExecutionOutcome`。

6. `dayu/host/dispatch.py:3316-3349`：生产 dispatch **不**传入 `execution_capsule_factory`，因此 `tool_runtime.py:3984-3987` 使用 `DeclaredToolExecutionCapsuleFactory(effective_bundle)` 作为默认值。

**语义闭环验证**：`ToolDefinition.execution`（声明真源）→ `DeclaredToolExecutionCapsuleFactory`（Host 内部 wiring）→ `_declared_capsule_for_execution`（capability-to-capsule 映射）→ capsule.run()（实际执行）→ JSON 信封（子进程）→ `_tool_outcome_from_process_envelope`（父进程映射）→ `ToolExecutionOutcome`。闭环完整，无不经过强类型的路径。

### 1.2 Engine 契约隔离

直接证据：

- `grep -rn "ToolExecutionCapability\|ToolExecutionMode\|ProcessBacked\|process_backed" dayu/engine/` 返回零命中（`tool_execution_timeout_seconds` 是 timeout 策略字段，不是 capability）。
- Engine 只通过 `ToolExecutor.execute(BatchToolExecutionRequest)` 与工具环境 handshake，不消费 `ToolDefinition` 或其任何字段。
- Engine `AgentRunRequest.tool_schemas` 是 `tuple[ToolSchema, ...]`，不含 capability。

### 1.3 LLM-facing Schema 隔离

直接证据：

- `ToolDefinition.to_tool_schema()` 返回 `self.schema`，不投影 `execution`。
- `_tool_execution_json_value` 只在 `dayu/runtime/tools_discovery.py:463-485` 中使用，用于 digest 稳定 JSON shape；不被 LLM 消费。
- 所有 `execution` 字段 docstring 均标注“不进入 LLM-facing schema”。

### 1.4 子进程信封走向一致性

- Host capsule parser：`_PROCESS_ENVELOPE_STATUS_FIELD = "status"`、`_PROCESS_ENVELOPE_COMPLETED_STATUS = "completed"`、`_PROCESS_ENVELOPE_FAILED_STATUS = "failed"`、`_PROCESS_ENVELOPE_COMPLETED_VALUE_FIELD = "value"`、`_PROCESS_ENVELOPE_FAILED_ERROR_TYPE_FIELD = "error_type"`、`_PROCESS_ENVELOPE_FAILED_MESSAGE_FIELD = "message"`（`tool_runtime.py:250-255`）。
- Doc process target：`_DOC_PROCESS_STATUS_FIELD = "status"` 等（`doc_tools.py:77-82`），字符串值一致。
- Fins process target：`_FINS_PROCESS_STATUS_FIELD = "status"` 等（`fins_tools.py:79-84`），字符串值一致。
- Web process target：`_WEB_PROCESS_STATUS_FIELD = "status"` 等（`web_tools.py:164-169`），字符串值一致。

**风险点**：三个工具族各自复制 process envelope 字段常量，与 Host parser 常量形成四份独立副本。虽然当前字符串值一致，测试覆盖充分，但若 envelope shape 演进需同步修改四处。这是必要性取舍（业务工具不得 import Host internals），但在 Finding 01 中记为低风险维护关注。

---

## 2. 生产关键路径阻塞 I/O 消除

**裁决：PASS**

### 2.1 Doc 工具族

- 五个 Doc tools 的 `ToolDefinition.execution` 均为 `ProcessBackedToolExecutionCapability(target_factory=...)`（`doc_tools.py:2195-2197` 调用点，所有 Doc tool 构造均传入 `process_target_factory`）。
- `_run_doc_callable_fallback`（`doc_tools.py:880-919`）仍包含 `asyncio.to_thread(business_call, token)`，但函数 docstring 明确标注“生产默认路径不再经过本函数……本函数只保留给直接调用 `ToolDefinition.callable` 的测试和非生产 fallback”。生产路径通过 `DeclaredToolExecutionCapsuleFactory` → `ProcessBackedToolExecutionCapsule` → 子进程执行，不经过该 fallback。
- `tests/tools/test_doc_tools_provider.py:273-287`：`test_all_doc_tool_definitions_declare_process_backed_execution` 验证五个 definition 的 `execution` 是 `ProcessBackedToolExecutionCapability`。`test_doc_process_target_factory_is_pickle_round_trippable` 验证序列化。

### 2.2 Fins read 工具族

- 九个 Fins read tools 的 `ToolDefinition.execution` 均为 `ProcessBackedToolExecutionCapability(target_factory=process_target_factory)`（`fins_tools.py:374` 等九个 `@tool(...)` 调用点均传入 `execution=ProcessBackedToolExecutionCapability(...)`）。
- `_run_fins_read_callable_fallback`（`fins_tools.py:985-1023`）仍包含 `asyncio.to_thread(business_call, cancellation_token)`，但函数 docstring 同样标注为 fallback 路径。
- `tests/fins/test_fins_storage_provider.py:731-746`：`test_fins_read_definitions_declare_process_backed_execution` 验证九个 definition 声明 `process_backed`。`test_fins_read_process_target_runs_in_spawned_child` 验证子进程内通过 `DefaultFinsRuntime.create(workspace_root=Path(...))` 重建只读 runtime。

### 2.3 Web 工具族

- `search_web` 和 `fetch_web_page` 的 `ToolDefinition.execution` 均为 `ProcessBackedToolExecutionCapability(target_factory=process_target_factory)`（`web_tools.py:1204-1206`、`1243-1245`）。
- `_call_search_web` 和 `_call_fetch_web_page` 中仍存在 `asyncio.to_thread(...)`（`web_tools.py:1378-1387`、`1475-1481`），但这些是 `ToolDefinition.callable` 的直接实现，生产路径不经过。
- `_WebProcessTarget.__call__` 在子进程内重建 `ToolCallRequest` 并调用 `_search_web_business` / `_fetch_web_page_business`（同步函数），不经过 asyncio。

### 2.4 Fins awaiting 工具族（download / preprocess / upload）

- `download_tools.py:176`、`upload_tools.py:164`、`preprocess_tools.py:174`：均声明 `execution=AsyncDirectToolExecutionCapability()`。
- 这三类工具返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`，不是 blocking read 工具。它们保持在 awaiting lifecycle（由 WU-WAIT-03 / activation hook 管理），不纳入 process-backed closeout。这是 plan 明确规定的非目标——正确。

### 2.5 Thread-backed guard

- `ThreadBackedToolExecutionCapability.production_safe_non_cooperative_cancel: Literal[False] = False`（`tool_execution.py:124`）：显式 guard 防止把 thread_backed 当作生产非协作 blocking cancel 证据。
- `tests/contracts/test_tool_declaration.py`：覆盖 thread-backed guard 值恒为 `False`。
- 当前无任何生产工具声明 `thread_backed`。

---

## 3. Cancel / Timeout / Late-result Accept Barrier

**裁决：PASS**

### 3.1 Host 通用 interrupt 路径

`tool_runtime.py:3175-3253`：`_dispatch_tool_call_with_bounds` 固定流程：

1. 检查 batch deadline 是否已耗尽 → `_runtime_timeout_policy_decision` 治理失败。
2. 检查 cancellation token 是否已取消 → `_runtime_cancelled_policy_decision` 治理失败。
3. 通过 `DeclaredToolExecutionCapsuleFactory` 创建 capsule。
4. `wait_for_or_cancel(capsule_task, token, timeout_seconds)` 等待结果。
5. `WaitCompleted`：返回子进程 outcome，然后 `capsule.close()`。
6. `WaitCancelled`：`request_interrupt` → `terminate` → 若 terminate 未完成则 `kill` → `capsule_task.cancel()` → `capsule.close()`，返回 `_governed_failure_outcome`。
7. `WaitTimedOut`：同 cancel 路径的 interrupt 流程，返回 `_governed_failure_outcome`。

### 3.2 Process capsule interrupt escalation

`tool_runtime.py:1753-1857`：`ProcessBackedToolExecutionCapsule`：

- `request_interrupt`：no-op（子进程不共享 Host token）。
- `terminate`：`self._handle.terminate(grace_seconds=0.2)`。
- `kill`：`self._handle.kill(grace_seconds=0.2)`。
- `close`：`self._handle.close()`，若进程仍存活则 best-effort kill。

中断升级链：cancel/timeout → `request_interrupt` → `terminate(0.2s)` → 若未退出 → `kill(0.2s)` → `capsule_task.cancel()` → `close()`。

### 3.3 Late-result accept barrier（跨工具族证据）

- Host generic test：`tests/host/test_toolruntime_executor.py:1577`：`test_tool_runtime_process_backed_cancel_does_not_wait_for_natural_completion` — 真实 `DefaultToolRuntimeFactory` + declaration-backed factory + 慢速 process target；取消后 accept 到的是 Host-governed cancel，不是子进程结果。
- Host timeout test：`tests/host/test_toolruntime_executor.py:1797`：`test_tool_runtime_process_backed_cancel_kills_when_terminate_is_ignored` — terminate 被忽略时升级 kill，返回 governed cancel。
- Doc test：`tests/tools/test_doc_tools_provider.py`：取消后不接受 late result。
- Fins read test：`tests/fins/test_fins_storage_provider.py:884`：`test_fins_read_process_backed_cancel_drops_late_result` — ToolRuntime 取消真实 Fins process target 后不接受 late result。
- Web test：`tests/tools/web/test_web_tools_provider.py`：延迟 HTTP server 返回不被 accept。
- Fins awaiting tools：不经过普通 completed-result accept barrier；它们走 awaiting accept / wait-resume lifecycle。

### 3.4 子进程信封治理

`tool_runtime.py:6532-6637`：`_tool_outcome_from_process_envelope`：

- 非 dict → `_PROCESS_BACKED_TOOL_MALFORMED_ENVELOPE_ERROR` fail closed。
- status 非 str → malformed fail closed。
- `"completed"` → `_completed_outcome_from_process_envelope`（必须有 `value` key，否则 malformed）。
- `"failed"` → `_failed_outcome_from_process_envelope`（必须有非空 `error_type` 和 `message`，否则 malformed）。
- `"awaiting"`、`"cancelled"`、`"timeout"`、`"host_cancelled"` → `_PROCESS_BACKED_TOOL_UNSUPPORTED_ENVELOPE_ERROR` fail closed。
- 未知 status → 同 unsupported fail closed。

子进程不得自报 Host-governed 状态。该治理与 plan 一致。

---

## 4. Residual Risk 分类与归属

**裁决：PASS with observations**

### 4.1 S2E 记录的 residual risks（逐项重审）

| Risk | S2E decision | DS re-review | 证据 |
|---|---|---|---|
| Web process cold-start cost | Accepted, non-blocking | **同意**。性能优化不改变 contract，可后续 worker pool 处理 | Plan §Residual Risks 原文记录 |
| Process failed envelope 无 structured `hint` field | Accepted, non-blocking | **同意**。`_failed_outcome_from_process_envelope` 当前 `hint=None`，子进程的 hint 信息已拼入 `message` 文本 | `tool_runtime.py:6603-6606` |
| Playwright nested process cleanup | Accepted with explicit residual | **同意**。Web process target 在子进程内重建 `requests.Session`，Playwright 路由不可 pickle，fail closed。parent 取消→kill 子进程后，OS 级浏览器子进程可能残留。这是已知测试缺口 | `web_tools.py:469-524`（`_WebProcessTarget.__call__` 内调用 `_execute_web_process_business_value` → `_fetch_web_page_business` → fetch orchestrator → Playwright fallback 不可序列化）；S2D review 已裁决 Web 走了 requests-only process-backed + Playwright fail-closed |
| `query_xbrl_facts` spawned-child fixture | Low residual, non-blocking | **同意**。9 个 Fins read tools 的 process-boundary 机制已验证；`query_xbrl_facts` 的特定 XBRL fixture 是非阻塞覆盖率扩面 | `tests/fins/test_fins_storage_provider.py:858` |
| Doc FIFO fixture | Accepted residual | **同意**。allowed-root boundary 不变，process-backed cancel/timeout 防御有效 | S2B review 裁决 |
| Thread-backed 误用 guard | Closed | **确认**。`Literal[False]` + test guard | `tool_execution.py:124` |
| Fins WAITING tools 不是 process-backed | Closed as intentional | **确认**。plan 明确非目标；awaiting lifecycle 独立管理 | `download_tools.py:176`、`upload_tools.py:164`、`preprocess_tools.py:174` |

### 4.2 是否还有应修复但被误判为 non-blocking 的项

逐项排查计划中列出的 concern 项：

- **Playwright nested process cleanup**：当前 Web process target 使用 `_fetch_web_page_business`（同步），Playwright 回退逻辑位于 fetch orchestrator 内。S2D 选择了 requests-only process-backed 执行 + Playwright unpicklable worker fail-closed。生产路径不会在子进程内启动 Playwright browser tree，因为 Playwright worker 不可 pickle 穿越 spawn boundary。`tests/tools/web/test_web_tools_provider.py` 的 unpicklable worker fail-closed 测试已覆盖。**判定：不误判，当前风险可控**。
- **hint-in-message**：`_failed_outcome_from_process_envelope` 中 `hint=None`，子进程的 hint 信息拼入 `message` 字符串。LLM-facing hint 仍由 Host ToolRuntime 上层 `_observe_llm_inline_tool_result` 或 `_governed_failure_outcome` 产生。**判定：不误判，非阻塞**。
- **Fins query_xbrl spawned-child fixture**：process-boundary 机制已验证（`test_fins_read_process_target_runs_in_spawned_child` 和 `test_fins_read_financial_statement_runs_in_spawned_child`）。**判定：不误判，非阻塞**。
- **Process envelope constants 碎片化**：Doc/Fins/Web 各自复制常量，但值一致且由测试覆盖。这是架构设计取舍（业务工具不得 import Host），不是实现疏忽。**判定：低风险维护关注**（见 Finding 01）。

### 4.3 所有 residual risk 是否有 owner

- Playwright cleanup → Later Web/Playwright cleanup smoke or stress test
- hint-in-message → Later Host process envelope contract hardening
- Fins XBRL fixture → Later Fins XBRL fixture expansion
- Doc FIFO → Later Doc test strategy/security review
- Web cold-start → Later performance work
- Thread guard → Closed
- Fins WAITING → WU-WAIT-03 / existing lifecycle

全部有 owner 或已 closed。无 orphan residual。

---

## 5. README / Design Sync

**裁决：PASS**

### 5.1 各 README 同步状态

| README | 关键更新 | 匹配程度 |
|---|---|---|
| `dayu/README.md:173` | `ToolExecutionCapability` 进入公共契约清单；明确“execution capability 只声明 Host / ToolRuntime 选择执行边界所需的运行期能力，不进入 LLM-facing tool schema” | 与实现一致 |
| `dayu/host/README.md:372` | ToolRuntime 默认从 effective `ToolDefinition.execution` 选择 capsule；`async_direct`/`thread_backed`/`process_backed` 三种模式说明；process-backed 子进程 JSON 信封映射规则；execution capability 不进入 Engine-facing `ToolSchema` | 与实现一致 |
| `dayu/fins/README.md:501` | Read path 九个 tools 生产执行形态为 `process_backed`；子进程通过 `DefaultFinsRuntime.create` 重建只读仓储；不跨进程序列化 runtime/repository/cache/lock/token | 与实现一致 |
| `tests/README.md:146-179` | Contracts 测试覆盖 execution capability、process-backed context/target/envelope pickle round-trip；Doc/Fins/Web provider tests 覆盖 process-backed 声明、序列化、spawned-child、cancel late-result 不接受 | 与实现一致 |

### 5.2 是否存在 public contract / developer boundary 文档缺口

- `ProcessBackedToolContext`、`ProcessBackedToolTarget`、`ProcessBackedToolTargetFactory` 均在 `dayu/contracts/__init__.py` 的 `__all__` 中导出。
- `ToolExecutionMode`、各 capability dataclass 已导出。
- 工具族开发者需要实现的契约（`ProcessBackedToolTargetFactory.build_process_target`）在 `tool_execution.py` docstring 中有完整的中文说明。
- Host 开发者需要的 wiring 知识在 `dayu/host/README.md` 中有覆盖。
- 无缺口。

### 5.3 无需更新的文档

- `docs/host/design.md`：本 WU 在 plan 和 implementation 中未修改 Host public cancel command、Run/Attempt 状态机、EventLog event type 或 durable schema，无需更新设计真源。
- `docs/engine/design.md`：Engine 边界未变更，无需更新。
- 根 `README.md`：本 WU 未改变 CLI/Web/WeChat 入口、命令参数、默认输出通道、日志定位或最终用户工作流，不触发更新。

---

## 6. AGENTS.md 约束检查

**裁决：PASS**

### 6.1 分层约束

- `dayu.contracts.tool_execution` 不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` → 通过。
- `dayu.runtime.interruptible_process` 只依赖 `dayu.contracts.json_value` 与标准库 → `dayu.runtime` import boundary 通过。
- `dayu.tools.doc_tools` / `dayu.fins.tools.*` / `dayu.tools.web.*` import `dayu.contracts` 公共契约，不 import `dayu.host.*` → 通过。
- `dayu.host.tool_runtime` import `dayu.contracts` 公共契约 + `dayu.runtime.interruptible_process` → Host → contracts/runtime 方向正确。
- 无反向依赖。

### 6.2 类型约束

- `tool_execution.py`：`grep -rn "object\|Any"` 零命中。
- 所有新增 dataclass 使用 `frozen=True, slots=True`。
- 所有新增 Protocol 有完整类型标注。
- `ToolExecutionCapability: TypeAlias = AsyncDirectToolExecutionCapability | ThreadBackedToolExecutionCapability | ProcessBackedToolExecutionCapability` 是封闭联合。

### 6.3 Docstring 约束

- 所有新增模块、类、Protocol、dataclass、函数、方法均有中文 docstring，至少包含参数、返回值、异常说明。
- 所有 execution capability 字段 docstring 均标注“不进入 LLM-facing schema”、“不进入 stable digest”（或“进入 stable digest”如 applicable）。
- 所有 process target / factory docstring 均标注“必须可序列化，不得捕获 repository/runtime/session 对象”。

### 6.4 无兼容胶水 / wrapper

- `grep -rn "wrapper\|facade\|alias\|compat\|backward\|old_" dayu/contracts/tool_execution.py dayu/contracts/tool_declaration.py` 零命中。
- S2A1 已通过 `rg -n "ToolDefinition\(" dayu tests` 扫描所有直接构造站点并迁移，不保留旧接口兼容。

### 6.5 无过度设计

- `ToolExecutionCapability` 仅三种成员，对应三种已验证的执行形态。
- `ProcessBackedToolContext` 仅五个标量字段，不包含治理对象。
- JSON 信封仅 completed / failed 两种业务状态。
- 无通用 lifecycle supervisor、跨 provider 平台、durable follower ledger 或新的 public await contract 被引入。

---

## 7. 验证矩阵完整性

**裁决：PASS**

### 7.1 逐 slice 验证对照

| Slice | Plan 要求 | 实际覆盖 | 判定 |
|---|---|---|---|
| S2A1 | contracts tool execution tests；discovery digest tests；直接构造站点迁移；pickle round-trip | `tests/contracts/test_tool_declaration.py` 覆盖 capability 默认/thread guard/process context-target-envelope pickle；`tests/contracts/test_package_exports.py` 覆盖 white-list；`tests/runtime/test_tools_discovery_digest.py` 覆盖 async/thread/process digest shape | 通过 |
| S2A2 | Host declaration-backed factory wiring；context 投影不含 token；Engine projection 不含 capability | `tests/host/test_toolruntime_executor.py` 覆盖：declared async direct default factory、declared thread-backed factory、capsule build failure bypasses accept、process-backed completion/failure/malformed/unsupported/Host-governed envelope、cancel 不等待自然完成、timeout governed failure、terminate ignored 升级 kill、default factory uses declared process-backed | 通过 |
| S2B | Doc process target cancel/timeout focused tests；五个 tools 声明 process-backed | `tests/tools/test_doc_tools_provider.py` 覆盖：五个 definition `process_backed` 声明、factory/target pickle round-trip、不携带 lock/processor、cancel 不接受 late result | 通过 |
| S2C | Fins read spawned-child `DefaultFinsRuntime.create` feasibility；九个 tools 声明 process-backed；九条路径至少覆盖 fast/processor/table/XBRL | `tests/fins/test_fins_storage_provider.py` 覆盖：九个 definition `process_backed` 声明、factory/target pickle、spawned child `DefaultFinsRuntime` 重建、`get_financial_statement` spawned child、fast/processor/table path、cancel 不接受 late result | 通过。`query_xbrl_facts` 的特定 XBRL instance 夹具为已知 residual |
| S2D | Web process-backed 或 async_direct close proof；Playwright fail-closed | `tests/tools/web/test_web_tools_provider.py` 覆盖：两个 definition `process_backed` 声明、factory/target pickle、spawned child success、cancel 不接受 late result、Playwright unpicklable worker fail closed、timeout 标量序列化 | 通过 |
| S2E | 合并运行；aggregate interrupt test；pyright；git diff --check | S2E validation artifact 记录：合并测试 219 passed + 92 passed、pyright 0 errors、git diff --check 通过 | 通过 |

### 7.2 是否遗漏 S2A1/S2A2 contract/discovery or affected provider tests

- S2A1 contract 测试：`tests/contracts/test_tool_declaration.py` 覆盖 capability declaration → 通过。
- S2A1 discovery digest 测试：`tests/runtime/test_tools_discovery_digest.py` 覆盖 execution capability JSON shape → 通过。
- S2A2 Host factory wiring 测试：`tests/host/test_toolruntime_executor.py` 已覆盖 declaration-backed factory、context projection、Engine-facing schema 不含 capability → 通过。
- 受影响 provider tests：Doc/Fins/Web provider 测试均已验证新 `execution` 字段 → 通过。
- **无遗漏**。

### 7.3 Aggregate late-result accept barrier 是否覆盖所有 process-backed 工具族

- Host generic（`test_toolruntime_executor.py`）：覆盖通用 process capsule 状态机。
- Doc（`test_doc_tools_provider.py`）：覆盖 ToolRuntime cancel + Doc process target late result。
- Fins（`test_fins_storage_provider.py`）：覆盖 ToolRuntime cancel + Fins process target late result。
- Web（`test_web_tools_provider.py`）：覆盖 ToolRuntime cancel + 延迟 HTTP response late result。
- S2E 决定不加 aggregate serial test，因为 code sharing 已通过共享 Host accept barrier 实现，再测一次只是重复验证相同机制——判断合理。

---

## Findings

### DS-AGG-F01 [低] — Process envelope 常量碎片化

- **入口/函数**: `_tool_outcome_from_process_envelope`（Host parser）、Doc `_DocProcessTarget.__call__`、Fins `_FinsReadProcessTarget.__call__`、Web `_WebProcessTarget.__call__`
- **文件(行号)**: `dayu/host/tool_runtime.py:250-258`（Host parser 常量）、`dayu/tools/doc_tools.py:77-82`（Doc 常量）、`dayu/fins/tools/fins_tools.py:79-84`（Fins 常量）、`dayu/tools/web/web_tools.py:164-169`（Web 常量）
- **输入场景**: 未来 process envelope shape 需要新增字段（如 `hint`、`diagnostic` 等）时。
- **实际分支**: 常量定义分别位于四个模块，无单一契约真源。
- **预期行为**: Envelope shape 应只有一个定义真源；其它层从该真源引用。
- **实际行为**: 业务工具不能 import Host internals（这是正确的架构约束），因此各自复制字符串常量。当前值一致且有测试覆盖，但演进风险存在。
- **直接证据**: 四个模块的 `_*_PROCESS_*` 常量字符串值相同，但常量名互不知晓。
- **影响**: 低。当前生产正确，但若 envelope shape 演进，需要人工确保四处同步修改。已有 S2E residual risk 记录。
- **建议改法和验证点**: 不属于当前 WU 修复范围。建议后续 Host process envelope contract hardening 时考虑将 envelope field names 以 `Final[str]` 形式稳定在 `dayu.contracts.tool_execution`（或新增最小 envelope contract 模块），使业务工具可以从 contracts 层引用常量的字符串值而非重复定义。验证点：常量字符串值 grep 确认零漂移。
- **修复风险（低）**: 纯粹是常量提升，不改逻辑。但需要在 contracts 层定义最小 envelope shape contract，需要裁决契约归属。
- **严重程度（低）**: 已有测试覆盖确保值一致，不是当前阻塞问题。

### DS-AGG-F02 [低] — Process capsule terminate/kill grace 常量硬编码 0.2s，高负载下可能过度升级 kill

- **入口/函数**: `ProcessBackedToolExecutionCapsule.terminate` / `ProcessBackedToolExecutionCapsule.kill`
- **文件(行号)**: `dayu/host/tool_runtime.py:325-326`
- **输入场景**: 高负载系统（慢盘 I/O、CPU 争抢）下，子进程 terminate 后 0.2 秒内无法完成 cleanup 退出。
- **实际分支**: terminate grace 耗尽 → `terminate_result.completed=False` → 立即调用 `kill`。
- **预期行为**: terminate grace 应足够子进程完成 graceful cleanup；kill 应为真正无响应的最后手段。
- **实际行为**: 0.2s 是固定常量，不可配置。S2D/S2E tests 通过，但测试环境负载低。
- **直接证据**: `_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS = 0.2`、`_PROCESS_CAPSULE_KILL_GRACE_SECONDS = 0.2`。plan 中未讨论这些常量的取值依据。
- **影响**: 低。当前 process targets 为纯计算（Doc 文件 I/O、Fins 仓储读、Web HTTP 请求），0.2s 内 terminate 通常足够。只有在极端负载下才可能误升级。kill 语义为本 WU 目标（可抢占性）服务，过度 kill 比挂起等待更好。
- **建议改法和验证点**: 可后续通过 `HostLocalExecutionOptions` 或 capsule factory 注入可配置 grace period。当前不作为阻塞项。
- **修复风险（低）**: 仅添加配置注入点，不改默认行为。
- **严重程度（低）**: 当前 0.2s 对子进程 cleanup 已足够，且 kill 后不会产生 worse outcome（cancel 结果仍是 governed cancel）。

---

## Open Questions

无。

所有审查维度均已获得直接代码路径证据。S2E 的 residual risks 均已有 owner 且无 orphan，Playwright nested process cleanup 和 hint-in-message 已确认不误判。

## Residual Risk

- **Process envelope 常量碎片化**（DS-AGG-F01）：低风险，后续 Host process envelope contract hardening 时可消解。当前由 S2E residual risk "Process failed envelope has no structured hint field" 的 owner 覆盖。
- **Process capsule grace period 可配置性**（DS-AGG-F02）：低风险，后续 performance / production hardening 时可消解。
- **S2E 记录的 residual risks**：全部已分类且有 owner，本轮未发现新增 orphan risk。
- **测试缺口**：`query_xbrl_facts` spawned-child real XBRL fixture 和 Playwright nested process tree cleanup 为已知 low residual，不阻塞 #87 closeout。
- **未检查区域**：WU-WAIT-03 / activation hook（不在本 WU scope）、Engine 内部实现（未变更）、`docs/host/issues-implementation-control.md`（计划由 phaseflow controller 后续更新）。

---

## Verdict

**PASS**

S2A1–S2D 合并后的 typed execution closed loop 语义完整，无 Engine contract 或 LLM-facing schema 泄漏。Doc / Fins read / Web 生产关键路径均通过 `ProcessBackedToolExecutionCapability` 进入可抢占子进程边界，不再依赖同进程不可抢占 blocking I/O。Fins download / preprocess / upload 保持 `async_direct` awaiting lifecycle，由 WU-WAIT-03 独立管理。cancel → terminate → kill escalation 链通过 Host 通用 `_interrupt_capsule_after_wait` 统一治理，late-result accept barrier 有 Doc / Fins read / Web 三族工具测试证据。所有 residual risks 已分类、有 owner、无 orphan。AGENTS.md 分层/类型/docstring 约束全部满足。验证矩阵完整，无遗漏 S2A1/S2A2 contract/discovery 或受影响 provider 测试。

两个 low-severity findings（envelope 常量碎片化、grace period 硬编码）均不阻塞 #87 closeout，且已记录为已知风险或有后续 owner。

---

READY_FOR_CONTROLLER
