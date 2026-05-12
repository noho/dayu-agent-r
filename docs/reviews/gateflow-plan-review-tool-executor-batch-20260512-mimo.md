# Gateflow Plan Review: ToolExecutor Batch Handshake

- **Review Gate**: plan review (evidence-based adversarial)
- **Reviewed Target**: `docs/reviews/gateflow-plan-tool-executor-batch-20260512.md`
- **Reviewer**: mimo
- **Date**: 2026-05-12

## Reviewer Conclusion

计划整体质量较高：动机真实且严重性正确，架构边界和依赖方向遵守项目硬约束，公共契约设计合理，命名决策有依据，Non-Goals 收敛，错误/race 语义完备。直接证据与当前代码一致。

但发现 **1 个中等严重度 blocker**（Slice 1 过粗）和 **5 个低严重度 finding**。无严重级别发现。Controller 已对全部 finding 作出裁决并完成 plan-fix 修订；这不表示代码实现已完成。

## Findings

### F01-计划已修订-中-Slice 1 过粗，28 步 / 18+ 文件作为一个 vertical slice 风险过高

- **Plan位置**: §9 Slice 1: Vertical Batch Contract and Agent Migration
- **问题类型**: 切片过粗
- **计划当前写法**: Slice 1 包含 28 个实施步骤，覆盖 `dayu/contracts/`（4 文件）、`dayu/engine/contracts/`（4 文件，含 1 新增）、`dayu/engine/agent.py`（1 文件）、`tests/`（7 文件）、包根导出（2 文件），共计 18+ 文件。计划声称"每个 slice 都是 pyright-green review checkpoint"，但整个 slice 作为单一交付单元。
- **为什么有问题**: 28 步 / 18+ 文件的变更量超出单次 handoff 的可控范围。implementation agent 在如此大的 slice 中：
  1. 难以在出错时定位是哪一步引入了问题。
  2. review agent 难以在合理时间内完成有意义的 code review。
  3. 若中途 pyright 失败，回退成本高。
  4. 步骤间存在隐式依赖（如步骤 1-4 改 contracts，步骤 7-10 改 events，步骤 12 改 agent.py），但未显式标注依赖关系。
- **直接证据**: Slice 1 steps 列表包含 28 个编号步骤；文件列表包含 `dayu/contracts/tool_call.py`、`dayu/contracts/tool_outcome.py`、`dayu/contracts/tool_executor.py`、`dayu/contracts/tool_declaration.py`、`dayu/contracts/__init__.py`、`dayu/engine/contracts/tool_records.py`（新增）、`dayu/engine/contracts/engine_events.py`、`dayu/engine/contracts/agent_run.py`、`dayu/engine/contracts/__init__.py`、`dayu/engine/__init__.py`、`dayu/engine/agent.py`、以及 7 个测试文件。
- **影响**: 实现 agent 可能在单个 slice 中产出难以 review 的大变更；若中间步骤出错，调试和回退成本高。
- **建议改法和验证点**: 将 Slice 1 拆为至少 2 个子切片：
  - **Slice 1a: Contract Layer Migration**（`dayu/contracts/` 全部 + `dayu/engine/contracts/tool_records.py` + 包根导出 + 对应 package export tests）。完成后 pyright-green，但 Engine agent.py 可以临时 import 新旧两套类型（通过内部兼容 shim，不是公共 re-export）。
  - **Slice 1b: Engine Event & Agent Migration**（`dayu/engine/contracts/engine_events.py` + `agent_run.py` + `agent.py` + 全部 Engine 测试迁移）。完成后移除临时 shim。
  - 或者，如果坚持单 slice，至少在 steps 中显式标注依赖批次（如 steps 1-5 必须先于 steps 6-10），并增加中间 pyright 检查点。
  - 验证点：拆分后每个子 slice 都能独立 pyright-green。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **Controller decision**: `accepted`
- **Plan-fix status**: 已修订计划 §9，说明不为拆分引入 public/internal compatibility shim，保留 vertical checkpoint 并增加 dependency batches、中间 pyright/pytest checks 与 stop conditions；未标记实现完成。

---

### F02-计划已修订-低-计划未覆盖 Host 侧迁移路径

