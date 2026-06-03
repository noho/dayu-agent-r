# WU-LAYER-02 Plan Review — DS 2026-06-02

## Review Metadata

- **Role:** plan review specialist (DS), adversarial review only — 不修改计划、代码或测试
- **Plan artifact:** `docs/host/wu-layer-02-shared-runtime-helper-consolidation-plan.md`
- **Design source:** `docs/host/design.md`
- **Control doc:** `docs/host/host-core-followup-implementation-control.md`
- **AGENTS:** `/Users/leo/workspace/dayu-agent-r/AGENTS.md`
- **Scope:** WU-LAYER-02 Shared Validation / Redaction / JSON Helper Consolidation

---

## 1. Evidence Baseline

审查基于以下直接证据（全部已读）：

| 文件 | 关键行号 | 审查内容 |
|---|---|---|
| `dayu/engine/agent.py` | 180-263 | Engine 私有 secret regex、`_exception_diagnostic_message`、`_contains_sensitive_exception_value`、`_safe_log_message` |
| `dayu/host/compaction_operation.py` | 44-49, 649-751 | Host 私有 secret regex、`_safe_exception_message`、`_exception_diagnostic_suffix`、`_exception_error_code` |
| `dayu/engine/runners/openai/diagnostic_payload.py` | 1-467 | OpenAI provider JSON diagnostic payload 全模块 |
| `dayu/runtime/_digest.py` | 1-58 | Runtime canonical JSON digest (`sha256:` prefix, `allow_nan=False`) |
| `dayu/runtime/__init__.py` | 1-35 | Runtime 包能力清单、不 re-export 契约 |
| `dayu/runtime/tool_truncation.py` | 1-20 | 层中立 tool truncation declaration helper |
| `tests/engine/test_agent_phase2.py` | 802-870 | Engine 异常诊断截断、secret redaction、`JWT token` 不误伤 |
| `tests/host/test_compaction_operation.py` | 117-133, 506-521 | `_SensitiveFailingCompactor`、compaction diagnostic redaction |
| `tests/host/test_import_boundary.py` | 30-36, 257-270 | `RUNTIME_FORBIDDEN_PREFIXES`、runtime import boundary guard |
| `tests/runtime/test_weak_typing_guard.py` | 1-219 | Runtime 全文件弱类型扫描、`_PHASE12_RUNTIME_HELPERS` 覆盖检查 |
| `docs/host/design.md` | 61-65 | `dayu.runtime` 层中立定义与硬约束 |

---

## 2. Motivation Verification

### 2.1 重复是否真实

**结论：真实成立。**

对比两处实现：

**Engine `agent.py:183-188`:**
```python
_BEARER_SECRET_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_API_KEY_VALUE_PATTERN = re.compile(
    r"(?i)\b(?:api[ _-]?key|apikey)\b\s*(?::|=|\s+)\s*[^,\s}\]]+"
)
_ASSIGNED_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)\b(?:authorization|password|secret|token)\b\s*[:=]\s*[^,\s}\]]+"
)
```

**Host `compaction_operation.py:47-48`:**
```python
_BEARER_SECRET_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_ASSIGNMENT_SECRET_PATTERN = re.compile(
    r"(?i)((?:api[_-]?key|authorization|token|secret)\s*[:=]\s*)[^,\s}\]]+"
)
```

- Bearer pattern：**完全相同**（字符级别一致）。
- API key / assigned secret pattern：**语义等价但分叉**。Engine 覆盖更宽（含 `api key` 空格写法、`apikey`、`password=`），Host 更窄且有 capturing group 用于 value substitution。
- 两处都实现了独立的 truncation 逻辑（Engine: 240 chars + `... [truncated]`，Host: 240 chars + `...`），语义一致但后缀不同。

Root cause 是缺少层中立 diagnostic text primitive owner，导致 regex 和截断逻辑在业务层重复演化。该判断有直接代码证据支撑。

### 2.2 "同名但 owner 不同"的拒绝是否正确

逐一核实：

