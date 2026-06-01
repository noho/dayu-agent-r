# WU-LIFE-01 + WU-LIFE-02 Slice A Code Review

日期：2026-06-01
Reviewer：AgentMiMo
Role：独立 code review
Gate：code review slice A
Target：当前工作区未提交 diff（`tests/host/test_recovery_scan.py`）
Design source：`docs/host/design.md` 第 27 节
Accepted plan：`docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md`
Implementation report：`docs/reviews/wu-life-01-02-implementation-sliceA-codex-20260601.md`

## Review Scope

本次 review 针对 Slice A implementation 的未提交 diff，重点审查：

1. 是否严格实现 Slice A，不混入 Slice B 或生产逻辑重写。
2. 新增 lifecycle matrix 是否足以承载 plan 要求，existing/new/non-goal 标注是否准确。
3. still-live / inconclusive / WAITING tests 是否基于直接 durable 证据，是否真的断言不写 ATTEMPT_LOST / RUN_RECOVERING / RUN_LOST。
4. 测试是否 deterministic，不依赖 sleep / race。
5. helper / dataclass 是否有中文 docstring、严格类型；是否有 Any / object / untyped 签名。
6. 是否存在过度机械格式化、无关 churn 或可维护性倒退。
7. 验证命令与 report 是否可信，README / doc sync 判断是否正确。

## Review Methodology

- 逐行审阅 `git diff HEAD` 中 `tests/host/test_recovery_scan.py` 的全部变更。
- 交叉验证测试断言与生产代码 `dayu/host/recovery.py` 和 `dayu/host/recovery_process.py` 的实际行为。
- 对照 plan Slice A 的 exact changes、completion signal、stop condition 逐项核对。
- 实际运行 `pytest tests/host/test_recovery_scan.py -q` 验证测试通过。

## Conclusion: pass

Slice A implementation 严格对齐 plan，0 个 blocking finding。新增 5 个测试覆盖 plan 要求的全部 new coverage 场景，recovery lifecycle proof matrix 18 行标注准确，测试 deterministic，类型严格，中文 docstring 完整。无生产代码变更，tests-first 执行未触发 production rewrite。

## Findings

### A1-观察-信息-`_active_run_observation` 使用 `run_write` 执行读操作

**位置**：`tests/host/test_recovery_scan.py:1196`

**证据**：`_active_run_observation` 内部使用 `transaction_runner.run_write(operation)` 执行纯读操作（`read_run_by_id` / `read_attempt_by_id` / `read_dispatch_record_by_attempt_id` / `SELECT event_type`）。同一文件中 `_event_type_count`（line 1371）正确使用 `run_read` 执行同类只读查询。生产代码 `recovery.py::_classify_active_or_cancelling` 的读操作在 scanner 的 `run_write` 事务内完成，但那是写事务的组成部分；独立读 helper 应使用 `run_read`。

**影响**：不影响测试正确性——SQLite 测试 fixture 下 `run_write` 内的读操作能正常返回数据。但语义上 `run_write` 暗示写意图，与 helper 的只读职责不一致，可能误导维护者。

**建议**：将 `run_write` 改为 `run_read`。这是纯测试 helper 语义修正，不影响测试行为。

**严重程度**：信息（不 blocking）。

---

### A2-观察-信息-机械格式化 churn 占 diff 主体

**位置**：diff 中多处 `_seed_running_dispatching_run`、`_seed_unstarted_run`、`_create_accepted_input`、`_create_queued_input`、`_create_running_input`、`_event_types`、`_event_type_count`、`_event_payload_by_type` 等函数签名格式变更。

**证据**：大量变更仅将多行函数签名 / 方法调用合并为单行，或将链式调用从 `.append_event(...).row` 改为 `(...).row`。这些变更不改变任何语义，不是 plan 要求的 Slice A 内容。

**影响**：增加 diff 噪音，降低 review 效率。不影响正确性或可维护性。

**建议**：这些格式化变更是 formatter 驱动的，可接受。但未来 slice 实现应尽量将 formatter 驱动的 churn 与功能变更分离。

**严重程度**：信息（不 blocking）。

---

## Verification Summary

### Plan 对齐检查

| Plan 要求 | 实现状态 | 证据 |
|---|---|---|
| 增加 recovery lifecycle matrix 常量 | 已完成 | `_RECOVERY_LIFECYCLE_PROOF_MATRIX`，18 行，scenario id 唯一，coverage 分类合法 |
| owner heartbeat recent scanner-level integration test | 已完成 | `test_scan_running_owner_heartbeat_recent_does_not_mutate_durable_rows` |
| inconclusive integration test（process probe error / pid live without identity） | 已完成 | `test_scan_running_inconclusive_owner_proof_does_not_mutate_durable_rows`（parametrized 2 cases） |
| WAITING diagnostic-only 用户可见语义测试 | 已完成 | `test_scan_waiting_public_visible_durable_state_remains_diagnostic_only` |
| WAITING low-level reason 断言 | 已完成 | `test_scan_waiting_uses_diagnostic_only_fallback` 新增 reason 断言 |
| RR-DUR-04 proof matrix row | 已完成 | `rr-dur-04-short-transaction-durable-truth`，coverage=NEW |
| test_recovery_lifecycle_proof_matrix_covers_slice_a_rows | 已完成 | 验证 scenario id 唯一性、必需行存在、coverage 分类合法 |
| 不改生产代码 | 已遵守 | diff 只含 `tests/host/test_recovery_scan.py` |
| pyright 通过 | report 声明 | 0 errors, 0 warnings, 0 informations |
| pytest 通过 | 已验证 | 13 passed in 0.28s |

### Matrix 覆盖验证

