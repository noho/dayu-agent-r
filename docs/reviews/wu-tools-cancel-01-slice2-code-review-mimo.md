# WU-TOOLS-CANCEL-01 Slice S2 Code Review — AgentMiMo

## Artifact

- Reviewer: AgentMiMo
- Branch: `phase/wu-tools-cancel-01`
- Diff scope: uncommitted changes after S1 accepted slice commit `eda4be1a`
- Design sources: `docs/host/design.md`, `docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Codex S2 report: `docs/reviews/wu-tools-cancel-01-slice2-implementation-codex.md`

## Findings

### F1 — Design Gate: Doc / Fins 生产阻塞路径无法迁移到 process_backed

**Severity**: DESIGN_GATE (blocking for #87 closeout, non-blocking for current slice commit)

**Scope**: `dayu/tools/doc_tools.py`, `dayu/fins/tools/fins_tools.py` (不在本次 diff 中，但直接影响 S2 完成判定)

**Direct evidence**:

1. `dayu/contracts/tool_declaration.py:86-108` 定义 `ToolDefinition`，字段为 `name`, `schema`, `callable`, `truncate`, `display`, `tags`——无 typed execution capability 字段。
2. S1 在 `dayu/host/tool_runtime.py` 内部建立了 `ToolExecutionMode` 枚举 (`ASYNC_DIRECT`, `THREAD_BACKED`, `PROCESS_BACKED`)，但该枚举是 Host 内部 capsule 工厂的实现细节，未暴露到 `dayu.contracts`。
3. Doc tools (`dayu/tools/doc_tools.py`) 和 Fins tools (`dayu/fins/tools/fins_tools.py`) 使用 `asyncio.to_thread(business_call, token)` 模式。这些工具位于 `tools` / `fins` 层，按 `UI -> Service -> Host -> Engine` 分层约束，不能 import Host 内部 capsule。
4. 计划 Section 7.4.1 说：process-backed 迁移需要"把 process 入口改成模块级函数，只传可序列化 path、参数、tool call identity 和必要 config"。当前 `business_call` 是闭包，捕获了 processor / runtime 对象，不可序列化。
5. 计划全局 stop condition (Section 7.4.1 末尾)：如果 doc、Fins read、Web sync 主路径不能迁移到 `process_backed`，也不能提供 request-abort-capable `async_direct` adapter，且修复需要改变 Host / Engine public contract、工具声明公共契约或业务存储架构，本 work unit 必须返回 design gate。

**Verdict on Codex claim**: AgentCodex 声称 Doc/Fins sync 主路径因缺少 typed execution capability 无法在不违反分层/契约的情况下迁移到 S1 process-backed——**由代码和设计直接支持**。

- `ToolDefinition` 无 execution mode 字段 → 工具无法声明自己的执行模式。
- 工具层不能 import Host capsule → Host 无法从工具声明获知执行模式。
- 要解决此问题，要么在 `dayu.contracts.ToolDefinition` 增加 execution capability 字段（公共契约变更），要么引入新的 provider 声明路径（设计变更）。两者都需要 design/contract gate。

**Impact on stop condition**: **命中全局 stop condition**。Doc 和 Fins read 生产阻塞路径不能标记为 production-grade non-cooperative cancel 已解决。当前 S2 slice 可以被接受为 partial migration（Web 改进 + Playwright fail-closed），但 #87 closeout 前必须经过 design/contract gate。

---

### F2 — Test assertion 过宽：playwright unpicklable worker 测试接受无关 failure reason

**Severity**: LOW (test quality, 非 blocking)

**File**: `tests/tools/web/test_web_tools_provider.py:1034-1037`

**Code**:
```python
assert result["reason"] in {
    "playwright_worker_not_picklable",
    "playwright_not_installed",
}
```

**Issue**: 测试目的是验证 unpicklable worker fail-closed，但断言接受 `playwright_not_installed` 作为合法 reason。`playwright_not_installed` 来自 `_fetch_and_convert_with_playwright` 开头的 `import playwright` 检查（`web_playwright_backend.py:1063-1070`），是完全不同的 failure mode——它意味着 playwright 包未安装，与 worker picklability 无关。

当 playwright 未安装时，函数在到达 `_is_picklable_worker` 检查之前就已返回 `playwright_not_installed`。此时测试虽然通过，但并未验证 unpicklable fail-closed 逻辑。

当前 CI 环境已安装 playwright，所以测试实际走的是 `playwright_worker_not_picklable` 路径。但断言设计不精确，降低了测试的防御价值。

**Suggested fix**（不阻塞当前 slice）:
```python
assert result["reason"] == "playwright_worker_not_picklable"
```

---

### F3 — Web timeout budget 传递正确性

**Severity**: INFO (correct, 无 blocking issue)

**Files**: `dayu/tools/web/web_tools.py:1180, 1274`

**Analysis**: 将 `timeout_budget=None` 改为 `timeout_budget=context.timeout_seconds` 是正确的改进。

- `context.timeout_seconds` 类型为 `float | None`，与 `timeout_budget` 参数类型 `float | None` 匹配。
- `web_http_session.py` 的 `_resolve_timeout_budget(...)` 已有 deadline-aware timeout helper，之前因调用方传 `None` 而未生效。
- 此变更使 HTTP 请求预算受工具执行 deadline 约束，符合计划 Section 7.3 "HTTP request / stream 类执行必须在 adapter 内实现 abort" 的 deadline propagation 要求。
- 不改变 LLM-facing tool schema text，不引入新的 LLM-facing 文本。

---

### F4 — Playwright fail-closed 变更正确性

**Severity**: INFO (correct, 无 blocking issue)

**File**: `dayu/tools/web/web_playwright_backend.py:1103-1111`

**Analysis**: 移除 unpicklable worker 的同进程 fallback 是正确的安全加固。

- 之前 unpicklable worker 会回落到同进程 `playwright_sync_worker(...)` 执行，在父进程中执行 blocking I/O，使 Host cancel 无法中断。
- 现在 fail-closed 返回 `{"ok": False, "availability": "unprocessable", "reason": "playwright_worker_not_picklable"}`。
- 符合计划 Section 7.4.1 Playwright 行："不可 picklable worker fallback 必须 fail closed，不回落为不可抢占 thread"。
- `Log.warning(...)` 提供了运维可观察性。
- 返回 dict 结构与 `playwright_not_installed` 和 `playwright_timeout` 的返回形状一致，类型为 `WebPayload`。

---

### F5 — Control doc 更新一致性

**Severity**: INFO (correct)

**File**: `docs/host/issues-implementation-control.md`

**Analysis**: control doc 从 `accepted-slice` gate 移到 `implementation` gate，更新了 `next entry point`、`implementation status` 和 `WU-TOOLS-CANCEL-01` 行。与 S2 实际状态一致。不触发 README 更新规则（无 `dayu/host/`, `dayu/engine/`, `dayu/fins/`, `tests/` 入口职责变化）。

---

## Questions to Codex report

### Q1: Doc/Fins sync 主路径 claim 是否由代码和设计直接支持？

**Answer**: **是**。直接证据链完整：

1. `ToolDefinition` 无 execution capability 字段（`dayu/contracts/tool_declaration.py:86-108`）。
2. S1 capsule mode 是 Host 内部实现，不在 `dayu.contracts` 中。
3. Doc/Fins 工具使用闭包 + `asyncio.to_thread(...)` 模式，闭包不可序列化。
4. 工具层不能 import Host 层（分层约束）。
5. 因此工具无法声明 process-backed 模式，Host 也无法从工具声明获知。

### Q2: 是否命中全局 stop condition？

**Answer**: **是**。计划 Section 7.4.1 全局 stop condition 明确说：如果 doc、Fins read、Web sync 主路径不能迁移到 `process_backed`，也不能提供 request-abort-capable `async_direct` adapter，且修复需要改变 Host / Engine public contract、工具声明公共契约或业务存储架构，必须返回 design gate，不得进入 #87 closeout。

当前状态：
- Doc / Fins read 路径不能迁移到 process_backed（缺少 typed execution capability 声明机制）。
- 修复需要在 `dayu.contracts.ToolDefinition` 增加字段或引入新的 provider 声明路径——两者都是公共契约变更。
- 因此 **必须返回 design gate**，不能把 #87 标记为 closeout。

但当前 S2 slice 的 Web 改进（budget propagation）和 Playwright fail-closed 变更本身是正确的增量改进，可以被接受为 partial migration。

## Verdict

**PASS_ACCEPT_PARTIAL**

理由：

1. **当前 diff 内容正确**：Web timeout budget 传递和 Playwright fail-closed 变更均正确实现了计划目标，不引入回归、不违反 AGENTS.md / LLM-facing / 分层 / README 规则。
2. **Design gate 必须在 #87 closeout 前通过**：Doc / Fins 生产阻塞路径因缺少 `dayu.contracts` 层的 typed execution capability 声明机制，无法在不违反分层约束的情况下迁移到 process_backed。这命中了计划的全局 stop condition。
3. **S2 slice 可标记为 partial migration accepted**：当前变更改善了 Web HTTP 预算约束和 Playwright 安全边界，是正确的增量进步。但不应声称 S2 production tools interrupt adapters 已完成——Doc/Fins 主路径未迁移。
4. **无当前 slice 内可修复的 blocking bug**：F2（test assertion 过宽）是 test quality 问题，不阻塞代码提交。
5. **下一步**：controller 应将 Doc/Fins execution capability 声明需求作为 design/contract gate 议题，在 #87 closeout 前解决。

## Validation

- `pytest tests/tools/web/test_web_tools_provider.py -q` → 23 passed
- `pyright` → 0 errors
- `git diff --check` → passed
