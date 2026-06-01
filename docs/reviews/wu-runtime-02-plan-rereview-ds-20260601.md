# WU-RUNTIME-02 Plan Re-review Artifact

- **Reviewed target**: `docs/host/wu-runtime-02-lane-clock-cancellation-plan.md`（已修版）
- **Work Unit**: WU-RUNTIME-02 Runtime Lane Clock and Cancellation Simplification
- **Review role**: plan re-review specialist (DS)
- **Review date**: 2026-06-01
- **Timestamp**: 20260601-070121
- **Branch**: `fix/wu-runtime-02-lane-clock-cancellation`
- **Re-review scope**: 仅复核 Controller accepted findings（Mimo F1、DS F1）是否已修复，并检查是否新增 blocking 问题

## Accepted Finding 复核

### Mimo F1 — cleanup timeout helper 返回/抛出语义需明确

- **原问题**: plan 写 "timeout 时抛出私有 runtime lane cleanup timeout 错误，**或**返回封闭的私有 timeout outcome"，"或"字让 implementation agent 需在两种语义间自行决定。
- **Controller 期望**: 固定为私有 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)` 抛出语义，不返回 outcome，不新增 public API。
- **已修 plan 证据**:
  - Line 119: "cleanup timeout 的内部表达固定为抛出私有 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)`。调用方沿用现有 `RuntimeLaneError` catch pattern 做 diagnostic / TTL fallback / token 状态保留，并始终对外重新抛出最初的 `asyncio.CancelledError`；**不得改成返回 timeout outcome 或新增 public API**。"
  - Line 239-240: "timeout 时抛出私有 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)`"
  - Line 241: "不得把 timeout 表达为返回 outcome、`None`、布尔值或 extra payload；不得新增 public API"
  - Line 243-246: 明确 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)` 为私有类，不加入 `__all__`，不向 public contract 暴露
- **裁决**: **已修复**。"或"歧义已删除，语义已固定为抛出私有异常，调用方 catch pattern 路径明确，不引入 public API。

### DS F1 — 设计真源 monotonic-to-wall 表述将变陈旧

- **原问题**: plan 未提及是否需要同步更新 `docs/host/design.md` line 222 的 "monotonic-to-wall strategy" 表述。实现后文档与代码不一致，后续维护者困惑。
- **Controller 期望**: plan 把 `docs/host/design.md` 同步纳入 implementation allowed files、exact changes、docs decision、validation，并要求真实 UTC per SQLite transaction，monotonic 只用于本进程等待 timeout。
- **已修 plan 证据**:
  - Line 132: `docs/host/design.md` 纳入 Allowed implementation files，明确 "仅同步 lane clock 表述：跨进程 TTL 使用每个 SQLite transaction 的真实 UTC，monotonic 只用于本进程等待 timeout"
  - Lines 189-193 (Slice 1 Exact changes): 详细列出 design.md 需修改的四项内容——
    1. 将现有 monotonic-to-wall strategy 表述替换为真实 `datetime.now(UTC)` per SQLite transaction
    2. 明确 stale cleanup、active count、claim insert / refresh update 在同一 SQLite transaction 内使用同一个 UTC `now` bound value
    3. 明确 monotonic 仅用于本进程 acquire wait timeout / cleanup wait timeout 等等待时长，不参与跨进程 TTL 判断
    4. 保留 "clock skew 只影响 runtime capacity availability，不影响 Host truth / EventLog / Attempt lifecycle" 的边界说明
  - Lines 213-215 (Slice 1 Docs decision): "`docs/host/design.md` 必须跟随本 WU 实现同步更新 lane clock 表述，避免设计真源继续描述旧的 monotonic-to-wall strategy"
  - Lines 286-288 (Slice 2 Docs decision): 再次确认 design.md lane clock 表述应已同步
  - Lines 313-323 (Validation Plan 独立 Design source validation 节): 三条必须断言——
    1. design.md 不得继续把 lane TTL 描述为 monotonic-to-wall strategy
    2. design.md 必须说明 lane TTL 使用真实 UTC per SQLite transaction
    3. design.md 必须说明 monotonic clock 只用于本进程等待 timeout
  - Lines 284-285 (Slice 2 Validation commands): 含 `rg` 命令验证 design.md 旧术语已清除、新术语已出现
- **裁决**: **已修复**。design.md 同步已完整纳入 allowed files、exact changes、docs decision、validation commands 和 design source validation 断言，覆盖了实施前中后三个阶段。

## 新增 Blocking 问题检查

对已修 plan 全文做 adversarial 扫描，检查修复过程中是否引入新的 blocking 问题：

- **Scope creep**: 未发现。Non-goals 未放宽，allowed files 未扩大，public API 不变化。
- **语义冲突**: 未发现。`_OuterCancellationCleanupTimeoutError` 的抛出语义与现有 `RuntimeLaneError` catch pattern 兼容，调用方始终对外重新抛出最初的 `asyncio.CancelledError`。
- **设计真源同步越界**: 未发现。design.md 修改范围限定为 lane clock 表述，不触及 Host architecture、状态机、EventLog、公共接口等。
- **测试缺口**: 未发现新增缺口。Slice 1/2 的测试描述覆盖 TTL time source proof、cleanup timeout success/failure、late result observer、token state retention。
- **实现歧义**: 未发现。cleanup timeout 计算公式（`busy_timeout_seconds + 0.25`）、observer 机制（done callback 或等价）、各调用点行为均已明确。
- **约束违反**: 未发现。无 callback/factory/profile/query/extra payload 接口新增，无 `Any`/`object`/无类型签名，无跨层 import。

无新增 blocking finding。

## Conclusion: PASS

两个 Controller accepted findings（Mimo F1、DS F1）均已修复。已修 plan 未引入新的 blocking 问题。Plan 仍保持 code-generation-ready。

**明确：没有 blocking finding。**
