# Code Review — WU-CM-12 S5 Selected-Id Provenance Reconciliation And Public Smoke

## Scope

- Mode: current changes (unstaged workspace changes)
- Branch: `wu-cm-12-conversation-memory-drift`
- Base: `main`
- Output file: `docs/reviews/code-review-wu-cm-12-s5-ds-20260618.md`
- Included scope: `dayu/host/context_fallback.py`、`dayu/host/run_input.py`、`dayu/host/memory.py`、`tests/host/test_dispatch_scheduler.py`、`tests/host/test_memory_projection.py`、`tests/host/test_public_compact_smoke.py` 的未提交 S5 diff，以及 `docs/reviews/wu-cm-12-s5-implementation-codex-20260618.md`。
- Excluded scope: S1-S4 已通过 review 的变更；reactive tier1-3 recovery（deferred intentional non-goal）。
- Parallel review coverage: 无。单一 reviewer 逐链路走读。

## Findings

未发现实质性问题。

## 逐项重点审查结论

### 1. proactive fallback selected-id 同源修复

**结论: PASS。** 修复正确，tier4 recent-window/floor/caps 语义完整保留。

**问题根因**（来自 implementation artifact）：pre-start compaction 使用 EventLog-backed material block ids（如 `eventlog:user:event-xxx`），而 RunInputBuilder ordinary material view 使用不同 id 空间（`memory:*` / `compact:*` / `continuity:*`）。S3 provenance guard 用 ordinary view 查找 selected ids 时，`eventlog:user:event-xxx` 不在 ordinary blocks 中 → `HostDurableError("fallback selected block id is missing from material view")`。

**修复架构**（两条互补路径）：

**Provider 侧** — `EventLogContextFallbackProvider._load_context_fallback_tx`（`context_fallback.py:376-406`）：

1. 从 window payload 读取 `trigger_source`（`_required_text`）
2. 若 `trigger_source == PROACTIVE`，调用 `_proactive_material_blocks_for_window` 重建 EventLog-backed frozen material view
3. 将 `material_blocks` 存入 `ActiveRecentWindowFallback.material_blocks`

`_proactive_material_blocks_for_window`（`context_fallback.py:410-456`）：
- 读取 Run → 校验 `run.input_event_id == current_input_ref`（defense-in-depth，Provider 入口已有相同校验）
- 读取 current input event → 获取 `display_text`
- 调用 `build_pre_dispatch_compact_material_view(transaction, event_log_store, run=run, current_display_text=current_display_text)` → 得到与 fallback selector 同源的 EventLog-backed material blocks
- 追加 `_current_input_material_block_for_fallback(block_id="current:{current_input_ref}", section=CURRENT_INPUT_ANCHOR, kind=CURRENT_INPUT_ANCHOR, ...)` → 匹配 fallback selector 的 current input block id 格式

**Consumer 侧** — `RunInputBuilder.build`（`run_input.py:1898-1910`）：

```python
fallback_material_blocks = (
    fallback.material_blocks                     # proactive: frozen EventLog-backed view
    if fallback.material_blocks is not None
    else build_run_input_material_blocks(...)    # reactive: ordinary material view
)
bounded_context_messages = _fallback_context_messages(
    fallback=fallback,
    material_blocks=fallback_material_blocks,
)
```

- 当 `fallback.material_blocks is not None`（proactive）→ 使用 frozen 同源 view
- 当 `fallback.material_blocks is None`（reactive / 其他非 proactive）→ 退回到 ordinary view（保持不变）

**tier4 语义保留验证**：

`_proactive_material_blocks_for_window` 重建的是完整的 `PreDispatchCompactMaterialView`，包含 historical trace/answer/evidence material blocks（与 fallback selector 运行时一致）。`_fallback_context_messages` 通过 `selected_block_ids` 过滤出 selected blocks，跳过 current input anchor。因此：

- **recent-window floor**：`selected_block_ids` 在 selection 时已由 S2 floor 算法确定，渲染时通过 `_validate_fallback_protected_groups` 二次校验 ✓
- **fallback caps**：`selected_block_ids` 在 selection 时已由 S2 caps 约束，渲染时通过 `selected_raw_turn_count` 校验 ✓
- **非 current-only**：测试 `test_pre_start_governance_compact_failure_is_attempt_free` 断言 `selected_block_ids` 包含 `"eventlog:user:event-input-run-compact-failure-old"`（historical floor block）和 `f"current:event-input-{seeded.run_id}"`（current input），且 rendered 内容包含 `"older fallback floor material that must render"` ✓

