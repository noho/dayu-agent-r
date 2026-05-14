# Code Review

## Scope

- Mode: current changes (scoped to A2 work unit)
- Branch: `fix/host-phase-4`
- Base: `main`
- Output file: `docs/reviews/repo-review-code-review-a2-host-liveness-lifecycle-hardening-glm-20260514.md`
- Included scope: `dayu/host/durable/errors.py`, `dayu/host/durable/liveness.py`, `tests/host/test_host_instance_liveness.py`, `docs/reviews/repo-review-fix-a2-host-liveness-lifecycle-hardening-20260514.md`
- Excluded scope: recovery, lease, fencing, takeover, Phase 11 dispatch, crash classifier
- Parallel review coverage: 无

## Findings

### 01-未修复-中-STOPPING 可被 heartbeat 静默回退为 RUNNING

- **入口/函数**: `heartbeat_current_instance()`
- **文件(行号)**: `dayu/host/durable/liveness.py` (42-45, 273-294)
- **输入场景**: 一个 Host instance 已进入 STOPPING 状态（shutdown 已发起但未完成），此时周期性 heartbeat 触发
- **实际分支**: UPDATE WHERE 子句使用 `status IN ('running', 'stopping')`，STOPPING 行被匹配并写回 RUNNING
- **预期行为**: A2 明确要求终态（STOPPED / CRASHED_SUSPECTED）不可回退，但对 STOPPING -> RUNNING 的语义未做显式裁决。然而 heartbeat 是自动定时操作，不代表 Host 有意取消 shutdown；STOPPING 是 Host 主动发起的有方向 lifecycle 转移，不应被自动 heartbeat 静默逆转
- **实际行为**: `heartbeat_current_instance()` 允许 STOPPING -> RUNNING 转移，因为 `_RUNNING_SOURCE_STATUSES` 包含 STOPPING 且与 `register_current_instance()` 共享同一常量
- **直接证据**:
  - 第 42-45 行：`_RUNNING_SOURCE_STATUSES = (HostInstanceStatus.RUNNING, HostInstanceStatus.STOPPING)`
  - 第 273 行：heartbeat 使用 `_status_values(_RUNNING_SOURCE_STATUSES)`
  - 第 280 行：UPDATE WHERE `status IN ({_status_placeholders(_RUNNING_SOURCE_STATUSES)})`
  - `register_current_instance()` 在第 224-231 行使用完全相同的常量
  - 测试 `test_repeated_register_same_identity_refreshes_heartbeat_and_status`（第 194-245 行）只验证了 register 路径的 STOPPING -> RUNNING，未验证 heartbeat 路径
- **影响**: Phase 11 recovery 将依赖 liveness row 作为恢复真源；STOPPING row 被自动 heartbeat 回退为 RUNNING 会产生以下风险：
  1. recovery 逻辑误判一个正在 shutdown 的 instance 仍在运行
  2. STOPPING 状态被丢失，recovery 无法区分"正在关闭"和"仍在运行"
  3. heartbeat timer 与 shutdown 流程的竞争条件导致 liveness row 状态与 Host 实际状态不一致
- **建议改法和验证点**:
  1. 将 heartbeat 的来源状态从 `_RUNNING_SOURCE_STATUSES` 改为仅 `(HostInstanceStatus.RUNNING,)`，即 heartbeat 只刷新 RUNNING row，STOPPING row 不被回退
  2. register 路径保留 STOPPING -> RUNNING（Host 显式重注册可取消 shutdown）
  3. 新增测试：STOPPING instance 的 heartbeat 应抛出 `HostInstanceLifecycleConflictError`
  4. 新增测试：STOPPING instance 的 register 应成功回退为 RUNNING（已有 `test_repeated_register_same_identity_refreshes_heartbeat_and_status` 覆盖，确认保留）
- **修复风险（低/中/高）**: 低——仅影响 heartbeat 路径的来源状态校验，register 路径不变
- **严重程度（低/中/高/严重）**: 中——当前不触发 production bug（Phase 11 未实现），但会留下与 A2 "终态不可回退" 精神不一致的隐性设计问题，且修复窗口在 Phase 11 开始前

### 02-未修复-低-mark_current_instance_stopped 终态来源缺少测试

