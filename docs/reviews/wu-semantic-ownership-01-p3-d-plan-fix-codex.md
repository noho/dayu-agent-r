# WU-SEMANTIC-OWNERSHIP-01 P3-D Plan Fix - AgentCodex

## Scope

- Gate: plan-fix
- Input plan: `docs/host/wu-semantic-ownership-01-p3-d-engine-provider-protocol-normalization-plan.md`
- Inputs reviewed:
  - `docs/reviews/wu-semantic-ownership-01-p3-d-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-d-plan-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-d-plan-review-controller-adjudication.md`
- Files modified:
  - `docs/host/wu-semantic-ownership-01-p3-d-engine-provider-protocol-normalization-plan.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-d-plan-fix-codex.md`
- Files intentionally not modified: production code, test code, commits.

## Gate State

- Status: `ready-for-plan-rereview`
- Blocking questions: none

## Fix Evidence

### P3-D-PF-01 - Host diagnostic event contract

Fixed in plan lines 20-22, 105-111, 220-226, and 247-257.

Evidence:

- Plan now names the non-fatal Host EventLog event as `PROVIDER_DIAGNOSTIC` with `EventClass.DIAGNOSTIC`.
- Plan states not to reuse fatal `_EVENT_TYPE_PROVIDER_PROTOCOL_ERROR`; default is a new `_EVENT_TYPE_PROVIDER_DIAGNOSTIC`.
- Plan defines ingest payload, no Run/Attempt transition, Tool Trace diagnostic-only behavior, Read API activity projection, outbox exclusion, and design doc update sections.

### P3-D-PF-02 - Context-overflow provenance Runner -> Agent -> Engine -> Host

Fixed in plan lines 60-64, 100-101, 120, 193-203, and 232-234.

Evidence:

- Plan lists `runner.py` and `error_classifier.py` as candidate files.
- Plan requires `ContextOverflowDetection` to travel through `runner.py` into `_AttemptFailedTerminal` or `RunnerHTTPErrorData.context_overflow_detection`, then through Agent into Engine diagnostics and Host `PROVIDER_DIAGNOSTIC`.
- Tests must verify marker fallback produces diagnostic provenance while canonical compaction remains based on typed HTTP code.

### P3-D-PF-03 - Log-only adapter warnings vs RunnerProtocolErrorData warnings

Fixed in plan lines 100, 197-202, 227-230, and 241-245.

Evidence:

- Plan splits existing `RunnerProtocolErrorData` warnings from current log-only warnings.
- Plan explicitly includes malformed usage and missing `Content-Type` as log-only warnings that must start emitting typed diagnostics.
- Plan includes `usage.py`, exact parser/runner call sites, streaming and non-streaming missing content type, and source scans.

### P3-D-PF-04 - Separate SSE/non-stream multi-choice semantics

Fixed in plan lines 115-116, 146-148, and 157-162.

Evidence:

- Plan separates SSE chunk semantics from non-stream response semantics.
- SSE validation timing is immediate in `_handle_chunk_object()`.
- Usage-only empty-choice semantics are scoped to SSE only.
- Tests cover non-stream multi-choice, SSE multi-choice chunk, usage-only chunk, empty delta plus valid delta, and conflicting content/tool-call choices.

### P3-D-PF-05 - Finish_reason non-string/empty/null/missing/conflicting values

Fixed in plan lines 117, 149-150, and 163-167.

Evidence:

- Plan defines fatal behavior for unknown non-empty string, empty string, non-string non-null values, bool, number, array, object, and cross-chunk conflicting terminal finish reasons.
- Plan defines null/missing as absent rather than `STOP`.
- Plan requires explicit negative tests for each boundary.

### P3-D-PF-06 - S1/S2 dependency and intermediate fatal state

Fixed in plan lines 183-185.

Evidence:

- Plan now states S2 depends on S1.
- Plan describes the intermediate state: after S1 and before S2, invalid/unknown `finish_reason` is fatal and still uses the existing fatal provider-protocol error path.

### P3-D-PF-07 - S3 split or atomicity justification

Fixed in plan lines 267-269.

Evidence:

- Plan keeps S3 atomic and explains why: public dataclass type changes must move with Engine contracts, Agent callers, Host consumers, tests, docs, weak-typing guard, and propagation audit.
- Plan rejects split-by-compatibility because project constraints forbid compatibility facades, aliases, and old string-only constructors.

### P3-D-PF-08 - Error-code propagation matrix and complete scans

Fixed in plan lines 95-111, 314-327, and 337-341.

Evidence:

- Plan adds current static propagation analysis for fatal protocol codes, non-fatal diagnostics, context-overflow classification, Engine-owned run failure codes, and provider/runner extension codes.
- Plan adds S3 propagation matrix covering `RunnerProtocolErrorData`, `ProviderProtocolErrorData`, `RunFailedData`, `EngineRunOutcomeFailed`, Agent constants/constructors, Host ingest, Read API, Tool Trace, outbox/public events, and memory/compact/evidence exclusion.
- Source scans now include `EngineRunOutcomeFailed(...)`, Host consumer files, `provider_error_code`, and `failure_metadata`.

### P3-D-PF-09 - Concrete weak-typing guard

Fixed in plan lines 308-311.

Evidence:

- Plan requires a checked-in pytest or validation script invoked by tests/CI.
- Plan states exact failure conditions: `error_code: str` in Engine contracts, literal string `error_code="..."` in typed constructors, and Host consumers bypassing the serializer.

### P3-D-PF-10 - RunnerSpecificErrorCode empty/serialization semantics

Fixed in plan lines 121, 303-305, and 335.

Evidence:

- Plan defines wrapper shape with `value` and closed `source`.
- Plan requires trimming, non-empty bounded validation, rejection of whitespace-only and overly long values, and single-helper serialization.
- Explicit empty provider/runner codes fail closed; missing provider detail uses an Engine-owned fallback enum rather than an empty wrapper.

### P3-D-PF-11 - Section-specific design/README updates

Fixed in plan lines 247-257 and 343-353.

Evidence:

- S2 lists exact sections or topics for `docs/engine/design.md`, `docs/host/design.md`, `dayu/engine/README.md`, `dayu/host/README.md`, and `tests/README.md`.
- S3 lists exact sections or topics for Engine event/outcome docs, Host terminal payload docs, public contract exports, Host diagnostic/terminal payload behavior, and weak-typing guard test organization.

### P3-D-PF-12 - Validation for no LLM-facing diagnostic leakage

Fixed in plan lines 35, 79, 111, 234, 327, 369-373, and 391.

Evidence:

- Plan repeatedly states diagnostics must not become LLM-facing material.
- S2 tests must verify marker-fallback diagnostic output does not enter memory, final answer, evidence, or compact prompt material.
- Validation summary requires a test or scan proving `PROVIDER_DIAGNOSTIC`, raw diagnostic text, `message_marker_fallback`, and diagnostic payload refs do not enter memory, final answer, accepted evidence material, compact material, or LLM-facing prompt messages.

## Docs-Only Validation

- Required validation: `git diff --check`
- Status: passed.

## Residual Risk

- No blocking question remains.
- This gate only makes the plan code-generation-ready. Implementation risk remains in S2/S3 because they intentionally touch cross-boundary contracts and must be verified by tests, pyright, coverage, source scans, README trigger checks, and propagation audit during implementation.
