# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B S1 Implementation

## Gate 与状态

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-B`
- Slice：`S1 — Engine Event / Message Contract And RunnerDone Commit`
- Gate：implementation
- Accepted plan commit：`d1cdfca4`
- 实施状态：S1 implementation 完成；controller 已批准窄化迁移 3 个 Host negative fixtures，所有指定验证通过，无默认测试失败或 blocking question。
- 下一入口：S1 code review；按用户约束在本 artifact 后停止，本轮不请求 review。
- Artifact：`docs/reviews/wu-semantic-ownership-01-round3-r3-b-s1-implementation-codex.md`

## 读取真源与边界

本 gate 已读取并遵守：

- `AGENTS.md`
- `docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-rereview-controller-adjudication.md`
- `docs/engine/design.md`
- `docs/host/issues-implementation-control.md`
- `dayu/engine/README.md` 的 `Agent更新约束【必须遵守】`
- `tests/README.md` 的当前测试文档职责

Preflight：分支 `phaseflow/host-issues-control`，dispatch 时工作区 clean，`HEAD=d1cdfca4`。本 gate 未修改 Host production、OpenAI parser/aggregator、JSON Schema、Fins、Web/Documents、CLI、Service、README 或设计/控制真源。

### Controller scope decision

Controller 明确允许额外修改 `tests/host/test_engine_ingest_mapping.py`，只迁移以下三个旧 negative cases：

- `test_unsupported_engine_event_shape_is_rejected`
- `test_transient_delta_event_rejects_missing_or_wrong_data[17-None]`
- `test_transient_delta_event_rejects_missing_or_wrong_data[18-data1]`

迁移后，tests 直接断言 `_candidate()` 内的 `EngineEvent(...)` 在 owner 构造边界分别抛出 `ValueError` / `TypeError`；不再期待 Host ingest 生成 downstream `REJECTED` diagnostic。合法 `EngineEvent` 的 Host consumer coverage 保持不变。未使用 `object.__new__`，未修改 Host production，未添加 compatibility shim。

## 改动文件

生产代码：

- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/messages.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/agent.py`

测试：

- `tests/engine/test_engine_event_contract.py`
- `tests/engine/contracts/test_agent_run.py`
- `tests/engine/test_agent_message_union.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/host/test_engine_ingest_mapping.py`（controller 批准的 3 个 negative fixture 迁移）

Artifact：

- `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s1-implementation-codex.md`

`tests/engine/contracts/test_messages.py` 仅参与验证，最终无 diff。

## Implementation decisions 与结果

### 1. EngineEvent discriminator/data owner validation

- 在 `engine_events.py` 新增只读 `ENGINE_EVENT_TYPE_TO_DATA`，覆盖全部 19 个 `EngineEventType`，data class 唯一。
- 新增 `engine_event_type_for_data()` 与 `validate_engine_event_pairing()`；`EngineEvent.__post_init__()` 在公共构造边界调用唯一 validator。
- raw string / 非枚举 type 与联合外 data 抛 `TypeError`；合法成员间 mismatch 抛 `ValueError`。
- tests 不再复制 type/data mapping；合法 pair 全矩阵、mismatch、raw discriminator 和联合外 data 均直接断言 production owner。

### 2. AgentMessage role 与 AgentRunRequest union owner validation

- `SystemMessage`、`UserMessage`、`AssistantMessage`、`ToolMessage` 在各自构造边界校验 role 必须是 `AgentMessageRole` 且等于本类唯一固有 role。
- wrong enum role 抛 `ValueError`；与枚举同值的 raw string role 抛 `TypeError`。
- `AgentRunRequest.__post_init__()` 拒绝 `messages` 中四元封闭联合之外的实例；没有在 payload builder、Runner 或 Host 增加 role fallback。

### 3. RunnerDone typed commit fact

