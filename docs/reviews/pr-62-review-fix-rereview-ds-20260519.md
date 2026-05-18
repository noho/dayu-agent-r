# PR 62 Review Fix Re-Review — AgentDS

## Scope

- Mode: re-review（只读，不修改代码、不 commit、不 push）
- Target: accepted fix PR62-F1/F2/F3 收口验证
- Source documents: `pr-62-deepreview-controller-adjudication-20260518.md`, `pr-62-review-fix-codex-20260519.md`, `pr-62-deepreview-mimo-20260518.md`, `pr-62-deepreview-ds-20260519.md`

## Verdict

**PASS** — blocking findings count = 0

## Accepted Fixes Status

### PR62-F1 — Direct SQLite event_log reads removed from public smoke

**Status: PASS**

Evidence:

- `tests/host/test_public_lifecycle_smoke.py` — 不再包含 `_event_type_count`/`_wait_for_event_type_count` 定义；所有状态等待通过 `_wait_for_run_status` 轮询 `host.get_run()` 完成；无直接 SQLite `event_log` 查询。
- `tests/host/test_public_retry_replay.py` — 不再包含 `_event_type_count`/`_wait_for_event_type_count` 定义；所有状态等待通过 `_wait_for_run_status` 轮询 `host.get_run()` 完成。
- `tests/host/test_public_cancel_smoke.py` — 从 `public_smoke_support` import `wait_for_diagnostic_event_type_count`，用于 ATTEMPT_RUNNING 同步；correctness assertion 走 `host.get_run()`、`host.watch_session_events()`、`HostEventKind`。
- `tests/host/test_public_steer.py` — 从 `public_smoke_support` import `wait_for_diagnostic_event_type_count`，用于 ATTEMPT_RUNNING 同步；correctness assertion 走 `host.get_run()`。
- `tests/host/test_public_cancel_session_runs.py` — `_event_count` helper 已从 raw SQL `SELECT COUNT(*) FROM event_log` 改为通过 `EventLogStore().read_events_after()` 读取；此为 command-facade 层级测试，非 public smoke，符合 F1 边界。
- `tests/host/public_smoke_support.py:1065-1086` — `wait_for_diagnostic_event_type_count` 集中定义，带中文注释声明"只用于 public smoke 中等待非 public-display 的调度诊断事件"、"它不是 correctness assertion"。
- `tests/host/public_smoke_support.py:1467-1486` — `_diagnostic_event_type_count` 为唯一 `sqlite3.connect` 实现，局限在 support 模块内。

### PR62-F2 — create_host_command_handle WAITING seed 移除

**Status: PASS**

Evidence:

- `tests/host/test_public_steer.py` — 不再 import `create_host_command_handle` 或 `dayu.host.command`。`test_steer_waiting_run_creates_new_attempt_public_path` 通过 `open_host(options)` + `AwaitingThenFinalWorkerFactory` + `awaiting_tooling_options()` + 公开 `submit_followup` + `wait_for_public_waiting_run` 生成 WAITING Run。
- `tests/host/test_public_resolve_wait_resume.py` — 不再 import `create_host_command_handle` 或 `dayu.host.command`。`test_resolve_wait_resumes_through_open_host_and_terminal_event` 通过 `open_host(options)` + `AwaitingThenFinalWorkerFactory` + `awaiting_tooling_options()` + 公开 `submit_followup` + `wait_for_public_waiting_run` + 公开 `resolve_wait` 完成 WAITING resume 验证。
- `tests/host/public_smoke_support.py:372-427` — `AwaitingThenFinalWorkerFactory` / `_AwaitingThenFinalWorker` 提供首个 dispatch 进入 WAITING 的 deterministic worker。
- `tests/host/public_smoke_support.py:1028-1062` — `wait_for_public_waiting_run` 先用 public `get_run` 观察 WAITING 状态，再用 durable `_active_wait_id` 桥接 `resolve_wait` 输入；中文注释声明"不能作为 smoke correctness assertion"。
- `tests/host/public_smoke_support.py:1199-1216` — `awaiting_tooling_options()` 提供等待型 mock tool 的完整 HostToolingOptions。

### PR62-F3 — Trailing whitespace cleanup

**Status: PASS（需 commit 后复验 main...HEAD）**

Evidence:

