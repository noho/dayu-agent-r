# WU-SEMANTIC-OWNERSHIP-01 / P2-E Plan - AgentCodex

## Gate / Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-E`
- Gate: plan
- Trigger: P2-D accepted implementation `abd44b67` 后，controller broad validation 剩余 7 个失败。
- Plan decision: 本轮只规划，不实施、不提交。

## Goal / Motivation / Success Signal

目标是把 P2-D 后 broad validation 暴露的 7 个失败按语义 owner 分类，并给出最小、owner-correct 的修复计划。第一性原理判断：这 7 个失败目前没有直接证据指向 P2-D 生产行为回归；多数失败是旧测试快照、旧 LLM-facing 断言或旧 durable fixture 与当前已接受生产契约不一致。

成功信号：

- 7 个失败均有 root-cause 假设、仍需直接证据、owner boundary、拟修复位置和验证命令。
- 实施只落在 owner boundary：生产契约 intended 时更新测试；生产行为回归时修生产 owner。
- 不通过放宽 durable schema、移除 public contract、恢复旧英文 LLM-facing guidance 或降低 stream diagnostic gating 来让测试通过。
- `pytest` targeted、broad suite、`pyright`、`git diff --check` 通过。

非目标：

- 不修改 `docs/host/design.md` / `docs/engine/design.md` 的架构决策。
- 不改变 EngineEvent、HostEvent、Run/Attempt/Wait 状态机或 durable schema。
- 不新增兼容读取路径、兼容 re-export、下游 fallback 分支。
- 不关闭 `WU-SEMANTIC-OWNERSHIP-01` umbrella。

## Direct Evidence

- `docs/engine/design.md` 明确 `iteration_started` 携带 `input_projection`，且包根导出 `RunnerInputMessageProjection` / `RunnerInputToolCallProjection`。
- `dayu/engine/contracts/engine_events.py` 中 `IterationStartedData` 当前包含 `input_projection`，`dayu/engine/__init__.py` 当前导出两个 projection 类型。
- stream heartbeat 生产代码使用 `STREAM_DEBUG_LOG_LEVEL`；`dayu/runtime/log_levels.py` 定义其值为 `DEBUG - 1`。既有 debug-stream artifacts 明确普通 `DEBUG` 不应捕获 `stream_idle.heartbeat`，`STREAM_DEBUG` 才捕获。
- `docs/host/design.md` / `dayu/host/README.md` 明确 `HostThinkingView` 是 HostEvent 的 public typed event view；`dayu/host/api.py` 与 `dayu/host/__init__.py` 当前均导出。
- wait-resume 设计与实现已改为优先重建 `user -> assistant(tool_call) -> tool` runner input；旧 system guidance 仅为缺少 replay 参数时的 fallback。
- durable schema 明确 `cancelling` / `cancelled` Run 必须有 `cancel_request_event_id`；Host README 说明 cancel lifecycle 在 Run row 保存 typed `cancel_request_event_id`。
- 最小复现命令：
  `source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_idle.py::test_idle_heartbeat_emits_debug_log_and_does_not_drop_bytes tests/engine/test_engine_event_contract.py::test_iteration_started_runner_input_signal_fields_are_locked tests/host/test_phase7_waiting_integration.py::test_local_awaiting_tool_manual_resolve_resumes_run tests/host/test_purge_session.py::test_purge_session_durable_rejects_non_terminal_runs --tb=short -q`
  结果：`4 failed, 5 passed`，失败形态与 controller 报告一致。

## Failure Taxonomy

| Failure | Taxonomy | Severity | First-principles judgment |
|---|---|---:|---|
| 1 stream idle heartbeat | stale diagnostic-level test expectation | Low | 生产 intended 行为是 stream-only 诊断低于 DEBUG；测试还按旧 DEBUG 捕获。 |
| 2 iteration_started fields | stale Engine event contract snapshot | Medium | `input_projection` 已进入设计真源和 production contract；测试快照滞后。 |
| 3 engine `__all__` | stale Engine public export snapshot | Medium | projection 类型已被设计真源列为包根公共契约；测试快照滞后。 |
| 4 host `__all__` | stale Host public export snapshot | Medium | `HostThinkingView` 已是 HostEvent public typed view；测试快照滞后。 |
| 5 host.api `__all__` | stale Host API export snapshot | Medium | 同 failure 4；`api.py` 是 public dataclass/API owner。 |
| 6 wait-resume guidance | stale LLM-facing integration assertion | Medium | 当前生产路径应重建工具协议闭环；旧英文 guidance 只适合旧 fallback。 |
| 7 purge cancelling fixture | invalid durable fixture | Medium | 测试 fixture 直接写入 schema 禁止的非法 durable Run。 |

