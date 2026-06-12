# WU-DUR-P01-S2-R2 runner-call event link hardening plan

## 目标

关闭 residual risk `WU-DUR-P01-S2-R2`：普通 `RUNNER_CALL_INPUT_ASSEMBLED` manifest 在 Engine `ITERATION_STARTED` 之前写入，Host 后续不能再用 `iteration_index == 0` 这类间接猜测把 Engine iteration 关联回 manifest。修复后必须满足：

- 普通 RunInputBuilder 仍先记录 prepared/input manifest，manifest 继续作为 Host 装配出的 `AgentRunRequest.messages` 的 durable reconstruction truth。
- Engine `ITERATION_STARTED` 到达后，Host 追加显式、稳定、可审计的 manifest-to-iteration link / validation / correlation。
- 初始 runner call 缺失 prepared manifest、候选 manifest 歧义、manifest 与 Engine 可观察输入不一致时 fail closed。
- Engine-only tool-loop continuation 仍可写 canonical limited-signal manifest，不把 missing projection artifact 误判为 Host prepared manifest 缺失。
- 不再依赖 `iteration_index == 0` 判断普通首轮 manifest；iteration index 只作为 Engine observation 记录和验证材料。
- durable truth、Tool Trace、manifest diagnostics、public RunInputBuilder contract 不倒退。

## 非目标

- 不修改 Engine 反向依赖 Host manifest id；Engine 继续只上报 `ITERATION_STARTED` 可观察字段。
- 不把完整 rendered messages、prompt、memory snapshot、compact material 或 provider raw request 写进 EventLog hot payload。
- 不回写或重算已写入的 `RUNNER_CALL_INPUT_ASSEMBLED` manifest body / payload digest。
- 不把 runner-call reconstruction 用于 Run / Attempt terminal decision、recovery scan、memory projection 或 dispatch decision。
- 不在本 residual 内改 compactor proposal trigger reason、compact outcome cross-reference 或 provider-specific raw atom contract。
- 不改变 public `RunInputBuilder` / `AgentRunRequest` 对外输入输出形状；新增能力限于 Host ingest / EventLog reconstruction / tests / docs。
- 不强制 Tool Trace 在本 slice 投影 `RUNNER_CALL_INPUT_ITERATION_LINKED`；最低实现只要求 design / README 明确 prepared manifest `complete` 与 Engine linked `complete` 的区别。

## 动机判断

动机成立，且不是“缺少 Engine event”的问题。Engine 已在每次 runner 调用前发出 `ITERATION_STARTED`，Host ingest 也会处理该事件；真实缺口是 prepared manifest 与 Engine iteration 之间没有追加式稳定 link，现有匹配函数用 `payload_iteration_id is None and iteration_index == 0` 兜底，属于间接猜测。

严重性没有被低估：该风险当前在 Engine iteration index 单调时不触发，但一旦 continuation、retry 或未来 Engine 执行语义出现 index reset，Host 可能把后续 Engine runner call 错连到最初 ordinary manifest，造成 Tool Trace / analyzer reconstruction 使用错误输入事实。

## Root Cause

`RunInputBuilder` 在 Host dispatch 前写入 ordinary `RUNNER_CALL_INPUT_ASSEMBLED`。此时 Engine 尚未开始 iteration，因此 ordinary manifest 的 `iteration_id` / `iteration_index` 是 `None`。`EngineEventIngestor` 收到 `ITERATION_STARTED` 后查找 manifest 时，将 “manifest 没有 iteration_id 且 Engine `iteration_index == 0`” 视为匹配。这个条件不是 durable identity，也不是 Engine 和 Host 的共同稳定契约。

正确 root cause 是：缺少追加式 `manifest_event_id/ref/digest -> iteration_id/index` 显式关联事实；不是 RunInputBuilder 没写 manifest，也不是 Engine 没发 `ITERATION_STARTED`。

## 直接证据

