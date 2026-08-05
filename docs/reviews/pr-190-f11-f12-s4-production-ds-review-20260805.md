# Code Review — AgentDS Independent Review

## Scope

- Mode: current changes (working tree, uncommitted)
- Branch: `codex/interactive-oracle`
- Base: `c824ea9038ecb4084621117c6806764cd63e9a20` (= HEAD)
- Output file: `docs/reviews/pr-190-f11-f12-s4-production-ds-review-20260805.md`
- Included scope:
  - `dayu/host/compact_pipeline.py` — 14 行变更
  - `dayu/host/context_fallback.py` — 29 行变更
  - `tests/host/test_dispatch_scheduler.py` — 165 行变更
  - 沿真实 proactive selection → durable fallback load → reactive recovery start → RunInput strict replay (`_selected_material_render_view`) → manifest/Attempt/Run terminal 路径逐行走读
  - 关键依赖：`dayu/host/compact_material.py` (`run_input_material_block`, `build_pre_dispatch_compact_material_view`, `selected_material_view_digest`, `normalized_material_text`)、`dayu/host/run_input.py` (`_selected_material_render_view`, `_fallback_context_messages`，两条 replay 路径)
- Excluded scope: baseline 以前的 PR 190 已接受提交、harness/oracle/scenario、旧 review/evidence、真实 provider evidence 重跑、S5 registry/PR body
- Parallel review coverage: 无。主 reviewer 完成全链路走读、adversarial failure pass、semantic ownership drift pass、test fixture adequacy 检查

## Independent Validation

以下验证由 AgentDS reviewer 独立执行，不依赖 MiMo/Codex 已有结论：

- 新增两条 regression tests（修复后）：`2 passed`
- 受影响 Host test files（`test_dispatch_scheduler.py`、`test_compact_pipeline.py`、`test_run_input_builder.py`、`test_engine_ingest_mapping.py`、`test_recovery_dispatch.py`、`test_public_compact_smoke.py`）：`409 passed, 1 skipped`
- pyright（变更文件）：`0 errors, 0 warnings, 0 informations`
- `git diff --check`：通过

## Findings

### 1-未修复-中-跨模块私有 helper 导入违反模块封装边界

- **入口/函数**: `dayu/host/compact_pipeline.py` 第 71 行 `import _fallback_current_input_material_block`
- **文件(行号)**: `dayu/host/compact_pipeline.py:71`、`dayu/host/context_fallback.py:490-511`
- **输入场景**: 任何触发 proactive/reactive fallback selection 的 compaction operation
- **实际分支**: `compact_pipeline._fallback_material_blocks` (line 1123) 调用从 `context_fallback` 私有导入的 `_fallback_current_input_material_block`
- **预期行为**: 跨模块共享的 builder/convenience helper 应位于公共契约层或双方共享的模块，不应通过私有命名（`_` 前缀）跨模块导入
- **实际行为**: `compact_pipeline` 导入 `context_fallback` 的私有 helper。`_fallback_current_input_material_block` 是一个纯薄包装——只调用 `compact_material.run_input_material_block` 并填入 fallback-specific `block_id` 格式——本身不依赖任何 `context_fallback` 内部状态
- **直接证据**:
  - `context_fallback.py:490-511`: `_fallback_current_input_material_block` 函数体仅调用 `run_input_material_block` 并传入硬编码 `block_id=f"current:{current_input_ref}"`、`section=CompactMaterialSection.CURRENT_INPUT_ANCHOR`、`kind=CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR`（共 3 行核心逻辑）
  - `context_fallback.py:1039-1058`: `__all__` 不包含此函数
  - `compact_pipeline.py:71`: 唯一跨模块私有导入点
  - `compact_pipeline.py:1279-1301`: `__all__` 不包含此函数
  - `dayu/host/__init__.py`: 不导出此函数
  - 全仓搜索确认：此函数仅在 `context_fallback.py`（定义 + 内部使用）和 `compact_pipeline.py`（私有导入）两处被引用
  - `dispatch.py`、`run_input.py` 从 `context_fallback` 导入的均为公开符号（`FALLBACK_ACTION_DISPATCH`、`ActiveRecentWindowFallback`、`load_context_fallback_in_transaction` 等），无私有符号泄漏
