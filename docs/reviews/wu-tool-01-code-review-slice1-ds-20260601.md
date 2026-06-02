# WU-TOOL-01 Slice 1 Code Review

## Gate / Role

- Gate: code review
- Role: code review specialist; 只产出 review artifact，不改 source/test/doc，不 commit/push/PR
- Work unit: WU-TOOL-01 Attempt-scoped Duplicate Governance
- Slice: 1 - Typed Policy And Attempt-scoped Duplicate State
- Approved plan: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- Implementation artifact: `docs/reviews/wu-tool-01-implementation-slice1-codex-20260601.md`

## Review Scope

- `dayu/host/tool_duplicate_governance.py` (new)
- `dayu/host/tool_runtime.py` (modified)
- `tests/host/test_toolruntime_duplicate_governance.py` (modified)
- `docs/reviews/wu-tool-01-implementation-slice1-codex-20260601.md` (implementation artifact)

## Verification Results

- **Tests**: `python -m pytest tests/host/test_toolruntime_duplicate_governance.py` — **24 passed**, 0 failed
- **Pyright**: `pyright` — **0 errors, 0 warnings**
- **Terminology grep**: `rg "run-local|run-scoped|RunScoped|RunLocal|同 Run" dayu/host/tool_runtime.py tests/host/test_toolruntime_duplicate_governance.py` — remaining matches are:
  - Unrelated truncation wording (run-scoped truncation, run-local cursor/remainder)
  - `RunScopedDuplicateGovernanceRegistry` / `InMemoryRunScopedDuplicateGovernanceRegistry` — documented residual for Slice 2 (see finding M1)
  - No "同 Run" matches in either file

## Findings

### 1-M1 [未修复] [中] Plan sequencing gap — RunScopedDuplicateGovernanceRegistry / InMemoryRunScopedDuplicateGovernanceRegistry 仍驻留在 tool_runtime.py

**证据**:

- `dayu/host/tool_runtime.py:1030-1063` — `RunScopedDuplicateGovernanceRegistry(Protocol)` 完整保留
- `dayu/host/tool_runtime.py:1518-1569` — `InMemoryRunScopedDuplicateGovernanceRegistry` 完整保留，含 `active_run_count()`
- `dayu/host/tool_runtime.py:2056` — `ToolRuntimeBuildRequest.duplicate_governance_registry: RunScopedDuplicateGovernanceRegistry | None = None`
- `dayu/host/dispatch.py:190` — `from dayu.host.tool_runtime import ... InMemoryRunScopedDuplicateGovernanceRegistry`
- `dayu/host/dispatch.py:735` — `self._duplicate_governance_registry = InMemoryRunScopedDuplicateGovernanceRegistry()`
- 上述类不在 `tool_runtime.py:__all__` 中（line 5466-5537）

**分析**:

Approved plan Slice 1 expected outcome: "No run-scoped duplicate class or protocol remains in tool_runtime.py or __all__." 但 Slice 1 allowed files 明确排除 `dispatch.py`，而 `dispatch.py` 仍 import 并实例化 `InMemoryRunScopedDuplicateGovernanceRegistry`。如果在 Slice 1 删除这些类，`dispatch.py` 会 import 失败，导致代码在两个 slice 之间不可构建。

Implementation artifact 将此记录为 documented residual: "Removing those names inside this slice would require editing dispatch.py, which the handoff explicitly forbids."

当前 `InMemoryRunScopedDuplicateGovernanceRegistry.duplicate_governance_for_run()` 实际创建的是 `InMemoryAttemptDuplicateGovernance(policy)`（line 1542），忽略 `run_id` 参数对 governance 状态的影响。这意味着它已不具备 run-scoped 共享语义，是纯 compatibility facade，违反 AGENTS.md "禁止兼容性代码：兼容性 wrapper / facade"。

**判定**: 非 Slice 1 blocking。这是 plan 本身的 sequencing gap（Slice 1 要求删除但禁止编辑依赖文件）。正确解决路径是 Slice 2 先更新 `dispatch.py` 的 import 和装配，再回 `tool_runtime.py` 删除这些类。当前状态是 Slice 1 → Slice 2 之间的合理过渡态。

