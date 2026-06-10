# WU-TOOLS-01-F03 Plan Re-Review — AgentMiMo

## Reviewed Target

- 文件：`docs/host/wu-tools-01-f03-web-ci-smoke-plan.md`（已由 AgentCodex 依据 controller adjudication 修正）
- 前序 review：`docs/reviews/wu-tools-01-f03-plan-review-mimo.md`
- Controller adjudication：`docs/reviews/wu-tools-01-f03-plan-review-controller-adjudication.md`
- Peer review：`docs/reviews/wu-tools-01-f03-plan-review-ds.md`
- 日期：2026-06-10

## Re-Review Scope

仅检查 controller adjudication 中标记为 `accepted` 的 findings 是否已在 plan 中修复。不检查 `accepted-with-note` / `accepted-low` / `deferred-with-owner` 项（这些不需要 plan 修正）。

---

## Finding Status

### 1. PDF Docling route evidence — 从静态推断改为 diagnostics-side narrow wrapper instrumentation

**原 finding**：MiMo F-1 / DS F-1 — diagnostics payload 无数据源证明 Docling route；plan 只留 Stop condition 未给解决方案。

**Controller 指令**：diagnostics-side instrumentation around Docling conversion callable。PDF pass 要求 recorded invocation evidence，不修改 production LLM-facing success payload。

**Plan 当前状态**：

- Slice 1 line 157-161：明确定义窄 wrapper instrumentation，wrapper 只在 diagnostic run 内安装，`finally` 恢复原始 callable，必须调用原始函数，记录 `invoked`、`stream_name`、`raw_bytes_length`、`target_module`、`target_function`、`original_completed`、`original_exception_type`、`docling_runtime_initialization_error`、`diagnostic_url`。
- Slice 1 line 161：明确 "记录对象只写入 diagnostics artifact，不写入 `ToolCompletedOutcome.result.value`，不暴露给生产 LLM-facing payload"。
- Line 59（第一性原理判断）：明确 "diagnostic run 内必须对当前 Web module 的 Docling conversion callable 做窄 instrumentation，wrapper 记录调用证据后委托原始函数执行"。
- Line 72（代码证据）：明确 "F03 不把 `extraction_source` 或其它 implementation-only 字段加入 production `fetch_web_page` LLM-facing success payload"。
- Slice 3 line 359：PDF pass 条件要求 "`docling_conversion_invocation_evidence.invoked=True`，`stream_name="page.pdf"`，原始 Docling callable completed"。
- Slice 1 line 217-219（Stop condition）：wrapper 无法观察到 invocation 时停止，不得退回 static code inference 或修改 production payload。

**判定**：**已修复**。Plan 从"无数据源"改为"diagnostics-side wrapper 记录实际 invocation evidence"，方案与 controller 指令完全对齐。不再依赖 content-type + fetch success + 静态代码推断。production LLM-facing payload 不变。

---

### 2. Playwright skipped + requests/fetch success 的 HTML pass 判定

**原 finding**：MiMo F-2 — `_classify_diagnostic_bucket` 没有"Playwright skipped + requests ok + fetch ok"的 bucket，该组合落入 `partial_sample`，HTML smoke 判定不可行。

**Controller 指令**：定义新 bucket 或直接从 diagnostics facts 定义 local HTML pass。

**Plan 当前状态**：

- Slice 1 line 178：明确 "计划采用 diagnostics facts 判定，不强制新增 bucket：smoke classification 直接读取 `requests_profile.result.ok=True`、`fetch_web_page_profile.ok=True`、`playwright_profile.sampled=False`"。同时允许 implementation 新增 additive bucket `requests_and_fetch_success_playwright_skipped` 作为辅助事实。
- Slice 2 line 290（映射表）：明确 "return code `0`，requests ok + fetch ok，但 Playwright skipped → pass；不要求 `all_success` bucket"。
- Slice 3 line 358：HTML pass 条件 "默认 `--skip-playwright` 时，`playwright_profile.sampled=False` 不影响 pass，也不要求 `comparison_bucket=all_success`"。
- Slice 3 line 391（Expected assertions）："Playwright skipped + requests ok + fetch ok 的 HTML payload pass"。

**判定**：**已修复**。Plan 采用 facts-based 判定而非依赖 bucket 名，彻底解决了 `partial_sample` 误分类问题。

---

### 3. PDF fixture 要求稳定可抽取文本、最小内容断言、空/过短 fail

**原 finding**：MiMo F-3 / DS F-2 / DS F-4 — `_MINIMAL_PDF` 无文本内容，Docling 可能返回空 markdown；plan 未定义 fixture 规范和空内容判定。

**Controller 指令**：PDF fixture 必须含稳定可抽取文本，最小内容断言，空/过短 = fail（Docling init skip 除外）。

**Plan 当前状态**：

