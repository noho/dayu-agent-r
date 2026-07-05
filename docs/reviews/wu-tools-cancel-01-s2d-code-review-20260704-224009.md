# Code Review

## Scope

- Mode: current changes (workspace diff, uncommitted S2D)
- Branch: `phase/wu-tools-cancel-01`
- Base: `main` (834b0df6)
- Output file: `docs/reviews/wu-tools-cancel-01-s2d-code-review-20260704-224009.md`
- Included scope:
  - `dayu/tools/web/web_tools.py` (unstaged changes)
  - `tests/tools/web/test_web_tools_provider.py` (unstaged changes)
  - `docs/reviews/wu-tools-cancel-01-s2d-implementation-codex.md` (untracked artifact)
- Excluded scope: 未修改的 Engine contract、durable schema、Host public contract、`dayu.runtime`。
- Parallel review coverage: 无。

## 审查真源与上下文

- `dayu/contracts/tool_execution.py` — `ProcessBackedToolExecutionCapability`、`ProcessBackedToolContext`、`ProcessBackedToolTarget` Protocol。
- `dayu/host/tool_runtime.py` — `DeclaredToolExecutionCapsuleFactory._declared_capsule_for_execution()` 分发逻辑；`ProcessBackedToolExecutionCapsule` spawn/wait/terminate/kill；`_tool_outcome_from_process_envelope()` 信封解析。
- `docs/host/wu-tools-cancel-01-typed-execution-capability-plan.md` — S2D stop conditions 与 process-backed entrypoint shape。
- `docs/host/issues-implementation-control.md` — #87 interrupt closeout 要求。

## Findings

未发现实质性问题。

### 逐项审查证据

#### 1. search_web / fetch_web_page 声明 ProcessBackedToolExecutionCapability

**直接证据**: `web_tools.py` L1204-1206 (`search_web`) 与 L1243-1245 (`fetch_web_page`) 均通过 `execution=ProcessBackedToolExecutionCapability(target_factory=process_target_factory)` 声明。`DeclaredToolExecutionCapsuleFactory._declared_capsule_for_execution()` (`tool_runtime.py` L1616-1621) 对 `ProcessBackedToolExecutionCapability` 走 `build_process_target` → `ProcessBackedToolExecutionCapsule(target)`。

**结论**: 生产路径走 process-backed，不走 `AsyncDirectToolExecutionCapsule`。

#### 2. _WebProcessTargetFactory / _WebProcessTarget 只保存可序列化配置

**直接证据**:
- `_WebProcessTargetFactory` (`web_tools.py` L527-570): frozen dataclass，唯一字段 `config: WebToolsConfig`。
- `_WebProcessTarget` (`web_tools.py` L440-524): frozen dataclass，字段为 `tool_name: str`、`arguments: dict[str, JsonValue]`、`config: WebToolsConfig`、`timeout_seconds: float | None`。
- `build_process_target` (`web_tools.py` L547-570): `arguments=dict(call.arguments)` 做浅拷贝；`timeout_seconds=context.timeout_seconds` 取标量。
- `WebToolsConfig` (`web_tools.py` L179-200): frozen dataclass，全部字段为 `str | float | int | bool | None` 标量。

**未捕获的对象**: `requests.Session`（由 `_get_web_session()` 在业务函数内创建）、`provider_lock`（`asyncio.Lock`，在 `build_web_tool_definitions` 闭包内）、`CancellationToken`（在 direct callable 闭包内）、Host/Run/Session、Playwright runtime/browser。

**结论**: 满足 process-backed entrypoint shape "只保存可序列化配置、tool name、arguments JSON 副本、timeout 标量"约束。

#### 3. 子进程重建 Web runtime；timeout budget 传入 HTTP/browser 阶段

