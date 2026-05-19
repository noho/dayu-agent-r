# Repo Review Accepted Findings 修复记录

## 任务范围

- 输入 artifact：`docs/reviews/repo-review-20260519-154715.md`。
- 主控接受并要求修复：Finding 02、03、04、08、09、10、11、12、14、15、16、17。
- 主控明确暂不修复：Finding 01、05、06、07、13。
- 本次不修改 `AGENTS.md`、`CLAUDE.md`，不 stage、commit、push。
- 本记录只覆盖本次 accepted findings 修复；工作区中既有的 Host README 重写相关改动不归入本次修复范围。

## 事实来源

- 当前代码：
  - `dayu/contracts/`
  - `dayu/runtime/`
  - `dayu/engine/`
  - `dayu/host/`
  - 对应测试目录
- Review artifact：`docs/reviews/repo-review-20260519-154715.md`。
- 项目约束：`AGENTS.md`、`CLAUDE.md`。
- 架构与日志约束参考：`dayu/README.md`。

## Accepted Findings 修复

- Finding 02：`HostDispatchScheduler._drain_loop` 捕获非取消异常后继续循环，并保留 warning 诊断，避免后台 dispatch loop 静默退出。
- Finding 03：`_safe_close_worker_handle` 与 `_safe_release_lane_token` 的 best-effort cleanup 失败路径增加 warning 日志，记录错误类型与关键上下文。
- Finding 04：`host_wait_records` snapshot 三元组约束改为三列同时为空或同时非空，并将 `HOST_SCHEMA_VERSION` 从 9 bump 到 10。
- Finding 08：`JsonValue` 文档明确 `float` 运行时必须是有限 JSON number，外部数据边界应拒绝 `NaN` 与正负无穷。
- Finding 09：`ToolResultMeta` 增加 `tool_name` 非空与 `finished_at >= started_at` 校验。
- Finding 10：`ToolParametersSchema` 文档明确本模块不做完整 runtime validator，但调用方必须保证 `required` 字段来自 `properties`。
- Finding 11：`AgentRunRequest` 增加 `messages` 非空入口校验。
- Finding 12：`run_agent_and_wait` fallback terminal shape 路径增加 warning 日志，记录 terminal type 与 data type。
- Finding 14：`await_or_cancel`、`wait_for_or_cancel`、`await_or_cancel_or_timeout` 增加 `poll_interval_seconds > 0` 校验；拒绝 coroutine 时主动关闭，避免未 await 警告。
- Finding 15：`LaneController` 外层取消后的底层 lane 异常改为 `raise cancelled from exc`，保留异常链。
- Finding 16：`HostToolAwaitingAcceptPort` 改为 ABC 抽象端口，`accept_tool_awaiting` 标记为 abstractmethod。
- Finding 17：`_record_terminal_replay` 重命名为 `_record_terminal_cancel_ack`，使名称与 `idempotent_replay=False` 的语义一致。

## 暂不修复项

- Finding 01：主控裁决为暂不修。当前 `command.py` / README 对 `RECOVERING` cancel 语义描述为 deferred unsupported；本次未发现必须覆盖该状态的更高优先级 public contract 证据。
- Finding 05：主控裁决为暂不修。`purge_session` 当前按 documented structured unsupported 处理。
- Finding 06：主控裁决为暂不修。该项涉及状态 mutation result 语义调整。
- Finding 07：主控裁决为暂不修。该项涉及诊断结构扩展。
- Finding 13：主控裁决为暂不修。该项涉及 provider finish_reason 归一语义调整。

## 改动文件

代码文件：

- `dayu/contracts/json_value.py`
- `dayu/contracts/tool_result.py`
- `dayu/contracts/tool_schema.py`
- `dayu/engine/agent.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/host/admission.py`
- `dayu/host/dispatch.py`
- `dayu/host/durable/schema.py`
- `dayu/host/waiting.py`
- `dayu/runtime/cancellation.py`
- `dayu/runtime/lane.py`

测试文件：

- `tests/contracts/test_tool_result_envelope.py`
- `tests/engine/contracts/test_agent_run.py`
- `tests/engine/test_agent_phase2.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_wait_awaiting_accept.py`
- `tests/runtime/test_cancellation.py`
- `tests/runtime/test_lane.py`

记录文件：

- `docs/reviews/repo-review-fix-codex-20260519.md`

## 验证命令与结果

- `source .venv/bin/activate && pytest tests/contracts/test_tool_result_envelope.py tests/contracts/test_tool_schema.py tests/engine/contracts/test_agent_run.py tests/engine/test_agent_phase2.py tests/runtime/test_cancellation.py tests/runtime/test_lane.py tests/host/test_durable_schema.py tests/host/test_dispatch_scheduler.py tests/host/test_wait_awaiting_accept.py -q`
  - 结果：通过，`158 passed in 1.69s`。
- `source .venv/bin/activate && pyright dayu/contracts dayu/runtime dayu/engine dayu/host tests/contracts/test_tool_result_envelope.py tests/engine/contracts/test_agent_run.py tests/engine/test_agent_phase2.py tests/runtime/test_cancellation.py tests/runtime/test_lane.py tests/host/test_durable_schema.py tests/host/test_dispatch_scheduler.py tests/host/test_wait_awaiting_accept.py`
  - 结果：通过，`0 errors, 0 warnings, 0 informations`。
- `source .venv/bin/activate && pytest tests/host/test_wait_awaiting_accept.py -q`
  - 结果：通过，`6 passed in 0.24s`。该命令用于 pyright 修正后的局部回归确认。
- `git diff --check`
  - 结果：通过，无输出。

## 未运行项

- 未运行全仓测试：本次修复范围集中在 accepted findings 的受影响模块，已覆盖 contracts、runtime、engine、host 相关 touched 文件的单元测试与 pyright；全仓测试成本高且包含本次未触及区域。
- 未运行全仓 pyright：已按主控要求覆盖 `dayu/contracts`、`dayu/runtime`、`dayu/engine`、`dayu/host` 与新增/修改测试文件；未对未触及目录做额外扫描。

## 剩余风险

- Finding 01、05、06、07、13 按主控裁决保留为 deferred，相关语义仍需后续独立设计或诊断结构调整。
- `HOST_SCHEMA_VERSION` 已 bump 到 10；本项目按全新 schema 起库处理，本次未实现旧库迁移兼容。
- `_drain_loop` 连续异常场景当前采取 warning 加继续循环，未加入连续失败计数或熔断策略，避免引入超出 accepted finding 的新治理语义。
- cleanup 失败日志只记录 warning，不改变 best-effort cleanup 的控制流；资源泄漏仍需依赖上层监控或后续诊断聚合发现。
