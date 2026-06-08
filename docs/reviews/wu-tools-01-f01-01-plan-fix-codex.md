# WU-TOOLS-01-F01-01 Plan Fix — AgentCodex

## Work unit / gate

- Work unit：`WU-TOOLS-01-F01-01`
- Gate：`fix`
- 任务类型：plan review accepted findings fix
- Plan artifact：`docs/host/wu-tools-01-f01-01-filelock-plan.md`

## Accepted findings fixed

### A1. `_release_ticker_lock` token parameter and dict cleanup

- 已修复。
- Plan 已明确要求 `_release_ticker_lock` 将旧 `stream` 参数改为 `token: RuntimeFileLockToken | None = None`。
- Plan 已明确要求 `_release_ticker_lock` 即使收到显式 token，也必须先通过 `_ticker_lock_tokens.pop(ticker, None)` 或等价方式移除 ticker 条目，再选择并 release token，避免保留 stale token reference。

### A2. `_StoreFileLock` fd-close test deletion rationale

- 已修复。
- Plan 已明确说明删除 `test_store_file_lock_closes_stream_when_flock_fails` 不是覆盖缺口。
- 已补充理由：收敛后 Fins 不再打开锁文件 `TextIO` / stream，fd 生命周期由 `dayu.runtime.filelock` 与第三方 `filelock` 实现内部管理。
- Completion report guidance 已要求 implementation agent 删除旧 fd-close 测试时确认这一点。

## Files changed

- `docs/host/wu-tools-01-f01-01-filelock-plan.md`
- `docs/reviews/wu-tools-01-f01-01-plan-fix-codex.md`

## Exact plan sections updated

- `## 8. Implementation decisions` / `Storage batch`
  - 增加 `_release_ticker_lock(..., token: RuntimeFileLockToken | None = None)` 签名要求。
  - 增加 `_ticker_lock_tokens.pop(ticker, None)` / 等价清理要求，覆盖显式 token 与 dict token release 路径。
- `## 9. Small implementation slices` / `Slice 1：Ingestion job store convergence` / `Exact allowed changes`
  - 增加 fd-close 测试删除理由与 implementation report 确认要求。
- `## 9. Small implementation slices` / `Slice 2：Storage batch lock convergence` / `Exact allowed changes`
  - 增加显式参数 rename 与 stale token reference 清理规则。
- `## 14. Completion report format`
  - 增加旧 `_StoreFileLock` fd-close 测试删除的 implementation report 指引。

## Validation performed

- `rg -n "_ticker_lock_tokens\\.pop|显式传入 token|fd lifecycle|文件描述符生命周期|Fins no longer opens lock streams" docs/host/wu-tools-01-f01-01-filelock-plan.md`
  - 已确认 plan 包含 `_ticker_lock_tokens.pop(ticker, None)` 或等价显式清理表述。
  - 已确认 plan 包含 fd lifecycle / Fins 不再持有 lock stream 生命周期的说明。
- `git diff --check docs/host/wu-tools-01-f01-01-filelock-plan.md docs/reviews/wu-tools-01-f01-01-plan-fix-codex.md`
  - 已通过，无 whitespace diagnostics。

## Remaining blocking open questions

- None.

## Residual risks classification

- 本 fix gate 未引入新的 blocking residual risk。
- accepted plan review findings 不再有未分类 residual risk。
- Plan 中既有 implementation-owned risks 保持不变：
  - `RuntimeFileLockError` docstring / error surface 变化仍归 Slice 1 / Slice 2 implementation 处理。
  - Storage batch release failure 类型变化仍归 Slice 2 implementation/report 处理。
  - 测试仍必须断言 Fins public behavior，不能断言第三方 reentrancy internals。
  - stale lock、lease、fencing、crash recovery ownership 和 distributed lock 语义按设计仍不属于本 work unit。
