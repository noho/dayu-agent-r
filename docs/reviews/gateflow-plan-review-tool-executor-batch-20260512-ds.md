# Gateflow Plan Review Artifact

## Review Gate

**Gate name**: plan-review
**Reviewed target**: `docs/reviews/gateflow-plan-tool-executor-batch-20260512.md`（ToolExecutor Batch Handshake Plan）
**Reviewer conclusion**: 通过，无阻塞性问题。发现 6 个 finding，最高严重度为中，均为可修复项；计划整体 handoff-ready，动机成立，架构边界正确，契约和状态机清晰。Controller 已对全部 finding 作出裁决并完成 plan-fix 修订；这不表示代码实现已完成。

## Open Questions and Residual Risk

1. **残存风险：大 batch 超时预算不足**。batch 内工具数量 × 单工具耗时可能超过 `tool_execution_timeout_seconds` 单值预算。计划已将并发策略交给 Host/ToolRuntime，但若 Host 串行执行且工具数量大，Engine timeout 会命中。当前计划通过 `WaitTimedOut → run_failed(tool_execution_timeout)` 收口，正确但可能需要 Host 侧的 batch-level timeout 协商机制——属于后续 work unit，不在本计划 scope。
2. **残存风险：外部调用方破坏**。计划明确声明所有旧 `ToolResultAcceptedData` 平铺字段、`ToolAwaitingData` 平铺字段、`RunSuspendedData` 单 awaiting 字段、`EngineRunOutcomeSuspended` 单 awaiting 字段、旧 `ToolExecutionRequest` / `ToolExecutionContext` 导出全部移除。这些调用方的迁移需要独立 work unit。
3. **残存风险：orphan cleanup 跟踪**。计划将 orphan cleanup 标记为 Host/ToolRuntime 职责；plan-fix 已在计划 §8 / §9 / §13 要求无 Host implementation 时更新 `docs/host/tracking.md`，但具体 tracking 文案仍需 implementation docs slice 落地。

---

## Findings

### 01-计划已修订-中-Slice 1 过粗，18+ 文件单 slice 编译迁移风险高

- **Plan 位置**: §9 Implementation Slices，Slice 1: Vertical Batch Contract and Agent Migration
- **问题类型**: 切片过粗
- **计划当前写法**:
  > "由于旧 single request/context 不保留兼容 wrapper，公共契约、tool declaration helper、Engine event/outcome shape 与 `dayu/engine/agent.py` 的最小编译迁移必须放在同一个 vertical slice 内完成。"
  > Slice 1 包含 18+ 个文件、28 个步骤，要求 pyright-green checkpoint。

- **为什么有问题**:
  计划将新旧类型迁移作为单一 vertical slice 是正确的架构选择（不保留兼容 wrapper 则不能分批暴露新旧签名），但 18+ 文件 + 28 步骤的 slice 对实现 Agent 来说认知负荷很高：
  - `dayu/contracts/tool_call.py` 改 context/request，同时 `dayu/contracts/tool_outcome.py` 新增 outcome 成员，同时 `dayu/contracts/tool_executor.py` 改协议签名，同时 `dayu/contracts/tool_declaration.py` 改 callable 类型——任何一个环节失误会导致 pyright 全链路报错。
  - `dayu/engine/agent.py` 的 `_execute_tool_batch`、`_execute_one_tool`、`_call_tool_executor`、`_make_suspended_terminal_with_close`、`_inject_tool_messages`、`_project_tool_outcome_for_llm`、`_all_records_failed` 等全部联动变更，内部类型 `_ToolOutcomeRecord` 也需要同步迁移。
  - 测试迁移同时进行，fake executor 签名、断言 shape 全部改变。

