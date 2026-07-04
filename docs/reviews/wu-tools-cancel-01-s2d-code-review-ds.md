# WU-TOOLS-CANCEL-01 S2D Web sync Process-Backed — Code Review (AgentDS)

## Scope

- **Mode**: current changes (uncommitted S2D diff only)
- **Branch**: `phase/wu-tools-cancel-01`
- **Base**: `main`（仅审未提交 workspace diff）
- **Output file**: `docs/reviews/wu-tools-cancel-01-s2d-code-review-ds.md`
- **Review date**: 2026-07-04T22:36:33+08:00
- **Included scope**:
  - `dayu/tools/web/web_tools.py`（未提交 diff）
  - `tests/tools/web/test_web_tools_provider.py`（未提交 diff）
  - `docs/reviews/wu-tools-cancel-01-s2d-implementation-codex.md`（实现产物）
- **Excluded scope**: 已提交 S2A1/S2A2/S2B/S2C 代码、`dayu.runtime.interruptible_process` 内部实现、Host dispatch wiring 细节
- **Parallel review coverage**: 无（本 slice 变更集中在单文件，由主 reviewer 逐行走读）

## 真源对齐

已阅读并交叉验证以下真源：

- `docs/host/wu-tools-cancel-01-typed-execution-capability-plan.md` — S2D 要求的 process target shape、JSON 信封契约、不可序列化对象禁止列表
- `docs/reviews/wu-tools-cancel-01-s2d-implementation-codex.md` — 实现意图声明与验证结果
- `dayu/contracts/tool_execution.py` — `ProcessBackedToolContext`、`ProcessBackedToolExecutionCapability`、`ProcessBackedToolTarget` 公共契约
- `dayu/contracts/cancellation.py` — `CancellationToken` 为 `@runtime_checkable` Protocol（确认 `_WebProcessCancellationToken` 通过结构子类型满足类型边界）
- `dayu/host/tool_runtime.py:1753-1858` — `ProcessBackedToolExecutionCapsule` 生命周期与 JSON 信封映射
- `dayu/host/tool_runtime.py:6532-6611` — `_tool_outcome_from_process_envelope` 对 `completed`/`failed`/malformed 信封的 fail-closed 映射

## 逐条审查结论

### 1. search_web / fetch_web_page production definitions 声明 process-backed

**通过。** 直接证据：

- `web_tools.py:1198-1215`：`search_web` 定义通过 `execution=ProcessBackedToolExecutionCapability(target_factory=process_target_factory)` 声明
- `web_tools.py:1235-1254`：`fetch_web_page` 定义通过 `execution=ProcessBackedToolExecutionCapability(target_factory=process_target_factory)` 声明
- `test_web_tools_provider.py:374-381`：`test_web_tool_definitions_declare_process_backed_execution` 遍历两个 Web tool 并断言 `isinstance(definition.execution, ProcessBackedToolExecutionCapability)`

Host production dispatch 从 `ToolDefinition.execution` 选择 capsule（S2A2 declaration-backed factory，已提交），不按工具名分支。Web 工具通过 `ToolDefinition.execution` 声明即可被 production ToolRuntime 走 process-backed。

### 2. _WebProcessTargetFactory / _WebProcessTarget 只保存可序列化配置

**通过。** 直接证据：

- `web_tools.py:527-570`：`_WebProcessTargetFactory` 为 `@dataclass(frozen=True, slots=True)`，唯一字段 `config: WebToolsConfig`。`WebToolsConfig`（`web_tools.py:179-201`）为 frozen dataclass，字段均为 `str`/`float`/`int`/`bool`/`str | None` 可序列化标量。未捕获 `requests.Session`、`provider_lock`、`CancellationToken`、Host/Run/Session、Playwright runtime/browser。
- `web_tools.py:440-524`：`_WebProcessTarget` 为 `@dataclass(frozen=True, slots=True)`，字段为 `tool_name: str`、`arguments: dict[str, JsonValue]`、`config: WebToolsConfig`、`timeout_seconds: float | None`。
- `test_web_tools_provider.py:384-428`：`test_web_process_target_factory_is_pickle_round_trippable` 执行 pickle round-trip 并断言 `repr(target)` 不含 `"Session"`、`"provider_lock"`、`"CancellationToken"`、`"Host"`、`"Browser"`、`"Playwright"`。

### 3. 子进程重建 Web runtime，timeout budget 传入 HTTP/browser 阶段

**通过。** 直接证据：

