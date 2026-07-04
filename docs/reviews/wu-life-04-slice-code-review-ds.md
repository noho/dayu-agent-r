# Code Review — WU-LIFE-04 Slice 1 + Slice 2 Combined Implementation

## Scope

- Mode: current changes
- Branch: `phase/wu-life-04-deadline-watchdog`
- Base: accepted plan commit `59be8480`
- Output file: `docs/reviews/wu-life-04-slice-code-review-ds.md`
- Included scope: all workspace changes (unstaged diff) relative to `59be8480`, covering `dayu/host/`, `docs/host/`, and `tests/host/`
- Excluded scope: `docs/reviews/` (review artifacts), `docs/host/wu-life-04-*.md` (plan), `dayu/engine/` (no changes expected or observed), `dayu/runtime/`, `dayu/service/`, `dayu/config/`, `utils/`, root `README.md`
- Parallel review coverage: 无（本 review 由单一 reviewer 完整走读所有关键入口和链路）

## Review Method Summary

走读了以下关键入口与调用链：

1. **Public contract cleanup**：`OpenHostOptions` / `HostLocalExecutionOptions` dataclass 字段删除、验证删除、投影删除
2. **Watchdog tick 主链路**：`wake_active_cancel_watchdog` → `tick_active_cancel_watchdog` → candidate scan (`_read_active_cancel_watchdog_candidates`) → `active_cancel_watchdog_closeout_in_transaction` → payload construction
3. **Watchdog 后台循环**：`_start_active_cancel_watchdog_loop` → `_active_cancel_watchdog_loop`
4. **Startup recovery 联动**：`open_host` 中 `tick_active_cancel_watchdog` → `StartupRecoveryScanner.scan`，其中 `defer_accepted_cancel_to_watchdog=True` 无条件生效
5. **Candidate preconditions**：Run `CANCELLING`、Attempt `RUNNING`、worker-accepted dispatch、linked accepted cancel fact
6. **Closeout replay / first-committer-wins**：`_active_cancel_watchdog_replay_result`、`_invalid_active_cancel_watchdog_closeout_precondition`
7. **Scheduler close**：watchdog task 在 `close()` 中被 cancel 和 await
8. **测试面**：active cancel dispatch、run/attempt transitions、open_host runtime startup recovery、engine ingest mapping、public options contract、dispatch scheduler

## Findings

### 1-未修复-低-`_normalized_event_occurred_at` 成为死代码

- **入口/函数**: `_normalized_event_occurred_at`（模块级私有辅助函数）
- **文件(行号)**: `dayu/host/durable/run_transition.py:6323`
- **输入场景**: 该函数不再被任何生产代码或测试代码调用
- **实际分支**: 函数定义存在但无调用点
- **预期行为**: 重构完成后应删除不再使用的私有辅助函数
- **实际行为**: 函数保留在模块中，从未被调用
- **直接证据**: `rg "_normalized_event_occurred_at" dayu/host/` 仅命中 `run_transition.py:6323` 的定义行，无任何调用点。旧代码中唯一的调用方是 `_active_timeout_cancelled_payload`（已被 `_active_watchdog_cancelled_payload` 替代），新 payload 函数不再调用此 helper
- **影响**: 仅维护性影响——死代码增加模块体积，可能让后续读者困惑其用途。不影响运行时正确性或性能
- **建议改法和验证点**: 删除 `_normalized_event_occurred_at` 函数定义（`run_transition.py:6323-6334`）；运行 `pyright dayu/host/` 确认无新增错误；运行现有 Host tests 确认无回归
- **修复风险（低）**: 该函数为纯函数（无副作用），删除不影响任何调用链
- **严重程度（低）**:
- **候选裁决**: accepted

## Core Contract Verification

以下逐项验证实现是否满足 plan 与 controller 设定的核心预期：

### 1. `active_cancel_timeout_seconds` 从 public API 和 internal options 删除

**验证结果：通过。**

- `OpenHostOptions.active_cancel_timeout_seconds` 字段、docstring、默认值 `_DEFAULT_ACTIVE_CANCEL_TIMEOUT_SECONDS`、`__post_init__` 验证均已删除（`dayu/host/api.py`）
- `HostLocalExecutionOptions.active_cancel_timeout_seconds` 字段、docstring、验证均已删除（`dayu/host/api.py`）
- `_local_execution_options_from_open_host_options` 中的投影行已删除（`dayu/host/open_host.py:1300` 附近）
- `rg "active_cancel_timeout_seconds" dayu/host tests/host docs/host/design.md dayu/host/README.md` 无匹配
- `test_open_host_options_do_not_accept_removed_active_cancel_budget` 测试覆盖了 dataclass fields 和 constructor signature 两个维度（`tests/host/test_public_open_host_options.py`）
- 未引入任何 internal disable flag、opt-out 或替代 public option

