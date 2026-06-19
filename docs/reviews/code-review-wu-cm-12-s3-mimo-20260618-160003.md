# Code Review

## Scope

- Mode: current changes
- Branch: wu-cm-12-conversation-memory-drift
- Base: main
- Output file: docs/reviews/code-review-wu-cm-12-s3-mimo-20260618-160003.md
- Included scope: WU-CM-12 S3 Shared Rendering And Selected-Id Provenance Guards。文件：`dayu/host/compact_material.py`、`dayu/host/context_fallback.py`、`dayu/host/run_input.py`、`tests/host/test_run_input_builder.py`、`tests/host/test_dispatch_scheduler.py`、`docs/reviews/wu-cm-12-s3-implementation-codex-20260618.md`。
- Excluded scope: S1/S2 已接受变更（`RunInputMaterialBlock.turn_group_id`、turn-group floor helpers、fallback caps wiring）；S4 tier fallback；Engine message dataclasses；EventLog/durable schema；public API。
- Parallel review coverage: 无。单一 reviewer 逐链路走读全部 S3 变更。

## Findings

### 1-未修复-高-EventLogContextFallbackProvider 对 always-present fallback window 字段使用 optional reader，导致数据损坏时静默跳过 guard

- **入口/函数**: `EventLogContextFallbackProvider._load_context_fallback_tx`
- **文件(行号)**: `dayu/host/context_fallback.py:356-374`
- **输入场景**: EventLog 中 `CONTEXT_COMPACTED` 的 `CONTEXT_COMPACTION_FAILED` payload 包含 fallback window，但 window 中 `selected_material_view_digest`、`selected_raw_turn_count`、`selected_recent_window_turn_floor` 字段因存储损坏、部分写入或 payload 迁移而缺失。
- **实际分支**: `_optional_text(window, _FIELD_SELECTED_MATERIAL_VIEW_DIGEST)` 返回 `None` → `ActiveRecentWindowFallback.selected_material_view_digest` 设为 `None` → `_selected_material_render_view` 中 `fallback.selected_material_view_digest is not None` 为 `False` → digest 一致性校验被跳过。同理 `_optional_non_negative_int` 对 `selected_raw_turn_count` 和 `selected_recent_window_turn_floor` 返回 `None` → `_validate_fallback_protected_groups` 中 raw turn count 校验和 protected group 校验被跳过。
- **预期行为**: S3 的设计意图是 fallback window payload 中 `selected_material_view_digest`、`selected_raw_turn_count`、`selected_recent_window_turn_floor` 是 always-present 字段（在 `RecentWindowFallbackSelection.to_window_payload` 中无条件写入）。读取时应使用 required reader：字段缺失即为 payload 损坏，应 fail closed（raise `HostDurableError`），而非静默跳过 guard。
- **实际行为**: 使用 `_optional_text` / `_optional_non_negative_int` 读取 always-present 字段。当字段缺失时返回 `None`，导致 `ActiveRecentWindowFallback` 对应字段为 `None`，下游 guard 条件 `is not None` 短路跳过。数据损坏不会被检测到。
- **直接证据**:
  - 写入端（`context_fallback.py:207-211`）：`_FIELD_SELECTED_RAW_TURN_COUNT: _raw_turn_count(self.selected_blocks)` 和 `_FIELD_SELECTED_MATERIAL_VIEW_DIGEST: selected_material_view_digest(self.selected_blocks)` 无条件写入。
  - 读取端（`context_fallback.py:361-373`）：`_optional_non_negative_int(window, _FIELD_SELECTED_RAW_TURN_COUNT)` 和 `_optional_text(window, _FIELD_SELECTED_MATERIAL_VIEW_DIGEST)` 使用 optional reader。
  - 消费端（`run_input.py:2796-2800`）：`if fallback.selected_material_view_digest is not None and ... != view_digest: raise` — 条件短路导致 guard 被跳过。
  - 消费端（`run_input.py:2810-2811`）：`if fallback.selected_raw_turn_count is not None: ...` — 同上。
- **影响**: EventLog fallback payload 中 always-present 字段损坏时，source refs / material view digest / raw turn count / protected group 一致性 guard 全部被静默跳过。旧/坏 fallback 可以被当作有效 fallback 渲染，导致 LLM 收到与当前 material view 不一致的 context，违反 S3 fail-closed 设计意图。
- **建议改法和验证点**:
  1. 将 `_optional_text(window, _FIELD_SELECTED_MATERIAL_VIEW_DIGEST)` 替换为 `_required_text(window, _FIELD_SELECTED_MATERIAL_VIEW_DIGEST)`（或在 `_optional_text` 返回 `None` 时 raise `HostDurableError`）。
  2. 将 `_optional_non_negative_int(window, _FIELD_SELECTED_RAW_TURN_COUNT)` 和 `_optional_non_negative_int(window, _FIELD_SELECTED_RECENT_WINDOW_TURN_FLOOR)` 替换为 required 版本。
  3. 验证：补充测试用例，构造 EventLog payload 中缺少 `selected_material_view_digest` / `selected_raw_turn_count` 的场景，断言 `EventLogContextFallbackProvider.load_context_fallback` raise `HostDurableError`。
  4. 注意：`fallback_input_window` 本身也有同样问题（always-written, optional-read），但已有 `fallback_window_digest` 校验在 window 存在时生效；建议同步改为 required。
