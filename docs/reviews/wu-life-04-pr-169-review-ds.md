# PR Review — WU-LIFE-04 PR #169

## Scope

- Mode: PR review
- Repository: noho/dayu-agent-r
- PR: #169 (draft)
- URL: https://github.com/noho/dayu-agent-r/pull/169
- Title: WU-LIFE-04: tool deadline watchdog closeout
- Author: noho
- Head branch: phase/wu-life-04-deadline-watchdog
- Base branch: main
- Work unit: WU-LIFE-04 Tool Execution Deadline And Issue 168 Watchdog Closeout
- Output file: docs/reviews/wu-life-04-pr-169-review-ds.md
- Review date: 2026-07-04
- Included scope: PR #169 相对 main 的完整 diff（37 files, 2583 insertions, 307 deletions），覆盖 `dayu/host/`、`tests/host/`、`docs/host/design.md`、`docs/host/wu-life-04-*.md`、30 个 `docs/reviews/wu-life-04-*` review artifacts
- Excluded scope: `dayu/engine/`、`dayu/runtime/`、`dayu/service/`、`dayu/config/`、`utils/`、根 `README.md`（均不在 PR diff 中）
- CI/checks: 该分支上无 CI check 报告（draft PR 预期状态）
- Parallel review coverage: 无（单一 reviewer 完整走读所有关键生产代码变更和测试变更）

## Review Method

本 PR review 按以下维度展开：

1. **PR body 准确性**：检查 summary、validation、residual risks 是否与实际 PR diff 一致；issue closing linkage 是否正确
2. **PR diff 生产代码走读**：逐文件追踪 `dayu/host/api.py`、`dayu/host/dispatch.py`、`dayu/host/durable/run_transition.py`、`dayu/host/open_host.py` 的关键入口和调用链
3. **与 accepted artifacts/commits 一致性**：对照 plan、aggregate deepreview findings 最终状态、control doc 的 accepted commit 记录
4. **测试变更走读**：验证 6 个测试文件变更的正确性、语义对齐和覆盖率
5. **设计文档/README 同步**：验证 `docs/host/design.md`、`dayu/host/README.md` 变更与生产代码一致
6. **未提交/未推送变更检查**：确认本地 workspace 无遗漏的必要变更
7. **PR 级别 blocker 检查**：adversarial pass 寻找 correctness、completeness、consistency、missing validation 问题
8. **control doc 当前 PR gate 状态一致性**：检查本地 control doc 状态与 PR 实际状态是否一致

走读了以下关键入口与调用链：

- Public contract 删除: `OpenHostOptions` → `_local_execution_options_from_open_host_options` → `HostLocalExecutionOptions`
- Watchdog closeout: `wake_active_cancel_watchdog` → `tick_active_cancel_watchdog` → `_read_active_cancel_watchdog_candidates` → `active_cancel_watchdog_closeout_in_transaction` → `_active_watchdog_cancelled_payload`
- Watchdog lifecycle: `_start_active_cancel_watchdog_loop` → `_active_cancel_watchdog_loop`
- Startup recovery: `open_host` (`tick_active_cancel_watchdog` before `StartupRecoveryScanner`) → `defer_accepted_cancel_to_watchdog=True` → `recovery._classify_run` → `_has_accepted_cancel_fact`
- Durable transition: `ActiveCancelWatchdogCloseoutInput` → `active_cancel_watchdog_closeout_in_transaction` → replay/idempotency/precondition checks → EventLog append

## Findings

未发现实质性问题。

### 逐项验证

#### 1. PR Body 准确性

**验证结果：通过。**

