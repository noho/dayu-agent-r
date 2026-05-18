# P10.5 Slice 4 Code Review Controller Adjudication

## Gate

P10.5 Slice 4 code review。

## Inputs

- MiMo review：`docs/reviews/phase10-5-slice4-code-review-mimo-20260518.md`
- DS review：`docs/reviews/phase10-5-slice4-code-review-ds-20260518.md`
- Implementation artifact：`docs/reviews/phase10-5-slice4-implementation-codex-20260518.md`
- Accepted plan：`docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`

## Verdict

接受 P10.5 Slice 4。进入 Slice 4 accepted slice commit。

MiMo review：PASS，blocking count = 0。

DS review：PASS，blocking count = 0。

## Controller Decisions

### D1. Polling EventLog projection is accepted for P10.5 Slice 4

Plan 使用 "committed EventLog / ingest path" 表达 HostEvent 来源。当前实现从 committed EventLog rows 轮询投影为 `HostEvent`，对外 contract 仍是 `watch_session_events(session_id) -> AsyncIterator[HostEvent]`，且不引入 Outbox、public payload reader 或第二套 stream contract。

Controller 接受该实现为 P10.5 本地 live watch 的可行第一版。Push-based fanout / notification 可作为 Phase 13 Outbox 或后续性能优化，不阻塞当前 slice。

### D2. Public namespace contraction accepted

`HostEventView`、`HostEventStream`、`stream_run_events` 已从 `dayu.host` 包根移除；内部 diagnostic 路径仍可从 `dayu.host.api` / `dayu.host.read_api` 显式导入。该边界符合 Slice 4 plan。

DS 提到 `HostLocalExecutionOptions` 仍可从包根模块属性访问但不在 `__all__`；这是 Slice 1 后的既有非阻塞遗留，不属于 Slice 4 引入，不阻塞当前 acceptance。

## Validation Evidence

Controller 本地验证：

```text
source .venv/bin/activate && pytest tests/host/test_watch_session_events.py tests/host/test_public_host_event.py -q
-> 7 passed

source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_public_event_stream.py tests/host/test_public_contracts.py -q
-> 62 passed

source .venv/bin/activate && python -m pyright dayu/host tests/host
-> 0 errors, 0 warnings, 0 informations
```

## Residual Risk

- `watch_session_events` 当前是 live-only polling EventLog projection；attach 前 terminal 补读仍归 Phase 13 Outbox owner。
- Push-based fanout / notification 不是当前 slice blocker，可在后续 performance / Outbox owner 中替换内部实现。
- Host close 已打开 watcher 自然结束，不写 cancel / failed facts；这符合 close 不伪装用户治理意图的设计。
