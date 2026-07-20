# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D Plan Fix — AgentCodex

## Gate Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Gate: `plan fix only`
- Timestamp: `2026-07-13T08:11:22+08:00`
- Plan target: `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`
- Artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-fix-codex.md`
- Design truth: `docs/host/design.md`、`docs/engine/design.md`
- Control truth: `docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md`
- Review inputs:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-review-controller-adjudication.md`
- Write scope: 只修改 plan target 并新增本 artifact；未修改生产代码、测试、README、设计真源、control doc 或 reviewer artifact，未 commit，未进入 implementation。

## 第一性原理与 Owner 判断

总控接受的 PF-01 至 PF-06 均成立，且严重性没有被高估。它们不是要求扩大 R3-D，而是补齐现有三 slice 内已经承诺的 owner contract：

- XBRL query owner 若不能区分 exception、合法空集、partial 与 all-failed，read/tool 层无法恢复真实执行事实。
- producer raw count 与 read-side dedup count 是两个不同事实；requiredness/owner 不明确会再次形成 extra/shadow contract。
- processor freshness 与 meta freshness面向不同调用路径；只修 processor build 会让 list/info/citation 继续返回旧事实。
- 10-Q expansion 的 ref 行为决定 refresh helper 能否安全重建索引，必须以 expansion owner 的直接代码事实裁决。
- HTML/OCR 没有 XBRL decimals，若 plan 不指定自己的 scale evidence owner，implementation 必然现场发明 fallback。
- LLM-facing description 与测试选择器都属于公开契约验证面；模糊模板和可 0-selected 的命令不能证明语义闭环。

正确 owner 保持不变：XBRL execution summary 与 financial producer contract 归 Fins domain/processor；dedup count 归 read projection；source revision 归 storage，reuse decision 归 read runtime；10-Q ref 集合归 expansion owner，index/table map 归 virtual-section mixin；HTML/OCR scale 归对应文本提取 helper；tool description 归 Fins tool schema。

## Controller Accepted Plan Fixes

### PF-01 — 已修复

直接证据：

- `dayu/fins/processors/sec_xbrl_query.py` 当前对 `query_obj.execute()` 使用 catch-and-continue，exception 与空 list 同样落成空 rows。
- `sec_processor.py` 与 `bs_report_form_common.py` 当前把 `_query_facts_rows()` 当 list，并各自用 `len(rows)` 构造 raw total。
- 本地 edgartools `5.30.0` 的 `edgar.xbrl.facts.FactQuery.execute()` 返回 `list[dict]`；正常零命中返回 `[]`，且没有吞掉 `get_facts`/filter/transform exception。

Plan 修正：

- 增加 implementation-start characterization pre-check；定义合法空 list 为 successful，execute/query-chain exception 与 malformed outer/row shape 为 failed，每 concept 固定执行一次、零 retry。
- 明确 attempted/successful/failed accounting、partial/all-failed matrix与 bounded identity/cause 规则。
- 明确两个 caller 统一消费 `summary.rows/successful_concepts/failed_concepts`，all-failed 不构造 payload。
- 明确 XBRL concept query 的 `data_quality=xbrl` 表示 XBRL 查询正常执行；`total=0` 表示没有匹配 fact。Financial statement 的 empty-row invariant 只约束 `FinancialStatementResult`，不误伤合法零命中 query。
- 同步命名 assertions、LLM-facing description 与 stop condition；未来依赖漂移必须在 producer 修改前 fail closed。

### PF-02 — 已修复

直接证据：

- 当前 `deduped_fact_count` 由 `read_runtime_helpers._normalize_xbrl_query_payload()` 在 read-side 去重后派生；processor/domain raw payload 的 owner fact 是 `total == len(raw facts)`。
- 当前 public `XbrlQueryResult` 把 dedup count 放在 `total=False` 可选字段中，requiredness 隐含。

Plan 修正：

- 明确 `deduped_fact_count` 不属于 domain `XbrlFactsResult`；raw producer夹带该字段须 fail closed。
- 明确它属于 public read projection，类型为 required `int`，无论是否发生删除都等于 public facts 长度，不放 extra、不用 `NotRequired`。
- 明确 raw `total` 始终复制 producer count且不得被覆盖，并增加有/无去重、raw extra、source scan assertions。

### PF-03 — 已修复

直接证据：

- 当前 `_get_source_meta_cached_by_kind()` 与 `_get_document_meta_cached()` cache hit 后直接返回 meta，不读取 storage revision。
- `list_documents` 与 citation 会独立调用 meta helper，不需要先构建 processor。

Plan 修正：

