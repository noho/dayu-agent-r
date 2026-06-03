# WU-LAYER-02 Aggregate Deep Review — DS

- **Reviewer**: DS (deepseek-v4)
- **Date**: 2026-06-02
- **Gate**: aggregate deep review
- **Scope**: WU-LAYER-02 Shared Runtime Helper Consolidation，Slice 1/2/3 全量聚合审查
- **Design source**: `docs/host/design.md` §3
- **Control doc**: `docs/host/host-core-followup-implementation-control.md`
- **Plan**: `docs/host/wu-layer-02-shared-runtime-helper-consolidation-plan.md`

## Verification Summary

| Check | Command | Result |
|---|---|---|
| Runtime direct + import boundary + weak typing | `pytest -q tests/runtime/test_diagnostic_text.py tests/runtime/test_weak_typing_guard.py tests/host/test_import_boundary.py` | 67 passed |
| Engine + Host compaction behavior | `pytest -q tests/engine/test_agent_phase2.py tests/host/test_compaction_operation.py` | 101 passed |
| Full cross-slice regression | `pytest -q tests/runtime tests/engine/test_agent_phase2.py tests/host/test_compaction_operation.py tests/host/test_import_boundary.py` | 430 passed |
| Pyright | `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| Production diff vs main | `git diff main...HEAD -- dayu/` | 10 files, only WU-LAYER-01 + WU-LAYER-02 scope |

## Findings（按 Severity 排序）

### F-01 [MEDIUM] `llm_compaction.py` 私有 secret regex 未迁移——遗漏的重复实现

**Severity**: Medium（不阻断当前 gate，但属于 WU-LAYER-02 目标范围内的遗漏）

**直接证据**:

`dayu/host/llm_compaction.py:76-77` 仍保留私有 secret regex：

```python
_BEARER_SECRET_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_ASSIGNMENT_SECRET_PATTERN = re.compile(r"(?i)((?:api[_-]?key|authorization|secret|token)\s*[:=]\s*)[^,\s}\]]+")
```

`dayu/host/llm_compaction.py:339-351` 的 `_safe_outcome_text` 自行实现 redact + truncate：

```python
def _safe_outcome_text(text: str) -> str:
    redacted = _BEARER_SECRET_PATTERN.sub(f"Bearer {_REDACTED_SECRET}", text)
    redacted = _ASSIGNMENT_SECRET_PATTERN.sub(rf"\1{_REDACTED_SECRET}", redacted)
    if len(redacted) <= _MAX_SAFE_OUTCOME_MESSAGE_CHARS:
        return redacted
    return redacted[:_MAX_SAFE_OUTCOME_MESSAGE_CHARS] + _TRUNCATED_SUFFIX
```

该函数被 `_non_final_outcome_message` (L304) 两处调用（L317、L322），处理 Engine runner outcome 的 `message` 和 `reason` 字段。

**问题性质**:

1. **语义完全重复**: `_safe_outcome_text` 的逻辑 = `redact_sensitive_diagnostic_values(text, redaction_marker="<redacted>")` → `truncate_diagnostic_text(text, max_chars=240, truncated_suffix="...")`。与已迁移的 `compaction_operation._safe_exception_message` 的 redact+truncate 部分完全相同。

2. **参数值完全重复**: `_MAX_SAFE_OUTCOME_MESSAGE_CHARS=240`、`_TRUNCATED_SUFFIX="..."`、`_REDACTED_SECRET="<redacted>"` 与 `compaction_operation.py` 已迁移版本的值完全一致。

3. **已知重复**: 2026-05-23 的全仓 review (`docs/reviews/repo-review-20260523-211835.md`) 已记录为 F13-已确认-低：`llm_compaction.py` 与 `compaction_operation.py` 的密钥脱敏逻辑完全重复。

4. **Plan 遗漏**: plan §3"Direct Evidence / Code References" 仅引用 `compaction_operation.py:44-49` 和 `compaction_operation.py:717-751`，未提及 `llm_compaction.py:73-77` 和 `llm_compaction.py:339-351`。plan review (MiMo/DS)、controller adjudication、三个 slice 的实现和 review 均未发现此遗漏。

5. **regex 替换安全隐患**: `rf"\1{_REDACTED_SECRET}"` 用字符串级 replacement 传给 `re.sub()`，依赖 `_REDACTED_SECRET` 不含 `\1`、`\g<name>` 或反斜杠等特殊字符。当前 `_REDACTED_SECRET = "<redacted>"` 是安全的，但已迁移的 runtime 使用 callable lambda replacement 是更安全的做法。

6. **无直接测试覆盖**: `tests/host/` 中没有针对 `_safe_outcome_text` 的 redaction 行为测试。

**影响评估**:

- 不影响 runtime correctness：`llm_compaction.py` 的 secret redaction 行为继续工作，没有退化。
- 不影响 Engine：Engine 已成功迁移到 runtime primitive。
- 不影响 `compaction_operation.py`：已成功迁移到 runtime primitive。
- 遗留的重复实现削弱了 WU-LAYER-02 的"共享 helper 收敛"目标完成度：Host compaction 域仍存在两套 secret regex，一套已迁移到 runtime，一套保留在 `llm_compaction.py`。

**建议**: 在本 aggregate gate 中记录为 deferred-with-owner，由后续 work unit 或 WU-LAYER-02 follow-up 处理。迁移路径明确且低风险：

```python
# llm_compaction.py 迁移后:
from dayu.runtime.diagnostic_text import (
    redact_sensitive_diagnostic_values,
    truncate_diagnostic_text,
)