| Candidate | Plan 判决 | 证据 | 审查结论 |
|---|---|---|---|
| OpenAI `diagnostic_payload.py` | 不下沉 | bare hex digest（非 `sha256:`）、`canonical_byte_size`、`payload_version`、provider error sub-object、invalid UTF-8 chunk — 全为 OpenAI runner 语义 | **正确拒绝** |
| `dayu/runtime/_digest.py` | 不改接口 | 已有 `sha256:` prefix + `allow_nan=False`，与 OpenAI bare hex / Host durable digest 是不同的 digest 语义 owner | **正确保留** |
| Host durable codec/payload/artifact/EventLog/tool_trace | 不迁 | Host durable truth / audit / trace 语义，不是层中立 helper | **正确拒绝** |
| `dayu/runtime/tool_truncation.py` | 不合并 | Tool declaration truncation policy helper，与 exception diagnostic text 不同质 | **正确保留** |

---

## 3. Findings

### Severity 定义

- **HIGH:** 计划存在设计缺陷，实施后将引入 correctness regression、破坏既有语义或违反 AGENTS 硬约束。
- **MEDIUM:** 计划存在不够精确的范围、遗漏的测试覆盖、API 契约不明确或未充分说明的行为变更，应在实施前或实施中修正。
- **LOW:** 命名、文档、并行化机会等改进建议，不阻塞实施。

---

### Finding DS-01 [MEDIUM] — `redact_sensitive_diagnostic_values` 的 `redacted_value` 参数进入 `re.sub()` 时存在 backslash 解释风险

**Evidence:**
计划 Section 7 定义 `redact_sensitive_diagnostic_values(message, *, redacted_value: str) -> str`，语义为 "只替换敏感 value"。Host 当前调用 `_BEARER_SECRET_PATTERN.sub(f"Bearer {_REDACTED_SECRET}", message)` 和 `_ASSIGNMENT_SECRET_PATTERN.sub(rf"\1{_REDACTED_SECRET}", redacted)`。

`re.sub()` 的 `repl` 参数会解释 backslash-digit 序列（如 `\1`、`\g<name>`）。若调用方传入 `redacted_value="<redacted>"`，安全；但若任何未来调用方传入包含 `\1` 的 replacement，将出现非预期的反向引用替换而非字面文本。

**Risk:** 调用方在不知情时传入含 backslash 的 replacement marker 会导致意外行为。

**Recommendation:**
- 在函数 docstring 中显式说明 `redacted_value` 作为字面替换文本，backslash 不会被特殊解释（即在实现中使用 `re.escape()` 对 replacement 做转义，或使用 `str.replace()` 风格的非 regex 替换）。
- 或者在实现中对 `redacted_value` 调用 `re.escape()` 后再用于 `re.sub()`，确保语义为字面替换。

**Controller action:** Accept / Reject / Defer

---

### Finding DS-02 [MEDIUM] — Host compaction secret detection scope 扩大未在 Slice 3 exact changes 中逐项枚举

**Evidence:**
当前 Host `_ASSIGNMENT_SECRET_PATTERN` 覆盖: `api[_-]?key`、`authorization`、`token`、`secret`（仅 `=` 和 `:` 分隔符）。计划 Section 7 的 runtime primitive 覆盖更宽：
- `api key <value>` 空格写法（Host 现行 **不** 覆盖）
- `apikey` 无分隔符变体（Host 现行 **不** 覆盖）
- `password=<value>`（Host 现行 **不** 覆盖）
- `:` 变体已由 Host 覆盖（但 `api-key: value` dash+colon 组合未覆盖）

计划 Section 11 Residual Risks 提到 "Regex unification may broaden Host compaction redaction to `api key <value>` space syntax"，但未列出完整的 4 项新增检测。Slice 3 exact changes 只说 "增加覆盖 `api key <value>` 空格写法"，未提及其他 3 项。

**Risk:** 实施者可能只意识到 `api key <value>` 一项变更，忽略 `apikey`、`password=` 等同样被扩大的检测范围，导致测试覆盖不完整。

**Recommendation:**
- 在 Slice 3 exact changes 中完整列出迁移后 Host 新增检测的所有模式：`api key <value>`（空格）、`apikey=<value>`、`password=<value>`、`api-key:<value>`（dash+colon）。
- 对应在 Slice 3 测试中至少为每类新增模式各增加一条 assertion。

**Controller action:** Accept / Reject / Defer

---

### Finding DS-03 [MEDIUM] — `truncate_diagnostic_text` 的 no-op 语义（`len(message) <= max_chars`）未在 API contract 中显式声明

