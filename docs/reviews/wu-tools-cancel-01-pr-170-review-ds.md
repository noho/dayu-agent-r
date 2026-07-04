# WU-TOOLS-CANCEL-01 PR #170 Review — AgentDS

## Scope

- **Mode**: PR review
- **Repository**: noho/dayu-agent-r
- **PR**: #170
- **Title**: WU-TOOLS-CANCEL-01: harden tool/provider cancellation
- **Author**: noho
- **Head branch**: `phase/wu-tools-cancel-01`
- **Base branch**: `main`
- **URL**: https://github.com/noho/dayu-agent-r/pull/170
- **Review artifact**: `docs/reviews/wu-tools-cancel-01-pr-170-review-ds.md`
- **Parallel review coverage**: 无；本 review 由 AgentDS 单线完成，沿 typed execution contract → Host capsule factory → Doc/Fins/Web provider → accept barrier → cancel/timeout closeout 逐链路走读

## Prerequisite Facts

- Issue #87 (OPEN) 是 Host Lifecycle Watchdog / Supervisor umbrella，含 child #91 (CLOSED) 和 #92 (CLOSED)
- 本 PR 是 WU-TOOLS-CANCEL-01 的 draft PR，声称是 #87 的 "final closeout slice"
- Commit 链: S1 interrupt capsule → S2 partial hardening → typed execution plan → S2A1 execution contract → S2A2 host factory wiring → S2B doc → S2C Fins read → S2D web → S2 aggregate validation
- `gh pr checks 170` 返回错误（no checks reported on branch），见下 Non-blocking Caveats

## Findings

### 01-NEEDS_FIX-严重-PR body "Closes #87" 表述不准确且缺乏证据支撑

- **入口/函数**: PR body Summary 段
- **文件(行号)**: PR #170 body line 3
- **输入场景**: 审阅者以 issue #87 的 scope 和 acceptance criteria 对 PR 进行 closeout 验证
- **实际分支**: PR body 写 "Closes #87" 并声称是 "final #87 closeout slice"
- **预期行为**: PR body 应准确说明与 #87 的关系。若 PR 对 #87 的原始 scope（shared lifecycle watchdog/supervisor umbrella）有替代方案，应引用授权该方案变更的 plan document；若只覆盖 #87 的部分子目标，应明确引用 child issues #91/#92 而非 umbrella
- **实际行为**: PR body 声称 Closes #87，但 #87 的 acceptance criteria 包括：
  1. `docs/host/design.md` 引入 shared Host lifecycle watchdog / supervisor design
  2. #91 和 #92 消费 shared supervisor 而非独立 watchdog
  3. 共享 common lifecycle concepts

  本 PR 实现的是 typed execution capability + process-backed execution + Host capsule terminate/kill，与 #87 的 "shared supervisor" 架构路径不同。child issues #91/#92 已 CLOSED，但本 PR diff 中未见 `docs/host/design.md` 的 shared supervisor design 变更，也未见统一的 watchdog runtime。若 plan document（`docs/host/wu-tools-cancel-01-plan.md`，不在本 branch 上）已授权此路径变更，PR body 应引用该文档；若未授权，则 PR body 不应声称 Closes #87
- **直接证据**:
  - `gh issue view 87` 显示 acceptance criteria 要求 shared supervisor design 与 child issue 消费 shared machinery
  - PR diff 中无 `docs/host/design.md` 变更
  - PR diff 中无统一 watchdog/supervisor runtime 实现
  - PR body 未引用 plan document 说明架构路径变更
- **影响**: PR metadata 误导审阅者对 closeout 范围的判断；若按 #87 原始 scope 审计，会发现缺失 shared supervisor design doc、缺失统一 watchdog runtime，不应判定为 close #87
- **建议改法和验证点**:
  - 最小修复：PR body 改为 "Contributes to #87 closeout" 或引用具体 child issues #91/#92，或引用计划文档解释架构路径变更
  - 若 plan document 已授权此路径：PR body 应显式引用该文档并说明 typed execution capability + process-backed 方案是 #87 的最终 closeout 路径，而非 shared supervisor
  - 验证点：PR body 修改后重新检查与 issue #87 scope 的对齐
- **修复风险（低）**: 仅修改 PR body 文本，不影响代码
- **严重程度（严重）**: PR metadata 错误会影响 merge 决策和后续 traceability；若不修正，merge 后 issue #87 会被 GitHub 自动关闭，但其原始 scope（shared supervisor design）实际未完成

