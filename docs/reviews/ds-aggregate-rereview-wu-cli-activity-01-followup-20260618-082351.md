# Code Review — WU-CLI-ACTIVITY-01 Follow-up Aggregate Fix Re-Review

## Scope

- Mode: focused re-review (uncommitted diff only)
- Branch: wu-cli-activity-01
- Base for re-review: aggregate review `docs/reviews/ds-aggregate-wu-cli-activity-01-followup-20260618-081532.md` + AgentMiMo aggregate findings `docs/reviews/mimo-aggregate-wu-cli-activity-01-followup-20260618-081816.md`
- Fix artifact: `docs/reviews/wu-cli-activity-01-followup-aggregate-fix-codex-20260618.md`
- Output file: `docs/reviews/ds-aggregate-rereview-wu-cli-activity-01-followup-20260618-082351.md`
- Included scope:
  - `dayu/host/read_api.py` — delta event dead code removal
  - `dayu/host/memory_repair.py` — docstring alignment
  - `tests/host/test_event_log_store.py` — new test for `matching_rows >= limit` branch
  - `tests/host/test_projection_runner.py` — new test for `clear_projection_failure` on no-match covered cursor advancement
- Excluded scope: all other production/test files (unchanged by this fix)

## Conclusion

**PASS** — 无阻断 finding。四个变更均正确、完整、无回归。

## Verification Matrix

| # | 检查项 | 结果 | 直接证据 |
|---|--------|------|----------|
| 1 | MiMo finding #1: `matching_rows >= limit` 分支测试 | ✅ PASS | `test_event_log_store.py:483-523` — 构造 2 个 TYPE_A 匹配行 + 1 个 TYPE_B 非匹配行，limit=2 触发 `len(matching_rows) >= limit` 分支，断言 `covered_event_id="event-2"`（最后匹配行，非 boundary row） |
| 2 | MiMo finding #2: no-match covered cursor 清除 failure 测试 | ✅ PASS | `test_projection_runner.py:661-709` — 写入旧 failure → runner 以 TYPE_A filter 扫描 TYPE_B event → 断言 `failure is None`、`events_scanned=1`、`events_matched=0`、`finished_cursor=latest.event_sequence` |
| 3 | MiMo finding #3: read_api delta dead code cleanup | ✅ PASS | `read_api.py:102-103` 删除 `_EVENT_TYPE_CONTENT_DELTA` / `_EVENT_TYPE_REASONING_DELTA` 常量定义；`read_api.py:1061` 删除 `if row.event_type in (CONTENT_DELTA, REASONING_DELTA): return None` 守卫。`_activity_from_row` 以 allowlist 匹配，未匹配的 event type 已通过行 1084 的 `return None` 兜底，移除显式 delta 守卫不改变行为 |
| 4 | memory_repair docstring 对齐 page size | ✅ PASS | `memory_repair.py:317` — docstring 从 "每批最多扫描的 EventLog row 数" 改为 "每次 projection 读取使用的 page size" |
| 5 | 无 public API / contract drift | ✅ PASS | 变更仅限内部实现（dead code removal + docstring），未修改任何 public dataclass、function signature、`__all__` 导出或 README |
| 6 | pyright | ✅ PASS | `dayu/ tests/ utils/` — 0 errors, 0 warnings, 0 informations |
| 7 | 受影响测试 | ✅ PASS | 184 passed (`test_event_log_store.py` 35, `test_projection_runner.py` 34, `test_memory_repair.py` 39, `test_run_input_builder.py` 45, `test_memory_projection.py` 11, `test_engine_ingest_mapping.py` 20) |

## Findings

未发现实质性问题。

## Detailed Trace

### Finding #1 fix — `test_read_events_after_matching_limit_covers_last_matching_row`

- **验证路径**: event-1 (TYPE_A, matching), event-2 (TYPE_A, matching), event-3 (TYPE_B, non-matching)
- **limit=2**, filter C=ANONICAL_FACT, T=TYPE_A
- **预期覆盖**: `covered_row = matching_rows[-1]` 即 event-2（`event_sequence=2`），而非 `boundary_row` 即 event-3
- **断言**: `covered_event_sequence=2`, `covered_event_id="event-2"` — 吻合代码行 `event_log.py:731-732`

### Finding #2 fix — `test_runner_clears_failure_when_covered_cursor_advances_without_match`

- **验证路径**:
  1. 写入 event-1 (TYPE_B, 非 consumer 关注类型)
  2. 写入旧 projection failure 标记 consumer 在 event-1 位置失败
  3. consumer filter 只关注 TYPE_A → read_events_after_matching 返回零匹配行，但 boundary_row=event-1 推进 covered cursor
  4. `_process_next_event` 走 `page.rows == 0 and covered_event_sequence > checkpoint` 分支（`projection.py:597`），调用 `clear_projection_failure`（`projection.py:611`）
- **断言**: `failure is None`（failure 被清除），`events_scanned=1`（一次 productive step），`events_matched=0`（未命中 consumer filter），`finished_cursor=1`（checkpoint 推进到 boundary row）

### Finding #3 fix — read_api dead code

- **删除代码位置**: `read_api.py:102-103`（常量），`read_api.py:1058-1059` 即原行 `1061`（守卫分支）
- **安全分析**: `_activity_from_row` 匹配逻辑为 allowlist（行 1059-1083），未命中任何已知 event type 的 EventLog row 最终走到行 1084 `return None`。删除显式 delta 过滤后，若 delta row 进入此函数（仅当旧数据库中有 delta row 且用户执行 watch），行为从"显式 return None"变为"走 allowlist 全部不命中 → return None"，结果一致
- **附加验证**: `TOOL_CALL_DELTA` 从未在 read_api 中有显式过滤或常量定义，证明旧代码本身不一致；删除后与 TOOL_CALL_DELTA 行为统一

### Finding #4 fix — docstring

- **变更**: `_validate_batch_size` docstring 的 `:param batch_size:` 从 "每批最多扫描的 EventLog row 数" 改为 "每次 projection 读取使用的 page size"，与设计文档 `docs/host/design.md:99` 的 "memory projection catch-up page size" 对齐

## Open Questions

无。

## Residual Risk

- 旧数据库中存在 delta EventLog rows 的场景：若从 delta-durable 旧版本升级到当前版本后再执行 `watch_session_events`，旧的 delta rows 在 activity allowlist 中不匹配任何已知 event type，会走到 `return None` 兜底，与显式过滤行为一致。此场景属于跨版本兼容性，当前设计不承诺旧版本数据库的 delta row 行为兼容；无实际风险。
