# WU-LAYER-02 Aggregate Deep Review — MiMo

## Review Scope

- Work unit: `WU-LAYER-02 Shared Runtime Helper Consolidation`
- Design source: `docs/host/design.md`
- Control doc: `docs/host/host-core-followup-implementation-control.md`
- Plan: `docs/host/wu-layer-02-shared-runtime-helper-consolidation-plan.md`
- Slice artifacts: 3 slices × (implementation report + MiMo review + DS review + controller adjudication) = 12 artifacts
- Current branch diff from plan acceptance commit `76ecdb8`

## Aggregate Review Checklist

### 1. dayu.runtime.diagnostic_text 层中立性 — PASS

**验证项**：runtime diagnostic_text 仍是纯层中立 text primitive，不知道 Exception/Run/Attempt/Host diagnostic ref/Engine event/provider payload。

**直接证据**：

- `dayu/runtime/diagnostic_text.py` 只 import `re` 和 `typing.Final`（均为标准库）。
- 模块 docstring 明确声明："它不理解 Exception、Run、Attempt、Host diagnostic ref、Engine event、provider payload、tool trace 或任何财报业务字段"。
- 不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`（grep 确认零命中）。
- `dayu/runtime/__init__.py` 的 `__all__: list[str] = []`，diagnostic_text 模块符号不可从包根直接访问。
- 不使用 `Any` / `object` / 无类型签名（grep 确认零命中）。
- 不使用 `getattr` / `hasattr`（grep 确认零命中）。

### 2. Engine 整条 redaction policy 保持 — PASS

**验证项**：Engine 只使用 runtime contains/truncate，仍保留 whole-message redaction policy、RunFailedData.message shape、Agent 状态机和 RunnerEvent public contract。

**直接证据**：

- `dayu/engine/agent.py` 已删除 Engine 私有 `_BEARER_SECRET_PATTERN`、`_API_KEY_VALUE_PATTERN`、`_ASSIGNED_SECRET_VALUE_PATTERN` 和 `_contains_sensitive_exception_value`。
- 改用 `from dayu.runtime.diagnostic_text import contains_sensitive_diagnostic_value, truncate_diagnostic_text`。
- `_exception_diagnostic_message` 保持 Engine 整条 redaction 策略：命中 sensitive 时返回 `f"{exc_type}: {_EXCEPTION_MESSAGE_REDACTED}"`，不使用 Host-style value redaction。
- `_safe_log_message` 保持 Engine 整条 redaction 策略：空白消息 → `_EXCEPTION_MESSAGE_REDACTED`；敏感命中 → `_EXCEPTION_MESSAGE_REDACTED`；普通消息 → runtime truncation。
- 保留 Engine 私有 policy 常量：`_EXCEPTION_MESSAGE_REDACTED`、`_EXCEPTION_MESSAGE_MAX_LENGTH=240`、`_EXCEPTION_MESSAGE_TRUNCATED_SUFFIX="... [truncated]"`。
- Agent 状态机、`RunnerEvent`、`RunFailedData` 字段、metadata、public contract 均未变更。

### 3. Host compaction 局部 value redaction policy 保持 — PASS

**验证项**：Host compaction 只使用 runtime redact/truncate，仍保留 local value redaction policy、error_code= 提取、diagnostic ref shape、attempt rejection/retry/quality/Context Governance owner。

**直接证据**：

- `dayu/host/compaction_operation.py` 已删除 Host 私有 `_BEARER_SECRET_PATTERN` 和 `_ASSIGNMENT_SECRET_PATTERN`。
- 改用 `from dayu.runtime.diagnostic_text import redact_sensitive_diagnostic_values, truncate_diagnostic_text`。
- `_safe_exception_message` 保持 Host 局部 value redaction 策略：`redact_sensitive_diagnostic_values(message, redaction_marker=_REDACTED_SECRET)` → `truncate_diagnostic_text(...)`。
- 保留 `_ERROR_CODE_PATTERN` 和 `_exception_error_code`（Host compaction `error_code=` 提取 owner）。
- 保留 `_exception_diagnostic_suffix`（Host diagnostic ref suffix 构造 owner）。
- 保留 Host policy 常量：`_REDACTED_SECRET="<redacted>"`、`_MAX_SAFE_EXCEPTION_MESSAGE_CHARS=240`、`_TRUNCATED_SUFFIX="..."`。
- `CompactionAttemptRejected` dataclass、`diagnostic_refs` 结构、failure category、repair budget、quality check、multi-pass merge、Context Governance 均未改动。

### 4. Explicitly Rejected Scope 未被误改 — PASS

**验证项**：OpenAI diagnostic payload、runtime digest、Host durable canonical JSON/digest/timestamp、tool trace/tool runtime digest/EventLog/audit semantics 未被误改。

**直接证据**：

- `dayu/runtime/_digest.py`：无变更。
- `dayu/engine/runners/openai/diagnostic_payload.py`：无变更。
- `dayu/host/durable/`（codec.py、payload.py、artifact.py、event_log.py、tool_trace.py、audit.py）：无变更。
- `dayu/host/tool_runtime.py`：无变更。
- `dayu/runtime/tool_truncation.py`：无变更。

### 5. README 与 tests README 只记录当前事实 — PASS

**验证项**：README 只记录当前已落地事实，不写未来计划或过程状态；无漏掉的必要文档同步。

**直接证据**：

- `dayu/README.md` L85：`diagnostic_text`：提供层中立 diagnostic 文本敏感值检测、局部脱敏和有界截断；不承载 Host / Engine 诊断事件语义、provider payload 语义或业务字段语义。✓ 只记录当前能力。
- `tests/README.md` L91：diagnostic text：覆盖层中立 diagnostic 文本中的 Bearer / API key / authorization / password / secret / token 敏感值检测、局部 value 脱敏、marker 字面替换、有界截断、空字符串 no-op、普通 token/header 诊断不误判，以及先脱敏再截断不泄漏原值。✓ 只记录当前测试事实。
- 根目录 `README.md`：正确未更新（用户入口、CLI、workflow 未变）。
- `dayu/engine/README.md`：正确未更新（Engine public contract 不变）。
- `dayu/host/README.md`：正确未更新（Host public contract、状态机不变）。
- 无未来计划、过程状态或实现细节写入文档。

### 6. 测试覆盖跨 slice 行为 — PASS

**验证项**：runtime direct tests、Engine behavior tests、Host compaction behavior tests、import boundary、weak typing guard、pyright 均覆盖。

**验证结果**：

| 验证命令 | 结果 |
|---|---|
| `pytest tests/runtime/test_diagnostic_text.py tests/runtime/test_weak_typing_guard.py tests/host/test_import_boundary.py` | 67 passed |
| `pytest tests/engine/test_agent_phase2.py tests/host/test_compaction_operation.py` | 101 passed |
| `pytest tests/runtime tests/engine/test_agent_phase2.py tests/host/test_compaction_operation.py tests/host/test_import_boundary.py` | 430 passed |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings |

**跨 slice 行为覆盖矩阵**：

| 行为维度 | Runtime 直接测试 | Engine 行为测试 | Host 行为测试 |
|---|---|---|---|
| Bearer detection/redaction | ✓ 14 patterns | ✓ | ✓ 9 parametrized |
| api key space form | ✓ | ✓ | ✓ |
| semicolon value start | ✓ | ✓ | ✓ |
| closing punctuation start | ✓ | ✓ | ✓ |
| JWT/header false-positive guard | ✓ 5 cases | ✓ | ✓ |
| Engine whole-message redaction | — | ✓ sensitive→redacted | — |
| Host value redaction | — | — | ✓ field prefix preserved |
| Truncation no-op/boundary/over-limit | ✓ | ✓ | ✓ |
| Empty string no-op | ✓ | ✓ | ✓ |
| Redact+truncate composition | ✓ | — | ✓ |
| Idempotency | ✓ | — | — |
| Import boundary | ✓ | — | ✓ |
| Weak typing guard | ✓ | — | — |

### 7. 编码规范合规 — PASS

**验证项**：无 overbroad abstraction、glue seam、兼容 re-export、Any/object/无类型签名、getattr/hasattr、魔法字符串问题。

**直接证据**：

- 无 `Any` / `object` / 无类型签名：全量 grep 确认零命中。
- 无 `getattr` / `hasattr`：全量 grep 确认零命中。
- 无兼容 wrapper / facade / re-export：`__all__: list[str] = []` 保持不变。
- 无胶水 seam / lazy import：所有 import 在模块顶部。
- 常量均为模块级私有 `Final`（runtime）或纯大写下划线（Host/Engine）。
- 中文 docstring 完整：所有函数/模块有 `:param` / `:returns` / `:raises`。
- 无 overbroad abstraction：runtime 只提供三个朴素函数，不接收 callback / factory / profile / query。

## Findings

**无 blocking / high / medium / low findings。**

全部 7 个审查维度均通过。三个 slice 的 implementation report、code review 和 controller adjudication 均记录为 PASS，无 accepted blocking finding。

## Validation Summary

| 验证项 | 结果 |
|---|---|
| Runtime direct tests | 22 tests, 0 failures |
| Weak typing guard | PASS |
| Import boundary | PASS |
| Engine behavior tests | 19 tests (new) + 既有测试, 0 failures |
| Host compaction behavior tests | 13 tests (new) + 既有测试, 0 failures |
| Cross-slice full test run | 430 passed |
| pyright | 0 errors, 0 warnings, 0 informations |
| Rejected scope git diff | 0 files changed |

## Residual Risks

| ID | 风险 | Owner | 说明 |
|---|---|---|---|
| RR-LAYER-02-01 | Runtime regex 演进 | future maintenance | 若未来新增 secret 形态，应优先扩展 `dayu.runtime.diagnostic_text` 及其直接测试，Host/Engine 通过同一 primitive 继承能力。当前 regex 覆盖 Bearer、api key 全形态、authorization、password、secret、token 赋值，短期无盲区。 |
| RR-LAYER-02-02 | Provider error payload 审计 | outside WU-LAYER-02 | Diagnostic ref 仍承载截断后的异常消息上下文；当前测试覆盖 value-bearing secret 与普通 token 句子，但不替代更广泛的 provider error payload 审计。 |
| RR-LAYER-02-03 | `_safe_log_message` 精确边界值 | low risk | Engine `_safe_log_message` 在 `len(message) == _EXCEPTION_MESSAGE_MAX_LENGTH`（240）时没有独立 Engine 层测试；当前行为依赖 runtime `truncate_diagnostic_text` 的 exact-boundary no-op 语义保证。 |

## Verdict

**PASS — ready for controller aggregate acceptance。**

WU-LAYER-02 Shared Runtime Helper Consolidation 全量聚合审查通过。三个 slice 的实现严格遵守 plan 的层中立边界、explicitly rejected scope、Engine/Host policy 保持和 README 同步规则。runtime diagnostic_text 是纯层中立 text primitive，Engine 保持整条 redaction 策略，Host 保持局部 value redaction 策略，rejected scope 无误改，测试覆盖充分（430 passed），pyright 零错误。无 blocking / high / medium / low finding。三条 residual risk 均为低风险或明确 deferred，不阻塞 acceptance。