def _safe_outcome_text(text: str) -> str:
    redacted = redact_sensitive_diagnostic_values(text, redaction_marker=_REDACTED_SECRET)
    return truncate_diagnostic_text(
        redacted,
        max_chars=_MAX_SAFE_OUTCOME_MESSAGE_CHARS,
        truncated_suffix=_TRUNCATED_SUFFIX,
    )
```

删除 `_BEARER_SECRET_PATTERN`、`_ASSIGNMENT_SECRET_PATTERN`，保留 `_REDACTED_SECRET`、`_MAX_SAFE_OUTCOME_MESSAGE_CHARS`、`_TRUNCATED_SUFFIX` 作为 Host display policy 常量。需补齐 `_safe_outcome_text` redaction 行为测试。

---

### F-02 [INFO] Runtime Layer Boundary — PASS

`dayu/runtime/diagnostic_text.py` 只 import `re` 与 `typing.Final`（均为标准库）。不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` 或其子模块。

模块 docstring 明确声明："它不理解 Exception、Run、Attempt、Host diagnostic ref、Engine event、provider payload、tool trace 或任何财报业务字段。"

`dayu/runtime/__init__.py` 的 `__all__: list[str] = []` 确保包根不 re-export 模块符号。

设计真源对齐: `docs/host/design.md:61-65` 定义的 runtime 层中立约束完全满足。

### F-03 [INFO] Engine 使用 runtime contains/truncate，保留 Engine policy — PASS

`dayu/engine/agent.py:116-119` import `contains_sensitive_diagnostic_value` 与 `truncate_diagnostic_text`（不含 `redact_sensitive_diagnostic_values`——Engine 不使用 Host-style value redaction）。

Engine 私有 secret regex（`_BEARER_SECRET_PATTERN`、`_API_KEY_VALUE_PATTERN`、`_ASSIGNED_SECRET_VALUE_PATTERN`）和 `_contains_sensitive_exception_value` 已完全删除。`import re` 也已删除（Engine 不再自行编译 regex）。

保留的 Engine policy：
- `_exception_diagnostic_message` (L201-220): 命中 secret → 整条 `"exception message redacted"`；未命中 → truncate 后拼接异常类型前缀。
- `_safe_log_message` (L223-239): 空白 → redacted；命中 secret → redacted；未命中 → truncate。
- `_EXCEPTION_MESSAGE_REDACTED = "exception message redacted"`、`_EXCEPTION_MESSAGE_MAX_LENGTH = 240`、`_EXCEPTION_MESSAGE_TRUNCATED_SUFFIX = "... [truncated]"` 作为 Engine display/diagnostic policy 保留。

未改变: Agent 状态机、RunnerEvent 类型、RunFailedData 字段（`error_code`、`message`、`provider_request_id`、`recoverable` 均未变）、public contract。

### F-04 [INFO] Host compaction 使用 runtime redact/truncate，保留 Host owner — PASS

`dayu/host/compaction_operation.py:33-36` import `redact_sensitive_diagnostic_values` 与 `truncate_diagnostic_text`。

Host 私有 secret regex（`_BEARER_SECRET_PATTERN`、`_ASSIGNMENT_SECRET_PATTERN`）已完全删除。

