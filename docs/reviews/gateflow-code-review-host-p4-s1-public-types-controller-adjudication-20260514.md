# Host P4-S1 Public Types Code Review Controller Adjudication

- **gate**: Phase 4 implementation
- **slice**: P4-S1 Public Types, Error Detail, Handle Options And Constants
- **approved plan**: `docs/host/phase4-public-api-command-path-plan.md`
- **implementation artifact**: `docs/reviews/gateflow-implementation-host-p4-s1-public-types-20260514.md`
- **review artifacts**:
  - `docs/reviews/gateflow-code-review-host-p4-s1-public-types-mimo-20260514.md`
  - `docs/reviews/gateflow-code-review-host-p4-s1-public-types-ds-20260514.md`
- **controller conclusion**: accepted
- **date**: 2026-05-14

## 裁决摘要

AgentMiMo 与 AgentDS 均独立确认 P4-S1 完整覆盖 accepted plan 的 public type slice，无 blocking finding。Controller 采纳两份 review 结论，P4-S1 可进入 accepted slice commit。

## 依据

- `HostApiErrorCode.UNSUPPORTED_OPERATION`、`SteerConflictDetail`、`HostApiErrorDetail` 与 `HostApiError.detail` 已冻结 public error envelope，未引入 dict / `Any` / extra payload。
- `FollowupSnapshot` 已改为 `accepted_run_id` / `accepted_run_status` shape，并约束 queue 分支只表达真实 queued 或 immediate running accept 结果。
- `HOST_EVENT_STREAM_DEFAULT_LIMIT` 与 `HOST_EVENT_STREAM_MAX_LIMIT` 已作为 public constants 暴露，为后续 EventLog-backed stream API 固定 public limit contract。
- `HostCommandHandleOptions` 已冻结 command handle factory 的 typed options envelope，并完成本 slice 范围内的类型和值域校验。
- `dayu.host.api` 与 `dayu.host` 包根导出、public contract tests、package export tests 与 `dayu/host/README.md` 均已同步。

## Review Finding 裁决

无 accepted blocking finding。

两份 review 中列出的非阻塞观察裁决如下：

- `_require_positive_float` runtime 接受 `int`：accepted-as-non-issue。字段 public type 仍为 `float`，runtime 防御性接受非 bool 数值不削弱契约。
- 旧 `_require_non_negative` 未补 bool guard：accepted-as-out-of-scope。该 helper 不属于 P4-S1 新配置值校验路径，不要求在本 slice 扩大修改面。
- `HostApiErrorDetail` 首版只有 `SteerConflictDetail`：accepted-as-intended。Phase 4 只冻结 steer conflict typed detail，后续 detail 成员必须继续通过显式 type union 扩展。
- `FollowupSnapshot` steer 分支未强制 `target_run_id`：accepted-as-non-issue。Phase 4 不实现 steer Attempt switching，后续 facade slice 只返回 stable unsupported；当前 shape 保持 future-compatible typed envelope。
- `HostCommandHandleOptions` 不做跨字段校验：accepted-as-deferred-to-factory。P4-S1 只冻结 typed options；factory/default 映射与跨字段策略属于后续 command handle slice。

## 后续追踪

- P4-S2 必须在不重新设计 P4-S1 public types 的前提下接入 session public APIs 与 snapshot mapping。
- P4-S3 必须只实现 queued / pre-dispatch `STARTING` 的 `cancel_session_runs` 子集。
- 后续 phase 必须继续追踪并补齐完整 session-scope cancel：Phase 5 覆盖 dispatching / active worker，Phase 7 覆盖 `WAITING`，Phase 11 覆盖 `RECOVERING`。不得把 Phase 4 子集写成最终语义。

## Validation

采纳 implementation agent 与两份 reviewer 的验证证据。Controller 在 accepted slice commit 前仍需重跑：

- `source .venv/bin/activate && pytest tests/host/test_public_contracts.py tests/host/test_package_exports.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- `git diff --check`

