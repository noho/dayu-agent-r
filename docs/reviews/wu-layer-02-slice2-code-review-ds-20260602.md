# WU-LAYER-02 Slice 2 Code Review — DS

## Scope

- Work unit: WU-LAYER-02 Shared Runtime Helper Consolidation.
- Slice: Slice 2 Engine Agent Exception Diagnostic Migration (post-blocker fix).
- Design source: `docs/host/design.md` §3.
- Plan source: `docs/host/wu-layer-02-shared-runtime-helper-consolidation-plan.md`.
- Blocker source: `docs/reviews/wu-layer-02-slice2-blocker-controller-adjudication-20260602.md`.
- Implementation report: `docs/reviews/wu-layer-02-slice2-implementation-report-20260602.md`.

## Verification Commands

```bash
source .venv/bin/activate && pytest -q tests/runtime/test_diagnostic_text.py tests/engine/test_agent_phase2.py
# → 112 passed in 0.15s

source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# → 0 errors, 0 warnings, 0 informations
```

## Findings

### 1. Runtime Layer Boundary — PASS

`dayu/runtime/diagnostic_text.py` 只 import `re` 与 `typing.Final`（均为标准库）。未 import `dayu.engine`、`dayu.host`、`dayu.service`、`dayu.ui`、`dayu.fins` 或任何上层模块。

模块职责保持 text-primitive-only：不知道 Exception、Run、Attempt、Host diagnostic ref、Engine event、provider payload 或业务字段。

### 2. Blocker Adjudication Compliance — PASS

逐一验证 blocker 裁决中的每项要求：

| 要求 | 状态 | 证据 |
|---|---|---|
| `api_key=;` / `token=;` 保持敏感 | PASS | `_ASSIGNED_SECRET_VALUE_PATTERN` value char class `[^,\s}\]]+` 不排除 `;`；`test_contains_sensitive_diagnostic_value_keeps_semicolon_value_start` (L70-92) 覆盖 `api_key=;`、`api-key:;`、`apikey=;`、`authorization=;`、`password=;`、`secret=;`、`token=;` |
| `api_key=}` / `api_key=]` / `token=}` / `token=]` 非敏感 | PASS | `}` 和 `]` 被 `[^,\s}\]]+` 排除；`test_contains_sensitive_diagnostic_value_ignores_closing_punctuation_start` (L95-116) 覆盖全部六个组合 |
| `Bearer }` / `Bearer ]` 非敏感 | PASS | `_BEARER_SECRET_PATTERN` token char class `[A-Za-z0-9._~+/=-]+` 不包含 `}` / `]`；同上测试覆盖 |
| `api key <plain-word>` broad match 保留 | PASS | `(?:api\s+key\|apikey)\b\s+` 交替分支覆盖空格分隔 api key；`test_contains_sensitive_diagnostic_value_detects_value_patterns` (L17-45) 覆盖 `api key sk-live-secret` |
| JWT/header false-positive guard 保留 | PASS | `authorization` / `password` / `secret` / `token` 只在后接 `[:=]` 时才命中；`test_contains_sensitive_diagnostic_value_ignores_plain_diagnostics` (L48-67) 覆盖 `JWT token has expired`、`Content-Type header is invalid`、`authorization header is missing`、`token refresh failed before assignment` |

### 3. Redaction / Contains 同源 — PASS

`contains_sensitive_diagnostic_value` 与 `redact_sensitive_diagnostic_values` 共享同一组模块级编译 regex（`_BEARER_SECRET_PATTERN`、`_ASSIGNED_SECRET_VALUE_PATTERN`），不存在分叉。同源性证据：

- `contains_sensitive_diagnostic_value` (L44-47): `_BEARER_SECRET_PATTERN.search(...) or _ASSIGNED_SECRET_VALUE_PATTERN.search(...)`
- `redact_sensitive_diagnostic_values` (L65-72): `_BEARER_SECRET_PATTERN.sub(...)` 然后 `_ASSIGNED_SECRET_VALUE_PATTERN.sub(...)`

