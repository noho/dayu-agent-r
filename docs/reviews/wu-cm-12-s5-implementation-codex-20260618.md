# WU-CM-12 S5 Implementation Artifact

## Changed Files

- `dayu/host/context_fallback.py`
  - `EventLogContextFallbackProvider` 读取 proactive fallback payload 后，重建与 dispatch tier4 selector 同源的 EventLog-backed material view，并挂到内部 `ActiveRecentWindowFallback.material_blocks`。
  - 原因：pre-start compaction 使用 EventLog-backed compact material block ids；后续 RunInputBuilder ordinary material view 使用 `memory:* / compact:* / continuity:*` id 空间。直接用 ordinary view 渲染会触发 S3 selected-id provenance guard。新路径不改 durable payload/schema，只在 provider 内重建同源 view，并继续用 selected ids / source refs / digest guard fail closed。
- `dayu/host/run_input.py`
  - fallback renderer 在 provider 提供 frozen material view 时优先使用该同源 view；reactive 或其它未提供 frozen view 的路径继续使用 ordinary material view。
- `dayu/host/memory.py`
  - `_facts_from_accepted_event` 遇到空 `evidence_labels` fact candidate 时改为 whole-item drop 并记录 diagnostic，不再清空同一 accepted event 中已累积的 valid facts。
- `tests/host/test_dispatch_scheduler.py`
  - Proactive compact failure smoke 证明 tier4 fallback 仍能选择 historical floor block，并且 RunInputBuilder 能渲染该 non-current selected block。
- `tests/host/test_memory_projection.py`
  - 新增 regression：valid fact 在前、后续 empty evidence labels candidate 在后时，valid fact 保留且记录 invalid diagnostic。
- `tests/host/test_public_compact_smoke.py`
  - 需要验证 compact 的 public smoke 改用短 current input 触发 soft threshold。
  - 超长 current input smoke 改为验证不生成 compactor proposal、不写 compact artifact，并进入 dispatch fallback；避免违反 no truncation/no preview 设计真源。

## Public Smoke Reconciliation

- `WU-CLI-ACTIVITY-01-PR-R1`: 可关闭。
  - 直接证据：两个指定 public continuity smoke 通过：`2 passed in 0.41s`。
- Public compact smoke:
  - 初始失败根因之一是旧测试要求超长 current input 仍进入 compactor proposal；但 `CurrentInputAnchorVNext.text` contract 为 1200 字符，`docs/host/design.md` 明确禁止 LLM-facing current input / compact material 字段级截断、preview 或 summary 化。
  - 处理方式：不截断、不 preview；超长 current input 不生成 compact proposal、不写 compact artifact，进入 dispatch fallback。需要 compact 的 public smoke 使用可无损进入 current anchor contract 的短 current input。
  - 最终结果：`tests/host/test_public_compact_smoke.py` 为 `11 passed, 1 skipped`。

## Residual Reconciliation

- `WU-CM-12-S1-R1`: 已修复。
  - 直接证据：`dayu/host/memory.py::_facts_from_accepted_event` 原逻辑在后续 fact candidate `evidence_labels=[]` 时直接返回 `(), diagnostics`，会丢弃此前已 append 的 valid facts。
  - 修复：该 invalid candidate whole-item drop，并记录 `EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` diagnostic；不改变 public API、durable schema 或 EventLog 语义。
  - 覆盖：`test_accepted_compact_keeps_valid_fact_before_empty_evidence_labels`。
- `WU-CM-12-S4-R1`: deferred follow-up / intentional non-goal。
  - 直接证据：S4 recovery loop 位于 `dayu/host/dispatch.py` proactive path；reactive path 位于 `dayu/host/engine_ingest.py`，当前只有 root request、single-block pass queue 和 existing fallback decision。
  - 补齐 reactive tier1-3 需要改动 Engine ingest recovery Attempt 流程、run-local cancellation token 检查、execution/cursor commit guard 和 reactive accepted/fallback sequencing，超出 S5 public smoke reconciliation 范围。
  - 本次不实现 reactive recovery，不新增 schema/API/EventLog contract。

## README Decision

- 已按触发规则检查 `dayu/host/README.md` 与 `tests/README.md` 的 Agent 更新边界。
- 不更新 README：
  - Host 改动是内部 proactive fallback selected-id 同源修正和 memory projection invalid candidate 处理，不改变 public Host API、装配方式、稳定开发手册入口或用户工作流。
  - Test 改动不改变测试目录结构、运行方式或维护规则。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py -q`
  - PASS: `312 passed in 2.34s`
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py::test_deterministic_two_turn_request_contains_prior_final_answer tests/host/test_public_tool_wiring_smoke.py::test_mock_tool_result_feeds_same_run_and_later_run_continuity -q`
  - PASS: `2 passed in 0.41s`
- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q`
  - PASS: `11 passed, 1 skipped in 0.87s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - PASS: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - PASS

## Residual Risk

- Reactive tier1-3 compact recovery remains intentionally deferred and should be owned as a follow-up if WU-CM-12 scope is expanded beyond proactive pre-dispatch recovery.
- Current `ConversationCompactInputVNext` cannot represent over-1200-character current input without schema change or invalid truncation; current behavior is to fail compact and dispatch fallback.
