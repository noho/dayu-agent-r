# WU-RUNTIME-02 Plan Re-Review Artifact

- **Reviewed target**: `docs/host/wu-runtime-02-lane-clock-cancellation-plan.md` (已修 plan)
- **Work Unit**: WU-RUNTIME-02 Runtime Lane Clock and Cancellation Simplification
- **Gate**: plan re-review
- **Re-review role**: plan re-review specialist (Mimo)
- **Re-review timestamp**: 20260601-070140
- **Branch**: `fix/wu-runtime-02-lane-clock-cancellation`
- **Original review artifacts**:
  - `docs/reviews/wu-runtime-02-plan-review-mimo-20260601.md`
  - `docs/reviews/wu-runtime-02-plan-review-ds-20260601.md`

## Re-Review Scope

复核 Controller accepted findings 是否已修复，并检查是否新增 blocking 问题。

## Accepted Findings 复核

### Mimo F1: cleanup timeout helper 返回/抛出语义需明确

**原问题**: plan 中 "timeout 时抛出私有 runtime lane cleanup timeout 错误，或返回封闭的私有 timeout outcome" 中的"或"字让 implementation agent 需要在两种语义间自行决定。

**期望修复**: 固定为私有 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)` 抛出语义，不返回 outcome，不新增 public API。

**复核结论: 已修复**

直接证据:

1. **Design Decision 2 (line 119)**:
   > cleanup timeout 的内部表达固定为抛出私有 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)`。调用方沿用现有 `RuntimeLaneError` catch pattern 做 diagnostic / TTL fallback / token 状态保留，并始终对外重新抛出最初的 `asyncio.CancelledError`；不得改成返回 timeout outcome 或新增 public API。

2. **Slice 2 Exact changes (line 239)**:
   > timeout 时抛出私有 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)`。

3. **Slice 2 Exact changes (line 241)**:
   > 不得把 timeout 表达为返回 outcome、`None`、布尔值或 extra payload；不得新增 public API。

4. **Slice 2 Exact changes (lines 243-246)**:
   > 新增私有 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)`：仅在 `_await_task_after_outer_cancellation()` 超过 cleanup deadline 时抛出。类必须提供中文 docstring。不加入 `__all__`，不向 public contract 暴露。

"或"字已删除，语义明确固定为抛出 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)`。调用方沿用现有 `RuntimeLaneError` catch pattern，不新增 isinstance 判断分支。

---

### DS F1: 设计真源 monotonic-to-wall 表述会陈旧

**原问题**: `docs/host/design.md` line 222 的 "clock 使用 runtime injected / stdlib monotonic-to-wall strategy 必须保证同一 process 内 TTL 计算一致" 表述在 plan 修改后会变得陈旧。

**期望修复**: plan 已把 `docs/host/design.md` 同步纳入 implementation allowed files、exact changes、docs decision、validation，并要求真实 UTC per SQLite transaction，monotonic 只用于本进程等待 timeout。

**复核结论: 已修复**

直接证据:

1. **Allowed implementation files (line 132)**:
   > `docs/host/design.md`，仅同步 lane clock 表述：跨进程 TTL 使用每个 SQLite transaction 的真实 UTC，monotonic 只用于本进程等待 timeout。

2. **Slice 1 Exact changes (lines 189-193)**:
   > 同步更新 `docs/host/design.md` 的 lane clock 表述：
   > - 将现有 monotonic-to-wall strategy 表述替换为真实 `datetime.now(UTC)` per SQLite transaction。
   > - 明确 stale cleanup、active count、claim insert / refresh update 在同一 SQLite transaction 内使用同一个 UTC `now` bound value。
   > - 明确 monotonic 仅用于本进程 acquire wait timeout / cleanup wait timeout 等等待时长，不参与跨进程 TTL 判断。
   > - 保留"clock skew 只影响 runtime capacity availability，不影响 Host truth / EventLog / Attempt lifecycle"的边界说明。

3. **Slice 1 Docs decision (lines 213-214)**:
   > `docs/host/design.md` 必须跟随本 WU 实现同步更新 lane clock 表述，避免设计真源继续描述旧的 monotonic-to-wall strategy。

4. **Slice 2 Validation commands (lines 284-285)**:
   > `! rg -n "monotonic-to-wall|monotonic.*TTL" docs/host/design.md`
   > `rg -n "真实 UTC|datetime.now\\(UTC\\)|SQLite transaction|本进程等待 timeout" docs/host/design.md`

5. **Design source validation (lines 321-323)**:
   > `docs/host/design.md` 不得继续把 lane TTL 描述为 monotonic-to-wall strategy。
   > `docs/host/design.md` 必须说明 lane TTL 的 `created_at` / `heartbeat_at` / `expires_at` 与 stale cleanup 判断使用真实 UTC per SQLite transaction。
   > `docs/host/design.md` 必须说明 monotonic clock 只用于本进程等待 timeout，不参与跨进程 TTL 判断。

Plan 已将 `docs/host/design.md` 纳入 implementation 范围，有明确的更新要求、验证命令和 stop condition。Implementation agent 无法跳过此文档同步。

---

## 新增 Blocking 问题检查

检查范围:

- Plan 结构完整性
- Design decisions 一致性
- Slices 边界和依赖
- Allowed/forbidden files 一致性
- Tests 覆盖要求
- Validation 命令完整性
- Stop conditions 明确性
- 与项目约束的符合性

**结论: 未发现新增 blocking 问题。**

Plan 结构完整，两个 Design Decision 逻辑自洽，Slices 边界清晰且有明确依赖关系（Slice 2 依赖 Slice 1），allowed files 与 forbidden files 一致，tests 覆盖 happy path 和 failure paths，validation 命令可执行，stop conditions 明确。项目约束（中文 docstring、pyright、README 触发规则、runtime import boundary）均已覆盖。

---

## Conclusion: PASS

两个 accepted findings 均已修复：

- **Mimo F1**: "或"字已删除，cleanup timeout helper 语义明确固定为抛出 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)`。
- **DS F1**: `docs/host/design.md` 已纳入 implementation allowed files、exact changes、docs decision、validation，有明确的更新要求和验证命令。

没有 blocking finding。Plan 是 code-generation-ready，可安全交给 implementation agent。
