# WU-SEMANTIC-OWNERSHIP-01 P3-E Plan Fix (AgentCodex)

## Scope

- Gate: `plan-fix`
- Target plan: `docs/host/wu-semantic-ownership-01-p3-e-tool-result-wait-fins-contracts-plan.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-e-plan-review-controller-adjudication.md`
- Constraint: plan text only; no production implementation, no tests, no commit, no push, no control-doc update.

## Fixes Closed

- `P3-E-PF-01`: Closed. S1 now requires auditing every `last_error_code` path touched by ToolRuntime hint cleanup and preserving the diagnostic in `message`, owner diagnostics, `failure_metadata`, or Tool Trace while keeping it out of LLM-facing `hint`.
- `P3-E-PF-02`: Closed. S1 now requires deterministic deletion of `_hint_with_diagnostic_refs`, its private hint separator/key constants, and any accept reason constants that become unreferenced after diagnostics/message migration.
- `P3-E-PF-03`: Closed. S2 now requires `_result_payload(...)` exit audit, unavailable payload tests, and an explicit semantic split: unavailable payload -> `LOST`; available payload with missing/blank/unrecognized typed status -> `UNKNOWN`.
- `P3-E-PF-04`: Closed. S2 now requires consumer regression coverage or no-op evidence for `read_api`, `run_input` / evidence material, memory projection, and compact material when accepted status is `UNKNOWN`.
- `P3-E-PF-05`: Closed. S3 now requires `_DirectStreamProducerDone` lifecycle audit across normal, exception, and terminal-result paths, plus no-hang validation. The stop condition is explicitly Fins runtime owner repair, not downstream timeout masking.
- `P3-E-PF-06`: Closed. S3 now declares Fins-owned `FinsDirectStreamProtocolError` as the source of truth and includes `dayu/cli/commands/fins.py` plus CLI tests to delete or replace CLI-local `FinsDirectStreamContractViolation`.

## Validation Checklist Added To Plan

- S1 source scan for `last_error_code`, hidden hint helper/constants, and `accept_rejected:` remaining references.
- S2 source scan for `_result_payload(...)`, `AcceptedToolResultStatus.UNKNOWN`, raw outcome status fallback, and payload-unavailable diagnostics.
- S3 source scan for `_DirectStreamProducerDone`, `FinsDirectStreamProtocolError`, stale CLI-local contract violation, and synthetic missing-result helpers.
- Aggregate validation now includes read-model, run-input, memory, compact-material, CLI, and Fins direct stream tests in addition to the original focused tests.

## Plan-Fix Validation Run

- `git diff --check -- docs/host/wu-semantic-ownership-01-p3-e-tool-result-wait-fins-contracts-plan.md docs/reviews/wu-semantic-ownership-01-p3-e-plan-fix-codex.md`: no whitespace errors.
- `git diff --check --no-index /dev/null docs/host/wu-semantic-ownership-01-p3-e-tool-result-wait-fins-contracts-plan.md`: no whitespace-error output; non-zero exit is expected because the file is compared against `/dev/null`.
- `git diff --check --no-index /dev/null docs/reviews/wu-semantic-ownership-01-p3-e-plan-fix-codex.md`: no whitespace-error output; non-zero exit is expected because the file is compared against `/dev/null`.
- `rg` self-check confirmed the target plan and this artifact mention `P3-E-PF-01` through `P3-E-PF-06`.
- `rg` self-check confirmed the target plan mentions the required fix evidence terms: `last_error_code`, `_hint_with_diagnostic_refs`, `_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY`, `_result_payload`, payload-unavailable diagnostics, `AcceptedToolResultStatus.UNKNOWN`, read/run-input/memory/compact consumers, `_DirectStreamProducerDone`, no-hang validation, `FinsDirectStreamContractViolation`, and `FinsDirectStreamProtocolError`.

## Blocking Questions

None.
