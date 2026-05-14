# Host P4-S4 Read Stream Deferred Code Re-Review Controller Adjudication

- **gate**: Phase 4 implementation
- **slice**: P4-S4 Read APIs, Event Stream And Deferred Facade Behavior
- **approved plan**: `docs/host/phase4-public-api-command-path-plan.md`
- **implementation artifact**: `docs/reviews/gateflow-implementation-host-p4-s4-read-stream-deferred-20260514.md`
- **review artifacts**:
  - `docs/reviews/gateflow-code-review-host-p4-s4-read-stream-deferred-mimo-20260514.md`
  - `docs/reviews/gateflow-code-review-host-p4-s4-read-stream-deferred-ds-20260514.md`
- **re-review artifacts**:
  - `docs/reviews/gateflow-code-re-review-host-p4-s4-read-stream-deferred-mimo-20260514.md`
  - `docs/reviews/gateflow-code-re-review-host-p4-s4-read-stream-deferred-ds-20260514.md`
- **controller conclusion**: accepted after fix
- **date**: 2026-05-14

## 裁决摘要

P4-S4 初次 review 中，AgentMiMo 提出 blocking finding：`stream_run_events` 在 missing Run 与 invalid limit 同时存在时先校验 limit，返回 `INVALID_STATE`，与 plan 要求的“先校验 Run 存在，missing Run 返回 `NOT_FOUND`”不一致。AgentDS 独立识别同一问题为 medium，并指出 default limit 测试隐式依赖 EventLog sequence 连续性。

Controller 接受该 finding 并要求修复。修复后，AgentMiMo 与 AgentDS re-review 均确认 fixed / no blocking findings。P4-S4 可进入 accepted slice commit。

## Accepted Finding 裁决

### P4S4-MIMO-001 stream_run_events validation order

- **source**: AgentMiMo blocking finding; AgentDS medium finding
- **decision**: accepted and fixed
- **root cause**: `stream_run_events` 外层先解析 `_resolve_stream_limit`，导致 missing Run + invalid limit 的错误优先级偏离 public contract。
- **fix**: `limit` 以 `int | None` 传入 `_StreamRunEventsOperation`，read transaction 内先 `read_run_by_id` 并在 missing 时抛 `NOT_FOUND`，再解析 limit，最后扫描 EventLog。
- **evidence**: 新增测试覆盖 missing Run + `limit=0`、`limit=-1`、`limit > HOST_EVENT_STREAM_MAX_LIMIT` 均返回 `NOT_FOUND`；existing Run + invalid limit 仍返回 `INVALID_STATE`。
- **re-review**: MiMo 与 DS 均确认 fixed。

### P4S4-DS-002 default limit test contiguity dependency

- **source**: AgentDS low finding
- **decision**: accepted and fixed
- **fix**: default limit 测试改为用 `_max_scanned_event_sequence` 从 DB 独立读取 scan window 末尾 event sequence，不再依赖 `cursor + default_limit` 的隐式连续性。

### P4S4-DS-003 terminal status set duplication

- **source**: AgentDS informational observation
- **decision**: accepted-as-non-issue
- **裁决**: `read_api.py` 的 terminal status set 只服务 public read fallback，`state.py` 的 terminal helper 仍是 durable validation 私有逻辑；当前语义一致，不在 P4-S4 内新增共享抽象。

## Scope 裁决

- `get_run`、`stream_run_events`、`retry_run`、`replay_run`、`resolve_wait`、`purge_session` 属 P4-S4 scope。
- P4-S3 cancel 子集语义未被修改；Phase 5 / 7 / 11 cancel owner reminder 保留。
- Deferred functions 直接抛 `UNSUPPORTED_OPERATION`，不写 EventLog、不写 idempotency record。
- `stream_run_events` 使用全局 EventLog cursor truth，empty filtered result 在扫描到 unrelated rows 时推进 `next_cursor`。
- `HostEventView` 不暴露 raw payload JSON、policy decision JSON 或 reason JSON。

## Validation

Controller 与 reviewers 验证：

- `source .venv/bin/activate && pytest tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host -q`
  - `201 passed`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed

## 后续入口

P4-S4 是 Phase 4 implementation 的最后一个 slice。Accepted slice commit 后，Phase 4 进入 aggregate deepreview gate。Aggregate review 必须同时派 AgentMiMo 与 AgentDS，复核整个 Phase 4 public command/read surface、P4-S1 至 P4-S4 交互、文档与 residual risk tracking。

