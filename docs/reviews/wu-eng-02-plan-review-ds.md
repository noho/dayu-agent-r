# WU-ENG-02 Plan Review — AgentDS

## Review Target / Gate

- **plan artifact**: `docs/host/wu-eng-02-provider-request-identity-plan.md`
- **gate**: plan review
- **reviewer**: AgentDS (adversarial, no implementation, no plan modification)
- **input documents**: `docs/host/design.md`, `docs/host/issues-implementation-control.md`
- **related issues**: #63, #64; #70 (subsequent Tool Trace analyzer consumer)

## Review Summary

| Dimension | Verdict |
|---|---|
| Motivation validity | pass |
| Direct code evidence | pass |
| Architecture adherence (UI→Service→Host→Engine) | pass-with-findings |
| Over-design risk | pass |
| Test matrix completeness | pass-with-findings |
| AGENTS.md compliance | pass |
| README sync triggers | pass |
| Schema change risks | pass |

**Overall**: pass-with-findings

---

## Findings

### Finding 1 (MEDIUM) — Force-answer / continuation runner call index semantics unspecified

**Direct evidence**: Plan §Slice 1 Exact Changes: "Add `_runner_call_index` counter to `_AsyncAgent`. In `_run_iteration`, build identity from ... incremented call index." But `_AsyncAgent` in `dayu/engine/agent.py` has three internal paths that call `_run_runner_iteration`:
- Main iteration loop (line 651)
- `_run_force_answer` (line 1938)
- Length continuation (also re-enters main loop but via `continue`)

**Impact**: If force_answer/continuation calls share the same counter, their `client_correlation_id` digests will be distinct and correct. If the counter is NOT incremented for these paths, it's a bug. The plan is ambiguous.

**Suggested fix**: In Slice 1 exact changes, explicitly state: "`_runner_call_index` is incremented on every call to `_run_runner_iteration`, including force-answer fallback and length-continuation re-entries." Or conversely, state if continuation deliberately reuses the previous value.

### Finding 2 (MEDIUM) — `request_identity: RunnerRequestIdentity | None` weakens completion signal

