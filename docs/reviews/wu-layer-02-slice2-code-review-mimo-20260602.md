# WU-LAYER-02 Slice 2 Code Review

**审查人**：MiMo  
**审查日期**：2026-06-02  
**审查范围**：WU-LAYER-02 Slice 2 Engine Agent Exception Diagnostic Migration

---

## 审查结论

**PASS**

本次变更符合设计文档、blocker 裁决和实现报告的要求，无阻塞性问题。

---

## Findings

无 findings。

---

## 审查详情

### 1. dayu/runtime/diagnostic_text.py 层中立边界检查

**结论**：✅ 符合要求

- 模块只依赖 `re` 标准库，未 import Host/Engine/Service/UI/Fins
- 边界符合 blocker 裁决：
  - `api_key=;` / `token=;` sensitive：分号不在 `[^,\s}\]]+` 排除列表中，会被 pattern 匹配
  - `api_key=}` / `api_key=]` / `token=}` / `token=]` / `Bearer }` / `Bearer ]` non-sensitive：右括号在排除列表中，不会被匹配
  - `api key <plain-word>` broad match 保留：pattern 支持 `api key`、`api_key`、`api-key`、`apikey` 多种写法
  - JWT/header false-positive guard 保留：普通 "JWT token has expired" 等诊断不会被误判

### 2. redaction 与 contains 同源性检查

**结论**：✅ 符合要求

- `contains_sensitive_diagnostic_value` 和 `redact_sensitive_diagnostic_values` 使用相同的 `_BEARER_SECRET_PATTERN` 和 `_ASSIGNED_SECRET_VALUE_PATTERN`
- `redact_sensitive_diagnostic_values` 不会泄漏分号 value start：pattern 匹配分号后会替换整个 value
- 不会误改 closing punctuation start：右括号不在匹配范围内，不会被替换

### 3. dayu/engine/agent.py Engine 私有 secret regex/helper 清理检查

**结论**：✅ 符合要求

已删除：
- `_BEARER_SECRET_PATTERN`
- `_API_KEY_VALUE_PATTERN`
- `_ASSIGNED_SECRET_VALUE_PATTERN`
- `_contains_sensitive_exception_value` 函数
- `import re`

已改用：
- `dayu.runtime.diagnostic_text.contains_sensitive_diagnostic_value`
- `dayu.runtime.diagnostic_text.truncate_diagnostic_text`

已保留：
- Engine 整条脱敏策略：`_EXCEPTION_MESSAGE_REDACTED = "exception message redacted"`
- 空白 log redaction：`_safe_log_message` 对空白消息使用固定脱敏文本
- Engine truncation suffix/max length：`_EXCEPTION_MESSAGE_MAX_LENGTH = 240`、`_EXCEPTION_MESSAGE_TRUNCATED_SUFFIX = "... [truncated]"`

### 4. Agent 状态机、RunnerEvent、RunFailedData 字段、metadata、public contract 检查

**结论**：✅ 无变更

- Agent 状态机未改变
- RunnerEvent 字段未改变
- RunFailedData 字段未改变
- metadata 语义未改变
- public contract 未改变

### 5. 测试覆盖检查

**结论**：✅ 覆盖充分

**tests/runtime/test_diagnostic_text.py** 新增测试：
- `test_contains_sensitive_diagnostic_value_keeps_semicolon_value_start`：覆盖分号 value start 敏感检测
- `test_contains_sensitive_diagnostic_value_ignores_closing_punctuation_start`：覆盖右括号类 value start 非敏感检测
- `test_redact_sensitive_diagnostic_values_redacts_semicolon_value_start`：覆盖分号 value start 脱敏
- `test_redact_sensitive_diagnostic_values_preserves_closing_punctuation_start`：覆盖右括号类 value start 不被改写

**tests/engine/test_agent_phase2.py** 新增测试：
- `test_exception_diagnostic_message_redacts_semicolon_value_start`：覆盖 Engine 层分号 value start 脱敏
- `test_exception_diagnostic_message_preserves_closing_punctuation_start`：覆盖 Engine 层右括号类 value start 保留
- `test_safe_log_message_redacts_blank_or_whitespace`：覆盖空白消息脱敏
- `test_safe_log_message_redacts_sensitive_message_whole`：覆盖敏感消息整条替换
- `test_safe_log_message_truncates_ordinary_long_message`：覆盖普通长消息截断
- `test_safe_log_message_preserves_false_positive_guards`：覆盖非敏感普通诊断文本保留

无明显缺失测试。

### 6. AGENTS.md 合规检查

**结论**：✅ 符合要求

- 未使用 `Any`、`object`、无类型参数、无类型返回值
- 函数均提供完整中文 docstring
- 未使用 `getattr`/`hasattr`
- 无魔法数字、魔法字符串（常量定义合理）
- README 同步触发判断：`dayu/engine/README.md` 不需要更新（未改变公共接口）

---

## 验证命令摘要

```bash
# 运行目标测试
source .venv/bin/activate && pytest -q tests/runtime/test_diagnostic_text.py tests/engine/test_agent_phase2.py
# 结果：112 passed

# 运行 pyright 类型检查
source .venv/bin/activate && python -m pyright dayu/runtime/diagnostic_text.py dayu/engine/agent.py
# 结果：0 errors, 0 warnings, 0 informations
```

---

## Residual Risk

无明显 residual risk。

本次变更：
1. 将 Engine 私有的 secret regex/helper 迁移到 runtime 公共 primitive
2. 保持了 Engine 层的脱敏策略、截断策略和空白处理策略
3. 新增了 blocker 裁决要求的边界测试（分号 value start、closing punctuation start）
4. 没有改变任何公共接口或契约

变更范围清晰，测试覆盖充分，符合设计文档和 blocker 裁决要求。
