# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/wu-cli-activity-01-continuity-smoke-fix-review-mimo-20260618.md`
- Included scope: dayu/host/terminal_payload.py, dayu/host/_terminal_answer.py, dayu/host/engine_ingest.py, dayu/host/read_api.py, dayu/host/evidence.py, dayu/host/memory.py, dayu/host/durable/memory.py, dayu/host/run_input.py, dayu/host/compact_material.py, dayu/host/compaction_evidence.py, tests/host/test_terminal_payload.py, tests/host/test_memory_projection.py, tests/host/test_public_tool_wiring_smoke.py, tests/host/test_engine_ingest_mapping.py
- Excluded scope: dayu/cli, dayu/fins, dayu/service, dayu/ui, dayu/runtime（不在本次 review 范围内）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Review Focus Area Analysis

### 1. nested summary / summary_text / result_preview / event_ref / payload_ref / digest 是否进入 Conversation Memory 或 ordinary RunInput 的 LLM-facing 内容

**结论：已正确排除。**

- `terminal_payload.py`（第 33-101 行）：`assistant_final_answer_text_from_run_payload` 只读取 `final_answer` 字段；`terminal_payload_content_text_from_payload` 只读取顶层 `content` 字段。两者均不读取 `summary_text`、`nested summary`、`preview`、`result_preview`。
- `_terminal_answer.py`（第 35-83 行）：`assistant_final_answer_continuity_text` 读取顺序固定为 `final_answer` → terminal artifact 顶层 `content`。不读取 `summary_text`、nested `summary`、裸 `content`。
- `memory.py` `_selected_evidence_text`（第 1671-1688 行）：通过 `accepted_evidence_envelope_from_payload` + `accepted_tool_raw_outcome_text_from_payload` 读取 `raw_tool_outcome`。出现旧 `result_preview` 时抛出 `ValueError`，缺失 `raw_tool_outcome` 时 fail closed。无 envelope 时返回中性文本。
- `test_terminal_payload.py`（第 71-129 行）：明确断言 `summary_text`、`summary.content`、`preview`、`result_preview` 不被读取。
- `test_engine_ingest_mapping.py`（第 444-445 行）：断言 terminal payload 中无 `summary` 和 `summary_text`。
- `test_memory_projection.py`（第 521-586 行）：断言 tool evidence 只使用 `raw_tool_outcome`，不含 `preview`、`event_id`、`payload_ref`。
- `test_public_tool_wiring_smoke.py`（第 83-87 行）：断言后续 Run 消息中不含 `event_ref=`、`payload_ref=`、`payload_digest=`、`result_preview`。

### 2. terminal_summary_ref 字段名保留是否只是 durable/public 字段名保留

**结论：正确。**

- `_terminal_answer.py`（第 31-32 行）：`terminal_summary_ref` / `terminal_summary_digest` 仅作为 terminal artifact descriptor 的引用标签和 digest 校验材料使用（第 66-72 行），不是 final answer 真值源。
- `read_api.py`（第 107-108 行、901-910 行）：`_succeeded_host_event` 从 RUN_SUCCEEDED payload 读取 `terminal_summary_ref` / `terminal_summary_digest`，仅用于定位 terminal artifact descriptor 并读取其顶层 `content`。不读取 `summary_text` 或 nested `summary`。
- `engine_ingest.py`（第 1123-1124 行）：`terminal_closeout_in_transaction` 接收 `terminal_summary_ref=descriptor.payload_ref`，仅作为 durable 字段写入。
- 设计文档 `docs/host/design.md` Conversation Memory 章节：只有 `latest_accepted_compacted_view` 是处理后的；post-compact delta 必须是原始 prompt / final answer / tool request / tool response。实现与此一致。

### 3. accepted tool evidence 是否从 accepted envelope 指向的 digest-checked payload 读取 raw_tool_outcome

**结论：正确，且缺失时 fail closed。**