- `_IterationState` 删除 `done_seen`、`finish_reason`、`provider_request_id`，只保留 `runner_done: RunnerDoneData | None` 作为 completion commit 真源。
- `_classify_iteration()`、continuation guard、force-answer 与 completion log 只从 `runner_done` 读取 finish reason / provider request id。
- Agent 在接收每个 RunnerEvent 前观察 pre-done cancellation；事件被接受后才建立对应事实。接受 `RunnerDoneData` 并产出 `ITERATION_COMPLETED` 后立即结束 RunnerEvent loop，不再恢复 Runner 获取后续事件。
- done-derived failure 通过 `_make_iteration_failure_terminal()` 直接提交 `RUN_FAILED`；仅 `runner_done is None` 的 pre-done 路径继续允许 cancellation 抢占。
- tool-call done 后即使出现迟到取消，也先产出 `TOOL_CALLS_BATCH_READY` 与全部 `TOOL_CALL_REQUESTED`，再在 ToolExecutor handshake 前取消收口。

### 4. First accepted failure candidate

- 新增 module-level `_set_first_failure_candidate()`；protocol、普通 HTTP、context overflow 与 runner exception 的所有候选写入都通过该 helper。
- `state.failure_candidate =` 只存在于 helper 内一处。
- runner generator 普通异常只在没有候选时建立 `runner_exception`；已有 protocol / HTTP / context candidate 时保留其 error code、provider request id、recoverable 与 client correlation，并记录保留首候选日志。
- exception 与 cancellation 并发且没有 RunnerDone 时，外层 pre-done 仲裁仍收口 `RUN_CANCELLED`。

### 5. Invalid/missing finish_reason fail closed

- 删除 Agent 的 `state.finish_reason or FinishReason.STOP` fallback。
- `_consume_runner_event()` 在接受 `RunnerDoneData` 前校验 `finish_reason` 是 `FinishReason`；`cast(FinishReason, None)` 注入不能建立 `runner_done`、不能产出 `ITERATION_COMPLETED` 或 final/tool decision。
- 非法值通过 first-candidate helper 收口为 `RUNNER_ABNORMAL_STOP`，diagnostic 为 `runner done has invalid or missing finish reason`。

## Concrete assertions 覆盖

- EngineEvent：mapping keys 完整、data class 唯一、19 个合法 pair 全通过；mismatch / raw type / 联合外 data 分型失败。
- Message：四种正确 role 成功；四种 wrong enum 与四种 raw string role 失败。
- AgentRunRequest：空 messages 继续失败；非空合法 union 成功；cast 注入联合外成员失败。
- Post-done 五路：ordinary final、force-answer final、protocol error、HTTP error、tool-call candidate 都先由 `anext()` 驱动至目标 `ITERATION_COMPLETED`，再请求取消。
- Pre-done：取消在 RunnerDone 消费前仍为 `RUN_CANCELLED`；无 done 自然结束与异常竞态保持 fail-closed / cancellation 语义。
- First candidate：protocol、HTTP、context 三路后续 runner exception 均不覆盖首候选。
- Invalid finish：无 `ITERATION_COMPLETED`、无 final、无 tool batch，唯一 terminal 为 `RUN_FAILED(RUNNER_ABNORMAL_STOP)`。
- Runner close 与 terminal：focused matrix 中 close exactly once，terminal 唯一且最后出现。

## Validation

### Plan 必需 focused node ids

```text
pytest <plan 中 8 个 S1 node ids> -q
8 passed in 0.14s
```

通过节点：

- `test_post_done_cancel_does_not_override_ordinary_final`
- `test_post_done_cancel_does_not_override_protocol_error_failure`
- `test_post_done_cancel_does_not_override_http_error_failure`
- `test_runner_exception_preserves_first_failure_candidate`
- `test_runner_exception_and_cancel_without_done_prefers_cancel`
- `test_runner_done_with_invalid_finish_reason_fails_closed`
- `test_post_done_cancel_does_not_override_force_answer_final`
- `test_post_done_cancel_does_not_skip_tool_call_candidate`

