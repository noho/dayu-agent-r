# P9.5 S15 Code Review — AgentDS

**Review scope**: S15 Engine / Host Necessary Logs By Level 未提交 diff  
**Base**: `p9.5-pre-p10-hardening` vs HEAD unstaged changes  
**Reviewer**: AgentDS  
**Date**: 2026-05-17  
**Verdict**: **PASS** — 0 blocking, 0 medium/high severity regressions

---

## Review methodology

按第一性原理逐项复核 S15 日志级别/脱敏/事务语义/架构依赖/测试覆盖。设计真源 `dayu/README.md` "日志与可观测性" + "日志级别语义" 表格；总控 `docs/host/implementation-control.md:1059-1066` S15 条目；计划 `docs/host/p9-5-pre-p10-hardening-plan.md` S15 scope。所有证据来自 `git diff HEAD` 直接阅读 + rg + pytest + pyright + git diff --check。

---

## Diff 概要

10 个文件改动 + 1 个新文件，净增约 525 行：

| 文件 | 改动 | 性质 |
|---|---|---|
| `dayu/host/command.py` | +55 | `start_run`/`submit_followup`/`resolve_wait` 入口 accepted/committed VERBOSE 日志 |
| `dayu/host/admission.py` | +46 | admission 层 run_committed + promotion_committed VERBOSE 日志 |
| `dayu/host/engine_ingest.py` | +40 | EngineEvent ingest accepted/committed VERBOSE 日志 |
| `dayu/host/local_proxy.py` | +33 | LocalProxy accept/events_opened/closed VERBOSE 日志 |
| `dayu/host/memory_repair.py` | +76 | rebuild/catch_up start + committed/failed 日志，failure 分支用 WARNING |
| `dayu/host/projection.py` | +7/-4 | `catch_up_projection_best_effort` 从 ERROR 降级到 WARNING，仅记 error_type |
| `dayu/host/tool_runtime.py` | +94 | `accept_tool_fact` accepted/committed/rejected/timed_out 日志 |
| `dayu/host/waiting.py` | +119 | `accept_tool_awaiting` accepted/committed/rejected/timed_out + `resolve_wait` accepted/committed 日志 |
| `tests/host/test_logging.py` | 新增 | 命令脱敏、LocalProxy 脱敏、memory catch-up 骨架 3 个 caplog 测试 |
| `tests/host/test_resolve_wait_command.py` | +32 | resolve_wait 日志脱敏 caplog 测试 |
| `tests/host/test_toolruntime_accept_barrier.py` | +37 | tool accept 日志脱敏 + catch-up failure WARNING 级别断言 |

---

## Finding 1: 日志级别符合 dayu/README.md 级别语义

**Severity**: PASS

**Checked**: 每条新增 `_LOGGER.log(VERBOSE_LOG_LEVEL, ...)` / `_LOGGER.debug(...)` / `_LOGGER.warning(...)` 与 dayu/README.md 日志级别语义表格逐行对照：

| 代码位置 | 级别 | README 定义匹配 |
|---|---|---|
| `command.py` start/submit/resolve accepted/committed | VERBOSE | "Host command accepted / committed" |
| `admission.py` run_committed / promotion_committed | VERBOSE | "Host command accepted / committed" |
| `engine_ingest.py` accepted / committed | VERBOSE | "EngineEvent ingest" |
| `local_proxy.py` accept / events_opened / closed | VERBOSE | "WorkerProxy accept" |
| `memory_repair.py` rebuild/catch_up start / committed | VERBOSE | "projection catch-up" |
| `tool_runtime.py` accept_tool_fact accepted / committed | VERBOSE | "ToolRuntime accept barrier" |
| `waiting.py` accept_tool_awaiting / resolve_wait accepted / committed | VERBOSE | "ToolRuntime accept barrier" / "wait resolve" |
| `tool_runtime.py` / `waiting.py` rejected / timed_out | DEBUG | "Host command / dispatch / ingest / projection / ToolRuntime / wait adapter 的受控分支、CAS 结果、cursor、计数和 diagnostic refs" |
| `memory_repair.py` failures > 0 | WARNING | "Host projection catch-up 失败但 command 已提交" |
| `projection.py` catch-up failure | WARNING | "Host projection catch-up 失败但 command 已提交" |

