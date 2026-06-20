# WU-CLI-DEBUG-STREAM-01 Plan Review

## Review Metadata

- **Work unit:** WU-CLI-DEBUG-STREAM-01
- **Plan artifact:** `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- **Reviewer:** AgentDS (planreview skill)
- **Date:** 2026-06-20
- **GitHub Issue:** [#148](https://github.com/noho/dayu-agent-r/issues/148)
- **Gate:** Plan review
- **Review scope:** plan only; no production code, tests, commit, push, or PR authorized

## Evidence Sources

- Plan artifact: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`
- GitHub Issue #148
- `dayu/runtime/log_levels.py`
- `dayu/runtime/log.py`
- `dayu/cli/arg_parsing.py`
- `dayu/cli/main.py`
- `dayu/host/engine_ingest.py` (lines 206-212 `_DELTA_ENGINE_EVENT_TYPES`; lines 700-712 `_ingest_before_reactive_compaction` accepted log; lines 758-778 `_finish_ingest` committed log; lines 3256-3265 `_engine_ingest_log_level`)
- `dayu/engine/runners/openai/runner.py` (line 374 `runner.attempt.start`; line 582 `runner.http.post`; line 608 `runner.http.response`; line 898 `runner.stream_idle.heartbeat`)
- `dayu/engine/runners/openai/sse_parser.py` (line 346 `sse.done_token received`)
- `dayu/host/memory_repair.py` (lines 33-38 `MemoryProjectionRepairStopReason`)
- `tests/host/test_logging.py` (lines 180-193 `test_engine_ingest_delta_events_use_debug_log_level`)
- `README.md` (line 290 `--log-level` choices)

## Alignment Verification

### GitHub Issue #148 Scope Match

**PASS.** The plan's goal, success signals, non-goals, and scope boundary map exactly to Issue #148:

| Issue requirement | Plan coverage |
|---|---|
| `--debug` no longer emits per-delta ingest logs | Decision 3, Slice 2 |
| `--debug-stream` enables per-delta diagnostics | Decision 1, Slice 2 |
| `--debug` and `--debug-stream` combinable | Decision 2 |
| README/CLI help distinction | Slice 4 |
| CLI parsing + log behavior tests | Slices 1–3 |
| No activity stream change | Non-Goals |
| No Host/Engine event contract change | Contract section |
| No content values in logs | Decision 5 |

### Design Source Alignment

**PASS.** Plan respects `UI -> Service -> Host -> Engine` layering (`docs/host/design.md`):

- The `--debug-stream` flag is a CLI (UI layer) parameter, resolved in `dayu/cli/main.py` and `dayu/runtime/log.py`
- Host `engine_ingest.py` only imports the new level constant from `dayu.runtime.log_levels` — no CLI state leaks into Host
- Engine `runner.py` / `sse_parser.py` only change log call levels — no Engine contract changes
- No Service layer changes needed
- No reverse dependencies introduced

Plan also correctly maps to `docs/engine/design.md` stream terminology (§1.1):
- `EngineEvent stream` — not changed
- `RunnerEvent stream` — not changed
- `SSE stream` / provider streaming — gated diagnostics only
- `Host event stream` — not changed
- `content_delta` / `reasoning_delta` / `tool_call_delta` — only log level change, no durable semantic change

### Control Document Compliance

**PASS against `docs/host/issues-implementation-control.md`:**

- Plan is based on direct code evidence, design sources, and GitHub Issue scope (§工作流)
- Plan explicitly lists non-goals and scope boundary (§工作流 discussion checklist)
- Plan avoids over-design (§工作流 "不得把局部缺口扩大成通用框架")
- Plan does not modify design source (§真源层级)
- Plan respects `memory_repair.catch_up.budget_exhausted` exclusion (control doc §当前状态: "Plan gate explicitly excludes budget_exhausted")
- Plan does not update control doc (plan §Non-Goals: "由 phaseflow 总控在后续 gate 处理")

## Findings

### F-1: `--debug-stream` resolution order relative to boolean flags is underspecified (MEDIUM)

**Severity:** MEDIUM
**Evidence:** Plan §Implementation Decisions item 2; `dayu/runtime/log.py:218-245` `_resolve_level()`

