# Phase 15 S5 Re-Review — AgentDS

- **Gate**: Phase 15 S5 re-review
- **Date**: 2026-05-29
- **Scope**: S5-ADJ-001 only（S5 新增/修改测试函数与 helper docstrings 中文完整性）
- **Controller adjudication**: `docs/reviews/phase15-s5-code-review-controller-adjudication-20260529.md`
- **Fix artifact**: `docs/reviews/phase15-s5-fix-codex-20260529.md`

## Verdict: PASS

## Evidence

### 1. Docstring 完整性逐函数复核

#### tests/host/test_projection_checkpoint.py

| 函数 | 行号 | :param | :returns | :raises | 判定 |
| --- | --- | --- | --- | --- | --- |
| `test_reset_refs_for_deleted_events_deletes_only_rebuildable_consumers` | 253 | ✅ | ✅ | ✅ AssertionError | PASS |
| `test_reset_refs_for_deleted_events_rejects_non_rebuildable_consumer` | 337 | ✅ | ✅ | ✅ AssertionError | PASS |

#### tests/host/test_projection_read_model.py

| 函数 | 行号 | :param | :returns | :raises | 判定 |
| --- | --- | --- | --- | --- | --- |
| `_close_request` | 294 | ✅ | ✅ | — | PASS |
| `_purge_request` | 308 | ✅ | ✅ | — | PASS |
| `_session_id_for_slot` | 335 | ✅ | ✅ | — | PASS |
| `_delete_checkpoint` | 408 | ✅ | ✅ | — | PASS |
| `_delete_minimal_read_model_owned_rows` | 423 | ✅ | ✅ | — | PASS |
| `_mark_run_terminal_for_projection_test` | 440 | ✅ | ✅ | ✅ AssertionError | PASS |
| `test_rebuild_after_purge_replays_remaining_eventlog_only` | 1081 | ✅ | ✅ | ✅ AssertionError | PASS |

#### tests/host/test_recovery_scan.py

| 函数 | 行号 | :param | :returns | :raises | 判定 |
| --- | --- | --- | --- | --- | --- |
| `test_scan_skips_non_terminal_run_when_session_row_is_missing` | 316 | ✅ | ✅ | ✅ AssertionError | PASS |
| `_delete_session_rows_without_foreign_keys` | 362 | ✅ | ✅ | ✅ sqlite3.Error | PASS |

#### tests/host/test_purge_session.py

| 函数 | 行号 | :param | :returns | :raises | 判定 |
| --- | --- | --- | --- | --- | --- |
| `_PurgeCapableHost.purge_session` | 146 | ✅ | ✅ | ✅ HostApiError | PASS |
| `_public_open_durable_options` | 200 | ✅ | ✅ | ✅ ValueError | PASS |
| `_purge_api_request` | 225 | ✅ | ✅ | — | PASS |
| `_retry_api_request` | 252 | ✅ | ✅ | ✅ ValueError | PASS |
| `_replay_api_request` | 280 | ✅ | ✅ | ✅ ValueError | PASS |
| `_json_lines` | 311 | ✅ | ✅ | ✅ AssertionError | PASS |
| `_json_object_file` | 328 | ✅ | ✅ | ✅ AssertionError, OSError, json.JSONDecodeError | PASS |
| `_purge_in_independent_process` | 503 | ✅ | ✅ | ✅ Exception | PASS |
| `_purge_in_independent_process_async` | 522 | ✅ | ✅ | ✅ Exception | PASS |
| `_read_after_purge_in_independent_process` | 556 | ✅ | ✅ | ✅ Exception | PASS |
| `_read_after_purge_in_independent_process_async` | 575 | ✅ | ✅ | ✅ AssertionError, Exception | PASS |
| `_host_api_error_code` | 622 | ✅ | ✅ | ✅ AssertionError | PASS |
| `test_public_purge_is_observed_by_independent_process_read_paths` | 2929 | ✅ | ✅ | ✅ AssertionError | PASS |

**总计：4 文件 24 个 S5 新增函数/方法，全部 PASS。**

### 2. Docstring-only 确认

- 修复范围与 fix artifact 声称一致：仅 `tests/host/test_projection_checkpoint.py`、`tests/host/test_projection_read_model.py`、`tests/host/test_recovery_scan.py`、`tests/host/test_purge_session.py` 四个测试文件。
- 未发现测试断言、控制流、imports 或生产代码行为变更。
- 生产代码文件（`dayu/host/durable/projection.py`、`dayu/host/durable/purge.py`、`dayu/host/recovery.py`、`dayu/host/dispatch.py`）的修改属于 S5 原始实现范围，未被 docstring fix 触及。

### 3. 测试与类型检查

```text
56 passed in 1.27s
0 errors, 0 warnings, 0 informations
```

### 4. 异常说明策略

- 测试函数统一使用 `AssertionError` 描述断言失败暴露方式。
- I/O 相关 helper（`_json_object_file`、`_delete_session_rows_without_foreign_keys`）补齐了对应底层异常（`OSError`、`json.JSONDecodeError`、`sqlite3.Error`）。
- 多进程 helper（`_purge_in_independent_process` 等）使用 `Exception` 描述子进程内透传异常，符合 fix strategy 中的 "按测试真实暴露方式书写" 约定。

## Residual Notes

- 无新增 blocker。
- 生产代码的 S5 行为正确性在原始 DS review 中已 PASS，本次 re-review 不重复评估。
- 预存在的测试函数 docstring 不一致（部分有完整 docstring、部分仅有单行描述）不在 S5-ADJ-001 范围内，不需要修复。

---

# Phase 15 S5 Second Re-Review — AgentDS

- **Gate**: Phase 15 S5 second re-review follow-up
- **Date**: 2026-05-29
- **Scope**: 复核 follow-up docstring-only fix（补 `:raises`）是否仍为 docstring-only、S5-ADJ-001 是否完全 fixed

## Verdict: PASS

## Follow-up Fix 变更复核

Fix artifact `phase15-s5-fix-codex-20260529.md` Follow-up Fix 节列出了 6 个缺少 `:raises` 的 S5 helper：

| Helper | 文件 | 行号 | `:raises` 补齐 | 判定 |
| --- | --- | --- | --- | --- |
| `_close_request` | test_projection_read_model.py | 294 | `ValueError` | PASS |
| `_purge_request` | test_projection_read_model.py | 309 | `ValueError` | PASS |
| `_session_id_for_slot` | test_projection_read_model.py | 337 | `HostApiError` | PASS |
| `_delete_checkpoint` | test_projection_read_model.py | 411 | `HostDurableError` | PASS |
| `_delete_minimal_read_model_owned_rows` | test_projection_read_model.py | 427 | `HostDurableError` | PASS |
| `_purge_api_request` | test_purge_session.py | 225 | `ValueError` | PASS |

### Docstring-only 确认

- 6 个 helper 仅 docstring 行新增 `:raises`，无断言、控制流、imports 变更。
- 生产代码文件未被 follow-up 触及。
- 第一轮 re-review 中已 PASS 的 24 个函数 docstring 不受影响。

### 验证

```text
56 passed in 1.26s
0 errors, 0 warnings, 0 informations (pyright)
```

### S5-ADJ-001 封闭状态

第一轮补齐 `:param`/`:returns`/`:raises` 后，所有 S5 新增函数已覆盖完整中文 docstring。第二轮流 follow-up 补齐了剩余 6 个无异常 helper 的 `:raises`。至此 S5-ADJ-001 完全 fixed，无新 blocker。
