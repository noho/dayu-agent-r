# WU-PROJ-01 Slice 2 Re-Review — AgentDS

## 元数据

- Reviewer：AgentDS
- Work unit：WU-PROJ-01
- Slice：Slice 2（Proactive Context Governance 使用同源 material view）
- Gate：re-review（fix gate 后）
- 日期：2026-06-11
- Fix report：`docs/reviews/wu-proj-01-slice2-fix-codex.md`
- Controller adjudication：`docs/reviews/wu-proj-01-slice2-code-review-controller-adjudication.md`
- Previous DS review：`docs/reviews/wu-proj-01-slice2-code-review-ds.md`
- Previous MiMo review：`docs/reviews/wu-proj-01-slice2-code-review-mimo.md`

## Re-Review Verdict

**PASS** — 2 个 accepted fix items 已正确修复，无新增 correctness / type / test / architecture 问题。

## Fixed Findings 逐项复验

### DS-S2-L2：`_proactive_fallback_material_blocks` current input 追加逻辑边界测试

**状态**：✅ Fixed

**验证证据**：

新测试 `test_proactive_fallback_material_blocks_append_current_input_once`（`test_dispatch_scheduler.py:3889-3944`）：

1. **直接断言 material view delta 不含 current input**（lines 3922-3929）：
   - `assert all(run.input_event_id not in block.canonical_source_refs for block in material_view.material_blocks)` — 验证 current input 的 `canonical_source_refs` 不在任何 material block 中。
   - `assert all(block.event_sequence != run.input_event_sequence for block in material_view.material_blocks)` — 验证没有任何 block 的 `event_sequence` 等于 current input 的 event sequence。
   - 同时在 lines 3917-3921 验证 old delta block 确实出现在 material_blocks 中（确保 view 非空，断言有鉴别力）。

2. **断言 fallback 追加后 current input anchor 只出现一次**（lines 3935-3944）：
   - 筛选 `kind is CURRENT_INPUT_ANCHOR` 且 `canonical_source_refs` 包含 `run.input_event_id` 的 block。
   - `assert len(current_input_blocks) == 1` — 恰好一个，没有重复。
   - 验证该 block 的 `text` 和 `event_sequence` 与 current input 一致。

测试正确使用生产路径 `build_pre_dispatch_compact_material_view`（通过 test helper `_pre_dispatch_material_view_for_run`）构造同源 material view，然后用 public API `_proactive_fallback_material_blocks` 追加 current input。断言覆盖了 controller adjudication 的两个要求：delta 不含 current input、追加后不重复。

### MiMo INFO-3：`test_multi_turn_proactive_compact_feeds_subsequent_run_input` 阈值注释

**状态**：✅ Fixed

**验证证据**：

测试 `test_multi_turn_proactive_compact_feeds_subsequent_run_input`（`test_dispatch_scheduler.py:4642-4716`）在 `_soft_compact_policy()` 调用处新增注释（lines 4654-4658）：

```python
context_budget_policy=_soft_compact_policy(
    # 同源 material view 估算包含 previous view、delta 与 current input；
    # 这里需超过 soft threshold 且低于 hard threshold，目标仍是 proactive lifecycle。
    context_window_size=200,
    soft_threshold_tokens=60,
    hard_threshold_tokens=160,
),
```

注释准确描述了：
- 同源 material view 的三个估算组件（previous view、delta、current input）。
- 阈值调整的原因：需超过 soft threshold（触发 proactive compact）且低于 hard threshold（避免 fail-closed）。
- 测试目标不变：仍是验证 proactive compact lifecycle。

注释不掩盖 hard-threshold 行为——它明确说明需要"低于 hard threshold"，与 hard-threshold precondition fail-closed 语义一致（见 `dispatch.py:1052-1085`）。

## Allowed Files 检查

Controller adjudication 指定 allowed files：
- `tests/host/test_dispatch_scheduler.py` ✅
- `docs/reviews/wu-proj-01-slice2-fix-codex.md` ✅

当前 working tree 中其他文件的修改（`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`tests/host/test_compact_material.py`、`docs/host/issues-implementation-control.md`）均来自原始 Slice 2 implementation，非本次 fix 引入。Fix 未新增或修改 production code、design docs、control doc、README 或 GitHub issue。

## Validation 复验

独立运行验证：

```text
$ pytest tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive" -q
19 passed, 48 deselected in 0.63s

$ pyright
0 errors, 0 warnings, 0 informations
```

与 Fix Report 声明的 19 passed、0 errors 一致。新测试 `test_proactive_fallback_material_blocks_append_current_input_once` 被 `proactive` 关键词匹配并执行。

## 无新增 Findings

对新测试的 adversarial 检查：

| 检查维度 | 结果 |
|---|---|
| 测试逻辑正确性 | ✅ — material view delta 不含 current input 的断言使用两种独立方式交叉验证（canonical_source_refs + event_sequence） |
| 测试不依赖实现细节 | ✅ — 通过 public API `build_pre_dispatch_compact_material_view` + `_proactive_fallback_material_blocks` 构造输入和验证输出 |
| 注释准确性 | ✅ — 注释描述的估算组成（previous view + delta + current input）与 `_pre_dispatch_budget_fragments` 实现一致 |
| 类型安全 | ✅ — pyright 0 errors，新测试使用完整类型注解的 fixture |
| 测试隔离 | ✅ — 新测试使用独立 tmp_path，不依赖全局状态或测试顺序 |
| 架构合规 | ✅ — 未引入跨层依赖或反向依赖 |

## Blocking Open Questions

无。

## Residual Risks

- 同 DS-S2 original review 的 deferred findings（DS-S2-L1、DS-S2-L3），按 controller adjudication 留给后续 owner。
- MiMo INFO-1（reactive budget estimate 仍用单 fragment）、INFO-2（`_MinimalSummaryCompactor` 假设 trace 非空）仍为 deferred/rejected，不在本轮 scope。
- 本轮只修了 accepted test/comment items，未改 production code。如 controller adjudication 所述，material source failure exception taxonomy、reactive diagnostic event、reactive budget estimate 等 deferred findings 由 Slice 3 diagnostic / reactive deep hardening 后续处理。
