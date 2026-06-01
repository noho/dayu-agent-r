# WU-LIFE-01 + WU-LIFE-02 Slice A Code Review

日期：2026-06-01
Reviewer：AgentDS
Controller：AgentController
Gate：code review slice A
Review target：`tests/host/test_recovery_scan.py` 未提交 diff + implementation report
Design source：`docs/host/design.md`
Plan artifact：`docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md`
Implementation report：`docs/reviews/wu-life-01-02-implementation-sliceA-codex-20260601.md`

## Review Summary

- **Conclusion**: pass
- **Total findings**: 4 (0 blocking, 1 medium, 3 low)
- **Blocking open questions**: none

Slice A 严格限定在 `tests/host/test_recovery_scan.py`，未修改任何生产代码，未混入 Slice B 内容。新增的 recovery lifecycle proof matrix 覆盖 plan 要求的全部 Slice A 场景，still-live / inconclusive / WAITING 测试基于直接 durable 证据、确定性 fake probe 和固定时间戳，不依赖 sleep/race。新增 dataclass 与 helper 具备中文 docstring 和严格类型，无 `Any`/`object`/untyped 签名。Production code 未改动，scanner 现有行为已满足 still-live / inconclusive proof 不写 recovery/terminal facts 的要求。

存在中度格式化 churn 和三个低严重度分类/命名问题，但不影响 correctness 或 stability。

---

## Findings

### A1-未修复-Medium-存在过度机械格式化 churn

**证据**：diff 中约 30 行变更是纯粹的代码格式化，无语义变化：

- 函数签名从多行收为单行：`_seed_running_dispatching_run` (L768)、`_seed_unstarted_run` (L841)、`_create_accepted_input` (L927)、`_create_queued_input` (L953)、`_create_running_input` (L978)、`_append_recovery_started_event` (L1235)、`_mark_run_status` (L1235)、`_event_types` (L1336)、`_event_type_count` (L1336)、`_event_payload_by_type` (L1336)。
- 多处 assert 语句从多行收为单行：`StartupRecoveryDecision.RUN_RECOVERING` (L617)、`WAITING_DIAGNOSTIC_ONLY` (L639)、`RUN_LOST` (L663)、`ACCEPTED_WAKE` (L680)、`QUEUE_PROMOTION_CHECK` (L684)、`NOT_FOUND` (L708)、`_REASON_CANCEL_IN_FLIGHT_ATTEMPT_LOST` (L663) 等。
- `input_event = EventLogStore().append_event(...)` 改为 `input_event = (EventLogStore().append_event(...)).row` 链式调用风格（L785、L860）。
- `store.transaction_runner.run_write(verify)` 从两行收为一行（L710）。

这些变更与 Slice A 的新增功能无关，纯属机械 reflow。它们增加了 diff 噪声，降低了 review 可聚焦性。

**影响**：不产生 bug，但混淆了语义变更与格式变更的边界，降低 diff 可读性，且部分单行签名超过 100 字符（如 `_create_running_input` 参数列表），对可维护性有轻微负面影响。

**建议修复**：回退格式化变更，只保留语义变更。若团队有统一 formatter（如 black/ruff），应在独立 commit 中应用，不与 feature work 混合。

---

### A2-未修复-Low-WAITING matrix row coverage 分类过宽

**证据**：plan 测试矩阵中 `WAITING` startup scan 分两行：
- Row 173: low-level → existing coverage in `tests/host/test_recovery_scan.py`
- Row 174: public/read semantics → new coverage

实现中只创建了一个 matrix row `waiting-diagnostic-only`，分类为 `_COVERAGE_NEW`。但实际上 `test_scan_waiting_uses_diagnostic_only_fallback` 是已有测试（本次只增强了 reason 断言和 `_assert_no_recovery_or_terminal_facts`），核心 diagnostic-only 行为在本次改动前已被覆盖。将整行标为 NEW 掩盖了已有覆盖基础。

**影响**：matrix 的 coverage classification 精度不足，但不影响测试正确性或 plan 验收。Implementation report 已通过文字描述区分了增强部分。

**建议修复**：拆分为两行（`waiting-diagnostic-only-low-level` → existing，`waiting-diagnostic-only-public-read` → new），或保持一行但标注为 `coverage_strengthened` 并注明现有测试增强 + 新增 durable-read 测试。

