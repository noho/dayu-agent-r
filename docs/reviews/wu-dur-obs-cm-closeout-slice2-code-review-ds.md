# WU-DUR-P01 Slice 2 Code Review — AgentDS

## verdict

**fail** — 1 项 blocking finding 需要 controller adjudication；4 项 medium findings 需要 fix 或计划调整。

## review scope

审查对象：未提交 workspace diff（当前 branch `phaseflow/wu-dur-obs-cm-closeout`），以及 Codex 撰写的 implementation artifact `docs/reviews/wu-dur-obs-cm-closeout-slice2-implementation-codex.md`。

设计真源：
- `docs/host/design.md` 13.1 Payload 存储、13.2 Canonical Event 最小集合、13.3 Canonical Event Contract Matrix（含 `RUNNER_CALL_INPUT_ASSEMBLED` hot payload 与状态副作用）、14.1 Tool Trace Hot/Cold Storage runner-call signal contract、23.1 Runner-call Input Assembly Manifest（含 `RunnerCallInputAssemblyManifest` 字段表、message entry、projector metadata、RunnerCallKind/RunnerCallTriggerReason 枚举、manifest size-boundary 不变量）。
- `docs/host/wu-dur-obs-cm-closeout-plan.md` Slice 2 Exact Changes、Invariants、Stop Condition。

变更文件：
- `dayu/engine/contracts/engine_events.py`：新增 `RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION`、`IterationStartedData` 增加 `role_sequence_digest` / `runner_input_serializer_schema_version`、新增 `runner_role_sequence_digest()` 函数。
- `dayu/engine/agent.py`：Engine 在 runner call start 计算并传入 role digest 和 serializer schema version。
- `dayu/engine/__init__.py`：重新导出新增符号。
- `dayu/host/run_input.py`：新增 `RunnerCallManifestRecordInput`、`DurableRunnerCallManifestRecorder`、manifest body/hot payload/descriptor 构造链路、message entry/projector metadata/digest 计算函数。
- `dayu/host/engine_ingest.py`：preview payload 扩展 `role_sequence_digest`、`runner_input_serializer_schema_version`；新增 `_runner_call_manifest_validation_summary` / `_find_runner_call_manifest_event` / `_optional_payload_int` / `_optional_payload_text`。
- `dayu/host/durable/schema.py`：新增 `RUNNER_CALL_INPUT_MANIFEST_DESCRIPTOR_KIND` 常量。
- `dayu/host/tool_trace.py`：新增 `RUNNER_CALL_INPUT_ASSEMBLED` 进入 canonical event types、新增 `_extract_runner_call_trace` / `_runner_call_trace_summary`、新增 `_optional_int`。
- 测试：`tests/engine/test_engine_event_contract.py`、`tests/engine/test_agent_phase3_tool_call.py`、`tests/host/test_engine_ingest_mapping.py`、`tests/host/test_run_input_builder.py`、`tests/host/test_tool_trace_projection.py`。
- README：`dayu/engine/README.md`、`dayu/host/README.md`、`tests/README.md`。

## findings

### finding-1 (blocking): Slice 2 工具循环 continuation manifest 未实现 — plan vs implementation scope gap

**文件：** `dayu/host/engine_ingest.py:4286-4350`（`_runner_call_manifest_validation_summary` 与 `_find_runner_call_manifest_event`）

**证据：**

Plan Slice 2 Exact Changes 明确要求：
> Engine tool-loop continuation / fallback / continuation call 通过 Engine event 暴露 iteration/message_count/role digest；Host ingest 根据 accepted lifecycle context 生成 `RUNNER_CALL_INPUT_ASSEMBLED` 与 manifest refs/digests。

Codex implementation artifact 自述：
> Engine ingest validates only against committed Host manifest signal. It does not write a manifest from Engine observations because Engine lacks Host source refs and projector metadata.