**建议**: Slice 2 实现时必须作为第一项工作删除这三个符号（protocol、class、BuildRequest field），不得遗漏。

---

### 2-M2 [未修复] [中] tool_runtime.py __all__ 中存在 duplicate governance typed contracts 兼容性 re-export

**证据**:

- `dayu/host/tool_runtime.py:5472-5492` — `__all__` 中列出: `DuplicateAcceptedEntry`, `DuplicateDecision`, `DuplicateDecisionKind`, `DuplicateDurableMissingReason`, `DuplicateGovernanceMessages`, `DuplicateGovernancePolicy`, `DuplicateGovernanceRequest`, `DuplicateGovernanceScope`, `InMemoryAttemptDuplicateGovernance`
- 这些符号在 `tool_runtime.py:121-131` 从 `dayu.host.tool_duplicate_governance` import
- Approved plan Section 6: "Do not keep compatibility re-exports in tool_runtime.py; callers must import duplicate governance typed contracts from dayu.host.tool_duplicate_governance."
- AGENTS.md: "禁止兼容性代码：兼容性 re-export：仅为保持旧导入路径而转发符号。"

**分析**:

grep 确认当前没有其他 Host 模块（除 dispatch.py 外）从 `tool_runtime.py` import 这些类型。`dispatch.py` 使用 `from dayu.host.tool_runtime import ...` 导入，但那是 Slice 2 的清理范围。测试文件已直接从 `dayu.host.tool_duplicate_governance` 导入。

**判定**: 非 Slice 1 blocking。这些 re-export 应在 Slice 2（dispatch.py 更新导入路径后）一并从 `__all__` 和 import 中移除。

---

### 3-M3 [未修复] [中] Awaiting 工具路径与 duplicate in-flight owner finally 块的交互缺陷

**证据**:

- `dayu/host/tool_runtime.py:2225-2228` — `duplicate_owner_needs_terminal` 对 fresh ALLOW owner 设为 True
- `dayu/host/tool_runtime.py:2279-2291` — `ToolAwaitingOutcome` 走 `_accept_awaiting` 分支，`_accept_awaiting` 内部不设置 `duplicate_terminal_recorded`（因为该变量在 `_execute_one` 闭包中，`_accept_awaiting` 无法访问）
- `dayu/host/tool_runtime.py:2346-2351` — finally 块对 `duplicate_owner_needs_terminal and not duplicate_terminal_recorded` 调用 `record_durable_missing`
- `dayu/host/tool_runtime.py:2571-2573` — `_accept_awaiting` 中注释 "Awaiting 是等待中间态，不写入 duplicate accepted index" 且 `del duplicate_request`（不影响外层变量）

**分析**:

当 fresh owner 的工具 callable 返回 `ToolAwaitingOutcome` 时：
1. in-flight record 已在 `decide_duplicate()` 中创建（state=OWNER_RUNNING）
2. `_accept_awaiting` 处理 awaiting accept
3. 方法返回后 finally 触发 `record_durable_missing(reason=GOVERNED_BEFORE_ACCEPT)`
4. in-flight record 被设为 DURABLE_MISSING 并从 map 中移除

Awaiting 本身不是 failure — 它是合法的中间态，Engine 后续会以新 iteration resume。但 `record_durable_missing` 将 in-flight 窗口标记为 "owner 未产生 accepted fact"，这有两方面影响：

- **对 concurrent duplicate waiter**: 如果同 Attempt 内有并发重复调用在等待此 owner，waiter 将收到 DURABLE_MISSING 而非等待 owner 的 awaiting 解析。这在语义上有偏 — 理想情况下 waiter 应同样进入 awaiting 或收到合适的等待通知。
- **对后续 resume**: Engine resume 时创建新 iteration 的新 tool call，此 call 进入 duplicate governance 时发现既无 in-flight record 也无 accepted entry，被授予 fresh ALLOW — 这实际是正确的恢复行为。但 resume call 的 duplicate key 与原始 awaiting call 相同，它不应被视为 "新" 请求。

**缓解因素**: 此场景要求 awaiting 工具同时存在同 Attempt 并发重复调用方，在实际财报分析场景中极为罕见。

