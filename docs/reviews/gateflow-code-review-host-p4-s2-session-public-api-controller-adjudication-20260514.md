# Host P4-S2 Session Public API Code Review Controller Adjudication

- **gate**: Phase 4 implementation
- **slice**: P4-S2 Session Public APIs And Snapshots
- **approved plan**: `docs/host/phase4-public-api-command-path-plan.md`
- **implementation artifact**: `docs/reviews/gateflow-implementation-host-p4-s2-session-public-api-20260514.md`
- **review artifacts**:
  - `docs/reviews/gateflow-code-review-host-p4-s2-session-public-api-mimo-20260514.md`
  - `docs/reviews/gateflow-code-review-host-p4-s2-session-public-api-ds-20260514.md`
- **controller conclusion**: accepted after non-behavioral documentation fix
- **date**: 2026-05-14

## 裁决摘要

AgentMiMo 与 AgentDS 均确认 P4-S2 严格限于 Host command handle / factory 与 Session public facade，无 Run admission、EventLog stream、purge 或 background supervisor 越界。两份 review 均无 blocking finding。Controller 采纳 accepted 结论，P4-S2 可进入 accepted slice commit。

## 依据

- `HostCommandHandle` public surface 只暴露 `host_handle_id` 与幂等 `close()`；durable store、transaction runner、admission service 与 store connection 均为私有依赖。
- `create_host_command_handle` 将 `HostCommandHandleOptions` 映射到 `HostDurableStoreOptions`、`PayloadStoragePolicy` 与 `HostSQLiteStoragePolicy`，并在内部依赖构造失败时关闭已打开 store。
- `ensure_session` / `create_session` / `close_session` 复用既有 durable lifecycle；`get_session` 通过新增 read transaction 从 durable truth 构造 `SessionSnapshot`。
- `get_session` 缺失 Session 时返回 `HostApiErrorCode.NOT_FOUND`，不依赖 projection、内存状态或 client-side cursor。
- `HostTransactionRunner.run_read` 是层中立 durable primitive，只表达普通 read transaction，不携带 command facade 语义。
- README 与 tests README 已按触发规则同步当前事实。

## Review Finding 裁决

### P4S2-DS-001 create_session metadata 静默丢弃

- **review source**: AgentDS Finding 1
- **severity**: medium in review, non-blocking
- **controller decision**: accepted-as-doc-fixed / future-design-owner
- **裁决**: P4-S2 plan 明确 public semantic digest 不包含 metadata bag；design 也把 metadata 定位为不参与状态机、幂等、恢复和审计主链的中性附加说明。因此当前行为不阻塞 P4-S2。但 request 暴露 `metadata` 字段而 public facade 清空它，确实需要让调用方和后续 phase 可见。
- **已执行修正**: `dayu/host/command.py` 的 `create_session` 与 `_request_without_create_metadata` docstring、`dayu/host/README.md`、implementation artifact 已明确说明：当前 `create_session` public facade 不持久化 metadata；若未来需要 public metadata persistence，必须先进入设计与 plan。
- **后续 owner**: 后续任何要让 `create_session` metadata 可读、可审计或可诊断持久化的 phase，必须先回到 `docs/host/design.md` 与 phase plan 明确语义，不能在实现中静默改变 idempotency 或 durable metadata 行为。

### P4S2-DS-002 call_context_digest 重复参与哈希

- **review source**: AgentDS Finding 2
- **controller decision**: accepted-as-non-issue
- **裁决**: 当前重复哈希不改变幂等冲突判断，不引入用户可见错误；不在 P4-S2 内扩大 durable lifecycle digest 设计。

### P4S2-DS-003 HostCommandHandle 持有未使用 admission service

- **review source**: AgentDS Finding 3
- **controller decision**: accepted-as-planned-dependency
- **裁决**: P4-S2 plan 要求 handle 持有私有 durable store 和 service dependencies；admission service 不暴露到 public surface，且 P4-S3 会消费该依赖。不要求修改。

### Informational observations

- `run_read` 使用 SQLite deferred `BEGIN` 适合纯读；accepted-as-non-issue。
- public options 与 durable policy 双重校验是分层防御性不变量；accepted-as-non-issue。

## Validation

Controller 在 documentation fix 后重跑：

- `source .venv/bin/activate && pytest tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_session_lifecycle.py -q`
  - `19 passed`
- `source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q`
  - `8 passed`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed

## 后续追踪

- P4-S3 进入 Run admission、follow-up queue、queued / pre-dispatch cancel public facade；必须复用 P4-S2 handle，不重新设计 public handle shape。
- P4-S4 进入 EventLog stream 与 deferred facade behavior。
- `create_session` metadata persistence 不是 P4-S3/P4-S4 的默认实现项；除非后续 phase 明确要求，否则维持 P4-S2 已记录的非持久化行为。
- 用户明确要求提醒后续 phase：P4-S3 的 `cancel_session_runs` 仍只能实现 queued / pre-dispatch `STARTING` 子集；Phase 5 / 7 / 11 必须分别补齐 dispatching / active worker、`WAITING`、`RECOVERING` 的完整 session-scope cancel 能力。

