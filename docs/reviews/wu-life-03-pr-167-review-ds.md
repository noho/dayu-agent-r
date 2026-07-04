# PR #167 Review — AgentDS (WU-LIFE-03 第二路 PR Review)

## Scope

- Mode: PR
- PR: #167
- Title: WU-LIFE-03: active cancel watchdog timeout closeout
- Author: noho
- Head: phase/host-engine-next
- Base: main
- URL: https://github.com/noho/dayu-agent-r/pull/167
- Output file: docs/reviews/wu-life-03-pr-167-review-ds.md
- Included scope: 43 changed files — dayu/host/ (8 production), tests/host/ (6 test), docs/host/ (3 docs), docs/reviews/ (26 review artifacts)
- Excluded scope: 无
- Parallel review coverage: 无

## PR Body 声明验证

### Closes #91

Issue #91 状态 OPEN，scope 为 "WU-LIFE-03: Active Attempt cancel watchdog target"。PR #167 实现了完整的 active cancel watchdog timeout closeout：
- durable timeout closeout helper（`active_cancel_timeout_closeout_in_transaction`）
- Host watchdog tick/loop（`HostDispatchScheduler.tick_active_cancel_watchdog` / `_active_cancel_watchdog_loop`）
- cancel commit 后 watchdog wakeup（`_wake_active_cancel_watchdog`）
- startup tick before recovery scan + recovery defer for accepted-cancel CANCELLING runs
- late terminal rejection（`_REASON_LATE_TERMINAL_AFTER_ACTIVE_CANCEL`）
- queue promotion after timeout closeout

PR body 使用 `Closes #91`，merge 后 auto-close 准确。

### Residual owner #87 / WU-TOOLS-CANCEL-01

PR body 声明的 residual risks：

| Residual Risk | Owner | 准确性 |
|---|---|---|
| Provider/tool physical interruption and active worker cleanup | WU-TOOLS-CANCEL-01 | 准确。plan non-goals 明确规定不做 provider-specific kill API，timeout closeout 只写 Host terminal truth。 |
| Watchdog runtime tuning, timeout default tuning, scan-query optimization, cross-instance clock skew | #87 umbrella | 准确。plan residual risks 和 design.md 均将 clock skew、tuning、scan optimization 归属 #87。 |
| `active_cancel_timeout_seconds=None` 作为 explicit opt-out | 无独立 owner，由 design.md 记录 | 准确。plan 和 design.md 均明确该行为。 |

## Scope Boundary 验证

所有 43 个 changed files 均在 WU-LIFE-03 plan 的 `Affected Files / Modules` 或 plan/review artifact 范围内：

- **生产代码** (8 files): `dayu/host/api.py`, `command.py`, `dispatch.py`, `durable/run_transition.py`, `engine_ingest.py`, `open_host.py`, `recovery.py`, `README.md` — 均对应该 plan 的 allowed modules。
- **测试代码** (6 files): `tests/host/test_active_cancel_dispatch.py`, `test_dispatch_scheduler.py`, `test_engine_ingest_mapping.py`, `test_open_host_runtime.py`, `test_recovery_scan.py`, `test_run_attempt_transitions.py` — 均对应 plan 中列出的测试模块。
- **文档** (3 files): `docs/host/design.md`, `issues-implementation-control.md`, `wu-life-03-active-cancel-watchdog-plan.md` — 设计真源和总控文档更新。
- **Review artifacts** (26 files): 完整的 plan review → slice 1 → slice 2 → aggregate deepreview 全链路 artifacts，controller adjudication 齐全。

无 WU-LIFE-03 范围外变更混入。

## 设计真源 / README / 总控一致性

- **`docs/host/design.md`**: 更新了 cancel governance 节（增加 `active_cancel_timeout_seconds` 行为说明、recovery defer 规则）、startup recovery 节（增加 watchdog 优先于 recovery 的 ordering）和 `CANCELLING` orphan 行为（启用 watchdog 时不走 LOST）。设计描述与代码实现一致。
- **`dayu/host/README.md`**: 更新了 `OpenHostOptions` 描述（增加 active cancel timeout）、cancel summary（增加 watchdog timeout closeout 行为）、dispatch scheduler 节（增加 watchdog tick/loop 说明）、recovery 节（增加 watchdog defer 规则）。README 更新符合其 `Agent更新约束`，只同步了 public boundary 变化。
- **`docs/host/issues-implementation-control.md`**: 更新了当前状态表（gate、implementation status、active work unit、next entry point）、WU-WAIT-02/WU-WAIT-03 状态、WU-LIFE-03 状态（含完整的 gate 流水记录）。状态描述与 PR #166 已 merge、WU-LIFE-03 进入 draft-PR-pass 的事实一致。
- **`docs/host/wu-life-03-active-cancel-watchdog-plan.md`**: plan artifact 在 plan gate 写入，未在后续 gate 修改，符合预期。

## Artifacts 完整性

gateflow 全链路 artifacts 齐全：

