# WU-TOOLS-01 Slice S2 Code Review Controller Adjudication

Gate: code review  
Work unit: WU-TOOLS-01  
Slice: S2 Tool Adapter And Typed Provider Config  
Controller: phaseflow  
Date: 2026-06-05  
Decision: needs fix

## Inputs

- Implementation artifact: `docs/reviews/wu-tools-01-slice2-implementation-codex.md`
- AgentMiMo review: `docs/reviews/wu-tools-01-slice2-code-review-mimo.md`
- AgentDS review: `docs/reviews/wu-tools-01-slice2-code-review-ds.md`
- Accepted plan: `docs/host/wu-tools-01-migration-plan.md`

## Review Summary

Both reviewers returned `pass-with-findings`.

The implementation satisfies the core S2 constraints: it does not migrate OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, or OLD projection owners; it keeps config pass-through layer-neutral; and the controller re-ran the target tests plus pyright successfully.

However, several low-severity adapter findings are cheap to fix now and directly strengthen the S2 contract before S3/S4/S5 consume it. Controller therefore sends S2 to a narrow fix gate.

## Findings Adjudication

### M1: `fetch_more` handling differs between single-tool and batch adapters

Decision: accepted.

Reason:

- `adapt_collected_tool(...)` fail-fast behavior is clearer than silently skipping reserved framework tool names in `adapt_collected_tools(...)`.
- Silent skip can hide provider declaration mistakes.

Required fix:

- Make `adapt_collected_tools(...)` fail fast when any declaration has the reserved `fetch_more` name.
- Update tests to expect fail-fast batch behavior.

### M2: `SERIAL_PER_PROVIDER` and generic exception projection lack tests

Decision: accepted.

Reason:

- These are implemented S2 code paths and should be covered before acceptance.

Required fix:

- Add a test proving `LegacyToolConcurrencyPolicy.SERIAL_PER_PROVIDER` shares one lock across different tool names.
- Add a test proving a generic exception projects to a current failure outcome with the expected execution-error classification.

### D1: OLD envelope detection treats any `{"ok": True, ...}` dict as an OLD envelope

Decision: accepted.

Reason:

- The accepted plan requires OLD ok/value envelopes to be unwrapped, not arbitrary business dicts containing an `ok` business field.
- The current behavior can silently replace a business dict with `None` when `value` is absent.

Required fix:

- Treat a success result as an OLD envelope only when `ok is True` and the `value` key is present.
- Add a test proving a plain business dict such as `{"ok": True, "status": "ready"}` is preserved as a plain dict.

### D2: `ToolPathValidationPolicy.file_path_params` may omit declared path params

Decision: accepted.

Reason:

- The user explicitly required Doc tools not to own path safety; fail-closed path validation must live in the outer adapter/provider boundary.
- If a provider supplies an incomplete path policy, the adapter should fail closed rather than silently skip a declared path parameter.

Required fix:

- When a `ToolPathValidationPolicy` is provided, validate that its `file_path_params` covers every `declaration.file_path_params` entry needed by the declaration.
- If coverage is incomplete, return a current `ToolFailedOutcome` before invoking the migrated callable.
- Add a test proving incomplete policy coverage does not call the migrated callable.

## Deferred / Residual Notes

No S2 review finding is deferred. Existing work-unit residuals still apply:

- Provider-specific typed config parsing remains S3/S4/S5 owner.
- Provider-specific Doc path whitelist behavior remains S3 owner.
- Concrete migrated truncating tools remain S3/S4/S5 owner.
- Combined ToolRuntime accept path remains S6 owner.

## Next Gate

Dispatch AgentCodex for a narrow S2 fix gate covering only the accepted findings above.
