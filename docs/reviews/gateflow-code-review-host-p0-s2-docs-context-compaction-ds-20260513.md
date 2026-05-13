# Gateflow Code Review — Host P0 S2 Docs Context Compaction

- Work gate: `code review`
- Review role: AgentDS
- Work unit: Host Phase 0 / P0 - Engine Context Compaction Event 语义前置
- Assigned slice: `P0-S2 docs-contract-sync`
- Under review artifact: `docs/reviews/gateflow-implementation-host-p0-s2-docs-context-compaction-20260513.md`
- Accepted plan commit: `866f6f5`
- Accepted P0-S1 commit: `ad6d116`

## 1. Review Scope

Per controller instruction, review target scope only:

- `docs/engine/design.md`
- `dayu/engine/README.md`
- `dayu/README.md`
- `docs/host/implementation-control.md`
- `docs/reviews/gateflow-implementation-host-p0-s2-docs-context-compaction-20260513.md`

Also verified correctly left unchanged:

- `dayu/engine/contracts/runner_events.py`
- `tests/README.md`
- `docs/host/design.md`

## 2. Review Method

Reviewed each target file against the approved plan (`docs/host/phase0-engine-context-compaction-plan.md`), the P0-S1 final contract (`budget_state: ContextBudgetSnapshot | None`, provider overflow path uses `None`), and README responsibility boundaries. Performed direct code read of `dayu/engine/contracts/engine_events.py` and `dayu/engine/contracts/agent_run.py` to confirm contract-code consistency. Executed sentinel checks for old `0/0/0` / `占位快照` patterns in each target file.

## 3. Evidence Summary

### 3.1 docs/engine/design.md

- §1 "Engine 当前不负责" (line 22): correctly lists `Host 上下文预算治理、proactive threshold compaction、context compact / retry、provider-aware tokenizer 或 budget policy`.
- §15 "Context Compaction" (lines 409-425): `budget_state` 设为 `None`, Engine 不做上下文压缩/compact/retry，不计算 Host budget，不做 proactive threshold compaction。`run_failed(recoverable=True)` 收口。职责明确归属调用方。
- Zero `0/0/0` or `占位快照` matches. ✓

### 3.2 dayu/engine/README.md

- "关键机制" section (line range ~408-412): `context_compaction_requested` 事件 `budget_state` 为 `None`，以可恢复失败候选收口；是否压缩、恢复、Host budget 不属于 Engine。`Engine 不做 proactive threshold compaction、compact / retry provident-aware tokenizer 或 Host budget policy` — wait.

**Wait — correction during evidence collection**: the filesystem MCP Read showed apparent "provident-aware" but Grep across the entire codebase returned zero matches for `provident-aware`. A targeted Grep for `provider-aware` in `dayu/engine/README.md` confirmed the line contains `provider-aware tokenizer` (correct). The filesystem Read rendering showed encoding artifacts in multiple places (e.g., "参数类型" rendered as "参数��型" elsewhere). The Grep-based check is authoritative.

Final: `dayu/engine/README.md` line 412 contains the correct text `provider-aware tokenizer`. No typo. ✓

- Zero `0/0/0` or `占位快照` matches. ✓

### 3.3 dayu/README.md

- "Context Governance" terminology entry (lines 117-119): Engine `context_compaction_requested` 是 reactive fallback，provider overflow 路径不携带真实 Host budget，Host Context Governance 使用自身 estimator/policy 记录预算并做 compact 决策。精化既有术语条目，未机械追加重复段落，未写成 Phase 10 已完成。 ✓
- Zero `0/0/0` or `占位快照` matches. ✓

### 3.4 docs/host/implementation-control.md