- **直接证据**:
  - `dayu/contracts/tool_call.py:74-119`：当前 `ToolExecutionContext` 含 8 字段（含 `tool_call_id` / `index_in_iteration`），`ToolExecutionRequest` 包装单个 `call`。
  - `dayu/contracts/tool_executor.py:25`：当前协议签名为 `async def execute(self, request: ToolExecutionRequest) -> ToolExecutionOutcome`。
  - `dayu/contracts/tool_declaration.py:29-31`：当前 `ToolFunctionCallable = Callable[[ToolExecutionRequest], Awaitable[ToolExecutionOutcome]]`。
  - `dayu/engine/agent.py:361-365`：`_ToolOutcomeRecord` 当前字段是 `call: ToolCallRequest` + `outcome: ToolCompletedOutcome | ToolFailedOutcome`。
  - `dayu/engine/agent.py:1397-1414`：当前逐 call 构造 `ToolExecutionRequest` / `ToolExecutionContext`。
  - `dayu/engine/agent.py:1516-1548`：`_execute_one_tool` 接收 `ToolExecutionRequest`，内调 `await_or_cancel_or_timeout`。
  - `dayu/engine/agent.py:1810-1833`：`_make_suspended_terminal_with_close` 接收单个 `ToolAwaitingOutcome`。
  - 所有 18 个文件都直接 import 或暴露 `ToolExecutionRequest` / `ToolExecutionContext`。

- **影响**:
  实现 Agent 需要在一个 commit 中同时修改所有 18+ 文件，编译边界很长；中间状态不会有 pyright 通过，调试窗口大。若遇到未预见的类型冲突，回退成本高。

- **建议改法和验证点**:
  保持当前 slice 划分不变（架构约束下确实无法拆分），但在 Slice 1 的 "Stop condition" 中增加一条：若 pyright 报错超过 20 个（排除测试文件），必须回到 Controller。同时在 Slice 1 的 Steps 中建议实现顺序：
  1. 先新增所有新类型（不删除旧类型）→ 验证 pyright 通过
  2. 替换 `agent.py` 内部逻辑 → 验证 pyright 通过
  3. 最后一次性删除旧类型并更新导出 → 验证 pyright 通过
  这种"先增后删"策略可缩短单次编译失败的窗口。

- **修复风险（低）**: 仅增加 stop condition 和实现顺序建议，不改变 slice 结构。
- **严重程度（中）**:
- **Controller decision**: `accepted`
- **Plan-fix status**: 已修订计划 §9，在保留 vertical checkpoint 的前提下增加 dependency batches、中间 pyright/pytest checks 与 stop conditions；未标记实现完成。

---

### 02-计划已修订-中-`_ToolOutcomeRecord` 内部类型迁移未在计划中显式描述

- **Plan 位置**: §4 Evidence、§9 Slice 1 Steps
- **问题类型**: 不可直接实施
- **计划当前写法**:
  > §4: "tests/engine/test_agent_phase3_tool_call.py 的 fake executor、timeout、awaiting、duplicate、late cancellation 等测试均围绕单工具 request 断言"
  > §9 Slice 1 Step 26: "Update `_project_tool_outcome_for_llm`, `_tool_outcome_name`, count helpers, `_all_records_failed`, `_inject_tool_messages`."

- **为什么有问题**:
  `_ToolOutcomeRecord` 是 `_execute_tool_batch` 的核心内部类型：
  - `dayu/engine/agent.py:361-365`：当前定义为 `call: ToolCallRequest` + `outcome: ToolCompletedOutcome | ToolFailedOutcome`。
  - 该类型被 `_count_completed_tool_records` (`agent.py:385`)、`_count_failed_tool_records` (`agent.py:399`)、`_inject_tool_messages` (`agent.py:1585`)、`_all_records_failed` (`agent.py:2018`) 消费。
  - 计划引入 `ToolCancelledOutcome` 后，`_ToolOutcomeRecord.outcome` 不再是 `ToolCompletedOutcome | ToolFailedOutcome`，而是 `ToolCompletedOutcome | ToolFailedOutcome | ToolCancelledOutcome`。
  - 新增的 `BatchToolExecutionRecord`（公共类型）与 `_ToolOutcomeRecord`（内部类型）概念相似但结构不同——`BatchToolExecutionRecord` 只有 `tool_call_id: str` + `outcome: ToolExecutionOutcome`，而 `_ToolOutcomeRecord` 携带完整 `call: ToolCallRequest`。