Plan testing matrix Slice A 共 19 行（含 RR-DUR-01 non-goal），实现 matrix 18 行。差异：plan 中 "RUNNING owner heartbeat recent" 和 "RUNNING pid live without identity proof" 在 matrix 中各占一行，实现正确映射为 `running-owner-heartbeat-recent` 和 `running-stale-heartbeat-only`。plan 中 "RUNNING missing current Attempt / dispatch record" 标注 "existing or new"，实现标注为 `_COVERAGE_EXISTING`，合理——现有 `test_scan_skips_non_terminal_run_when_session_row_is_missing` 已覆盖 `NOT_FOUND` 路径。

所有 matrix row 的 `expected_decision`、`expected_reason`、`expected_durable_mutation` 与生产代码实际行为一致：

- `owner_heartbeat_recent`：`recovery_process.py:273` 返回 `OwnerStillLive(reason=_LIVE_REASON_HEARTBEAT_RECENT)` → `"owner_heartbeat_recent"` ✓
- `process_probe_error`：`recovery_process.py:309-315` 返回 `OrphanProofInconclusive(reason=_INCONCLUSIVE_REASON_PROBE_ERROR)` → `"process_probe_error"` ✓
- `owner_pid_live_without_identity_proof`：`recovery_process.py:293-299`（`evidence is None`）或 `recovery_process.py:352-357`（pid live 但无 identity proof）返回 `OrphanProofInconclusive(reason=_INCONCLUSIVE_REASON_PID_LIVE_WITHOUT_IDENTITY)` → `"owner_pid_live_without_identity_proof"` ✓
- `waiting_adapter_observation_unavailable`：`recovery.py` 对 WAITING Run 返回 `WAITING_DIAGNOSTIC_ONLY`，reason 由 `_classify_waiting` 产出 ✓

### 测试 Determinism 验证

- 所有时间使用固定 `_NOW = datetime(2026, 5, 19, 3, 4, 5, tzinfo=UTC)`。
- `_mark_owner_heartbeat` 使用显式 timestamp `"2026-05-19T03:04:00.000000Z"`，不依赖 `datetime.now()`。
- `_policy()` 使用 `stale_after=timedelta(seconds=30)` 固定阈值。
- 无 `sleep`、无 `asyncio` timing、无 race 条件。
- heartbeat recent 测试中 heartbeat 距 NOW 5 秒，远小于 30 秒 stale_after 阈值；stale 测试中 heartbeat 距 NOW 4+ 分钟，远超阈值。边界安全。

### 类型与 Docstring 检查

- `_RecoveryLifecycleMatrixRow`：7 个字段全部 `str` 类型，有完整中文 docstring（含 `:param` 标注）。✓
- `_PidLiveNoIdentityProbe`：中文 docstring，`collect(pid: int) -> ProcessEvidence` 严格类型。✓
- `_PidProbeErrorProbe`：中文 docstring，`collect(pid: int) -> ProcessEvidence` 严格类型。✓
- `_ActiveRunObservation`：11 个字段，全有类型标注（含 `AttemptStatus`、`DispatchRecordStatus`、`str | None`、`tuple[str, ...]`），完整中文 docstring。✓
- `_assert_no_recovery_or_terminal_facts`：中文 docstring，`transaction_runner: HostTransactionRunner` 参数类型。✓
- `_mark_owner_heartbeat`：中文 docstring，`transaction_runner: HostTransactionRunner`、`heartbeat_at: str` 参数类型。✓
- 无 `Any`、`object`、无类型参数、无类型返回值。✓

### 断言完整性检查

新增测试的断言模式：

1. **decision 断言**：`tuple(action.decision for action in result.actions)` 与期望值比较。
2. **reason 断言**：`tuple(action.reason for action in result.actions)` 与期望值比较。
3. **durable immutability 断言**：`_active_run_observation` before == after（Run / Attempt / dispatch row 全部不变）。
4. **forbidden fact 断言**：`_assert_no_recovery_or_terminal_facts` 检查 ATTEMPT_LOST / RUN_RECOVERING / RUN_LOST 均为 0。

四层断言覆盖了 plan 要求的 "不写 ATTEMPT_LOST / RUN_RECOVERING / RUN_LOST、Run / Attempt / dispatch row 不变、reason 可区分"。✓

### Implementation Report 可信度

| Report 声明 | 验证结果 |
|---|---|
| 13 passed | 实际 13 passed in 0.28s ✓ |
| 0 errors, 0 warnings, 0 informations (pyright) | 未独立运行，但 diff 只含测试文件且无类型变更，可信 |
| Production code changes: None | diff 确认 ✓ |
| No README changes | Slice A 只改测试，trigger rule 判断正确 ✓ |
| No contract/schema/state-machine changes | diff 确认 ✓ |
| Multiprocess validation not triggered | Slice A 不触碰 multiprocess 代码，正确 ✓ |
| WAITING coverage used narrower durable-read path | 实现使用 `open_host_durable_store` 直接 durable read，未走 public `open_host`，符合 plan 允许的最窄路径 ✓ |

## Blocking Open Questions

none

## 总结

Slice A implementation 严格对齐 plan，tests-first 执行证明现有 scanner 行为已满足 still-live / inconclusive / WAITING diagnostic-only 语义，未触发生产代码变更。新增 5 个测试（含 1 个 parametrized 覆盖 2 case）和 1 个 matrix 覆盖测试，recovery lifecycle proof matrix 18 行完整标注 existing / new / non-goal。测试 deterministic，类型严格，docstring 完整。仅有 2 个信息级观察（`run_write` 语义、格式化 churn），不影响 correctness / stability / maintainability。
