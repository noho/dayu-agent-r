# WU-LAYER-02 Slice 1 Code Review — MiMo

## Review Scope

- `dayu/runtime/diagnostic_text.py` (新增)
- `tests/runtime/test_diagnostic_text.py` (新增)
- `dayu/runtime/__init__.py` (docstring 更新)
- `tests/runtime/test_weak_typing_guard.py` (coverage set 更新)
- `dayu/README.md` (能力清单更新)
- `tests/README.md` (分层说明更新)
- `docs/host/host-core-followup-implementation-control.md` (状态更新，仅审阅一致性)

设计真源: `docs/host/design.md`
计划文档: `docs/host/wu-layer-02-shared-runtime-helper-consolidation-plan.md`
实现报告: `docs/reviews/wu-layer-02-slice1-implementation-report-20260602.md`

## Findings

### F-01 — Regex value 终止字符与 Engine/Host 现有语义不一致

**Severity: Low**

Runtime `_ASSIGNED_SECRET_VALUE_PATTERN` 使用 `[^\s,;]+` 作为 value 终止字符类，而 Engine `_API_KEY_VALUE_PATTERN` / `_ASSIGNED_SECRET_VALUE_PATTERN` 和 Host `_ASSIGNMENT_SECRET_PATTERN` 使用 `[^,\s}\]]+`。

差异:
- Runtime **不**将 `}` 和 `]` 作为 value 终止符: `api_key=secret}` 中 runtime 捕获 `secret}`，Engine/Host 只捕获 `secret`。
- Runtime 将 `;` 作为终止符: `api_key=secret;other` 中 runtime 只捕获 `secret`，Engine/Host 捕获 `secret;other`。

当前 Slice 1 是独立 runtime primitive，无调用方依赖旧行为，因此不影响 correctness。但 Slice 2 (Engine migration) 和 Slice 3 (Host migration) 时，如果直接替换 regex 而不调整 value 终止字符类，会导致 `RunFailedData.message` 和 Host compaction diagnostic ref 在含 `}` / `]` / `;` 的 edge case 上产生不同 redaction 行为。

**建议**: migration slices review 时重点检查此差异。可选修复: runtime regex 改为 `[^,\s}\];]+` 以同时兼容两套终止符；或在 migration test 矩阵中显式覆盖含 `}` / `]` 的 diagnostic text。当前 slice 不需要修改。

### F-02 — 无阻塞 finding

以下审查点均通过:

- **层中立**: `diagnostic_text.py` 只 import `re` 和 `typing.Final`，不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- **包根不 re-export**: `__init__.py` 的 `__all__` 保持空列表；diagnostic_text 模块符号不可从 `dayu.runtime` 包根直接访问。
- **API 与计划一致**: 三个朴素函数 `contains_sensitive_diagnostic_value` / `redact_sensitive_diagnostic_values` / `truncate_diagnostic_text`，签名与计划 §7 完全匹配。
- **redaction_marker 字面替换**: 使用 `lambda` callable replacement 传给 `re.sub()`，marker 中的 `\1`、`\g<name>`、反斜杠不会被 regex replacement 解释。测试 `test_redaction_marker_is_used_as_literal_replacement_text` 锁定此语义。
- **Bearer word-boundary**: 使用 `\b` word-boundary，与 Engine 现有行为对齐，收窄 Host 现有无 `\b` 的误伤面。
- **authorization / password / secret / token 只在 `:` / `=` 后命中**: 普通 `JWT token has expired`、`Content-Type header is invalid`、`token refresh failed before assignment` 不误伤。
- **api key 空格写法覆盖**: `api key <value>` 和 `API key <value>` 被检测。
- **api_key / api-key / apikey 覆盖**: 下划线、短横线和无分隔符写法均被检测。
- **Bearer 大小写不敏感**: `re.IGNORECASE` 确保 `bearer` / `BEARER` 等变体被识别；脱敏后统一输出 `Bearer ` 前缀。
- **truncate_diagnostic_text no-op 语义**: `len(message) <= max_chars` 原样返回 `message`；空字符串是 no-op。测试 `test_truncate_diagnostic_text_short_message_returns_original` 断言 `truncated is message`（同一对象引用）。
- **exact-boundary**: `len(message) == max_chars` 原样返回。测试直接断言。
- **超限截断**: 返回 `message[:max_chars - len(suffix)] + suffix`，长度精确等于 `max_chars`。
- **非法参数**: `max_chars <= 0` 和 `len(suffix) >= max_chars` fail fast `ValueError`。
- **幂等性**: 无空白 marker 的 redaction 重复执行不继续改变结果。
- **redact+truncate 组合**: 先脱敏再截断不泄漏原值。
- **中文 docstring**: 所有函数和模块有完整中文 docstring，包含参数、返回值、异常。
- **类型签名**: 无 `Any`、`object`、无类型参数或无类型返回值。
- **无 getattr / hasattr / lazy import / glue seam / 兼容 wrapper**。
- **模块级私有 Final 常量**: regex 在模块级编译，错误消息常量为 `Final[str]`。
- **弱类型守卫**: `test_weak_typing_guard.py` 已将 `diagnostic_text.py` 加入 `_PHASE12_RUNTIME_HELPERS` 集合。
- **README 更新**: `dayu/README.md` 在 `dayu.runtime` 能力清单中补充 diagnostic_text 说明；`tests/README.md` 在 `tests/runtime/` 分层说明中补充 diagnostic text 测试事实。两处均只记录当前能力，不写实现细节或未来计划。

## Validation

| 验证项 | 结果 |
|---|---|
| `pytest -q tests/runtime/test_diagnostic_text.py tests/runtime/test_weak_typing_guard.py tests/host/test_import_boundary.py` | 47 passed |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| Runtime import boundary (AST check) | PASS — diagnostic_text.py 不 import 上层 |
| Weak type / hasattr / getattr scan | PASS — 无违规 |
| Runtime `__init__` re-export check | PASS — `__all__` 为空，无 diagnostic_text 符号泄漏 |

## Open Questions

1. **F-01 需要在 migration slices 裁决**: runtime regex `[^\s,;]+` 与 Engine/Host `[^,\s}\]]+` 的 value 终止字符差异是否需要在 Slice 2/3 migration 前统一？若 migration 后 Engine/Host 的 diagnostic text 在含 `}` / `]` 的 edge case 上行为变化可接受（因为是 diagnostic-only），则当前实现可保留；否则 runtime regex 应扩展终止字符类。此决策属于 migration slice scope，不阻塞 Slice 1。

## Verdict

**PASS** — 无阻塞 finding。F-01 为 low severity observation，记录待 migration slice 处理。

实现与计划 §7 API 完全一致，层中立边界严格，类型签名完备，测试覆盖充分（detection / false-positive guard / redaction / literal marker / truncate semantics / idempotency / combination path / illegal arguments），README 更新在职责范围内且只记录当前事实。
