# P9.5 S8 Engine Wait Confirmation Matching-Ref Implementation

日期：2026-05-17

## 动机判断

S8 动机成立。Engine 公共 `TOOL_AWAITING` / `RUN_SUSPENDED` 事件不携带 Host wait id 或 accepted refs，不能作为 Host wait truth。若 Host 仅凭 Engine payload 或 Run / Attempt 状态确认等待事件，会允许 Engine event 绕过 ToolRuntime awaiting accept path，间接伪造等待确认。正确边界是：Engine event 只能确认 Host durable 中已经由 ToolRuntime accept path 接受的 wait record 与 canonical refs。

## 改动文件

- `dayu/host/engine_ingest.py`
  - 在 `EngineEventIngestor` 的 waiting confirmation 分支中加入 private durable matching 校验。
  - 校验当前 Run / Attempt 必须是 `WAITING` / `SUSPENDED`。
  - 读取当前 Run 下 active wait record，并要求与 envelope 的 `run_id`、`attempt_id`、`execution_id` 唯一匹配。
  - 回读最新 `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED` canonical facts，校验 event row identity、wait record created / updated refs、payload wait id、event ref 链、tool identity、await spec 与 snapshot。
  - 对 Engine `ToolAwaitingData` / `RunSuspendedData` 的 awaiting record 做 tool call、tool name、await spec、deadline、snapshot 匹配；不匹配只写未确认 diagnostic / rejection，不做状态推进。
- `tests/host/test_engine_ingest_mapping.py`
  - 增加真实 ToolRuntime awaiting accept path 后的 `TOOL_AWAITING` 与 `RUN_SUSPENDED` accepted refs replay confirmation 测试。
  - 增加 mismatched Engine awaiting record、wrong Attempt identity、wrong execution identity、old Attempt late confirmation after resolve 的 fail-closed 测试。
- `dayu/host/README.md`
  - 同步 Engine waiting confirmation 当前契约：必须匹配 Host accepted wait record 与 canonical refs 才记为确认。
- `tests/README.md`
  - 同步 Host 测试覆盖说明中的 Engine awaiting confirmation accepted refs matching。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_wait_awaiting_accept.py tests/host/test_phase7_waiting_integration.py tests/host/test_wait_cancel_late_result.py`：38 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`：0 errors, 0 warnings, 0 informations。
- `git diff --check`：通过，无输出。

## 文档决策

本次触及 `dayu/host` 与 `tests/host`，按 AGENTS.md 触发检查并更新 `dayu/host/README.md` 与 `tests/README.md` 中与当前行为直接相关的说明。未修改根 README 或其它包 README，因为没有用户入口、配置入口或跨层架构边界变化。

## 残余风险

- Engine contract 仍不携带 Host wait refs；本实现按 S8 裁决在 Host 事务内回读 durable accepted refs 做确认，不改变 Engine 公共契约。
- 当前仅支持现有单 active wait record 不变量；若未来允许同一 Run 多 active wait，需要重新设计 confirmation 匹配输入。
- RemoteProxy、callback endpoint、recovery、exactly-once remote semantics 仍未实现，保持在后续 phase 范围。

## 停止状态

implementation 完成；未 commit、未 push、未创建 PR。
