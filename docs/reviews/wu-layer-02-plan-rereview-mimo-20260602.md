# WU-LAYER-02 Plan Re-Review — MiMo

- Gate: plan re-review
- Reviewer: MiMo
- Date: 2026-06-02
- Revised artifact: `docs/host/wu-layer-02-shared-runtime-helper-consolidation-plan.md`
- Original review: `docs/reviews/wu-layer-02-plan-review-mimo-20260602.md`
- Controller adjudication: `docs/reviews/wu-layer-02-plan-review-controller-adjudication-20260602.md`

## Accepted Fix Verification

逐条对照 controller adjudication 中 accepted plan fixes 与修订后 plan 的落地情况。

### PF-01 / DS-02: Regex 差异矩阵 [Verified]

Plan §7 新增 "Engine / Host 当前 regex 差异矩阵" 表（lines 142-153），覆盖：

- Bearer `\b` word-boundary 差异
- `api key <value>` 空格写法：Engine 覆盖、Host 不覆盖、Runtime 覆盖、Host migration 后新增命中
- `api_key=<value>` / `api-key=<value>`：双方覆盖、无新增
- `api-key:<value>` / `api-key: <value>`：Engine 覆盖、Host 当前不覆盖、Runtime 覆盖、新增命中
- `apikey=<value>`：Engine 覆盖、Host `api[_-]?key` 不覆盖无分隔 `apikey`、新增命中
- `password=<value>`：Engine 覆盖、Host 不覆盖、新增命中
- `authorization` / `token` / `secret` 赋值：双方覆盖、无新增
- 捕获组差异：Engine 不需要、Host 使用捕获组、Runtime 必须捕获前缀

**落地：完整。**

### PF-02 / TG-07: `_safe_log_message` 测试矩阵 [Verified]

Plan §8 Slice 2 Exact changes（lines 267-271）新增四个 bullet：

1. 空字符串和全空白字符串 → `_EXCEPTION_MESSAGE_REDACTED`
2. 包含 sensitive value → 整条 `_EXCEPTION_MESSAGE_REDACTED`
3. 普通超长消息按常量截断
4. `JWT token has expired` 等不误伤，未超长时原样返回

**落地：完整。**

### PF-03 / DS-03: `truncate_diagnostic_text` no-op 语义 [Verified]

Plan §7（line 137）新增："`truncate_diagnostic_text` 在 `len(message) <= max_chars` 时 no-op，必须原样返回 `message`；空字符串也是 no-op。"

Plan §8 Slice 1 test cases（line 201）新增："`truncate_diagnostic_text` 在 `len(message) < max_chars` 与 `len(message) == max_chars` 时 no-op 原样返回；exact-boundary case 必须直接断言。"

Line 203 增加空字符串显式断言：三个函数对空字符串输入均返回 `False` / `""` / `""`。

**落地：完整。**

### PF-04: `_exception_diagnostic_suffix` 空消息路径 [Verified]

Plan §8 Slice 3 Exact changes（line 328）新增："增加覆盖 `_exception_diagnostic_suffix` 空消息路径：当异常 `str(exc)` 为空时，suffix 只返回异常类名，不拼接 `:<message>`，保持 Host 现有语义。"

**落地：完整。**

### DS-01 / DS-06: `redaction_marker` 字面替换 [Verified]

- API 签名已从 `redacted_value` 改为 `redaction_marker`（line 117）。
- §7 Semantics（line 135）新增："`redaction_marker` 是替换敏感值的字面文本，不是待脱敏原文。实现必须用 callable replacement 或等效方式传给 `re.sub()`，保证 marker 中的 `\1`、`\g<name>`、反斜杠等字符不会被 regex replacement 解释。"
- §8 Slice 1 Exact changes（line 193）重申 marker 字面文本约束。
- §8 Slice 1 test cases（line 200）新增："`redaction_marker` 包含反斜杠、`\1` 或类似 group reference 文本时必须按字面值进入结果。"
- §8 Slice 3（line 318）已更新为 `redaction_marker=_REDACTED_SECRET`。

**落地：完整。**

### DS-04: `api-key` 冒号变体测试 [Verified]

Plan §7 Semantics（line 131）已列出 `api-key:<value>` 和 `api-key: <value>`。

Plan §8 Slice 1 test cases（line 197）已列出 `api-key:<value>` / `api-key: <value>` 检测。

**落地：完整。**

### DS-05: Host compaction 新增模式测试 [Verified]

Plan §8 Slice 3 Exact changes（lines 324-326）更新 `_SensitiveFailingCompactor` 异常消息覆盖：`password=<value>`、`api key <value>`、`apikey=<value>`、`api-key:<value>` / `api-key: <value>`。

Line 326 明确列出 Host migration 后新增检测范围。

**落地：完整。**

### DS-07: False-positive guard 设计说明 [Verified]

Plan §7（line 140）新增完整 paragraph："Runtime regex 采用 word-boundary + assignment-operator guard 作为 false-positive 控制：敏感 key 前需要词边界，`authorization` / `password` / `secret` / `token` 等普通词只有后接 `:` 或 `=` 才命中；`api key` / `apikey` 类 key 才允许空白分隔的 value。这是为了保留 `JWT token has expired`、`Content-Type header is invalid` 等普通诊断文本。"

**落地：完整。**

### DS-08: Slice 2/3 Sequencing Note [Verified]

Plan §8（lines 164-166）新增 "Sequencing note"：明确 Slice 2 与 Slice 3 都只依赖 Slice 1，彼此无依赖；串行推进是为了缩小 review 变更面。

**落地：完整。**

## Additional Observations

### Regex Table 补充核对

原始 review F-01 提到 Engine pattern 覆盖 `password` 而 Host 不覆盖。差异矩阵已正确记录（line 151）：Host migration 后新增 `password=<value>` 命中。

原始 review F-01 提到 `\b` 边界差异。差异矩阵已正确记录（line 146）：Runtime 采用 Engine 风格 `\b` word-boundary，Host 收窄误伤面。

### `api-key:<value>` 新增命中准确性

差异矩阵（line 149）标注 Engine 当前已覆盖 `api-key:<value>` / `api-key: <value>`，Host 当前不覆盖，migration 后新增命中。这是准确的——Engine 的 `_API_KEY_VALUE_PATTERN` 使用 `api[ _-]?key` 匹配 `api-key`，且 `(?::|=|\s+)` 匹配 `:`；Host 的 `api[_-]?key` 也匹配 `api-key`，但 `[:=]` 不匹配 `:` 后跟空格的 `api-key: <value>` 变体。

### Slice 1 Redaction Idempotency

Line 204 新增 "增加 redaction 幂等性测试，即重复 redaction 不继续改变结果"。这是良好的防御性测试，确保 runtime primitive 的正确幂等性。

## Implementation-Entry Blocker Check

| 检查项 | 状态 |
|---|---|
| 所有 accepted plan fixes 已落地 | ✅ |
| Regex 差异矩阵完整 | ✅ |
| `_safe_log_message` 测试矩阵明确 | ✅ |
| 空字符串 no-op 语义已定义 | ✅ |
| `_exception_diagnostic_suffix` 空消息覆盖 | ✅ |
| `redaction_marker` 字面替换约束 | ✅ |
| False-positive guard 设计说明 | ✅ |
| Slice sequencing 说明 | ✅ |
| 无新增 scope creep 或架构变更 | ✅ |
| AGENTS.md 约束仍覆盖 | ✅ |

## Verdict

**PASS — 无 implementation-entry blocker。Plan code-generation-ready，可进入 Slice 1 implementation。**