当前实现中：
1. `RunInputBuilder` → `DurableRunnerCallManifestRecorder.record_runner_call_manifest()` 只为 **ordinary dispatch**（initial/follow-up）写入 `RUNNER_CALL_INPUT_ASSEMBLED` canonical event。
2. Engine `iteration_started` 事件承载 Engine-owned `role_sequence_digest` 与 `message_count`。
3. `_runner_call_manifest_validation_summary()` 在 ingest 中对工具循环 continuation 的 Engine iteration_started 调用，查找已有 manifest。若未找到（工具循环 continuation 当前无 manifest），返回 `limited_signal`，但 **不生成** `RUNNER_CALL_INPUT_ASSEMBLED`。
4. `Ingest` 的 `_preview_payload` 写入的是 `EventClass.PREVIEW`（非 `CANONICAL_FACT`），preview 不进入 EventLog canonical truth、不进入 Tool Trace projection、不进入 manifest 复算。

**与 plan stop condition 关系：**

Stop condition 是 "真实 runner call message_count 与 manifest message_count 不能一致时停止"。对 ordinary 路径该条件已通过；但对工具循环 continuation，因为没有 manifest，Engine `message_count` 只能与无 manifest 的 preview `limited_signal` 中的 `observed_count` 比较——这不是 plan 要求的 "manifest message_count" 对齐。

**判断：**

这不是 "later-slice residual"。Plan Slice 2 的目标是 "为**每次** logical runner call 记录轻量、可校验的 input assembly manifest signal"（plan 行 459）。工具循环 continuation 是 logical runner call，是 Slice 2 的 scope 内交付。Slice 2 exact changes 的三句话是 AND 关系（Engine contract 加字段 AND Host RunInputBuilder 生成 ordinary manifest AND Host ingest 生成工具循环 continuation manifest），其中第三项未实现。

但这也不是必须在本次 review gate 前补齐的完全阻塞——当前 Engine 已经暴露了 role_sequence_digest 和 message_count，Host 有 `_runner_call_manifest_validation_summary` 的校验框架，补齐工具循环 continuation manifest 写入只需要在 ingest 中增加 descriptor/manifest 构造逻辑。建议 controller 裁决以下二选一：
- **Option A**：在本 slice 内补齐工具循环 continuation manifest 写入（在 engine_ingest 中对无 manifest 的工具循环 iteration 生成 manifest 与 canonical event）。
- **Option B**：将工具循环 continuation manifest 显式调整为 Slice 2.5 或 Slice 4 的前置微交付（因为 Slice 4 Tool Trace signal 需要消费 manifest），同时在 plan 和 control doc 中记录该 scope 调整。

### finding-2 (medium): Tool Trace diagnostic 结构仅部分实现 — 永远不会生成非 None 的 diagnostic 细节

**文件：** `dayu/host/tool_trace.py:573-595`（`_runner_call_trace_summary` 的 `"diagnostic"` 块）

**证据：**

```python
"diagnostic": {
    "status": _optional_text(payload, _FIELD_VALIDATION_STATUS),
    "reason": None,               # 硬编码
    "missing_atom_kind": None,    # 硬编码
    "missing_ref_kind": None,     # 硬编码
    "missing_ref": None,          # 硬编码
    "observed_count": None,       # 硬编码
    "expected_count": None,       # 硬编码
    "observed_digest": None,      # 硬编码
    "expected_digest": None,      # 硬编码
    "consumer_boundary": "tool_trace_query",
},
```

根据 design.md 14.1（`RunnerCallReconstructionDiagnostic` contract）：当 status 非 `complete` 时，`reason` 必填，`observed_count`/`expected_count` 对应 mismatch 场景必填，`missing_atom_kind`/`missing_ref_kind` 对应 limited_signal 场景必填。当前 Trace 总是将这些字段硬编码为 `None`。

目前不会触发：因为 `RUNNER_CALL_INPUT_ASSEMBLED` canonical event 的 `validation_status` 总是 `"complete"`（由 `DurableRunnerCallManifestRecorder` 写入时固定）。但如果 1) finding-1 工具循环 manifest 补齐后引入 limited_signal 状态，或 2) manifest 校验产生 mismatch，tool trace 会产出违反 contract 的 diagnostic（status=limited_signal 且 reason=None）。

**建议：** 当 `validation_status != "complete"` 时，从 manifest payload 中读取实际 diagnostic 字段（`reason`、`observed_count` 等），而不是硬编码 None。同时考虑 trace summary 是否需要从 preview payload 的 `runner_call_manifest_validation` 块补全 diagnostic 信息——因为 ingest 的 validation summary 已经计算了 observed/expected counts 和 digests。