| 检查项 | 状态 | 证据 |
|---|---|---|
| Summary 描述与 PR diff 一致 | ✓ | 删除了 public/internal `active_cancel_timeout_seconds`，转换为 accepted-cancel no-extra-budget 语义，重命名 closeout helpers/reason/signal/payload 字段 |
| Validation 数据与 controller 验证一致 | ✓ | engine tests 44 passed、Host tests 250 passed、pyright 0 errors、`git diff --check` passed、grep checks 无匹配 |
| `Closes #168` 链接正确 | ✓ | PR body 末尾明确 `Closes #168`；Issue #168 当前 OPEN，标题为 "WU-LIFE-04: Tool execution deadline and #87 watchdog closeout" |
| 未错误关闭 #87 | ✓ | PR body 使用 `Related to #87`，不是 `Closes #87` |
| Residual risks / owners 描述准确 | ✓ | Tool/provider physical interruption → WU-TOOLS-CANCEL-01；Watchdog scan query optimization、clock/audit diagnostics、shared supervisor → #87 |

#### 2. Public API 删除完整性

**验证结果：通过。**

| 检查项 | 状态 | 证据 |
|---|---|---|
| `OpenHostOptions.active_cancel_timeout_seconds` 字段删除 | ✓ | `dayu/host/api.py` dataclass 中无此字段，docstring 中描述已移除 |
| `_DEFAULT_ACTIVE_CANCEL_TIMEOUT_SECONDS` 常量删除 | ✓ | `rg` 全仓库无匹配 |
| `__post_init__` 中验证调用删除 | ✓ | 验证 `_require_optional_positive_finite_float` 调用已移除，该函数定义已删除 |
| `HostLocalExecutionOptions.active_cancel_timeout_seconds` 删除 | ✓ | 字段、docstring、`__post_init__` 验证均已移除 |
| `_local_execution_options_from_open_host_options` 投影删除 | ✓ | `open_host.py` 不再构造该字段 |
| 无 internal disable flag | ✓ | `defer_accepted_cancel_to_watchdog=True` 硬编码；watchdog 无条件启动 |
| 无兼容 wrapper / re-export | ✓ | `rg "active_cancel_timeout_seconds" dayu/host tests/host docs/host/design.md dayu/host/README.md` → exit 1 |
| 公开 option 测试验证拒绝旧字段 | ✓ | `tests/host/test_public_open_host_options.py:test_open_host_options_do_not_accept_removed_active_cancel_budget` |

#### 3. Watchdog No-Extra-Budget Closeout

**验证结果：通过。**

| 检查项 | 状态 | 证据 |
|---|---|---|
| `wake_active_cancel_watchdog` 不再因 timeout=None 返回 | ✓ | 无条件执行 `Queue.put_nowait`，删除了 `if self._local_execution.active_cancel_timeout_seconds is None: return` |
| `_start_active_cancel_watchdog_loop` 不再被 timeout 门控 | ✓ | 无条件创建 asyncio task |
| `tick_active_cancel_watchdog(now)` 不再比较 elapsed time | ✓ | 无 `(now - candidate.cancel_requested_at).total_seconds()` 比较；所有 scanned candidates 直接进入 eligible |
| `_read_active_cancel_watchdog_candidates` 前置条件保持严格 | ✓ | 四个条件：`current_attempt_id` 非空、Attempt `RUNNING`、dispatch record worker-accepted 且非 pre-accept cancel、linked accepted cancel fact |
| 首 tick 即 closeout 测试通过 | ✓ | `test_active_cancel_watchdog_closes_on_first_tick_after_cancel` 断言 `result.closed == 1`、`RunStatus.CANCELLED` |

#### 4. Closeout Helper/Reason/Signal/Payload 重命名

**验证结果：通过。**

