# Code Review

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `c824ea9038ecb4084621117c6806764cd63e9a20`
- Output file: `docs/reviews/pr-190-f11-f12-s4-production-mimo-review-20260805.md`
- Included scope: `dayu/host/compact_pipeline.py`、`dayu/host/context_fallback.py`、`tests/host/test_dispatch_scheduler.py`
- Excluded scope: 其他未修改文件
- Parallel review coverage: 无

## Findings

### 001-未修复-[高]-compact_pipeline 跨模块导入 context_fallback 私有 helper

- **入口/函数**: `_fallback_material_blocks`
- **文件(行号)**: `dayu/host/compact_pipeline.py:71`
- **输入场景**: proactive fallback material block 构造
- **实际分支**: 导入 `_fallback_current_input_material_block`（私有函数）
- **预期行为**: 模块间应通过公共接口交互，不应导入私有 helper
- **实际行为**: `compact_pipeline.py` 直接导入 `context_fallback._fallback_current_input_material_block`
- **直接证据**: `dayu/host/compact_pipeline.py:71` 显示 `from dayu.host.context_fallback import ... _fallback_current_input_material_block`
- **影响**: 违反模块边界，增加耦合，未来修改 `_fallback_current_input_material_block` 签名时需同步修改两个模块
- **建议改法和验证点**:
  1. 将 `_fallback_current_input_material_block` 提升为公共函数（加入 `__all__`），或
  2. 让 `compact_pipeline.py` 直接使用 `run_input_material_block` 构造 block，或
  3. 在 `context_fallback` 中提供公共封装函数
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### 002-未修复-[中]-proactive 与 reactive fallback 使用不同 material block 构造路径

- **入口/函数**: `_fallback_material_blocks`（proactive） vs `_fallback_material_blocks_for_window`（reactive）
- **文件(行号)**: `dayu/host/compact_pipeline.py:1114` vs `dayu/host/context_fallback.py:443`
- **输入场景**: proactive fallback 与 reactive fallback
- **实际分支**: proactive 使用 `_fallback_material_blocks`，reactive 使用 `_fallback_material_blocks_for_window`
- **预期行为**: 两者应使用完全相同的 material block 构造逻辑
- **实际行为**: 两者都调用 `_fallback_current_input_material_block`，但 `_fallback_material_blocks` 直接使用 `source_snapshot`，而 `_fallback_material_blocks_for_window` 从 EventLog 重建
- **直接证据**:
  - `compact_pipeline.py:1123` 调用 `_fallback_current_input_material_block`
  - `context_fallback.py:482` 调用 `_fallback_current_input_material_block`
- **影响**: 如果 `_fallback_current_input_material_block` 的实现发生变化，两者会同步变化，但构造来源不同可能导致边界情况不一致
- **建议改法和验证点**: 确认两种路径在边界情况下行为一致（如空文本、特殊字符）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 003-未修复-[低]-测试使用 `_AlwaysQualityRejectingCompactor` 可能掩盖真实 compactor 行为

- **入口/函数**: `test_proactive_exhausted_fallback_normalizes_current_input_for_replay`
- **文件(行号)**: `tests/host/test_dispatch_scheduler.py:8289`
- **输入场景**: proactive fallback 测试
- **实际分支**: 使用 `_AlwaysQualityRejectingCompactor` 强制 rejection
- **预期行为**: 测试应覆盖真实 compactor 行为
- **实际行为**: 测试使用 fake compactor，可能掩盖真实 compactor 的边界行为
- **直接证据**: `_AlwaysQualityRejectingCompactor` 总是返回 rejection
- **影响**: 测试不覆盖真实 compactor 的质量检查逻辑
- **建议改法和验证点**: 考虑添加使用真实 compactor 的测试（如果可行）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

1. **跨模块私有导入**: `compact_pipeline.py` 导入 `context_fallback` 的私有 helper，增加模块耦合
2. **测试覆盖**: 测试使用 fake compactor，可能不覆盖真实 compactor 的边界行为
3. **whitespace 折叠**: 测试只覆盖了常规空白字符，未覆盖 non-breaking space 等特殊空白字符

## Validation

- `pytest tests/host/test_dispatch_scheduler.py::test_proactive_exhausted_fallback_normalizes_current_input_for_replay -xvs`: 1 passed
- `pytest tests/host/test_dispatch_scheduler.py::test_reactive_compact_failure_fallback_dispatch_uses_failed_view -xvs`: 1 passed
- `pyright dayu/host/compact_pipeline.py dayu/host/context_fallback.py tests/host/test_dispatch_scheduler.py`: 0 errors, 0 warnings, 0 informations
- `git diff --check`: 通过

