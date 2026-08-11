# WU-CLI-DOWNLOAD-02-DL-F12-F14 Aggregate Deepreview（AgentDS）

## Scope

- **Mode**: aggregate deepreview（cross-slice adversarial）
- **Branch**: `codex/download-oracle`
- **Base**: `3811f95c82fbf0daf15740a5d217eed4d8b49df5`
- **Target HEAD**: `a24671793c0d69f2a3e0f2d39e1b611d945b6044`
- **Output file**: `docs/reviews/wu-cli-download-02-aggregate-deepreview-ds-20260810.md`
- **Review date**: 2026-08-10
- **Reviewer**: AgentDS
- **Artifacts read**: goal confirmation、accepted plan、2 plan review rounds + adjudication、6 plan review artifacts、slice 1/2/3 implementation + review fix + adjudication artifacts、6 slice code review artifacts、`docs/cli_ci.md`、`AGENTS.md`、`docs/host/design.md`、`docs/engine/design.md`
- **Code review scope**: full `git diff base...HEAD` — 66 files, ~7064 insertions, ~287 deletions；逐文件走读全部 production diff、关键 owner tests 与三份 README diff
- **Excluded scope**: 无；非 Python gate 与 review artifacts 只读，不进入 product correctness 判定
- **Parallel review coverage**: 无；本 aggregate 由单一 reviewer 完整走读全部 diff

## Pre-review Guard Verification

以下静态/运行时 guard 在 aggregate review 开始前完整执行并通过：

| Guard | 命令/方法 | 结果 |
|---|---|---|
| 旧 contract 残留 | `rg "TargetPeriodResolution\|resolve_target_periods" dayu/ tests/` | 无匹配（exit 1） |
| 旧 category code | `rg "13600" dayu/fins/downloaders/hkexnews_downloader.py` | 无匹配（exit 1） |
| candidate `.fiscal_period` compat | `rg "\.fiscal_period" dayu/ --glob '*.py'` 过滤已知独立字段 | 无 CnReportCandidate compat property |
| mutation mode single owner | `rg "overwrite_existing and rebuild_local_artifacts" dayu/` | 仅 `download_contract.py:79` 一处 |
| identity 仅用于 ID/missing | `rg "build_cn_filing_ids.*covered_periods" dayu/` | 无匹配 |
| category spec dedup | 运行时验证：Q1-Q4 共用同一 `_HkCategorySpec` | 3 unique specs（annual/interim/results），正确去重 |
| covered 无默认值 | `inspect.signature(FinsDownloadDocumentResult)` / `FinsDownloadPublicDocument` | 均为 `inspect._empty`（无默认） |
| rebuild fail-closed | 运行时：缺字段、非 list、非法 period 三种旧 meta 输入 | 均 raise ValueError |
| classifier edge cases | 运行时：空 category、双 family、report+quarter token | 均返回 None |
| 真实 HKEX-like 输入 | 运行时：中期業績→Q2/(H1,Q2)、末期業績→Q4/(FY,Q4)、年報→FY/(FY,)、中期報告→H1/(H1,) | 全部正确 |
| hasattr/getattr 禁止 | `rg "hasattr\|getattr"` over changed production files | 无匹配 |
| public JSON chain | `to_json_value()` 显式写入 `covered_fiscal_periods`；round-trip 验证 | 通过 |

## Findings

### 未发现实质性问题

经过对全部 66 个 changed files 的逐文件走读、对七个关键 guard 维度的 cross-slice adversarial review，以及对 accepted plan 每一个 invariant 的直接代码/运行时验证，**本轮 aggregate deepreview 未发现 correctness、stability、maintainability、semantic ownership drift、过度耦合、scope drift 或 README/LLM-facing 语义层面的 material finding**。

以下逐项记录各 cross-slice adversarial surface 的审查结论与直接证据。

## Cross-Slice Adversarial Surface 审查

### 1. F12 typed invariant — 全构造路径与 standalone modes

