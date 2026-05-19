# Gateflow Plan Review: Host-owned LLM context compactor public opener contract

**Reviewer**: AgentMiMo (gateflow)
**Date**: 2026-05-19
**Plan artifact**: `docs/host/host-owned-compactor-plan.md`
**Design source of truth**: `docs/host/design.md` §865, §869, §2595-2616
**Review scope**: gateflow plan review — code-generation readiness, architecture boundaries, residual old semantics, transaction boundaries, tests/validation, sequencing

## 0. 审查依据

- 设计真源：`docs/host/design.md` §2 分层边界、§861-869 compaction ownership 决策、§2595-2616 retry/repair/transaction 边界
- 代码事实：`dayu/host/dispatch.py:979-1063`（proactive compact 在 write transaction 内）、`dayu/host/engine_ingest.py:513-515, 979-984`（reactive compact 在 write transaction 内）、`dayu/host/context_policy.py:42`（ContextBudgetPolicy 当前无 `max_compaction_attempts_per_operation` 字段）
- 初审：`docs/reviews/host-owned-compactor-plan-review-mimo.md`（3 blocking findings，已全部 RESOLVED）
- DS 审：`docs/reviews/host-owned-compactor-plan-review-ds.md`（无 blocking findings）
- 复审：`docs/reviews/host-owned-compactor-plan-rereview-mimo.md`（PASS，所有 blocking findings 确认收口）

## 1. Gateflow 审查结论

**PASS-WITH-RISKS**

Plan 整体 code-generation-ready，架构边界正确，无 blocking finding。存在一个需要 implementation agent 注意的 plan 内部表述矛盾和两个 residual risks。

## 2. Motivation & Severity 审查

### 2.1 动机是否成立

**成立**。直接 repo/design 证据充分：

| 证据来源 | 内容 |
|----------|------|
| `design.md:865` | "Service / `open_host(options)` 只能提供 compactor runner / storage 配置...不能提供 `ContextCompactor` 实例、compact prompt、policy ref、candidate builder、quality check、artifact writer 或 repair callback" |
| `design.md:869` | "普通 Service 不得为了完成多轮闭环而直接装配或调用...`ContextCompactor.compact(...)`" |
| `dayu/host/api.py:1039` | `compactor_baseline: CompactorExecutionBaseline | None` 包含 `context_compactor: ContextCompactor | None` |
| `dayu/host/__init__.py:154` | `CompactorExecutionBaseline` 在包根 `__all__` 导出 |
| `utils/smoke_host_public_multiturn.py` | `DeepSeekContextCompactor(ContextCompactor)` 自行拼 prompt、调用 LLM、构造 candidate |
| `tests/host/test_public_compact_smoke.py` | `_RealLLMContextCompactor(ContextCompactor)` 同上 |

Plan 正确识别了 `CompactorExecutionBaseline.context_compactor` → `OpenHostOptions.compactor_baseline` → `open_host._local_execution_options_from_open_host_options()` 的完整泄漏链。

### 2.2 严重性是否正确评估

**正确**。Plan 评为"中高"，理由充分：不立即破坏 EventLog truth（dispatch/ingest 仍由 Host 做 quality check、artifact 写入和 canonical event append），但破坏 public contract 长期边界——Service 可通过自定义 `ContextCompactor` 决定 prompt、candidate mapping 和 failure 语义，实质进入 Host governance 语义。与 `design.md:865` 的冻结目标直接矛盾。

## 3. Code-Generation-Readiness 审查

### 3.1 文件清单

Plan 6 个 Slice 列出的文件清单完整且具体：

| Slice | 文件 | 评价 |
|-------|------|------|
| 1 | `dayu/host/api.py`, `dayu/host/__init__.py`, `tests/host/test_public_open_host_options.py`, `tests/host/test_package_exports.py` | 完整 |
| 2 | 新增 `dayu/host/llm_compaction.py`, 新增 `tests/host/test_llm_compaction.py` | 完整 |
| 3 | `dayu/host/open_host.py`, `dayu/host/context_policy.py`, `tests/host/test_open_host_runtime.py`, `tests/host/test_context_policy.py` | 完整 |
| 4 | `dayu/host/dispatch.py`, `dayu/host/engine_ingest.py` + focused tests | 完整 |
| 5 | `utils/smoke_host_public_multiturn.py`, `tests/host/test_public_compact_smoke.py`, `tests/host/public_smoke_support.py` | 完整 |
| 6 | `README.md`, `dayu/host/README.md`, `tests/README.md` | 完整 |

### 3.2 Public contract 具体性

`CompactorRunnerBaseline` 的完整 dataclass 定义已给出（§3.1），字段类型明确。`OpenHostOptions` 的字段变更从 `compactor_baseline: CompactorExecutionBaseline | None` 到 `compactor_runner_baseline: CompactorRunnerBaseline | None` 明确无歧义。