### finding-3 (medium): 工具循环 continuation 的 Engine→Host 校验信号只在 preview payload，不进入 Tool Trace

**文件：** `dayu/host/engine_ingest.py:4229-4236`（`_preview_payload` 中 `runner_call_manifest_validation` 的注入）、`dayu/host/tool_trace.py:137`（`_CANONICAL_EVENT_TYPES` 不含 preview event）

**证据：**

`_runner_call_manifest_validation_summary()` 的返回值写入 preview payload（`EventClass.PREVIEW`）。Tool Trace 只消费 canonical events（`_CANONICAL_EVENT_TYPES`）。因此，工具循环 continuation 的 `limited_signal`（无 manifest）、或 `mismatch`（message_count / role digest 冲突）只能从 preview payload dump 看到，不能从 Tool Trace hot row 或 cold JSONL 查询到。

这与 design.md 14.1 的定位不完全一致："Tool Trace 对 runner-call reconstruction 的消费边界固定为 read-only signal。它只能消费 `RUNNER_CALL_INPUT_ASSEMBLED` manifest refs/digests"——如果 manifest 不存在，trace 至少应有 limited_signal 诊断。当前 trace 对没有 manifest 的 runner call 完全没有记录（因为没有 `RUNNER_CALL_INPUT_ASSEMBLED` canonical event 供 trace 消费）。

**建议：** 与 finding-1 耦合。若 tool-loop continuation manifest 被补齐，trace 自然可以通过 manifest canonical event 消费。若不补齐，可考虑让 ingest 对无 manifest 的工具循环 iteration 也写一个 `RUNNER_CALL_INPUT_ASSEMBLED` canonical event（即使 manifest 字段是 limited）。这将同时解决 finding-1、finding-3 和 finding-2 部分。

### finding-4 (medium): `_runner_call_kind_and_trigger` 的分派逻辑在边界场景可能误分类

**文件：** `dayu/host/run_input.py:3925-3955`（`_runner_call_kind_and_trigger`）

**证据：**

```python
def _runner_call_kind_and_trigger(record_input):
    start_payload = _payload_object(record_input.current_facts.run_started_event)
    start_reason = start_payload.get(_PAYLOAD_FIELD_START_REASON)
    if start_reason == "recovery" or record_input.fallback is not None:
        return (_RUNNER_CALL_KIND_POST_COMPACTION_DISPATCH,
                _RUNNER_CALL_TRIGGER_CONTEXT_COMPACTION_COMPLETED)
    if start_reason == "resume":
        return (_RUNNER_CALL_KIND_FOLLOWUP_USER_DISPATCH,
                _RUNNER_CALL_TRIGGER_HOST_RESUME)
    if len(record_input.continuity.messages) > 0:
        return (_RUNNER_CALL_KIND_FOLLOWUP_USER_DISPATCH,
                _RUNNER_CALL_TRIGGER_FOLLOWUP_USER_INPUT)
    return (_RUNNER_CALL_KIND_INITIAL_USER_DISPATCH,
            _RUNNER_CALL_TRIGGER_INITIAL_USER_INPUT)
```

三个问题：

1. **`initial_user_dispatch` vs `followup_user_dispatch` 判别依赖 `continuity.messages` 数量**：如果 Session 中第一次 user dispatch 但 `continuity.messages` 不为空（例如有 system prompt 或 prefilled context），会被误判为 `followup_user_dispatch`。当前实现中这通常不成立（system prompt 在 memory block 而非 continuity），但判别逻辑本身不是基于 "是否有前序 user turn"，而是 "是否有前序任意 agent messages"。

2. **`"recovery"` start_reason 与 `fallback` 合并为同一 kind**：recovery 启动（例如 RUN 从 LOST 恢复）与 compaction fallback 是不同的语义，但被合并到同一个 `post_compaction_dispatch` / `context_compaction_completed`。recovery 不一定与 compaction 相关。

3. **`post_compaction_dispatch` 的 trigger 固定为 `context_compaction_completed`**：当 `start_reason == "recovery"` 且 `fallback is None` 时，这也不准确。