### Plan 必需 focused file matrix

```text
pytest tests/engine/test_engine_event_contract.py \
  tests/engine/contracts/test_messages.py \
  tests/engine/contracts/test_agent_run.py \
  tests/engine/test_agent_message_union.py \
  tests/engine/test_agent_phase2.py \
  tests/engine/test_agent_phase3_tool_call.py -q
154 passed in 0.24s
```

### 扩大只读验证

```text
pytest tests/engine -q
537 passed in 2.21s
```

额外运行：

```text
pytest tests/host/test_dispatch_scheduler.py \
  tests/host/test_engine_ingest_mapping.py -q
180 passed in 2.57s
```

原三个失败均已按 controller scope decision 迁移到 owner-boundary expectation：type/data mismatch 断言 `ValueError`，联合外 `None` data 断言 `TypeError`。Host ingestor 不再承担不可构造 event 的 repair/rejection；合法 consumer matrix 保持全绿。

### Pyright

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

### Source scans

```text
rg -n 'state\.(done_seen|finish_reason|provider_request_id)' dayu/engine/agent.py
# exit 1，无命中

rg -n 'or FinishReason\.STOP' dayu/engine/agent.py
# exit 1，无命中

rg -n 'state\.failure_candidate\s*=' dayu/engine/agent.py
564:    state.failure_candidate = candidate
```

第三条只命中 module-level first-candidate helper 的唯一 owner 赋值，符合 plan。

### Whitespace

```text
git diff --check
# exit 0，无输出
```

## README / design trigger decision

- `dayu/engine/README.md`：`dayu/engine/` public contract 与 cancellation commit 行为变化，命中更新触发；但 S1 allowed files 不含 README，accepted plan 将 documentation sync 放在 S3 后统一完成，本 gate 不修改。
- `tests/README.md`：新增 Engine contract 与 cancellation ordering coverage，命中更新触发；同样按 accepted plan 延至 S3 documentation scope，本 gate 不修改。
- `docs/engine/design.md`：当前 §13/§14 已支持本实现方向，最终事实同步按 accepted plan 延至 S3；本 gate 不修改。
- `docs/host/design.md`、`dayu/host/README.md`、`dayu/README.md`、根 README、Fins/Config README：层级、durable schema、用户入口与对应 owner 未变化，不触发当前修改。

## 未改范围

- 未进入 S2；未修改 OpenAI parser、aggregator、finish policy、OLD arguments compatibility 或 error classifier markers。
- 未进入 S3；未修改 ToolParametersSchema、runtime enum equality 或共享工具 schema。
- 未修改 Host production、durable schema、ingest mapping、Fins、Web/Documents、CLI config 或 Service assembly。
- 未修改 README、设计/控制真源。
- 未 commit、未 push、未请求 code review。
- Rejected runner identity delimiter / OpenAI marker findings 保持 rejected，未伪装成已修复。

## Residual risks / uncovered areas

此前 Host negative fixture scope gap 已由 controller 决策并在当前 slice 修复；`180 passed` 证明该 residual 已关闭，分类为 `fixed in current slice`。没有直接证据支持其它当前 S1 residual risk 或 uncovered area。

## Completion report

- S1 implementation：完成。
- Plan required validation：全部通过。
- Extra Engine matrix：`537 passed`。
- Extra Host consumer matrix：`180 passed`，三个 owner-migration fixture failures 已关闭。
- `git diff --check`：通过，无输出。
- README：已判断触发，按 accepted plan 延至 S3，未修改。
- Scope：只修改 S1 allowed production/tests、controller 额外批准的单个 Host test file 与本 artifact。
- Blocking question：无。
- Current gate / next entry point：S1 implementation 完成，下一入口为 code review；按用户要求停止，不 commit、不进入 S2、不请求 code review。
