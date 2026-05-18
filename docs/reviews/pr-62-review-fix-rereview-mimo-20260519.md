# PR 62 Review Fix Re-Review — AgentMiMo

## Verdict

**PASS**

blocking findings count = 0；无新 blocker。

## Accepted Fixes Status

### PR62-F1 — Public smoke 直连 SQLite event_log 收口

状态：**已收口**

- `test_public_lifecycle_smoke.py`、`test_public_retry_replay.py`、`test_public_cancel_session_runs.py` 中重复的 `_event_type_count` / `_wait_for_event_type_count` 实现已删除。
- 剩余 `wait_for_diagnostic_event_type_count(...)` 集中在 `tests/host/public_smoke_support.py:1065-1086`，有中文 docstring 声明"只用于 public smoke 中等待非 public-display 的调度诊断事件……不是 correctness assertion"。
- `_diagnostic_event_type_count(db_path, event_type)` 在 `public_smoke_support.py:1467-1486`，是唯一保留的 SQLite 直读点，用途限定为 diagnostic event 同步。
- `test_public_cancel_smoke.py` 和 `test_public_steer.py` 通过 import `wait_for_diagnostic_event_type_count` 复用，不再各自实现。
- 所有 final answer / cancel / close / steer / retry / replay / resolve_wait 结果断言均通过 public `get_run(...)` / `RunStatus` / `HostEvent` 证明。

### PR62-F2 — WAITING setup 不再使用 `create_host_command_handle`

状态：**已收口**

- `test_public_steer.py:17` 已移除 `from dayu.host.command import create_host_command_handle`，改为 import `AwaitingThenFinalWorkerFactory`、`awaiting_tooling_options`、`wait_for_public_waiting_run` from `public_smoke_support`。
- `test_public_resolve_wait_resume.py:10` 同上，已移除 `create_host_command_handle` import。
- WAITING setup 路径：`open_host(options)` → `submit_followup(...)` → `AwaitingThenFinalWorkerFactory` 首次 dispatch 进入 awaiting → `wait_for_public_waiting_run(host, options, run_id)` 通过 public `get_run(...)` 观察 `WAITING` 状态 → 后续 `submit_followup(steer)` / `resolve_wait(...)` 验证 public path。
- `wait_for_public_waiting_run(...)` 从 durable wait record 读取 `wait_id`（仅用于桥接 public `resolve_wait` 输入），集中在 `public_smoke_support.py:1028-1062`，docstring 声明"不是 correctness assertion"。

### PR62-F3 — Trailing whitespace 清理

状态：**部分收口**（working tree clean，committed artifacts 未清理）

- `git diff --check` — clean（working tree vs HEAD）
- `git diff --check main` — clean（working tree vs main）
- `git diff --check main...HEAD` — 仍报 7 处 committed review artifacts 的 trailing whitespace：
  - `docs/reviews/phase10-5-aggregate-deepreview-controller-adjudication-20260518.md:7`
  - `docs/reviews/phase10-5-aggregate-rereview-controller-adjudication-20260518.md:7`
  - `docs/reviews/phase10-5-slice6-implementation-codex-20260518.md:37,39,41,43,45`
- Codex fix artifact 已说明：handoff 明确禁止 commit，`main...HEAD` 比较 committed state，clean 需要提交后复验。
- **结论**：fix 内容存在于 working tree，提交后 `git diff --check main...HEAD` 预期 clean。不构成 merge blocker。

## Verification Results

| Command | Result |
|---------|--------|
| `pytest tests/host/test_public_steer.py tests/host/test_public_resolve_wait_resume.py tests/host/test_public_lifecycle_smoke.py tests/host/test_public_retry_replay.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py -q` | 22 passed in 0.65s |
| `pytest tests/host -q` | 696 passed, 1 skipped in 49.17s |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |
| `git diff --check main` | clean |
| `git diff --check main...HEAD` | 7 trailing whitespace in committed review artifacts（需提交后复验） |

## Remaining Risk

1. **Committed review artifacts trailing whitespace**：`git diff --check main...HEAD` 的 7 处 trailing whitespace 在已 committed 的 review artifacts 中。fix 内容已在 working tree，需在 PR review fix commit 中一并提交，提交后复验。
2. **`wait_for_public_waiting_run` 读取 durable wait record**：该 helper 从 durable store 读取 `wait_id`，因为 public HostEvent / RunSnapshot surface 不暴露 `wait_id`。读取集中在 `public_smoke_support.py`，docstring 声明非 correctness assertion，不影响 public contract freeze 结论。
3. **`test_public_cancel_session_runs.py` 仍使用 `create_host_command_handle`**：该文件不在 PR62-F2 裁决 scope 内（F2 仅覆盖 `test_public_steer.py` 和 `test_public_resolve_wait_resume.py`），其 `create_host_command_handle` 用法属于 command-facade 层级测试，非 public smoke。