- **入口/函数**: `mark_current_instance_stopped()`
- **文件(行号)**: `tests/host/test_host_instance_liveness.py` (248-295)
- **输入场景**: STOPPED 或 CRASHED_SUSPECTED 状态的 liveness row 被 `mark_current_instance_stopped()` 调用
- **实际分支**: 测试 parametrize 循环仅验证 `register_current_instance`、`heartbeat_current_instance`、`mark_current_instance_stopping` 三种操作在终态下抛出 `HostInstanceLifecycleConflictError`，未验证 `mark_current_instance_stopped`
- **预期行为**: 按 A2 scope，终态 row 不应被任何操作回退或覆盖。`_STOPPED_SOURCE_STATUSES = (RUNNING, STOPPING)` 不包含终态，SQL UPDATE 零命中后 `_raise_liveness_update_conflict` 会抛出 `HostInstanceLifecycleConflictError`，代码行为正确
- **实际行为**: `mark_current_instance_stopped` 终态路径无测试保护
- **直接证据**: 第 274-287 行仅对 `register_current_instance`、`heartbeat_current_instance`、`mark_current_instance_stopping` 断言 `HostInstanceLifecycleConflictError`；缺少对 `mark_current_instance_stopped` 的同类断言
- **影响**: 若未来 `_STOPPED_SOURCE_STATUSES` 被误改为包含 `STOPPED` 或 `CRASHED_SUSPECTED`，回归测试无法捕获
- **建议改法和验证点**: 在 `test_terminal_instance_does_not_revert_to_running_or_stopping` 的 parametrize 循环内增加 `mark_current_instance_stopped` 的 `HostInstanceLifecycleConflictError` 断言
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低——代码行为正确，仅缺测试回归保护

### 03-未修复-低-register identity precheck 后 rowcount 零测试缺失

- **入口/函数**: `register_current_instance()`
- **文件(行号)**: `tests/host/test_host_instance_liveness.py`
- **输入场景**: register 路径的 identity precheck 通过后，UPDATE 因并发 token 漂移而 rowcount 为零
- **实际分支**: heartbeat 和 mark_stopping 路径已有 `_IdentityDriftTransaction` 测试覆盖此场景；register 路径缺少同类测试
- **预期行为**: register 的 `_require_single_liveness_update` 应正确将 rowcount 零分类为 `HostInstanceIdentityConflictError` 或 `HostInstanceLifecycleConflictError`
- **实际行为**: register 路径的 rowcount 零分类逻辑未测试
- **直接证据**: 第 401-462 行有两个 `_IdentityDriftTransaction` 测试覆盖 heartbeat 和 mark_stopping；register 路径无对应测试
- **影响**: 若 register 路径的 rowcount 零分类逻辑因未来修改而回归，测试无法捕获
- **建议改法和验证点**: 增加 `test_register_rowcount_zero_after_identity_precheck_raises_conflict`，使用 `_IdentityDriftTransaction` wrapper 在 register 的 UPDATE 前制造 token 漂移，断言抛出 `HostInstanceIdentityConflictError`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低——代码逻辑与 heartbeat/mark 路径共享 `_require_single_liveness_update`，行为一致，仅缺测试

## Open Questions

- **STOPPED -> STOPPED 幂等性**: `mark_current_instance_stopped()` 对已处于 STOPPED 的 row 会抛出 `HostInstanceLifecycleConflictError`。A2 scope 未覆盖此场景。如果 Host shutdown 流程可能重复调用 mark_stopped（如 signal handler + cleanup 代码），调用方需处理此异常。是否应设计为幂等吸收（返回已 STOPPED 的 row）是 Phase 11 前需要决定的设计问题，但不属于 A2 scope。

## Residual Risk

- Finding 01 的 STOPPING -> heartbeat -> RUNNING 路径无测试覆盖，若裁决为 finding 则需补测试。
- Finding 02 的 `mark_current_instance_stopped` 终态路径无测试保护。
- `_IdentityDriftTransaction` 测试 wrapper 未调用 `super().__init__()`，依赖 Python 对未初始化父类属性的惰性访问。当前可行因为 `execute` 和 `fetchone` 均被 override，但若 `HostTransaction` 未来新增抽象方法且 liveness 代码调用它，此 wrapper 会暴露 `NotImplementedError`。风险极低，仅记录。
- 本次 review 未检查 `dayu/host/durable/` 其余模块是否受 `HostInstanceLifecycleConflictError` 新异常类型的影响（如 transaction runner 异常分类），因为 A2 scope 限定在 liveness primitive 内。

## Verdict

A2 实现与 adjudication scope 中明确列出的五项要求完全一致：

1. 终态 STOPPED/CRASHED_SUSPECTED 不可回退为 RUNNING 或 STOPPING ✅
2. register/heartbeat/status mark 的 identity precheck 与 UPDATE rowcount 零命中分类为结构化 identity/lifecycle/not-registered 错误 ✅
3. mark_current_instance_stopping 仅允许 RUNNING -> STOPPING ✅
4. mark_current_instance_stopped 保持 RUNNING -> STOPPED 与 STOPPING -> STOPPED ✅
5. 缺失 row 的 status mark 仍返回 None ✅

核心行为正确，pyright 和 14 项测试全部通过。Finding 01 是本次 review 最关键的裁决点：**STOPPING -> RUNNING via heartbeat 是否应被允许**。A2 adjudication 只明确裁决了终态不可回退，但 STOPPING 是有方向的非终态转移，被自动 heartbeat 静默逆转与 A2 "lifecycle 状态转移不可被非显式操作逆转" 的精神不一致。建议 controller 裁决此 finding 后再决定是否合入。Finding 02 和 03 是低优先级测试补全项。
