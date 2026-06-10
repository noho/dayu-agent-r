# WU-TOOLS-01-F03 Plan Review — AgentDS

## Reviewed Target

- **Plan**: `docs/host/wu-tools-01-f03-web-ci-smoke-plan.md`
- **设计真源**: `docs/host/design.md`, `docs/engine/design.md`
- **总控真源**: `docs/host/issues-implementation-control.md`
- **F02 closeout**: `docs/reviews/wu-tools-01-f02-final-closeout-controller.md`
- **Review date**: 2026-06-10

## Review Summary

Plan 整体扎实，基于直接代码证据，诚实处理了 Docling route evidence 无法从 production tool runtime 直接获取的约束，明确区分了 local fixture gate 与 external diagnostic-only，复用 F02 diagnostics 作为真源而非绕过。5 个 slice 的拆分合理、依赖关系清晰、每个 slice 有明确的 stop condition。

以下按 severity 排列 findings。

---

## Findings

### Finding 1 [HIGH] Docling route evidence 依赖 code-route inference，而非 production tool runtime 直接字段

**证据**:

- `dayu/tools/web/web_tools.py:1560-1564` — `fetch_web_page` 成功时对 LLM 可见 payload 只有 `url/final_url/title/content/fetch_backend`，不暴露 `extraction_source` / `renderer_source`。
- `utils/diagnose_web_access.py:1283-1296` — `_build_tool_fetch_profile()` 从 `ToolCompletedOutcome` 只提取 `title/final_url/fetch_backend/content_prefix/content_length`，不提取 `extraction_source`。
- Plan line 127-128: "必须说明这是基于'raw response content-type / URL suffix + current fetch success + current code route'的诊断推导，不是财报事实或站点事实。"
- Plan line 70-71: "`ToolCompletedOutcome` 对 LLM 可见 payload 只返回 `url/final_url/title/content/fetch_backend`。因此 F03 若要让 smoke artifact 明确表达 Docling route，优先在 diagnostics summary 中增加...Code route 推导出的 Docling route 证据字段。"

**分析**:

Plan 对此约束的处理是正确的——不在 smoke 外壳绕过诊断、不修改 production tool schema。但 code-route inference 存在一个未充分讨论的风险：如果未来 `_should_route_response_to_html_pipeline()` 的判断规则或 `convert_non_html` 的实现路径变更（例如 PDF 改用其他转换器），当前的 inference 会静默失效，smoke "pass" 不再证明 Docling path 仍然有效。

Plan 的 stop condition (line 353) 只覆盖了"诊断无法证明 Docling route"时的停止，但没有覆盖"code route 已变更但 inference 逻辑未同步更新"时的静默漂移风险。

**建议裁决**: **accepted-with-note** — 接受 plan 当前的 code-route inference 方案，但要求：
1. `fetch_non_html_route_evidence` 字段中显式记录推断所依据的 code 版本信息（至少记录 `_should_route_response_to_html_pipeline` 和 `convert_non_html` 的导入源和函数名），使 future reader 能核对 inference 与当前 code route 是否对齐。
2. 在 Slice 1 的 stop condition 中增加一条：如果 code-route inference 所依赖的生产函数签名或语义发生变更，smoke 必须 fail 而非静默 pass。

---

### Finding 2 [HIGH] PDF smoke 对 Docling 转换成功但输出空内容的边界未定义

**证据**:

- Plan line 314: "PDF case pass 条件：raw requests sampled / ok，response content-type 包含 PDF，fetch sampled / ok，diagnostics 给出 PDF Docling route evidence。"
- Plan line 121: "fail：...PDF fetch 成功但无法建立 Docling route evidence。"
- Plan line 505-506: "Minimal PDF 可能在部分 Docling 版本或平台上被判为无有效文本。计划允许把 Docling runtime dependency/init failure 作为 skip，但如果转换成功却内容过短触发 current fetch `empty_content`，需要调整 fixture PDF 为仍很小但含稳定文本的 PDF；不得跳过 PDF route。"

**分析**:

Docling 转换 PDF 可能产生三种结果：
1. Docling init failure → plan 正确处理为 skip。
2. Docling 成功但输出空/极短 markdown → `fetch_web_page` 可能返回 `ToolCompletedOutcome`（content 为空）或 `ToolFailedOutcome`（empty_content）。Plan 说"调整 fixture PDF"但未定义 smoke 判定：如果 fixture 已含稳定文本但 Docling 仍输出空内容，这算 fail 还是 skip？

当前代码 `dayu/tools/web/web_fetch_orchestrator.py:694-730` 的 `_docling_convert_to_markdown` 只捕获 `DoclingRuntimeInitializationError` 和通用 Exception；通用 Exception 会 raise `RuntimeError`，最终导致 `ToolFailedOutcome`。但如果 Docling 不抛异常只是输出空字符串，会返回 `ToolCompletedOutcome` 且 content 为空。此时 raw response 有内容但 fetch content 为空——这是一个应该被识别为异常的信号。

