# Phase 10 Plan Re-review — AgentMiMo

- Reviewer: AgentMiMo
- Date: 2026-05-18
- Artifact reviewed: `docs/host/phase10-context-governance-plan.md` (post-fix)
- Prior review: `docs/reviews/phase10-plan-review-mimo-20260518.md`
- Fix artifact: `docs/reviews/phase10-plan-fix-codex-20260518.md`
- Related: `docs/reviews/phase10-plan-review-ds-20260518.md`

---

## Verdict

**PASS**

---

## Summary

上轮 3 条 blocking findings（B1/B2/B3）均已修复，修复内容具体且可执行。9 条 high/medium/low findings 全部标记为 fixed，修复内容合理。Codex fix 未引入新的 blocking 或 high plan defect。

Plan 现在可以交给 implementation agent 按 slice 顺序执行。

---

## Fixed Findings Table

| Finding | Severity | Status | Fix Quality |
|---------|----------|--------|-------------|
| B1 `cancel_run` 不识别 `ACCEPTED` | blocking | **FIXED** | Plan §Pre-start Governance Gate 第 186 行明确 `cancel_run` 处理 `ACCEPTED`：追加 `RUN_CANCELLED`，不创建 Attempt / dispatch record。Slice 4 tests 第 417 行有对应断言。 |
| B2 `promote_queued_run_in_transaction` 绕过 governance | blocking | **FIXED** | Plan 第 190-191 行明确 queued in-place governance 方案：同一 governance gate 接收 `origin=accepted \| queued`，旧 `promote_queued_run_in_transaction` 不再由 production 直接调用，替换为 `start_queued_run_with_starting_attempt_after_governance_in_transaction`。 |
| B3 `CONTEXT_COMPACTED` projection 解析不具体 | blocking | **FIXED** | Plan 第 317-321 行新增 `_compact_episode_summary_from_projection_event` 和 `_apply_pinned_state_patch_candidate` helper 描述，含三态 patch 语义、`confirmed_subjects` ref 校验、伪代码流程（第 333-339 行）。 |
| H1 per-Run trigger count 查询未说明 | high | **FIXED** | Plan 第 104-106 行明确 transaction-scoped EventLog count helper、同事务查询、fail-closed 行为。 |
| H2 新旧 start helper 关系不清楚 | high | **FIXED** | Plan 第 187 行明确新 helper 接受已存在的 `RUN_ACCEPTED` event，只追加 `RUN_STARTED` + `ATTEMPT_STARTED`；第 189 行明确旧 `create_running_run_with_starting_attempt_in_transaction` 不再由 production start path 调用。 |
| M1 estimator 常量未指定 | medium | **FIXED** | Plan 第 93-99 行列出 7 个命名常量示例，含名称和默认值。 |
| M2 production wiring 不细 | medium | **FIXED** | Plan 第 499-506 行明确 `HostCommandHandleOptions` / `HostLocalExecutionOptions` 字段名和类型；第 509-513 行明确 Service composition root 传参路径。 |
| M3 `CONTEXT_COMPACTED` 状态表述模糊 | medium | **FIXED** | Plan 第 344 行改为"event payload 本身不编码 Run/Attempt 状态变更；状态变更由同一事务中的 `RUN_STARTED` / `ATTEMPT_STARTED` 完成"。 |
| M4 schema CHECK 兼容性 | medium | **FIXED** | Plan 第 179 行明确 fresh schema 起库约定，与 CLAUDE.md 一致。 |
| L1 fake compactor import boundary | low | **FIXED** | Plan 第 516 行明确 fake compactor 模块 docstring 要求和显式注入约束。 |
| L2 usage payload 扩展范围 | low | **FIXED** | Plan 第 236 行明确"P10 不扩展 `USAGE_REPORTED` EventLog payload"。 |
| L3 tests README 更新类别 | low | **FIXED** | Plan 第 520 行列出 4 个新增测试类别。 |
| L4 fake compactor placement | low | **FIXED** | 同 L1，第 516 行。 |

---

## DS Review Findings Cross-check

DS review 的 3 条 high findings 同时被 Codex fix 处理：

| DS Finding | Status |
|-----------|--------|
| H1 pre-start wakeup 未指定 | **FIXED** — Plan 第 196-201 行新增 `PreStartGovernanceWakeupPort`、`HostPreStartGovernanceScheduler`、governance loop 扫描顺序。 |
| H2 `ACCEPTED` 与 `ATTACH_ACTIVE` | **FIXED** — Plan 第 182 行明确 `ATTACH_ACTIVE` conflict with `ACCEPTED`（no Attempt to attach）。 |
| H3 queued promotion 状态机 | **FIXED** — Plan 第 190 行明确 queued in-place governance，不做 `QUEUED -> ACCEPTED` 中间态。 |