- **直接证据**:
  - `dayu/engine/agent.py:361-365`：`_ToolOutcomeRecord` 的 `outcome` 类型为 `ToolCompletedOutcome | ToolFailedOutcome`。
  - `dayu/engine/agent.py:1468`：构造 `_ToolOutcomeRecord(call=call, outcome=completed_outcome)`，其中 `completed_outcome` 来自 `outcome.value`（已排除 awaiting）。
  - 计划 §5.3 新增 `ToolCancelledOutcome`，`ToolExecutionOutcome` 扩展到四成员。但在 Engine 内部，如果 executor 返回 cancelled，它应该被当作 accepted fact 处理（类似 completed/failed），因此 `_ToolOutcomeRecord` 需要扩展。

- **影响**:
  实现 Agent 时如果不更新 `_ToolOutcomeRecord` 的类型定义，pyright 会在所有消费点报类型不匹配；如果错误地将 `ToolCancelledOutcome` 当作失败处理，`_all_records_failed` 和 `_count_failed_tool_records` 的语义会错误。

- **建议改法和验证点**:
  在 Slice 1 Step 26 之前增加一个显式步骤："更新 `_ToolOutcomeRecord.outcome` 字段类型为 `ToolCompletedOutcome | ToolFailedOutcome | ToolCancelledOutcome`；更新 `_count_failed_tool_records` 排除 `ToolCancelledOutcome`；更新 `_all_records_failed` 仅在所有 outcome 都为 `ToolFailedOutcome` 时返回 True。" 同时考虑将 `_ToolOutcomeRecord` 重命名为 `_AcceptedOutcomeRecord` 或直接复用 `BatchToolExecutionRecord`（但 `BatchToolExecutionRecord` 缺少 `call` 字段）。
  验证：在 `_all_records_failed` 的单测中覆盖全部 cancelled、全部 failed、mixed failed+cancelled 三种情况。

- **修复风险（低）**: 仅补充计划步骤描述，不改变接口设计。
- **严重程度（中）**:
- **Controller decision**: `accepted`
- **Plan-fix status**: 已修订计划 §5.9 与 §9 Slice 1 Step 26，明确 accepted record union、count helpers、`_all_records_failed`、projection/injection 语义和 all-cancelled / all-failed / mixed failed+cancelled 测试；未标记实现完成。

---

### 03-计划已修订-低-`correlation_id` 语义从 per-tool 变为 per-batch 未列入显式破坏清单

- **Plan 位置**: §5.2 与 §7 Error and Race Semantics, §5.7 Explicit Public Contract Breaks
- **问题类型**: 契约缺失
- **计划当前写法**:
  > §5.2: `correlation_id = f"{run_id}:{iteration_id}:tool_batch"`
  > §5.7: 列出 6 项显式破坏，不含 correlation_id 语义变化。

- **为什么有问题**:
  当前 `_execute_tool_batch` 在 `agent.py:1409-1411` 为每个 call 生成唯一 correlation_id：
  ```python
  correlation_id=self._correlation_id(
      iteration_id=decision.iteration_id,
      tool_call_id=call.tool_call_id,
  )
  ```
  计划改为 batch-level 单一 `correlation_id = f"{run_id}:{iteration_id}:tool_batch"`。这意味着跨 Host observer / ToolRuntime 的中性关联标识不再能区分同一 batch 内的不同工具调用。虽然 correlation_id 的 docstring 明确为"中性，不得用作 trace recorder 私有入口"，但任何在 ToolRuntime 侧消费该字段的 observer（如日志关联、metrics 打点）会观察到语义变化。

- **直接证据**:
  - `dayu/contracts/tool_call.py:15-16`：docstring 声明 "correlation_id 仅用于跨 Host observer / ToolRuntime 的中性关联，不是 ToolTraceRecorder 私有入口"。
  - `dayu/engine/agent.py:1397-1414`：当前为每个 call 生成独立 correlation_id。
  - 计划 §5.2：新 batch context 的 correlation_id 为 `f"{run_id}:{iteration_id}:tool_batch"`，不再包含 `tool_call_id`。

- **影响**:
  任何消费旧 per-call correlation_id 的 observer 需要调整为 batch-level 关联。影响范围未知，应在 public break summary 中显式提示。

