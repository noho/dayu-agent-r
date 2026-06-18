# Aggregate Deep Review — WU-CM-12 Conversation Memory Drift Repair

## Scope

- Mode: current changes (aggregate — cumulative branch vs `main`)
- Branch: `wu-cm-12-conversation-memory-drift`
- Base: `main`
- Output file: `docs/reviews/deepreview-wu-cm-12-ds-20260618.md`
- Included scope:
  - **Design/plan**: `docs/host/design.md` (3564 lines, chapters 23-25 primary), `docs/host/host-issues/wu-cm-12-conversation-memory-drift-plan.md` (390 lines)
  - **Control**: `docs/host/issues-implementation-control.md` (1619 lines)
  - **Production code**: `dayu/host/memory.py`, `compact_material.py`, `context_fallback.py`, `run_input.py`, `dispatch.py` (and accumulated changes in `engine_ingest.py`, `api.py`, etc.)
  - **Tests**: `tests/host/test_memory_projection.py`, `test_compact_material.py`, `test_run_input_builder.py`, `test_dispatch_scheduler.py`, `test_compaction_operation.py`, `test_context_compact_events.py`, `test_public_compact_smoke.py`, `test_public_open_host_multiturn_smoke.py`, `test_public_tool_wiring_smoke.py`
  - **Review artifacts**: 30+ review/adjudication/implementation artifacts across S1-S5 + design writeback
- Excluded scope: `utils/`, `dayu/render/`, `dayu/cli/`, `dayu/fins/` (not modified by WU-CM-12); `engine_ingest.py` reactive path (intentionally unchanged except S2 policy wiring).
- Cumulative diff: **54 files, 8886 insertions, 299 deletions** (vs `main`)
- Parallel review coverage: 3 sub-agents for design doc exploration, control doc residual scanning, and MemoryProjectionPolicy ownership audit.

## Findings

### 1-未修复-低-control doc 中 `WU-CLI-ACTIVITY-01-PR-R1` 状态陈旧

- **入口/函数**: N/A（文档级别不一致）
- **文件(行号)**: `docs/host/issues-implementation-control.md:214`
- **输入场景**: 读取 WU-CLI-ACTIVITY-01 section 的 active residual 状态时。
- **实际分支**: Line 214 记录 `WU-CLI-ACTIVITY-01-PR-R1` 状态为 "deferred with owner"。
- **预期行为**: 该 residual 已在 WU-CM-12 S5 中由 public continuity smokes 关闭（line 1543: "closed by passing public continuity smokes"）。WU-CLI-ACTIVITY-01 section 应反映最新状态。
- **实际行为**: WU-CLI-ACTIVITY-01 closeout section（lines 214, 355）未在 WU-CM-12 关闭该 residual 后更新，仍显示 "deferred with owner"。
- **直接证据**:
  - Line 214: `"residual WU-CLI-ACTIVITY-01-PR-R1 deferred with owner"`
  - Line 1543: `"WU-CLI-ACTIVITY-01-PR-R1 closed by passing public continuity smokes"`
  - Line 1598: WU-CM-12 target 明确包含 "覆盖 residual `WU-CLI-ACTIVITY-01-PR-R1`"
- **影响**: 读者可能认为该 residual 仍未解决，导致重复排查。不影响代码正确性。
- **建议改法和验证点**: 将 line 214 更新为 `closed`，引用 WU-CM-12 S5 的 public continuity smoke 通过证据。
- **修复风险（低）**: 纯文档更新。
- **严重程度（低）**: 文档不一致，不影响 correctness/stability。

### 2-未修复-低-`WU-CM-12-S4-R1` 缺少具体 owner

