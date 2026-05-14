# Host P4-S1 Public Types Implementation Artifact

- **gate**: Phase 4 implementation
- **slice**: P4-S1 Public Types, Error Detail, Handle Options And Constants
- **approved plan**: `docs/host/phase4-public-api-command-path-plan.md`
- **controller accepted plan commit**: `e004031`
- **agent**: AgentCodex
- **artifact path**: `docs/reviews/gateflow-implementation-host-p4-s1-public-types-20260514.md`

## Scope And Non-goals

本 slice 只修改 public type contract、package exports、对应 contract tests 与 Host README 中当前契约说明。

已遵守 non-goals：

- 未启动 `$gateflow`。
- 未 commit、push 或创建 PR。
- 未修改 `dayu/host/admission.py`、`dayu/host/durable/*`。
- 未新增 command facade、read API 或任何运行时实现。
- 未修改 Engine / Fins / Service / UI / runtime。
- 未修改与 P4-S1 无关测试或文档。

## Changed Files

- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `tests/host/test_public_contracts.py`
- `tests/host/test_package_exports.py`
- `dayu/host/README.md`
- `docs/reviews/gateflow-implementation-host-p4-s1-public-types-20260514.md`

## Implemented Plan Items

- 新增 `HostApiErrorCode.UNSUPPORTED_OPERATION = "unsupported_operation"`。
- 新增 frozen / slots `SteerConflictDetail`，字段为 `target_run_id`、`target_run_status`、`current_active_run_id`、`current_active_run_status`。
- 新增显式 typed alias `HostApiErrorDetail`；第一版成员为 `SteerConflictDetail`，未引入 dict / JsonValue / Any / object / extra payload。
- 扩展 `HostApiError.detail: HostApiErrorDetail | None = None`，保留原有 code/message/retryable/str 行为。
- 将 `FollowupSnapshot` 替换为 accepted-run shape：`accepted_input_ref`、`behavior`、`accepted_run_id`、`accepted_run_status`、`current_cursor`、`queued_run_id`、`target_run_id`。
- 实现 `FollowupSnapshot` queue 校验：accepted input/ref 非空、queue 不允许 target、queue + `QUEUED` 要求 `queued_run_id == accepted_run_id`、queue + `RUNNING` 要求 `queued_run_id is None`、queue 拒绝其它状态；steer 不要求 `queued_run_id`。
- 新增并导出 `HOST_EVENT_STREAM_DEFAULT_LIMIT = 100` 与 `HOST_EVENT_STREAM_MAX_LIMIT = 1000`。
- 新增 frozen / slots `HostCommandHandleOptions`，包含 plan §3 指定字段，并校验 optional handle id、path 类型、bool 类型、正数 timeout/delay/backoff/threshold、非负 retry count，且拒绝 bool 混入数值配置。
- 更新 `dayu.host.api.__all__` 与 `dayu.host` 包根导出。
- 更新 public contract / package export 测试覆盖 enum、error detail、FollowupSnapshot accepted-run validation、stream constants、HostCommandHandleOptions validation 与 package exports。

## Validation Results

- `source .venv/bin/activate && pytest tests/host/test_public_contracts.py tests/host/test_package_exports.py -q`
  - 结果：通过，`30 passed in 0.09s`。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：通过，`0 errors, 0 warnings, 0 informations`。
- `git diff --check`
  - 结果：通过，无输出。

## Docs Decision

已更新 `dayu/host/README.md`。更新范围仅限当前 public type contract：新增 stream constants、`HostCommandHandleOptions`、typed error detail、`UNSUPPORTED_OPERATION` 与 `FollowupSnapshot` accepted-run 校验规则。未写入后续 command facade 或运行时实现声明。

## Residual Risks And Uncovered Areas

- P4-S1 只冻结 public types，不实现 `create_host_command_handle`、public command functions、EventLog-backed stream read 或 deferred function behavior；这些按 approved plan 后续 slice 处理。
- `HostCommandHandleOptions` 当前只做公共输入契约校验，尚未映射到 durable internal options；该映射属于后续 command handle / factory slice。
- `SteerConflictDetail` 已冻结为 typed detail，但 Phase 4 当前 steer 行为仍由后续 facade slice 返回 stable unsupported，不在本 slice 评估 steer precondition。

## Completion Status

P4-S1 implementation complete. 当前无 blocking open question；未触发 stop condition。
