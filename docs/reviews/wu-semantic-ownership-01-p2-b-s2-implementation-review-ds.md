# WU-SEMANTIC-OWNERSHIP-01 P2-B S2 Implementation Review — AgentDS

## Scope

- Mode: current changes (uncommitted workspace changes on branch `phaseflow/host-issues-control`)
- Base: `main` (implied by deepreview default)
- Output file: `docs/reviews/wu-semantic-ownership-01-p2-b-s2-implementation-review-ds.md`
- Included scope:
  - `dayu/host/_terminal_answer.py` — 模块 docstring 同步
  - `dayu/host/memory.py` — `MemoryProjectionEvent.assistant_final_answer_text` 新增字段与 `_selected_assistant_item` 消费优先级
  - `dayu/host/durable/memory.py` — `_MemoryProjectionPayloadView` 新增 typed material 字段，`_memory_projection_payload_view` 停止 payload mutation
  - `dayu/host/run_input.py` — `_memory_projection_event_from_row` 停止 payload mutation，新增 `_assistant_final_answer_text`
  - `docs/host/design.md` — 24.5 节与 24.6 节 terminal answer continuity 契约同步
  - `dayu/host/README.md` — descriptor-backed terminal answer continuity 合约说明
  - `tests/README.md` — typed terminal answer material 与 cross-path 等价覆盖说明
  - `tests/host/test_memory_projection.py` — typed material、durable projection、direct consumer descriptor-blind 测试
  - `tests/host/test_run_input_builder.py` — cross-path equivalence 测试与 `_assert_terminal_answer_text_has_no_internal_refs`
- Excluded scope: 未修改的 Host 模块（`compact_material.py`、`outbox.py`、`terminal_payload.py` 实际逻辑等）不在本 review 范围内；仅验证其 terminal answer resolver 引用一致性。
- Parallel review coverage: 无（全部 review 由本 reviewer 完成）

## Findings

未发现实质性问题。

### 各审查要点结论

#### 1. Terminal answer continuity owner boundary

**结论：正确。**

`RUN_SUCCEEDED` canonical terminal fact + payload descriptor + terminal artifact 是成功终态回答的真源。`assistant_final_answer_continuity_text()` 是唯一 resolver，读取顺序固定为 inline `final_answer` → digest-checked terminal artifact `content`。durable memory projection（`dayu/host/durable/memory.py:392-399`）与 RunInputBuilder inline delta（`dayu/host/run_input.py:3234-3240`）均调用同一 resolver，使用同一 `PayloadTextReadPolicy.STRICT_NON_EMPTY`。`compact_material.py:2213` 的 `_run_succeeded_answer_material` 也使用同一 resolver、同一 policy。三个消费点从同一真源派生，语义一致。

#### 2. 停止 synthetic final_answer 注入

**结论：已停止，旧代码已移除。**

- `dayu/host/durable/memory.py` 旧 `_memory_projection_payload_view` 中的 `merged: dict[str, JsonValue] = dict(event.payload); merged[_PAYLOAD_FIELD_FINAL_ANSWER] = final_answer` 已完全移除；现在 `_MemoryProjectionPayloadView` 携带 `assistant_final_answer_text` 作为独立 typed material，`payload` 保持原样。
- `dayu/host/run_input.py` 旧 `_payload_with_assistant_final_answer` 函数（含同等 payload mutation 逻辑）已重命名为 `_memory_projection_payload`，移除 mutation 分支；新增独立 `_assistant_final_answer_text` 函数产生 typed material。
- 两个文件中的 `_PAYLOAD_FIELD_FINAL_ANSWER = "final_answer"` 常量已删除。`rg` 扫描确认无残留: `merged[_PAYLOAD_FIELD_FINAL_ANSWER]` 与 `transient final_answer` 在所有 Host 源文件中无匹配。
- `terminal_payload.py` 和 `outbox.py` 中保留的 `_PAYLOAD_FIELD_FINAL_ANSWER` 分别用于定义字段名与 outbox 展示读取，不属于 mutation 路径。

#### 3. `MemoryProjectionEvent.assistant_final_answer_text` 设计

**结论：正确。**