- `evidence.py` `accepted_tool_raw_outcome_text_from_payload`（第 335-355 行）：读取 `raw_tool_outcome`，拒绝旧 `result_preview`（出现时抛出 `ValueError`）。缺失 `raw_tool_outcome` 时返回 `None`。
- `memory.py` `_selected_evidence_text`（第 1671-1688 行）：有 envelope 时必须读取 `raw_tool_outcome`；出现旧 `result_preview` 或缺失 `raw_tool_outcome` 时 raise。
- `compact_material.py` `_accepted_tool_evidence_delta_blocks`（第 2028-2112 行）：通过 `event_payload_object_for_result_ref` 读取 digest-checked payload，再调用 `accepted_tool_raw_outcome_text_from_payload`。缺失时 raise `HostDurableError`。
- `compaction_evidence.py` `_tool_result_evidence_materials`（第 199-247 行）：同样通过 `_accepted_tool_result_payload` → `event_payload_object_for_result_ref` → `accepted_tool_raw_outcome_text_from_payload` 链路。缺失时 raise。
- `durable/memory.py` `_tool_result_memory_payload`（第 380-409 行）：通过 `accepted_evidence_envelope_from_payload` + `event_payload_object_for_result_ref` 读取完整 accepted tool result payload。envelope 存在但 payload descriptor 损坏时 raise。

### 4. durable projection、inline repair、compact material、compaction evidence 是否共享同一语义

**结论：共享同一语义，无逻辑漂移。**

所有路径均通过以下共享 helper 实现：
- `evidence.py` `accepted_evidence_envelope_from_payload`：校验 accepted evidence envelope。
- `evidence.py` `accepted_tool_raw_outcome_text_from_payload`：读取 `raw_tool_outcome` 并拒绝 `result_preview`。
- `terminal_payload.py` `assistant_final_answer_text_from_run_payload`：读取 `final_answer`。
- `_terminal_answer.py` `assistant_final_answer_continuity_text`：读取 final answer continuity。

消费方：
- `memory.py` `_selected_evidence_text`（durable projection consumer）
- `compact_material.py` `_accepted_tool_evidence_delta_blocks`（compact material builder）
- `compaction_evidence.py` `_tool_result_evidence_materials`（compaction evidence collector）
- `durable/memory.py` `_tool_result_memory_payload`（durable memory projection consumer）
- `run_input.py`（RunInputBuilder，通过 compact_material 间接使用）

所有路径的语义一致：有 envelope → 必须有 `raw_tool_outcome`；缺失 → fail closed。

### 5. 是否无 Host / Engine public API/contract drift

**结论：无 drift。**

- `read_api.py`：新增 activity 投影（`HostActivityView`），不改变现有 public API 签名。
- `engine_ingest.py`：transient delta 事件改为 `_accepted_no_event_result()`，不写 EventLog。preview 事件不再包含 delta 类型。均为内部行为变更，不影响 public contract。
- `durable/memory.py`：提取 `conversation_memory_projection_event_filter()` 为模块级函数，不改变 public API。
- `terminal_payload.py`：新模块，纯 internal helper。
- `_terminal_answer.py`：重构为使用 `terminal_payload.py` helper，public 签名不变。

### 6. 测试是否覆盖两个 smoke root cause

**结论：已覆盖。**

Root cause 1（final answer continuity）覆盖：
- `test_terminal_payload.py`：8 个测试覆盖 `final_answer` 读取、`content` fallback、`summary_text` 排除、strict/lenient 策略、continuity resolver 优先级。
- `test_engine_ingest_mapping.py::test_final_answer_closes_attempt_and_run_with_phase5_payload`：断言 terminal payload 无 `summary` / `summary_text`。

Root cause 2（tool evidence memory）覆盖：
- `test_memory_projection.py::test_accepted_tool_evidence_uses_raw_outcome_not_preview_or_refs`：断言 raw_tool_outcome 进入 memory，不含 preview / event_id / payload_ref。
- `test_memory_projection.py::test_accepted_tool_evidence_rejects_result_preview`：断言 result_preview 导致拒绝。
- `test_public_tool_wiring_smoke.py::test_mock_tool_result_feeds_same_run_and_later_run_continuity`：断言后续 Run 消息不含 `event_ref=`、`payload_ref=`、`payload_digest=`、`result_preview`。

### 7. README 触发边界是否合理

**结论：合理。**

实现记录中说明：本次改动未改变 Host / Engine public API 或用户工作流，也未新增测试层级。`dayu/host/README.md` 与 `tests/README.md` 按各自更新边界无需修改。此判断与实际改动范围一致。

## Open Questions

无。

## Residual Risk

1. `memory.py` `_ref_summary_text`（第 2935-2944 行）：当 `USER_INPUT_ACCEPTED` payload 缺失 `display_text` 时，fallback 会生成 `payload_ref=...; payload_digest=...` 或 `event_ref=...` 文本进入 selected recent window。虽然 `USER_INPUT_ACCEPTED` 正常情况下必有 `display_text`，但该 fallback 违反了禁止 `event_ref/payload_ref/digest` 作为 LLM-facing truth 的约束。建议将 fallback 改为中性文本（如"用户输入"）或直接 raise。**严重程度：低**（正常路径不会触发）。

