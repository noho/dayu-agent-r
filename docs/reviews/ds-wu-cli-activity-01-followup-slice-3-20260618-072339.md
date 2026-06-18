# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `HEAD` (reviewing uncommitted Slice 3 workspace changes only)
- Output file: `docs/reviews/ds-wu-cli-activity-01-followup-slice-3-20260618-072339.md`
- Design truth: `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md` Slice 3
- Included scope:
  - `dayu/host/durable/event_log.py` — 新增 `EventLogReadClassFilter`、`EventLogReadFilter`、`FilteredEventLogPage`、`read_events_after_matching(...)` 及内部 helper
  - `dayu/host/projection.py` — 新增 `_event_log_read_filter_from_projection_filter(...)`，`ProjectionRunner` 改用 filtered read
  - `tests/host/test_event_log_store.py` — 新增 3 个 filtered read 测试
  - `tests/host/test_projection_runner.py` — 新增/更新 filtered read + runner 行为测试
  - `tests/host/test_projection_read_model.py` — 最小更新以适配新 `max_event_sequence` 语义
  - `docs/reviews/wu-cli-activity-01-followup-slice-3-implementation-codex-20260618.md` — Codex implementation report（作为参考，不作为 review 目标）
- Excluded scope:
  - 已提交 commits（Slice 1、Slice 2）
  - Slice 4/5 相关文件（`memory_repair.py`、`open_host.py`、`dispatch.py`、`run_input.py`）
  - `MemoryProjectionCatchupBudget` 移除（属 Slice 4）
- Parallel review coverage: 无

## Findings

### 01-未修复-低-ProjectionRunner run_once 每步传递冗余 read_limit 导致 filtered query 重复执行

- **入口/函数**: `ProjectionRunner.run_once` → `_process_next_event`
- **文件(行号)**: `dayu/host/projection.py:460-469`
- **输入场景**: `run_once(consumer_id, limit=N)` 被调用，EventLog 中存在多条连续 matching row
- **实际分支**: 循环内每步调用 `_process_next_event(transaction, consumer, read_limit=limit, ...)`，`_process_next_event` 将其原样传给 `read_events_after_matching(..., limit=read_limit)`；但 `_process_next_event` 只消费 `page.rows[0]`
- **预期行为**: 每步只需取一条 matching row；`read_limit` 的唯一 correctness 作用是决定 covered cursor 在"无匹配 row"时的推进幅度。当存在大量连续 matching row 时，`read_limit=N` 会每次返回 N 条 matching row 但仅消费第一条，后续 `N-1` 次循环中 checkpoint 已推进，需重新执行 filtered query
- **实际行为**: 同预期，每次 filtered query 均产生实际 SQL 执行，仅首条结果被使用；剩余 `N-1` 条被丢弃
- **直接证据**:
  - `dayu/host/projection.py:583-589` — `read_events_after_matching(..., limit=read_limit)` 传入 `read_limit`（即外部 `limit`）
  - `dayu/host/projection.py:620` — `row = page.rows[0]` 仅取首行
  - `dayu/host/projection.py:460` — `for _index in range(limit)` 循环上限同为 `limit`
- **影响**: 当 consumer filter 命中密集 matching row 且 `limit` 较大时，后续步骤的 filtered read 查询范围仅比前一步少一个 event_sequence，SQL 执行开销接近 O(N²)。对典型 EventLog 量级（数万行）和典型 batch_size（数十到数百）不构成可观测性能退化；仅在极端场景（百万行 + batch_size=10000）下可能显现
- **建议改法和验证点**: 将 `_process_next_event` 的 `read_limit` 改为 `max(read_limit, 剩余 step 数)` 或固定为 1，仅当 step 数为 1 或剩余少于此值时缩小 read_limit。但需验证：`read_limit=1` 时无匹配 row 的 covered cursor 只能推进到紧邻的下一条真实 row，可能增加总 step 数。当前实现以"较大 read_limit 换取较少无匹配 step"是合理的 tradeoff。建议在 `_process_next_event` 或 `run_once` docstring 中明确注释此 tradeoff
- **修复风险（低）**: 改动 read_limit 传递逻辑可能改变 covered cursor 推进粒度，影响无匹配 row 时的 step 计数
- **严重程度（低）**: 不构成 correctness 问题；仅在高 batch_size + 高匹配密度极端场景下有可观测但非阻塞的 SQL 效率损耗

