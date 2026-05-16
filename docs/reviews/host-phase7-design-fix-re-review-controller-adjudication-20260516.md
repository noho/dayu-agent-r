# Host Phase 7 Design Fix Re-Review Controller Adjudication - 2026-05-16

## 结论

Controller 裁决：Phase 7 design fix re-review 通过，可以进入 handoff implementation-ready plan gate。

两路 re-review 结论：

- `docs/reviews/host-phase7-design-fix-re-review-mimo-20260516.md`：PASS。
- `docs/reviews/host-phase7-design-fix-re-review-ds-20260516.md`：PASS。

两路均确认 controller accepted findings 已关闭，且未引入新的 blocking design issue。

## 已关闭 findings

- MiMo-1：`resolve_wait` 返回类型缺失。已在 `docs/host/design.md` 明确
  `resolve_wait(wait_id, request) -> RunSnapshot`。
- MiMo-2：`ResolveWaitRequest.outcome_ref` 替换命名不明确。已在 `docs/host/design.md` 明确
  `outcome_ref: str` 必须被强类型 `outcome` envelope 替代。
- DS-F3：late result diagnostic 路径缺失。已在 `docs/host/design.md` 明确追加
  `WAIT_LATE_RESULT_REJECTED` diagnostic EventLog event；`docs/host/implementation-control.md` 已纳入验证要求。
- DS-F4：`WAITING` cancel 单数 active wait record 措辞不精确。已改为标记 Run 下所有 active `status=waiting` wait records，
  并保留 Phase 7 第一版单 active wait record invariant。
- DS-F5：测试矩阵缺少竞态覆盖。已补充 cancel-vs-resolve first-committer-wins、poll adapter observe cancelled wait、
  late diagnostic EventLog event 测试要求。
- DS-F1 / DS-F2 / MiMo-3 / DS-F6：`observed_at` 类型、lost outcome 与 wait record lost 区分、`adapter_key` 来源、
  `snapshot_ref` / `external_job_id` typed ref 约束，已作为 plan gate requirement 写入退出条件。

## 进入 Plan Gate 的硬要求

Phase 7 plan 必须逐项覆盖：

- `ResolveWaitRequest` typed outcome envelope 字段名、封闭联合成员、payload ref / result ref 约束。
- `observed_at` 使用 `datetime` 还是 strict validated string。
- adapter reported lost / unable-to-confirm outcome 与 Host wait record `lost` terminal 状态的裁决关系。
- `adapter_key` 来源；不得扩展 Engine 契约让 Engine 选择 Host adapter。
- `snapshot_ref` 与 `external_job_id` typed ref 约束。
- `WAIT_LATE_RESULT_REJECTED` diagnostic EventLog event schema、rejection reason 枚举、outcome digest / refs 格式。
- `WAITING` cancel 与 `resolve_wait` 并发 first-committer-wins。
- poll adapter 观察到 cancelled wait 后停止 / abandon observation 的行为。

## 当前 Gate

Phase 7 design discussion / design fix / design re-review 已完成。当前 gate 推进为 Phase 7 handoff implementation-ready plan。

Planning agent 必须以 `docs/host/design.md` 和 `docs/host/implementation-control.md` 为真源，不得从旧 Phase 6 unsupported
awaiting guard 反推架构边界。
