# P9.5 S17 Documentation Review Controller Adjudication

## Scope

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening
- Slice: S17 Documentation And Control Tracking
- Design source: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Implementation artifact: `docs/reviews/p9-5-s17-documentation-control-tracking-implementation-20260517.md`
- Reviews:
  - `docs/reviews/p9-5-s17-doc-review-mimo-20260517.md`
  - `docs/reviews/p9-5-s17-doc-re-review-mimo-20260517.md`
  - `docs/reviews/p9-5-s17-doc-review-ds-20260517.md`

## Controller Verdict

S17 is accepted with no blocking findings.

The documentation changes are intentionally small and describe only current stable facts. They correct stale or incomplete wording for ToolRuntime effective bundle same-source constraints, the private default Runner assembly point, projection catch-up warning behavior, and import-boundary test coverage. They do not add future promises, process history, or public API changes.

## Review Finding Adjudication

### AgentMiMo F1: `tests/README.md` Engine import boundary memory wording

Verdict: Accepted and fixed.

The original wording listed `memory` as an independent Engine import-boundary item, while the test guard enforces it through the broader `dayu.host` prefix. The docs wording was corrected to `Host（含 memory）`, and AgentMiMo re-review confirmed F1 fixed.

### AgentDS Review

Verdict: Accepted.

AgentDS reported PASS with 0 blocking findings. The review confirmed that all touched README / design entries match current code, do not exceed their document responsibilities, and leave `docs/host/implementation-control.md` for post-accept tracking instead of duplicating process history inside S17 docs.

## Validation Accepted By Controller

- `git diff --check`: clean.
- AgentDS additionally ran `python -m pyright dayu tests`: 0 errors / 0 warnings / 0 informations.

## Documentation Decision

The accepted documentation updates are:

- `dayu/README.md` and `docs/design.md`: `tool_schemas` and ToolRuntime `tool_executor` must come from the same attempt-local effective `ToolBundle`.
- `dayu/engine/README.md`: current function entry uses a private default OpenAI-compatible Runner assembly point, not a public factory / registry / runner selection extension.
- `dayu/host/README.md`: best-effort projection catch-up failure logs projection-local `WARNING` with `error_type`, preserving durable command / accept results.
- `tests/README.md`: import-boundary descriptions now match runtime, contracts, engine, and host guard tests, including Host business tool scanner prohibition and `fetch_more` owner guard.

No `docs/host/design.md` change is required because the Host design source already contains the same design goals and this slice did not change them. `docs/host/implementation-control.md` will be updated after the accepted S17 commit, following the established tracking pattern.

## Residual Risk

- S17 did not run aggregate tests; S18 owns aggregate validation before readiness.
- The documentation remains intentionally high-level. Implementation details such as exact helper function names, private file names, and slice process history stay in code or review artifacts, not README files.
