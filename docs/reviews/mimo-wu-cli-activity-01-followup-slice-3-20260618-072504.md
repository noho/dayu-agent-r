# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/mimo-wu-cli-activity-01-followup-slice-3-20260618-072504.md`
- Included scope:
  - `dayu/host/durable/event_log.py` — 新增 `EventLogReadClassFilter`、`EventLogReadFilter`、`FilteredEventLogPage`、`read_events_after_matching` 及私有 helpers
  - `dayu/host/projection.py` — 新增 `_event_log_read_filter_from_projection_filter`，`ProjectionRunner._process_next_event` 改用 filtered page
  - `tests/host/test_event_log_store.py` — 新增 3 个 filtered read 测试
  - `tests/host/test_projection_runner.py` — 新增 4 个 runner 测试，更新 1 个断言
  - `tests/host/test_projection_read_model.py` — 最小更新 failing consumer 测试
  - `docs/reviews/wu-cli-activity-01-followup-slice-3-implementation-codex-20260618.md` — 实施报告
- Excluded scope: 已提交 commits（Slice 1/2）；Slice 4/5 未实现部分
- Parallel review coverage: 3 个 subagent 分别覆盖 event_log.py 实现、projection.py 实现、测试覆盖度

## Findings

### 001-未修复-低-limit 作为 step cap 边界未被测试覆盖

- **入口/函数**: `ProjectionRunner.run_once(dayu/host/projection.py:460)`
- **文件(行号)**: `dayu/host/projection.py:460`, `tests/host/test_projection_runner.py`
- **输入场景**: 5 条匹配事件，`limit=3`，预期只处理 3 条
- **实际分支**: `for _index in range(limit)` 循环在 `limit` 次迭代后终止
- **预期行为**: 测试应断言 `events_matched == 3` 且剩余 2 条未处理
- **实际行为**: 所有现有测试要么使用足够大的 `limit` 耗尽全部事件，要么使用 `limit=1` 恰好处理 1 条事件；没有测试验证 `limit` 作为 step cap 在仍有剩余事件时的实际截断行为
- **直接证据**: `test_projection_runner.py` 中无测试构造"事件数 > limit"场景；`range(limit)` (line 460) 的截断语义仅通过代码阅读确认
- **影响**: 若 `range(limit)` 被意外修改为其他循环条件，现有测试无法捕获回归
- **建议改法和验证点**: 新增测试：追加 5 条匹配事件，`limit=3`，断言 `events_matched == 3`、`finished_cursor` 指向第 3 条匹配事件的 sequence、checkpoint 与之相同
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-未修复-低-FilteredEventLogPage 校验允许非空 rows 时 covered_event_id 为 None

- **入口/函数**: `FilteredEventLogPage.__post_init__(dayu/host/durable/event_log.py:234-236)`
- **文件(行号)**: `dayu/host/durable/event_log.py:244-249`
- **输入场景**: 构造 `FilteredEventLogPage(rows=(row,), covered_event_sequence=1, covered_event_id=None)`
- **实际分支**: `__post_init__` 只检查 `covered_event_sequence >= last_row.event_sequence`，不检查 `covered_event_id` 是否非空
- **预期行为**: 当 `rows` 非空时，`covered_event_id` 应强制非空（因为 covered cursor 必须对应真实 EventLog row）
- **实际行为**: 校验通过；但 `read_events_after_matching` 生产者始终从 `matching_rows[-1]` 或 `boundary_row` 取 `event_id`，两者均非 None，因此运行时不会触发此边界
- **直接证据**: `FilteredEventLogPage.__post_init__` line 244-249 只检查 sequence 比较；`read_events_after_matching` line 719-727 的 `covered_row.event_id` 始终来自真实 row
- **影响**: 防御性校验缺口；生产者正确，但未来新增生产者可能构造不一致的 page
- **建议改法和验证点**: 在 `__post_init__` 中增加：当 `rows` 非空时，`covered_event_id` 必须非空；或当 `covered_event_sequence > _MIN_EVENT_CURSOR` 时，`covered_event_id` 必须非空
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 003-未修复-低-max_event_sequence < cursor 时返回 cursor 而非报错

- **入口/函数**: `read_events_after_matching(dayu/host/durable/event_log.py:671-676)`
- **文件(行号)**: `dayu/host/durable/event_log.py:983-987`
- **输入场景**: `cursor=10`, `max_event_sequence=5`
- **实际分支**: `_read_latest_covered_event_row` 查询 `event_sequence > 10 AND event_sequence <= 5`，返回 `None`；函数返回 `covered_event_sequence=10, covered_event_id=None`
- **预期行为**: 设计真源未要求此场景报错；当前行为（空窗口、cursor 不变）语义正确
- **实际行为**: 返回空 page，cursor 不变；调用方判定 idle
- **直接证据**: `_validate_filtered_read_inputs` line 983-987 只检查 `max_event_sequence < 0`，不检查 `max_event_sequence < cursor`
- **影响**: 语义正确但可能让调用方困惑（传入了矛盾参数却无提示）
- **建议改法和验证点**: 可选：在 `_validate_filtered_read_inputs` 中增加 `max_event_sequence < cursor` 的 warning 或 error；或保持现状并在 docstring 中说明此行为
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 004-未修复-低-store 层缺少 session_id 参数的直接测试

- **入口/函数**: `read_events_after_matching(dayu/host/durable/event_log.py:633)`
- **文件(行号)**: `tests/host/test_event_log_store.py`
- **输入场景**: 多 session 事件，使用 `session_id` 参数过滤
- **实际分支**: 现有 store 测试未传入 `session_id` 参数
- **预期行为**: store 层应有测试证明 `session_id` 过滤正确工作
- **实际行为**: session 过滤仅在 read model 集成测试中间接覆盖
- **直接证据**: `test_event_log_store.py` 中 3 个新测试均未传入 `session_id`
- **影响**: store 层 helper 的 session 过滤路径缺少单元级证明
- **建议改法和验证点**: 新增测试：追加 session "s1" 和 "s2" 的事件，用 `session_id="s1"` 读取，断言只返回 s1 的事件且 covered cursor 只覆盖 s1 范围
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

- **limit 双重语义（page size + step cap）未分别测试**: 现有测试证明 `limit` 作为 page size 工作（`limit=1` 时每步最多返回 1 条匹配 row），但未证明 `limit` 作为 step cap 的截断行为。风险低：`range(limit)` 是标准 Python 语义，不易被意外修改。
- **`events_scanned` 语义变更**: 从"扫描的 EventLog row 数"改为"read/apply step 数"。docstring 和测试已更新，但下游消费方若依赖旧行为可能受影响。本 slice 未修改 public API，风险可控。
- **covered cursor 跳过不匹配区域时的 re-scan**: 当 `len(matching_rows) >= limit` 时，covered cursor 设为最后一条匹配 row 的 sequence，而非 boundary row。下次调用会重新扫描最后匹配 row 与 boundary 之间的不匹配事件。这是正确性保证的 trade-off，非性能问题。
