# WU-TOOLS-01-F03 Plan Re-Review — AgentDS

## Re-Review Target

- **Reviewed plan**: `docs/host/wu-tools-01-f03-web-ci-smoke-plan.md` (post-controller-adjudication amended version)
- **Previous DS review**: `docs/reviews/wu-tools-01-f03-plan-review-ds.md`
- **Controller adjudication**: `docs/reviews/wu-tools-01-f03-plan-review-controller-adjudication.md`
- **Peer review (reference)**: `docs/reviews/wu-tools-01-f03-plan-review-mimo.md`
- **Re-review date**: 2026-06-10

## Re-Review Scope

只检查 controller adjudication 中 accepted findings 是否已在 amended plan 中修复。不检查 accepted-with-note / accepted-low / deferred 项是否需要进一步动作（这些已在 adjudication 中裁决，不属于 re-review 阻塞范围）。

---

## Finding Status

### Finding 1 [DS-F1 / MiMo-F1] — PDF Docling route evidence: 从静态推断改为 diagnostics-side narrow wrapper instrumentation

**Controller adjudication**: accepted. 要求 diagnostics-side instrumentation around current Docling conversion callable，PDF pass 需要 recorded invocation evidence，不修改 production LLM-facing tool output。

**Plan evidence**:
- Line 59-60: "diagnostic run 内必须对当前 Web module 的 Docling conversion callable 做窄 instrumentation，wrapper 记录调用证据后委托原始函数执行"
- Line 127-128: `docling_conversion_invocation_evidence` 字段 "必须来自 diagnostic run 内对 `dayu.tools.web.web_tools._docling_convert_to_markdown` 的窄 wrapper 调用记录"
- Lines 157-161: wrapper 只在本 diagnostic run 安装、`finally` 恢复、调用原始函数、不吞异常、记录 `invoked/stream_name/raw_bytes_length/target_module/target_function/original_completed/original_exception_type/docling_runtime_initialization_error/diagnostic_url`
- Line 161: "记录对象只写入 diagnostics artifact，不写入 `ToolCompletedOutcome.result.value`，不暴露给生产 LLM-facing payload"
- Line 72: "Docling route evidence 只能写入 diagnostics artifact"
- Line 178: `_build_single_diagnostic_payload()` 追加 `docling_conversion_invocation_evidence`，"该字段必须来自 wrapper 记录的实际 invocation"
- Line 128: 字段说明必须标注"它是诊断观察事实，不是财报事实、站点事实或 production tool public output"
- Slice 1 stop condition (line 219-220): 若 wrapper 无法观察到 Docling callable invocation，"停止；不得退回 content-type + fetch success + static code inference，也不得修改 production success payload"

**Status**: **已修复**

Plan 已从 code-route inference 方案完整转为 diagnostics-side narrow wrapper instrumentation 方案。wrapper 的安装/恢复/委托/记录语义明确，证据字段归属清晰（只写入 diagnostics artifact），production `fetch_web_page` LLM-facing payload 明确不修改。

---

### Finding 2 [MiMo-F2] — Playwright skipped + requests/fetch success 的 HTML pass 判定

**Controller adjudication**: accepted. 要求 plan 明确 diagnostic bucket 或直接基于 diagnostics facts 判定。

**Plan evidence**:
- Lines 178-179: "对 Playwright skipped + requests/fetch 成功的 local HTML 场景，计划采用 diagnostics facts 判定，不强制新增 bucket：smoke classification 直接读取 `requests_profile.result.ok=True`、`fetch_web_page_profile.ok=True`、`playwright_profile.sampled=False`。若 implementation 选择新增 bucket，也必须是 additive bucket，例如 `requests_and_fetch_success_playwright_skipped`，并保留 facts 判定。"
- Line 121: "若 Playwright 被 skip，不要求 `comparison_bucket=all_success`"
- Mapping table row (line 291): "return code `0`，requests ok + fetch ok，但 Playwright skipped | pass；不要求 `all_success` bucket"

**Status**: **已修复**

Plan 明确了两条路径：(a) 直接基于 diagnostics facts 判定（`requests ok + fetch ok + playwright not sampled`），不依赖 bucket 名；(b) 若 implementation 选择新增 bucket，必须是 additive。这消除了原 review 中 "`partial_sample` 导致 HTML pass 判定不可行" 的阻塞。

---

### Finding 3 [DS-F2 / MiMo-F3] — PDF fixture 稳定可抽取文本与最小内容断言

**Controller adjudication**: accepted. 要求 PDF fixture 含稳定可抽取文本、最小内容断言、空/过短 fail。

**Plan evidence**:
- Line 116: "使用很小但含稳定可抽取文本的 PDF bytes；不得复用空白或无文本 minimal PDF"
- Lines 354-356: "PDF 必须包含固定可抽取英文文本，例如 `Dayu Web Smoke PDF` 与 `This PDF verifies Docling conversion.`"，定义模块级常量 `PDF_FETCH_MIN_CHARS`，最小值不得低于 20 个可打印字符，"禁止用魔法数字散落"
- Line 358-359: "PDF fetch 成功但内容为空/过短必须 fail，不能因为 fetch ok 或 content-type 正确而 pass。这覆盖 Docling 静默丢弃内容的情况。"
- Mapping table row (line 293): "local PDF fetch ok，但 fetch content 为空或短于 `PDF_FETCH_MIN_CHARS` | fail，exit code `1`"
- Line 122: fail 条件明确包含 "PDF fetch 成功但内容为空/过短"