- `web_tools.py:469-524`：`_WebProcessTarget.__call__()` 在子进程内调用 `_execute_web_process_business_value`，该函数（`web_tools.py:1558-1633`）创建 `_WebProcessCancellationToken()` 作为子进程 token，重建 `ToolCallRequest`，调用现有同步业务 helper `_search_web_business` / `_fetch_web_page_business`。
- `_fetch_web_page_business`（`web_tools.py:1817-2235`）通过 `_get_web_session()` 创建新 requests Session（不传父进程全局 Session），通过 `_prepare_call_session` 设置 timeout，Playwright fallback 通过 `_try_playwright_fallback` → `_fetch_and_convert_with_playwright` → `_web_playwright_backend._fetch_and_convert_with_playwright` 在独立 worker 子进程中执行。
- `test_web_tools_provider.py:431-471`：`test_web_process_target_fast_search_success_path` 验证 `timeout_budget=4.25` 被完整传入 `_search_web_business`
- `test_web_tools_provider.py:491-513`：`test_web_process_target_timeout_budget_is_serialized_to_target` 参数化验证两个工具的 `target.timeout_seconds == 6.75`

### 4. Direct callable fallback 只作为测试/非生产 fallback

**通过。** 直接证据：

- `web_tools.py:1195`：`provider_lock = asyncio.Lock()` 在 `build_web_tool_definitions` 内创建
- `web_tools.py:1216-1233`：`search_web` 的 `@tool` 装饰的 async callable 仍通过 `_call_search_web(call, context, config, provider_lock)` 使用 `asyncio.to_thread` + `provider_lock`
- `web_tools.py:1255-1272`：`fetch_web_page` 同理
- `web_tools.py:1204-1205`、`web_tools.py:1243-1244`：两个工具的 `execution=ProcessBackedToolExecutionCapability(...)` 与 direct callable 同时存在于同一 `ToolDefinition` 上

Host production ToolRuntime 从 `ToolDefinition.execution` 选择 capsule（S2A2 逻辑），不走 `ToolDefinition.callable`。测试仍可通过 `definition.callable(call, context)` 直接调用 async callable fallback。现有 `test_web_provider_serializes_search_and_fetch_business`（`test_web_tools_provider.py:1776-1908`）验证 provider lock 串行语义在 direct callable fallback 中生效。

### 5. Schema、success payload、failure code/message/hint、truncate spec、URL safety、provider config、Playwright fail-closed 语义保持

**通过。** 逐项证据：

| 项目 | 保持方式 | 证据 |
|------|----------|------|
| Schema | `_execute_web_process_business_value` 调用与 direct callable 相同的 `validate_and_project_arguments` + `_build_search_web_parameters` / `_FETCH_WEB_PAGE_PARAMETERS` | `web_tools.py:1587-1598`、`web_tools.py:1615-1620` |
| Success payload | `_search_web_business` / `_fetch_web_page_business` 返回原始业务载荷，process target 包装为 `{"status": "completed", "value": <payload>}` | `web_tools.py:521-524` |
| Failure code/message/hint | `ToolBusinessError` 的 `code`/`message`/`hint` → `_web_process_failed_envelope`；hint 合入 message（因 Host envelope 不消费独立 hint 字段） | `web_tools.py:497-502`、`web_tools.py:1636-1668` |
| Truncate spec | 未修改；Host ToolRuntime 从 `ToolDefinition.truncate` 读取并应用截断，与 process target 解耦 | `web_tools.py:1207-1214`、`web_tools.py:1246-1253` |
| URL safety | `_fetch_web_page_business` 内 `_is_safe_public_url` 仍在子进程中执行 | `web_tools.py:1842-1853` |
| Provider config | `_WebProcessTargetFactory` 捕获完整 `WebToolsConfig`，通过 pickle 传入子进程 | `web_tools.py:1196`、`web_tools.py:545` |
| Playwright fail-closed | `_fetch_and_convert_with_playwright` → `_web_playwright_backend._fetch_and_convert_with_playwright` 在 worker 子进程中执行，不可序列化时 fail closed（`test_web_tools_provider.py:1430-1475` 已覆盖） | `web_tools.py:2590-2636` |

### 6. 测试覆盖

**通过。** 逐项验证：

| 覆盖点 | 测试函数 | 行号 |
|--------|----------|------|
| 两个 definitions process-backed | `test_web_tool_definitions_declare_process_backed_execution` | `374-381` |
| Pickle round-trip factory + target | `test_web_process_target_factory_is_pickle_round_trippable` | `384-428` |
| Failed JSON envelope | `test_web_process_target_failed_json_envelope_preserves_code_and_hint` | `474-488` |
| Timeout budget 传入 | `test_web_process_target_timeout_budget_is_serialized_to_target` | `491-513` |
| 真实 ProcessBackedToolExecutionCapsule spawned child 成功 | `test_web_process_backed_capsule_spawns_child_success` | `516-548` |
| 真实 Web process target cancel → 无 late accept | `test_web_toolruntime_cancel_real_process_target_has_no_late_accept` | `551-610` |
| 保留 direct callable cancellation | `test_search_web_cancelled_before_provider_returns_host_cancelled`、`test_fetch_web_page_cancelled_before_work_returns_safe_host_cancelled` 等 | `819-1116` |
| 保留 provider lock 串行 | `test_web_provider_serializes_search_and_fetch_business` | `1776-1908` |
| Playwright fail-closed | `test_playwright_unpicklable_worker_fails_closed` | `1430-1475` |

