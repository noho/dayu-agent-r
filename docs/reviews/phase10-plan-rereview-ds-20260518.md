# Phase 10 Plan Re-Review — AgentDS

**Artifact**: `docs/reviews/phase10-plan-rereview-ds-20260518.md`
**Reviewer**: AgentDS
**Plan Under Re-Review**: `docs/host/phase10-context-governance-plan.md` (post-Codex fix)
**Prior Reviews**: `phase10-plan-review-mimo-20260518.md`, `phase10-plan-review-ds-20260518.md`
**Fix Artifact**: `phase10-plan-fix-codex-20260518.md`
**Date**: 2026-05-18
**Scope**: 只判断 MiMo B1/B2/B3 与 DS H1/H2/H3 是否被 Codex fix 修复；检查 fix 是否引入新 blocking/high plan defect。

---

## Verdict: PASS

Codex fix 已正确修复全部 3 条 MiMo blocking 和 3 条 DS high findings。未引入新的 blocking 或 high plan defect。发现 1 条 medium、2 条 low、2 条 info 新 finding，均不阻断 implementation 启动。

---

## Fixed Findings Table

| Finding | Reviewer | Severity | Status | Plan Fix Evidence |
|---|---|---|---|---|
| B1 `cancel_run` 不识别 `ACCEPTED` | MiMo | blocking | **FIXED** | plan:185-186 显式 ACCEPTED cancel path；Slice 4 tests:417 包含 cancel 断言 |
| B2 queued promotion 绕过 governance | MiMo | blocking | **FIXED** | plan:189-192 选择 in-place governance + `start_queued_run_with_starting_attempt_after_governance_in_transaction`；旧 helper 不再 production 调用 |
| B3 `CONTEXT_COMPACTED` projection 解析不具体 | MiMo | blocking | **FIXED** | plan:316-325 补全 `_compact_episode_summary_from_projection_event`、`_apply_pinned_state_patch_candidate`、三态语义与伪代码 |
| H1 pre-start wakeup 未指定 | DS | high | **FIXED** | plan:195-202 独立 `PreStartGovernanceWakeupPort` + `HostPreStartGovernanceScheduler`；governance loop 与 dispatch scheduler 分离 |
| H2 `ACCEPTED` 与 `ATTACH_ACTIVE` | DS | high | **FIXED** | plan:180-184 ATTACH_ACTIVE conflict；REJECT conflict；QUEUE / submit_followup 排队 |
| H3 queued promotion 状态机 | DS | high | **FIXED** | plan:189-191 不做 `QUEUED->ACCEPTED` 中间态；`StartGovernanceCandidate` 统一接受 `origin=accepted\|queued` |

### Also Fixed (non-blocking/non-high from prior reviews)

| Finding | Reviewer | Severity | Status |
|---|---|---|---|
| H1 per-Run trigger count 查询未说明 | MiMo | high | **FIXED** | plan:104-106 transaction-scoped EventLog count helper + fail-closed |
| H2 新旧 start helper 关系 | MiMo | high | **FIXED** | plan:187-189 新 helper 复用 RUN_ACCEPTED；旧 combined helper 不走 production start |
| M1 estimator 常量未指定 | MiMo | medium | **FIXED** | plan:93-98 6 个命名常量放在 `dayu/host/context_budget.py` |
| M2 production wiring 不细 | MiMo | medium | **FIXED** | plan:498-513 `HostCommandHandleOptions` / `HostLocalExecutionOptions` 字段 + Service composition root 传参 |
| M3 CONTEXT_COMPACTED 状态表述 | MiMo | medium | **FIXED** | plan:344 event payload 不编码状态变更 |
| M4 schema CHECK 兼容性 | MiMo | medium | **FIXED** | plan:179 fresh-schema 起库；不做旧库兼容 |
| L1 fake compactor import boundary | MiMo | low | **FIXED** | plan:516-517 production 包内 docstring + 显式注入约束 |
| L2 usage payload 扩展 | MiMo | low | **FIXED** | plan:236-237 不扩展 `USAGE_REPORTED` EventLog payload |
| L3 tests README 更新 | MiMo | low | **FIXED** | plan:520 明确四个新测试类别 |
| M1 RunStartReason.RECOVERY | DS | medium | **FIXED** | plan:213 改为必须新增，不再用条件语气 |
| M2 RunStartReason.STEER | DS | medium | **FIXED** | plan:213 "STEER belongs to the steer phase owner" |
| M3 schema migration awareness | DS | medium | **FIXED** | plan:179 fresh-schema 起库约定 |
| M4 EPISODE_SUMMARY_ACCEPTED removal | DS | medium | **FIXED** | plan:316 移出 memory compact truth path；plan:316 确认无非测试消费者 |
| M5 DurableCompactArtifactProvider message | DS | medium | **FIXED** | plan:393-399 明确 system message 内容/边界/可为空 |
| L3 CONTEXT_COMPACTION_FAILED projection | DS | low | **FIXED** | plan:323 不进入 production consumer filter |
| L4 fake compactor placement | DS | low | **FIXED** | plan:516-517 同 MiMo L1 |