## Failure Details

### 1. OpenAI stream idle heartbeat

- Root-cause hypothesis: `runner.stream_idle.heartbeat` 已从普通 `DEBUG` 迁移到 `STREAM_DEBUG_LOG_LEVEL`，测试仍用 `caplog.at_level(logging.DEBUG)` 捕获，因此得不到 heartbeat。readany race 本身没有直接回归证据。
- Required direct evidence still needed:
  - 修改测试前后，用 `STREAM_DEBUG_LOG_LEVEL` 捕获该日志并确认仍不丢 bytes。
  - 必须在同一测试或同一测试文件中同时覆盖正负语义：`STREAM_DEBUG_LOG_LEVEL` 能捕获 `runner.stream_idle.heartbeat`，普通 `logging.DEBUG` 不能捕获该 heartbeat，防止破坏 `--debug` / `--debug-stream` 语义。
- Semantic owner boundary:
  - 事实产生：OpenAI Runner `_iter_response_bytes_with_idle`。
  - 诊断级别真源：`dayu.runtime.log_levels.STREAM_DEBUG_LOG_LEVEL` 与 runtime logging policy。
  - 测试 owner：`tests/engine/runners/openai/test_stream_idle.py`。
- Proposed fix location: 更新该测试的 caplog level/import；不改 `runner.py`。
- Required implementation assertion:
  - 正向断言：使用 `STREAM_DEBUG_LOG_LEVEL` 捕获 heartbeat，且继续确认 response bytes 未丢失。
  - 负向断言：使用普通 `logging.DEBUG` 捕获同类流过程时不得出现 heartbeat 记录；不得通过放宽 logger、提升生产日志级别或改 `runner.py` 让测试通过。
- Tests to run:
  - `pytest tests/engine/runners/openai/test_stream_idle.py -q`
  - `pytest tests/runtime/test_log_levels.py tests/runtime/test_log.py tests/engine/runners/openai/test_runner_diagnostics.py -q`

### 2. `IterationStartedData` extra `input_projection`

- Root-cause hypothesis: Engine production contract 已扩展 `iteration_started` runner input signal，测试快照仍锁定旧字段集合。
- Required direct evidence still needed:
  - 用 `docs/engine/design.md` 与 P2-B/P2-C/P2-D artifacts 确认 `input_projection` 是 accepted public contract，而不是未审泄漏。
  - 检查 `tests/engine/test_engine_event_contract.py` 是否还需断言 projection 不含 Host refs/provider secrets。
- Semantic owner boundary:
  - 事实产生：Engine Agent 在调用 Runner 前观察实际 messages。
  - 事实投影：`RunnerInputMessageProjection` / `RunnerInputToolCallProjection`。
  - Public contract owner：`dayu/engine/contracts/engine_events.py`。
  - 快照测试 owner：`tests/engine/test_engine_event_contract.py`。
- Proposed fix location: 更新测试字段集合，并优先增加 projection shape/no-host-ref 断言；不移除生产字段。
- Tests to run:
  - `pytest tests/engine/test_engine_event_contract.py -q`
  - `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py -q`（确认 Host ingestion/RunInput 消费仍一致）

### 3. `dayu.engine.__all__` extra projection types

- Root-cause hypothesis: `RunnerInputMessageProjection` 与 `RunnerInputToolCallProjection` 已是 Engine public contract，`EXPECTED_EXPORTS` 未同步。
- Required direct evidence still needed:
  - 再核对 `docs/engine/design.md` 包根导出段与 `dayu/engine/contracts/__init__.py`。
  - 确认两个类型不是实现类、不是 runner 私有 adapter 类型。
- Semantic owner boundary:
  - Public export owner：`dayu.engine.__all__`。
  - Snapshot owner：`tests/engine/test_package_exports.py`。
- Proposed fix location: 更新 `EXPECTED_EXPORTS`，并保留 forbidden implementation classes 不可导出断言。
- Tests to run:
  - `pytest tests/engine/test_package_exports.py -q`

### 4. `dayu.host.__all__` extra `HostThinkingView`

- Root-cause hypothesis: `HostThinkingView` 已成为 Host public `HostEvent.thinking` typed view，包根导出 intended；测试快照未更新。
- Required direct evidence still needed:
  - 核对 `dayu/host/api.py::HostEvent` 对 `thinking: HostThinkingView | None` 的校验。
  - 核对 `dayu/host/read_api.py` 是否实际投影 reasoning delta 到 `HostThinkingView`。