The plan states: "`set_level_from_flags()` should resolve `debug_stream=True` to `LogLevel.STREAM_DEBUG` before ordinary `log_level` strings." The current `_resolve_level()` has a 6-step priority chain: `log_level` string → `quiet` → `debug` → `verbose` → `info` → default INFO. The plan only specifies where `debug_stream` falls relative to `log_level` string, but not relative to `quiet`, `verbose`, or `info` booleans.

For example, `dayu-cli prompt "x" --debug-stream --quiet` has two explicit user intents: "show me all stream diagnostics" and "only show errors." The plan's residual risk section acknowledges this tension but Slice 1's implementation spec should include the full resolution order to avoid implementation ambiguity.

**Recommendation:** Add explicit full priority chain to plan or Slice 1 spec: `debug_stream` → `log_level` string → `quiet` → `debug` → `verbose` → `info` → default INFO. The plan should also consider whether the CLI help for `--debug-stream` should warn about the override behavior (e.g., "Overrides all other log-level flags").

**Adjudication categories:** accepted / rejected-with-reason / deferred-with-owner

---

### F-2: Test function name becomes misleading after level change (MEDIUM)

**Severity:** MEDIUM
**Evidence:** `tests/host/test_logging.py:180` — `test_engine_ingest_delta_events_use_debug_log_level`

The test currently asserts:
```python
assert _engine_ingest_log_level(EngineEventType.CONTENT_DELTA) == logging.DEBUG
```

After Slice 2 implementation, delta events will use `STREAM_DEBUG_LOG_LEVEL` (= 9), not `logging.DEBUG` (= 10). While the plan's Slice 2 mentions updating tests, it does not explicitly call out that the test function name should be renamed to reflect the new semantics (e.g., `test_engine_ingest_delta_events_use_stream_debug_log_level`). Keeping the old name would be misleading to future readers who may assume `DEBUG` still applies to delta ingest.

**Recommendation:** Slice 2 "Exact changes" should explicitly list this test rename.

**Adjudication categories:** accepted / rejected-with-reason

---

### F-3: Missing explicit combined `--debug --debug-stream` test (LOW)

**Severity:** LOW
**Evidence:** Plan §Slice 1 "Expected assertions"

Slice 1 lists individual flag parsing tests (`--debug-stream` alone) but does not include a combined assertion. Since `--debug` writes to `dest="log_level"` and `--debug-stream` would write to `dest="debug_stream"`, there should be no argparse-level conflict. However, a combined test would:
1. Verify argparse accepts both flags simultaneously
2. Verify the resolution function correctly picks STREAM_DEBUG when both are present
3. Prevent future refactoring from accidentally making the flags mutually exclusive

**Recommendation:** Add to Slice 1 expected assertions: `parse_cli_args(("prompt", "x", "--debug", "--debug-stream")).debug_stream is True` or equivalent combined test.

**Adjudication categories:** accepted / deferred-with-owner

---

### F-4: `ParsedCliArgs` construction in prompt/interactive tests may need attention (LOW)

**Severity:** LOW
**Evidence:** Plan §Slice 3; `dayu/cli/arg_parsing.py:122-186` `ParsedCliArgs`

The plan says: "If tests manually instantiate `ParsedCliArgs`, add `debug_stream=False`." `ParsedCliArgs` extends `argparse.Namespace`, which accepts arbitrary attribute assignment at runtime. Adding `debug_stream: bool` as a type annotation without a default value means type checkers (pyright) will flag test code that constructs `ParsedCliArgs()` without the field as potentially missing an attribute — but only if tests use keyword-argument construction rather than attribute assignment.

Since the plan delegates this to Slice 3 as a compatibility concern, the risk is low, but the plan could be more precise about the expected construction patterns in existing tests.

**Recommendation:** During Slice 3 implementation, verify that all `ParsedCliArgs` construction sites (keyword-argument or attribute-assignment) work correctly with the new field. No plan change required.

**Adjudication categories:** deferred-with-owner (implementation gate)

---

### F-5: Pre-existing README `critical` mismatch should not be worsened (INFO)

**Severity:** INFO
**Evidence:** `README.md:290` lists `critical` as valid `--log-level` choice; `dayu/cli/arg_parsing.py:17-23` `LOG_LEVEL_CHOICES` excludes `critical`