**block_id 格式一致性**：
- Fallback selector 的 `current_input_block`：block_id 格式为 `current:{current_input_ref}`（由 `build_pre_dispatch_compact_material_view` 调用链确定）
- 重建的 `_current_input_material_block_for_fallback`：block_id=`f"current:{current_input_ref}"` → **一致** ✓
- Fallback selector 的其他 blocks：block_id 格式为 `eventlog:{kind}:{event_id}` 或类似，由 `build_pre_dispatch_compact_material_view` 生成
- 重建 view 的其他 blocks：来自同一个 `build_pre_dispatch_compact_material_view` → **一致** ✓

**无退化为 current-only**：测试明确断言 historical block 被选择且被渲染 ✓。

### 2. provenance guards 的 fail-closed 状态

**结论: PASS。** S3 的所有 provenance guard 在 `_selected_material_render_view` 中保持不变（`run_input.py:2766-2818`）。唯一变化是 `material_blocks` 入参来源（frozen vs ordinary），但 guard 逻辑不变：

| Guard | 代码位置 | S5 影响 |
|-------|---------|---------|
| material block ids 唯一性 | 2780, 2831-2833 | 不变，作用于入参 material_blocks |
| selected ids 去重 | 2782-2783 | 不变 |
| selected ids 全部存在 | 2787-2788 | 不变 — block_id 格式一致性保证可找到 |
| current input ref 唯一匹配 | 2789-2792, 2849-2857 | 不变 — `current:{ref}` block 可被 `CURRENT_INPUT_ANCHOR` section + `canonical_source_refs` 匹配 |
| source refs 一致 | 2794-2795 | 不变 — 同源 view 的 source refs 与 selection 时一致 |
| fallback input digest 一致 | 2796-2801 | 不变 — `fallback_input_window` 直接从 payload 读取 |
| selected material view digest 一致 | 2803-2807 | 不变 — `selected_material_view_digest(selected_blocks)` 基于同源 blocks |
| protected group consistency | 2808-2812, 2875-2919 | 不变 — 同源 view 的 `turn_group_id` 与 selection 时一致 |

**edge case：重建 view 的 block 数量与 selection 时不同**：
- 更多 blocks → selected blocks 仍可找到（superset），digest 仍基于 selected blocks ✓
- 更少 blocks → `len(selected_blocks) != len(selected_ids)` → `HostDurableError` ✓

**edge case：`_proactive_material_blocks_for_window` 在 provider 内失败**：
- Run missing → `HostDurableError("fallback run is missing")`
- input_event_id mismatch → `HostDurableError("fallback current_input_ref mismatch")`
- current input event missing → `HostDurableError("fallback current input event is missing")`
- `build_pre_dispatch_compact_material_view` 内任何 error → 异常向上传播 → dispatch 失败 ✓

**`ActiveRecentWindowFallback.material_blocks` 校验**：
- `__post_init__` 中 `if self.material_blocks is not None: _require_block_tuple(...)` → 类型安全 ✓
- `_require_block_tuple` 校验每个元素为 `RunInputMaterialBlock` 实例 ✓

### 3. `_facts_from_accepted_event` whole-drop 修复

**结论: PASS。** 修复只 whole-drop 单个 invalid empty-evidence-labels fact candidate，不丢此前 valid facts。不改 public/durable/EventLog contract。

**修复前**（`memory.py`，旧逻辑）：
```python
if len(labels) == 0:
    return ((), tuple(diagnostics) + (diagnostic,))
```
`return` 立即退出循环，**丢弃该 event 中所有已 append 的 valid facts** + 停止处理后续 fact candidates。

**修复后**（`memory.py:1825-1832`）：
```python
if len(labels) == 0:
    diagnostics.append(diagnostic)
    continue
```
`continue` 跳过当前 invalid fact candidate，保留已累积的 valid facts，继续处理后续 candidates。