### 2. Watchdog 不再按 `cancel_requested_at + timeout_seconds` 延迟

**验证结果：通过。**

- `tick_active_cancel_watchdog`（`dayu/host/dispatch.py:1069-1142`）中，candidate loop 直接对每个候选调用 `active_cancel_watchdog_closeout_in_transaction`，无任何时间比较
- 旧代码中的 `(now - candidate.cancel_requested_at).total_seconds() < timeout_seconds` 判断已完全删除
- `test_active_cancel_watchdog_closes_on_first_tick_after_cancel`（原 `test_active_cancel_watchdog_noops_before_timeout`）验证 cancel accepted 后首个 tick 即 closeout：`result.closed == 1`、`RunStatus.CANCELLED`、`RUN_CANCELLED` event count 为 1

### 3. Closeout helper/reason/signal/payload 语义不再描述 timeout

**验证结果：通过。**

- `ActiveCancelTimeoutCloseoutInput` → `ActiveCancelWatchdogCloseoutInput`（`dayu/host/durable/run_transition.py:872`）
- `active_cancel_timeout_closeout_in_transaction` → `active_cancel_watchdog_closeout_in_transaction`（`run_transition.py:2248`）
- 内部 helper 全部重命名：`_active_timeout_attempt_cancelled_event_request` → `_active_watchdog_attempt_cancelled_event_request`、`_active_timeout_cancelled_payload` → `_active_watchdog_cancelled_payload` 等
- reason：`"active_cancel_timeout"` → `"active_cancel_watchdog_closeout"`（`run_transition.py:104` 定义 `_ACTIVE_CANCEL_WATCHDOG_CLOSEOUT_REASON`）
- worker lifecycle signal：`"active_cancel_timeout"` → `"active_cancel_watchdog_closeout"`（`dispatch.py:166`）
- event ID prefix：`event-attempt-cancelled-timeout` → `event-attempt-cancelled-watchdog`、`event-run-cancelled-timeout` → `event-run-cancelled-watchdog`（`dispatch.py:177-178`）
- payload：不再包含 `timeout_seconds` 和 `timed_out_at`；改为 `cancel_requested_at` 和 `closed_out_at`（`run_transition.py:4435-4437`）
- `rg "active_cancel_timeout|timeout_seconds.*active" dayu/host tests/host docs/host/design.md dayu/host/README.md` 无匹配
- 测试断言均验证新 payload 不含 `timeout_seconds` / `timed_out_at`，含 `closed_out_at`（`test_run_attempt_transitions.py:1837-1838`）

### 4. Candidate preconditions 保持严格

**验证结果：通过。**

`_active_cancel_watchdog_candidate_from_run`（`dispatch.py:4062-4099`）前置条件逐项验证：

| 条件 | 检查位置 | 失败行为 |
|---|---|---|
| Run 存在且 `current_attempt_id` 非空 | line 4076-4077 | 返回 `None`（非候选） |
| Attempt 存在且状态为 `RUNNING` | line 4078-4080 | 返回 `None` |
| dispatch record 存在且有 worker-accepted durable fact，未被 pre-accept cancel | line 4081-4086 → `_dispatch_record_has_worker_accept` (line 4102-4117) | 返回 `None` |
| linked accepted cancel fact（`CANCEL_REQUESTED` 通过 `RUN_CANCELLING` payload 链接，且 `CANCEL_REQUESTED` event 同 run_id、正确 event_type） | line 4087-4093 → `_read_linked_cancel_requested_event` (line 4120-4162) | 返回 `None` |

`_invalid_active_cancel_watchdog_closeout_precondition`（`run_transition.py:5062-5119`）在事务内做二次 CAS 检查：Run `CANCELLING`、Attempt `RUNNING`、dispatch record worker-accepted 且未被 cancel、各 ID 对齐。这是事务内的 last-moment recheck，防止 candidate scan 到 closeout 之间的 TOCTOU（虽然在同一事务内不会发生，但防御性保留是正确的）。

### 5. Startup recovery 与 always-enabled watchdog 一致

**验证结果：通过。**

