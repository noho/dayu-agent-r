# WU-LAYER-02 Plan Review — MiMo

- Gate: plan review
- Reviewer: MiMo
- Date: 2026-06-02
- Artifact under review: `docs/host/wu-layer-02-shared-runtime-helper-consolidation-plan.md`
- Design source: `docs/host/design.md`
- Control doc: `docs/host/host-core-followup-implementation-control.md`

## 1. Motivation Validation

Plan 第 2 节 first-principles 分析正确：

- Engine `agent.py` 的 `_contains_sensitive_exception_value` / `_safe_log_message` 与 Host `compaction_operation.py` 的 `_safe_exception_message` 确实在解决同一类层中立问题：secret-value detection + bounded truncation。
- 两处实现已分叉：Engine 整条 redacted，Host 只替换 value。但底层 regex 和截断逻辑是同质 primitive。
- Root cause 不是状态机错误，而是缺少层中立 diagnostic text primitive owner。

**裁决：动机真实成立，不是"名字相同"误判。** Plan 正确区分了同名但 owner 不同的 helper（OpenAI diagnostic payload、Host durable digest、tool runtime truncation）。

## 2. Findings Ordered by Severity

### F-01: Engine vs Host Regex 差异未在 Plan 中显式声明 [Medium]

Engine `agent.py:183-189` 的 secret regex 使用 `\b` word boundary：

```python
# Engine
_BEARER_SECRET_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_API_KEY_VALUE_PATTERN = re.compile(r"(?i)\b(?:api[ _-]?key|apikey)\b\s*(?::|=|\s+)\s*[^,\s}\]]+")
_ASSIGNED_SECRET_VALUE_PATTERN = re.compile(r"(?i)\b(?:authorization|password|secret|token)\b\s*[:=]\s*[^,\s}\]]+")
```

Host `compaction_operation.py:47-48` 的 secret regex 无 `\b`，且 `ASSIGNMENT_SECRET_PATTERN` 捕获赋值前缀：

```python
# Host
_BEARER_SECRET_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_ASSIGNMENT_SECRET_PATTERN = re.compile(r"(?i)((?:api[_-]?key|authorization|token|secret)\s*[:=]\s*)[^,\s}\]]+")
```

差异点：
1. Engine Bearer 有 `\b`，Host 无 `\b`。Host 可能匹配 `bearer123 token=xxx` 中的 `bearer123`。
2. Engine `api[ _-]?key` 匹配 `api key`、`api-key`、`apikey`；Host `api[_-]?key` 只匹配 `api_key`、`apikey`，不匹配 `api key` 空格写法。
3. Engine `ASSIGNED_SECRET_VALUE_PATTERN` 不捕获前缀；Host `ASSIGNMENT_SECRET_PATTERN` 捕获前缀 `\1` 用于 `sub` 替换时保留字段名。
4. Engine pattern 覆盖 `password`；Host pattern 不覆盖 `password`。

Plan 第 7 节说 "value-bearing pattern" 列出了 `api key` 空格写法和 `password`，暗示 runtime 采用 Engine 的更宽 pattern。但这意味着 Host compaction migration 后会新增 `api key <value>` 和 `password=<value>` detection——Plan 第 11 节 "Residual Risks" 只提到了 `api key` 空格写法，未提及 `password` 和 `\b` 边界差异。

**要求：** Plan 必须在第 7 节或 Residual Risks 中显式声明 runtime regex 与 Engine/Host 当前 regex 的所有差异点，以及 migration 后 Host compaction 的行为变化范围（新增哪些 pattern 命中）。

### F-02: `_safe_log_message` 无直接测试 [Medium]

Engine `agent.py:1288` 在生产路径中调用 `_safe_log_message(data.message)`。但 `tests/engine/test_agent_phase2.py` 中搜索 `safe_log_message` 无结果。当前只有 `_exception_diagnostic_message` 的间接测试覆盖。