### 3.3 `LLMContextCompactor` 构造签名具体性

§3.2 给出完整构造签名：

```python
class LLMContextCompactor(ContextCompactor):
    def __init__(
        self,
        *,
        runner_spec: RunnerSpec,
        runner_options: RunnerCallOptions,
    ) -> None: ...
```

内部固定策略枚举完整：prompt 为 Host private helper、`AgentPolicy` 固定为 `allow_tool_calls=False` + 小上限 `max_iterations`、`tool_schemas=()` + rejecting tool executor、`CancellationToken` 第一版不传入。

### 3.4 状态转换具体性

§3.6 的 compaction operation durable 语义状态机明确：

```
CONTEXT_COMPACTION_REQUESTED → attempt 1 LLM proposal → Host quality/budget gate
  → optional CONTEXT_COMPACTION_ATTEMPT_REJECTED → optional bounded repair attempt N
  → CONTEXT_COMPACTED or CONTEXT_COMPACTION_FAILED
```

stale result 策略（Slice 4 step 5）和 fail-closed 路径（Slice 4 step 4）均已明确。

### 3.5 测试具体性

§6.2 列出的测试函数名完整，覆盖五个关键维度：candidate mapping、dirty output fail closed、retry policy 透传、transaction 边界、stale result 防护。验证命令具体可执行。

### 3.6 Sequencing 具体性

6 个 Slice 的依赖关系清晰：Slice 1（API shape）→ Slice 2（Host-owned compactor）→ Slice 3（open_host 接线）→ Slice 4（transaction 边界拆分）→ Slice 5（smoke 迁移）→ Slice 6（README 同步）。Slice 1-3 必须作为同一 PR 内连续变更完成（Slice 3 step 7），消除了中间态合并风险。

## 4. Residual Old Semantics 检查

### 4.1 Service-facing ContextCompactor

**已移除**。`OpenHostOptions` 不再引用 `CompactorExecutionBaseline`，`dayu.host` 包根不再导出 `CompactorExecutionBaseline`。§3.5 明确 `ContextCompactor` 最多保留为 Host internal / low-level test seam。

### 4.2 Raw policy_ref

**已移除**。`CompactorRunnerBaseline` 不包含 `policy_ref` 字段。§3.3 明确"Service 不传 raw `policy_ref`"。Host 内部记录固定 policy id / version 作为 diagnostic metadata。

### 4.3 Service prompt/candidate/repair callback

**已移除**。§3.3 枚举了 Service 不能传的 7 类 governance 语义（prompt、candidate builder、preservation evidence builder、pinned state patch builder、quality check override、compact event payload、artifact writer）。§3.2 枚举了 Service 只能传的 5 类配置（RunnerSpec、RunnerCallOptions、artifact root、artifact create-parent-dir、ContextBudgetPolicy）。

### 4.4 Smoke-only compactor injection

**已移除**。Slice 5 删除 `DeepSeekContextCompactor` 和 `_RealLLMContextCompactor`，改为通过 `CompactorRunnerBaseline` 传 runner config，由 Host 内部构造 `LLMContextCompactor`。

## 5. Architecture Boundary 审查

### 5.1 UI -> Service -> Host -> Engine 分层

**遵守**。Plan 的目标架构：Service 只提供 runner/config（配置层），Host 内部构造 compactor 并管理 governance（治理层），LLM 调用复用 Engine runner API（执行层）。`LLMContextCompactor` 放在 `dayu/host/llm_compaction.py`，不放入 `dayu.runtime`（§3.2 明确说明理由）。

### 5.2 `dayu.runtime` 不得接收 Host governance 语义

**遵守**。Plan §3.2 明确"不得放入 `dayu.runtime`，因为它需要理解 Host `CompactionRequest` / `CompactionCandidate`、Host prompt/scene、candidate mapping 和 quality-check 预期，属于 Host Context Governance 内部能力，不是层中立 runtime primitive"。

### 5.3 Engine retry vs Host semantic repair ownership

**无歧义**。§3.6 三层分离明确：

| 层级 | 职责 | 范围 |
|------|------|------|
| Engine Runner | transport/provider retry | 网络错误、timeout、5xx、rate limit；按 `RunnerSpec.max_retries` 在一次 proposal call 内处理 |
| `LLMContextCompactor` | 单次 proposal executor | 把 immutable request + Host prompt 映射为一次 LLM proposal；不决定 retry/repair |
| Host Context Governance | semantic repair | 非 final answer、空 summary、解析失败、candidate reject、quality reject；按 `max_compaction_attempts_per_operation` bounded attempts |

## 6. Transaction Boundary 审查

### 6.1 代码事实确认

当前 proactive 和 reactive compact 的 LLM 调用都在 write transaction 内：

