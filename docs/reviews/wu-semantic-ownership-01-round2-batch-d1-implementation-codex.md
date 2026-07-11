# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch D1 Implementation

## Scope

本轮只处理 Batch D1：Engine RunnerEvent / AgentPolicy / Agent state public contract ownership。未展开 Host terminal/status、tool outcome codec、compaction evidence、memory projection，也未修改 Batch E Fins read/runtime。

## Owner Corrections

- Engine public contract 现在拥有 `RunnerEvent.type` 与 `RunnerEvent.data` 的判别关系。`RunnerEvent` 构造期校验配对，OpenAI stream / non-stream adapter 复用同一个 `runner_event_type_for_data(...)` 派生 helper，不再各自维护映射。
- Engine Agent 现在拥有 final answer 空白判定。普通 final 与 force-answer final 都拒绝空字符串和纯空白字符串；Host ingest 不再用另一套 `strip()` 谓词把 Engine `final_answer` 重写为失败。
- `AgentFallbackMode` 下沉到层中立 `dayu.contracts.agent_policy`。runtime、scene、Service 与 Engine `AgentPolicy` construction boundary 复用同一枚举和值集合；`AgentPolicy` 构造时拒绝非枚举值。
- Engine Agent fallback trigger reason 收敛为 owner-level 结构化触发原因。`RAISE_ERROR` 使用同一 trigger，force-answer 自身失败时在失败消息中保留原始 trigger error code。
- Engine Agent 测试不再导入 OpenAI runner parser 私有实现；非 runner-specific Engine 测试新增 import boundary 扫描。

## Tests And Validation

- `source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py tests/engine/test_runner_event_contract.py tests/engine/test_import_boundary.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_sse_done.py tests/host/test_engine_ingest_mapping.py tests/host/test_watch_session_events.py tests/runtime/test_assembly_helpers.py tests/runtime/test_scene_prepare.py tests/runtime/test_config_loader.py tests/service/test_host_assembly.py -q`
  - Result: `436 passed, 3 warnings`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`

## Residual Risk

- D2 范围仍保留给后续批次：Host terminal/status、tool outcome codec、compaction evidence、memory projection 未在本轮修复。
- 本轮未做旧 schema / 旧接口兼容分支；按当前任务约束视为全新 owner contract 修复。

## No Commit Or Push

未 commit，未 push，未创建 PR。
