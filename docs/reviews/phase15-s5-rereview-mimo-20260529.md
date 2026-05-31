# Phase 15 S5 Re-Review: S5-ADJ-001

- **Gate**: Phase 15 S5 re-review
- **Date**: 2026-05-29
- **Finding**: S5-ADJ-001 — S5 新增/修改测试函数与 helper docstrings 是否已补齐中文参数、返回值、异常说明
- **Controller adjudication**: `docs/reviews/phase15-s5-code-review-controller-adjudication-20260529.md`
- **Fix artifact**: `docs/reviews/phase15-s5-fix-codex-20260529.md`

## First Pass Verdict

**PASS**（首次 re-review，3 个 helper 缺 `:raises` 判定为不构成 blocker）

## Follow-up Pass Verdict

**PASS**（二次 re-review，follow-up 已补齐全部 `:raises`，S5-ADJ-001 完全 fixed）

## Analysis

### 1. Fix 是否为 docstring-only，无行为改动

确认为 docstring-only。S5 实现（`phase15-s5-implementation-codex-20260529.md`）新增了以下测试函数和 helper，fix pass + follow-up 仅在其上补齐 docstring：

| 文件 | S5 新增函数 | 类型 |
|---|---|---|
| `test_projection_checkpoint.py` | `test_reset_refs_for_deleted_events_deletes_only_rebuildable_consumers` | 测试 |
| `test_projection_checkpoint.py` | `test_reset_refs_for_deleted_events_rejects_non_rebuildable_consumer` | 测试 |
| `test_projection_read_model.py` | `_close_request` | helper |
| `test_projection_read_model.py` | `_purge_request` | helper |
| `test_projection_read_model.py` | `_session_id_for_slot` | helper |
| `test_projection_read_model.py` | `_mark_run_terminal_for_projection_test` | helper |
| `test_projection_read_model.py` | `test_rebuild_after_purge_replays_remaining_eventlog_only` | 测试 |
| `test_recovery_scan.py` | `test_scan_skips_non_terminal_run_when_session_row_is_missing` | 测试 |
| `test_recovery_scan.py` | `_delete_session_rows_without_foreign_keys` | helper |
| `test_recovery_scan.py` | `_event_type_count` | helper |
| `test_purge_session.py` | `_PurgeCapableHost` (Protocol class) | 协议 |
| `test_purge_session.py` | `_public_open_durable_options` | helper |
| `test_purge_session.py` | `_retry_api_request` | helper |
| `test_purge_session.py` | `_replay_api_request` | helper |
| `test_purge_session.py` | `_json_object_file` | helper |
| `test_purge_session.py` | `_purge_in_independent_process` | helper |
| `test_purge_session.py` | `_purge_in_independent_process_async` | helper |
| `test_purge_session.py` | `_read_after_purge_in_independent_process` | helper |
| `test_purge_session.py` | `_read_after_purge_in_independent_process_async` | helper |
| `test_purge_session.py` | `_host_api_error_code` | helper |
| `test_purge_session.py` | `test_public_purge_is_observed_by_independent_process_read_paths` | 测试 |

- 所有 S5 新增函数均已在 HEAD 中不存在（`git show HEAD:...` 确认），属于本次 branch 的新增代码。
- 生产代码（`dayu/host/`）仅有 S5 实现阶段的原始变更，fix pass + follow-up 未新增任何生产代码改动。
- 测试断言、控制流、imports 均未改动。

### 2. Docstring 完整性检查

使用 AST 自动扫描全部 21 个 S5 新增函数/方法：

**首次 pass**：18 OK，3 缺 `:raises`（`_close_request`、`_purge_request`、`_session_id_for_slot`）。

**Follow-up 补齐**：

| 函数 | 补充的 `:raises` |
|---|---|
| `_close_request` | `:raises ValueError: 请求字段非法时由 dataclass 校验抛出。` |
| `_purge_request` | `:raises ValueError: 请求字段非法时由 dataclass 校验抛出。` |
| `_session_id_for_slot` | `:raises HostApiError: ensure_session public command 失败时抛出。` |

Follow-up 同时为已有 helper `_delete_checkpoint` 和 `_delete_minimal_read_model_owned_rows` 补充了 `:raises HostDurableError`（bonus，超出 S5-ADJ-001 范围但无副作用）。

**二次 pass 结果**：21/21 全部 OK，`:param` + `:returns` + `:raises` 三要素齐全。

### 3. 验证

- `pytest` 56 passed in 1.28s ✅
- `pyright` 0 errors, 0 warnings, 0 informations ✅

### 4. 无新 Blocker

Follow-up 仅追加 `:raises` 行，未引入任何行为变更、新依赖、新 import 或新的架构违反。S5-ADJ-001 完全 fixed。
