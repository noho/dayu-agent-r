# Code Review — AgentDS Independent Re-review (S4.1 Fix)

## Scope

- Mode: current changes (working tree, uncommitted)
- Branch: `codex/interactive-oracle`
- Base: `c824ea9038ecb4084621117c6806764cd63e9a20` (= HEAD)
- Output file: `docs/reviews/pr-190-f11-f12-s4-production-ds-rereview-20260805.md`
- Inputs:
  - `docs/reviews/pr-190-f11-f12-s4-production-review-adjudication-20260805.md`
  - `docs/reviews/pr-190-f11-f12-s4-production-fix-20260805.md`
  - `docs/reviews/pr-190-f11-f12-s4-production-ds-review-20260805.md`
- Included scope:
  - `dayu/host/compact_pipeline.py` — `_fallback_material_blocks` 改为直接调用 `run_input_material_block`
  - `dayu/host/context_fallback.py` — 删除私有 helper、统一 PROACTIVE/REACTIVE durable load、更新 docstring、新增 fail-closed gate
  - `tests/host/test_dispatch_scheduler.py` — 两条新 owner test 的完整 state-machine assertions
  - `tests/host/test_compact_pipeline.py` — 新增 pure dataclass equality 断言
  - 沿 selection → durable write → durable read → replay 全链路逐行走读
- Excluded scope: baseline 以前的 PR 190 已接受提交、harness/oracle/scenario、旧 review/evidence、真实 provider evidence 重跑、S5 registry/PR body
- Parallel review coverage: 无。主 reviewer 独立完成全链路走读与逐项裁决验证。

## Re-review 目标

本 re-review 逐项验证 production adjudication 的 fix acceptance checklist（5 项）与分类处置：

1. 原 DS Finding 1（跨模块私有 helper 导入）已关闭
2. 两个 producer 直接使用 `compact_material.run_input_material_block`，无新 public surface/wrapper
3. Owner test 对两条路径的 fallback current-input block construction 等价作直接断言
4. `ActiveRecentWindowFallback.material_blocks` docstring 已修正
5. 删除 helper 后未重新产生 id/section/kind drift 或重复 owner；RunInput None residual 仍无真实 production 可达证据

## Independent Validation

以下验证由 AgentDS reviewer 独立执行：

- 定向 owner tests（3 条）：`3 passed`
  - `test_proactive_exhausted_fallback_normalizes_current_input_for_replay`
  - `test_reactive_compact_failure_fallback_dispatch_uses_failed_view`
  - `test_fallback_decision_input_dispatch_and_fail_closed`
- 受影响 Host test files（6 文件）：`409 passed, 1 skipped`
- pyright（变更文件）：`0 errors, 0 warnings, 0 informations`
- `git diff --check`：通过
- 私有 helper 全仓搜索：`_fallback_current_input_material_block`、`_current_input_material_block_for_fallback` 均无匹配

## Findings — 逐项裁决验证

### 1-PASS-DS Finding 1 已关闭：跨模块私有 helper 导入已消除

- **原 Finding**: `compact_pipeline._fallback_material_blocks` 私有导入 `context_fallback._fallback_current_input_material_block`（DS review Finding 1，severity 中）
- **Adjudication**: 接受。修复必须复用 `compact_material.run_input_material_block`，消除跨模块私有依赖，不扩张 package/public export
- **当前状态**:
  - `context_fallback._current_input_material_block_for_fallback`（原 fallback replay 侧私有 helper）已删除，调用内联至 `_fallback_material_blocks_for_window:482`，直接调用 `run_input_material_block`
  - `compact_pipeline._fallback_material_blocks:1123` 直接从 `compact_material` 导入并调用 `run_input_material_block`
  - 全仓搜索确认：`_fallback_current_input_material_block`、`_current_input_material_block_for_fallback` 均无匹配
  - `__all__` 两文件均无变更（`context_fallback.py:1018`、`compact_pipeline.py:1282`）
- **直接证据**:
  - `compact_pipeline.py:32`: `from dayu.host.compact_material import (..., run_input_material_block, ...)`
  - `compact_pipeline.py:1123-1130`: `current = run_input_material_block(block_id=..., section=..., kind=..., text=..., canonical_source_refs=..., event_sequence=...)`
  - `context_fallback.py:21`: `from dayu.host.compact_material import (..., run_input_material_block, ...)`
  - `context_fallback.py:482-489`: `run_input_material_block(block_id=..., section=..., kind=..., text=..., canonical_source_refs=..., event_sequence=...)`
- **结论**: PASS。两个 producer 均直接从 `compact_material` 公共模块导入并调用公开 owner `run_input_material_block`，无私有命名跨模块导入、无新增 wrapper、无新增 re-export、无 `__all__` 扩张

### 2-PASS-两个 producer 均直接使用 run_input_material_block，无新 public surface

