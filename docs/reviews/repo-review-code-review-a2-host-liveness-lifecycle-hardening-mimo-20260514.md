# Code Review

## Scope

- Mode: current changes (scoped to A2 work unit)
- Branch: `fix/host-phase-4`
- Base: `main`
- Output file: `docs/reviews/repo-review-code-review-a2-host-liveness-lifecycle-hardening-mimo-20260514.md`
- Included scope: `dayu/host/durable/errors.py`, `dayu/host/durable/liveness.py`, `tests/host/test_host_instance_liveness.py`, `docs/reviews/repo-review-fix-a2-host-liveness-lifecycle-hardening-20260514.md`
- Excluded scope: recovery, lease, fencing, takeover, Phase 11 dispatch, crash classifier
- Parallel review coverage: 无

## Findings

### 01-未修复-中-`mark_current_instance_stopped` 终态回退缺少测试覆盖

- **入口/函数**: `mark_current_instance_stopped()` / `test_terminal_instance_does_not_revert_to_running_or_stopping`
- **文件(行号)**: `tests/host/test_host_instance_liveness.py` (248-295)
- **输入场景**: `STOPPED` 或 `CRASHED_SUSPECTED` 状态的 liveness row 被 `mark_current_instance_stopped()` 调用
- **实际分支**: 测试仅验证 `register`、`heartbeat`、`mark_stopping` 三种操作在终态下抛出 `HostInstanceLifecycleConflictError`，未验证 `mark_stopped`
- **预期行为**: 按 A2 scope，终态 row 不应回退到任何活动状态；`STOPPED → STOPPED` 和 `CRASHED_SUSPECTED → STOPPED` 均应被拒绝或至少不改变终态。代码层面 `_STOPPED_SOURCE_STATUSES = (RUNNING, STOPPING)` 不包含终态，SQL UPDATE 零命中后会抛出 `HostInstanceLifecycleConflictError`，行为正确。但测试未覆盖此路径。
- **实际行为**: `mark_current_instance_stopped` 终态回退路径无测试保护
- **直接证据**: 测试文件 274-287 行仅对 `register_current_instance`、`heartbeat_current_instance`、`mark_current_instance_stopping` 断言 `HostInstanceLifecycleConflictError`；缺少对 `mark_current_instance_stopped` 的同类断言
- **影响**: 若未来 `_STOPPED_SOURCE_STATUSES` 被误改为包含 `STOPPED` 或 `CRASHED_SUSPECTED`，回归测试无法捕获
- **建议改法和验证点**: 在 parametrize 循环内增加 `mark_current_instance_stopped` 的 `HostInstanceLifecycleConflictError` 断言；可选：补充 `CRASHED_SUSPECTED → STOPPED` 的专门断言确认终态不被覆盖
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 02-未修复-低-`_raise_liveness_update_conflict` 异常分类假设 identity 已在 precheck 中验证

- **入口/函数**: `_raise_liveness_update_conflict()`
- **文件(行号)**: `dayu/host/durable/liveness.py` (481-508)
- **输入场景**: UPDATE rowcount 为 0 时进入诊断路径
- **实际分支**: 函数先 `read_host_instance`，若 row 存在则 `_require_same_identity`，若 identity 匹配但 status 不在 `allowed_source_statuses` 内则抛 `LifecycleConflictError`，否则抛 `IdentityConflictError`
- **预期行为**: 当 identity precheck 通过但 UPDATE 零命中时，最常见原因是 identity 在 precheck 和 UPDATE 之间发生漂移（TOCTOU），应抛 `IdentityConflictError`
- **实际行为**: 逻辑正确。函数先排除 `NotRegistered`，再排除 `IdentityConflict`，最后排除 `LifecycleConflict`。最后一个 fallback `raise HostInstanceIdentityConflictError` 覆盖了 identity precheck 通过但 row 被替换为同 pid/token 不同 id 的极端场景（虽然在当前单写者模型下几乎不可能）
- **直接证据**: 第 501 行 `_require_same_identity` 通过后，第 502 行 status 检查通过意味着 status 在 `allowed_source_statuses` 内，此时必然是 identity 匹配但 WHERE 条件的其他列（如 `process_start_token`）不匹配——这在当前 schema 中不可能发生，因为 `process_start_token` 是 identity 的一部分
- **影响**: 当前无实际影响，fallback 分支是防御性兜底。若 schema 未来扩展 WHERE 条件列，此 fallback 可能误分类
- **建议改法和验证点**: 无需修改；可在注释中标注此 fallback 是防御性分支，当前 schema 下不可达
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- **STOPPING → RUNNING 是否为 A2 合理行为？** `_RUNNING_SOURCE_STATUSES` 包含 `STOPPING`，允许 `register_current_instance()` 和 `heartbeat_current_instance()` 将 `STOPPING` 状态的 row 写回 `RUNNING`。这在当前设计下是合理的：graceful shutdown 期间若收到新 registration 或 heartbeat，可取消 shutdown 恢复运行。A2 仅要求终态（`STOPPED` / `CRASHED_SUSPECTED`）不可回退，未要求 `STOPPING` 不可回退。测试 `test_repeated_register_same_identity_refreshes_heartbeat_and_status` 覆盖了 `STOPPING → RUNNING` 路径。**结论：可接受，不是 finding。**

## Residual Risk

- `mark_current_instance_stopped` 终态路径无测试保护（Finding 01），是当前唯一可操作的测试补全项。
- `_IdentityDriftTransaction` 测试 wrapper 未调用 `super().__init__()`，依赖 Python 对未初始化父类属性的惰性访问。当前可行因为 `execute` 和 `fetchone` 均被 override，但若 `HostTransaction` 未来新增方法被 liveness 代码调用，此 wrapper 会暴露未初始化状态。风险低，仅记录。
- 本次 review 未检查 `dayu/host/durable/` 其余模块是否受 A2 变更影响（如 transaction runner 对新异常类型的处理），因为 A2 scope 限定在 liveness primitive 内。

## Verdict

A2 实现与 adjudication scope 一致。终态不可回退、rowcount 零命中结构化错误、来源状态守卫、缺失 row 返回 `None` 等核心行为均已正确实现且有测试覆盖。代码通过 pyright 和全部 14 项测试。**建议补全 Finding 01 的测试覆盖后合入。**
