# WU-SEMANTIC-OWNERSHIP-01 P1-B Plan Delivery

## 完成状态

AgentCodex 已完成 P1-B plan gate。本轮未修改生产代码、未修改 tests、未提交、未 push。

产出：

- Plan artifact：`docs/host/wu-semantic-ownership-01-p1-b-plan.md`
- 交付说明 artifact：`docs/reviews/wu-semantic-ownership-01-p1-b-plan-codex.md`

## 扫描命令

任务要求扫描：

```bash
rg -n "RUN_SUCCEEDED|RUN_FAILED|RUN_CANCELLED|RUN_LOST|TERMINAL_EVENT|TERMINAL_STATUS|terminal event|terminal status|outbox terminal|RUN_CANCELLING|cancel_request_event_id|_cancel_request_event_id_from_cancelling" docs/host/design.md dayu/host tests/host
rg -n "request_active_attempt_cancel_in_transaction|mark_run_cancelling|RUN_CANCELLING|cancel_request_event_id|watchdog|active cancel" dayu/host tests/host
```

补充扫描：

```bash
rg -n "P1-B|terminal|cancel" docs/host/wu-semantic-ownership-01-umbrella-plan.md docs/host/issues-implementation-control.md docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md
rg -n "RUN_LOST|outbox|terminal|cancel_request_event_id|RUN_CANCELLING" docs/host/design.md
rg -n "_TERMINAL_STATUS_BY_EVENT_TYPE|_TERMINAL_EVENT_TYPES|RUN_LOST|RUN_SUCCEEDED|RUN_FAILED|RUN_CANCELLED" dayu/host --glob '*.py'
```

## 直接证据摘要

- `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md` 已接受 P1 findings：terminal event type strings 重复、Outbox terminal set 与 `RUN_LOST` 不一致、`cancel_request_event_id` 只在 `RUN_CANCELLING` payload JSON。
- `docs/host/design.md` 已确认 `RUN_LOST` 是 Host terminal/lifecycle fact，但没有自足地区分 Host terminal set、public outbox terminal item set 和 non-public terminal skip/diagnostic 行为。
- `dayu/host/outbox.py` 的 `_TERMINAL_EVENT_TYPES` 包含 `RUN_LOST`，而 `_TERMINAL_STATUS_BY_EVENT_TYPE` 不含 lost，靠 `apply_event()` 单独 skip。
- `dayu/host/durable/outbox.py` latest terminal sequence 查询仍使用包含 `RUN_LOST` 的 `_TERMINAL_EVENT_TYPES`。
- `dayu/host/read_model.py`、`dayu/host/tool_trace.py`、`dayu/host/read_api.py`、`dayu/host/engine_ingest.py`、`dayu/host/durable/run_transition.py` 等生产模块仍重复 terminal event strings / mappings。
- `dayu/host/durable/schema.py` 与 `dayu/host/durable/state.py` 当前 `host_runs` / `RunRow` 没有 typed cancel request link。
- `dayu/host/durable/run_transition.py`、`dayu/host/engine_ingest.py`、`dayu/host/dispatch.py` 当前仍从 latest `RUN_CANCELLING` payload 解析或读取 `cancel_request_event_id` 作为 active cancel critical linkage。

## 计划结论

问题仍成立。P1-B implementation 前必须先更新 `docs/host/design.md`，明确：

- Host terminal/lifecycle event set 包含 `RUN_LOST`。
- Public outbox terminal item event set 排除 `RUN_LOST`。
- `RUN_LOST` 在 Outbox 中只能产生 explicit skip / diagnostic，不要求 public item，也不得影响 public item watermark 语义。

计划选择：

- 新增 Host-owned `dayu/host/lifecycle_events.py` 作为 terminal/lifecycle event helper。
- 在 `host_runs` 新增 typed `cancel_request_event_id` nullable 列，作为 accepted cancel request durable link；不新增 relation 表，除非后续发现同一 Run 需要多条 accepted cancel history。
- 迁移 watchdog / engine ingest / dispatch / recovery 从 Run row typed link 读取，不再解析 `RUN_CANCELLING` payload JSON 作为 critical link。

## 未决风险

- 若 controller 要求兼容既有 workspace DB，则当前“全新 schema 起库”方案需要重新裁决。
- 若 implementation 扫描发现同一 Run 有多条 accepted cancel request 的真实 history 需求，单列方案必须暂停并改为 typed relation design。
- `RUN_SUCCEEDED`-only final answer continuity helper不应被机械迁移为 generic terminal helper；implementation review 需要区分 terminal set 消费者和 success-only 业务消费者。

## 验证

本轮按任务限制只运行：

```bash
git diff --check
```

结果：通过，无 whitespace error。