- 要求 kind-specific meta helper 或等价唯一 owner 独立比较 revision；no-kind positive read先解析 kind再委托该 owner，不保留无 revision 快路。
- 规定 meta rebuild 的 `M1 -> read/parse -> M2` 与 processor 的 `R1 -> build -> R2`；两类 race 均固定零次自动 retry并立即 typed fail，不留给实现者选择重试次数。
- freshness matrix新增 independent meta read；tests必须在不调用processor registry时验证 list/info/citation更新，并分别断言 processor/meta race只尝试一次且不cache混合结果。

### PF-04 — 已修复

直接证据：

- 当前 `expand_ten_q_virtual_sections_content()` 只修改已有 section 的 `start/end/content/preview` 并排序，没有 append/insert，也不创建 child ref。

Plan 修正：

- 明确 S2 不设计 child ref schema；expansion 前后 section object/ref multiset必须相同且refs唯一。
- 测试须在 table assignment 前断言 ref 集合/唯一性，再验证 refresh 后索引与双向 table map。
- 若实现时发现 expansion 已创建或必须创建 child ref，停止并回 plan/re-review，由 expansion owner定义唯一规则；禁止 refresh consumer追加后缀消歧。

### PF-05 — 已修复

直接证据：

- HTML table 已由 `_infer_scale_from_caption()` 读取 caption scale；OCR 已由 `_extract_ocr_currency_and_scale()` 读取 heading scale。
- 当前 HTML/OCR units builder会把 scale 拼入 units，部分 OCR summary path固定 `scale=None` 却声明 `extracted`。

Plan 修正：

- 分别把 HTML caption helper 与 OCR heading helper固定为各自 direct-evidence scale owner；禁止从currency、units、金额绝对值或下游字段反推。
- 所有 HTML/OCR/table/OCR-summary producer把scale与fiscal evidence交给同一quality/reason owner；无scale直接证据时 `partial + scale_unavailable`，两类语义都缺时使用组合reason。
- 明确units不再承载scale，并增加HTML caption、OCR heading、missing-scale、missing-scale-and-period、OCR summary producer tests。

### PF-06 — 已修复

直接证据：

- 当前两个 tool description只有“读取标准财务报表”和“查询结构化 XBRL 数值 facts”，没有说明结果字段与判断规则。
- `tests/fins/test_sec_pipeline_download.py` 当前没有同时命中 `6k and decode` 的命名 test，原命令可能 0 selected。

Plan 修正：

- 为 `get_financial_statement` 与 `query_xbrl_facts` 提供可直接实现的简洁中文模板，覆盖periods/scale/units/quality/reason与raw total/required dedup count，并解释合法XBRL零命中。
- S2固定新增 `test_sec_6k_preview_rejects_invalid_utf8`，validation与aggregate均按pytest node id执行；test不存在或未收集时命令直接失败。

## Scope 与 Slice 结构

- 保持 3 个 implementation slices：S1 financial/XBRL/public projection；S2 virtual section/source freshness/read failure；S3 fiscal/normalization/version/ticker/docs aggregate closure。
- PF-01、PF-02、PF-05、PF-06 的LLM/financial部分吸收到S1；PF-03、PF-04与PF-06的6-K decode验证吸收到S2；S3不扩 scope。
- 没有直接证据要求第4 slice；现有三 slice仍按owner、validation matrix与failure blast radius形成最小稳定闭环。
- 未引入 tool-security、R3-E、upload/download security、SSRF、TLS、redirect、byte budget或security schema。
- 未引入6-K dual-engine routing、creation-lock lifetime、full `DocumentMeta` migration。

## Validation

- `git diff --check`: pass（exit 0，无输出）。
- untracked plan/artifact no-index whitespace checks: pass（均无 whitespace diagnostic；exit 1 仅表示文件相对 `/dev/null` 存在内容差异）。
- pytest / pyright: 未运行；本 gate 只修改 Markdown plan/review artifact，禁止实现生产/测试代码。

## Residual Risks 与 Blocking Questions

- edgartools后续版本行为漂移：由S1 characterization tests与stop condition fail closed，owner为S1 adapter contract。
- revision comparison的额外storage read成本：correctness优先，性能优化不属于本plan-fix；owner为S2 storage/read cache。
- HTML/OCR直接文本没有scale evidence：不再是open design，按producer `partial` contract表达。
- Blocking questions: 0。

## Gate Result

- PF-01: 已修复。
- PF-02: 已修复。
- PF-03: 已修复。
- PF-04: 已修复。
- PF-05: 已修复。
- PF-06: 已修复。
- Implementation slices: 3（保持S1/S2/S3）。
- Decision: `ready-for-plan-rereview`。
- Next gate: controller派发AgentMiMo与AgentDS parallel plan re-review；本轮未进入implementation。