- **入口/函数**: N/A（residual tracking 级别）
- **文件(行号)**: `docs/host/issues-implementation-control.md:205`
- **输入场景**: 需要推进 reactive tier1-3 recovery 时。
- **实际分支**: Owner 字段为 "Future reactive compact recovery follow-up; owner must be assigned by user or GitHub Issue before implementation"。
- **预期行为**: `deferred-with-owner` 状态的 residual 应有具体 owner（人员、GitHub Issue 编号或 follow-up WU ID）。
- **实际行为**: Owner 字段描述了一个目的地（reactive compact recovery follow-up）但没有具体 assignee。控制文档 tracking rule（line 185）接受 `deferred-with-owner` 状态进入 draft-PR，但当前没有可查询状态的具体人员或 issue。
- **直接证据**: Line 205: `"owner must be assigned by user or GitHub Issue before implementation"`
- **影响**: 该 deferred residual 可能被遗漏。不影响当前 WU 的正确性（reactive recovery 是 intentional non-goal）。
- **建议改法和验证点**: 创建 follow-up GitHub Issue 并在 control doc 中引用；或在 closeout 时指定明确的后续 WU ID。
- **修复风险（低）**: 流程/文档层面。
- **严重程度（低）**: 不影响当前实现，但属 residual tracking 不完整。

## 逐项重点审查结论

### 1. design.md 作为设计真源

**结论: PASS。** `docs/host/design.md` (3564 lines) 是 WU-CM-12 的单一设计真源。

- **讨论稿不再替代真源**：plan 和 design writeback artifacts（`docs/reviews/wu-cm-12-design-writeback-*.md`）已回写到 design.md chapters 23-25。WU-CM-12 S1-S5 的实现 artifact 明确引用 design.md 章节号作为真源。
- **No silent truncation**: Chapter 24.2 (line 2866) 明确禁止 "字段级 silent truncation、preview 化或 summary 化"。Chapter 25 (line 3292) 规定 "只能 whole-block keep-drop、section-aware keep-drop、chunking with provenance 或 fail closed"。Chapter 24.6 (line 3115) 禁止 "runtime 字段级或逐 section silent truncation"。
- **No preview**: Chapter 13 定义 `preview` event class 与 `canonical_fact` 边界。Line 2866 禁止 "preview 化"。
- **No assemble/stitch/rewrite**: Line 3263 禁止列表明确禁止 "截断、重新 summary、改写 fact/anchor/intent/continuity、临时生成新 compacted view"。Line 3292 规定 "selection 输出的 block id/provenance 必须从 selection 到 rendering 全程同源"。
- **Five semantic memories**: Chapter 24.5 (lines 3061-3081) 定义完整的五种 Session Semantic Memory：Trace Memory、Evidence/Fact Memory、Session Summary Memory、Answer Anchor Memory、Forward Intent Memory。Line 2815 明确 "selected_recent_window 不是第六类 Semantic Memory"。
- **Fallback tiers**: Chapter 25 (lines 3193-3265) 完整定义 tier 0-5。Tier 1-3 为 compact recovery fallback（仍使用 LLM compactor），tier 4-5 为 dispatch fallback（无 compactor）。

**实现偏离检查**：

| 设计约束 | 实现状态 |
|----------|---------|
| 禁止字段级 silent truncation | `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS` 已移除（S1）；`_COMPACT_SUMMARY_MAX_CHARS` 已移除（S3）；`_bounded_text` 已移除（S2） |
| chunking with provenance | `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS=4096` 的 `_evidence_chunks()` 保留完整文本，拆分为多个 labeled chunks（非 truncation） |
| selected_id 从 selection 到 rendering 同源 | S3 provenance guards + S5 同源修复 |
| tier 1-3 仍使用 LLM compactor | S4 proactive recovery 正确实现，每 tier `run_compaction_operation(max_attempts=1)` |
| tier 4 有 floor 保护 | S2 fallback selection 实现 floor/caps/hard-budget |
| tier 5 current-input-only | S2 `build_recent_window_fallback_selection` 当 floor-only 超 hard budget 时调用方 fail closed |

### 2. MemoryProjectionPolicy 作为 LLM-facing material 产量单一 owner

**结论: PASS。** 经全面审计，MemoryProjectionPolicy 是 LLM-facing material 产量控制的主要 owner。