### 02-未修复-低-FilteredEventLogPage covered cursor 语义在 page rows 填满时不验证 covered_event_id 一致性

- **入口/函数**: `read_events_after_matching`
- **文件(行号)**: `dayu/host/durable/event_log.py:719-727`
- **输入场景**: matching rows 数量 >= limit
- **实际分支**: `covered_row = matching_rows[-1]` (line 720)，`covered_event_sequence` 与 `covered_event_id` 取自最后一条 matching row
- **预期行为**: covered cursor 准确反映本次 page 已覆盖到的边界
- **实际行为**: 同预期。`FilteredEventLogPage.__post_init__` 在 line 244-249 已验证 `covered_event_sequence >= rows[-1].event_sequence`
- **直接证据**: `dayu/host/durable/event_log.py:720` — `covered_row = matching_rows[-1]`
- **影响**: 无 correctness 问题。此处仅记录为形式化确认：当 `len(rows) >= limit` 时，covered cursor 定为最后一条 matching row，该 row 必然存在于 EventLog 且其 `event_id` 非空，满足 `FilteredEventLogPage` 与 checkpoint schema 的不变量
- **建议改法和验证点**: 无需修改。提为 finding 仅为显式确认该分支的 covered cursor 语义与设计 doc "当有匹配 row 且达到 page limit 时，covered cursor 是最后一条匹配 row" 一致
- **修复风险（低）**: 无
- **严重程度（低）**: 无实质问题

### 03-未修复-低-session_id filtered read 参数在 ProjectionRunner 中未被使用且缺少集成测试覆盖

- **入口/函数**: `read_events_after_matching` — `session_id` 参数；`ProjectionRunner._process_next_event`
- **文件(行号)**: `dayu/host/durable/event_log.py:360` (参数声明)，`dayu/host/projection.py:583-589` (调用点未传 session_id)
- **输入场景**: 存在跨 session 的 EventLog rows；consumer 只关心特定 session
- **实际分支**: `_process_next_event` 调用 `read_events_after_matching` 时不传 `session_id`；filtered read 返回所有 session 的匹配 row
- **预期行为**: 对全局 projection（如 minimal read model），不过滤 session 是正确的。对 session-scoped projection，应在 read 层过滤 session 以避免无效匹配 row 进入 consumer。当前所有已注册 projection consumer（MinimalReadModel、ToolTrace、Audit、Outbox、ConversationMemory）均通过自身 `apply_event` 做 session 判断，未依赖 runner 层做 session 过滤
- **实际行为**: 同预期；`session_id` 参数在 `read_events_after_matching` 的 SQL 生成逻辑（`_event_log_session_filter_sql`、`_read_latest_covered_event_row`）已完整实现，单元测试 `test_read_events_after_matching_filters_mixed_classes_and_covers_latest` 未覆盖 session 维度，集成测试也未构造跨 session 场景
- **直接证据**:
  - `dayu/host/projection.py:583-589` — 调用点不传 `session_id`
  - `dayu/host/durable/event_log.py:1051-1061` — `_event_log_session_filter_sql` 实现完整
  - `tests/host/test_event_log_store.py` — 所有 `read_events_after_matching` 调用不传 `session_id`
- **影响**: Slice 3 当前无 session-scoped consumer，无 material 影响。Slice 5 (inline repair) 将使用 `session_id` 参数，届时需补齐测试。风险：若 Slice 5 实现者认为 `session_id` 已测试覆盖而跳过验证，可能遗漏 SQL 绑定顺序（`(cursor, *max_sequence_params, *session_params)` 与 SQL 片段顺序的一致性）问题
- **建议改法和验证点**: 在 `test_event_log_store.py` 中新增一个测试：`test_read_events_after_matching_with_session_id_filters_by_session`，构造两个 session 各追加匹配事件，验证只返回指定 session 的 rows 且 covered cursor 不超过该 session 边界
- **修复风险（低）**: 新增测试无回归风险
- **严重程度（低）**: `session_id` SQL/参数绑定经静态走读确认正确；缺测试为覆盖盲区而非已知缺陷

## 逐项 Focus Area 结论

以下按用户指定的 focus areas 逐项给出基于代码走读的证据结论：