---

## New Findings

### No blocking or high findings.

以下为 fix 后残留的 medium/low/info 级观察，不阻断 implementation：

### M1. `StartGovernanceCandidate` typed contract 未显式定义

**Severity: medium**

Plan 第 190 行提到 governance gate 接收 `StartGovernanceCandidate` with `origin=accepted | queued`，但未像 `CompactionRequest`、`BudgetEstimateInput` 等一样给出 typed dataclass 字段列表。

**Evidence:** `docs/host/phase10-context-governance-plan.md:190`

**Impact:** Implementation agent 需要自行决定 `StartGovernanceCandidate` 的字段。不同 agent 可能做出不一致选择（例如是否携带 session_id、run_id、FIFO 排序键）。

**Recommendation:** 不阻断，但建议 implementation agent 在 Slice 4 第一个 commit 中先定义该 dataclass，字段至少包含 `run_id`、`session_id`、`origin: Literal["accepted", "queued"]`。

---

### L1. Pre-start governance wakeup 的异常路径语义可进一步明确

**Severity: low**

Plan 第 202 行说"Phase 11 owns startup recovery scan"，但未明确 P10 implementation 中 governance loop 遍历 `ACCEPTED` Run 时如果发现 Run 已被并发 cancel（status 变为 terminal），应该如何处理。

**Evidence:** `docs/host/phase10-context-governance-plan.md:196-202`

**Impact:** 低。governance loop 读到 terminal status 的 Run 应跳过，这属于常规 defensive check，implementation agent 可以自行处理。

---

### L2. `CONTEXT_COMPACTED` payload 中 `confirmed_subjects` ref 校验的 helper 选择未指定

**Severity: low**

Plan 第 321 行提到 `confirmed_subjects` patch values "must parse through existing opaque ref JSON helpers or a new private helper using `OpaqueMemoryRef` / `HostNeutralRefKind` validation"。"or" 留给了 implementation agent 决策空间。

**Evidence:** `docs/host/phase10-context-governance-plan.md:321`

**Impact:** 低。两种方式都可行，implementation agent 可根据现有 helper 的适用性选择。

---

## Residual Risks

1. **`RunStatus.ACCEPTED` 仍是 public state-machine/schema 变更。** implementation 需要同步 admission、cancel、read-model / public contract 测试。Plan 已识别。

2. **Pre-start governance wakeup 是新增执行环节。** P10 只覆盖同进程 wakeup，进程重启后的 orphan/startup scan 归 Phase 11。Plan 已明确。

3. **Queued in-place governance 要求同一 write transaction 严格 FIFO 和 single-start arbitration。** 实现复杂度可能被低估，但 plan 已给出事务边界约束。

4. **Conservative estimator 可能偏早触发 compact。** 这是有意的 fail-safe 设计。Provider-specific tokenizer adapter 继续 deferred。

5. **Real LLM compactor 未就绪。** Fake compactor 可验证 Host governance，但 production 需要显式注入 compactor port。Plan 已识别。

---

## Appendix: Evidence Index

| File | Lines | Relevance |
|------|-------|-----------|
| `docs/host/phase10-context-governance-plan.md` | 186 | B1 fix: cancel_run for ACCEPTED |
| `docs/host/phase10-context-governance-plan.md` | 190-191 | B2 fix: queued in-place governance |
| `docs/host/phase10-context-governance-plan.md` | 317-321, 333-339 | B3 fix: compact projection helpers + pseudo-flow |
| `docs/host/phase10-context-governance-plan.md` | 104-106 | H1 fix: transaction-scoped count helper |
| `docs/host/phase10-context-governance-plan.md` | 187-189 | H2 fix: new vs old start helper relationship |
| `docs/host/phase10-context-governance-plan.md` | 93-99 | M1 fix: estimator constants |
| `docs/host/phase10-context-governance-plan.md` | 499-513 | M2 fix: production wiring fields |
| `docs/host/phase10-context-governance-plan.md` | 344 | M3 fix: CONTEXT_COMPACTED state wording |
| `docs/host/phase10-context-governance-plan.md` | 179 | M4 fix: fresh schema convention |
| `docs/host/phase10-context-governance-plan.md` | 196-201 | DS H1 fix: governance wakeup port/scheduler |
| `docs/host/phase10-context-governance-plan.md` | 180-184 | DS H2 fix: ACCEPTED + ATTACH_ACTIVE / REJECT / QUEUE |
| `dayu/host/admission.py` | 1044-1048 | Code evidence: cancel_run raises INVALID_STATE for unknown status |
| `dayu/host/durable/run_transition.py` | 679-739 | Code evidence: old combined start helper |
| `dayu/host/memory.py` | 1049-1051 | Code evidence: only EPISODE_SUMMARY_ACCEPTED consumed |