**Evidence:**
计划 Section 7 semantics 只写了 "在 `len(message) > max_chars` 时返回..."，暗示 `<= max_chars` 时原样返回，但未显式约定。Engine `_exception_diagnostic_message` 当前的行为是 `len(raw_message) > _EXCEPTION_MESSAGE_MAX_LENGTH` 时才截断，`<=` 时原样拼接。Host `_safe_exception_message` 同理。

**Risk:** 若实施者将 `<=` 场景也做了某种处理（如添加 suffix），会改变 Engine `RunFailedData.message` 的既有文本形状，违反了 plan 自身 "本 WU 不改变用户可见 failure message contract" 的约束。

**Recommendation:**
- 在 Section 7 `truncate_diagnostic_text` semantics 中增加一条：当 `len(message) <= max_chars` 时，原样返回 `message`，不做任何修改。
- 在 runtime 测试中增加一条 `len(message) == max_chars` 边界测试，断言返回原字符串（is 或 ==）。

**Controller action:** Accept / Reject / Defer

---

### Finding DS-04 [MEDIUM] — Runtime 测试计划缺少 `api-key:<value>`（dash+colon）和 `apikey=<value>` 的显式 detection 覆盖

**Evidence:**
计划 Section 7 semantics bullet 130 列出 `api-key:<value>` 作为应命中模式。但 Section 8 Slice 1 测试列表只写了 "Bearer / api key 空格写法 / api_key / apikey / authorization / password / secret / token 命中 detection"，未显式列出 `api-key:<value>`（dash+colon）变体。

当前 Engine test (`test_agent_phase2.py:848-858`) 已参数化覆盖 `Bearer`、`API key`、`api_key=`、`apikey=`、`authorization=`、`password=`、`secret=`、`token=`，但同样缺少 `api-key:` 变体。

**Risk:** `api-key:<value>` 模式可能未被 runtime regex 正确覆盖，或者覆盖了但没有测试证明。Engine 和 Host 的既有测试均未覆盖此变体，新 runtime primitive 应该补上。

**Recommendation:**
- 在 Slice 1 runtime 测试中增加 `api-key:sk-secret-value` 和 `api-key: sk-secret-value` 两个变体的 detection assertion。
- 同步在 Slice 2 Engine 测试的 parametrize 中增加 `api-key:` 变体（可选，因为 runtime 层已覆盖；但 Engine 层 defense-in-depth 建议保留）。

**Controller action:** Accept / Reject / Defer

---

### Finding DS-05 [MEDIUM] — Host compaction test 的 `_SensitiveFailingCompactor` 消息未覆盖 `password=` 和 `api key `（空格）模式

**Evidence:**
当前 `_SensitiveFailingCompactor` (test_compaction_operation.py:131-133) 抛出的异常消息为：
```python
"provider failed Bearer secret-token api_key=plain-secret token=token-secret secret=raw-secret"
```
包含：`Bearer`、`api_key=`、`token=`、`secret=`。不包含：`password=`、`api key `（空格）、`apikey=`、`api-key:`。

迁移后 Host 将使用 runtime primitive，其 regex 覆盖 `password=` 和 `api key ` 空格写法。若测试消息不包含这些模式，即使 runtime regex 正确，也无法在 Host 层证明新增检测模式在 compaction 异常路径生效。

**Risk:** Host 层对新增检测模式（`password=`、`api key ` 空格等）缺少端到端验证，可能遗漏 Host 特有调用策略（value redaction + 先 redact 再 truncate）与 runtime 集成的边界 bug。

**Recommendation:**
- 更新 `_SensitiveFailingCompactor` 的异常消息，增加 `password=plain-secret` 和 `api key sk-secret-value` 两种模式。
- 在 Slice 3 测试中分别断言这些模式的 value 被替换为 `<redacted>` 且不泄漏原始 secret。

**Controller action:** Accept / Reject / Defer

---

### Finding DS-06 [LOW] — `redacted_value` 参数命名歧义

**Evidence:**
参数名 `redacted_value` 在语义上可被解读为 "被脱敏的值"（即 secret 原文）或 "脱敏后的替换值"。实际语义是后者（replacement marker）。当前 Host 模块级常量命名为 `_REDACTED_SECRET = "<redacted>"`，更清晰表达这是"脱敏标记"而非"脱敏对象"。

