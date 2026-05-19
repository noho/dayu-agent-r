# Adversarial Plan Review: Host-owned LLM context compactor

**Reviewer**: AgentMiMo
**Date**: 2026-05-19
**Plan artifact**: `docs/host/host-owned-compactor-plan.md`
**Review scope**: adversarial plan review, no production code change, no commit, no push

## 0. 审查依据

- 设计真源：`docs/host/design.md` §2 分层边界、§861-869 compaction ownership 决策
- 总控真源：`docs/host/implementation-control.md`（P10.5 checklist）
- 阶段目标：`docs/host/post-p10.md` G13、S4 compact smoke 要求
- 代码事实：`dayu/host/api.py`、`dayu/host/open_host.py`、`dayu/host/dispatch.py`、`dayu/host/__init__.py`
- 测试事实：`tests/host/test_public_compact_smoke.py`、`utils/smoke_host_public_multiturn.py`

## 1. Blocking Findings

### B-1 [HIGH] Plan 遗漏了 `ContextCompactor` 从 `CompactorExecutionBaseline` 拆除后，`open_host.py` 如何构造 Host-owned compactor 的具体映射步骤

**证据**：Plan Slice 3 写到"在 `_local_execution_options_from_open_host_options(...)` 中读取 `options.compactor_runner_baseline`"并构造 `LLMContextCompactor`，但没有说明：

1. `LLMContextCompactor` 需要哪些构造参数。`RunnerSpec`、`RunnerCallOptions`、policy ref 是 plan 列出的，但 `LLMContextCompactor` 内部调用 `run_agent_and_wait(AgentRunRequest(...))` 时，还需要构造 `SystemMessage`、`UserMessage`、`AgentPolicy`、`CancellationToken`。Plan 没有定义这些参数的来源——是从 `CompactorRunnerBaseline` 显式传入，还是由 `LLMContextCompactor` 内部硬编码？

2. `LLMContextCompactor` 的 prompt ownership 边界。Plan §3.3 说"第一版应采用 Host 通用、财报语义中立的 prompt"，但没有给出这个 prompt 的内容约束。当前 manual smoke 和 public smoke 的 compactor prompt 分别是 40 字摘要和 30 字摘要——约束不同。Plan 应明确 Host-owned compactor 的 prompt 是固定写死、还是由 `CompactorRunnerBaseline` 的某字段控制。

3. `LLMContextCompactor` 的 `CancellationToken` 来源。`dispatch.py` proactive compact 在 `HostDispatchScheduler` 内部发起，此时有 `AttemptDispatchSnapshot.cancellation_token`。但 reactive compact 在 `EngineEventIngestor` 内部发起，token 来源不同。Plan 没有说明 `LLMContextCompactor` 如何获取取消 token。

**Why blocking**：缺少这些映射细节，Slice 2/3 的实现会回到"实现者自行决定"，可能再次引入 prompt 外放或 candidate builder 外放。

**建议**：Plan Slice 2 必须明确 `LLMContextCompactor.__init__` 的完整签名，以及 prompt/AgentPolicy/CancellationToken 的固定策略。

### B-2 [HIGH] Plan 未覆盖 reactive compact 路径的 `LLMContextCompactor` 注入方式

**证据**：`dispatch.py` proactive compact 直接从 `self._local_execution.context_compactor` 取 compactor。但 `engine_ingest.py` reactive compact 路径也接收 `context_compactor`，其来源是 `EngineEventIngestor.__init__` 的构造参数。Plan Slice 4 说"原则上不需要改 `dispatch.py` 和 `engine_ingest.py` 的核心逻辑"，但 `open_host.py` 当前通过 `_local_execution_options_from_open_host_options` 把 `context_compactor` 注入到 `HostLocalExecutionOptions`，而 `HostDispatchScheduler.open()` 再把它传给 `EngineEventIngestor`。

问题在于：Plan 说"CompactorExecutionBaseline 降级，保留在 `dayu.host.api` 仅供低层测试 / internal composition"，但 `open_host.py` 的 `_local_execution_options_from_open_host_options` 当前直接读取 `options.compactor_baseline.context_compactor`。Plan 要把 `OpenHostOptions.compactor_baseline` 改成 `compactor_runner_baseline`（不含 `context_compactor`），那 `_local_execution_options_from_open_host_options` 必须从 `CompactorRunnerBaseline` 构造 `LLMContextCompactor`，再注入到 `HostLocalExecutionOptions.context_compactor`。

