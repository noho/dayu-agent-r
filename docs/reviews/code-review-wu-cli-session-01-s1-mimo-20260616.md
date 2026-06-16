# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-session-01`
- Base: `653c9966` (accepted plan commit)
- Output file: `docs/reviews/code-review-wu-cli-session-01-s1-mimo-20260616.md`
- Included scope: `dayu/host/api.py`, `dayu/host/read_api.py`, `dayu/host/open_host.py`, `dayu/host/durable/state.py`, `dayu/host/__init__.py`, `tests/host/test_public_session_api.py`, `tests/host/test_package_exports.py`, `docs/reviews/wu-cli-session-01-s1-implementation-codex.md`
- Excluded scope: `docs/host/issues-implementation-control.md`（controller bookkeeping）
- Parallel review coverage: 无

## Findings

### 1-未修复-低-N+1 查询：list_sessions 对每个 Session 额外执行 2 条 Run 查询

- **入口/函数**: `_session_list_item_from_rows` → `session_snapshot_from_rows`
- **文件(行号)**: `dayu/host/read_api.py:315`, `dayu/host/durable/state.py:4480-4481`
- **输入场景**: 任何 `list_sessions()` 调用
- **实际分支**: 每个 Session row 通过 `session_snapshot_from_rows` 再调用 `_read_active_run_id`（SELECT on `host_runs`）和 `_read_queued_run_ids`（SELECT on `host_runs`），共 N×2 条额外查询
- **预期行为**: plan 第 6 节明确指出"复用 `session_snapshot_from_rows(...)` 以保持 active / queued / cursor 语义同源"，当前实现确实复用了
- **实际行为**: 行为正确，但对 N 个 Session 会产生 1 + 2N 条 SQL 查询（1 条 list + N×2 条 run 查询）
- **直接证据**: `state.py:4480` 调用 `_read_active_run_id(transaction, session.session_id)`，`state.py:4481` 调用 `_read_queued_run_ids(transaction, session.session_id)`；两个函数各自执行一条 `SELECT ... FROM host_runs WHERE session_id = ?`（`state.py:5719`, `state.py:5751`）
- **影响**: 正确性无影响。性能方面，plan 第 12 节已明确记录"List query amplification"为已知风险，第一版不做 pagination 是有意的最小设计。当前 Session 规模在 Host 生命周期内通常较小，不构成实际瓶颈
- **建议改法和验证点**: 当前不需修改。若未来 Session 规模增长，可考虑在 SQL 层一次读取所有 Run 状态并内存分组，或在 `read_all_sessions_with_slots` 中 left join `host_runs` 子查询。plan 已将此推迟到 future list pagination / performance hardening
- **修复风险（低）**: 低
- **严重程度（低）**: 低

### 2-未修复-低-SessionListItem.__post_init__ 中 7 条 assert 语句在 if-any-None 之后是冗余的

- **入口/函数**: `_slot_row_from_session_list_host_row`
- **文件(行号)**: `dayu/host/durable/state.py:1008-1014`
- **输入场景**: 任何 left join row 中 slot 字段部分为 None
- **实际分支**: `if any(value is None for value in slot_values)` 已经 raise `HostDurableError`，控制流到达 assert 时所有值已确认非 None
- **预期行为**: assert 后的代码使用这些值构造 `SessionSlotRow`，pyright 需要类型窄化
- **实际行为**: 7 条 `assert ... is not None` 存在，功能正确，但它们是类型窄化的辅助手段而非运行时防御
- **直接证据**: `state.py:1004-1014`：先 `if all(...): return None`，再 `if any(...): raise`，然后 7 条 assert，最后构造 `SessionSlotRow`
- **影响**: 无功能影响。这些 assert 只帮助 pyright 类型窄化，不会在运行时触发（因为前面的 `if any` 已覆盖）
- **建议改法和验证点**: 不需修改。现有代码模式在本仓库中是常见做法（用于 pyright narrow）。如果团队希望减少冗余 assert，可以用 `typing.cast` 或 `typing.assert_type` 替代，但当前做法无害且可读
- **修复风险（低）**: 低
- **严重程度（低）**: 低

## Open Questions

- 无

## Residual Risk

- `list_sessions` 第一版无分页。这是 accepted plan 的有意设计（plan §12），对当前 Session 规模可接受。若未来规模增长，需独立 work 实现 pagination。
- 未覆盖 `closed_at` malformed 的独立测试。当前测试只覆盖 `created_at` malformed 场景。`closed_at` 使用同一个 `_parse_session_row_timestamp`，错误路径逻辑一致，但未被显式测试覆盖。
- `_session_list_item_from_rows` 复用 `session_snapshot_from_rows` 保证了 active/queued/cursor 与 `get_session` 同源，但未测试验证 `list_sessions` 返回的 `active_run_id` / `queued_run_ids` 在有活跃 Run 时与 `get_session` 一致。
