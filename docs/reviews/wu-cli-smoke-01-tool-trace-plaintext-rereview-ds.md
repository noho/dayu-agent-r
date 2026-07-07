# Code Review: Tool Trace 明文可审计性修复 DS Finding Re-review

## Scope

- Mode: current changes (workspace + staged + committed on branch)
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-tool-trace-plaintext-rereview-ds.md`
- Included scope: `dayu/host/durable/payload.py`, `dayu/host/durable/artifact.py`, `dayu/host/durable/tool_trace.py`, `dayu/host/durable/transaction.py`, `dayu/host/durable/connection.py`, `dayu/host/durable/schema.py`, `dayu/host/durable/options.py`, `dayu/host/run_input.py`, `dayu/host/engine_ingest.py`, `dayu/host/tool_trace.py`, `tests/host/test_run_input_builder.py`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_tool_trace_queries.py`, `tests/host/test_durable_transaction.py`, `docs/host/design.md`, `docs/reviews/wu-cli-smoke-01-tool-trace-plaintext-fix-codex.md`
- Excluded scope: 其他不属于 Tool Trace 明文修复范围的 workspace 文件
- Parallel review coverage: 无（单人逐行走读）

## Verification Baseline

- pyright: `0 errors, 0 warnings, 0 informations`
- pytest (affected test files): `232 passed`
- git diff --check: clean
- import 完整性验证: 所有新增类型可正常导入

## DS Finding Closure Status

### DS-F1: 双端 projection payload 写入策略统一 — Pass

**入口/函数**: `_write_runner_call_projection_payload` (双端)
**文件(行号)**:
  - `dayu/host/run_input.py:4390-4424`
  - `dayu/host/engine_ingest.py:5191-5225`
  - 共享 helper: `dayu/host/durable/payload.py:366-425` (`write_bounded_json_payload`)

**验证**:

- run_input.py:4390-4424 的 `_write_runner_call_projection_payload` 通过 `payload_store.write_bounded_json_payload(transaction, BoundedJsonPayloadWriteRequest(...))` 委托写入。
- engine_ingest.py:5191-5225 的 `_write_runner_call_projection_payload` 通过相同的 `payload_store.write_bounded_json_payload(transaction, BoundedJsonPayloadWriteRequest(...))` 委托写入。
- 两端各自保留模块级 `payload_ref` / `sqlite_payload_id` 派生规则（run_input 使用 `_RUNNER_CALL_PROJECTION_PAYLOAD_REF_PREFIX`，engine_ingest 使用 `_RUNNER_CALL_PROJECTION_REF_PREFIX`，但值相同均为 `"payload-runner-call-input-projection"`），作为 8 行薄 wrapper 存在，不构成策略重复。
- 无胶水 seam：`write_bounded_json_payload` 在 `dayu.host.durable.payload` 中定义，是合理的公共基础设施，调用方向为 `Host → durable`，无反向依赖。
- 无跨模块穿透：`run_input.py` 与 `engine_ingest.py` 彼此不 import，各自独立依赖 durable payload helper。

**结论**: 已关闭。payload 写入策略（inline/artifact 阈值判断、digest 校验、idempotency）统一在 `write_bounded_json_payload` 中实现，两端不复刻策略逻辑。

### DS-F2: projection payload 按 inline 阈值冷热分离 — Pass

**入口/函数**: `write_bounded_json_payload`
**文件(行号)**: `dayu/host/durable/payload.py:366-425`

**验证**:

- payload.py:396 行 `encoded.payload_size_bytes <= transaction.payload_inline_threshold_bytes` 作为分支判断：
  - ≤ 阈值：走 `write_sqlite_payload`（SQLite inline payload + descriptor）
  - > 阈值：走 `LocalArtifactStore.write_artifact_bytes` + `write_payload_descriptor_for_artifact`（文件系统 artifact + descriptor）
