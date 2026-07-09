# Code Review: Tool Trace 明文可审计性修复

## Scope

- Mode: current changes (unstaged workspace)
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-tool-trace-plaintext-review-ds.md`
- Included scope: `dayu/engine/contracts/engine_events.py`, `dayu/engine/agent.py`, `dayu/host/run_input.py`, `dayu/host/engine_ingest.py`, `dayu/host/tool_trace.py`, `dayu/host/durable/tool_trace.py`, `dayu/host/durable/schema.py`, `docs/engine/design.md`, `docs/host/design.md`, `dayu/engine/README.md`, `dayu/host/README.md`, `tests/README.md`, `tests/host/test_run_input_builder.py`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_tool_trace_queries.py`
- Excluded scope: 其他未在 scope 中列出的 workspace 文件（它们属于当前分支的其他 feature work，不在本次 Tool Trace 明文修复 scope 内）
- Parallel review coverage: 无（单人逐行走读）

## Verification Baseline

- pyright: `0 errors, 0 warnings, 0 informations`
- pytest (受影响的 test files): `176 passed in 1.49s`
- git diff --check: clean

## Findings

### 1-未修复-中-run_input.py 与 engine_ingest.py 中 projection payload 写入逻辑重复

- **入口/函数**: `_write_runner_call_projection_payload` (两处)
- **文件(行号)**: `dayu/host/run_input.py:4395-4431` 与 `dayu/host/engine_ingest.py:5190-5231`
- **输入场景**: 每次写入 runner-call projection payload 时触发
- **实际分支**: 两处都执行相同的幂等写入逻辑：读取已有 descriptor、校验 digest 一致性、通过 `PayloadStore.write_sqlite_payload` 写入 SQLite payload
- **预期行为**: 复用同一实现，避免未来修改一侧而忘记同步另一侧
- **实际行为**: 两个模块拥有近乎相同的 `_write_runner_call_projection_payload`、`_runner_call_projection_payload_ref`、`_runner_call_projection_sqlite_payload_id`、`_runner_call_projection_id` 四函数。唯一差异是 separator 字符（run_input 用 `-`，engine_ingest 用 `:`）以及写入方 prefix 常量命名不同
- **直接证据**: 对比 `run_input.py:4395-4431` 与 `engine_ingest.py:5190-5231`，两个 `_write_runner_call_projection_payload` 函数体除 prefix 变量名外完全一致；`run_input.py:4703-4740` 与 `engine_ingest.py:5338-5378` 同理
- **影响**: 未来修改 payload 写入行为（例如增加 size 阈值检查、切换 artifact 写入、添加 retention metadata）时，必须同步修改两处，容易产生单侧遗漏回归
- **建议改法和验证点**: 评估是否可提取为 `_event_payload` 模块的公共 helper（传入 prefix/separator 作为参数），或至少在两处添加交叉引用注释提醒同步。该重复不违反 AGENTS.md 的"禁止胶水 seam"约束——公共 payload 写入 helper 是合理的公共基础设施，不是为兼容旧代码而设的 seam。若决定保持现状，至少应在两处 docstring 中标注另一处存在重复实现
- **修复风险（低）**: 提取公共 helper 仅影响这两处调用；需保证 separator 差异继续生效
- **严重程度（中）**

### 2-未修复-中-projection payload 无 size bound 检查