- 字段位于所有既有 evidence 字段之后（`dayu/host/memory.py:989`），默认值 `None`。
- `__post_init__` 中新增 `_require_optional_non_empty` 校验（`memory.py:1016-1019`）。
- 所有构造方均使用 keyword argument: `assistant_final_answer_text=...`，因此不会因新增字段破坏既有 positional 调用。测试 helper `_event()`（`test_memory_projection.py:239`）与 `_memory_projection_event_from_test_row`（`test_run_input_builder.py:4894`）均使用 keyword args。
- docstring 明确标注"它是 projection-internal typed material，不是 EventLog payload 字段"（`memory.py:969-970`）。
- 属于 projection-internal 的语义正确：该字段不写入 EventLog，不被 durable store 直接持久化，不与 canonical payload 混淆。

#### 4. Durable memory projection 与 RunInputBuilder 使用同一 resolver

**结论：正确。**

| 调用方 | 文件:行号 | Resolver | Text Policy |
|---|---|---|---|
| Durable projection | `durable/memory.py:392-395` | `assistant_final_answer_continuity_text` | `STRICT_NON_EMPTY` |
| RunInput inline delta | `run_input.py:3236-3239` | `assistant_final_answer_continuity_text` | `STRICT_NON_EMPTY` |
| Compact material | `compact_material.py:2213-2215` | `assistant_final_answer_continuity_text` | `STRICT_NON_EMPTY` |

payload mapping 在三个路径中均保持 unchanged：durable projection 传 `payload=event.payload`（`durable/memory.py:397`），RunInput 传原始 `_payload_object(row)` 结果（`run_input.py:3214`），compact material 传 `event_payload_object` 结果（`compact_material.py:2208`）。

#### 5. Direct memory consumer descriptor-blind

**结论：正确。**

`_selected_assistant_item`（`memory.py:1641-1669`）的消费优先级为:
1. `event.assistant_final_answer_text` — typed material（来自 durable projection / RunInputBuilder 的 resolver 输出）
2. `assistant_final_answer_text_from_run_payload(event.payload, text_policy=PayloadTextReadPolicy.LENIENT_NON_EMPTY)` — 仅读 inline `final_answer`，不跟踪 descriptor

测试 `test_memory_direct_consumer_does_not_follow_terminal_descriptor`（`test_memory_projection.py:1193`）验证：当 `MemoryProjectionEvent` 不含 `assistant_final_answer_text` 且 payload 仅有 `terminal_summary_ref`/`terminal_summary_digest` 时，selected recent window 为空——正确拒绝跟随 descriptor。

#### 6. Cross-path 测试覆盖

**结论：充分。**

- `test_terminal_answer_text_matches_durable_projection_and_run_input`（`test_run_input_builder.py:2800`）：在真实 durable store 中写入 descriptor-backed `RUN_SUCCEEDED`，分别通过 durable `ConversationMemoryProjectionConsumer` 与 `RunInputBuilder` 消费，断言两者产出的 LLM-facing assistant answer text 完全一致。
- `_assert_terminal_answer_text_has_no_internal_refs`（`test_run_input_builder.py:6354`）：断言 answer text 不含 `terminal_summary_ref`、`terminal_summary_digest`、`payload_ref`、`payload_digest`、`artifact_ref`、`event_id`、`digest`、`cursor`、`projection`、`governance`、`sha256:` 等内部标签。
- `test_durable_projection_uses_typed_terminal_answer_material`（`test_memory_projection.py:1099`）：在真实 SQLite 中写入 terminal artifact 与仅含 descriptor 的 `RUN_SUCCEEDED`，经 `ConversationMemoryProjectionConsumer` 投影后验证 answer text 正确且不含内部引用片段。

#### 7. Docs / README 同步

**结论：已同步。**

- `docs/host/design.md` §24.5: 更新为"`RUN_SUCCEEDED` canonical terminal fact、payload descriptor 与 terminal artifact 是成功终态回答的真源；terminal answer continuity resolver 可以从已提交 terminal fact 的 inline `final_answer` 或 digest-checked terminal artifact `content` 读取 LLM-facing answer text。Conversation Memory projection 与 RunInputBuilder 只能消费该 resolver 产出的 typed continuity material，不能通过修改 EventLog payload mapping 让下游误以为 descriptor-backed answer 来自 canonical hot payload。"——与代码行为完全一致。
- `docs/host/design.md` §24.6: 新增"terminal answer continuity 投影只能输出回答文本本身，不得输出 `terminal_summary_ref`、`terminal_summary_digest`、payload ref、artifact ref、EventLog id、digest、cursor 或 Host governance label。"——与测试断言一致。
- `dayu/host/README.md`: 新增"descriptor-backed terminal answer continuity 由 Host terminal resolver 解析成 typed LLM-facing material，Memory projection 与 RunInputBuilder 不通过改写 EventLog payload 来投影回答文本。"——与实现一致。
- `tests/README.md`: P12.6 段新增"typed terminal answer continuity material"与"descriptor-backed terminal answer 与 durable memory projection 的 LLM-facing 文本等价"——与测试覆盖一致。

