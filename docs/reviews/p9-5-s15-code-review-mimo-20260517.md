# P9.5 S15 Code Review — Engine / Host Necessary Logs By Level

## Review Context

- Reviewer: AgentMiMo
- Scope: S15 Engine / Host Necessary Logs By Level
- Design source: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Plan: `docs/host/p9-5-pre-p10-hardening-plan.md` S15
- Diff: uncommitted changes on `p9.5-pre-p10-hardening`

## Verdict: CONDITIONAL PASS — 缺少 Engine 侧日志

S15 Host 侧日志实现正确，级别语义、脱敏、命名均符合约束。但 S15 plan 明确要求 Engine 侧日志（`dayu/engine/agent.py`、`dayu/engine/runners/openai/*`），当前 diff 未包含，属于 scope gap。

---

## Findings

### F1 — Engine 侧日志缺失

**Severity: MEDIUM (scope gap)**

S15 plan 明确列出允许修改的文件：

> `dayu/engine/agent.py`, `dayu/engine/runners/openai/*`

且 Exact changes 要求：

> Add `VERBOSE` skeleton logs for Engine run/iteration/runner call/tool loop/terminal

当前 diff 只包含 Host 侧模块（admission、command、engine_ingest、local_proxy、memory_repair、projection、tool_runtime、waiting），未包含任何 Engine 侧改动。

**证据**：`git diff HEAD --stat` 无 `dayu/engine/` 文件。

**建议**：确认 Engine 侧日志是否属于 S15 scope。若属于，需补充 `dayu/engine/agent.py` 和 `dayu/engine/runners/openai/*` 的 VERBOSE 骨架日志。若已裁决排除，需在实施 artifact 中记录裁决理由。

---

### F2 — `dispatch.py` 状态推进日志缺失

**Severity: LOW (scope gap)**

S15 plan Exact changes 要求：

> dispatch state advance

`dayu/host/dispatch.py` 在允许修改文件列表中，但当前 diff 未包含 dispatch 模块改动。

**建议**：确认 dispatch 状态推进日志是否属于 S15 scope。Host dispatch 是关键执行路径，缺少 VERBOSE 骨架日志会降低生产可观测性。

---

### F3 — Host 日志级别语义

**Severity: PASS**

逐模块验证日志级别是否符合 `dayu/README.md` 定义：

| 模块 | 日志内容 | 级别 | README 定义 | 判定 |
|------|----------|------|-------------|------|
| `admission.py` | `host.admission.run_committed` | VERBOSE | Host command committed | ✓ |
| `admission.py` | `host.admission.promotion_committed` | VERBOSE | dispatch 状态推进 | ✓ |
| `command.py` | `host.command.accepted` | VERBOSE | Host command accepted | ✓ |
| `command.py` | `host.command.committed` | VERBOSE | Host command committed | ✓ |
| `engine_ingest.py` | `host.engine_ingest.accepted` | VERBOSE | EngineEvent ingest | ✓ |
| `engine_ingest.py` | `host.engine_ingest.committed` | VERBOSE | EngineEvent ingest | ✓ |
| `local_proxy.py` | `host.local_proxy.accept` | VERBOSE | WorkerProxy accept | ✓ |
| `local_proxy.py` | `host.local_proxy.events_opened` | VERBOSE | WorkerProxy accept | ✓ |
| `local_proxy.py` | `host.local_proxy.closed` | VERBOSE | terminal closeout | ✓ |
| `memory_repair.py` | `host.memory_repair.rebuild.start` | VERBOSE | projection catch-up | ✓ |
| `memory_repair.py` | `host.memory_repair.catch_up.start` | VERBOSE | projection catch-up | ✓ |
| `memory_repair.py` | `host.memory_repair.*.committed` | VERBOSE | projection catch-up | ✓ |
| `memory_repair.py` | `host.memory_repair.*.failed` | WARNING | 可恢复异常 | ✓ |
| `projection.py` | `projection catch-up failed` | WARNING | 可恢复异常 | ✓ |
| `tool_runtime.py` | `accept_tool_fact.accepted` | VERBOSE | ToolRuntime | ✓ |
| `tool_runtime.py` | `accept_tool_fact.committed` | VERBOSE | ToolRuntime | ✓ |
| `tool_runtime.py` | `accept_tool_fact.rejected` | DEBUG | 有界决策 | ✓ |
| `tool_runtime.py` | `accept_tool_fact.timed_out` | DEBUG | 有界决策 | ✓ |
| `waiting.py` | `accept_tool_awaiting.accepted` | VERBOSE | wait resolve | ✓ |
| `waiting.py` | `accept_tool_awaiting.committed` | VERBOSE | wait resolve | ✓ |
| `waiting.py` | `accept_tool_awaiting.rejected` | DEBUG | 有界决策 | ✓ |
| `waiting.py` | `accept_tool_awaiting.timed_out` | DEBUG | 有界决策 | ✓ |
| `waiting.py` | `resolve_wait.accepted` | VERBOSE | wait resolve | ✓ |
| `waiting.py` | `resolve_wait.committed` | VERBOSE | wait resolve | ✓ |