| Gate | Artifacts | 状态 |
|---|---|---|
| Plan review | `plan-review-20260704-105429.md`, `plan-review-20260704-105503.md`, controller adjudication | 已完成 |
| Plan fix | `wu-life-03-plan-fix-codex.md` | 已完成 |
| Plan re-review | `plan-review-20260704-110623.md`, `plan-review-20260704-110719.md`, controller adjudication | 已完成 |
| Slice 1 implementation | `wu-life-03-slice1-implementation-codex.md` | 已完成 |
| Slice 1 code review | `code-review-20260704-112548.md`, `code-review-20260704-112608.md`, controller adjudication | 已完成 |
| Slice 1 fix | `wu-life-03-slice1-fix-codex.md` | 已完成 |
| Slice 1 re-review | `code-review-20260704-113656.md`, `code-review-20260704-113657.md`, controller adjudication | 已完成 |
| Slice 2 implementation | `wu-life-03-slice2-implementation-codex.md` | 已完成 |
| Slice 2 code review | `wu-life-03-slice2-code-review-mimo.md`, `wu-life-03-slice2-code-review-ds.md`, controller adjudication | 已完成 |
| Slice 2 fix | `wu-life-03-slice2-fix-codex.md` | 已完成 |
| Slice 2 re-review | `wu-life-03-slice2-code-rereview-mimo.md`, `wu-life-03-slice2-code-rereview-ds.md`, controller adjudication | 已完成 |
| Aggregate deepreview | `wu-life-03-aggregate-deepreview-mimo.md`, `wu-life-03-aggregate-deepreview-ds.md`, controller adjudication | 已完成 |
| PR review (当前) | 本 artifact + MiMo review (待完成) | 进行中 |

所有 artifact 均已提交并推送到 `phase/host-engine-next` 分支。

## 测试 / pyright 声明与实际一致性

PR body 声明的验证命令与实测结果：

| 命令 | 声明 | 实测 |
|---|---|---|
| `pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py tests/host/test_recovery_scan.py -q` | — | **142 passed** |
| `pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py -q` | — | **123 passed** |
| `pyright` | — | **0 errors, 0 warnings** |
| `git diff --check` | — | **clean** |

测试覆盖了 plan 中列出的关键场景：
- `test_active_cancel_watchdog_times_out_non_cooperative_worker` — 覆盖 blocked worker timeout closeout
- `test_active_cancel_watchdog_noops_before_timeout` — 覆盖 timeout 前不动作
- `test_active_cancel_watchdog_zero_cancelling_runs_noops` — 覆盖空扫描
- `test_active_cancel_timeout_closeout_writes_cancelled_terminal_facts` — 覆盖 durable transition
- `test_active_cancel_timeout_closeout_first_committer_wins_after_cooperative_cancel` — 覆盖 CAS race
- `test_late_final_answer_after_run_cancelling_is_rejected_with_diagnostic` — 覆盖 late terminal rejection
- `test_late_run_failed_after_run_cancelling_is_rejected_with_diagnostic` — 覆盖 late failure rejection
- `test_active_cancel_watchdog_reopen_closes_existing_cancelling_run` — 覆盖 clean-close-reopen
- `test_active_cancel_watchdog_reopen_defers_not_yet_timed_out_cancelling_run` — 覆盖 recovery defer
- `test_cancel_session_replay_repropagates_before_timeout_without_new_facts` — 覆盖 replay
- `test_scheduler_close_does_not_write_active_cancel_timeout_terminal` — 覆盖 close boundary
- `test_active_cancel_timeout_promotes_queued_run` — 覆盖 queue promotion after closeout

## Findings

### 01-未修复-低-Watchdog Scan 全量非终态 Run 扫描

- **入口/函数**: `_read_active_cancel_watchdog_candidates` → `read_non_terminal_runs`
- **文件(行号)**: `dayu/host/dispatch.py:4058`
- **输入场景**: Host 中存在大量非终态 Run（ACCEPTED, QUEUED, RUNNING, WAITING, RECOVERING）时，每次 watchdog tick 都执行全表扫描。
- **实际分支**: `read_non_terminal_runs` 返回所有非终态 Run（6 种 status），然后 Python 侧过滤 `CANCELLING`。
- **预期行为**: 当前实现符合 plan 的 "scan source is durable SQL state" 设计方向。
- **实际行为**: SQL 层面 `WHERE status IN (...)` 已包含精确过滤，但 SQL 仍返回所有非终态行，由 Python 循环过滤。
- **直接证据**: `dayu/host/durable/state.py:1791` — `WHERE status IN (?, ?, ?, ?, ?, ?)` 返回 6 种状态；`dayu/host/dispatch.py:4058` — `for run in read_non_terminal_runs(transaction)` 遍历所有非终态 Run。
- **影响**: 大量非终态 Run 时每次 tick 产生不必要的 row 扫描和 Python 对象构造开销。不影响 correctness。
- **建议改法和验证点**: 可添加专用 `read_cancelling_runs` SQL 查询，在 SQL 层只返回 `CANCELLING` 行。但 plan 已将该优化归属 #87 umbrella follow-up，当前不作为 PR blocker。
- **修复风险（低）**: 纯查询优化，不影响状态机。
- **严重程度（低）**: performance optimization，非 blocking。

## Open Questions

无。

## Residual Risk

- Watchdog scan 全量非终态 Run 扫描在高负载场景下的性能影响归属 #87 umbrella tuning。
- `active_cancel_timeout_seconds` 默认值 300.0 秒是否满足生产需求需实际运维验证，归属 #87。
- Cross-instance UTC clock skew 可能导致 reopen 后 timeout 检测偏早或偏晚，归属 #87。
- Provider/tool physical interrupt 能力缺失意味着 timeout `CANCELLED` 后旧 worker 的 side effects 可能继续，归属 WU-TOOLS-CANCEL-01。

## 结论

**PASS**

PR #167 完整承载 WU-LIFE-03 / #91 scope。实现严格遵循 plan 的 contract、state machine、slice 切分和测试规格。与 main 相比只有 WU-LIFE-03 范围内变更。design.md / README.md / issues-implementation-control.md 更新完整且与代码实现一致。所有 artifacts 已提交推送。测试和 pyright 声明与实际一致。未发现 PR 级别 blocker 或 correctness/blocking regression。
