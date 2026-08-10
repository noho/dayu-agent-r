# `WU-CLI-DOWNLOAD-02-DL-F12-F14` Plan Review Fix Artifact

## 1. Gate 与范围

- Work unit：`WU-CLI-DOWNLOAD-02-DL-F12-F14`
- Gate：plan review -> fix
- 日期：2026-08-10
- 修复对象：`docs/gateflow/wu-cli-download-02-plan-20260810.md`
- 裁决真源：`docs/gateflow/wu-cli-download-02-plan-review-adjudication-20260810.md`
- Review inputs：`docs/reviews/plan-review-20260810-161417.md`、`docs/reviews/plan-review-20260810-161634.md`
- Changed files：修订原 plan；新增本 artifact
- 明确未做：产品代码、tests、README、post-fix CLI、pyright、pytest、coverage、commit、push、PR
- Completion status：`fix complete / next=MiMo+DS re-review`，按用户要求完成后停下等待总控
- Artifact path：`docs/gateflow/wu-cli-download-02-plan-fix-20260810.md`

## 2. 第一性原理复核

修复前重新核对了动机与 owner。结论仍是问题真实且严重性评估正确：

1. overwrite 与 rebuild 具有相反 I/O 边界，双 true 不是第三种合法模式；应由 public typed invocation contract 在 workspace/runtime 前拒绝。
2. HKEX raw discovery 不返回 row 时，下游无法恢复材料；全 results group 的直接 provider response 是 discovery owner 的根因证据。
3. material identity 与内容 coverage 是两个事实；把 coverage 当 identity 会复制 source，把 identity 当 coverage 会丢失业务事实。
4. effective、discovery、missing eligibility 是三个集合；下游从一个 tuple 猜另外两个会产生跨市场错误。

因此本 fix 没有采纳默认值兼容、CLI 重算、policy notes、ticker/title/date/URL 特例或 storage manifest 扩张；只补齐 owner contract、真实调用点与验证矩阵。

## 3. `rg` 穷举证据

在更新 allowed files 前，从仓库根执行了以下只读枚举：

```bash
rg -l --glob '*.py' 'CnReportCandidate\s*\(' dayu tests
rg -l --glob '*.py' 'candidate\.fiscal_period|item\.fiscal_period' dayu/fins/pipelines dayu/fins/downloaders tests/fins
rg -n --glob '*.py' 'TargetPeriodResolution|resolve_target_periods|\.target_periods|target_periods=' dayu/fins/pipelines dayu/fins/downloaders tests/fins
rg -n --glob '*.py' 'FinsDownloadDocumentResult\s*\(' dayu tests
rg -n --glob '*.py' 'FinsDownloadPublicDocument\s*\(' dayu tests
rg -n --glob '*.py' 'FinsDownloadEffectiveFilters\s*\(' dayu tests
rg -n --glob '*.py' 'commit_cn_filing_source_document\s*\(|build_cn_filing_ids\s*\(' dayu tests
rg -n --glob '*.py' 'download\.to_json_value\(\)|document_rows|_download_document_line|FinsDownloadPublicSummary' dayu/cli dayu/service dayu/fins tests/cli tests/service tests/fins
```

直接结果已写入 plan §4.3：

- `CnReportCandidate` 的 production constructor 只在 `cn_report_selection.py`，但 identity consumer 还包括原计划漏掉的 `cn_download_filing_workflow.py`、`cn_download_source_upsert.py`。
- `FinsDownloadDocumentResult` production constructors 为 CN 3 处、SEC 4 处、runtime 2 处。
- `FinsDownloadPublicDocument` production constructor 只有 runtime 1 处；JSON 是 `direct_events.py::to_json_value()` 显式 serializer，随后由 wait adapter 与 CLI typed row 消费。
- period policy/query rename 涉及 form utils、models、workflow、rebuild、selection、CNInfo、HKEX 与 protocol typed contract；同名其它业务模型字段不属于本 WU。
- download 路径的 `build_cn_filing_ids(...)` production calls 只有 workflow/filling workflow 两处；upload 路径同名调用不改。

## 4. DS review `161417` 逐 finding 修复

### DS-01 SEC 构造点漏列 — `已修复`

- 裁决：接受。
- 修复：Slice 3 allowed production files 新增 `dayu/fins/pipelines/sec_pipeline.py`，test files 新增 `tests/fins/test_sec_pipeline_download.py`。
- Contract：`covered_fiscal_periods` 无默认值；SEC 4 个构造点显式传 `()`，runtime 2 个 non-persisted 构造点也显式传 `()`。
- 证据：plan §4.3 构造点表、§5.3 public projection、§6 Slice 3 items 10-11。

