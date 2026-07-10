# WU-SEMANTIC-OWNERSHIP-01 P3-E Plan Review Controller Adjudication

## Reviewed Artifacts

- Plan: `docs/host/wu-semantic-ownership-01-p3-e-tool-result-wait-fins-contracts-plan.md`
- AgentMiMo plan review: `docs/reviews/plan-review-20260711-005941.md`
- AgentDS plan review: `docs/reviews/wu-semantic-ownership-01-p3-e-plan-review-ds.md`

## Controller Decision

Plan review gate returns `fix-required`.

Both reviewers returned `pass-with-risks` and found no blocking open question. The plan is directionally correct, but the accepted findings below must be fixed in the plan before implementation. The fixes are plan-text and validation-checklist changes only; no production implementation belongs in this gate.

## Merged Findings

### P3-E-PF-01 - Accepted - S1 must preserve `last_error_code` semantics outside LLM-facing hint

- **Sources**: AgentMiMo 001.
- **Decision**: accepted.
- **Reasoning**: P3-E removes governance/diagnostic codes from LLM-facing `hint`, but timeout branches currently use `hint=result.last_error_code or ...`. The plan must state where this diagnostic remains visible, such as message, failure metadata, Tool Trace, or an explicit owner-owned diagnostic field. The implementation agent must not mechanically set `hint=None` and lose the last error.
- **Required plan fix**: S1 must explicitly require auditing every `last_error_code` path and preserving it in non-LLM-facing diagnostics or self-contained `message` text where user-visible recovery needs it. Add validation scans/tests for `last_error_code`.

### P3-E-PF-02 - Accepted - S1 hint helper and constants cleanup must be deterministic

- **Sources**: AgentMiMo 004, AgentDS 4.
- **Decision**: accepted.
- **Reasoning**: Once `_awaiting_accept_failure_outcome` stops writing diagnostic refs into `hint`, `_hint_with_diagnostic_refs` and its private separator/key constants become dead infrastructure for the removed hidden string protocol.
- **Required plan fix**: Replace conditional "remove if unused" wording with deterministic deletion after reference scan: `_hint_with_diagnostic_refs`, `_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY`, `_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`, `_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR`, plus any accept-reason constants that become unreferenced after message/diagnostic migration.

### P3-E-PF-03 - Accepted - S2 LOST / UNKNOWN migration must prove result-payload diagnostics

- **Sources**: AgentDS 1.
- **Decision**: accepted.
- **Reasoning**: Removing raw outcome fallback is correct, but the plan must preserve `LOST` for unavailable accepted result payloads. If the new implementation relies only on diagnostics, the plan must require proving every `result_payload=None` path emits the correct diagnostic or adding an explicit safeguard.
- **Required plan fix**: S2 must inspect `_result_payload(...)` exits, add tests for unavailable payload paths, and specify the exact intended result when typed status is absent but payload is unavailable versus payload available with missing typed status.

### P3-E-PF-04 - Accepted - UNKNOWN accepted status needs consumer regression coverage

- **Sources**: AgentMiMo 002, AgentDS 5.
- **Decision**: accepted.
- **Reasoning**: Returning `UNKNOWN` instead of reconstructing `FAILED` / `COMPLETED` from raw outcome is the correct owner-boundary fix, but downstream consumers must prove they do not reintroduce raw fallback or break when status is `UNKNOWN`.
- **Required plan fix**: S2 validation must include explicit consumer coverage for read activity mapping and LLM/material consumers, at minimum `read_api`, `run_input` / evidence material, memory, and compact material paths or documented no-op evidence for files not affected.

### P3-E-PF-05 - Accepted - S3 RESULT buffering requires producer lifecycle audit and concrete stop criteria

- **Sources**: AgentMiMo 003, AgentDS 2.
- **Decision**: accepted.
- **Reasoning**: Detecting duplicate `RESULT` by draining until producer done is correct, but it changes the previous early-break lifecycle. The implementation must first prove `_DirectStreamProducerDone` is emitted on all producer exits, and the stop condition must be actionable if a producer hangs after terminal result.
- **Required plan fix**: S3 must add a producer lifecycle audit step, verification of sentinel emission on normal/exception/terminal-result paths, and a concrete no-hang validation strategy. If a hang is found, the plan must stop at Fins runtime owner and avoid ad hoc downstream timeout hacks.

### P3-E-PF-06 - Accepted - S3 must disposition existing CLI direct-stream exception type

- **Sources**: AgentDS 3.
- **Decision**: accepted.
- **Reasoning**: The plan proposes a new Fins-owned protocol error while `dayu/cli/commands/fins.py` already has `FinsDirectStreamContractViolation` for overlapping missing-terminal semantics. Keeping both without disposition creates duplicate truth for the same protocol violation.
- **Required plan fix**: S3 must explicitly make the Fins-owned typed protocol error the source of truth, decide whether to delete or replace the CLI-local exception, and include `dayu/cli/commands/fins.py` plus CLI tests in allowed scope when needed.

## Rejected / Deferred Findings

None. All material reviewer findings are accepted as plan fixes.

## Non-blocking Residual Notes

- Removing LLM-facing hints must not remove business-authored recovery hints from ordinary tools; this remains S1 scope control.
- Callback string provider refs breaking old ad hoc callers is accepted contract hardening, not a compatibility blocker.
- The MiMo artifact used the skill timestamp path rather than the requested stable path; this is accepted as reviewer-output variance and does not affect the review content.

## Next Gate

Dispatch AgentCodex to the plan-fix gate for `P3-E-PF-01` through `P3-E-PF-06`. The fix gate must update only the plan artifact unless it finds the plan cannot be made code-generation-ready without changing the goal confirmation or design truth.