### 02-NEEDS_FIX-中-PR body Residual Risks 段格式不符合 Gateflow 留痕要求

- **入口/函数**: PR body Residual Risks 段
- **文件(行号)**: PR #170 body Residual Risks 段
- **输入场景**: 后续 work unit owner 或 on-call 需按 residual risk 定位相关代码与修复入口
- **实际分支**: PR body 将 6 项 residual risk 以 narrative paragraph 形式列出，无结构化 owner/destination/trigger 映射
- **预期行为**: Residual risk 应按结构化格式记录：每条至少包含 risk description、当前缓解证据、owner/destination（后续 work unit 或 issue）、判定（accepted/deferred）
- **实际行为**: 6 项 risk 以 narrative 方式列出："process envelope structured hints, Web process cold-start cost, Playwright nested process cleanup smoke/stress coverage, Fins real XBRL spawned-child fixture breadth, process envelope constants single-source cleanup, and process capsule grace-period tuning"，无 owner/destination，无结构化判定
- **直接证据**: PR body Residual Risks 段全文为单段 narrative，与 S2E aggregate validation artifact（`docs/reviews/wu-tools-cancel-01-s2e-aggregate-validation-codex.md`）中的结构化 residual risk 表格式不一致
- **影响**: 后续 owner 无法快速定位自己的责任项；merge 后 residual risk 可能丢失 owner
- **建议改法和验证点**:
  - 最小修复：补充结构化 residual risk 表，至少包含 risk / evidence / decision / owner 四列
  - 或：引用 S2E aggregate validation artifact 中的 residual risk 表，PR body 只做摘要
  - 验证点：确认每项 residual risk 有明确的后续 owner 或判定为 accepted
- **修复风险（低）**: 仅修改 PR body，不涉及代码
- **严重程度（中）**: 影响长期可维护性和 residual risk 追踪，但不影响当前代码正确性

### 03-非阻塞-低-PR checks 未报告

- **入口/函数**: CI/check infrastructure
- **文件(行号)**: N/A（infrastructure）
- **输入场景**: 审阅者需要 PR checks 结果验证测试和类型检查通过
- **实际分支**: `gh pr checks 170` 返回 "no checks reported on the 'phase/wu-tools-cancel-01' branch"
- **预期行为**: PR 应有 CI checks 报告（pytest、pyright、lint）或显式说明 CI 未配置
- **实际行为**: 无任何 check 报告
- **直接证据**: `gh pr checks 170` exit code 1，输出 "no checks reported"
- **影响**: 审阅者无法从 GitHub UI 直接确认 CI 通过；需手动重现验证
- **建议改法和验证点**:
  - Non-blocking: PR body 已列出本地验证命令和结果（pytest 219+92 passed, pyright 0 errors）
  - 若仓库有 CI 配置，确认 branch 命名是否匹配 CI trigger 规则
  - 若仓库无 CI，此为已知状态，记录为 caveat 即可
- **修复风险**: N/A
- **严重程度（低）**: PR body 已提供手动验证结果，不阻塞 merge；但应记录为 caveat

## Architecture & Implementation Review

以下按用户指定的重点审查维度逐项报告。无 material finding 的维度标记为 PASS。

### 1. Host Esc/cancel 后快速回到可交互

**结论: PASS**

证据链:
- `_dispatch_tool_call_with_bounds()` (`dayu/host/tool_runtime.py:3175`) 使用 `wait_for_or_cancel()` 等待 capsule task，支持 cancel token 和 timeout 双路径
- cancel 路径: `WaitCancelled` → `_interrupt_capsule_after_wait()` → terminate (0.2s grace) → kill if needed (0.2s grace) → task cancel → close → 返回 `_governed_failure_outcome`
- timeout 路径: `WaitTimedOut` → 同上 interrupt 路径 → 返回 governed timeout failure
- 预检查: `context.cancellation_token.is_cancelled()` 在 `_dispatch_tool_call_with_bounds` line 3193 提前短路，避免进入 capsule 创建
- 超时预检查: `_remaining_batch_timeout_seconds()` 在 line 3189 提前短路 ≤0 的剩余预算
- Process capsule terminate/kill 总 blocking ≤0.6s（0.2s terminate grace + 0.2s kill grace + close），符合"快速回到可交互"

### 2. 旧 tool/provider 结果不可污染 cancelled Run

