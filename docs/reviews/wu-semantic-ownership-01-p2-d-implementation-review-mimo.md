# WU-SEMANTIC-OWNERSHIP-01 P2-D Implementation Review - AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-D`
- Gate: implementation review
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p2-d-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-d-implementation-controller-validation.md`
- Accepted plan: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-codex.md`

## Review Focus Results

### F1: source-unavailable 文案是否只在 projection owner 定义并被下游复用

**结论：通过。**

- `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 仅在 `dayu/host/accepted_result_projection.py:38-40` 定义，通过 `__all__` 导出。
- 下游消费者均从 projection 派生 source text，未各自补造：
  - `dayu/host/compact_material.py:2294` — `readable_source_text=projection.source.text`
  - `dayu/host/durable/memory.py:433,454` — `evidence_source_text=projection.source.text`
  - `dayu/host/run_input.py:3018-3019` — 直接消费 `block.readable_source_text`
- Tool Trace (`dayu/host/tool_trace.py`) 不暴露 source text 字段；source refs 仅通过 trace summary 的内部结构传递，不进入 LLM-facing cold text。
- 无下游 fallback：`rg` 扫描 `dayu/host/` 未发现 `source.*fallback`、`fallback.*source` 或 `or "..."` 对 `source.text` 的补救。

### F2: `AcceptedToolResultSourceProjection.text: str` 收紧是否合理

**结论：通过。**

- `text` 从 `str | None` 收紧为 `str`（`accepted_result_projection.py:120`），docstring 已更新为"LLM-facing source 文本；无业务 source 时为业务中性不可用文案"。
- 与 query projection 对齐：`AcceptedToolResultQueryProjection.text` 已经是 `str`，unavailable 时返回 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`。source projection 现在遵循同一模式。
- `state=UNAVAILABLE` / `diagnostic_reason` 仍区分两种 unavailable 原因：
  - `accepted_evidence_envelope_missing`（envelope 缺失）
  - `business_source_unavailable`（envelope 存在但可见业务 source refs 为空）
- 测试覆盖：
  - `test_projection_missing_envelope_returns_shared_unavailable_source_text` — envelope 缺失路径
  - `test_projection_unavailable_source_uses_shared_llm_text_and_filters_internal_refs` — business source 不可用路径
  - `test_projection_falls_back_to_arguments_when_semantic_query_is_absent` — 断言已更新为 `UNAVAILABLE` + 常量

### F3: 是否有 downstream fallback 泄漏 event id / payload ref / digest / cursor / policy / ToolRuntime / Host governance

**结论：通过。**

- compact material（`dayu/host/compact_material.py`）：直接使用 `projection.source.text`，无 `or ...` fallback，无内部 ref 补造。
- RunInputBuilder（`dayu/host/run_input.py`）：`_accepted_tool_evidence_content` 从 `block.readable_source_text` 拼接 `source=` 行；不读取 payload ref / event id / digest。
- Memory（`dayu/host/durable/memory.py`）：`_tool_result_memory_payload_view` 使用 `projection.source.text` 作为 `evidence_source_text`；字段类型保持 `str | None` 以覆盖非 accepted-result 路径，但 accepted-result 正常路径始终非空。
- Tool Trace（`dayu/host/tool_trace.py`）：不暴露 source text 字段；测试新增 `OpaqueEvidenceRef(ref_kind="payload", ...)` 输入并断言 `"payload-source-internal" not in cold_text`。
- 跨消费者等价性测试（`test_accepted_result_projection.py:629`）：source-unavailable accepted result 在 compact material / RunInput / Memory / Tool Trace 中均断言 `"payload-internal" not in visible_text` 和 `"event-internal" not in visible_text`。

### F4: `selected_recent_window_turn_floor=0` 是否是合法测试目标装配

**结论：通过，是合法测试目标装配。**

- `selected_recent_window_turn_floor` 是 `MemoryProjectionPolicy` 的已有字段，控制 selected recent window 保护的最少 turn group 数量。
- 设计真源（`docs/host/design.md`）规定 `floor` 与 item / char cap 冲突时 floor 优先；默认值保护最近 N 个 turn group。
- `test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` 的测试目标是"刚产生的 accepted evidence 进入 compactor"。将 floor 设为 0 意味着不保护任何 recent turn，使刚产生的 raw accepted evidence 可以被 compact。这是测试目标驱动的合法装配，不是掩盖 production selection 问题。
- `_fake_compact_open_options` 的 `selected_recent_window_turn_floor` 参数默认为 `None`（使用 production 默认值），只有该特定 smoke 测试覆盖为 0。其它 public compact smoke 测试不受影响。
- 不改变 production `MemoryProjectionPolicy` 默认值或 selection 语义。