- Semantic owner boundary:
  - Public API owner：`dayu.host.api`。
  - Package root public surface owner：`dayu.host.__init__`。
  - Snapshot owner：`tests/host/test_package_exports.py`。
- Proposed fix location: 更新 `EXPECTED_HOST_EXPORTS`；不移除生产导出。
- Tests to run:
  - `pytest tests/host/test_package_exports.py tests/host/test_read_api.py -q`

### 5. `dayu.host.api.__all__` extra `HostThinkingView`

- Root-cause hypothesis: 同 failure 4；API module `__all__` intended 包含 `HostThinkingView`。
- Required direct evidence still needed:
  - 同 failure 4。
- Semantic owner boundary:
  - API export owner：`dayu/host/api.py`。
  - Snapshot owner：`tests/host/test_package_exports.py::test_api_all_stays_request_snapshot_boundary`。
- Proposed fix location: 更新 `EXPECTED_API_EXPORTS`；不改生产 API。
- Tests to run:
  - `pytest tests/host/test_package_exports.py::test_api_all_stays_request_snapshot_boundary -q`

### 6. Phase 7 wait-resume integration still expects old English guidance

- Root-cause hypothesis: integration test 仍断言旧 fallback system guidance `"A previous interrupted step..."`、`tool_name=...`、`resolution_kind=completed`。当前 production owner 已在 RunInputBuilder 中优先重建 `UserMessage`、`AssistantMessage(tool_call)`、`ToolMessage`，fallback guidance 也已中文自解释。
- Required direct evidence still needed:
  - implementation 第一步必须在该 integration path 中诊断 `resume_request.messages`，记录实际 message types、tool call id、tool name、arguments 与 tool result JSON。
  - 确认该测试经 production `DefaultHostToolAwaitingAcceptPort` 写入 request atom / accepted evidence envelope，而不是旧 fixture fallback。
- Semantic owner boundary:
  - 等待事实产生/持久化：Host ToolRuntime awaiting accept path、wait record、`TOOL_CALL_REQUESTED` request atom、`TOOL_AWAITING`、`TOOL_RESULT_ACCEPTED`。
  - LLM-facing resume projection owner：`dayu/host/run_input.py`。
  - Integration assertion owner：`tests/host/test_phase7_waiting_integration.py`。
- Proposed fix location: 更新 integration test，断言当前协议闭环：
  - 包含当前 user prompt。
  - 正常路径必须断言 message 顺序和类型为 `UserMessage -> AssistantMessage(tool_call) -> ToolMessage`。
  - assistant tool call 的 `id/name/arguments` 与原 awaiting request 一致或为 LLM-safe replay 投影；其中 `AssistantToolCall.id` 必须等于原 awaiting `tool_call_id`。
  - `ToolMessage.tool_call_id` 必须等于同一个 `AssistantToolCall.id`，content JSON 包含 `answer: 42`。
  - 不再要求旧英文 fallback guidance。
- Fixture/request-atom policy:
  - 如果诊断发现只有当前中文 fallback guidance，先修测试 fixture / request atom / accepted evidence envelope，让正常协议闭环路径可被覆盖，再迁移 assertion。
  - 如果诊断发现旧英文 guidance 仍出现，停止 Slice E2 wait-resume alignment，并升级 production owner（`dayu/host/run_input.py` / awaiting accept path）；不得把旧英文 guidance 当成可接受输出。
- Tests to run:
  - `pytest tests/host/test_phase7_waiting_integration.py::test_local_awaiting_tool_manual_resolve_resumes_run -q`
  - `pytest tests/host/test_resolve_wait_command.py tests/host/test_run_input_builder.py tests/host/test_wait_awaiting_accept.py -q`

### 7. Purge non-terminal `cancelling` fixture violates durable CHECK

- Root-cause hypothesis: purge test fixture 直接插入 `status='cancelling'` Run，但未写 `cancel_request_event_id`。生产 schema 正确拒绝非法 durable truth；测试在到达 purge precondition 前已经造数失败。
- Required direct evidence still needed:
  - 确认 `_SeedClosedSessionMatrixOperation(run_status='cancelling')` 是唯一违规入口。
  - 检查相关 parametrize 是否包含 `cancelled`；若包含，`cancelled` fixture 必须同样补合法 `cancel_request_event_id`。
  - 确认 fixture 修复后 purge helper 仍按预期拒绝 non-terminal Run，而不是因为其它 CHECK 失败。