分号 value start 不泄漏：`redact_sensitive_diagnostic_values("runtime failed api_key=; token=;", ...)` → `"runtime failed api_key=<redacted> token=<redacted>"`；`;` 被 lambda `match.group(1) + redaction_marker` 替换，不会残留在结果中。测试 `test_redact_sensitive_diagnostic_values_redacts_semicolon_value_start` (L119-133) 直接断言 `"api_key=;" not in redacted` 且 `"token=;" not in redacted`。

右括号 start 不误改：`api_key=}` / `token=]` / `Bearer ]` 等不命中 regex，redaction 原样返回。测试 `test_redact_sensitive_diagnostic_values_preserves_closing_punctuation_start` (L136-162) 断言 `redacted == message`。

### 4. Engine Migration Completeness — PASS

`dayu/engine/agent.py` 变更：

- **删除**：`import re`、`_BEARER_SECRET_PATTERN`、`_API_KEY_VALUE_PATTERN`、`_ASSIGNED_SECRET_VALUE_PATTERN`、`_contains_sensitive_exception_value`。全部清理干净，无残留引用。
- **新增 import**：`contains_sensitive_diagnostic_value`、`truncate_diagnostic_text` from `dayu.runtime.diagnostic_text`。
- **保留 Engine policy 常量**：`_EXCEPTION_MESSAGE_REDACTED = "exception message redacted"`、`_EXCEPTION_MESSAGE_MAX_LENGTH = 240`、`_EXCEPTION_MESSAGE_TRUNCATED_SUFFIX = "... [truncated]"`。这些是 Engine display/diagnostic policy，非 runtime truth。

`_exception_diagnostic_message` 策略保持：
- 空消息 → 只返回异常类型名。
- 敏感命中 → 整条 `"{exc_type}: exception message redacted"`（Host-style value redaction 未引入 Engine）。
- 普通消息 → runtime `truncate_diagnostic_text` 截断，使用 Engine suffix。

`_safe_log_message` 策略保持：
- 空白消息 → `"exception message redacted"`。
- 敏感命中 → `"exception message redacted"`（整条替换）。
- 普通消息 → runtime `truncate_diagnostic_text` 截断，使用 Engine suffix。

两个调用点（L1121: `_exception_diagnostic_message(exc)`、L1264: `_safe_log_message(data.message)`）参数类型与返回类型均兼容迁移后签名。

### 5. Agent State Machine / Public Contract — PASS

本次变更仅触及两个私有辅助函数的内部实现和 import 清单，未修改：

- `_AsyncAgent` 状态机逻辑。
- `RunnerEvent` 类型定义或字段。
- `RunFailedData` 字段（`error_code`、`message`、`provider_request_id`、`recoverable` 均未变）。
- `EngineEvent` / `EngineEventType` 枚举。
- metadata 结构。
- 任何 public class/function 签名、参数或返回值。

`RunFailedData.message` 的文本格式（`"{exc_type}: {safe_message}"`）、redaction marker（`"exception message redacted"`）和 truncation suffix（`"... [truncated]"`）均保持不变。

### 6. Test Coverage — PASS (with observation)

Runtime 直接测试 (`test_diagnostic_text.py`): 22 个测试函数覆盖 detection/redaction/truncation 全部 primitive，包括 punctuation boundary matrix、redaction marker literal treatment、idempotency、empty string paths、fail-fast validation、redact+truncate 组合路径。

Engine 行为测试 (`test_agent_phase2.py`): 新增 7 个测试函数覆盖：
- `_exception_diagnostic_message` semicolon value start redaction (L874-895)。
- `_exception_diagnostic_message` closing punctuation preserved (L898-923)。
- `_safe_log_message` blank/whitespace redaction (L926-938)。
- `_safe_log_message` sensitive whole-message redaction (L941-963)。
- `_safe_log_message` long message truncation (L966-976)。
- `_safe_log_message` false positive guards (L979-998)。

