# Tool Trace 明文可审计性修复 Re-Review

## Scope

- Mode: current changes (unstaged workspace)
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-tool-trace-plaintext-rereview-mimo-20260707-210515.md`
- Included scope: DS findings (DS-F1~DS-F4) 修复验证，初审 artifacts 复核，补充测试覆盖检查
- Excluded scope: 其他分支改动
- Parallel review coverage: 无

## Verification Baseline

- pytest (受影响测试): `232 passed` (Controller 已复跑)
- pyright: `0 errors, 0 warnings, 0 informations` (Controller 已复跑)
- git diff --check: clean (Controller 已复跑)

## Findings

未发现实质性问题。

### DS-F1 关闭验证：projection payload 写入策略抽取

**状态：已关闭**

**证据**：

1. `dayu/host/durable/payload.py:92-109`：新增 `BoundedJsonPayloadWriteRequest` frozen dataclass，封装 `payload_ref`、`sqlite_payload_id`、`payload_json`、`media_type`、`metadata`、`expected_digest`。
2. `dayu/host/durable/payload.py:363-431`：新增 `write_bounded_json_payload()` 模块级函数，实现 inline 阈值判断逻辑。
3. `dayu/host/durable/payload.py:213-228`：`PayloadStore.write_bounded_json_payload()` 委托到模块级函数。
4. `dayu/host/run_input.py:4390-4424`：`_write_runner_call_projection_payload()` 调用 `payload_store.write_bounded_json_payload()`。
5. `dayu/host/engine_ingest.py:5190-5225`：`_write_runner_call_projection_payload()` 调用 `payload_store.write_bounded_json_payload()`。

**结论**：两端 projection payload 写入均复用同一 durable payload helper，仅保留各自 ref/id 派生规则。无胶水 seam，无反向依赖。

### DS-F2 关闭验证：projection payload size bound

**状态：已关闭**

**证据**：

1. `dayu/host/durable/payload.py:398-431`：`write_bounded_json_payload()` 实现 inline 阈值判断：
   - `encoded.payload_size_bytes <= transaction.payload_inline_threshold_bytes` 时写 SQLite payload
   - 超过阈值时通过 `LocalArtifactStore.write_artifact_bytes()` 写 artifact，再调用 `write_payload_descriptor_for_artifact()`
2. `dayu/host/durable/connection.py:50-57`：`HostDurableStore` 初始化时将 `artifact_root` 和 `create_artifact_root` 传入 `HostTransactionRunner`。
3. `tests/host/test_run_input_builder.py:485-561`：`test_runner_call_manifest_is_bounded_and_does_not_inline_messages` 设置 `payload_inline_threshold_bytes=21000`，验证大 prompt (20000+ 字符) 的 projection 走 artifact 路径：
   - `projection_descriptor.payload_kind is PayloadKind.ARTIFACT_REF`
   - `projection_descriptor.sqlite_payload_id is None`

**结论**：projection payload 按 inline 阈值在 SQLite payload 与 artifact descriptor 间切换。hot/cold trace 仍只保存 ref/digest/size，bounded。

### DS-F3 关闭验证：complete manifest diagnostic self-describing

**状态：已关闭**

**证据**：

1. `dayu/host/engine_ingest.py:5322-5348`：新增 `_manifest_hot_diagnostic()` 函数：
   - validation_status 不是 complete 时返回 manifest 原有 diagnostic
   - validation_status 是 complete 时返回显式 `{status: "complete", reason: None, observed_count, expected_count, observed_digest, expected_digest, consumer_boundary}` diagnostic object
2. `dayu/host/engine_ingest.py:5318`：hot payload 的 `"diagnostic"` 字段调用 `_manifest_hot_diagnostic(manifest)`。
3. `tests/host/test_engine_ingest_mapping.py:3667-3695`：`test_iteration_started_continuation_with_projection_writes_complete_manifest` 验证：
   - `hot_diagnostic["status"] == "complete"`
   - `hot_diagnostic["reason"] is None`

**结论**：complete manifest 的 EventLog hot payload `diagnostic` 现在写入显式 self-describing diagnostic object。manifest body 仍保留 `diagnostic: null`，不改变 cold manifest contract。

### DS-F4 关闭验证：resolver 支持 artifact JSON payload

**状态：已关闭**

**证据**：

1. `dayu/host/durable/tool_trace.py:447-484`：`read_tool_trace_json_payload()` 支持两类 descriptor：
   - `PayloadKind.SQLITE_PAYLOAD` → `_read_sqlite_payload_json()`
   - `PayloadKind.ARTIFACT_REF` → `_read_artifact_payload_json()`
2. `dayu/host/durable/tool_trace.py:521-546`：`_read_artifact_payload_json()` 调用 `read_artifact_bytes()` 做路径 containment、size 与 digest 校验后解析 JSON。
3. `dayu/host/durable/artifact.py:197-235`：新增 `read_artifact_bytes()` 函数，实现完整校验链：`validate_artifact_ref` → `_validate_published_artifact_relative_path` → `_ensure_contained` → `read_bytes` → `sha256_digest_bytes` → size 校验。
4. `tests/host/test_tool_trace_queries.py:844-920`：`test_runner_call_projection_resolver_reads_artifact_projection_payload` 验证 artifact projection payload 可恢复明文。

**结论**：resolver 支持 SQLite payload 和 artifact JSON payload，含路径/size/digest/JSON object 校验。

### 测试覆盖验证

**逐条 message digest cross-verify**：

1. `tests/host/test_run_input_builder.py:546-561`：`test_runner_call_manifest_is_bounded_and_does_not_inline_messages` 验证：
   - `len(messages) == len(manifest_entries)`
   - 逐条断言 `message["index"] == entry["index"]`、`message["role"] == entry["role"]`、`message["content_digest"] == entry["content_digest"]`、`message["content_size_bytes"] == entry["content_size_bytes"]`
   - 逐条断言 `entry["projection_artifact_ref"] == projection_ref`、`entry["projection_artifact_digest"] == projection_digest`

2. `tests/host/test_engine_ingest_mapping.py:3720-3735`：`test_iteration_started_continuation_with_projection_writes_complete_manifest` 验证 continuation 路径的逐条 cross-verify。

**resolver fail-closed 错误路径**：

1. `tests/host/test_tool_trace_queries.py:922-960`：`test_runner_call_projection_resolver_fails_closed_for_missing_manifest_ref` 验证 signal 缺 manifest ref 时抛出 `HostDurableError("no manifest_ref")`。
2. `tests/host/test_tool_trace_queries.py:962-1018`：`test_runner_call_projection_resolver_fails_closed_for_digest_mismatch` 验证 projection descriptor digest 不匹配时抛出 `HostDurableError("descriptor digest mismatch")`。
3. `tests/host/test_tool_trace_queries.py:1020-1078`：`test_runner_call_projection_resolver_fails_closed_for_non_object_payload` 验证 projection payload 不是 JSON object 时抛出 `HostDurableError("must be object")`。

**artifact JSON payload resolver**：

`tests/host/test_tool_trace_queries.py:844-920`：`test_runner_call_projection_resolver_reads_artifact_projection_payload` 验证 artifact 形式的 projection payload 可恢复明文。

### 架构合规性验证

1. **Host durable 分层**：`BoundedJsonPayloadWriteRequest` 和 `write_bounded_json_payload` 位于 `dayu/host/durable/payload.py`，是 PayloadStore 的公共 primitive，符合 Host durable 分层。
2. **不保存 secrets**：新增 projection/snapshot 不写 provider Authorization/API key。`_provider_state_projection()` 对 `thought_signature` 仅保存 sha256 digest。
3. **不破坏 existing payload descriptor schema**：新增 `PayloadKind.ARTIFACT_REF` 路径复用既有 `write_payload_descriptor_for_artifact()`，descriptor 表结构无变化。
4. **无过度设计**：新增类型均为 frozen dataclass + slots，字段最小化。
5. **无 Any/object 类型问题**：所有新增函数均有完整类型标注。

## Open Questions

无。

## Residual Risk

1. **Retention/purge owner 归属**：projection payload 与 schema snapshot payload 的 retention/purge owner 归属哪个 issue/WU？建议归入 #43/#78/WU-RET-03。
2. **`_provider_state_projection` 的 thought_signature digest 安全性**：若 `thought_signature` 本身是敏感材料，仅做 sha256 可能通过字典攻击恢复短签名。建议确认熵级别。
3. **大 projection 性能**：极端长对话下 projection payload 可达 MB 级，未被性能测试覆盖。
4. **Cold JSONL schema evolution**：hot row 新增 `runner_call_projection_artifact_ref/digest/size_bytes` 三个可选字段，cold JSONL consumer 需知晓这些字段可能为 null。

## 结论

**Pass**。DS-F1、DS-F2、DS-F3、DS-F4 均已关闭，补充测试覆盖逐条 message digest cross-verify 和 resolver fail-closed 错误路径。新增 durable payload helper 符合 Host durable 分层，无阻断问题。
