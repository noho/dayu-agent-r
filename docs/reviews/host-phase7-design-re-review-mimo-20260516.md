# Host Phase 7 Design Re-Review - 2026-05-16

## Review Target

- 设计讨论：`docs/reviews/host-phase7-design-discussion-codex-20260516.md`
- 设计真源 diff：`docs/host/design.md` §20, §21, §22 及 `resolve_wait` public API 文本
- 总控 diff：`docs/host/implementation-control.md` Phase 7

## Scope

复核已确认的 Phase 7 设计决策是否足够、最小化且与 Host 架构对齐。重点：
typed ResolveWaitRequest outcome envelope、wait record durable typed fields、
callback limited to adapter contract、WAITING cancel and late result diagnostic-only behavior、
no Engine/RemoteStub ownership of wait truth、no overdesign。

## Assumptions Tested

1. `ResolveWaitRequest` 从 `outcome_ref: str` 改为强类型 outcome envelope 足以支撑 Phase 7 测试矩阵。
2. wait record 字段列表完备且与现有 `ToolAwaitSpec` / `ToolAwaitSnapshot` 契约兼容。
3. callback 限定为 adapter contract 不会阻塞 Phase 7 最小闭环。
4. `WAITING` cancel + late result diagnostic-only 行为与 §22 Cancel 规则一致。
5. Engine 不拥有 wait truth 的约束在 diff 中被正确维护。
6. 设计决策不包含过度设计。

## Findings

### 1-未修复-低-resolve_wait 返回类型未在设计文本中显式声明

- **位置**: design.md §20 `resolve_wait` 签名段
- **问题类型**: 契约缺失
- **当前写法**: diff 将签名从 `resolve_wait(wait_id, outcome, source, idempotency_key)` 改为 `resolve_wait(wait_id, request)`，但设计文本未声明返回类型。
- **反例/失败场景**: implementation agent 可能推断返回 `None`、`RunSnapshot` 或自定义 `ResolveWaitResult`，导致实现不一致。
- **为什么有问题**: §20 其它 command（如 `cancel_run`）均在设计文本中声明返回类型；`resolve_wait` 缺失会迫使 implementation agent 从 implementation-control.md 侧面推断（Phase 7 交付物提到 `RunSnapshot`）。
- **直接证据**: design.md diff 只写了 `resolve_wait(wait_id, request)`，无返回类型注解；implementation-control.md Phase 7 退出条件提到 "Run 进入 WAITING，并由统一 `resolve_wait` 创建新 Attempt 继续"，暗示返回 `RunSnapshot`。
- **影响**: implementation agent 需要猜测返回类型，可能选择不一致方案。
- **建议改法和验证点**: 在 design.md §20 `resolve_wait` 段补充返回类型声明，例如 `resolve_wait(wait_id, request) -> RunSnapshot`。验证：与 Phase 4 public API 列表中的签名一致。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-ResolveWaitRequest 字段替换命名未显式声明

- **位置**: design.md §20 `resolve_wait` request 描述段
- **问题类型**: 契约缺失
- **当前写法**: diff 补充 "request 必须携带 `source`、`idempotency_key`、`observed_at` 与强类型等待结果 envelope"，但未声明 envelope 字段名是否替换现有 `outcome_ref`。
- **反例/失败场景**: implementation agent 可能保留 `outcome_ref: str` 并新增 `outcome: WaitOutcome`，导致 request 同时存在弱引用和强类型字段。
- **为什么有问题**: 现有代码 `ResolveWaitRequest` 有 `outcome_ref: str`；设计说 "不应只携带无语义的字符串结果引用"，但未明确删除还是重构该字段。
- **直接证据**: `dayu/host/api.py:1248` 当前为 `outcome_ref: str`；design.md diff 新增文本 "外部结果引用或 payload ref 只能作为 envelope 的受限字段"。
- **影响**: 轻微；implementation agent 可能创建冗余字段或命名不一致，但语义方向已明确。
- **建议改法和验证点**: 在设计文本中补充一句，明确 `outcome_ref: str` 被强类型 envelope 字段（如 `outcome: WaitOutcome`）替代，外部引用可作为 envelope 内部的可选 ref 字段。验证：Phase 7 plan slice 1 的 `ResolveWaitRequest` 修改应移除 `outcome_ref`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-ToolAwaitSpec 到 wait record 字段的映射未显式声明

- **位置**: design.md §20 wait record 最小语义段
- **问题类型**: 契约缺失
- **当前写法**: wait record 字段列出 `adapter_key`、`await_kind`、`resume_token`、`snapshot_ref?`，但未说明这些字段如何从 Engine 侧的 `ToolAwaitingOutcome.await_spec: ToolAwaitSpec` 和 `ToolAwaitingOutcome.snapshot: ToolAwaitSnapshot | None` 映射而来。
- **反例/失败场景**: `ToolAwaitSpec` 有 `await_kind` 和 `resume_token`，但没有 `adapter_key`。implementation agent 需要推断 `adapter_key` 从哪来（ToolRuntime adapter registry？ToolExecutor 返回值？ToolAwaitingOutcome 扩展字段？）。
- **为什么有问题**: `adapter_key` 是 wait record 的核心字段，用于 Host restart 后恢复 adapter observation。若来源不明确，implementation agent 可能选择不同路径：扩展 `ToolAwaitingOutcome`、扩展 `ToolAwaitSpec`、或从 ToolRuntime context 推导。
- **直接证据**: `dayu/contracts/tool_await.py:44-46` 中 `ToolAwaitSpec` 只有 `await_kind`、`deadline`、`resume_token`，无 `adapter_key`。wait record 字段列表包含 `adapter_key` 但无映射说明。
- **影响**: implementation agent 可能做出不一致的 adapter_key 来源选择，影响 Phase 7 与 Phase 6 ToolRuntime 的接口边界。
- **建议改法和验证点**: 在 plan 阶段明确 `adapter_key` 来源，例如 "ToolRuntime 从 adapter registry 查找 adapter_key，作为 ToolAwaitingOutcome accept candidate 的一部分提交给 Host"。无需修改设计文本，但 plan slice 1 必须覆盖该映射。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 4-未修复-低-snapshot_ref 存储路径未指定