### 1. `read_events_after_matching` SQL filter correctness

**结论：正确。**

- `_event_log_read_filter_sql` (line 1064-1084) 为每个 `EventLogReadClassFilter` 生成 `event_class = ?` 或 `(event_class = ? AND event_type IN (?, ...))` 条件，多 class filter 以 OR 连接
- 过滤 SQL 被外层 `AND ({filter_sql})` 包裹，避免 OR 与 AND 优先级问题
- `_event_log_session_filter_sql` (line 1051-1061) 正确生成 `AND session_id = ?` 或空
- 参数绑定顺序与 SQL 占位符顺序完全一致：
  - matching rows 查询 (line 710-716)：`(cursor, boundary_row.event_sequence, *session_params, *filter_params, limit)`
  - covered row 查询 (line 1044)：`(cursor, *max_sequence_params, *session_params)`
- durable helper 不包含任何 memory-specific event type 或 class 硬编码
- 测试 `test_read_events_after_matching_filters_mixed_classes_and_covers_latest` 覆盖三类 `EventClass` 混合 + 通配 `event_types=None` + 指定 `event_types` 的组合 OR 过滤

### 2. `covered_event_sequence`/`covered_event_id` boundaries

**结论：所有边界情况处理正确，与设计 doc 描述一致。**

| 场景 | 代码路径 | 预期 | 实际 | 测试 |
|------|---------|------|------|------|
| 空 EventLog | `_read_latest_covered_event_row` → None → `covered=cursor, id=None` | idle | ✅ | `test_...empty_log...are_idle` (cursor=7) |
| cursor 在 latest row | `event_sequence > cursor` 无结果 → None | idle | ✅ | `test_...empty_log...are_idle` (cursor=1 after append) |
| cursor 超过 latest | 同"空 EventLog"路径 | idle | ✅ | 同空 EventLog 测试路径 |
| max_event_sequence 超过 latest | `_read_latest_covered_event_row` 查询到实际 latest row | covered=latest | ✅ | `test_...covers_real_row...` (max=99, latest=5) |
| max_event_sequence 落在 gap | `ORDER BY event_sequence DESC` 返回 ≤max 的最近真实 row | covered=最近真实 row | ✅ | `test_...covers_real_row...` (max=4, gap at 4, actual=3) |
| max_event_sequence ≤ cursor | `event_sequence > cursor AND <= max` 永假 → None | idle | ✅ | 无显式测试，但语义正确 |
| 有 session_id 但 session 无 rows | 边界与匹配查询均附加 `AND session_id = ?` → None | idle | ✅ | 缺测试 (见 Finding 03) |

### 3. Same-transaction invariant

**结论：满足。**

- `read_events_after_matching` 在同一 `transaction` 对象上先后调用 `_read_latest_covered_event_row` (line 665) 和 matching rows 查询 (line 679)
- `_process_next_event` (line 556-645) 在同一 write transaction 内依次完成：checkpoint 读取 → filtered read → consumer apply → checkpoint advance → failure clear
- SQLite serializable 事务保证两个查询之间不会插入新 row
- `ProjectionRunner.run_once` 每个 step 都经 `self._transaction_runner.run_write(...)` 包裹为独立 transaction

### 4. No memory-specific logic in durable helper

**结论：满足。**

- `dayu/host/durable/event_log.py` 的 import 列表中无 `memory`、`conversation`、`projection` 引用
- `EventLogReadClassFilter` / `EventLogReadFilter` 使用泛型 `EventClass` 枚举 + 任意 `event_types: tuple[str, ...] | None`，不含 memory event type 硬编码
- `_event_log_read_filter_sql` 基于传入 filter 纯机械生成 SQL，不判断任何 event type 语义
- 转换函数 `_event_log_read_filter_from_projection_filter` 在 `projection.py` 中，不在 `event_log.py` 中

### 5. ProjectionRunner conversion from ProjectionEventFilter

**结论：机械 1:1 映射，正确。**

- `_event_log_read_filter_from_projection_filter` (line 706-724) 逐 `class_filter` 映射：
  - `ProjectionEventClassFilter.event_class` → `EventLogReadClassFilter.event_class`
  - `ProjectionEventClassFilter.event_types` → `EventLogReadClassFilter.event_types`
