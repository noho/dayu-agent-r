# WU-CTX-02 + WU-CTX-03 Slice B implementation artifact

## Gate / Slice

- Gate: WU-CTX-02 + WU-CTX-03 implementation Slice B
- Slice objective: 补齐 `CONTEXT_COMPACTION_FAILED` payload 诊断字段，为后续 fallback 与 overflow E2E 提供可观察诊断。
- Approved plan: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`
- Accepted plan commit: `9d89db3`
- Accepted Slice A commit: `2f2f22c`

## Allowed files / modules

- `dayu/host/context_events.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `docs/reviews/wu-ctx-02-03-implementation-sliceB-codex-20260601.md`

## Changed files

- `dayu/host/context_events.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `docs/reviews/wu-ctx-02-03-implementation-sliceB-codex-20260601.md`

## Implemented plan items

- 扩展 `build_context_compaction_failed_payload` 和 `validate_context_compaction_failed_payload`，把 `operation_id`、`attempt_count`、`retry_repair_budget_exhausted` 与 fallback 诊断字段纳入 required fields。
- 无 fallback 路径默认写入 `fallback_policy_decision=null`、`fallback_input_window=null`、`fallback_input_digest=null`、`fallback_budget_result=null`、`fallback_action="not_applicable"`。
- validator 覆盖 fallback action 枚举，只允许 `dispatch`、`fail_closed`、`not_applicable`。
- proactive failed append helper 显式接收 operation id、attempt count 与 retry / repair budget exhausted。
- reactive failed append helper 显式接收 operation id、attempt count 与 retry / repair budget exhausted。
- precondition / missing compactor failure 使用 `attempt_count=0`、`retry_repair_budget_exhausted=false`。
- operation failure 使用 rejected attempt count；有 rejected attempts 的最终 operation failure 标记 `retry_repair_budget_exhausted=true`。
- stale result 保留 rejected attempt count 诊断，但不标记 retry / repair budget exhausted。

## State-machine / payload changes

- State-machine: 未改变。未新增 `CONTEXT_COMPACTION_REQUESTED`，未新增 fallback dispatch，未改变 Run / Attempt transition。
- Durable schema: 未改变。未读旧 failed payload，未加入兼容读取。
- Public API: 未改变。
- Payload: `CONTEXT_COMPACTION_FAILED` 新 required fields 为 `operation_id`、`attempt_count`、`retry_repair_budget_exhausted`、`fallback_policy_decision`、`fallback_input_window`、`fallback_input_digest`、`fallback_budget_result`、`fallback_action`。
- 无 request fact 的 precondition failure 使用稳定的 precondition operation id，不通过 schema 或状态机新增 request fact。
- 未加入 raw provider payload。

## Tests

- `source .venv/bin/activate && pytest tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py -q`
- Result: `126 passed in 1.29s`

## Pyright

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- Result: `0 errors, 0 warnings, 0 informations`

## Docs decision

- Checked `dayu/host/README.md`: 当前只描述 Context Governance compact failure 收口语义，没有维护 `CONTEXT_COMPACTION_FAILED` payload 字段清单；新增字段不会造成 README 与代码不一致。
- Checked `tests/README.md`: 当前只描述测试覆盖范围，并已包含 context compact canonical payload builder / validator、dispatch scheduler 与 EngineEvent ingest 覆盖；无需因字段级扩展更新。
- Decision: 不更新 README。

## Invariants checked

- 所有 `CONTEXT_COMPACTION_FAILED` builder 输出都必须包含 operation id、attempt count、retry / repair budget exhausted 与 fallback 诊断字段。
- 无 fallback 路径 payload 的 fallback fields 为 null / `not_applicable`。
- fallback dispatch / fail closed payload 需要结构化 fallback policy、input window、digest 和 budget result。
- 非法负数 `attempt_count` 被 validator 拒绝。
- 非法 `fallback_action` 被 validator 拒绝。
- proactive missing compactor、proactive compact count precondition、proactive repair exhausted 与 stale result 测试均断言新增字段。
- reactive missing compactor、reactive count precondition、reactive corrupt count 与 stale result 测试均断言新增字段。
- 未改变状态机、未改 durable schema、未实现 fallback。

## Residual risks

- Slice B 只补 payload 诊断；fallback selection、fallback budget re-estimate、fallback dispatch / fail closed E2E 仍由后续 Slice C / D / E 覆盖。
- 无 request fact 的 precondition failure 当前使用稳定 synthetic operation id 作为诊断锚点；这是为了遵守“不改变状态机”的 Slice B 边界。
- README 未列字段级 payload contract；本 Slice 不新增字段清单文档，避免 Host README 越界为 schema 手册。

## Stop status

- Slice B implementation complete.
- 未触发 stop conditions：未读取旧 failed payload，未改变 EventLog 表结构或 public API，未实现 deterministic fallback，指定测试与 pyright 均通过。
- 已按 handoff 要求停止在 implementation artifact 完成点；未进入 review、commit、push 或 PR。

## Artifact path

- `docs/reviews/wu-ctx-02-03-implementation-sliceB-codex-20260601.md`
