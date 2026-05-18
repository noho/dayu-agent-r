# P10.5 Slice 3 Follow-up Re-Review Artifact

## Gate

P10.5 Slice 3 follow-up re-review。

## Review Target

Controller adjudication accepted follow-up fix（F1 测试 helper 迁移 + F2 fix artifact 更新）的实现是否完成且未引入新 blocker。

## Review Inputs

- Controller re-review adjudication: `docs/reviews/phase10-5-slice3-rereview-controller-adjudication-20260518.md`
- Previous re-review MiMo: `docs/reviews/phase10-5-slice3-rereview-mimo-20260518.md`
- Previous re-review DS: `docs/reviews/phase10-5-slice3-rereview-ds-20260518.md`
- Updated fix artifact: `docs/reviews/phase10-5-slice3-fix-codex-20260518.md`
- 总控文档: `docs/host/implementation-control.md`

## Follow-up Fix Verification

### F1: 迁移受影响低层测试 helper 到新的 admission baseline 边界

**裁决**: accepted，完成。

#### 1.1 test_admission_queue.py `_service()` helper 注入 OrdinaryRunExecutionBaseline

**代码证据** (`tests/host/test_admission_queue.py:1253-1277`):

```python
def _service(...) -> HostAdmissionService:
    return create_host_admission_service(
        transaction_runner,
        clock=_FixedClock(),
        id_factory=_SequentialIdFactory(label),
        wakeup_port=spy if spy is not None else _WakeupSpy(),
        projection_catchup_port=projection_catchup,
        ordinary_run_baseline=_ordinary_run_baseline(),
        tooling_options=None,
    )
```

新 helper `_ordinary_run_baseline()` (lines 1280-1311) 构造合法的 `OrdinaryRunExecutionBaseline`，包含:
- `RunnerSpec(provider="test", model="admission-baseline-model", ...)`
- `RunnerCallOptions(temperature=None, max_tokens=None, top_p=None, stream=False)`
- `AgentPolicy(max_iterations=1, continuation_max_attempts=0, allow_tool_calls=False, ...)`

`tooling_options=None` 保持无业务工具语义，与原始 helper 行为等价。

**原 queue/promotion/cancel/closeout 断言语义保持不变**：

| 测试 | 原断言 | 状态 |
| --- | --- | --- |
| `test_start_run_on_open_session_creates_accepted_run_and_governance_wakeup` | ACCEPTED Run + promotion wakeup + 无 Attempt/dispatch | 不变 |
| `test_followup_queue_with_active_creates_queued_run_with_supplied_target` | QUEUED + 显式 target + active promotion skip | 不变 |
| `test_followup_queue_without_active_creates_accepted_run` | ACCEPTED follow-up + 无 Attempt | 不变 |
| `test_closed_session_rejects_start_and_followup_without_event_side_effects` | INVALID_STATE + 无 side effect | 不变 |
| `test_duplicate_idempotency_returns_same_run_without_extra_events` | queued + direct 幂等 replay + 无额外事件 | 不变 |
| `test_followup_idempotency_excludes_later_resolved_execution_target` | 同 key 重试不改写 target | 不变 |
| `test_same_idempotency_key_with_changed_input_digest_conflicts` | IDEMPOTENCY_CONFLICT + 无额外事件 | 不变 |
| `test_reject_and_attach_active_conflict_with_accepted_active` | CONFLICT ×2 + 无 side effect | 不变 |
| `test_unknown_queue_policy_raises_value_error_without_transaction` | ValueError + 无事务副作用 | 不变 |
| `test_promotion_skips_with_active_then_promotes_earliest_queued_run` | active skip → 释放后 FIFO promotion + dispatch wakeup | 不变 |
| `test_cancel_queued_run_is_idempotent_and_creates_no_attempt` | CANCELLED + 幂等 + 无 Attempt | 不变 |
| `test_cancel_predispatch_starting_promotes_exactly_one_queued_run` | cancel 释放 slot + 仅 promotion 一条 queue | 不变 |
| `test_cancel_predispatch_starting_promotion_survives_queue_wakeup_failure` | wakeup 失败不掩盖 promotion 结果 | 不变 |
| `test_promote_next_queued_run_returns_result_when_dispatch_wakeup_fails` | dispatch wakeup 失败不掩盖 promotion | 不变 |
| `test_terminal_closeout_promotes_exactly_one_queued_run_after_commit` | closeout 后 promotion + 无 dispatch | 不变 |
| `test_terminal_closeout_survives_after_commit_projection_catchup_failure` | catchup 失败不影响 closeout/promotion | 不变 |
| `test_terminal_closeout_promotion_survives_queue_wakeup_failure` | wakeup 失败不掩盖 promotion | 不变 |
| `test_cancel_terminal_run_returns_current_terminal_without_new_facts` | 终态 cancel 返回当前态 + 无新 fact | 不变 |
| `test_cancel_attempt_running_enters_cancelling_with_cancel_facts` | CANCELLING + cancel facts 追加 | 不变 |
| `test_rollback_before_cancel_commit_does_not_wake_or_promote` | rollback 无 wakeup/promotion | 不变 |
| `test_concurrent_promotion_attempts_promote_at_most_one_run` | 两线程竞争至多一条 promotion | 不变 |
| `test_start_run_survives_after_commit_projection_catchup_failure` | catchup 失败不掩盖命令结果 | 不变 |
| `test_start_run_concrete_memory_catchup_projects_user_input` | memory catch-up 投影用户输入 | 不变 |