- **入口/函数**: `_runner_call_projection_body` / `_write_runner_call_projection_payload`
- **文件(行号)**: `dayu/host/run_input.py:4273-4324`、`dayu/host/engine_ingest.py:4691-4748`
- **输入场景**: 长对话（多轮 tool call）、大 system prompt（多 scene section）、大 tool result 内容
- **实际分支**: projection body 直接包含所有 messages 的完整 `content` 字段，不经任何 size 检查即写入 SQLite payload
- **预期行为**: 与工具参数、manifest body 一致，projection payload 超过阈值时应走 artifact（文件系统）而非 SQLite inline payload；或至少记录 projection size 并标记 risk
- **实际行为**: 无论 projection 多大，一律写入 SQLite payload。SQLite payload 本身无硬上限，但大 payload 会影响 vacuum/backup 性能，且与设计文档 "manifest canonical JSON 字节数小于等于 `payload_inline_threshold_bytes` 时可以写 SQLite payload，超过阈值必须写 artifact root" 的通用冷热分离规则不完全一致
- **直接证据**: `_runner_call_projection_body` (run_input.py:4276) 无条件组合所有 messages 到单个 JSON object；`_write_runner_call_projection_payload` (run_input.py:4395) 通过 `SQLitePayloadWriteRequest` 直接写入，无 `payload_inline_threshold_bytes` 判断分支
- **影响**: 极端长对话（数十轮 tool call、大量 tool result 注入）下 projection 可达 MB 级，SQLite 性能下降；与设计文档 bounded 原则有偏差
- **建议改法和验证点**: 在 `_write_runner_call_projection_payload` 中添加 size check，超过 `payload_inline_threshold_bytes` 时走 artifact descriptor 路径；或至少在 manifest 中增加 `projection_storage_kind` 字段标记当前为 sqlite/artifact。该建议可 deferred 到 payload policy / retention 统一治理时一并实施
- **修复风险（中）**: 引入 artifact 路径涉及文件系统写入、atomic rename、digest 校验等额外复杂度
- **严重程度（中）**

### 3-未修复-低-`_manifest_optional_diagnostic` 语义与 hot payload consumer 预期存在微妙不一致

- **入口/函数**: `_runner_call_manifest_hot_payload` → `_manifest_optional_diagnostic`
- **文件(行号)**: `dayu/host/engine_ingest.py:5324`（调用侧）、`dayu/host/engine_ingest.py:6062-6078`（定义侧）
- **输入场景**: complete continuation manifest（projection 存在，`manifest["diagnostic"]` 为 `None`）
- **实际分支**: `_manifest_optional_diagnostic` 返回 `None`，hot payload 的 `"diagnostic"` 字段为 `None`
- **预期行为**: 行为正确——`_runner_call_payload_diagnostic` (engine_ingest.py:5958) 通过先检查 `validation_status` 再 fallback 到 `diagnostic` 字段来处理此情况。但 hot payload 中 `diagnostic=None` 在语义上与传统 `diagnostic={status:"complete", ...}` 不同，直接读取 hot payload 而不走 `_runner_call_payload_diagnostic` 的 consumer 可能将 `None` 误解为"未提供 diagnostic"而非"complete"
- **直接证据**: engine_ingest.py:5324 `"diagnostic": _manifest_optional_diagnostic(manifest)` 对 complete manifest 返回 `None`；engine_ingest.py:5970-5973 通过 `status == "complete"` 分支正确处理；但 Tool Trace projection 侧 (`dayu/host/tool_trace.py:708`) 直接使用 `hot_payload["diagnostic"]`——它依赖 `_runner_call_payload_diagnostic` 的上游保证
- **影响**: 当前所有已知 consumer 均通过 `_runner_call_payload_diagnostic` 读取，无实际 bug。但 future consumer 若直接读取 hot payload `diagnostic` 字段，可能对 `None` 做错误分类
- **建议改法和验证点**: 可选：让 complete manifest 的 `diagnostic` 在 hot payload 中写为显式 `{status: "complete"}` synthetic object 而非 `None`，保证 hot payload self-describing
- **修复风险（低）**: 改动仅影响 hot payload 字段值，不改变 manifest body
- **严重程度（低）**

### 4-未修复-低-resolver 仅支持 SQLite payload，不支持 artifact payload

