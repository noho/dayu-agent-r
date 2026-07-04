# WU-LIFE-04 Final Closeout

## 基本信息

- Work unit: WU-LIFE-04 Tool Execution Deadline And Issue 168 Watchdog Closeout
- Gate: final closeout
- Date: 2026-07-04
- Draft PR: https://github.com/noho/dayu-agent-r/pull/169
- GitHub Issue: https://github.com/noho/dayu-agent-r/issues/168
- Umbrella owner: https://github.com/noho/dayu-agent-r/issues/87

## 变更摘要

- 删除 Host public API 与 internal local execution options 中的 `active_cancel_timeout_seconds`。
- 将 active cancel watchdog closeout 固定为 accepted-cancel no-extra-budget 语义，不再引入取消后的第二套执行预算。
- 将 closeout helper、reason、worker lifecycle signal 与 EventLog payload 字段从 timeout 命名迁移到 accepted-cancel closeout 命名。
- 将 active cancel watchdog scan 从全局非终态 Run 读取改为专用 `CANCELLING` Run 查询，并为 status-ordered scan 增加 durable index。
- 补齐 startup recovery、Engine ingest mapping、dispatch scheduler、public options、effective execution config 和 transition regression 测试。
- 更新 Host design、Host README、测试 README、plan/review/deepreview/fix/re-review artifacts 与总控文档。

## 验证记录

- `pytest tests/engine/test_agent_phase3_tool_call.py -q` -> 44 passed
- `pytest tests/host/test_active_cancel_dispatch.py tests/host/test_run_attempt_transitions.py tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_effective_execution_config.py tests/host/test_public_open_host_options.py -q` -> 250 passed
- `python -m pyright dayu/ tests/ utils/` -> 0 errors
- `git diff --check` -> passed
- Required grep checks for `active_cancel_timeout_seconds` and `active_cancel_timeout|timeout_seconds.*active` -> no matches in required scope
- `pytest tests/host/test_state_schema.py tests/host/test_durable_schema.py tests/host/test_active_cancel_dispatch.py -q` -> 84 passed
- `gh pr checks 169 --repo noho/dayu-agent-r` -> no checks reported on branch `phase/wu-life-04-deadline-watchdog`

## Review / Finding 状态

- Plan review: MiMo / DS completed; accepted findings fixed; plan re-review passed.
- Implementation review: MiMo / DS completed; accepted dead helper cleanup finding fixed; code re-review passed.
- Aggregate deepreview: MiMo / DS completed; accepted stale docstring finding fixed; aggregate re-review passed.
- PR review: MiMo / DS completed; no accepted findings; accepted PR review commit `52cf5dc9` pushed to draft PR 169.

## Issue / PR Closeout

- Draft PR 169 is open and draft: https://github.com/noho/dayu-agent-r/pull/169
- PR body uses `Closes #168`; merge will automatically close GitHub Issue 168.
- PR body uses `Related to #87`; Issue 87 remains the umbrella owner and must not be closed by this PR.
- Issue closeout comment posted: https://github.com/noho/dayu-agent-r/issues/168#issuecomment-4881439527
- Issue closeout correction comment posted: https://github.com/noho/dayu-agent-r/issues/168#issuecomment-4881529208

## Remaining Risks / Owners

- Tool/provider physical interruption remains owned by WU-TOOLS-CANCEL-01.
- Watchdog scan query optimization is closed in this PR by a dedicated `CANCELLING` Run query and status sequence index.
- Clock/audit diagnostics and shared supervisor abstraction are not active WU-LIFE-04 defects after the accepted-cancel closeout and scan-query fix; they do not remain as independent Issue 87 follow-up owners.
- After PR 169 merges, the next implementation entry point is WU-TOOLS-CANCEL-01 from updated `main`.
- After both WU-LIFE-04 and WU-TOOLS-CANCEL-01 are complete, Issue 87 can be closed as the lifecycle watchdog / supervisor umbrella.