- `docs/host/issues-implementation-control.md` active residual 表记录 `WU-DUR-P01-S2-R2`，要求 harden 或测试 `_runner_call_manifest_matches_iteration`，尤其关注 continuation 场景 `iteration_index == 0` reset。
- `docs/host/design.md` 规定 `RunInputBuilder` 是唯一 ordinary `AgentRunRequest.messages` 构造 owner，`EngineEvent Ingest` 是唯一 Engine / Worker / ToolRuntime 回传事件验证与 Host event 转换 owner。
- `docs/host/design.md` 规定 `RUNNER_CALL_INPUT_ASSEMBLED` 是 canonical reconstruction event，无 Run / Attempt 状态副作用；manifest body 通过 payload descriptor 存储，完整 rendered messages 不能成为 EventLog hot payload。
- `docs/host/design.md` 规定 ordinary manifest 必须记录 one-system-message normalization 后最终 messages，`message_count`、`message_entries`、`role_sequence_digest` 必须与实际交给 Engine / Runner 的 `AgentRunRequest.messages` 同源。
- `docs/host/design.md` 规定 Tool Trace 只能消费 `RUNNER_CALL_INPUT_ASSEMBLED` refs / digests、Engine 可观察的 iteration/message count 和 projection metadata，不得读取 EngineRunner 内存或重新运行 prompt builder。
- `dayu/host/run_input.py` 的 `_runner_call_manifest_body` 对 ordinary manifest 写入 `iteration_id=None`、`iteration_index=None`，并用 normalized final messages 计算 `message_count` 与 `role_sequence_digest`。
- `dayu/host/run_input.py` 的 `DurableRunnerCallManifestRecorder` 按同一 `attempt_id` / `execution_id` 幂等记录一次 ordinary manifest，说明 prepared manifest 是 Host dispatch input truth，不是 Engine observation。
- `dayu/engine/agent.py` 在 runner call 开始前发出 `ITERATION_STARTED`，字段包括 `iteration_id`、`iteration_index`、`message_count`、`role_sequence_digest` 与 runner input serializer schema version。
- `dayu/host/engine_ingest.py` 的 `_runner_call_manifest_matches_iteration` 当前逻辑是：iteration id 相等则匹配，否则 `payload_iteration_id is None and iteration_index == 0` 也匹配。
- `tests/host/test_engine_ingest_mapping.py` 已覆盖 `iteration_index=1` continuation 写 limited-signal manifest，但没有覆盖 reset 到 `0` 时不能误匹配 ordinary prepared manifest。
- `dayu/host/tool_trace.py` 与 `dayu/host/durable/tool_trace.py` 当前只把 `RUNNER_CALL_INPUT_ASSEMBLED` 作为 runner-call reconstruction signal；因此修复不能通过回写旧 manifest 或改变该事件含义来伪造 link。

## 设计契约变更

### 1. Prepared manifest 保持为 input assembly truth

ordinary `RUNNER_CALL_INPUT_ASSEMBLED` 继续由 `RunInputBuilder` 在构造 `AgentRunRequest` 后、交给 Engine 前写入。它的 `validation_status="complete"` 只表示 Host manifest 自身完整且与 Host-built final messages 同源，不表示已经与 Engine iteration 关联。

ordinary manifest 的 `iteration_id` / `iteration_index` 可以保持 `None`。实现不得为了补 link 去更新 manifest body、payload descriptor、payload digest 或原 EventLog hot payload。

### 2. 新增追加式 link event

在 `EngineEventIngestor` 接受 `ITERATION_STARTED` 时新增 canonical event：

```text
RUNNER_CALL_INPUT_ITERATION_LINKED
```

该 event 是 Host-owned runner-call reconstruction fact，只表达 prepared manifest 与 Engine iteration 的 link / validation / correlation；它没有 Run / Attempt 状态副作用，不参与 terminal decision、recovery、memory projection、dispatch decision 或 resume。

hot payload 字段固定为：

```text
session_id
host_run_id
attempt_id
execution_id
manifest_event_id
manifest_payload_ref
manifest_digest
manifest_schema_version
runner_call_index
runner_call_kind
runner_call_trigger_reason
iteration_id
iteration_index
engine_message_count
engine_role_sequence_digest
runner_input_serializer_schema_version
expected_message_count
expected_role_sequence_digest
validation_status
diagnostic
```

`validation_status` 复用 runner-call diagnostic 状态集合：

- `complete`：唯一 prepared manifest 与 Engine observation 一致。
- `mismatch`：找到唯一 prepared manifest，但 `message_count` 或 `role_sequence_digest` 与 Engine observation 不一致。该 status 不表达 link identity conflict。
- `limited_signal`：只用于 Engine-only continuation 的 existing limited-signal manifest，不用于 ordinary prepared manifest link。

`diagnostic` 复用当前 runner-call typed diagnostic shape。`RUNNER_CALL_INPUT_ITERATION_LINKED` 的 diagnostic reason 只属于 runner-call reconstruction diagnostic reason 闭集；不得混入 Engine ingest rejected reason。`complete` 时 `reason=None`；`mismatch` 时 reason 只允许：

- `message_count_mismatch`
- `role_sequence_digest_mismatch`

`manifest_event_id` 是 link 的稳定主引用；`manifest_payload_ref` / `manifest_digest` 用于 Tool Trace、audit 和 analyzer read-only reconstruction。link event id 必须由 `run_id`、`attempt_id`、`execution_id`、`manifest_event_id`、`iteration_id`、`iteration_index` 派生，确保重复 ingest 幂等。

