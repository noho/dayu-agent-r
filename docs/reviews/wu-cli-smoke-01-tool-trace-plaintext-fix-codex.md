# wu-cli-smoke-01 Tool Trace 明文可审计性修复记录

## 结论

本轮修复了 Tool Trace 无法从 run / runner-call 追溯 LLM-facing 明文输入输出的 blocker。修复后，`RUNNER_CALL_INPUT_ASSEMBLED` hot payload 与 Tool Trace hot/cold 仍只保存 bounded ref / digest / summary；完整 runner input messages、selected tool schema full JSON、工具结果 payload 与 terminal final answer 通过 payload descriptor 按需 resolve。

真实 smoke 已验证：`dayu-cli prompt --ticker V '请调用可用工具获取当前时间，并说明当前分析对象。'` 成功调用 `get_current_time`，新增 resolver 能恢复 `# 当前时间`、`# 当前分析对象`、`V（Visa Inc.）`、工具调用/结果和 final answer。

## Root Cause

问题动机成立，严重性评估正确。根因不是 Tool Trace 查询参数错误，而是 bounded manifest 设计与 resolver / projection artifact 实现之间存在未完成项：

- RunInputBuilder 生成了真实 `AgentRunRequest.messages`，但 manifest entry 的 `projection_artifact_ref` / digest 固定为空。
- selected tool schema snapshot 只有 count / disable_tools 派生 ref，没有保存完整 LLM-facing schema JSON。
- Engine tool-result continuation 的真实 messages 只存在于 Engine run-local loop，Host 只能拿到 `message_count` / `role_sequence_digest`，因此第二轮 manifest 降级为 `limited_signal(missing_projection_artifact)`。
- Tool Trace 查询层只有 hot row / reconstruction signal 分页，没有从 ref/digest 解析 manifest、projection、schema、工具参数、工具结果和 terminal payload 的 public durable helper。

## 改动

- Engine `IterationStartedData` 新增 `input_projection`，以中性 dataclass 暴露本轮实际 Runner 输入 messages 的 role / content / tool call 参数，不包含 Host refs、provider headers、Authorization/API key 或 raw provider request。
- Host RunInputBuilder 写入：
  - `runner_call_input_projection` payload，保存完整 LLM-facing messages。
  - `selected_tool_schema_snapshot` payload，保存 selected tool schema full JSON。
  - manifest 只保存 projection / schema snapshot ref、digest、size 与 message digest/size/source refs。
- Host Engine ingest 在 tool-result continuation 中：
  - 若 Engine `input_projection` 完整，写 complete continuation manifest 与 projection payload。
  - 若 projection 缺失，保留旧的 limited diagnostic。
- Tool Trace projection 增加 runner-call projection ref/digest/size summary，但不内联明文。
- Tool Trace durable query helper 新增 resolver：
  - `resolve_runner_call_projection_from_signal`
  - `resolve_tool_trace_hot_row_payloads`
  - `read_tool_trace_json_payload`
- 更新测试覆盖 projection resolve、schema snapshot resolve、continuation complete manifest、工具参数/结果/final answer resolver。
- 更新设计与开发文档：`docs/engine/design.md`、`docs/host/design.md`、`dayu/engine/README.md`、`dayu/host/README.md`、`tests/README.md`。

## 验证

