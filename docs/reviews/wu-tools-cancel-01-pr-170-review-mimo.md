# PR #170 Review — AgentMiMo

## Scope

- Mode: PR
- PR: #170
- Title: WU-TOOLS-CANCEL-01: harden tool/provider cancellation
- Author: noho
- Head branch: phase/wu-tools-cancel-01
- Base branch: main
- URL: https://github.com/noho/dayu-agent-r/pull/170
- State: draft, OPEN
- Output file: docs/reviews/wu-tools-cancel-01-pr-170-review-mimo.md
- Included scope: PR 相对 base branch 的完整 diff（118 files, +13900/-560）
- Excluded scope: 无
- Parallel review coverage: 无（单 reviewer 覆盖全 PR）

## Findings

未发现实质性问题。

以下为详细审查结论：

### 1. PR 对 WU-TOOLS-CANCEL-01 / #87 closeout 的覆盖完整性

**验证结果：PASS。**

PR 完整覆盖三个核心验收信号：

- **Host Esc/cancel 后快速回到可交互**：`local_proxy.py` 的 `on_cancel()` 现在调用 `self.close()`（通过后台 task），关闭 Engine event stream，取消 active `anext`，让 `_consume_worker_events` 进入 `finally` 释放 lane token。`dispatch.py` 新增 `_LOCAL_WORKER_CLOSE_GRACE_SECONDS = 3.0` 作为 bounded cleanup grace，不是第二套 cancel timeout。
- **旧 tool/provider 结果不可污染 cancelled Run**：现有 ToolRuntime accept barrier（Run/Attempt/dispatch 同源校验）和 Engine ingest late rejection 未被修改。process-backed capsule 的 late result 由父进程 Host 独占治理，子进程不得返回 `host_cancelled` / `timeout` / `awaiting` 信封。
- **tool_execution_timeout_seconds 不被延长**：所有 deadline 继续来自 `BatchToolExecutionContext.timeout_seconds`。`_LOCAL_WORKER_CLOSE_GRACE_SECONDS` 是 cleanup grace，不是 cancel timeout，不从 `tool_execution_timeout_seconds` 派生。PR 未引入第二套 timeout。

### 2. PR Body 准确性

**验证结果：PASS。**

- `Closes #87`：正确。WU-TOOLS-CANCEL-01 是 #87 umbrella 最后的 closeout slice；WU-LIFE-03、WU-LIFE-04、WU-WAIT-01/02/03 均已完成并 merge。PR #170 是 #87 关闭前置的最后一项。
- Validation 部分：pytest 219 passed + 92 passed、pyright 0 errors、git diff --check passed — 与 PR body 声明一致。
- Residual risks：PR body 正确列出了 process envelope structured hints、Web process cold-start cost、Playwright nested process cleanup、Fins real XBRL fixture breadth、process envelope constants single-source cleanup、process capsule grace-period tuning — 均为 non-blocking follow-up hardening，不阻塞 #87 closeout。

### 3. Typed Execution Capability 复核

**验证结果：PASS。**

- `dayu/contracts/tool_execution.py`：新增 `ToolExecutionMode`（StrEnum）、`ProcessBackedToolContext`、`ProcessBackedToolTarget`（Protocol）、`ProcessBackedToolTargetFactory`（Protocol）、`AsyncDirectToolExecutionCapability`、`ThreadBackedToolExecutionCapability`、`ProcessBackedToolExecutionCapability`。所有类型 frozen、slots、有完整中文 docstring。`ToolExecutionCapability` 是封闭 TypeAlias 联合。
- `ToolDefinition.execution`：默认 `AsyncDirectToolExecutionCapability()`，不进入 LLM-facing schema。
- `dayu/runtime/tools_discovery.py`：digest 包含 execution mode 稳定 JSON 投影，不含 callable 或 factory 对象身份。
- `ToolDefinition` 所有直接构造站点已迁移：Doc、Fins download/preprocess/upload、Host framework `fetch_more`、tests helpers。

### 4. Host Declaration-backed Factory 复核

**验证结果：PASS。**

- `DeclaredToolExecutionCapsuleFactory`：持有 `EffectiveToolBundle`，从 `ToolDefinition.execution` 选择 capsule。不按工具名特判。
- `ToolRuntimeBuildRequest.execution_capsule_factory`：可选测试注入；默认使用 `DeclaredToolExecutionCapsuleFactory`。
- `create_tool_runtime()` 中 factory 优先级正确：测试注入 > declaration-backed 默认。
- `_declared_capsule_for_execution()`：三路 isinstance dispatch，未知类型抛 `TypeError`。

### 5. Doc/Fins/Web Process-backed 复核

**验证结果：PASS。**