**结论: PASS**

证据链:
- Cancel/timeout 时 `_dispatch_tool_call_with_bounds` 返回 `_governed_failure_outcome(decision)`，而非 `wait_result.value`
- Capsule task 的原始结果被丢弃（`_interrupt_capsule_after_wait` line 3275-3280 cancel task 后不读取 task.result()）
- `_tool_outcome_from_process_envelope()` (`dayu/host/tool_runtime.py:6532`) 对 `awaiting`、`cancelled`、`timeout`、`host_cancelled` 信封 fail closed，子进程无法伪造 Host-governed 状态
- Process capsule `run()` 使用 `timeout_seconds=None`（无限等待），但被 `wait_for_or_cancel` 的 Host 级 timeout 外层保护
- 测试 `test_tool_runtime_process_backed_cancel_does_not_wait_for_natural_completion` (`tests/host/test_toolruntime_executor.py:1577`) 验证 cancel 后不等待自然完成，callable 调用次数为 0
- Doc/Fins/Web provider 级测试均有 "cancel 后不接受 late result" 覆盖

### 3. tool_execution_timeout 不被延长

**结论: PASS**

证据链:
- Timeout 在 `_dispatch_tool_call_with_bounds` 层由 `wait_for_or_cancel(timeout_seconds=...)` 执行，不进入 capsule 内部
- Capsule `run()` 内部无限等待 (`timeout_seconds=None`)，但 timeout 已在 Host 层触发并返回 `WaitTimedOut`
- `_interrupt_capsule_after_wait` 的 terminate/kill 是 cleanup 步骤，发生在 timeout decision 之后，不延长原始 timeout budget
- `_remaining_batch_timeout_seconds()` 在每次调用前重新计算剩余预算，使用 monotonic clock 避免时钟回拨

### 4. Typed execution capability

**结论: PASS**

证据链:
- `ToolExecutionCapability` 封闭联合 (`dayu/contracts/tool_execution.py:139`)：`AsyncDirect | ThreadBacked | ProcessBacked`
- `ToolDefinition.execution` 字段 (`dayu/contracts/tool_declaration.py:114`) 默认 `AsyncDirectToolExecutionCapability()`
- `@tool(...)` 装饰器支持 `execution=` 参数 (`dayu/contracts/tool_declaration.py:249`)，不进入 LLM-facing schema
- Execution capability 进入稳定 digest 但只记录 mode（process_backed 不记录 target_factory identity）
- `tools_discovery.py` 的 `_tool_execution_json_value()` (`dayu/runtime/tools_discovery.py:463`) 按类型分别投影 async/thread/process 的 digest shape

### 5. Host declaration-backed factory

**结论: PASS**

证据链:
- `DeclaredToolExecutionCapsuleFactory` (`dayu/host/tool_runtime.py:1544`) 从 `ToolDefinition.execution` 选择 capsule
- 生产默认路径 (`dayu/host/tool_runtime.py:3984-3987`): `request.execution_capsule_factory or DeclaredToolExecutionCapsuleFactory(effective_bundle)`
- `_declared_capsule_for_execution()` 的 dispatch 顺序: `AsyncDirect` → `ThreadBacked` → `ProcessBacked` → `TypeError`
- 测试 `test_tool_runtime_default_factory_uses_declared_process_backed_execution` 验证 factory 按声明选择 process-backed capsule，context 投影正确，callable 不被调用

### 6. Doc process-backed

**结论: PASS**

证据链:
- 五个 Doc tools (`list_files`, `get_file_sections`, `search_files`, `read_file`, `read_file_section`) 均声明 `ProcessBackedToolExecutionCapability`(`dayu/tools/doc_tools.py:2184-2202`)
- `_DocProcessTargetFactory` 只保存 spawn 可序列化路径 locator，不捕获 provider lock、DocumentProcessor、repository
- `_DocProcessTarget` 子进程内使用 `_DocProcessCancellationToken`（永不取消），真实取消由父进程 capsule 独占
- `_invoke_doc_business()` 仍保留为 fallback callable，供测试和非生产路径使用（不进入生产代码的 process-backed 路径）

### 7. Fins process-backed 与 WAITING lifecycle 保持

**结论: PASS**

