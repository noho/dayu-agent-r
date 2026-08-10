# WU-CLI-DOWNLOAD-02 plan review 裁决

## 裁决对象

- Plan：`docs/gateflow/wu-cli-download-02-plan-20260810.md`
- 独立 review：
  - `docs/reviews/plan-review-20260810-161417.md`
  - `docs/reviews/plan-review-20260810-161634.md`
- 基线：`3811f95c82fbf0daf15740a5d217eed4d8b49df5`
- 当前结论：**plan 尚未接受；先修复本裁决接受项，再做 MiMo/DS 双路 re-review。**

## 逐项裁决

### DS review `161417`

1. **SEC 构造点未纳入 allowed files：接受。**
   `FinsDownloadDocumentResult` 是跨 CN/HK/SEC 的公共 typed result；不得用默认值掩盖未迁移调用点。Slice 3 必须先穷举全部构造点，将 `sec_pipeline.py` 及对应 owner tests 纳入，并由 SEC 构造点显式投影不适用的空 coverage。
2. **`FinsDownloadPublicDocument.to_json_value()` 漏列：接受。**
   Plan 必须写明 dataclass、runtime projection、显式 JSON serializer、CLI/wait 消费测试的完整链路。
3. **`FinsDownloadEffectiveFilters` 可构造非法双 true：接受，但修复不得形成双 owner。**
   `download_contract.py` 内新增唯一私有 mode invariant helper；`FinsDownloadRequest` 在业务 operation 前调用，`FinsDownloadEffectiveFilters` 作为同一事实的公共投影也复用该 helper。parser、Service、workflow 不得复制判断或保留 precedence/fallback。
4. **rebuild missing 回归断言不足：接受。**
   CN/HK bare rebuild 都必须显式断言 `missing_periods == ()`/空列表投影，且不联网、不覆盖 source、不触发 process/processed/reprocess。
5. **results/report 分类优先级不足：接受。**
   Plan 必须给出 category-first 的明确分类矩阵与负例；report 只产生 FY/H1 singleton，results 才允许产生 Q1～Q4 identity 及 coverage。共享 token 不得靠偶然遍历顺序裁决。
6. **candidate 字段迁移未穷举：接受。**
   实施前用 `rg` 穷举 `CnReportCandidate` 构造与 `.fiscal_period` 消费者；当前直接证据已显示 `cn_download_filing_workflow.py` 等文件不在原清单，必须补齐 slice allowed files，禁止 compatibility property。

Open questions 一并裁决：`covered_fiscal_periods` 不使用兼容默认；SEC 显式传空 tuple；source meta 的 `form_type`/`fiscal_period` 均从 `identity_period` 派生；CLI 行至少明确展示 identity 与 coverage，不新增模糊的内部 label。

### MiMo review `161634`

1. **HKEX `t2code=-2` 缺证：接受“补强直接证据”，不接受“必须找到未公开 API 文档”作为 blocker。**
   总控已用 production `HkexnewsDiscoveryClient` 对 0700、`2025-01-01..2026-04-30` 直接查询 `t1code=10000,t2Gcode=3,t2code=-2`：只返回 results group 的 12 条 raw rows，并包含 `11793094` 中期业绩和 `12056833` 末期业绩；中英文查询均复现。Plan 必须记录精确参数、row/category/source URL 与验证方式；实现后 owner test 和真实运行再次验证。直接 provider 响应是本 owner 的数据证据，不把无可得的非公开文档当新前置条件。
2. **results/report token 重叠：接受。** 与 DS finding 5 合并修复。
3. **allowed files 不完整：接受。** 与 DS finding 6 合并修复，并明确 Slice 2/3 对共有文件的修改边界。
4. **coverage public JSON 下游未穷举：接受。** 与 DS finding 2 合并；必须列出所有构造、序列化和 consumer tests，不做旧 schema 兼容。
5. **HK effective forms 与 optional rows 可能混淆：接受为低风险 UX 验证项。**
   `effective forms` 仍只表达 market baseline；document row 显示实际 identity/coverage。Plan/README/真实 screen 应让用户能够区分二者，但不得为此新增另一套 policy 或在 CLI 下游重算 optional 语义。