`_safe_log_message` 的语义与 `_exception_diagnostic_message` 不同：
- 空白字符串 → `_EXCEPTION_MESSAGE_REDACTED`（而非异常类型名）
- 命中 sensitive → `_EXCEPTION_MESSAGE_REDACTED`（同）
- 截断使用相同常量（同）

Slice 2 plan 提到 "补一条 `_safe_log_message` 对 sensitive value 整条 redacted 的直接测试"，但只提了 "一条"。至少需要覆盖：空消息、sensitive 命中、普通消息截断、JWT token 不误伤。

**要求：** Slice 2 Exact changes 中明确列出 `_safe_log_message` 的直接测试覆盖矩阵。

### F-03: `truncate_diagnostic_text` 对空字符串的行为未定义 [Low]

Plan 第 7 节说 "空字符串不被 runtime 特判为 redacted；空字符串如何显示由调用方 owner 决定"。但未定义 runtime primitive 对空字符串的返回值：
- `contains_sensitive_diagnostic_value("")` → `False`（合理）
- `redact_sensitive_diagnostic_values("", redacted_value="x")` → `""`（合理）
- `truncate_diagnostic_text("", max_chars=10, truncated_suffix="...")` → `""`（合理，但未显式声明）

当前 Engine 的 `_safe_log_message` 对空字符串返回 `_EXCEPTION_MESSAGE_REDACTED`，这是调用方策略。但 runtime primitive 应该显式声明空字符串是 no-op 还是 fail。

**要求：** Slice 1 test cases 增加空字符串输入的显式断言。

### F-04: Host `_exception_diagnostic_suffix` 依赖 `_safe_exception_message` 的返回值语义 [Low]

Host `compaction_operation.py:649-659`：

```python
def _exception_diagnostic_suffix(exc: Exception) -> str:
    message = _safe_exception_message(exc)
    if message == exc.__class__.__name__:
        return exc.__class__.__name__
    return f"{exc.__class__.__name__}:{message}"
```

当 `_safe_exception_message` 返回异常类名（空消息场景）时，suffix 只返回类名，不拼接 `:message`。Migration 后 `_safe_exception_message` 改为调用 runtime primitive，必须确保空消息路径返回值不变。

**要求：** Slice 3 test cases 覆盖空异常消息进入 `_exception_diagnostic_suffix` 的行为。

### F-05: `_PHASE12_RUNTIME_HELPERS` 集合是否需要更新 [Informational]

`tests/runtime/test_weak_typing_guard.py:13-22` 维护了一个 `_PHASE12_RUNTIME_HELPERS` 集合，用于验证 Phase 12 helper 文件存在于扫描范围内。但 `test_runtime_disallows_weak_typing()` 使用 `_iter_runtime_files()` 做 `rglob("*.py")`，会自动扫描新增的 `diagnostic_text.py`。

`_PHASE12_RUNTIME_HELPERS` 检查的是文件存在性，不是扫描范围限定。新增 `diagnostic_text.py` 不需要加入此集合，除非我们想把它标记为 Phase 12 helper。

**裁决：** Plan 提到 "如决定显式列入 helper coverage set" 是正确的保守表述。实现时可以选择不加入，因为 rglob 已自动覆盖。

## 3. Assumption Challenges

### A-01: "runtime 只提供三个函数" 假设是否过窄

Plan 提议三个函数：`contains_sensitive_diagnostic_value`、`redact_sensitive_diagnostic_values`、`truncate_diagnostic_text`。

Engine 调用路径：`contains_sensitive_diagnostic_value` → 整条 redacted → 否则 `truncate_diagnostic_text`。
Host 调用路径：`redact_sensitive_diagnostic_values` → `truncate_diagnostic_text`。

这意味着 Engine 不使用 `redact_sensitive_diagnostic_values`，Host 不使用 `contains_sensitive_diagnostic_value`。三个函数中每个调用方只用两个。

