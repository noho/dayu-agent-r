# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B S1 Controller Validation

## 范围

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-B`
- Slice：`S1 — Engine Event / Message Contract And RunnerDone Commit`
- Implementation artifact：`docs/reviews/wu-semantic-ownership-01-round3-r3-b-s1-implementation-codex.md`
- Controller validation time：2026-07-12

## 范围裁决

S1 生产修改只触及 accepted plan 允许的 Engine files：

- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/messages.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/agent.py`

测试修改除 S1 allowed tests 外，额外包含 `tests/host/test_engine_ingest_mapping.py`。该额外测试修改由 controller 在 implementation gate 中批准，原因是 EngineEvent runtime validation 将非法 type/data pairing 的 owner 前移到 EngineEvent 构造边界，旧 Host negative fixture 继续构造非法 `EngineEvent(...)` 会让默认 Host matrix 失败。该修改只迁移 3 个旧测试到 owner-boundary expectation，没有修改 Host production，没有使用 `object.__new__` 绕过构造器，也没有新增 Host downstream repair。

## Controller rerun

### S1 high-risk node ids

```text
pytest tests/engine/test_agent_phase2.py::test_post_done_cancel_does_not_override_ordinary_final tests/engine/test_agent_phase2.py::test_post_done_cancel_does_not_override_protocol_error_failure tests/engine/test_agent_phase2.py::test_post_done_cancel_does_not_override_http_error_failure tests/engine/test_agent_phase2.py::test_runner_exception_preserves_first_failure_candidate tests/engine/test_agent_phase2.py::test_runner_exception_and_cancel_without_done_prefers_cancel tests/engine/test_agent_phase2.py::test_runner_done_with_invalid_finish_reason_fails_closed tests/engine/test_agent_phase3_tool_call.py::test_post_done_cancel_does_not_override_force_answer_final tests/engine/test_agent_phase3_tool_call.py::test_post_done_cancel_does_not_skip_tool_call_candidate -q
8 passed in 0.15s
```

### S1 focused file matrix

```text
pytest tests/engine/test_engine_event_contract.py tests/engine/contracts/test_messages.py tests/engine/contracts/test_agent_run.py tests/engine/test_agent_message_union.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q
154 passed in 0.27s
```

### Host consumer matrix

```text
pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py -q
180 passed in 2.71s
```

### Pyright

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

### Source scans

```text
rg -n 'state\.(done_seen|finish_reason|provider_request_id)' dayu/engine/agent.py
# no output

rg -n 'or FinishReason\.STOP' dayu/engine/agent.py
# no output

rg -n 'state\.failure_candidate\s*=' dayu/engine/agent.py
564:    state.failure_candidate = candidate
```

The remaining `state.failure_candidate =` hit is the module-level first-candidate helper owner assignment.

### Whitespace

```text
git diff --check
# no output
```

## Controller conclusion

S1 implementation is ready for code review. No blocking question remains. Review focus should include:

- EngineEvent validation does not break legitimate Engine/Host producers.
- Message role validation and AgentRunRequest union validation do not force downstream repair.
- RunnerDone commit boundary genuinely prevents post-done cancellation overwrite while preserving pre-done cancellation.
- First failure candidate helper is the sole failure candidate writer.
- Invalid/missing finish reason fails closed without reintroducing `STOP` fallback.
- Host test migration reflects owner-boundary movement rather than weakening Host coverage.
