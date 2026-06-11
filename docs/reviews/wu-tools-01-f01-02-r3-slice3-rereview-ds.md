# WU-TOOLS-01-F01-02-R3 Slice 3 Fix Re-Review — DS

## 1. Verdict

**PASS** — S3-CR-01 fix 正确且完整。7/7 检查点通过，无 residual finding。

## 2. Review Scope

依 Controller adjudication 要求，仅审查 S3-CR-01 fix 与回归面：

| 文件 | 角色 |
|---|---|
| `dayu/fins/tools/fins_tools.py` | `_cancelled_from_token` fix |
| `dayu/fins/tools/read_runtime_helpers.py` | `raise_fins_cancelled` fix |
| `tests/fins/test_fins_storage_provider.py` | 新 focused test + 辅助函数 |
| `docs/reviews/wu-tools-01-f01-02-r3-slice3-fix-codex.md` | Fix 记录 |

对照真源：Controller adjudication S3-CR-01 Required fix 清单。

## 3. 检查点逐项验证

### 3.1 `_cancelled_from_token` 不再读取/拼接 `cancellation_token.cancel_reason()` 到 LLM-facing message

**结论：PASS**

证据：
- `fins_tools.py:925`: `del cancellation_token` — 函数体不读取 token 任何属性。
- `fins_tools.py:928`: `message="财报读取工具调用已被取消。"` — 使用固定业务可读消息，无字符串拼接。
- `fins_tools.py:926-932`: 仍通过 `host_cancelled_outcome(...)` 返回，`reason` 保持 `host_cancelled`。

### 3.2 `raise_fins_cancelled` 不再读取/拼接 `cancellation_token.cancel_reason()` 到 `FinsReadCancelledError.message`

**结论：PASS**

证据：
- `read_runtime_helpers.py:334`: `del cancellation_token` — 函数体不读取 token 任何属性。
- `read_runtime_helpers.py:335-338`: `raise FinsReadCancelledError(message=message, hint="当前工具调用已停止；等待新的用户指令或后续调度。")` — message 仅使用调用方提供的业务可读说明，hint 为固定字符串。
- 参数签名 `message: str` — 要求调用方显式提供业务可读取消说明，不做隐式 token 原因拼接。

### 3.3 `ToolCancelledOutcome.reason` 仍为 `host_cancelled`

**结论：PASS**

证据：
- `fins_tools.py:926`: `host_cancelled_outcome(...)` — 使用项目标准 helper，`reason` 固定为 `TOOL_CANCELLED_REASON_HOST_CANCELLED`。
- `test_fins_storage_provider.py:1393`: `assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED` — 所有取消测试的共享断言不变。

### 3.4 新 focused test 同时覆盖 pre-cancel 和深层搜索取消，并验证 message/hint 不含 Host 治理标识

**结论：PASS**

新测试 `test_cancelled_read_outcomes_hide_host_governance_reason` (line 787)：

**Pre-cancel 路径 (lines 797-808):**
- 构造 `_ManualCancellationToken(cancel_reason=_HOST_GOVERNANCE_CANCEL_REASON)`，其中含 `run_id=run-secret session_id=session-secret correlation_id=correlation-secret payload_ref=payload-secret digest=sha256-secret cancellation_token=token-secret`
- 立即 `cancel()`，调用 `list_documents`，断言 pre-cancel outcome 不含治理标识。

**深层搜索取消路径 (lines 810-831):**
- 同样构造含治理标识 reason 的 `_ManualCancellationToken`
- 通过 `_SearchCancellingProcessor` 在搜索循环内触发取消
- 调用 `search_document`，断言深层取消 outcome 不含治理标识
- `assert processor.search_calls == ["annual"]` — 确认搜索在首个候选项后正确停止

**治理标识检查覆盖度 (lines 105-118):**
`_HOST_GOVERNANCE_FORBIDDEN_TERMS` 覆盖 12 个禁止术语：
```
"run_id", "session_id", "correlation_id", "payload_ref", "digest",
"cancellation_token", "run-secret", "session-secret", "correlation-secret",
"payload-secret", "sha256-secret", "token-secret"
```
同时覆盖治理字段名和具体取值，防止通过字段名或取值任一形式泄漏。