- **建议改法和验证点**:
  在 §5.7 显式破坏清单中增加一项："correlation_id 从 per-call 变为 per-batch：`BatchToolExecutionContext.correlation_id` 不包含 `tool_call_id`；需要 per-call 关联的 observer 改用 `BatchToolExecutionRecord.tool_call_id` 自行拼接。" 同时在 §13 Completion Report Format 的 public contract break summary 中纳入。
  验证：`rg "correlation_id"` 检查仓库内消费方。

- **修复风险（低）**: 仅补充文档说明。
- **严重程度（低）**:
- **Controller decision**: `accepted`
- **Plan-fix status**: 已修订计划 §5.2、§5.7、§9 Validation、§10 与 §13，明确 per-batch 破坏面、grep 验证和 completion report 要求；未标记实现完成。

---

### 04-计划已修订-低-`dayu/engine/__init__.py` 新增 `tool_records` 导出未在步骤中显式列出

- **Plan 位置**: §8 Affected Files / Modules 与 §9 Slice 1 Steps
- **问题类型**: 不可直接实施
- **计划当前写法**:
  > §8: `dayu/engine/__init__.py` 列入 Affected Files。
  > §9 Slice 1 Step 11: "Export new batch and record types from package roots; remove old single request/context exports from public export lists and export whitelist tests."

- **为什么有问题**:
  `dayu/engine/__init__.py` 是 Engine 调用方的单一稳定 API surface（`dayu/engine/__init__.py:1-8` 明确说明其"双源 re-export"职责）。计划新增 `dayu/engine/contracts/tool_records.py` 定义了三个公共类型：
  - `AssistantToolCallBatchSnapshot`
  - `AcceptedToolExecutionRecord`
  - `AwaitingToolExecutionRecord`

  这些类型需要经过两条路径暴露：
  1. `dayu/engine/contracts/__init__.py`：从 `tool_records` import 并加入 `__all__`。
  2. `dayu/engine/__init__.py`：从 `dayu.engine.contracts` re-export 并加入 `__all__`。

  Slice 1 Step 11 说"从 package roots 导出新类型"但没有显式列出哪些新类型需要加入 `dayu/engine/__init__.py` 的 `__all__`。同时 `ToolCancelledOutcome`、`BatchToolExecutionOutcome`、`BatchToolExecutionRequest` 等从 `dayu.contracts` 起源的新类型也需要出现在 `dayu/engine/__init__.py` 的 re-export 列表中。

- **直接证据**:
  - `dayu/engine/__init__.py:41-111`：当前从 `dayu.engine.contracts` re-export 46 个符号，从 `dayu.contracts` re-export 18 个符号。
  - `dayu/engine/contracts/__init__.py:52-164`：当前 `__all__` 不含任何 `tool_records` 类型（文件尚不存在）。
  - 计划新增 `dayu/engine/contracts/tool_records.py` 作为新文件，内含三个公共 dataclass。

- **影响**:
  实现时容易遗漏某个导出点，导致 public API surface 不一致或 pyright 报缺失导出；`test_package_exports.py` 会捕获遗漏但会增加迭代次数。

- **建议改法和验证点**:
  在 Slice 1 Steps 中显式增加：
  - Step 11a: 在 `dayu/engine/contracts/__init__.py` 中 import `AssistantToolCallBatchSnapshot`、`AcceptedToolExecutionRecord`、`AwaitingToolExecutionRecord` 并加入 `__all__`。
  - Step 11b: 在 `dayu/engine/__init__.py` 中 re-export 上述三个类型，并 re-export 新的 `BatchToolExecutionContext`、`BatchToolExecutionRequest`、`BatchToolExecutionRecord`、`BatchToolExecutionOutcome`、`ToolCancelledOutcome`（从 `dayu.contracts` 路径）。
  验证：`pytest tests/engine/test_package_exports.py tests/contracts/test_package_exports.py`。

- **修复风险（低）**: 仅补充步骤描述。
- **严重程度（低）**:
- **Controller decision**: `accepted`
- **Plan-fix status**: 已修订计划 §5.8 与 §9 Slice 1 Step 11，显式列出 `dayu/engine/contracts/__init__.py`、`dayu/engine/__init__.py`、`dayu/contracts/__init__.py` 新增/移除符号；未标记实现完成。