- Semantic owner boundary:
  - Durable schema invariant owner：`dayu/host/durable/schema.py`。
  - Cancel lifecycle truth owner：Host admission / run transition 写入 `CANCEL_REQUESTED` 并把 event id 保存在 Run row。
  - Test fixture owner：`tests/host/test_purge_session.py`。
- Proposed fix location: 在 test fixture 中为 `cancelling` Run 写入 dedicated cancel request EventLog row（使用专用 event id，不能复用任意已有 event），并把 `cancel_request_event_id` 插入 Run row；若相关 parametrize 包含 `cancelled`，同样应用该 durable invariant fix；不放宽 schema，不在 purge helper 捕获 CHECK 失败。
- Tests to run:
  - `pytest tests/host/test_purge_session.py::test_purge_session_durable_rejects_non_terminal_runs -q`
  - `pytest tests/host/test_purge_session.py -q`

## Slice Recommendation

不建议拆成 7 个 sub WU，也不建议按示例拆成 A/B/C 三个 implementation WU。原因：

- 7 个失败都来自同一次 broad validation，且当前直接证据都指向测试快照/fixture 对 accepted production contract 的滞后。
- 修复面虽跨 Engine/Host，但每个修复都只改测试断言或测试 fixture，不改变生产契约；拆成过多 WU 会让 gate 成本高于实现风险。
- stream idle heartbeat 与 Engine contract/export 都属于 Engine 测试对既有 public/diagnostic contract 的 alignment，可合并为一个 Engine test-owner slice。
- Host export、wait-resume integration、purge fixture 都属于 Host 测试对已接受 public/durable/LLM-facing contract 的 alignment，可合并为一个 Host test-owner slice。

推荐一个 sub WU：`P2-E validation fallout alignment`，两个 implementation slices：

### Slice E1 - Engine contract / stream diagnostic test alignment

- Objective: 修复 failures 1、2、3。
- Allowed files:
  - `tests/engine/runners/openai/test_stream_idle.py`
  - `tests/engine/test_engine_event_contract.py`
  - `tests/engine/test_package_exports.py`
- Exact allowed changes:
  - heartbeat test 使用 `STREAM_DEBUG_LOG_LEVEL` 捕获 stream heartbeat，并正向断言 heartbeat 可见、bytes 不丢失；同时负向断言普通 `logging.DEBUG` 不捕获 heartbeat。
  - `IterationStartedData` 字段快照纳入 `input_projection`，必要时补 projection shape/no internal refs 断言。
  - Engine `EXPECTED_EXPORTS` 纳入两个 projection public types。
- Stop condition: 若发现 `input_projection` 或 projection types 没有 accepted design / artifact 支撑，停止并要求生产契约裁决，不改快照。

### Slice E2 - Host public export / wait-resume / purge fixture alignment

- Objective: 修复 failures 4、5、6、7。
- Allowed files:
  - `tests/host/test_package_exports.py`
  - `tests/host/test_phase7_waiting_integration.py`
  - `tests/host/test_purge_session.py`
- Exact allowed changes:
  - Host/API expected exports 纳入 `HostThinkingView`。
  - wait-resume integration 先诊断 `resume_request.messages`；正常路径改断言当前 `UserMessage -> AssistantMessage(tool_call) -> ToolMessage` LLM-facing replay，并检查 `AssistantToolCall.id` 与原 awaiting `tool_call_id` 一致、`ToolMessage.tool_call_id` 与该 id 一致；不断言旧英文 guidance。
  - purge fixture 为 `cancelling` Run 补 dedicated cancel request EventLog ref；若 `cancelled` 在相关 parametrize 中，同样补 `cancel_request_event_id`。
- Stop condition and split policy:
  - 若 `resume_request.messages` 是当前中文 fallback guidance 或缺 request atom / accepted evidence envelope，先修 fixture/request atom，使测试覆盖正常协议闭环路径，再迁移 assertion。
  - 若 `resume_request.messages` 仍出现旧英文 guidance，停止 wait-resume alignment，并升级 production owner（`dayu/host/run_input.py` / awaiting accept path）。
  - 如果 wait-resume 诊断触发 production owner，Slice E2 必须拆分：先独立完成 Host export / purge fixture alignment，再把 wait-resume 作为 production-owner follow-up slice 处理；不得让 wait-resume production 风险阻塞已确认的 Host export / purge fixture 测试对齐。

## Validation Plan

Targeted:

```bash
source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_idle.py -q
source .venv/bin/activate && pytest tests/engine/test_engine_event_contract.py tests/engine/test_package_exports.py -q
source .venv/bin/activate && pytest tests/host/test_package_exports.py -q
source .venv/bin/activate && pytest tests/host/test_phase7_waiting_integration.py::test_local_awaiting_tool_manual_resolve_resumes_run -q
source .venv/bin/activate && pytest tests/host/test_purge_session.py::test_purge_session_durable_rejects_non_terminal_runs -q
```

Regression:

```bash
source .venv/bin/activate && pytest tests/host/test_resolve_wait_command.py tests/host/test_run_input_builder.py tests/host/test_wait_awaiting_accept.py -q
source .venv/bin/activate && pytest tests/runtime/test_log_levels.py tests/runtime/test_log.py tests/engine/runners/openai/test_runner_diagnostics.py -q
source .venv/bin/activate && pytest tests/engine tests/runtime tests/service/test_host_assembly.py tests/host -q
source .venv/bin/activate && pyright
git diff --check
```

Expected broad result: controller suite moves from `7 failed` to all pass, preserving existing skipped/deselected/warning profile unless unrelated tests changed.

## README / Doc Trigger Analysis

Plan artifact itself does not change production code, tests, public behavior, schema, CLI behavior, or README-owned user workflows.

Implementation trigger expectations:

- Slice E1 only changes `tests/engine/*`; per AGENTS trigger, check `tests/README.md`. Likely no update because no new test category or command is introduced. `dayu/engine/README.md` should not need update because production Engine contract is already documented.
- Slice E2 only changes `tests/host/*`; check `tests/README.md`. Likely no update because fixture/assertion alignment does not introduce a new test layer. `dayu/host/README.md` should not need update because `HostThinkingView`, wait-resume replay, cancel request durable invariant, and purge precondition are already documented.
- If implementation discovers a real production contract change is required, re-evaluate corresponding README triggers before coding.

Implementation closeout requirement:

- 必须显式记录 Engine `input_projection` / projection export snapshot alignment 与 Host `HostThinkingView` export snapshot alignment 均是测试对既有 design / README public contract 的对齐；生产代码、生产契约和 README 不需要变更。
- 若 wait-resume 诊断触发 production owner，closeout 必须记录 Slice E2 已拆分，以及 Host export / purge fixture alignment 与 wait-resume follow-up 的边界。

## Propagation Audit Expectations For Wait-Resume LLM-facing Semantics

If Slice E2 only updates stale test expectations, propagation audit should record no production LLM-facing text change:

1. Awaiting accept persists `TOOL_CALL_REQUESTED` request atom, `TOOL_AWAITING`, wait record, and accepted replay arguments / digest.
2. `resolve_wait` persists `TOOL_RESULT_ACCEPTED` with accepted evidence envelope and raw outcome.
3. `RunInputBuilder` reads the current resume `RUN_STARTED` ref and accepted result projection.
4. Normal path projects `UserMessage -> AssistantMessage(tool_call) -> ToolMessage` from the same request atom/result truth.
5. Fallback path uses only current Chinese self-explaining guidance when replay arguments are unavailable; no old English guidance, `tool_name=...` key-value phrasing, wait id, event id, payload ref, digest, poll/runtime terminology, or Host governance terms should be asserted as required LLM context.
6. Memory, compact, trace, audit and read-model outputs must remain derived from canonical EventLog / shared accepted-result projection, not from test-only strings.

If implementation changes production wait-resume text, it must include focused tests proving the text is self-contained, Chinese, business-readable, and does not expose Host/ToolRuntime governance identifiers.

## Risks / Open Questions

- Risk: updating snapshots without reconfirming design would mask unintended public contract expansion. Mitigation: each snapshot update is gated by design/artifact evidence listed above.
- Risk: purge fixture could be made schema-valid but semantically poor by pointing `cancel_request_event_id` at an arbitrary terminal event. Mitigation: prefer adding an explicit cancel request EventLog row in the fixture, even if the purge matrix helper uses generic test event rows.
- Risk: wait-resume integration might expose a real production regression if protocol messages are absent. Mitigation: Slice E2 stop condition requires inspecting actual messages before changing assertion.
- No blocking open question for implementation if this plan is accepted.

## Completion Report Format

Implementation closeout should state:

- Which tests/fixtures were aligned and why production code was unchanged, or which stop condition forced a production owner fix.
- Exact validation commands and pass/fail result.
- README/doc decisions.
- Residual risks, especially any uncovered wait-resume real-provider behavior or broad-suite warnings.