---

## New Findings

### M1. ACCEPTED partial unique index "if needed" 留下并发 start_run 窗口

**Severity: medium**

**Plan reference**: plan:178

```text
Add a separate fresh-schema partial uniqueness guard for one pre-start candidate
per session if needed, for example host_runs_one_accepted_per_session WHERE
status = 'accepted'
```

**Evidence**:

- `start_run` 创建 `ACCEPTED` Run 在 admission transaction（plan:184），governance gate 在独立 transaction（plan:197）
- 两个并发 `start_run` 可能同时通过 admission check（plan:192 的 single-start arbitration 在 governance transaction 而非 admission transaction）
- plan:192 的单次启动仲裁在 governance write transaction 内——语义上保护了"只启动一个 ACCEPTED"，但未阻止 admission 产生第二个 `ACCEPTED` Run
- 第二个 `ACCEPTED` Run 可能永远不被启动：governance loop 总是选最早 ACCEPTED（plan:197），启动后 active-run index 阻止新的 start，但剩余的 `ACCEPTED` 无自动超时/清理机制
- 若两个 ACCEPTED 存在于 governance loop 两次迭代间，第一个被启动为 RUNNING 后第二个因 active-run unique index 冲突而无法启动——但其 status 仍为 `accepted`，不会被 cancel_run 自动清理

**Impact**: 并发场景下可能产生孤儿 `ACCEPTED` Run，用户需手动 cancel。单线程 admission 下窗口极窄，但 plan 的 "if needed" 未裁决是否需要 schema-level guard。

**Recommendation**: Implementation 应在 Slice 4 明确选择：要么加 `host_runs_one_accepted_per_session` partial unique index，要么在接受 "at most one ACCEPTED by governance arbitration" 语义的同时，添加 governance loop 对多余 ACCEPTED 的 fail-safe 清理（例如在启动第一个 ACCEPTED 后将同 session 的其他 ACCEPTED 标记为 FAILED）。

---

### L1. 旧 `create_running_run_with_starting_attempt_in_transaction` 的处置为 either/or 未裁决

**Severity: low**

**Plan reference**: plan:189

```text
Either delete it if no tests or production paths still need the old combined
semantics, or keep it as an internal test-only helper with call sites migrated
away; do not leave a production bypass around context governance.
```

**Evidence**:

- `dayu/host/durable/run_transition.py:679` 当前被 `dayu/host/admission.py:1791-1817` 的 `start_run` flow 调用
- 删除或保留的裁决影响 refactoring 范围：删除需要迁移所有 call site 和测试；保留需要添加 "test-only" 文档和可能的 assert guard

**Impact**: Low。plan 已明确"production path must stop calling it"，这是 correctness 的硬性要求。删除 vs 保留是 cleanup 决策，不影响架构正确性。

**Recommendation**: Implementation agent 应在 Slice 4 第一个 commit 中决定：优先删除（减少代码路径），除非测试依赖太重。

---

### L2. 两个新 start helper 签名和实现可能重复

**Severity: low**

**Plan reference**: plan:187,190

- `start_accepted_run_with_starting_attempt_in_transaction`（plan:187）
- `start_queued_run_with_starting_attempt_after_governance_in_transaction`（plan:190）

**Evidence**: 两个 helper 都执行"创建 RUN_STARTED + ATTEMPT_STARTED + dispatch record"，只是输入 Run 的 origin status 不同（accepted vs queued）。plan 未说明是否共享内部实现。

**Impact**: Low。两个 helper 可能产生代码重复但不影响正确性。Implementation 可以用共享内部 helper + 外层 status 检查来消除重复。

**Recommendation**: Implementation agent 应考虑提取 shared private helper `_start_run_with_starting_attempt_after_governance`。

---

### I1. `HostCommandHandleOptions` 新增 required int fields 是 breaking change

**Severity: info**

**Plan reference**: plan:498-499

```text
HostCommandHandleOptions.context_window_size: int
HostCommandHandleOptions.reserved_output_tokens: int
```

**Evidence**: plan:537 的 public contract test 要求 "reject invalid values"，说明这两个字段是 required positive int。现有 `HostCommandHandleOptions` dataclass 不含这两个字段，添加 required fields 会导致所有现有 call site 编译/类型检查失败。

