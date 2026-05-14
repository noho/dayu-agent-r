# Code Review (Re-review)

## Scope

- Mode: current changes (scoped A2 re-review after review-fix iteration)
- Branch: `fix/host-phase-4`
- Base: `main`
- Output file: `docs/reviews/repo-review-code-re-review-a2-host-liveness-lifecycle-hardening-glm-20260514.md`
- Included scope: `dayu/host/durable/errors.py`, `dayu/host/durable/liveness.py`, `tests/host/test_host_instance_liveness.py`, `docs/reviews/repo-review-fix-a2-host-liveness-lifecycle-hardening-20260514.md`
- Excluded scope: recovery, lease, fencing, takeover, Phase 11 dispatch, crash classifier
- Source review artifacts: `repo-review-code-review-a2-host-liveness-lifecycle-hardening-mimo-20260514.md`, `repo-review-code-review-a2-host-liveness-lifecycle-hardening-glm-20260514.md`
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Finding Resolution Verification

### GLM F01 (中): STOPPING 可被 heartbeat 静默回退为 RUNNING

- **修复方式**: 将原 `_RUNNING_SOURCE_STATUSES` 拆分为 `_REGISTER_RUNNING_SOURCE_STATUSES = (RUNNING, STOPPING)` 和 `_HEARTBEAT_SOURCE_STATUSES = (RUNNING,)`
- **验证**:
  - `liveness.py:46` `_HEARTBEAT_SOURCE_STATUSES = (HostInstanceStatus.RUNNING,)` — heartbeat 来源仅含 RUNNING
  - `liveness.py:274-295` heartbeat 使用 `_HEARTBEAT_SOURCE_STATUSES` — STOPPING row 的 heartbeat UPDATE 匹配不到，rowcount=0，走 `_raise_liveness_update_conflict` 抛出 `HostInstanceLifecycleConflictError`
  - `liveness.py:42-45` `_REGISTER_RUNNING_SOURCE_STATUSES = (RUNNING, STOPPING)` — register 保留 STOPPING -> RUNNING
  - `liveness.py:225-247` register 使用 `_REGISTER_RUNNING_SOURCE_STATUSES` — STOPPING row 的 register UPDATE 可匹配
  - `test_stopping_instance_heartbeat_does_not_revert_to_running` (304-336) — 断言 STOPPING + heartbeat → `HostInstanceLifecycleConflictError`，后续读取仍为 STOPPING
  - `test_repeated_register_same_identity_refreshes_heartbeat_and_status` (194-245) — 保留 STOPPING + register → RUNNING 的既有行为
- **结论**: ✅ 已修复

### GLM F02 / MIMO F01 (中): mark_current_instance_stopped 终态来源缺少测试

- **修复方式**: 在 `test_terminal_instance_does_not_revert_to_running_or_stopping` 的 parametrize 循环内增加 `mark_current_instance_stopped` 的 `HostInstanceLifecycleConflictError` 断言
- **验证**:
  - `test_host_instance_liveness.py:288-293` 对 STOPPED 和 CRASHED_SUSPECTED 均断言 `mark_current_instance_stopped` 抛出 `HostInstanceLifecycleConflictError`
  - 代码路径追踪：`_STOPPED_SOURCE_STATUSES = (RUNNING, STOPPING)` 不含终态 → UPDATE WHERE `status IN ('running', 'stopping')` 匹配不到终态 → rowcount=0 → `_raise_liveness_update_conflict` 读取 row → 终态不在 `_STOPPED_SOURCE_STATUSES` → 抛出 `HostInstanceLifecycleConflictError`
- **结论**: ✅ 已修复

### GLM F03 (低): register identity precheck 后 rowcount 零测试缺失

- **修复方式**: 新增 `test_register_rowcount_zero_after_identity_precheck_raises_conflict`
- **验证**:
  - `test_host_instance_liveness.py:506-535` 使用 `_IdentityDriftTransaction` 在 register UPDATE 前改写 token → UPDATE 零命中 → `_raise_liveness_update_conflict` 读取 row → 新 token 不匹配 → `_require_same_identity` 抛出 `HostInstanceIdentityConflictError`
  - 与既有 heartbeat 和 mark_stopping 的同类测试结构一致
- **结论**: ✅ 已修复

### MIMO F02 (低): _raise_liveness_update_conflict 异常分类假设

- MIMO 原评定为"无需修改"的防御性分支，不要求修复
- 无变化，维持原判定

## State Machine Completeness

逐条验证 liveness 状态机所有转移：