其中 `test_web_toolruntime_cancel_real_process_target_has_no_late_accept`（`551-610`）是最关键的端到端证据：构造真实 `DefaultToolRuntimeFactory` + `ToolRuntimeHandle`，对延迟 5s 的 server 发起 fetch → 400ms 后 cancel → 断言 `elapsed < 2.0s`（证明未等 server 完成）、`governed_outcome.result.hint == "tool_runtime_cancelled"`（证明返回取消 outcome）、`len(accept_port.candidates) == 1` 且 `reason_code == "tool_runtime_cancelled"`（证明 accept barrier 只接受取消事实，不接受 late child result）。

**不存在 fake-only 证明不足。** 真实子进程 spawn 和真实 ToolRuntime 端到端路径均已覆盖。

### 7. 未修改 Engine contract、durable schema、Host public contract、runtime JsonValue envelope

**通过。** 直接证据：

- `git diff --stat` 仅包含 `dayu/tools/web/web_tools.py` 和 `tests/tools/web/test_web_tools_provider.py`
- `dayu/contracts/tool_execution.py` 由 S2A1 已提交，S2D 不修改
- `dayu/runtime/interruptible_process.py` JsonValue envelope 契约（`status`/`value`/`error_type`/`message`）由 S1 已定义，S2D 不修改
- Host capsule `_tool_outcome_from_process_envelope`（`tool_runtime.py:6532-6611`）由 S2A2 已提交，S2D 只消费其 `completed`/`failed` 信封映射

### 8. AGENTS.md 硬约束

**通过。** 逐项检查：

- **中文 docstring**：所有新增类（`_WebProcessCancellationToken`、`_WebProcessTarget`、`_WebProcessTargetFactory`）、新增函数（`_execute_web_process_business_value`、`_web_process_failed_envelope`）均有完整中文 docstring，包含参数、返回值、异常说明
- **类型**：无 `Any`、`object`、无类型参数、无类型返回值签名。关键类型为 `str`、`dict[str, JsonValue]`、`WebToolsConfig`、`float | None`、`JsonValue`、`WebPayload`（`dict[str, JsonValue]`）
- **无不当 `getattr`/`hasattr`**：新增代码未使用 `getattr` 或 `hasattr`
- **README 触发边界**：`tests/` 有修改，但仅在既有 test 文件内补覆盖点，未新增测试层级、目录职责或运行方式；实现 artifact 明确声明无需更新 `tests/README.md`

---

## Findings

### 01-未修复-低-`_WebProcessCancellationToken` 未显式实现 `CancellationToken` Protocol

- **入口/函数**: `_WebProcessCancellationToken`（`web_tools.py:385-437`）
- **文件(行号)**: `dayu/tools/web/web_tools.py:385-437`
- **输入场景**: 所有通过 `_execute_web_process_business_value` 的 process-backed 执行路径
- **实际分支**: `_WebProcessCancellationToken` 通过结构子类型（duck typing）满足 `CancellationToken` Protocol 的方法签名要求
- **预期行为**: `_WebProcessCancellationToken` 应在类型层面满足 `CancellationToken`
- **实际行为**: 当前通过 `@runtime_checkable CancellationToken(Protocol)` 的结构子类型隐式满足；未显式声明 `implements`/继承关系；如果 `CancellationToken` Protocol 新增方法，`_WebProcessCancellationToken` 不会在类型检查层面报错，但运行时会因 `AttributeError` 被 `_WebProcessTarget.__call__()` 的 `except Exception` 兜底为 generic failure
- **直接证据**: `dayu/contracts/cancellation.py:18`：`@runtime_checkable` / `class CancellationToken(Protocol)`；`web_tools.py:385-437`：`_WebProcessCancellationToken` 未显式继承或声明实现关系
- **影响**: 低 — 当前运行正确，仅当 `CancellationToken` Protocol 扩展时才存在静默不兼容风险
- **建议改法和验证点**: 无需立即修改。这是一个防御性标注建议：考虑在 `_WebProcessCancellationToken` 类 docstring 中注明"本类通过结构子类型满足 `CancellationToken` Protocol"，或使用 `typing.runtime_checkable` 的显式注册。若后续 `CancellationToken` 扩展，需同步更新本类
- **修复风险**: 低
- **严重程度**: 低

### 02-未修复-低-Web process target 常量与 Host capsule 常量独立定义