| 检查项 | 状态 | 证据 |
|---|---|---|
| `ActiveCancelTimeoutCloseoutInput` → `ActiveCancelWatchdogCloseoutInput` | ✓ | `run_transition.py:872`；`cancel_requested_at: str` + `closed_out_at: datetime` 替换 `timeout_seconds: float` + `timed_out_at: datetime` |
| 函数重命名 | ✓ | `active_cancel_timeout_closeout_in_transaction` → `active_cancel_watchdog_closeout_in_transaction`；所有内部 helper 同步重命名 |
| reason 常量 | ✓ | `_ACTIVE_CANCEL_WATCHDOG_CLOSEOUT_REASON = "active_cancel_watchdog_closeout"` |
| worker lifecycle signal | ✓ | `_ACTIVE_CANCEL_WORKER_LIFECYCLE_SIGNAL = "active_cancel_watchdog_closeout"` |
| event ID prefix | ✓ | `event-attempt-cancelled-watchdog`、`event-run-cancelled-watchdog` |
| payload 不含 `timeout_seconds` / `timed_out_at` | ✓ | payload 字段为 `cancel_requested_at`、`closed_out_at`、`watchdog_owner`、`worker_lifecycle_signal` 等 |
| `_normalized_event_occurred_at` 死代码删除 | ✓ | 函数定义已从 `run_transition.py` 删除（AGG-F01 前身 S1S2-CR-F01 已修复） |
| `_validate_active_cancel_watchdog_closeout_input` 验证更新 | ✓ | `timeout_seconds` 验证替换为 `cancel_requested_at` 文本非空验证 |
| `rg "active_cancel_timeout\|timeout_seconds.*active"` | ✓ | `dayu/host tests/host docs/host/design.md dayu/host/README.md` 范围内无匹配 |

#### 5. Startup Recovery 一致性

**验证结果：通过。**

| 检查项 | 状态 | 证据 |
|---|---|---|
| `open_host` 中 watchdog tick 在 recovery scan 之前 | ✓ | `open_host.py:892`：先 tick 再 scan |
| `defer_accepted_cancel_to_watchdog=True` 硬编码 | ✓ | `open_host.py:898`：无条件传入 |
| recovery defer 逻辑 | ✓ | `recovery.py`：`CANCELLING` + `defer_accepted_cancel_to_watchdog` + `_has_accepted_cancel_fact` → `DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG` |
| reopen 后 watchdog closeout 测试 | ✓ | `test_open_host_reopen_closes_accepted_cancel_with_watchdog` 断言 `CANCELLED`（非 `CANCELLING`）且 `RUN_LOST == 0` |
| `_force_cancel_requested_at` 删除 | ✓ | 不再需要操纵 cancel 时间来触发 timeout |

#### 6. 设计文档/README 同步

**验证结果：通过。**

| 检查项 | 状态 | 证据 |
|---|---|---|
| `docs/host/design.md` Cancel 章节 | ✓ | 删除 `OpenHostOptions.active_cancel_timeout_seconds` 段落，替换为 accepted-cancel closeout supervisor 描述 |
| `docs/host/design.md` Startup recovery 章节 | ✓ | 删除 `active_cancel_timeout_seconds=None` opt-out，改为无条件 watchdog 优先处理 |
| `dayu/host/README.md` `OpenHostOptions` 描述 | ✓ | 删除 `active cancel timeout`，保留 `truncation manager 开关` |
| `dayu/host/README.md` Cancel 章节 | ✓ | 删除 `active_cancel_timeout_seconds` 描述，改为 accepted-cancel closeout supervisor |
| `dayu/host/README.md` Startup recovery 章节 | ✓ | 删除 "启用 active cancel watchdog 时" 条件措辞 |
| 设计文本中无残留 `active_cancel_timeout` | ✓ | grep 确认 |

#### 7. 测试变更

**验证结果：通过。**

