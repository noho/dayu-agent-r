# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B S1 Code Review — AgentMiMo

## Review Target

`dayu/engine/contracts/engine_events.py`、`dayu/engine/contracts/messages.py`、`dayu/engine/contracts/agent_run.py`、`dayu/engine/agent.py` 的 S1 实现改动；`tests/host/test_engine_ingest_mapping.py` 的 3 个 controller 批准 fixture 迁移。

## Design / Control Context

- `docs/engine/design.md` §13 Cancellation Commit Boundary、§14 EngineEvent Stream
- `docs/host/design.md` §13.4 Host ingest mapping
- `AGENTS.md` 语义所有权与修复边界、LLM-facing 文本约束

## Review Focus 验证

### 1. EngineEvent runtime validation ✅

- `ENGINE_EVENT_TYPE_TO_DATA` 使用 `MappingProxyType` 只读 mapping，覆盖全部 19 个 `EngineEventType`。
- `engine_event_type_for_data()` 使用 `isinstance` 遍历 mapping，对联合外 data 抛 `TypeError`。
- `validate_engine_event_pairing()` 校验 type 非枚举抛 `TypeError`，type/data mismatch 抛 `ValueError`。
- `EngineEvent.__post_init__()` 调用 `validate_engine_event_pairing()`，在构造边界拦截非法 pairing。
- 测试 `test_engine_event_contract.py` 不再复制 mapping；合法 pair 全矩阵、mismatch、raw type、联合外 data 均断言 production owner。
- Host `test_engine_ingest_mapping.py` 3 个旧 negative fixture 迁移到 owner-boundary expectation：`_candidate()` 内 `EngineEvent(...)` 构造抛 `ValueError`/`TypeError`，Host ingestor 不再承担 repair。
- 未使用 `object.__new__`，未修改 Host production，未新增 Host downstream repair。

### 2. AgentMessage role / AgentRunRequest union validation ✅

- `_validate_message_role()` 私有 helper：非 `AgentMessageRole` 抛 `TypeError`，role 不匹配固有 role 抛 `ValueError`。
- 四种 message dataclass 各自在 `__post_init__` 调用该 helper，校验本类唯一固有 role。
- `AgentRunRequest.__post_init__()` 使用 `isinstance` 四元 tuple 检查 messages 联合成员，拒绝联合外实例抛 `TypeError`。
- 未在 payload builder、Runner 或 Host 增加 role fallback。

### 3. RunnerDone commit boundary ✅

- `_IterationState` 删除 `done_seen`、`finish_reason`、`provider_request_id`，只保留 `runner_done: RunnerDoneData | None`。
- Runner event loop：先检查 pre-done cancellation → 消费事件 → 产出 engine events → 检查 `runner_done is not None` 则 break → 检查 post-done cancellation。顺序正确。
- `_make_iteration_failure_terminal()` 新 helper：`runner_done is not None` 时直接 `_make_terminal_failed(failure)` 不检查取消；`runner_done is None` 时 fallthrough 到 `_make_failed_or_cancelled_terminal_with_close(failure)` 检查取消。
- 5 个 post-done 测试均使用 `_collect_with_cancel_after_iteration_completed()` 驱动到 `ITERATION_COMPLETED` 后才 `token.request_cancel()`，断言 done-derived terminal 不被覆盖。
- tool-call done 后迟到取消：先产出 `TOOL_CALLS_BATCH_READY` + 全部 `TOOL_CALL_REQUESTED`，再在 ToolExecutor handshake 前取消收口（line 1963-1965）。
- Pre-done cancellation 保留：`_make_cancelled_terminal_with_close()` 在 pre-done 路径继续使用。
- `_make_failed_or_cancelled_terminal_with_close` 仅在 pre-done 上下文中使用（max_iterations check、missing terminal、tool batch failure、fallback RAISE_ERROR、fallback missing terminal）。

### 4. First-candidate helper ✅

- `_set_first_failure_candidate()` module-level helper：`state.failure_candidate is not None` 时返回 `False` 不覆盖；否则写入并返回 `True`。
- `state.failure_candidate =` 只存在于 helper 内 line 564。
- Protocol error、HTTP error、context overflow、runner exception 四路全部通过该 helper 写入。
- Runner exception 后检查 `candidate_accepted`，未接受时记录 warning 日志保留首候选。
- Source scan `rg -n 'state\.failure_candidate\s*=' dayu/engine/agent.py` 只命中 helper 内唯一赋值。

### 5. Invalid/missing finish_reason fail closed ✅

- `_consume_runner_event()` 在接受 `RunnerDoneData` 前校验 `isinstance(data.finish_reason, FinishReason)`。
- 非法值通过 `_set_first_failure_candidate` 收口为 `RUNNER_ABNORMAL_STOP`，diagnostic 为 `runner done has invalid or missing finish reason`。
- 不产出 `ITERATION_COMPLETED`，不写入 `state.runner_done`。
- `_classify_iteration()` 在 `runner_done is None` 时走 failure/abnormal-stop fail-closed 分支。
- `or FinishReason.STOP` fallback 已删除，source scan 无命中。
- Test `test_runner_done_with_invalid_finish_reason_fails_closed` 覆盖 `cast(FinishReason, None)` 注入。

### 6. Host test migration ✅

- `test_unsupported_engine_event_shape_is_rejected`：旧测试断言 `EngineEventIngestor.ingest()` 返回 `REJECTED`；新测试断言 `_candidate()` 内 `EngineEvent(...)` 构造抛 `ValueError`。语义从"Host 拒绝非法 event"迁移到"EngineEvent owner 拒绝非法 pairing"。
- `test_transient_delta_event_rejects_missing_or_wrong_data`：两个 parametrize case 同样迁移到 owner-boundary expectation。
- 合法 `EngineEvent` 的 Host consumer coverage 保持不变（`test_transient_delta_event_accepts_matching_type_without_row` 等未修改）。
- 未使用 `object.__new__`，未削弱合法 Host ingest coverage。

### 7. 无兼容 shim / hasattr/getattr / loose parsing / 反向依赖 ✅

- Diff 中无 `hasattr`/`getattr` 新增。
- 无 compatibility shim、feature flag、provider 名单或 loose parsing。
- 无反向依赖：改动只在 Engine contracts 和 Agent 内部。
- README trigger decision 按 accepted plan 延至 S3 documentation scope。

## Findings

未发现实质性问题。S1 实现完整覆盖 plan 的 5 项 frozen decisions 和所有 concrete assertions。EngineEvent/message validation 在正确 owner，RunnerDone commit boundary 真正防止 post-done cancellation overwrite，first-candidate helper 是唯一 failure_candidate writer，invalid/missing finish_reason fail closed，Host test 迁移合理。

## Open Questions

无。

## Residual Risks

| Risk | Classification | Owner |
| --- | --- | --- |
| `run_agent_and_wait` 对非法 terminal 现在抛 `ValueError` 而非返回 `EngineRunOutcomeFailed` | 行为变更，符合 plan intent | Engine public contract；调用方需处理 `ValueError` |
| README/design sync 延至 S3 | accepted plan sequencing | S3 documentation scope |

## Code Review Conclusion

**status: pass**

S1 实现正确落实 plan 的所有 implementation decisions。EngineEvent/message validation 在 owner 构造边界，RunnerDone commit boundary 防止 post-done cancellation overwrite，first-candidate helper 统一管理 failure_candidate，invalid/missing finish_reason fail closed，Host test 迁移不削弱 coverage。无新增 compat shim、hasattr/getattr 或反向依赖。

**artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s1-code-review-mimo.md`
**findings**: 0
**blocking questions**: 0