- **Plan位置**: §4 Non-Goals、§8 Affected Files / Modules、§12 Risks
- **问题类型**: 契约缺失
- **计划当前写法**: 计划修改了 `ToolExecutor` 协议签名（从单工具到 batch），但 §4 Non-Goals 写"不实现外部长事务恢复、轮询、后台 job 生命周期治理或 orphan cleanup"，§8 未列出任何 Host 侧文件，§12 仅将 orphan cleanup 标记为 residual risk。
- **为什么有问题**: `ToolExecutor` 是 Host / ToolRuntime 实现的协议。签名从 `execute(ToolExecutionRequest) -> ToolExecutionOutcome` 变为 `execute(BatchToolExecutionRequest) -> BatchToolExecutionOutcome`，所有现有 Host 侧 `ToolExecutor` 实现都会立即 break。计划虽然在 §5.7 声明这是 intentional break，但未提供：
  1. Host 侧需要修改的文件清单。
  2. Host 侧 batch executor 的最小实现指引（至少应说明：batch 内串行调用旧单工具 callable 是可接受的最小迁移路径）。
  3. Host 侧测试迁移范围。
- **直接证据**: §8 Affected Files 列表中无任何 `dayu/host/` 或 `dayu/service/` 文件。当前 `ToolExecutor` 协议（`dayu/contracts/tool_executor.py:25`）的 `execute` 签名是 Host / ToolRuntime 必须实现的接口。
- **影响**: implementation agent 完成 Engine 侧迁移后，Host 侧代码会 pyright 失败，但计划未覆盖这些文件，导致实现不完整。
- **建议改法和验证点**: 在计划中增加一个 section 或在 §12 中明确：
  1. 列出 Host 侧所有实现 `ToolExecutor` 的文件。
  2. 说明 Host 侧最小迁移策略（如 batch 内串行调用旧 callable）。
  3. 说明 Host 侧测试是否在本 work unit 范围内，还是作为 follow-up。
  4. 验证点：`rg "ToolExecutor|execute.*ToolExecutionRequest" dayu/host/ dayu/service/` 找到所有受影响文件。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Controller decision**: `partially-accepted`
- **Plan-fix status**: 已修订计划 §8 Host / Service Discovery、§9 Validation、§10 与 §13，要求运行 `rg "ToolExecutor|execute.*ToolExecutionRequest" dayu/host dayu/service` 并记录结果；当前代码库缺少 `dayu/host` 与 `dayu/service` 时不扩展 Host 实现，只更新 `docs/host/tracking.md`；未标记实现完成。

---

### F03-计划已修订-低-Slice 1 未明确要求新增 batch 语义的基本行为测试

- **Plan位置**: §9 Slice 1 Steps、Slice 1 Expected Assertions
- **问题类型**: 测试缺口
- **计划当前写法**: Slice 1 step 28 说"Migrate all existing tests and fake executors touched by the removed old request/context exports so the repository is pyright-green at the end of this slice"。Expected Assertions 只检查结构（如"Batch executor receives exactly one request"、"Old exports are absent"），不要求行为正确性。
- **为什么有问题**: Slice 1 只要求"迁移现有测试使其 pyright-green"，但不要求新增 batch 语义的行为测试。这意味着 Slice 1 完成后，代码可能结构正确但行为未验证（如 batch 内多工具是否都被执行、batch outcome records 是否正确对应）。Slice 2 的"Batch Semantics and Edge-Case Hardening"名称暗示 Slice 1 只覆盖 happy path，但 Slice 1 的 Expected Assertions 中没有 happy path 行为断言。
- **直接证据**: Slice 1 Steps 列表中无"add batch happy-path behavioral tests"步骤。Slice 1 Expected Assertions 全部是结构断言，无行为断言。Slice 2 steps 1 说"Add strict mismatch tests and implementation fixes if Slice 1 only covered the happy path"，隐含 Slice 1 应覆盖 happy path。
- **影响**: Slice 1 完成后可能有 pyright-green 但行为不正确的代码，将所有行为验证推迟到 Slice 2。
- **建议改法和验证点**: 在 Slice 1 Expected Assertions 中增加至少以下行为断言：
  1. Multi-tool batch causes exactly one `ToolExecutor.execute` call with all tools in `request.calls`。
  2. Each tool in batch produces a `tool_result_accepted` event。
  3. No-awaiting batch produces `tool_calls_batch_done` with correct counts。
  - 验证点：Slice 1 测试命令通过且包含上述断言。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Controller decision**: `accepted`