**直接证据**:
- `_WebProcessTarget.__call__` (`web_tools.py` L469-524): 构造新 `ToolCallRequest`，调用 `_execute_web_process_business_value`。
- `_execute_web_process_business_value` (`web_tools.py` L1558-1633): 创建 `_WebProcessCancellationToken()`，调用 `_search_web_business` / `_fetch_web_page_business`。
- `_search_web_business` (`web_tools.py` L1514-1555): 调用 `search_public_web(... timeout_budget=timeout_budget ...)` 传入 HTTP 阶段。
- `_fetch_web_page_business` (`web_tools.py` L1817-2235): 调用 `_get_web_session()` 重建 session，`_compute_deadline_monotonic(timeout_budget)` 计算 deadline，传入 warmup / probe / fetch / playwright 阶段。
- `_get_web_session()` 由 `web_http_session` 模块提供，每次调用返回独立 session。

**父进程全局 Session 不跨进程传递**: `provider_lock` (`asyncio.Lock`) 不可 pickle；`_get_web_session()` 在子进程内重新创建。

**结论**: 子进程完整重建 Web runtime；timeout budget 正确传入 HTTP/browser 阶段。

#### 4. direct callable fallback 仅作直接测试/非生产 fallback

**直接证据**:
- `_call_search_web` (`web_tools.py` L1315-1417) 与 `_call_fetch_web_page` (`web_tools.py` L1420-1511) 保留 `provider_lock`、`asyncio.to_thread`、`CancellationToken` cooperative cancel 逻辑。
- `ToolDefinition.callable` 属性指向这些 direct callable。
- `DeclaredToolExecutionCapsuleFactory` 按 `definition.execution` 类型分发；`ProcessBackedToolExecutionCapability` 走 capsule，不走 callable。
- 测试通过 `definition.callable(...)` 直接调用，验证 cooperative cancel、provider lock、timeout budget 等行为。

**结论**: direct callable 仅在测试或非声明路径使用；生产由 process-backed capsule 独占。

#### 5. schema / success payload / failure code / truncate / URL safety / provider config / Playwright fail-closed

**直接证据**:
- schema: `_build_search_web_parameters` 与 `_FETCH_WEB_PAGE_PARAMETERS` 未修改。
- success payload: `_search_web_business` 返回 `SearchWebOutput`（不变）；`_fetch_web_page_business` 返回 `{"url", "final_url", "title", "content", "fetch_backend"}`（不变）。
- process target 成功信封 (`web_tools.py` L521-524): `{"status": "completed", "value": value}` — 对齐 `ProcessBackedToolTarget` Protocol。
- process target 失败信封 (`web_tools.py` L1636-1668): `{"status": "failed", "error_type": ..., "message": ...}` — 对齐 Protocol。hint 合入 message（documented，L1649-1650）。
- `_web_process_failed_envelope` 空值保护: `error_type.strip() or "execution_error"`、`message.strip() or "Tool execution failed."`。
- truncate spec: `ToolTruncateSpec` 声明未修改。
- URL safety: `_is_safe_public_url` 在 `_fetch_web_page_business` 内调用，process target 走同一路径。
- provider config: `WebToolsConfig` 由 `_WebProcessTargetFactory` 保存，传入 `_WebProcessTarget`，子进程内使用。
- Playwright fail-closed: `web_playwright_backend._is_picklable_worker` 检查 worker 可序列化性；不可序列化时返回 `{"ok": False, "reason": "playwright_worker_not_picklable"}`，不回落到同进程执行。子进程内 Playwright 由父进程 capsule terminate/kill 治理。

**结论**: 所有语义保持不变。

#### 6. 测试覆盖审查

| 覆盖点 | 测试 | 证据类型 |
|---|---|---|
| 两个 definitions 声明 process-backed | `test_web_tool_definitions_declare_process_backed_execution` | 直接 |
| factory/target pickle round-trip | `test_web_process_target_factory_is_pickle_round_trippable` | 直接，含 repr 断言 |
| failed JSON envelope | `test_web_process_target_failed_json_envelope_preserves_code_and_hint` | 直接，含 error_type/Hint 断言 |
| timeout budget 标量序列化到 target | `test_web_process_target_timeout_budget_is_serialized_to_target` (parametrized) | 直接 |
| search fast success path | `test_web_process_target_fast_search_success_path` | 直接，含 budget 断言 |
| 真实 capsule spawned child 成功 | `test_web_process_backed_capsule_spawns_child_success` | 直接，含内容断言 |
| 真实 process target cancel 后无 late accept | `test_web_toolruntime_cancel_real_process_target_has_no_late_accept` | 直接，含 accept count/reason 断言 |
| direct callable timeout budget | `test_search_and_fetch_pass_tool_timeout_budget_to_business` | 直接 |
| Playwright fail-closed (unpicklable) | `test_playwright_unpicklable_worker_fails_closed` | 直接 |