**关键校准**: `projection.py:507-512` 将 `catch_up_projection_best_effort` 的日志从 `LOGGER.exception(...)` (ERROR + traceback) 改为 `LOGGER.warning("... error_type=%s", type(exc).__name__)` (WARNING + 仅类型名)。理由：
1. `dayu/README.md` 明确定义 WARN 用于 "Host projection catch-up 失败但 command 已提交"——这是本场景的精确定义
2. 旧 ERROR 级别不准确：catch-up 失败不回滚已提交 command，本次操作（command）实际成功
3. 不输出完整 exception message 避免潜在敏感信息泄漏（实现计划 line 1062-1064: "日志只记录 typed ids、refs、digest、cursor、policy / diagnostic refs，不记录完整 prompt、完整工具参数 / 结果..."）
4. 对应测试 `test_tool_fact_accept_survives_projection_catchup_failure` 已更新为 `caplog.at_level("WARNING", ...)` 并断言 `all(record.levelname == "WARNING" for record in caplog.records)`

**Conclusion**: 全部级别选择符合真源定义，无漏级或误级。

---

## Finding 2: 无敏感数据泄漏

**Severity**: PASS

**Checked**: 扫描全部新增日志格式字符串，逐字段验证数据类别：

| 日志字段类别 | 示例 | 是否属于敏感数据 |
|---|---|---|
| typed ids | `session_id`, `run_id`, `attempt_id`, `execution_id`, `dispatch_record_id`, `local_worker_id`, `wait_id`, `tool_call_id`, `tool_name`, `tool_fact_id`, `tool_result_event_id`, `input_event_id`, `consumer_id` | 否——稳定标识符 |
| status values | `run_status`, `ingest_status`, `engine_event_type`, `reason_code`, `tool_fact_kind`, `adapter_key`, `last_error_code` | 否——枚举值 |
| counts/bools | `message_count`, `event_count`, `events_scanned`, `events_matched`, `events_applied`, `duplicates`, `failures`, `accepted_event_count`, `attempt_count`, `created`, `queued`, `idempotent_replay`, `pending_dispatch`, `terminal_closeout`, `promotion_triggered`, `disable_tools`, `retryable` | 否——量化/布尔 |
| cursors/limits | `started_cursor`, `finished_cursor`, `batch_size`, `max_event_sequence`, `worker_event_index` | 否——顺序/配置 |
| operation names | `operation=start_run/submit_followup/resolve_wait`, `skip_reason` | 否——操作元数据 |

**明确不记录的内容**:
- `display_text` (prompt 文本) → 不在任何日志格式中
- `payload_json` / `payload_ref` / `payload_digest` → 不在任何日志格式中（仅 tool_fact_id / tool_result_event_id 等标识符）
- `authorization_claims` 原文 → 不在任何日志格式中
- `provider` / `api_key_ref` → 不在任何日志格式中（仅 disable_tools 布尔值）
- 工具结果 / outcome 内容 → 不在任何日志格式中

**脱敏专项测试验证**:
1. `test_command_logs_verbose_ids_without_prompt_or_auth_claims`: 将 `_SECRET_PROMPT` 放入 `HostInput.display_text` 和 `AuthorizationClaim.value`，断言 VERBOSE 日志中不出现 `_SECRET_PROMPT` 和 `_SECRET_AUTH`
2. `test_local_proxy_accept_log_uses_counts_not_message_content`: 将 `_SECRET_PROMPT` 放入 `SystemMessage.content`，断言 accept 日志用 `message_count=1` 而非消息内容
3. `test_resolve_wait_logs_ids_without_result_payload`: 断言 resolve_wait 日志中不出现 `"answer": 42` 或 `result` 字面量
4. `test_tool_fact_accept_logs_ids_without_tool_payload`: 断言 tool accept 日志中不出现 `{"outcome":` 或 `{"payload":`

