# Code Review

## Scope

- Mode: current changes
- Branch: feat/phase-12-5-conversation-memory-optimize
- Base: 851a2e7 (gateflow: accept P12.6 slice 5)
- Output file: docs/reviews/p12-6-slice6-code-review-mimo-20260524.md
- Included scope: dayu/host/memory.py, dayu/host/README.md, tests/README.md, tests/host/test_memory_projection.py, tests/host/test_run_input_builder.py, docs/reviews/p12-6-slice6-implementation-codex-20260524.md
- Excluded scope: docs/host/implementation-control.md (总控状态改动)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下为低严重度观察项，不影响正确性或可合并性：

### 001-未修复-低-`DEFAULT_MEMORY_MAX_EPISODE_SUMMARIES_FLOOR` 命名语义歧义

- **入口/函数**: `_policy_bounded_recent_episode_summaries` (memory.py:2441)
- **文件(行号)**: memory.py:57, memory.py:2453
- **输入场景**: 任何使用 episode summary bounding 的 memory projection
- **实际分支**: `max_items = max(DEFAULT_MEMORY_MAX_EPISODE_SUMMARIES_FLOOR, policy.recent_raw_turns_floor)`
- **预期行为**: 常量名含 "FLOOR" 暗示下限语义，但实际用作 episode summary 数量上限的下限保底
- **实际行为**: `DEFAULT_MEMORY_MAX_EPISODE_SUMMARIES_FLOOR = 1` 与 `policy.recent_raw_turns_floor = 2` 取 max，有效上限为 2。行为正确，但 "FLOOR" 用于 "MAX" 语义的常量容易误导
- **直接证据**: memory.py:57 定义 `DEFAULT_MEMORY_MAX_EPISODE_SUMMARIES_FLOOR = 1`；memory.py:2453 `max_items = max(DEFAULT_MEMORY_MAX_EPISODE_SUMMARIES_FLOOR, policy.recent_raw_turns_floor)`
- **影响**: 仅命名清晰度，不影响运行时行为
- **建议改法和验证点**: 考虑重命名为 `DEFAULT_MEMORY_EPISODE_SUMMARIES_MIN_CAP` 或类似名称，明确表达"episode summary 上限的下限保底"语义。纯命名重构，验证现有测试通过即可
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-未修复-低-`_evidence_backed_fact_cover_refs` 包含 `candidate_id` 的覆盖语义

- **入口/函数**: `_evidence_backed_fact_cover_refs` (memory.py:2528)
- **文件(行号)**: memory.py:2537-2545
- **输入场景**: minimum preserve item 的 `source_refs` 包含某个 fact 的 `candidate_id`
- **实际分支**: `refs.add(fact.candidate_id)` 在 cover refs 构建中
- **预期行为**: candidate_id 是 candidate-local 诊断 id，不是权威 provenance
- **实际行为**: candidate_id 被加入 cover refs，意味着 minimum preserve 可以被 candidate_id 覆盖。这在当前测试场景中不会触发（测试的 source_refs 使用 event-input 等 event 级 ref），但语义上允许 candidate_id 级别的覆盖
- **直接证据**: memory.py:2539 `refs.add(fact.candidate_id)`
- **影响**: 当前无实际影响，因为 minimum preserve 的 source_refs 通常指向 event 级 ref。但若未来 compactor 输出的 minimum preserve 使用 candidate_id 作为 source_ref，会产生非预期覆盖
- **建议改法和验证点**: 当前行为可接受。若需收紧，可移除 `candidate_id` 的 cover ref 注入，仅保留 `item_id`、`evidence_refs`、`event_id`、`compact_artifact_ref`、`payload_ref`。添加测试验证 candidate_id 不覆盖 minimum preserve
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Tests reviewed / recommended

已 review 测试：

- `test_final_answer_user_input_summary_do_not_become_evidence_backed_fact`: 验证 final answer / user input / episode summary 不升级为 stable fact。覆盖 anti-hallucination 矩阵。
- `test_memory_projection_materializes_pinned_state_current_value_not_patch_log`: 验证 pinned state 只暴露当前物化值，不保留 patch log。
- `test_evidence_backed_fact_working_set_is_bounded_and_deterministic`: 验证 dedupe key（normalized claim_text + sorted evidence_refs + evidence_kind）去重、superseded diagnostic、bounded working set 确定性。
- `test_episode_summaries_are_policy_bounded_not_append_only_rendered`: 验证 episode summaries 只保留 policy bounded recent working set，旧 summary 被 budget diagnostic 解释。
- `test_minimum_preserve_expires_when_covered_by_stable_or_summary`: 验证 minimum preserve 被后续 episode summary 覆盖后退出 continuity working set。
- `test_run_input_builder_renders_claim_text_and_evidence_refs_not_digest_only`: 验证 RunInputBuilder 渲染 stable facts 包含 claim_text / evidence_refs / evidence_kind，不退化为 digest-only。
- `test_no_compaction_recent_raw_turns_continuity_still_works`: 验证未 compact 时 recent raw turns 仍提供连续性，不产生 evidence-backed facts block。

推荐补充测试（非 blocking）：

- 多次 compact 后 fact dedupe 的 event sequence 相同时，item_id 字典序决定保留哪个的边界场景。
- `_select_evidence_backed_fact_working_set` 在 token overlap 全为零时的 fallback 行为（当前依赖 event_sequence 降序，已有隐式覆盖但无显式测试）。

## Residual Risk

- fact working set relevance 排序使用 Host-neutral token overlap，不引入财务业务特定排序。设计文档明确这是第一版策略，后续可作为独立 Host policy / retrieval owner 设计。当前无风险。
- episode summary bounding 使用 `policy.recent_raw_turns_floor` 作为上限参考值。若 future policy 将 `recent_raw_turns_floor` 调大，episode summary 上限也会同步增大。这是设计意图，不是 bug。
- 无 compatibility wrapper、无跨层依赖、无 Any/object 类型、无反向 import。README 更新在职责范围内。
