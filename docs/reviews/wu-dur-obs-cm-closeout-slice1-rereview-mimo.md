# WU-DUR / WU-OBS / WU-CM Closeout Slice 1 Re-Review

## Verdict

**pass-with-findings**。Controller 接受的两个 fix 已完全落地且测试覆盖充分；无新增 blocking finding。一个非 blocking 维护性观察保留。

## 复审范围

- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- 复审对象: Slice 1 implementation + fix 后的 workspace diff
- 文件: `dayu/host/durable/schema.py`、`dayu/host/tool_runtime.py`、`dayu/host/payload_resolution.py`、`dayu/host/engine_ingest.py`、`tests/host/test_toolruntime_accept_barrier.py`、`tests/host/test_engine_ingest_mapping.py`、`tests/host/test_tool_trace_projection.py`、`tests/host/test_durable_schema.py`、`dayu/host/README.md`、`tests/README.md`
- 上游 artifacts: implementation codex、MiMo code review、DS code review、controller adjudication、fix codex

## 已核验的 Accepted Fixes

### Fix 1: Storage kind 常量单一真源

**结论: 完全修复。**

- 7 个 storage kind 常量（`TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND`、`TOOL_CALL_SEMANTIC_QUERY_DESCRIPTOR_KIND`、`TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON`、`TOOL_CALL_ARGUMENTS_STORAGE_PAYLOAD_DESCRIPTOR`、`TOOL_CALL_SEMANTIC_QUERY_STORAGE_ABSENT`、`TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT`、`TOOL_CALL_SEMANTIC_QUERY_STORAGE_PAYLOAD_DESCRIPTOR`）全部定义在 `dayu/host/durable/schema.py:204-223`。
- `tool_runtime.py:83-93` 和 `payload_resolution.py:15-24` 均从 `schema.py` 导入，无本地重复定义。
- grep 确认 `dayu/host/` 下无残留的私有 storage kind 常量定义。
- 测试 `test_durable_schema.py:test_tool_call_request_payload_descriptor_kinds_are_stable` 验证常量值稳定。

### Fix 2: inline_json / inline_text 携带 payload ref 时 fail-closed

**结论: 完全修复，测试覆盖充分。**

- Arguments: `payload_resolution.py:238-239` — `inline_json` 分支检查 `arguments_payload_ref is not None`，不满足时抛 `HostDurableError("inline tool call arguments must not carry payload ref")`。
- Semantic query: `payload_resolution.py:292-293` — `inline_text` 分支检查 `semantic_query_payload_ref is not None`，不满足时抛 `HostDurableError("inline semantic query must not carry payload ref")`。
- 测试 `test_toolruntime_accept_barrier.py:test_tool_call_request_atoms_reject_inline_arguments_payload_ref` 构造畸形 payload（inline + payload_ref），断言 `HostDurableError`。
- 测试 `test_toolruntime_accept_barrier.py:test_tool_call_request_atoms_reject_inline_semantic_query_payload_ref` 构造畸形 payload（inline_text + payload_ref），断言 `HostDurableError`。
- 对照 absent 分支（`payload_resolution.py:282-289`）已有三字段完整性检查，新 fix 与既有防御风格一致。

## Findings

### F1-[观察]-非阻塞-`_payload_size_bytes` 在两个模块重复定义

- **文件(行号)**: `payload_resolution.py:392-399`，`tool_runtime.py` 中存在同名同实现私有函数
- **说明**: DS code review F2 已指出此问题。Fix gate 未将其纳入 scope（不在 controller accepted findings 中）。这是纯维护性问题，不影响运行时正确性，因为 `canonical_json_dumps` 的输出稳定且两处实现完全一致。
- **建议**: 后续 slice 可考虑提取到 `dayu/host/durable/codec.py`。
- **严重程度**: 低，不阻塞。

## 原始实现复审

以下检查点在 implementation + fix 后的代码中均通过：

1. **Digest 同源性**: `_accepted_arguments_digest` 使用 `sha256_digest_json({"arguments": dict(arguments)})` 作为 canonical preimage，与 `_normalized_arguments_digest` → `_accepted_arguments_digest(call.arguments)` 完全同源。写入端 `_tool_call_request_payload_plan` 校验 `arguments_payload_digest != candidate.call.normalized_arguments_digest`；读取端 `tool_call_request_atoms` 三重校验（`arguments_payload_digest != normalized_digest`、`sha256_digest_json(arguments_json) != arguments_payload_digest`、`_payload_size_bytes != arguments_json_size_bytes`）。

