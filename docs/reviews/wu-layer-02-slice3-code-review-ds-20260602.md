# WU-LAYER-02 Slice 3 Code Review — DS

## Review metadata

- **Reviewer**: DS (DeepSeek)
- **Target**: WU-LAYER-02 Slice 3 — Host Compaction Exception Diagnostic Migration
- **Reviewed files**: `dayu/host/compaction_operation.py`, `tests/host/test_compaction_operation.py`
- **Date**: 2026-06-02
- **Review stance**: adversarial correctness/stability/maintainability review；不修改代码、不 commit、不 push

## 审查依据

- `docs/host/design.md` §3 dayu.runtime 分层边界
- `docs/host/wu-layer-02-shared-runtime-helper-consolidation-plan.md` Slice 3 精确变更清单
- `docs/reviews/wu-layer-02-slice3-implementation-report-20260602.md`
- 当前 `git diff` (branch: `refactor/host-layer-followup-wu-layer-01-02`)

## Verification Commands

```bash
# Slice 3 target tests
source .venv/bin/activate && pytest -q tests/runtime/test_diagnostic_text.py tests/host/test_compaction_operation.py
# Result: 93 passed in 0.38s

# Import boundary, weak typing guard, Engine regression
source .venv/bin/activate && pytest -q tests/host/test_import_boundary.py tests/runtime/test_weak_typing_guard.py tests/engine/test_agent_phase2.py
# Result: 75 passed in 1.28s

# Full pyright
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# Result: 0 errors, 0 warnings, 0 informations
```

## Findings

### F-01 (PASS) Host 私有 secret-value redaction regex 已删除

**Severity**: N/A（验证通过）

旧 `_BEARER_SECRET_PATTERN` 与 `_ASSIGNMENT_SECRET_PATTERN` 已从 `dayu/host/compaction_operation.py` 完全删除。`grep` 确认生产文件中无残留。

`_safe_exception_message` (L735-756) 已改为调用 runtime primitive:
```python
redacted = redact_sensitive_diagnostic_values(message, redaction_marker=_REDACTED_SECRET)
return truncate_diagnostic_text(redacted, max_chars=_MAX_SAFE_EXCEPTION_MESSAGE_CHARS, truncated_suffix=_TRUNCATED_SUFFIX)
```

Host 常量 (`_MAX_SAFE_EXCEPTION_MESSAGE_CHARS=240`, `_TRUNCATED_SUFFIX="..."`, `_REDACTED_SECRET="<redacted>"`) 正确保留为 Host display/diagnostic policy，未下沉到 runtime。

### F-02 (PASS) `_ERROR_CODE_PATTERN` 与 `_exception_error_code` 正确保留为 Host owner

**Severity**: N/A（验证通过）

`_ERROR_CODE_PATTERN` (L51) 与 `_exception_error_code` (L719-732) 完整保留，`re` 模块 import (L12) 仍仅用于 Host compaction 的 `error_code=` 提取。未迁移到 runtime。

### F-03 (PASS) `_safe_exception_message` 保持 Host 策略完整

**Severity**: N/A（验证通过）

三层策略完整保留:
- `exc is None` → `"none"` (L743-744)
- 空白异常消息 → 返回异常类名 (L745-747)
- 非空消息 → 先局部 value redaction → 再 Host max/suffix 截断 (L748-755)

未改变 failure category、repairable、attempt number、diagnostic_refs shape、quality check、multi-pass merge 或 Context Governance。

### F-04 (PASS) `_exception_diagnostic_suffix` 保持 Host owner 语义

**Severity**: N/A（验证通过）

函数 (L651-661) 保持原有异常类型前缀与消息拼接规则，未迁移到 runtime。空消息路径 (`message == exc.__class__.__name__`) 正确只返回类名，不拼接 `:<message>`。

### F-05 (PASS) `CompactionAttemptRejected` / `diagnostic_refs` 结构未变

**Severity**: N/A（验证通过）

Dataclass (L60-79) 字段完整保留：`attempt_number`, `failure_category`, `repairable`, `runner_attempt_summary_refs`, `diagnostic_refs`, `next_policy_decision`, `budget_after_attempted_compact`。diagnostic ref 格式 `"diagnostic:{failure_category}:{operation_ref}:{diagnostic_suffix}"` 未变。

### F-06 (PASS) 测试覆盖既有和新增 secret 形态

**Severity**: N/A（验证通过）

测试矩阵覆盖完整:

| 测试函数 | 覆盖场景 |
|---|---|
| `test_run_compaction_operation_redacts_exception_diagnostic_refs` | 9 种 secret value 组合，逐一断言不泄漏原文，断言 `<redacted>` 出现 |
| `test_run_compaction_operation_redacts_each_value_bearing_secret_pattern` | 参数化 9 种单独模式：Bearer, api_key=, token=, secret=, password=, api key <space>, apikey=, api-key:, api-key: <space> |
| `test_run_compaction_operation_keeps_plain_token_expired_context` | `JWT token has expired` 不误脱敏，`<redacted>` 不出现 |
| `test_exception_diagnostic_suffix_uses_exception_type_for_empty_message` | `RuntimeError()` 无参构造，空消息 suffix 只返回 `:RuntimeError`，不拼接 `:RuntimeError:` |

参数化测试为每类 value-bearing secret 单独验证了:
- `secret_value not in diagnostic_ref` (原文不泄漏)
- `redacted_fragment in diagnostic_ref` (保留字段上下文，如 `Bearer <redacted>`, `api_key=<redacted>`)
- `"<redacted>" in diagnostic_ref` (redaction marker 出现)