**建议：** 增加显式的 host state 判别（例如检查 `CONTEXT_COMPACTED` canonical event 是否存在）而非依赖 `start_reason` 字符串推断；或者至少将 `start_reason == "recovery"` 且无 fallback 的路径独立映射为新的 kind/trigger 对（如 `followup_user_dispatch` + `host_resume`）。此 finding 不影响当前正确性（因为当前 start_reason 枚举值覆盖了实际场景），但增加未来的分类脆弱性。

### finding-5 (low): `_message_content_digest_preimage` 对 AssistantMessage 的 content 处理不对称

**文件：** `dayu/host/run_input.py:3822-3838`（`_message_content_digest_preimage`）

**证据：**

```python
if isinstance(message, AssistantMessage):
    return {
        ...
        "content": message.content,  # str | None, 可为 None
        ...
    }
return {
    ...
    "content": _message_content_text(message),  # 将 None 转为 ""
    ...
}
```

对于非 assistant 消息，`_message_content_text` 将 null content 转为空字符串；对于 assistant 消息，null content 直接进入 canonical JSON 成为 `"content": null`。语义上 assistant 无 text content（只有 tool_calls）与有空白 text content 确实不同，所以这个不对称是语义正确的。但未来新增 message type 时可能引入同样的不对称 bug。

**建议：** 不需要在 Slice 2 修复；在 `_message_content_digest_preimage` 中显式注释说明此不对称是 intentional。

## tests / pyright 核验

| 项目 | 结果 |
| --- | --- |
| `pytest` (153 targets, Slice 2 affected) | **153 passed in 1.07s** |
| `pyright` | **0 errors, 0 warnings** |

测试覆盖：

- **Engine role digest 正算**：`test_iteration_started_carries_role_digest_from_actual_messages` 验证 Engine `IterationStartedData.role_sequence_digest` 与 `runner_role_sequence_digest(实际 messages roles)` 一致，同时验证 `message_count` 和 `runner_input_serializer_schema_version`。
- **Engine contract field lock**：`test_iteration_started_runner_input_signal_fields_are_locked` 验证 `IterationStartedData` 只增加两个 Engine-owned 字段，未混入 Host refs/index。
- **Manifest boundedness**：`test_runner_call_manifest_is_bounded_and_does_not_inline_messages` 验证 20KB 大输入下 manifest body < 5000 字节、大输入文本不进入 manifest、不进入 hot payload、但仍在 request.messages 中。
- **Noop provider row counts**：`test_noop_providers_only_create_runner_call_manifest_rows` 验证 noop providers 路径增加了 manifest descriptor/canonical event/sqlite payload 三行。
- **Tool Trace signal**：`test_tool_trace_projects_runner_call_manifest_signal` 验证 Tool Trace hot row 和 cold JSONL 都复制了 manifest refs/digests、message_count、role_sequence_digest、projector_metadata_summary 和 diagnostic。
- **Ingest mapping**：`test_unsupported_engine_event_shape_is_rejected` 更新了 `IterationStartedData` 新字段的 mock 值。

未覆盖的关键边界：
- **无 manifest 的 iteration_started**：没有一个测试模拟 "工具循环 continuation 的 Engine iteration_started 到达 ingest 时，EventLog 中还没有 manifest" 的情况，并验证 preview payload 中 `runner_call_manifest_validation.status == "limited_signal"`。当前 `test_unsupported_engine_event_shape_is_rejected` 虽构造了 `IterationStartedData`，但不会进入真实的 ingest 校验流程。
- **manifest digest 不匹配**：没有测试验证 manifest payload digest 不一致时的 raised error（`_write_runner_call_manifest_payload` 的 `expected_digest` 校验路径）。
- **`_next_runner_call_index` 溢出或重复**：没有边界测试覆盖同一 run 下多个 manifest 的 index 递增一致性。

## scope completeness judgment

