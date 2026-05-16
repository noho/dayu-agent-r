# Host Phase 7 Design Re-Review Controller Adjudication - 2026-05-16

## 结论

Controller 裁决：Phase 7 design discussion 方向成立，但 re-review 提出的若干可低成本收敛项应在进入 plan gate 前写回。

两路 review 结论：

- `docs/reviews/host-phase7-design-re-review-mimo-20260516.md`：PASS，无 blocking finding。
- `docs/reviews/host-phase7-design-re-review-ds-20260516.md`：PASS，无 blocking finding；提出 1 个中严重度 finding 与 5 个低严重度 finding。

本轮已写回：

- `docs/host/design.md`
- `docs/host/implementation-control.md`

写回目标是让 planning agent 不需要重新设计 `resolve_wait` request envelope、late result diagnostic 载体、WAITING cancel
复数收口与测试矩阵。

## 裁决记录

### MiMo-1 accepted - `resolve_wait` 返回类型未显式声明

裁决：接受。

理由：Phase 4 public API 已定义 `resolve_wait(host, wait_id, request) -> RunSnapshot`，§20 中改成
`resolve_wait(wait_id, request)` 后缺少返回类型，容易让 planning / implementation agent 自行选择结果类型。

写回：`docs/host/design.md` 已明确 `resolve_wait(wait_id, request) -> RunSnapshot`，并说明 public command 成功返回当前
`RunSnapshot`。

### MiMo-2 accepted - `ResolveWaitRequest.outcome_ref` 替换命名未显式声明

裁决：接受。

理由：当前代码仍有 `ResolveWaitRequest.outcome_ref: str`。设计只说不应只携带字符串引用，仍可能诱导实现保留弱字段并叠加
新字段。

写回：`docs/host/design.md` 已明确 `ResolveWaitRequest.outcome_ref: str` 必须被强类型 `outcome` envelope 替代。

### MiMo-3 / DS-F6 accepted as plan requirement - adapter / snapshot / external refs 需要 plan 具体化

裁决：接受为 plan gate requirement，不作为 design blocker。

理由：`adapter_key` 来源、`snapshot_ref` 与 `external_job_id` 的 typed ref 约束是实现 plan 必须具体化的 contract detail；
当前设计已确认不得保存 adapter object、callable 或无结构 metadata bag，足以支撑 plan。

写回：`docs/host/implementation-control.md` 退出条件已要求 plan 与实现明确 `adapter_key` 来源、`snapshot_ref` /
`external_job_id` typed ref 约束。

### DS-F1 accepted as plan requirement - `observed_at` 类型未定

裁决：接受为 plan gate requirement。

理由：当前 `ResolveWaitRequest.observed_at` 是 `str`，但等待契约中 `deadline`、`captured_at` 已是 `datetime`。是否改成
`datetime` 或保留 string + strict parse validation，必须在 plan 中明确，不能由 implementation agent 临场选择。

写回：`docs/host/implementation-control.md` 退出条件已要求 plan 与实现明确 `observed_at` 类型或解析策略。

### DS-F2 accepted as plan requirement - lost outcome 与 wait record lost 状态需区分

裁决：接受为 plan gate requirement。

理由：adapter 带回的 unable-to-confirm outcome 与 Host 最终把 wait record 置为 `lost` 是不同层次。Host 仍应由
resolve_wait pipeline 根据 envelope + policy 决定 wait terminal 状态。

写回：`docs/host/implementation-control.md` 退出条件已要求 plan 与实现明确 lost outcome 与 wait record lost 状态区别。

### DS-F3 accepted - late result diagnostic 记录路径缺失

裁决：接受，并在进入 plan gate 前写回设计真源。

理由：`WAITING` cancel 后迟到结果不得作为 canonical fact 进入 EventLog，但也不能静默丢弃。Phase 8 projection / tool trace
无法重建 Phase 7 未记录的 late result evidence。最小 diagnostic EventLog event 是当前最佳实践：它不改变 canonical fact
状态机，不要求本 phase 实现完整 tool trace 投影，但给后续 projection 留下稳定输入。

写回：`docs/host/design.md` 已要求迟到 poll / callback / manual result 至少追加
`event_class=diagnostic`、`event_type=WAIT_LATE_RESULT_REJECTED` 的 EventLog diagnostic event，payload 包含 `wait_id`、
`run_id`、`source`、`idempotency_key`、`observed_at`、rejection reason 与 outcome digest / refs。`docs/host/implementation-control.md`
已把该 diagnostic event 纳入关键设计问题与验证要求。

### DS-F4 accepted - WAITING cancel 单数 active wait record 措辞不精确

裁决：接受。

理由：Phase 7 第一版应保持同一 Run 同时只有一个 active wait record 的 invariant，但 cancel 状态收口不应被单数措辞限制。

写回：`docs/host/design.md` 已改为 CAS 标记该 Run 下所有 active `status=waiting` wait records 为 `cancelled`，同时说明
Phase 7 第一版应保持单 active wait invariant，复数更新是防御性状态收口。

### DS-F5 accepted - 测试矩阵缺少关键竞态

裁决：接受。

理由：cancel-vs-resolve first-committer-wins 与 poll adapter 观察 cancelled wait 后停止 / abandon observation，都是 Phase 7
核心正确性语义，必须进入测试矩阵。

写回：`docs/host/implementation-control.md` 验证要求已补充 cancel-vs-resolve、poll adapter cancelled observation 与
late diagnostic EventLog event 测试。

## 当前 Gate

当前 gate：Phase 7 design fix write-back completed，等待 design fix re-review。

进入 plan gate 前必须取得至少两路 re-review PASS，确认本轮写回未引入新的 blocking open question。

## Plan Gate 必须覆盖

- `ResolveWaitRequest` typed outcome envelope 的字段名、封闭联合成员、payload ref / result ref 约束。
- `observed_at` 使用 `datetime` 还是 strict validated string。
- adapter reported lost / unable-to-confirm outcome 与 Host wait record `lost` terminal 状态的裁决关系。
- `adapter_key` 来源：不得扩展 Engine 契约让 Engine 选择 Host adapter；应由 ToolRuntime / Host adapter registry 在 accept candidate
  中提供。
- `snapshot_ref` 与 `external_job_id` 的 typed ref 约束。
- `WAIT_LATE_RESULT_REJECTED` diagnostic EventLog event schema 与测试。
- `WAITING` cancel 与 `resolve_wait` 并发 first-committer-wins。
