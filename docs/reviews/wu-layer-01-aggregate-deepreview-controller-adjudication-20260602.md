# WU-LAYER-01 Aggregate Deepreview Controller Adjudication

## Scope

- Work unit: `WU-LAYER-01`
- Review type: Aggregate deepreview across Slice 1 to Slice 4
- Design source: `docs/host/design.md`
- Control doc: `docs/host/host-core-followup-implementation-control.md`
- Plan: `docs/host/wu-layer-01-durable-row-primitive-cleanup-plan.md`
- Accepted slice commits:
  - Slice 1: `02396e5`
  - Slice 2: `ff64f0b`
  - Slice 3: `b4fc923`
  - Slice 4: `2397e72`
- Review artifacts:
  - `docs/reviews/wu-layer-01-aggregate-deepreview-mimo-20260602.md`
  - `docs/reviews/wu-layer-01-aggregate-deepreview-ds-20260602.md`

## Review Results

| Reviewer | Verdict | Blocking findings |
|---|---|---|
| AgentMiMo | PASS | none |
| AgentDS | PASS | none |

## Accepted Findings

None.

## Rejected / Deferred Findings

| Finding | Source | Controller adjudication |
|---|---|---|
| `_assert_host_row_decode_error` is duplicated in two test files | AgentDS | Deferred as non-blocking test maintenance. It is limited to test-local assertion helpers, does not affect production durable row decode ownership, and extracting a shared test helper now would broaden WU-LAYER-01 beyond durable row primitive cleanup. Reconsider only if future test maintenance creates a third duplicate or changes the assertion contract. |

## Controller Verification

- Both aggregate reviews independently confirm schema expected SQL is generated from `HOST_DURABLE_DDL` through SQLite catalog SQL and does not introduce hand-written DDL expectation drift.
- Both aggregate reviews independently confirm current-version open paths fail closed on missing table, missing index, same-name wrong table definition, and same-name wrong index definition without repair; fresh bootstrap does not false-positive.
- Both aggregate reviews independently confirm Slice 2 terminal DDL CHECK generation remains covered by Slice 1 schema definition validation.
- Both aggregate reviews independently confirm Run, Attempt, and WaitRecord terminal rules are same-source across DDL CHECK, Python validation, CAS WHERE, and decode-time validation.
- Both aggregate reviews independently confirm `_row_rules.py` remains durable-private, is not re-exported, does not import higher layers, does not pollute `_validation.py`, and does not become a generic validation framework.
- Both aggregate reviews independently confirm corrupted WaitRecord and Run CAS scenarios are test-only, prove CAS does not overwrite corrupted rows, and align with the `HostRowDecodeError` read boundary.
- Both aggregate reviews independently confirm `HostRowDecodeError` remains internal to durable state handling, is not exported through public Host API/docs, wraps row decode missing column/type/enum/terminal shape failures, and preserves cause chains.
- Both aggregate reviews independently confirm README sync is accurate and within `dayu/host/README.md` responsibility boundaries.
- Validation reported by reviewers:
  - AgentMiMo: aggregate Host pytest command -> 136 passed; pyright -> 0 errors.
  - AgentDS: aggregate Host pytest command -> 136 passed; pyright -> 0 errors.

## Verdict

PASS. No accepted blocking, high, or medium finding remains. WU-LAYER-01 may proceed to accepted aggregate deepreview commit.
