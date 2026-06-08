# WU-TOOLS-01-F01 S1 Fix Re-Review - MiMo

## Metadata

- Gate: re-review.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: S1 Shared Fins Runtime Foundation.
- Scope: only re-review controller accepted findings from `docs/reviews/wu-tools-01-f01-s1-code-review-controller-adjudication.md`.
- Code review artifacts:
  - `docs/reviews/wu-tools-01-f01-s1-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-s1-code-review-ds.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f01-s1-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-tools-01-f01-s1-fix-codex.md`
- Re-review artifact: `docs/reviews/wu-tools-01-f01-s1-rereview-mimo.md`
- Validation run: `pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py` (23 passed, 3 warnings) + `pyright dayu/fins/ingestion_runtime.py` (0 errors)

## Overall Verdict

All 4 accepted findings are 已修复. No remaining blockers for S1 slice commit.

## Finding Status Table

| # | Finding | Status | Evidence |
|---|---|---|---|
| 1 | `_bounded_text` slash semantics: source-like fields reject path separators; form_types/document-id fields allow business-valid slash including `10-K/A` | 已修复 | `_bounded_text` / `_optional_bounded_text` / `_bounded_text_tuple` 接受 `reject_path_separators: bool = True` 参数（`ingestion_runtime.py:880, 905-910, 930-935`）。`source` 调用保持默认 `True`（line 617）；`form_types` 和 `document_ids` 调用显式传 `reject_path_separators=False`（lines 620-621, 654-655）；result summary 的 `written_document_ids` 和 `processed_document_ids` 同样传 `False`（lines 183, 229）。测试覆盖：`test_start_download_allows_sec_amended_form_type`（`10-K/A`）、`test_start_download_still_rejects_path_separator_in_source`（`../sec`）、`test_start_preprocess_allows_slash_in_document_ids`（`sec/aapl-2024-10ka`）、`test_result_summaries_allow_slash_in_document_ids`。 |
| 2 | `market`/`exchange` 反序列化从 `ticker_normalization.Market`/`Exchange` 派生合法值 | 已修复 | 模块级常量 `_NORMALIZED_MARKET_VALUES` 和 `_NORMALIZED_EXCHANGE_VALUES`（lines 46-51）通过 `frozenset(cast(..., get_args(...)))` 从 `NormalizedTickerMarket` / `NormalizedTickerExchange` Literal 类型提取合法值，是 single truth。`_market_from_text`（line 1144）和 `_exchange_from_optional_text`（line 1164）使用 `in` 检查这些 frozenset，非法值仍抛 `ValueError`。pyright clean（0 errors）。 |
| 3 | `_write_record_locked` 在写入/替换失败时清理 temp file | 已修复 | `_write_record_locked`（lines 549-559）用 `try/except BaseException` 包裹 temp file 创建、写入、fsync、replace 和 directory fsync；`except` 中执行 `tmp_path.unlink(missing_ok=True)` 后 re-raise。测试 `test_job_store_removes_temp_file_when_atomic_replace_fails` mock `os.replace` 抛 `OSError`，断言 `jobs_dir.glob(".*.tmp")` 为空。 |
| 4 | `_StoreFileLock.__enter__` 在 `flock` 失败时关闭已打开的 stream | 已修复 | `__enter__`（lines 793-799）打开 stream 后用 `try/except BaseException` 包裹 `fcntl.flock` 调用；`except` 中执行 `stream.close()` 后 re-raise。测试 `test_store_file_lock_closes_stream_when_flock_fails` mock `fcntl.flock` 抛 `OSError`，捕获 fd 并验证 `os.fstat(captured_fd)` 抛 `OSError`（fd 已关闭）。 |

## Validation Run

```
$ source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -v
23 passed, 3 warnings

$ source .venv/bin/activate && pyright dayu/fins/ingestion_runtime.py
0 errors, 0 warnings, 0 informations
```

Warnings 均为第三方 `edgar` 库 deprecation warnings，与本 slice 无关。

## Residual Risks

| Risk | Classification | Owner / Destination |
|---|---|---|
| Read lock throughput observation（rejected finding） | deferred-with-owner | Later S5 polling / performance hardening only if contention evidence appears |
| Real preprocess pipeline | covered by later approved slice | `WU-TOOLS-01-F01` S2 |
| Real download runtime adapter protocol / fake path | covered by later approved slice | `WU-TOOLS-01-F01` S3 |
| Download / preprocess providers | covered by later approved slice | `WU-TOOLS-01-F01` S4 |
| Fins wait adapter and Service assembly | covered by later approved slice | `WU-TOOLS-01-F01` S5 |

无新增 residual risk。S1 fix gate 无 blockers。
