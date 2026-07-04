# WU-WAIT-03 Plan Review Controller Adjudication

## Scope

- Work unit: WU-WAIT-03 / GitHub Issue #92
- Gate: plan review
- Plan artifact: `docs/host/wu-wait-03-external-job-lifecycle-plan.md`
- Review artifacts:
  - `docs/reviews/wu-wait-03-plan-review-mimo.md`
  - `docs/reviews/wu-wait-03-plan-review-ds.md`

## Controller Decision

Verdict: `fix-required`

Reason: 两路 review 均确认 plan 的目标、边界、Host / Engine 分层、2-slice 切分和避免过度设计方向成立；但 `WaitPollLastOutcome` 新值、unsupported/noop 终端标记、durable mutation path 和 Fins missing/corrupt handle 映射仍有歧义。该歧义会把 durable state mutation 设计推给 implementation agent，因此当前 plan 尚未达到 fully code-generation-ready。

## Finding Adjudication

| Finding | Source | Decision | Required plan-fix action |
|---|---|---|---|
| WaitPollLastOutcome enum conditional language | MiMo F01 / DS F01 | accepted | Plan 必须明确添加 `ABANDON_UNSUPPORTED` 与 `ABANDON_NOOP`，并说明 StrEnum serialize/deserialize、row validation 与 tests 的处理。不得保留 “if needed / only if needed” 表述。 |
| unsupported/noop durable write path | MiMo F02 / DS F02 / DS F03 | accepted | Plan 必须明确参数化 `mark_wait_record_poll_abandoned(...)` 或新增等价 mutation。Controller 裁决优先方案：参数化 existing mutation，新增 `last_outcome: WaitPollLastOutcome = WaitPollLastOutcome.ABANDONED`，unsupported/noop 同样设置 `poll_abandoned_at` 以阻止 re-claim。 |
| Fins non-transient error / corrupt / missing handle mapping | MiMo F03 / DS F04 | accepted | Plan 必须明确：corrupt token、missing observation 或非 transient observation error 均映射为 `WaitExternalJobLifecycleNoop`，并写清 reason 语义；`TRANSIENT_UNAVAILABLE` 继续 re-raise 进入 retry/backoff。 |
| WaitPollOnceResult.abandoned counter semantics | MiMo F04 | accepted | Plan 必须明确 applied / unsupported / noop 这三类 terminal lifecycle result 均计入 `abandoned`，因为它们都会完成 cancelled wait 的 lifecycle terminal marker。不得新增当前 WU 不需要的新 counter。 |
| unsupported/noop CAS conflict and prepared cancel tests | DS F05 | accepted | Plan 必须把 unsupported/noop terminal marker CAS conflict 和 prepared observation cancel + abandon 明确列入 Slice 1 / Slice 2 测试矩阵。 |
| `WaitExternalJobLifecycleAction.REVOKE` support | DS F06 | accepted-for-clarification | 不要求删除 `REVOKE`。Issue #92 明确包含 revoke / invalidate future delivery 语义，保留该 internal enum 可以接受；但 plan 必须说明 action selection rule：adapter 返回实际采取的最强 lifecycle action；`REVOKE` 只用于 provider 能 invalidate future delivery/result 但不 necessarily physical stop 的场景。当前 Fins adapter 返回 `ABANDON`。 |

## Accepted Plan Strengths

- Work unit 动机成立且未被扩大为 Host cancellation correctness 缺陷。
- Host command cancel path 不做 provider I/O。
- Engine 不拥有 wait / cancel / poll / external lifecycle。
- `resolve_wait(...)` 仍是 late result 唯一治理入口。
- 不新增 public Host API、Engine contract、durable table、provider capability registry 或第二套 watchdog。
- 2 个 implementation slices 符合 control doc Slice 切分原则。

## Plan-fix Stop Conditions

Plan-fix 只允许修改 `docs/host/wu-wait-03-external-job-lifecycle-plan.md`，不得修改生产代码、测试或 control doc。若修复过程中发现必须新增 durable schema column/table、public Host API、Engine contract、provider capability registry 或第二套 watchdog，必须停止并报告。

## Residual Risks

当前没有未归属 residual risk。已有风险均保留原 owner/destination：

- Provider 不支持 physical cancel：provider-specific adapter owners under GitHub Issue #92 / #87。
- Poller disabled deployment 不执行 external lifecycle：Service composition / WU-WAIT-04。
- Fins running operation 只做 cooperative checkpoint：Fins provider/runtime owners。
- 更丰富 tool trace lifecycle diagnostic：后续 tool trace / diagnostic projection work。
