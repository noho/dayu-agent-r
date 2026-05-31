# Phase 15 P15-S3 Implementation Artifact

- **Gate**: Phase 15 implementation Slice P15-S3
- **Work unit**: Retention / Purge / Production Hardening
- **Assigned slice**: P15-S3 Public Command Wiring And Read-after-purge Semantics
- **Approved plan**: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- **Implementation agent**: AgentCodex implementation specialist
- **Date**: 2026-05-29

## Scope And Non-goals

本次只实现 approved P15-S3 范围：

- 将 `dayu.host.command.purge_session(...)` 从 structured unsupported 接到 S2 durable purge helper。
- 保持 closed-handle guard 优先于 transaction / durable 分支。
- 通过 frozen `PurgeSessionRequest` dataclass 字段构造 semantic digest 和 durable delete request，不引入 extra payload。
- 在 write transaction 内调用 `purge_session_durable(...)`。
- 将 durable purge 错误映射到现有 public `HostApiErrorCode`。
- 返回 frozen `PurgeSessionResult(session_id, purged=True, purge_tombstone_ref, deleted_counts_digest)`。
- 将 `open_host` concrete public handle 接到 command facade，不新增 `OpenHostOptions`。
- 用 public tests 证明 purge 后 `get_session`、`get_run`、`retry_run`、`replay_run`、`watch_session_events` fail closed，不从 tombstone/projection/audit 重建事实。

明确未做：

- 未写 purge audit JSONL；P15-S4 owns purge tombstone audit record 与 fail-before-success hardening。
- 未新增 public reader、wait helper、watch cursor 或 public error code。
- 未改 Engine / Service / UI / Fins。
- 未做 commit / push / PR。

## Changed Files

- `dayu/host/command.py`
- `dayu/host/open_host.py`
- `tests/host/test_command_handle.py`
- `tests/host/test_public_session_api.py`
- `tests/host/test_public_run_api.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_public_lifecycle_smoke.py`
- `docs/reviews/phase15-s3-implementation-codex-20260529.md`

## Implemented Plan Items

- `command.purge_session(...)` 现在先执行 `host._raise_if_closed()`，再构造 `_PurgeSessionOperation`。
- `_PurgeSessionOperation` 从 `PurgeSessionRequest.context`、`reason` 与 path `session_id` 构造 stable semantic digest，并传入 `PurgeSessionDeleteRequest`。
- durable helper 在 command write transaction 内执行，返回 tombstone replay 或新 purge result。
- public error mapping：
  - `PurgeSessionInvalidStateError` -> `INVALID_STATE`
  - `HostIdempotencyConflictError` -> existing `IDEMPOTENCY_CONFLICT` mapping
  - `PurgeSessionAlreadyPurgedError` -> `CONFLICT`
  - `PurgeSessionNotFoundError` -> `NOT_FOUND`
  - 其它 durable inconsistency/internal -> existing internal durable mapping
- `open_host._PublicHostHandle.purge_session(...)` 转发到 command facade，并保持 `HostClosedError` gate 优先。
- Tests 覆盖 closed empty Session purge result、idempotent replay、open Session invalid state、already purged different request conflict、purge 后 read/retry/replay/watch not found、open_host closed handle purge fail-fast。

## Validation

通过：

```bash
source .venv/bin/activate && pytest tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py tests/host/test_open_host_runtime.py tests/host/test_purge_session.py -q
```

结果：`69 passed in 1.00s`

通过：

```bash
source .venv/bin/activate && python -m pyright dayu/host/command.py dayu/host/open_host.py dayu/host/read_api.py tests/host
```

结果：`0 errors, 0 warnings, 0 informations`

## Docs Decision

未更新 README。

原因：

- 当前 handoff 的 allowed files 未包含 `dayu/host/README.md` 或 `tests/README.md`。
- Approved plan 将 Host README purge 语义同步列在 P15-S6，并说明需在 S3/S4 完成后更新；S4 audit JSONL purge tombstone record 尚未实现。
- 当前 `dayu/host/README.md` 仍有 `purge_session` structured unsupported 旧描述，这是已知文档残余，建议由后续 docs slice 按最终 S3+S4 行为统一修正。

## Residual Risks And Uncovered Areas

- P15-S4: public success 目前仍可在没有 purge audit JSONL line 的情况下返回 tombstone result；这是 approved plan 的后续 slice owner，不在 S3 实施。
- P15-S5: projection rebuild、startup recovery、scheduler/local multiprocess hardening 未在本 slice 验证。
- P15-S6: README 与 import-boundary / weak-typing guard 的最终同步未在本 slice 处理。
- 文件系统 cold artifact commit 后慢清理仍未接 public command；本 slice 未扩大到文件 IO cleanup。

## Stop Status

P15-S3 implementation complete. No blocking question. Ready for controller code review handoff.