**语义正确性**：
- `_required_text_tuple` 已验证字段存在且元素均为非空文本 → `evidence_labels=[]` 是合法值（空列表），表示该 fact candidate 无证据支持
- 单个无证据 candidate 不应 invalidate 同 event 中其他有证据支持的 candidates ✓
- diagnostic 仍记录（`EVIDENCE_BACKED_FACT_CANDIDATE_INVALID`），保持可观测性 ✓

**contract 变更检查**：
- `_facts_from_accepted_event` 为模块级私有函数 → 非 public API ✓
- 返回值类型不变：`tuple[tuple[EvidenceBackedFactView, ...], tuple[MemoryDiagnostic, ...]]` ✓
- 无 durable schema / EventLog type / EventLog payload 变更 ✓
- 调用方 `project_conversation_memory_event`（`memory.py:1260-1261`）的消费语义不变：接收 `(facts, diagnostics)` tuple ✓

**测试覆盖**：`test_accepted_compact_keeps_valid_fact_before_empty_evidence_labels` 验证：
- 第一个 fact（`evidence_labels=["E1"]`）→ 保留在 `evidence_backed_facts` ✓
- 第二个 fact（`evidence_labels=[]`）→ whole-drop，不出现 ✓
- diagnostic 记录 `EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` ✓

### 4. public compact smoke 超长 current input 新预期

**结论: PASS。** 符合 `docs/host/design.md` no-truncation/no-preview 约束。

**三个 smoke 改动**：

**改动 1**：`test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence`、`test_multi_compact_public_path_keeps_memory_and_compactor_input_bounded` 改用 `_soft_threshold_prompt()`（短 input）替代 `_long_compaction_prompt()`。

- 原因：需要 compact 的测试必须使用可无损进入 `CurrentInputAnchorVNext.text` 1200-char contract 的短 input
- 测试仍覆盖原意图（compact → fact reuse / multi-compact bounded），只是 input 长度变了 ✓

**改动 2**：`test_proactive_compact_duplicate_prompt_does_not_exceed_compactor_window` → 重命名 `test_proactive_compact_duplicate_prompt_falls_back_without_lossy_anchor`。

- 旧断言：`fake_compactor.prompt_lengths == [1]`（compactor 被调用）、compact artifact 存在
- 新断言：
  - `fake_compactor.prompt_lengths == []` — **compactor 从未被调用** ✓
  - `_compact_artifact_files(...) == ()` — **无 compact artifact 写入** ✓
  - `terminal.kind is HostEventKind.SUCCEEDED` — **Run 仍成功完成**（通过 dispatch fallback） ✓
- docstring：`"超长 current input 不能无损进入 compact schema 时走 dispatch fallback"`

**设计真源对齐**：
- `docs/host/design.md` 禁止 LLM-facing current input / compact material 字段级截断、preview 或 summary 化
- `CurrentInputAnchorVNext.text` contract 为 1200 字符
- 超长 current input → 不能无损 compact → 不生成 compact proposal → 不写 compact artifact → dispatch fallback ✓

**结果**：`tests/host/test_public_compact_smoke.py` 为 `11 passed, 1 skipped`（skipped = no continuous session-id smoke）。

### 5. README decision 与 residual reconciliation

**结论: PASS。** 充分且准确。

**README decision**：
- `dayu/host/README.md`：不更新。S5 是内部 selected-id 同源修正 + memory projection invalid candidate 处理，不改变 Host public API、装配方式、开发手册入口或用户工作流。
- `tests/README.md`：不更新。test 改动不改变测试目录结构、运行方式或维护规则。
- 判断符合 CLAUDE.md 的 README 更新触发规则。✓

**Residual reconciliation**：

| Residual | 状态 | 直接证据 |
|----------|------|----------|
| `WU-CLI-ACTIVITY-01-PR-R1` | 已关闭 | 两个 public continuity smoke 通过：`2 passed in 0.41s` |
| `WU-CM-12-S1-R1`（fact whole-drop） | 已关闭 | `_facts_from_accepted_event` 修复 + `test_accepted_compact_keeps_valid_fact_before_empty_evidence_labels` |
| `WU-CM-12-S4-R1`（reactive recovery） | deferred / intentional non-goal | 改动在 `dispatch.py` proactive path；reactive path 需独立 Engine ingest recovery 流程改造，超出 S5 scope |
| `CurrentInputAnchorVNext.text` 1200-char 上限 | intentional design constraint | 超长 input → 不 compact → dispatch fallback；需 schema 变更才能扩大，当前 scope 不包含 schema 变更 |