全部 23 个测试（含 20 个 admission queue 原测试 + 2 个投影 read model 原测试 + 1 个随 fix 已迁移的 memory catchup 测试）的断言语义未变。`_service()` helper 是唯一注入点。

**结论**: COMPLETE。

#### 1.2 test_projection_read_model.py baseline-aware test handle

**代码证据** (`tests/host/test_projection_read_model.py:105-151`):

新增私有 helper `_host_with_ordinary_baseline(tmp_path)`:
- 手工装配 `HostDurableStoreOptions` → `open_host_durable_store()`
- 手工构造 baseline-aware `HostAdmissionService`（注入 `_ordinary_run_baseline()` + `tooling_options=None`）
- 手工装配 `ActiveWorkerRegistry()`
- 手工构造 `HostCommandHandle`
- 异常安全：assembly 失败时关闭 durable store

**使用点审查**:

| 测试 | 使用 helper | 原因 |
| --- | --- | --- |
| `test_user_input_timeline_preserves_repeated_text_and_null_fallback` | `_host_with_ordinary_baseline` | 调用 `submit_followup` 并做 read-model 断言 |
| `test_cancelled_input_and_later_input_remain_separate_items` | `_host_with_ordinary_baseline` | 调用 `cancel_run` + `submit_followup` 并做 read-model 断言 |
| 其余 11 个测试 | `create_host_command_handle(_options(tmp_path))` | 仅做 projection/repair/validation，无需 baseline |

**Durable resource 关闭验证**:
- `test_user_input_timeline_preserves_repeated_text_and_null_fallback`: `try: ... finally: host.close()` (line 812)
- `test_cancelled_input_and_later_input_remain_separate_items`: `try: ... finally: host.close()` (line 882)

`HostCommandHandle.close()` 关闭内部持有的 durable store。

**生产 `create_host_command_handle()` 未修改**: Grep 确认 `command.py` 中 `create_host_command_handle` 函数签名、逻辑、返回类型与 Slice 3 implementation 一致，未变更。`_host_with_ordinary_baseline` 仅作为测试内私有 helper，不改变生产入口或 public API。

**结论**: COMPLETE。baseline-aware handle 仅用于正常 submit_followup read-model 测试，durable resource 正确关闭，未改变生产 create_host_command_handle 或 public API。

### F2: 修正 fix artifact residual risk

**裁决**: accepted，完成。

Updated fix artifact (`docs/reviews/phase10-5-slice3-fix-codex-20260518.md`) Follow-up Fix 段已记录:
1. `test_admission_queue.py` `_service()` helper 迁移到 ordinary baseline 边界
2. `test_projection_read_model.py` 新增 `_host_with_ordinary_baseline()` helper
3. `test_effective_execution_config.py::test_submit_followup_without_ordinary_baseline_fails_before_dispatch` 保留

Residual Risk 段已更新: "既有 admission queue / projection read-model 正常 follow-up 测试 helper 已迁移到 ordinary baseline 边界；无 baseline misuse 仍由 dedicated fail-early 测试覆盖。"

**结论**: COMPLETE。

## Point-by-Point Verification

### P1: test_admission_queue.py helper 正确注入 OrdinaryRunExecutionBaseline，保持原 queue/promotion/cancel/closeout 断言语义

**Pass**。`_service()` helper 是唯一注入点，`_ordinary_run_baseline()` 构造完整合法的 baseline。全部 20 个原测试的断言语义一字未改，仅 helper 构造部分新增两个参数。