---

### 05-计划已修订-低-混合 awaiting batch 的 assistant message 重建未指定 Engine 是否提供公共 helper

- **Plan 位置**: §5.6 Assistant Batch Snapshot and Engine Suspension Records
- **问题类型**: 契约缺失
- **计划当前写法**:
  > "调用方可以仅凭 `EngineRunOutcomeSuspended.accepted_records` / `awaiting_records` 中任一 record 的 `batch_snapshot` 重建 assistant tool-call roundtrip message；再用每个 record 的 `call` 和 `outcome` / `await_spec` 重建同一批次的 accepted 与 awaiting facts。"

- **为什么有问题**:
  计划描述了恢复能力的存在性，但没有明确：
  - Engine 是否提供公共 helper 函数（如 `reconstruct_assistant_message_from_snapshot(...)`）供调用方使用？
  - 还是调用方必须手动从 `batch_snapshot.assistant_content`、`batch_snapshot.assistant_reasoning_content`、`batch_snapshot.tool_calls` 构造 `AssistantMessage`？
  - 如果是后者，"assistant tool-call roundtrip message" 的具体构造方式（如何从 `ToolCallRequest` 构造 `AssistantToolCall`、如何设置 `provider_state` 回写）在 Engine messages 契约中有定义，但调用方是否需要知道这些细节？

- **直接证据**:
  - `dayu/engine/contracts/messages.py` 中 `AssistantMessage` 和 `AssistantToolCall` 定义（未直接阅读，但通过 import 可知）。
  - 计划 §5.6: `AssistantToolCallBatchSnapshot` 包含 `assistant_content`、`assistant_reasoning_content`、`tool_calls` 三个字段。
  - 计划 §9 Slice 2 Step 3: 仅要求测试"reconstructs the assistant tool-call message from record.batch_snapshot"，但测试实现方式依赖于是否提供公共 helper。

- **影响**:
  如果 Engine 不提供公共 helper，每个调用方都需要实现相同的重建逻辑，导致跨 Host/Service 的重复实现。如果提供 helper，helper 属于 Engine 公共 API surface，需要在 `dayu/engine/__init__.py` 中导出。

- **建议改法和验证点**:
  在计划 §5.6 末尾增加决策："Engine 不提供公共重建 helper；调用方自行从 `batch_snapshot` 字段与 `record.call` 构造 `AssistantMessage` / `ToolMessage`。重建正确性由 Slice 2 的集成测试覆盖。" 或者反过来："Engine 提供 `reconstruct_tool_call_roundtrip(batch_snapshot, records) -> tuple[AgentMessage, ...]` 公共 helper，作为 Engine API 表面的一部分导出。"
  验证：无论哪种决策，Slice 2 Step 3 的测试需要对应调整。

- **修复风险（低）**: 仅需决策并更新文档。
- **严重程度（低）**:
- **Controller decision**: `accepted-with-clarification`
- **Plan-fix status**: 已修订计划 §5.6 与 Slice 3 docs steps，明确 Engine 不提供公共 reconstruction helper，只暴露 stable snapshot/record data shapes；测试只验证 shape 足够重建；未标记实现完成。

---

### 06-计划已修订-低-`docs/engine/design.md` 更新未提及引擎状态机图中的 `SUSPENDED` 节点语义变化

- **Plan 位置**: §11 Docs Decision 与 §9 Slice 3
- **问题类型**: 范围漂移
- **计划当前写法**:
  > §11: "Update: `dayu/engine/README.md` because `dayu/engine/` behavior and public Engine contract change. `docs/engine/design.md` because it currently documents the old single-tool handshake and single awaiting suspended fact."

