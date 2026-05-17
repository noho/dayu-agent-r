# P9.5 S6 Read API Enum Mapping And Minimal Read Model Reset Contract Implementation

## 范围

- Gate：P9.5 S6 Read API Enum Mapping And Minimal Read Model Reset Contract implementation。
- 分支：`p9.5-pre-p10-hardening`。
- 计划来源：`docs/host/p9-5-pre-p10-hardening-plan.md` 的 S6。

## 动机判断

S6 动机成立。直接证据是部分 public read view 从 durable row dataclass 构造 snapshot / event view 时依赖已有类型注解或 DB CHECK，而直接构造 durable row 可绕过 SQLite enum 约束。read facade 是 public 边界，未知 durable enum 必须 fail closed，并让 `HostCommandHandle._run_read` 统一转换为 `HostApiError`，不能把未知字符串泄漏到 public snapshot / event view。

## 变更文件

- `dayu/host/read_api.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/read_model.py`
- `tests/host/test_public_event_stream.py`
- `tests/host/test_projection_read_model.py`
- `tests/host/test_public_run_api.py`
- `tests/host/test_public_session_api.py`
- `dayu/host/README.md`
- `docs/reviews/p9-5-s6-read-api-enum-reset-implementation-20260517.md`

## 实现内容

- 在 public event stream 映射处新增 private durable `EventClass` -> public `HostEventClass` helper；未知或非当前 durable enum 值抛 `HostDurableError`。
- 在 durable state snapshot mapping 中新增 private Session / Run status helper；`session_snapshot_from_rows` 与 `run_snapshot_from_row` 在构造 public snapshot 前显式校验当前 public enum。
- 保留 Attempt status 现有 row codec deserializer，并补当前枚举 exhaustiveness 与未知值 fail-closed 测试。
- 在 minimal read model durable codec 中增加 Python validation parity：`RunResultRow.terminal_status` 必须是当前 Run 终态，`SessionTimelineItemRow.item_kind` 必须是当前 minimal timeline kind。
- 在 `reset_minimal_read_model_projection` docstring 与测试中明确 `host_run_results` / `host_session_timeline_items` 由固定 `host.minimal-read-model` single consumer 独占；reset 后 EventLog replay 是合法 repair，不引入 `consumer_id` schema 或 multi-consumer isolation。
- 更新 Host README 的 Phase 8 minimal read model 说明，写入当前 single-consumer 独占与 reset/replay repair contract。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_public_event_stream.py tests/host/test_projection_read_model.py tests/host/test_public_run_api.py tests/host/test_public_session_api.py`
  - 结果：52 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：通过，无输出。

## 文档决策

- 已更新 `dayu/host/README.md`，只同步当前 Phase 8 minimal read model single-consumer ownership 与 reset/replay repair contract。
- 已检查 `tests/README.md`。现有测试手册已经描述 minimal RunResult / Session timeline read model projection 与 repair reset / replay 覆盖类别，本次不需要修改。

## 残余风险

- 本次没有新增 public facade、public error code、状态名、schema column、consumer isolation 或 multi-consumer 读模型。
- 未让 read model 成为 truth；`get_run` / `get_session` 仍读 durable Run / Session truth，`stream_run_events` 仍读 EventLog。
- Unknown enum 的 public facade 转换当前落在既有 durable error -> `INTERNAL_ERROR` 分类，未引入新的 public error code。

## 停止状态

S6 implementation 完成。未 commit、未 push、未创建 PR，未进入 review gate。