**建议裁决**: **accepted-with-amendment** — 在 pass/fail 规则中增加：
- PDF case: 如果 raw response 有内容（`text_length > 0` 或 `content_length > N`）但 fetch content 为空（`content_length == 0` 或小于预期），标记为 `diagnostic_gap_fail`，不标记为 pass。这防止了"Docling 静默丢弃内容但 smoke 报告 pass"的误判。

---

### Finding 3 [MEDIUM] Slice 1 新增字段的语义归属不清晰——diagnostic fact vs smoke classification

**证据**:

- Plan line 155-167: `_build_batch_result_row()` 追加 `primary_failure_bucket`, `primary_failure_path`, `evidence_path`, `failure_url`, `suggested_next_step`, `diagnostic_only_reason`。
- Plan line 163-167: `_build_batch_summary()` 追加 `failure_buckets`, `failure_items`, `diagnostic_only_items`, `skip_items`, `suggested_next_steps`。
- Plan line 128: "smoke 外壳只读取这些诊断字段和单 URL payload，不自行解析 raw HTML、重建 comparison bucket 或猜测 next action。"

**分析**:

`primary_failure_bucket` 和 `primary_failure_path` 的"primary"语义来自 smoke gate 视角（哪个路径导致 smoke fail），不是纯诊断语义（诊断只报告各路径状态，不判断"哪个是 primary"）。`suggested_next_step` 同理——它依据 smoke pass/fail/skip 规则推导，不是诊断证据。

User 硬要求 #1 说"如果 F03 需要超出 F02 最小字段集，应该强化 F02 diagnostics 真源"。强化 diagnostics 是正确方向，但强化内容应该是"更细粒度的诊断事实"，而非"植入 smoke 判定结果"。当前命名模糊了这条线。

**建议裁决**: **accepted-with-amendment** — 建议调整字段归属：
1. 纯诊断事实（`evidence_path`, `failure_url`,`diagnostic_only_reason`）留在 `_build_batch_result_row()` / `_build_batch_summary()` 中。
2. Smoke 判定结果（`primary_failure_bucket`, `primary_failure_path`, `suggested_next_step`, `failure_items`, `diagnostic_only_items`, `skip_items`）放在 Smoke 模块自己的 helper 中，消费 diagnostics summary 的纯诊断字段来生成。这避免了 diagnostics 模块承担 smoke 判定职责，同时满足"smoke 外壳不复制诊断逻辑"的要求——smoke 做的是 classification，不是 re-diagnosis。
3. 或者保留在 diagnostics 中但重命名为诊断视角的术语：`observed_failure_bucket`（替代 `primary_failure_bucket`），`observed_failing_path`（替代 `primary_failure_path`），`diagnostic_action_hint`（替代 `suggested_next_step`）。这样保持字段"描述发生了什么"的语义，而非"判断 smoke 该怎么看"。

---

### Finding 4 [MEDIUM] PDF fixture 缺少最小内容规范

**证据**:

- Plan line 115: "`/fixture.pdf` 使用很小 PDF bytes，优先复用 `tests/fins/test_docling_upload_service_integration.py` 中已有 minimal PDF 形态。"
- Plan line 505: "Minimal PDF 可能在部分 Docling 版本或平台上被判为无有效文本。"

**分析**:

Plan 引用了现有 minimal PDF fixture 但没有验证它是否含实际可解析文本。Docling 的 `do_ocr=True` 可能会在极小 PDF（如单页空白背景+少量文字）上产生不可靠结果。此外，不同 Docling 版本对最小可行 PDF 的要求可能不同。

Implementation agent 需要明确的规范才能不浪费迭代时间在 PDF 调参上。

**建议裁决**: **needs-more-evidence** — 在 implementation 开始前：
1. 确认 `tests/fins/test_docling_upload_service_integration.py` 中的 PDF fixture 的输出文本及其在 Docling 各版本下的稳定性。
2. 如果该 fixture 不含稳定文本（例如只含图片或矢量图形），定义新的 minimal PDF spec：至少含一段英文文本（如 "Hello World\nThis is a smoke test PDF."），确保 Docling OCR/解析能提取至少 20 个可打印字符。
3. 在 Slice 3 中增加 `PDF_CONTENT_MIN_CHARS` 常量，用于 smoke pass 条件判断。

---

### Finding 5 [MEDIUM] Smoke 读取 diagnostics subprocess 输出的数据流缺少错误分类细节

**证据**:

- Plan line 258-259: "diagnostics 子进程 return code 非 0：local case fail；external case diagnostic-only，除非 schema / script itself broken。"
- Plan line 177: "缺少新增字段时，smoke 应把它分类为 `diagnostic_schema_gap` failure，而不是静默 fallback。"

**分析**:

子进程 return code 非 0 有多种原因：
- URL 安全校验拒绝（`blocked_by_diagnostic_url_policy`）→ 应 fail（local fixture 不应该触发此项）。
- 网络错误 → 应 fail（local server 应可达）。
- Docling init failure → 应 skip（按 plan 规则）。
- Python 环境问题（import 失败等）→ infrastructure error，exit code 2。

Plan 将所有 non-zero return code 统一为"local case fail"，但 local PDF 的 Docling init failure 应 skip 而非 fail。`_build_tool_fetch_profile` 内部捕获 `DoclingRuntimeInitializationError` 但会以什么形式体现在子进程输出中？如果 Docling init failure 导致 `fetch_web_page_profile.ok=False` 且 `fetch_web_page_profile.error_code` 为某个特定值，smoke 需要能识别这个信号。

当前 plan 缺少这个分类路径的具体映射表。

**建议裁决**: **needs-more-evidence** — 在 Slice 2/3 中明确定义子进程输出到 smoke 判定的映射表：

| 子进程信号 | Local HTML | Local PDF |
|---|---|---|
| return code 0, fetch ok, requests ok | pass | pass (需额外 Docling route evidence) |
| return code 0, fetch ok, requests ok, but PDF route evidence missing | — | fail |
| return code != 0, diagnostic JSON 含 `DoclingRuntimeInitializationError` | — | skip |
| return code != 0, diagnostic JSON 含其他错误 | fail | fail |
| diagnostic JSON schema gap (缺必需字段) | fail | fail |
| 子进程无输出 / JSON 解析失败 | fail | fail |

---

### Finding 6 [LOW] `--external-limit` 采样策略未定义

**证据**:

- Plan line 373: "传 `--external-url-file utils/web_ci_urls.jsonl --external-limit N` 时，只取前 N 个或带 metadata 的小样本；禁止默认全量。"

**分析**:

"前 N 个"是文件顺序的前 N 个，可能不具代表性（例如全是一个 region 或一个 category）。对于 diagnostic-only external，随机采样更好。但这不是 blocking issue——external 本身不参与 gate。

**建议裁决**: **deferred-with-owner** — 留给 implementation agent 决定（取前 N 或随机 N），在 smoke 文档中说明采样策略。如果用户后续要求 representative sampling，改为随机采样并增加 `--external-seed` 参数。

---

### Finding 7 [LOW] Shell wrapper 状态不明确

**证据**:

- Plan line 85: "`utils/smoke_web_ci.sh`，可选 shell wrapper。"
- Plan line 217: "`utils/smoke_web_ci.sh`" 列为 Slice 2 allowed file。
- Plan line 272: `bash -n utils/smoke_web_ci.sh` 列为 validation command。
- Plan line 459: `bash -n utils/smoke_web_ci.sh` 再次列为 validation。

**分析**:

Plan 在 scope 中说 wrapper 可选，但在 validation 中每次都包含 `bash -n`。Implementation agent 需要知道是否必须创建这个文件。

**建议裁决**: **accepted** — 这不是 plan 缺陷。建议在 implementation 时将 wrapper 标记为"如果创建则必须通过 `bash -n`"。

---

### Finding 8 [LOW] R2 residual transfer 缺少具体 Issue 编号

**证据**:

- Plan line 530-532: "Real external sites challenge / anti-bot / DNS / timeout：转移到后续 Web provider observability 或 operator-run diagnostic maintenance owner。"
- Plan line 531-532: "Real Playwright browser / Chrome channel / storage-state cookies：转移到后续 browser-capability smoke owner。"
- Plan line 534: "不得留下无 owner residual。若无法确定 owner，closeout 前停止让用户裁决。"

**分析**:

Plan 已认识到转移需要 owner，但未预指定可能的 owner issue 编号（例如是否应创建新 Issue 或关联已有 Issue）。这符合 plan gate 的职责范围——plan 只需声明转移条件，具体 issue 由 closeout 时裁决。

**建议裁决**: **accepted** — plan 已正确处理。在 closeout 时必须确保每个 transferred residual 有具体 owner（GitHub Issue 编号或明确的人名/角色）。

---

### Finding 9 [INFO] Slice 5 总控更新点的正确性验证

**证据**:

- Plan line 437-439: "`WU-TOOLS-01-S5-R2`：若 local HTML/PDF smoke 与 summary contract 完成，则标记 closed；若 external/browser/provider 仍不稳定，转移到有 owner 的 residual，并说明不是 F03 local smoke 阻塞。"
- Control doc line 198: "`WU-TOOLS-01-S5-R2` | deferred-with-owner | WU-TOOLS-01-F02 then WU-TOOLS-01-F03 / GitHub Issue #120。"