**判定**: 非 Slice 1 blocking，但建议在 Slice 2 之前或 Slice 2 中处理。可能的修复方向：
- 为 awaiting 引入专门的 duplicate terminal 状态（如 `_InFlightDuplicateState.AWAITING`），使 waiter 也能进入等待
- 或显式记录 "awaiting 不在 duplicate governance 范围内"，不在 finally 中 release in-flight record

---

### 4-M4 [未修复] [低] `_duplicate_message()` 使用默认 DuplicateGovernanceMessages 而非配置 policy 的 messages

**证据**:

- `dayu/host/tool_runtime.py:4737-4744`:
  ```python
  def _duplicate_message(kind: DuplicateDecisionKind) -> str:
      return DuplicateGovernanceMessages().message_for(kind)
  ```
- 此函数在 `_policy_decision_from_duplicate` line 4672 作为 fallback:
  ```python
  message=decision.message or _duplicate_message(decision.kind),
  ```
- 在 `_validate_duplicate_governed_candidate` line 4056 作为 fallback:
  ```python
  expected_message = candidate.duplicate_decision_message or _duplicate_message(decision)
  ```

**分析**:

当前所有正常路径中 `decision.message` / `candidate.duplicate_decision_message` 均从配置 policy 的 messages 填充（via `InMemoryAttemptDuplicateGovernance._decision_for_accepted_entry` line 449, `_allow_decision` line 501, DURABLE_MISSING 路径 line 374）。因此 `_duplicate_message` 的 fallback 路径在正常流程中不会被触发。

但函数签名设计有缺陷：它不接收 policy 参数，任何时候调用都创建新的默认 `DuplicateGovernanceMessages()`。如果未来有代码路径创建 `DuplicateDecision` 时遗漏 message，fallback 将使用默认消息而非配置消息。

Approved plan Section 7.10 要求: "`_policy_decision_from_duplicate()` must read messages from `DuplicateGovernancePolicy.messages`, not from `_duplicate_message()` hardcoded branches."

当前实现已满足此要求（主路径从 `decision.message` 读取），但 `_duplicate_message()` 的 fallback 行为不符合 typed policy 精神。

**判定**: 低优先级。建议将 `_duplicate_message` 改为接收 `DuplicateGovernancePolicy` 参数或直接删除（在确认 fallback 永不被触发后）。

---

### 5-L1 [未修复] [低] 缺少 owner cancellation 并发测试

**证据**:

- Implementation artifact: "Owner cancellation via external cancellation token is covered in implementation through bounded cancellation durable-missing mapping, but the slice test added for owner failure focuses on callable exception plus accept rejected/timeout."
- `dayu/host/tool_runtime.py:2440-2442` — cancellation 路径返回 `_runtime_cancelled_policy_decision` → `bounded_policy_decision` 非 None → `durable_missing_reason = _durable_missing_reason_for_policy(...)` → finally 块 record_durable_missing
- 测试文件中有 `_BlockingCountingTool` 和 `asyncio.Event` 原语可用于构建此类测试

**分析**:

代码路径存在且逻辑正确，但缺少并发测试验证 waiter 在 owner 被取消时收到正确的 DURABLE_MISSING 决策。现有 `_OpenCancellationToken` 始终返回未取消，无法用于触发取消路径。

**判定**: 非 blocking。建议在 Slice 2 或后续补充使用 `asyncio.Event` + 可控 cancellation token 的并发测试。

---

### 6-L2 [未修复] [低] Timeout 测试断言弱于同类测试

**证据**:

- `tests/host/test_toolruntime_duplicate_governance.py:826-854` — `test_same_attempt_concurrent_timed_out_accept_reports_durable_missing`
- 只断言 `tool.call_count == 1`（line 854）
- 同类 rejected accept 测试（line 783-823）断言:
  - `tool.call_count == 1`
  - owner/waiter outcome 均为 `ToolFailedOutcome`
  - waiter outcome hint 为 `"duplicate_prior_accept_missing"`
  - 后续第三次调用重新执行（`tool.call_count == 2`）

**分析**:

Timeout 测试未验证 waiter outcome 类型、hint 内容、或第三次调用的 fresh ALLOW 行为。虽然 timeout 路径与 rejected 路径在 `_execute_one` 中走相同的 `finally` 清理逻辑，但测试覆盖度不一致。

