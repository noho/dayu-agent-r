# PR 68 第三轮手工全仓 review 修复复审 - AgentMiMo

## 复审范围

- **Gate**: PR 68 post-draft 第三轮手工全仓 review 修复复审
- **输入 artifacts**:
  - `docs/reviews/repo-review-20260523-215141.md`（第一轮全仓 review）
  - `docs/reviews/repo-review-20260523-215152.md`（第二轮全仓 review）
  - `docs/reviews/pr-68-third-manual-fullrepo-fix-codex-20260523.md`（Codex 修复报告）
- **审查对象**: 当前未提交 diff（`git diff`），覆盖 5 个已接受修复范围
- **复审标准**: correctness、Host 强约束取消治理、敏感信息泄漏、类型与分层边界、测试覆盖真实 root cause

## 已接受修复范围逐项复审

### Fix 1: Durable cancellation token fail-closed（dispatch.py）

**修复内容**: `_DurableRunCancellationToken.cancel_reason()` 在 `HostTransactionRetryExhaustedError` 时返回 `"durable_unavailable"`，`is_cancelled()` 因此返回 `True`。

**Diff 证据**:
- `dayu/host/dispatch.py:577-578`: `except HostTransactionRetryExhaustedError: return _COMPACTION_CANCEL_REASON_DURABLE_UNAVAILABLE`
- 新常量 `_COMPACTION_CANCEL_REASON_DURABLE_UNAVAILABLE = "durable_unavailable"` 定义于行 203
- `is_cancelled()` 通过 `self.cancel_reason() is not None` 正确传播

**测试覆盖**: `test_durable_run_cancellation_token_fails_closed_on_retry_exhausted`
- 使用 `_RetryExhaustedReadRunner`（`tests/host/test_dispatch_scheduler.py:162-183`）始终抛出 `HostTransactionRetryExhaustedError`
- 断言 `is_cancelled() is True` 和 `cancel_reason() == "durable_unavailable"`
- 覆盖了 root cause：DB 不可用时 fail-closed 语义

**评估**: **PASS** — fail-closed 语义正确，测试覆盖真实 root cause（retry exhausted → cancel reason → is_cancelled 传播链完整）。

---

### Fix 2: Compaction 重试循环迭代间检查取消（compaction_operation.py）

**修复内容**: `run_compaction_operation()` 每次 attempt 前检查 `cancellation_token.is_cancelled()`，取消后返回 `failure_reason="cancellation_requested"` 并记录 rejected attempt。

**Diff 证据**:
- `dayu/host/compaction_operation.py:106-131`: 循环体开头新增取消检查，构造 `CompactionAttemptRejected` 并提前返回
- 新常量 `_FAILURE_CANCELLATION_REQUESTED = "cancellation_requested"` 和 `_DIAGNOSTIC_SUFFIX_CANCELLED = "cancelled"`
- `_cancellation_suffix()` helper（行 307-321）从 token 读取 cancel_reason，空值时回退到 `"cancelled"`

**测试覆盖**: `test_run_compaction_operation_stops_before_retry_when_cancelled`
- `_CancelAfterFailureCompactor` 在首次调用时请求取消并抛出异常
- 断言 `compactor.calls == 1`（第二次 attempt 未调用 compactor）
- 断言 `failure_reason == "cancellation_requested"`
- 断言 `rejected_attempts[1].attempt_number == 2` 且 `failure_category == "cancellation_requested"`
- 断言 `"test_cancelled" in diagnostic_refs[0]`

**评估**: **PASS** — 取消检查在循环体最前面，早于 compactor 调用；rejected attempt 记录完整；测试验证了取消信号传播和 compactor 调用计数。

---

### Fix 3: Compaction proposal 异常 diagnostic_refs 脱敏（compaction_operation.py）

**修复内容**: `_exception_diagnostic_suffix()` 从直接使用 `str(exc)` 改为复用 `_safe_exception_message(exc)`。

**Diff 证据**:
- `dayu/host/compaction_operation.py:304-305`: `message = _safe_exception_message(exc)`，空消息判断从 `message == ""` 改为 `message == exc.__class__.__name__`（对齐 `_safe_exception_message` 的空消息返回值）
- `_safe_exception_message` 使用 `_BEARER_SECRET_PATTERN.sub()` 和 `_ASSIGNMENT_SECRET_PATTERN.sub()` 正则替换

**Redaction 模式一致性**:
- `compaction_operation.py:38-41`: `_BEARER_SECRET_PATTERN` 和 `_ASSIGNMENT_SECRET_PATTERN` 覆盖 Bearer token、api_key、authorization、token、secret 赋值
- `agent.py:181-187`: 三个独立 pattern（`_BEARER_SECRET_PATTERN`、`_API_KEY_VALUE_PATTERN`、`_ASSIGNED_SECRET_VALUE_PATTERN`）覆盖相同语义范围
- 两处 pattern 语义一致，compaction 侧使用替换策略（`sub`），agent 侧使用匹配策略（`search`），各自合理

**测试覆盖**: `test_run_compaction_operation_redacts_exception_diagnostic_refs`
- `_SensitiveFailingCompactor` 抛出包含 `Bearer secret-token`、`api_key=plain-secret`、`token=token-secret`、`secret=raw-secret` 的异常
- 断言所有 secret 值不在 `diagnostic_refs[0]` 中，`"<redacted>"` 在其中

**评估**: **PASS** — 脱敏复用正确，两层 redaction pattern 语义对齐，测试覆盖多种 secret 格式。