Plan 没有明确写出这条注入链：`CompactorRunnerBaseline` → `LLMContextCompactor` → `HostLocalExecutionOptions.context_compactor` → `HostDispatchScheduler` / `EngineEventIngestor`。

**Why blocking**：如果注入链不清晰，reactive compact 路径可能在 Slice 3 之后断掉，而 Slice 4 的"不需要改核心逻辑"假设不成立。

**建议**：Plan Slice 3 必须明确写出 `LLMContextCompactor` 实例注入到 `HostLocalExecutionOptions.context_compactor` 的完整路径，并确认 `HostDispatchScheduler.open()` 和 `EngineEventIngestor` 的 `context_compactor` 参数来源不变。

### B-3 [MEDIUM] Plan 未覆盖 `CompactorExecutionBaseline` 降级后 `tests/host/test_public_compact_smoke.py` 的 `_candidate_from_summary` 去向

**证据**：`test_public_compact_smoke.py` 的 `_RealLLMContextCompactor` 内部包含 `_candidate_from_summary`、`_preservation_evidence`、`_range_for_request`、`_summarized_ranges`、`_confirmed_fact_summaries` 等 helper。这些 helper 与 `utils/smoke_host_public_multiturn.py` 的同名 helper 几乎完全相同——是典型的复制粘贴。

Plan Slice 5 说"删除 `DeepSeekContextCompactor` / `_RealLLMContextCompactor` 类及其 rejecting executor / thread wrapper / candidate mapper 重复逻辑"，但没有说明：

1. `LLMContextCompactor`（Host-owned）内部的 candidate mapping 逻辑从哪里来？是从 smoke 中抽取，还是重新实现？
2. Smoke 测试删除 `_RealLLMContextCompactor` 后，如何验证 compact 路径？Plan 说"构造 `OpenHostOptions` 时传 `compactor_runner_baseline=CompactorRunnerBaseline(...)`"，这意味着 `LLMContextCompactor` 由 `open_host` 内部构造，Smoke 不能再直接观测 `compactor.call_count` / `compactor.last_summary`。Plan 的断言策略（"compact artifact root 下存在 artifact"）是否足够？

**Why blocking**：如果 candidate mapping 逻辑从 smoke 删除但没有在 Host 内部找到安放位置，会丢失 coverage。如果 Smoke 断言只检查 artifact 文件存在，可能无法区分"compactor 真的跑了"和"artifact 是旧的"。

**建议**：Plan Slice 2 必须明确 `LLMContextCompactor` 内部的 candidate mapping 是从 smoke 抽取还是全新实现。Slice 5 的断言策略需要补充"artifact 文件的创建时间在本次 smoke 运行窗口内"或等价时效性检查。

## 2. 非 Blocking 但需收口的 Finding

### F-1 [LOW] Plan 命名建议 `CompactorRunnerBaseline` 与设计真源的术语不完全对齐

**证据**：设计真源 `design.md:865` 使用的术语是"compactor execution baseline"，而 Plan 建议改名为 `CompactorRunnerBaseline`。这不 blocking，但命名变更需要同步到 design.md 的相关表述，否则设计真源和代码会出现术语分裂。

**建议**：实现时确认命名，如果选 `CompactorRunnerBaseline`，需要更新 design.md 中对应的引用。

### F-2 [LOW] Plan 的验证矩阵没有列出 `tests/host/test_llm_compaction.py` 的具体测试用例

**证据**：Plan Slice 2 提到"新增单元测试覆盖：LLM final answer summary 映射为 candidate；非 final answer / 空 summary fail fast；candidate 保留 current input、tool facts、verified facts 与 evidence refs；不暴露 tool schemas，不允许 tool call"。但验证矩阵 §6.2 只列了 `pytest tests/host/test_llm_compaction.py -q`，没有列出具体测试函数名或断言点。

**建议**：验证矩阵应补充 `test_llm_compaction.py` 的具体测试用例清单。

### F-3 [INFO] Plan §5.2 "不做事项"完整且与设计真源一致

Plan 明确列出了 12 项"不做"，与 `design.md` 的 compaction ownership 决策完全对齐。没有发现遗漏。

## 3. Governance 语义泄漏检查

### 3.1 Service 是否会通过 Plan 接触到 Host governance 语义？

