# WU-SEMANTIC-OWNERSHIP-01 P2-B S2 Implementation Artifact

## Motivation / Root Cause Confirmation

S2 动机成立。直接代码证据显示，`RUN_SUCCEEDED` descriptor-backed terminal answer 已有同源 resolver，但 memory durable projection 与 RunInputBuilder 旧实现把 resolver 输出合并回 transient `payload["final_answer"]`。这会让下游 consumer 看起来像读取了 canonical hot payload，语义所有权从 terminal fact / resolver 漂移到 projection payload mutation。

本次修复没有改变 durable EventLog schema、`ConversationMemorySnapshotVNext` schema、`SelectedRecentWindowItem` schema，也没有改变 Host public terminal contract。

## Owner Boundary

- 首次产生：Engine 产出成功终态 final answer；Host ingest 将成功终态写为 `RUN_SUCCEEDED` canonical terminal fact，并可通过 terminal payload descriptor / artifact 保存 answer material。
- 校验：Host terminal answer continuity resolver 校验 inline `final_answer` 或 digest-checked terminal artifact `content`。
- 持久化 / 真源：EventLog `RUN_SUCCEEDED`、payload descriptor、terminal artifact 与 digest 是 durable truth；Conversation Memory snapshot 和 RunInputBuilder input 是派生 read model。
- 投影：durable memory projection 与 RunInputBuilder 只消费 typed `assistant_final_answer_text` material；direct memory consumer 在没有 typed material 时只读 inline `final_answer`，保持 descriptor-blind。

## Implementation Summary

- `dayu/host/memory.py`
  - 在 `MemoryProjectionEvent` 增加 projection-internal `assistant_final_answer_text: str | None`。
  - `_selected_assistant_item(...)` 优先读取 typed answer material，缺失时才 lenient 读取 inline payload `final_answer`。
- `dayu/host/durable/memory.py`
  - `_MemoryProjectionPayloadView` 增加 typed answer material。
  - `RUN_SUCCEEDED` durable projection 调用 `assistant_final_answer_continuity_text(...)`，但保持 `event.payload` 原样，不再写回 `final_answer`。
  - `TOOL_RESULT_ACCEPTED` accepted evidence projection 只补默认 typed field，原 owner boundary 未改写。
- `dayu/host/run_input.py`
  - inline delta / ordinary memory event row conversion 保持 payload 原样。
  - 对 `RUN_SUCCEEDED` 生成 typed `assistant_final_answer_text`，交给 memory projection consumer。
- `_terminal_answer.py` 与 `docs/host/design.md`
  - 同步说明 resolver 是 typed continuity material source；consumer 不通过 payload mutation 消费 descriptor-backed answer。
- 测试
  - durable projection descriptor-backed final answer 测试改为 typed material 语义。
  - 保留 direct memory consumer descriptor-blind 测试。
  - 新增真实 durable store cross-path equivalence：同一 descriptor-backed `RUN_SUCCEEDED` 被 RunInputBuilder inline delta 与 durable memory projection 分别消费，LLM-facing assistant answer text 完全一致且不包含 ref/digest/cursor/governance label。

## Propagation Audit

1. Engine final answer：Engine 仍只负责单次 run 输出；本次未改 Engine。
2. Host terminal fact / resolver：`RUN_SUCCEEDED` canonical terminal fact、descriptor 与 terminal artifact 保持真源；`assistant_final_answer_continuity_text(...)` 继续从 inline `final_answer` 或 digest-checked terminal artifact `content` 读取 answer text。
3. Durable memory projection：`ConversationMemoryProjectionConsumer` 通过 resolver 生成 typed `assistant_final_answer_text`，payload 不变。
4. RunInputBuilder：inline delta / ordinary event row path 通过同一 resolver 生成 typed `assistant_final_answer_text`，payload 不变。
5. Direct consumer descriptor-blind：直接调用 `build_conversation_memory_snapshot_from_events(...)` 且没有 typed material 时，不从 `terminal_summary_ref` / `terminal_summary_digest` 反推 final answer。
6. LLM-facing output：selected recent assistant item 与 ordinary RunInput assistant message 只包含 answer text，不输出 terminal descriptor、payload/artifact ref、event id、digest、cursor 或 Host governance label。

## Validation Results

- `source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py`
  - 205 passed.
- `source .venv/bin/activate && pyright`
  - 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - passed.
- `rg -n "merged\\[_PAYLOAD_FIELD_FINAL_ANSWER\\]|transient ``final_answer``" dayu/host docs/host/design.md`
  - no matches.
- `rg -n "terminal_summary_ref|terminal_summary_digest|payload_ref|payload_digest|artifact_ref|event_id|cursor" tests/host/test_memory_projection.py tests/host/test_run_input_builder.py`
  - matches are expected test inputs, helper parameters, cursor-specific tests, and negative assertions; reviewed output assertions do not use these fragments as expected LLM-facing answer text.

## README Decision

- Updated `dayu/host/README.md` because Host production code now exposes a stable developer-facing terminal answer continuity projection contract.
- Updated `tests/README.md` because Host test coverage now explicitly includes typed terminal answer material and memory projection / RunInputBuilder cross-path equivalence.
- No root README or `dayu/README.md` update needed: no CLI/Web/WeChat workflow, installation, command, workspace layout, or layer relationship changed.

## Residual Risks / Stop Conditions

- Residual risk: no known unclassified residual risk for S2.
- Stop conditions: none triggered. Implementation did not require durable schema changes, old DB compatibility reads, or Host public terminal contract changes.
- Uncovered area: broader `pytest tests/host` was not run in this slice; required affected tests, pyright, source scans, and diff check passed.
