# WU-CLI-SESSION-01 S1 Implementation Report

## Completion Status

完成 S1 - Host public list sessions API。未进入 code review/fix/re-review/commit/push/PR，未修改 control doc。

## Changed Files

- `dayu/host/api.py`
- `dayu/host/read_api.py`
- `dayu/host/open_host.py`
- `dayu/host/durable/state.py`
- `dayu/host/__init__.py`
- `tests/host/test_public_session_api.py`
- `tests/host/test_package_exports.py`
- `docs/reviews/wu-cli-session-01-s1-implementation-codex.md`

工作区中 `docs/host/issues-implementation-control.md` 已有 controller bookkeeping 脏改动，本 slice 未读取、未改写、未 stage。

## Exact API Added

- `dayu.host.api.SessionListItem`
  - fields: `session_id`, `status`, `slot`, `active_run_id`, `queued_run_ids`, `timeline_cursor`, `created_at`, `closed_at`
  - `created_at` / `closed_at` 只存在于 list item，未扩展 `SessionSnapshot`。
- `dayu.host.api.ListSessionsResult`
  - fields: `sessions`
- `Host.list_sessions(self) -> ListSessionsResult`
- `dayu.host.read_api.list_sessions(host) -> ListSessionsResult`
- `open_host(...)._PublicHostHandle.list_sessions() -> ListSessionsResult`
- `dayu.host.list_sessions` 包根导出

Durable helper:

- `dayu.host.durable.state.SessionWithSlotRows`
- `dayu.host.durable.state.read_all_sessions_with_slots(transaction)`

该 helper 从 `host_sessions` left join 当前 `host_session_slots`，只返回未 purge sessions，排序为 `created_at DESC, session_id ASC`。

## Implementation Notes

- `read_api.list_sessions` 是 read transaction snapshot，不写 EventLog，不依赖 projection，不触发 dispatch。
- list item 的 active/queued/cursor/slot 转换复用 `session_snapshot_from_rows(...)`，保持和 `get_session` 同源。
- `created_at` / `closed_at` 使用 `dayu.host.durable.codec.parse_utc_timestamp(...)` 转换。
- malformed durable timestamp 会包装为 `HostDurableError("session row timestamp is invalid: ...")`；经当前 public read facade 暴露为 `HostApiError(INTERNAL_ERROR)`，cause 保留 `HostDurableError`。

## Tests Run

- `source .venv/bin/activate && pytest tests/host/test_public_session_api.py tests/host/test_package_exports.py -q`
  - result: `26 passed in 0.34s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - result: `0 errors, 0 warnings, 0 informations`
  - note: pyright only reported an available version update.
- `git diff --check`
  - result: passed

## Docs Decision

- CLI/README/设计文档不在本 slice。
- 按触发规则读取了 `tests/README.md`。本次是在既有 Host public session API 测试文件中扩展覆盖，没有新增测试层级；同时 allowed write files 不包含 README，因此未更新 README。

## Residual Risks

- `list_sessions` 第一版无分页；这符合 accepted plan，但大量 sessions 时 CLI 后续可能需要分页或过滤作为独立 work。
- 当一个 Session 理论上存在多个当前 slot row 时，list 选择与 `read_session_slot_by_session_id(...)` 相同的最新 slot；这保持现有语义，但不会在 S1 扩展 slot ownership 模型。