### F5: 测试覆盖是否足够

**结论：通过。**

| 测试文件 | 变更 | 覆盖内容 |
|---|---|---|
| `test_accepted_result_projection.py` | +2 tests, 更新 1 assertion | envelope missing source、business source unavailable、internal ref filtering、跨消费者等价性 |
| `test_compact_material.py` | +1 test | 缺业务 source refs 时 compact material 使用 projection owner 文案 |
| `test_run_input_builder.py` | 更新 1 test | RunInputBuilder 消费 projection source-unavailable 文案，不输出 event refs |
| `test_memory_projection.py` | +1 assertion | Conversation Memory 使用 projection source-unavailable 文案 |
| `test_tool_trace_projection.py` | +2 source ref inputs, +1 assertion | Tool Trace 不泄漏 internal source refs |
| `test_public_compact_smoke.py` | +1 parameter | raw accepted evidence compact fact reuse smoke 从 source-unavailable evidence 生成 stable fact |

所有修改的测试均通过（implementation artifact 报告 `13 + 206 + 46 + 1 = 266 passed`）。

### F6: README 触发判断是否正确；memory docstring 是否同步充分

**结论：通过。**

- `dayu/host/README.md` 已说明 accepted tool result 的 query/status/result/source 由 Host 统一投影，下游只消费该投影。本次实现未改变该 public contract，无需更新。
- `tests/README.md` 未新增测试层级或运行方式，无需更新。
- `dayu/host/durable/memory.py` 的 `_MemoryProjectionPayloadView.evidence_source_text` docstring 已更新为"可选业务可读 source 文本；accepted result 正常路径由统一 projection owner 提供非空 source 文本"。这是 docstring-only 变更，无行为修改。

## Source-Leak Scan

```
rg -n "event_id|payload_ref|payload_digest|cursor|policy|ToolRuntime|Host governance|digest" dayu/host/accepted_result_projection.py tests/host/test_accepted_result_projection.py
```

命中均为：
- 内部实现字段（`_FIELD_NORMALIZED_ARGUMENTS_DIGEST`、`_INTERNAL_SOURCE_REF_KINDS` 中的 `"digest"`）
- diagnostic payload refs（`_payload_refs` 函数）
- digest 校验路径（`sha256_digest_json`、`expected_payload_digest`）
- 测试 fixture 输入（`sha256_digest_json` 构造 digest、`event_id=` 构造 fixture）
- `projection_result_digest` helper

新增 `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 常量文本为"业务来源不可用；工具结果未提供可安全展示的来源。"，不包含 event id、payload ref、digest、cursor、policy、ToolRuntime 或 Host governance 文本。

## Propagation Audit

1. **Durable truth**：`TOOL_RESULT_ACCEPTED` payload、accepted evidence envelope 与 raw outcome 仍是唯一持久事实；schema 未变。
2. **Projection**：`project_accepted_tool_result(...)` 统一投影 query/status/result/source。source available 时输出业务 refs；source unavailable 时输出唯一共享 LLM-facing 文案，并保留结构化诊断原因（`accepted_evidence_envelope_missing` / `business_source_unavailable`）。
3. **Compact material**：`_accepted_tool_evidence_delta_blocks(...)` 继续直接使用 `projection.source.text`，无 `or ...` fallback；evidence block 不暴露 event id、payload ref 或 digest 作为 source。
4. **Compactor input**：source-unavailable evidence 进入 `evidence_material`，fake compactor 只用 prompt-local label 生成 fact candidate。
5. **Accepted compact fact**：stable fact 从 raw accepted evidence material 派生；source-unavailable 文案只表示来源状态，不升级为财报事实。
6. **Follow-up visible outputs**：RunInputBuilder、Conversation Memory 与 Tool Trace 均从同一 accepted-result projection 派生；测试覆盖 no internal source ref leakage。

## Conclusion

**pass**

P2-D implementation 正确地在 projection owner boundary 收紧了 source contract，新增 `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 常量，将 `AcceptedToolResultSourceProjection.text` 从 `str | None` 收紧为 `str`，并在所有 direct consumers 中保持同源投影语义。`state` / `diagnostic_reason` 仍区分 envelope missing 与 business source unavailable。无 downstream fallback，无 internal ref 泄漏。`selected_recent_window_turn_floor=0` 是合法测试目标装配。测试覆盖充分，README 无需更新，memory docstring 已同步。

无 finding。