证据链:
- 九个 Fins read tools 声明 `ProcessBackedToolExecutionCapability` (`dayu/fins/tools/fins_tools.py`)
- Fins download/preprocess/upload 声明 `AsyncDirectToolExecutionCapability()`，返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`
- Process target factory 只保存配置、workspace root 等可序列化字段，子进程内重建 `DefaultFinsRuntime`
- WAITING 工具不进入 process-backed 路径，awaiting accept / wait-resume lifecycle 保持

### 8. Web process-backed

**结论: PASS**

证据链:
- `search_web` / `fetch_web_page` 声明 `ProcessBackedToolExecutionCapability` (`dayu/tools/web/web_tools.py:1204,1243`)
- `_WebProcessTargetFactory` 只保存可序列化 `WebToolsConfig`，不捕获 `requests.Session`、provider lock、CancellationToken、Playwright runtime
- `_WebProcessTarget` 子进程内使用 `_WebProcessCancellationToken`，取消由父进程 capsule 独占
- `_execute_web_process_business_value()` 在子进程内重建参数校验和业务路由
- Playwright nested process 场景仍由 `_fetch_and_convert_with_playwright` 在子进程内处理，父进程 cancel 时 terminate/kill 整个 process tree

### 9. Aggregate validation evidence

**结论: PASS**

证据链:
- S2E aggregate validation (`docs/reviews/wu-tools-cancel-01-s2e-aggregate-validation-codex.md`) 已验证:
  - Production execution mode matrix (contract/discovery/Host/Doc/Fins read/Web/Fins awaiting)
  - Late-result accept barrier across all tool families
  - Residual risk adjudication with owner/destination
- `tests/README.md` 已更新覆盖: contract execution capability, Doc process-backed late-result, Fins read process-backed, Fins awaiting EXTERNAL_JOB

## Open Questions

- **OQ1**: WU-TOOLS-CANCEL-01 plan document (`docs/host/wu-tools-cancel-01-plan.md`) 是否已授权 typed execution capability + process-backed 方案替代 #87 原始 shared supervisor 架构？该文档不在本 branch 上，无法验证。若已授权，finding 01 的修复只需在 PR body 中引用该文档；若未授权，需讨论 #87 scope 是否应更新
- **OQ2**: `_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS = 0.2` 和 `_PROCESS_CAPSULE_KILL_GRACE_SECONDS = 0.2` 的取值依据是什么？0.2s 对重度 I/O 的子进程（如 Playwright browser cleanup）是否足够？当前测试用 `_SleepingProcessTarget(sleep_seconds=5.0)` 和 `_IgnoreTerminateProcessTarget` 覆盖了 terminate 成功和忽略两种场景，但未覆盖 terminate 耗时 >0.2s 但 < 某个合理上限的边界

## Residual Risk

| Risk | Severity | Owner/Destination |
|---|---|---|
| Web process cold-start cost (per-call process spawn for Web tools) | 低 | Later performance work |
| Playwright nested process cleanup 无 smoke/stress 覆盖 | 低 | Later Web/Playwright cleanup smoke test |
| Fins `query_xbrl_facts` 无独立 spawned-child real XBRL fixture | 低 | Later Fins XBRL fixture expansion |
| Process envelope 无独立 hint 字段（hint 合入 message） | 低 | Later Host process envelope contract hardening |
| Doc FIFO fixture 扩展了 `read_file` 允许文件类型 | 低 | Later Doc security review if disallowed |
| Process capsule grace-period (0.2s/0.2s) 未覆盖重度 subprocess cleanup 边界 | 低 | OQ2 follow-up |

## Conclusion

**NEEDS_FIX**

Finding 01（PR body "Closes #87" 表述不准确）必须在 merge 前修复。Finding 02（Residual Risks 格式）建议一并修复。

其他维度 — typed execution capability、Host declaration-backed factory、Doc/Fins/Web process-backed、Fins WAITING lifecycle 保持、cancel/timeout/late-result accept barrier、tool_execution_timeout 不延长 — 均通过审查。代码实现与架构设计在 review scope 内未发现 material defect。

README 更新（`tests/README.md`）准确反映了新增测试覆盖范围。`dayu/README.md` 和 `dayu/contracts/__init__.py` 的更新准确反映了新增公共符号。

## Non-blocking Caveats

1. **No CI checks reported**: `gh pr checks 170` 返回错误，branch 上无 checks。PR body 已提供手动验证结果（pytest 219+92 passed, pyright 0 errors），不阻塞 merge。
2. **OQ2**: Process capsule grace-period 常数的取值依据建议在后续 hardening 中补充文档或测试覆盖。