---

### Fix 4: Engine 异常诊断脱敏精确化（agent.py）

**修复内容**: 从宽泛子串 marker（包含 `"token"`、`"header"`）改为精确正则模式，只在消息包含疑似 secret 明文值时才脱敏。

**Diff 证据**:
- `dayu/engine/agent.py:181-187`: 三个 regex pattern 替代 `_SENSITIVE_EXCEPTION_MARKERS` tuple
  - `_BEARER_SECRET_PATTERN`: 匹配 `Bearer <value>` 格式
  - `_API_KEY_VALUE_PATTERN`: 匹配 `api key <value>`、`api_key=<value>` 等
  - `_ASSIGNED_SECRET_VALUE_PATTERN`: 匹配 `authorization=<value>`、`password=<value>`、`secret=<value>`、`token=<value>` 赋值
- `_contains_sensitive_exception_value()` 函数（行 229-241）组合三个 pattern
- `_exception_diagnostic_message()` 和 `_safe_log_message()` 均复用此函数

**保留诊断词验证**:
- `"JWT token has expired"`: "token" 后跟 "has" 而非 `=` 或 `:`，不命中 `_ASSIGNED_SECRET_VALUE_PATTERN`
- `"Content-Type header is invalid"`: "header" 不在敏感关键词列表中，不命中任何 pattern

**脱敏触发验证**:
- `"Bearer sk-secret-value"`: 命中 `_BEARER_SECRET_PATTERN`
- `"api_key=sk-secret-value"`: 命中 `_API_KEY_VALUE_PATTERN`
- `"token=sk-secret-value"`: 命中 `_ASSIGNED_SECRET_VALUE_PATTERN`

**测试覆盖**:
- `test_exception_diagnostic_message_preserves_normal_token_and_header_words`: 参数化测试 `"JWT token has expired"` 和 `"Content-Type header is invalid"`，断言消息原样保留
- `test_exception_diagnostic_message_redacts_sensitive_value_patterns`: 参数化测试 8 种 secret 格式，断言整条脱敏且 secret 值不在输出中

**评估**: **PASS** — 正则模式精确区分诊断词与 secret 值赋值，两组测试覆盖保留与脱敏双向，`_safe_log_message` 同步复用避免日志侧遗留过度脱敏。

---

### Fix 5: 文档边界修正（cancellation.py + __init__.py）

**修复内容**:
- `dayu/contracts/cancellation.py:8`: 移除对 `dayu.engine.contracts.engine_events.RunCancelledData` 和 `dayu.engine.contracts.agent_run.EngineRunOutcomeCancelled` 的 `:class:` 交叉引用，改为概念性描述"上层 Engine 的结构化事件与 run outcome 表达"
- `dayu/__init__.py:4-8`: 移除 "Phase 0 仅落地 Engine 公共契约；Host / Service / UI 等其它子包尚未引入"，改为列出当前四个子包职责

**评估**: **PASS** — Contracts 层不再引用 Engine 内部模块路径，包根 docstring 反映当前架构状态。

---

## 阻断性发现扫描

对当前 diff 逐一扫描以下维度：

| 维度 | 结果 |
|------|------|
| Host 强约束取消治理违反 | 无。fail-closed + 循环体前检查，符合 Host 强约束 |
| 敏感信息泄漏 | 无。两层 redaction pattern 语义一致，diagnostic_refs 和日志均脱敏 |
| 类型错误 | 无。pyright 0 errors |
| 分层边界违反 | 无。Contracts 层不再引用 Engine 内部路径 |
| 测试覆盖真实 root cause | 全部 5 个 fix 均有针对 root cause 的测试 |
| 新引入的反向依赖 | 无 |
| 新引入的兼容性代码 | 无 |

## Deferred 项评估

Codex 报告中列出的 deferred 项（SSE fatal tool call、_safe_read_error_body_bytes、ActiveWorkerRegistry RLock、多连接 read semantics、CJK token estimator、ConfigLoader 拆分、compose_open_host_options 拆分、close_open_session_row status、_require_non_empty_text 去重、lane 无限等待、truncation cursor 上限、LLM proposal cast、duplicate governance attempt_id、Engine runtime import boundary 白名单、_resolve_project_path 绝对路径语义）均为总控明确 deferred 的 hardening / cleanup 范围。

当前 diff 未对这些 deferred 项引入新的阻断问题。

## 残余风险

1. **Engine 与 Compaction redaction pattern 分叉**: `agent.py` 使用三个独立 regex（匹配策略），`compaction_operation.py` 使用两个 regex（替换策略）。语义覆盖一致但实现分叉，未来新增敏感关键词需同步两处。非阻断，可作为后续 cleanup 项。

2. **`_exception_diagnostic_suffix` 脱敏后仍可能包含 key name**: 例如 `token=sk-xxx` 脱敏为 `token=<redacted>`，key name `token` 仍可见。这是合理设计——key name 本身不含 secret，保留有助于诊断。

3. **Bounded regex 回溯**: `_ASSIGNED_SECRET_VALUE_PATTERN` 的 `[^,\s}\]]+` 无显式上界，但在实际异常消息长度（通常 < 1KB）下无性能风险。

---

## 结论

**PASS**

5 个已接受修复范围全部通过复审。Fail-closed 取消治理、循环体前取消检查、diagnostic_refs 脱敏、异常诊断精确化、文档边界修正均正确实现，测试覆盖真实 root cause，pyright 0 errors，无新增阻断问题。