### DS-02 显式 JSON serializer 漏列 — `已修复`

- 裁决：接受。
- 修复：plan 固定 workflow row -> CN adapter -> typed result -> runtime public projection -> public document -> `FinsDownloadPublicDocument.to_json_value()` -> summary `documents[]` -> wait adapter/CLI 的完整链路。
- JSON contract：serializer 必须写 `"covered_fiscal_periods": list(...)`；CN/HK/SEC strict JSON round-trip 都断言 key 始终存在。
- 证据：plan §4.3、§5.3、§6 Slice 3 item 11、§7.3 JSON validation。

### DS-03 EffectiveFilters 双 true 防御缺口 — `已修复`

- 裁决：接受，但不得形成双 owner。
- 修复：plan 指定 `download_contract.py` 内唯一私有 `_validate_download_mutation_mode(...)`；request 与 effective-filter 复用同一个 helper，parser/Service/workflow 不复制判断。
- Tests：两种类型都覆盖 `00/10/01` 成功与 `11` 精确失败，另有静态 guard 证明只有 helper 实现 conjunction。
- 证据：plan §5.1、§6 Slice 1 items 1/5。

### DS-04 rebuild missing 回归不足 — `已修复`

- 裁决：接受。
- 修复：CN bare 与 HK bare rebuild 都必须断言 workflow 空 list、typed/public 空 tuple；provider/HTTP 为 0，不覆盖 source，不触发 process/processed/reprocess。
- 证据：plan §6 Slice 2 item 9、Slice 3 item 8。

### DS-05 results/report 分类优先级不足 — `已修复`

- 裁决：接受。
- 修复：plan §5.3 改为 category-first 封闭矩阵。category 先唯一判定 report/results；family 内再使用 duration/quarter facts。共享 `HALF YEAR`/`半年`、`FULL YEAR`/`全年` 不再靠枚举遍历顺序。
- 正负例：Q2 result vs H1 report、Q4 result vs FY report、three+six month、category 缺失/冲突、report+quarter title 都有确定结果。
- 证据：plan §5.3 matrix、§6 Slice 3 items 2-4。

### DS-06 candidate 字段迁移未穷举 — `已修复`

- 裁决：接受。
- 修复：完成 §3 `rg`，补齐 `cn_download_filing_workflow.py` 与全部真实 consumers；不新增 compatibility property。Slice 2/3 共有文件用表格精确拆分修改边界。
- 证据：plan §4.3、§6 Slice 3“共有文件边界”与 allowed files。

### DS open questions — `已修复`

- coverage 无默认值，SEC 显式空 tuple。
- source meta 的 `form_type`、`fiscal_period`、`report_kind` 全部由 `identity_period` 派生；commit/base-meta 删除 caller `form_type` 参数，upsert request 仍显式接收派生值。
- CLI 行保留 `form_or_period=<identity>` 并新增 `covered_fiscal_periods=[...]`，不新增模糊内部 label。

## 5. MiMo review `161634` 逐 finding 修复

### MiMo-F01 `t2code=-2` 直接证据不足 — `已修复`

- 裁决：接受补强直接证据，不把不可得的非公开 API 文档当 blocker。
- 修复：plan 记录 production client 的精确 ticker/stockId/window/category 参数、繁中/英文各 12 条 raw rows、row category 与 source URL。
- 冻结 URLs：
  - `11793094` 中文：`https://www1.hkexnews.hk/listedco/listconews/sehk/2025/0813/2025081300262_c.pdf`
  - `12056833` 中文：`https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0318/2026031800389_c.pdf`
  - `12056833` 英文：`https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0318/2026031800388.pdf`
- 边界：英文 PDF/Docling 的 `Fourth Quarter of 2025` 是 coverage 内容证据；raw title 本身不单独证明 Q4。ID/URL 不进入 production。
- 证据：plan §4.2 raw provider evidence、§9.5 post-fix evidence。

### MiMo-F02 token 重叠误分类 — `已修复`

- 与 DS-05 合并，见 plan §5.3 category-first matrix。

### MiMo-F03 allowed files 不完整 — `已修复`

- 与 DS-06 合并；§4.3 给出 constructors/consumers，§6 明确 Slice 2/3 共有文件边界。

### MiMo-F04 public JSON 下游未穷举 — `已修复`

- 与 DS-02 合并；显式列出 serializer、runtime constructor、CLI typed consumer、wait JSON consumer 与 owner tests，不做旧 schema 兼容。

### MiMo-F05 HK baseline 与 optional row UX 混淆 — `已修复`

