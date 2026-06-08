# WU-TOOLS-01-F01 S1 Re-Review Controller Adjudication

## Metadata

- Gate: S1 re-review controller adjudication.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: S1 Shared Fins Runtime Foundation.
- Implementation artifact: `docs/reviews/wu-tools-01-f01-s1-implementation-codex.md`.
- Fix artifact: `docs/reviews/wu-tools-01-f01-s1-fix-codex.md`.
- Re-review artifacts:
  - `docs/reviews/wu-tools-01-f01-s1-rereview-mimo.md`
  - `docs/reviews/wu-tools-01-f01-s1-rereview-ds.md`

## Decision

PASS. Both re-review agents confirmed all four controller-accepted code review findings are fixed:

- Slash validation is field-specific: source-like fields reject path separators, while form/document id fields allow business-valid `/`, including `10-K/A`.
- Market/exchange deserialization derives allowed values from the ticker normalization type truth.
- Atomic job record write failure cleans temporary files.
- File lock acquisition failure explicitly closes the opened stream.

The rejected read-lock throughput observation remains unchanged, as intended.

## Controller Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py`: passed, `23 passed, 3 warnings`.
- `source .venv/bin/activate && pyright`: passed, `0 errors`.
- `git diff --check`: passed.

## README Sync

S1 changed `dayu/fins/` and `tests/`, so README sync was required before accepted slice commit.

- `dayu/fins/README.md` now describes `DefaultFinsRuntime` as the shared Fins assembly root and documents that ingestion runtime foundation exists, while download/preprocess tool providers and real pipelines are not yet implemented.
- `tests/README.md` now records `tests/fins/test_fins_ingestion_runtime.py` coverage for workspace-scoped job store, queued job persistence, ticker normalization, cancellation, record leakage boundary and job store failure paths.

## Residual Risks

| Risk | Classification | Owner / Destination |
|---|---|---|
| Read lock throughput observation | deferred-with-owner | Later S5 polling / performance hardening only if contention evidence appears |
| Real preprocess pipeline | covered by later approved slice | `WU-TOOLS-01-F01` S2 |
| Real download runtime adapter protocol / fake path | covered by later approved slice | `WU-TOOLS-01-F01` S3 |
| Download / preprocess providers | covered by later approved slice | `WU-TOOLS-01-F01` S4 |
| Fins wait adapter and Service assembly | covered by later approved slice | `WU-TOOLS-01-F01` S5 |
| Real SEC/CN/HK network adapters | assigned to later work unit | Later Fins source-adapter owner or explicit user-approved F01 scope expansion |

No unclassified residual risk remains for S1.

## Next Gate

Create accepted slice commit for S1. After the commit is recorded, enter S2 implementation gate.
