# Controller Adjudication — Host Phase 0 / P0 Plan Review

- work unit: Host Phase 0 / P0 - Engine Context Compaction Event 语义前置
- current gate: plan review adjudication
- controller: AgentController
- date: 2026-05-13
- reviewed plan: `docs/host/phase0-engine-context-compaction-plan.md`
- review artifacts:
  - `docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-mimo-20260513.md`
  - `docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-ds-20260513.md`
- conclusion: plan direction is approved, but accepted non-blocking findings require a plan fix and re-review before user confirmation.

## Controller Summary

两份 review 均给出 pass 且无 blocker。controller 判断 P0 动机成立：当前 Engine overflow 路径确实用 `ContextBudgetSnapshot(0, 0, 0)` 表达 unknown budget，且该表达会误导后续 Host Context Governance implementation agent。

严重性边界按 plan 与 review 结论收敛：该问题阻塞 Phase 10 Context Governance / Compaction，不阻塞 Host Phase 1-9。

`budget_state: ContextBudgetSnapshot | None` 是当前最小可维护方案。无需引入 unknown marker dataclass、enum 或 sentinel。P0 不得把 proactive budget governance、compact、retry、tokenizer 或 Host state transition 放进 Engine。

## Accepted Findings Requiring Plan Fix

### A1-已修复-[低]-accepted-MiMo-003-Runner HTTP overflow event-path 测试需显式化