- Line 116："`/fixture.pdf` 使用很小但含稳定可抽取文本的 PDF bytes；不得复用空白或无文本 minimal PDF。响应头必须是 `Content-Type: application/pdf`，fixture 文本需包含固定短句并满足 smoke 的最小内容断言。"
- Slice 3 line 353-356：明确定义 "PDF 必须包含固定可抽取英文文本，例如 `Dayu Web Smoke PDF` 与 `This PDF verifies Docling conversion.`"，定义 `PDF_FETCH_MIN_CHARS` 最小值不得低于 20，"如果现有 minimal PDF 为空白或不能稳定抽取文本，不得复用；应在 smoke 脚本内定义新的小型文本 PDF fixture"。
- Slice 3 line 360："PDF fetch 成功但内容为空/过短必须 fail，不能因为 fetch ok 或 content-type 正确而 pass。"
- Slice 2 line 292（映射表）：local PDF fetch ok 但 content 为空或短于 `PDF_FETCH_MIN_CHARS` → fail。
- Line 555（Risks）："只要 Docling callable completed 且 `fetch_web_page` 成功返回，内容为空/过短就是 local PDF fail，必须调整 fixture 或修正真实 bug，不得跳过 PDF route。"

**判定**：**已修复**。Fixture 规范、最小内容常量、空/过短 fail 规则均已明确。

---

### 4. diagnostics observed facts 与 smoke classification 分离

**原 finding**：DS F-3 — `primary_failure_bucket`、`suggested_next_step` 等字段混杂诊断事实与 smoke 判定语义。

**Controller 指令**：分离 diagnostics facts 与 smoke classification，或重命名字段使 diagnostics 描述 observed facts。

**Plan 当前状态**：

- Slice 1 line 163-169：字段已重命名为诊断视角术语：`observed_bucket`（替代 `primary_failure_bucket`）、`observed_failing_path`（替代 `primary_failure_path`）、`diagnostic_action_hint`（替代 `suggested_next_step`）、`diagnostic_only_reason`。
- Slice 1 line 156：helper 输出 "诊断事实与 diagnostic action hint，不输出 smoke primary failure"。
- Slice 2 line 271-275（Smoke classification ownership）：明确分离 — "Diagnostics 输出 observed facts：URL、profiles、bucket、schema version、content-type、content length、Docling invocation evidence、diagnostic action hint" vs "Smoke wrapper 输出 classification：`passed` / `failed` / `skipped` / `diagnostic_only`，以及 smoke-specific `primary_failure_bucket`、`suggested_next_step`、exit code"。
- Slice 2 line 275："不把 smoke-specific primary failure 语义写回 diagnostics，除非字段名清楚表明只是 diagnostic action hint"。
- Line 129-130（Implementation Decisions #4）："`utils/smoke_web_ci.py` 负责 smoke-specific pass/fail/skip/diagnostic-only classification、primary failure 和 suggested next step。若 diagnostics 中保留 action hint，命名必须清楚表明只是 `diagnostic_action_hint`，不得混同 smoke primary failure 语义。"

**判定**：**已修复**。字段已重命名为诊断视角，职责分离在 plan 中显式声明。

---

### 5. schema/version gap 与 `diagnostic_schema_gap` failure path

**原 finding**：MiMo F-4 — 无 schema version 检查，旧版 diagnostics + 新版 smoke 会误报。

**Controller 指令**：schema/version validation 和 clear `diagnostic_schema_gap` failure path。

**Plan 当前状态**：

- Slice 1 line 155：新增模块级常量定义 diagnostics schema/version。
- Slice 1 line 169、176：batch row 和 summary 追加 `diagnostic_schema_version`。
- Slice 2 line 254-259：smoke 读取 diagnostics artifact 前必须执行 schema validation — 检查 `diagnostic_schema_version` 存在、version 满足最低版本、local HTML/PDF 必需 facts 存在；不满足时生成 `diagnostic_schema_gap` failure。
- Slice 2 line 289（映射表）：schema missing / version too old / required facts missing → `diagnostic_schema_gap`，exit code `2`。
- Slice 1 line 187："缺少 schema version、version 低于 smoke 需求、缺少 `docling_conversion_invocation_evidence` 等必需字段时，smoke 应把它分类为 `diagnostic_schema_gap` failure，而不是静默 fallback。"

**判定**：**已修复**。schema validation 逻辑、version check 和 `diagnostic_schema_gap` failure path 均已明确。

---

### 6. 子进程输出到 smoke 判定的映射表

**原 finding**：DS F-5 — 子进程 return code 非 0 有多种原因，plan 统一为 "local case fail"，缺少分类路径映射。

**Controller 指令**：包含 mapping table for diagnostic subprocess results、JSON parsing failure、Docling init skip、local HTML/PDF fail、external diagnostic-only。

**Plan 当前状态**：

