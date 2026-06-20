# WU-CLI-DEBUG-STREAM-01 Plan Re-Review

## Metadata

- **Work unit**: WU-CLI-DEBUG-STREAM-01
- **Gate**: re-review
- **Reviewer**: AgentDS (planreview skill, re-review mode)
- **Date**: 2026-06-20
- **Plan artifact**: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- **Plan fix artifact**: `docs/reviews/plan-fix-wu-cli-debug-stream-01-20260620.md`
- **Prior review artifacts**:
  - `docs/reviews/plan-review-wu-clli-debug-stream-01-mimo-20260620.md`
  - `docs/reviews/plan-review-wu-cli-debug-stream-01-ds-20260620.md`
- **Adjudication artifact**: `docs/reviews/plan-review-wu-cli-debug-stream-01-adjudication-20260620.md`
- **Re-review artifact**: `docs/reviews/plan-rereview-wu-cli-debug-stream-01-ds-20260620.md`

## Scope

This re-review gate only verifies whether the 5 accepted plan-review findings have been properly fixed in the plan fix artifact. No implementation, production code modification, commit, push, or next-gate entry is authorized.

Allowed files used:

- Added: `docs/reviews/plan-rereview-wu-cli-debug-stream-01-ds-20260620.md`

Files intentionally not changed:

- Plan artifact, fix artifact, production code, tests, README, control documents, prior review/adjudication artifacts.

## Accepted Findings — Fix Verification

### Finding 1: `--debug-stream` precedence is explicit

**Source**: DS F-1 / MiMo F-1
**Adjudication**: accepted
**Required**: `debug_stream=True` entering runtime logging resolves to `STREAM_DEBUG` before any parsed `log_level` value. CLI help / README plan says `--debug-stream` enables ordinary DEBUG plus stream diagnostics and discourages contradictory log flags.

**Evidence in plan (Decision 2, lines 101-107)**:
- `set_level_from_flags()` must resolve `debug_stream=True` to `LogLevel.STREAM_DEBUG` **before** any parsed `log_level` value.
- Plan explicitly states `--debug-stream` wins over `--debug`, `--verbose`, `--info`, `--quiet`, and `--log-level <level>`.
- CLI help and README wording must describe intended non-contradictory usage: `--debug-stream` enables ordinary DEBUG diagnostics plus high-frequency stream delta / SSE / per-delta ingest diagnostics. Users should not combine mutually contradictory log-level flags.

**Plan fix claim (DS F-1 / MiMo F-1)**: states the plan now contains the explicit precedence rule, the most-verbose diagnostic request definition, and the CLI help / README wording requirement.

**Verdict**: 已修复 — plan text matches fix claim exactly. The precedence rule is explicit, implementation-ready, and consistent with the adjudicated behavior.

---

### Finding 2: Slice 2 requires renaming old Host logging test

**Source**: DS F-2
**Adjudication**: accepted
**Required**: Rename `test_engine_ingest_delta_events_use_debug_log_level` to a stream-debug-specific name.

**Evidence in plan (Slice 2, line 190)**:
- "Rename the old `tests/host/test_logging.py` test `test_engine_ingest_delta_events_use_debug_log_level` to a stream-debug-specific name, for example `test_engine_ingest_delta_events_use_stream_debug_log_level`."

**Plan fix claim (DS F-2)**: states Slice 2 now explicitly requires the rename.

**Verdict**: 已修复 — the test rename is explicitly listed as an exact change in Slice 2.

---

### Finding 3: Combined `--debug --debug-stream` test

**Source**: DS F-3
**Adjudication**: accepted
**Required**: Slice 1 expected assertions must include combined parsing and runtime resolution tests for `--debug` with `--debug-stream`.

**Evidence in plan (Slice 1, lines 164, 168)**:
- Combined parsing assertion: `parse_cli_args(("prompt", "x", "--debug", "--debug-stream"))` accepts both flags, keeps `debug_stream is True`, and resolves the ordinary debug flag into the parsed log-level field (line 164).
- Combined runtime resolution assertion: `set_level_from_flags(log_level="debug", debug_stream=True, ...) is LogLevel.STREAM_DEBUG`, covering combined `--debug` and `--debug-stream` runtime resolution (line 168).

**Plan fix claim (DS F-3)**: states Slice 1 now requires both a combined parsing test and a combined runtime resolution coverage test.

**Verdict**: 已修复 — both the parsing-level and runtime-resolution combined tests are now explicitly listed in Slice 1 expected assertions.

---

### Finding 4: `main()` initial and cleanup spy assertions both carry `debug_stream`

**Source**: MiMo F-2
**Adjudication**: accepted
**Required**: Slice 1 expected assertions must require both initial and cleanup `set_level_from_flags()` calls to carry `debug_stream`.