**Status**: **已修复**

Plan 明确了：(a) 不复用空白/无文本 minimal PDF；(b) 自包含新 PDF fixture，含固定英文文本；(c) `PDF_FETCH_MIN_CHARS >= 20` 模块级常量；(d) 空/过短 = fail（exit code 1），不因 content-type 正确或 fetch ok 而 pass。

---

### Finding 4 [DS-F3] — diagnostics observed facts 与 smoke classification 分离

**Controller adjudication**: accepted. 要求字段语义归属清晰：diagnostics 只输出 observed facts，smoke 负责 classification。

**Plan evidence**:
- Line 127: "diagnostics observed facts 与 smoke classification 分离"（新增小标题）
- Line 129: "`utils/smoke_web_ci.py` 负责 smoke-specific pass/fail/skip/diagnostic-only classification、primary failure 和 suggested next step"
- Line 130: "若 diagnostics 中保留 action hint，命名必须清楚表明只是 `diagnostic_action_hint`，不得混同 smoke primary failure 语义"
- Lines 162-176: 字段重命名：
  - `observed_bucket`（原 `primary_failure_bucket`）
  - `observed_failing_path`（原 `primary_failure_path`）
  - `diagnostic_action_hint`（原 `suggested_next_step`）
  - `diagnostic_only_reason`（保留）
  - `observed_buckets` / `observed_items` / `diagnostic_only_observed_items` / `skip_observed_items` / `diagnostic_action_hints`（summary 层面）
- Lines 273-275: "Diagnostics 输出 observed facts...Smoke wrapper 输出 classification...不把 smoke-specific primary failure 语义写回 diagnostics，除非字段名清楚表明只是 diagnostic action hint。"

**Status**: **已修复**

字段命名从 smoke 判定语义（`primary_failure_bucket`, `suggested_next_step`）改为诊断观察语义（`observed_bucket`, `diagnostic_action_hint`）。smoke classification 职责明确归属 `utils/smoke_web_ci.py`。

---

### Finding 5 [MiMo-F4 / DS-F5] — schema/version gap 与子进程输出映射表

**Controller adjudication**: accepted. 要求 schema/version validation、`diagnostic_schema_gap` failure path、子进程输出映射表。

**Plan evidence**:
- Lines 254-259: smoke 读取 diagnostics artifact 前必须执行 schema validation：`diagnostic_schema_version` 存在、version/revision 满足 F03 最低版本、local HTML/PDF 必需 facts 完整。"不满足时生成 `diagnostic_schema_gap` failure"
- Line 188: "diagnostics payload / summary 必须携带 schema version 或 smoke-required revision"
- Line 187: "缺少 schema version、version 低于 smoke 需求、缺少必需字段时，smoke 应把它分类为 `diagnostic_schema_gap` failure，而不是静默 fallback"
- Lines 286-298: 完整子进程输出映射表，覆盖 return code 0/非0、JSON parse 成功/失败、schema valid/missing、requests/fetch ok/fail、content-type 检查、Docling invocation evidence、Docling init/dependency error、Playwright skipped、server 启动失败等所有信号组合
- 映射表明确区分 local HTML / local PDF / external 三种 case

**Status**: **已修复**

Plan 包含完整映射表（9 行 × 3 列判定），覆盖所有 controller 要求的信号路径。schema version validation 逻辑独立且明确，`diagnostic_schema_gap` 有独立 exit code `2`。

---

### Finding 6 [DS-F7] — Shell wrapper validation 条件化

**Controller adjudication**: accepted-with-note. 如果创建 wrapper 则验证；否则 implementation report 不列 `bash -n`。

**Plan evidence**:
- Lines 327-328: "如果创建 `utils/smoke_web_ci.sh`，`bash -n` wrapper pass；如果不创建 wrapper，implementation report 不列 `bash -n` 作为已执行验证"

**Status**: **已修复**

Validation 命令说明已条件化，不再隐含 wrapper 必须创建。

---

### Finding 7 [DS-F8 / MiMo residuals] — R2 residual transfer owner

**Controller adjudication**: accepted. closeout 必须 close R2 或 transfer 到 concrete owner/issue。

**Plan evidence**:
- Lines 580-585: "需要转移的 residual" 三分类（external sites / real browser / provider availability），每类要求 "转移到具体...issue 或明确 owner 角色"
- Line 585: "不得留下无 owner residual。若 closeout 时无法写出具体 GitHub Issue 编号、控制文档条目或明确 owner 角色，不得关闭 `WU-TOOLS-01-S5-R2`，必须停止让用户裁决。"

**Status**: **已修复**（plan gate 层面）

Plan 在 plan gate 层面已明确 transfer 条件与 closeout gate 的硬约束（无 owner 不关闭）。具体 Issue 编号由 closeout 阶段执行，不属于 plan gate 职责。

