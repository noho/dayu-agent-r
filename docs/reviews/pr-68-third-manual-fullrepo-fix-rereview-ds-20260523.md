# PR 68 第三轮手工全仓 Review 修复复审 — AgentDS

## 复审结论：PASS

## 复审范围

本轮复审对照已接受修复范围（5 项），逐项审计当前未提交 diff 的正确性、安全性与测试覆盖，并做 adversarial 边界推演。

## 逐项审计

### 1. `_DurableRunCancellationToken` fail-closed（dispatch.py:577-578）

- **变更**：`except HostTransactionRetryExhaustedError: return None` → `return _COMPACTION_CANCEL_REASON_DURABLE_UNAVAILABLE`
- **正确性**：`is_cancelled()` 判断 `cancel_reason() is not None`（行 558）。旧实现返回 `None` 导致 DB 不可用时 `is_cancelled()` 为 `False`，compaction 继续对状态未知的 Run 执行写入。新实现 fail-closed 返回 `"durable_unavailable"`，`is_cancelled()` 为 `True`，compaction 被正确阻止。
- **测试覆盖**：`test_durable_run_cancellation_token_fails_closed_on_retry_exhausted` 使用 `_RetryExhaustedReadRunner` 模拟 transaction retry 耗尽，断言 `is_cancelled() is True` 且 `cancel_reason() == "durable_unavailable"`。覆盖充分。
- **边界推演**：DB 短暂不可用后恢复的场景——compaction 本次已 abort，scheduler 可在后续周期重试。fail-closed 语义正确。
- **结论**：PASS

### 2. `run_compaction_operation` 每 attempt 前检查取消（compaction_operation.py:105-128）

- **变更**：在 `for` 循环体开头新增 `if cancellation_token.is_cancelled()` 检查，已取消时返回 `failure_reason="cancellation_requested"` 并记录 `CompactionAttemptRejected`。
- **正确性**：检查位于 `compactor.compact()` 调用（行 136）之前，填补了 attempt N 失败后、attempt N+1 开始前取消信号到达的窗口。
- **测试覆盖**：`test_run_compaction_operation_stops_before_retry_when_cancelled` 使用 `_CancelAfterFailureCompactor`：首次 `compact()` 调用中 `request_cancel` + 抛异常，验证 `compactor.calls == 1`（未发起第二次调用），`failure_reason == "cancellation_requested"`，`rejected_attempts[1].failure_category == "cancellation_requested"`。
- **边界推演**：首次迭代时 token 已取消（此前未执行任何 attempt）→ 仍创建一个 `attempt_number=1` 的 rejected attempt。语义一致：attempt 被 cancellation 拒绝，而非"未尝试"。`last_budget` 为 `None` 正确。
- **结论**：PASS

### 3. compaction diagnostic_refs 脱敏（compaction_operation.py:297-307）

- **变更**：`_exception_diagnostic_suffix()` 从直接 `str(exc)` 改为调用 `_safe_exception_message(exc)`，使诊断后缀与同模块已有脱敏路径一致。
- **正确性**：`_safe_exception_message`（行 381-403）对 Bearer token 做 `Bearer <redacted>` 替换，对 `api_key`/`authorization`/`token`/`secret` 赋值做值部分替换。`_exception_diagnostic_suffix` 在 `_safe_exception_message` 返回仅类名时（空消息）只返回类名，避免 `RuntimeError:RuntimeError` 双前缀。
- **测试覆盖**：`test_run_compaction_operation_redacts_exception_diagnostic_refs` 构造包含 `Bearer secret-token`、`api_key=plain-secret`、`token=token-secret`、`secret=raw-secret` 的异常消息，验证 diagnostic_refs 中不含任何明文 secret，且含 `<redacted>`。
- **残余注意**：compaction 的 `_ASSIGNMENT_SECRET_PATTERN`（行 39-41）未覆盖 `password` 和 `apikey`（无分隔符形式），与 engine/agent.py 的 pattern 覆盖范围不完全一致。此为**既有状态**，非本轮引入。本轮修复的实质改进是 `_exception_diagnostic_suffix` 不再绕过 `_safe_exception_message`。
- **结论**：PASS

### 4. Engine 异常诊断脱敏精确化（engine/agent.py:181-241）

- **变更**：
  - 删除宽泛子串 marker 元组 `_SENSITIVE_EXCEPTION_MARKERS`（含 `"token"`、`"header"` 等），替换为三个精确正则：
    - `_BEARER_SECRET_PATTERN`：`(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+`
    - `_API_KEY_VALUE_PATTERN`：`(?i)\b(?:api[ _-]?key|apikey)\b\s*(?::|=|\s+)\s*[^,\s}\]]+`
    - `_ASSIGNED_SECRET_VALUE_PATTERN`：`(?i)\b(?:authorization|password|secret|token)\b\s*[:=]\s*[^,\s}\]]+`
  - 提取 `_contains_sensitive_exception_value()` 函数，同时用于 `_exception_diagnostic_message()` 和 `_safe_log_message()`。