**质疑：** 是否应该只提供两个函数，让 Engine 自己用 `contains_sensitive_diagnostic_value` + `truncate_diagnostic_text`，Host 自己用 `redact_sensitive_diagnostic_values` + `truncate_diagnostic_text`？

**裁决：** 当前设计合理。三个函数各自职责清晰，不存在过宽问题。Engine 选择整条 redacted 是因为 `RunFailedData.message` 面向用户，Host 选择 value redaction 是因为 diagnostic ref 需要保留上下文。runtime 不应把这些策略合并成一个 "safe_exception_message" helper。

### A-02: "Engine `api key` 空格写法统一到 runtime" 是否改变 Host 安全边界

Plan 第 11 节提到 "Regex unification may broaden Host compaction redaction to `api key <value>` space syntax. This is a security-hardening diagnostic-only change"。

**质疑：** 这是 security hardening 还是 behavior change？Host compaction 当前不检测 `api key <value>` 空格写法。Migration 后如果 runtime regex 更宽，Host 的 `_safe_exception_message` 会开始整条 redact 包含 `api key <value>` 的异常消息。这可能改变 compaction diagnostic ref 的内容，进而影响 compaction retry 诊断。

**裁决：** 这是 security hardening，不是 correctness regression。diagnostic ref 内容变化不影响 compaction 状态机、retry 逻辑或 failure category。但 Plan 应该在 Slice 3 的 test cases 中显式覆盖 `api key <value>` 空格写法进入 compaction exception 时的行为。

### A-03: "Host `_ASSIGNMENT_SECRET_PATTERN` 捕获前缀" 的替换语义是否能在 runtime 统一

Host 使用 `_ASSIGNMENT_SECRET_PATTERN.sub(rf"\1{_REDACTED_SECRET}", redacted)`，保留字段名前缀（如 `token=<redacted>`）。Engine 整条 redacted，不使用 `sub`。

Runtime `redact_sensitive_diagnostic_values` 需要支持 Host 的 "保留前缀" 语义。这意味着 runtime regex 也需要捕获前缀 group。

**质疑：** Plan 第 7 节说 "Bearer 统一替换为 `Bearer {redacted_value}`，赋值类字段保留字段名前缀和分隔符"。但未明确 runtime regex 是否使用捕获组。

**裁决：** Plan 需要在第 7 节或 Slice 1 Exact changes 中明确 runtime regex 的捕获组设计，确保 `redact_sensitive_diagnostic_values` 能保留字段名前缀。

## 4. Slice Sequencing Review

### Slice 1: Runtime Diagnostic Text Primitive

**评价：** 正确。先建 runtime primitive 并用直接测试锁定语义，再迁移业务层调用。allowed files 仅 6 个，足够窄。

**问题：**
- Slice 1 test cases 列表缺少空字符串输入测试（见 F-03）。
- `dayu/runtime/__init__.py` docstring 更新范围清晰。

### Slice 2: Engine Agent Exception Diagnostic Migration

**评价：** 正确。只改 `agent.py` 和对应测试，保留 Engine 私有 marker / 常量 / 策略。

**问题：**
- `_safe_log_message` 直接测试覆盖不足（见 F-02）。
- Stop condition 正确：`RunFailedData.message` 文本不得变化。

### Slice 3: Host Compaction Exception Diagnostic Migration

**评价：** 正确。只改 `compaction_operation.py` 和对应测试，保留 Host `_exception_error_code`、`_exception_diagnostic_suffix`、`diagnostic_refs` 结构。

**问题：**
- 需要覆盖空异常消息进入 `_exception_diagnostic_suffix` 的行为（见 F-04）。
- 需要覆盖 `api key <value>` 空格写法进入 compaction 的新行为（见 A-02）。

### Sequencing 依赖

Slice 1 → Slice 2 → Slice 3 是正确顺序。Slice 2 和 Slice 3 无相互依赖，但按序执行合理，因为 Slice 2 验证 Engine migration 后可以增强对 runtime primitive 的信心，再做 Host migration。

