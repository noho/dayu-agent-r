# P9.5 S15 Engine / Host Necessary Logs By Level Implementation

## 审计结论

S15 的问题真实存在，但范围应保持克制：日志只服务运行期诊断，不是 Host truth、audit、tool trace、projection checkpoint 或 UI 输出。现有 Engine agent 与 OpenAI runner 已有较完整的 `VERBOSE` / `DEBUG` / `WARN` 覆盖，Host 侧已实现 P1-P9 路径中仍缺少若干主路径骨架日志与 post-commit failure 级别校准。

审计后确认的 Host 缺口：

- `dayu.host.command`：public command accepted / committed 缺少 `VERBOSE` 骨架日志。
- `dayu.host.admission`：start / follow-up / promotion committed 缺少 durable ids 与状态摘要。
- `dayu.host.engine_ingest`：EngineEvent ingest accepted / committed 缺少事件类型、worker event index、terminal closeout 与 promotion 摘要。
- `dayu.host.local_proxy`：WorkerProxy accept / events opened / close 缺少运行路径日志。
- `dayu.host.tool_runtime`：tool fact accept barrier 缺少 accepted / committed / rejected / timed out 有界日志。
- `dayu.host.waiting`：awaiting accept 与 resolve_wait 缺少主路径日志。
- `dayu.host.memory_repair`：memory rebuild / catch-up 缺少 cursor / count / failure 汇总。
- `dayu.host.projection`：post-commit projection catch-up failure 原本使用 exception 级错误日志，按 README 语义应是 recoverable `WARN`，且不应输出异常 message 中潜在 payload。

## 为什么没有改 Engine agent / OpenAI runner

`dayu.engine.agent` 已有 run / iteration / runner call / tool loop / terminal 相关 `VERBOSE` 与细节 `DEBUG`，并已有 warning / critical 路径测试。OpenAI runner、parser、SSE、HTTP client 也已有 provider attempt、protocol warning、idle / cancellation diagnostics 等日志和 caplog 覆盖。

本 slice 的目标是“只补必要日志”。继续改 Engine agent / OpenAI runner 会扩大 diff，增加日志噪音与敏感字段回归风险，但没有直接证据表明当前 S15 success signal 需要它。因此本次只在 Host 已实现路径补缺，并保留 Engine 现状。

## 改动文件摘要

- `dayu/host/command.py`：新增 command accepted / committed `VERBOSE` 日志，记录 operation、session/run/wait/dispatch ids 与 run status。
- `dayu/host/admission.py`：新增 admission committed 与 promotion committed `VERBOSE` 日志，记录 Run / Attempt / dispatch ids、状态、是否 created / queued / replay / pending dispatch。
- `dayu/host/engine_ingest.py`：新增 ingest accepted / committed `VERBOSE` 日志，记录 envelope ids、worker event index、EngineEvent type、ingest status、event count、terminal closeout 与 promotion 标记。
- `dayu/host/local_proxy.py`：新增 LocalProxy accept / event stream opened / closed `VERBOSE` 日志，记录 worker / dispatch ids、message_count 与 disable_tools，不记录 message content。
- `dayu/host/tool_runtime.py`：新增 tool fact accept accepted / committed `VERBOSE` 与 rejected / timeout `DEBUG` 日志，记录 tool_call_id、tool_name、fact kind、event refs/counts、reason。
- `dayu/host/waiting.py`：新增 awaiting accept 与 resolve_wait `VERBOSE` / `DEBUG` 日志，记录 wait_id、adapter_key、dispatch refs、reason。
- `dayu/host/memory_repair.py`：新增 memory rebuild / catch-up start、committed、failed 日志，记录 consumer_id、cursor、event counts、failure count。
- `dayu/host/projection.py`：将 best-effort catch-up failure 从 exception/error 语义校准为 `WARNING`，只记录 `error_type`。
- `tests/host/test_logging.py`：新增 Host logging caplog 测试，覆盖 command、LocalProxy、memory catch-up 的 level / fields / redaction。
- `tests/host/test_toolruntime_accept_barrier.py`：补 tool accept 日志与 projection catch-up warning 级别测试。
- `tests/host/test_resolve_wait_command.py`：补 resolve_wait 日志脱敏测试。

## 日志级别 / 脱敏 / 非 truth 裁决

- `VERBOSE`：只用于主路径骨架，如 command accepted / committed、ingest accepted / committed、LocalProxy accept、ToolRuntime accept、resolve_wait、memory catch-up start / committed。
- `DEBUG`：只用于有界分支结果，如 ToolRuntime / awaiting accept rejected 或 timeout。
- `WARNING`：用于可恢复且不破坏 truth 的 projection catch-up failure；不回滚 command，不改 Run / Attempt / EventLog，不改变 recovery。
- 未新增 `INFO` / `ERROR` / `CRITICAL` 路径；现有 `CRITICAL` / `WARNING` Engine 和 dispatch 路径保持不变。
- 日志字段只记录 typed ids / refs / digest-like refs / status / reason / counts / cursor：`session_id`、`run_id`、`attempt_id`、`execution_id`、`dispatch_record_id`、`wait_id`、`tool_call_id`、`tool_name`、`event_count`、`cursor` 等。
- 明确不记录完整 prompt、tool args、tool result、delta body、authorization claims、provider secret、Fins source text、财报原文或大 payload。
- 日志不是 public API，不承担 UI 输出、审计真源、tool trace、EventLog canonical fact、projection checkpoint 或恢复输入职责。

## 测试验证

- `pytest tests/host/test_logging.py tests/host/test_toolruntime_accept_barrier.py -k "log or logging" tests/host/test_resolve_wait_command.py -k "log or logging"`
  - 结果：5 passed。
- `pytest tests/engine tests/host -k "log or logging or diagnostics or dispatch or ingest or projection or toolruntime"`
  - 结果：293 passed，632 deselected。
- `pytest tests/host/test_logging.py tests/host/test_admission_queue.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_memory_projection.py tests/host/test_projection_runner.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_executor.py`
  - 结果：163 passed。
- `python -m pyright dayu tests`
  - 结果：0 errors / 0 warnings / 0 informations。
- `git diff --check`
  - 结果：clean。

## README 不更新理由

本次实现没有改变 `dayu/README.md` 已定义的日志级别语义、字段命名、脱敏要求或“日志非 truth”约束，只是按既有规则补齐 Host 已实现路径的日志和测试。因此 README 不需要更新。`dayu/host/README.md` 的架构 / 执行路径说明也未发生稳定语义变化，新增日志不改变 public command、dispatch、projection、ToolRuntime 或 wait 的契约。

## 剩余风险

- 本次不引入 audit / tool trace / outbox sink；未来若需要稳定查询、审计、关联工具调用明细，应进入 Phase 13，而不是扩大 runtime logging。
- 日志覆盖是必要路径补齐，不是全路径逐行 tracing；过度 DEBUG / VERBOSE 会增加噪音和泄漏面。
- Engine agent / OpenAI runner 保持现状；若后续 review 发现明确缺口，应以具体 evidence 单独修正，避免 S15 扩散成 Engine 日志重构。
- Projection catch-up failure 现在只记录 `error_type`，利于脱敏；如需更细 failure 归因，应使用 projection-local failure row 或后续 trace / audit owner。