- **Single owner**: `_validate_download_mutation_mode(...)` in `download_contract.py:57-81` 是唯一含 `overwrite_existing and rebuild_local_artifacts` production 判断的位置。
- **Consumer count**: `FinsDownloadRequest.__post_init__`（`download_contract.py:650`）与 `FinsDownloadEffectiveFilters.__post_init__`（`download_contract.py:226`）各调用一次；CLI parser 只投影 help 文案（`arg_parsing.py:888-896`）。
- **Pre-side-effect sequencing**: CLI argv → `_prevalidate_download_request` → `build_fins_download_request` → `FinsDownloadRequest.__post_init__` 在 `_resolve_workspace_root`、`FINS_DIRECT_SERVICE_FACTORY`、stream、provider、storage 之前（直接代码路径证据见 `dayu/cli/commands/fins.py` 调用顺序与 `build_fins_download_request` 的 `FinsDownloadRequest(...)` 构造点）。
- **Standalone modes**: `00`、`10`、`01` 三种合法组合均通过 owner test 矩阵验证。
- **No downstream compat**: workflow、runtime、adapter 不含 mode precedence、fallback、默认纠正或第二个布尔 conjunction。
- **Verdict**: PASS — typed invariant 在所有构造路径早于副作用，standalone modes 不被破坏。

### 2. F14 policy effective/discovery/missing — CN/HK bare、explicit forms、rebuild 全链同源

- **Single policy owner**: `resolve_download_period_policy(...)` in `cn_form_utils.py:197-251` 是唯一产生 `CnDownloadPeriodPolicy` 的函数。
- **Triple-route consumption verified**:
  - `effective_periods` → `filters.forms`（`cn_download_workflow.py:368`、`cn_download_rebuild.py:115`）
  - `discovery_periods` → `CnReportQuery.discovery_periods`（`cn_download_workflow.py:180`）、`resolve_period_windows(discovery_periods=...)`（`cn_download_workflow.py:99-103`、`cn_download_rebuild.py:71-75`）
  - `missing_eligible_periods` → `_resolve_missing_periods(...)`（`cn_download_workflow.py:238-240`）
- **CN bare**: effective/discovery/missing = `(FY,H1,Q1,Q3)`；CNInfo downloader Q2/Q4 无独立分类时按既有行为跳过，不进入 missing。
- **HK bare**: effective/missing = `(FY,H1)`、discovery = 六期全量。optional Q2/Q4 result 的 identity 不满足 FY/H1 report missing baseline。
- **CN explicit Q2/Q4**: 三集合均为 `(Q2,Q4)`，行为与 baseline 一致（显式请求但无候选时报告 missing）。
- **Rebuild**: discovery 用于本地 source scan scope，effective 用于 filters.forms，`missing_periods` 硬编码为 `[]`。
- **No recomputation**: workflow/rebuild 都不从 `filters.forms`、selected rows 或 provider category 反推 policy。
- **Verdict**: PASS — 三集合在 CN/HK bare、explicit forms、rebuild、missing 全链路同源，subset invariant 由 `CnDownloadPeriodPolicy.__post_init__` 强制执行。

### 3. F13 HKEX discovery — category query、classifier 一般化与 Q2/Q4 根因

