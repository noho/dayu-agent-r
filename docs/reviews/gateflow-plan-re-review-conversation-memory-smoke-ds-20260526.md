# Plan Re-Review: Host Public Conversation Memory Smoke

- **Re-review artifact**: `docs/reviews/gateflow-plan-re-review-conversation-memory-smoke-ds-20260526.md`
- **Updated plan**: `docs/reviews/gateflow-plan-conversation-memory-smoke-20260526.md`
- **Original DS review**: `docs/reviews/gateflow-plan-review-conversation-memory-smoke-ds-20260526.md`
- **MiMo review**: `docs/reviews/gateflow-plan-review-conversation-memory-smoke-mimo-20260526.md`
- **Re-reviewer role**: plan re-review worker (not controller, not implementer)
- **Date**: 2026-05-26

## Re-Review Objective

Verify that the updated plan fully resolves DS advisory findings 1-7 and remains handoff-ready / code-generation-ready without introducing new blocking issues. Specifically check: class name / tool instance recovery, `include_pressure` behavior, session snapshot soft observation, Round 3 no-pass-fail scope, constants inventory, additive pressure calibration, and public API boundary.

---

## Advisory Resolution Verification

### Finding 1 — Python class name for mock tool callable → RESOLVED

- **Original**: Section 5 never declared the Python class name.
- **Updated plan §5**: Explicitly declares `类名：MockFinanceFactTool` with `SmokeFactTool` callable pattern reference (call_count, last_marker, typed `__call__`).
- **Updated plan §12**: Confirms "`MockFinanceFactTool` 类名、`SmokeFactTool` callable 模式...已明确。"
- **Verdict**: Resolved. Implementation worker has unambiguous class name and pattern.

### Finding 2 — `pressure_blob` inclusion logic underspecified → RESOLVED

- **Original**: Plan didn't specify behavior when `include_pressure=false`.
- **Updated plan §5**: "tool result 在 `include_pressure=true` 时包含 `pressure_blob`，内容为确定性重复文本，目标长度为 `_SMOKE_TOOL_PRESSURE_CHARS = 120_000`。`include_pressure=false` 时仍返回 `pressure_blob` 字段，但值固定为空字符串 `""`；这样返回 shape 稳定，同时不会制造工具侧 pressure。"
- **Updated plan §12**: Confirms "`include_pressure` 的 `pressure_blob` 条件行为已固定为 true 时填充、false 时空字符串。"
- **Verdict**: Resolved. Both branches specified with rationale (stable return shape).

### Finding 3 — Session snapshot assertion conditional without fallback → RESOLVED

- **Original**: `active_run_id` / `queued_run_ids` assertion was conditional ("如...则断言") with no fallback behavior.
- **Updated plan §7**: Changed to soft observation: "`SessionSnapshot.active_run_id` 与 `queued_run_ids` 只做 soft observation：每轮结束后打印 public snapshot 中的 active / queued 状态；若仍显示 active 或 queued，不直接失败，因为后台 compact / lane scheduling 可能存在短暂状态。"
- **Updated plan §12**: Confirms "`SessionSnapshot.active_run_id` / `queued_run_ids` 已从硬断言改为 soft observation。"
- **Verdict**: Resolved. Correctly downgraded from hard assertion to log-only observation with documented rationale.

### Finding 4 — Round 3 signal depends on NPL ratio visibility → RESOLVED

- **Original**: Round 3 answer content had ambiguous pass/fail weight since `npl_ratio` wasn't in assertion_line.
- **Updated plan §6 Round 3**: "该轮是 topic-shift / no-tool pressure only，不承载 pass/fail 权重；即使模型回答'不确定'也不影响 smoke 结论，因为 `npl_ratio` 不在最终核对行内，不要求一定被 compaction 后上下文保留。"
- **Updated plan §12**: Confirms "Round 3 已明确为 topic-shift / no-tool pressure only，不承载 pass/fail 权重。"
- **Verdict**: Resolved. Round 3 explicitly classified as pressure-only with zero pass/fail weight.

### Finding 5 — Tool instance access path not documented → RESOLVED

- **Original**: Plan assumed but didn't state the `_find_smoke_tool(assembly.effective_tool_bundle)` recovery pattern.
- **Updated plan §6 Round 1**: "`MockFinanceFactTool` 实例必须从 `assembly.effective_tool_bundle` 中按 type/name 恢复，模式参考既有 `_find_smoke_tool`；禁止用模块级全局计数器替代 effective ToolBundle 中真实注册的 callable 实例。"
- **Updated plan §8**: "mock tool 实例通过 effective ToolBundle 恢复并断言调用状态，不能依赖模块级全局变量、global counter 或外部副本。"
- **Updated plan §12**: Confirms "effective ToolBundle 实例恢复路径已明确。"
- **Verdict**: Resolved. Recovery path documented in both §6 (assertion context) and §8 (implementation requirements).

