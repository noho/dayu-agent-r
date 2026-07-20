# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-p2-b-s2-implementation-review-mimo.md`
- Included scope: WU-SEMANTIC-OWNERSHIP-01 P2-B S2 terminal answer continuity projection contract
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Review Detail

### 1. Terminal answer continuity owner boundary

Owner boundary 正确：

- **首次产生**：Engine 产出成功终态 final answer；Host ingest 将成功终态写为 `RUN_SUCCEEDED` canonical terminal fact，可通过 payload descriptor / artifact 保存 answer material。
- **校验**：`assistant_final_answer_continuity_text()` (`_terminal_answer.py:35`) 校验 inline `final_answer` 或 digest-checked terminal artifact `content`。
- **持久化 / 真源**：EventLog `RUN_SUCCEEDED`、payload descriptor、terminal artifact 与 digest 是 durable truth。
- **投影**：durable memory projection 与 RunInputBuilder 只消费 typed `assistant_final_answer_text` material；direct memory consumer 在没有 typed material 时只读 inline `final_answer`，保持 descriptor-blind。

直接证据：

- `dayu/host/durable/memory.py:392-404`：`_memory_projection_payload_view` 对 `RUN_SUCCEEDED` 调用 resolver，将结果放入 `assistant_final_answer_text`，payload 保持 `event.payload` 原样不变。
- `dayu/host/run_input.py:3220-3240`：`_assistant_final_answer_text` 对 `RUN_SUCCEEDED` 调用同一 resolver。
- `dayu/host/memory.py:1650-1656`：`_selected_assistant_item` 优先读取 typed material，缺失时才 lenient 读取 inline `final_answer`。

### 2. Payload mutation 已停止

旧实现通过 `merged: dict[str, JsonValue] = dict(event.payload); merged[_PAYLOAD_FIELD_FINAL_ANSWER] = final_answer` 将 resolver 输出写回 payload view，让下游误以为 descriptor-backed answer 来自 canonical hot payload。

新实现 (`dayu/host/durable/memory.py:397-404`) 直接传递 `payload=event.payload` 原样，resolver 输出只进入 `assistant_final_answer_text` typed field。

`rg -n "merged\\[_PAYLOAD_FIELD_FINAL_ANSWER\\]" dayu/host` 验证无残留 mutation 代码。

### 3. MemoryProjectionEvent.assistant_final_answer_text 是 projection-internal typed material

- `dayu/host/memory.py:989`：`assistant_final_answer_text: str | None = None` 定义在 `evidence_source_text` 之后，保持既有 evidence fields 的 positional 兼容行为。
- `dayu/host/durable/memory.py:117`：`_MemoryProjectionPayloadView.assistant_final_answer_text` 作为 projection-internal 字段传递给 `MemoryProjectionEvent`。
- 该字段不进入 EventLog payload、不进入 durable schema、不暴露给 LLM-facing output。

### 4. Durable memory projection 与 RunInputBuilder 使用同一 terminal resolver

两者均调用 `assistant_final_answer_continuity_text()` (from `dayu/host/_terminal_answer.py`)：

- Durable projection：`dayu/host/durable/memory.py:392`
- RunInputBuilder：`dayu/host/run_input.py:3236`

两者均使用 `PayloadTextReadPolicy.STRICT_NON_EMPTY`。payload mapping 保持 unchanged。

### 5. Direct memory consumer 仍 descriptor-blind

`dayu/host/memory.py:1650-1656`：`_selected_assistant_item` 在 `assistant_final_answer_text is None` 时回退到 `assistant_final_answer_text_from_run_payload(event.payload, text_policy=PayloadTextReadPolicy.LENIENT_NON_EMPTY)`。这读取 inline `final_answer`，不解析 terminal artifact descriptor。

### 6. 新 cross-path 测试覆盖充分

`tests/host/test_run_input_builder.py:2800-2876`：`test_terminal_answer_text_matches_durable_projection_and_run_input` 测试：

- 创建 descriptor-backed terminal answer（payload 只含 descriptor，不含 inline answer）
- 通过 RunInputBuilder inline delta path 读取
- 通过 durable memory projection 读取
- 断言两者 assistant answer text 完全一致：`run_input_answers[-1] == projection_answers[-1]`
- 断言不包含内部引用：`terminal_summary_ref`、`terminal_summary_digest`、`payload_ref`、`payload_digest`、`event_id`、`digest`、`cursor`、`sha256:` 等

`tests/host/test_memory_projection.py:1066-1096`：`test_typed_terminal_answer_material_becomes_selected_recent_window` 覆盖 typed material 优先消费。

`tests/host/test_memory_projection.py:1099-1176`：`test_durable_projection_uses_typed_terminal_answer_material` 覆盖 durable store 中 descriptor-backed answer 的 projection。

`tests/host/test_memory_projection.py:1323-1414`：`test_accepted_tool_evidence_missing_projection_fields_fail_closed` 和 `test_accepted_tool_evidence_uses_projection_fields_without_payload_rebuild` 覆盖 accepted evidence projection 字段缺失时不从 payload 重建。

### 7. Docs / README 同步

- `docs/host/design.md`：terminal answer continuity truth 和 projection constraints 已更新（line 3082 区域）。
- `dayu/host/README.md`：Host developer-facing terminal answer continuity contract 已更新。
- `tests/README.md`：coverage boundary 已更新，包含 typed terminal answer material 和 cross-path equivalence。

### 8. Controller validation 的 compact smoke failure 分类

Controller validation 记录的 `tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` 失败（`TypeError: RunInputMaterialBlock.readable_source_text must be str`）确实是独立 umbrella residual。

直接证据：该失败在 accepted tool evidence compact material source projection 路径，不在 terminal answer continuity projection 路径。P2-B S2 的改动范围是 `MemoryProjectionEvent`、`_MemoryProjectionPayloadView`、`_selected_assistant_item`、`_selected_evidence_text` 和 `_assistant_final_answer_text`，不涉及 `RunInputMaterialBlock` 构造或 compact material source projection。Controller 分类正确：应作为 umbrella closeout 前的 follow-up sub WU 处理。

### 9. Accepted evidence projection 共享契约

新增 `dayu/host/accepted_result_projection.py` 模块提供 `project_accepted_tool_result()` 作为 accepted tool result 的统一可读投影。`durable/memory.py` 和 `run_input.py` 均消费该共享投影，不再各自重建 request atom 读取逻辑。这正确落实了语义所有权：一个 source-of-truth / public contract，多个消费者复用。

`ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 常量从 `memory.py` 迁移到 `accepted_result_projection.py`，`memory.py` 通过 lazy import 消费（打断循环导入），文案真源保持唯一。

### 10. Source text 过滤职责迁移

旧实现中 `run_input.py` 包含 `_llm_facing_evidence_source_text` 和 `_is_internal_evidence_source_part` 过滤函数，每个消费者自行过滤内部 provenance。

新实现中 source text 由 `accepted_result_projection.py` 的 `_source_projection()` 统一清洗，`run_input.py` 直接消费 `block.readable_source_text`。这正确落实了"若多个消费者需要同一语义，必须抽取或复用同一个 source-of-truth"。

## Open Questions

无。

## Residual Risk

- `tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` 失败是独立 umbrella residual，不在 P2-B S2 scope 内。Owner boundary 是 accepted evidence material projection / compact material source，应在 umbrella closeout 前修复。
- broader `pytest tests/host` 未在 S2 slice 内完整运行；S2 验证覆盖了 affected tests (`205 passed`)、pyright、`git diff --check` 和 source scan。Controller validation 确认通过。

## Conclusion

pass