2. `durable/memory.py` `_tool_result_memory_payload`（第 380-409 行）：envelope 不存在时直接返回原始 `event.payload`，不读取 `raw_tool_outcome`。此时 payload 可能包含旧 `display_text` 或 `content`。这与 `_selected_evidence_text` 的 fallback 策略一致（返回中性文本），但 durable projection consumer 会将该 payload 传给 `project_conversation_memory_event`，其中 `_selected_evidence_text` 会处理。**严重程度：低**（两条路径最终汇入同一 fail-safe 逻辑）。

3. 旧 `terminal_summary_payload.py` 和 `tests/host/test_terminal_summary_payload.py` 已删除，且 `grep -rn 'terminal_summary_payload'` 无引用。删除干净。

## Conclusion

**PASS**

本次改动正确解决了两个 smoke root cause：
1. final answer continuity 只允许 `RUN_SUCCEEDED.final_answer` 和 digest-checked terminal artifact 顶层 `content`。
2. tool evidence memory 从 accepted envelope 指向的 digest-checked payload 读取 `raw_tool_outcome`，缺失时 fail closed。

所有 7 个 review focus area 均通过检查。测试覆盖两个 smoke root cause 的正向和反向路径。无 Host / Engine public API/contract drift。Residual risk 为低严重程度的防御性 fallback，不影响正常路径。

---

## Incremental Review（Codex residual risk fix）

- Scope: `dayu/host/memory.py`、`tests/host/test_memory_projection.py`、`docs/reviews/wu-cli-activity-01-continuity-smoke-fix-codex-20260618.md`
- Base: 上一轮 review 后的 HEAD

### 1. _ref_summary_text 删除与 USER_INPUT fallback

**已正确修复。**

- `_ref_summary_text` 已从 `memory.py` 删除（diff 第 2924-2944 行移除）。
- `_user_visible_text`（第 2924-2931 行）fallback 从 `_ref_summary_text(event)` 改为常量 `_USER_INPUT_TEXT_UNAVAILABLE = "用户输入文本不可用。"`。该文本不含 `event_ref=`、`payload_ref=`、`payload_digest=`、`sha256:` 或任何内部 event id / payload id。
- `_selected_evidence_text`（第 1669-1688 行）新增，替代旧的 `display_text` → `content` → `_ref_summary_text` 链。新逻辑通过 `accepted_evidence_envelope_from_payload` + `accepted_tool_raw_outcome_text_from_payload` 读取 `raw_tool_outcome`；无 envelope 时返回 `"工具结果已接受；原始工具响应不可用。"`；有 envelope 但缺 `raw_tool_outcome` 时 raise。无内部标识泄漏。

### 2. 新测试覆盖

**已覆盖。**

- `test_user_input_missing_display_text_does_not_expose_refs`：构造空 payload 的 `USER_INPUT_ACCEPTED` 事件（无 `display_text`），但设置 `payload_ref` 和 `payload_digest`。断言 selected recent user text 不含 `event_ref=`、`payload_ref=`、`payload_digest=`、`sha256:`、event id、payload id。精确覆盖了 residual risk 场景。
- `test_accepted_tool_evidence_uses_raw_outcome_not_preview_or_refs`：断言 tool evidence 只使用 `raw_tool_outcome`，不含 preview / event_id / payload_ref。
- `test_accepted_tool_evidence_rejects_result_preview`：断言 `result_preview` 导致 `ValueError`。

### 3. Public API/contract drift

**无 drift。**

- `memory.py` 变更均为 internal：删除 `_ref_summary_text`、新增 `_selected_evidence_text`、修改 `_user_visible_text` fallback。无 public 函数签名变更。
- `_USER_INPUT_TEXT_UNAVAILABLE` 是模块级私有常量，不暴露。
- import 从 `terminal_summary_payload` 改为 `terminal_payload` + `evidence`，与主 review 的模块重命名一致。

### Incremental Conclusion

**PASS**

Codex 修复正确消除了 residual risk #1（`_ref_summary_text` fallback 泄漏内部标识）。`_ref_summary_text` 已删除，USER_INPUT fallback 改为不含内部治理标识的中性占位文本。新测试精确覆盖缺 `display_text` 且带 payload ref/digest 的场景。无新 public API/contract drift。