**Direct evidence**: Plan §Slice 1 Completion Signal: "No Runner call path remains without explicit `request_identity`." But the public contract change (§Contract/Public-Interface #4) uses `RunnerRequestIdentity | None`. Plan §Slice 2 also says "`request_identity is None`: no outbound header, even if policy enabled."

**Impact**: The type system cannot enforce the "no call path without identity" invariant if `None` is a valid value. The plan acknowledges that direct Engine tests and compactor calls may legitimately pass `None`. This tension is manageable but the plan's phrasing "no Runner call path remains without explicit `request_identity`" overstates the constraint.

**Suggested fix**: Either (a) keep `| None` and change the completion signal to "All Agent→Runner call paths pass non-None `request_identity`; direct Engine/compactor paths may legitimately pass `None`" or (b) make it required and require direct Engine tests to provide a minimal/zeroed identity. Option (a) is consistent with the Non-Goals and stop conditions.

### Finding 3 (LOW) — `EngineRunOutcomeFailed` miscategorized as EngineEvent data class

**Direct evidence**: Plan §Contract/Public-Interface #6 lists `EngineRunOutcomeFailed` among "EngineEvent data classes that already carry provider request identity." But `EngineRunOutcomeFailed` is in `dayu/engine/contracts/agent_run.py` as a member of `AgentRunResult`, not an `EngineEventData` variant.

**Impact**: Implementation could mistakenly look for `EngineRunOutcomeFailed` in `engine_events.py`. However, the plan correctly includes `agent_run.py` in the allowed files for Slice 1 and in the affected files list, so the change destination is unambiguous.

**Suggested fix**: Recategorize as "AgentRunResult outcome class" in the final wording. No plan change needed — implementation notes should suffice.

### Finding 4 (LOW) — Digest length not explicit

**Direct evidence**: Plan §Client Correlation ID Source Choice: "a stable `dayu-` prefix plus a fixed-length hex SHA-256 digest over a canonical tuple" and "The emitted `client_correlation_id` must be ASCII and short."

**Impact**: Full SHA-256 = 64 hex + 5 prefix = 69 chars. Truncated to e.g. 16 hex = 21 chars. Both are well within provider limits (OpenAI's undocumented ~200 char limit for this header). But the difference matters for collision probability: full SHA-256 is negligible; truncated increases collision risk.

**Suggested fix**: Specify full SHA-256 (64 hex chars) as the default, or state "truncated to first N hex chars" with reasoning. Full SHA-256 is recommended since 69 chars is well within provider limits.

### Finding 5 (LOW) — `ClientCorrelationPolicy` naming: category-first enum with provider-tied values

**Direct evidence**: Plan §Adapter Policy: enum `ClientCorrelationPolicy.DISABLED` / `OPENAI_X_CLIENT_REQUEST_ID`. Future values: Anthropic `metadata.user_id` (prose note), Claude Code gateway policy (prose note).

**Impact**: The enum name implies a general policy category, but its concrete values are provider-specific header policies. This is a design tension but not a flaw — the alternatives (provider-name branching in if-else) are explicitly rejected by Non-Goals.

**Suggested fix**: Accept as-is. The design is category-first with provider-tied values because headers are inherently provider-specific. Adding a docstring note that "values are provider-specific because outbound header mapping is provider-protocol-specific" would clarify intent.

### Finding 6 (LOW) — `iteration_id` contains `run_id` — redundant digest input

**Direct evidence**: `dayu/engine/agent.py:2253-2263`, `_iteration_id()` produces `f"{self._request.run_id}_iteration_{iteration_index + 1}"`. Plan §Client Correlation ID Source Choice canonical tuple includes both `run_id` and `iteration_id`.

**Impact**: Non-harmful redundancy in digest inputs. Uniqueness guarantee is unaffected. If this is intentional (belt-and-suspenders), it's fine. Implementation should note this.

**Suggested fix**: None required. Implementation may keep both for robustness or drop `run_id` from the tuple as `iteration_id` already encodes it.

---

## Architecture Boundary Verification

### UI → Service → Host → Engine layering

- **pass**: `RunnerRequestIdentity` is defined in Engine contracts, constructed by Agent, consumed by Runner. No reverse dependency.
- **pass**: Host supplies `attempt_id/execution_id` from `AttemptDispatchSnapshot` → `AgentRunRequest`. Engine doesn't read Host durable store.
- **pass**: `ClientCorrelationPolicy` enters `RunnerSpec` (Engine contract), projected through Host execution config JSON. Host doesn't write governance into Runner.

### Runner public contract

- **pass**: `AsyncRunner.call()` gets keyword-only `request_identity`. Runner implementations decide how (or whether) to use it.
- **pass**: `RunnerEvent` remains unchanged — no Host ownership leakage.

### Host Attempt identity projection

- **pass**: `AttemptDispatchSnapshot` already has `attempt_id/execution_id` (`dayu/host/api.py:572-598`). `RunInputBuilder.build()` (`dayu/host/run_input.py:1595-1688`) currently doesn't project these fields.
- **pass**: Plan correctly adds fields to `AgentRunRequest` and projects them in `RunInputBuilder.build()`.

### OpenAI-compatible header policy

- **pass**: No provider name string branching in Host/Agent. Policy expressed as `ClientCorrelationPolicy` enum on `RunnerSpec`.
- **pass**: `RunnerSpec.headers` static header conflict detection under enabled policy.

### Tool Trace signal persistence

- **pass**: No new SQLite column. `client_correlation_id` in existing `trace_summary_json` + cold JSONL.
- **pass**: Consistent with existing `provider_request_id` storage pattern (hot row column for `provider_request_id` exists; `client_correlation_id` goes in JSON summary because it's a local computation, not a provider response fact).

---

## AGENTS.md / CLAUDE.md Compliance Check

| Rule | Status |
|---|---|
| No `Any`/`object`/untyped signatures | pass — plan explicitly rejects these |
| No fake user id | pass — Non-Goals: `session_id`/`run_id` not faked as user governance |
| No dynamic ID in `RunnerSpec.headers` | pass — explicitly in Non-Goals |
| No provider string hardcoded governance | pass — uses `ClientCorrelationPolicy` enum |
| Chinese docstring completeness | pass — plan requires docstrings for new types |
| No lazy imports, nested functions | pass — plan explicitly rejects |
| No compatibility wrappers | pass — plan explicitly rejects |
| No God object/function/dataclass | pass — `RunnerRequestIdentity` is a focused contract |

---

## Contract / Schema Change Gaps

1. **`EngineRunOutcomeFailed` missing from explicit contract change list in Slice 3**: Slice 3 only mentions EngineEvent data classes. If `EngineRunOutcomeFailed` gets `client_correlation_id`, Slice 3's Host ingest should also handle it when producing terminal summaries. The plan's exact changes for Slice 3 list provider diagnostic, compaction, run failed payloads — this likely covers it, but the data flow diagram should note `EngineRunOutcomeFailed.client_correlation_id` as a terminal summary path.

2. **`RunnerSpec` backward compatibility**: Adding `client_correlation_policy` to `RunnerSpec` is a required field. All existing `RunnerSpec` construction sites must be updated. Plan correctly lists "Update all RunnerSpec factories and direct constructors." This is a compile-time safe change (Python won't let you construct a frozen dataclass without all fields).

---

## Test Matrix Review

| Slice | New test files | Existing test files | Coverage gap |
|---|---|---|---|
| 1 | `test_runner_identity.py` (new) | `test_agent_run.py`, `test_agent_phase2.py`, `test_agent_phase3_tool_call.py`, `test_metadata_boundary.py` | Force-answer/continuation call index behavior not explicitly tested |
| 2 | `test_request_identity.py` (new) | `test_runner_spec.py`, `test_streaming_capability_and_content_type.py`, `test_http_error_event.py`, `test_effective_execution_config.py` | Static header conflict edge case covered |
| 3 | none new | `test_run_input_builder.py`, `test_engine_ingest_mapping.py`, `test_tool_trace_projection.py`, `test_tool_trace_queries.py`, `test_local_proxy_engine_ingest.py` | Ingest test for missing `client_correlation_id` (None) covered |

**Finding**: Test matrix is adequate but Finding 1 (force-answer/continuation index semantics) implies a test gap: test_agent_phase2/phase3 should verify that force-answer and continuation calls get incrementing call indices.

---

## Blocking Open Questions

**None.** All questions are addressable during implementation without plan restructure:

1. Q: Should force_answer and length continuation calls increment `_runner_call_index`? A: Likely yes — each logical Runner call should have a distinct identity for provider debugging. Implementation can decide.

2. Q: Full SHA-256 (64 hex) or truncated? A: Use full 64 hex = 69 total chars with prefix. Well within any reasonable provider limit.

3. Q: Should `request_identity` be `| None` or required? A: Keep `| None` as designed. The plan explicitly allows direct Engine/compactor paths to pass `None`.

---

## Residual Risks

| Risk | Classification | Owner |
|---|---|---|
| Provider-specific `x-client-request-id` format/length constraints may reject `dayu-` prefix | Low probability; OpenAI documents this as free-form | Implementation: verify with fake session tests |
| Digest collision between different logical calls | Negligible (SHA-256, 2^256 space) | Closed by design |
| `client_correlation_id` field bloat in EngineEvent data classes (adding to 5+ dataclasses) | Moderate — each change touches multiple frozen dataclass constructors | Implementation must update all call sites |
| `_execution_config_projection.py` JSON round-trip for new policy field | Low — follows existing pattern for RunnerSpec fields | Implementation must add `client_correlation_policy` to `runner_spec_json()` and `runner_spec_from_json()` |

---

## Validation / Docs Gaps

1. `dayu/engine/README.md` — Plan correctly flags as requiring update (Runner public contract change).
2. `dayu/host/README.md` — Plan correctly flags as requiring update (Host projection behavior change).
3. `tests/README.md` — Plan correctly flags as potential update.
4. Root `README.md` — Plan correctly says no change expected.
5. No `dayu.runtime` changes anticipated — confirmed consistent with runtime neutrality.

---

## Conclusion

**pass-with-findings** — 6 findings, 0 blocking open questions.

The plan's motivation is valid, its evidence is direct and code-verified, and its architecture respects all layering constraints. The 2 medium findings (force-answer/continuation call index semantics, `| None` type tension) are addressable during implementation without plan restructure. The 4 low findings are minor clarifications.

Only the review artifact at `docs/reviews/wu-eng-02-plan-review-ds.md` was modified.