- 两个类型的 `__post_init__` 校验逻辑一致（非空 class、非空 types、不重复 event_class、不重复 event_type），转换前后均经过校验
- `_process_next_event` (line 580-582) 每次 step 都从 `consumer.event_filter` 重新转换，不会缓存可能变 stale 的 filter

### 6. Matching row apply/checkpoint

**结论：正确，同一事务内完成。**

- `_process_next_event` line 620-645：`projection_event_view_from_row(row)` → `consumer.apply_event(transaction, event)` → `advance_projection_checkpoint(transaction, ...)` → `clear_projection_failure(transaction, ...)`
- checkpoint 推进到该 matching row 的 `event_sequence` 与 `event_id`
- consumer 成功返回 `DUPLICATE` 或 `SKIPPED` 时同样推进 checkpoint（line 631-638）
- 测试 `test_runner_commits_projection_write_and_checkpoint_together` 验证 consumer projection write 与 checkpoint 在同一事务提交

### 7. No matching covered advance / no apply

**结论：正确。**

- `_process_next_event` line 590-618：`len(page.rows) == 0` 分支
- `page.covered_event_sequence > checkpoint` 时：`advance_projection_checkpoint(..., event_sequence=page.covered_event_sequence, event_id=page.covered_event_id)` + `clear_projection_failure`，不调用 consumer
- `page.covered_event_sequence == checkpoint` 时：返回 `scanned=False`，判定 idle
- 测试 `test_runner_advances_covered_cursor_without_apply_when_no_matching_rows` 验证无匹配时只推进 checkpoint 不 apply
- 测试 `test_runner_target_before_next_matching_row_advances_to_target_without_apply` 验证 `max_event_sequence` 落在匹配 row 之前时只推进 checkpoint 不 apply

### 8. Failure must not advance past failed matching row

**结论：正确。**

- `_ProjectionApplyFailed` 在 `consumer.apply_event` 抛出异常时被 raise (line 628)，此时 `advance_projection_checkpoint` 尚未执行；write transaction rollback 使 checkpoint 保持在 step 开始前的值
- `_ProjectionEventViewFailed` 同样在 `advance_projection_checkpoint` 之前 raise (line 624)
- `run_once` 捕获两者后调用 `_record_failure`（独立事务），`break` 退出循环
- 测试 `test_matching_row_failure_does_not_advance_past_failed_row` 验证：matching row 失败后 `checkpoint.checkpoint_event_sequence < failed.event_sequence`
- 测试 `test_payload_parsing_failure_records_failure_without_advancing_checkpoint` 验证 payload 不可解析时不推进 checkpoint
- 测试 `test_consumer_write_failure_rolls_back_write_and_checkpoint` 验证 consumer write 与 checkpoint 在失败时均 rollback

**补充验证**：失败行之前的 unmatched row 会在失败前的独立 step 中被 covered advance 推进 checkpoint，checkpoint 停留在 unmatched row 之后、failed matching row 之前——这正是设计预期的行为。失败行之前的不匹配行不会阻止 checkpoint 推进。

### 9. `run_once` limit semantics as page size/step cap

**结论：正确，语义与设计 doc 一致。**

- `run_once` docstring (line 427-437) 明确："``limit`` 是单步 filtered read page size 与本轮最多 read/apply step 数，不表达 consumer 必须停在某个语义 catch-up 预算"
- `for _index in range(limit)` (line 460) — step cap
- `read_events_after_matching(..., limit=read_limit)` 其中 `read_limit=limit` (line 466) — page size
- 循环会在 `scanned=False`（idle）、failure、或达到 limit 步数时终止
- `events_scanned` 计数的是 step 数（`scanned=True` 的 step），不是 EventLog row 数；测试断言已更新为 step 语义

### 10. Tests prove these behaviors

**结论：核心行为已覆盖，存在一个已知覆盖盲区 (Finding 03)。**