- **Category query**: `_PERIOD_TO_CATEGORY_SPEC`（`hkexnews_downloader.py:145-176`）中 Q1-Q4 全部映射到同一个 `_HkCategorySpec(t1code=10000, t2Gcode=3, t2code=-2)`。运行时验证确认 3 unique specs（annual report、interim report、all results group），Q1-Q4 去重为一次查询。
- **No issuer/ticker/date/URL 特例**: production（`hkexnews_downloader.py`、`cn_report_selection.py`）不含 `0700`、腾讯、`11793094`、`12056833` 或完整标题字面量作为分类分支条件。
- **Category-first classification**: `_classify_hk_period_projection(...)`（`cn_report_selection.py:506-557`）先只由 `category_text` 判定 report/results family，再在 family 内共同解释 category 与 title 的期间事实。运行时验证确认：空 category、双 family（report+results 同时出现）、report family 含 quarter token 均 fail closed 返回 `None`。
- **Shared token disambiguation**: `_HK_REPORT_H1_TOKENS` 包含 "半年報"/"半年度報告" 等，`_HK_REPORT_FY_TOKENS` 包含 "年報"/"年度報告" 等。"半年報" 包含子串 "年報"，但 `_remove_tokens()`（`cn_report_selection.py:577-594`）在 FY 匹配前先移除 H1 token，消除误判。report family 永不产生 Q1-Q4 identity。
- **results identity resolution**: `_resolve_hk_results_identity(...)`（`cn_report_selection.py:597-618`）按 Q4 > Q3 > Q2 > Q1 cascade 且冲突时 fail closed（Q4+Q2→None、Q4+Q3→None、Q2+Q3→None）。Q4+Q1→Q4（不冲突）。
- **Root cause fixation**: 旧代码的 `t2code=13600` 季度业绩子类 → 缺失 Q2/Q4 raw rows → 丢失 candidate。修复为 `t2code=-2` 全 results group，并辅以 category-first classification 确保不会误收。根因直接对应 provider category 查询范围，不需要 ticker/title/date/URL 的任何特例。
- **Verdict**: PASS — 根因一般化处理，classifier 对官方 Q2/Q4 材料正确识别且无 issuer 特例。

### 4. 同 source 单 identity、coverage 不满足 baseline

- **Identity vs coverage separation**: `CnReportPeriodProjection`（`cn_download_models.py:137-183`）。
  - `identity_period`：用于 document ID（`build_cn_filing_ids(...)` 的 `form_type`/`fiscal_period`）、selection 分组、排序、窗口过滤、business-year limit、missing satisfaction、`form_type`、`fiscal_period`、`report_kind`。
  - `covered_periods`：仅用于 source meta `covered_fiscal_periods`、workflow filing result、typed/public result 和 CLI row 的机械投影。
- **One source, one identity**: `_candidate_document_id(...)`（`cn_download_workflow.py:823-844`）与 `run_cn_download_single_filing_stream`（`cn_download_filing_workflow.py:155-161`）均只传 `candidate.period_projection.identity_period` 给 `build_cn_filing_ids(...)` 恰好一次。不遍历 `covered_periods`。
- **Coverage ≠ missing satisfaction**: `_resolve_missing_periods(...)`（`cn_download_workflow.py:569-587`）只消费 `missing_eligible_periods` 与 selected candidates 的 `identity_period`（line 586: `{item.period_projection.identity_period for item in selected}`）。Q2 result 的 `covered=(H1,Q2)` 不消除 H1 missing，Q4 result 的 `covered=(FY,Q4)` 不消除 FY missing。
- **No document duplication**: 同一 `document_id` 只生成一个 source document、一个 filing manifest item、一个 `FinsDownloadDocumentResult`、一个 `FinsDownloadPublicDocument`。covered periods 不增加 document/manifest 数量。
- **Verdict**: PASS — 同 source 单 identity 且 coverage 不绕过 baseline missing contract。

### 5. Fresh schema / skip / rebuild / overwrite 交互

- **Rebuild strict parse**: `_required_covered_fiscal_periods(...)`（`cn_download_rebuild.py:451-488`）对 fresh schema source meta 做 required list、成员、非空、去重、canonical order、identity inclusion 全部校验。运行时验证确认：缺字段、非 list、非法 period 均 raise ValueError。
- **Old meta 无兼容读取**: rebuild 不包含 `.get("covered_fiscal_periods", default=())` 或旧 schema 版本判断。缺 coverage 的旧 meta fail closed。
- **Skip 不变**: skip 路径由既有 `previous_meta.download_version == CN_PIPELINE_DOWNLOAD_VERSION` 控制；coverage 字段的新增不改变 skip eligibility 判断逻辑。
- **Overwrite/rebuild 互斥**: F12 mode validation 在 typed request 层，与 F13/F14 正交。rebuild 不访问 provider 或运行 Docling，仅重建 meta/manifest。
- **Rebuild missing contract**: `rebuild_cn_download_artifacts(...)` 直接输出 `"missing_periods": []`（`cn_download_rebuild.py:124`）。不调用 `_resolve_missing_periods`。
- **Verdict**: PASS — fresh schema strict parse fail-closed，rebuild/overwrite/skip 交互符合 accepted plan contract。