- `git diff --check` — clean（working tree 无 trailing whitespace）
- `git diff --check main` — clean（working tree 相对 main 无 trailing whitespace）
- `git diff --check main...HEAD` — 仍报 5 处 committed artifacts trailing whitespace（`phase10-5-aggregate-deepreview-controller-adjudication-20260518.md:7`、`phase10-5-aggregate-rereview-controller-adjudication-20260518.md:7`、`phase10-5-slice6-implementation-codex-20260518.md:37,39,41,43,45`）

原因：whitespace cleanup 已在 working tree 完成但尚未 commit；`main...HEAD` 比较的是已提交 HEAD 与 main 的差异，因此仍显示 committed whitespace。re-review handoff 明确禁止 commit，此为预期状态。

## 验证结果

| Command | Result |
|---------|--------|
| `pytest tests/host/test_public_steer.py tests/host/test_public_resolve_wait_resume.py tests/host/test_public_lifecycle_smoke.py tests/host/test_public_retry_replay.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py -q` | 22 passed in 0.66s |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |
| `git diff --check main` | clean |
| `git diff --check main...HEAD` | 5 trailing whitespace in committed artifacts（working tree 已修复，待 commit） |

## 额外检查项

### 测试断言方式

所有 public smoke 测试的 correctness assertion 均通过以下 public path 完成：

- `host.get_run(run_id)` — Run 状态/current_attempt_id 断言
- `host.watch_session_events(session_id)` + `HostEventKind` — terminal event 断言
- `host.get_session(session_id)` — Session 状态断言
- 公开 `HostApiError` / `HostClosedError` — 错误路径断言
- deterministic worker observable（`factory.handles[0].cancel_reasons`、`factory.accepted_requests[-1].disable_tools`）— worker 行为断言，非 durable 直读

### 无 duplicate diagnostic helper

`_event_type_count`/`_wait_for_event_type_count` 在 public smoke 文件中已无重复定义。`test_public_lifecycle_smoke.py` 和 `test_public_retry_replay.py` 各自有独立的 `_wait_for_run_status` helper，但其实现是 `host.get_run()` polling——不涉及 `event_log` 直连。

### test_public_cancel_session_runs.py 边界

该文件是 `cancel_session_runs` command facade 测试，非 public opener smoke。它仍使用 `create_host_command_handle`、`start_run`、直接 `sqlite3.connect` 操作 `host_runs` 表——但这些在 command facade 测试上下文中是被允许的，因为该文件测试的是低层 command 行为（幂等重放、unsupported 分类、partial mutation 防护），不是 public smoke。

## Remaining Risk

1. **F3 commit gate**：`git diff --check main...HEAD` 需在 whitespace cleanup commit 后复验。当前 working tree 已 clean，commit 后应通过。
2. **`_active_wait_id` durable 读取**：`public_smoke_support.py:1431-1464` 中的 `_active_wait_id` 通过 `open_host_durable_store` 读取 wait record，用于 `resolve_wait` 的 `wait_id` 桥接。该 helper 局限在 support 模块且带中文注释声明非 correctness assertion，但仍是 durable 直读。若后续 `read_active_wait_records_for_run` 签名变更，`wait_for_public_waiting_run` 需要同步更新。
3. **`_diagnostic_event_type_count` sqlite3.connect**：`public_smoke_support.py:1467-1486` 中的 `_diagnostic_event_type_count` 仍使用 `sqlite3.connect` 直连 `event_log` 表。这是唯一保留的 SQLite bypass，局限在 support 模块且被 `wait_for_diagnostic_event_type_count` 包装，符合 controller F1 裁定（集中到 support 模块 + 中文注释声明仅同步用途）。

## 结论

PR62-F1/F2/F3 三个 accepted fix 均已收口。public smoke 文件不再包含直接 SQLite `event_log` correctness assertion；diagnostic wait 集中在 `public_smoke_support.py` 且仅为同步 primitive；`test_public_steer.py` 与 `test_public_resolve_wait_resume.py` 不再 import `create_host_command_handle`，WAITING setup 通过 `open_host` + public `submit_followup` + awaiting mock tool path 完成；trailing whitespace 已在 working tree 修复，待 commit 后 `git diff --check main...HEAD` 可 clean。所有测试通过，pyright 0 errors。无新 blocker。