- **正确性**：
  - "JWT token has expired" 不再被误杀：`token` 后无 `[:=]` 赋值语法，不命中任何 pattern。
  - "Content-Type header is invalid" 不再被误杀：`header` 已从检测项移除。
  - `Bearer sk-xxx`、`api_key=xxx`、`authorization=xxx`、`password=xxx`、`secret=xxx`、`token=xxx` 仍触发整条脱敏。
- **测试覆盖**：
  - `test_exception_diagnostic_message_preserves_normal_token_and_header_words`：验证普通诊断保留。
  - `test_exception_diagnostic_message_redacts_sensitive_value_patterns`：8 个参数化用例验证敏感值脱敏。
  - 既有 `test_exception_diagnostic_message_redacts_*` 测试仍通过。
- **边界推演**：
  - `_API_KEY_VALUE_PATTERN` 在 "API key is invalid" 场景下会匹配 `API key is`（`\s+` 匹配空格后 `is` 作为值部分），触发整条脱敏。这是 false positive，但远好于旧实现的全局 `"token"`/`"header"` 子串匹配。属 fail-safe 脱敏的可接受 trade-off。
  - `_BEARER_SECRET_PATTERN` 在 "invalid bearer token" 下会匹配 `bearer token`（`token` 匹配 `[A-Za-z0-9._~+/=-]+`）。同为可接受 false positive。
  - `_safe_log_message` 无独立测试，但通过 `_contains_sensitive_exception_value` 与 `_exception_diagnostic_message` 共享判断逻辑，间接覆盖。
- **结论**：PASS

### 5. 文档边界修正

- **dayu/contracts/cancellation.py**：docstring 从引用 `dayu.engine.contracts.engine_events.RunCancelledData` 改为概念性描述"由上层 Engine 的结构化事件与 run outcome 表达"。消除 Contracts 层对 Engine 内部模块路径的文档引用。
- **dayu/__init__.py**：docstring 从 "Phase 0 仅落地 Engine 公共契约" 改为列出当前实际子包（engine、host、runtime、service）。
- **结论**：PASS

## 测试与类型检查

- `pytest tests/host/test_compaction_operation.py tests/engine/test_agent_phase2.py tests/host/test_dispatch_scheduler.py -q`：103 passed
- `pyright dayu tests`：0 errors, 0 warnings, 0 informations

## adversarial failure pass

| 场景 | 推演 | 结论 |
|------|------|------|
| DB retry 耗尽 + compaction 正在执行 | fail-closed → `is_cancelled=True` → abort | 安全 |
| compaction attempt 间取消到达 | 下次循环头 `is_cancelled()` 命中 | 不再调用 compactor |
| 异常消息含 `Bearer sk-xxx` + 换行 | `re.search` 默认不跨行；`str(exc)` 单行为主 | 低风险 |
| `cancel_reason()` 返回 `None` 但 `is_cancelled()` 为 True | `_cancellation_suffix` 防御性 fallback 到 `"cancelled"` | 安全 |
| 恶意构造超长 secret 值绕过 pattern | `[^,\s}\]]+` 在空白/逗号/括号处截断，截断后仍触发脱敏 | 安全 |

## 残余风险

1. **compaction 与 engine 脱敏 pattern 不一致**：compaction 的 `_ASSIGNMENT_SECRET_PATTERN` 缺少 `password` 和 `apikey`（无分隔符）。既有状态，非本轮引入。建议后续统一为一个 `dayu.runtime` 公共脱敏 helper。
2. **`_API_KEY_VALUE_PATTERN` false positive**：`API key is invalid` 等不含 secret 的诊断可能被整条脱敏。属于 fail-safe 脱敏的可接受 trade-off，远优于旧实现的全局子串匹配。
3. **`_safe_log_message` 无独立单测**：通过 `_contains_sensitive_exception_value` 间接覆盖。如需严格达到 80% 分支覆盖可后续补充。
4. **Engine 整条脱敏 vs Compaction 字段级脱敏**：策略不同（engine 更保守），各自有明确设计理由，非缺陷。

## Deferred 项确认

以下为总控明确 deferred 的 hardening/cleanup 项，本轮未引入相关变更，复审确认无新增风险：

- SSE fatal tool call partial completion
- `_safe_read_error_body_bytes` context overflow 推断
- `ActiveWorkerRegistry` RLock → asyncio.Lock
- 多连接 read semantics
- CJK token estimator
- `ConfigLoader` 拆分 / `compose_open_host_options` 拆分
- `close_open_session_row` status 统一
- `_require_non_empty_text` 去重
- lane 无限等待 / truncation cursor 上限
- LLM proposal cast / duplicate governance attempt_id
- Engine runtime import boundary 白名单
- `_resolve_project_path` 绝对路径语义

## 总评

本轮 5 项修复全部正确，测试覆盖充分，类型检查干净。着重解决了两个安全问题（DB 不可用时 fail-open 的取消判定、诊断路径绕过脱敏），显著收窄了异常脱敏的 false positive 面，文档边界修正消除了分层文档耦合。无阻断性问题。