- `open_host` 中 `defer_accepted_cancel_to_watchdog=True` 无条件传入 `StartupRecoveryScanner`（`open_host.py:898`）
- `StartupRecoveryScanner._classify_run`（`recovery.py:292-309`）：`CANCELLING` + `defer_accepted_cancel_to_watchdog` + `_has_accepted_cancel_fact` 时返回 `DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG`
- startup 先执行 `scheduler.tick_active_cancel_watchdog(datetime.now(UTC))` 再执行 scanner（`open_host.py:892-899`），确保 watchdog 先收口，scanner 不再看到已收口的 Run
- `_has_accepted_cancel_fact`（`recovery.py:654-695`）与 `_read_linked_cancel_requested_event`（`dispatch.py:4120-4162`）使用等价的 fact chain 验证逻辑：`RUN_CANCELLING` → payload `cancel_request_event_id` → `CANCEL_REQUESTED` event（同 run_id、正确 type）
- `test_open_host_reopen_closes_accepted_cancel_with_watchdog`（原 `test_open_host_reopen_before_timeout_defers_cancelling_to_watchdog`）验证 reopen 后 accepted-cancel Run 被关闭为 `CANCELLED` 且无 `RUN_LOST`

### 6. Orphan CANCELLING without accepted cancel 仍不被错误 closeout

**验证结果：通过。**

- Candidate 过滤器要求 `_read_linked_cancel_requested_event` 返回非 None（`dispatch.py:4092-4093`），无 linked cancel fact 的 CANCELLING Run 不会被选为候选
- `_invalid_active_cancel_watchdog_closeout_precondition` 要求 Run 状态为 `CANCELLING`（`run_transition.py:5099`），并进一步要求 `RUN_CANCELLING` event 存在且 payload 含有效 `cancel_request_event_id`（`run_transition.py:2284-2296`）
- Startup recovery scanner：`CANCELLING` 无 accepted cancel fact → 不 defer → 进入 `_classify_active_or_cancelling` → 走 orphan proof 路径 → 满足条件时转为 `LOST`
- `test_active_cancel_watchdog_closeout_requires_cancelling_run` 验证无 cancel fact 时 closeout 返回 `INVALID_STATE`（`test_run_attempt_transitions.py:1903`）

### 7. Late terminal first-committer-wins、queued promotion、command replay、scheduler close 语义未回归

**验证结果：通过。**

- **First-committer-wins**：`_active_cancel_watchdog_replay_result` 在 Run/Attempt 已是 `CANCELLED` 时返回 `UPDATED`（`run_transition.py:5047-5058`）；`_invalid_active_cancel_watchdog_closeout_precondition` 在状态不匹配时返回 `INVALID_STATE`。测试：`test_active_cancel_watchdog_closeout_first_committer_wins_after_cooperative_cancel`（cooperative cancel 先收口）、`test_active_cancel_watchdog_closeout_rejects_after_succeeded_terminal`（success terminal 先提交）
- **Queued promotion**：`tick_active_cancel_watchdog` 在 closeout 成功后调用 `wake_queue_promotion(session_id)`（`dispatch.py:1136`）。测试：`test_active_cancel_watchdog_closeout_promotes_queued_run`
- **Command replay**：`test_cancel_session_replay_after_watchdog_does_not_append_or_propagate` 验证 terminal 后 session cancel replay 不追加 facts
- **Scheduler close**：`close()` 方法在 line 2505-2508 cancel/await watchdog task。测试：`test_scheduler_close_does_not_write_active_cancel_watchdog_closeout_terminal` 验证 close 不写 terminal facts

### 8. Engine `tool_execution_timeout_seconds` contract 未被修改

**验证结果：通过。**

- `dayu/engine/` 目录无任何变更（`git diff 59be8480...HEAD -- dayu/engine/` 无输出）
- `tests/engine/test_agent_phase3_tool_call.py` 44 passed（controller 验证结果）
- `dayu/config/execution_profiles.json` 未变更
- `docs/engine/design.md` 未变更

## Design Doc Consistency

`docs/host/design.md` 的修改与实现一致：

- Cancel 章节删除了 `OpenHostOptions.active_cancel_timeout_seconds` 独立 post-cancel timeout 描述，改为 accepted-cancel closeout supervisor 语义（line 2493）
- 明确 closeout 不表示 provider/tool 物理停止（line 2493）
- Startup recovery 章节删除 `active_cancel_timeout_seconds=None` opt-out（line 2502）
- `defer_accepted_cancel_to_watchdog` 改为无条件生效（line 2502-2503, 2661-2662）
- 所有 `active_cancel_timeout` 语义替换为 watchdog closeout 语义

