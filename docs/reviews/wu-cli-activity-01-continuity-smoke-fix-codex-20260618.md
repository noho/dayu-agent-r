# WU-CLI-ACTIVITY-01 Continuity Smoke Fix 实现记录

## Root Cause

两个 public smoke failure 的根因都在 Host continuity 真源边界，而不是 smoke 语义过期。

1. final answer continuity 写入端把 Engine `final_answer.content` 放在 terminal artifact 的 nested `summary.content` 中；而 continuity resolver 按既定裁决只允许读取 `RUN_SUCCEEDED.final_answer` 或 digest 校验后的 terminal artifact 顶层 `content`。因此第二轮 RunInput 无法从第一轮 terminal artifact hydrate 原始 final answer。
2. tool evidence memory delta 在缺少直接文本时会 fallback 到 `event_ref` / `payload_ref` / `payload_digest` 摘要；同时 durable projection / inline repair 只读取 hot EventLog payload，遇到 accepted tool result 冷 payload descriptor 时拿不到 `raw_tool_outcome`。因此后续 run 看到的是内部引用而不是原始工具响应。

## 改动

- 将 terminal continuity helper 从 `dayu.host.terminal_summary_payload` 收敛为 `dayu.host.terminal_payload`，只读取允许字段：`RUN_SUCCEEDED.final_answer` 与 terminal artifact 顶层 `content`。`summary_text`、nested `summary.content`、preview 字段均不是 continuity 来源。
- `EngineEventIngestor` 写 terminal artifact 时不再写 `payload["summary"]` 容器；当前 terminal artifact schema 以顶层 `content` / `finish_reason` / `filtered` / `degraded` 以及失败、取消、lost 顶层 diagnostic 字段为真源，并保留必要 provenance 字段。
- `read_api` 成功终态 public projection 改为读取 digest-checked terminal artifact 顶层字段，不再要求 nested `summary` object。
- 在 `dayu.host.evidence` 抽出 accepted evidence envelope 校验与 `raw_tool_outcome` 文本读取 helper；`compact_material`、`compaction_evidence`、durable memory projection 与 RunInput inline repair 复用同一语义。
- `ConversationMemory` 的 accepted tool evidence selected item 不再用 `display_text` / `content` / event ref / payload ref fallback；有 accepted envelope 时必须读取 `raw_tool_outcome`，出现旧 `result_preview` 或缺 raw outcome 会 fail closed。
- `ConversationMemory` 的 `USER_INPUT_ACCEPTED` selected item 在缺少 `display_text` 时不再 fallback 到 `event_ref` / `payload_ref` / `payload_digest`；改为不含内部治理标识的中性占位文本，并删除 `_ref_summary_text` fallback。
- public tool wiring smoke 增加反向断言，禁止 `event_ref=`、`payload_ref=`、`payload_digest=`、`result_preview` 进入后续 RunInput。

## 测试

- `source .venv/bin/activate && pytest tests/host/test_terminal_payload.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_compaction_operation.py tests/host/test_engine_ingest_mapping.py::test_final_answer_closes_attempt_and_run_with_phase5_payload tests/host/test_public_open_host_multiturn_smoke.py::test_deterministic_two_turn_request_contains_prior_final_answer tests/host/test_public_tool_wiring_smoke.py::test_mock_tool_result_feeds_same_run_and_later_run_continuity -q`
  - 结果：`178 passed`
- `source .venv/bin/activate && pyright dayu/host/_terminal_answer.py dayu/host/terminal_payload.py dayu/host/engine_ingest.py dayu/host/read_api.py dayu/host/evidence.py dayu/host/memory.py dayu/host/durable/memory.py dayu/host/run_input.py dayu/host/compact_material.py dayu/host/compaction_evidence.py tests/host/test_terminal_payload.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_open_host_multiturn_smoke.py`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过

补充修复验证：

- `source .venv/bin/activate && pytest tests/host/test_memory_projection.py::test_user_input_missing_display_text_does_not_expose_refs -q`
  - 结果：通过
- `source .venv/bin/activate && pyright dayu/host/memory.py tests/host/test_memory_projection.py`
  - 结果：通过

## README 判断

本次改动未改变 Host / Engine public API 或用户工作流，也未新增测试层级；`dayu/host/README.md` 与 `tests/README.md` 按各自更新边界无需修改。

## 风险

- 现有 durable 字段名 `terminal_summary_ref` / `terminal_summary_digest` 仍保留，以避免修改当前 Host public / durable contract；其指向内容的当前语义已改为 terminal payload artifact 顶层字段。
- 对旧 nested `summary` terminal artifact 不做兼容读取；按当前裁决按全新 schema 起库处理。
