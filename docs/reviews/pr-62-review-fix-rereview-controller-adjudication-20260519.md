# PR 62 Review Fix Re-Review Controller Adjudication

## Verdict

PR 62 review fix accepted。

AgentMiMo re-review：PASS，blocking findings count = 0。
AgentDS re-review：PASS，blocking findings count = 0。

Controller 裁决：PR62-F1 / F2 / F3 已按当前 gate 要求收口。Public smoke 文件不再用重复 direct SQLite `event_log` 查询作为 correctness assertion；`test_public_steer.py` 与 `test_public_resolve_wait_resume.py` 不再通过 `create_host_command_handle` seed WAITING；已提交 review artifacts 的 trailing whitespace 已在 working tree 清理，待 accepted fix commit 后复验 `git diff --check main...HEAD`。

## Accepted Evidence

- PR62-F1：`tests/host/test_public_lifecycle_smoke.py`、`tests/host/test_public_retry_replay.py`、`tests/host/test_public_cancel_session_runs.py` 已删除重复 `_event_type_count` / `_wait_for_event_type_count` 直连 `event_log` 的 correctness assertion。保留的 `wait_for_diagnostic_event_type_count(...)` 集中在 `tests/host/public_smoke_support.py`，并声明仅用于等待非 public-display diagnostic event，不作为 correctness assertion。
- PR62-F2：`tests/host/test_public_steer.py` 与 `tests/host/test_public_resolve_wait_resume.py` 不再 import `dayu.host.command` 或 `create_host_command_handle`。WAITING setup 通过 `open_host(options)`、public `submit_followup(...)`、awaiting mock tool 与 `wait_for_public_waiting_run(...)` 完成；后续 steer / resolve_wait 仍走 public command。
- PR62-F3：`git diff --check` 与 `git diff --check main` 在 working tree 中均 clean。`git diff --check main...HEAD` 仍显示旧 HEAD 中的 committed review artifact whitespace，原因是当前 fix 尚未提交；提交后必须复验。

## Validation

Controller 本地复跑：

```bash
source .venv/bin/activate && pytest tests/host/test_public_steer.py tests/host/test_public_resolve_wait_resume.py tests/host/test_public_lifecycle_smoke.py tests/host/test_public_retry_replay.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py -q
# 22 passed

source .venv/bin/activate && pytest tests/host/test_package_exports.py -q
# 8 passed

source .venv/bin/activate && pytest tests/host -q
# 696 passed, 1 skipped

source .venv/bin/activate && python -m pyright dayu/host tests/host
# 0 errors, 0 warnings, 0 informations

git diff --check
# clean

git diff --check main
# clean
```

AgentMiMo 复跑 focused public smoke、`tests/host`、pyright、`git diff --check`、`git diff --check main`，均通过；`main...HEAD` 的旧 whitespace 待 commit 后复验。AgentDS 复跑 focused public smoke、pyright、`git diff --check`、`git diff --check main`，均通过；`main...HEAD` 的旧 whitespace 待 commit 后复验。

## Residual Risks

- `wait_for_public_waiting_run(...)` 为取得 public `resolve_wait(wait_id, ...)` 的输入，在 public `get_run(...)` 已观察到 `WAITING` 后读取 durable wait record id。该 helper 仅存在于 `public_smoke_support.py`，不作为 correctness assertion；若后续 public surface 冻结 wait id event / snapshot 字段，应迁移到纯 public wait id 读取。
- `_diagnostic_event_type_count(...)` 仍直连 SQLite `event_log`，但仅由 `wait_for_diagnostic_event_type_count(...)` 包装用于 diagnostic event 同步，不作为 public smoke correctness assertion。
- `test_public_cancel_session_runs.py` 仍包含低层 command-facade 测试 helper；它不在 PR62-F2 public smoke seed scope 内。
