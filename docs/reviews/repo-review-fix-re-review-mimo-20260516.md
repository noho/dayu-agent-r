# Code Review Fix Re-Review - AgentMiMo - 2026-05-16 21:27

## Scope

- Mode: current changes (fix diff only)
- Branch: feat/host-phase8-projection-core-event-stream
- Base: main
- Output file: docs/reviews/repo-review-fix-re-review-mimo-20260516.md
- Input adjudication: docs/reviews/repo-review-controller-adjudication-20260516-2109.md
- Input fix artifact: docs/reviews/repo-review-fix-codex-20260516.md
- Input review artifacts: docs/reviews/repo-review-20260516-2105.md, docs/reviews/repo-review-20260516-2059.md
- Included scope: Codex fix diff for DR-ALL-A1 through DR-ALL-A5
- Excluded scope: 全仓 re-review；Engine / Fins / Service / UI / schema DDL

## Findings

未发现实质性问题。

逐项验证：

### DR-ALL-A1: RuntimeFileLock active token -- PASS

`acquire()` 在获取第三方锁前检查 `self._active_token is not None and not self._active_token.released`，
满足 adjudication "fail fast" 要求。token release 后 `.released` 为 `True`，guard 不阻塞再次 acquire。
`__enter__` 委托 `acquire()` 消除了此前 `__enter__` 与 `acquire()` 分别设置 `_active_token` 的双写问题。
4 个新测试覆盖嵌套 `with`、context 内 manual acquire、manual acquire 后 context enter、manual release 后
reacquire，与 adjudication 要求的测试矩阵一一对应。

### DR-ALL-A2: HostEventView event_class public contract -- PASS

新增 `HostEventClass`（StrEnum，4 成员：`CANONICAL_FACT` / `PREVIEW` / `DIAGNOSTIC` / `PROJECTION_SIGNAL`），
与 durable `EventClass` 成员和值一一对应。`HostEventView` 新增 `event_class: HostEventClass` 字段，
`__post_init__` 增加 `isinstance` 守卫。`_event_view_from_row` 使用 `HostEventClass(row.event_class.value)`
映射，值域安全。`__all__` 在 `api.py` 和 `__init__.py` 均已导出。`dayu/host/README.md` 已同步字段说明。
测试通过创建 PREVIEW EventLog row 验证 caller 可区分 `PREVIEW` 与 `CANONICAL_FACT`，覆盖 adjudication
要求的 "至少非 canonical event row 的 stream regression"。

### DR-ALL-A3: terminal_closeout status pair -- PASS

`_TERMINAL_STATUS_PAIRS` 定义 4 组合法配对 `(SUCCEEDED/SUCCEEDED, FAILED/FAILED, CANCELLED/CANCELLED,
LOST/LOST)`。`_validate_terminal_input` 在单独校验 `_attempt_terminal_event_type` /
`_run_terminal_event_type` 之后追加 `_terminal_status_pair_is_compatible` 检查，非法交叉配对抛
`HostDurableError`。`cancelled/cancelled` 路径通过 `_terminal_attempt_row_for_closeout` /
`_terminal_run_row_for_closeout` 委托 `cancel_running_attempt_row` / `cancel_running_run_row` CAS
helper，复用既有取消语义，未复制 SQL。`_attempt_terminal_event_type` 和 `_run_terminal_event_type`
均已补充 `CANCELLED` 分支。测试覆盖 4 类合法配对与 2 类非法输入（`SUCCEEDED/FAILED` 配对不合法、
`SUSPENDED/SUCCEEDED` Attempt status 不受支持），与 adjudication 要求一致。

### DR-ALL-A4: after_commit callback 全量尝试 -- PASS

`_run_after_commit` 使用 `first_error` / `first_error_index` 收集第一个异常但继续循环，
循环结束后若有失败则抛出 `HostAfterCommitError(callback_index=first_error_index)`。
语义满足 adjudication "保留第一个失败 callback_index 并在循环后抛"。测试验证 `callback_events ==
["first", "second"]` 且 `callback_index == 0`，证明后续 callback 被调用且 index 指向第一个失败。

### DR-ALL-A5: WaitPoller adapter Exception 隔离 -- PASS

`poll_once()` 中 `abandon_wait` 和 `poll_wait` 两个 try/except 均从 `except RuntimeError` 改为
`except Exception`，满足 adjudication "捕获普通 Exception 但不吞 BaseException"。Protocol docstring
已更新。测试创建 `_AbandonValueErrorThenNotReadyAdapter`，在 `abandon_wait` 抛 `ValueError` 后验证
`observed == 2, adapter_errors == 1, not_ready == 1`，证明异常被隔离且后续 wait record 仍被 poll。

### 裁决边界合规 -- PASS

- 修改文件全部在 adjudication "允许修改" 列表内
- 未触碰 `dayu/engine/`、`dayu/fins/`、`dayu/service/`、`dayu/ui/`
- 未修改 schema version / DDL
- 未执行 git commit / push / PR

### 回归验证 -- PASS

- `pytest tests/runtime/test_filelock.py tests/host/test_public_event_stream.py tests/host/test_package_exports.py tests/host/test_run_attempt_transitions.py tests/host/test_durable_transaction.py tests/host/test_wait_adapter_polling.py -q` => 80 passed
- `pytest tests/host tests/runtime -q` => 529 passed
- `pyright dayu/runtime/filelock.py dayu/host/api.py dayu/host/read_api.py dayu/host/__init__.py dayu/host/durable/run_transition.py dayu/host/durable/transaction.py dayu/host/wait_adapter.py` => 0 errors
- 未引入新类型错误或测试失败

## Open Questions

无。

## Residual Risk

- `_TERMINAL_STATUS_PAIRS` 使用 `tuple[tuple[...], ...]` + `in` 线性查找，当前 4 组配对无性能问题；
  若未来终态类型扩展，可考虑 `frozenset`，但不属于当前修复范围。
- `after_commit` fix 仅保留第一个失败异常；若多个 callback 失败，后续失败被静默丢弃。这是 adjudication
  明确接受的设计选择（"保留第一个失败"），不是遗漏。
- CANCELLED closeout 路径要求 Attempt 当前为 RUNNING（沿用 `cancel_running_attempt_row` CAS 语义），
  Attempt STARTING 的取消由已有 pre-dispatch / active cancel primitive 负责，与 adjudication 裁决一致。

## Conclusion

**PASS**

Codex 对 DR-ALL-A1 至 DR-ALL-A5 的修复完整、符合裁决边界、未引入回归。所有 5 项 fix 的实现、测试覆盖与
README 同步均满足 adjudication 要求。