| Slice 2 plan exact change | 实现状态 | 判断 |
| --- | --- | --- |
| Engine contract 只增加 Engine-owned observation fields (role digest, serializer schema version) | Engine `IterationStartedData` 新增 `role_sequence_digest`、`runner_input_serializer_schema_version`。Host-owned `runner_call_index`/manifest ref/source refs 均未进入 Engine contract。 | **done** |
| Host 初始 RunInputBuilder 生成 ordinary call manifest refs | `DurableRunnerCallManifestRecorder` 在 `RunInputBuilder` 调用后、transaction 内写入 `RUNNER_CALL_INPUT_ASSEMBLED` canonical event 与 manifest body descriptor。`runner_call_index` 由 Host 按 run_id scope 自增管理。`message_count` 和 role digest 来自实际传给 Engine 的 messages。 | **done** |
| Engine tool-loop continuation 暴露 iteration/message_count/role digest | Engine `_AsyncAgent` 对每次 runner call 都计算并 emit role digest。这些字段随 `iteration_started` EngineEvent 到达 Host ingest。 | **done** |
| Host ingest 根据 accepted lifecycle context 生成 RUNNER_CALL_INPUT_ASSEMBLED 与 manifest refs/digests | `_runner_call_manifest_validation_summary` 只校验已有 manifest，不生成 manifest。工具循环 continuation 无 manifest 时返回 limited_signal 但不生成 canonical event。 | **not done（blocking）** |
| Manifest 不内联完整 message text | `test_runner_call_manifest_is_bounded_and_does_not_inline_messages` 验证了 boundedness。Manifest 只包含 digest/ref/size summary。 | **done** |
| `runner_call_index` 与 manifest refs/digests 只由 Host 产生 | `_next_runner_call_index`、manifest event 写入均在 Host 侧。Engine 不含这些字段。 | **done** |
| 大 input 下 manifest body 只增长 refs/digests/entries summary | Boundedness 测试覆盖。Manifest body 中 message entries 只记录 digest/size/source refs，不记录 content。 | **done** |

**结论：** Slice 2 的 7 项 exact changes 中 6 项完成，1 项（工具循环 continuation manifest 生成）未实现。该缺失违反 plan 的 explicit scope——plan 明确写了 "Host ingest 生成 RUNNER_CALL_INPUT_ASSEMBLED"，实现做了相反的设计决策（只校验不生成）。需要 controller 裁决是否作为 blocking fix 还是计划调整。

## remaining risks

1. **工具循环 continuation manifest 缺失**（finding-1）：当前唯一未覆盖的 runner call 类型。补齐风险低——Engine 已暴露基础信号，只需要在 ingest 中增加 manifest 构造（参考 `DurableRunnerCallManifestRecorder` 的模式）。但 ingest 缺少 Host source refs/projector metadata，对工具循环 manifest 只能是 limited completeness 的手势。

2. **Tool Trace diagnostic 硬编码 None**（finding-2）：当前无害，但一旦有 limited_signal/mismatch manifest 进入 EventLog，trace 将违反 `RunnerCallReconstructionDiagnostic` contract。修复代价很低（从 manifest hot payload 读取字段而非硬编码 None）。

3. **ingest validation 信号不可投影**（finding-3）：preview payload 中的 validation 结果无法进入 Tool Trace。该风险与 finding-1 同源——补全 manifest 写入后自然解决。

4. **RunnerCallKind 判别逻辑脆弱**（finding-4）：当前 `start_reason` 枚举值有限，但在 recovery/resume/retry 路径全面启用时需要更严格的 manifest kind 判定逻辑。

5. **无 manifest→Engine digest 匹配的无差别测试**（uncovered boundary）：测试只验证了有 manifest 的 ordinary 路径，没有端到端测试工具循环 continuation 的 ingest validation 路径。

## ready for controller adjudication

**yes** — 产出完整的 findings、scope completeness 评估和 remaining risks。

建议 adjudication：
1. 对 finding-1（blocking）：controller 决定是回修 Slice 2 补全工具循环 manifest 写入，还是将 scope 调整为 ordinary path only 并在 control doc 中记录 deferred 到 Slice 4（或新增 Slice 2.5）。
2. 若选 Option A（回修）：一并修复 finding-2 和 finding-3（两者是 finding-1 的伴生问题）。
3. 若选 Option B（scope 调整）：将 finding-2 标记为 Slice 4 前置需求，finding-3 标记为 Slice 4 覆盖项。
4. 对 finding-4（medium）：建议在 Slice 3（compactor manifest）或 Slice 4（tool trace signal）的 plan 中增加 RunnerCallKind 判别逻辑的硬化要求。
5. 对 uncovered boundary：建议工具循环 manifest 补齐后增加对应的端到端 ingest validation 测试。