- **修复风险（低）**: 替换 reader 函数，不改变正常路径行为。
- **严重程度（高）**: 违反 S3 fail-closed 设计意图；损坏 fallback payload 可静默绕过所有 provenance guard。

### 2-未修复-中-EventLogContextFallbackProvider 缺少 fail-closed 行为的直接测试覆盖

- **入口/函数**: `EventLogContextFallbackProvider.load_context_fallback`
- **文件(行号)**: `dayu/host/context_fallback.py:255-277`（public API）；消费方 `run_input.py:2768-2838`（`_selected_material_render_view`）
- **输入场景**: EventLog 中存在 `CONTEXT_COMPACTION_FAILED` event，但 fallback window 缺失、digest 不匹配、或 current_input_ref 不匹配。
- **实际分支**: S3 将这些场景从 `return None` 改为 `raise HostDurableError`，但测试矩阵中没有直接覆盖 `EventLogContextFallbackProvider` 的 fail-closed 路径。
- **预期行为**: S3 实现 artifact 声明 "EventLogContextFallbackProvider 的 fail-closed 行为" 已实现。应有测试直接验证 provider 在 window 缺失、digest 不匹配、current_input_ref 不匹配时 raise `HostDurableError`。
- **实际行为**: 现有测试只覆盖 `_fallback_context_messages`（`run_input.py` 内部函数）的 fail-closed 路径，通过构造 `ActiveRecentWindowFallback` fixture 直接传入。`EventLogContextFallbackProvider` 的 EventLog 读取 → payload 校验 → 构造 `ActiveRecentWindowFallback` 这条完整路径没有被测试。
- **直接证据**:
  - `test_run_input_builder.py` 中 `_active_fallback` helper 总是构造包含 `fallback_input_window` 的完整 `ActiveRecentWindowFallback`，绕过了 provider 的 EventLog 读取逻辑。
  - grep `EventLogContextFallbackProvider` 在 `test_run_input_builder.py` 中只出现在 `test_fallback_provider_renders_only_selected_window_and_current_input`，该测试构造的是 happy path（window 完整、digest 匹配）。
  - S3 新增的 fail-closed 行为（`raise HostDurableError("active fallback input window is missing")`、`raise HostDurableError("fallback input digest mismatch")`、`raise HostDurableError("fallback current_input_ref mismatch")`）没有直接测试。
- **影响**: 如果 provider 的 fail-closed 逻辑被回归破坏（例如误改回 `return None`），现有测试不会发现。
- **建议改法和验证点**:
  1. 补充测试：构造 EventLog payload 中 `fallback_input_window` 为 `None` 的场景，断言 `load_context_fallback` raise `HostDurableError`。
  2. 补充测试：构造 EventLog payload 中 `fallback_input_digest` 与 window digest 不匹配的场景，断言 raise `HostDurableError`。
  3. 补充测试：构造 EventLog payload 中 `current_input_ref` 与请求的 `current_input_ref` 不匹配的场景，断言 raise `HostDurableError`。
- **修复风险（低）**: 纯测试补充。
- **严重程度（中）**: 不影响当前正确性，但 fail-closed 路径缺少回归保护。

## Open Questions

- `_required_text_field`（`run_input.py:3655`）的 docstring 声称 "字段缺失或非文本时抛出"，但实际实现 `value.strip() == ""` 也拒绝空白文本。这是正确行为还是 docstring 不精确？当前 `_optional_semantic_text_field` 依赖此行为来拒绝空字符串 `""`，但 docstring 未说明。不影响 S3 正确性，仅为可读性观察。

## Residual Risk

- **S3 digest scope 限制**: `selected_material_view_digest` 只覆盖 `block_id`、`canonical_source_refs`、`content_digest`，不包含 `text`、`size_units`、`kind` 等字段。这是有意设计（避免 rendering-irrelevant 字段导致 false drift），但如果 `text` 被篡改而 `content_digest` 未同步更新（例如 compact material pack 构造 bug），digest 不会检测到。当前 `content_digest` 由 `sha256_digest_json({"text": text})` 计算（`compact_material.py:1417`），篡改 text 必然改变 content_digest，因此此风险在当前实现下不成立。
- **S4 tier fallback 未实现**: 明确 out of scope。
- **dispatch scheduler 测试阈值调整**: `test_second_proactive_compact_uses_previous_view_without_old_raw_replay` 和 `test_multi_turn_proactive_compact_feeds_subsequent_run_input` 的 budget 阈值被调高以适应完整语义 compact 渲染。这些测试的稳定性取决于阈值与实际 token 估算的对齐，如果 future slices 改变渲染格式，阈值可能需要再次调整。