**判定**: 低优先级。建议补齐与 rejected 测试对等的断言。

---

### 7-L3 [未修复] [低] tool_trace.py 未携带 duplicate_scope

**证据**:

- `dayu/host/tool_trace.py:76-77` — 定义 `_FIELD_DUPLICATE_KEY`、`_FIELD_DUPLICATE_DECISION`
- 无 `_FIELD_DUPLICATE_SCOPE` 或 `duplicate_scope` 相关字段
- `dayu/host/tool_trace.py:722-723` — `ToolTraceRecord` 含 `duplicate_key`、`duplicate_decision` 但不含 `duplicate_scope`

**分析**:

Approved plan Slice 3 负责: "Update tool_trace.py constants/extractors/summary builder to carry duplicate_scope." 当前 trace 携带 duplicate_key 和 duplicate_decision（均为 str），满足 Slice 1 要求。duplicate_scope 的 trace 集成属于 Slice 3 范围。

**判定**: 按计划延期至 Slice 3，非 Slice 1 缺陷。

---

## 计划符合性逐项检查

| Plan Slice 1 要求 | 状态 | 证据 |
|---|---|---|
| 新增 `dayu/host/tool_duplicate_governance.py` | 已实现 | 文件存在，580 行，完整类型定义 |
| `DuplicateGovernanceScope` with `kind: Literal["attempt"]`, `attempt_id` | 已实现 | L48-68, `__post_init__` 校验 |
| `DuplicateGovernanceRequest` 带 `scope: DuplicateGovernanceScope` | 已实现 | L188-226 |
| `DuplicateDecision` 带 `scope: DuplicateGovernanceScope` | 已实现 | L254-277 |
| `DuplicateGovernanceMessages` 默认值 + 拒绝空/空白 | 已实现 | L71-117, 测试 `test_duplicate_governance_messages_reject_empty_text` |
| `DuplicateGovernancePolicy` with typed config | 已实现 | L139-185 |
| `DuplicateGovernancePort` async | 已实现 | L987-1027, 三个方法均 `async def` |
| ToolRuntime callers await port | 已实现 | L2222, L2716, L2348 均 `await` |
| `_duplicate_key()` 含 `attempt_id` | 已实现 | L506-524, `scope` 包含 kind + attempt_id |
| In-flight owner/waiter 状态机 | 已实现 | `_AttemptDuplicateGovernanceState`, `_InFlightDuplicateRecord`, condition lock |
| owner terminal → record_durable_missing in finally | 已实现 | L2346-2351, 覆盖 accept rejected/timeout/cancelled/callable exception |
| allow 语义保持显式许可 | 已实现 | `_decision_for_accepted_entry` 对 ALLOW 调用 `_allow_decision`（带 prior_refs） |
| configure message 替换默认 | 已实现 | `DuplicateGovernanceMessages` 字段可自定义，测试覆盖 |
| 测试: key 含 attempt_id | 已实现 | `test_duplicate_key_includes_attempt_id` |
| 测试: 同 Attempt 并发 reuse | 已实现 | `test_same_attempt_concurrent_reuse_waits_for_owner_accept` |
| 测试: durable-missing (rejected/timeout/exception) | 部分 | rejected + exception 完整, timeout 断言弱 (见 L2) |
| 测试: allow 并发等 owner | 已实现 | `test_allow_policy_concurrent_waits_for_owner_before_second_execution` |
| 测试: allow 后 owner 完成再执行 | 已实现 | `test_allow_policy_post_owner_completion_executes_again` |
| 中文 docstring 完整 | 已实现 | 所有新增 class/function 含完整中文 docstring，参数/返回值/异常 |
| 无 Any/object/无类型签名 | 已实现 | 全文件类型签名完整 |
| 无 magic strings | 已实现 | reason codes 使用 enum 或模块级常量 |
| 删除 `_duplicate_message()` 或降为 policy method | 已降级 | L4737-4744 delegate to `DuplicateGovernanceMessages().message_for()` |
| `ToolRuntimeBuildRequest` 含 `duplicate_governance_policy` | 已实现 | L2053-2054 |
| Factory 创建 `InMemoryAttemptDuplicateGovernance` | 已实现 | L2893-2895, 忽略 `duplicate_governance_registry` 参数 |
| `TOOL_CALL_GOVERNED` payload 含 `duplicate_scope` | 已实现 | L3253-3255 |
| `ToolFactAcceptCandidate` 含 `duplicate_scope` | 已实现 | L436 |
| 工具 callable 和 Host accept 不在 condition lock 内 | 已实现 | `decide_duplicate` 在 `async with condition` 内获取/释放，executor 在外部 |