### P2: test_projection_read_model.py baseline-aware handle 仅用于正常 submit_followup read-model 测试，关闭 durable resource，未改变生产 create_host_command_handle 或 public API

**Pass**。`_host_with_ordinary_baseline()` 仅用于 2 个需要 submit_followup 的 read-model 测试。其余 11 个测试继续使用原有 `create_host_command_handle`（无需 baseline）。durable resource 在 caller 的 finally 块中关闭。生产代码 `create_host_command_handle` 零变更。

### P3: 无 baseline misuse contract 仍由 test_effective_execution_config.py 覆盖

**Pass**。`test_submit_followup_without_ordinary_baseline_fails_before_dispatch` (`test_effective_execution_config.py:323-345`) 保留，断言:
- 低层 `create_host_command_handle` 路径无 baseline 时 `submit_followup` 抛出 `HostApiError`
- 错误码 `INVALID_STATE`
- 错误消息包含 `"ordinary Run baseline"`
- 失败发生在 dispatch 之前（通过 command handle close 前无 accepted 事件隐式验证）

### P4: 47-test 集合和 pyright 必跑验证通过

```
pytest tests/host/test_admission_queue.py tests/host/test_projection_read_model.py \
  tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py \
  tests/host/test_effective_execution_config.py -q
→ 47 passed in 0.52s

python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings, 0 informations
```

### P5: 是否引入新的 correctness/stability/maintainability blocker

**Pass** — 未发现新 blocker。详细检查:

- **Correctness**: 测试 helper 仅注入 baseline 构造参数，不改变 admission service 行为逻辑。`_ordinary_run_baseline()` 使用独立、与生产基线不冲突的测试值 (`provider="test"`, `model="admission-baseline-model"` / `"projection-baseline-model"`)。`tooling_options=None` 保持原测试无业务工具语义。

- **Stability**: `_host_with_ordinary_baseline()` 手工装配 HostCommandHandle（durable store + admission service + registry），该模式与项目既有测试辅助函数风格一致。assembly 失败时关闭 durable store 防止资源泄漏。caller 通过 finally 确保 handle 关闭。

- **Maintainability**: 两个测试文件分别定义各自的 `_ordinary_run_baseline()`，无共享依赖。这是故意选择——避免测试文件间耦合。如果未来多个测试文件需要相同 baseline，可以抽取共享 fixture，但不影响当前维护性。

- **无测试删除**: 原有 fail-early 测试 `test_submit_followup_without_ordinary_baseline_fails_before_dispatch` 保留且未被改动。

- **无生产代码修改**: `dayu/host/` 下所有模块零变更。仅测试文件和 fix artifact 文档有修改。

## Test Coverage Summary

| 测试文件 | 测试数 | 备注 |
| --- | --- | --- |
| `test_admission_queue.py` | 20 | helper 已迁移 baseline，断言语义不变 |
| `test_projection_read_model.py` | 13 | 2 个使用 baseline-aware handle，其余不变 |
| `test_submit_followup_public_contract.py` | 3 | Slice 3 原有 |
| `test_per_run_tool_selection.py` | 4 | Slice 3 原有 |
| `test_effective_execution_config.py` | 7 | 含 F3 fail-early 测试 |
| **Total** | **47** | |

## Verdict

**PASS** — blocking count = 0。

### Summary

| 项目 | 状态 |
| --- | --- |
| F1: admission queue helper 注入 baseline | 完成，23 个测试原断言语义不变 |
| F1: projection read model baseline handle | 完成，仅用于 submit_followup read-model 路径，资源正确关闭 |
| F2: fix artifact residual risk 更新 | 完成 |
| P1: admission queue 断言语义 | 不变 |
| P2: baseline handle scope + 资源管理 | 正确 |
| P3: 无 baseline misuse contract 覆盖 | 保留，未删除 |
| P4: 47-test 集合 | 47 passed |
| P4: pyright | 0 errors |
| P5: 新 blocker | 0 |

### Previous re-review N1/N2 状态

- **N1** (16 个既有测试因 baseline=None 失败): **已修复**。admission queue 20 个测试 + projection read model 2 个 submit_followup 测试现在注入 baseline。其余 projection read model 测试无需 baseline（不经过 submit_followup 路径）。
- **N2** (fix artifact residual risk 声明不完整): **已修复**。fix artifact Follow-up Fix 和 Residual Risk 段均已更新。

### 无新 non-blocking findings

## Artifact Path

`docs/reviews/phase10-5-slice3-followup-rereview-ds-20260518.md`
