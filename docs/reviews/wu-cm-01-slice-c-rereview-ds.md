# WU-CM-01 Slice C Fix Re-Review

## Gate

- Work unit: WU-CM-01 Conversation Memory
- Gate: Slice C fix re-review
- Reviewer: ds (deepreview stance)
- Date: 2026-06-04
- Scope: controller accepted findings F-1, F-2, F-3 fix verification
- Fix artifact: `docs/reviews/wu-cm-01-slice-c-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-cm-01-slice-c-code-review-controller-adjudication.md`

## Verdict

**PASS.** 三个 accepted findings 均已正确修复，测试覆盖到位，deferred/rejected items 未被误改，无新增 policy/schema/README 问题。pytest 58 passed, pyright 0 errors.

---

## Accepted Findings — 逐项验证

### F-1 [BLOCKER] context_window_size 参数被 Service assembly 丢弃 — 已关闭

- **严重性**: blocking
- **状态**: 已修复，验证通过

**Production 修复** (`dayu/service/host_assembly.py:997`):

```python
context_window_size=context_window_size,
```

函数参数（来自 effective model `context_window_tokens`）现正确传入 `MemoryProjectionPolicy`，不再使用 `policy.context_window_size`。与 `docs/host/design.md:95` 要求一致。

**测试覆盖** (`tests/service/test_host_assembly.py:644`):

`test_memory_projection_context_window_uses_effective_model_window` 构造：
- profile policy `context_window_size=262144`
- effective model `deepseek-v4-flash` 的 `context_window_tokens=1048576`

断言 Host `memory_projection_policy.context_window_size == 1048576`，确认 effective model 值生效。

**验证**: 测试通过。

---

### F-2 [MEDIUM] DuplicateMaterialSectionOwnerError dedicated 覆盖 — 已关闭

- **严重性**: medium test coverage
- **状态**: 已修复，验证通过

**测试覆盖** (`tests/host/test_compact_material.py:203`):

`test_duplicate_section_owner_raises_for_vnext_previous_and_trace_material`：
- 构造 snapshot，其 `session_summary_memory` 含 `summary_text="duplicate readable content"`
- 构造 trace material block 含相同 text，且 `canonical_source_refs=("snapshot-duplicate-owner",)` 与 snapshot 的 previous block `canonical_source_refs` 一致
- 两者进入不同 section（PREVIOUS_COMPACTED_VIEW vs TRACE_MATERIAL），断言 `build_compact_material_pack` raise `DuplicateMaterialSectionOwnerError`

**旧测试保留**: `test_vnext_snapshot_does_not_bridge_old_goal_into_previous_view` (line 164) 未被删除，no-old-goal bridge 覆盖完整。

**验证**: 测试通过。

---

### F-3 [MEDIUM] vNext budget limiting focused 覆盖 — 已关闭

- **严重性**: medium test coverage
- **状态**: 已修复，验证通过

**测试覆盖** (`tests/host/test_memory_projection.py:317`):

`test_accepted_compact_limits_evidence_facts_and_records_budget_diagnostic`：
- `evidence_fact_item_cap=1`，输入两个 accepted compact fact candidates
- 断言只保留最新 fact (`"新 fact 应被保留。"`)，旧 fact 被截断
- 断言 snapshot diagnostics 含 `MemoryDiagnosticReason.BUDGET_LIMIT_REACHED`

**验证**: 测试通过。

---

## Deferred / Rejected Items — 确认未修改

| Finding | 来源 | 裁决 | 状态 |
|---------|------|------|------|
| compact artifact message path 旧 payload reader | MiMo Advisory-1 | deferred-with-owner | 未修改，`_memory_messages` / `_compact_artifact_message_content` 代码路径维持原状 |
| `_memory_messages` `del policy` cleanup | DS F-3 | rejected | 未修改，`run_input.py:1966` 仍保留 `del policy` |
| `_snapshot_with_goal` helper API cleanup | DS F-4 | rejected | 未修改，仍接受 `current_goal` 参数并 `del current_goal` |
| old schema_version explicit rejection message | DS F-5 | rejected | 未添加 |

---

## 新增问题检查

- **Policy**: 无新增 policy 字段。`_empty_snapshot` / `_snapshot_with_goal` 返回类型从 `ConversationMemorySnapshot` 改为 `ConversationMemorySnapshotVNext` 是测试 fixture 的 vNext 迁移，符合 Slice C 设计方向。
- **Schema**: 无 durable schema 变更。
- **README**: 无 README 修改。
- **类型**: pyright 0 errors, 0 warnings。

---

## 验证结果

```text
source .venv/bin/activate
pytest tests/service/test_host_assembly.py tests/host/test_compact_material.py tests/host/test_memory_projection.py -q
→ 58 passed in 0.32s

python -m pyright dayu/ tests/ utils/
→ 0 errors, 0 warnings, 0 informations
```

---

## Residual Risk

- 无。三个 accepted findings 均已关闭，deferred/rejected items 维持 controller 裁决状态，无新增 blocking finding。