- **入口/函数**: `read_tool_trace_json_payload`
- **文件(行号)**: `dayu/host/durable/tool_trace.py:464-465`
- **输入场景**: projection / schema snapshot payload 以 artifact 而非 SQLite 方式存储
- **实际分支**: `if descriptor.payload_kind is not PayloadKind.SQLITE_PAYLOAD: raise HostDurableError(...)`
- **预期行为**: 目前所有 payload 均以 SQLite 方式写入，此限制实际上不会触发
- **实际行为**: 若未来引入 artifact-based payload（例如大 projection 外移），resolver 直接 fail，不给 caller 恢复路径
- **直接证据**: `tool_trace.py:464-465` 的显式 guard
- **影响**: 与 residual risk 明确记录一致——"大 payload 转 artifact 的策略仍由后续 payload policy / retention 工作统一治理"。当前不是 bug，但作为 #70/#71 前置依赖，应在此 guard 处留下明确的 TODO/issue 引用
- **建议改法和验证点**: 在 guard 处添加注释引用未来的 artifact resolver 工作项；或至少 error message 中包含 `payload_ref` 帮助排障
- **修复风险（低）**: 仅添加注释，无代码行为变更
- **严重程度（低）**

## 专项检查逐项 Pass/Fail

### 1. Host/Engine 分层：Pass

- Engine `input_projection` (`dayu/engine/contracts/engine_events.py:74-91`) 仅包含 `index`、`role`、`content`、`tool_call_id`、`tool_calls`（名称+参数）。不含 Host refs、manifest ref、source refs、memory/compact refs、provider headers、Authorization/API key 或 raw provider request/response
- Engine `_runner_input_projection` (`dayu/engine/agent.py:260-273`) 从 `AgentMessage` 投影，不访问任何 Host 状态
- Host `_provider_state_projection` (`dayu/host/run_input.py:4350-4367`) 对 Gemini `thought_signature` 仅保存 sha256 digest，不保存明文
- Engine-observed 路径 `_observed_projection_message` (`dayu/host/engine_ingest.py:4761-4792`) 不包含 provider_state
- Residual risk: 若未来 `AgentMessage` 新增携带 secret 的字段，`_runner_input_projection` 的 match-case 不会自动投影（`assert_never` 在新增 variant 时会 fail），但需人工确保新增分支不引入 secret

### 2. Hot payload / Cold Tool Trace bounded：Pass

- ordinary manifest hot payload (`dayu/host/run_input.py:4676-4694`) 只保存 `runner_call_projection_artifact_ref` / `digest` / `size_bytes`，不内联明文
- continuation manifest hot payload (`dayu/host/engine_ingest.py:5279-5326`) 同样只保存 ref/digest/size
- Tool Trace projection (`dayu/host/tool_trace.py:705-728`) 仅复制可选 ref/digest/size 字段到 hot row，不内联大明文
- 已有测试 `test_runner_call_manifest_is_bounded_and_does_not_inline_messages` (`tests/host/test_run_input_builder.py:517`) 验证大 prompt 不进 manifest；本次改动保持该断言成立并增加了 projection resolve 验证
- Residual risk: 无

### 3. runner_call_input_projection payload 完整性：Pass

- ordinary run: `DurableRunnerCallManifestRecorder` (`dayu/host/run_input.py:806-833`) 在 manifest 写入前先写 projection payload + schema snapshot payload，manifest 中记录 ref/digest
- tool-result continuation: `_append_limited_runner_call_manifest_event` (`dayu/host/engine_ingest.py:2716-2792`) 在 Engine 提供完整 projection 时写 projection payload，否则降级为 limited_signal
- 已有测试：
  - `test_runner_call_manifest_is_bounded_and_does_not_inline_messages` (`tests/host/test_run_input_builder.py:517`) 验证 projection 可 resolve 且 content digest 匹配
  - `test_iteration_started_continuation_with_projection_writes_complete_manifest` (`tests/host/test_engine_ingest_mapping.py:3568`) 验证 continuation complete manifest