**测试充分性判断**: 测试覆盖了 process-backed 声明、pickle 安全、信封格式、timeout budget、真实子进程、取消语义。取消测试通过真实 socket server (5s delay) + 0.4s 后 cancel + 2s timeout 断言，证明 governed outcome 在 2s 内返回且 accept barrier 只记录 1 个 cancelled candidate。

**结论**: 测试覆盖充分，无 fake-only 证明不足问题。

#### 7. 未修改 Engine contract / durable schema / Host public contract / runtime envelope

**直接证据**: diff 仅涉及 `dayu/tools/web/web_tools.py` 和 `tests/tools/web/test_web_tools_provider.py`。未修改 `dayu/contracts/`、`dayu/runtime/`、`dayu/host/`、`dayu/engine/`。

**结论**: 满足 stop condition。

#### 8. AGENTS.md 硬约束

- **中文 docstring**: 新增的 `_WebProcessCancellationToken`、`_WebProcessTarget`、`_WebProcessTargetFactory`、`_execute_web_process_business_value`、`_web_process_failed_envelope` 均提供完整中文 docstring，含 Args/Returns/Raises。
- **类型签名**: 新增函数/方法均使用严格类型标注；无 `Any`、`object`、无类型参数或返回值。
- **getattr/hasattr**: 未新增不当 `getattr`/`hasattr` 使用。
- **README 触发**: 修改了 `tests/`；已阅读 `tests/README.md`。本次在既有测试文件内补覆盖点，未新增测试层级/目录职责/运行方式，无需更新。

**结论**: 满足 AGENTS.md 硬约束。

## Open Questions

无。

## Residual Risk

1. **Process-backed hint 信息丢失**: `_web_process_failed_envelope` 把 hint 合入 message 字段。Host `_failed_outcome_from_process_envelope` 解析时只取 `error_type` 和 `message`，`ToolFailedOutcome.result.hint` 为 `None`。LLM 会收到 message 中嵌入的 hint 文本（`"... Hint: ..."`），但结构化 hint 字段丢失。这是 process-backed envelope 契约的已知限制，非本 slice 引入。当前 direct callable path 的 hint 传递不受影响。

2. **取消测试 late accept 验证深度**: `test_web_toolruntime_cancel_real_process_target_has_no_late_accept` 在 governed outcome 返回后只等 0.3s。server delay 为 5s，理论上子进程仍在运行。测试证明了 cancel → governed outcome 的快速返回和 accept barrier 记录，但未在子进程实际完成后再检查 accept count。生产正确性由 `ProcessBackedToolExecutionCapsule.terminate()` + Host accept barrier 状态机保证。

3. **Web tool 冷启动成本**: process-backed 每次调用 spawn 子进程，会增加冷启动延迟。当前 #87 closeout 优先保证取消可抢占；worker pool / 复用优化应作为后续性能 work unit。

4. **子进程内 provider lock 缺失**: direct callable path 通过 `provider_lock` 串行化 search/fetch 业务体。process-backed path 在子进程内无此锁。设计意图是子进程独立，不存在父进程级并发竞争；但若未来同一 config 的多个 Web tool 子进程并发运行，各子进程间无序列化保证。当前单 tool call per capsule 的架构下无风险。

## 结论

**PASS**

未发现实质性问题。S2D 实现正确完成了 search_web / fetch_web_page 从 direct callable 到 process-backed 的迁移：ToolDefinition.execution 声明 ProcessBackedToolExecutionCapability；process target 只保存可序列化配置；子进程重建 Web runtime 并正确传递 timeout budget；Playwright fail-closed 语义保持；所有语义（schema、success payload、failure envelope、truncate spec、URL safety）不变。测试覆盖充分。
