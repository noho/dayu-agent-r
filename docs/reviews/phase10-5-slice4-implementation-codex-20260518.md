# P10.5 Slice 4 Implementation - AgentCodex

## Scope

- 当前 gate：P10.5 Slice 4 implementation。
- 分支：`feat/host-p10-5-public-contract-freeze`。
- 本次实现 Slice 4: Session-level Live Host Events And Terminal Final Answer View。
- 未实现 Outbox offline catch-up、`wait_final_answer`、Slice 5 control commands、Engine / Service / UI / Fins 修改或 durable schema 变更。

## Motivation Check

动机成立。P10.5 要冻结普通本地多轮 Service-facing Host contract；如果 Service 仍需要依赖 run-level `HostEventView`、raw EngineEvent 或内部 payload reader 才能展示 final answer，Host public boundary 仍未冻结。本 slice 应把普通事件入口收敛到 `open_host(...).watch_session_events(session_id)` 返回的 Host-owned typed `HostEvent`。

## Changes

1. `dayu/host/api.py`
   - 将 `Host.watch_session_events(session_id)` 协议收敛为直接返回 `AsyncIterator[HostEvent]`，对齐 plan / design 中 `events = host.watch_session_events(...)` 的普通 async iterator 形态。

2. `dayu/host/open_host.py`
   - 实现 public handle `watch_session_events(session_id)`。
   - 打开 watch 时 fail-fast 校验 Host handle lifecycle 与 Session 存在性。
   - watch 只观察 attach cursor 之后的新 EventLog rows，不接收 public cursor，不做离线补读。
   - terminal event 只是 iterator 中的一条事件，不自动结束 iterator。
   - consumer 取消 / `aclose()` 只结束本次订阅，不写 EventLog、不 cancel Run。
   - Host handle close 后新 watch 抛 `HostClosedError`；已打开 watcher 在 close 后自然结束轮询。

3. `dayu/host/read_api.py`
   - 新增内部 session live watch 投影读取 helper，读取 committed EventLog rows 并投影为 public `HostEvent`。
   - `RUN_SUCCEEDED` 映射为 `HostEventKind.SUCCEEDED`，并从 terminal summary payload descriptor 内联 `HostFinalAnswerView(content, filtered, degraded, finish_reason, terminal_status)`。
   - `RUN_FAILED` / `RUN_CANCELLED` 映射 typed terminal status，并只暴露 display-safe `error_message` / `cancel_reason` 字段。
   - 非 terminal rows 映射为 `HostEventKind.PROGRESS`，作为 live wiring proof。
   - payload / EventLog 读取仅作为内部 projection source；未新增 public payload reader、`read_payload` 或 `get_run_result`。

4. `dayu/host/__init__.py`
   - 从包根移除 `HostEventView`、`HostEventStream`、`stream_run_events` 的普通 public namespace 暴露。
   - 低层 run-level diagnostic path 保留在 `dayu.host.read_api` / `dayu.host.api` 内部测试路径。

5. Tests
   - 新增 `tests/host/test_watch_session_events.py`，覆盖：
     - 两个 watcher 观察同一个 terminal HostEvent，且 `event_id` / `event_sequence` / `dedupe_key` 可去重。
     - terminal event 不结束 iterator，后续 follow-up terminal 仍可继续读取。
     - consumer early cancel 不取消 Run、不写 EventLog。
     - `SUCCEEDED` final answer 只从 watch terminal `HostEvent.final_answer` 取得。
     - `FAILED` / `CANCELLED` terminal typed status 与 display-safe 字段。
     - handle close、Session missing、Session CLOSED watch 语义。
   - 新增 `tests/host/test_public_host_event.py`，覆盖 root namespace 不导出 `HostEventView` / `HostEventStream` / `stream_run_events`，以及 terminal `HostEvent` payload contract。
   - 迁移既有内部 diagnostic 测试 import：`tests/host/test_command_handle.py`、`tests/host/test_public_event_stream.py`、`tests/host/test_public_contracts.py` 改为从内部模块路径导入 `HostEventView` / `HostEventStream` / `stream_run_events`。
   - 更新 `tests/host/test_package_exports.py`，明确禁止这些 diagnostic symbols 出现在 `dayu.host` 包根。
   - 修正 `tests/host/test_public_event_stream.py` 中一个固定 26 个无关 Run 的旧假设，改为按 `HOST_EVENT_STREAM_DEFAULT_LIMIT` 自适应生成足够扫描窗口外事件。

## README Sync

- 已更新 `dayu/host/README.md`：
  - 记录 `watch_session_events(session_id)` 已是普通 Service-facing session-level live event entry。
  - 记录 terminal `SUCCEEDED` 内联 `HostFinalAnswerView`，`FAILED` / `CANCELLED` 暴露 typed terminal status 与 display-safe 字段。
  - 记录 run-level `stream_run_events` / `HostEventView` 为内部 diagnostic / 低层测试路径，不从包根作为普通 public contract 使用。
- 已更新 `tests/README.md`：
  - 增加 Slice 4 focused test 命令。
  - 在 Host public run / wait / event API 覆盖说明中加入 session live watch 与 root export 收敛测试事实。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_watch_session_events.py tests/host/test_public_host_event.py -q`
  - 结果：`7 passed in 0.37s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：`0 errors, 0 warnings, 0 informations`
- 额外补跑导出和内部 diagnostic 受影响测试：
  - `source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_public_event_stream.py tests/host/test_public_contracts.py -q`
  - 结果：`62 passed in 0.30s`

## Residual Risk

- `watch_session_events` 当前是 live watch + polling EventLog projection，不实现 Outbox concrete offline catch-up；离线 terminal 补读仍按 plan 留给 Phase 13 / later owner。
- watch attach cursor 当前从最新 EventLog sequence 开始，因此 attach 前已经提交的 terminal 不会被补读；这符合 P10.5 live watch non-goal，Service reconnect 仍需未来 Outbox path 去重补投。
- Host close 对已打开 watcher 的处理是停止轮询并自然结束；没有写 cancel / failed terminal facts，也不表达用户停止 Run 的治理意图。
- 本 slice 未修改 durable schema、Engine、Service、UI 或 Fins。