**判定**：所有已添加日志的级别均符合 README 定义。

---

### F4 — 敏感数据泄漏检查

**Severity: PASS**

逐项检查 README 禁止泄漏的数据类型：

| 数据类型 | 是否泄漏 | 证据 |
|----------|----------|------|
| 完整 prompt | 否 | 所有日志只记录 typed refs（session_id、run_id 等） |
| 完整 tool args | 否 | 只记录 `tool_call_id`、`tool_name`，不记录 arguments |
| 完整 tool results | 否 | 只记录 `tool_fact_id`、`tool_result_event_id`，不记录 result value |
| delta 全量 | 否 | 无 delta 内容日志 |
| 财报原文 | 否 | 无财报内容日志 |
| provider secret | 否 | 无 provider 相关日志 |
| 大 payload | 否 | 只记录 `len(request.messages)` 和 `disable_tools` 布尔值 |
| authorization claims | 否 | 无 authorization 相关日志 |
| raw cursor / scope token | 否 | 只记录 `started_cursor`、`finished_cursor` 整数值 |

**补充验证**：
- `local_proxy.py:329` 记录 `len(request.messages)` — `AgentRunRequest.messages` 类型为 `tuple[AgentMessage, ...]`，`len()` 安全，不泄漏内容
- `local_proxy.py:330` 记录 `request.disable_tools` — 布尔值，安全
- 测试 `test_tool_fact_accept_logs_ids_without_tool_payload` 断言 `"{\"outcome\":" not in caplog.text` 和 `"{\"payload\":" not in caplog.text` — 验证 digest 原始 JSON 未泄漏

---

### F5 — 日志是否错误地成为 truth / audit / projection checkpoint

**Severity: PASS**

所有新增日志均为诊断性骨架日志，不承担以下职责：

- 不写 EventLog（事实真源）
- 不写 projection checkpoint
- 不写 audit / tool trace
- 不作为 public API

日志只记录已提交事务的结果摘要（`run_id`、`status`、`event_count` 等），不改变任何 durable 状态。

---

### F6 — `accepted` / `committed` 命名是否与事务语义一致

**Severity: PASS**

命名约定：
- `accepted`：操作被接受、验证通过、进入事务执行前
- `committed`：durable transaction 已提交后

验证：
- `command.py`：`host.command.accepted` 在 `_raise_if_closed()` 之后、事务调用之前；`host.command.committed` 在事务返回之后。✓
- `admission.py`：`_log_run_admission_result` 在事务返回后调用，使用 `run_committed`。✓
- `engine_ingest.py`：`accepted` 在 `_validate_candidate_shape` 之后、事务调用之前；`committed` 在 `_with_terminal_promotion_retry` 返回之后。✓
- `tool_runtime.py`：`accepted` 在事务调用之前；`committed` / `rejected` / `timed_out` 在事务返回之后。✓
- `waiting.py`：同上模式。✓

---

### F7 — `projection.py` 日志级别变更

**Severity: INFO (合理)**

变更：`_LOGGER.exception(...)` → `_LOGGER.warning(..., type(exc).__name__)`

原代码使用 `exception()` 在 ERROR 级别记录完整 traceback。新代码使用 `warning()` 在 WARNING 级别记录 `error_type`。