**Conclusion**: 日志字段严格限定为 typed ids / refs / digest / cursor / counts / status values，无 prompt、工具结果、delta、财报原文、authorization claims 或 provider secret 泄漏。

---

## Finding 3: 日志未被当作 truth / audit / projection checkpoint

**Severity**: PASS

**Checked**: 每个新增日志调用点的副作用范围：

- 所有日志均通过 `logging.getLogger(__name__)` 发出，走 Python stdlib logging pipeline
- 无一将日志写入 EventLog table、SQLite durable store、projection checkpoint table、audit table、tool trace 或任何 durable 存储
- `memory_repair.py` 的 `_log_memory_projection_result` 只在 `catch_up_conversation_memory_projection` / `rebuild_conversation_memory_projection` 返回值后调用，读取的是已完成的 `ConversationMemoryProjectionRepairResult` dataclass 字段，不写回 projection checkpoint
- `catch_up_projection_best_effort` 的 WARNING 日志在 catch-up port 调用返回后发出，不改变 catch-up 结果或 durable state

**Conclusion**: 日志仅用于诊断，不承担任何 durable truth / audit / projection checkpoint 职责。符合 `dayu/README.md:185`: "日志不是 public API，不承担 UI 输出、审计真源、tool trace 热 / 冷数据、EventLog canonical fact 或 projection checkpoint 职责"。

---

## Finding 4: `accepted` / `committed` 命名与事务语义一致

**Severity**: PASS

**Checked**: 所有日志事件名前缀模式：

| 模块 | 日志事件名 | 发出时机 | 事务语义 |
|---|---|---|---|
| `command.py` | `host.command.accepted` | `run_write` 调用前 | 命令已通过 validation，即将提交 durable transaction |
| `command.py` | `host.command.committed` | `run_write` 返回后 | 事务已提交，结果已返回 |
| `admission.py` | `host.admission.run_committed` | `run_write` 返回后 | 事务已提交 |
| `admission.py` | `host.admission.promotion_committed` | promotion `run_write` 返回后 | 事务已提交 |
| `engine_ingest.py` | `host.engine_ingest.accepted` | `run_write` 调用前 | 事件已验证，即将提交 durable transaction |
| `engine_ingest.py` | `host.engine_ingest.committed` | `run_write` 返回 + terminal promotion 后 | 事务已提交，后续 promotion 已完成 |
| `local_proxy.py` | `host.local_proxy.accept` | worker handle 构造时 | worker handle 已创建 |
| `local_proxy.py` | `host.local_proxy.events_opened` | event stream 打开时 | 异步 stream 已就绪 |
| `local_proxy.py` | `host.local_proxy.closed` | event stream close 后 | worker 已关闭 |
| `memory_repair.py` | `host.memory_repair.rebuild.start` | reset transaction 前 | 即将开始 rebuild |
| `memory_repair.py` | `host.memory_repair.rebuild.committed` | runner idle 后 + `failures == 0` | 全部 projection 已提交 |
| `memory_repair.py` | `host.memory_repair.rebuild.failed` | runner idle 后 + `failures > 0` | 部分 projection 失败 |
| `tool_runtime.py` | `host.tool_runtime.accept_tool_fact.accepted` | `run_write` 调用前 | 候选已就绪，即将提交 |
| `tool_runtime.py` | `host.tool_runtime.accept_tool_fact.committed` | `run_write` 返回后 + `ToolFactAcceptedAck` | 事务已提交 |
| `tool_runtime.py` | `host.tool_runtime.accept_tool_fact.rejected` | exception handler 内 | 事务拒绝 |
| `waiting.py` | `host.waiting.accept_tool_awaiting.accepted` | `run_write` 调用前 | 候选已就绪 |
| `waiting.py` | `host.waiting.accept_tool_awaiting.committed` | `run_write` 返回后 + `ToolAwaitingAcceptedAck` | 事务已提交 |
| `waiting.py` | `host.waiting.resolve_wait.accepted` | `run_write` 调用前 | 请求已验证 |
| `waiting.py` | `host.waiting.resolve_wait.committed` | `run_write` 返回后 + catch-up | 事务已提交 |

