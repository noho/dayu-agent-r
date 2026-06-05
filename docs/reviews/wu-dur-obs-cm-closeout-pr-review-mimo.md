# PR 118 Draft Review — WU-DUR/OBS/CM Closeout

- **Reviewer**: AgentMiMo
- **Date**: 2026-06-05
- **Branch**: `phaseflow/wu-dur-obs-cm-closeout` -> `main`
- **Verdict**: **pass**

---

## Summary

PR 118 closes the WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01 closeout chain. The scope includes:

1. **Durable runner-call reconstruction atoms**: `RUNNER_CALL_INPUT_ASSEMBLED` canonical fact with manifest payload descriptor, `RUNNER_CALL_INPUT_ITERATION_LINKED` correlation event, fail-closed handling for missing/ambiguous/mismatch/link conflict cases.
2. **Compactor proposal manifests**: `DurableCompactorProposalManifestRecorder` writing durable manifests before each compactor proposal runner call, with first-proposal vs retry trigger reason distinction.
3. **Tool-call request durable atoms**: `TOOL_CALL_REQUESTED` accepted arguments cold-hot separation (inline JSON / payload descriptor), optional semantic query atom, digest validation.
4. **One-system-message envelope**: Ordinary RunInput normalizes to at most one leading system envelope with user/assistant roles preserved.
5. **Compaction prompt rewrite**: LLM-facing compaction prompts now self-document input JSON, output JSON fields, label rules, and minimum examples.
6. **Evidence query readability**: Compact evidence `query_text` consumes durable tool-call request atoms (semantic query or bounded arguments JSON) instead of raw `tool_call_id`.
7. **Tool Trace reconstruction signals**: `RunnerCallReconstructionSignal` read-model with typed diagnostic, by-Run query helper.
8. **Compaction outcome cross-reference**: Accepted/rejected compact payloads carry proposal manifest ref/digest pairs.

137 files changed, ~21k lines added. Tests, pyright, and public smoke all pass.

---

## Blocking Findings

**None.**

---

## Non-blocking Findings / Residuals

### 1. WU-DUR-P01 status label: `completed-with-residuals`

- **Location**: `docs/host/issues-implementation-control.md:296`
- **Evidence**: The residual risk table (lines 276-280) shows all WU-DUR-P01 residuals as `closed` or `transferred-to-issue`. The work unit status `completed-with-residuals` is technically stale since all residuals are resolved.
- **Severity**: informational — does not block PR.
- **Owner**: control doc maintainer (PR author).
- **Recommendation**: After PR merge, update WU-DUR-P01 status to `completed` since all residuals are closed or transferred.

### 2. WU-ENG-02-S3-R1 transferred to issue #119

- **Location**: `docs/host/issues-implementation-control.md:280`
- **Evidence**: Issue #119 exists and is OPEN with proper scope definition. Transfer is documented in the residual table.
- **Severity**: non-blocking — properly transferred with owner.

### 3. Real compactor smoke remains environment-gated

- **Location**: PR body residual risk section
- **Evidence**: `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` gate is by design. Deterministic fake compactor covers the test path.
- **Severity**: non-blocking — documented and intentional.

---

## Evidence Reviewed

### Code Changes (key files)