**理由**：
- README 定义 WARNING 用于"可恢复异常。Host projection catch-up 失败但 command 已提交"
- README 定义 ERROR 用于"本次操作失败"
- projection catch-up 失败不导致 command 失败，因此 WARNING 正确
- 移除 traceback 可接受，`error_type=%s` 提供足够诊断上下文

**测试同步**：`test_tool_fact_accept_survives_projection_catchup_failure` 已更新 caplog 级别从 `ERROR` 到 `WARNING`，并增加 `assert all(record.levelname == "WARNING" ...)` 断言。✓

---

### F8 — Logger 获取模式

**Severity: PASS**

S15 plan 要求：

> Where local code already uses module-level `logging.getLogger(__name__)`, keep that pattern and do not introduce constructor-injected loggers. If a module has no logger and needs one, default to module-level `_LOGGER = logging.getLogger(__name__)`.

验证：
- `admission.py`：新增 `_LOGGER = logging.getLogger(__name__)` ✓
- `command.py`：新增 `_LOGGER = logging.getLogger(__name__)` ✓
- `engine_ingest.py`：新增 `_LOGGER = logging.getLogger(__name__)` ✓
- `local_proxy.py`：新增 `_LOGGER = logging.getLogger(__name__)` ✓
- `memory_repair.py`：新增 `_LOGGER = logging.getLogger(__name__)` ✓
- `tool_runtime.py`：新增 `_LOGGER = logging.getLogger(__name__)` ✓
- `waiting.py`：新增 `_LOGGER = logging.getLogger(__name__)` ✓
- `projection.py`：已有 `_LOGGER`，未变更模式 ✓

所有模块使用 `dayu.runtime.log_levels.VERBOSE_LOG_LEVEL` 常量，不硬编码数值。✓

---

### F9 — caplog 测试覆盖

**Severity: PASS (有限覆盖)**

当前测试覆盖：

1. `test_resolve_wait_logs_ids_without_result_payload`：
   - 验证 `host.waiting.resolve_wait.accepted` 和 `committed` 出现
   - 验证 `wait_id` 和 `run_id` 出现
   - 验证 result payload `{"answer": 42}` 未泄漏
   - 验证 `"result"` 字面量未出现

2. `test_tool_fact_accept_logs_ids_without_tool_payload`：
   - 验证 `host.tool_runtime.accept_tool_fact.accepted` 和 `committed` 出现
   - 验证 `run_id`、`attempt_id`、`tool_call_id`、`tool_name` 出现
   - 验证 outcome JSON 和 payload JSON 未泄漏

3. `test_tool_fact_accept_survives_projection_catchup_failure`：
   - 已更新为 WARNING 级别断言
   - 验证所有 record 级别为 WARNING

**覆盖缺口**：
- `admission.py` 日志未测试
- `command.py` 日志未测试
- `engine_ingest.py` 日志未测试
- `local_proxy.py` 日志未测试
- `memory_repair.py` 日志未测试
- rejected / timed_out 路径日志未测试

S15 plan 要求"Add caplog tests for level and redaction"，当前测试覆盖了关键的 redaction 场景（payload 未泄漏），但 level 覆盖有限。

**建议**：补充至少一个 admission 或 command 的 caplog 测试，验证 VERBOSE 级别和字段完整性。

---

## Summary

| Finding | Description | Severity |
|---------|-------------|----------|
| F1 | Engine 侧日志缺失（agent.py、runners/openai/*） | MEDIUM |
| F2 | dispatch.py 状态推进日志缺失 | LOW |
| F3 | Host 日志级别语义正确 | PASS |
| F4 | 无敏感数据泄漏 | PASS |
| F5 | 日志未成为 truth / audit / projection | PASS |
| F6 | accepted / committed 命名与事务语义一致 | PASS |
| F7 | projection.py 级别变更合理 | INFO |
| F8 | Logger 获取模式符合 plan | PASS |
| F9 | caplog 测试覆盖有限但关键场景已覆盖 | PASS |

## 结论

Host 侧日志实现质量高，级别语义、脱敏、命名、事务边界均正确。主要 gap 是 Engine 侧日志和 dispatch 状态推进日志未在当前 diff 中。需确认这些是否属于 S15 scope；若属于，需补充实现。
