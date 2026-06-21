# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f01-02-r1`
- Base: `2634f361` (Slice 2 checkpoint commit)
- Output file: `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-mimo.md`
- Included scope: Slice 2 implementation diff (uncommitted changes after checkpoint)
- Excluded scope: Slice 1 commit `e10f2e99`、`docs/host/issues-implementation-control.md` 仅作状态上下文
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- **Slice 3 Service wiring 风险**: `build_fins_wait_activation_registry(...)` 当前按 workspace root 构造 runtime；production 中需确保 awaiting tool runtime、poll adapter runtime 与 activation adapter runtime 的 process-local observation registry 装配一致。此项已在实现文档中记录。
- **prepared-but-unaccepted observation 生命周期**: 本 Slice 未引入 durable prepared job 状态；prepared observation 在 runtime teardown 后自然丢弃。如果 Host awaiting accept 在进程重启前未完成，observation 会丢失，wait poll adapter 会将其映射为 LOST。此项符合 Slice 2 设计意图。
- **executor.submit 线程安全性**: `activate_observation` 在锁外调用 `self.executor.submit`，依赖 executor 实现的线程安全性。当前 `_HoldingExecutor` 和 `_FailingSubmitExecutor` 测试替身未验证并发安全，但 `FinsIngestionExecutor` 协议预期线程安全。此项属 executor 实现契约，非本 Slice 新增风险。

## Review Details

### 验证结果

1. **download / preprocess / upload callable 是否真正 prepare-only，不 submit executor**
   - ✅ 已验证。`download_tools.py:86`、`preprocess_tools.py:85`、`upload_tools.py:100` 均从 `start_observed_*` 改为 `prepare_observed_prepare`。
   - ✅ 测试 `test_awaiting_tool_callables_prepare_without_executor_submit` 验证三个 callable 返回 `ToolAwaitingOutcome` 且 `executor.submitted_job_ids == ()`。

2. **ToolAwaitingOutcome shape / opaque resume token 没变**
   - ✅ 已验证。测试使用 `_assert_resume_token_is_opaque` 断言 token 以 `finsobs_` 开头，不包含 `job`、`cursor`、`sidecar`、`storage`、`.dayu`、`/`、`\` 等片段。

3. **activate_observation 是否幂等，重复 activation 不 double-submit**
   - ✅ 已验证。`activate_observation` 在锁内检查 `record.submitted` 标志，已提交则直接返回。
   - ✅ 测试 `test_activate_observation_is_idempotent_for_same_handle` 验证重复 activation 后 `executor.operations` 只有 1 个。

4. **activate/cancel 是否通过同一个 observation lock 协调**
   - ✅ 已验证。`activate_observation`（`ingestion_runtime.py:2387`）和 `cancel_observation`（`ingestion_runtime.py:2337`）均使用 `self._observation_lock`。
   - ✅ 测试 `test_cancel_and_activate_share_observation_lock_without_timing_sleep` 使用 `_HookedObservationLock` 验证锁互斥。

5. **cancel-before-activate 是否不 submit 且可观察 terminal/cancelled**
   - ✅ 已验证。`cancel_observation` 在 `not record.submitted` 时设置 `status = CANCELLED`、`result = _observation_cancelled_result(...)`；`activate_observation` 检查 `record.status in _TERMINAL_OBSERVATION_STATUSES`，cancelled 状态直接返回。
   - ✅ 测试 `test_cancel_prepared_observation_prevents_later_activation_submit` 验证 cancelled 后 activation 不提交且 poll 可观察 CANCELLED。

6. **activation submit failure 是否把 observation terminal FAILED，不泄漏 raw provider/path/job/cursor/Host id 到 LLM-facing output**
   - ✅ 已验证。`activate_observation` 异常处理（`ingestion_runtime.py:2405-2414`）调用 `_mark_observation_failed` 将 record 标记为 FAILED，message 为 `"Observation activation failed."`。
   - ✅ `_safe_observation_message` 过滤路径、job、cursor 等片段。
   - ✅ 测试 `test_activation_submit_failure_is_observed_as_failed_by_wait_adapter` 验证 submit failure 后 wait adapter 返回 `ResolveWaitFailedOutcome`。

7. **unexpected activation exception 是否把 observation terminal FAILED，不永久 PENDING**
   - ✅ 已验证。`activate_observation` 异常处理捕获所有 `Exception`，调用 `_mark_observation_failed` 后 re-raise。
   - ✅ 测试 `test_unexpected_activation_exception_terminalizes_prepared_observation` 验证 `ValueError` 后 poll 返回 FAILED。

8. **FinsIngestionWaitActivationAdapter 是否只解析 existing opaque resume token 并调用 runtime.activate_observation；corrupt token 不误 activate**
   - ✅ 已验证。`wait_adapter.py:196` 调用 `parse_observation_handle_id_token`，corrupt token 抛出 `ValueError`，不调用 `runtime.activate_observation`。
   - ✅ 测试 `test_fins_wait_activation_adapter_rejects_corrupt_resume_token` 验证 corrupt token 抛出 `ValueError` 且 `runtime.activated_handles == ()`。

9. **是否无 Engine/Host/Service scope creep；Service wiring 留到 Slice 3 是否合理且风险已记录**
   - ✅ 已验证。实现只新增 Fins activation adapter 和 builder，未接入 Service / production Host assembly。
   - ✅ 实现文档已记录 Slice 3 assembly 风险。

10. **README 更新是否必要且最小**
    - ✅ 已验证。`dayu/fins/README.md` 更新同步了 `start_observed_*` → `prepare_observed_*` 的事实变化，补充了 activation 流程说明。

11. **测试是否真正覆盖 Slice 2 expected assertions；是否有测试被改弱、旧 failure path 是否只是被删除而没有 activation 端覆盖**
    - ✅ 已验证。旧测试从 `assert isinstance(outcome, ToolFailedOutcome)` 改为 `assert isinstance(outcome, ToolAwaitingOutcome)`，这是因为 executor 错误不再在 prepare 阶段触发。
    - ✅ activation 端已有独立测试覆盖 submit failure 和 unexpected exception。
    - ✅ `_assert_failed_outcome_hides_internal_terms` 被移除，因为 prepare 阶段不再有失败 outcome；`_assert_cancelled_outcome_hides_host_term` 保留用于取消 outcome。

12. **不引入过度设计，不引入 durable prepared status / lifecycle supervisor / public await contract**
    - ✅ 已验证。未发现 durable prepared status、lifecycle supervisor 或 public await contract。