- source: MiMo finding 003
- controller decision: `accepted`
- reason: 当前 `test_context_overflow_classifier.py` 只覆盖 classifier 函数级分类，不能证明完整 Runner HTTP error path 不会把 context overflow 误归为普通 client error。P0-S1 已把 `test_http_error_event.py` 列为条件候选，但当前证据显示该测试缺口真实存在，应改为明确要求。
- required plan fix:
  - 将 Runner HTTP context overflow 回归测试从条件项改为 P0-S1 的明确测试要求。
  - 验证 400 context overflow body 产出 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`、保留 `provider_request_id`，并以 `RunnerDoneData(FinishReason.ERROR)` 收口。

### A2-已修复-[低]-accepted-MiMo-004-P0-S1 completion signal 必须显式包含 pyright

- source: MiMo finding 004
- controller decision: `accepted`
- reason: plan §7 已要求 pyright，但 slice completion signal 只写测试与 sentinel 搜索，容易让 implementation artifact 把 pyright 当成全局可选验证。
- required plan fix:
  - P0-S1 completion signal 增加 `source .venv/bin/activate && pyright` 通过。

### A3-已修复-[中]-accepted-DS-002-Phase 5 与 Phase 10 对 budget_state=None 的责任切分需明确

- source: DS finding 02
- controller decision: `accepted`
- reason: `budget_state=None` 会同时影响 EngineEvent ingest 的结构接受和 Context Governance 的策略解释。plan 当前写成 “Phase 5 或 Phase 10” 归属不够精确，后续 phase 可能互相等待或重复定义语义。
- required plan fix:
  - 将 residual risk destination 精确拆分：
    - Phase 5 owns EngineEvent ingest validation：接受 `budget_state=None` 的 Engine event shape，不把 `None` 当作协议错误，不要求 Engine 提供 Host budget ref。
    - Phase 10 owns Context Governance semantics：当 Engine overflow budget unknown 时，使用 Host estimator / policy 生成 before / after budget refs，并决定 compact / recovery。
  - P0 closeout 必须把该切分回写 `docs/host/implementation-control.md` 追踪区。

### A4-已修复-[低]-accepted-DS-003-Sentinel 搜索需补充多行构造防线

- source: DS finding 03
- controller decision: `accepted`
- reason: grep 不是主防线，但当前命令可能漏掉多行 keyword-argument 形式。P0 的目标正是清除误导性 sentinel，completion signal 应足够直接。
- required plan fix:
  - 在 sentinel 搜索中补充更稳妥的检查，例如单独搜索 `ContextBudgetSnapshot(`、`prompt_tokens=0`、`completion_tokens=0`、`total_tokens=0` 的组合，或要求 implementation report 说明多行构造检查结果。
  - 允许历史 review artifact 命中旧文本；生产代码、当前 tests、当前 README / design docs 不得保留旧 unknown-budget sentinel 语义。

### A5-已修复-[低]-accepted-DS-004-Contract test 应覆盖 None 与真实 snapshot 两条合法路径

- source: DS finding 04
- controller decision: `accepted`
- reason: P0 不是禁止 `ContextBudgetSnapshot(0, 0, 0)` 作为普通 int 三元组，而是禁止用它表示 unknown budget。合约测试应避免把 unknown 语义修成类型级禁用。
- required plan fix:
  - P0-S1 contract tests 同时覆盖 `budget_state=None` 合法，以及 `budget_state=ContextBudgetSnapshot(1000, 500, 1500)` 这类真实 snapshot 合法。
  - 文档说明 `0/0/0` 不得作为 unknown sentinel；不要求 dataclass 校验禁止零值。

### A6-已修复-[低]-accepted-DS-005-P0-S2 需目检 runner_events docstring

- source: DS finding 05
- controller decision: `accepted`
- reason: 当前 runner event docstring 没有明显旧语义，但 P0-S2 是文档同步 slice，应显式要求检查该 contract docstring，避免遗漏。
- required plan fix:
  - 将 `dayu/engine/contracts/runner_events.py` 作为 P0-S2 可选检查文件。
  - 若无需修改，implementation artifact 记录 `checked, no change needed`。

### A7-已修复-[低]-accepted-MiMo-002-and-DS-006-dayu/README.md 应精化已有术语而非机械追加

- source: MiMo finding 002, DS finding 06
- controller decision: `accepted`
- reason: `dayu/README.md` 当前已说明 Engine event 是 reactive fallback。P0-S2 应精化该术语，加入 budget unknown 边界，避免重复或把未来 Phase 10 写成已完成。
- required plan fix:
  - 将 `dayu/README.md` 操作从 “补充” 改为 “精化已有 Context Governance 术语条目”。
  - 只说明当前边界：Engine overflow event 在 provider overflow 路径不携带真实 Host budget；Host Context Governance 使用自身 estimator / policy。

## Deferred Findings

### D1-未修复-[低]-deferred-with-owner-MiMo-001-reason 字符串自由度

- source: MiMo finding 001
- controller decision: `deferred-with-owner`
- owner / destination: Host Phase 5 EngineEvent ingest mapping and Phase 10 Context Governance ingest semantics.
- reason: P0 只清理 unknown budget sentinel。`reason: str` 当前与 `RunFailedData.error_code` 风格一致，且已有私有常量约束。把 reason 改成公共 enum 会扩大 P0 公共契约变更面。
- required follow-up: Phase 5 / Phase 10 plan 必须决定是否在 Host ingest 层建立 typed mapping，不让 implementation agent 直接散落字符串分支。

## Rejected Or No-Action Findings

### R1-证据失效-[低]-rejected-with-reason-DS-001-真源层级 no-action finding

- source: DS finding 01
- controller decision: `rejected-with-reason`
- reason: 该 finding 实际验证 plan 正确，不是需要修复的问题。无需进入 fix scope。

## Plan Fix Scope

Plan fix agent 只允许修改：

- `docs/host/phase0-engine-context-compaction-plan.md`

Plan fix agent不得修改生产代码、测试代码或设计文档。fix 目标只是把上述 accepted findings 写回 plan，产出可 re-review 的 revised plan。

## Re-review Requirements

Plan re-review 必须验证：

- A1-A7 均已写回 plan。
- revised plan 仍不夹带 Host implementation code、Engine proactive governance、compact / retry / tokenizer / policy。
- residual risk destination 已精确到 P0 closeout、Phase 5 或 Phase 10，没有悬空项。
- revised plan 仍可直接交给 implementation agent 实施。

## Artifact Path

`docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-controller-adjudication-20260513.md`
