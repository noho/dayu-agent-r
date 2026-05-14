# Host P4-S3 Run Follow-up Cancel Code Review Controller Adjudication

- **gate**: Phase 4 implementation
- **slice**: P4-S3 Run Admission, Follow-up Queue, Cancel Run And Cancel Session Runs Subset
- **approved plan**: `docs/host/phase4-public-api-command-path-plan.md`
- **implementation artifact**: `docs/reviews/gateflow-implementation-host-p4-s3-run-followup-cancel-20260514.md`
- **review artifacts**:
  - `docs/reviews/gateflow-code-review-host-p4-s3-run-followup-cancel-mimo-20260514.md`
  - `docs/reviews/gateflow-code-review-host-p4-s3-run-followup-cancel-ds-20260514.md`
- **controller conclusion**: accepted after scope correction
- **date**: 2026-05-14

## 裁决摘要

AgentMiMo 与 AgentDS 均确认 P4-S3 最终 diff 已移除首次实现中越界的 P4-S4 `get_run` / `stream_run_events` 内容。两份 review 均为 accepted / no blocking finding。Controller 采纳 accepted 结论，P4-S3 可进入 accepted slice commit。

## 依据

- Public command facade 已实现 `start_run`、`submit_followup(queue)`、`cancel_run`、`cancel_session_runs`，并从包根导出。
- Public read facade 未新增 `get_run` 或 `stream_run_events`；P4-S4 read/event stream scope 未侵入 P4-S3。
- `start_run` 复用 internal admission，保留 direct running、queue、reject、attach-active 行为；attach-active 不追加 canonical EventLog attach fact。
- `submit_followup` 校验路径 `session_id` 与 request session id 一致；`STEER` 返回 `UNSUPPORTED_OPERATION` 且不追加 EventLog。
- `cancel_run` 覆盖 queued 与 pre-dispatch `STARTING`，deferred cancel states 映射为 `UNSUPPORTED_OPERATION`，未把 `NOT_FOUND`、idempotency conflict 或 terminal true invalid precondition 错误吞掉。
- `cancel_session_runs` 在单 write transaction 内先读取并校验全部 non-terminal Runs；发现 unsupported non-terminal 时在任何 cancel fact append 前返回 `UNSUPPORTED_OPERATION`，无 partial cancel，无 silent ignore。
- `cancel_session_runs` idempotency digest 不包含动态 Run 列表；same key replay 只返回当前 `SessionSnapshot`，不取消首次操作后新接受的 Run；empty supported set 记录 idempotency 且不追加 cancel event。
- `cancel_session_runs` 不触发 queue promotion。
- `read_non_terminal_runs_for_session` 与 `run_snapshot_from_row` 是 narrow durable helper，未承载 public facade 或 projection truth。

## Review Finding 裁决

无 accepted blocking finding。

### Scope correction

- **source**: Controller pre-review check
- **decision**: fixed before review
- **裁决**: 首次 P4-S3 implementation 越界实现了 P4-S4 的 `get_run` / `stream_run_events`。Controller 已要求 implementation agent 做 scope correction。最终 code review 已确认这些内容未实现、未导出，artifact 已记录 correction。

### P4S3-NB-001 submit_followup(queue) default execution target

- **source**: AgentMiMo residual risk, AgentDS independent review
- **decision**: accepted-as-deferred-owner
- **裁决**: `SubmitFollowupRequest` 当前没有 `resolved_execution_target` 字段，policy provider integration 不属于 P4-S3。使用 Host facade 内部默认 execution target 可让 Phase 1-3 admission 闭环通过 public API，但不是终态 policy resolution。后续 policy provider / execution target resolution owner 必须替换为显式 Host policy resolution output，不得把该默认值视为最终执行目标策略。

### P4S3-NB-002 session-scope cancel subset

- **source**: design truth, user reminder, both reviews
- **decision**: accepted-as-deferred-owner
- **裁决**: P4-S3 只允许 queued / pre-dispatch `STARTING` 子集。后续 phase 必须继续补齐完整 session-scope cancel：Phase 5 覆盖 dispatching / active worker，Phase 7 覆盖 `WAITING`，Phase 11 覆盖 `RECOVERING`。任何 README、control doc 或后续 plan 都不得把 P4-S3 子集写成最终 cancel 语义。

## Validation

Controller 与 reviewers 均已验证：

- `source .venv/bin/activate && pytest tests/host/test_public_run_api.py tests/host/test_public_cancel_session_runs.py tests/host/test_admission_queue.py tests/host/test_admission_multiprocess.py -q`
  - `37 passed`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed

Additional reviewer checks:

- `source .venv/bin/activate && pytest tests/host/test_package_exports.py -q`
  - `5 passed`
- `source .venv/bin/activate && pytest tests/host -q`
  - `191 passed`

## 后续入口

P4-S4 owns public read APIs, EventLog stream cursor behavior and deferred facade stable unsupported behavior. P4-S4 必须从当前 P4-S3 accepted surface 出发，不得修改 P4-S3 cancel 子集语义，除非先回到 design discussion。