- **Plan-fix status**: 已修订计划 §9 Slice 1 Step 28 与 Expected assertions，要求首个 green implementation slice 覆盖一次 executor call、每个工具产生 accepted/awaiting record、no-awaiting batch done counts；未标记实现完成。

---

### F04-计划已修订-低-§5.6 声称 tool_records.py 防止 agent_run.py 与 engine_events.py 互相 import，但当前两者并不互相 import

- **Plan位置**: §5.6 Assistant Batch Snapshot and Engine Suspension Records
- **问题类型**: 其它（动机描述不精确）
- **计划当前写法**: "为避免 `agent_run.py` 与 `engine_events.py` 互相 import，新增 `dayu/engine/contracts/tool_records.py`"。
- **为什么有问题**: 当前 `agent_run.py` 和 `engine_events.py` 并不互相 import。`agent_run.py` 导入 `dayu.contracts.tool_await`、`dayu.contracts.tool_executor`、`dayu.contracts.tool_schema`、`dayu.engine.contracts.agent_policy` 等；`engine_events.py` 导入 `dayu.engine.contracts.agent_run`（仅 `ContextBudgetSnapshot` 和 `RunResumeHint`）、`dayu.contracts.tool_await`、`dayu.contracts.tool_outcome`。两者之间只有 `engine_events.py -> agent_run.py` 的单向 import。新增 `tool_records.py` 的真正动机是将 `AssistantToolCallBatchSnapshot`、`AcceptedToolExecutionRecord`、`AwaitingToolExecutionRecord` 放在一个独立模块中，避免这些新类型加剧 `engine_events.py` 和 `agent_run.py` 之间的耦合——这是合理的，但原始描述不精确。
- **直接证据**: `engine_events.py:19` 导入 `from dayu.engine.contracts.agent_run import ContextBudgetSnapshot, RunResumeHint`；`agent_run.py` 不 import `engine_events.py`。
- **影响**: 不影响实现正确性，但会让 implementation agent 对动机产生误判。
- **建议改法和验证点**: 将描述改为"为将 batch snapshot 与 record 类型独立于 event data 和 run outcome，新增 `dayu/engine/contracts/tool_records.py`，避免新增类型加剧 `engine_events.py` 对 `agent_run.py` 的已有单向依赖"。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Controller decision**: `accepted`
- **Plan-fix status**: 已修订计划 §5.6，将动机改为降低耦合并让 shared snapshot/record types 独立于 event data/run outcome modules；未标记实现完成。

---

### F05-计划已修订-低-Non-Goals 未明确排除 Engine 侧 batch 内并发/审批/限流

- **Plan位置**: §4 Non-Goals
- **问题类型**: 范围漂移
- **计划当前写法**: §4 第 5 条"Engine 不在内部并发执行工具；并发、串行、限流、审批、awaiting、tool-level cancellation 均由 Host / ToolRuntime / batch executor 决定"。
- **为什么有问题**: 这条 non-goal 写在正文中，但措辞较长且与其它 non-goal 混合。对于 handoff agent，这条约束至关重要——它决定了 Engine 侧 `_execute_tool_batch_handshake` 的实现方式（只能调用一次 `tool_executor.execute`，不能自行拆分 batch）。建议将其提升为独立的架构约束条目，或在 §6 状态转换中显式重申。
- **直接证据**: §6.1 步骤 4 写"Agent 构造一个 `BatchToolExecutionRequest`，调用一次 `ToolExecutor.execute(...)`"，与 non-goal 一致，但 §6 和 §4 之间没有显式交叉引用。
- **影响**: 低。实现 agent 若仔细阅读 §6.1 应该不会误解，但显式约束更安全。
- **建议改法和验证点**: 在 §6.1 开头增加一句："Engine 对 batch 内部执行策略无感知：只调用一次 `ToolExecutor.execute`，不拆分、不并发、不审批、不限流。"或在 §4 中将该条 non-goal 加粗。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/低/严重）**: 低
- **Controller decision**: `accepted`
- **Plan-fix status**: 已修订计划 §4 Non-Goals 与 §6.1，将 Engine 只调用一次 `ToolExecutor.execute`、不拆分/并发/审批/限流提升为硬架构约束；未标记实现完成。

---

### F06-计划已修订-低-§5.7 公共破坏面列表遗漏 ToolCallsBatchDoneData 新增 cancelled_count

