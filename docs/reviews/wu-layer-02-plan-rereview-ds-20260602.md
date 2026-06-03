# WU-LAYER-02 Plan Re-review — DS 2026-06-02

## Re-review Metadata

- **Role:** plan review specialist (DS), adversarial re-review only — 不修改计划、代码或测试
- **Revised plan:** `docs/host/wu-layer-02-shared-runtime-helper-consolidation-plan.md`
- **Original DS review:** `docs/reviews/wu-layer-02-plan-review-ds-20260602.md`
- **Controller adjudication:** `docs/reviews/wu-layer-02-plan-review-controller-adjudication-20260602.md`
- **Scope:** 确认 controller adjudication 中全部 10 项 accepted plan fixes 是否落地，以及是否仍有 implementation-entry blocker

---

## 1. Accepted Fix Verification Matrix

| Fix ID | 来源 | Controller 要求 | 修订后计划行号 | 状态 |
|---|---|---|---|---|
| PF-01 / DS-02 | MiMo, DS | Regex 差异矩阵：Engine vs Host Bearer word-boundary、`api key ` 空格、`apikey`、`password=`、`api-key:<value>` 差异 | Section 7 行 142-153 | **CLOSED** |
| PF-02 / TG-07 | MiMo, DS | Slice 2 `_safe_log_message` 测试矩阵：blank/whitespace、sensitive 整条 redacted、普通 truncation、`JWT token` false-positive guard | Slice 2 行 267-271 | **CLOSED** |
| PF-03 / DS-03 | MiMo, DS | `truncate_diagnostic_text` no-op 语义显式化 + exact-boundary 测试 | Section 7 行 137; Slice 1 行 201 | **CLOSED** |
| PF-04 | MiMo | Slice 3 `_exception_diagnostic_suffix` 空消息路径测试 | Slice 3 行 328 | **CLOSED** |
| DS-01 / DS-06 | DS | `redacted_value` → `redaction_marker`，字面替换不进 `re.sub()` backslash 解释 | Section 7 行 117, 135; Slice 1 行 200; Layer mapping 行 158; Slice 3 行 318 | **CLOSED** |
| DS-04 | DS | Slice 1 runtime tests 显式覆盖 `api-key:<value>` 和 `api-key: <value` 变体 | Section 7 行 131; Slice 1 行 197 | **CLOSED** |
| DS-05 | DS | Slice 3 `_SensitiveFailingCompactor` 消息覆盖 `password=` 和 `api key <value>` + 逐项泄漏断言 + 新增检测范围枚举 | Slice 3 行 324-326 | **CLOSED** |
| DS-07 | DS | Word-boundary + assignment-operator guard 作为 false-positive 控制的设计说明 | Section 7 行 140 | **CLOSED** |
| DS-08 | DS | Slice 2/3 串行推进理由说明 | Section 8 行 164-166 | **CLOSED** |

**全部 10 项 accepted fixes 已验证落地，无遗漏。**

---

## 2. 关键修订质量检查

### 2.1 Regex 差异矩阵准确性

修订后计划行 142-153 的差异矩阵逐项核对：

| 矩阵声称 | 代码证据 | 结论 |
|---|---|---|
| Engine Bearer 使用 `\b`，Host 无 `\b` | Engine: `r"(?i)\bbearer\s+..."`, Host: `r"(?i)bearer\s+..."` | **准确** |
| Host 不覆盖 `api key <value>` 空格 | Host: `api[_-]?key` 不含空格 | **准确** |
| Host 不覆盖 `apikey=<value>` | Host: `api[_-]?key` 至少需要一个 `_` 或 `-` | **准确** |
| Host 不覆盖 `password=<value>` | Host: 无 `password` 在 alternation 中 | **准确** |
| `api-key:<value>` 标注 "Host 不覆盖" | Host `api[_-]?key\s*[:=]\s*` **可** 匹配 `api-key:value`；此为保守假设 | **保守但不影响正确性**（见 §2.2） |
| Engine 不需要 capturing prefix，Host 需要 | Engine 整条 redacted；Host `_ASSIGNMENT_SECRET_PATTERN` 有 capturing group | **准确** |

