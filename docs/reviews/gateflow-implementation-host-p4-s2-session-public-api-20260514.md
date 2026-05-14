# Gateflow Implementation Artifact: Host P4-S2 Session Public APIs And Snapshots

- gate: Phase 4 implementation
- work unit: Host Public API Command Path
- slice: P4-S2 Session Public APIs And Snapshots
- accepted plan: `docs/host/phase4-public-api-command-path-plan.md`
- design truth: `docs/host/design.md`
- baseline accepted slice: `b1e6eec`
- implementation status: completed

## Scope And Non-goals

本 slice 只实现 Host command handle / factory 与 Session public facade：

- `ensure_session`
- `create_session`
- `get_session`
- `close_session`

本 slice 未实现 Run admission、follow-up queue facade、EventLog stream、purge、background supervisor facet、dispatch scheduler、WorkerProxy、Engine dispatch、wait / recovery cancel 或 Service / UI 装配。

未修改 `docs/host/design.md`；本实现未发现 P4-S2 需要变更设计真源。

## Changed Files

- `dayu/host/command.py`
- `dayu/host/read_api.py`
- `dayu/host/__init__.py`
- `dayu/host/durable/transaction.py`
- `dayu/host/README.md`
- `tests/host/test_command_handle.py`
- `tests/host/test_public_session_api.py`
- `tests/host/test_package_exports.py`
- `tests/README.md`
- `docs/reviews/gateflow-implementation-host-p4-s2-session-public-api-20260514.md`

`tests/host/test_package_exports.py` 与 `tests/README.md` 是 P4-S2 public export 与新增测试事实的同步更新：包根新增 command facade 后，既有导出白名单必须随当前 public contract 更新；新增 Host 测试文件后，测试手册需要记录当前测试分层与收窄命令。

## Implemented Items

- 新增 `HostCommandHandle` concrete public handle：
  - public surface 只暴露 `host_handle_id` 与幂等 `close()`。
  - 私有持有 `HostDurableStore` 与内部 `HostAdmissionService`，不向 public handle 暴露 transaction runner、store connection、durable store 或 admission service。
  - close 后调用 public facade 统一抛出 `HostApiError(code=INVALID_STATE, retryable=False)`。
- 新增 `create_host_command_handle(options)`：
  - 将 `HostCommandHandleOptions` 映射到 `HostDurableStoreOptions`、`PayloadStoragePolicy` 与 `HostSQLiteStoragePolicy`。
  - 打开并 bootstrap `HostDurableStore`。
  - 未显式传入 handle id 时生成当前 handle 生命周期内稳定 id。
- 新增 Session public facade：
  - `ensure_session(host, request) -> SessionSnapshot`
  - `create_session(host, request) -> SessionSnapshot`
  - `get_session(host, session_id) -> SessionSnapshot`
  - `close_session(host, session_id, request) -> SessionSnapshot`
- 新增 read transaction support：
  - `HostReadTransactionOperation`
  - `HostTransactionRunner.run_read(...)`
  - `get_session` 使用 read transaction，不用 write transaction 承载纯读。
- `get_session` 从 durable truth 读取：
  - Session row
  - 当前 slot binding
  - active Run id
  - queued Run id 列表
  - missing Session 返回 `HostApiErrorCode.NOT_FOUND`。
- `close_session` 仅复用既有 durable lifecycle 执行 `OPEN -> CLOSED`，不 cancel、不 purge、不删除 facts。
- public semantic digest 在 facade 边界基于显式 request 字段与 `HostCallContext` semantic digest 计算；不包含 runtime-only object、内部依赖或 metadata bag。

## Tests Added Or Updated

- `tests/host/test_command_handle.py`
  - factory fresh DB
  - explicit / generated stable public handle id
  - public handle 不暴露内部 mutable dependency
  - close idempotent
  - close 后 facade predictable failure
  - Host import boundary 仍排除 Engine / Fins / Service / UI
- `tests/host/test_public_session_api.py`
  - repeated `ensure_session` returns same `SessionSnapshot`
  - `create_session` idempotent replay returns same Session
  - same idempotency key with different digest returns `IDEMPOTENCY_CONFLICT`
  - `close_session` idempotent replay returns same closed snapshot
  - `close_session` does not remove Session durable truth
  - `get_session` missing returns `NOT_FOUND`
- `tests/host/test_package_exports.py`
  - package root whitelist includes P4-S2 command facade exports
  - command facade remains outside `dayu.host.api`

## Validation Results

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_session_lifecycle.py -q
```

Result:

```text
19 passed
```

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
```

Result:

```text
8 passed
```

Passed:

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

Passed:

```bash
git diff --check
```

Result: no whitespace errors.

## Residual Risks And Classification

- Run public facade, follow-up queue facade, cancel facade and EventLog stream are intentionally unimplemented in P4-S2.
  - classification: covered by later approved slices P4-S3 / P4-S4.
- `create_session` public facade excludes metadata bag from semantic digest. To keep P4-S2 digest contract while reusing existing durable lifecycle helper, public create requests are passed to durable lifecycle with empty metadata.
  - classification: accepted P4-S2 implementation constraint; current docstring and Host README state that `create_session` metadata is not persisted. If Host later needs public metadata persistence semantics, that should be addressed as an explicit design / plan item rather than silently changing idempotency semantics.
- `HostCommandHandle` currently creates the internal admission service dependency but P4-S2 does not expose run admission functions.
  - classification: covered by later P4 run facade slice; no user-visible Run behavior is introduced in this slice.

## Completion Signal

P4-S2 implementation is complete for the assigned scope. No PR, push, commit, service start or design truth change was performed.