既有 Engine 测试全部继续通过，迁移前后语义一致。

**Minor observation (non-blocking):**

- `_safe_log_message` 在 `len(message) == _EXCEPTION_MESSAGE_MAX_LENGTH`（精确边界值 240）时没有直接单测。当前行为依赖 `truncate_diagnostic_text` 的 exact-boundary no-op 语义（该语义在 runtime 测试 `test_truncate_diagnostic_text_exact_boundary_returns_original` L291-306 中已直接覆盖，包括 `is` identity 断言），因此不存在回归风险。但 Engine 调用方策略的边界行为缺少独立断言，后续若 runtime 变更边界语义，Engine 测试不会直接报警。建议将来在 Engine 测试中增加 `len(message) == 240` 的精确边界 case。

### 7. AGENTS.md Compliance — PASS

逐项检查：

| 约束 | 状态 | 说明 |
|---|---|---|
| 禁止 `Any`/`object`/无类型签名 | PASS | 全部函数有完整类型标注 |
| 中文 docstring | PASS | 所有函数/类/模块有中文 docstring，含 param/returns/raises |
| 禁止 `hasattr`/`getattr` | PASS | 未使用 |
| 魔法字符串 | PASS | 常量均为模块级 `Final`；regex 在模块级编译 |
| 禁止兼容性 wrapper/re-export | PASS | 无 |
| 禁止反向依赖 | PASS | `diagnostic_text.py` 只依赖 `re` 和 `typing.Final` |
| 禁止胶水 seam/lazy import | PASS | 无 lazy import |
| README 同步触发 | PASS | 正确判断无需更新：Engine public contract 不变；runtime capability 已在 Slice 1 文档化 |
| 禁止显式参数塞 extra payload | PASS | 无 |

### 8. Changed Files Audit — PASS

实际变更文件（5 个）均在 allowed files 范围内：
- `dayu/runtime/diagnostic_text.py` — regex char class 精修（2 行改动）。
- `dayu/engine/agent.py` — 删除私有 regex/helper，切换 runtime 调用（约 30 行净删除）。
- `tests/runtime/test_diagnostic_text.py` — 新增 punctuation boundary 测试（+96 行）。
- `tests/engine/test_agent_phase2.py` — 新增 `_safe_log_message` 直接测试 + semicolon/closing-punctuation 覆盖（+130 行）。
- `docs/host/host-core-followup-implementation-control.md` — status 更新（文档性变更）。

未修改 `dayu/runtime/__init__.py`（Slice 1 已完成）、未修改任何 README、未修改 Host 文件。

## Summary

**Overall: PASS.** 全部 8 个审查维度均通过。blocker 裁决中的六项 punctuation boundary 约束已全部满足且有直接测试覆盖。Engine 私有 secret regex/helper 已完全删除，运行时 primitive 调用语义正确保持 Engine whole-message redaction 策略。Agent 状态机、RunnerEvent、RunFailedData、public contract 均未改变。112 测试通过，pyright 零错误。

## Residual Risks

1. `_safe_log_message` 精确边界值（len == 240）缺少 Engine 层直接测试，当前依赖 runtime 边界测试间接保证。风险低，但不为零。
2. `apikey:value`（冒号分隔无空格）被第一交替分支 `api[_-]?key`（`[_-]?` 可选）覆盖，行为与旧 Engine regex 一致；但 runtime regex 的交替结构比旧 Engine 单独 `_API_KEY_VALUE_PATTERN` 更紧凑，若未来有人在不解整体结构的情况下只修改部分交替，有引入分叉的微风险。当前测试矩阵已充分锁定行为。
3. Host compaction migration (Slice 3) 尚未执行，跨层最终 owner 边界需在 aggregate review 时再确认。
