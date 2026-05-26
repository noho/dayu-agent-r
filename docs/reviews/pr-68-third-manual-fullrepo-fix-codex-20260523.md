# PR 68 Third Manual Full-Repo Review Repair - AgentCodex

## 实际修复项

1. `dayu/host/dispatch.py`
   - `_DurableRunCancellationToken.cancel_reason()` 在 `HostTransactionRetryExhaustedError` 时改为 fail-closed，返回 `durable_unavailable`。
   - `is_cancelled()` 因此在 durable read 重试耗尽时返回 `True`，避免 proactive compaction 在 Run 状态不可确认时继续执行。
   - 新增 `tests/host/test_dispatch_scheduler.py::test_durable_run_cancellation_token_fails_closed_on_retry_exhausted` 覆盖 retry exhausted 下 `is_cancelled/cancel_reason`。

2. `dayu/host/compaction_operation.py`
   - `run_compaction_operation()` 在每次 attempt 调用 compactor 前检查 `cancellation_token.is_cancelled()`。
   - 已取消时不再调用 compactor，返回 `failure_reason="cancellation_requested"`，并写入一个 `CompactionAttemptRejected` 结构化拒绝结果。
   - 新增 `tests/host/test_compaction_operation.py::test_run_compaction_operation_stops_before_retry_when_cancelled` 覆盖首次失败后 token 被取消，不发起第二次 compactor 调用。

3. `dayu/host/compaction_operation.py`
   - `_exception_diagnostic_suffix()` 改为复用 `_safe_exception_message()` 的脱敏结果，不再直接拼接 `str(exc)`。
   - 新增 `tests/host/test_compaction_operation.py::test_run_compaction_operation_redacts_exception_diagnostic_refs` 覆盖 Bearer token、`api_key`、`token`、`secret` 赋值不进入 `diagnostic_refs`。

4. `dayu/engine/agent.py`
   - `_exception_diagnostic_message()` 的敏感判断从宽泛子串 marker 改为精确模式：
     - 保留普通诊断词，例如 `JWT token has expired`、`Content-Type header is invalid`。
     - 仍整条脱敏疑似 secret 明文值，例如 Bearer token、API key、`api_key`、`apikey`、`authorization`、`password`、`secret`、`token` 赋值。
   - `_safe_log_message()` 复用同一敏感值判断，避免日志摘要继续沿用过度脱敏的 root cause。
   - 新增 `tests/engine/test_agent_phase2.py` 对普通 token/header 诊断保留和敏感值模式脱敏的覆盖。

5. 低风险文档修正
   - `dayu/contracts/cancellation.py` docstring 不再直接引用 Engine 内部模块路径。
   - `dayu/__init__.py` 顶层 docstring 移除 “Phase 0 仅 Engine” 的过时表述，改为列出当前主要子包职责。

## Deferred 项及理由

- SSE fatal tool call partial completion：涉及 `RunnerContentCompletedData` contract 是否新增 partial 字段和 Engine 事件序列设计，本 gate 明确 deferred。
- `_safe_read_error_body_bytes` body 读取失败下 context overflow 推断、`ActiveWorkerRegistry` RLock、多连接 read semantics、CJK token estimator、`ConfigLoader` 拆分、`compose_open_host_options` 拆分、`close_open_session_row` status、`_require_non_empty_text` 去重、lane 无限等待、truncation cursor 上限、LLM proposal cast、duplicate governance attempt_id、Engine runtime import boundary 白名单：均为总控明确 deferred 的 hardening / cleanup 范围，本轮未修改。
- `_resolve_project_path` 绝对路径语义：总控明确保持当前裁决，本轮未修改。

## 运行命令和结果

- `source .venv/bin/activate && pytest tests/host/test_compaction_operation.py`
  - 结果：21 passed。
- `source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py -k exception_diagnostic_message`
  - 结果：12 passed, 27 deselected。
- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -k durable_run_cancellation_token_fails_closed_on_retry_exhausted`
  - 结果：1 passed, 42 deselected。
- `source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py`
  - 结果：39 passed。
- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py`
  - 结果：43 passed。

## Pyright 结果

- `source .venv/bin/activate && pyright dayu tests`
  - 结果：0 errors, 0 warnings, 0 informations。

## README 检查结论

- 本轮触及 `dayu/host/`、`dayu/engine/`、`tests/`、`dayu/contracts/` 和包根 docstring，已按触发规则检查根 `README.md`、`dayu/README.md`、`dayu/engine/README.md`、`dayu/host/README.md`、`tests/README.md`。
- 修复内容未改变 public API、CLI、配置入口、分层关系或用户工作流；现有 README 对 Host compaction/cancellation、Engine cancellation/diagnostic 和测试分层的稳定描述仍一致，因此无需修改 README。

## 剩余风险

- `run_compaction_operation()` 在取消检查命中后会为取消生成一次 rejected attempt；调用方已按现有 `CompactionOperationResult` 消费 rejected attempts，未引入新结果类型。
- Engine 异常诊断仍采用整条脱敏策略；本轮只收窄“何时脱敏”的判定，不做字段级局部脱敏，以避免误保留 secret 片段。
- 本轮只运行受影响测试和 `pyright dayu tests`，未运行全仓 pytest。