### 2.2 低严重观察：`api-key:<value>` 矩阵条目

**Observation (LOW, non-blocking):** 差异矩阵将 `api-key:<value>` / `api-key: <value>` 标注为 "Controller adjudication 按当前 Host 不覆盖处理"。直接代码核对显示 Host `_ASSIGNMENT_SECRET_PATTERN` = `r"(?i)((?:api[_-]?key|authorization|token|secret)\s*[:=]\s*)[^,\s}\]]+"` — 其中 `api[_-]?key\s*[:=]\s*` 确实可以匹配 `api-key:value`（`api-key` 匹配 `api[_-]?key`，`:` 匹配 `[:=]`）。但这是保守假设：将覆盖范围假设得更窄，意味着 migration 后 runtime 的覆盖范围是安全超集。不影响正确性，controller adjudication 已接受此解读。无需 plan fix。

### 2.3 `redaction_marker` 字面语义一致性

修订后计划中 `redaction_marker` 的语义贯穿全部 3 层：

| 位置 | 文本 | 语义 |
|---|---|---|
| API 签名 (行 117) | `redaction_marker: str` | 参数名统一 |
| API semantics (行 135) | "必须用 callable replacement 或等效方式传给 `re.sub()`，保证 marker 中的 `\1`、`\g<name>`、反斜杠等字符不会被 regex replacement 解释" | 字面替换语义明确 |
| Slice 1 test (行 200) | "`redaction_marker` 包含反斜杠、`\1` 或类似 group reference 文本时必须按字面值进入结果" | 测试锁定 |
| Layer mapping (行 158) | `redaction_marker="<redacted>"` | Engine 保持 `_EXCEPTION_MESSAGE_REDACTED` 整条策略（不使用 runtime redact），Host 传入 marker 做 value redaction |
| Slice 3 (行 318) | `redaction_marker=_REDACTED_SECRET` | Host 保留私有 `_REDACTED_SECRET = "<redacted>"` |

Engine Agent 的整条 redacted 策略（`_exception_diagnostic_message` / `_safe_log_message`）使用 `contains_sensitive_diagnostic_value` 检测 + 私有 `_EXCEPTION_MESSAGE_REDACTED` marker，**不** 调用 `redact_sensitive_diagnostic_values`。这正确保留了 Engine 和 Host 的策略差异。

### 2.4 `truncate_diagnostic_text` no-op 语义

修订后计划在 3 处锁定 no-op 语义：

- Section 7 行 137：`len(message) <= max_chars` 时 "必须原样返回 `message`；空字符串也是 no-op"
- Slice 1 行 201：`len(message) < max_chars` 与 `len(message) == max_chars` 均 no-op，"exact-boundary case 必须直接断言"
- Slice 1 行 203：空字符串在全部三个函数上的行为明确定义

对比现有代码行为：
- Engine `_exception_diagnostic_message`: `len(raw_message) > 240` 才截断，`<=` 原样 `${exc_type}: ${raw_message}` → 一致
- Host `_safe_exception_message`: `len(redacted) <= 240` 原样返回 → 一致

### 2.5 `_safe_log_message` 测试矩阵完整性

修订后 Slice 2 行 267-271 定义的测试矩阵：

| 场景 | 期望 | 覆盖当前行为？ |
|---|---|---|
| 空字符串 | `_EXCEPTION_MESSAGE_REDACTED` | Engine `agent.py:254-255` ✓ |
| 全空白字符串 | `_EXCEPTION_MESSAGE_REDACTED` | Engine `agent.py:254` `.strip() == ""` ✓ |
| 包含 sensitive value | 整条 `_EXCEPTION_MESSAGE_REDACTED` | Engine `agent.py:256-257` ✓ |
| 普通超长 (>240 chars) | 截断 + suffix | Engine `agent.py:258-263` ✓ |
| `JWT token has expired` 未超长 | 原样返回 | 现有 `test_agent_phase2.py:828-844` 间接覆盖 |

测试矩阵覆盖了 `_safe_log_message` 的全部 4 条代码路径（blank → redacted, sensitive → redacted, short-normal → pass-through, long-normal → truncate）。