- `dispatch.py:831`: `self._transaction_runner.run_write(_operation)` → `_operation` 内调用 `_compact_before_dispatch`（line 802）→ `compactor.compact(request)`（line 1063）在 write transaction 内
- `engine_ingest.py:513`: `self._transaction_runner.run_write(_operation)` → `_operation` 内调用 `_ingest_validated`（line 511）→ `_start_reactive_context_recovery`（line 704）→ compact 在 write transaction 内

### 6.2 Plan 的三段拆分方案

Plan Slice 4 要求拆分为：

1. **Transaction 内**：冻结 input snapshot / durable request，append `CONTEXT_COMPACTION_REQUESTED`，提交
2. **Transaction 外**：运行 `compactor.compact(request)` + Host semantic repair attempts
3. **新 Transaction 内**：recheck run/attempt/session state + cursor，写 `CONTEXT_COMPACTED` 或 `CONTEXT_COMPACTION_FAILED`

方案与 `design.md:2606-2612` 的 durable 语义完全对齐。

### 6.3 Stale result 防护

Plan Slice 4 step 5 明确："LLM 返回后若 run/attempt/session 已被取消、关闭、替换或 cursor 不匹配，不写 `CONTEXT_COMPACTED`；只写必要 diagnostic / failed event"。这是 transaction 拆分后的必要防护，Plan 已覆盖。

### 6.4 Reactive path 方法签名影响

Slice 4 step 3 要求 reactive compact 同样三段拆分，但未具体说明 `EngineEventIngestor` 方法签名如何变化。当前 `_start_reactive_context_recovery` 在 write transaction 内返回 `_ReactiveRecoveryAccepted`，由调用方 `_complete_reactive_recovery_after_compact` 继续。拆分后，compact 需要在 transaction 外执行，`EngineEventIngestor` 需要返回一个 pending 标识让调用方在 transaction 外执行 LLM call 再回来写结果。Plan 没有写出这个交互细节，但 Slice 4 step 8 的测试要求会在实现时自然暴露。

**残留风险**：低。Plan 的约束（"LLM call 不在 write transaction 内"）和测试（`test_reactive_compaction_calls_llm_outside_write_transaction`）足以引导实现者找到正确的拆分方式。

## 7. Plan 内部表述矛盾

### 7.1 [INFO] Slice 4 step 1 与 Slice 4 整体要求的矛盾

**证据**：Slice 4 step 1 写"保持 `HostDispatchScheduler` 和 `EngineEventIngestor` 只从 internal `context_compactor` 取 compactor；compactor 来源由 Slice 3 的 Host-owned 注入链提供"，这暗示核心调用路径不变。但 Slice 4 step 2-3 要求 proactive 和 reactive compact 拆成三段，这需要改变 `_compact_before_dispatch` 和 `_start_reactive_context_recovery` / `_complete_reactive_recovery_after_compact` 的方法结构和调用方式。Plan 的 §7 handoff step 4 也确认"审计并调整 dispatch / engine ingest compact 执行阶段"。

**影响**：如果 implementation agent 只读 step 1 可能误判为"不需要改 dispatch/ingest 方法结构"，但 step 2-3 的三段拆分要求会纠正这个理解。

**建议**：Implementation agent 应以 Slice 4 step 2-3 的三段拆分要求为准，step 1 的"compactor 来源不变"仅指 `context_compactor` 实例注入链不变，不指方法内的执行流程不变。此矛盾不阻塞 plan 批准，但在实现 review 时应确认拆分已正确实施。

## 8. EventLog / HostEvent 语义审查

### 8.1 EventLog 留痕

Plan §3.6 和 §4 Slice 4 step 7 明确了 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 的 payload 内容：operation id、attempt number、failure category、repairable、runner attempt summary refs、quality / parse / budget diagnostic refs、next policy decision。不记录 API key、headers、完整 prompt 或完整 provider payload。

与 `design.md:2606-2614` 的 durable 语义完全对齐。

### 8.2 HostEvent 暴露粒度

Plan §3.6 和 Slice 4 step 8 的分层策略与 `design.md:2616` 一致：

| 事件类型 | Service-facing HostEvent | 说明 |
|----------|--------------------------|------|
| `CONTEXT_COMPACTION_REQUESTED` | Yes | 触发信号 |
| `CONTEXT_COMPACTED` | Yes | 成功终态 |
| `CONTEXT_COMPACTION_FAILED` | Yes | 失败终态 |
| `CONTEXT_COMPACTION_ATTEMPT_REJECTED` | 可选 typed diagnostic/progress | 修复尝试失败 |
| Engine runner 内部 HTTP retry | No | 只进 log / aggregated diagnostic |

## 9. Slice Size 与 Implementation-Readiness

### 9.1 Slice 大小

6 个 Slice 的粒度合理，每个 Slice 聚焦单一职责：