| 转移 | 操作 | 来源状态常量 | 允许 | 测试覆盖 |
|---|---|---|---|---|
| RUNNING → RUNNING | register | `_REGISTER_RUNNING_SOURCE_STATUSES` | ✅ | test_repeated_register (194) |
| RUNNING → RUNNING | heartbeat | `_HEARTBEAT_SOURCE_STATUSES` | ✅ | test_heartbeat_updates_only_same_identity (358) |
| RUNNING → STOPPING | mark_stopping | `_STOPPING_SOURCE_STATUSES` | ✅ | test_mark_stopping_and_stopped (599) |
| RUNNING → STOPPED | mark_stopped | `_STOPPED_SOURCE_STATUSES` | ✅ | test_mark_stopping_and_stopped (599) |
| STOPPING → RUNNING | register | `_REGISTER_RUNNING_SOURCE_STATUSES` | ✅ | test_repeated_register (194) |
| STOPPING → RUNNING | heartbeat | `_HEARTBEAT_SOURCE_STATUSES` | ❌ | test_stopping_heartbeat (304) |
| STOPPING → STOPPED | mark_stopped | `_STOPPED_SOURCE_STATUSES` | ✅ | test_mark_stopping_and_stopped (599) |
| STOPPING → STOPPING | mark_stopping | `_STOPPING_SOURCE_STATUSES` | ❌ | (隐含：STOPPING ∉ (RUNNING,)) |
| STOPPED → * | 任何操作 | 终态守卫 | ❌ | test_terminal (248) |
| CRASHED_SUSPECTED → * | 任何操作 | 终态守卫 | ❌ | test_terminal (248) |

所有转移与 A2 裁决一致。

## Rowcount-Zero Test Coverage

| 操作 | identity drift 测试 | 状态冲突测试 |
|---|---|---|
| register | test_register_rowcount_zero (506) | test_terminal (248) 含 register |
| heartbeat | test_heartbeat_rowcount_zero (442) | test_terminal (248) 含 heartbeat + test_stopping_heartbeat (304) |
| mark_stopping | test_status_mark_rowcount_zero (474) | test_terminal (248) 含 mark_stopping |
| mark_stopped | _(共享 `_mark_current_instance_status` 路径)_ | test_terminal (248) 含 mark_stopped |

`mark_stopped` 的 identity drift 测试与 `mark_stopping` 共享同一 `_mark_current_instance_status` + `_require_single_liveness_update` 代码路径，仅 `allowed_source_statuses` 参数不同；identity drift 场景下该参数不影响异常分类（drift 走 `_require_same_identity` 抛 `IdentityConflictError`）。无需额外测试。

## Adversarial Failure Pass

1. **STOPPING → RUNNING via heartbeat 被拒绝后，Host lifecycle 是否有恢复路径？** 有。`register_current_instance()` 仍允许 STOPPING → RUNNING，Host 可通过显式重注册取消 shutdown。
2. **register 在 STOPPING 状态下是否仍能心跳刷新？** 是。register 路径会同时写 `heartbeat_at` 和 `status = RUNNING`，所以 STOPPING row 被 register 后既刷新心跳又回退状态。这是显式操作，语义合理。
3. **拆分常量后是否有遗漏引用？** diff 中旧名 `_RUNNING_SOURCE_STATUSES` 已完全替换为 `_REGISTER_RUNNING_SOURCE_STATUSES` 和 `_HEARTBEAT_SOURCE_STATUSES`，无残留。
4. **是否引入 recovery/lease/fencing scope creep？** 否。仅修改来源状态常量拆分和测试补全，无新功能。

## Validation

- 测试: `16 passed`
- pyright: `0 errors, 0 warnings, 0 informations`
- 无 whitespace error

## Open Questions

无。

## Residual Risk

- `_IdentityDriftTransaction` 测试 wrapper 未调用 `super().__init__()`（前次 review 已记录，风险极低，维持原判定）。
- 本次 review 未检查 `dayu/host/durable/` 其余模块是否受 `HostInstanceLifecycleConflictError` 新异常类型的影响（A2 scope 限定在 liveness primitive 内，维持原判定）。

## Verdict

**可合入。** 三项 review finding（GLM F01/F02/F03，MIMO F01）全部修复且验证通过：

1. heartbeat 来源状态拆分为 RUNNING-only，STOPPING 不再被自动 heartbeat 静默回退
2. register 保留 STOPPING → RUNNING 显式重注册语义
3. 终态 row 的 `mark_current_instance_stopped` 拒绝路径已有测试保护
4. register identity drift rowcount-zero 路径已有测试保护
5. 16 测试通过，pyright 0 error，无 scope creep