**Policy 字段覆盖率**：

| 字段 | 消费点 | 机制 |
|------|--------|------|
| `session_summary_char_cap` | `memory.py:1731` | 超限 → whole-drop + diagnostic（不截断） |
| `evidence_fact_char_cap` | `memory.py:1813` | 超限 → whole-item drop + diagnostic |
| `selected_recent_window_turn_floor` | `memory.py:1981`, `compact_material.py:1530`, `context_fallback.py:379`, `dispatch.py:1498` | 保护最近 N 个 turn group |
| `fallback_selected_recent_window_item_cap` | `context_fallback.py:781`, `dispatch.py:1504` | 非 floor block 追加时 item cap |
| `fallback_selected_recent_window_char_cap` | `context_fallback.py:784`, `dispatch.py:1502` | 非 floor block 追加时 char cap |

**已移除的私有 cap**：
- `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS=1200` — 已删除（S1），current_input_anchor 不再被截断
- `_COMPACT_SUMMARY_MAX_CHARS=1200` — 已删除（S3），compact artifact 完整语义渲染
- `_bounded_text` — 已删除（S2），不再作为私有截断函数

**保留的非截断常量**：
- `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS=4096` — 用于 `_evidence_chunks()` 的确定性 chunking。**非 truncation**：文本完整保留，拆分为多个 labeled chunks 并携带 `parent_label`/`chunk_ordinal` provenance。符合 design.md "chunking with provenance" 许可。

**结论**：不再存在绕过 MemoryProjectionPolicy 的对 LLM-facing material 做私有截断的代码路径。所有 cap 均以 whole-drop（不截断）+ diagnostic 的方式生效。

### 3. turn_group_id / floor / fallback caps 正确性

**结论: PASS。** turn-group-based floor 完整保护 Host Run group，不打散 floor，不用后续小块绕 cap。

**floor 计算**（三个 selector 一致）：
- `memory._protected_recent_run_ids` — 按 `run_id` 分组，取 newest N group
- `compact_material.protected_recent_turn_group_ids_for_material_blocks` — 按 `turn_group_id` 分组，取 newest N group
- `context_fallback` — 从 `compact_material` import 共享 helper

**caps 保护顺序**（S2 `build_recent_window_fallback_selection`）：
1. Floor 先建（不受 caps 裁剪）
2. Non-floor 整块追加受 `fallback_selected_recent_window_item_cap` / `fallback_selected_recent_window_char_cap` 限制
3. Cap 拒绝后 `break`（不 later backfill）
4. Hard budget 超限时整块回滚

**strict cap 防绕序**（S4 `select_compact_segment` + `max_selected_item_count`）：
- 首个 block 超 budget 且 `max_selected_item_count is not None` → `budget_blocked=True` → 所有后续 block 被排除
- 防止用更晚小块绕过 cap
- `max_selected_item_count is None` 时（normal/reactive path）behavior unchanged

**floor 优先于 cap**：
- `context_fallback.py:509`: "floor 不受 fallback item/char caps 裁剪"
- `_fallback_caps_allow_append` 只检查非 floor block 的追加

**turn_group_id 缺失 → fail closed**：
- memory: `ValueError("selected recent window item is missing run_id")`
- compact: `ValueError("eligible material block is missing turn_group_id")`
- context_fallback: `ValueError("eligible fallback material block is missing turn_group_id")`

### 4. provenance guard 完整性与 selected-id 同源

**结论: PASS。** S3 的 9 项 provenance guard + S5 的 material_blocks 同源修复构成完整的 fail-closed 保护。

**S3 guards**（`_selected_material_render_view`, `run_input.py:2766-2818`）：