- **影响**: 不影响 correctness——两个调用方已正确委托同一 `run_input_material_block` owner。但私有命名跨模块导入导致：(a) 维护者可能认为修改此 helper 只影响 `context_fallback` 内部而实际影响 `compact_pipeline`；(b) 若 `context_fallback` 未来重构，此依赖可能被意外破坏；(c) 违反模块封装原则，增加认知负担
- **建议改法和验证点**: 将 `_fallback_current_input_material_block` 移至 `dayu/host/compact_material.py`（作为模块级 helper，与 `run_input_material_block` 同模块），`context_fallback` 和 `compact_pipeline` 从同一 `compact_material` 源导入。验证点：(a) 两条 fallback selection/replay 路径 digest 一致；(b) `compact_pipeline` 不再私有导入 `context_fallback` 内部符号；(c) 全量 Host tests 通过
- **修复风险（低）**: 纯函数移动，不改变行为；`compact_material` 已是两模块的公共依赖
- **严重程度（中）**: 不导致 correctness bug，但违反项目"语义所有权与修复边界"指令——helper 的真正 owner 是 `compact_material.run_input_material_block`，wrapper 不应由消费者模块私有持有

### 2-已修复-严重-Proactive fallback current-input digest mismatch（S4-001 Bug 1）

- **入口/函数**: `dayu/host/compact_pipeline._fallback_material_blocks` → `dayu/host/run_input._selected_material_render_view`
- **文件(行号)**: 基线 `compact_pipeline.py:1119-1128`（旧）、当前 `compact_pipeline.py:1114-1128`（新）
- **输入场景**: Proactive compaction 两次 `quality_check_rejected` 后触发 fallback selection；用户输入含连续空白/空行/换行（例如 `"  hello  \n\n world  "`）
- **实际分支**:
  - **Selection 侧（旧）**: `_fallback_material_blocks` 手工构造 `RunInputMaterialBlock(text=raw_text, size_units=len(raw_text), content_digest=sha256_digest_json({"text": raw_text}))` —— 使用 RAW text，未经过 `normalized_material_text` 规范化
  - **Replay 侧**: `_selected_material_render_view` 从 `fallback.material_blocks`（EventLog-backed，经 `run_input_material_block` → `normalized_material_text` 规范化）重建 selected view，计算 `selected_material_view_digest` —— 使用 NORMALIZED text
- **预期行为**: Selection 和 replay 必须从同一 `run_input_material_block` 构造 current input block，使用相同的 `normalized_material_text` → `size_units` → `content_digest` 派生链
- **实际行为**: Selection 计算 digest(raw text)，Replay 计算 digest(normalized text) → `HostDurableError: fallback selected material view digest mismatch`
- **直接证据**:
  - `compact_material.py:779`: `material_text = text if accepted_tool_evidence is not None else normalized_material_text(text)` —— `run_input_material_block` 对非 evidence block 强制执行 `normalized_material_text`
  - `compact_material.py:785-787`: `size_units=len(material_text)`, `content_digest=_text_digest(material_text)` —— 均基于规范化文本
  - `compact_material.py:706-721`: `normalized_material_text` 执行 `" ".join(text.split())` per line + 过滤空行
  - 基线 `compact_pipeline.py:1119-1128`: 旧代码绕过 `run_input_material_block`，用 `len(source_snapshot.current_input_text)` 和 `sha256_digest_json({"text": source_snapshot.current_input_text})` 手工计算
  - `run_input.py:5104-5106`: `view_digest = selected_material_view_digest(selected_blocks)` + `fallback.selected_material_view_digest != view_digest` → 抛出 digest mismatch
  - 新增测试 `test_proactive_exhausted_fallback_normalizes_current_input_for_replay` 使用 `"   collapsible\n\n whitespace   input"` 作为输入，修复前在基线上复现 `fallback selected material view digest mismatch`