### 6. SEC / generic mandatory field 迁移

- **SEC 四个构造点**: `sec_pipeline.py` 的 downloaded、skipped、rejected、failed 四种 disposition 的 `FinsDownloadDocumentResult` 构造均显式传 `covered_fiscal_periods=()`。
- **Generic runtime 两个构造点**: `ingestion_runtime.py` 的 `FinsDownloadDocumentResult`（line 3843-3856）与 rejected artifact 构造（line 3864-3877）均显式传 `covered_fiscal_periods=()`。
- **Runtime public projection**: `_public_download_summary(...)` → `FinsDownloadPublicDocument`（`ingestion_runtime.py:5096-5103`）原样复制 `row.covered_fiscal_periods`。
- **Public document validation**: `FinsDownloadPublicDocument.__post_init__()`（`direct_events.py:305-310`）校验 tuple 类型、成员在 `FISCAL_PERIODS`、无重复。空 tuple 合法 — SEC/generic 的 `()` 通过。
- **JSON serialization**: `to_json_value()`（`direct_events.py:357`）显式写入 `"covered_fiscal_periods": list(self.covered_fiscal_periods)`。SEC summary JSON 含 `"covered_fiscal_periods": []`。
- **No default value**: 运行时 `inspect.signature` 验证两个公共类型的 `covered_fiscal_periods` 均为 `inspect._empty`（无默认参数）。
- **Verdict**: PASS — SEC/generic 所有构造点显式迁移，公共类型无默认值，JSON 链完整。

### 7. 取消 / 失败 / 空候选

- **Cancelled path**: `cn_download_workflow.py:242-256` 在 filing loop 中检查 `cancel_checker`，设置 `cancelled=True` 并 break。`_build_result(status="cancelled")`（line 362-364）。cancelled 时不调用 `_resolve_missing_periods`（未达到该代码点），`missing_periods` 保持初始值 `()`。
- **Failed candidate**: `_build_candidate_failed_result(...)`（`cn_download_workflow.py:590-627`）携带完整 `covered_fiscal_periods` 与 `FinsDownloadDocumentDisposition.FAILED`。
- **Exception path**: `try/except Exception`（line 306-326）构造 failed result 并 yield `FILING_FAILED` event，不丢失 coverage 信息。
- **Empty candidates**: `missing_periods` 正常计算（所有 eligible periods 均 missing）；zero-candidate 不抛异常；`terminal_disposition` 允许 zero-candidate 时 `FAILED` 或 `CANCELLED` override（`download_contract.py:397-400`）。
- **Verdict**: PASS — 取消/失败/空候选路径均正确处理，coverage 信息不丢失。

### 8. Semantic ownership drift / 过度耦合 / compat/fallback/default/loose parsing/特例

- **No hasattr/getattr**: changed production files 中无任何 `hasattr` 或 `getattr` 使用。
- **No compat property**: `CnReportCandidate` 无 `fiscal_period` compatibility property、alias 或 re-export。
- **No loose parsing**: rebuild 的 `_required_covered_fiscal_periods` 不使用 `.get(default)` 或隐式默认值。CN adapter 的 `_required_cn_covered_fiscal_periods` 不使用 empty tuple fallback。
- **No 特例 in new code**: production classifier、discovery client、policy 不含 `0700`、腾讯、`11793094`、`12056833` 或完整标题特例。
- **No downstream recomputation**: CLI output（`output.py:462`）直接投影 `row.covered_fiscal_periods`；wait adapter 机械消费 `to_json_value()`；不在任何下游从 `form_or_period`、标题或 meta 字符串重算 coverage。
- **No Host/Engine coupling**: 全部修改在 `UI → Service → Fins` 边界内。Host/Engine contract、design doc 与 README 无变化。
- **No storage schema change**: `FilingManifestItem` 不变；coverage 保存在 source meta 中。
- **Verdict**: PASS — 无 semantic ownership drift、过度耦合、compat/fallback/default/loose parsing 或 issuer 特例的证据。

### 9. README 与 LLM-facing / 用户语义