| # | Guard | Fail-closed 行为 |
|---|-------|-----------------|
| 1 | material block ids 唯一性 | `HostDurableError("material view block ids must be unique")` |
| 2 | selected ids 去重 | `HostDurableError("fallback selected block ids must be unique")` |
| 3 | 全部 selected id 存在 | `HostDurableError("fallback selected block id is missing from material view")` |
| 4 | current input ref 唯一匹配 | `HostDurableError("fallback current_input_ref mismatch")` |
| 5 | source refs 一致 | `HostDurableError("fallback selected source refs mismatch")` |
| 6 | fallback input digest 一致 | `HostDurableError("fallback input digest mismatch")` |
| 7 | selected material view digest 一致 | `HostDurableError("fallback selected material view digest mismatch")` |
| 8 | selected raw turn count 一致 | `HostDurableError("fallback selected raw turn count mismatch")` |
| 9 | protected group consistency | `HostDurableError("fallback protected group consistency mismatch")` |

**S5 同源修复**：
- Provider 侧：`EventLogContextFallbackProvider._load_context_fallback_tx` 在 proactive path 重建 EventLog-backed frozen material view（`_proactive_material_blocks_for_window`，调用 `build_pre_dispatch_compact_material_view`）
- Consumer 侧：`RunInputBuilder.build` 优先使用 `fallback.material_blocks`（若非 None）
- block_id 格式一致性：重建 view 使用与 fallback selector 相同的 `build_pre_dispatch_compact_material_view` → identical id 格式
- 非 proactive path（reactive）退回到 ordinary `build_run_input_material_blocks`（behavior unchanged）

**EventLogContextFallbackProvider fail-closed**（S3）：
- window/digest 缺失 → `HostDurableError("active fallback input window is missing")`（不再 `return None`）
- digest 不匹配 → `HostDurableError("fallback input digest mismatch")`（新增检查）
- current_input_ref 不匹配 → `HostDurableError("fallback current_input_ref mismatch")`（不再 `return None`）
- provenance 字段（`selected_recent_window_turn_floor`/`selected_raw_turn_count`/`selected_material_view_digest`）→ `_required_non_negative_int`/`_required_text` fail closed

### 5. tier 1-5 state machine 正确性

**结论: PASS。** proactive tier 1-5 state machine 正确实现；reactive deferred 在 control doc 中有记录。

**Proactive state machine**（`dispatch.py:_execute_proactive_compaction_async`）：

```
normal compact (tier 0)
  ├─ accepted → _append_compacted_event(CONTEXT_COMPACTED)
  └─ not accepted → recovery loop:
       ├─ [stale check] is_cancelled? → break
       ├─ tier 1: bounded caps + full previous view → run_compaction_operation(max_attempts=1)
       │   ├─ [stale check] is_cancelled? → break
       │   ├─ accepted → CONTEXT_COMPACTED (accepted_attempt_number = global seq)
       │   └─ failed → continue
       ├─ tier 2: (conditional) section-degraded previous view → run_compaction_operation(max_attempts=1)
       │   └─ same pattern
       ├─ tier 3: bounded caps + empty previous view → run_compaction_operation(max_attempts=1)
       │   └─ same pattern
       └─ all fail → commit:
            ├─ [stale check] Session open? → CONTEXT_COMPACTION_FAILED
            ├─ accepted_result accepted? → CONTEXT_COMPACTED (if recovery succeeded)
            └─ not accepted → _append_compaction_failed_with_proactive_fallback
                 ├─ fallback dispatch → tier 4 (floor + current input)
                 └─ or fail_unstarted → tier 5 (current input only or fail closed)
```

**Stale checks 三层覆盖**：
1. Before tier attempt: `cancellation_token.is_cancelled()` (durable Run/Session check)
2. After tier proposal: `cancellation_token.is_cancelled()`
3. Commit transaction: Run status/input cursor + `_run_session_allows_proactive_compaction` (Session OPEN/closed_at)

**Reactive recovery deferred**：
- S4-R1 在 control doc line 205 记录为 `deferred-with-owner`
- 原因：reactive path 在 `engine_ingest.py` 中独立实现，需要 Engine ingest recovery 流程改造（execution id、run-local cancellation、cursor commit guard、reactive accepted/fallback sequencing）
- 当前 reactive 行为不变（无 tier 1-3 recovery，直接 tier 4/5 fallback）
- 不阻断本 WU：proactive recovery 已完整实现