- **Doc**：`_DocProcessTargetFactory` 只保存 `allowed_root_locators`（str tuple）和 `DocToolLimits`。`_DocProcessTarget` 子进程内通过 `_resolve_allowed_root_locators()` 重新解析路径。不捕获 lock、processor、runtime。五个 Doc tools 均声明 `ProcessBackedToolExecutionCapability`。
- **Fins read**：`_FinsReadProcessTargetFactory` 只保存 `workspace_root_locator`（str）和 `FinsToolLimits`。`_FinsReadProcessTarget` 子进程内通过 `DefaultFinsRuntime.create(workspace_root=Path(...))` 重新打开只读仓储。九个 read tools 均声明 `ProcessBackedToolExecutionCapability`。Fins download/preprocess/upload 保持 `AsyncDirectToolExecutionCapability`（awaiting lifecycle）。
- **Web**：`_WebProcessTargetFactory` 只保存 `WebToolsConfig`。`_WebProcessTarget` 子进程内创建短生命周期 session。search_web 和 fetch_web_page 均声明 `ProcessBackedToolExecutionCapability`。Playwright 不可序列化 worker 已 fail closed（返回 `unprocessable`）。

### 6. Fins WAITING Lifecycle 保持

**验证结果：PASS。**

`download_tools.py`、`preprocess_tools.py`、`upload_tools.py` 均显式声明 `execution=AsyncDirectToolExecutionCapability()`。它们的 awaiting `EXTERNAL_JOB` lifecycle 不受影响。

### 7. Aggregate Validation Evidence

**验证结果：PASS。**

PR 包含完整的 S2 aggregate validation evidence：
- `docs/reviews/wu-tools-cancel-01-s2-aggregate-deepreview-mimo.md`
- `docs/reviews/wu-tools-cancel-01-s2-aggregate-deepreview-ds.md`
- `docs/reviews/wu-tools-cancel-01-s2-aggregate-deepreview-controller-adjudication.md`

Controller adjudication accepted aggregate，所有 accepted findings 已修复。

### 8. Merge 前必须修复的问题

**未发现。**

- 代码：类型安全（pyright 0 errors）、process target 可序列化（pickle round-trip 测试覆盖）、信封解析 fail-closed（malformed/unsupported/reserved status 均返回 `ToolFailedOutcome`）。
- 测试：覆盖 async_direct、thread_backed、process_backed 三种 capsule 模式；覆盖 cancel/timeout/terminate/kill 路径；覆盖 late result quarantine；覆盖 envelope parsing 正常和异常路径。Doc/Fins/Web 各有 process target 专项测试。
- README/design/control doc：`dayu/README.md`、`dayu/host/README.md`、`dayu/fins/README.md`、`docs/host/issues-implementation-control.md` 均已更新。新增 plan 文档和 review artifacts。
- PR metadata：draft 状态正确，body 准确，`Closes #87` 合理。

### 9. Checks 未报告

**Non-blocking caveat。**

`gh pr checks 170` 返回 `no checks reported on the 'phase/wu-tools-cancel-01' branch`。这表明该 branch 未配置 CI checks（或 checks 未触发）。PR body 手动报告了 pytest / pyright / git diff --check 结果。建议 merge 前确认 CI 是否需要配置，或 maintainer 接受手动验证。

## Open Questions

无。

## Residual Risk

- **Process envelope constants single-source cleanup**：`_FINS_PROCESS_*`、`_DOC_PROCESS_*`、`_WEB_PROCESS_*` 和 `_PROCESS_ENVELOPE_*` 常量分散在多个模块。当前通过 Host capsule envelope parsing 统一约束，但常量本身未抽取为共享定义。Non-blocking follow-up。
- **Web process cold-start cost**：每次 Web tool 调用都会 spawn 子进程并创建新的 requests session。当前 #87 目标优先级是取消可抢占性，性能优化可后续评估 worker pool。Non-blocking。
- **Playwright nested process cleanup**：Playwright 不可序列化 worker 已 fail closed，但未覆盖 nested process cleanup smoke/stress。Non-blocking。
- **Fins real XBRL spawned-child fixture breadth**：Fins read process target 测试覆盖了 fast path、processor path 和 financial statement path，但 XBRL 专项覆盖可扩展。Non-blocking。
- **Process capsule grace-period tuning**：`_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS = 0.2` 和 `_PROCESS_CAPSULE_KILL_GRACE_SECONDS = 0.2` 是初始值，生产环境可能需要调优。Non-blocking。
- **CI checks 未配置**：branch 无 CI checks 报告。建议确认 CI 配置或 maintainer 接受手动验证。

## Verdict

**PASS**

PR #170 完整覆盖 WU-TOOLS-CANCEL-01 的所有验收信号，typed execution capability 设计正确，process-backed 迁移覆盖 Doc/Fins/Web 生产路径，Fins WAITING lifecycle 保持不变，测试覆盖充分，README/design 同步完整。无 blocking findings。建议 maintainer review 后 merge。

---

## Artifact Path

`docs/reviews/wu-tools-cancel-01-pr-170-review-mimo.md`

READY_FOR_CONTROLLER
