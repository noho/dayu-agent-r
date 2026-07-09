# WU-SEMANTIC-OWNERSHIP-01 / P2-E Implementation Controller Validation

## Scope

本 artifact 记录 controller 对 AgentCodex P2-E implementation 的本地复核。P2-E 目标是关闭 P2-D 后 broad matrix 暴露的 7 个 stale test / fixture alignment failures。

输入 artifact：

- `docs/reviews/wu-semantic-ownership-01-p2-e-plan-codex.md`
- `docs/reviews/wu-semantic-ownership-01-p2-e-plan-rereview-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-p2-e-implementation-codex.md`

## Diff Scope

生产代码未修改。变更范围仅为 P2-E 允许的测试 / fixture 文件：

- `tests/engine/runners/openai/test_stream_idle.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_package_exports.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_phase7_waiting_integration.py`
- `tests/host/test_purge_session.py`

Controller 另补了新增 / 修改测试函数与 helper 的中文 docstring 参数 / 返回值 / 异常说明，不改变行为。

## Owner-Boundary Check

- Stream heartbeat：测试 capture level 对齐 `STREAM_DEBUG_LOG_LEVEL`；普通 `logging.DEBUG` 负向断言使用等价 idle 条件，未修改 runner 生产日志级别。
- Engine event / export snapshot：测试快照对齐 `docs/engine/design.md` 已接受的 `input_projection` 与 projection public exports。
- Host export snapshot：测试快照对齐 `dayu/host/README.md` 已接受的 `HostThinkingView` public typed view。
- Wait-resume：实际诊断显示 `resume_request.messages` 已是 `SystemMessage` 后接 `UserMessage -> AssistantMessage(tool_call) -> ToolMessage`，无旧英文 guidance；测试改为断言 protocol closure 与 `tool_call_id` identity closure。
- Purge fixture：`_NON_TERMINAL_RUN_STATUSES` 不包含 `cancelled`；fixture 只在 `cancelling` / `cancelled` 状态按需生成 dedicated `CANCEL_REQUESTED` EventLog row，并写入 `cancel_request_event_id`，未放宽 durable schema。

## Validation

Controller rerun passed:

```bash
source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_idle.py::test_idle_heartbeat_emits_debug_log_and_does_not_drop_bytes tests/engine/test_engine_event_contract.py::test_iteration_started_runner_input_signal_fields_are_locked tests/engine/test_package_exports.py::test_engine_all_matches_expected_set tests/host/test_package_exports.py::test_host_all_matches_current_public_contracts tests/host/test_package_exports.py::test_api_all_stays_request_snapshot_boundary tests/host/test_phase7_waiting_integration.py::test_local_awaiting_tool_manual_resolve_resumes_run 'tests/host/test_purge_session.py::test_purge_session_durable_rejects_non_terminal_runs[cancelling]' -q
# 7 passed in 0.52s
```

```bash
source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_idle.py tests/engine/test_engine_event_contract.py tests/engine/test_package_exports.py tests/host/test_package_exports.py tests/host/test_phase7_waiting_integration.py tests/host/test_purge_session.py -q
# 65 passed in 1.70s
```

```bash
source .venv/bin/activate && pytest tests/engine tests/runtime tests/service/test_host_assembly.py tests/host -q
# 2596 passed, 1 skipped, 5 deselected, 3 warnings in 59.05s
```

```bash
source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_idle.py tests/host/test_purge_session.py -q
# 32 passed in 1.79s
```

```bash
source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations
```

```bash
git diff --check
# passed
```

The broad matrix warnings are existing `edgar` dependency deprecation warnings and are unrelated to P2-E.

## README / Doc Trigger

No README update required. This implementation changes tests only and aligns them to already documented production contracts in `docs/engine/design.md` and `dayu/host/README.md`. No new test category or command convention was introduced.

## Controller Result

Implementation is ready for AgentMiMo / AgentDS code review.