## Semantic Ownership Analysis

### S4-001 修复的 semantic owner 判定

S4-001 的 root cause 是 fallback current-input material block 的 construction/digest 不同源：
- **selection 阶段**: `compact_pipeline._fallback_material_blocks` 使用 raw `source_snapshot.current_input_text` 构造 block
- **replay 阶段**: `context_fallback._fallback_material_blocks_for_window` 使用 `run_input_material_block`（会规范化文本）

修复后的 semantic owner 判定：
1. `dayu.host.compact_material.run_input_material_block` 唯一拥有 material 文本规范化、`size_units` 与 `content_digest` 派生
2. `dayu.host.context_fallback._fallback_current_input_material_block` 是 fallback current-input block 的构造 owner
3. `dayu.host.compact_pipeline._fallback_material_blocks` 是 selection 的直接上游 producer，原实现绕过 material owner

修复正确地将 `_fallback_material_blocks` 改为使用 `_fallback_current_input_material_block`，从而实现同源。

### proactive/reactive/recovery/protected-recent 同源性

修复后，proactive 和 reactive fallback 都使用 `_fallback_current_input_material_block` 构造 current-input block：
- **proactive**: `compact_pipeline._fallback_material_blocks` → `_fallback_current_input_material_block`
- **reactive**: `context_fallback._fallback_material_blocks_for_window` → `_fallback_current_input_material_block`

两者都委托 `run_input_material_block` 进行文本规范化和 digest 计算，因此是同源的。

### policy/caps/public surface/terminal/schema 变更检查

- **fallback policy**: 未改变
- **caps**: 未改变
- **public surface**: 未改变（`__all__` 未变）
- **terminal permit**: 未改变
- **Run / Attempt state machine**: 未改变
- **schema**: 未改变
- **Memory**: 未改变
- **harness/renderer**: 未改变

### 测试证明分析

**test_proactive_exhausted_fallback_normalizes_current_input_for_replay**:
- ✅ whitespace digest: `assert expected_current_block.text != current_input`（证明规范化）
- ✅ 唯一 failed terminal: `assert _event_count(store.transaction_runner, CONTEXT_COMPACTION_FAILED) == 1`
- ✅ bounded fallback dispatch: `assert payload["fallback_action"] == "dispatch"`
- ✅ manifest: `assert fallback_source.manifest.source_refs.context_fallback_decision_ref == expected_fallback_ref`
- ✅ cleanup: `assert scheduler._active_tasks == set()`
- ✅ 无 fixture compensation: 使用 `_seed_accepted_run_with_compactable_history` 和 `_AlwaysQualityRejectingCompactor`，未为 fallback 写 fixture 补偿

**test_reactive_compact_failure_fallback_dispatch_uses_failed_view**:
- ✅ whitespace digest: `assert expected_current_block.text != current_input`
- ✅ protected recent replay: `assert "recent protected\nreplay material" in second_contents`
- ✅ recovery manifest: `assert recovery_source.manifest.source_refs.context_fallback_decision_ref == expected_fallback_ref`
- ✅ source Attempt failed: `assert first_attempt.status is AttemptStatus.FAILED`
- ✅ recovery Attempt succeeded: `assert recovery_attempt.status is AttemptStatus.SUCCEEDED`
- ✅ Run succeeded: `assert _run_status(store.transaction_runner, seeded.run_id) is RunStatus.SUCCEEDED`
- ✅ task cleanup: `assert scheduler._active_tasks == set()`

### Adversarial Counterexamples

1. **Non-breaking space (U+00A0)**: `normalized_material_text` 使用 `split()`，按 Python 文档会处理 Unicode 空白字符，包括 U+00A0。测试未覆盖，但逻辑应正确。
2. **空文本**: `normalized_material_text` 会抛出 `ValueError`，但 `current_input_text` 不应为空。
3. **特殊字符**: `block_id` 使用 `f"current:{current_input_ref}"`，应能处理特殊字符。
4. **超长文本**: 未测试，但 `run_input_material_block` 没有长度限制。

## Closeout

PR 190 F11/F12 S4.1 production fix 的代码审查完成。主要发现是 `compact_pipeline.py` 跨模块导入 `context_fallback` 的私有 helper，违反模块边界。测试覆盖了 whitespace digest、唯一 failed terminal、bounded fallback dispatch、manifest 与 cleanup，但使用 fake compactor。修复风险低，建议将私有 helper 提升为公共函数或重构为使用公共接口。Semantic owner 判定正确，proactive/reactive/recovery/protected-recent 同源，未改变 policy/caps/public surface/terminal/schema。