- **影响**: 连续空白输入导致 Run 静默失败 / 不可恢复；用户看到错误但无法理解根因
- **建议改法和验证点**: 已修复——`_fallback_material_blocks` 改为调用 `_fallback_current_input_material_block` → `run_input_material_block`。验证点：(a) 测试中使用空白折叠输入验证 digest 一致；(b) `expected_current_block.text != current_input` 断言确认规范化发生
- **修复风险（低）**: 委托给已存在的 owner contract；不改变 `run_input_material_block` 行为
- **严重程度（严重）**: Production blocker，导致合法输入无法通过 fallback dispatch

### 3-已修复-严重-Reactive fallback block id mismatch（S4-001 Bug 2）

- **入口/函数**: `dayu/host/context_fallback.load_context_fallback_in_transaction` → `dayu/host/run_input._selected_material_render_view`
- **文件(行号)**: 基线 `context_fallback.py:407-414`（旧）、当前 `context_fallback.py:406-417`（新）
- **输入场景**: Reactive compaction failure 后 dispatch fallback；recent history 含 protected turn-group material
- **实际分支**:
  - **Selection 侧**: `build_recent_window_fallback_selection` 从 `_fallback_material_blocks(source_snapshot)` 获取 material blocks，其中包含 EventLog-backed block IDs（如 `eventlog:user:event-reactive-fallback-recent-input`）
  - **Replay 侧（旧）**: `load_context_fallback_in_transaction` 仅对 `PROACTIVE` trigger 填充 `material_blocks`；对 `REACTIVE` trigger，`material_blocks=None`
  - **Replay 侧 fallthrough（旧）**: `run_input.py:3703-3706` 中 `fallback.material_blocks is None` → 调用 `build_run_input_material_blocks`，后者构造 `memory:N`、`continuity:N`、`current:...` 格式的 block IDs
- **预期行为**: Reactive fallback replay 使用的 material blocks 必须与 selection 时的 block IDs 同源（EventLog-backed）
- **实际行为**: Replay 使用 memory-based block IDs，不匹配 selection 的 EventLog-backed IDs → `_selected_material_render_view:5090` 中 `len(selected_blocks) != len(selected_ids)` → `HostDurableError: fallback selected block id is missing from material view`
- **直接证据**:
  - 基线 `context_fallback.py:407-414`: 旧代码 `if trigger_source == ContextCompactionTriggerSource.PROACTIVE.value: material_blocks = _proactive_material_blocks_for_window(...)` —— REACTIVE 分支不赋值，`material_blocks` 保持 `None`
  - `run_input.py:3703-3706`: `fallback.material_blocks if fallback.material_blocks is not None else build_run_input_material_blocks(...)`
  - `run_input.py:4814-4823`: `build_run_input_material_blocks` 当前 input block ID 为 `f"current:{current_facts.user_input_event.event_id}"`，而 selection 侧 EventLog material block ID 格式为 `eventlog:user:...`
  - `run_input.py:5089-5091`: `selected_blocks = tuple(block for block in material_blocks if block.block_id in selected_ids)` + `len(selected_blocks) != len(selected_ids)` → 抛出
  - 新增测试 `test_reactive_compact_failure_fallback_dispatch_uses_failed_view` 使用 `"recent   protected\n replay material"` 作为 recent history、`"dispatch   prompt\n\n with   collapsible whitespace"` 作为 current input，修复前在基线上复现 `fallback selected block id is missing from material view`
- **影响**: 任何 reactive compaction failure 后的 fallback dispatch 均失败；Run 进入不可恢复状态
- **建议改法和验证点**: 已修复——`load_context_fallback_in_transaction` 对 PROACTIVE 和 REACTIVE 统一调用 `_fallback_material_blocks_for_window`，该函数通过 `build_pre_dispatch_compact_material_view` 构造与 selection 同源的 EventLog-backed material blocks。验证点：(a) 测试中 `selected_block_ids` 包含 `eventlog:user:event-reactive-fallback-recent-input`；(b) `selected_material_view_digest` 与 selection 一致；(c) protected recent material 正确回放
- **修复风险（低）**: 将已有 PROACTIVE 路径的 EventLog-backed 重建逻辑扩展到 REACTIVE；未改变 `build_pre_dispatch_compact_material_view` 或 `run_input_material_block` 行为
- **严重程度（严重）**: Production blocker，导致所有 reactive compaction failure 的 fallback 不可用

