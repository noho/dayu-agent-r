# WU-DUR-P01 Slice 2 Code Review - MiMo

## verdict

**pass-with-findings**

## review scope

未提交 workspace diff，覆盖以下文件：
- `dayu/engine/contracts/engine_events.py`：`IterationStartedData` 新增 `role_sequence_digest` / `runner_input_serializer_schema_version`；新增 `runner_role_sequence_digest()` 函数与 `RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION` 常量。
- `dayu/engine/agent.py`：`_AsyncAgent` 在 iteration_started emit 时计算 role digest。
- `dayu/engine/__init__.py`：公共 re-export。
- `dayu/host/run_input.py`：`RunnerCallManifestRecordInput` / `RunnerCallManifestRecorder` protocol / `DurableRunnerCallManifestRecorder`；`RunInputBuilder.build()` 写入 `RUNNER_CALL_INPUT_ASSEMBLED` canonical fact 与 manifest payload descriptor；manifest body 构造、message entries、projector metadata、source refs、digest 计算、runner_call_kind/trigger 分类、hot payload 构造。
- `dayu/host/engine_ingest.py`：preview payload 携带 Engine-owned role digest / schema version；`_runner_call_manifest_validation_summary()` 校验 Engine signal 与 Host manifest。
- `dayu/host/durable/schema.py`：新增 `RUNNER_CALL_INPUT_MANIFEST_DESCRIPTOR_KIND` 常量。
- `dayu/host/tool_trace.py`：`_extract_runner_call_trace()` / `_runner_call_trace_summary()` 复制 manifest read-model signal。
- 测试：`test_engine_event_contract.py`、`test_agent_phase3_tool_call.py`、`test_engine_ingest_mapping.py`、`test_run_input_builder.py`、`test_tool_trace_projection.py`。
- README：`dayu/engine/README.md`、`dayu/host/README.md`、`tests/README.md`。
- design.md 13.1 / 13.2 / 13.3 / 16 (Tool Trace runner-call signal) / 23.1 (Runner-call Input Assembly Manifest) 作为 review 基准。

## findings

### F1 - medium：`_find_runner_call_manifest_event` 在 `run_input.py` 与 `engine_ingest.py` 重复实现

- 文件：`dayu/host/run_input.py:3330-3374`，`dayu/host/engine_ingest.py:4351-4393`（行号基于 diff）
- 证据：两个函数逻辑几乎完全相同——按 `run_id` + `event_type` 查询 EventLog，遍历结果匹配 `attempt_id` / `execution_id`。区别仅在 `engine_ingest` 版本的 `run_id` 来自 `context.run.run_id`。
- 违反约束：AGENTS.md "数据处理、存储、工具调用职责必须分离，重复逻辑必须抽取"。
- 建议：抽取到 `dayu/host/durable/event_log.py` 或 `dayu/host/_event_payload.py` 作为共享 helper，两处调用方传入 `run_id` / `attempt_id` / `execution_id`。

### F2 - medium：`_runner_call_kind_and_trigger` 将 `start_reason="recovery"` 无条件映射为 `post_compaction_dispatch` / `context_compaction_completed`

- 文件：`dayu/host/run_input.py:4058-4064`（行号基于 diff）
- 证据：`if start_reason == "recovery" or record_input.fallback is not None: return (POST_COMPACTION_DISPATCH, CONTEXT_COMPACTION_COMPLETED)`。当 `start_reason="recovery"` 但 recovery 原因不是 context compaction（例如 attempt lost recovery），trigger reason `context_compaction_completed` 语义不准确。
- 设计基准：design.md 23.1 `RunnerCallTriggerReason` 表中 `context_compaction_completed` 语义为 "accepted compact 或 fallback permits next dispatch"。
- 实际影响：在 ordinary RunInputBuilder 路径中，`start_reason="recovery"` 通常确实源于 compaction recovery；但当前逻辑未区分 compaction recovery 与非 compaction recovery，可能产生不精确的 trigger reason。
- 建议：要么在 `RUN_STARTED` payload 中携带 recovery sub-reason，要么在此处使用更通用的 trigger reason（如新增 `host_recovery`），避免把非 compaction recovery 错误归类。