`dayu/host/README.md` 的修改与实现一致：

- `OpenHostOptions` 描述删除 `active cancel timeout`（line 91）
- Cancel mechanism 描述更新：watchdog 不再提供 public post-cancel timeout budget（line 568）
- Dispatch scheduler 描述更新：不再描述 timeout 判定，改为 accepted cancel fact closeout（line 590）
- Startup recovery 描述更新：删除 "启用 active cancel watchdog 时" 条件前缀（line 602）

## Test Coverage Assessment

| 测试文件 | 关键覆盖 |
|---|---|
| `test_public_open_host_options.py` | public field removal + constructor signature check |
| `test_active_cancel_dispatch.py` | first-tick closeout, zero-candidate no-op, multiple eligible, queued promotion, session replay, scheduler close |
| `test_run_attempt_transitions.py` | closeout terminal facts, precondition rejection (no cancel fact, malformed payload), first-committer-wins (cooperative, success), replay |
| `test_open_host_runtime.py` | public watch observes closeout, reopen closes accepted-cancel CANCELLING, reopen with watchdog closeout |
| `test_engine_ingest_mapping.py` | late worker terminal after watchdog closeout, helper/fixture/payload rename sync |
| `test_dispatch_scheduler.py` | watchdog loop transient failure recovery, scheduler close cleanup |

**未覆盖或弱覆盖区域：**

- 无测试直接验证 candidate filter 对"RUN_CANCELLING 存在但 linked CANCEL_REQUESTED 缺失"的 Run 正确排除。当前通过 closeout 层 `_invalid_active_cancel_watchdog_closeout_precondition` 间接覆盖（`test_active_cancel_watchdog_closeout_requires_cancelling_run` 测试无 cancel fact 场景），但 candidate filter 层无独立测试。风险低——candidate filter 和 closeout preconditions 使用逻辑等价的 fact chain 验证。
- 无测试覆盖 watchdog loop 在 scheduler close 后的行为（close 已设置 `_closed=True`，loop 在下次迭代检查 `_closed` 时退出）。`test_scheduler_close_does_not_write_active_cancel_watchdog_closeout_terminal` 覆盖了 close 后 tick 不写 terminal facts，但没有直接测试 loop 退出。
- 无性能/压力测试覆盖全表扫描路径（已知 residual risk，已有 #87 owner）。

## Open Questions

无。

## Residual Risk

| 风险 | Owner | 说明 |
|---|---|---|
| Watchdog 全表扫描性能 | Issue #87 performance follow-up | `read_non_terminal_runs` 扫描所有非终态 Run，在 Run 数量大时可能成为瓶颈 |
| 物理中断未实现 | WU-TOOLS-CANCEL-01 | Host closeout 只表达 durable cancel 收口，不物理停止工具线程/进程/HTTP 请求 |
| Per-tool deadline observability | WU-TOOLS-CANCEL-01 或 #87 child | Host 当前无法精确知道"正在运行的单个工具调用"的原始 deadline |
| 死代码 `_normalized_event_occurred_at` | 本 WU（见 Finding 1） | 重构后遗留的未使用私有函数 |
| Clock skew / multi-host timestamp ordering | Issue #87 diagnostics/audit follow-up | 去掉 timeout 比较降低了 clock skew 风险，但 event timestamp 仍依赖 Host clock |
| Shared supervisor abstraction | Issue #87 umbrella | 多 target-specific supervisor 出现真实重复或运维需求前不引入 |

## Review Conclusion

**Pass.** 实现完整、准确地满足了 WU-LIFE-04 plan 的所有核心要求。`active_cancel_timeout_seconds` 已从 public API 和 internal options 完全删除，watchdog 改为 accepted-cancel closeout supervisor 无 post-cancel 时间预算，所有 closeout 语义、reason、signal、payload 已从 timeout 重命名为 watchdog closeout。Candidate preconditions 保持严格，startup recovery 与 always-enabled watchdog 一致，late terminal first-committer-wins、queued promotion、command replay、scheduler close 语义均未回归。Engine `tool_execution_timeout_seconds` contract 未被修改。

发现 1 个低严重度 finding（死代码 `_normalized_event_occurred_at`），建议在 closeout 前清理。无 blocking finding，无 open question。
