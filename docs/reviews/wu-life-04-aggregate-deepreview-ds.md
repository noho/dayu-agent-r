# Aggregate Deepreview — WU-LIFE-04 Tool Execution Deadline And Issue 168 Watchdog Closeout

## Scope

- Mode: current changes (aggregate deepreview over full branch diff + workspace uncommitted)
- Branch: `phase/wu-life-04-deadline-watchdog`
- Base: `main`
- Output file: `docs/reviews/wu-life-04-aggregate-deepreview-ds.md`
- Review date: 2026-07-04
- Included scope: full `git diff main...HEAD` (30 files, 1968 insertions, 306 deletions) + workspace uncommitted `docs/host/issues-implementation-control.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Plan: `docs/host/wu-life-04-tool-execution-deadline-watchdog-plan.md`
- Control source: `docs/host/issues-implementation-control.md`
- Prior review artifacts: plan review → plan fix → plan re-review → Slice 1/2 implementation → code review → fix → code re-review (all passed)
- Excluded scope: `docs/reviews/` (review artifacts), `dayu/engine/` (no changes, not in review scope), `dayu/runtime/`, `dayu/service/`, `dayu/config/`, `utils/`, root `README.md`
- Parallel review coverage: 无（本 aggregate deepreview 由单一 reviewer 完整走读所有关键入口与调用链）

## Review Method

本 aggregate deepreview 对以下维度逐一展开 adversarial 走读：

1. **跨 commit / 全 work unit 一致性**：plan → 2-slice implementation → fix → re-review → accepted commit `c75205c5` → workspace control doc 更新
2. **Public API 删除完整性**：`OpenHostOptions.active_cancel_timeout_seconds`、`HostLocalExecutionOptions.active_cancel_timeout_seconds`、`_DEFAULT_ACTIVE_CANCEL_TIMEOUT_SECONDS` 是否完整删除，有无残留兼容 wrapper
3. **Watchdog no-extra-budget closeout**：与 Host design、startup recovery、EventLog payload、tests、README 的一致性
4. **README/control residual risk owner**：是否遗漏需更新的 README 或未归属 residual risk
5. **Plan/review artifact 与代码一致性**：plan 中的每条 exact change 是否落到代码
6. **Gate bookkeeping**：workspace 未提交 control doc 状态更新是否正确，无遗漏

走读了以下关键入口与调用链：

- Public contract: `dayu/host/api.py` (`OpenHostOptions`, `HostLocalExecutionOptions`), `dayu/host/open_host.py` (`_local_execution_options_from_open_host_options`)
- Watchdog: `dispatch.py` (`wake_active_cancel_watchdog` → `tick_active_cancel_watchdog` → `_read_active_cancel_watchdog_candidates` → `active_cancel_watchdog_closeout_in_transaction` → `_active_watchdog_cancelled_payload`), `_start_active_cancel_watchdog_loop` → `_active_cancel_watchdog_loop`
- Startup recovery: `open_host.py` (`tick_active_cancel_watchdog` before scan, `defer_accepted_cancel_to_watchdog=True`), `recovery.py` (`_classify_run`, `_has_accepted_cancel_fact`)
- Durable transition: `run_transition.py` (`ActiveCancelWatchdogCloseoutInput`, `active_cancel_watchdog_closeout_in_transaction`, payload construction)
- Command path: `command.py` (`active_cancel_watchdog_wakeup_port` integration)
- Tests: `test_active_cancel_dispatch.py`, `test_run_attempt_transitions.py`, `test_open_host_runtime.py`, `test_public_open_host_options.py`, `test_dispatch_scheduler.py`, `test_engine_ingest_mapping.py`
- Docs: `docs/host/design.md`, `dayu/host/README.md`, `docs/host/issues-implementation-control.md`

## Findings

### AGG-F01-未修复-低-`ActiveCancelWatchdogTickResult.eligible` docstring 残留旧 timeout 语义

- **入口/函数**: `ActiveCancelWatchdogTickResult` dataclass docstring
- **文件(行号)**: `dayu/host/dispatch.py:400`
- **输入场景**: 任何读取此 dataclass docstring 的开发者
- **实际分支**: docstring 文本
- **预期行为**: `eligible` 字段的 docstring 应描述为 "本轮满足 accepted-cancel 收口前置条件的 Run 数"，与当前 no-extra-budget 语义一致
- **实际行为**: docstring 写的是 `本轮达到 timeout 条件的 Run 数`——这是旧 timeout-based watchdog 的残留描述
- **直接证据**: `dayu/host/dispatch.py:400`：`:param eligible: 本轮达到 timeout 条件的 Run 数。`。当前代码中 `tick_active_cancel_watchdog`（line 1069-1142）已完全删除 timeout 比较逻辑，`eligible` 计数来自 `_read_active_cancel_watchdog_candidates` 返回的 candidates 列表长度（每个 candidate 满足 CANCELLING + RUNNING Attempt + worker-accepted dispatch + linked accepted cancel fact 前置条件），与 "timeout 条件" 无关
- **影响**: 仅文档准确性——docstring 与代码行为不一致，可能误导后续维护者。不影响运行时正确性
- **建议改法和验证点**: 将 `dayu/host/dispatch.py:400` 的 docstring 改为 `本轮满足 accepted-cancel 收口前置条件的 Run 数。` 或等效描述；运行 pyright 确认无新增错误
- **修复风险（低）**: 纯 docstring 修改，不涉及逻辑变更
- **严重程度（低）**:
- **候选裁决**: accepted

## Core Contract Verification

以下逐项验证实现是否满足 plan 设定的每项目标：

### 1. `active_cancel_timeout_seconds` 从 public API 删除

**验证结果：通过。**

| 检查项 | 状态 | 证据 |
|---|---|---|
| `OpenHostOptions.active_cancel_timeout_seconds` 字段删除 | ✓ | `api.py` dataclass 中无此字段 |
| `_DEFAULT_ACTIVE_CANCEL_TIMEOUT_SECONDS` 删除 | ✓ | `rg` 全仓库无匹配 |
| `OpenHostOptions.__post_init__` 中验证删除 | ✓ | 验证代码中无 `active_cancel_timeout` 引用 |
| `HostLocalExecutionOptions.active_cancel_timeout_seconds` 删除 | ✓ | dataclass 字段、docstring、验证均已移除 |
| `_local_execution_options_from_open_host_options` 投影删除 | ✓ | `open_host.py:1269-1303` 不再构造该字段 |
| 未引入 internal disable flag | ✓ | `defer_accepted_cancel_to_watchdog=True` 硬编码，watchdog 无条件启用 |
| 无兼容 wrapper/re-export | ✓ | `rg "active_cancel_timeout_seconds" dayu/host tests/host docs/host/design.md dayu/host/README.md` → exit 1（无匹配） |
| 公开 option 测试验证拒绝旧字段 | ✓ | `tests/host/test_public_open_host_options.py:test_open_host_options_do_not_accept_removed_active_cancel_budget` |

### 2. Watchdog no-extra-budget closeout

**验证结果：通过。**

| 检查项 | 状态 | 证据 |
|---|---|---|
| tick 不再比较 elapsed time | ✓ | `dispatch.py:1069-1142`：candidate loop 直接对每个候选调用 closeout，无 `(now - candidate.cancel_requested_at).total_seconds()` |
| cancel commit 唤醒 watchdog | ✓ | `dispatch.py:1054-1067`：`wake_active_cancel_watchdog` 通过 `Queue.put_nowait` + `_start_active_cancel_watchdog_loop` 唤醒 |
| 首 tick 即 closeout | ✓ | `test_active_cancel_watchdog_closes_on_first_tick_after_cancel` 验证 `result.closed == 1`, `RunStatus.CANCELLED` |
| `wake_active_cancel_watchdog` 不再因 timeout=None 返回 | ✓ | 当前实现无条件唤醒（`Queue.put_nowait`），无 timeout 判断 |

### 3. Closeout helper/reason/signal/payload 语义

**验证结果：通过。**

| 检查项 | 状态 | 证据 |
|---|---|---|
| `ActiveCancelTimeoutCloseoutInput` → `ActiveCancelWatchdogCloseoutInput` | ✓ | `run_transition.py:872` |
| `active_cancel_timeout_closeout_in_transaction` → `active_cancel_watchdog_closeout_in_transaction` | ✓ | `run_transition.py:2248` |
| reason 字符串 | ✓ | `run_transition.py:104`：`_ACTIVE_CANCEL_WATCHDOG_CLOSEOUT_REASON = "active_cancel_watchdog_closeout"` |
| worker lifecycle signal | ✓ | `dispatch.py:228`：`_ACTIVE_CANCEL_WORKER_LIFECYCLE_SIGNAL = "active_cancel_watchdog_closeout"` |
| event ID prefix | ✓ | `event-attempt-cancelled-watchdog`, `event-run-cancelled-watchdog` |
| payload 不含 `timeout_seconds` / `timed_out_at` | ✓ | `run_transition.py:4428-4448`：payload 字段为 `cancel_requested_at` / `closed_out_at` |
| 测试断言验证 payload 字段 | ✓ | `test_run_attempt_transitions.py:1837-1838`：`assert "timeout_seconds" not in payload`, `assert "timed_out_at" not in payload`, `assert payload["closed_out_at"] == "..."` |
| `rg "active_cancel_timeout\|timeout_seconds.*active"` | ✓ | exit 1（无匹配） |

### 4. Candidate preconditions

**验证结果：通过。**

`_active_cancel_watchdog_candidate_from_run`（`dispatch.py:4062-4099`）前置条件逐项验证：

| 条件 | 代码位置 | 失败行为 |
|---|---|---|
| Run `current_attempt_id` 非空 | line 4076-4077 | 返回 `None` |
| Attempt 存在且状态 `RUNNING` | line 4078-4080 | 返回 `None` |
| dispatch record 已有 worker accept，未 pre-accept cancel | line 4081-4086 → `_dispatch_record_has_worker_accept` (line 4102-4117) | 返回 `None` |
| linked accepted cancel fact | line 4087-4093 → `_read_linked_cancel_requested_event` | 返回 `None` |

`_invalid_active_cancel_watchdog_closeout_precondition` 在事务内做二次 CAS recheck，保证 closeout 写入时的 last-moment 状态一致性。

### 5. Startup recovery 一致性

**验证结果：通过。**

| 检查项 | 状态 | 证据 |
|---|---|---|
| `open_host` 中 watchdog tick 在 recovery scan 之前 | ✓ | `open_host.py:892`：`scheduler.tick_active_cancel_watchdog(datetime.now(UTC))` 在 `StartupRecoveryScanner(...).scan()`（line 893-899）之前执行 |
| `defer_accepted_cancel_to_watchdog=True` 硬编码 | ✓ | `open_host.py:898`：无条件传入 |
| recovery defer 逻辑 | ✓ | `recovery.py:292-306`：`CANCELLING` + `defer_accepted_cancel_to_watchdog` + `_has_accepted_cancel_fact` → `DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG` |
| `_has_accepted_cancel_fact` 验证 | ✓ | `recovery.py:654-695`：读取 `RUN_CANCELLING` → 提取 `cancel_request_event_id` → 读取 `CANCEL_REQUESTED` → 验证 `run_id` 匹配 |
| test_open_host_reopen 两条路径 | ✓ | `test_open_host_reopen_closes_existing_cancelling_run_as_cancelled`（closed 后 reopen → `CANCELLED`，非 `LOST`）; `test_open_host_reopen_closes_accepted_cancel_with_watchdog`（reopen 后 watchdog closeout → `CANCELLED`，非 `LOST`） |

### 6. Design doc 同步

**验证结果：通过。**

- `docs/host/design.md` Cancel 章节（line 2490-2501 in diff）：删除 `OpenHostOptions.active_cancel_timeout_seconds` 段落与 `reason=active_cancel_timeout` 措辞，替换为 "accepted-cancel closeout supervisor, no post-cancel budget"
- `docs/host/design.md` Startup recovery 章节（line 3446-3464 in diff）：删除 `active_cancel_timeout_seconds=None` opt-out 描述，改为 "startup 先执行一次 watchdog tick，再由 scanner defer 剩余 accepted-cancel CANCELLING Run"
- 设计文本中无残留 `active_cancel_timeout` 引用

### 7. README 同步

**验证结果：通过。**

- `dayu/host/README.md` line 88-91：`OpenHostOptions` 描述删除 `active cancel timeout`，改为仅列 `truncation manager 开关`
- `dayu/host/README.md` Cancel 章节（line 565-568）：删除 `active_cancel_timeout_seconds` 相关描述，改为 "accepted-cancel closeout supervisor, no post-cancel timeout budget"
- `dayu/host/README.md` Startup recovery 章节（line 599-602）：删除 "启用 active cancel watchdog 时"条件措辞，改为无条件 defer 描述
- `tests/README.md`：不包含 `active_cancel_timeout` 引用，测试分类描述与变更一致，无需更新

### 8. Plan 逐条 exact change 对照

**Slice 1 exact changes 对照：**

| Plan 要求 | 实现状态 |
|---|---|
| 更新 `docs/host/design.md` Cancel 和 startup recovery 文本 | ✓ 已更新 |
| 删除 `_DEFAULT_ACTIVE_CANCEL_TIMEOUT_SECONDS` | ✓ 已删除（grep 无匹配） |
| 删除 `OpenHostOptions.active_cancel_timeout_seconds` 字段、docstring、验证 | ✓ 已删除 |
| 删除 `_local_execution_options_from_open_host_options` 中的投影 | ✓ 已删除 |
| 删除 `HostLocalExecutionOptions.active_cancel_timeout_seconds` | ✓ 已删除 |
| 不新增 internal disable flag | ✓ 无条件启用 |
| 更新 `dayu/host/README.md` | ✓ 已更新 |

**Slice 2 exact changes 对照：**

| Plan 要求 | 实现状态 |
|---|---|
| `wake_active_cancel_watchdog` 不再因 timeout=None 返回 | ✓ 无条件唤醒 |
| `_start_active_cancel_watchdog_loop` 不再被 timeout 门控 | ✓ 无条件启动 |
| `tick_active_cancel_watchdog(now)` 不再比较 elapsed time | ✓ 直接 closeout |
| `_read_active_cancel_watchdog_candidates` preconditions 保持严格 | ✓ 四个前置条件均检查 |
| 重命名 `ActiveCancelTimeoutCloseoutInput` → `ActiveCancelWatchdogCloseoutInput` | ✓ 已完成 |
| 重命名 terminal reason 和 worker lifecycle signal | ✓ `active_cancel_watchdog_closeout` |
| payload 不含 `timeout_seconds` / `timed_out_at` | ✓ 已替换为 `cancel_requested_at` / `closed_out_at` |
| startup recovery 无条件 defer accepted-cancel | ✓ `defer_accepted_cancel_to_watchdog=True` 硬编码 |
| 测试覆盖 no-post-cancel-budget、reopen、promotion 等场景 | ✓ 测试已重命名并更新断言 |

### 9. 先前 review findings 最终状态

| Finding ID | 原状态 | 最终状态 | 验证依据 |
|---|---|---|---|
| S1S2-CR-F01 (`_normalized_event_occurred_at` 死代码) | accepted → 已修复 | 已关闭 | re-review 确认函数定义已从 `run_transition.py` 删除，`import math` 已清理，`rg` 无匹配 |
| S1S2-CR-R01 (watchdog loop fatal exit 无自动恢复) | deferred-with-owner | 仍 deferred | owner: Issue #87 umbrella diagnostics/supervisor follow-up |

### 10. Controller 验证结果（face-value acceptance）

Controller 报告以下验证已通过（本 review 不重新执行，作为 face-value acceptance）：

- `pytest tests/engine/test_agent_phase3_tool_call.py -q`: 44 passed
- Host focused tests: 250 passed
- pyright: 0 errors
- `git diff --check`: passed
- `rg "active_cancel_timeout_seconds" dayu/host tests/host docs/host/design.md dayu/host/README.md`: no matches
- `rg "active_cancel_timeout\|timeout_seconds.*active" dayu/host tests/host docs/host/design.md dayu/host/README.md`: no matches

### 11. Workspace 未提交 control doc 一致性

**验证结果：通过。**

Workspace diff (`docs/host/issues-implementation-control.md`) 变更：
- `gate`: `accepted slice commit` → `aggregate deepreview`（正确反映当前 gate）
- `implementation status`: 追加 "Accepted Slice 1 + Slice 2 implementation commit 为 `c75205c5`。当前进入 aggregate deepreview gate。"
- `next entry point`: 更新为 "WU-LIFE-04 aggregate deepreview gate: run two independent deepreviews over the full branch diff since main."
- WU-LIFE-04 行末尾追加 accepted slice commit 记录 `c75205c5`

变更与当前 gate 状态一致，无遗漏或错误。

## Open Questions

- 无。本 aggregate deepreview 无阻碍 confident judgment 的开放问题。

## Residual Risk

以下 residual risks 在 plan 和先前 review 中均已明确 owner/destination，本 aggregate deepreview 确认无新增未归属风险：

| Risk | Owner | 状态 |
|---|---|---|
| Per-tool original deadline durable observability | WU-TOOLS-CANCEL-01 或 Issue #87 child | deferred-with-owner |
| Physical interruption after Host closeout | WU-TOOLS-CANCEL-01 | deferred-with-owner |
| Watchdog scan query optimization (全表扫描) | Issue #87 performance follow-up | deferred-with-owner |
| Clock skew / multi-host timestamp ordering | Issue #87 diagnostics/audit follow-up | deferred-with-owner |
| Shared supervisor abstraction | Issue #87 umbrella | deferred-with-owner |
| Watchdog loop fatal exit 无自动恢复 | Issue #87 umbrella diagnostics/supervisor follow-up | deferred-with-owner (S1S2-CR-R01) |
| `ActiveCancelWatchdogTickResult.eligible` docstring 残留旧 timeout 语义 | 本 WU fix gate（AGG-F01） | open（低严重度） |

## Aggregate Deepreview Conclusion

**Pass.** 本 aggregate deepreview 确认 WU-LIFE-04 实现满足 accepted plan 的全部目标：

- `active_cancel_timeout_seconds` 已从 `OpenHostOptions` 和 `HostLocalExecutionOptions` 完整删除，无兼容 wrapper、无 internal disable flag。
- Watchdog no-extra-budget closeout 正确实现：cancel commit 唤醒 watchdog，首 tick 即 closeout 符合条件的 CANCELLING Run。
- Closeout helper、reason、worker lifecycle signal、EventLog payload 已全面从 timeout 语义迁移到 accepted-cancel watchdog closeout 语义。
- Startup recovery 无条件 defer accepted-cancel CANCELLING Run 给 watchdog，不将其路由到 LOST。
- Host design、README、control doc 均已同步更新。
- 所有先前 review 的 accepted findings 已修复并验证关闭；deferred risks 均有明确 owner。
- Controller 验证通过（engine 44 tests, Host 250 tests, pyright 0 errors）。

发现 1 个低严重度 docstring 残留问题（AGG-F01），不阻塞 aggregate deepreview pass。

**Finding 数量**: 1（低严重度）
**Blocking findings**: 0
**Blocking open questions**: 0