The plan correctly identifies this as a pre-existing mismatch and explicitly excludes it from scope ("Root README currently mentions `critical` for `--log-level` while parser choices in `dayu/cli/arg_parsing.py` do not include it. This is a pre-existing documentation/parser mismatch outside Issue #148").

When updating `README.md` to add `--debug-stream`, the plan should ensure the update does not accidentally expand the `--log-level` choices column to include `critical` or other unsupported values. The plan's Slice 4 language is adequate: "In root README CLI shared parameters, add `--debug-stream` and explain..."

**Recommendation:** No action needed — informational observation. The pre-existing mismatch should be addressed in a separate cleanup work unit or issue.

**Adjudication categories:** N/A (info only)

---

## Specific Challenge Responses

### Challenge 1: Custom STREAM_DEBUG level vs. filter/module override

**Verdict: Plan's approach is correct and not over-designed.**

The plan proposes `STREAM_DEBUG_LOG_LEVEL = 9` (below `DEBUG = 10`). This is the right choice:

- **Mechanically clean:** stdlib logging uses `level >= threshold`. Setting the logger to STREAM_DEBUG (9) emits everything at 9+, including ordinary DEBUG (10). Setting to DEBUG (10) excludes level-9 stream records. No dynamic record inspection needed.
- **Follows local precedent:** `VERBOSE = 15` is already a Dayu custom level registered via `logging.addLevelName()`. STREAM_DEBUG follows the same pattern.
- **No coupling to module names:** A filter approach would need to know which logger names or message patterns count as "stream" diagnostics. A module-override approach would need a hardcoded list that breaks when code moves. The level-based approach leaves classification to the producer and threshold to the consumer.
- **No new public surface:** Only one new integer constant added to the existing `dayu.runtime.log_levels` module.

The plan's defense in "Why This Is Not Over-Designed" is accurate: one global CLI flag, one runtime logging level, reclassification of existing high-frequency records.

### Challenge 2: `--debug-stream` alone = most verbose — CLI user semantics

**Verdict: Self-consistent but the plan could be more explicit about the override behavior.**

The plan's position is that `--debug-stream` always resolves to STREAM_DEBUG, regardless of other log-level flags. This is internally consistent because:

1. `--debug-stream` explicitly requests stream delta diagnostics.
2. Stream delta diagnostics require seeing ordinary DEBUG records to be useful (you need both "runner.attempt.start" and "delta accepted" to correlate).
3. The flag name `--debug-stream` implies "stream-aware debug mode," not "add stream diagnostics to whatever level I'm at."

The plan's residual risk section acknowledges the conflict with quieter flags. The CLI help text (Slice 1) should make this explicit: "single use enables normal DEBUG plus stream delta / SSE diagnostics" is stated in the plan. I recommend adding: "overrides --log-level, --quiet, --verbose, and --info" to the help text.

### Challenge 3: Old `--debug-sse` / `--debug-tool-delta`

**Verdict: Plan correctly preserves these as unsupported execution options.**

The plan (Decision 4) correctly identifies that `--debug-sse` and `--debug-tool-delta` are legacy Agent execution parameters registered via `_add_agent_execution_arguments()` on `prompt`/`interactive`/`session resume` commands. `--debug-stream` is a global CLI logging switch. These are categorically different:

- Old flags: per-command Agent execution parameters, unsupported, on specific subcommands
- New flag: global parent parser, logging infrastructure, all commands

The plan explicitly states `--debug-stream` should NOT be added to `unsupported_execution_option_names()`. This is correct.

### Challenge 4: `memory_repair.catch_up.budget_exhausted` exclusion

**Verdict: Plan correctly excludes this — it is not a current code fact.**

Direct evidence:
- `dayu/host/memory_repair.py:33-38`: `MemoryProjectionRepairStopReason` has only `IDLE`, `TARGET_REACHED`, `FAILURE` — no `BUDGET_EXHAUSTED`
- The `_log_repair_result()` function warns only on `result.failures > 0`; success catch-up uses `VERBOSE_LOG_LEVEL`
- WU-CLI-ACTIVITY-01 follow-up Slice 4 (commit `794d3b74`) already removed `MemoryProjectionCatchupBudget` and `BUDGET_EXHAUSTED` semantics