- **Adjudication 要求**: 两个 producer 直接委托 `compact_material.run_input_material_block`，不新增 compatibility wrapper、re-export 或新 public surface
- **当前状态**:
  - Producer 1（selection，`compact_pipeline._fallback_material_blocks:1123`）: 直接调用 `run_input_material_block`
  - Producer 2（replay，`context_fallback._fallback_material_blocks_for_window:482`）: 直接调用 `run_input_material_block`
  - 无中间 wrapper 函数
  - `__all__` 两文件均无变更
  - 无新增公开符号
- **直接证据**:
  - `grep -n "run_input_material_block"` 在 `context_fallback.py` 和 `compact_pipeline.py` 中仅命中 import 行和直接调用行——无 wrapper 定义
  - `git diff HEAD -- dayu/host/context_fallback.py | grep "__all__"` 无输出
  - `git diff HEAD -- dayu/host/compact_pipeline.py | grep "__all__"` 无输出
- **结论**: PASS

### 3-PASS-Docstring 已修正

- **原 Finding**: `ActiveRecentWindowFallback.material_blocks` docstring 写"仅 proactive ... 填充"与当前 proactive/reactive 均填充的事实冲突
- **Adjudication**: 接受（低），只更新 owner docstring
- **当前状态**: `context_fallback.py:243-244`
  ```
  :param material_blocks: 与 selected ids 同源的 frozen material view；valid proactive
      或 reactive durable loader 均从 EventLog-backed source 重建并填充。
  ```
- **直接证据**: `context_fallback.py:243-244`
- **结论**: PASS

### 4-PASS-Pure dataclass equality test 验证 selection 侧 block construction 等价

- **Adjudication 要求**: owner test 对两条路径的 fallback current-input block construction 等价作直接断言
- **当前状态**: `test_fallback_decision_input_dispatch_and_fail_closed`（`test_compact_pipeline.py:844`）:
  - 输入含连续空白的文本 `"  current   user input\n\nwith   preserved line  "`
  - 通过 `build_fallback_decision_input` → `_fallback_material_blocks` → `run_input_material_block` 构造 selection block
  - 独立构造 `expected_current` 通过相同的 `run_input_material_block(...)` 参数
  - `assert selected_current == expected_current` —— `RunInputMaterialBlock` 为 `@dataclass(frozen=True, slots=True)`（`compact_material.py:180`），`__eq__` 比较全部字段（block_id、section、kind、text、size_units、content_digest、canonical_source_refs、event_sequence 等）
- **直接证据**:
  - `test_compact_pipeline.py:875-884`: `expected_current = run_input_material_block(...)` + `assert selected_current == expected_current`
  - `compact_material.py:180`: `@dataclass(frozen=True, slots=True)` 保证全字段 `__eq__`
- **结论**: PASS。此断言等价于验证 selection 侧 block 的所有派生字段（text、size_units、content_digest）与独立构造的 reference block 完全一致，防止未来 block id/section/kind 漂移

### 5-PASS-Proactive full state-machine assertions

- **Adjudication 要求**: 重跑两条回归、受影响 Host tests
- **当前状态**: `test_proactive_exhausted_fallback_normalizes_current_input_for_replay`（`test_dispatch_scheduler.py:8277`）:
  - 输入: `"<soft_threshold_prompt>   collapsible\n\n whitespace   input"`
  - Compactor: `_AlwaysQualityRejectingCompactor`（两次 proposal 均为 `quality_check_rejected`）
  - Policy: `max_compaction_attempts_per_operation=2`
  - 断言层级:
    1. **Compaction 生命周期**: `compactor.calls == 2`、`CONTEXT_COMPACTION_ATTEMPT_REJECTED == 2`、`CONTEXT_COMPACTION_FAILED == 1`
    2. **Fallback digest 同源**: `expected_current_block.text != current_input`（确认规范化）、`window["selected_material_view_digest"] == selected_material_view_digest((expected_current_block,))`
    3. **Fallback manifest**: `context_fallback_decision_ref` 在 candidate 与 manifest 中一致、`sizing_stage is DISPATCH_FALLBACK`
    4. **Attempt 生命周期**: 1 个 ordinary Attempt、`factory.accepted_requests == 1`
    5. **Proactive projection**: `phase is FAILED`、`decision is USE_FAILED_FALLBACK`、`prepared_attempt_numbers == (1,2)`、`rejected_attempt_numbers == (1,2)`
    6. **Run terminal**: `RUN_SUCCEEDED == 1`、`RUN_LOST == 0`
    7. **Scheduler cleanup**: `scheduler._active_tasks == set()`
- **结论**: PASS。完整覆盖 proactive exhausted fallback 从 compaction rejection → fallback selection → dispatch → Attempt → Run terminal → scheduler cleanup 全状态机路径