### 2.6 Slice 3 Host 新增模式覆盖完整性

修订后 Slice 3 明确列出新增检测范围（行 326）：`api key <value>`、`apikey=<value>`、`password=<value>`、`api-key:<value>` / `api-key: <value>`。与差异矩阵（行 142-153）中 "是" 列完全一致。

`_SensitiveFailingCompactor` 异常消息覆盖（行 324）：`Bearer`、`api_key=`、`token=`、`secret=`（既有）+ `password=`、`api key `、`apikey=`、`api-key:`（新增）= 8 种模式。

---

## 3. 未覆盖项检查

### 3.1 原 review LOW findings 状态

| ID | 内容 | 修订后状态 |
|---|---|---|
| DS-06 | `redacted_value` 命名歧义 | **CLOSED** — 已改名为 `redaction_marker`（与 DS-01 合并处理）|
| DS-07 | False-positive guard 未显式说明 | **CLOSED** — 行 140 已增加设计说明 |
| DS-08 | Slice 2/3 串行理由未说明 | **CLOSED** — 行 164-166 已增加 sequencing note |

### 3.2 Reserved concern: Host `_REDACTED_SECRET` 命名

Host 保留私有常量 `_REDACTED_SECRET = "<redacted>"`（行 318），该常量名在原 review 中未被 challenge。随着 runtime API 参数已改为 `redaction_marker`，Host 的 `_REDACTED_SECRET` 命名与 runtime 参数名 `redaction_marker` 之间存在术语不一致（一个是 "secret"，一个是 "marker"）。这是 **LOW cosmetic** 问题，不阻塞实施，但建议 Slice 3 implementer 考虑是否将 Host 私有常量也改名为 `_REDACTION_MARKER` 以对齐术语。

---

## 4. Implementation-entry Blocker 检查

| 检查项 | 状态 |
|---|---|
| Runtime API 签名无 Any/object/无类型 | **通过** — `str -> bool`, `(str, str) -> str`, `(str, int, str) -> str` |
| Runtime 不 import 上层 | **通过** — 计划明确约束 + `test_import_boundary.py` 自动守护 |
| Engine whole-message redaction 保留 | **通过** — Layer mapping 行 157 明确 |
| Host value redaction 保留 | **通过** — Layer mapping 行 158 明确 |
| OpenAI diagnostic payload 不下沉 | **通过** — Section 5 明确拒绝 |
| `_digest.py` 语义不变 | **通过** — Section 5 明确拒绝 |
| 无 callback/factory/profile/query | **通过** — 三个朴素函数 |
| 无 compat wrapper/re-export | **通过** — Section 6 明确禁止 |
| 无 hasattr/getattr | **通过** — API 不涉及 |
| 三个 slices allowed files 不交叉 | **通过** — Slice 2/3 分别只改各自层文件 |
| 每个 slice 有独立验证命令 | **通过** — Section 8 各 slice 有明确 pytest + pyright 命令 |
| Stop conditions 在 API 过宽时可阻止 | **通过** — 每个 slice 有明确 stop condition |

**未发现 implementation-entry blocker。**

---

## 5. Verdict

**PASS — Plan is code-generation-ready for Slice 1.**

全部 10 项 controller-accepted plan fixes 已验证落地。修订后计划在以下关键维度均已收敛到可实施精度：

- Regex 差异矩阵完整且代码证据对齐（1 项保守假设不影响正确性）
- `redaction_marker` 字面语义贯穿 API、实现约束、测试和两个调用方
- `truncate_diagnostic_text` no-op 语义在 API 和测试层面双重锁定
- `_safe_log_message` 测试矩阵覆盖全部 4 条代码路径
- Host migration 新增检测模式逐项枚举并与差异矩阵一致
- Word-boundary + assignment-operator false-positive guard 设计意图已记录
- Slice 2/3 串行推进理由已说明

唯一的低严重观察（§2.2 `api-key:<value>` 矩阵保守假设、§3.2 Host `_REDACTED_SECRET` 命名不一致）不阻塞实施。