#### 8. Controller validation compact smoke failure 归属

**结论：不属于 P2-B S2。直接证据如下：**

- 失败测试: `tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence`
- 错误路径: `TypeError: RunInputMaterialBlock.readable_source_text must be str`
- 错误发生位置: `dayu/host/compact_material.py:2294` 的 `readable_source_text=projection.source.text`，属于 accepted tool evidence compact material 路径
- S2 变更范围: `_terminal_answer.py`（仅 docstring）、`memory.py`（新增 `assistant_final_answer_text` 字段与 `_selected_assistant_item` 优先级）、`durable/memory.py`（`_MemoryProjectionPayloadView` 与 `_memory_projection_payload_view` 重构）、`run_input.py`（同理重构）。以上所有变更均不触及 `compact_material.py` 的 `_accepted_tool_evidence_delta_blocks` 函数或 `project_accepted_tool_result` 的 `source.text` 字段。
- S2 对 `_tool_result_memory_payload_view` 的唯一修改是添加 `assistant_final_answer_text=None` keyword argument（`durable/memory.py:427,449`），不影响 evidence material 路径的任何行为。
- 因此该 failure 在 S2 前即存在，S2 未引入、未掩盖、未改变其触发条件。Controller 将其分类为 independent umbrella residual 是正确的。

## Open Questions

无。

## Residual Risk

- **Compact smoke failure** (`test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence`): 已由 Controller 确认为 independent umbrella residual，属于 accepted tool evidence compact material source projection 的 owner boundary，应在 P2-B umbrella closeout 前单独修复。不在 S2 scope 内。
- **未覆盖的 resolver 错误路径**: `assistant_final_answer_continuity_text` 中 `sqlite_payload_object` 对损坏的 terminal artifact descriptor 的 `HostDurableError` 抛出路径缺乏独立单元测试。当前由更高级别的集成路径（durable projection 失败即 fail-closed）间接覆盖，风险低。
- **未运行的 broader 测试**: Controller validation 仅运行了 S2 相关 focused 测试（205 passed）。broader `pytest tests/host` 未在 S2 中运行。由于变更范围极小（仅重构 terminal answer 的 typed material 传递方式，不改变 state machine 或 schema），回归风险低。

## Validation Summary

本文基于以下直接证据完成 review:

- 完整阅读 `dayu/host/_terminal_answer.py`、`dayu/host/memory.py`（相关部分）、`dayu/host/durable/memory.py`（相关部分）、`dayu/host/run_input.py`（相关部分）、`dayu/host/terminal_payload.py` 源代码
- 完整阅读 `tests/host/test_memory_projection.py`（相关测试）与 `tests/host/test_run_input_builder.py`（相关测试与 helper）
- 审查 `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md` 的 S2 diff
- 审查 implementation artifact `docs/reviews/wu-semantic-ownership-01-p2-b-s2-implementation-codex.md` 与 controller validation artifact `docs/reviews/wu-semantic-ownership-01-p2-b-s2-implementation-controller-validation.md`
- 沿以下调用链逐行走读:
  1. `assistant_final_answer_continuity_text` → `assistant_final_answer_text_from_run_payload` / `terminal_payload_content_text_from_payload`
  2. Durable: `_memory_projection_payload_view` → `_memory_projection_event_from_view` → `MemoryProjectionEvent` → `_selected_assistant_item`
  3. RunInput: `_memory_projection_event_from_row` → `_assistant_final_answer_text` → `MemoryProjectionEvent` → `_selected_assistant_item`
  4. Direct consumer: `MemoryProjectionEvent` (no typed material) → `_selected_assistant_item` → lenient fallback
  5. Compact material: `_run_succeeded_answer_material` → same resolver
- 验证无 `merged[_PAYLOAD_FIELD_FINAL_ANSWER]` 残留
- 验证三个消费方使用同一 resolver + 同一 policy
- 验证测试断言覆盖内部引用泄漏检查

## Conclusion

**pass** — 未发现实质性问题。P2-B S2 实现正确完成了 terminal answer continuity 的 semantic ownership 修复: 停止 payload mutation、建立 typed material channel、保持 direct consumer descriptor-blind、三个消费方使用同一 resolver、cross-path 测试覆盖等价性与无泄漏断言、docs/READMEs 准确同步。
