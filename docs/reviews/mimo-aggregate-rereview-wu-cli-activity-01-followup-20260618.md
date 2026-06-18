# Re-Review — WU-CLI-ACTIVITY-01 Follow-up Aggregate Fix

## Scope

- Mode: current changes (uncommitted diff)
- Branch: `wu-cli-activity-01`
- Base: uncommitted working tree vs last commit `49c813a5`
- Fix artifact: `docs/reviews/wu-cli-activity-01-followup-aggregate-fix-codex-20260618.md`
- Prior review: `docs/reviews/mimo-aggregate-wu-cli-activity-01-followup-20260618-081816.md`
- Output file: `docs/reviews/mimo-aggregate-rereview-wu-cli-activity-01-followup-20260618.md`

## Convered Scope

4 files changed, 90 insertions, 5 deletions:

| 文件 | 变更 |
|---|---|
| `tests/host/test_event_log_store.py` | +42 — 新增 `test_read_events_after_matching_limit_covers_last_matching_row` |
| `tests/host/test_projection_runner.py` | +47 — 新增 `test_runner_clears_failure_when_covered_cursor_advances_without_match` |
| `dayu/host/read_api.py` | -4 — 移除 `_EVENT_TYPE_CONTENT_DELTA`/`_EVENT_TYPE_REASONING_DELTA` 常量及 dead code 过滤 |
| `dayu/host/memory_repair.py` | ±1 — `_validate_batch_size` docstring 对齐 page size 语义 |

## Finding Verification

### Finding #1: `matching_rows >= limit` 分支缺少显式测试 → 已覆盖

**新测试**: `test_read_events_after_matching_limit_covers_last_matching_row` (test_event_log_store.py:483)

**验证逻辑**:
- 插入 3 个事件：event-1 (TYPE_A, seq=1), event-2 (TYPE_A, seq=2), event-3 (TYPE_B, seq=3)
- Filter: `CANONICAL_FACT + TYPE_A`，limit=2
- Boundary row = seq=3（未过滤最新 row）
- Filtered query 返回 2 个匹配 rows (seq=1, seq=2)
- `len(matching_rows) = 2 >= limit = 2` → 走 `covered_row = matching_rows[-1]` 分支（event_log.py:731-732）
- 断言：`covered_event_sequence == 2`，`covered_event_id == "event-2"`

**结论**: ✅ 正确覆盖 `matching_rows >= limit` 分支，验证 `covered_event_sequence` 停在最后一个匹配 row 而非 boundary row。

### Finding #2: ProjectionRunner 无匹配 covered cursor 推进未测试 `clear_projection_failure` → 已覆盖

**新测试**: `test_runner_clears_failure_when_covered_cursor_advances_without_match` (test_projection_runner.py:661)

**验证逻辑**:
- 插入 1 个事件 event-1 (TYPE_B)，写入 projection failure
- Consumer filter: TYPE_A（不匹配 event-1）
- 运行 `ProjectionRunner.run_once(limit=10)`
- `_process_next_event` 路径：page.rows 为空，`covered_event_sequence > checkpoint` → 推进 checkpoint 并调用 `clear_projection_failure`（projection.py:611）
- 断言：`events_scanned == 1`，`events_matched == 0`，`finished_cursor == latest.event_sequence`，`failure is None`

**结论**: ✅ 正确覆盖无匹配 covered cursor 推进路径的 failure 清除逻辑。

### Finding #3: `read_api.py` delta dead code cleanup → 行为不变

**变更**: 移除 `_EVENT_TYPE_CONTENT_DELTA`、`_EVENT_TYPE_REASONING_DELTA` 常量定义（行 102-103）及 `_activity_from_row` 中的过滤分支（行 1061-1062）。

**行为分析**:
- 这些常量和过滤分支在旧代码中用于从 activity view 中排除 delta rows
- 自 slice-1 起，`engine_ingest.py:928` 的 `_is_transient_delta_event` 已在 ingest 入口短路 delta events，不再产生 durable rows
- `grep -rn "_EVENT_TYPE_CONTENT_DELTA\|_EVENT_TYPE_REASONING_DELTA" dayu/host/read_api.py` 返回空 — 无残留引用
- 移除 dead code 不改变任何可达代码路径的行为

**结论**: ✅ 行为不变，dead code 清理正确。

### Docstring 对齐 → 正确

**变更**: `_validate_batch_size` docstring 从 `"每批最多扫描的 EventLog row 数"` 改为 `"每次 projection 读取使用的 page size"`。

**结论**: ✅ 与 `memory_repair.py` 全文及 `ProjectionRunner` 语义一致。

## Public API / Contract Drift 检查

| 检查项 | 结果 |
|---|---|
| `read_api.py` 移除的常量是否为 public export | PASS — 均为模块私有（`_` 前缀），不在 `__all__` 或包根导出中 |
| 新增测试是否引入新依赖 | PASS — 仅使用已有 `write_projection_failure`（从 `durable.projection` 导入） |
| Pyright | PASS — 0 errors, 0 warnings, 0 informations |
| 全量测试 | PASS — 237 passed, 0 failures |

## Residual Risk

无。

## Conclusion

**PASS。** 4 项变更全部正确覆盖了 aggregate review 的 3 项 low findings：

1. ✅ Finding #1 — `matching_rows >= limit` 分支有显式测试
2. ✅ Finding #2 — 无匹配 covered cursor 推进路径有 failure 清除测试
3. ✅ Finding #3 — dead code 清理，行为不变
4. ✅ Docstring 对齐 page size 语义

无阻断 finding。无 public API/contract drift。无新类型/测试问题。