保留的 Host owner：
- `_ERROR_CODE_PATTERN` (L51) 与 `_exception_error_code`：Host compaction `error_code=` 提取。
- `_exception_diagnostic_suffix`：Host-owned 异常类型前缀与消息拼接规则。
- `CompactionAttemptRejected` dataclass、`diagnostic_refs` 结构、failure category、repair budget、quality check、multi-pass merge、Context Governance。
- Host display policy 常量: `_MAX_SAFE_EXCEPTION_MESSAGE_CHARS=240`、`_TRUNCATED_SUFFIX="..."`、`_REDACTED_SECRET="<redacted>"`。

`_safe_exception_message` (L735-756) 正确分层：
1. `exc is None` → `"none"` (Host semantic)
2. 空白异常消息 → 异常类名 (Host semantic)
3. 非空消息 → runtime `redact_sensitive_diagnostic_values` → runtime `truncate_diagnostic_text` (层中立 primitive)

### F-05 [INFO] Explicitly Rejected Scope — 全部 PASS

逐项核对：

| Rejected candidate | 状态 | 证据 |
|---|---|---|
| `dayu/engine/runners/openai/diagnostic_payload.py` | 未修改 | `git diff main...HEAD --` 无该文件 |
| `dayu/runtime/_digest.py` | 未修改 | `git diff main...HEAD --` 无该文件 |
| `dayu/runtime/tool_truncation.py` | 未修改 | 不在 diff 中 |
| `dayu/host/durable/codec.py` 等 | 未由 WU-LAYER-02 修改 | diff 中的 durable 变更为 WU-LAYER-01 |
| Host durable canonical JSON / digest / timestamp | 未迁移 | `compaction_operation.py` 保留全部 Host durable owner 常量 |
| OpenAI diagnostic payload digest 格式 | 未替换 | `diagnostic_payload.py` 保留 bare SHA-256 digest，不改为 runtime `sha256:` 前缀 |

### F-06 [INFO] README 与 tests README 状态 — PASS

`dayu/README.md:85`:
```
- `diagnostic_text`：提供层中立 diagnostic 文本敏感值检测、局部脱敏和有界截断；
  不承载 Host / Engine 诊断事件语义、provider payload 语义或业务字段语义。
```
仅记录当前稳定能力，不写实现细节、过程状态或未来计划。

`tests/README.md:91`:
```
- diagnostic text：覆盖层中立 diagnostic 文本中的 Bearer / API key / authorization /
  password / secret / token 敏感值检测、局部 value 脱敏、marker 字面替换、有界截断、
  空字符串 no-op、普通 token/header 诊断不误判，以及先脱敏再截断不泄漏原值。
```
仅记录当前测试覆盖事实。

未更新的 README 决策正确：
- 根目录 `README.md`：用户入口、CLI 命令、workflow 不变。
- `dayu/engine/README.md`：Engine public contract 不变。
- `dayu/host/README.md`：Host public contract、状态机、Context Governance 不变。

### F-07 [INFO] 测试覆盖跨 Slice 行为 — PASS (with observation)

跨 slice 测试矩阵：

| 测试域 | 测试文件 | 覆盖目标 | 结果 |
|---|---|---|---|
| Runtime direct | `tests/runtime/test_diagnostic_text.py` (22 tests) | detection/redaction/truncation 全部 primitive，包括 punctuation boundary、marker literal、idempotency、composition path | 通过 |
| Runtime weak typing | `tests/runtime/test_weak_typing_guard.py` | `diagnostic_text.py` 入 `_PHASE12_RUNTIME_HELPERS` 集合，扫描无 Any/object/无类型签名 | 通过 |
| Import boundary | `tests/host/test_import_boundary.py` | runtime 不 import Host/Engine/Service/UI/Fins | 通过 |
| Engine behavior | `tests/engine/test_agent_phase2.py` | `_exception_diagnostic_message` 和 `_safe_log_message` 的 Engine policy（整条 redact、truncate suffix、semicolon/closing-punctuation boundary、false-positive guard） | 通过 |
| Host compaction behavior | `tests/host/test_compaction_operation.py` | `_safe_exception_message` 的 Host policy（value redaction、9 种 parametrized secret pattern、JWT 不误伤、空消息 suffix）、diagnostic ref 不泄漏 | 通过 |

**Observation**: `llm_compaction.py` 的 `_safe_outcome_text` 无直接 redaction 行为测试。该函数当前仅在 `_non_final_outcome_message` 的 integration 路径中被间接调用，未单独断言 secret 不泄漏。若后续迁移该函数到 runtime primitive，需补齐直接测试。

### F-08 [INFO] Overbroad Abstraction / Glue Seam / 兼容 Re-export 检查 — PASS

逐项核对（覆盖全部 WU-LAYER-02 变更文件）：