6. **`ingestion_runtime.py` 80% 门槛过重：拒绝其豁免建议。**
   用户和 `AGENTS.md` 要求修改生产文件的单文件覆盖率目标不低于 80%。Plan 应先确认该文件是否确属必要 owner projection；若必要则保留并真实测量，不用 pragma/omit/仅增量行口径绕过；若无需修改则从 diff 删除。不能用测试成本改变验收契约。
7. **policy `notes` 无目标映射：接受。**
   从 `CnDownloadPeriodPolicy` 删除 `notes`；workflow 自己拥有运行期 cancellation/diagnostic notes，form policy 只拥有 effective/discovery/missing 三集合。

### 总控追加的证据约束

1. 直接解析 `12056833` 对应英文 HKEX PDF，正文明确包含 `Fourth Quarter of 2025` 与截至 12 月 31 日的三个月数据；因此该 source 的 FY/Q4 coverage 有文档内容证据，而非仅从 CLI summary 或时间戳推断。
2. HKEX 中英文 raw title 本身只写 annual/final results，没有直接写 fourth quarter。Plan 不得声称 title 单独证明 Q4 coverage；应把 provider results category 与通用 result material contract写清，并在真实 0700 evidence 中以 PDF/Docling 内容验证 coverage。禁止 ticker/title/date/URL 特例。
3. Q2/H1、Q4/FY 两对 material 必须保留不同 source identity。`covered_fiscal_periods` 只能描述一份 source 的内容覆盖，不能参与 mandatory missing 满足，也不能复制 document/manifest entry。

## 修复后 re-review 必须回答

- 每个新增/变更 public typed field 的全部构造、校验、序列化、持久化和 consumer 是否已穷举？
- category-first 分类矩阵是否能排除 report/results 共享 token 的误判，并含通用正负例？
- `effective_periods`、`discovery_periods`、`missing_eligible_periods` 是否仍由唯一 policy owner 产生？
- Slice allowed files 是否覆盖当前全部直接调用点，同时没有把 Host/Engine、通用 runtime/CI/harness 拉入？
- 覆盖率、真实观察和 README 触发项是否保持用户冻结的验收口径？

## 第一轮 re-review 裁决

Re-review artifacts：

- `docs/reviews/plan-review-20260810-164812.md`：MiMo，结论 `pass`。
- `docs/reviews/plan-review-20260810-164911.md`：DS，结论 `fail`。

逐项裁决：

1. **DS N1：接受，blocking。** `cn_report_selection.py` 当前两处直接消费 `query.target_periods`，但修订 plan 只把它列入 Slice 3；Slice 2 删除旧字段后会立即造成 pyright 失败。必须将该文件加入 Slice 2，并在共有文件表明确 Slice 2 只做 query rename、Slice 3 才做 classification/projection。
2. **DS N2：接受。** `CN_FISCAL_PERIOD_ORDER` 在 Slice 2 首次由 policy 使用；共有文件表必须明确 Slice 2 定义常量，Slice 3 的 projection/selection 只复用。
3. **MiMo C01：按直接代码证据关闭。** `dayu/fins/domain/filing_semantics.py::FISCAL_PERIODS` 已存在；无需创建新模块或替代校验真源。Plan fix artifact 应记录该路径核验。
4. **MiMo C07：接受文字澄清。** 删除的是 `commit_cn_filing_source_document(...)` 与 `_build_base_meta(...)` 对 caller 暴露的冗余 `form_type` 参数；内部 `_build_upsert_request(...)` 仍显式接收从 candidate identity 派生的局部值。这不是保留外部双真源。

本轮只允许上述 plan/artifact 修订；不得实施产品代码。修复后 MiMo/DS 必须再次独立 re-review，DS N1 未关闭前不得形成 accepted plan commit。

## 第二轮 re-review 与 accepted plan 裁决

- `docs/reviews/plan-review-20260810-165513.md`：DS，结论 `pass`。
- `docs/reviews/plan-review-20260810-165548.md`：MiMo，结论 `pass`。

两路均以直接 plan/代码证据确认 DS N1/N2 与 MiMo C01/C07 已关闭，并再次检查 category-first matrix、fresh-schema strict parse、全部构造/消费点、slice allowed files、coverage、README 与 production evidence 范围，未发现新的 blocking finding。

总控裁决：**accepted plan**。下一入口是 Slice 1 implementation；每个 slice 仍须独立 implementation、MiMo/DS 双路 review、accepted finding fix/re-review 和 protected commit，不得跨 slice 偷跑。