**Tier 2 条件跳过**：
- 当 `degraded_previous_view == original` 或 `len(degraded) == 0` 时 tier 2 不添加
- 原因：degrade 无效果时 tier 2 与 tier 1 等价，跳过避免冗余 attempt
- 正确但未在 design.md 中显式文档化

### 6. S5 public smoke reconciliation

**结论: PASS。** 超长 current input 正确处理，符合 design.md no-truncation/no-preview。

**三个 smoke 改动**：

| 测试 | 改动 | 验证 |
|------|------|------|
| `test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` | `_long_compaction_prompt()` → `_soft_threshold_prompt()` | 短 input 进入 compact → fact reuse |
| `test_multi_compact_public_path_keeps_memory_and_compactor_input_bounded` | `_long_compaction_prompt()` → `_soft_threshold_prompt()` | 短 input 进入 compact → multi-compact bounded |
| `test_proactive_compact_duplicate_prompt_does_not_exceed_compactor_window` → 重命名 `test_proactive_compact_duplicate_prompt_falls_back_without_lossy_anchor` | 改为验证 no-compactor path | `fake_compactor.prompt_lengths == []`, `compact_artifact_files == ()`, `terminal.kind == SUCCEEDED` |

**超长 input 路径**：`CurrentInputAnchorVNext.text` 1200-char contract → 超长 → 不生成 compactor proposal → 不写 compact artifact → dispatch fallback → Run 成功。无截断、无 preview、无 summary。符合 design.md。

**Public continuity smokes**：`test_deterministic_two_turn_request_contains_prior_final_answer` + `test_mock_tool_result_feeds_same_run_and_later_run_continuity` → **2 passed**。WU-CLI-ACTIVITY-01-PR-R1 已关闭。

**Public compact smoke**：`11 passed, 1 skipped`。

### 7. active residual table 准确性

**结论: PASS（含 2 个 low-severity findings）。**

**当前 active residual table（lines 196-205）**：

| ID | 状态 | 评估 |
|----|------|------|
| `WU-CM-12-S4-R1` | `deferred-with-owner` | 正确。Reactive recovery deferred。Owner 缺具体 assignee（Finding 2） |
| 其他 5 项 | `transferred-to-issue` 或 `deferred-with-owner` | 正确。各有明确的 issue/WU 引用 |

**已关闭 residual 的 artifact 依据**：

| Residual | 关闭依据 |
|----------|---------|
| `WU-CM-12-S1-R1` | `_facts_from_accepted_event` root-cause fix + `test_accepted_compact_keeps_valid_fact_before_empty_evidence_labels` regression test |
| `WU-CLI-ACTIVITY-01-PR-R1` | 2 public continuity smokes passed |
| `RR-ACT-01` through `RR-ACT-05` | WU-CLI-ACTIVITY-01 slices |

**注意**：
- `WU-CLI-ACTIVITY-01-PR-R1` 在 line 214 状态陈旧（Finding 1）
- 大多数已关闭 residual 的 control doc 记录不引用具体 review artifact 路径
- `WU-CLI-INTERACTIVE-RESUME-01-R1/R2`（lines 391-393）使用非规范 disposition 语言（"rejected by user裁决", "fixed immediately"）
- 不存在无状态的 orphan residual

### 8. README decision

**结论: PASS。** 符合 CLAUDE.md 的 README 更新触发规则。

- `dayu/host/README.md`：S1-S5 累计变更不改变 Host public API、装配方式、稳定开发手册入口或用户工作流 → 不更新
- `tests/README.md`：test 变更不改变测试目录结构、运行方式或维护规则 → 不更新
- 根 `README.md`：无 CLI/Web/WeChat 入口、命令参数、默认输出通道、日志定位或用户工作流变化 → 不更新
- `dayu/README.md`：无分层关系、装配方式或边界变化 → 不更新
- `dayu/engine/README.md`：未修改 Engine 层 → 不更新
- `dayu/fins/README.md`：未修改 fins 层 → 不更新
- `dayu/config/README.md`：未修改 config 层 → 不更新