| 约束 | 状态 | 说明 |
|---|---|---|
| 禁止 `Any` / `object` / 无类型签名 | PASS | 所有函数签名完整标注；pyright 0 errors |
| 禁止胶水 seam / lazy import | PASS | 无 lazy import |
| 禁止兼容性 wrapper / re-export | PASS | 无 compat code；`__all__: list[str] = []` |
| 禁止 `hasattr` / `getattr` | PASS | grep 确认零命中 |
| 禁止魔法数字 / 魔法字符串 | PASS | 所有常量模块级 Final 或私有模块常量 |
| 禁止 overbroad abstraction | PASS | runtime API 保持三个朴素函数；不接收 callback/factory/profile/query |
| 中文 docstring | PASS | 所有函数/类/模块有完整中文 docstring，含 `:param`/`:returns`/`:raises` |
| Engine 不误用 Host value redaction | PASS | Engine 不 import `redact_sensitive_diagnostic_values` |
| Host 不误接受 Engine whole-message redaction | PASS | Host 保留局部 value redaction 策略 |

---

## Aggregate Owner Boundary Map（最终状态）

```
dayu.runtime.diagnostic_text  ← 唯一真源：层中立 secret detection / value redaction / truncation
    ↑                              ↑
    │                              │
dayu.engine.agent              dayu.host.compaction_operation
  uses: contains, truncate       uses: redact, truncate
  policy: whole-message          policy: local value redaction
          redacted                       + error_code= extract (Host owner)
          + Engine suffix                + diagnostic suffix (Host owner)
          + blank→redacted               + None→"none" (Host owner)
                                         + attempt reject state machine (Host owner)

dayu.host.llm_compaction       ← 未迁移：私有 _BEARER_SECRET_PATTERN +
  _safe_outcome_text               _ASSIGNMENT_SECRET_PATTERN + 手动 slice truncate
  (duplicate,→ F-01)

dayu.engine.runners.openai     ← explicitly rejected: JSON key-based redaction,
  diagnostic_payload.py           provider-specific payload digest, not text regex

dayu.runtime._digest           ← explicitly rejected: sha256:<hex> format,
                                   not replaced by or replacing anything
```

---

## Residual Risks

1. **RR-L2-01 (F-01)**: `llm_compaction.py._safe_outcome_text` 未迁移到 runtime primitive。Owner: 后续 WU-LAYER-02 follow-up 或下一个 Host hardening work unit。迁移路径明确、低风险；当前行为无退化。
2. **RR-L2-02**: `_safe_outcome_text` 使用 `rf"\1{_REDACTED_SECRET}"` 字符串级 replacement 传给 `re.sub()`，依赖 `_REDACTED_SECRET` 不含 regex replacement 特殊字符。当前值 `<redacted>` 安全，但不如 runtime 的 callable lambda replacement 稳健。
3. **RR-L2-03**: `llm_compaction.py._safe_outcome_text` 无直接 redaction 行为测试。当前仅通过 `_non_final_outcome_message` 的 integration 路径间接覆盖。
4. **RR-L2-04**: `_safe_outcome_text` 的旧 Host regex 未使用 `\b` word-boundary guard（与旧 `compaction_operation.py` 一致），且不覆盖 `api key <value>` 空格写法、`apikey`、`password`、`api-key:` 等 runtime 新增的 security hardening 模式。这些是 diagnostic-only 安全增强的缺失，不影响 compaction 状态机。

---

## Verdict

**PASS — 1 medium deferred finding, 0 blocking/high.**

WU-LAYER-02 的核心目标已达成：
- `dayu.runtime.diagnostic_text` 建立了唯一的层中立 diagnostic text primitive owner。
- Engine Agent 和 Host `compaction_operation.py` 已删除私有 secret regex，统一使用 runtime primitive。
- 所有 explicitly rejected scope（OpenAI diagnostic payload、runtime digest、Host durable、tool trace digest）未被误改。
- Engine 保留 whole-message redaction policy，Host 保留 local value redaction policy，runtime 不吞并上层策略差异。
- README 仅记录当前事实，不写未来计划。
- 430 测试通过，pyright 0 errors，import boundary clean。

F-01（`llm_compaction.py` 未迁移）是计划阶段的 scope 遗漏，不是实现质量缺陷。该文件与 `compaction_operation.py` 有相同的 redact+truncate 重复模式（已被 2026-05-23 全仓 review 识别），但未被 WU-LAYER-02 plan 纳入 scope。建议记录为 deferred residual risk，由后续 work unit 收尾。

**Ready for controller aggregate acceptance.**