已执行并通过：

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_tool_trace_queries.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py
```

结果：`211 passed`。

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

结果：无输出，clean。

真实 smoke：

```bash
source .venv/bin/activate && dayu-cli prompt --ticker V '请调用可用工具获取当前时间，并说明当前分析对象。'
```

结果：成功调用 `get_current_time`，最终回答包含当前时间和 `V（Visa Inc.）`。

resolver 验证：

```bash
source .venv/bin/activate && python workspace/tmp/verify_tool_trace_resolver.py
```

结果：

```text
{'run_id': 'run-2bb53b743b894e43a977595bc1f6ff27', 'runner_call_count': 2, 'tool_trace_row_count': 7, 'projection_checks': 'ok', 'payload_checks': 'ok'}
```

## Residual Risks

- 本轮未实现完整 #70 analyzer CLI 或 #71 产品化诊断 UI，只提供可消费的 durable resolver helper。
- projection payload 已按 inline threshold 在 SQLite payload 与 artifact descriptor 间切换；schema snapshot 仍使用 SQLite JSON payload descriptor。
- reasoning delta 仍不纳入普通 Tool Trace 明文输出，符合本轮非目标。
- 真实 durable payload 中历史上可能已有 secret-bearing execution config；本轮新增 projection/snapshot 不写 provider Authorization/API key，但既有 secret retention / purge owner 仍需后续安全治理工作处理。
- `dayu-cli prompt --ticker V` 当前 CLI 仍要求 positional prompt；本轮真实 smoke 使用等价命令补充了 prompt 文本。

## Code Review Fix: Tool Trace Plaintext Accepted Findings

### Controller Findings Closure

- DS-F1 已修复：在 `dayu.host.durable.payload` 抽取 `BoundedJsonPayloadWriteRequest` 与 `write_bounded_json_payload`，RunInputBuilder 与 Engine ingest 的 runner-call projection payload 写入均复用同一 durable payload helper；两端仅保留各自 ref/id 派生规则，避免 payload 存储策略漂移。
- DS-F2 已修复：projection canonical JSON payload 先计算 canonical bytes 与 digest；小于等于 `payload_inline_threshold_bytes` 时写 SQLite payload，超过阈值时通过既有 `LocalArtifactStore` 与 `PayloadStore.write_payload_descriptor_for_artifact` 写 artifact descriptor。manifest / hot payload 仍只保存 ref、digest、size。
- DS-F3 已修复：complete manifest 的 EventLog hot payload `diagnostic` 现在写入显式 `{status: "complete", ...}` diagnostic object；manifest body 仍保留 complete `diagnostic: null`，不改变 cold manifest contract。
- DS-F4 已修复：`read_tool_trace_json_payload` 支持 `sqlite_payload` 与 `artifact_ref` 两类 descriptor；artifact 路径通过 `read_artifact_bytes` 做路径 containment、size 与 digest 校验后解析 JSON object。

### Residual Test Gaps Closure

- 已补 projection messages 与 manifest `message_entries` 逐条 `index`、`role`、`content_digest`、`content_size_bytes`、projection ref/digest cross-verify。
- 已补 resolver fail-closed 分支：signal 缺 manifest ref、projection digest mismatch、projection payload 非 JSON object。
- 已补 artifact JSON payload resolver 覆盖，验证 artifact projection payload 可恢复明文。

### 本轮新增/修改文件

- `dayu/host/durable/transaction.py`
- `dayu/host/durable/connection.py`
- `dayu/host/durable/artifact.py`
- `dayu/host/durable/payload.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/host/run_input.py`
- `dayu/host/engine_ingest.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_tool_trace_queries.py`
- `docs/host/design.md`
- `tests/README.md`
- `docs/reviews/wu-cli-smoke-01-tool-trace-plaintext-fix-codex.md`

### Code Review Fix 验证

定向新增/修改测试已通过：

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py::test_runner_call_manifest_is_bounded_and_does_not_inline_messages tests/host/test_engine_ingest_mapping.py::test_iteration_started_continuation_with_projection_writes_complete_manifest tests/host/test_tool_trace_queries.py::test_runner_call_projection_resolver_reads_artifact_projection_payload tests/host/test_tool_trace_queries.py::test_runner_call_projection_resolver_fails_closed_for_missing_manifest_ref tests/host/test_tool_trace_queries.py::test_runner_call_projection_resolver_fails_closed_for_digest_mismatch tests/host/test_tool_trace_queries.py::test_runner_call_projection_resolver_fails_closed_for_non_object_payload
```

结果：`6 passed`。

完整指定测试已通过：

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_tool_trace_queries.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py
```

结果：`215 passed`。

类型检查已通过：

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

diff 空白检查已通过：

```bash
git diff --check
```

结果：无输出。

真实 smoke resolver 验证已通过：

```bash
source .venv/bin/activate && python workspace/tmp/verify_tool_trace_resolver.py
```

结果：

```text
{'run_id': 'run-2bb53b743b894e43a977595bc1f6ff27', 'runner_call_count': 2, 'tool_trace_row_count': 7, 'projection_checks': 'ok', 'payload_checks': 'ok'}
```
