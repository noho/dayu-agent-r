# Plan Review: Host Public Conversation Memory Smoke

- **Review artifact**: `docs/reviews/gateflow-plan-review-conversation-memory-smoke-ds-20260526.md`
- **Plan under review**: `docs/reviews/gateflow-plan-conversation-memory-smoke-20260526.md`
- **Source intent**: `/Users/leo/workspace/dayu-agent/docs/conversation_memory_test.md`
- **Reference implementation**: `utils/smoke_host_public_multiturn.py`
- **Reviewer role**: plan review worker (not controller, not implementer)
- **Date**: 2026-05-26

## Summary

**Verdict: No blocking findings. Plan is code-generation-ready with 7 advisory findings.**

The plan correctly narrows the scope from the broad `conversation_memory_test.md` (five test groups, real Fins tools, DB reads, 20+ round stability) to a single well-defined smoke: four rounds of mock-tool-confirmed finance facts under compaction pressure, all through public Host APIs. The scenario selection (test group D core + group B auxiliary) is appropriate; groups A, C, E are correctly rejected with clear reasoning. The hard-assertion design can actually distinguish memory continuity from tool re-calls or random LLM output because tools are disabled after Round 1 and the marker values (`1.88%`, `-0.14pct`) are non-trivial.

---

## Finding 1 — ADVISORY: Python class name for mock tool callable is undeclared

**Status**: ADVISORY

Section 5 defines the tool name `get_mock_finance_facts`, its schema, and its return JSON. Section 6 assertions reference `MockFinanceFactTool.call_count` and `MockFinanceFactTool.last_marker`. But Section 5 never declares the Python class name for the tool callable. The existing reference smoke uses `SmokeFactTool` as the class name; the plan should explicitly name the class (e.g., `ConversationMemorySmokeTool` or `MockFinanceFactTool`) in Section 5 so the implementation worker doesn't need to invent it.

**Recommendation**: Add a line in Section 5: "Python 工具类名：`MockFinanceFactTool`，参考 `SmokeFactTool` 的模式实现 `__call__`。"

---

## Finding 2 — ADVISORY: `pressure_blob` inclusion logic is underspecified

**Status**: ADVISORY

Section 5 defines `include_pressure` as a required boolean parameter in the tool schema, and Round 1's prompt passes `include_pressure=true`. But the plan never specifies what the tool should do when `include_pressure=false`. The return JSON shows `pressure_blob` as a top-level field with a note saying "optional deterministic repeated text." The implementation worker needs to decide: always include `pressure_blob` (ignore the parameter), include conditionally, or omit the field entirely when false.

**Recommendation**: Specify the behavior: "当 `include_pressure=true` 时，返回结果包含 `pressure_blob` 字段（~120K chars）；当 `include_pressure=false` 时，`pressure_blob` 为 `null` 或空字符串。"

---

## Finding 3 — ADVISORY: Session snapshot assertion is conditional without fallback

**Status**: ADVISORY

Section 7 hard assertions include: "如 public snapshot 字段显示 `active_run_id is None` 且 `queued_run_ids == ()`，则断言。" The "如" (if) makes this conditional — but the plan doesn't specify what the smoke should do when the condition is NOT met. Between rounds, a background compact or lane scheduling could leave `active_run_id` non-None transiently. The existing reference smoke doesn't make this assertion at all; it only prints `SMOKE SESSION_STATUS`.

**Recommendation**: Either (a) make this a soft/log observation instead of a hard assertion, or (b) add a brief retry loop (e.g., poll `get_session` up to 3 times with 1s intervals) and specify the failure message when the condition never materializes.

---

## Finding 4 — ADVISORY: Round 3 (topic shift) signal depends on NPL ratio being in visible context

**Status**: ADVISORY

Round 3 asks the model for NPL ratio (`npl_ratio=0.94%`) without tools. The plan correctly notes this round "不作为核心 pass/fail." However, the NPL ratio value exists only in the tool's return JSON (`facts.npl_ratio`), not in the `assertion_line` (which covers only NIM and YoY). If the model's context was compacted between Rounds 2 and 3, the raw tool result containing `npl_ratio` may have been evicted, and the episode summary may or may not carry it. This means Round 3 could produce "不确定" even under correct memory behavior — which is fine per the plan's soft assertion — but it also means Round 3 provides negligible signal one way or the other.

