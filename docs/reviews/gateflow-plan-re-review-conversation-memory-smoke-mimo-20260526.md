# Plan Re-Review: Host Public Conversation Memory Smoke

- **Reviewer**: mimo
- **Re-review artifact**: `docs/reviews/gateflow-plan-re-review-conversation-memory-smoke-mimo-20260526.md`
- **Updated plan**: `docs/reviews/gateflow-plan-conversation-memory-smoke-20260526.md`
- **Original review**: `docs/reviews/gateflow-plan-review-conversation-memory-smoke-mimo-20260526.md`
- **DS review**: `docs/reviews/gateflow-plan-review-conversation-memory-smoke-ds-20260526.md`
- **Date**: 2026-05-26

---

## Summary

**Plan re-review passed. All DS advisory findings (1-7) and MiMo observations (F1-F2) are resolved. No new blocking issues introduced.**

---

## Checkpoint Verification

### 1. Class name / tool instance recovery — RESOLVED

**DS Finding 1** (class name undeclared) and **DS Finding 5** (tool instance access path undocumented):

- Plan §5 now declares: "类名：`MockFinanceFactTool`" with `call_count`、`last_marker` 观测状态。
- Plan §5 now states: "工具实例通过 `assembly.effective_tool_bundle` 从 tool bundle 中按类型取出（参考 `SmokeFactTool` 模式），不依赖模块级全局变量。"
- Plan §6 Round 1 hard assertions: "`MockFinanceFactTool` 实例必须从 `assembly.effective_tool_bundle` 中按 type/name 恢复，模式参考既有 `_find_smoke_tool`；禁止用模块级全局计数器替代 effective ToolBundle 中真实注册的 callable 实例。"

Both the class name and the recovery mechanism are now fully specified. An implementation worker has zero ambiguity.

### 2. include_pressure behavior — RESOLVED

**DS Finding 2** (pressure_blob inclusion logic underspecified):

- Plan §5 now states: "`include_pressure=true` 时包含 `pressure_blob`，内容为确定性重复文本，目标长度为 `_SMOKE_TOOL_PRESSURE_CHARS = 120_000`。`include_pressure=false` 时仍返回 `pressure_blob` 字段，但值固定为空字符串 `""`；这样返回 shape 稳定，同时不会制造工具侧 pressure。"

The conditional behavior is fully deterministic. Return shape stability (always present, empty when inactive) is a sound design choice — avoids schema-level conditional fields while keeping pressure behavior explicit.

### 3. Session snapshot soft observation — RESOLVED

**DS Finding 3** (session snapshot assertion conditional without fallback):

- Plan §7 "只做日志或 soft assertion" now states: "`SessionSnapshot.active_run_id` 与 `queued_run_ids` 只做 soft observation：每轮结束后打印 public snapshot 中的 active / queued 状态；若仍显示 active 或 queued，不直接失败，因为后台 compact / lane scheduling 可能存在短暂状态。"

Correctly downgraded from conditional hard assertion to unconditional soft observation. This eliminates the false-failure risk from transient scheduling states without losing diagnostic visibility.

### 4. Round 3 no-pass-fail scope — RESOLVED

**DS Finding 4** (Round 3 signal depends on NPL ratio surviving compaction):

- Plan §6 Round 3 now states: "该轮是 topic-shift / no-tool pressure only，不承载 pass/fail 权重；即使模型回答'不确定'也不影响 smoke 结论，因为 `npl_ratio` 不在最终核对行内，不要求一定被 compaction 后上下文保留。"

Explicitly documented as zero pass/fail weight. The `npl_ratio` not being in `assertion_line` is now a deliberate design choice rather than an oversight.

### 5. Constants inventory — RESOLVED

**DS Finding 6** (constants inventory incomplete):

- Plan §5 now has a dedicated subsection "模块级 `Final` 常量 inventory" listing 18 named constants with proposed values and naming convention guidance.
- Covers: scene id, slot key prefix, tool name, tag, provider id/spec id, import display path, smoke marker, assertion prefix, client request prefix, default subject, default user, preview chars, pressure chars, pressure chunk, compact pressure reserve tokens, terminal timeout, stdout prefix constants.

The inventory is comprehensive. Constants that depend on existing smoke values (`_COMPACT_PRESSURE_RESERVE_TOKENS`, `_TERMINAL_TIMEOUT_SECONDS`) correctly defer to the reference implementation, avoiding duplication of values that should be kept in sync.

### 6. Additive pressure calibration — RESOLVED

**DS Finding 7** (dual pressure mechanism relationship implicit):

- Plan §5 now states: "tool pressure 与 Round 2 prompt pressure 是 additive pressure，必须共同按同一个 `OpenHostOptions.context_budget_policy` 校准；两者与基础上下文的估算总量应落在 soft threshold 以上、hard threshold 以下，计算方式参考既有 `_compact_pressure_padding()` / reserve pattern，禁止把两段 pressure 分别独立打满。"

The additive nature, the shared calibration target, and the prohibition against independent maxing are all explicit. An implementation worker cannot accidentally overshoot the hard threshold.

### 7. Public API boundary — PASS (unchanged)

The plan's §4 allow/deny list is identical to the original review. No new APIs introduced, no boundary violations. Assembly helpers remain correctly classified as pre-Host typed composition.

---

## MiMo Original Observations Re-check

### F1: Round 4 value co-occurrence false-pass risk — NO CHANGE NEEDED

Plan still asserts marker + `1.88%` + `-0.14pct` conjunction. The three-field match remains sufficiently discriminating for a smoke test. No change required.

### F2: Mock tool callable parameter handling — RESOLVED

Plan §5 now explicitly states: "工具参数只用于 schema / tool-call contract 校验与 pressure 行为选择；除 `include_pressure` 外，`company`、`period`、`topic`、`metric` 不参与动态业务计算，返回固定 deterministic JSON。" This makes the "ignore all except include_pressure" intent explicit.

---

## New Issue Check

No new issues found. The plan changes are purely additive clarifications — they fill specification gaps without altering round design, assertion strategy, scope boundaries, or public API contract. The §12 "Plan Fix Note" accurately summarizes all changes and their mapping to the original findings.

---

## Conclusion

**Plan re-review passed.** All 7 DS advisory findings and 2 MiMo observations are resolved in the updated plan. No new blocking issues introduced. The plan remains handoff-ready and code-generation-ready.
