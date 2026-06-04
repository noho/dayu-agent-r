# WU-CM-01 Slice C Fix Re-Review - MiMo

## Gate

- Work unit: WU-CM-01
- Gate: Slice C fix re-review
- Reviewer: mimo
- Artifact path: `docs/reviews/wu-cm-01-slice-c-rereview-mimo.md`
- Scope source: controller adjudication accepted findings F-1, F-2, F-3
- Fix artifact: `docs/reviews/wu-cm-01-slice-c-fix-codex.md`

## Verdict

**PASS.** 三个 accepted findings 均已关闭，无新增 blocking finding。fix 范围正确，未触及 deferred / rejected 项，未引入新 policy / schema / README 问题。

## Findings

无新增 finding。

## Accepted Finding Verification

### F-1: `context_window_size` 参数被 Service assembly 丢弃

**Status: CLOSED.**

**Production fix 验证:**

- `dayu/service/host_assembly.py:984-1021` `_memory_projection_policy_from_config` 函数签名接收 `context_window_size: int` 参数。
- Line 997: `context_window_size=context_window_size` 使用函数参数（来自 `ordinary_selection.model.context_window_tokens`，line 499），而非 `policy.context_window_size`。
- 与 `docs/host/design.md:2879` "Service / composition root 从 effective model config 读取 context_window_tokens，作为 MemoryProjectionPolicy.context_window_size 直接传入 typed policy" 一致。

**Test 验证:**

- `tests/service/test_host_assembly.py:644-701` `test_memory_projection_context_window_uses_effective_model_window`。
- 测试构造 profile policy `context_window_size=262144`（execution_profiles.json default），同时使用 effective model `deepseek-v4-flash` 的 `context_window_tokens=1048576`。
- 断言 `result.options.memory_projection_policy.context_window_size == 1048576` — 确认 model-derived 参数覆盖 profile config 值。
- 测试同时断言 `config.models.models[_MODEL_ID].context_window_tokens == 1048576` 与 `config.execution_profiles...memory_projection_policy.context_window_size == 262144`，确认两个值不同以覆盖 diverge 场景。

### F-2: `DuplicateMaterialSectionOwnerError` dedicated 覆盖丢失

**Status: CLOSED.**

**测试验证:**

- `tests/host/test_compact_material.py:203-249` `test_duplicate_section_owner_raises_for_vnext_previous_and_trace_material`。
- 测试构造 `ConversationMemorySnapshotVNext`，在 `session_summary_memory` 中填充 `"duplicate readable content"` 文本与 `source_refs=("event:summary",)`。
- 构造 `trace_material` block，text 为相同 `"duplicate readable content"`，`canonical_source_refs=("snapshot-duplicate-owner",)`。
- 通过 `build_compact_material_pack` public builder 路径调用，断言抛出 `DuplicateMaterialSectionOwnerError`。
- 覆盖路径：同一 canonical content（相同可读文本 + 同一 snapshot digest）进入 `previous_view`（session_summary）与 `trace_material` 两个 LLM-facing section 时触发 duplicate guard。

**保留测试:**

- `tests/host/test_compact_material.py:164` `test_vnext_snapshot_does_not_bridge_old_goal_into_previous_view` 仍存在，no-old-goal bridge 覆盖未丢失。

### F-3: vNext budget limiting 缺少直接单测

**Status: CLOSED.**

**测试验证:**

- `tests/host/test_memory_projection.py:317-348` `test_accepted_compact_limits_evidence_facts_and_records_budget_diagnostic`。
- 把 `evidence_fact_item_cap` 降为 1（`replace(_policy(), evidence_fact_item_cap=1, evidence_fact_floor=0)`）。
- 输入两个 accepted compact fact candidates: `"旧 fact 应被截断。"` 和 `"新 fact 应被保留。"`。
- 断言 `evidence_backed_facts` 只保留最新 fact（`"新 fact 应被保留。"`），旧 fact 被截断。
- 断言 `MemoryDiagnosticReason.BUDGET_LIMIT_REACHED` 出现在 `snapshot.diagnostics` 中。

## Deferred / Rejected Findings 确认

fix artifact 明确声明 "未处理 rejected / deferred cleanup"。验证：

- **Deferred: compact artifact message reader** — fix 未修改 `dayu/host/run_input.py` 中旧 payload reader。维持 deferred-with-owner 状态。
- **Rejected: `_memory_messages` `del policy` cleanup** — fix 未触及。维持 rejected-with-reason。
- **Rejected: `_snapshot_with_goal` helper API cleanup** — fix 未修改 helper。维持 rejected-with-reason。
- **Rejected: old schema_version explicit rejection message** — fix 未修改 schema 读取。维持 rejected-with-reason。

## Scope 确认

Changed files（fix scope 内）:

- `dayu/service/host_assembly.py` — F-1 production fix
- `tests/service/test_host_assembly.py` — F-1 test
- `tests/host/test_compact_material.py` — F-2 test
- `tests/host/test_memory_projection.py` — F-3 test

fix 未引入新 policy / schema / README 变更。未修改 `MemoryProjectionPolicy` 字段集合、durable schema CHECK 约束、或任何 README。

## Validation

```
$ source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/host/test_compact_material.py tests/host/test_memory_projection.py -q
58 passed in 0.32s

$ source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

## Completion

controller adjudication 中三个 accepted findings 均已关闭，无新增 blocking finding。fix 范围正确，未扩大到 deferred / rejected 项。re-review verdict: **pass**。