- Tracking section "Engine Context Compaction Event 语义前置" (lines 1100-1125):
  - Lines 1107-1108: 正确记录 P0-S1 最终契约：`budget_state: ContextBudgetSnapshot | None`，`None` 表示未知，`ContextBudgetSnapshot` 数值为零仍是真实快照。
  - Line 1123: **DS finding 02 Phase 5 责任已记录** — Phase 5 owns EngineEvent ingest validation 接受 `budget_state=None`。
  - Line 1124: **DS finding 02 Phase 10 责任已记录** — Phase 10 owns semantic interpretation，使用 Host estimator/policy 生成 before/after budget refs 并决策 compact/recovery。
  - Line 1125: Phase 10 测试设计覆盖要求已记录。
- Phase Map Phase 0 entry (lines 222-277): 退出条件、后续依赖与追踪项一致。 ✓
- Zero `0/0/0` or `占位快照` matches. ✓

### 3.5 Implementation Artifact Verification

Checked `docs/reviews/gateflow-implementation-host-p0-s2-docs-context-compaction-20260513.md`:

- All plan items claimed as implemented correspond to actual file changes. ✓
- Validation results: 13 tests passed, pyright 0 errors — consistent with P0-S1 code review closeout. ✓
- Sentinel check classification describes expected matches in historical artifacts only; current production docs/README clean. Independent sentinel verification confirmed. ✓
- "Checked but not modified" list correctly includes `runner_events.py`, `tests/README.md`, `docs/host/design.md`. ✓
- No stop conditions hit. ✓
- Residual risks classified with Phase 5 / Phase 10 destinations. ✓
- Non-goals honored. ✓

### 3.6 Files Correctly Left Unchanged

- **`dayu/engine/contracts/runner_events.py`**: `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` docstring says "是否 compact 由 Host 决定" — no Engine budget governance, no `0/0/0`, no compact/retry implication. Correctly not modified. ✓
- **`tests/README.md`**: Existing taxonomy covers Engine contract, Runner HTTP error, context overflow classifier tests. No structural change needed per plan. ✓
- **`docs/host/design.md`**: Plan §3.3 explicitly says "默认不改". No direct conflict with P0-S1 final contract. Correctly not modified. ✓
- **Root `README.md`**: Plan §3.3 explicitly excludes. No change needed — P0 doesn't alter user-facing workflow. ✓

### 3.7 Contract-Code Consistency

Independently verified:

- `dayu/engine/contracts/engine_events.py` line 268: `budget_state: ContextBudgetSnapshot | None` — matches docs. ✓
- `dayu/engine/contracts/agent_run.py` lines 34-49: `ContextBudgetSnapshot` docstring no longer describes `0/0/0` sentinel; states "预算未知时，使用方必须在持有本类型的字段上显式表达缺失语义". ✓

## 4. Findings

无。

所有计划项均已正确实施。文档与 P0-S1 最终契约一致。旧 `0/0/0` unknown-budget sentinel 已从当前生产文档/README 中清除。Phase 5/Phase 10 责任切分已在 implementation-control.md 追踪区正确记录。README 职责边界保持，`dayu/README.md` 只精化既有 Context Governance 术语，未重复；根 README 未触及。应保持不修改的文件均未更改。

## 5. Controller Decision Status

无 findings 需控制器裁决。

## 6. Open Questions

无。所有 deferred items（Phase 5 ingest validation 接受 `budget_state=None`、Phase 10 semantic interpretation、provider-specific tokenizer adapter、D1 reason string）均有明确 destination。

## 7. Residual Risk

- 所有 residual risks 已在 implementation artifact 中分类并指派到后续 phase，与计划 §11 一致。
- 历史 review artifacts 中保留的旧 `0/0/0` 文本是预期证据痕迹，不是当前生产真源。
- `docs/host/implementation-control.md` Phase 5 entry（进入条件、关键设计问题）尚未显式写入 `budget_state=None` 验证要求，但追踪区已明确记录该责任，Phase 5 plan 应以追踪区为真源。此为 deferred phase detail，不属于 P0-S2 scope。

## 8. Conclusion

**Pass.** P0-S2 docs-contract-sync implementation 正确、完整，与 P0-S1 final contract 一致。Finding 数量: 0.

## 9. Artifact Path

`docs/reviews/gateflow-code-review-host-p0-s2-docs-context-compaction-ds-20260513.md`