## 5. Testing Gaps

| Gap | 来源 | 严重度 | 建议 |
|---|---|---|---|
| `_safe_log_message` 无直接测试 | F-02 | Medium | Slice 2 增加至少 4 个直接测试 |
| Engine vs Host regex 差异未显式声明 | F-01 | Medium | Plan 补充差异矩阵 |
| 空字符串输入行为未定义 | F-03 | Low | Slice 1 增加空字符串测试 |
| `_exception_diagnostic_suffix` 空消息路径 | F-04 | Low | Slice 3 增加覆盖 |
| `password=<value>` 在 Host 新增 detection | A-02 | Low | Slice 3 显式测试 |

## 6. Open Questions

1. **Runtime regex 是否使用 `\b` word boundary？** 影响 `bearer123` 等边界 case。建议采用 Engine 的 `\b` 方案，更严格。
2. **Runtime regex 是否需要捕获赋值前缀 group？** 影响 `redact_sensitive_diagnostic_values` 的替换逻辑。建议明确。
3. **`_PHASE12_RUNTIME_HELPERS` 集合是否更新？** 信息性，不影响 correctness。

## 7. AGENTS.md Compliance Check

| 约束 | 状态 |
|---|---|
| 无 `Any` / `object` / 无类型签名 | Plan 第 6 节明确禁止 |
| 无 `getattr` / `hasattr` | Plan 第 6 节明确禁止 |
| 无 lazy import / glue seam | Plan 第 6 节明确禁止 |
| 无兼容 wrapper / facade / re-export | Plan 第 6 节明确禁止 |
| runtime 不 import 上层 | Slice 1 stop condition 显式检查 |
| 不把显式参数放进 extra payload | API 使用显式参数 |
| 中文 docstring | Plan 提到"完整中文 docstring" |
| 模块级私有辅助函数 | Plan 提到"模块级私有 `Final`" |
| 不使用魔法数字/字符串 | 常量使用 `Final` |

**裁决：** AGENTS.md 约束已覆盖。

## 8. Residual Risk / Deferred Item 评估

Plan 第 11 节列出 5 项 residual risk：

1. **Regex unification broadening** — 正确识别，但缺少 `password` 差异。
2. **Engine vs Host policy difference** — 正确保留。
3. **OpenAI diagnostic payload separate** — 正确拒绝。
4. **`_digest.py` no dedicated test** — 正确 defer。
5. **README minimal updates** — 正确。

**建议新增：**
- RR-LAYER-02-01: `_safe_log_message` 生产路径测试缺口，当前无直接测试。Owner: WU-LAYER-02 Slice 2。

## 9. Verdict

**PASS — 可进入 implementation，但需先修复以下 plan fix items：**

| ID | 严重度 | 描述 | Fix 方式 |
|---|---|---|---|
| PF-01 | Medium | Engine vs Host regex 差异（`\b`、`password`、捕获组）必须在 Plan 第 7 节或 Residual Risks 中显式声明 | Plan 文本补充 |
| PF-02 | Medium | `_safe_log_message` 直接测试覆盖矩阵必须在 Slice 2 Exact changes 中明确 | Plan 文本补充 |
| PF-03 | Low | 空字符串输入行为必须在 Slice 1 test cases 中显式断言 | Plan 文本补充 |
| PF-04 | Low | `_exception_diagnostic_suffix` 空消息路径必须在 Slice 3 test cases 中覆盖 | Plan 文本补充 |

PF-01 和 PF-02 为 plan fix 前置条件。PF-03 和 PF-04 可在 implementation 时补齐。

Plan 整体设计合理：动机真实、scope 收窄正确、非目标明确、API 朴素、slice 依赖清晰、AGENTS.md 约束覆盖。上述 findings 均为 plan 文本补全，不改变架构方向或 slice 结构。
