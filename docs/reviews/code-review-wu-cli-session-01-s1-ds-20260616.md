# Code Review

## Scope

- Mode: current changes
- Branch: wu-cli-session-01
- Base: 653c9966 (accepted plan commit)
- Output file: docs/reviews/code-review-wu-cli-session-01-s1-ds-20260616.md
- Included scope:
  - `dayu/host/api.py` — `SessionListItem`、`ListSessionsResult` dataclass 与 `Host` Protocol `list_sessions`
  - `dayu/host/read_api.py` — `list_sessions` facade、`_ListSessionsOperation`、timestamp 解析 helper
  - `dayu/host/open_host.py` — `_PublicHostHandle.list_sessions` async 转发
  - `dayu/host/durable/state.py` — `SessionWithSlotRows`、`read_all_sessions_with_slots`、LEFT JOIN row decoder
  - `dayu/host/__init__.py` — 包根导入与 `__all__` 导出
  - `tests/host/test_public_session_api.py` — 3 个新测试 + 测试夹具
  - `tests/host/test_package_exports.py` — expected exports 同步
- Excluded scope:
  - `docs/host/issues-implementation-control.md`（controller bookkeeping，非 S1 code）
  - 其他未改动文件
- Parallel review coverage: 无（单 reviewer 全量走读）

## Findings

### 1-未修复-低-list_sessions 缺少空库边界测试

- **入口/函数**: `list_sessions()` / `_ListSessionsOperation.__call__`
- **文件(行号)**: `tests/host/test_public_session_api.py`（测试缺失位置）
- **输入场景**: 数据库中没有任何 Session（全新 Host instance 立即调用 `list_sessions`）
- **实际分支**: `read_all_sessions_with_slots` 执行 `SELECT ... LEFT JOIN ... ORDER BY ...` 返回空结果集，`tuple(...)` 产生空元组，`ListSessionsResult(sessions=())` 构造成功
- **预期行为**: 返回 `ListSessionsResult(sessions=())`，不抛异常
- **实际行为**: 当前代码路径会返回空结果，但未被测试覆盖
- **直接证据**: `tests/host/test_public_session_api.py` 中 `test_list_sessions_returns_durable_rows_with_stable_sort_and_no_purged` 先创建了 labeled/anonymous/closed/purged 四个 Session；`test_open_host_list_sessions_and_closed_handle` 也先创建了一个 Session。两个正向测试均假设至少有一个 Session 存在。
- **影响**: 静默未覆盖边界；若将来 `ListSessionsResult.__post_init__` 或 list comprehension 逻辑变更，空结果行为可能退化，但当前无回归保护
- **建议改法和验证点**: 增加 `test_list_sessions_empty_database_returns_empty_result`，在 `_open_handle(tmp_path)` 后直接调用 `list_sessions(command_handle)`，断言 `result.sessions == ()`
- **修复风险（低）**: 纯测试新增，不改变生产代码
- **严重程度（低）**: 当前实现行为正确，只是缺少回归保护

### 2-未修复-低-_slot_row_from_session_list_host_row 使用裸 row.get() 与已有 decode 模式不一致

- **入口/函数**: `_slot_row_from_session_list_host_row()`
- **文件(行号)**: `dayu/host/durable/state.py:969-1023`
- **输入场景**: SQL 查询因编程错误缺少某 LEFT JOIN 列（如 `slot.scope AS slot_scope` 被误删）
- **实际分支**: `row.get("slot_scope")` 返回 `None`（dict `.get()` 缺省返回 None 而非抛 KeyError），`_optional_text(None, ...)` 返回 `None`，`all(value is None for value in slot_values)` 为 `True`，函数返回 `None`
- **预期行为**: 应像同模块 `session_row_from_host_row` / `_decode_scalar` 那样，缺列时以 `HostRowDecodeError` 明确报错，而非静默将 labeled Session 展示为 anonymous
- **实际行为**: SQL 列缺失时所有 Session 的 slot 被静默解析为 `None`，list 结果中所有 Session 显示为 anonymous，不报任何错误
- **直接证据**: `row.get("slot_scope")`（第 977 行）与 `_decode_scalar` 模式对比——后者在 `row.get(column)` 外包裹 `try/except KeyError` 并抛 `HostRowDecodeError`（`dayu/host/durable/state.py:737-754`）
- **影响**: 仅当 SQL 查询列名与 Python 解码列名不同步时触发（编程错误），影响面窄；但静默数据错误不符合 fail-closed 原则
- **建议改法和验证点**: 在 `_slot_row_from_session_list_host_row` 中复用 `_decode_scalar` 或将 `row.get()` 调用封装为缺列即抛错的 helper；或至少在 docstring 中注明"调用方必须保证 SQL 列名与解码字段一一对应"
- **修复风险（低）**: 改变 row 访问方式不影响正常路径行为
- **严重程度（低）**: 仅编程错误场景触发，且 SQL 与本函数在同一文件中紧密相邻，实际误同步概率低

## Open Questions

无。

## Residual Risk

- **N+1 query 模式**: `_session_list_item_from_rows` 每项调用 `session_snapshot_from_rows`，后者为每个 Session 执行 `read_active_run_for_session` + `read_non_terminal_runs_for_session` 两次额外查询。对于 N 个 Session，总计 1 + 2N 次查询。此风险已在 accepted plan §12 中明确记录为已知接受项，不构成新 finding。
- **无分页**: 第一版 `list_sessions` 无分页参数，已在 plan §12 中记录为有意最小设计，大量 Session 时的性能由后续 work unit 负责。
- **`SessionWithSlotRows` 无下划线前缀**: 该类型仅在 `durable/state.py` 与 `read_api.py` 之间使用，未进入 `dayu/host.__init__` 或 `read_api.__all__` 的公开导出。命名前缀与同模块 `SessionRow` / `SessionSlotRow` 等内部 durable row 类型保持一致，不属于公开 API 泄漏。
