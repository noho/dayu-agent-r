# WU-TOOLS-01-F01 S1 Code Review Controller Adjudication

## Metadata

- Gate: code review controller adjudication.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: S1 Shared Fins Runtime Foundation.
- Implementation artifact: `docs/reviews/wu-tools-01-f01-s1-implementation-codex.md`.
- Code review artifacts:
  - `docs/reviews/wu-tools-01-f01-s1-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-s1-code-review-ds.md`

## Overall Decision

Enter fix gate. The S1 implementation is within approved scope and validation passed, but accepted findings must be fixed before re-review and accepted slice commit.

## Findings Adjudication

| Finding | Source | Decision | Reasoning | Required fix |
|---|---|---|---|---|
| `_bounded_text` rejects `/` and blocks valid SEC amended form types such as `10-K/A` | DS F01 | accepted | Form type filtering is part of the approved download request shape. Rejecting `/` at the shared helper level would make a valid SEC form unusable before S3 can implement the adapter protocol. Path-injection defense should be field-specific, not applied to all business identifiers. | Split validation semantics so source-like fields can reject path separators while form types and document ids can allow business-valid `/` values. Add a test for `FinsDownloadRequest(..., form_types=("10-K/A",))`. |
| `_market_from_text` / `_exchange_from_optional_text` duplicate ticker normalization literal sets | MiMo F02 / DS F02 | accepted | The project constraint discourages duplicated magic strings. `ticker_normalization.Market` and `Exchange` are the type truth. Runtime validation should derive allowed values from that truth or a shared exported constant. | Replace hard-coded branches with validation derived from `typing.get_args(...)` for `Market` and `Exchange`, while keeping pyright-clean return types and illegal-value rejection tests. |
| `_write_record_locked` leaves temp files on write/replace failure | MiMo F01 / DS F03 | accepted | Atomic write implementations should clean temp files on failure. The fix is local, low risk, and directly supports the S1 job store durability boundary. | Add `try/except BaseException` cleanup around temp file creation/write/replace and test that a mocked failure removes the temp file. |
| `_StoreFileLock.__enter__` does not explicitly close opened stream if `flock` fails | DS F04 | accepted | The code should not rely on CPython reference counting for resource cleanup. The local fix is low risk. | Close the stream explicitly when `fcntl.flock(...)` raises and add a focused test. |
| `read_job` uses an exclusive store lock and serializes reads | MiMo F03 | rejected-with-reason | In S1 the store prioritizes correctness, atomic replacement and simple cross-instance safety over read throughput. There is no current concurrent read workload or correctness failure. Future S5 polling throughput may revisit shared/per-file read locks with evidence. | No S1 fix. Record as non-blocking performance observation if needed later. |

## Residual Risk Classification

| Risk | Classification | Owner / Destination |
|---|---|---|
| Four accepted S1 findings above | fixed in current slice after fix gate | `WU-TOOLS-01-F01` S1 |
| Read lock throughput | deferred-with-owner | Later S5 polling / performance hardening if evidence shows contention |
| Real preprocess pipeline | covered by later approved slice | `WU-TOOLS-01-F01` S2 |
| Real download runtime adapter protocol/fake path | covered by later approved slice | `WU-TOOLS-01-F01` S3 |
| Download/preprocess providers | covered by later approved slice | `WU-TOOLS-01-F01` S4 |
| Fins wait adapter and Service assembly | covered by later approved slice | `WU-TOOLS-01-F01` S5 |
| Real SEC/CN/HK network adapters | deferred-with-owner | Later Fins source-adapter owner or explicit user-approved F01 scope expansion |

## Next Gate

Plan: dispatch AgentCodex for S1 fix. Required validation after fix:

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py`
- `source .venv/bin/activate && pyright`
- `git diff --check`
