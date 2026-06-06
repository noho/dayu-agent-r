# WU-CM-01-F04 Plan Fix — AgentCodex

## Scope

当前 gate 只执行 plan review findings fix。已修改 plan artifact，新增本 fix artifact；未进入 implementation / review / re-review gate，未修改生产代码、测试代码、README、总控文档，未 commit / push / PR / merge。

Plan artifact:

- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md`

Review artifacts:

- `docs/reviews/wu-cm-01-f04-plan-review-mimo.md`
- `docs/reviews/wu-cm-01-f04-plan-review-ds.md`

## Fix Status

Plan status: ready after fix.

Findings fixed: 7.

Findings rejected: 1.

Blocking open questions: none.

## Finding Resolution

### DS Finding 1 / MiMo F4 — semantic scan, not literal `FakeContextCompactor()` search

Status: 已修复。

Plan changes:

- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:14` 将成功信号改为 implementation 前必须语义枚举所有 proactive compactor injection。
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:115`-`156` 新增 Slice 0，要求 grep `_RequestCapturingCompactor`、`_TransactionReadableCompactor`、`_StaleMutatingCompactor`、`_RaisingCompactor`、`_QualityRejectOnceCompactor`、`context_compactor=` 与 direct `FakeContextCompactor()`，再按 accepted / rejected / stale-fallback / reactive 分类。
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:284`-`287` 重写 Slice 4，明确 broad scan 不限于 `context_compactor=FakeContextCompactor()` 字面量。

### DS Finding 2 / MiMo F1 — `_StaleMutatingCompactor` must not migrate

Status: 已修复。

Plan changes:

- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:109` 明确 `_StaleMutatingCompactor` 不迁移，理由是 test 期望 `CONTEXT_COMPACTED == 0`，stale check 在 accepted guard 前写 `CONTEXT_COMPACTION_FAILED`。
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:149` 在 Slice 0 excluded 清单中列出该 test。
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:215` 与 `:286` 在 Slice 2 / Slice 4 再次声明不迁移。

### DS Finding 3 — `_TransactionReadableCompactor` explicit migration

Status: 已修复。

Plan changes:

- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:108` 将 `_TransactionReadableCompactor` 设为必须显式迁移，并要求保留独立读事务语义。
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:142` 在 Slice 0 accepted inventory 中列出 `test_proactive_compaction_calls_llm_outside_write_transaction`。
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:211`、`:214` 在 Slice 2 中显式分配该迁移，禁止降级为普通 prepared helper。

### DS Finding 4 — `_RequestCapturingCompactor` usage scan

Status: 已修复。

Plan changes:

- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:106` 要求 implementation 前 grep `_RequestCapturingCompactor` 全部使用点，并将 proactive accepted path 归入 accepted migration slice。
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:139`-`140` 在 Slice 0 inventory 中列出两个 current proactive accepted 使用点。
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:208`-`209`、`:213` 在 Slice 2 中明确迁移并保留 captured request 语义。

### DS Finding 5 / MiMo residual — `RUNNER_CALL_INPUT_ASSEMBLED` count as conditional assertion

Status: 已修复。

Plan changes:

- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:220` 将 accepted path 的 `RUNNER_CALL_INPUT_ASSEMBLED` count 改为 conditional assertion，核心验收仍是 `CONTEXT_COMPACTED` payload manifest ref/digest。
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:253` 将 rejected path 的 count 断言改为 conditional assertion。
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:375` 在 residual risks 中明确不稳定时只断言 compacted/rejected payload manifest ref/digest。

### DS Finding 6 — digest constant over-design

Status: 证据失效 / rejected-with-reason 已纳入 plan。

Reason:

- Controller 已裁决模块级私有 digest 常量不是过度设计，且项目禁止魔法字符串。
- Plan 仍避免无必要新增常量：优先复用测试文件现有 `_CALL_CONTEXT_DIGEST`；只有无合适常量时才新增语义明确的私有 digest 常量。

Plan changes:

- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:170` 替换原 `_COMPACTOR_TEST_DIGEST` 建议。

### DS Finding 7 / MiMo F2 — `_RaisingCompactor` usage scan and post-manifest failure semantics

Status: 已修复。

Plan changes:

- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:110` 要求先 grep `_RaisingCompactor` 全部使用点，并明确迁移为 prepared post-manifest failure 是有意 test 语义升级。
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:147` 在 Slice 0 inventory 中列出 rejected proactive attempt 使用点和 grep 要求。
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:247`、`:270` 在 Slice 3 中重申使用点扫描、post-manifest failure 与不伪装 quality rejection。

### MiMo F3 — `_QualityRejectOnceCompactor` first quality rejection manifest coverage

Status: 已修复。

Plan changes:

- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:107` 明确第一次 quality rejection 的 rejected manifest assertion 是新增覆盖。
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:145` 在 Slice 0 mixed inventory 中要求第一次 rejected 与第二次 accepted 都有 manifest assertions。
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md:254`-`255` 在 Slice 3 中要求补第一次 quality rejected payload 和第二次 accepted attempt manifest assertions。

## Validation Performed

- 读取并对照 plan artifact、MiMo review artifact、DS review artifact。
- 只读 grep `tests/host/test_dispatch_scheduler.py` 中 `_RequestCapturingCompactor`、`_TransactionReadableCompactor`、`_StaleMutatingCompactor`、`_RaisingCompactor`、`_QualityRejectOnceCompactor`、`context_compactor=`、`FakeContextCompactor()` 使用点，用于修正 plan 的 semantic inventory。
- 只读 grep dispatch scheduler 及参考测试中的 digest / `RUNNER_CALL_INPUT_ASSEMBLED` 使用，确认 plan 应优先复用 `_CALL_CONTEXT_DIGEST`，并将 runner call event count 设为 conditional assertion。
- 未运行 pytest 或 pyright；本 gate 只改 plan/review artifact，未改生产代码或测试代码。

## Files Changed

- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md`
- `docs/reviews/wu-cm-01-f04-plan-fix-codex.md`

## Blocking Open Questions

无。