### Finding 6 — Constants inventory incomplete → RESOLVED

- **Original**: No consolidated constants list; implementation worker would need to invent from scattered references.
- **Updated plan §5**: Full "模块级 `Final` 常量 inventory" subsection with 20 named constants covering scene id, slot key, tool name, tag, provider ids, marker, assertion prefix, client request prefix, default subject/user, preview chars, pressure chars, pressure chunk text, reserve tokens, terminal timeout, and stdout prefix constants. Each has explicit type annotation and proposed value.
- **Updated plan §12**: Confirms "模块级 `Final` 常量 inventory 已补齐，包含 scene id、slot key、工具名、tag、provider ids、marker、client request prefix、默认 subject/user、preview chars、pressure 参数、timeout 与 stdout 前缀。"
- **Verdict**: Resolved. Comprehensive inventory provided.

### Finding 7 — Dual pressure mechanism relationship implicit → RESOLVED

- **Original**: Plan didn't explicitly state that tool pressure and prompt pressure are additive and jointly calibrated.
- **Updated plan §5**: "tool pressure 与 Round 2 prompt pressure 是 additive pressure，必须共同按同一个 `OpenHostOptions.context_budget_policy` 校准；两者与基础上下文的估算总量应落在 soft threshold 以上、hard threshold 以下，计算方式参考既有 `_compact_pressure_padding()` / reserve pattern，禁止把两段压力分别独立打满。"
- **Updated plan §12**: Confirms "tool pressure 与 Round 2 prompt pressure 已明确为 additive，并需共同按同一个 `context_budget_policy` 校准。"
- **Verdict**: Resolved. Joint calibration requirement is explicit with explicit prohibition against independent max-out.

---

## MiMo Observation Absorption Check

- **MiMo F1** (Round 4 false-pass risk): The plan's three-field conjunction (marker + `1.88%` + `-0.14pct`) is acknowledged as sufficiently discriminating. The plan §6 already prints assertion line status for human inspection. No plan change needed — the risk assessment was accepted as-is.
- **MiMo F2** (tool callable parameter handling): Plan §5 already states "除 `include_pressure` 外，`company`、`period`、`topic`、`metric` 不参与动态业务计算，返回固定 deterministic JSON." Plan §12 confirms "吸收 mock tool 参数 deterministic 处理说明." Adequately addressed.

---

## New-Issue Scan

The updated plan was scanned for regressions or newly introduced issues:

| Check | Result |
|---|---|
| Constants inventory conflicts with existing plan sections | None — values are consistent with §3, §5, §6 |
| `include_pressure=false` returning `""` vs `null` conflicts with schema | None — `pressure_blob` is typed as string in JSON, `""` is valid |
| Soft observation for session snapshot removes useful signal | Not blocking — public snapshot status is still printed; only failure behavior changed |
| Round 3 zero-weight conflicts with "final answer 非空" hard assertion | None — Round 3 still asserts terminal SUCCEEDED + non-empty answer; only `npl_ratio` content is weightless |
| Additive pressure wording potentially conflicts with Round 1 `include_pressure=true` | None — Round 1 tool pressure is part of the additive total; calibration accounts for both sources |
| Public API boundary unchanged by plan updates | Confirmed — §4 allow/deny list unchanged |

No new blocking issues introduced.

---

## Cross-Cutting Re-Verification

### Public API boundary — CONFIRMED INTACT
§4 allow/deny list unchanged from original review. All six `Host` protocol methods verified present in `dayu/host/api.py`.

### Hard assertion stratification — CONFIRMED CORRECT
§7 now cleanly separates hard assertions (host lifecycle, tool call count, Round 4 marker+values) from soft/log observations (session snapshot status, Round 2 assertion line, compaction artifacts, natural-language consistency).

### Implementation constraints — CONFIRMED INTACT
§8 requirements unchanged: Chinese docstrings, strict typing, no Any/object, no magic strings (now backed by §5 inventory), ToolBundle-based instance recovery, no durable DB/EventLog/memory reads.

### Verification commands — CONFIRMED VALID
§9 focused tests, pyright, and manual smoke commands unchanged and still match the file set.

### README scope — CONFIRMED CORRECT
§10 correctly limits updates to root README only; `dayu/config/README.md` and `tests/README.md` correctly excluded.

---

## Final Assessment

**Plan re-review status: PASSED.**

All 7 DS advisory findings are resolved with concrete, verifiable plan changes. The MiMo observations are adequately absorbed. No new blocking issues were introduced. The updated plan is code-generation-ready and handoff-ready.

The plan's core design — four rounds of mock-tool-confirmed finance facts under additive compaction pressure, all through public Host APIs, with cleanly stratified hard vs. soft assertions — remains sound and well-scoped.