**结论**：不会。Plan 的目标是把 `ContextCompactor` 从 `OpenHostOptions` / `CompactorExecutionBaseline` 中移除，Service 只传 `CompactorRunnerBaseline`（runner spec/options/policy/artifact root）。`LLMContextCompactor` 的构造、prompt、candidate mapping、quality check 全部在 Host 内部完成。`dispatch.py` / `engine_ingest.py` 的 governance 路径不变。

**残留风险**：`CompactorRunnerBaseline` 仍然暴露 `compactor_runner_spec` 和 `compactor_runner_options`，这意味着 Service 可以通过选择不同的 runner spec 来间接影响 compactor 行为。这是合理的——Service 控制"用哪个模型做压缩"，但不控制"如何压缩"。

### 3.2 Plan 是否保留低层测试 seam 而不污染 public opener？

**结论**：是。Plan §3.5 明确保留 `ContextCompactor` 作为 `dayu.host.compaction` 内部 typed boundary 和 `HostLocalExecutionOptions.context_compactor` 的 low-level test seam。`FakeContextCompactor` 等测试替身仍可通过 `HostLocalExecutionOptions` 注入。Plan 明确说"不再出现在普通 Service-facing package root / `OpenHostOptions` public contract 中"。

**残留风险**：无。

## 4. Prompt / Candidate / Quality Check / Artifact / EventLog / Memory 边界检查

| 维度 | Plan 覆盖 | 评价 |
|------|-----------|------|
| Prompt ownership | §3.3 | 已覆盖。"compactor prompt/scene 归 Host-owned compactor 内部管理"。但缺少 prompt 内容约束，见 B-1。 |
| Candidate structure | §3.4 | 已覆盖。明确列出 `current_user_input_ref`、`preserved_input_event_refs`、`preservation_evidence`、`budget_after_compact` 的构造规则。 |
| Quality check | §3.4 | 已覆盖。"Host 现有 `check_compaction_candidate(...)` ... 不变"。 |
| Artifact boundary | §2.1, §3.1 | 已覆盖。`compact_artifact_root` 从 `CompactorRunnerBaseline` 传入。 |
| EventLog boundary | §4 Slice 4 | 已覆盖。"保持 quality check、artifact store、`CONTEXT_COMPACTED`、memory projection catch-up 现有路径"。 |
| Memory projection | §4 Slice 4 | 已覆盖。"保持 ... memory projection catch-up 现有路径"。 |

## 5. 迁移步骤 / 测试矩阵 / README 同步检查

### 5.1 迁移步骤

Plan 的 6 个 Slice 顺序合理：先改 API shape → 增 Host-owned compactor → open_host 内部构造 → 确认 governance 路径 → smoke 迁移 → README 同步。依赖关系清晰。

**残留风险**：Slice 1 到 Slice 3 之间存在"半完成态"——`CompactorExecutionBaseline` 降级但 `LLMContextCompactor` 尚未就位时，`open_host` 无法构造 compactor。Plan 应明确这个中间态是否允许（例如：Slice 1 完成后，compact 能力暂时丧失，直到 Slice 3 完成）。

### 5.2 测试矩阵

Plan §6 列出了完整的验证命令，覆盖 pyright、focused unit tests、manual smoke、全量 regression 和 README 同步检查。

**残留风险**：缺少 `tests/host/test_llm_compaction.py` 的具体用例清单（见 F-2）。

### 5.3 README 同步

Plan §4 Slice 6 列出了 README 同步的具体步骤，与 CLAUDE.md 的 README 触发规则一致。

## 6. 总结

**Blocking findings**: 3 (B-1 HIGH, B-2 HIGH, B-3 MEDIUM)

B-1 和 B-2 是 Plan 的实现细节缺失，会导致实现者在 Slice 2/3 自行决定 prompt/注入链，可能重新引入 governance 泄漏。B-3 是 smoke 迁移的断言策略不足。

如果这三个 blocking finding 被收口，Plan 的其余部分完整、架构边界清晰、与设计真源一致。

**Residual risks**（收口 blocking 后仍存在）：
1. `LLMContextCompactor` 第一版 prompt 内容过简可能导致 compact 摘要质量不稳定——但 Plan 已明确"业务摘要质量不作为 P10.5 评测目标"。
2. Slice 1 到 Slice 3 的中间态可能导致 compact smoke 暂时失败——需要在实现时控制 slice 节奏。
3. 真实 provider 行为不稳定——Plan 已要求 env-gated skip。