### 6-PASS-Reactive full state-machine assertions

- **当前状态**: `test_reactive_compact_failure_fallback_dispatch_uses_failed_view`（`test_dispatch_scheduler.py:9053`）:
  - Recent history: `"recent   protected\n replay material"`（含可折叠空白）
  - Current input: `"dispatch   prompt\n\n with   collapsible whitespace"`
  - Policy: `_compact_floor_one_memory_policy()`（保留 protected recent）
  - 断言层级:
    1. **EventLog-backed block identity**: `selected_block_ids` 包含 `eventlog:user:event-reactive-fallback-recent-input` 与 `current:event-input-dispatch`
    2. **Fallback digest 同源**: 通过 `build_pre_dispatch_compact_material_view` 独立构造 expected blocks → `window["selected_material_view_digest"] == selected_material_view_digest(expected_selected)`
    3. **Protected recent 回放**: `"recent protected\nreplay material" in second_contents`
    4. **Normalization**: `expected_current_block.text != current_input`
    5. **Fallback manifest**: `context_fallback_decision_ref` 在 recovery candidate 与 manifest 中一致
    6. **Attempt 生命周期**: first Attempt `FAILED`、recovery Attempt `SUCCEEDED`
    7. **Run terminal**: `RunStatus.SUCCEEDED`
    8. **Scheduler cleanup**: `scheduler._active_tasks == set()`
- **结论**: PASS。完整覆盖 reactive compaction failure → fallback selection → durable write → durable load → recovery dispatch → Attempt/Run terminal → scheduler cleanup 全状态机路径

### 7-PASS-无 id/section/kind drift，单一 owner

- **检查项**: 删除私有 helper 后是否重新产生 block_id/section/kind 不一致或重复 owner
- **当前状态**:
  - 两处调用 `run_input_material_block` 的参数完全一致:
    - `block_id`: 均为 `f"current:{current_input_ref}"`
    - `section`: 均为 `CompactMaterialSection.CURRENT_INPUT_ANCHOR`
    - `kind`: 均为 `CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR`
    - `canonical_source_refs`: 均为 `(current_input_ref,)`
  - `text` 参数来源:
    - Selection 侧: `source_snapshot.current_input_text` ← `PreDispatchCompactMaterialView.current_input_text` ← `build_pre_dispatch_compact_material_view(current_display_text=...)` ← EventLog `USER_INPUT_ACCEPTED.display_text`
    - Replay 侧: `material_view.current_input_text` ← `build_pre_dispatch_compact_material_view(current_display_text=...)` ← EventLog `USER_INPUT_ACCEPTED.display_text`
    - 同一 EventLog source → 同一 `current_display_text` → 同一 `normalized_material_text` → 同一 `size_units` + `content_digest`
- **直接证据**:
  - `compact_pipeline.py:1123-1130` vs `context_fallback.py:482-489`: 参数结构完全一致
  - `compact_material.py:779`: `material_text = text if accepted_tool_evidence is not None else normalized_material_text(text)` —— 单一规范化 owner
  - `compact_material.py:785-787`: `size_units=len(material_text)`, `content_digest=_text_digest(material_text)` —— 单一派生 owner
- **结论**: PASS。无 drift，`run_input_material_block` 是 material 规范化/size_units/content_digest 的唯一 owner

### 8-PASS-RunInput None residual 无新 production 可达证据

- **Adjudication 分类**: 接受为分类 residual，不在本 slice 扩张
- **当前状态**:
  - `load_context_fallback_in_transaction:407-411`: 对非 PROACTIVE/REACTIVE trigger 新增 fail-closed gate → `raise HostDurableError("fallback trigger_source is invalid")`
  - `load_context_fallback_in_transaction:412`: `material_blocks` 不再条件赋值——valid trigger 必定调用 `_fallback_material_blocks_for_window` 返回 non-None blocks
  - `run_input.py:2335-2336`: `fallback.material_blocks if fallback.material_blocks is not None else _pre_start_fallback_material_blocks(...)` —— `else` 分支仍存在
  - `run_input.py:3705-3706`: `fallback.material_blocks if fallback.material_blocks is not None else build_run_input_material_blocks(...)` —— `else` 分支仍存在
- **分析**: 两个 `else` 分支的触发条件是 `fallback.material_blocks is None`。修复后，所有 production-legal trigger（PROACTIVE、REACTIVE）均保证 `material_blocks` 非 None；未知 trigger 在 `load_context_fallback_in_transaction` 中 fail closed。因此无真实 production 路径可达 `else` 分支。`else` 分支仍服务于注入式 contract/tests 路径（例如 `ActiveRecentWindowFallback` 直接构造 `material_blocks=None`），不在本 slice 范围内。
- **结论**: PASS。与 adjudication 结论一致，无新 production 可达反例