**结论**: `accepted` = "arguments validated, about to enter write transaction"; `committed` = "write transaction returned successfully, result available"。`failed` (memory_repair) = "runner stopped with failures > 0"。`rejected` / `timed_out` (tool accept / awaiting accept) = "barrier returned non-accept result"。事件名与事务边界一一对应。

---

## Finding 5: 无架构反向依赖或过度日志

**Severity**: PASS

**Checked**:

1. **依赖方向**: 所有新增 import 为 `from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL`（层中立 runtime 基础设施，CLAUDE.md 明确允许）和 `import logging`（stdlib）。无一模块从 Engine 导入日志 helper、从 Service/UI 导入日志工具，或从上层构建日志 pipeline。

2. **日志粒度**: 每个模块的日志量符合 "VERBOSE 应比 DEBUG 更安静" 的原则。以一次 `start_run` 为例：
   - command.py: 2 条 VERBOSE (accepted + committed)
   - admission.py: 1 条 VERBOSE (run_committed)
   - 总计 3 条 VERBOSE per start_run，每条约 150-250 字符

3. **无冗余日志**: 未发现同一事件在多层记录（command.py `host.command.committed` 记录 run_id/run_status/input_event_id，admission.py `host.admission.run_committed` 记录 session_id/run_id/run_status/attempt_id/dispatch_record_id/created/queued/idempotent_replay/pending_dispatch——二者字段交集为 run_id/run_status，其他字段互不重叠，表达不同层次的不同信息）

4. **无过多 `_raise_if_closed` 变动**: `command.py` 在 `resolve_wait` 中增加了 `host._raise_if_closed()` 调用（line 181-182），与 `start_run`/`submit_followup` 保持一致。这不属于日志变更，是防御性一致性改进，不引入架构问题。

**Conclusion**: 架构方向正确，日志量克制，无冗余或反向依赖。

---

## Finding 6: caplog 测试覆盖有意义路径

**Severity**: PASS

**Checked**: 5 个新增/增强 caplog 测试覆盖的核心断言：

| 测试 | 验证范围 | 关键断言 |
|---|---|---|
| `test_command_logs_verbose_ids_without_prompt_or_auth_claims` | command 层入口脱敏 | `_SECRET_PROMPT not in caplog.text`、`_SECRET_AUTH not in caplog.text`、`all(record.levelno == VERBOSE_LOG_LEVEL)` |
| `test_local_proxy_accept_log_uses_counts_not_message_content` | LocalProxy accept 脱敏 | `message_count=1 in caplog.text`、`_SECRET_PROMPT not in caplog.text` |
| `test_memory_catchup_logs_cursors_and_counts` | memory catch-up 骨架 | `consumer_id=host.memory.session.v1`、`events_scanned=0`、`finished_cursor=0` |
| `test_resolve_wait_logs_ids_without_result_payload` | resolve_wait 脱敏 | `host.waiting.resolve_wait.accepted`/`committed` 出现、`"answer": 42 not in caplog.text`、`result not in caplog.text` |
| `test_tool_fact_accept_logs_ids_without_tool_payload` | tool accept 脱敏 | `tool_call_id=tool-call-logging`、`tool_name=lookup`、`{"outcome": not in caplog.text`、`{"payload": not in caplog.text` |
| `test_tool_fact_accept_survives_projection_catchup_failure` (更新) | WARNING 级别校准 | `caplog.at_level("WARNING", ...)`、`all(record.levelname == "WARNING")` |

**覆盖维度**:
- 正面路径 (accepted/committed) 的日志存在性和字段完整性
- 负面路径 (catch-up failure) 的级别正确性
- 脱敏路径 (prompt/auth/result payload/outcome JSON) 的排他性断言
- 骨架路径 (cursor/counts) 的计数正确性