## Adversarial Failure Pass

### Selection/replay material reconstruction exact data flow

沿完整链路逐行走读：

1. **Selection**: `compact_pipeline._build_fallback_decision_input` (line 779) → `_fallback_material_blocks` (line 1114) → `_fallback_current_input_material_block` (context_fallback:490) → `run_input_material_block` (compact_material:734) → `normalized_material_text` (compact_material:706) → `RunInputMaterialBlock(text=normalized, size_units=len(normalized), content_digest=_text_digest(normalized))`
2. **Durable write**: `RecentWindowFallbackSelection.to_window_payload` (context_fallback:206) → `selected_material_view_digest(selection.selected_blocks)` (compact_material:547) → 基于 normalized block id/source_refs/content_digest 计算
3. **Durable read**: `load_context_fallback_in_transaction` (context_fallback:351) → `_fallback_material_blocks_for_window` (context_fallback:443) → `build_pre_dispatch_compact_material_view` (compact_material:429) → `_fallback_current_input_material_block` → `run_input_material_block`（同一条规范化链）
4. **Replay**: `_fallback_context_messages` (run_input:5046) → `_selected_material_render_view` (run_input:5071) → 对 selected blocks 重新计算 `selected_material_view_digest` → 与 durable window 中的 digest 比对

**结论**: 修复后 4 步使用同一条 `run_input_material_block` → `normalized_material_text` → `size_units` → `content_digest` 链。selection 与 replay 的 digest 计算输入完全一致（block_id、canonical_source_refs、content_digest 三元组）。

### Reactive trigger 从 None material_blocks 变为 EventLog material rebuild

- **旧行为**: REACTIVE trigger → `material_blocks=None` → replay fallthrough 到 `build_run_input_material_blocks`（memory-based IDs）
- **新行为**: REACTIVE trigger → `_fallback_material_blocks_for_window` → `build_pre_dispatch_compact_material_view` → EventLog-backed blocks
- **新增 fail-closed gate**: `trigger_source not in (PROACTIVE, REACTIVE)` → `HostDurableError("fallback trigger_source is invalid")` —— 旧代码对未知 trigger 静默放行（material_blocks=None），新代码 fail closed
- **block/source_ref/order/protected flag**: `_fallback_material_blocks_for_window` 返回与 selection 完全同源的 blocks（通过 `build_pre_dispatch_compact_material_view` 从同一 EventLog 范围构造）。block order 由 `build_pre_dispatch_compact_material_view` 的 EventLog sequence 顺序保证。`protected_recent_raw_turn` flag 在 selection 阶段由 `protected_recent_turn_group_ids_for_material_blocks` 判定，在 replay 阶段由 `_validate_fallback_protected_groups` (run_input:5107) 校验
- **无丢失/增加**: `build_pre_dispatch_compact_material_view` 构造的是 latest compact 后、当前输入前的 delta material + previous compacted view，与 selection 时的 material source 完全一致

### CONTEXT_COMPACTION_FAILED uniqueness