- `_encode_bounded_json_payload` (payload.py:506-527) 在分支前计算 canonical bytes、size、digest，确保同一 payload 在两种路径下 digest 一致。
- `write_sqlite_payload` 收到 `expected_digest=encoded.payload_digest`，内部 `_encode_sqlite_payload` 重新计算 digest 后由 `_validate_expected_digest` 做一致性校验（payload.py:245-248），保证双编码路径的 digest 同源。
- `LocalArtifactStore.write_artifact_bytes` 在 payload.py:413-418 收到 `expected_digest=encoded.payload_digest`，artifact 层独立完成 digest 校验（artifact.py:88-89）。
- idempotency：payload.py:391-395 在 `existing is not None` 且 digest 一致时直接返回已有 descriptor；digest 不一致时 fail closed。
- manifest / hot payload 仍只保存 ref、digest、size（`runner_call_projection_artifact_ref/digest/size_bytes`），不内联大明文。
- 测试验证：`test_runner_call_manifest_is_bounded_and_does_not_inline_messages` (test_run_input_builder.py:482-559) 使用 `payload_inline_threshold_bytes=21000` 触发 artifact 路径，line 547 断言 `projection_descriptor.payload_kind is PayloadKind.ARTIFACT_REF`。
- schema snapshot 仍使用 SQLite JSON payload descriptor（`_write_selected_tool_schema_snapshot_payload` 在 run_input.py:4454 直接调用 `write_sqlite_payload`），这是明确的设计决策（Codex fix artifact 中已记录），因为 tool schema 始终远小于阈值。

**结论**: 已关闭。projection payload 按阈值在 SQLite inline 与文件系统 artifact 间切换；hot/cold trace bounded。

### DS-F3: complete manifest hot payload diagnostic self-describing — Pass

**入口/函数**: `_manifest_hot_diagnostic`
**文件(行号)**: `dayu/host/engine_ingest.py:5322-5348`

**验证**:

- engine_ingest.py:5333 行 `if _manifest_validation_status(manifest) != _RUNNER_CALL_MANIFEST_STATUS_COMPLETE:` 分支：
  - 非 complete：返回 manifest 内 diagnostic object（如 limited_signal 的 reason/missing_atom_kind 等）
  - complete：返回 `_runner_call_manifest_diagnostic(status="complete", ...)` — 显式 synthetic diagnostic object
- `_manifest_validation_status` (engine_ingest.py:6104-6115) 在 manifest `diagnostic` 为 `None` 时返回 `"complete"` — 处理 complete manifest body 中 `diagnostic: null` 的约定。
- hot payload 中 `diagnostic` 字段通过 `_manifest_hot_diagnostic` 写入（engine_ingest.py:5318），确保 hot payload 中 diagnostic 始终为 explicit JSON object。
- 设计文档已更新：`docs/host/design.md` 明确 "complete hot payload 的 diagnostic 必须显式写 `status="complete"`，不得用 `null` 表达 complete"。
- 测试验证：`test_runner_call_manifest_is_bounded_and_does_not_inline_messages` (test_run_input_builder.py:549-550) 断言 `diagnostic["status"] == "complete"`。

**结论**: 已关闭。complete manifest 的 hot payload diagnostic 显式写为 `{status: "complete", ...}` synthetic object，self-describing。

### DS-F4: resolver 支持 artifact JSON payload — Pass

**入口/函数**: `read_tool_trace_json_payload` → `_read_artifact_payload_json`
**文件(行号)**:
  - `dayu/host/durable/tool_trace.py:447-484` (read_tool_trace_json_payload)
  - `dayu/host/durable/tool_trace.py:514-539` (_read_artifact_payload_json)
  - `dayu/host/durable/artifact.py:200-230` (read_artifact_bytes)

**验证**:

- tool_trace.py:469-474 行按 `descriptor.payload_kind` 分发：
  - `SQLITE_PAYLOAD` → `_read_sqlite_payload_json` (tool_trace.py:487-511)
  - `ARTIFACT_REF` → `_read_artifact_payload_json` (tool_trace.py:514-539)
  - 其他 → `raise HostDurableError("tool trace payload kind is unsupported")`
- `_read_artifact_payload_json` 验证链路：
  1. 断言 `descriptor.artifact_relative_path is not None` (line 526-527)
  2. 从 descriptor 构造 `LocalArtifactRef` (line 530-534)
  3. 调用 `read_artifact_bytes` (line 528) 完成路径 containment、digest、size 三重校验 (artifact.py:200-230)
  4. UTF-8 decode，失败时 `raise HostDurableError("tool trace artifact payload is not UTF-8 JSON")` (line 539)
  5. 返回 JSON 文本，由 `read_tool_trace_json_payload` 的 line 475-477 完成 JSON object 与 digest 最终校验