**未覆盖项 (low risk)**:
- `memory_repair.py` failures > 0 的 WARNING 路径 — 测试 projection failure 需要较大 setup 成本，现有 `test_tool_fact_accept_survives_projection_catchup_failure` 间接覆盖了 projection 层的 failure logging，且 memory_repair `_log_memory_projection_result` 的 `failures > 0` 分支逻辑简单（仅读取 result dataclass 字段），风险低
- `engine_ingest.py` 的 committed 日志 — `test_engine_ingest_*` 测试通过 caplog 零配置的默认行为间接覆盖，但无显式断言 VERBOSE 级别下的特定字段；风险低，因为 ingest 日志字段与 accepted 日志一致且均为 typed ids

---

## Full Host regression

- `pytest tests/host -q` → **559 passed** in 6.29s (S14: 554 + S15: 5 new)
- `pyright dayu tests` → **0 errors, 0 warnings, 0 informations**
- `git diff --check` → clean

---

## Adversarial failure pass

1. **日志注入攻击**: 所有日志使用 `%s` 占位符，由 Python logging 框架的惰性格式化处理。即使 `session_id` 或 `run_id` 包含换行符或日志元字符，也不会破坏日志行的结构完整性。验证通过。

2. **异常信息泄漏**: `catch_up_projection_best_effort` 改为 `LOGGER.warning("... error_type=%s", type(exc).__name__)`，不记录 `str(exc)` 或 traceback。即使异常消息包含敏感上下文（如工具返回的错误文本），也不会进入日志。验证通过。

3. **日志级别配置绕过**: 所有日志通过 `logging.getLogger(__name__)` 发出，遵守 Python logging 的标准级别/过滤器/处理器配置。生产环境可通过标准 logging 配置关闭 VERBOSE 或 DEBUG。验证通过。

4. **高负载下日志风暴**: 每条日志约 150-350 字符，VERBOSE 级别下每 command 3-4 条日志，总量约 1KB per command。不会构成日志风暴。

5. **`result` 字段误匹配**: `test_resolve_wait_logs_ids_without_result_payload` 断言 `"result" not in caplog.text`。在本次日志格式中，"result" 作为 Python 变量名出现在 format string 参数中但不在日志输出中（输出使用 `%s` 替换后的值，如 `run_status=RUNNING`）。该断言验证了日志格式不包含 Python 对象名或 payload 字段，不会因 future log format 修改产生误报——当 `result` 字面量确实应出现在日志中时，测试会明确失败要求更新。

---

## Summary

| # | Finding | Severity | Verdict |
|---|---|---|---|
| F1 | 日志级别符合 `dayu/README.md` 级别语义 | — | PASS |
| F2 | 无敏感数据泄漏 (prompt / tool result / delta / auth / secret) | — | PASS |
| F3 | 日志非 truth / audit / projection checkpoint | — | PASS |
| F4 | `accepted`/`committed` 命名与事务语义一致 | — | PASS |
| F5 | 无架构反向依赖或过度日志 | — | PASS |
| F6 | caplog 测试覆盖有意义路径 | — | PASS |

**Overall verdict**: **PASS** — S15 按设计真源 `dayu/README.md` 日志级别语义为 Engine / Host P1-P9 已实现路径补全了必要日志：VERBOSE 级表达执行骨架（command accepted/committed、dispatch accept、ingest、projection catch-up、ToolRuntime accept barrier、wait resolve），DEBUG 级表达受控细节（reject/timed-out barrier 结果），WARNING 级表达可恢复异常（catch-up failure）。日志字段严格限定为 typed ids / refs / digest / cursor / counts / status values，不记录 prompt、工具参数/结果、delta、财报原文、authorization claims 或 provider secret。5 个 caplog 专项测试覆盖了脱敏和骨架路径。`projection.py` catch-up failure 从 ERROR 降为 WARNING 是正确的级别校准（"Host projection catch-up 失败但 command 已提交"）。

0 blocking findings。全量回归 559 passed, pyright clean。