- **位置**: design.md §20 wait record 最小语义段
- **问题类型**: 契约缺失
- **当前写法**: wait record 列出 `snapshot_ref?` 为可选字段，`ToolAwaitSnapshot` 有 `snapshot_id` 和 `captured_at`，但设计未说明快照内容存储在哪。
- **反例/失败场景**: implementation agent 可能将快照内容内联到 wait record row、存入 payload table、或只存 snapshot_id 引用让 adapter 自行管理。
- **为什么有问题**: 若快照较大，内联到 wait record row 会影响查询性能；若只存引用，需要明确存储契约。
- **直接证据**: `dayu/contracts/tool_await.py:60-73` 中 `ToolAwaitSnapshot` 有 `snapshot_id: str` 和 `captured_at: datetime`，是引用而非内容。wait record 的 `snapshot_ref` 命名暗示也是引用。
- **影响**: 轻微；implementation agent 大概率选择存引用（与现有 `ToolAwaitSnapshot` 设计一致），但缺少显式约束。
- **建议改法和验证点**: plan 阶段确认 `snapshot_ref` 存储 `ToolAwaitSnapshot.snapshot_id`，快照内容由 Host / ToolRuntime 管理，不在 wait record row 内联。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Architecture Boundary Review

**PASS**。设计决策正确维护了 Host 架构边界：

- Host 是 wait truth 的唯一 owner：wait record 由 Host transaction 创建，Engine `tool_awaiting` / `run_suspended` 只能 diagnostic / idempotent confirmation。
- `resolve_wait` 是 Host 内部 command path，所有 adapter（poll / callback / manual）必须走它，不能各自写 Run 状态。
- Engine 不读取 wait record，不恢复旧 Agent / Runner。
- wait record 是 durable state index，不是 EventLog 替代品，不是 projection truth。定位清晰。

## Best-Practice Review

**PASS**。设计符合项目最佳实践：

- wait record 使用强类型字段而非无结构 metadata bag。
- `resolve_wait` 是短事务 command，幂等范围 `(wait_id, idempotency_key)` 明确。
- cancel 与 resolve 并发时先提交者赢，CAS 语义清晰。
- callback 限定为 adapter contract，不提前产品化，符合最小闭环原则。

## Optimal-Solution Review

**PASS**。当前方案是 credible alternatives 中最实际的路径：

- wait record 作为 durable state index 是解决 active wait 查询、adapter observation 恢复、取消 CAS 和 late result 拒绝的最直接方案。
- 统一 `resolve_wait` pipeline 避免了 adapter 各自写状态的碎片化。
- 不实现 callback 产品化是正确的 scope 控制。

## Overengineering Review

**PASS**。未发现过度设计：

- wait record 字段列表刚好覆盖 Phase 7 需求，没有预留无用字段。
- callback 只保留 contract，不实现 HTTP endpoint / 认证 / 复杂重放防护。
- 不保证外部 job physical cancel，不实现 retry / replay，scope 收敛。

## Overcoupling Review

**PASS**。未发现过度耦合：

- wait record 与 EventLog 是互补关系，不是重复存储。
- adapter 通过 adapter_key 引用，不保存进程内 adapter 对象到 durable row。
- `resolve_wait` pipeline 是唯一的 resolution 路径，但不强制所有 adapter 使用相同实现，只强制走同一入口。

## Open Questions

无。所有 design discussion 中的 blocking questions 已在 D1-D4 中确认。

## Residual Risks

| 风险 | 严重程度 | 跟踪方式 |
| --- | --- | --- |
| `adapter_key` 来源需在 plan 阶段明确，否则 implementation agent 可能选择不一致路径 | 低 | Plan review gate |
| `snapshot_ref` 存储路径需在 plan 阶段确认 | 低 | Plan review gate |
| `resolve_wait` 返回类型和 `outcome_ref` 字段替换命名需在 plan 中显式覆盖 | 低 | Plan review gate |

以上风险均为 plan 阶段可解决的实现细节澄清，不构成设计层面的 blocker。

## Conclusion

**pass**

Phase 7 设计决策 D1-D4 足够、最小化且与 Host 架构对齐。typed outcome envelope 替代弱 `outcome_ref`、wait record 作为 Host durable state index、callback 限定 adapter contract、WAITING cancel + late result diagnostic-only 四项决策均正确，无过度设计或过度耦合。设计文本 diff 和 implementation-control diff 一致。发现的 4 个低严重度 gaps 均为 plan 阶段实现细节澄清，不阻塞 handoff。
