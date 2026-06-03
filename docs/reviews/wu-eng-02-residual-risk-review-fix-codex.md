# WU-ENG-02 Residual Risk Review Fix 处理记录

## 接受的 finding

DS 复审低严重度 finding 成立：`test_tool_execution_timeout_wins_over_runner_close_cancel` 与另外两个工具超时测试相比，缺少对 terminal `RunFailedData.client_correlation_id` 的直接断言。该缺口是测试覆盖不一致，不是生产路径缺陷；三个工具超时变体仍走同一超时收口分支。

S3-R1 保持总控裁决：继续 defer 到 WU-OBS-00 / GitHub Issue #70 analyzer contract，本次不修改 `UsageReportedData` 或 Host usage projection。

## 改动

- 在 `tests/engine/test_agent_phase3_tool_call.py` 的 `test_tool_execution_timeout_wins_over_runner_close_cancel` 中先断言 `runner.request_identities_seen[0] is not None`。
- 补齐断言：`failed.client_correlation_id == runner.request_identities_seen[0].client_correlation_id`。

## 验证

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py::test_tool_execution_timeout_wins_over_runner_close_cancel tests/engine/test_agent_phase3_tool_call.py tests/engine/contracts/test_runner_spec.py tests/engine/runners/openai/test_request_identity.py tests/host/test_run_attempt_transitions.py
```

结果：`125 passed in 0.74s`。

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。Pyright 额外提示有新版本 `v1.1.410`，不影响本次验证。