**Impact**: Info。这是预期的 breaking change，所有 call site 均需更新。plan:510-513 已描述 Service/composition root 如何传入这些值。

**Recommendation**: Implementation 在 Slice 6 改动时需同时更新所有 `HostCommandHandleOptions` 构造点。

---

### I2. Governance gate transaction 与 concurrent cancel_run 的竞态未讨论

**Severity: info**

**Plan reference**: plan:185-186 (cancel_run handles ACCEPTED), plan:197-200 (governance loop)

**Evidence**: 若 governance gate 事务正在将 ACCEPTED → RUNNING，同时 cancel_run 事务尝试取消同一 ACCEPTED Run。两者在不同 transaction 中执行——先提交者胜，后提交者应处理 stale state（如 Run 已变为 RUNNING 则按 RUNNING cancel；如已被 cancel 则 governance 启动失败）。

**Impact**: Info。这是通用事务冲突问题，非 P10 特有。现有 `cancel_run` 对 RUNNING 已有处理路径（plan:185-186 补全了 ACCEPTED path）。governance gate 读 ACCEPTED 时需在事务内 re-read 当前 status 以防御 stale read。

**Recommendation**: Implementation agent 可在 governance gate transaction 内加 `read_run_by_id` 验证 status 仍为 `accepted` 后再执行 start。

---

## Non-issues / Verified Correct

以下检查项经代码核对确认无问题：

1. **`RunStartReason.RECOVERY` 缺失**：`dayu/host/durable/state.py:114-119` 当前只有 `INITIAL`、`QUEUE_PROMOTION`、`RESUME`。plan:213 已改为必须新增。✅

2. **Schema CHECK constraint `'accepted'` 缺失**：`dayu/host/durable/schema.py:301-312` 当前 CHECK 无 `'accepted'`。plan:176 明确新增，plan:179 明确 fresh schema 起库。✅

3. **Active-run index 不包含 `accepted`**：`dayu/host/durable/schema.py:800-803` 索引只含 `running/waiting/cancelling/recovering`。plan:178 明确 `accepted` 不加入 active-run index。✅

4. **`CONTEXT_COMPACTION_REQUESTED` 当前 unsupported recovery 收口**：`dayu/host/engine_ingest.py:513-530` 正确识别。plan:447-455 完全替换该路径。✅

5. **`EPISODE_SUMMARY_ACCEPTED` 移除范围**：`dayu/host/durable/memory.py:73-78` 只有 memory projection consumer 引用。Grep 确认无其他消费者后（plan:316），可安全移出 compact truth path。✅

6. **`CompactArtifactProvider` protocol 与 RunInputBuilder message 顺序**：`dayu/host/run_input.py:338-350` protocol 已定义，`dayu/host/run_input.py:1209` 顺序为 scene→memory→compact→continuity→user prompt。plan:391-399 的 DurableCompactArtifactProvider 插入 compact 插槽，不破坏顺序。✅

7. **Fake compactor placement**：plan:516-517 要求 production 包内 `fake_compaction.py` 带 docstring 声明 + 仅显式注入。对齐现有 `NoopCompactArtifactProvider`（`run_input.py:888`）模式。✅

---

## Residual Risks

1. **`RunStatus.ACCEPTED` 的广泛测试更新**（plan:584）：新增 public enum 成员和 schema CHECK 值影响所有 RunStatus 匹配测试。Risk 已在 plan 中识别。

2. **Engine 双重事件幂等性**（plan:585）：Engine 可能 emit 两个 related context events。plan:454 要求 idempotent 处理，但实现复杂度可能被低估。

3. **Real LLM compactor 未就绪**（plan:586）：Fake compactor 验证 governance，production 需显式注入 compactor port 或 fail closed。

4. **Conservative estimator 过度触发 compact**（plan:589）：这是有意的 fail-safe 设计。

5. **Orphan artifact 文件**（plan:588）：crash 在 artifact 写入后、DB commit 前产生孤立文件。P11 负责清理。

6. **ACCEPTED partial unique index missing**（本次 M1）：并发 start_run 可能产生多余 ACCEPTED Run。Implementation 需在 Slice 4 处理。

7. **Pre-start wakeup 进程重启**（plan:202）：P10 只覆盖同进程 wakeup；跨进程/重启后的 orphan ACCEPTED scan 归 Phase 11。

---

## Conclusion

Plan is **PASS** for implementation handoff. All 3 MiMo blocking + 3 DS high findings confirmed fixed. 6 non-blocking/non-high findings from prior reviews also confirmed fixed in the Codex fix pass. 1 new medium (ACCEPTED partial index ambiguity), 2 new low, 2 new info findings — none block implementation start. Implementation agent should resolve M1 in Slice 4 before or during the first commit.