- `effective forms` 仍唯一表达 applicable baseline；不新增另一套 policy 或 `optional` label。
- document row 明确同时展示 identity `form_or_period` 与 `covered_fiscal_periods`；README 与真实 screen 必须说明 baseline forms 与实际发现材料的差异。
- 证据：plan §5.3 public projection、§8 README、§9.4-9.5 evidence。

### MiMo-F06 `ingestion_runtime.py` coverage 豁免建议 — `已修复`

- 裁决：拒绝豁免建议。
- 修复：plan 固定所有 changed production `.py` 整文件 line coverage 各自 `>=80%`；不允许 aggregate、incremental、omit、pragma、降阈值或大文件豁免。若文件非必要则从 diff 删除。
- 证据：plan §7.2。

### MiMo-F07 policy `notes` 无目标映射 — `已修复`

- 裁决：接受。
- 修复：从 `CnDownloadPeriodPolicy` 删除 `notes`；policy 只拥有 effective/discovery/missing 三集合，workflow 继续拥有运行期 notes。
- 证据：plan §5.2、§11。

### MiMo open questions — `已修复`

- `t2code=-2` 由 direct provider response 证明，implementation/post-fix evidence 再验证，不要求非公开文档。
- `commit_cn_filing_source_document` 的 form 只从 candidate identity 派生，见 DS open questions。
- CLI 不新增 optional policy；用 baseline summary + identity/coverage row 自解释。

## 6. 总控追加证据约束

| 约束 | Fix status | Plan evidence |
|---|---|---|
| annual/Q4 coverage 必须来自 PDF 内容，不得由 title/时间戳推断 | 已修复 | §4.2、§9.5 |
| raw title 不写 fourth quarter，production 禁止 ticker/title/date/URL 特例 | 已修复 | §4.2、§5.3、§7.3 guards |
| Q2/H1、Q4/FY 保留独立 source identity；coverage 不满足 mandatory missing、不复制 manifest | 已修复 | §5.3 identity flow、四材料矩阵、Slice 3 items 5-7 |
| 唯一 canonical period order，不在 policy/projection/selection 重复硬编码 | 已修复 | §5.2 `CN_FISCAL_PERIOD_ORDER` |

## 7. Re-review 问题的计划内答案

1. Public typed field：构造、owner validation、source meta 持久化、runtime projection、显式 JSON serializer与 CLI/wait consumers 已由 `rg` 穷举并进入 allowed files/tests。
2. 分类矩阵：先 category family、后 duration；report 永不产生 quarter，results 不产生 FY/H1 identity，含正负例与 ambiguous fail-closed。
3. 三集合：只由 `resolve_download_period_policy(...)` 产生；无 notes、默认兼容或下游反推。
4. Allowed files：覆盖当前所有直接 call sites；未引入 Host/Engine、`dayu.runtime`、CI/harness 或 storage schema。
5. 验收口径：所有 changed production files 整文件 line coverage `>=80%`；post-fix production evidence 延后到实现/review 后；根/Fins/tests README 均按自身写作约束更新当前事实。

## 8. Validation 与 docs decision

本 fix 只修改 Markdown，执行了：

- 分支/worktree preflight；
- 四份指定 plan/review/adjudication artifact 完整读取；
- §3 所列全部 `rg` 构造/消费点枚举；
- README 写作边界读取；
- plan 静态复核：无 policy `notes` 字段、无 coverage 默认值方案、SEC 与 JSON 全链均显式列入；
- 对两份未跟踪 artifact 分别执行 `git diff --no-index --check /dev/null <artifact>`；无 whitespace error 输出，检查通过。

本 gate 不更新 README；implementation 稳定后更新 `README.md`、`dayu/fins/README.md`、`tests/README.md`。Host/Engine/dayu README 与 design docs 不更新。

## 9. Residual risks / uncovered areas

| Residual risk / uncovered area | 分类 | Owner / destination |
|---|---|---|
| 全 results group 的真实分页量、provider 变动 | covered by later approved slice | Slice 3 HKEX owner tests + post-fix provider evidence |
| category/title 通用矩阵在更多发行人措辞上的边界 | covered by later approved slice | Slice 3 parameterized positive/negative tests + real 0700 evidence |
| `ingestion_runtime.py` 等 changed file 的整文件 line coverage 成本 | covered by later approved slice | implementation validation；不得豁免 |
| fresh-schema coverage meta 与 public JSON 实际运行一致性 | covered by later approved slice | Slice 3 owner tests、pyright、JSON round-trip、post-fix evidence |
| 当前尚未执行 MiMo/DS re-review | covered by later approved slice | 总控下一 gate |

没有 unclassified residual risk，没有 blocking open question。本 artifact 完成后停在 `next=MiMo+DS re-review`，等待总控。