- `read_artifact_bytes` (artifact.py:200-230) 的校验链：`validate_artifact_ref` → path containment → `read_bytes` → digest recheck (line 226-227) → size recheck (line 228-229)
- 测试验证：`test_runner_call_projection_resolver_reads_artifact_projection_payload` (test_tool_trace_queries.py:858-941) 构造 artifact payload → 写入 → resolver 恢复 → 断言明文一致。

**结论**: 已关闭。resolver 支持 SQLite payload 与 artifact JSON payload 两种 descriptor kind；artifact 路径含路径/size/digest/JSON object 完整校验。

## 补充测试覆盖

### 逐条 message digest cross-verify — Pass

**文件(行号)**: `tests/host/test_run_input_builder.py:553-559`

**验证**:

```python
assert len(messages) == len(manifest_entries)
for message, entry in zip(messages, manifest_entries, strict=True):
    assert message["index"] == entry["index"]
    assert message["role"] == entry["role"]
    assert message["content_digest"] == entry["content_digest"]
    assert message["content_size_bytes"] == entry["content_size_bytes"]
    assert entry["projection_artifact_ref"] == projection_ref
    assert entry["projection_artifact_digest"] == projection_digest
```

逐条验证所有 message 与 manifest entry 的 index、role、content_digest、content_size_bytes、projection ref/digest 一致性。使用 `strict=True` 确保数量必须先一致。

### resolver fail-closed 错误路径 — Pass

**文件(行号)**: `tests/host/test_tool_trace_queries.py:944-1050+`

**验证**:
- `test_runner_call_projection_resolver_fails_closed_for_missing_manifest_ref` (line 944): signal 无 `manifest_ref` → `pytest.raises(HostDurableError, match="no manifest_ref")`
- `test_runner_call_projection_resolver_fails_closed_for_digest_mismatch` (line 984): descriptor digest 与 expected_digest 不匹配 → `pytest.raises(HostDurableError, match="digest mismatch")`
- `test_runner_call_projection_resolver_fails_closed_for_non_object_payload` (line 1048): payload JSON 不是 object → `pytest.raises(HostDurableError, ...)`

## 分层与架构边界检查

### durable payload/artifact helper 分层 — Pass

- `dayu/host/durable/payload.py`: `BoundedJsonPayloadWriteRequest` 与 `write_bounded_json_payload` 不接受任何 Engine/UI/Service 类型，只依赖 `dayu.host.durable.*` 与标准库。新增 public `PayloadKind.ARTIFACT_REF` enum member 为已有 enum 的正交扩展。
- `dayu/host/durable/artifact.py`: `read_artifact_bytes` 与 `delete_artifact_file` 只做文件系统操作 + containment/digest 校验，不写 SQLite，不访问 Host 业务状态。
- `dayu/host/durable/transaction.py`: `HostTransaction` 新增 `artifact_root`、`create_artifact_root` 属性，`HostTransactionRunner` 透传这两个参数。所有现有 `HostTransaction`、`HostTransactionRunner` 构造点已更新（transaction.py 内 2 处 + test_durable_transaction.py 内 3 处）。
- 无反向依赖：Engine contracts 不 import Host；Host 不 import Service/UI。
- 无跨层穿透：`run_input.py` 和 `engine_ingest.py` 彼此不 import，各自独立依赖 durable。

### secret retention — Pass

- projection body (`_runner_call_projection_body` / `_observed_runner_call_projection_body`) 仅包含 LLM-facing 字段：index、role、content、tool_call_id、tool_calls(name+arguments)。
- schema snapshot (`_selected_tool_schema_snapshot_body`) 仅包含 tool type、function.name、function.description、function.parameters。
- `_provider_state_projection` (run_input.py:4380-4387) 只保存 `state_digest: sha256({"thought_signature": ...})`，不保存明文 `thought_signature`。
- 无 provider Authorization/API key、raw provider request/response 或 provider headers 写入。

### payload descriptor schema — Pass

- 新增 payload descriptor kind: `runner_call_input_projection`、`selected_tool_schema_snapshot`（schema.py:238, 249）。
- 新增 schema version: `runner_call_input_projection.v1`、`selected_tool_schema_snapshot.v1`（schema.py:241, 252）。
- 新增 media type: `application/vnd.dayu.runner-call-input-projection+json`、`application/vnd.dayu.selected-tool-schema-snapshot+json`（schema.py:244-247, 255-258）。
- 既有 `TABLE_PAYLOAD_DESCRIPTORS`、`TABLE_SQLITE_PAYLOADS` schema 无变更。新增字段均为 descriptor metadata 中的 additive 字段，不破坏 existing descriptor 的读取。
- `RUNNER_CALL_INPUT_ASSEMBLED` hot payload 新增三个可选字段（`runner_call_projection_artifact_ref/digest/size_bytes`），旧 hot row 不包含这些字段时 resolver 在 ref 缺失时 fail closed。