### 3. ENGINE_EVENT_REJECTED 与 reason 契约

本 plan 依赖现有 Host ingest fail-closed event `ENGINE_EVENT_REJECTED`。Slice 0 必须把它补入 design source 的 event type list 与 event contract matrix；这不是新增生产行为，而是补齐当前代码已经使用但设计真源遗漏的 Host ingest diagnostic contract。

`ENGINE_EVENT_REJECTED` contract：

- scope：`session_id`、`host_run_id`、`attempt_id`、`execution_id`、`worker_event_index`、`engine_event_type`。
- payload：`reason`、`stop_worker_stream`、可选 `diagnostic_refs`、可选 runner-call link / manifest refs。`stop_worker_stream` 同时是 `EngineIngestResult` 的控制信号；event payload 也必须记录同名布尔值，便于 audit 解释 fail-closed 决策。
- 状态副作用：无 Run / Attempt lifecycle transition，不驱动 recovery、memory projection、dispatch decision 或 resume。
- consumer：audit / Tool Trace 可读；memory / recovery / dispatch 不消费。

本 plan 新增的 `ENGINE_EVENT_REJECTED.reason` 必须进入 Engine ingest rejected reason 闭集，而不是 runner-call reconstruction diagnostic reason 闭集：

- `missing_runner_call_manifest`：当前 `attempt_id` + `execution_id` 的第一个 accepted `ITERATION_STARTED` 到达时，没有唯一 unlinked prepared ordinary manifest。用于 initial runner call fail-closed；不得用于 Engine-only continuation。
- `ambiguous_runner_call_manifest`：当前 `attempt_id` + `execution_id` 下存在多条 unlinked prepared ordinary manifest，Host 无法唯一确定 Engine iteration 对应哪个 prepared input。使用时不得追加 link event。
- `runner_call_iteration_link_conflict`：同一 `run_id` + `attempt_id` + `execution_id` + `iteration_id` 已有 accepted link，但当前 Engine observation 与既有 link 的 manifest identity、iteration index、message count、role digest 或 serializer schema version 不一致。使用时不得追加第二条 link event。
- `runner_call_manifest_mismatch`：存在唯一 unlinked prepared ordinary manifest，并已追加 `RUNNER_CALL_INPUT_ITERATION_LINKED` mismatch event；其 `message_count` 或 `role_sequence_digest` 与 Engine observation 不一致。该 reason 只作为 rejected event 对 link mismatch 的 fail-closed 控制原因；具体差异写在 link event diagnostic 的 `message_count_mismatch` 或 `role_sequence_digest_mismatch` 中。

`ambiguous_runner_call_manifest` 与 `runner_call_iteration_link_conflict` 不得写入 `RUNNER_CALL_INPUT_ITERATION_LINKED.diagnostic.reason`。`runner_call_manifest_mismatch` 不得写入 Tool Trace runner-call reconstruction diagnostic reason，除非后续 design gate 明确扩展 Tool Trace enum。

### 4. Durable ordering guarantee

普通 prepared manifest 必须在 Engine worker 可产生 `ITERATION_STARTED` 之前 durable committed。Slice 0 design sync 必须明确检查并记录该 ordering guarantee：

- `RunInputBuilder` 写入 ordinary `RUNNER_CALL_INPUT_ASSEMBLED` 的 transaction 必须在 Attempt dispatch / worker start 之前完成提交。
- Engine ingest 处理 `ITERATION_STARTED` 时，若当前 attempt/execution 是首次 accepted iteration observation，却看不到 prepared manifest，这被视为 Host durable ordering 或 input assembly 缺失，必须 fail closed。
- 若实施核对发现 ordinary manifest write 与 worker start / `ITERATION_STARTED` ingest 之间没有 durable ordering guarantee，不得用 sleep、retry、grace window 或 limited-signal 掩盖；必须回到 design gate。

### 5. Link resolution contract

`EngineEventIngestor` 对 `ITERATION_STARTED` 使用以下 resolution，不再调用 `iteration_index == 0` fallback：

1. 先按 `run_id`、`attempt_id`、`execution_id`、`iteration_id` 查找既有 `RUNNER_CALL_INPUT_ITERATION_LINKED`。
2. 若存在同 iteration 的 link：
   - 既有 link 的 `validation_status="complete"` 且与当前 Engine observation 完全一致：幂等接受，并继续写/读对应 preview。
   - 既有 link 的 `validation_status="mismatch"` 且与当前 Engine observation 一致：append `ENGINE_EVENT_REJECTED`，reason 使用 `runner_call_manifest_mismatch`，`stop_worker_stream=True`；不得 append accepted `ITERATION_STARTED` preview。
   - 指向不同 manifest 或 expected/observed 字段不一致：append `ENGINE_EVENT_REJECTED`，reason 使用 `runner_call_iteration_link_conflict`，`stop_worker_stream=True`。