**decision 合理，符合触发规则。**

## 综合验证

| 验证项 | 结果 |
|--------|------|
| `pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_public_compact_smoke.py -q` | **323 passed, 1 skipped in 2.86s** |
| `pytest tests/host/test_public_open_host_multiturn_smoke.py::test_deterministic_two_turn_request_contains_prior_final_answer tests/host/test_public_tool_wiring_smoke.py::test_mock_tool_result_feeds_same_run_and_later_run_continuity -q` | **2 passed in 0.38s** |
| `python -m pyright dayu/host/` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check main...HEAD` (production code only) | **无 whitespace 错误**（review artifacts 有 2 个 pre-existing blank-line-at-EOF） |

## Residual Risk

### WU-CM-12 scope 内

| ID | Risk | Status |
|----|------|--------|
| S4-R1 | Reactive tier 1-3 compact recovery 未实现 | `deferred-with-owner` — 需 follow-up WU/Issue |
| — | `ConversationCompactInputVNext` 1200-char current input anchor 上限 | intentional design constraint — 超长 input 走 dispatch fallback |
| — | Tier 2 条件跳过行为未在 design.md 显式文档化 | Low — 行为正确，如需文档化可在后续 design writeback 补充 |
| — | `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS=4096` 未映射到 MemoryProjectionPolicy 字段 | 非 truncation（是 chunking-with-provenance），但 chunk size 不由 policy 控制 |

### WU-CM-12 scope 外（control doc 传递）

| ID | Risk |
|----|------|
| WU-CM-12-S4-R1 | Reactive tier 1-3 compact recovery follow-up（待 assign owner） |
| Various transferred-to-issue | 已转移到对应 GitHub Issues |

## Open Questions

1. **`WU-CM-12-S4-R1` concrete owner**：当前 owner 字段为 "must be assigned by user or GitHub Issue"。建议在 closeout 时创建 follow-up Issue 并回写 control doc。

2. **`EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS` 是否需要 policy 化**：当前 4096-char chunk size 是硬编码常量。若未来需要按场景调整 chunk size（如不同 compactor 有不同的 optimal chunk size），可考虑将其加入 MemoryProjectionPolicy。

## Conclusion

**PASS** — WU-CM-12 S1-S5 累计实现正确、完整，符合 design.md 设计真源。

- **Design doc** 是单一设计真源，讨论稿不再替代。No silent truncation/preview/assemble/stitch/rewrite 约束均已编码到实现中。
- **MemoryProjectionPolicy** 是 LLM-facing material 产量的主要 policy owner。所有已移除的私有 cap（`CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS`、`_COMPACT_SUMMARY_MAX_CHARS`、`_bounded_text`）确认已删除。`EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS` 是 chunking-with-provenance 而非 truncation。
- **turn_group_id/floor/caps** 完整保护 Host Run group，floor 优先于 caps，strict budget_blocked 防绕序，missing turn_group_id fail closed。
- **provenance guards** S3 9 项 guard + S5 material_blocks 同源修复构成完整 fail-closed 保护。EventLog-backed 与 ordinary 两个 material view 路径均正确。
- **tier 1-5 state machine** proactive recovery 完整实现（stale checks 三层覆盖、accepted_attempt_number 全局序号）。Reactive deferred 有记录。
- **S5 public smoke** 超长 input 正确处理（no compactor + no artifact + dispatch fallback），public continuity smokes 通过。
- **Residual table** 整体准确。2 个 low-severity documentation findings（PR-R1 状态陈旧、S4-R1 缺具体 assignee）。
- **README** decision 符合触发规则。

**323 passed, 1 skipped; 0 pyright errors; public smokes 2 passed; git diff --check clean.**
