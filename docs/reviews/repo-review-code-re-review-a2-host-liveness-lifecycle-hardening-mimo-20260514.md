# Code Re-Review

## Scope

- Mode: current changes (scoped A2 re-review after accepted fixes)
- Branch: `fix/host-phase-4`
- Base: `main`
- Output file: `docs/reviews/repo-review-code-re-review-a2-host-liveness-lifecycle-hardening-mimo-20260514.md`
- Included scope: `dayu/host/durable/errors.py`, `dayu/host/durable/liveness.py`, `tests/host/test_host_instance_liveness.py`
- Excluded scope: recovery, lease, fencing, takeover, Phase 11 dispatch, crash classifier
- Parallel review coverage: 无
- Source review artifacts:
  - `docs/reviews/repo-review-code-review-a2-host-liveness-lifecycle-hardening-mimo-20260514.md` (Mimo initial review)
  - `docs/reviews/repo-review-code-review-a2-host-liveness-lifecycle-hardening-glm-20260514.md` (GLM initial review)

## Verification Checklist

### 1. heartbeat uses RUNNING-only source and no longer changes STOPPING to RUNNING

**通过。**

- `_HEARTBEAT_SOURCE_STATUSES = (HostInstanceStatus.RUNNING,)` — 仅包含 RUNNING（第 46 行）
- `heartbeat_current_instance()` 使用 `_HEARTBEAT_SOURCE_STATUSES`（第 274、281、295 行）
- 旧 `_RUNNING_SOURCE_STATUSES` 已完全替换为 `_REGISTER_RUNNING_SOURCE_STATUSES`，无残留引用
- 新增测试 `test_stopping_instance_heartbeat_does_not_revert_to_running`（第 304-336 行）：注册 → mark_stopping → heartbeat 断言 `HostInstanceLifecycleConflictError`，且 row 状态保持 STOPPING

### 2. explicit register still preserves STOPPING to RUNNING

**通过。**

- `_REGISTER_RUNNING_SOURCE_STATUSES = (HostInstanceStatus.RUNNING, HostInstanceStatus.STOPPING)` — 包含 STOPPING（第 42-45 行）
- `register_current_instance()` 使用 `_REGISTER_RUNNING_SOURCE_STATUSES`（第 225、232、246 行）
- 已有测试 `test_repeated_register_same_identity_refreshes_heartbeat_and_status`（第 194-245 行）覆盖 STOPPING → RUNNING 路径
- register 路径额外增加了终态 pre-check（第 221-224 行）：`if existing.status in _TERMINAL_STATUSES: raise HostInstanceLifecycleConflictError`，在进入 UPDATE 前即拦截终态 row

### 3. terminal STOPPED/CRASHED_SUSPECTED rejects mark_current_instance_stopped

**通过。**

- `test_terminal_instance_does_not_revert_to_running_or_stopping`（第 248-301 行）现在对 `mark_current_instance_stopped` 也断言 `HostInstanceLifecycleConflictError`（第 288-293 行）
- 覆盖 STOPPED 和 CRASHED_SUSPECTED 两种终态
- 代码层面 `_STOPPED_SOURCE_STATUSES = (RUNNING, STOPPING)` 不包含终态，SQL UPDATE 零命中后 `_raise_liveness_update_conflict` 分类为 `HostInstanceLifecycleConflictError`

### 4. register, heartbeat, and status mark rowcount-zero paths all have focused tests

**通过。**

- heartbeat rowcount-zero: `test_heartbeat_rowcount_zero_after_identity_precheck_raises_conflict`（第 442-471 行）
- status mark rowcount-zero: `test_status_mark_rowcount_zero_after_identity_precheck_raises_conflict`（第 474-503 行）
- register rowcount-zero: `test_register_rowcount_zero_after_identity_precheck_raises_conflict`（第 506-535 行）
- 三个测试均使用 `_IdentityDriftTransaction` 在 identity precheck 后制造 token 漂移，断言 `HostInstanceIdentityConflictError`

### 5. tests pass, pyright passes

**通过。**

- `pytest tests/host/test_host_instance_liveness.py -q` → 16 passed（从 14 增加到 16）
- `pyright dayu/host/durable/liveness.py dayu/host/durable/errors.py tests/host/test_host_instance_liveness.py` → 0 errors, 0 warnings, 0 informations

### 6. no scope creep beyond A2

**通过。**

- 新增代码仅涉及：source status 常量拆分、终态 pre-check、rowcount 校验、结构化异常分类、对应测试
- 未引入 recovery、lease、fencing、takeover、dispatch owner 或 Phase 11 扫描逻辑
- `HostInstanceLifecycleConflictError` 定义在 `errors.py` 中，符合既有错误分类架构
- `_TERMINAL_STATUSES` 仅被 register 路径的终态 pre-check 使用，不泄漏到外部

## Resolved Findings from Initial Reviews

| Source Finding | Status | Evidence |
|---|---|---|
| Mimo-01: `mark_current_instance_stopped` 终态缺测试 | **已修复** | 第 288-293 行新增断言 |
| Mimo-02: `_raise_liveness_update_conflict` fallback 防御性分支 | **无需修复** | 低风险防御性分支，行为正确 |
| GLM-01: STOPPING 可被 heartbeat 静默回退为 RUNNING | **已修复** | `_HEARTBEAT_SOURCE_STATUSES` 仅含 RUNNING；新增 `test_stopping_instance_heartbeat_does_not_revert_to_running` |
| GLM-02: `mark_current_instance_stopped` 终态缺测试 | **已修复** | 同 Mimo-01 |
| GLM-03: register identity precheck 后 rowcount 零测试缺失 | **已修复** | 新增 `test_register_rowcount_zero_after_identity_precheck_raises_conflict` |

## Open Questions

- 无。

## Residual Risk

- `_IdentityDriftTransaction` 测试 wrapper 未调用 `super().__init__()`，依赖 Python 对未初始化父类属性的惰性访问。当前可行因为 `execute` 和 `fetchone` 均被 override，但若 `HostTransaction` 未来新增方法被 liveness 代码调用，此 wrapper 会暴露未初始化状态。风险极低，仅记录。
- `STOPPED → STOPPED` 幂等性：当前 `mark_current_instance_stopped()` 对已 STOPPED 的 row 抛出 `HostInstanceLifecycleConflictError`，而非幂等返回已有 row。若 Host shutdown 流程可能重复调用 mark_stopped（signal handler + cleanup），调用方需处理此异常。这是 Phase 11 前的设计决策，不属于 A2 scope。

## Verdict

**通过。** A2 实现与 adjudication scope 完全一致，两份初始 review 的全部 accepted findings 均已修复或确认无需修复：

1. 终态 STOPPED/CRASHED_SUSPECTED 不可回退为 RUNNING 或 STOPPING ✅
2. register/heartbeat/status mark 的 identity precheck 与 UPDATE rowcount 零命中分类为结构化 identity/lifecycle/not-registered 错误 ✅
3. mark_current_instance_stopping 仅允许 RUNNING → STOPPING ✅
4. mark_current_instance_stopped 保持 RUNNING → STOPPED 与 STOPPING → STOPPED ✅
5. 缺失 row 的 status mark 仍返回 None ✅
6. heartbeat 不再将 STOPPING 静默回退为 RUNNING ✅
7. register 保留 STOPPING → RUNNING 的显式重注册语义 ✅

测试从 14 项增加到 16 项，pyright 无报错，无 scope creep。可合入。