**Risk:** 仅命名歧义，不影响正确性。但若后续有人误读 API 传入 secret 原文，会导致 secret 泄漏而非隐藏。

**Recommendation:**
- 考虑将参数名改为 `redaction_marker` 或 `replacement`，使语义更精确。
- 在 docstring 中显式说明该参数是 "替换敏感值的字面文本"，不是 "待脱敏的值"。

**Controller action:** Accept / Reject / Defer

---

### Finding DS-07 [LOW] — 未显式说明 word-boundary + assignment-operator 是防误伤机制

**Evidence:**
计划 Section 7 bullet 133 声明 `contains_sensitive_diagnostic_value` 不因 `JWT token has expired` 误伤。现有 Engine test (`test_agent_phase2.py:828-844`) 通过 parametrize 覆盖了 `JWT token has expired` 和 `Content-Type header is invalid`。

但计划未在 API semantics 中解释 WHY 这些不会误伤：regex 使用 `\b` word boundary + `\s*[:=]\s*` assignment operator 作为 guard。`JWT token has expired` 中 `token` 后面没有 `=` 或 `:`，因此不匹配 `_ASSIGNED_SECRET_VALUE_PATTERN`，也不匹配 `_API_KEY_VALUE_PATTERN`（该 pattern 只匹配 `api key` / `apikey` 前缀）。

**Risk:** 低。测试已经覆盖误伤防护。但缺乏显式说明可能导致未来维护者不理解 regex 的设计意图，在修改时错误移除 word boundary 或 assignment operator guard。

**Recommendation:**
- 在 `diagnostic_text.py` 模块 docstring 中说明 word-boundary + assignment-operator 两段式 guard 是防误伤的核心机制。

**Controller action:** Accept / Reject / Defer

---

### Finding DS-08 [LOW] — Slice 2 和 Slice 3 可并行化但计划未说明为何选择串行

**Evidence:**
Slice 2 (Engine 迁移) 和 Slice 3 (Host 迁移) 都只依赖 Slice 1 的 runtime primitive，彼此之间无依赖。计划默认串行推进，未解释原因。

**Risk:** 无 correctness 风险。串行推进可降低 review 复杂度，是合理选择。

**Recommendation:**
- 在 Slice sequencing 说明中简要注明 "Slice 2 与 Slice 3 无相互依赖，串行推进仅为控制 review 复杂度"。

**Controller action:** Accept / Reject / Defer

---

## 4. Assumption Challenges

### A-01: "空字符串不被 runtime 特判为 redacted"

**Plan claim (Section 8 Slice 1):** "空字符串不被 runtime 特判为 redacted；空字符串如何显示由调用方 owner 决定。"

**Challenge:** 验证通过。Engine `_exception_diagnostic_message` 对空 `str(exc)` 返回 `exc_type.__name__`（非 redacted marker）；Host `_safe_exception_message` 对空消息返回 `exc.__class__.__name__`。Runtime 不应该替调用方决定空字符串的展示策略。

### A-02: "truncate_diagnostic_text 对非法参数 fail fast"

**Plan claim (Section 7):** "`truncate_diagnostic_text` 对 `max_chars <= 0` 或 `len(truncated_suffix) >= max_chars` fail fast `ValueError`，避免负数切片和不可见 body。"

**Challenge:** 验证通过。该防御性设计是合理的。但有一个边界情况：`max_chars == 1` 且 `len(truncated_suffix) == 1` 应该被拒绝（因为 body 长度 = 1-1=0，suffix 会完全覆盖 body），`len(truncated_suffix) >= max_chars` 条件正确捕获了此边界。

### A-03: OpenAI diagnostic payload 与 runtime text redaction 是不同质的问题

**Plan claim (Section 2):** "OpenAI diagnostic payload 处理 provider JSON object / invalid UTF-8 chunk 的 bounded diagnostic payload。它的 source/kind、provider error sub-object、top-level preview、bare hex digest 和 payload version 都是 OpenAI-compatible runner diagnostic 语义，不是通用 runtime text redaction。"

**Challenge:** 验证通过。对比代码：
- OpenAI `diagnostic_payload.py`：处理 `dict[str, JsonValue]` JSON object，有 bounded size (4096 bytes)、key-based sensitive redaction（`_SENSITIVE_KEY_FRAGMENTS`）、bare hex digest、payload version、container summary。对象级 JSON 诊断。
- Runtime `diagnostic_text.py`（计划）：处理 `str` 文本，regex-based value redaction、character-length truncation。文本级字符串诊断。