## AGENTS.md 合规检查

| 约束 | 状态 | 备注 |
|---|---|---|
| 中文 docstring 完整 | 通过 | 所有新代码 |
| 禁止 Any/object/无类型签名 | 通过 | 全类型标注 |
| 禁止 lazy import | 通过 | 无 lazy import |
| 禁止兼容性 re-export | 违规 | `__all__` re-export duplicate gov types (M2), defer to Slice 2 |
| 禁止 compatibility wrapper/facade | 违规 | `InMemoryRunScopedDuplicateGovernanceRegistry` (M1), defer to Slice 2 |
| 禁止 magic strings | 通过 | reason codes 使用 enum/常量 |
| 职责分离 | 通过 | contracts in `tool_duplicate_governance.py`, runtime in `tool_runtime.py` |
| 禁止 God object | 通过 | `_AttemptDuplicateGovernanceState` 职责清晰 |
| 函数模块级私有 | 通过 | 辅助函数均为模块级 |
| 禁止 hasattr/getattr | 通过 | 无使用 |

## 测试质量评估

### 并发测试真实性

- `test_same_attempt_concurrent_reuse_waits_for_owner_accept` (L741-780):
  - 使用 `asyncio.Event` 控制 owner 执行进度
  - `entered.wait()` 确保 owner 先进入执行
  - `asyncio.sleep(0)` 给 waiter 调度机会
  - 在 release 前断言 `tool.call_count == 1` 且 `not waiter.done()`
  - release 后 gather 等待两者完成
  - **结论**: 真并发测试，时序控制严谨

- `test_allow_policy_concurrent_waits_for_owner_before_second_execution` (L897-921):
  - 同样的 Event 模式
  - 断言 `tool.call_count == 1` 在 release 前
  - release 后断言 `tool.call_count == 2`
  - **结论**: 真并发测试

- 其他 concurrent 测试 (rejected/timeout/exception):
  - 均使用相同的 asyncio.Event + create_task + gather 模式
  - **结论**: 真并发测试

### 假阳性风险

- 无 `time.sleep()` 或固定延时等待 — 使用 Event 同步
- `asyncio.sleep(0)` 仅用于 yield event loop，不依赖时序
- 无 mock patch 覆盖核心并发逻辑
- **风险**: 低

### 测试命名

- 测试名称清晰描述场景和预期行为
- 使用 `test_same_attempt_concurrent_*` 前缀区分并发测试
- 中文 docstring 完整

## 实施工件可信度

Implementation artifact 声明:
- "24 tests passed" → **已验证**: 实际运行 24 passed
- "pyright 0 errors" → **已验证**: 实际运行 0 errors
- "terminology grep non-empty" → **已验证**: 剩余匹配均为已记录的允许项

Worker 声称可信。

## 综合结论

**Slice 1 实现可接受，无 blocking finding。** 核心架构变更（attempt-scoped key、async port、in-flight owner/waiter 状态机、typed policy messages、durable-missing 治理）均已正确实现且测试通过。

4 个 medium findings 中，M1 和 M2 是 plan sequencing gap 导致的已知 residual，正确解决路径在 Slice 2。M3（awaiting + finally）是窄边界条件，建议在 Slice 2 前评估是否需处理。M4 是 fallback 路径的防御性设计缺陷。

3 个 low findings 为测试覆盖补齐建议。

**Blocking findings: 0**

---

## Review Metadata

- Reviewer: DS (deepreview specialist)
- Date: 2026-06-01
- Target branch: `fix/wu-tool-01-attempt-scoped-duplicate-governance`
- Artifact path: `docs/reviews/wu-tool-01-code-review-slice1-ds-20260601.md`