| File | Lines Added | Key Changes |
|---|---|---|
| `dayu/host/engine_ingest.py` | ~1577 | Runner-call manifest recording, iteration link resolution, fail-closed validation, continuation limited-signal |
| `dayu/host/run_input.py` | ~1381 | One-system-message normalization, runner-call manifest body construction, manifest recorder protocol |
| `dayu/host/compaction_operation.py` | ~887 | `CompactorProposalRunInput`, `DurableCompactorProposalManifestRecorder`, proposal manifest body |
| `dayu/host/tool_trace.py` | ~325 | `RunnerCallReconstructionSignal` read-model, by-Run query helper |
| `dayu/host/durable/tool_trace.py` | ~522 | Typed reconstruction enums, signal parsing, diagnostic validation |
| `dayu/host/durable/schema.py` | ~35 | New descriptor kind and schema version constants |
| `dayu/host/compaction_evidence.py` | ~124 | Durable request atom consumption for `query_text` |
| `dayu/host/context_events.py` | ~51 | Optional ref/digest pair fields and validation |
| `dayu/host/dispatch.py` | ~71 | Compactor proposal manifest recorder wiring |
| `dayu/host/payload_resolution.py` | ~272 | `ToolCallRequestAtoms`, arguments/semantic query resolution |
| `dayu/host/llm_compaction.py` | ~167 | `prepare_compactor_proposal_run_input`, `run_prepared_compactor_proposal` |
| `dayu/engine/contracts/engine_events.py` | ~25 | `RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION`, `runner_role_sequence_digest` |
| `dayu/engine/agent.py` | ~18 | Role sequence digest computation in `IterationStartedData` |
| `dayu/config/prompts/scenes/conversation_compaction.md` | ~10 | Semantic rewrite: self-documenting system prompt |
| `dayu/config/prompts/scenes/conversation_compaction_user.md` | ~59 | Full input/output JSON schema, label rules, minimum example |

### Design & Documentation

| Document | Changes |
|---|---|
| `docs/host/design.md` | +257 lines: runner-call reconstruction, durable tool-call atoms, cold-hot separation, compaction manifest contract |
| `docs/host/issues-implementation-control.md` | +62/-13: residual table updates, work unit status updates |
| `dayu/host/README.md` | +9/-6: runner-call manifest, tool-call request atoms, evidence query readability, compaction manifest |
| `dayu/config/README.md` | +3/-1: compaction prompt LLM-facing constraint |
| `dayu/engine/README.md` | +2: role sequence digest |

### Tests

| Test File | Coverage |
|---|---|
| `test_engine_ingest_mapping.py` | +1127 lines: ordinary manifest, iteration link, fail-closed, continuation limited-signal |
| `test_compaction_operation.py` | +755 lines: proposal manifest, trigger reason, manifest body validation |
| `test_run_input_builder.py` | +267 lines: one-system-message envelope, manifest bounded, role digest |
| `test_tool_trace_projection.py` | +323 lines: runner-call signal, diagnostic, by-Run query |
| `test_tool_trace_queries.py` | +151 lines: typed reconstruction signal queries |
| `test_toolruntime_accept_barrier.py` | +275 lines: tool-call request atoms, digest validation |
| `test_context_compact_events.py` | +84 lines: proposal manifest ref/digest pairs |
| `test_public_compact_smoke.py` | +194 lines: compactor manifest bounded, prompt self-documenting |
| `test_public_tool_wiring_smoke.py` | +9 lines: one-system-message assertion |
| Other test files | Minor additions for schema, durable, engine event contract |

### Residual Table Audit

| Residual ID | Status | Verified |
|---|---|---|
| WU-DUR-P01-S2-R2 | closed | Yes — implementation report exists |
| WU-DUR-P01-S3-R1 | closed | Yes — trigger reason enum precision implemented |
| WU-DUR-P01-S3-R2 | closed | Yes — outcome cross-reference contract codified |
| WU-CM-01-F01-S7-R1 | closed | Yes — one-system-message assembly accepted |
| WU-ENG-02-S3-R1 | transferred-to-issue | Yes — issue #119 OPEN with proper scope |

No open or ownerless residual items.

---

## Validation Commands

```
# Engine tests
pytest tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase3_tool_call.py -q
# Result: 56 passed

# Host mapping/trace tests
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q
# Result: 105 passed

# Compaction/run_input tests
pytest tests/host/test_compaction_operation.py tests/host/test_run_input_builder.py -q
# Result: 89 passed

# Public smoke tests
pytest tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q
# Result: 13 passed, 1 skipped

# Pyright
pyright --stats
# Result: 0 errors

# Working tree
git status
# Result: clean
```

---

## Draft-PR-Pass Recommendation

**PASS.** No blocking findings. All residual items have owners. Tests, pyright, and public smoke pass. Design doc, README, and control doc are consistent with code. LLM-facing prompts are self-documenting and follow the Agent 语义约束. The PR is ready for draft-PR-pass gate.