**分析**:

Plan 的 closeout 条件与 control doc 的 R2 状态一致。Plan 正确识别了 R2 的两个子问题：(a) pass/fail/skip gate 缺失 → F03 关闭；(b) external/browser instability → 转移。方向正确。

**建议裁决**: **accepted** — 无修正需求。Closeout 时注意：如果 local smoke 完成但外部全部 all_failed（站点变更、anti-bot 升级等），这不是 F03 的缺陷，而是证明 external 确实不适合做 gate。

---

### Finding 10 [INFO] Plan 合规性检查通过项

以下项目已核实，无问题：

| Check | Status | Evidence |
|---|---|---|
| 分层边界守住了 | 通过 | Smoke 只在 `utils/` + `tests/`，不 import Host/Engine/Service/UI (line 265) |
| 不修改 production tool schema | 通过 | Plan line 71, 98-103 |
| 不修改 Host/Engine contract | 通过 | Plan line 27-28, 99-103 |
| 复用 F02 diagnostics 真源 | 通过 | Plan line 58, 127-128 |
| Local PDF + Docling route | 通过 | Plan line 59-60, 114-116，code evidence 确认可行 |
| Deterministic test 边界 | 通过 | Plan line 432-434，与 `tests/README.md:143` 一致 |
| 不把 external 失败当 gate | 通过 | Plan line 113, 377-378 |
| 不新增默认 CI workflow | 通过 | Plan line 130-131 |
| 不复制诊断逻辑 | 通过 | Stop condition 在 Slice 2/3 各 slice 中定义 |
| 不修改 control doc 在 plan gate | 通过 | Plan line 33 |

---

## Open Questions

1. **Q1**: 现有 `tests/fins/test_docling_upload_service_integration.py` 中的 minimal PDF fixture 在 Docling 各版本下是否能稳定产生至少 20 个可打印字符的 markdown？如果没有，需要定义新 fixture spec。
   - **影响**: Slice 3 PDF fixture 选择。
   - **建议**: Implementation Slice 3 第一步先验证，再决定是否复用。

2. **Q2**: `DoclingRuntimeInitializationError` 在当前 `_build_tool_fetch_profile` 中的表现是什么？是通过 `ToolFailedOutcome` 的哪个 error_code 暴露？
   - **影响**: Slice 2/3 的子进程输出到 skip 分类的映射表。
   - **建议**: Slice 1 开始前检查 `dayu/tools/web/web_tools.py:1595-1610` 中 `_docling_convert_to_markdown` 的异常传播路径。

3. **Q3**: R2 residual transfer 后是否需要创建新 GitHub Issue 追踪 external/browser/provider instability？
   - **影响**: Closeout 时 R2 的"已转移"状态是否可验证。
   - **建议**: Closeout 前与用户讨论，至少给出候选 issue 编号或明确 owner 角色。

---

## Residual Risks

1. **[Acceptable]** Docling code-route inference 静默漂移 — 缓解：Finding 1 建议的 code version annotation 和 stop condition 扩展。

2. **[Acceptable]** Minimal PDF 在 Docling 不同版本间产生不一致输出 — 缓解：Finding 4 建议的内容规范 + Slice 3 前置验证。

3. **[Acceptable]** External diagnostic-only 结果可能随时间退化（站点改版、anti-bot 升级）导致误以为"diagnostic 环境出了问题" — 缓解：summary 的 `diagnostic_only` bucket 分类 + `suggested_next_step` 应说明这是 external instability，不是 infrastructure failure。

4. **[Watch]** Smoke 的 `utils/smoke_web_ci.py` 可能因为 Python import 路径问题无法直接 `python -m utils.smoke_web_ci`（需要 `utils/` 在 `sys.path`）。缓解：F02 的 `diagnose_web_access.py` 已解决同类问题，可复用方案。

---

## Final Recommendation: **PASS-WITH-FIXES**

Plan 可以被 implementation agent 直接执行，前提是以下 3 项 fix 在 implementation 开始前或在对应 slice 中落实：

1. **Finding 2 fix**: PDF pass 规则中增加"raw response 有内容但 fetch content 为空时标记为 fail"。
2. **Finding 3 fix**: 调整 Slice 1 新增字段的语义归属——diagnostic fact 和 smoke classification 分属不同 helper 或至少调整命名。
3. **Finding 5 fix**: 定义子进程输出到 smoke 判定的映射表。

其余 findings 为 accepted-with-note 或 deferred，不阻塞 implementation。

Open questions Q1-Q2 应在 Slice 1/3 开始前澄清；Q3 留给 closeout 阶段裁决。
