# WU-CM-01-F02 Slice 5 Code Review Controller Adjudication

## Gate

- gate: code review adjudication
- work unit: WU-CM-01-F02 Compact Evidence Query Readability Quality Closeout
- slice: Slice 5 Compact Evidence Query Readability
- branch: `phaseflow/wu-dur-obs-cm-closeout`
- status: accepted

## Inputs

- implementation artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice5-implementation-codex.md`
- AgentMiMo review: `docs/reviews/wu-dur-obs-cm-closeout-slice5-code-review-mimo.md`
- AgentDS review: `docs/reviews/wu-dur-obs-cm-closeout-slice5-code-review-ds.md`
- plan source: `docs/host/wu-dur-obs-cm-closeout-plan.md` Slice 5
- design source: `docs/host/design.md`

## Review Results

AgentMiMo verdict: PASS. No blocking findings.

AgentDS verdict: PASS. No blocking findings.

Both reviews independently confirmed:

- `query_text` is derived from durable `TOOL_CALL_REQUESTED` atoms through `tool_call_requested_event_ref`.
- durable `semantic_query_text` takes priority over arguments fallback.
- arguments fallback is canonical, bounded, business-readable, and does not expose Host refs, payload refs, digests, cursors, EventLog ids, or `tool_call_id`.
- missing / unreadable / mismatched request material emits structured limited-signal text instead of silently falling back to a bare id.
- same-source validation covers session boundary, `tool_call_id`, `tool_name`, and normalized arguments digest.
- chunked evidence shares the same base `query_text`; chunk ordinal stays in the prompt-local label.
- compact candidate output schema is unchanged.
- result content is not mixed into `query_text`.
- README updates are within assigned responsibilities.

## Findings Adjudication

No accepted blocking findings. No fix gate is required for Slice 5.

MiMo and DS both noted missing focused tests for some limited-signal branches such as missing request event, session mismatch, and request / evidence atom mismatch. Controller classifies these as non-blocking test gaps because the implemented branches are fail-safe and return limited-signal, the direct missing-ref branch is covered, and the durable atom parser / digest checks are already covered by lower-level tests. These gaps do not invalidate Slice 5 acceptance.

DS noted that `InitialEvidenceMaterial.tool_call_event_ref` can still fall back to the `TOOL_RESULT_ACCEPTED` event id when the request ref is absent, while the docstring names it as a `TOOL_CALL_REQUESTED` ref. Controller does not accept this as a Slice 5 fix because that field is internal provenance, not LLM-facing `query_text`, and the current compact material / evidence map contract still requires a non-empty provenance ref. Changing it to nullable would expand the compact provenance contract and can make the missing-request limited-signal path fail during material pack construction instead of producing bounded LLM-facing evidence. This is a valid low-risk follow-up for a later compact provenance contract cleanup, not a blocker for the current query readability slice.

## Validation

Controller validation before review dispatch:

- `source .venv/bin/activate && pytest tests/host/test_compaction_operation.py tests/host/test_public_compact_smoke.py`
  - result: 49 passed, 1 skipped
- `source .venv/bin/activate && pyright`
  - result: 0 errors
- `git diff --check`
  - result: passed

AgentMiMo also ran focused checks:

- `pytest tests/host/test_compaction_operation.py -x -q`
  - result: 44 passed
- `pytest tests/host/test_public_compact_smoke.py -x -q`
  - result: 5 passed, 1 skipped
- `pyright dayu/host/compaction_evidence.py`
  - result: 0 errors

## Decision

Slice 5 implementation is accepted as-is. Proceed to acceptance commit for:

- `dayu/host/compaction_evidence.py`
- `tests/host/test_compaction_operation.py`
- `dayu/host/README.md`
- `tests/README.md`
- Slice 5 implementation and review artifacts
- control document review-gate bookkeeping