### F3 - low：`_projector_id_for_message` 使用 content prefix 匹配识别 memory session summary

- 文件：`dayu/host/run_input.py:3780-3781`（行号基于 diff）
- 证据：`if _message_content_text(message).startswith(_MEMORY_SESSION_SUMMARY_HEADER): return _PROJECTOR_ID_MEMORY`。依赖消息内容前缀 `"Session Summary Memory:"` 做 projector 分类，而非结构化标记。
- 风险：如果某条 SystemMessage 内容恰好以该前缀开头（例如引用或讨论该 header），会被误分类为 memory projector。
- 实际影响：低。RunInputBuilder 控制消息构造，实际触发概率极低。
- 建议：后续迭代考虑在 `SystemMessage` 上增加结构化 `source_kind` 标记，替代 content prefix 匹配。

### F4 - low：Tool Trace diagnostic 结构为简化硬编码 dict，未完全对齐 design.md typed shape

- 文件：`dayu/host/tool_trace.py:592-603`（行号基于 diff）
- 证据：`_runner_call_trace_summary` 中 diagnostic dict 将 `reason` / `missing_atom_kind` / `missing_ref_kind` / `missing_ref` / `observed_count` / `expected_count` / `observed_digest` / `expected_digest` 全部硬编码为 `None`，`consumer_boundary` 硬编码为 `"tool_trace_query"`。而 `engine_ingest.py` 的 validation summary 可以产生 `limited_signal` / `mismatch` 状态及具体 observed/expected 值。
- 原因：Tool Trace 从 canonical event hot payload 读取，而 hot payload 只存储 `validation_status`（来自 `_runner_call_manifest_hot_payload`），不存储完整 diagnostic。ingest 的 validation summary 写入的是 preview payload，不是 canonical hot payload。
- 影响：Tool Trace 的 diagnostic 只能表达 status，不能表达具体 mismatch 详情。这符合当前 Slice 2 的实现范围——canonical hot payload 按 design.md 23.1 只存 `validation_status`，完整 diagnostic 信息在 preview payload 中。
- 建议：后续 Slice 4 Tool Trace Reconstruction Signal Projection 应将 diagnostic detail 从 preview payload 或 manifest body 中抽取到 trace summary，而非仅依赖 canonical hot payload。

### F5 - low：projector purpose 覆盖不完整

- 文件：`dayu/host/run_input.py:3785-3794`（行号基于 diff）
- 证据：`_projector_purpose()` 只返回 `ordinary_run_input` 或 `post_compaction_input`。design.md 23.1 要求至少覆盖 `ordinary_run_input`、`tool_continuation_input`、`post_compaction_input`、`compactor_proposal_input`、`retry_replay_resume_input`、`forced_answer_input`、`length_continuation_input`。
- 原因：Slice 2 只覆盖 ordinary RunInputBuilder 路径，tool-loop / compactor / retry / forced-answer 路径在后续 slice。
- 影响：manifest projector purpose 对非 ordinary 路径不精确，但不影响 ordinary 路径正确性。
- 建议：后续 slice 扩展时补充对应 purpose 枚举值和分类逻辑。

### F6 - low：manifest bounded-size 测试断言阈值偏宽松

- 文件：`tests/host/test_run_input_builder.py`（test_runner_call_manifest_is_bounded_and_does_not_inline_messages）
- 证据：`assert len(manifest_text) < 5000` 对 20000 字符输入。阈值 5000 是经验值，但未验证 manifest 大小与输入大小的非线性关系（例如将输入翻倍后 manifest 是否仍 bounded）。
- 建议：可增加参数化测试，验证不同输入大小下 manifest 大小增长 bounded。

## tests / pyright 核验