- `tests/host/test_active_cancel_dispatch.py`：测试重命名（`_noops_before_timeout` → `_closes_on_first_tick_after_cancel`）、断言更新（`closed == 0`/`CANCELLING` → `closed == 1`/`CANCELLED`）、`_open_scheduler` 删除 `active_cancel_timeout_seconds` 参数、replay/promotion/close 测试同步重命名
- `tests/host/test_run_attempt_transitions.py`：import、helper 函数、event_id、payload 断言、docstring 全部从 timeout 语义重命名为 watchdog 语义
- `tests/host/test_open_host_runtime.py`：测试重命名、删除 `active_cancel_timeout_seconds=0.5`/`=300.0` 构造参数、删除 `_force_cancel_requested_at` helper、断言更新
- `tests/host/test_public_open_host_options.py`：新增 `test_open_host_options_do_not_accept_removed_active_cancel_budget` 验证字段不存在于 dataclass fields 和 constructor parameters
- `tests/host/test_dispatch_scheduler.py`：删除 `active_cancel_timeout_seconds=1.0` 参数、新增 watchdog task cleanup（watchdog 现在无条件启动）
- `tests/host/test_engine_ingest_mapping.py`：import、operation 类、event_id、payload 字段同步重命名

所有测试重命名完整、无遗漏，断言语义与 watchdog no-extra-budget closeout 行为一致。

#### 8. 先前 Review Findings 最终状态

| Finding ID | 最终状态 | 验证依据 |
|---|---|---|
| AGG-F01 (eligible docstring) | 已修复 | aggregate fix + re-review 确认；当前代码中 docstring 已改为 accepted-cancel 收口前置条件语义 |
| S1S2-CR-F01 (`_normalized_event_occurred_at` 死代码) | 已修复 | re-review 确认删除；`import math` 已清理 |
| S1S2-CR-R01 (watchdog loop fatal exit) | deferred-with-owner | owner: #87 umbrella |

#### 9. PR Commits vs Accepted Artifacts 一致性

**验证结果：通过。**

| Accepted Artifact | Commit | 状态 |
|---|---|---|
| Accepted plan | `59be8480` gateflow: accept plan for WU-LIFE-04 | ✓ PR 包含 |
| Accepted implementation (Slice 1 + 2) | `c75205c5` gateflow: accept WU-LIFE-04 implementation | ✓ PR 包含 |
| Accepted aggregate deepreview | `cd92dbb9` gateflow: accept deepreview for WU-LIFE-04 | ✓ PR 包含 |
| Draft PR preparation | `0cd4e0b2` gateflow: prepare WU-LIFE-04 draft PR | ✓ PR 包含 |

4 个 commit 均在 PR 中，与 control doc 记录的 accepted commit 一致。远程分支 HEAD = 本地 HEAD = `0cd4e0b2`，已推送。

#### 10. 未提交/未推送变更检查

**验证结果：通过（gate bookkeeping 预期内）。**

- 本地 unstaged：`docs/host/issues-implementation-control.md` 更新 gate 从 `ready-to-open-draft-PR` → `PR review`，WU-LIFE-04 状态从 `ready-to-open-draft-PR` → `review`，next entry point 更新为 PR review gate 描述
- 本地 staged：无
- 这些变更是 controller workflow 的正常 gate bookkeeping，不是遗漏的必要变更。PR diff 中包含的 control doc 状态（`ready-to-open-draft-PR`）是 draft PR 准备时的状态，当前 `PR review` 是进入 PR review gate 后的更新
- 远程 HEAD = 本地 HEAD，无未推送 commit

#### 11. Control Doc PR Gate 状态一致性

**验证结果：通过。**

PR 中的 control doc (`0cd4e0b2`):
- gate: `ready-to-open-draft-PR`
- WU-LIFE-04: `ready-to-open-draft-PR`
- next entry point: draft PR gate

本地 unstaged control doc 更新:
- gate: `PR review`
- WU-LIFE-04: `review`
- next entry point: PR review gate

这是正常的 gate 推进：controller 在准备 draft PR 时写入 `ready-to-open-draft-PR`，进入 PR review gate 后更新为 `PR review`。PR 中的 control doc 状态与 PR 创建时的 gate 一致，本地更新反映当前 gate。无 mismatch 或遗漏。

#### 12. PR 级别 Blocker 检查

以下 adversarial pass 逐项未发现 blocker：