3. 若不存在 link，查找当前 attempt/execution 下尚未 link 的 prepared ordinary manifest：
   - 只允许 `RUNNER_CALL_INPUT_ASSEMBLED`，`validation_status="complete"`，`iteration_id is None`，`iteration_index is None`，`compactor_identity is None`，且 `runner_call_kind` 属于闭集 `initial_user_dispatch` / `followup_user_dispatch` / `post_compaction_dispatch`。该闭集覆盖 ordinary RunInputBuilder 的三类 dispatch，排除 `tool_result_continuation` 与 `compactor_proposal`。
   - unlinked 定义：没有任何同一 `run_id`、`attempt_id`、`execution_id` 的 accepted `RUNNER_CALL_INPUT_ITERATION_LINKED` hot payload 使用该 `RUNNER_CALL_INPUT_ASSEMBLED.event_id` 作为 `manifest_event_id`。
   - anti-join 查询策略：在同一个 Host transaction 内用 `NOT EXISTS` 子查询排除已 linked manifest；link event 的 `manifest_event_id` 从 hot payload JSON 读取，优先使用 SQLite JSON1 `json_extract(payload_json, '$.manifest_event_id')`。查询必须同时按 `run_id`、`attempt_id`、`execution_id` 和 event type 收窄范围；不得只用全 Run `RUNNER_CALL_INPUT_ASSEMBLED` 计数，也不得在事务外做 Python 端差集。若当前 durable store 无法支持该 anti-join 且不能给出 bounded O(n) 同事务扫描证明，停止并回到 design gate。
   - 候选数为 1：用 Engine `message_count` / `role_sequence_digest` 校验 manifest hot payload。匹配则 append `RUNNER_CALL_INPUT_ITERATION_LINKED complete`，再 append `ITERATION_STARTED` preview。
   - 候选数大于 1：append `ENGINE_EVENT_REJECTED`，reason 使用 `ambiguous_runner_call_manifest`，`stop_worker_stream=True`；不得追加 link event。
   - 候选数为 0 且当前 attempt/execution 已有 prior accepted iteration observation：这是 Engine-only continuation，沿用现有 limited-signal manifest 路径；不得因为 `iteration_index == 0` reset 去匹配旧 ordinary manifest。
   - 候选数为 0 且没有 earlier accepted iteration：这是 initial runner call 缺少 prepared manifest，append `ENGINE_EVENT_REJECTED`，reason 使用 `missing_runner_call_manifest`，`stop_worker_stream=True`；不得写 limited-signal manifest 掩盖 ordinary prepared manifest 缺失。
4. 若候选 manifest 存在但 `message_count` 或 `role_sequence_digest` mismatch：append `RUNNER_CALL_INPUT_ITERATION_LINKED mismatch`，再 append `ENGINE_EVENT_REJECTED`，reason 使用 `runner_call_manifest_mismatch`，`stop_worker_stream=True`；不得 append accepted `ITERATION_STARTED` preview。

`_has_prior_iteration_observation(...)` 的 durable query scope 必须固定：

- 只查询当前 `run_id` + `attempt_id` + `execution_id`。
- accepted prior observation 只包括 committed `RUNNER_CALL_INPUT_ITERATION_LINKED` canonical event，或 committed accepted `ITERATION_STARTED` preview event。
- 不跨 execution，不看 compactor proposal execution，不看同 Run 其它 Attempt。
- 明确排除 `RUNNER_CALL_INPUT_ASSEMBLED` 计数、`ENGINE_EVENT_REJECTED`、其它 diagnostic event、terminal event 和 rejected preview。
- 若 link event 与 preview event 在同一 transaction 内尚未提交，当前 query 只能看到本 transaction 已 append 的 rows；实现不得用 transaction 外缓存判断 prior observation。

`RUNNER_CALL_INPUT_ITERATION_LINKED` 与对应 accepted `ITERATION_STARTED` preview 必须在同一个 Host write transaction 中 append。`RUNNER_CALL_INPUT_ITERATION_LINKED mismatch` 与对应 `ENGINE_EVENT_REJECTED` 也必须在同一个 Host write transaction 中 append。若实现无法保持同事务原子性，必须停止并回到 design gate。

### 6. Preview payload correlation

`ITERATION_STARTED` preview payload 继续包含 `runner_call_manifest_validation`，但 summary 必须来自 link resolution 结果，而不是重新调用旧 matching helper。成功 link 时 preview payload 增加：