---

### Finding 8 [DS-F4] — PDF fixture 规范（原 needs-more-evidence）

**Controller adjudication**: accepted（与 MiMo F-3 / DS-F2 合并裁决）

**Plan evidence**: 见 Finding 3 的证据。

**Status**: **已修复**（证据已失效，被合并裁决覆盖）

原 DS-F4 的 "needs-more-evidence" 是针对旧 plan 引用 `_MINIMAL_PDF` 的。Amended plan 已放弃复用 `_MINIMAL_PDF`，改为自包含新 PDF fixture with explicit text spec。原 finding 的前提条件已消失。

---

### Finding 9 [DS-F6] — External sampling 策略

**Controller adjudication**: deferred（留给 implementation agent）

**Plan evidence**: Plan line 422-423 保持 "前 N 个或带 metadata 的小样本"。

**Status**: **未修复（不阻塞）**

Controller 已裁决为 deferred，不属于 plan gate blocking item。Implementation agent 可自行决定。

---

### Finding 10 [MiMo-F5 / F-6] — Line references / status naming polish

**Controller adjudication**: accepted-low. Amend where cheap, 不阻塞。

**Plan evidence**:
- Line references: lines 68-71 已更新为精确行号（`web_fetch_orchestrator.py:675-682`, `694-730`, `818-879` 等分段引用）
- Status naming: plan 仍使用 `diagnostic_only` 作为 status 值

**Status**: **部分修复（不阻塞）**

Line references 已修正。Status naming 的 `diagnostic_only` vs 字段名冲突未被采纳，但 controller 已裁决为 accepted-low 且不阻塞 implementation。

---

## Controller Adjudication 全部 accepted findings 覆盖审计

| Controller 裁决项 | 来源 | 状态 |
|---|---|---|
| PDF Docling route evidence → diagnostics-side instrumentation | MiMo F-1, DS F-1 | 已修复 |
| Playwright skipped + requests/fetch success → facts-based 或 additive bucket | MiMo F-2 | 已修复 |
| PDF fixture 稳定文本 + 最小内容断言 + 空/过短 fail | MiMo F-3, DS F-2, DS F-4 | 已修复 |
| Diagnostics facts 与 smoke classification 分离 | DS F-3 | 已修复 |
| Schema/version gap + `diagnostic_schema_gap` failure path | MiMo F-4 | 已修复 |
| 子进程输出映射表 | DS F-5 | 已修复 |
| Shell wrapper validation 条件化 | DS F-7 | 已修复 |
| R2 residual transfer owner 硬约束 | MiMo residuals, DS F-8 | 已修复 |
| Line references / status naming polish | MiMo F-5, F-6 | 部分修复（不阻塞） |

---

## 补充检查项

### PDF Docling route 不修改 production LLM-facing payload

Plan 以下位置均明确此约束：
- Line 72: explicit prohibition
- Line 161: "不写入 `ToolCompletedOutcome.result.value`，不暴露给生产 LLM-facing payload"
- Line 103: "不修改 `fetch_web_page` 对 LLM 返回字段"
- Line 195: invariants 中 "不把 `extraction_source`、`renderer_source`、Docling callable name 等 implementation-only 字段加入 production `fetch_web_page` LLM-facing success payload"

**确认：无泄露风险。**

### Playwright skipped + requests/fetch success 的 HTML pass 明确性

Plan 三处对齐：
- Facts-based 判定（line 178-179）
- Pass 规则（line 121）
- Mapping table（line 291）

**确认：一致，无矛盾。**

### PDF fixture 规范完整性

Plan 自包含：
- 不复用空白 PDF（line 116）
- 固定英文文本示例（lines 354-355）
- `PDF_FETCH_MIN_CHARS >= 20`（line 355-356）
- 空/过短 fail（lines 358-359, 293）

**确认：完整。**

### diagnostics observed facts 与 smoke classification 分离完整性

Plan 覆盖：
- 字段重命名（lines 162-176）
- 职责归属说明（lines 273-275）
- action hint 语义标注（line 130）

**确认：分离到位。**

### schema/version gap 与映射表完整性

Plan 包含：
- Schema validation 步骤（lines 254-259）
- Version requirement（lines 187-188）
- 9 行 × 3 列完整映射表（lines 286-298）

**确认：完整且自洽。**

---

## Final Recommendation: **PASS**

Controller adjudication 要求的 6 项 plan amendment 已全部在 amended plan 中修复：

1. PDF Docling route evidence → diagnostics-side narrow wrapper instrumentation，不修改 production payload
2. Playwright skipped + requests/fetch success → facts-based 判定 + 可选 additive bucket
3. PDF fixture → 稳定可抽取文本、`PDF_FETCH_MIN_CHARS >= 20`、空/过短 fail
4. Diagnostics facts 与 smoke classification → 字段重命名 + 职责分离
5. Schema/version gap + 子进程输出映射表 → 完整覆盖
6. residual owner / wrapper validation → 条件化 + 硬约束

无新发现。无遗留 blocking issue。

计划可进入 implementation gate。