**Evidence in plan (Slice 1, lines 165-166)**:
- "`main(("prompt", "x", "--debug-stream"))` passes `debug_stream=True` and `log_level="info"` to runtime log assembly for both the initial configuration call and the cleanup reconfiguration call."

**Plan fix claim (MiMo F-2)**: states Slice 1 now requires spy coverage for both the initial runtime logging configuration call and the cleanup reconfiguration call, both carrying `debug_stream=True` and the parsed `log_level` value.

**Verdict**: 已修复 — the cleanup path is now explicitly named alongside the initial configuration call in Slice 1 expected assertions.

---

### Finding 5: Deferred items remain correctly scoped

**Source**: DS F-4, DS F-5 / MiMo residual, memory_repair exclusion
**Adjudication**: deferred-with-owner (DS F-4, DS F-5) or excluded (memory_repair)
**Required**: No plan changes; verify the fix correctly defers these items.

**Evidence**:

- **DS F-4 (ParsedCliArgs construction sites)**: Plan fix defers to implementation gate with explicit owner. The plan already covers this in Slice 3: "If tests manually instantiate `ParsedCliArgs`, add `debug_stream=False`." The fix gate correctly does not inspect or edit production/test construction sites.
- **DS F-5 / MiMo residual (README `critical` mismatch)**: Plan fix defers to separate cleanup work unit. The plan already identifies this as a pre-existing docs/parser mismatch outside Issue 148 scope in Residual Risks (line 307). The fix correctly avoids scope creep.
- **memory_repair.catch_up.budget_exhausted**: Plan fix confirms this remains excluded as an already-fixed bug / no-regression verification point. Plan's Non-Goals (line 23) and First-Principles section (line 54) correctly state current code has no `BUDGET_EXHAUSTED` stop reason.

**Verdict**: 已修复 — all three items are correctly deferred or excluded per adjudication. The fix gate properly respects its scope boundary.

---

## Fix Artifact Self-Consistency Check

The plan fix artifact (`plan-fix-wu-cli-debug-stream-01-20260620.md`) claims 4 findings as "已修复" (DS F-1/MiMo F-1, DS F-2, DS F-3, MiMo F-2) and 2 as "deferred-with-owner" (DS F-4, DS F-5/MiMo residual). Each claim has been independently verified against the current plan text:

| Fix claim | Plan text location | Match |
|---|---|---|
| Precedence rule explicit in Decision 2 | Decision 2, lines 101-107 | ✓ |
| Test rename in Slice 2 | Slice 2, line 190 | ✓ |
| Combined parsing/runtime test in Slice 1 | Slice 1, lines 164, 168 | ✓ |
| Cleanup spy assertion in Slice 1 | Slice 1, lines 165-166 | ✓ |
| DS F-4 deferred to impl | Fix §DS F-4, Plan Slice 3 | ✓ |
| DS F-5 deferred to cleanup | Fix §DS F-5, Plan Residual Risks line 307 | ✓ |

No inconsistencies found between fix claims and plan text.

## Overall Verdict

**PASS**

All 5 accepted plan-review findings have been properly fixed in the plan artifact. No new issues introduced by the fix. The plan is ready for implementation gate.

## Accepted Finding Final Statuses

| # | Finding | Status |
|---|---|---|
| 1 | `--debug-stream` precedence is explicit | 已修复 |
| 2 | Slice 2 requires renaming old Host logging test | 已修复 |
| 3 | Slice 1 requires combined `--debug --debug-stream` parsing/runtime tests | 已修复 |
| 4 | Slice 1 requires main() initial and cleanup spy assertions both carry `debug_stream` | 已修复 |
| 5 | Deferred items (ParsedCliArgs construction, README `critical` mismatch, memory_repair exclusion) | 已修复 |

## Residual Risks / Uncovered Areas

1. **Implementation fidelity**: The plan fix only updates the plan text. Whether implementation correctly follows the explicit precedence rule, test rename, combined test assertions, and cleanup spy assertions depends on implementation gate execution. Risk remains at implementation level only.

2. **`ParsedCliArgs` construction-site verification**: Deferred to implementation gate. If `debug_stream: bool` is added without a default value, pyright may flag keyword-argument construction sites in existing tests. Implementation must verify all sites.

3. **README `critical` mismatch**: Pre-existing, outside scope, not worsened by this WU. Remains unresolved and owned by a separate cleanup work unit.

4. **Future stream diagnostics at wrong level**: Plan-level mitigation exists (tests assert expected levels, README defines distinction). Implementation must uphold this.

5. **`--debug-stream` + contradictory quiet flags**: Plan now explicitly defines precedence and requires CLI help / README to discourage contradictory combinations. The resolution (`--debug-stream` wins) is mechanically simple and consistent with the flag's purpose as the most-verbose diagnostic request. No additional plan change needed.

No blocking residual risks. The plan is implementation-ready.