### README/design 一致性 — Pass

- `docs/host/design.md` 已更新：
  - section 20: hot payload 字段表新增三行 projection ref/digest/size_bytes。
  - section 20: 明确 "complete hot payload 的 diagnostic 必须显式写 `status="complete"`，不得用 `null` 表达 complete"。
  - section 23.1: manifest body 字段表新增三行 projection ref/digest/size_bytes。
  - section 23.1: 修正 `tool_schema_snapshot_refs` 描述为 "selected tool schema snapshot ref / digest / size"。
  - section 23.1: 增加 Engine continuation 中 `runner_call_input_projection` 写入策略描述。
- `dayu/host/README.md`、`dayu/engine/README.md`、`tests/README.md` 的更新在本次 scope 外（初审时未要求更新这些文件），但 `docs/host/design.md` 的更新与实现一致。

## Findings

未发现实质性问题。

## 专项检查逐项 Pass/Fail

| 项目 | 状态 |
|------|------|
| DS-F1: 双端 projection payload 写入策略统一 | Pass |
| DS-F2: projection payload 按 inline 阈值冷热分离 | Pass |
| DS-F3: complete manifest hot payload diagnostic self-describing | Pass |
| DS-F4: resolver 支持 artifact JSON payload | Pass |
| 逐条 message digest cross-verify 测试 | Pass |
| resolver fail-closed 错误路径测试 | Pass |
| durable payload/artifact helper 分层 | Pass |
| secret retention | Pass |
| payload descriptor schema 兼容 | Pass |
| README/design 一致性 | Pass |
| 过度设计 | 无 |
| 类型问题 | 无 (pyright: 0 errors) |
| 反向依赖 | 无 |
| 胶水 seam | 无 |

## Open Questions

1. **`write_bounded_json_payload` → `write_sqlite_payload` 路径存在双重 canonical JSON 编码**：`_encode_bounded_json_payload` (payload.py:517) 已计算 canonical bytes + digest，但其后 `write_sqlite_payload` → `_encode_sqlite_payload` (payload.py:572) 再次执行 `canonical_json_dumps` 并重新计算 digest，仅凭 `expected_digest` 校验保证一致性。对 KB 级 payload 性能影响可忽略，不建议作为 finding，但若未来重构可考虑让 `write_sqlite_payload` 接受预计算 digest + bytes 的 "fast path"。
2. **`_write_selected_tool_schema_snapshot_payload` (run_input.py:4427-4470) 未使用 `write_bounded_json_payload`**：当前直接调用 `write_sqlite_payload`，自带 idempotency 检查。Codex fix artifact 明确说明 "schema snapshot 仍使用 SQLite JSON payload descriptor"，这是有意识的设计决策。若未来 tool schema 可能增长到超过阈值（例如 multi-thousand tool list），需考虑切换到 `write_bounded_json_payload`。
3. **cold JSONL schema evolution**：Tool Trace cold JSONL 中 `runner_call_projection_artifact_ref/digest/size_bytes` 为可选字段（可能为 null），cold JSONL consumer 需知晓这一约定。当前无 cold JSONL schema versioning 机制——这一点在初审 DS Residual Risk 中已记录，本轮未解决，但不属于本轮 scope。

## Residual Risk

- **既有 secret retention**: GAP artifact 发现的旧 `USER_INPUT_ACCEPTED.payload_json.effective_execution_config.runner_spec.headers` 中 Authorization header 明文仍存于 durable 中，不在本次 scope。
- **大 projection artifact 清理**: 大 projection 走 artifact 路径后，文件由 content-addressed `sha256/` namespace 管理；retention/purge 时需确保 artifact 文件与 SQLite descriptor 同步清理。当前 `delete_artifact_file` (artifact.py:167-197) 提供单文件删除能力，但批量 purge 逻辑未实现。
- **cold JSONL 新增字段**: 如上 Open Questions#3，cold JSONL consumer 需知晓三个可选字段可能为 null。
- **`write_bounded_json_payload` 双重编码**: 如上 Open Questions#1，当前无 correctness 风险，仅轻微性能浪费。
