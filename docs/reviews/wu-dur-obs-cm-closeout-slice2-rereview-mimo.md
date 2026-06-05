# WU-DUR-P01 Slice 2 Fix Re-Review - MiMo

## verdict

**pass**

## review scope

Fix gate re-review，基于 controller adjudication 接受的 S2-F1 / S2-F2 / S2-F3 三项 findings。复审 fix artifact、当前 workspace diff 中 fix 相关的 production / test / README 变更，以及 design.md 13.1 / 13.3 / 16 / 23.1 的 contract 对齐。

Fix 变更文件：
- `dayu/host/engine_ingest.py`：continuation `iteration_started` 写 canonical limited-signal manifest
- `dayu/host/tool_trace.py`：non-complete diagnostic 从 canonical typed diagnostic 读取
- `dayu/host/run_input.py`：ordinary path manifest writer 与 Engine 共享 schema constants
- `dayu/host/durable/schema.py`：manifest schema version / media type / descriptor kind 常量
- `tests/host/test_engine_ingest_mapping.py`：continuation canonical manifest 测试
- `tests/host/test_tool_trace_projection.py`：non-complete typed diagnostic 测试
- `tests/host/test_run_input_builder.py`：bounded manifest 与 manifest idempotency 测试
- `dayu/host/README.md`、`tests/README.md`：文档同步

## accepted fixes verification

### S2-F1：Engine-internal continuation iteration_started 写 canonical RUNNER_CALL_INPUT_ASSEMBLED

**已修复。**

直接证据：
- `engine_ingest.py` `_append_iteration_started_events`（diff line 77-107）：`iteration_started` 事件先于 generic preview mapping 处理。调用 `_find_runner_call_manifest_event` 查找匹配 manifest，不存在时调用 `_append_limited_runner_call_manifest_event` 写入 canonical fact。
- `_append_limited_runner_call_manifest_event`（diff line 109-155）：写入 `EventClass.CANONICAL_FACT` 的 `RUNNER_CALL_INPUT_ASSEMBLED`。manifest body 通过 `_limited_runner_call_manifest_body` 构造，diagnostic reason 为 `missing_projection_artifact`，`message_entries` 为空列表（Engine 无法提供 Host source/projector material）。
- `_limited_runner_call_manifest_body`（diff line 192-258）：包含 Host-owned `runner_call_index`、manifest identity fields、Engine-observed `message_count` / `role_sequence_digest`、bounded source refs、projector metadata。不包含完整 messages、prompt、compact material、memory snapshot、provider raw。
- manifest body 存为 `runner_call_input_manifest` payload descriptor，canonical hot payload 只存 scope + identity + ref + digest + diagnostic。
- 测试 `test_iteration_started_writes_limited_runner_call_manifest_for_continuation` 验证：`iteration_index=1` 产生 `RUNNER_CALL_INPUT_ASSEMBLED` canonical fact + `ITERATION_STARTED` preview，manifest hot payload 包含 `runner_call_kind=tool_result_continuation`、`validation_status=limited_signal`、typed diagnostic、`message_entries=[]`。
- 不是 preview-only：`event_class == EventClass.CANONICAL_FACT`。
- 不伪造 complete truth：diagnostic reason 为 `missing_projection_artifact`，`message_entries` 为空。

### S2-F2：Tool Trace non-complete diagnostic 从 canonical typed diagnostic 读取

**已修复。**

直接证据：
- `tool_trace.py` `_runner_call_diagnostic`（diff line 583-603）：读取 `validation_status` 与 `diagnostic` 字段。`complete` 状态返回标准化 None 字段结构。非 complete 时检查 `diagnostic` 是否为 Mapping，不是则 `raise HostDurableError`（fail closed）。从 diagnostic dict 读取 `status`、`reason`、`missing_atom_kind`、`missing_ref_kind`、`missing_ref`、`observed_count`、`expected_count`、`observed_digest`、`expected_digest`。
- `_required_text` / `_optional_int` 辅助函数（diff line 1042-1082）提供类型安全读取。
- 测试 `test_tool_trace_projects_limited_runner_call_manifest_diagnostic` 验证：`limited_signal` diagnostic 从 hot payload 的 `diagnostic` 字段读取，包含完整 typed fields（`missing_ref_kind=runner_call_projection_artifact`、`observed_count=3` 等），不硬编码 None。
- 测试 `test_tool_trace_projects_runner_call_manifest_signal` 验证：`complete` 状态返回标准化 None 字段结构。

### S2-F3：continuation validation 通过 canonical manifest / Tool Trace signal 可见

**已修复。**