- **为什么有问题**:
  `docs/engine/design.md` 当前在多个位置描述单工具手shake：
  - 第 234 行：`ToolExecutor.execute(ToolExecutionRequest)` 作为 Engine 工具调用边界的唯一引用。
  - 第 256 行：`ToolExecutor returned ToolAwaitingOutcome(await_spec, snapshot)`。
  - 第 333-337 行：Engine 状态机描述，`SUSPENDED` 状态来源是"ToolExecutor 返回 ToolAwaitingOutcome"。

  计划将 Engine 改为调用一次 batch execute，SUSPENDED 的来源变为"batch outcome 中包含至少一个 awaiting record"。计划在 §11 提到了设计文档更新但 Slice 3 Steps 缺少对状态机图/描述的显式修改项——特别是 `SUSPENDED` 现在可能同时包含 accepted records 和 awaiting records，这与当前"单个 awaiting 触发 `SUSPENDED`"的描述有本质差异。

- **直接证据**:
  - `docs/engine/design.md:333-337`：状态机描述。`SUSPENDED` 标注来源为"ToolExecutor 返回 ToolAwaitingOutcome"。
  - 计划 §6.2: "batch outcome 返回后，Agent 按原始 call 顺序先 emit completed / failed / cancelled 的 tool_result_accepted。再按原始 call 顺序 emit 每个 awaiting 的 tool_awaiting。" 这意味着 `SUSPENDED` 不再是"单个工具 awaiting"，而是"批次混合终态"。

- **影响**:
  文档更新不完整会导致后续开发者和调用方基于旧状态机理解消费 suspended outcome。

- **建议改法和验证点**:
  在 Slice 3 Steps 中增加一项："更新 `docs/engine/design.md` 中 Engine 状态机部分，将 `SUSPENDED` 的来源描述从'ToolExecutor 返回 ToolAwaitingOutcome'改为'batch outcome 包含 ≥1 个 awaiting record'；标注 suspended terminal 同时包含 accepted_records 和 awaiting_records；标注恢复调用方可从任一 record 的 batch_snapshot 重建 assistant 消息。"
  验证：Slate 3 doc sanity grep 中增加对 `docs/engine/design.md` 的检查。

- **修复风险（低）**: 仅补充文档步骤描述。
- **严重程度（低）**:
- **Controller decision**: `accepted`
- **Plan-fix status**: 已修订计划 §9 Slice 3 Steps 与 §11，要求更新 `docs/engine/design.md` 中 `SUSPENDED` 来源与 terminal records 语义；未标记实现完成。

---

## Controller Decision Status

| Finding | Controller decision | Plan-fix status |
|---------|---------------------|-----------------|
| 01 - Slice 1 过粗 | `accepted` | 作为 plan-risk 处理；计划 §9 已增加 dependency batches、中间 checks 与 stop conditions |
| 02 - `_ToolOutcomeRecord` 迁移 | `accepted` | 计划 §5.9 与 §9 Step 26 已补充内部 accepted record 语义与测试 |
| 03 - `correlation_id` per-batch | `accepted` | 计划 §5.2、§5.7、§9、§10、§13 已补充破坏面与验证 |
| 04 - package exports | `accepted` | 计划 §5.8 与 §9 Step 11 已列明新增/移除符号 |
| 05 - reconstruction helper | `accepted-with-clarification` | 计划 §5.6 已明确本 work unit 不提供公共 helper |
| 06 - `SUSPENDED` docs semantics | `accepted` | 计划 §9 Slice 3 与 §11 已补充 design doc 状态机更新 |

以上均为 plan-fix 状态，不代表生产代码或测试实现已完成。

## Artifact Path

`docs/reviews/gateflow-plan-review-tool-executor-batch-20260512-ds.md`

---

## Review Methodology

- 逐条对照 AGENTS.md 约束检查：架构分层、dayu.runtime 边界、禁止 Any/object、禁止兼容性代码、测试覆盖、README 触发规则、pyright 要求。
- 对计划中的每个断言在代码库中寻找直接证据（文件路径 + 行号）。
- 对每个 implementation slice 评估是否足够小、是否有序、是否包含必要的 stop condition。
- 验证所有 public contract break 是否已列出、error/race semantics 是否完整。
- 特别注意：`dayu/engine/contracts/tool_records.py` 为新增文件，不依赖上层，符合架构。
- 验证 `dayu.runtime` 未被计划修改，符合层中立约束。