两者处理的数据类型不同（`dict` vs `str`）、敏感信息检测机制不同（key name match vs regex value match）、digest 格式不同（bare hex vs `sha256:`）、大小约束机制不同（JSON byte size vs char count）。不存在可合并的共性。

---

## 5. Slice Sequencing Review

| Slice | 依赖 | 交付物 | 可验证闭环 | 审查结论 |
|---|---|---|---|---|
| Slice 1 | 无 | `diagnostic_text.py` + runtime tests | 独立 runtime primitive + 直接测试 | **合理** |
| Slice 2 | Slice 1 | Engine 迁移 + Engine 行为测试 | Engine exception diagnostic 语义不变 | **合理** |
| Slice 3 | Slice 1 | Host 迁移 + Host 行为测试 | Host compaction diagnostic ref 语义不变 | **合理** |

Slice 切分满足三个约束：
- 模型上下文可承载：每个 slice 涉及 2-6 个文件，范围清晰。
- 代码依赖边界：Slice 1 建立 runtime owner → Slice 2/3 各自消费，依赖单向。
- 可独立验证：每个 slice 有独立测试命令和 completion signal。

**唯一改进建议 (DS-08):** 注明 Slice 2/3 的串行选择理由。

---

## 6. Testing Gaps

| ID | Gap | Severity | 关联 Finding |
|---|---|---|---|
| TG-01 | Runtime test 缺少 `api-key:<value>` dash+colon 变体 | MEDIUM | DS-04 |
| TG-02 | Runtime test 缺少 `redacted_value` 含 backslash 的边缘行为 | MEDIUM | DS-01 |
| TG-03 | Host test 的 `_SensitiveFailingCompactor` 未覆盖 `password=` 和 `api key ` 空格 | MEDIUM | DS-05 |
| TG-04 | Runtime test 缺少 `len(message) == max_chars` 精确边界 | MEDIUM | DS-03 |
| TG-05 | Runtime test 缺少 `redact + truncate` 组合路径（先 redact 再 truncate，模拟 Host 调用方策略） | LOW | — |
| TG-06 | Runtime test 缺少 `redact_sensitive_diagnostic_values` 的幂等性（对已含 `<redacted>` 的文本再次调用） | LOW | — |
| TG-07 | 计划未要求 `_safe_log_message` 的 dedicated test（计划 Slice 2 说"补一条 `_safe_log_message` 对 sensitive value 整条 redacted 的直接测试"，但未具体化） | LOW | — |

**说明：** TG-01 至 TG-04 建议在 Slice 1 实施时补全。TG-05 和 TG-06 是 defense-in-depth 建议。TG-07 已在计划中提及但缺少具体参数化。

---

## 7. AGENTS 合规检查

| 规则 | 计划是否满足 | 证据 |
|---|---|---|
| 动机先判断 | **满足** | Section 2 对比了两处代码的 regex 和 truncation 重复，提供了直接代码引用 |
| 质疑用户路径 | **满足** | 正确拒绝了 OpenAI diagnostic payload、runtime digest、tool_truncation 的下沉，收窄为 diagnostic text primitive |
| 禁止 `Any`/`object`/无类型签名 | **满足** | 所有 API 签名使用 `str` / `bool`，Section 6 non-goals 明确禁止 |
| 禁止 `hasattr`/`getattr` | **满足** | API 不涉及动态属性访问 |
| 禁止 lazy import / glue seam | **满足** | 无 lazy import；模块只 import `re` 和 `typing.Final` |
| 禁止兼容性代码 | **满足** | Section 6 明确 "不做兼容性 wrapper / facade / re-export" |
| 禁止魔法数字/字符串 | **满足** | 所有常量使用模块级 `Final`，作为显式参数传入 |
| runtime 不 import 上层 | **满足** | 计划明确约束，且 `test_import_boundary.py` 自动守护 |
| 禁止 callback/factory/profile/query | **满足** | API 为朴素 `str -> str` / `str -> bool` 函数 |
| 显式参数不入 extra payload | **满足** | `redacted_value`、`max_chars`、`truncated_suffix` 均为显式 keyword-only 参数 |

