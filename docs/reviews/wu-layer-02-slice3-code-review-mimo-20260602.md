# WU-LAYER-02 Slice 3 Code Review

- Reviewer: MiMo
- Date: 2026-06-02
- Target: Host Compaction Exception Diagnostic Migration
- Scope: `dayu/host/compaction_operation.py`, `tests/host/test_compaction_operation.py`

## Findings

### F-01 [PASS] Host 私有 secret regex 已删除，改用 runtime primitive

`_BEARER_SECRET_PATTERN` 与 `_ASSIGNMENT_SECRET_PATTERN` 已从 `compaction_operation.py` 删除。`_safe_exception_message` 改为调用 `redact_sensitive_diagnostic_values` 和 `truncate_diagnostic_text`。import 路径 `dayu.runtime.diagnostic_text` 正确，不违反 runtime import boundary。

### F-02 [PASS] Host compaction owner 未下沉

以下 Host-owned 组件均原样保留：

- `_ERROR_CODE_PATTERN`（行 51）与 `_exception_error_code`：Host compaction `error_code=` 提取。
- `_exception_diagnostic_suffix`（行 651–661）：异常类型前缀与消息拼接规则。
- `_REDACTED_SECRET`、`_MAX_SAFE_EXCEPTION_MESSAGE_CHARS`、`_TRUNCATED_SUFFIX`：Host display policy 常量。
- `CompactionAttemptRejected` dataclass、`diagnostic_refs` 结构、failure category、repair budget、quality check、multi-pass merge 与 Context Governance 均未改动。

### F-03 [PASS] `_safe_exception_message` 保持 Host 策略

重构后的逻辑完整覆盖三条路径：

1. `exc is None` → `"none"`
2. `str(exc).strip() == ""` → `exc.__class__.__name__`
3. 非空消息 → `redact_sensitive_diagnostic_values(message, redaction_marker=_REDACTED_SECRET)` → `truncate_diagnostic_text(redacted, max_chars=240, truncated_suffix="...")`

truncation 使用 runtime primitive 的 `max_chars - len(suffix)` 语义，与原实现 `body_length = _MAX_SAFE_EXCEPTION_MESSAGE_CHARS - len(_TRUNCATED_SUFFIX)` 等价。

### F-04 [PASS] 测试覆盖完整

新增测试矩阵覆盖：

| 测试 | 覆盖目标 |
|---|---|
| `test_run_compaction_operation_redacts_exception_diagnostic_refs` | 9 种 secret value 全部不出现在 diagnostic ref |
| `test_run_compaction_operation_redacts_each_value_bearing_secret_pattern`（参数化 × 9） | 每类 value-bearing secret 单独验证局部 redaction 和字段上下文保留 |
| `test_run_compaction_operation_keeps_plain_token_expired_context` | `JWT token has expired` 不误脱敏 |
| `test_exception_diagnostic_suffix_uses_exception_type_for_empty_message` | 空异常消息 → suffix 只输出异常类名 |

`_SensitiveFailingCompactor` 扩展为可配置异常消息，`_EmptyMessageFailingCompactor` 新增覆盖空消息路径。所有测试 helper 和测试函数均有完整中文 docstring。

### F-05 [PASS] 行为变更风险评估

- **Bearer regex 收窄**：新 runtime regex 使用 `\b` word-boundary，比旧 Host regex（无 `\b`）更严格。这是 security hardening，不影响正常 `Bearer <token>` 场景，减少误伤面。
- **新增 secret 形态覆盖**：`password=`、`api key` 空格写法、`apikey=`、`api-key:`、`api-key: ` 在旧 Host 实现中不被检测，迁移后获得 runtime 覆盖。这是 diagnostic-only security hardening，不改变 compaction 状态机。
- **Truncation 语义**：runtime `truncate_diagnostic_text` 对 `len(message) <= max_chars` 返回原字符串，与原实现 `len(redacted) <= _MAX_SAFE_EXCEPTION_MESSAGE_CHARS` 等价。
- **Diagnostic ref 文本**：`_exception_diagnostic_suffix` 未改动，ref 构造逻辑不变。
- **Retry/reject 语义**：未触及 `run_compaction_operation` 的 attempt 循环、repair 判断或 cancellation 逻辑。

### F-06 [PASS] 编码规范合规

- 无 `Any`、`object`、无类型签名。
- 所有函数/类有完整中文 docstring，含 `:param` / `:returns` / `:raises`。
- 无 `getattr` / `hasattr` 滥用。
- 常量使用模块级私有 `Final`（runtime）或纯大写下划线（Host），无魔法数字/字符串。
- 无兼容性 wrapper / facade / re-export。
- runtime `diagnostic_text.py` 只依赖标准库 `re` 和 `typing.Final`，不 import 上层。

### F-07 [PASS] README 同步决策正确

本 Slice 只将 Host 私有 regex 切换到已存在的 runtime primitive，未改变 Host public contract、状态机、配置入口或分层关系。按 README 触发规则，`dayu/host/README.md` 不需更新。Slice 1 已在 `dayu/README.md` 中记录 runtime capability。

## Verification Summary

```
source .venv/bin/activate && pytest -q tests/runtime/test_diagnostic_text.py tests/host/test_compaction_operation.py
# 93 passed in 0.41s

source .venv/bin/activate && python -m pyright dayu/host/compaction_operation.py tests/host/test_compaction_operation.py dayu/runtime/diagnostic_text.py
# 0 errors, 0 warnings, 0 informations
```

## Residual Risks

1. **Runtime regex 演进依赖**：未来新增 secret 形态应优先扩展 `dayu.runtime.diagnostic_text` 及其直接测试，Host 通过同一 primitive 继承能力。当前 regex 覆盖 Bearer、api key 全形态、authorization、password、secret、token 赋值，短期无盲区。
2. **Provider error payload 审计**：Diagnostic ref 承载截断后的异常消息上下文，测试覆盖 value-bearing secret 与普通 token 句子，但不替代更广泛的 provider error payload 审计。
3. **Bearer `\b` 边界**：runtime regex 的 `\b` word-boundary 比旧 Host regex 更严格。若未来出现 `Bearer` 前紧邻非单词字符的 edge case（如 URL path segment），需在 runtime 层评估是否需要额外 pattern。当前所有已知 provider 错误格式不命中此 edge case。

## Conclusion

**PASS** — Slice 3 实现与 plan 完全一致。Host 私有 secret regex 已删除，改用 runtime primitive；Host compaction owner（error_code=、diagnostic suffix、state machine）未下沉；测试覆盖完整；无行为回归风险；编码规范合规。
