# WU-CM-05-S1 Implementation Report

## Gate / Work Unit / Slice

- Gate: implementation only
- Work unit: `WU-CM-05 LLM Compaction Proposal Typed Parsing`
- Slice: `WU-CM-05-S1 / Introduce direct typed candidate parser`
- Accepted plan commit: `153c43e3`
- Plan artifact: `docs/host/host-issues/wu-cm-05-llm-compaction-proposal-typed-parsing-plan.md`

## Changed Files

- `dayu/host/llm_compaction.py`
- `tests/host/test_llm_compaction.py`
- `docs/reviews/wu-cm-05-s1-implementation-report.md`

## Implementation Decisions

- Replaced `_parse_vnext_proposal(...)` as a cross-function `Mapping[str, JsonValue]` contract with direct construction of `ConversationCompactOutputVNext`.
- Kept raw `Mapping[str, JsonValue]` only inside local JSON object helper boundaries after `json.loads(...)` is narrowed through `JsonValue`.
- Removed the previous broad `cast(Mapping[str, JsonValue], parsed)` from the vNext proposal parsing path and removed the unused `cast` import from production code.
- Added explicit `_field_path(...)` and `_item_path(...)` helpers and rewired field helpers to receive `parent_path` or full field paths.
- Added typed local helpers for required values, arrays, strings, string tuples, enums, optional non-negative integers, and JSON objects.
- Validated `schema_version` before constructing the final candidate so schema version failures point at `schema_version`.
- Preserved `ConversationCompactOutputVNext.__post_init__` unchanged as the Host contract safety net.
- Preserved `LLMCompactionProposalError` as the public proposal failure type; parser and candidate safety-net failures are wrapped through that type at the public parser boundary.
- Kept `_validate_vnext_candidate_source_labels(...)` as the source label accept barrier, preserving current input anchor, unknown, stale, and cross-section rejection semantics.

## Tests / Validation

Commands run:

```bash
source .venv/bin/activate && pytest tests/host/test_llm_compaction.py -q
```

Result:

```text
23 passed in 0.28s
```

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

Pyright also printed a version availability warning: `v1.1.409 -> v1.1.410`. No type errors were reported.

## README / Docs Decision

- Checked `dayu/host/README.md` update constraints. This slice only changes private parser implementation and does not change Host public API, durable schema, state machine, architecture boundary, or stable developer-facing component contract. No README update required.
- Checked `tests/README.md` update boundary. This slice adds assertions to an existing Host test file without adding a test layer, command, or maintenance rule. No README update required.
- Wrote this implementation artifact as required by the implementation gate.

## Residual Risks / Uncovered Areas

- Full invalid proposal matrix remains uncovered in this slice; classification: covered by later approved slice `WU-CM-05-S2`.
- Cleanup beyond removing the now-unneeded production broad cast was not performed; classification: covered by later approved slice `WU-CM-05-S3`.
- Parser still intentionally relies on existing Host-owned candidate constructors for non-empty text and candidate-level label cardinality safety-net checks instead of duplicating every invariant in field helpers; classification: tracked by current slice design and covered by the added safety-net wrapping test.

## Stop Condition Status

- No blocking open question encountered.
- No scope expansion required.
- No README update required.
- No validation failure.
- No commit, push, PR, review, fix, or re-review gate was started.