- Residual risk: projection message content 与 manifest `message_entries` 的 content_digest 一致性未在测试中逐条 cross-verify（仅验证了最后一条 message）；建议补充完整 cross-verify

### 4. selected_tool_schema_snapshot 安全性：Pass

- `_tool_schema_json` (`dayu/host/run_input.py:4503-4526`) 仅投影 OpenAI function-call 风格字段：type、function.name、function.description、function.parameters
- 不包含 provider-specific headers、API keys、raw request body、tool implementation details 或 provider raw configuration
- schema snapshot 在无工具时返回 `None`，manifest `tool_schema_snapshot_refs` 为空
- 已有测试 `test_tool_enabled_manifest_resolves_selected_schema_snapshot` (`tests/host/test_run_input_builder.py:702`) 验证 snapshot 可 resolve 且包含预期 tool name
- Residual risk: 若未来 ToolSchema 增加 provider raw config 字段，`_tool_schema_json` 需显式排除

### 5. Tool Trace resolver API 完整性：Pass

- `resolve_runner_call_projection_from_signal` (`dayu/host/durable/tool_trace.py:369-405`) 从 signal 恢复 manifest → projection → schema snapshot，digest 逐级校验
- `resolve_tool_trace_hot_row_payloads` (`dayu/host/durable/tool_trace.py:408-439`) 从 hot row 恢复 source EventLog payload + descriptor payload，覆盖 TOOL_CALL_REQUESTED（工具参数）、TOOL_RESULT_ACCEPTED（工具结果 payload）、RUN_SUCCEEDED（terminal final answer）
- `read_tool_trace_json_payload` (`dayu/host/durable/tool_trace.py:442-478`) 提供底层 payload 读取+digest 校验
- 缺失时行为：manifest 无 projection ref → `HostDurableError("runner-call manifest has no projection artifact ref")`；payload descriptor 缺失 → `HostDurableError("tool trace payload descriptor is missing")`；digest 不匹配 → `HostDurableError("tool trace payload descriptor digest mismatch")`
- 已有测试：
  - `test_runner_call_projection_resolver_reads_manifest_projection_and_schema` (`tests/host/test_tool_trace_queries.py:661`) 验证完整 resolve 链路
  - `test_tool_trace_row_resolver_reads_args_result_and_final_answer` (`tests/host/test_tool_trace_queries.py:780`) 验证工具参数/结果/final answer
- Residual risk: 未测试 resolver 在 manifest ref 缺失、digest mismatch、payload 非 JSON object 时的错误路径

### 6. 第二轮 tool-result continuation 不再无条件 missing_projection_artifact：Pass

- `_append_limited_runner_call_manifest_event` (`dayu/host/engine_ingest.py:2747-2764`) 通过 `_has_complete_observed_input_projection(data)` 判断 Engine 是否提供完整 projection
- 有 projection → 写 complete manifest（`diagnostic=None`，`validation_status="complete"`）
- 无 projection → 保留旧 limited diagnostic（`status="limited_signal"`, `reason="missing_projection_artifact"`）
- `_resolution_from_limited_manifest_event` (`dayu/host/engine_ingest.py:5841-5873`) 正确计算 `continuation_limited_signal = (status != "complete")`
- 已有测试 `test_iteration_started_continuation_with_projection_writes_complete_manifest` (`tests/host/test_engine_ingest_mapping.py:3568`) 验证 complete path
- 已有测试 `test_iteration_started_writes_limited_runner_call_manifest_for_continuation` (`tests/host/test_engine_ingest_mapping.py:3563`) 验证 limited path（旧行为保持）
- Residual risk: 无

### 7. 过度设计 / schema 兼容包袱 / 反向依赖 / Any/object / LLM-facing 文本 / secret retention：Pass（附注）

