# WU-CM-05-S2 Implementation Report

## Gate / Work Unit / Slice

- Gate: implementation
- Work unit: WU-CM-05 LLM Compaction Proposal Typed Parsing
- Slice: WU-CM-05-S2 / Complete invalid proposal diagnostics coverage
- Branch: `work/cm-05-06-08-09`
- Plan artifact: `docs/host/host-issues/wu-cm-05-llm-compaction-proposal-typed-parsing-plan.md`
- Accepted plan commit: `153c43e3`
- Previous slice commit: `7f2ce2c5`
- Artifact path: `docs/reviews/wu-cm-05-s2-implementation-report.md`

## Changed Files

- `dayu/host/llm_compaction.py`
- `tests/host/test_llm_compaction.py`
- `docs/reviews/wu-cm-05-s2-implementation-report.md`

Pre-existing dirty file preserved as read-only context:

- `docs/host/issues-implementation-control.md`

## Implementation Decisions

- Kept the public parser boundary unchanged: invalid proposal tests call `parse_conversation_compact_output_vnext(compact_input, raw_json)` and do not depend on `_parse_vnext_proposal` internals.
- Completed Slice 2 diagnostics coverage in `tests/host/test_llm_compaction.py` for malformed JSON, top-level non-object, missing required key, field type error, nested array type error, array item type error, top-level array overlimit, nested array overlimit, invalid enum values, unknown label, stale label, cross-section label, current anchor label, and old patch schema fail-closed.
- Addressed deferred S1 finding DS-F01 by including a redacted and truncated actual enum value in `_required_enum` diagnostics. This keeps the failure useful without allowing unbounded or obvious sensitive text into the exception message.
- Did not change compact business semantics, public API, durable schema, EventLog, Engine, Service, Fins, Config, prompt assets, LLM-facing schema, or README.

## Validation Results

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_llm_compaction.py -q
```

Result:

```text
36 passed in 0.27s
```

Passed:

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

Pyright also printed an upstream version availability notice: `v1.1.409 -> v1.1.410`.

## README / Docs Decision

- Read `dayu/host/README.md` update constraints. No update required because this slice only tightens internal parser diagnostics and test coverage; it does not change stable Host public contracts, architecture boundaries, context governance semantics, extension points, or LLM-facing schema.
- Read `tests/README.md` update constraints. No update required because this slice only adds cases to an existing Host compactor parser test file; it does not add a test layer, command category, or maintenance convention.
- No prompt assets or config docs were modified.

## Residual Risks / Uncovered Areas

- DS-F02 from S1 remains deliberately out of scope and covered by later approved Slice 3: test helper `_proposal_json` still uses `cast`.
- Slice 3 cleanup remains covered by later approved slice: no broad parser helper cleanup was attempted in this implementation gate.
- No unclassified residual risk remains for Slice 2.

## Stop Condition Status

- No blocking open question encountered.
- No README-required behavior change encountered.
- No validation failure encountered.
- No commit, push, PR, review, fix, or re-review gate was performed.
- Implementation status: completed.

## Fix Gate Update 2026-06-12

- Fix gate: completed.
- Accepted finding addressed: `docs/reviews/code-review-20260612-144954.md` Finding 1.
- Change: added explicit `forward_intents[0].intent_type` invalid enum diagnostic coverage in `tests/host/test_llm_compaction.py`, through `parse_conversation_compact_output_vnext(compact_input, json.dumps(...))`.
- Validation: `pytest tests/host/test_llm_compaction.py -q` passed with 37 tests.
- Validation: `python -m pyright dayu/ tests/ utils/` passed with 0 errors, 0 warnings, 0 informations.
- No production code, README, control document, code review artifact, commit, push, PR, or re-review gate was changed/performed.