- Slice 2 line 284-297：完整的 10 行映射表，覆盖：
  - return code 0 + schema valid + requests/fetch ok → pass（HTML）/ 继续检查（PDF）
  - return code 0 + schema gap → `diagnostic_schema_gap`，exit code 2
  - return code 0 + Playwright skipped → pass（HTML）/ diagnostic-only（external）
  - return code 0 + PDF content-type 非 PDF → fail
  - return code 0 + PDF content 空/过短 → fail
  - return code 0 + Docling invocation evidence 缺失 → fail
  - return code 0 或非 0 + Docling dependency/init failure → skip
  - return code 非 0 + 非 Docling init error → fail
  - 无 artifact / JSON parse failure → infrastructure failure，exit code 2
  - server 启动失败 / artifact 写入失败 / CLI 参数非法 → exit code 2

**判定**：**已修复**。映射表完整覆盖所有 controller 指令要求的 case。

---

### 7. Shell wrapper optionality（DS F-7，accepted-with-note）

**原 finding**：plan 说 wrapper 可选但 validation 中总包含 `bash -n`，implementation agent 不知是否必须创建。

**Controller 指令**：accepted-with-note — 如果创建则验证，否则不列。

**Plan 当前状态**：

- Slice 2 line 327："如果创建 `utils/smoke_web_ci.sh`，`bash -n` wrapper pass；如果不创建 wrapper，implementation report 不列 `bash -n` 作为已执行验证。"

**判定**：**已修复**（此为 accepted-with-note，plan 修正已到位）。

---

### 8. External/browser/provider residual ownership（MiMo residuals / DS F-8，accepted）

**原 finding**：residual 转移缺少具体 Issue 编号或 owner。

**Controller 指令**：closeout 必须关闭或转移到具体 owner/issue。

**Plan 当前状态**：

- Line 579-585：列出三类 residual 转移，每类要求 "转移到具体 ... issue 或明确 owner 角色"。
- Line 585："不得留下无 owner residual。若 closeout 时无法写出具体 GitHub Issue 编号、控制文档条目或明确 owner 角色，不得关闭 `WU-TOOLS-01-S5-R2`，必须停止让用户裁决。"

**判定**：**已修复**（此为 accepted，plan 已有明确约束）。

---

### 9. Line references 和 status naming（MiMo F-5 / F-6，accepted-low）

**原 finding**：行号引用偏大；`diagnostic_only` status 值与同名字段冲突。

**Controller 指令**：accepted-low — amend where cheap。

**Plan 当前状态**：

- Line 70：引用改为 `818`-`879`，范围合理（包含路由判断和非 HTML 分支）。
- `diagnostic_only` status（line 261）与 `diagnostic_only` summary 字段名（line 267）仍共存，但 Slice 2 line 271-275 的 ownership 分离说明已缓解混淆风险。

**判定**：**部分修复** — 行号引用已改善；`diagnostic_only` 命名歧义仍存在但被 ownership 说明缓解。此为 accepted-low，不阻塞。

---

## New Issues Introduced by Amendments

无新增 blocking issue。修正后的 plan 在以下方面引入了新复杂度，但均有充分处理：

1. **Wrapper instrumentation 维护风险**：Line 557 承认 "Diagnostics wrapper instrumentation 可能随生产 callable 名称或装配方式变化而失效"，并要求 "失效时应产生 `diagnostic_schema_gap` 或 local PDF fail，不能静默退回 static code inference"。这是合理的失效模式处理。

2. **`--allow-private-network-url` 安全边界**：Line 558 确认 "这是诊断脚本显式 opt-in，不得弱化默认 URL 安全策略"。无新增风险。

---

## Residual Risks

| 风险 | 严重性 | 说明 |
|---|---|---|
| Docling 版本/平台兼容性 | Low | Plan 已明确 skip 判定逻辑和最小内容断言，比原 review 的 Medium 降级。 |
| Wrapper 随生产 callable 变化失效 | Low | Plan 要求失效时产生 `diagnostic_schema_gap` 或 fail，不静默退回推断。 |
| `diagnostic_only` 命名歧义 | Very Low | ownership 分离说明已缓解，implementation agent 可按 plan 行事。 |

---

## Final Recommendation

**pass**

所有 controller adjudication 中标记为 `accepted` 的 findings 均已在 plan 中修复或充分处理：

| 原 finding | 状态 |
|---|---|
| PDF Docling route evidence（MiMo F-1 / DS F-1） | 已修复 |
| Playwright skipped + requests/fetch success（MiMo F-2） | 已修复 |
| PDF fixture 稳定文本 + 最小内容断言（MiMo F-3 / DS F-2 / DS F-4） | 已修复 |
| diagnostics facts 与 smoke classification 分离（DS F-3） | 已修复 |
| schema/version gap + `diagnostic_schema_gap`（MiMo F-4） | 已修复 |
| 子进程输出映射表（DS F-5） | 已修复 |
| Shell wrapper optionality（DS F-7） | 已修复 |
| Residual ownership（DS F-8） | 已修复 |
| Line references / status naming（MiMo F-5 / F-6） | 部分修复（accepted-low，不阻塞） |

Plan 可以进入 implementation。