- `test_proactive_exhausted_fallback_normalizes_current_input_for_replay` 断言 `_event_count(store.transaction_runner, CONTEXT_COMPACTION_FAILED) == 1`
- Policy 设置 `max_compaction_attempts_per_operation=2`，两次 proposal 均被 `_AlwaysQualityRejectingCompactor` 拒绝为 `quality_check_rejected` → 两次 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` → 一次 `CONTEXT_COMPACTION_FAILED`
- 单次 `CONTEXT_COMPACTION_FAILED` 后进入 `DISPATCH_FALLBACK` → 仅创建一个 ordinary Attempt → Run 收敛为 `SUCCEEDED`
- 无重复 terminal、无孤儿状态

### Caps/policy/public API/schema 无漂移

- `context_fallback.__all__`（line 1039-1058）未变更
- `compact_pipeline.__all__`（line 1279-1301）未变更
- 无新增公开符号、无枚举值变更、无 schema 字段增删
- Fallback item/char caps、budget hard/soft threshold、recent turn floor 逻辑均未触及
- `ActiveRecentWindowFallback` dataclass 字段未变更——`material_blocks` 字段在旧代码中已存在（PROACTIVE 时填充），此次仅扩展填充条件至 REACTIVE

### 跨模块依赖边界

- `compact_pipeline` → `context_fallback` → `compact_material`：无反向依赖，无新增 import cycle
- `dispatch.py`、`run_input.py` 从 `context_fallback` 导入均为公开符号：确认无私有符号泄漏
- `context_fallback` 不导入 `compact_pipeline`：无 cycle

### Test fixture adequacy

- `_AlwaysQualityRejectingCompactor`: 继承 `_PreparedManifestProactiveCompactor`，重写 `run_prepared_compactor_proposal` 将所有 candidate 的 semantic 字段置空 → 必然触发 quality rejection。正确模拟 production 中 compactor 返回无效 proposal 的场景
- `_FinalAnswerWorkerFactory` + `_FinalAnswerWorker`: accept 后立即返回 `FINAL_ANSWER`，记录 `accepted_snapshots` 和 `accepted_requests`。用于验证 fallback dispatch 的完整 attempt 生命周期
- `_ReactiveRecoveryWorkerFactory` + `_ReactiveRecoveryWorker`: 第一轮 accept 返回 `CONTEXT_COMPACTION_REQUESTED`（触发 reactive compaction），第二轮返回 `FINAL_ANSWER`。正确模拟 reactive overflow → compaction → recovery 流程
- `_fallback_cap_memory_policy()`: `fallback_selected_recent_window_item_cap=1` 收紧到 current-only，使 fallback selection 只包含 current input block，简化测试断言
- `_seed_current_run` 新增 `display_text` 参数（默认 `"dispatch prompt"`），向后兼容所有已有调用方。新测试传入含连续空白的文本来验证规范化路径
- **潜在盲区**: 测试使用 fake worker/compactor 而非真实 LLM provider。`_AlwaysQualityRejectingCompactor` 始终返回空 candidate，不验证 compactor 返回部分有效 candidate（例如有 session_summary 但无 evidence_facts）的边缘情况。但此盲区属于 compactor quality contract 测试范围，非本次 fallback selection/replay 修复的范围

## Open Questions

- 无。

## Residual Risk

- **跨模块私有 helper 漂移**: `_fallback_current_input_material_block` 位于 `context_fallback` 但本质属于 `compact_material` 的 convenience wrapper。未来 `context_fallback` 重构时可能被意外修改而不察觉对 `compact_pipeline` 的影响。建议移入 `compact_material`
- **Replay else-branch 死代码**: `run_input.py:2333-2336` 和 `run_input.py:3703-3706` 的 `if fallback.material_blocks is not None else ...` 分支中，line 3706 的 `else` 路径调用 `build_run_input_material_blocks`（memory-based IDs），若因 future regression 导致 `material_blocks` 再次变为 None，仍会触发 block ID mismatch。line 2336 的 `else` 路径调用 `_pre_start_fallback_material_blocks`（同样使用 memory-based IDs for memory/continuity blocks），存在相同风险。建议在后续 slice 中评估是否应将 `else` 分支改为 fail-closed（raise 而非 fallthrough），或将 `build_run_input_material_blocks` 也迁移至 EventLog-backed source
- **`covered by later approved slice`**: S4 mandatory Mimo→DeepSeek real-provider evidence 需在本 review 通过后使用全新 evidence root 重跑；旧 S4 bundle 保持 immutable/superseded，不可据此关闭真实 observation
- 无未分类 implementation residual risk
