# WU-TOOLS-01-F01 S1 Fix Re-Review

## Metadata

- Gate: re-review (fix verification).
- Work unit: `WU-TOOLS-01-F01`.
- Slice: S1 Shared Fins Runtime Foundation.
- Code review artifacts:
  - `docs/reviews/wu-tools-01-f01-s1-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-s1-code-review-ds.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f01-s1-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-tools-01-f01-s1-fix-codex.md`
- Re-review artifact: `docs/reviews/wu-tools-01-f01-s1-rereview-ds.md`

## Scope

Re-review only the four controller-accepted findings. No new full code review. No file modifications, no commit/push/PR.

## Overall Verdict

全部四项已接受 finding 均已修复，修复方式符合 controller adjudication 要求的改法，测试覆盖到位，pyright 零错误。无阻塞性 residual risk。

## Finding Status Table

| Finding | 状态 | 验证证据 |
|---|---|---|
| `_bounded_text` slash semantics | 已修复 | `_bounded_text` / `_optional_bounded_text` / `_bounded_text_tuple` 新增 `reject_path_separators` 参数（默认 `True`）；`source` 字段保持拒绝路径分隔符；`form_types`、`document_ids`、`written_document_ids`、`processed_document_ids` 传 `reject_path_separators=False` 允许业务合法 `/`。测试覆盖：`test_start_download_allows_sec_amended_form_type`（`"10-K/A"`）、`test_start_download_still_rejects_path_separator_in_source`（`"../sec"`）、`test_start_preprocess_allows_slash_in_document_ids`（`"sec/aapl-2024-10ka"` 和 `"10-K/A"`）、`test_result_summaries_allow_slash_in_document_ids`。 |
| market/exchange deserialization | 已修复 | `_NORMALIZED_MARKET_VALUES` 和 `_NORMALIZED_EXCHANGE_VALUES` 通过 `frozenset(cast(..., get_args(...)))` 从 `ticker_normalization.Market`/`Exchange` 的 Literal 类型推导，作为运行时合法值唯一真源。`_market_from_text` 和 `_exchange_from_optional_text` 改为 `if value in _NORMALIZED_*_VALUES` 成员判断，非法值仍抛 `ValueError`。`cast` 仅在 validated 边界使用，pyright 零错误。所有现有 job record round-trip 测试继续通过。 |
| `_write_record_locked` temp file cleanup | 已修复 | 临时文件创建/写入/fsync/os.replace/dir fsync 整体包裹在 `try/except BaseException` 中；异常时执行 `tmp_path.unlink(missing_ok=True)` 后 re-raise。测试 `test_job_store_removes_temp_file_when_atomic_replace_fails` mock `os.replace` 抛 `OSError` 并断言 `assert tuple(jobs_dir.glob(".*.tmp")) == ()`。 |
| `_StoreFileLock.__enter__` stream close on flock failure | 已修复 | `__enter__` 中 `stream = self._path.open(...)` 后，`fcntl.flock(...)` 包裹在 `try/except BaseException` 中；异常时显式 `stream.close()` 再 `raise`；成功时才赋值 `self._stream = stream`。测试 `test_store_file_lock_closes_stream_when_flock_fails` mock `fcntl.flock` 抛 `OSError`，捕获 fd 后通过 `os.fstat(captured_fd)` 抛 `OSError` 验证 fd 已关闭。 |

## Rejected Finding 确认

| Finding | 状态 | 验证 |
|---|---|---|
| `read_job` exclusive lock serialization | 未修改（符合裁决） | `read_job`（`ingestion_runtime.py:459`）仍使用 `with _StoreFileLock(self.root_dir / _LOCK_FILE_NAME):` 独占锁；controller 已裁决 `rejected-with-reason`，不在 S1 修复范围。代码未因其他修改而破坏此行为。 |

## Validation Run

```text
$ pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -v
23 passed, 3 warnings in 1.03s
```

Warnings 为第三方 `edgar` 弃用提示，非本次修改引入。

```text
$ pyright
0 errors, 0 warnings, 0 informations
```

## Residual Risks

| Risk | Classification | Owner / Destination |
|---|---|---|
| 四项已接受 S1 code review finding | 已在当前 slice 修复并验证 | `WU-TOOLS-01-F01` S1 |
| Read lock 吞吐 | deferred-with-owner | 后续 S5 polling / performance hardening |
| 真实 preprocess pipeline | covered by later approved slice | `WU-TOOLS-01-F01` S2 |
| 真实 download runtime adapter protocol/fake path | covered by later approved slice | `WU-TOOLS-01-F01` S3 |
| Download/preprocess providers | covered by later approved slice | `WU-TOOLS-01-F01` S4 |
| Fins wait adapter and Service assembly | covered by later approved slice | `WU-TOOLS-01-F01` S5 |
| 真实 SEC/CN/HK 网络 adapters | assigned to later work unit | 后续 Fins source-adapter owner |

无新增 unclassified residual risk。