- **根 README**: 新增用户可见 mode 互斥说明、CN bare default `FY,H1,Q1,Q3`、HK effective baseline FY/H1 + optional discovery、missing baseline 规则、`covered_fiscal_periods` 数组说明。不写 plan/review/WU 历史或 future capability。
- **`dayu/fins/README.md`**: 新增全 results discovery、category-first 分类说明、identity/coverage owner、public contract。不写 WU 或 evidence 标识。
- **`tests/README.md`**: 更新 download owner matrix 与 coverage 测试事实。
- **`dayu/README.md`**: 不变（分层/装配边界未变化）。
- **Host/Engine README / design doc**: 不变。
- **Verdict**: PASS — 三份 README 更新均在各自写作边界内，不使用 LLM 不可理解的内部术语。

### 10. Test fixtures — 未固化实现偶然性

- **Category fixtures**: HKEX raw fixture 使用通用标题/category 文本，不含完整 title/date/URL 特例。正负例参数化覆盖繁中/简中/英文 token。
- **Policy tests**: 四行矩阵（CN bare、HK bare、CN explicit、HK explicit）直接断言 policy owner contract；不通过 mock workflow behavior 间接验证。
- **Classifier tests**: 正负例覆盖空 category、双 family、report+quarter、duration 冲突；token 通过参数化 fixture 注入，不冻结完整标题。
- **Rebuild tests**: 直接断言 `missing_periods == []`、provider HTTP 零调用、local-only 边界；不依赖 side-effectful setup。
- **Public projection tests**: JSON round-trip 验证 `documents[].covered_fiscal_periods` 存在且为 array；SEC 显式断言空 array。
- **Verdict**: PASS — test fixtures 验证 owner 级 contract，不固化实现偶然性或旧行为。

### 11. Scope drift 与过度设计

- **Allowed files**: production diff 严格落在 plan §6 的 Slice 1/2/3 allowed files 内。无 Host/Engine、storage schema、通用 infrastructure 或其它命令的修改。
- **No new abstractions**: 仅新增两个必要的值类型（`CnDownloadPeriodPolicy`、`CnReportPeriodProjection`），不新增 provider abstraction、policy registry、issuer 配置、状态机、数据库表、migration layer。
- **No future capability**: README 只写当前实现事实，不预写未实现能力。
- **No compatibility shim**: 无旧名字 re-export、wrapper、facade 或 compat property。
- **Verdict**: PASS — 无 scope drift 或过度设计。

## Open Questions

无。全部 blocking contract questions 已在 accepted plan 与 slice adjudications 中裁决闭合。

## Residual Risk

| Residual risk | 分类 | Owner / 处置 |
|---|---|---|
| 真实 HKEX 全 results 数据规模与边缘 category 文本 | 已批准后续 gate | production CLI post-fix evidence；当前 code gate 不处理 |
| 通用 substring token 在未知 provider 文本上可能保守 discard | acceptable fail-closed | production evidence；不在 code gate 添加 issuer 特例 |
| 旧 workspace 无 coverage 的 source meta 无兼容读取 | accepted fresh-schema boundary | 非本 work unit；用户另行授权 migration 才处理 |
| 真实 CN/HK provider 与 production CLI post-fix evidence 未执行 | 已批准后续 gate | accepted plan §9 CLI evidence gate；所有 slice/aggregate review 通过后执行 |
| `cn_report_selection.py` Slice 2 的 Ruff-required 非语义换行 | no behavioral impact | 已由两名 reviewer 验证无 token/顺序/分类/控制流变化 |

无 unclassified residual risk；无 blocking contract question。

## Review Conclusion

**PASS** — 经逐文件走读全部 66 个 changed files、七个 guard 维度的 cross-slice adversarial 验证、关键不变量运行时确认与已裁决 findings 的 closed-loop re-verification，本轮 aggregate deepreview 未发现 correctness、stability、maintainability、semantic ownership drift、过度耦合、scope drift 或 README/LLM-facing 语义层面的 material finding。

三个 slice 的 implementation 均严格符合 accepted plan，已裁决 findings 均已关闭且经 re-review 独立确认，静态/运行时 guards 全部通过。