## Review Checklist 逐项结论

### 1) selected_material_view_digest 覆盖范围

**结论: PASS（有条件）。** Digest 覆盖 `block_id` + `canonical_source_refs` + `content_digest`，其中 `content_digest = sha256({"text": text})`。三者联合足以证明 LLM-facing 内容同源：`block_id` 标识 identity，`source_refs` 标识 provenance，`content_digest` 标识 text content。不包含 `text` 直接值是正确设计——避免 rendering-irrelevant 字段（`size_units`、`kind`、`event_sequence`）导致 false drift。条件：当前 `content_digest` 与 `text` 严格绑定（`compact_material.py:1417`），如果 future refactor 解耦二者，digest 覆盖范围需要重新评估。

### 2) EventLogContextFallbackProvider fail-closed 行为

**结论: FAIL。** S3 将 `return None` 改为 `raise HostDurableError` 的 3 处（window 缺失、digest 不匹配、current_input_ref 不匹配）是正确的 fail-closed 改进。但 always-present 字段（`selected_material_view_digest`、`selected_raw_turn_count`、`selected_recent_window_turn_floor`）使用 optional reader 读取，导致数据损坏时 guard 被跳过。详见 Finding 1。

### 3) run_input fallback renderer 不重新选择、不读 EventLog

**结论: PASS。** `_fallback_context_messages`（`run_input.py:2751-2788`）调用 `_selected_material_render_view` 构造渲染视图，然后遍历 `render_view.selected_blocks` 渲染消息。renderer 不调用 EventLog store、不重新选择 material、不修改 selected ids。`_selected_material_render_view`（`run_input.py:2780-2838`）只做校验和从 `material_blocks` 中取回 selected blocks。current input 通过 `block.block_id == render_view.current_input_block.block_id` 跳过，不会重复渲染。

### 4) guard 完整性

**结论: PASS（有缺陷）。** 以下 guard 已实现：
- duplicate selected ids（`run_input.py:2782-2783`）
- missing selected id（`run_input.py:2786-2787`）
- current_input_ref mismatch（`run_input.py:2790-2791`）
- source_refs mismatch（`run_input.py:2793-2794`）
- fallback_input_digest mismatch（`run_input.py:2795-2800`）
- selected_material_view_digest mismatch（`run_input.py:2801-2806`）
- selected_raw_turn_count mismatch（`run_input.py:2811-2817`）
- protected turn-group consistency（`run_input.py:2818-2819`）

缺陷：`selected_material_view_digest`、`selected_raw_turn_count`、`selected_recent_window_turn_floor` 在 provider 读取时为 optional，导致 guard 可被跳过。详见 Finding 1。

### 5) accepted compact semantic renderer 不泄漏内部治理信息

**结论: PASS。** `_vnext_compact_candidate_semantic_lines`（`run_input.py:3392-3431`）渲染以下 LLM-facing 语义字段：
- `session_summary`（summary_text）
- `claim_text`、`evidence_kind`、`evidence_labels`、`source_labels`（fact）
- `anchor_title`、`anchor_items[].display_text`、`anchor_items[].ordinal`（answer anchor）
- `intent_type`、`status`、`text`（forward intent）
- `text`、`reason`、`source_labels`（reference continuity）

不包含 `event_id`、`payload_ref`、`payload_digest`、`tool_call_id`、`accepted_evidence_id`、`artifact_ref`、`estimator_digest`、`compact_artifact_ref`、`compact_artifact_digest` 等内部治理字段。optional 字段（`evidence_kind`、`reason`）通过 `_optional_semantic_text_field` 处理：缺失时省略，存在但非法时 raise `HostDurableError`。

### 6) tests 覆盖关键失效模式

**结论: PASS（有缺口）。** 已覆盖：
- selected ids render all and only selected blocks
- missing/duplicate selected id fail closed
- current_input_ref mismatch fail closed
- source_refs mismatch fail closed
- fallback_input_digest mismatch fail closed
- selected_material_view_digest mismatch fail closed
- selected_raw_turn_count mismatch fail closed
- mixed protected turn group fail closed
- protected group consistency mismatch fail closed
- accepted compact optional text field invalid fail closed
- accepted compact semantic renderer full items

缺口：
- `EventLogContextFallbackProvider` 的 fail-closed 路径（window 缺失、digest 不匹配、current_input_ref 不匹配）没有直接测试（Finding 2）。
- always-present fallback window 字段损坏场景没有测试（Finding 1）。

## Conclusion

**FAIL** — S3 实现的 selected material view rendering、provenance guard 逻辑和 accepted compact semantic renderer 设计正确，但 `EventLogContextFallbackProvider` 对 always-present fallback window 字段使用 optional reader（Finding 1，高），导致数据损坏时 guard 被静默跳过，违反 S3 fail-closed 设计意图。Provider 的 fail-closed 路径也缺少直接测试覆盖（Finding 2，中）。

173 tests passed / pyright 0 errors / git diff --check clean。