**Recommendation**: Either (a) include `npl_ratio=0.94%` in the `assertion_line` so it's more likely to survive compaction, or (b) explicitly document that Round 3 is purely for topic-shift pressure and its answer content carries no pass/fail weight.

---

## Finding 5 — ADVISORY: Tool instance access path is not documented

**Status**: ADVISORY

Section 6 asserts `MockFinanceFactTool.call_count == 1` and `MockFinanceFactTool.last_marker == "..."`. The existing reference smoke accesses the tool instance via `_find_smoke_tool(assembly.effective_tool_bundle)` which walks `tool_bundle.definitions` looking for a callable of type `SmokeFactTool`. The plan assumes but doesn't state that the new smoke should follow this same pattern. A naive implementation might try to hold a separate global counter, which would be fragile.

**Recommendation**: Add a sentence in Section 6 or Section 8: "工具实例通过 `_find_smoke_tool(assembly.effective_tool_bundle)` 从 tool bundle 中按类型取出（参考 `SmokeFactTool` 模式），不依赖模块级全局变量。"

---

## Finding 6 — ADVISORY: Constants inventory is incomplete

**Status**: ADVISORY

Section 8 requires "常量化所有 smoke marker、工具名、scene id、slot key、stdout marker、pressure 参数." The plan names several constants inline (`_SMOKE_TOOL_PRESSURE_CHARS = 120_000`, scene id `smoke_host_public_conversation_memory`, tool name `get_mock_finance_facts`) but doesn't provide a consolidated constants inventory. The implementation worker will need to define module-level `Final` constants for at least: scene id, slot key prefix, tool name, tool tag, provider spec id, provider import path, smoke marker, client request prefix, default subject, default user, final preview chars, pressure chars, terminal timeout — mirroring the existing smoke's constant block (lines 94-114 of the reference).

**Recommendation**: Add a subsection in Section 5 or Section 8 listing the required `Final` constants with their proposed values.

---

## Finding 7 — ADVISORY: Dual pressure mechanism relationship is implicit

**Status**: ADVISORY

Section 5 says the tool result "可带 `_SMOKE_TOOL_PRESSURE_CHARS = 120_000` 左右的 `pressure_blob`." Section 6 Round 2 says "第二轮 prompt 再补 pressure padding." The plan references the existing smoke's adaptive `_compact_pressure_padding()` approach which calculates prompt padding such that (tool pressure + prompt pressure + base context) lands between soft and hard thresholds. But the plan doesn't explicitly state that the two pressure sources are additive and must be jointly calibrated against the same `context_budget_policy` thresholds. If the implementation worker treats them as independent, the combined pressure could overshoot the hard threshold.

**Recommendation**: Add a sentence: "工具 pressure 和 Round 2 prompt pressure 共享同一个 `context_budget_policy` 阈值计算，两者之和应落在 soft threshold 以上、hard threshold 以下。计算方式参考 `_compact_pressure_padding()` 与 `_compact_pressure_reserve_tokens()`。"

---

## Cross-cutting verification

### Scope and motivation — PASS

- Plan correctly identifies the source doc's scope mismatch (real Fins, DB reads, 20+ rounds) and narrows to the feasible subset.
- Explicitly states what is NOT proven: full Conversation Memory semantics, pinned_state monotonicity, compactor's internal write path.
- No overclaiming detected.

### Public API boundary — PASS

- Allowed: `open_host`, `ensure_session`, `submit_followup`, `watch_session_events`, `get_session`, `get_run`. All confirmed present in `Host` protocol (api.py:2724-2896).
- Disallowed: durable store, EventLog, memory tables, SQLite queries, internal compaction reads. Explicitly listed in Section 4.
- Assembly helpers (`ConfigLoader`, `resolve_runtime_locations`, `discover_service_tools`, `prepare_scene`, `compose_open_host_options`, `compose_submit_followup_request`) are correctly classified as pre-Host typed composition, not Host private internals.

### Scenario selection — PASS

- Test group D selected as primary path (NIM confirmed fact cross-round consistency). This is the right choice: it directly tests the "compaction → episode summary → confirmed facts survive → model answers from memory not tools" path.
- Test group B borrowed as auxiliary (continuity phrasing). Appropriate.
- Groups A (dual-company switch), C (8K-15K char disclosure), E (20+ round stability) correctly rejected.

