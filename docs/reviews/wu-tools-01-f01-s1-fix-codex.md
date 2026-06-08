# WU-TOOLS-01-F01 S1 Fix - Codex

## Gate Metadata

- Gate: fix.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S1 Shared Fins Runtime Foundation`.
- Scope: only code review accepted findings adjudicated in `docs/reviews/wu-tools-01-f01-s1-code-review-controller-adjudication.md`.
- Artifact path: `docs/reviews/wu-tools-01-f01-s1-fix-codex.md`.
- Stop condition: not hit. All accepted findings were fixed inside S1 allowed files without expanding scope.

## Changed Files

- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `docs/reviews/wu-tools-01-f01-s1-fix-codex.md`

No change was made to `dayu/fins/service_runtime.py`, Host, Engine, Service, config, provider, README, PR, branch control document, or control document.

## Finding Status

| Accepted finding | Status | Evidence |
|---|---|---|
| `_bounded_text` rejects slash and blocks valid SEC amended form types like `10-K/A` | 已修复 | `_bounded_text` / `_optional_bounded_text` / `_bounded_text_tuple` now accept `reject_path_separators`. `source` still rejects separators; `form_types` and document-id fields allow business-valid `/`. Added tests for `FinsDownloadRequest(ticker="AAPL", form_types=("10-K/A",))`, source separator rejection, preprocess slash fields, and result-summary document IDs. |
| `_market_from_text` / `_exchange_from_optional_text` duplicate ticker normalization literal sets | 已修复 | Runtime legal-value sets now derive from `typing.get_args(NormalizedTickerMarket)` and `typing.get_args(NormalizedTickerExchange)`, with pyright-clean casts at the validation boundary. Illegal values still raise `ValueError`. |
| `_write_record_locked` leaves temp files on write/replace failure | 已修复 | Atomic write now wraps temp creation, write, fsync, replace and directory fsync in `try/except BaseException`; failure unlinks the temp path and re-raises. Added focused `os.replace` failure test that asserts no `.*.tmp` file remains. |
| `_StoreFileLock.__enter__` should explicitly close opened stream if `fcntl.flock` raises | 已修复 | `__enter__` now closes the opened stream before re-raising when `fcntl.flock` fails. Added focused test that captures the fd and verifies it is closed after the failure. |

Rejected finding `read_job` exclusive lock serialization was not changed, per controller adjudication.

## Validation

Command:

```text
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py
```

Result:

```text
23 passed, 3 warnings
```

Warnings were existing third-party `edgar` deprecation warnings.

Command:

```text
source .venv/bin/activate && pyright
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

Pyright also printed a version-available notice (`1.1.409 -> 1.1.410`), not a type failure.

Command:

```text
git diff --check
```

Result: passed with no output.

## Docs Decision

No README was updated. The requested fix gate allowed files do not include README files, and this fix does not change user-facing commands, configuration entry points, architecture boundaries, provider behavior, or stable Fins README usage guidance.

## Residual Risks

| Risk | Classification | Owner / Destination |
|---|---|---|
| Four accepted S1 code review findings | fixed in current slice | `WU-TOOLS-01-F01` S1 |
| Read lock throughput observation | deferred-with-owner | Later S5 polling / performance hardening only if contention evidence appears |
| Real preprocess pipeline | covered by later approved slice | `WU-TOOLS-01-F01` S2 |
| Real download runtime adapter protocol / fake path | covered by later approved slice | `WU-TOOLS-01-F01` S3 |
| Download / preprocess providers | covered by later approved slice | `WU-TOOLS-01-F01` S4 |
| Fins wait adapter and Service assembly | covered by later approved slice | `WU-TOOLS-01-F01` S5 |
| Real SEC / CN / HK network adapters | assigned to later work unit | Later Fins source-adapter owner or explicit user-approved F01 scope expansion |

No unclassified residual risk remains for this fix gate.

## Completion Status

Fix gate work is complete. No commit, push, PR, re-review, accepted slice commit, deepreview, next gate action, or control document update was performed.