- 无过度设计：新增类型均为 frozen dataclass + slots，字段最小化，无多余抽象层
- 无 schema 兼容包袱：新增 schema version 常量直接为 `v1`，未保留旧版本兼容逻辑
- 无反向依赖：Engine 不 import Host 模块；Host 通过 Engine contracts 读取 `input_projection`
- 无 Any/object 类型问题：所有新增函数均有完整类型标注
- LLM-facing 文本：`RunnerInputMessageProjection` / `RunnerInputToolCallProjection` 的字段名（index、role、content、tool_call_id、name、arguments）自解释，符合 LLM-facing 文本约束
- secret retention：本次新增的 projection / schema snapshot 不写 provider Authorization/API key；旧 durable payload 中已有 secret-bearing execution config（见 GAP artifact 第 51 行），但那是既有问题，不在本次 scope
- 附注：`_provider_state_projection` (`dayu/host/run_input.py:4350-4367`) 对 `thought_signature` 做 sha256 digest 是正确的脱敏设计

### 8. 测试覆盖 root cause 与边界：Pass（附注）

- 已覆盖核心路径：
  - ordinary manifest projection resolve + content digest cross-verify (`test_runner_call_manifest_is_bounded_and_does_not_inline_messages`)
  - schema snapshot resolve (`test_tool_enabled_manifest_resolves_selected_schema_snapshot`)
  - continuation complete manifest (`test_iteration_started_continuation_with_projection_writes_complete_manifest`)
  - projection + schema snapshot resolver (`test_runner_call_projection_resolver_reads_manifest_projection_and_schema`)
  - tool args/result/final answer resolver (`test_tool_trace_row_resolver_reads_args_result_and_final_answer`)
  - noop provider 新增 payload descriptor counting (`test_noop_providers_create_manifest_and_projection_payloads`)
- 未覆盖的边界（已在 Residual Risk 中记录）：
  - resolver 错误路径（manifest ref 缺失、digest mismatch、payload 非 JSON object）
  - projection message content 与 manifest message_entries 的逐条 content_digest cross-verify
  - very large projection（MB 级）的写入/读取性能
  - retention / purge 后 resolver 返回 unavailable/redacted 的语义

## Open Questions

1. projection payload 与 schema snapshot payload 的 retention / purge owner 归属哪个 issue/WU？GAP artifact 建议归入 #43/#78/WU-RET-03，但修复 artifact 中未明确引用。
2. `_provider_state_projection` 中对 Gemini `thought_signature` 做 sha256 是否足够？若 `thought_signature` 本身是敏感材料（可用于重放或伪造 provider 请求），仅做 digest 仍可能通过字典攻击恢复短签名。建议确认 `thought_signature` 的熵级别。
3. 大 projection（MB 级）转 artifact 的阈值 `payload_inline_threshold_bytes` 是否与 manifest body 共用同一阈值，还是需要独立阈值？

## Residual Risk

- **Resolver 错误路径未测试**: manifest ref 缺失、digest mismatch、payload 非 JSON object 时 resolver 的错误行为缺少专项测试
- **Projection content digest cross-verify 不完整**: 当前测试仅验证最后一条 message 的 content_digest 一致性，未逐条验证所有 messages
- **大 payload 性能**: 极端长对话下 projection payload 可达 MB 级，未被性能测试覆盖
- **Artifact-based payload 路径缺失**: 当前 resolver 仅支持 SQLite payload；未来引入 artifact 存储时 resolver 需一并升级
- **Secret retention 既有问题**: GAP artifact 发现的旧 `USER_INPUT_ACCEPTED.payload_json.effective_execution_config.runner_spec.headers` 中 Authorization header 明文仍存于 durable 中，不在本次 scope 但属于不可 defer 太久的风险
- **Tool Trace cold JSONL 中新增字段的 schema evolution**: hot row 新增 `runner_call_projection_artifact_ref/digest/size_bytes` 三个可选字段，cold JSONL consumer 需知晓这些字段可能为 null；当前无 cold JSONL schema versioning 机制
