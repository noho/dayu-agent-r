# WU-ENG-02 Slice 1 Fix - AgentCodex

## Gate / Work Unit / Slice

- gate: fix
- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- slice id: Slice 1 - Engine Contract And Agent Identity
- agent: AgentCodex

## Accepted Finding Status

1. EngineEvent / Agent outcome 中的 `client_correlation_id` 值缺少直接断言。
   - status: 已修复
   - evidence: 在既有 phase2 成功流断言 `IterationCompletedData.client_correlation_id` 与 Runner 捕获的 `RunnerRequestIdentity.client_correlation_id` 一致；在既有 phase3 工具循环与 length continuation 流断言每个 `ITERATION_COMPLETED` 事件与对应 Runner call identity 一致；在既有 finish reason mismatch 失败流断言 `IterationCompletedData` 与 terminal `RunFailedData` 均携带同一 correlation id；在既有 `run_agent_and_wait` outcome 映射测试中断言 `EngineRunOutcomeFailed.client_correlation_id` 透传。

2. `_validate_batch_bijection` 生成的 `RunFailedData` 未携带当前 tool batch 的 `client_correlation_id`。
   - status: 已修复
   - evidence: `_validate_batch_bijection` 接收 `client_correlation_id` 参数，并在 duplicate record 与 input/output id set mismatch 两条失败路径写入 `RunFailedData.client_correlation_id`；既有工具异常测试补充了 mismatch outcome 场景，断言失败 data 的 correlation id 与当前 Runner request identity 一致。

## Changed Files

- `dayu/engine/agent.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `docs/reviews/wu-eng-02-slice1-fix-codex.md`

## Validation Commands / Results

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py tests/engine/contracts/test_runner_identity.py tests/engine/contracts/test_agent_run.py tests/engine/test_metadata_boundary.py
```

Result: 127 passed.

```bash
source .venv/bin/activate && pyright
```

Result: 0 errors, 0 warnings, 0 informations.

## Residual Risks

- 本 fix gate 未进入 Slice 2/3 行为：OpenAI header policy / Host projection / Host ingest / Tool Trace 仍由后续 slice 处理。
- 本 fix gate 未执行 re-review、commit、push 或 PR gate。
- 本 fix gate 按任务要求未修改 README 或 control_doc。

## Blocking Open Questions

无。

## Completion Status

Complete for WU-ENG-02 Slice 1 fix gate.