2. **冷热分离阈值**: 写入端 `arguments_size_bytes <= transaction.payload_inline_threshold_bytes` 决定 inline/descriptor；读取端按 `arguments_storage_kind` 严格 dispatch，其它值抛 `HostDurableError`。descriptor 路径校验 descriptor kind + payload digest + size bytes。

3. **Semantic query 独立性**: `semantic_query_text` 来自 `candidate.call.semantic_query_text`，与 `semantic_input_digest`（来自 `candidate.idempotency.semantic_input_digest`）完全独立。absent 路径三字段完整性检查；digest 使用 `sha256_digest_json({"semantic_query_text": query_text})`，与 `semantic_input_digest` 不同 preimage。

4. **事务边界**: `PayloadStore().write_sqlite_payload(transaction, ...)` 在同一 Host transaction 内写入 descriptor 和 SQLite payload；`append_event` 在同一 `run_write` 回调内完成。

5. **ToolAcceptCall.accepted_arguments optional default**: 按 controller adjudication 延后处理。当前双防线（构造时条件校验 + 写入时 `_required_accepted_arguments` 强制校验）保护生产路径。无新增 blocking 证据。

6. **类型严格性**: `ToolCallRequestAtoms` frozen dataclass，所有字段类型明确（`str`、`Mapping[str, JsonValue]`、`str | None`），无 `Any`/`object`。所有校验失败抛 `HostDurableError`。

7. **Engine preview 仍为 diagnostic**: `engine_ingest.py:4247-4249` 新增 `normalized_arguments_digest` 仅写入 `EventClass.PREVIEW` payload，不写入 canonical EventLog。

8. **分层边界**: 未修改 `dayu/host/run_input.py`、`dayu/host/tool_trace.py`、`dayu/host/compaction_evidence.py`、`dayu/engine/` 下任何文件。未引入 Slice 2-7 范畴的 contract。

9. **LLM-facing 语义**: 新增 payload 字段（`arguments_storage_kind`、`arguments_inline_json`、`arguments_payload_ref` 等）仅存在于 EventLog canonical fact payload，未投影到 LLM-facing compact material 或 prompt。README 更新准确描述了 durable atom 边界。

10. **README 同步**: `dayu/host/README.md` 新增 `TOOL_CALL_REQUESTED` request atom 说明准确；`tests/README.md` 更新覆盖描述完整。无未来计划、无实现细节泄漏。

## 测试 / Pyright 核验

- **测试**: `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_durable_schema.py` → **119 passed**，与 fix codex 报告一致。
- **Pyright**: `source .venv/bin/activate && pyright` → **0 errors, 0 warnings, 0 informations**。
- 新增测试覆盖: 8 个新增测试函数（inline arguments atom、large arguments descriptor、inline arguments payload ref rejection、arguments digest mismatch、semantic query inline + descriptor、inline semantic query payload ref rejection、descriptor kind stability、Tool Trace large arguments not inlined）。

## Remaining Risks

1. **`ToolAcceptCall.accepted_arguments` optional default**: 按 controller adjudication 延后处理，owner 为 Slice 7 或 dedicated cleanup。当前双防线有效。
2. **`_payload_size_bytes` 重复定义**: 低维护风险，不影响正确性。
3. **Semantic query 生产路径始终为 absent**: `_tool_fact_accept_candidate` 和 `_tool_fact_reuse_accept_candidate` 均未设置 `semantic_query_text`，semantic query 基础设施仅通过测试驱动。这属于后续 slice 的消费端问题，不阻塞 Slice 1。
4. **Tool Trace hot projection signal**: 未在本 slice 验证 `arguments_storage_kind`、`arguments_payload_ref` 等是否进入 trace hot row，属于后续 OBS scope。

## 是否 Ready for Controller Adjudication

**是**。Controller 接受的两个 fix 已完全落地；无新增 blocking finding；测试与 pyright 通过。建议 controller 授予 Slice 1 accepted 并推进到 Slice 2。
