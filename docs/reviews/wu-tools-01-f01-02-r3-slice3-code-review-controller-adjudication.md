# WU-TOOLS-01-F01-02-R3 Slice 3 Code Review Controller Adjudication

## Gate

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: Slice 3: Fins Read Native Tools
- Gate: code review adjudication
- Controller: AgentController
- Inputs:
  - `docs/reviews/wu-tools-01-f01-02-r3-slice3-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-slice3-code-review-ds.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-slice3-implementation-codex.md`

## Review Results

- MiMo verdict: `PASS_WITH_FINDINGS`
- DS verdict: `PASS_WITH_FINDINGS`
- Blocking findings: none

## Accepted Findings

### S3-CR-01: Do not project raw cancellation token reason into Fins read tool messages

- Source: DS `F001`
- Severity: low
- Files: `dayu/fins/tools/fins_tools.py`, `dayu/fins/tools/read_runtime_helpers.py`, `tests/fins/test_fins_storage_provider.py`
- Decision: accepted

Reasoning:

`CancellationToken.cancel_reason()` belongs to Host cancellation governance. Even though the protocol describes it as a neutral string, Fins read tools should not concatenate that value into LLM-facing `ToolCancelledOutcome.message`. This is an Agent semantic boundary issue: cancellation outcome reason is already structurally represented as `host_cancelled`, while the message only needs to tell the model that the read tool stopped.

Required fix:

- `_cancelled_from_token(...)` must use a fixed business-readable cancellation message and must not embed `cancel_reason()`.
- `raise_fins_cancelled(...)` must raise `FinsReadCancelledError` with a fixed business-readable cancellation message and must not embed `cancel_reason()`.
- Add a focused test where the cancellation token reason contains Host/governance-looking identifiers and assert those identifiers do not appear in cancelled outcome message or hint.
- Keep `ToolCancelledOutcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED`.

## Rejected / Non-Actionable Findings

### MiMo F1: Catch-order documentation

Decision: no fix required. The catch order is correct and covered by cancellation tests. Additional docstring text is optional but not necessary for Slice 3 acceptance.

### MiMo F2: `search_document` diagnostics `.pop()`

Decision: no fix required. Current `FinsReadRuntime.search_document(...)` constructs a fresh result mapping per call; there is no shared cache mutation risk in this slice.

### MiMo F3: `_normalize_periods` hard-coded `list_documents`

Decision: no fix required. The helper is currently only used by `list_documents`; changing the signature would add churn without reducing current risk.

### MiMo F4: `_BusinessCall` return cast

Decision: no fix required. The cast bridges TypedDict-like Fins result payloads to the project JSON value contract and does not introduce runtime behavior risk.

### MiMo F5: Private-method monkeypatch in cancellation test

Decision: no fix required. The monkeypatch targets the exact fallback block under test and is an acceptable focused test seam.

### MiMo F6: Concurrency test uses `time.sleep(0.05)`

Decision: no fix required. The test synchronizes with `Event`; sleep only keeps the first synchronous business body active long enough for the second task to contend on the provider lock.

### DS F002: Parameter extraction inside provider lock

Decision: no fix required for Slice 3. The extraction helpers are constant-time type narrowing over already validated arguments, and the provider lock is released by `async with` on all exception paths. Moving extraction outside the lock can be considered only if future argument processing becomes non-trivial.

### DS F003: Duplicate name-order validation

Decision: no fix required. The builder-level check guards the native definition construction invariant; provider-level validation is acceptable defense at discovery boundary.

## Controller Validation Before Fix

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py`: passed, 21 tests.
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -k cancellation`: passed, 1 selected test.
- `source .venv/bin/activate && pyright`: passed, 0 errors.
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools|ToolBusinessError\\(.*tool_cancelled" dayu/fins/tools tests/fins/test_fins_storage_provider.py`: no matches.
- `git diff --check`: passed.

## Next Gate

Dispatch AgentCodex fix for accepted `S3-CR-01`, then run MiMo / DS re-review focused on the accepted fix and regression surface.