```text
runner_call_iteration_link_event_id
runner_call_manifest_event_id
manifest_payload_ref
manifest_digest
```

实现必须显式传递 link resolution result，避免 `_preview_payload` 重新执行 manifest matching：

- 增加私有 result dataclass / typed helper result，例如 `_RunnerCallIterationResolution`，字段包含 status、reason、link_event_id、manifest_event_id、manifest_payload_ref、manifest_digest、expected/observed count/digest、是否 continuation limited-signal、是否 rejected。
- `_append_iteration_started_events` 在同一 transaction 内先完成 resolution，再把 result 传给专用 preview payload builder。
- `_preview_payload` 可以新增可选参数，或拆出 `_iteration_started_preview_payload(transaction, context, data, resolution)`；禁止在 preview builder 内再次调用 `_find_runner_call_manifest_event` 或 `_runner_call_manifest_matches_iteration`。
- preview 的 `runner_call_manifest_validation` 与顶层 `runner_call_iteration_link_event_id` / `runner_call_manifest_event_id` 必须来自同一个 resolution result。

limited-signal continuation preview 保持当前 observed count / digest diagnostic 语义。

### 7. Tool Trace 与 manifest diagnostics

最低实现要求：

- 保持现有 `RUNNER_CALL_INPUT_ASSEMBLED` Tool Trace projection 不变；prepared manifest 仍按原 signal 进入 Tool Trace。
- 新 link event 不展开 manifest body，不读取 full messages，不重新运行 RunInputBuilder。
- design / README 必须明确：`RUNNER_CALL_INPUT_ASSEMBLED.validation_status="complete"` 只表示 prepared input manifest 完整；`RUNNER_CALL_INPUT_ITERATION_LINKED.validation_status="complete"` 才表示该 prepared input 已由 Engine `ITERATION_STARTED` observation 验证。
- 若实现把 `RUNNER_CALL_INPUT_ITERATION_LINKED` 纳入 Tool Trace，必须作为独立 read-only signal 投影，`trace_summary.event_type` 保持新 event type，并复制 manifest ref/digest、iteration fields、expected/observed count/digest 与 typed diagnostic；不得改变现有 `read_runner_call_reconstruction_signals_by_run` 对 `RUNNER_CALL_INPUT_ASSEMBLED` 的返回语义，除非同步更新 durable Tool Trace contract 和全部消费者测试。
- existing limited-signal continuation manifest diagnostic 必须保留；missing projection artifact 仍是 limited signal，不是 EventLog fact 缺失。

## 实施切片

### Slice 0: Design sync

允许文件：

- `docs/host/design.md`
- `docs/host/issues-implementation-control.md`
- `dayu/host/README.md`
- `tests/README.md`

动作：

- 在 Host design runner-call reconstruction 章节补充 prepared manifest 与 Engine iteration link 的追加式契约。
- 在 EventLog event type 表中加入 `RUNNER_CALL_INPUT_ITERATION_LINKED`，明确无状态副作用。
- 在 EventLog event type 表和 event contract matrix 中补录现有 `ENGINE_EVENT_REJECTED`，明确 scope、payload、`stop_worker_stream` 记录、无状态副作用与 audit / Tool Trace 消费边界。
- 在 runner-call reconstruction diagnostic reason 闭集中确认 link event 只使用 `message_count_mismatch` / `role_sequence_digest_mismatch`；不要把 Engine ingest rejected reason 混入 Tool Trace diagnostic enum。
- 在 Engine ingest rejected reason 闭集中补充并定义 `missing_runner_call_manifest`、`ambiguous_runner_call_manifest`、`runner_call_iteration_link_conflict`、`runner_call_manifest_mismatch` 的语义、使用边界和与 runner-call diagnostic reason 的区别。
- 明确 ordinary manifest 的 `validation_status=complete` 只表示 Host input assembly 完整，不表示 Engine observation 已 linked。
- 明确 `RUNNER_CALL_INPUT_ITERATION_LINKED.validation_status=complete` 才表示 prepared input 已通过 Engine `ITERATION_STARTED` observation 校验。
- 明确 ordinary prepared manifest durable commit 必须先于 Attempt dispatch / worker start；若该 ordering guarantee 不成立，本 plan 不可实施。
- 明确 fail-closed 条件：missing initial prepared manifest、ambiguous prepared manifest、message count mismatch、role digest mismatch、link conflict。
- 明确 `ENGINE_EVENT_REJECTED` 只写 diagnostic / control fact，不改变 Run / Attempt 状态；rejected 后状态机与现有 unsupported Engine event rejected 路径一致。

验收：