---

### A3-未修复-Low-`running-missing-current-attempt-or-dispatch` 标注为 existing 但无直接测试

**证据**：matrix row `running-missing-current-attempt-or-dispatch` 分类为 `_COVERAGE_EXISTING`。扫描 `tests/host/test_recovery_scan.py` 全部现有测试：

- `test_scan_skips_non_terminal_run_when_session_row_is_missing` 覆盖 Session missing → NOT_FOUND 路径
- 无测试直接构造 RUNNING Run + 缺失 current_attempt_id 或 dispatch record 的场景，并断言 `ORPHAN_INCONCLUSIVE` + reason `missing_current_attempt_or_dispatch`

该代码路径存在于 `recovery.py:_classify_active_or_cancelling()` L360-365，但未被现有 scanner 级测试直接覆盖。classifier 级 (`test_recovery_orphan_classifier.py`) 可能覆盖了部分子路径，但 scanner 级集成断言缺失。

**影响**：coverage classification 不准确，但 plan 对该行的要求是 "existing or new if matrix finds no direct test"，即允许标注为 existing 并在发现无测试时补充。当前实现未补充该测试，但 plan 也未强制要求。

**建议修复**：将 coverage 改为 `_COVERAGE_NEW` 并加入 Slice A 待补列表，或在 Slice B/deepreview 阶段补一个轻量 scanner 集成测试。

---

### A4-未修复-Low-`test_scan_waiting_public_visible_durable_state_remains_diagnostic_only` 名称暗示 public API 但实现为 durable read

**证据**：测试名称含 `public_visible`，但实现通过 `open_host_durable_store` + `_count_rows` + `_run_status` 走 durable-level read，不经过 Host public API（如 `open_host()` / `Host.watch()`）。Plan 明确允许此路径："优先放在 `tests/host/test_recovery_scan.py` 做 durable read 证明"，因此测试方式符合 plan 授权。

**影响**：测试名可能误导后续维护者以为该测试覆盖了 public API 路径。不产生功能缺陷。

**建议修复**：测试名改为 `test_scan_waiting_durable_state_remains_diagnostic_only`（去掉 `public_visible`，保留 `durable`），或在 docstring 中明确说明 "通过 durable read 而非 public API 证明"。

---

## Plan Alignment Check

逐项对照 plan Slice A requirements：

| Plan Requirement | Status | Evidence |
|---|---|---|
| Recovery lifecycle matrix 常量 | ✓ | `_RECOVERY_LIFECYCLE_PROOF_MATRIX` 含 18 行，覆盖全部 Slice A 场景 |
| scanner still-live integration test | ✓ | `test_scan_running_owner_heartbeat_recent_does_not_mutate_durable_rows` |
| scanner inconclusive integration test | ✓ | 参数化 `test_scan_running_inconclusive_owner_proof_does_not_mutate_durable_rows` (process probe error + pid live no identity) |
| WAITING diagnostic-only 用户可见语义 | ✓ | 增强 `test_scan_waiting_uses_diagnostic_only_fallback` + 新增 `test_scan_waiting_public_visible_durable_state_remains_diagnostic_only` |
| RR-DUR-04 proof matrix row | ✓ | `rr-dur-04-short-transaction-durable-truth` row，标注 NEW，不触发 production rewrite |
| 不新增 production recovery API | ✓ | 无生产代码变更 |
| 不改变 WAITING/Run/Attempt 状态机 | ✓ | 无生产代码变更 |
| 不实现 remote takeover/lease/fencing | ✓ | 无生产代码变更 |
| 不把 stress 纳入默认 validation | ✓ | stress row 标注 non-goal |
| Matrix 每个 row 标注 coverage | ✓ | 全部 18 行均有 existing/new/non-goal 标注（见 A2、A3 的精度问题） |
| 新增测试证明不写 ATTEMPT_LOST/RUN_RECOVERING/RUN_LOST | ✓ | `_assert_no_recovery_or_terminal_facts` 被所有 still-live/inconclusive/WAITING 测试调用 |
| RR-DUR-04 未误扩为 production rewrite | ✓ | 无生产代码变更 |
| pyright 通过 | ✓ per implementation report |

## Contract / Schema / State-Machine Boundary Check