**S5 artifact 中的 residual risk 准确**：
- Reactive tier1-3 compact recovery 仍需 follow-up
- `ConversationCompactInputVNext` 不能表达 1200+ 字符的 current input

## 验证结果

| 验证项 | 结果 |
|--------|------|
| `pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py -q` | **312 passed in 2.31s** |
| `pytest tests/host/test_memory_projection.py tests/host/test_dispatch_scheduler.py::test_pre_start_governance_compact_failure_is_attempt_free tests/host/test_dispatch_scheduler.py::test_reactive_compact_failure_fallback_dispatch_uses_failed_view tests/host/test_dispatch_scheduler.py::test_reactive_fallback_decision_uses_memory_policy_caps tests/host/test_public_compact_smoke.py -q` | **51 passed, 1 skipped in 0.99s** |
| `pyright dayu/host/context_fallback.py dayu/host/run_input.py dayu/host/memory.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_projection.py tests/host/test_public_compact_smoke.py` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | **无 whitespace 错误** |

### Architecture / Public API Drift 检查

- **`ActiveRecentWindowFallback` 新增字段**：`material_blocks: tuple[RunInputMaterialBlock, ...] \| None = None`。默认 `None` 保持向后兼容；`__post_init__` 中 `_require_block_tuple` 类型校验。
- **`EventLogContextFallbackProvider._load_context_fallback_tx` 新增逻辑**：仅在 `trigger_source == PROACTIVE` 时重建 material view；非 proactive 路径 behavior unchanged。
- **新增 `_proactive_material_blocks_for_window`**：模块级私有函数，仅被 Provider 内部调用。不暴露为 public API。
- **新增 `_current_input_material_block_for_fallback`**：模块级私有函数，构造 current input block。仅被 `_proactive_material_blocks_for_window` 调用。
- **`build_pre_dispatch_compact_material_view` 的 import**：已在 S1-S4 中存在于 `compact_material.__all__`，S5 首次在 `context_fallback.py` 中使用。方向正确（`context_fallback` → `compact_material`，Host 层内依赖）。
- **`read_run_by_id` import**：已在 `durable.state` 模块中定义，S5 首次在 `context_fallback.py` 中使用。方向正确（`context_fallback` → `durable.state`，Host 层内依赖）。
- **无新 EventLog type / durable schema / public API / Engine role / policy field 变更。**
- **`_facts_from_accepted_event` 变更**：return-early → continue。返回值类型不变，调用方消费语义不变。

## Open Questions

无。

## Residual Risk

- **Reactive tier1-3 recovery 仍需 follow-up**：S5 artifact 明确记录为 intentional non-goal。当前修复只确保 proactive fallback 能正确渲染 selected blocks，不扩展 reactive 路径。
- **`_proactive_material_blocks_for_window` 的 `build_pre_dispatch_compact_material_view` 调用在 provider 的 read transaction 内执行**：该函数读取 EventLog 并构建 material view。若 EventLog 规模极大，可能增加 read transaction 耗时。当前 design 未对此做预算约束，但 proactive path 在 dispatch 前执行（非用户等待路径），实际影响有限。
- **`ConversationCompactInputVNext` 1200-char current input anchor 上限**：无计划在本 WU 中扩大。超长 input 走 dispatch fallback 是正确的 fail-open 行为（Run 仍成功），但失去了 compact 带来的 context 压缩收益。

## Conclusion

**PASS** — S5 修复正确、完整，无 correctness/stability/maintainability findings。

- proactive fallback selected-id 同源修复通过 Provider 重建 EventLog-backed frozen material view 实现，Consumer 优先使用同源 view。tier4 recent-window/floor/caps 语义完整保留（historical floor block 被选择且被渲染）。
- S3 provenance guards（selected ids、source refs、digest、protected group consistency、current input ref）在重建 view 上全部 fail closed，无退化。
- `_facts_from_accepted_event` whole-drop 修复只丢弃单个 invalid empty-evidence-labels candidate，保留此前 valid facts。无 public/durable/EventLog contract 变更。
- public compact smoke 超长 current input 新预期符合 `docs/host/design.md` no-truncation/no-preview：不调用 compactor、不写 compact artifact、走 dispatch fallback。
- README decision 和 residual reconciliation 充分且一致。