**回归防护：**
`_assert_host_cancelled_outcome` (line 1375) 现在在所有取消断言中调用 `_assert_host_governance_terms_hidden` (line 1397)。这意味着原有的 6 个取消测试也共享此治理标识检查，即使它们的 token 使用默认 `cancel_reason="test cancellation"`——若未来有人意外将 `cancel_reason()` 重新拼接到 message/hint，所有测试会集体失败。

### 3.5 没有扩大到 Doc/Web 或其它非允许文件

**结论：PASS**

Fix codex 声明变更范围仅限 controller 指定的三个文件：
- `dayu/fins/tools/fins_tools.py`
- `dayu/fins/tools/read_runtime_helpers.py`
- `tests/fins/test_fins_storage_provider.py`

验证：当前 working tree 的 modified files（`dayu/fins/tools/fins_tools.py`, `dayu/fins/tools/provider.py`, `dayu/fins/tools/read_runtime.py`, `dayu/fins/tools/read_runtime_helpers.py`, `dayu/fins/tools/search_engine.py`, `tests/fins/test_fins_storage_provider.py`）均在 controller adjudication 的原始 review scope 内。S3-CR-01 fix 本身仅触及 `fins_tools.py`、`read_runtime_helpers.py`、`test_fins_storage_provider.py`，符合 fix scope 约束。

### 3.6 无新 legacy adapter 命中

**结论：PASS**

Fix codex 验证：
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools|ToolBusinessError\(.*tool_cancelled" dayu/fins/tools tests/fins/test_fins_storage_provider.py` — no matches
- 已有 `test_fins_read_tools_do_not_import_retired_adapter` (line 659) 持续守卫

S3-CR-01 fix 的变更本身不涉及任何 import 语句修改，不可能引入新 legacy 依赖。

### 3.7 无 pyright/test regression

**结论：PASS**

Fix codex 验证：
- `pytest tests/fins/test_fins_storage_provider.py` — 22 passed（fix 前 21，新 focused test +1）
- `pytest tests/fins/test_fins_ingestion_tools.py -k cancellation` — 1 passed
- `pyright` — 0 errors, 0 warnings
- `git diff --check` — passed

## 4. 补充验证

### 4.1 `_ManualCancellationToken` 注入能力

`_ManualCancellationToken.__init__` (line 155) 支持 `cancel_reason` 关键字参数，默认值为 `"test cancellation"`。新测试利用此能力注入 `_HOST_GOVERNANCE_CANCEL_REASON`，不影响已有测试——已有测试使用默认值，行为不变。设计合理。

### 4.2 防御深度

Fix 采用了双重防御：
1. **生产代码层**：`_cancelled_from_token` 和 `raise_fins_cancelled` 均不再访问 `cancel_reason()`，从源头消除泄漏可能。
2. **测试回归层**：`_assert_host_cancelled_outcome` 在所有取消测试中强制检查 `_assert_host_governance_terms_hidden`，即使未来有人误改生产代码也会被立即捕获。

`del cancellation_token` 写法在语义上明确表达了"此函数不消费 token 内容"的意图，比仅不使用更可读。

## 5. 结论

| 检查点 | 结论 |
|---|---|
| `_cancelled_from_token` 不再嵌入 `cancel_reason()` | PASS |
| `raise_fins_cancelled` 不再嵌入 `cancel_reason()` | PASS |
| `ToolCancelledOutcome.reason` 保持 `host_cancelled` | PASS |
| 新 focused test 覆盖 pre-cancel + 深层取消 + governance terms | PASS |
| 无 Doc/Web 范围扩大 | PASS |
| 无新 legacy adapter 命中 | PASS |
| 无 pyright/test regression | PASS |
| **总体** | **PASS** |

S3-CR-01 fix 完整且正确，无 residual finding。

---

*Reviewer: DS (Claude Fable 5)*
*Date: 2026-06-10*
*Artifact: docs/reviews/wu-tools-01-f01-02-r3-slice3-rereview-ds.md*