- **入口/函数**: `_WebProcessTarget.__call__()` 返回的 JSON 信封
- **文件(行号)**: `dayu/tools/web/web_tools.py:164-169` vs `dayu/host/tool_runtime.py` 内的 `_PROCESS_ENVELOPE_*` 常量
- **输入场景**: 所有 process-backed 执行
- **实际分支**: Web process target 使用模块级 `_WEB_PROCESS_STATUS_FIELD` 等私有常量；Host capsule 使用自身 `_PROCESS_ENVELOPE_STATUS_FIELD` 等常量
- **预期行为**: 信封字段名契约应单源定义（如在 `dayu.contracts.tool_execution` 或 `dayu.runtime.interruptible_process`）
- **实际行为**: 两端用相同字面量值（`"status"`/`"completed"`/`"failed"`/`"value"`/`"error_type"`/`"message"`），但独立定义，存在无意漂移风险
- **直接证据**: `web_tools.py:164-169` 定义 `_WEB_PROCESS_*`；`tool_runtime.py` 另有 `_PROCESS_ENVELOPE_*` 常量（由 S1/S2A2 定义）。两端值相同但无编译期或导入期交叉验证
- **影响**: 低 — 当前值一致，仅当一方独立变更时才会漂移。这是架构改进建议，不是当前缺陷
- **建议改法和验证点**: 考虑在 `dayu.contracts.tool_execution` 或 `dayu.runtime.interruptible_process` 中定义信封字段名公共常量，让 Web process target 与 Host capsule 引用同一符号。若不做，至少在 process target 的 docstring 中注明"字段名必须与 Host capsule `_PROCESS_ENVELOPE_*` 常量保持一致"
- **修复风险**: 低
- **严重程度**: 低

---

## Open Questions

1. **Web process target 内的 Playwright fallback 嵌套进程管理**：`_fetch_web_page_business` → `_try_playwright_fallback` → `_fetch_and_convert_with_playwright` → `_web_playwright_backend._fetch_and_convert_with_playwright` 在 worker 子进程中执行。在 process-backed 路径下，这形成 ToolRuntime capsule → Web tool process → Playwright worker process 三层进程树。当 ToolRuntime capsule 对 Web tool process 执行 `terminate`/`kill` 时，OS 应级联清理 Playwright worker（作为子进程）。但若 Playwright worker 内又 fork 了 browser 进程（Chromium 多进程架构），完整的进程树清理依赖 OS 进程组语义。当前测试 `test_web_toolruntime_cancel_real_process_target_has_no_late_accept` 使用 `requests` 主路径（不含 Playwright），未覆盖 process-backed + Playwright fallback + cancel 的完整嵌套进程树清理。这应在 S2E aggregate validation 中补齐，不阻塞 S2D。

2. **hint 合入 message 后 LLM 解析可靠性**：`_web_process_failed_envelope` 将 hint 以 `" Hint: {hint}"` 格式拼接进 message。Host capsule `_failed_outcome_from_process_envelope` 将整个 message 作为 `ToolFailedOutcome.message` 传递给 LLM，`hint` 字段为 `None`。当前 LLM-facing prompt 没有明确指示从 message 中解析 hint 的规则。若下游 prompt 依赖 `hint` 字段为非空才展示恢复建议，则本修改可能导致 LLM 忽略 hint。建议在 Host capsule 或 prompt 层面验证 LLM 能否从拼接后的 message 中正确提取 hint 语义。

---

## Residual Risk

1. **Process-backed 冷启动成本**：每次 Web tool 调用需 spawn 子进程（Python + import `dayu.tools.web`），增加延迟。实现 artifact 已记录为后续性能 work unit 评估，当前 S2D 不处理。

2. **网络波动与真实 provider**：测试使用本地 socket HTTP server，未覆盖真实外网 provider 的取消路径。真实 provider 的 TCP 连接在进程被 kill 后的 socket close 依赖于 OS 级别清理（SIGTERM → socket close → TCP RST），已在 S1 `interruptible_process` 层面验证。

3. **Playwright 嵌套进程树在 cancel 下的完整清理**：见 Open Question 1。

---

## Verdict

**PASS**

本 slice 实现严格遵循 S2D 计划，八项审查重点全部通过。两层 process target factory/target 均只保存可序列化配置，子进程重建 Web runtime 且 timeout budget 正确传入，direct callable fallback 保留，schema/success/failure/truncate/URL safety/Playwright fail-closed 语义均保持，测试覆盖真实子进程 spawn 和真实 ToolRuntime cancel → 无 late accept 端到端路径。未修改 Engine contract、durable schema、Host public contract 或 runtime JsonValue envelope。AGENTS.md 硬约束全部满足。

两个低严重度 findings（`_WebProcessCancellationToken` 未显式实现 Protocol、信封常量双源定义）均为架构改进建议，不阻塞 merge。两个 open questions 建议在 S2E aggregate validation 中验证，不阻塞 S2D。

---

READY_FOR_CONTROLLER