### Mock tool design — PASS (with Advisory #1, #2)

- Schema is deterministic: 5 string params + 1 boolean, `additionalProperties=false`.
- Return JSON has unique marker, fixed values, and assertion line for downstream parsing.
- Values (`1.88%`, `-0.14pct`, `npl_ratio=0.94%`) are specific enough that random LLM output cannot coincidentally match.

### Round assertions can distinguish memory continuity — PASS

- Round 1: tool must be called once (proves fact was ingested via tool).
- Rounds 2-4: `tool_names=frozenset()` (proves no re-retrieval).
- Round 4: must contain marker + `1.88%` + `-0.14pct` (proves fact survived compaction/topic-shift).
- This combination rules out: tool re-calls (disabled), random guessing (values too specific), and hallucination-from-thin-air (marker is unique).

### Compaction pressure realism — PASS (with Advisory #7)

- Plan follows the existing smoke's proven approach: calculate thresholds from `context_budget_policy`, target between soft and hard.
- Compact observation is limited to artifact root/count (public `OpenHostOptions.compactor_runner_baseline.compact_artifact_root`), not internal reads.
- Acknowledged that proactive/background compact timing is not fully controllable — correctly classified as log observation, not hard assertion.

### Implementation slice size — PASS

- 3 new files + 1 README update. Single slice, no intermediate non-runnable states.
- Explicitly says "不要在本 work unit 重构既有 smoke" — good scope discipline.

### Project constraints — PASS

- Chinese docstrings: required in Section 8.
- Strict typing: no `Any`, `object`, untyped signatures — required.
- No magic strings: constants centralized — required.
- No `hasattr`/`getattr` abuse, no lazy imports — required.
- No reading durable DB/EventLog/memory tables — required.

### README decisions — PASS

- Root README update only (adjacent to existing smoke entry). Correct.
- `dayu/config/README.md`, `tests/README.md` not updated. Correct — no schema/config contract changes, no test classification changes.

### Risk acknowledgment — PASS

- LLM format non-compliance: handled via soft assertion for Round 2.
- Compaction timing: handled via log observation, not hard assertion.
- Environment failures vs code failures: implementation report must distinguish.
- Code duplication from reference: acknowledged as tradeoff, deferred to future refactor.

---

## Items confirmed correct

1. **Scene manifest structure** matches existing `smoke_host_public_multiturn.json` pattern (schema_version, scene, capability_tags, model, agent_policy, tool_selection, fragments, context_slots).
2. **`Host` protocol** (api.py:2724) exposes exactly the methods the plan lists. `SessionSnapshot` has `active_run_id`, `queued_run_ids`, `status`. `RunSnapshot` has `terminal_result_summary`.
3. **`SessionStatus`** is `OPEN | CLOSED` — "非关闭/异常" maps to `SessionStatus.OPEN`.
4. **`OpenHostOptions.compactor_runner_baseline.compact_artifact_root`** is a public `pathlib.Path` — safe to observe without private API access.
5. **`context_budget_policy`** is a public field on `OpenHostOptions` — threshold calculation is legitimate pre-Host math, not internal state reading.
6. **Tool selection**: `tool_names=assembly.scene_inputs.tool_selection.tool_names` for Round 1 and `frozenset()` for Rounds 2-4 — mirrors the reference smoke's correct pattern.
7. **Terminal failure summary** uses `host.get_run()` (public) with `_safe_summary_text()` sanitization — no private state exposure.
8. **Round 4 normalization**: whitespace stripping, fullwidth percent normalization, case normalization only — no semantic guessing. Correctly conservative.

---

## Final assessment

The plan is **implementation-ready**. All seven findings are advisory — none would cause the implementation worker to produce a broken or invalid smoke. The plan correctly constrains scope, enforces the public API boundary, designs assertions that can distinguish memory continuity from confounding factors, and respects all project constraints. The most impactful advisories are #2 (pressure_blob conditional logic) and #7 (dual pressure calibration), which the implementation worker should resolve during coding by referencing the existing smoke's `_compact_pressure_padding()` and `_tool_pressure_blob()` patterns.