- 测试：`source .venv/bin/activate && pytest tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase3_tool_call.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py` → **153 passed in 1.09s**
- pyright：`source .venv/bin/activate && pyright` → **0 errors, 0 warnings, 0 informations**
- 测试覆盖了：Engine role digest 锁定、Engine iteration_started 携带 digest 与 schema version、Host manifest 写入与 bounded 断言、ingest preview payload 校验、Tool Trace runner-call signal 投影。
- 缺失覆盖：manifest 幂等写入（重复调用 `record_runner_call_manifest`）、ingest validation summary mismatch 路径、tool_result_continuation / post_compaction_dispatch 路径的 manifest（属于后续 slice）。

## scope completeness judgment

Slice 2 的 exact changes 要求 "为每次 logical runner call 记录轻量、可校验的 input assembly manifest signal"。当前实现覆盖了 ordinary RunInputBuilder 路径（initial / follow-up / resume / post-compaction dispatch）。tool-loop continuation（Engine 内部 tool results 后的继续调用）只有 Engine-owned signal（`IterationStartedData.role_sequence_digest` / `message_count`），Host 侧无 source-ref-rich manifest writer。

**判断：可接受的 later-slice residual，不违反 Slice 2 stop condition。**

理由：
1. Slice 2 stop condition 是 "真实 runner call message_count 与 manifest message_count 不能一致时停止"——ordinary 路径满足该条件。
2. tool-loop continuation 不经过 `RunInputBuilder`，需要在 Engine continuation path 中独立实现 manifest 写入。这是架构上的合理分层：Host manifest writer 绑定到 `RunInputBuilder` 调用点，Engine continuation 路径的 Host manifest 写入是独立的 implementation concern。
3. Codex artifact 明确声明了该 residual，未掩盖 scope gap。
4. Slice 2 plan 的 "Host ingest 根据 accepted lifecycle context 生成 RUNNER_CALL_INPUT_ASSEMBLED" 对 tool-loop continuation 路径实际需要的是 ingest validation（已实现），而非 manifest 写入（需后续 slice）。

## Engine / Host boundary 验证

- Engine `IterationStartedData` 只包含 Engine-owned observations：`iteration_id`、`iteration_index`、`message_count`、`role_sequence_digest`、`runner_input_serializer_schema_version`。未包含 Host-owned `runner_call_index`、manifest ref、source refs。✓
- Host manifest 包含 Host-owned fields：`runner_call_index`、manifest refs/digests、source refs、projector metadata、compact/memory refs。✓
- Engine ingest 只做 validation summary（preview payload），不从 Engine event 伪造成 Host manifest truth。✓
- `_runner_role_sequence_digest` 使用 canonical UTF-8 `"\n".join(roles)` preimage，Engine 和 Host 共用同一函数。✓

## Manifest truth 验证

- `RUNNER_CALL_INPUT_ASSEMBLED` 是 `EventClass.CANONICAL_FACT`，无 Run/Attempt 状态副作用。✓
- 不驱动 recovery / memory / dispatch / lifecycle transition。✓
- `runner_call_index` 通过 `_next_runner_call_index()` 按 run_id 计数，单调递增。✓
- manifest body 存为 `runner_call_input_manifest` payload descriptor，canonical event hot payload 只存 scope + identity + ref + digest。✓

## Digest correctness 验证

- `role_sequence_digest`：`runner_role_sequence_digest(("system", "user"))` 的确定性断言存在于 `test_engine_event_contract.py`。✓
- `content_digest`：使用 `sha256_digest_json` 基于 `serializer_schema_version` + `role` + `content` + 可选 `reasoning_content_digest` / `tool_calls_digest`。确定性。✓
- `input_projection_digest`：基于 message entry 摘要 + projector metadata + source cursor refs 的 canonical JSON digest。确定性。✓
- `manifest_digest`：`sha256_digest_json(manifest_body)`。确定性。✓
- 无 ad-hoc string 拼接或不稳定 serialization。✓

## ready for controller adjudication

**yes**

pass-with-findings。6 个 findings 中 0 个 blocking、2 个 medium、4 个 low。medium findings（重复逻辑、recovery trigger reason 精确性）可在后续 slice 或 fix 中处理，不阻塞 Slice 2 accepted commit。scope completeness 判断为可接受 later-slice residual。