- **Plan位置**: §5.7 Explicit Public Contract Breaks
- **问题类型**: 契约缺失
- **计划当前写法**: §5.7 列出了 6 个公共破坏面，但未提及 `ToolCallsBatchDoneData` 新增 `cancelled_count` 字段。
- **为什么有问题**: §5.6 第 9 步明确说"Add `cancelled_count` to `ToolCallsBatchDoneData`"。这是一个公共事件 data 结构的变更，虽然不是破坏性删除，但属于公共契约变更，应在 §5.7 中列出以便 downstream 调用方知晓。
- **直接证据**: §5.6 steps 9 写"Add `cancelled_count` to `ToolCallsBatchDoneData`"；§5.7 列表中无此条目；当前 `ToolCallsBatchDoneData`（`engine_events.py:197-209`）只有 `completed_count` 和 `failed_count`。
- **影响**: 低。downstream 调用方如果使用 `dataclass` 构造 `ToolCallsBatchDoneData`，新增字段会导致 positional arg 错误；但如果使用 keyword args 或只读取字段，则无影响。
- **建议改法和验证点**: 在 §5.7 列表中增加一条："`ToolCallsBatchDoneData` 新增 `cancelled_count: int` 字段；调用方构造该 dataclass 时需补充该参数。"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Controller decision**: `accepted`
- **Plan-fix status**: 已修订计划 §5.7 与 §13，明确 `ToolCallsBatchDoneData.cancelled_count` 是 public contract change 并纳入 completion report；未标记实现完成。

---

## Open Questions and Residual Risk

| # | 问题 | 状态 | 说明 |
|---|------|------|------|
| 1 | Host 侧哪些文件实现 `ToolExecutor`？ | plan-fix 已覆盖验证 | 计划 §8 / §9 要求运行 `rg "ToolExecutor|execute.*ToolExecutionRequest" dayu/host dayu/service` 并记录结果；当前 plan-fix 证据为目录不存在 |
| 2 | Host 侧最小迁移策略是什么？ | partially-accepted | 当前无 Host implementation 时不迁移 Host 代码；若实现时发现 pyright 必需代码，只做最小迁移，不扩展 Host 设计 |
| 3 | Slice 1 是否需要拆分？ | accepted | 作为 plan-risk 处理；不为拆分引入兼容 shim，计划 §9 改为 bounded vertical checkpoint + dependency batches + stop conditions |
| 4 | `ToolCancelledOutcome` 的 `reason` 字段是否有约定的值域？ | residual risk | plan 说"中性原因码"但未给出具体枚举或示例；不阻塞本 plan-fix |

Residual risks（继承自 plan §12）：
- Host / ToolRuntime orphan cleanup 仍为 Host 侧 responsibility。
- Downstream app code 旧导入破坏是 intentional break。
- Batch executor 内部并行导致 record 顺序不确定——Engine 按 input order 处理，已缓解。

## Controller Decision Status

| Finding | Controller decision | Plan-fix status |
|---------|---------------------|-----------------|
| F01 - Slice 1 过粗 | `accepted` | 作为 plan-risk 处理；计划 §9 已增加 bounded vertical checkpoint、dependency batches、中间 checks 与 stop conditions |
| F02 - Host 侧迁移路径未覆盖 | `partially-accepted` | 计划 §8、§9、§10、§13 已要求运行 Host / Service discovery；无 Host 代码时只做 tracking |
| F03 - Slice 1 缺少 batch 行为测试 | `accepted` | 计划 §9 Step 28 与 Expected assertions 已补充基本行为测试 |
| F04 - tool_records.py 动机描述不精确 | `accepted` | 计划 §5.6 已重写动机 |
| F05 - Non-Goals 未明确排除 Engine batch 并发 | `accepted` | 计划 §4 与 §6.1 已提升为硬架构约束 |
| F06 - §5.7 遗漏 cancelled_count | `accepted` | 计划 §5.7 与 §13 已补充公共契约变化 |

以上均为 plan-fix 状态，不代表生产代码或测试实现已完成。

## Summary

- **Finding 总数**: 6
- **最高严重程度**: 中（F01）
- **Blocker**: F01 已由 plan-fix 通过 bounded vertical checkpoint、dependency batches、中间检查点和 stop conditions 处理；不代表实现完成。
- **结论**: 计划整体设计质量高，架构边界正确，契约设计合理。Controller 裁决后的 plan-fix 已覆盖 F01-F06，后续仍需 re-review 确认。
