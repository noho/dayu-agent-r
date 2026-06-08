# WU-TOOLS-01-F01-01 Plan Re-Review — AgentDS

## Scope

- Work unit: `WU-TOOLS-01-F01-01`
- Gate: plan re-review
- Plan artifact: `docs/host/wu-tools-01-f01-01-filelock-plan.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f01-01-plan-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-tools-01-f01-01-plan-fix-codex.md`
- Original reviews: `docs/reviews/wu-tools-01-f01-01-plan-review-mimo.md`, `docs/reviews/wu-tools-01-f01-01-plan-review-ds.md`

## Verdict

**pass**

两个 accepted findings A1/A2 已在 plan fix 中完整修复。无 blocking open questions。

## Accepted Finding Re-Review

### A1. `_release_ticker_lock` token parameter and dict cleanup

- **Status**: 已修复
- **Controller requirement**: plan 必须明确 `_release_ticker_lock` 参数从 `stream` 改为 `token: RuntimeFileLockToken | None = None`；即使显式传入 token，也必须从 `_ticker_lock_tokens` 移除对应 ticker 条目，避免 stale-reference edge case。
- **Evidence**:
  - Plan §8 Implementation decisions / Storage batch，第 184 行：`_release_ticker_lock` 的参数 `stream` 必须改为 `token: RuntimeFileLockToken | None = None`；实现签名为 `_release_ticker_lock(ticker, *, token: RuntimeFileLockToken | None = None)` 或等价的严格类型签名。
  - Plan §8，第 185 行：`_release_ticker_lock` 必须无条件先执行 `_ticker_lock_tokens.pop(ticker, None)` 或同等 dict 清理；即使调用方显式传入 `token`，也必须移除对应 ticker 条目，避免继承当前显式 stream release 不 pop dict 的 stale-reference edge case。随后 release 显式 token 或 pop 得到的 token，存在则 release。
  - Plan §9 Slice 2 Exact allowed changes，第 271 行：`_release_ticker_lock` 的显式参数必须从 `stream` 改为 `token: RuntimeFileLockToken | None = None`；函数内部必须 pop `_ticker_lock_tokens` 中的 ticker 条目或等价清理，即使显式传入 token 也不能留下 stale token reference。
- **Assessment**: 三处表述一致，完整覆盖 controller 要求的两点（参数签名变更 + dict 清理语义）。已修复。

### A2. `_StoreFileLock` fd-close test deletion rationale

- **Status**: 已修复
- **Controller requirement**: plan 必须明确删除旧 `test_store_file_lock_closes_stream_when_flock_fails` 不是覆盖缺口；替换后 Fins 不再打开 lock stream，fd lifecycle 由 `dayu.runtime.filelock` / 第三方 `filelock` 管理；implementation report 需确认。
- **Evidence**:
  - Plan §9 Slice 1 Exact allowed changes，第 219 行：`删除旧 test_store_file_lock_closes_stream_when_flock_fails 不是覆盖缺口：替换后 Fins 不再打开锁文件 TextIO / stream，文件描述符生命周期由 dayu.runtime.filelock 与第三方 filelock 内部管理；implementation report 必须明确确认这一点。`
  - Plan §14 Completion report format，第 473 行：`If deleting old _StoreFileLock fd-close test, confirm it is not a coverage gap because Fins no longer opens lock streams and fd lifecycle is owned by dayu.runtime.filelock / third-party filelock.`
- **Assessment**: 两处表述一致，完整覆盖 controller 要求的三点（非覆盖缺口声明 + fd 生命周期理由 + implementation report 确认要求）。已修复。

## Blocking Open Questions

无。

## Residual Risks / Uncovered Areas

- 本 re-review 不引入新的 residual risk。
- Plan 中既有 implementation-owned risks (R1-R5) 保持不变，均已有 owner/destination。
- 注意：Plan §12 R3 提到 `filelock.FileLock` 同进程 reentrancy 不应被 tests 断言——implementation agent 在 Slice 1/2 替换时需注意测试不侵入第三方内部行为。此为既有 risk，已在 plan 中分类。

## Validation Performed

| 验证 | 结果 |
|---|---|
| 读 plan artifact 全文，逐条对照 A1/A2 controller requirement | A1/A2 均已修复，证据完整 |
| 读 controller adjudication 确认 accepted findings 范围 | 仅 A1/A2 为 accepted，R1/R2 为 rejected-with-reason，不在本次 re-review 范围 |
| 读 fix artifact 确认 claimed fix 与实际 plan 内容一致 | 一致，fix artifact 所述的 plan section 修改均已出现在当前 plan 中 |
| `rg -n "显式传入 token.*pop\|_ticker_lock_tokens\.pop\(ticker" docs/host/wu-tools-01-f01-01-filelock-plan.md` | 命中第 185 行、第 271 行，确认 dict pop 清理语义存在 |
| `rg -n "不是覆盖缺口\|fd lifecycle\|文件描述符生命周期\|Fins no longer opens lock streams" docs/host/wu-tools-01-f01-01-filelock-plan.md` | 命中第 219 行、第 473 行，确认 fd-close 测试删除理由存在 |