## Adversarial Failure Pass

### Selection → replay 完整数据流一致性

修复后 4 步使用同一条规范化链：

1. **Selection**: `compact_pipeline._fallback_material_blocks:1123` → `run_input_material_block` → `normalized_material_text` → `size_units` + `content_digest`
2. **Durable write**: `RecentWindowFallbackSelection.to_window_payload` → `selected_material_view_digest(selection.selected_blocks)` → 基于 normalized block id/source_refs/content_digest 三元组
3. **Durable read**: `load_context_fallback_in_transaction:412` → `_fallback_material_blocks_for_window:482` → `run_input_material_block`（同一规范化链）
4. **Replay**: `_selected_material_render_view` → `selected_material_view_digest(selected_blocks)` → 与 durable window 中的 digest 比对

**结论**: 4 步使用同一条 `run_input_material_block` → `normalized_material_text` → `size_units` → `content_digest` 链。selection 与 replay 的 digest 计算输入完全一致。

### Fail-closed gate 覆盖

- 旧行为: 未知 `trigger_source` → `material_blocks=None` → 下游静默 fallthrough 到 memory-based ID 构造
- 新行为: `trigger_source not in (PROACTIVE, REACTIVE)` → `raise HostDurableError("fallback trigger_source is invalid")`
- 无静默放行路径

### Context compaction terminal uniqueness

- `CONTEXT_COMPACTION_FAILED` 唯一性：2 次 `quality_check_rejected` → 1 次 `CONTEXT_COMPACTION_FAILED` → `DISPATCH_FALLBACK` → 单次 Attempt → `RUN_SUCCEEDED`
- 无重复 terminal、无孤儿状态

### 跨模块依赖边界

- `compact_pipeline` → `compact_material`（公共导入）
- `context_fallback` → `compact_material`（公共导入）
- 无 `compact_pipeline` → `context_fallback`（消除原私有导入）
- 无反向依赖、无新增 import cycle

### Test fixture adequacy

- `_AlwaysQualityRejectingCompactor`: 继承 `_PreparedManifestProactiveCompactor`，重写 `run_prepared_compactor_proposal` 将所有 candidate 的 semantic 字段置空 → 必然触发 quality rejection。正确模拟 production 中 compactor 返回无效 proposal
- `_FinalAnswerWorkerFactory` + `_FinalAnswerWorker`: accept 后立即返回 `FINAL_ANSWER`，记录 `accepted_snapshots` 和 `accepted_requests`
- `_ReactiveRecoveryWorkerFactory` + `_ReactiveRecoveryWorker`: 第一轮 accept 返回 `CONTEXT_COMPACTION_REQUESTED`，第二轮返回 `FINAL_ANSWER`
- `_fallback_cap_memory_policy()`: `fallback_selected_recent_window_item_cap=1` 收紧到 current-only
- `_seed_current_run` 新增 `display_text` 参数（默认 `"dispatch prompt"`），向后兼容所有已有调用方
- **潜在盲区**: 与原 DS review 一致——测试使用 fake worker/compactor 而非真实 LLM provider。此盲区属于 compactor quality contract 测试范围，非本次 fallback selection/replay 修复范围

## Open Questions

- 无。

## Residual Risk

- **RunInput else-branch 死代码**: `run_input.py:2335-2336` 和 `run_input.py:3705-3706` 的 `else` 分支（`_pre_start_fallback_material_blocks` / `build_run_input_material_blocks`）在修复后无 production 可达路径，但若因 future regression 导致 `material_blocks` 再次变为 None，仍会触发 block ID mismatch。建议后续 slice 评估是否将 `else` 分支改为 fail-closed。此风险与原始 DS review residual risk 一致，adjudication 已分类为不在本 slice 扩张。
- **Fake compactor/worker 盲区**: 与原始 DS review 一致。测试使用 fake 而非真实 LLM provider。`S4 mandatory Mimo→DeepSeek real-provider evidence` 需在本 review 通过后使用全新 evidence root 重跑。
- 无未分类 implementation residual risk。

## 总裁决

**PASS — 所有 8 项验证均通过。** Adjudication 的 5 项 fix acceptance checklist 全部满足：

1. ✅ 跨模块私有 helper 导入已消除，两个 producer 直接从 `compact_material` 导入公开 owner
2. ✅ 无新增 compatibility wrapper、re-export 或新 public surface
3. ✅ Owner test 对 selection/replay 路径的 block construction 等价作直接断言（pure dataclass equality + digest match）
4. ✅ `ActiveRecentWindowFallback.material_blocks` docstring 已修正
5. ✅ 3 条 owner tests pass、409 条 Host tests pass（1 skipped）、pyright clean、git diff --check clean

无新增 finding。Residual risk 与原始 DS review 一致，adjudication 已分类处置。