**未发现 AGENTS 违规。**

---

## 8. Design Doc Alignment

| 设计真源条款 | 计划对齐 |
|---|---|
| `dayu.runtime` 只能承载层中立、运行期通用、可被多层复用的基础能力 (design.md:61-65) | **对齐** — `diagnostic_text` 只做 secret-value detection / redaction / bounded truncation，不知道 Exception / Host / Engine / provider |
| `dayu.runtime` 不得 import 业务层 (design.md:65) | **对齐** — 模块只 import 标准库 |
| 各层优先复用或扩展 runtime (design.md:65) | **对齐** — Engine 和 Host 删除私有实现，改为调用 runtime primitive |
| 公共契约优先直接传参数 (AGENTS.md:33) | **对齐** — 三个函数均为直接参数，无 callback/factory/profile/query |

---

## 9. Risk Register Review

计划 Section 11 列出 5 项 residual risks。逐项审查：

| Risk | 审查结论 |
|---|---|
| Regex unification may broaden Host detection → security-hardening diagnostic-only change | **同意。** 建议补充完整的新增检测模式列表 (DS-02) |
| Engine whole-message vs Host value redaction 差异不能 collapse | **同意。** 计划 API 设计正确保留了两条调用路径 |
| OpenAI diagnostic payload intentional separation | **同意。** 正确拒绝 |
| `_digest.py` 无 dedicated direct test | **同意。** 不在此 WU 做 |
| README updates intentionally minimal | **同意。** 符合 README 职责边界 |

**建议新增 residual risk:**
- `RR-LAYER-02-01`: `redact_sensitive_diagnostic_values` 的 replacement 参数若含 backslash 会被 `re.sub()` 解释。若未来有调用方传入含 `\1` 的 marker，将产生意外行为。Owner: `diagnostic_text.py` 实现者；Mitigation: 在 docstring 中明确说明，或对 replacement 使用 `re.escape()`。

---

## 10. Open Questions

| ID | Question | 建议 |
|---|---|---|
| OQ-01 | `truncate_diagnostic_text` 的 `max_chars` 是字符数（`len(str)`）而非字节数（`len(str.encode())`）。对 CJK 等多字节字符，240 chars 可能对应 >240 bytes。这是否是期望行为？ | Engine 和 Host 当前都用 `len(message)` 做字符截断，保持一致即可。不是本 WU 需要改变的行为。 |
| OQ-02 | `contains_sensitive_diagnostic_value` 是否需要对 `Bearer` 后的 token-like value 做最小长度校验（如 `Bearer A` 不应被当作 secret）？ | 当前 Engine/Host 的 Bearer regex 要求 `[A-Za-z0-9._~+/=-]+`（至少 1 字符），未设最小长度。保持与现状一致即可。 |
| OQ-03 | 是否需要处理 `redact_sensitive_diagnostic_values` 返回的字符串长度 > `max_chars` 导致后续 `truncate_diagnostic_text` 必然截断的情况？ | 这是 Host 调用方的组合策略问题（先 redact 再 truncate），runtime 不需要感知。调用方负责以正确顺序组合调用。 |

---

## 11. Verdict

**Verdict: PASS**

The plan is code-generation-ready for Slice 1. The motivation is real, the scope is correctly narrowed, the rejected candidates are correctly rejected, and the API design preserves both Engine whole-message redaction and Host value redaction policies.

**条件：** 以下 MEDIUM findings 应在 Slice 1 实施前或实施中修正（不要求回到 plan fix loop，可在 implementation 中直接处理）：

1. **DS-01** — `redacted_value` 的 `re.sub()` backslash 风险：在 docstring 中说明约束，或对 replacement 做 `re.escape()`。
2. **DS-02** — Slice 3 exact changes 中完整列出 Host 迁移后的新增检测模式。
3. **DS-03** — `truncate_diagnostic_text` no-op 语义显式化（`len(message) <= max_chars` 原样返回）。
4. **DS-04** — Runtime test 补充 `api-key:<value>` dash+colon 变体。
5. **DS-05** — Host test 的 `_SensitiveFailingCompactor` 消息补充 `password=` 和 `api key ` 空格模式。

**LOW findings (DS-06, DS-07, DS-08) 不阻塞实施**，实施者可根据判断采纳。

**未发现 HIGH severity 的 blocking 问题。**
