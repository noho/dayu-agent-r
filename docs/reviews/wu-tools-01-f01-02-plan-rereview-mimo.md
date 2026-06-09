# WU-TOOLS-01-F01-02 Plan Re-Review — AgentMiMo

## Review Metadata

| 项目 | 值 |
|---|---|
| reviewer | AgentMiMo |
| artifact type | plan re-review gate |
| work unit | WU-TOOLS-01-F01-02 |
| plan artifact | `docs/host/wu-tools-01-f01-02-cancellation-plan.md` |
| fix report | `docs/reviews/wu-tools-01-f01-02-plan-fix-codex.md` |
| controller adjudication | `docs/reviews/wu-tools-01-f01-02-plan-review-controller-adjudication.md` |
| re-review date | 2026-06-08 |

## Verdict

**Plan 可进入 implementation gate。所有 accepted plan fix 已完整落入 plan artifact。无新 blocking finding。**

---

## Accepted Findings Verification

### AF-1: Slice 1 明确 ToolCancelledOutcome 已包含在 ToolExecutionOutcome 中，无需改 callable / Host / Engine contract

**状态**: 已修复

**Plan 证据**:

- §6 Contract Changes (line 96): "direct Fins awaiting callable 的返回类型 `ToolExecutionOutcome` 已合法包含 `ToolCancelledOutcome`。因此 download / preprocess callable 在观察到 Host token 已取消时可以直接返回 cancelled outcome；这不是 callable 协议变更，也不需要修改 Host / Engine contract。"
- §8 Slice 1 (line 159): "start 前若 token 已取消，返回 `ToolCancelledOutcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED, ...)`，不创建 durable job。"
- §8 Slice 1 (line 160): "若 start 后 token 取消，调用 `runtime.request_cancel(start.job_id)` 并返回取消 outcome。"
- §7 Implementation Decisions (line 136): "direct Fins awaiting callable 可以直接返回 `ToolCancelledOutcome`，因为它不经过 legacy exception projection；该返回值已经属于 `ToolExecutionOutcome` 联合类型，不需要修改 callable 协议、Host contract 或 Engine contract。"

**结论**: plan 在 contract 层和 slice 层均自足说明了 `ToolCancelledOutcome` 的类型合法性，implementation agent 不会误判为 contract change。

---

### AF-2: Slice 1 明确 durable job create 后、executor.submit 前必须同步 checkpoint；_start_lock 或二次 checkpoint 时序 invariant 足够

**状态**: 已修复

**Plan 证据**:

- §8 Slice 1 (line 163): "durable job create 后、后台 `executor.submit` 前必须做同步 token checkpoint；若 checkpoint 命中取消，必须调用 `runtime.request_cancel(job_id)` 并不得 submit 后台 job。"
- §8 Slice 1 (line 164): "create / checkpoint / submit 决策必须满足同一个不可破坏时序：实现可以扩展 `_start_lock` 范围覆盖 durable create、同步 checkpoint 与 submit 决策，也可以在锁释放后、submit 前做二次同步 checkpoint；无论采用哪种方案，都不得留下'checkpoint 已看到取消但仍 submit 后台 job'的窗口。"
- §8 Slice 1 Invariant (line 182): "durable job create 后、后台 submit 前的取消检查必须是同步 checkpoint；命中取消后必须先桥接到 `runtime.request_cancel(job_id)`，再返回 cancelled outcome 或可收口的 cancelled job 事实。"

**结论**: plan 明确了三种层次的约束——slice 描述中的行为要求、时序方案选择权（`_start_lock` 扩展或二次 checkpoint）、不可违反的 invariant。implementation agent 有足够信息选择具体方案且不会留下 race window。

---

### AF-3: Slice 4 明确瞬时读方法 vs 搜索 / XBRL / processor / 循环 / 大结果组装的 checkpoint 密度裁决

**状态**: 已修复

**Plan 证据**:

- §8 Slice 4 (line 312-313): "Instant read methods whose work is bounded to one repository metadata/blob access or one direct processor read only need an entry checkpoint plus a checkpoint before the single high-risk call when applicable."
- §8 Slice 4 (line 314): "Methods involving search, XBRL facts, processor traversal, directory/file loops, table/fact filtering loops, or large result assembly need checkpoints inside the loop or immediately before and after the high-risk boundary."
- §8 Slice 4 (lines 315-320): 逐项列出 checkpoint 位置——repository list/meta/blob reads、processor creation/section/table reads、search engine query loops、XBRL fact query/filtering loops、large table/statement result assembly loops。

**结论**: plan 提供了清晰的二分裁决标准和具体 checkpoint 位置清单，implementation agent 不会因密度歧义而漏 checkpoint 或过度 checkpoint。

---

### AF-4: Slice 2 明确 search_public_web provider fallback loop 每次 provider attempt 前检查 token，取消后不得尝试后续 fallback provider

**状态**: 已修复

**Plan 证据**:

- §8 Slice 2 (line 211): "at the start of each provider fallback loop iteration, before each candidate provider attempt;"——明确 checkpoint 在每次 provider attempt 前。
- §8 Slice 2 (line 224): "If token cancellation is observed before a provider attempt, `search_public_web` must not try that provider or any later fallback provider."——明确取消后不得尝试当前或后续 provider。
- §8 Slice 2 Invariant (line 229): "Provider fallback loop checks token before every attempt; cancellation after one provider failure must prevent subsequent fallback attempts."——invariant 级约束。

**结论**: plan 在 slice 描述、error handling 和 invariant 三个层次均明确了 provider fallback loop 的取消行为，implementation agent 不会留下"取消后仍尝试后续 provider"的窗口。

---

## New Finding Scan

在验证过程中未发现新 blocking finding。plan 的 scope、design alignment、non-goals 均未因 fix 产生漂移。

---

## Gate Decision

**Plan is implementation-ready. No blocking findings.**

所有 4 项 accepted plan fix 均已完整落入 plan artifact，且在 slice 描述、contract 层和 invariant 层三个层次提供了自足说明。Plan 可进入 implementation gate。