| 行为 | 测试 | 文件 |
|------|------|------|
| SQL class/type 过滤 | `test_read_events_after_matching_filters_mixed_classes_and_covers_latest` | `test_event_log_store.py:400` |
| 空 log / cursor 在 latest | `test_read_events_after_matching_empty_log_and_cursor_at_latest_are_idle` | `test_event_log_store.py:482` |
| max_event_sequence 边界 | `test_read_events_after_matching_covers_real_row_for_max_sequence_boundaries` | `test_event_log_store.py:528` |
| runner 跳过 unmatched | `test_runner_skips_unmatched_events_and_advances_to_matching_checkpoint` | `test_projection_runner.py:580` |
| 无匹配 covered advance | `test_runner_advances_covered_cursor_without_apply_when_no_matching_rows` | `test_projection_runner.py:623` |
| target before matching | `test_runner_target_before_next_matching_row_advances_to_target_without_apply` | `test_projection_runner.py:660` |
| failure 不越过失败行 | `test_matching_row_failure_does_not_advance_past_failed_row` | `test_projection_runner.py:699` |
| consumer write + checkpoint 同事务 | `test_runner_commits_projection_write_and_checkpoint_together` | `test_projection_runner.py:397` |
| failure rollback | `test_consumer_write_failure_rolls_back_write_and_checkpoint` | `test_projection_runner.py:429` |
| payload 解析失败 | `test_payload_parsing_failure_records_failure_without_advancing_checkpoint` | `test_projection_runner.py:469` |
| duplicate 仍推进 checkpoint | `test_duplicate_apply_result_still_advances_checkpoint` | `test_projection_runner.py:520` |
| success after failure clears | `test_success_after_failure_clears_failure_row` | `test_projection_runner.py:550` |
| 多 class 独立过滤 | `test_per_class_filters_do_not_share_event_type_sets` | `test_projection_runner.py:351` |
| session_id 过滤 | **缺测试** | — |
| 多 consumer run_all_once | 基础覆盖存在于已有 projection consumer tests | — |

## Open Questions

1. `session_id` 在 `read_events_after_matching` 中的 SQL 参数绑定顺序（`*max_sequence_params` 在 `*session_params` 之前）与 SQL 片段拼接顺序是否在所有 `max_event_sequence`+`session_id` 组合下保持一致？经静态走读确认一致（`max_sequence_sql` 在 `session_sql` 之前拼接，参数同样），但缺动态测试覆盖。

2. `ProjectionRunner._process_next_event` 不传 `session_id`，ConversationMemoryProjectionConsumer 在 Slice 4/5 是否需要 runner 层做 session 过滤？当前 consumer 自身在 `apply_event` 中按 session 做判断；若 Slice 5 inline repair 通过 runner 做 session-scoped catch-up，需决定是通过 runner 新增 `session_id` 参数还是在 read layer 透传。

## Residual Risk

- **session_id filtered read 未集成测试**（见 Finding 03 与 Open Question 1）：风险低，SQL 绑定顺序经静态走读确认正确。Slice 5 inline repair 将首次在集成场景使用 `session_id`。
- **`events_scanned` 语义变更的消费方影响**：Slice 4 (`memory_repair.py`) 当前使用 `events_scanned` 做 budget 耗尽判断；Slice 4 将删除 budget 语义，届时 `events_scanned` 仅保留诊断用途。Slice 3 未修改 `memory_repair.py` 的消费逻辑，存在短暂的语义不一致窗口（`events_scanned` 现在计 step 数而非 row 数），但 Slice 4 即将删除相关预算判断，窗口可接受。
- **`run_once` 对 `max_event_sequence <= started_cursor` 无显式早退**：当前行为正确（每步 idle → break），但缺少 early validation。若未来有人在 `_ensure_checkpoint` 和循环之间插入有副作用的 setup 逻辑，可能产生不必要的 setup 执行。
- **`_process_next_event` 每步做 filtered read 而只消费首行**：见 Finding 01。在极端场景下有可观测但非阻塞的 SQL 效率损耗；当前设计以较大的 read page 换取较少的无匹配 step，是正确的 tradeoff。
- **仅 `page.rows[0]` 消费**：当 `read_events_after_matching` 返回多行但 `_process_next_event` 只取首行时，其余匹配行在下次 step 重新查询。当前设计保证 per-transaction atomicity，是正确的；若未来需要 batch apply，需重新设计事务边界。

## Conclusion

Slice 3 实现正确满足了设计 doc 的全部要求。所有 10 个 focus area 经逐行代码走读和测试断言验证，未发现 correctness、state machine、data consistency 或 architecture boundary 问题。3 个低严重度 finding 中：Finding 01 为效率 tradeoff 注释建议，Finding 02 为形式化确认，Finding 03 为测试覆盖盲区。无阻塞性问题。