- 文档中没有让 Engine import Host、读取 Host durable store 或携带 Host manifest id。
- 文档中没有要求 mutation old manifest / payload digest。
- 文档中没有把 link event 变成 lifecycle/recovery/memory/dispatch truth。
- 文档中 `ENGINE_EVENT_REJECTED`、`RUNNER_CALL_INPUT_ITERATION_LINKED`、新增 rejected reason 和 runner-call diagnostic reason 的闭集定义均可 grep 到。
- 文档中明确 prepared `complete` 与 Engine linked `complete` 是两个不同语义。

### Slice 1: Engine ingest link resolution

允许文件：

- `dayu/host/engine_ingest.py`
- 必要时 `dayu/host/durable/tool_trace.py` / `dayu/host/tool_trace.py` 只加 diagnostic enum 支撑，不做 Tool Trace 行为扩张。

动作：

- 删除 `_runner_call_manifest_matches_iteration`，并删除或重写其唯一调用方 `_find_runner_call_manifest_event`。新逻辑不得留下仍按 `iteration_index == 0` 匹配 prepared manifest 的 dead code。
- 增加模块级 helper：
  - `_find_runner_call_iteration_link_event(...)`
  - `_find_unlinked_prepared_runner_call_manifest_events(...)`
  - `_has_prior_iteration_observation(...)`
  - `_append_runner_call_iteration_link_event(...)`
  - `_runner_call_iteration_link_payload(...)`
  - `_runner_call_link_validation_summary(...)`
  - `_iteration_started_preview_payload(..., resolution=...)` 或等价 typed payload builder
- `_find_unlinked_prepared_runner_call_manifest_events(...)` 必须按当前 `run_id` + `attempt_id` + `execution_id` 查询 `RUNNER_CALL_INPUT_ASSEMBLED`，过滤 `validation_status="complete"`、`iteration_id is None`、`iteration_index is None`、`compactor_identity is None`、`runner_call_kind in ("initial_user_dispatch", "followup_user_dispatch", "post_compaction_dispatch")`，并用同事务 anti-join 排除已被 `RUNNER_CALL_INPUT_ITERATION_LINKED.manifest_event_id` 引用的 manifest。
- `_has_prior_iteration_observation(...)` 必须只看当前 `run_id` + `attempt_id` + `execution_id` 下 accepted `RUNNER_CALL_INPUT_ITERATION_LINKED` 或 accepted `ITERATION_STARTED` preview；不得看 `RUNNER_CALL_INPUT_ASSEMBLED` 计数、`ENGINE_EVENT_REJECTED` 或跨 execution event。
- `_append_iteration_started_events` 改为：
  - 用 link resolution 产生 complete / continuation limited-signal / fail-closed result。
  - complete：append/read link event，再用同一个 resolution result append preview。
  - continuation：沿用 current limited-signal manifest append，再 append preview。
  - mismatch：同 transaction append link mismatch，再 append `ENGINE_EVENT_REJECTED`，`stop_worker_stream=True`。
  - missing / ambiguous / conflict：同 transaction append `ENGINE_EVENT_REJECTED`，`stop_worker_stream=True`。
- `_preview_payload` 的 `runner_call_manifest_validation` 使用 link resolution result，不再重新扫描并做 index fallback；实现可通过新增 `_iteration_started_preview_payload` 避免影响其它 preview event。

验收：

- 普通 initial `ITERATION_STARTED` 必须产生 `RUNNER_CALL_INPUT_ITERATION_LINKED` + `ITERATION_STARTED` preview。
- continuation 即使 `iteration_index == 0`，只要没有 unlinked prepared manifest 且已有 earlier iteration observation，也必须走 limited-signal path。
- missing initial manifest 不写 limited-signal manifest，直接 rejected。
- mismatch 不产生 accepted preview。
- mismatch link event 与 rejected diagnostic 在同一 Host transaction 中提交或一起回滚。
- link complete event 与 accepted preview 在同一 Host transaction 中提交或一起回滚。
- `rg "_runner_call_manifest_matches_iteration|def _find_runner_call_manifest_event" dayu/host/engine_ingest.py` 不再命中旧 fallback 函数；若保留同名 finder，必须证明其不再接受 `iteration_index == 0` fallback。

### Slice 2: Focused tests

允许文件：

- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_run_input_builder.py`
- 必要时 `tests/host/test_tool_trace_projection.py`
- 必要时 `tests/host/test_tool_trace_queries.py`

新增 / 更新测试：

- ordinary prepared manifest + initial `ITERATION_STARTED` 写 `RUNNER_CALL_INPUT_ITERATION_LINKED`，preview payload 指向 link event 和 manifest event/ref/digest。
- ordinary prepared manifest mismatch message_count：写 mismatch link event + rejected diagnostic，`stop_worker_stream=True`，不写 accepted preview。
- ordinary prepared manifest mismatch role_sequence_digest：同上。
- no prepared manifest + first `ITERATION_STARTED`：rejected，reason `missing_runner_call_manifest`，不写 limited-signal manifest。
- initial link 已存在后，continuation `iteration_index=0`：不得匹配已 linked ordinary manifest，必须写 limited-signal continuation manifest。fixture seeding 必须先通过生产 helper / ingest 路径创建 ordinary manifest 与 accepted link，或使用 dedicated test helper 追加 typed `RUNNER_CALL_INPUT_ITERATION_LINKED`；不得用 raw SQL 绕过 payload shape。
- 更新现有 `test_iteration_started_writes_limited_runner_call_manifest_for_continuation`：在发送 `iteration_index=1` continuation 前 seed 当前 attempt/execution 下的 prior accepted iteration observation，否则新逻辑会正确 reject 为 missing initial manifest。
- duplicate same `ITERATION_STARTED` / same link：幂等，不产生第二条 link。
- same iteration id 指向不同 manifest 或同 manifest 指向不同 iteration：rejected conflict。
- followup ordinary manifest 与 post-compaction ordinary manifest 均能被 link，证明 ordinary dispatch kind 闭集没有漏掉 lawful manifest。
- compactor proposal manifest 不会被 ordinary link resolution 选中，证明 `compactor_identity is None` / kind 闭集排除了 internal compactor call。
- prior observation helper 不把 `RUNNER_CALL_INPUT_ASSEMBLED` 计数或 `ENGINE_EVENT_REJECTED` 当作 prior iteration：seed 仅 prepared manifest 或 rejected event 时，missing first iteration 仍 rejected。
- RunInputBuilder existing manifest boundedness、message_count、role digest、one-system-message tests 继续通过，证明 public builder 未倒退。
- Tool Trace existing complete / limited_signal / mismatch tests 继续通过；若实现投影 link event，补 dedicated test 证明 link trace 不展开 manifest body。

### Slice 3: README / control doc sync and residual closure

允许文件：

- `dayu/host/README.md`
- `tests/README.md`
- `docs/host/issues-implementation-control.md`

动作：

- `dayu/host/README.md` 更新 runner-call reconstruction 段落：prepared manifest 先写，Engine iteration link 后写；prepared manifest `complete` 表示 input assembly 完整，link event `complete` 表示 Engine observation validated；Tool Trace 最小实现仍只读 prepared manifest refs/digests 和 diagnostic，不强制投影 link event。
- `tests/README.md` 更新测试矩阵：Engine ingest 覆盖 explicit runner-call iteration link、fail-closed missing/mismatch、continuation reset index 不误匹配。
- `docs/host/issues-implementation-control.md` 将 `WU-DUR-P01-S2-R2` 从 active residual 标记为 closed，记录 accepted commit / 验证命令 / 关闭依据。若实现时发现需要拆到后续 owner，保持 deferred 并写明新的 owner。

## 测试命令

实施后按顺序运行：

```bash
source .venv/bin/activate
pytest tests/host/test_engine_ingest_mapping.py -k "iteration_started or runner_call_manifest"
pytest tests/host/test_run_input_builder.py
pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py
pytest tests/host/test_public_tool_wiring_smoke.py -k "runner_call or tool_wiring or system"
pyright
```

实施后还必须做静态检查：

```bash
rg "_runner_call_manifest_matches_iteration|payload_iteration_id is None and iteration_index == 0" dayu/host/engine_ingest.py
```

该命令不得命中旧 fallback。若 `_find_runner_call_manifest_event` 仍存在，必须人工确认它不再按 `iteration_index == 0` 匹配 prepared manifest。

若 Slice 1 修改 Tool Trace projection / durable query，追加：

```bash
source .venv/bin/activate
pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -k "runner_call"
```

若 Slice 0 更新 design / README 后没有代码变更，不需要跑测试；进入 implementation slice 后必须跑上述受影响测试和 pyright。

## README 触发判断

- 修改 `dayu/host/` 与 Host EventLog / Engine ingest / Tool Trace 语义，命中 `dayu/host/README.md`。
- 修改 `tests/host/` 测试矩阵，命中 `tests/README.md`。
- 不改变 CLI、render、utils/analyze_tool_trace.py、配置入口或项目级使用方式，不触发根 `README.md`。
- 不改变整体 `UI -> Service -> Host -> Engine` 分层、装配方式或项目级术语，不触发 `dayu/README.md`。
- 不修改 `dayu/engine/`，不触发 `dayu/engine/README.md`。

## 风险与缓解

- 风险：新增 link event 过度扩张 EventLog contract。缓解：只新增一个 Host-owned reconstruction fact，不参与 lifecycle/recovery/memory/dispatch；不修改 Engine contract。
- 风险：Tool Trace consumer 误把 prepared manifest `complete` 当作 Engine validated。缓解：README/design 明确 complete 是 assembly completeness；Engine validation 看 link event / preview validation。
- 风险：missing initial manifest 被当作 limited-signal，掩盖 Host durable truth 缺失。缓解：first iteration 无 prepared manifest 必须 rejected + stop worker stream。
- 风险：continuation index reset 后仍误匹配 ordinary manifest。缓解：只选择 unlinked prepared manifest；已有 prior iteration observation 且无 unlinked prepared 时走 continuation limited-signal，不看 index 值。
- 风险：mismatch link event 写入后 terminal / recovery 路径仍继续消费后续 Engine events。缓解：mismatch 同事务或同 ingest result append rejected diagnostic，并 `stop_worker_stream=True`。
- 风险：实现为了补 link 回写 old manifest。缓解：stop condition 禁止 mutation；测试断言 original manifest payload digest 不变。
- 风险：anti-join 查询在大 Run EventLog 下退化。缓解：查询 scope 固定到当前 `run_id` + `attempt_id` + `execution_id`，单 Attempt ordinary manifest 预期很少；若实现发现必须跨 Run/Attempt 扫描，停止回到 design gate。
- 风险：Engine 重复发送 `iteration_index=0` 且新 `iteration_id` 的 `ITERATION_STARTED`。缓解：只要当前 attempt/execution 已有 accepted prior observation 且无 unlinked prepared manifest，就按 Engine-only continuation limited-signal 记录，不误连 ordinary manifest；该异常只影响 reconstruction diagnostic，不改变 Run/Attempt lifecycle。

## Stop Condition

实施 Agent 遇到以下任一情况必须停止并回到 controller / design gate：

- 发现 current durable store / EventLog API 无法追加 `RUNNER_CALL_INPUT_ITERATION_LINKED` 而不破坏 schema 或 projection contract。
- 发现 `ENGINE_EVENT_REJECTED` 无法进入 design source event type list / matrix，或无法在 payload 中记录 `stop_worker_stream` 与 runner-call rejected reason。
- 发现 ordinary prepared manifest write 与 Attempt dispatch / worker start / `ITERATION_STARTED` ingest 之间没有 durable commit-before-start ordering guarantee。
- 发现同一 ordinary attempt/execution 在首次 Engine iteration 前可能合法存在多个 prepared manifests，且无法用现有 durable identity 唯一区分。
- 发现 `_find_unlinked_prepared_runner_call_manifest_events` 无法在同一 Host transaction 内用 bounded query 或 SQLite JSON anti-join 排除已 linked manifest。
- 发现 `_has_prior_iteration_observation` 必须依赖 `RUNNER_CALL_INPUT_ASSEMBLED` 计数、rejected event 或跨 execution event 才能识别 continuation。
- 发现 link event 与 accepted preview，或 mismatch link event 与 rejected diagnostic，无法在同一 Host transaction 中 append。
- 发现必须让 Engine 携带 Host manifest id、读取 Host store 或理解 Host policy 才能完成 link。
- 发现只能通过更新旧 `RUNNER_CALL_INPUT_ASSEMBLED` payload、manifest body 或 payload digest 才能让 Tool Trace / analyzer 工作。
- 发现需要在 LLM-facing material 中暴露 manifest id、event id、payload ref、digest、iteration link id 或其它内部治理标识。
- 发现新增 runner-call diagnostic reason 未在设计真源 / durable Tool Trace enum 闭集内定义，或新增 Engine ingest rejected reason 未在 design source 的 rejected reason 闭集内定义。
- 受影响测试或 pyright 失败，且修复需要回退到 `iteration_index == 0` 猜测、`Any` / `object` 签名、raw payload bag 或兼容 wrapper。

## Plan review lenses

- Architecture boundary review：修复只动 Host ingest / Host EventLog reconstruction；Engine 不反向依赖 Host，RunInputBuilder 不承担 Engine event correlation。
- Best-practice review：用 append-only link fact 表达后到达 observation，避免 mutation old truth；mismatch / missing fail closed。
- Optimal-solution review：比给 Engine 增加 Host manifest id 更小；比 preview-only link 更可审计；比回写 manifest 更符合 durable truth。
- Overengineering review：不引入通用 correlation framework，不扩展 public RunInputBuilder，不改变 provider request identity。
- Overcoupling review：prepared manifest、Engine preview、Tool Trace read model 分别保持 owner；link event 只通过 refs/digests 连接，不共享可变状态。
