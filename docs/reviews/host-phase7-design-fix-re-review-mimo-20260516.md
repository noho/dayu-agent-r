# Host Phase 7 Design Fix Re-Review - 2026-05-16

## Review Target

- Controller adjudication：`docs/reviews/host-phase7-design-re-review-controller-adjudication-20260516.md`
- Fix diff：`docs/host/design.md`（相对于 review 基线的增量变更）
- Fix diff：`docs/host/implementation-control.md`（相对于 review 基线的增量变更）

## Scope

复核 controller adjudication 中接受的 findings 是否已在 fix diff 中正确关闭，以及 fix 是否引入新 blocking issue。

## Accepted Findings Closure Checklist

### MiMo-1: `resolve_wait` 返回类型未显式声明 — **CLOSED**

- design.md §20 签名段已改为 `resolve_wait(wait_id, request) -> RunSnapshot`
- public API 文本已补充 "`resolve_wait(host, wait_id, request)` 成功返回当前 `RunSnapshot`"
- 与 Phase 4 public API 列表一致

### MiMo-2: `outcome_ref` 替换命名未显式声明 — **CLOSED**

- design.md public API 段已明确 "`ResolveWaitRequest.outcome_ref: str` 必须被强类型 `outcome` envelope 替代"
- 明确了 `outcome` envelope 至少区分 completed / failed / cancelled / lost
- 外部引用只能作为 `outcome` envelope 的受限字段

### DS-F1: `observed_at` 类型未定 — **CLOSED as plan requirement**

- implementation-control.md 退出条件已要求 plan 与实现明确 "`observed_at` 类型或解析策略"
- 不作为 design blocker，正确委派到 plan gate

### DS-F2: lost outcome 与 wait record lost 状态需区分 — **CLOSED as plan requirement**

- implementation-control.md 退出条件已要求 plan 与实现明确 "lost outcome 与 wait record lost 状态区别"
- 不作为 design blocker，正确委派到 plan gate

### DS-F3: late result diagnostic 记录路径缺失 — **CLOSED**

- design.md §20 已新增 `WAIT_LATE_RESULT_REJECTED` diagnostic EventLog event 规则，包含完整 payload 字段列表（`wait_id`、`run_id`、`source`、`idempotency_key`、`observed_at`、rejection reason、outcome digest / refs）
- design.md §22 cancel 规则已同步更新，迟到结果 "至少追加 `WAIT_LATE_RESULT_REJECTED` diagnostic EventLog event"
- implementation-control.md 关键设计问题与验证要求均已纳入

### DS-F4: WAITING cancel 单数 active wait record 措辞不精确 — **CLOSED**

- design.md §22 已改为 "CAS 标记该 Run 下所有 active `status=waiting` wait records 为 `cancelled`"
- 同时明确 "Phase 7 第一版应保持同一 Run 同时只有一个 active wait record 的 invariant，并用测试守护；复数更新是防御性状态收口"
- 既维护了第一版 invariant 约束，又不被单数措辞限制未来扩展

### DS-F5: 测试矩阵缺少关键竞态 — **CLOSED**

- implementation-control.md 验证要求已补充：
  - `cancel-vs-resolve first-committer-wins`
  - `poll adapter observes cancelled wait and stops / abandons observation`
  - `late result writes diagnostic EventLog event`

### MiMo-3 / DS-F6: adapter / snapshot / external refs 需要 plan 具体化 — **CLOSED as plan requirement**

- implementation-control.md 退出条件已要求 plan 与实现明确 "`adapter_key` 来源、`snapshot_ref` / `external_job_id` typed ref 约束"
- Controller adjudication 明确 "`adapter_key` 来源：不得扩展 Engine 契约让 Engine 选择 Host adapter；应由 ToolRuntime / Host adapter registry 在 accept candidate 中提供"

## Fix Diff Quality Check

**未引入新 blocking issue**。fix diff 变更范围严格限于 adjudication 指定的写回目标：

- design.md：3 处增量变更（public API 段、§20 签名与 diagnostic 规则、§22 cancel 规则）
- implementation-control.md：2 处增量变更（关键设计问题新增 diagnostic event、退出条件新增 plan gate requirements、验证要求补充竞态测试）

所有变更都是对已有设计文本的补充和精确化，未修改已有状态机语义、未引入新概念、未改变 Phase 7 scope。

## Plan Gate Requirements Verification

Controller adjudication 列出的 plan gate 必须覆盖项，与 implementation-control.md 写回对照：

| Plan Gate 必须覆盖项 | implementation-control.md 状态 |
| --- | --- |
| `ResolveWaitRequest` typed outcome envelope 字段名、封闭联合成员 | 退出条件覆盖 |
| `observed_at` 使用 `datetime` 还是 strict validated string | 退出条件覆盖 |
| adapter reported lost 与 Host wait record `lost` terminal 状态区别 | 退出条件覆盖 |
| `adapter_key` 来源 | 退出条件覆盖 + adjudication 约束不得扩展 Engine 契约 |
| `snapshot_ref` / `external_job_id` typed ref 约束 | 退出条件覆盖 |
| `WAIT_LATE_RESULT_REJECTED` diagnostic EventLog event schema 与测试 | 关键设计问题 + 验证要求覆盖 |
| `WAITING` cancel 与 `resolve_wait` 并发 first-committer-wins | 验证要求覆盖 |

全部 plan gate requirements 已在 implementation-control.md 中有对应条目。

## Conclusion

**PASS**

所有 7 个 accepted findings 已正确关闭：3 个直接写回 design.md（return type、outcome_ref 替换、diagnostic event），1 个措辞精确化（WAITING cancel 复数收口），3 个作为 plan gate requirements 委派到 implementation-control.md（observed_at 类型、lost 状态区分、adapter/snapshot/external refs）。fix diff 未引入新 blocking issue。plan gate requirements 与 implementation-control.md 退出条件完整对齐。