### F-07 (PASS) 无行为变更风险

**Severity**: N/A（验证通过）

逐项检查:

1. **diagnostic ref 文本**: 新增 `api key <value>`, `apikey=<value>`, `password=<value>`, `api-key:<value>`, `api-key: <value>` 的 secret 检测属于计划内的 security hardening，不改变 compaction 状态机。既有 diagnostic ref 格式不变。

2. **retry/reject 语义**: `_attempt_rejected`、`repairable`、`next_policy_decision` 均未碰触，`run_compaction_operation` 主循环逻辑 (L127-287) 完全未改。

3. **error_code= 提取**: `_exception_error_code` 完整保留，`_log_rejected_attempt` 仍调用它生成日志 error_code。

4. **truncation 边界**: 新旧语义等价。旧: `len(redacted) <= max_chars` no-op，超限取 `redacted[:max_chars - len(suffix)] + suffix`。新: `truncate_diagnostic_text` 内部逻辑一致，加上 fail-fast 前置校验 `max_chars > 0` 和 `len(suffix) < max_chars`。Host 传入的 `max_chars=240`, `suffix="..."` 满足校验条件。

5. **Host local redaction vs runtime regex**: Runtime regex 比旧 Host regex 更精确（加入 `\b` word-boundary guard），且扩展了安全覆盖范围。对已覆盖的所有模式无检测退化：
   - Bearer: 旧 `(?i)bearer\s+[A-Za-z0-9._~+/=-]+` → 新 `\bBearer\s+([A-Za-z0-9._~+/=-]+)` — 加入 word-boundary 收窄误伤面，正常 Bearer token 场景不受影响
   - api_key=/api-key=/authorization=/token=/secret= 赋值: 旧已覆盖，新继续覆盖
   - 已有覆盖面的 regex value-matching 字符类 `[A-Za-z0-9._~+/=-]+` (Bearer) 和 `[^,\s}\]]+` (assignment) 均保持一致

### F-08 (PASS) AGENTS.md 合规

**Severity**: N/A（验证通过）

- 生产文件 (`compaction_operation.py`): 模块/类/函数均有完整中文 docstring，含 `:param`/`:returns`/`:raises`
- 测试文件: 新增/修改的函数和测试均有中文 docstring，含 `:param`/`:returns`/`:raises`
- 无 `Any`/`object`/无类型签名 — grep 确认生产代码零命中
- 无 `hasattr`/`getattr` — grep 确认零命中
- 无兼容性 wrapper/facade/re-export
- 无魔法数字/魔法字符串 — 所有字面量均为模块级私有常量
- README 同步决策: 按 AGENTS.md 触发规则，本 Slice 只做内部 helper owner 收敛，Host public contract、状态机、配置入口、分层关系均未变，不需要更新 README — 决策正确

### F-09 (LOW) 空消息异常测试断言存在逻辑蕴含但无害

**Severity**: Low（不阻塞，不要求修复）

`test_exception_diagnostic_suffix_uses_exception_type_for_empty_message` (L636-652) 两个断言:
```python
assert diagnostic_ref.endswith(":RuntimeError")
assert ":RuntimeError:" not in diagnostic_ref
```

第二条断言在正常路径下完全被第一条蕴含（endswith `:RuntimeError` 意味着不可能以 `:RuntimeError:` 结尾）。仅当 diagnostic_ref 中出现两个 `RuntimeError` 片段且第一个后跟 `:` 时，第二条才有独立检查价值。考虑到当前实现只在 suffix 中放一次类名，实际路径下第二条不增加覆盖率。

**Why**: 不阻塞——即使冗余，断言明确表达了意图（防止格式错误产生 `:RuntimeError:` trailing colon），且不存在误报。

## Review Summary

| Category | Result |
|---|---|
| Host 私有 regex 删除 | PASS |
| error_code= 提取保留 | PASS |
| Host 策略保持 | PASS |
| diagnostic ref 结构不变 | PASS |
| 测试覆盖 | PASS — 93 tests, 9 parametrized secret patterns + JW token + empty message |
| 行为变更风险 | PASS — 无退化，security hardening only |
| AGENTS.md 合规 | PASS — 完整 docstring, 无 Any/object/hasattr/getattr, 无兼容 wrapper |
| pyright | PASS — 0 errors, 0 warnings |
| Import boundary | PASS — runtime 不 import Host/Engine/Service/UI/Fins |
| Cross-slice regression | PASS — Engine test_agent_phase2 75 passed |
| README sync | PASS — 正确判定无需更新 |

**Overall verdict: PASS — 0 blocking/high/medium findings, 1 low non-blocking note (F-09)**

## Residual Risks

1. **Diagnostic ref 仍承载截断后的异常消息上下文**: 当前测试覆盖 value-bearing secret 与普通 token 句子。更广泛的 provider error payload 审计（如 multi-line traceback、非标准异常消息格式）不在本 Slice 范围内，测试不替代完整的 secret 审计覆盖。

2. **Regex 扩展覆盖面的长尾验证**: 当前测试覆盖了 plan 明确列出的 9 种新增/既存 secret 模式。极边缘的 secret 文本变体（如带 Unicode 非标准分隔符、多行折叠 header）未被覆盖，属于 runtime primitive 的直接测试职责（已由 `test_diagnostic_text.py` 承担），不重复在本 Slice 测试中。

3. **Runtime regex 后续演进**: 若未来需要新增 secret 形态，应优先扩展 `dayu.runtime.diagnostic_text` 的 regex 和直接测试，Host 通过同一 primitive 继承能力。不要在 Host 层重新引入私有 secret regex。