直接证据：
- canonical manifest event 本身就是 `EventClass.CANONICAL_FACT`，存在于 EventLog 中，可通过 `event_type=RUNNER_CALL_INPUT_ASSEMBLED` 查询。
- preview payload 中 `runner_call_manifest_validation` 字段（`engine_ingest.py` `_preview_payload`，diff line 183-184）包含 validation summary，对 continuation 路径为 `limited_signal` 状态。
- Tool Trace 投影复制 manifest read-model signal（`tool_trace.py` `_extract_runner_call_trace`），包含 manifest ref/digest、message count、role digest、diagnostic。
- 测试 `test_iteration_started_writes_limited_runner_call_manifest_for_continuation` 验证 preview payload 中 `runner_call_manifest_validation.status == "limited_signal"`。

## Engine / Host boundary 验证

- Engine 侧（`engine_events.py`、`agent.py`）：`IterationStartedData` 只增加 Engine-owned `role_sequence_digest` / `runner_input_serializer_schema_version`。未添加 Host-owned `runner_call_index`、manifest ref、source refs、memory/compact/tool schema refs。✓
- Host limited manifest（`engine_ingest.py`）：不包含完整 messages、prompt、compact material、memory snapshot、provider raw request/response。`message_entries` 为空。source refs 只包含 Host 可证明的 event refs。✓
- Host ordinary manifest（`run_input.py`）：从同一 `messages` tuple 构造，message entries 包含 content digest 和 source refs，不内联完整 message text。✓
- schema 常量（`schema.py`）：`RUNNER_CALL_INPUT_MANIFEST_DESCRIPTOR_KIND` / `SCHEMA_VERSION` / `MEDIA_TYPE` 由 RunInputBuilder 和 Engine ingest 共用。✓

## runner_call_index / manifest lookup 验证

- `_next_runner_call_index` 按 `run_id` + `event_type=RUNNER_CALL_INPUT_ASSEMBLED` COUNT 计数，单调递增。✓
- `_find_runner_call_manifest_event`（engine_ingest 版本）：按 `run_id` 查询所有 manifest events，匹配 `attempt_id` / `execution_id` / `iteration_id`。`_runner_call_manifest_matches_iteration` 逻辑：`payload_iteration_id == iteration_id` 直接匹配；`payload_iteration_id is None and iteration_index == 0` 允许 ordinary manifest（iteration_id 为 None）匹配 iteration_index==0 的首次 iteration。这避免了把 continuation 误配到 ordinary first manifest。✓
- `_find_existing_runner_call_manifest_event`（run_input 版本）：按 `attempt_id` / `execution_id` 匹配，无 iteration 过滤。这是 ordinary path 的幂等保护——同一 attempt/execution 只写一次 manifest。✓
- 两个 `_find_*` 函数逻辑接近但用途不同（controller adjudication 已判定 MiMo F1 为不阻塞的 maintenance issue）。✓

## findings

无新 findings。

已知未阻塞项（来自 MiMo code review，controller 已判定不在 fix gate 范围）：
- `_find_runner_call_manifest_event` 在 run_input.py 与 engine_ingest.py 重复实现（MiMo F1，medium，maintenance issue）。
- `_runner_call_kind_and_trigger` 对 `start_reason="recovery"` 映射为 `post_compaction_dispatch` 精确性（MiMo F2，medium）。

## tests / pyright

- `pytest tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase3_tool_call.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py`：**155 passed in 1.07s**
- `pyright`：**0 errors, 0 warnings, 0 informations**
- `git diff --check`：clean

新增测试覆盖：
- `test_iteration_started_writes_limited_runner_call_manifest_for_continuation`：验证 continuation iteration 写 canonical limited-signal manifest。
- `test_runner_call_manifest_is_bounded_and_does_not_inline_messages`：验证大输入不完整内联到 manifest。
- `test_tool_trace_projects_runner_call_manifest_signal`：验证 complete 状态 Tool Trace signal。
- `test_tool_trace_projects_limited_runner_call_manifest_diagnostic`：验证 non-complete typed diagnostic projection。
- `test_noop_providers_only_create_runner_call_manifest_rows`：验证 manifest 写入 durable rows。

## remaining risks

- Continuation manifest 是 intentional limited-signal：Host ingest 无法从 Engine event contract 恢复完整 rendered messages / source refs / projector mapping。diagnostic `missing_projection_artifact` 明确记录该限制。后续 slice 若需要 continuation full manifest，需扩展 Engine event contract 或添加 broader production handoff。
- manifest 幂等写入（重复 ingest 同一 continuation iteration）的 `_find_runner_call_manifest_event` 按 iteration_id 匹配，重复 ingest 会返回已有 manifest event 而不写第二条。但无专用测试覆盖该路径。
- `_find_runner_call_manifest_event` 辅助函数重复实现是 maintenance issue，不在 fix gate 范围。

## ready for controller adjudication

**yes**