The plan's non-goal language is precise: "不修复 `memory_repair.catch_up.budget_exhausted`。当前代码已经没有该 stop reason；本 WU 只把它作为不回归核对项。"

### Challenge 5: Missing tests, README, or pyright

**Verdict: Plan has adequate coverage but see F-2, F-3 above.**

The plan's test coverage is comprehensive:
- `tests/runtime/test_log.py` + `tests/runtime/test_log_levels.py` — runtime log assembly
- `tests/cli/test_arg_parsing.py` — flag parsing
- `tests/host/test_logging.py` — Host ingest log level
- `tests/engine/runners/openai/test_runner_diagnostics.py` — runner/SSE log levels
- Prompt/interactive CLI tests — compatibility

Pyright validation is included in the plan's validation commands. README updates are scoped in Slice 4.

Gaps identified: F-2 (test rename), F-3 (combined flag test). Neither is blocking.

### Challenge 6: Over-design or cross-layer leakage

**Verdict: No over-design, no cross-layer leakage.**

The plan adds:
- One global CLI flag (UI layer)
- One runtime logging level constant (runtime layer, layer-neutral)
- Level reclassification in Host ingest + Engine runner/SSE (importing the new constant)

It does NOT add:
- New Host/Engine request fields
- Host/Engine event contract changes
- Config files, logger registries, dynamic filters
- Durable schema changes
- Activity stream changes
- Cross-layer state passing (CLI flag stays in CLI; Host/Engine only see the log level constant)

## Overall Verdict

**PASS_WITH_FINDINGS**

The plan is code-generation-ready with two medium findings (F-1, F-2) and one low finding (F-3) that should be addressed before or during implementation. No blocking issues found.

### Findings Summary

| ID | Severity | Summary | Recommendation |
|---|---|---|---|
| F-1 | MEDIUM | `debug_stream` resolution order relative to boolean flags (quiet/verbose/info) is underspecified in `_resolve_level()` | Add full priority chain to plan: `debug_stream` → `log_level` string → `quiet` → `debug` → `verbose` → `info` → default |
| F-2 | MEDIUM | `test_engine_ingest_delta_events_use_debug_log_level` name becomes misleading | Explicitly list test rename in Slice 2 |
| F-3 | LOW | Missing combined `--debug --debug-stream` parsing test | Add combined test assertion to Slice 1 |
| F-4 | LOW | `ParsedCliArgs` construction in existing tests may need `debug_stream=False` | Verify during Slice 3 implementation |
| F-5 | INFO | Pre-existing `critical` in README `--log-level` choices not in `LOG_LEVEL_CHOICES` | Don't worsen; fix in separate WU |

### Residual Risks / Uncovered Areas

1. **Future stream diagnostics at wrong level:** The plan acknowledges this (Residual Risks §1). Mitigation exists (tests assert expected levels, README defines distinction). **Risk: LOW.**

2. **`--debug-stream` + quieter flag conflict:** The plan acknowledges this (Residual Risks §2). CLI help should explicitly state the override behavior. **Risk: LOW.**

3. **Per-SSE-chunk or per-byte content logging:** The plan correctly states it "must not add one just to satisfy the flag." Existing stream diagnostics are the only targets. **Risk: NONE — explicitly excluded.**

4. **README `critical` mismatch:** Pre-existing, outside scope. Plan correctly identifies and excludes it. **Risk: NONE — deferred to separate cleanup.**

5. **Uncovered area:** The plan does not discuss whether `dayu/host/README.md` or `dayu/engine/README.md` need updates. The plan's decision is "likely not" because no public contract changes. This is reasonable because the new `STREAM_DEBUG_LOG_LEVEL` constant is a runtime infrastructure detail, not a Host/Engine package API. The plan says to "re-check after implementation diff" — this is adequate. **Risk: LOW.**

6. **Uncovered area:** No specific discussion of how `STREAM_DEBUG_LOG_LEVEL` interacts with third-party logger suppression (`_DEFAULT_THIRD_PARTY_SUPPRESSIONS`). Since the new level only affects `dayu` namespace logger and doesn't change `_DEFAULT_THIRD_PARTY_LEVEL = WARN_LOG_LEVEL`, third-party suppression is unaffected. **Risk: NONE.**