| Boundary | Status |
|---|---|
| Durable schema | 未变更 ✓ |
| EventLog event type | 未变更 ✓ |
| Host public API | 未变更 ✓ |
| Run / Attempt state machine | 未变更 ✓ |
| WAITING durable semantics | 未变更 ✓ |
| Close terminal fact boundary | 未变更（Slice A 不涉及 close）✓ |

## Design Source Alignment

对照 `docs/host/design.md` 第 27 节：

- 新增测试确认 `OWNER_STILL_LIVE` 不写 `ATTEMPT_LOST` / `RUN_RECOVERING` / `RUN_LOST`，对齐 design L2948 "owner heartbeat stale 但 positive orphan proof 不成立时，只能追加或投递 suspect diagnostic" ✓
- 新增测试确认 `ORPHAN_INCONCLUSIVE` 不写 recovery/terminal facts，对齐 design L2973 "任一条件缺失都只能得到 suspect / inconclusive 结论，不得推进 recovery" ✓
- WAITING 测试确认不创建 Attempt、不改变状态，对齐 design L2935 "不创建 Attempt；只恢复 wait adapter observation" ✓
- `pid live without identity proof` 返回 `ORPHAN_INCONCLUSIVE` 的分类行为与 design L2964 "heartbeat_at 单独不构成 orphan proof" 一致；implementation report 正确记录了此行为与 plan 矩阵 row 177 的差异 ✓

## Implementation Report Accuracy

| Report Claim | Verification |
|---|---|
| "No production code changes" | 确认：diff 仅涉及 `tests/host/test_recovery_scan.py` ✓ |
| "13 passed" (recovery_scan only) | 可验证：8 existing + 5 new test functions = 13 items（含 2 parametrized cases）✓ |
| "pyright 0 errors, 0 warnings, 0 informations" | 未独立运行，接受 report 声明 |
| "README/doc sync: not needed" | 确认：无生产代码、公共 API、测试分层/约定变更，触发规则不要求更新 ✓ |
| "Contract/schema/state-machine/public-interface changes: none" | 确认 ✓ |
| "pid live without identity proof is classifier-defined as ORPHAN_INCONCLUSIVE" | 确认：`recovery_process.py:_classify_stale_owner()` L352-358 返回 `OrphanProofInconclusive(reason="owner_pid_live_without_identity_proof")` ✓ |

## Type Quality

| Item | Check |
|---|---|
| `_RecoveryLifecycleMatrixRow` | frozen, slots=True, 全部字段有类型标注，中文 docstring ✓ |
| `_PidLiveNoIdentityProbe` | frozen, slots=True, `collect()` 返回 `ProcessEvidence` ✓ |
| `_PidProbeErrorProbe` | frozen, slots=True, `collect()` 返回 `ProcessEvidence` ✓ |
| `_ActiveRunObservation` | frozen, slots=True, 全部字段有类型标注，`event_types: tuple[str, ...]` ✓ |
| `_mark_owner_heartbeat` | 参数有类型标注，中文 docstring ✓ |
| `_active_run_observation` | 返回类型 `_ActiveRunObservation`，中文 docstring ✓ |
| `_assert_no_recovery_or_terminal_facts` | 中文 docstring ✓ |
| 无 `Any`/`object`/untyped 签名 | 确认 ✓ |

## Determinism

- 所有新增测试使用 fake probe（`_PidMissingProbe`、`_PidLiveNoIdentityProbe`、`_PidProbeErrorProbe`），不调用真实 `os.kill(pid, 0)` ✓
- 使用固定时间戳 `_NOW = datetime(2026, 5, 19, 3, 4, 5, tzinfo=UTC)` 与固定 `StartupRecoveryPolicy` ✓
- 无 `asyncio.sleep`、`time.sleep` 或 race 依赖 ✓
- 所有断言基于 durable read 回来的 SQLite 行，不依赖 projection/read-model ✓

## Residual Risks

- RR-DUR-04 proof matrix row 是文档级映射，未添加机械化的交易时长检测 instrumentation；implementation report 将其列为 residual risk 是合适的。
- `running-missing-current-attempt-or-dispatch` 的 scanner 级集成测试缺失（见 A3），当前依赖 classifier 级测试间接覆盖。

## Blocking Open Questions

none