1. API shape 切换（纯类型变更）
2. Host-owned compactor 内部类（新增模块）
3. open_host 接线（构造 + 注入）
4. Transaction 边界拆分（治理流程重构）
5. Smoke 迁移（测试适配）
6. README 同步（文档）

### 9.2 不强制未来 Slice 工作

Plan 多处明确"不在本计划范围"：

- 多套 scene-specific compaction policy（§3.3）
- 主动取消 compactor call（§3.2）
- 完整 Recovery（`design.md:855` 已冻结）
- Outbox read / drain API（`design.md:903` 已冻结）

这些边界清晰，不会让 implementation agent 误入 future-scope。

## 10. Tests/Validation 与 README 更新

### 10.1 测试矩阵

| 维度 | 测试函数 | 覆盖 |
|------|---------|------|
| candidate mapping | `test_llm_context_compactor_maps_final_answer_to_candidate` | Slice 2 |
| dirty output fail closed | `test_llm_context_compactor_rejects_empty_or_non_final_output` | Slice 2 |
| ref/evidence ownership | `test_llm_context_compactor_preserves_host_owned_refs_and_evidence` | Slice 2 |
| retry vs repair 边界 | `test_llm_context_compactor_uses_runner_retry_policy_without_owning_semantic_repair` | Slice 2 |
| transaction 边界 (proactive) | `test_proactive_compaction_calls_llm_outside_write_transaction` | Slice 4 |
| transaction 边界 (reactive) | `test_reactive_compaction_calls_llm_outside_write_transaction` | Slice 4 |
| stale result 防护 | `test_compaction_stale_result_does_not_write_compacted_event` | Slice 4 |
| repair attempt 记录 | `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` | Slice 4 |
| runner retry 不 emit HostEvent | `test_runner_provider_retry_does_not_emit_host_event` | Slice 4 |
| budget policy 验证 | `test_context_budget_policy_validates_max_compaction_attempts_per_operation` | Slice 3 |

与 `CLAUDE.md` 测试约束对齐：不引入网络 pytest、优先验证通过、pyright 0 errors。

### 10.2 README 更新

Plan Slice 6 覆盖三个 README 的变更点，与 `CLAUDE.md` README 触发规则一致：

- `README.md`：manual smoke 描述更新
- `dayu/host/README.md`：opener public contract 和 compaction 章节更新
- `tests/README.md`：如涉及 public compact smoke 分层描述

## 11. Residual Risks

### R-1 [LOW] Reactive compact 三段拆分的 `EngineEventIngestor` 方法签名变化

Plan 没有写出 `EngineEventIngestor` 的 reactive compact 方法如何返回 compact pending 标识。当前 `_start_reactive_context_recovery` 在 write transaction 内返回 `_ReactiveRecoveryAccepted`，拆分后需要让调用方在 transaction 外执行 LLM call。Plan 的测试要求（`test_reactive_compaction_calls_llm_outside_write_transaction`）会在实现时自然暴露这个交互点。

**应对**：Implementation agent 在 Slice 4 实现时应先设计 `EngineEventIngestor` 的 compact-pending 返回协议，再实现三段拆分。

### R-2 [LOW] `CONTEXT_COMPACTION_REQUESTED` 与 `CONTEXT_COMPACTED` 跨 transaction 的可追溯链

拆分后两条 event 不在同一个 transaction 内。实现时需确保 `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` 的 payload 能正确引用 `CONTEXT_COMPACTION_REQUESTED` 的 `event_id` / `operation_id`，形成可追溯链。

**应对**：`CONTEXT_COMPACTION_REQUESTED` 的 `event_id` 应作为 compaction operation 的 durable anchor，后续 event 通过 `operation_id` 引用。

### R-3 [INFO] Slice 1-3 合并为同一 PR 的 review 复杂度

三个 Slice 涉及 `api.py`、`__init__.py`、`open_host.py`、`context_policy.py` 和多个测试文件，合并 PR 的 review 复杂度较高。Plan 要求同一 PR 内完成（Slice 3 step 7），这是正确的架构决策，但 review 时需要关注变更的一致性。

## 12. 总结

**PASS-WITH-RISKS。**

Plan 无 blocking finding。动机成立、严重性正确评估、code-generation-ready、无 residual old semantics、架构边界遵守、Engine retry vs Host semantic repair 无歧义、EventLog/HostEvent 语义明确、transaction 边界方案正确、slice 粒度合理、测试/README 覆盖完整。

一个 plan 内部表述矛盾（Slice 4 step 1 vs step 2-3）不阻塞批准，implementation agent 应以 step 2-3 的三段拆分要求为准。

三个 residual risks 均为 LOW/INFO 级别，不影响 plan 有效性，implementation agent 在 Slice 4 实现时应重点关注 R-1。