| 风险维度 | 检查结果 |
|---|---|
| 公共 API 兼容性 | `active_cancel_timeout_seconds` 完整删除，无残留兼容 wrapper；grep 确认 |
| 状态机正确性 | `RUNNING → cancel → CANCELLING → watchdog closeout → CANCELLED` 不变；first-committer-wins 不变 |
| 并发/竞态 | watchdog closeout 与 worker cooperative closeout 通过 CAS recheck + first-committer-wins 保护；与 WU-LIFE-03 一致 |
| 恢复路径 | startup recovery 无条件 defer accepted-cancel 给 watchdog；watchdog tick 在 scan 前执行 |
| EventLog payload 变更 | 字段重命名遵循 new-schema 策略（项目策略允许），无旧兼容读取 |
| 取消/idempotency | `cancel_session_runs` replay 在 watchdog terminal 后不追加 facts、不传播 cancel（`test_cancel_session_replay_after_watchdog_does_not_append_or_propagate`） |
| 测试覆盖率 | 关键行为均有测试：first-tick closeout、first-committer-wins、replay protection、queued promotion、malformed payload rejection、reopen paths |
| Docs/README 同步 | 设计文档和 README 均已更新 |

#### 13. Review Artifacts 检查

PR 包含 30 个 `docs/reviews/wu-life-04-*` review artifacts。这些是 gate 流程记录（plan review、plan fix、plan re-review、slice implementation、code review、fix、re-review、aggregate deepreview、aggregate fix、aggregate re-review、controller adjudication），均为预期内 artifact。逐一检查确认：

- 所有 review artifact 的最终结论与 controller adjudication 一致
- 所有 accepted findings 均已关闭
- 所有 deferred residual risks 均有明确 owner
- 无 artifact 之间的结论冲突

## Open Questions

无。

## Residual Risk

以下 residual risks 在 plan、aggregate deepreview、PR body 和 control doc 中均已明确 owner/destination，本 PR review 确认无新增未归属风险：

| Risk | Owner | 状态 |
|---|---|---|
| Per-tool original deadline durable observability | WU-TOOLS-CANCEL-01 或 #87 child | deferred-with-owner |
| Physical interruption after Host closeout | WU-TOOLS-CANCEL-01 | deferred-with-owner |
| Watchdog scan query optimization | #87 performance follow-up | deferred-with-owner |
| Clock skew / multi-host timestamp ordering | #87 diagnostics/audit follow-up | deferred-with-owner |
| Shared supervisor abstraction | #87 umbrella | deferred-with-owner |
| Watchdog loop fatal exit 无自动恢复 | #87 umbrella diagnostics/supervisor follow-up | deferred-with-owner (S1S2-CR-R01) |

## PR Review Conclusion

**Pass.** 本 PR review 确认 PR #169 满足 WU-LIFE-04 全部目标：

1. `active_cancel_timeout_seconds` 已从 `OpenHostOptions` 和 `HostLocalExecutionOptions` 完整删除，无兼容 wrapper、无 internal disable flag
2. Watchdog no-extra-budget closeout 正确实现：cancel commit 唤醒 watchdog，首 tick 即 closeout 符合条件的 CANCELLING Run
3. Closeout helper、reason、worker lifecycle signal、EventLog payload 已全面从 timeout 语义迁移到 accepted-cancel watchdog closeout 语义
4. Startup recovery 无条件 defer accepted-cancel CANCELLING Run 给 watchdog，不路由到 LOST
5. Host design、README、control doc 均已同步更新
6. 所有先前 review 的 accepted findings 均已修复并验证关闭
7. 4 个 commit 与 control doc 记录的 accepted artifacts 一致，均已推送到远程
8. 本地 workspace 仅有正常 gate bookkeeping 的 unstaged control doc 更新
9. PR body 正确使用 `Closes #168`，仅 `Related to #87`，不会错误关闭 #87

**Finding 数量**: 0（未发现实质性问题）
**Blocking findings**: 0
**Blocking open questions**: 0
