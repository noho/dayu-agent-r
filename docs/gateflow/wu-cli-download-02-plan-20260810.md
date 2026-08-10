# `WU-CLI-DOWNLOAD-02-DL-F12-F14` Gateflow Plan Gate

## 1. 文档状态

- Work unit：`WU-CLI-DOWNLOAD-02-DL-F12-F14`
- Gate：plan（经 plan review fix 修订）
- 日期：2026-08-10
- Goal Confirmation：`docs/gateflow/wu-cli-download-02-goal-confirmation-20260810.md`
- 用户冻结输入：`docs/cli_ci.md`
- 前序 Oracle 裁决：`docs/gateflow/wu-cli-download-01-post-fix-oracle-adjudication-20260810.md`
- Design inputs：`docs/host/design.md`、`docs/engine/design.md`
- Plan reviews：`docs/reviews/plan-review-20260810-161417.md`、`docs/reviews/plan-review-20260810-161634.md`
- First re-reviews：`docs/reviews/plan-review-20260810-164812.md`、`docs/reviews/plan-review-20260810-164911.md`
- Review adjudication：`docs/gateflow/wu-cli-download-02-plan-review-adjudication-20260810.md`
- 当前结论：动机成立且严重性评估正确。DL-F12 是公开调用契约允许两个相斥 mutation mode 同时进入 operation；DL-F13 是 HKEX provider category discovery 丢失原始候选，并进一步暴露单期间 candidate 无法承载合并披露；DL-F14 是单一 `target_periods` 同时承担默认、发现与 missing 三种不同语义。三者均为 owner contract 问题，不能在 CLI output、summary、测试 fixture 或腾讯特例中补偿。
- 本 artifact 已逐项落实原 plan review 与第一轮 re-review 的总控裁决；两轮逐 finding 修复证据分别见 `docs/gateflow/wu-cli-download-02-plan-fix-20260810.md` 与 `docs/gateflow/wu-cli-download-02-plan-fix-2-20260810.md`。它不授权本轮修改产品代码、测试或 README，也不授权 implementation、post-fix CLI、commit、push 或 PR。下一入口只能由总控发起第二轮 MiMo/DS 双路 re-review。

## 2. Preflight 与输入完整性

| 检查项 | 直接结果 | 判定 |
|---|---|---|
| branch | `codex/download-oracle` | 非保护分支，可规划 |
| HEAD | `3811f95c82fbf0daf15740a5d217eed4d8b49df5` | 本计划读取的代码基线 |
| `github/main` | `bad90963abad48d29b5571d44a1cd9a80e0e2d77` | 可解析 |
| ahead / behind | `github/main...HEAD = 0 / 19` | 当前分支 ahead 19、behind 0 |
| merge / rebase / conflict | 无 | 无进行中的历史改写或冲突 |
| worktree | `docs/cli_ci.md` 已修改；WU-01 与本 WU gate/review artifacts 未跟踪 | `docs/cli_ci.md` 与 WU-01 均为无关/冻结输入，原样保留；本 fix 只改原 plan 并新增 plan-fix artifact |

Preflight 后未 checkout、merge、rebase、reset、commit、push 或创建 PR。本 re-review fix loop 2 唯一允许写入的是本 plan 与 `docs/gateflow/wu-cli-download-02-plan-fix-2-20260810.md`；上一轮 fix artifact 和全部 review/adjudication 输入只读保留。

## 3. 第一性原理判断、目标与非目标

### 3.1 第一性原理判断

1. `overwrite` 表示允许远端下载覆盖完整本地 source，`rebuild` 表示只基于本地 source 重建下载元数据且不访问远端。二者要求相反的 I/O 边界；同时为真不是有意义的第三种模式，必须在 public request 成为可执行 operation 前拒绝。
2. Provider 没有返回 raw row 时，任何下游 classifier、summary 或 storage 都不可能正确恢复该材料。0700 Q2/Q4 的直接数据证明 HKEX 全 `業績` 组存在对应 row，因此 DL-F13 的首要 root cause 是 discovery category 过窄，不是 UI 漏显示。
3. “一份文档属于哪个 material identity”与“该文档内容覆盖哪些业务期间”不是同一事实。Q2 业绩与 H1 中期报告、合并年度/Q4业绩与 FY 年报分别是不同材料；复制一份 provider source 会破坏 identity，压成单值又会丢失 coverage。
4. “默认向用户承诺哪些 forms”“为了发现实际 optional material 要搜索哪些 periods”“哪些未发现 periods 可以报告 missing”是三个不同集合。用一个 tuple 表达三者必然在 CN 或 HK 至少一方产生错误语义。

### 3.2 目标与完成定义

实现 gate 完成时必须同时满足：

1. DL-F12：`--overwrite --rebuild` 与 `--rebuild --overwrite` 均以 exit 2 结束；Service factory、operation、网络和 workspace 业务写入均为 0；help 明确两者不可组合；单独使用任一 flag 的既有语义不变。
2. DL-F14：CN bare-default 的 effective/discovery/missing-eligible 均为 `FY,H1,Q1,Q3`；HK Main Board bare-default 的 effective 与 missing-eligible 为 `FY,H1`，discovery 为 `FY,H1,Q1,Q2,Q3,Q4`；显式 forms 在两市场都令三个集合等于显式 canonical 集合，因此显式 CN Q2/Q4 行为保持不变。
3. DL-F13：HKEX 对任一季度 discovery 只查询一次 `公告及通告 -> 業績` 全 results group，而不是 `季度業績` 单一子类；通用 selection 能把 Q2 结果、H1 报告、合并 FY/Q4 结果、FY 年报投影为四个不同 material/identity；同一 provider source 只产生一个 document identity。
4. CN/HK candidate、workflow result、source meta、filing manifest identity、public terminal row、missing periods 都从 typed period projection / typed form policy 派生；CLI 不扫描 storage、不重算期间、不隐藏 missing。
5. owner tests、受影响 test union、Ruff、compileall、全量 pyright、diff/static guards 全部通过；每个修改的 production `.py` 文件单文件 line coverage 均不低于 80%。
6. 实现与审查完成后的 production CLI post-fix run 产生新的 immutable observed-behavior evidence；旧冻结报告与 Oracle/registry/readiness 不回写，等待用户裁决。

### 3.3 非目标

- 不新增 `--source`、market 参数、issuer policy 配置、GEM 板块识别、multi-ticker、prune、后台 job 或 Host Run。
- 不把 Q1～Q4 建模为所有港股发行人的 mandatory baseline。
- 不把 CN Q2/Q4 alias 到 H1/FY，不改变显式 CN `--forms Q2 Q4` 的当前“可请求、无候选时报告 missing”行为。
- 不使用 0700、腾讯、固定 document id、固定日期、固定 URL 或完整标题特例。
- 不复制 PDF/source document 来表达多期间，不为同一 provider source 创建 FY/Q4 或 H1/Q2 两份 identity。
- 不改变 `build_cn_filing_ids(...)` 的 hash seed、现存 identity 算法或 amendment 语义；本 WU 只确保它恰好一次消费 typed `identity_period`。
- 不新增兼容 property、旧字段 alias、compat wrapper、loose parsing、`.get()` 默认补偿或下游 fallback。
- 不修改 Host / Engine contract、实现、design 或 README。direct download 继续位于 `UI -> Service -> Fins` 路径，不进入 Host lifecycle；Engine 不拥有 provider discovery、财期或 source storage。
- 不在本 WU 更新 `docs/cli_ci.md`、Oracle/scenario registry、readiness proof 或旧 observed report。

## 4. Design alignment 与直接代码证据

### 4.1 Design alignment

- `docs/host/design.md` 将 Host 定义为 Agent/Runner 生命周期、取消与治理真源，而不是财报 provider、期间分类或 storage owner。本 WU 不向 Host 注入 Fins 业务语义。
- `docs/engine/design.md` 将 Engine 限定为单次运行编排，不拥有金融业务事实或持久化。本 WU 不修改 Engine。
- 公开依赖仍为 `UI -> Service -> Fins`；CLI 只负责 argv/help 与机械 exit/output，Service 只建立 typed request，Fins pipeline 拥有市场策略、provider discovery、selection 与 source projection。
- source 写入继续且只能经 `dayu.fins.storage` repository protocol/implementation；本 WU 不从 workflow 直接写文件或 manifest。

### 4.2 Root cause 证据矩阵

| Finding | 直接生产代码 / 数据证据 | 唯一 owner |
|---|---|---|
| DL-F12 | `dayu/cli/arg_parsing.py::_register_download_command` 独立注册两个 `store_true`；`dayu/fins/download_contract.py::build_fins_download_request` 原样构造两个 bool；`FinsDownloadRequest` 没有组合不变量；`tests/cli/test_fins_commands.py::test_download_command_maps_args_to_service` 反向固化二者同时成功 | `FinsDownloadRequest` 的 pre-workspace typed invocation invariant；CLI help 只做文案投影 |
| DL-F13 raw discovery | `_PERIOD_TO_CATEGORY_SPEC` 把 Q1～Q4 全映射到 `t2code=13600`；HKEX 全 results group 中 `11793094`（`中期業績`）和 `12056833`（`末期業績`）存在，当前窄查询不返回 | `HkexnewsDiscoveryClient` provider category query |
| DL-F13 classification | `_infer_fiscal_period_from_text` 已有三/六个月、全年等通用 token，但只返回单个 period；`CnReportCandidate.fiscal_period`、source meta、operation result 也都是单值 | `CnReportPeriodProjection` + `cn_report_selection` |
| DL-F13 identity | `build_cn_filing_ids(...)` 由 ticker/form/year/period/amended 生成；若从 covered periods 循环生成会复制同一 source，若只保留一个无类型单值会丢覆盖事实 | pipeline 只用 `identity_period` 调用既有 ID owner 一次；source meta 保留完整 coverage |
| DL-F14 | `DEFAULT_FORMS_CN == DEFAULT_FORMS_HK == FY,H1,Q1,Q2,Q3,Q4`；`TargetPeriodResolution.target_periods` 同时进入 query、windows、`filters.forms` 和 `_resolve_missing_periods` | `dayu.fins.pipelines.cn_form_utils` 的 market-specific typed form policy |

HKEX 直接调查事实冻结为：

- `11793094`，2025-08-13，`中期業績`，标题同时表达截至 2025-06-30 的三个月与六个月结果；material identity 为 Q2 结果，coverage 为 `H1,Q2`。
- `12056833`，2026-03-18，`末期業績`，中英文 raw title 只表达截至 2025-12-31 的年度/全年结果；title 本身不证明 Q4 coverage。对应英文 PDF 的实际正文同时包含 `Fourth Quarter of 2025` 和截至 12 月 31 日的三个月数据，才构成 `identity=Q4, covered=(FY,Q4)` 的内容证据。
- H1 中期报告与 FY 年报属于 `財務報表/環境、社會及管治資料` 下的独立 report material，不得由上述 results 替代。

总控冻结的 raw provider 证据如下，implementation 不得重新发明查询参数：

- 使用 production `HkexnewsDiscoveryClient`，ticker `0700`、HKEX `stockId=7609`、窗口 `2025-01-01..2026-04-30`，精确 category 参数 `t1code=10000`、`t2Gcode=3`、`t2code=-2`；繁中与英文查询各自都只返回 results group 的 12 条 raw rows，并同时包含 `11793094`（`中期業績` / Interim Results）与 `12056833`（`末期業績` / Final Results）。验证方式是保存 production client 的 request 参数与原始 row/category/source URL，不以 CLI summary、搜索页或时间戳替代 raw response。
- `11793094` 中文 source URL：`https://www1.hkexnews.hk/listedco/listconews/sehk/2025/0813/2025081300262_c.pdf`。
- `12056833` 中文 source URL：`https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0318/2026031800389_c.pdf`；英文 source URL：`https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0318/2026031800388.pdf`。
- 上述 URL、document id、ticker 与冻结标题只能进入 test/evidence；production 只实现 category-first 通用规则。实现后 owner HTTP fixture 再验证精确 request/category，post-fix production evidence 再验证 raw rows 与 PDF/Docling 内容。

### 4.3 `rg` 构造/消费点穷举与 allowed-files 真源

plan fix 在更新 §6 前已从仓库根执行精确 `rg`。以下清单是当前基线的完整直接构造/消费结果，不把同名但属于其它业务模型的 `fiscal_period`/`target_periods` 误计入：

| Contract | Production 构造/消费点 | 直接受影响 tests |
|---|---|---|
| `CnReportCandidate` 构造 | `cn_report_selection.py`（CNInfo/HKEX 两个 builder） | `test_cn_download_runtime.py`、`test_cn_pipeline.py`、`test_cn_download_workflow.py`、`test_cninfo_downloader.py`、`test_hkexnews_downloader.py` |
| `candidate.fiscal_period` 消费 | `cn_report_selection.py`、`cn_download_workflow.py`、`cn_download_filing_workflow.py`、`cn_download_source_upsert.py`；`cn_download_rebuild.py` 消费 source-meta identity period | `test_cn_report_selection.py`、`test_cn_download_workflow.py`、`test_cninfo_downloader.py`、`test_hkexnews_downloader.py` |
| `TargetPeriodResolution` / `resolve_target_periods` / `CnReportQuery.target_periods` | `cn_form_utils.py`、`cn_download_models.py`、`cn_download_workflow.py`、`cn_download_rebuild.py`、`cn_report_selection.py`、`cninfo_downloader.py`、`hkexnews_downloader.py`；protocol 只通过 `CnReportQuery` 消费 typed contract | `test_cn_download_workflow.py`、`test_cn_report_selection.py`、`test_cninfo_downloader.py`、`test_hkexnews_downloader.py` |
| `FinsDownloadDocumentResult(...)` | `cn_pipeline.py` 3 处、`sec_pipeline.py` 4 处、`ingestion_runtime.py` 2 处 | `test_cn_pipeline.py`、`test_sec_pipeline_download.py`、`test_fins_ingestion_runtime.py` |
| `FinsDownloadPublicDocument(...)` / JSON | `ingestion_runtime.py` 唯一 production constructor；`direct_events.py::to_json_value()` 显式 serializer；`cli/output.py` typed row consumer；`service/fins_wait_adapter.py` 机械消费 summary JSON | `test_fins_ingestion_runtime.py`、`test_output.py`、`test_fins_wait_adapter.py` |
| `FinsDownloadEffectiveFilters(...)` | `cn_pipeline.py`、`sec_pipeline.py`、`ingestion_runtime.py`；公共类型与唯一 mode helper 位于 `download_contract.py` | `test_fins_ingestion_runtime.py`、`test_output.py`、`test_fins_wait_adapter.py` 另有 fixture constructors，owner invariant 放在 Slice 1 contract tests |

`build_cn_filing_ids(...)` 的 download production 调用只有 `cn_download_workflow.py::_candidate_document_id` 与 `cn_download_filing_workflow.py`；`cn_pipeline.py` 的另一调用属于 upload 路径，不改写。`commit_cn_filing_source_document(...)` 的 production caller 只有 `cn_download_filing_workflow.py`。§6 allowed files 必须覆盖上表所有需要迁移的 owner/call site；`dayu/service/fins_wait_adapter.py` 是确认无需修改的机械 JSON consumer，不因测试更新而扩大 production diff。

## 5. Semantic owner、类型、函数与不变量

### 5.1 DL-F12：唯一 validation owner 与 help 投影

唯一语义 owner 仍是 public invocation contract；同一模块内用一个私有 helper 作为 mode invariant 的唯一实现真源：

- 在 `dayu.fins.download_contract` 新增 `_validate_download_mutation_mode(*, overwrite_existing: bool, rebuild_local_artifacts: bool) -> None`。helper 先校验两个字段确为 `bool`，再在二者同为真时抛 `FinsDownloadUsageError`；固定 actionable 文本说明 `--overwrite` 与 `--rebuild` 不能同时使用、必须只选择一种模式。模块内不得存在第二份 boolean conjunction、precedence 或错误文本。
- `FinsDownloadRequest.__post_init__` 调用该 helper，承担 pre-workspace public request 合法性；`FinsDownloadEffectiveFilters.__post_init__` 作为同一事实的公共投影，也调用同一个 helper，拒绝任何独立构造出的非法双 true。后者是防御性复用，不是第二个语义 owner。
- `build_fins_download_request(...)` 继续负责 canonicalization 并构造 request，不重复写组合判断；所有 CLI/Service production 构造点继续进入同一个 request invariant。
- `_run_fins_direct_command_async -> _prevalidate_download_request -> build_direct_download_request -> build_fins_download_request -> FinsDownloadRequest` 的当前顺序不改，因此该错误发生在 `_resolve_workspace_root`、`FINS_DIRECT_SERVICE_FACTORY`、stream、provider 与 storage 之前。
- `dayu/cli/arg_parsing.py::_register_download_command` 不再成为第二个 validator；不用 `add_mutually_exclusive_group` 重复 owner 判断。两个 option 的 help 文案各自明确“不可与另一项同时使用”，作为同一公开 contract 的 UI projection。parser 仍解析两个 bool，typed request owner 决定组合合法性。

固定不变量：

- `overwrite=False,rebuild=False`、`True,False`、`False,True` 可构造；`True,True` 在 typed request 构造时失败。
- 两种 argv 顺序错误完全等价，exit code 均为 2。
- `FinsDownloadEffectiveFilters(True, True)` 与 request 一样失败；runtime、source adapter、CN/HK/SEC workflow、parser 和 tests 不含 mode precedence、冲突 fallback、默认纠正或复制判断。

### 5.2 DL-F14：market-specific typed form policy

在 `dayu/fins/pipelines/cn_form_utils.py` 以新类型替换语义过载的 `TargetPeriodResolution`：

```text
CnDownloadPeriodPolicy
  effective_periods: tuple[CnFiscalPeriod, ...]
  discovery_periods: tuple[CnFiscalPeriod, ...]
  missing_eligible_periods: tuple[CnFiscalPeriod, ...]
```

CN/HK 的 canonical period order 在 **Slice 2** 由 `cn_download_models.py` 新增唯一常量 `CN_FISCAL_PERIOD_ORDER = (FY,H1,Q1,Q2,Q3,Q4)`，供同 slice 的 form policy canonicalization 使用；Slice 3 的 `CnReportPeriodProjection` 与 selection sort 只复用该既有常量，禁止重新定义或在各模块重复硬编码排序 tuple。

新唯一入口为 `resolve_download_period_policy(raw_forms, market)`；删除 `resolve_target_periods`，不保留 wrapper/re-export。常量改为语义化名字，不再保留歧义 `DEFAULT_FORMS_*`：

| market / input | effective | discovery | missing eligible |
|---|---|---|---|
| CN bare | `FY,H1,Q1,Q3` | `FY,H1,Q1,Q3` | `FY,H1,Q1,Q3` |
| HK bare | `FY,H1` | `FY,H1,Q1,Q2,Q3,Q4` | `FY,H1` |
| CN explicit | canonical explicit tuple | 同左 | 同左 |
| HK explicit | canonical explicit tuple | 同左 | 同左 |

`CnDownloadPeriodPolicy` 不承载 `notes`、诊断或 cancellation；workflow 继续拥有运行期 notes。`__post_init__` 固定：三个 tuple 非空、canonical、无重复，且 `missing_eligible_periods ⊆ effective_periods ⊆ discovery_periods`。显式 forms 的 canonical parser、alias、排序与错误行为不改，不使用默认值补偿非法/空显式输入。

将 `CnReportQuery.target_periods` 直接重命名为 `discovery_periods`，同步 protocol、CNInfo、HKEX 与 tests；不保留 alias。data flow 固定为：

```text
raw forms + market
  -> resolve_download_period_policy
     -> effective_periods -> workflow filters.forms -> FinsDownloadEffectiveFilters.form_types
     -> discovery_periods -> period windows -> CnReportQuery.discovery_periods -> provider/selection
     -> missing_eligible_periods + selected identity_periods -> missing_periods
```

`run_cn_download_stream_impl(...)` 与 `rebuild_cn_download_artifacts(...)` 都按上述字段消费：

- 普通 download 的 provider query、窗口过滤与 business-year limit 使用 `discovery_periods`。
- `_resolve_missing_periods(...)` 只接收 `missing_eligible_periods` 与候选 `identity_period`，不接收 covered periods。
- result `filters.forms` 只写 `effective_periods`；public adapter 继续把它严格投影为 `FinsDownloadEffectiveFilters.form_types`。
- HK bare optional quarter 被发现后可以出现在 document rows，但不会进入 missing baseline；没有 optional material 时也不会显示 Q1～Q4 missing。
- local rebuild 不访问 provider，但其本地 source scan/window scope 使用 `discovery_periods`，从而不会遗漏已经存在的 HK optional material；其 `filters.forms` 仍为 effective baseline，且 rebuild 按既有 contract 不生成 missing。

### 5.3 DL-F13：全 results discovery 与 typed period projection

#### Provider category discovery

`dayu/fins/downloaders/hkexnews_downloader.py`：

- 保留 FY annual report category 与 H1 interim report category。
- 删除 `_HKEXNEWS_T2_QUARTERLY_RESULTS = "13600"` 及其映射。
- 新增一个命名的全 results category spec：`t1code=10000`、`t2_group_code=3`、`t2code=-2`；Q1～Q4 都映射到此 spec。
- 继续按 category spec 去重；bare HK 的四个 optional quarter 只能触发一次全 results group 查询。
- category query 仍拥有 cumulative `rowRange`、语言、日期、取消、HTTP/protocol failure；selection 仍拥有语言过滤、财年/期间分类、amended 优先与 material 去重。

#### Candidate period contract

在 `dayu/fins/pipelines/cn_download_models.py` 新增：

```text
CnReportPeriodProjection
  identity_period: CnFiscalPeriod
  covered_periods: tuple[CnFiscalPeriod, ...]
```

并把 `CnReportCandidate.fiscal_period` 替换为 `period_projection: CnReportPeriodProjection`，不保留 compatibility property。类型不变量：

- `covered_periods` 非空、按唯一 `CN_FISCAL_PERIOD_ORDER` canonical ordered、无重复；必须包含 `identity_period`。
- `identity_period` 表示 material/document identity、selection grouping、window、missing satisfaction、`form_type`、`fiscal_period`、`report_kind` 与 `build_cn_filing_ids(...)` 输入。
- `covered_periods` 表示该唯一 source 内容覆盖的业务期间，只用于 typed coverage projection；不得用于 mandatory missing satisfaction。
- CNInfo report candidate 使用 singleton projection `(period,)`。
- HK report material：annual report 为 `identity=FY, covered=(FY,)`；interim report 为 `identity=H1, covered=(H1,)`。
- HK intermediate result：`identity=Q2, covered=(H1,Q2)`；HK final result：`identity=Q4, covered=(FY,Q4)`。
- Q1/Q3 result 使用 singleton `Q1` / `Q3`；当前 period enum 不凭累计月份猜造不存在的 9M 等新业务期间。

#### Category-first 一般化分类矩阵

`cn_report_selection.py` 用 `_classify_hk_period_projection(title, category_text)` 替换单值 `_infer_fiscal_period_from_text(...)`。实现必须先只用 provider `category_text` 确定 material family，再在该 family 内解释 title/category duration token；禁止先把 title/category 拼成字符串后靠 tuple 遍历顺序选第一个命中。

Material family 判定固定为：

- `results`：category 明确包含 `業績` / `业绩` / `RESULTS`（包括 Quarterly/Interim/Final Results），且不含 report marker。
- `report`：category 明确包含 `年報` / `年报` / `REPORT` / `INTERIM/HALF-YEAR REPORT` 等 report marker，且不含 results marker。
- 两类 marker 同时出现、两类都不出现或 category 为空：ambiguous，返回 `None`。title 不能替代 category 决定 material family。

Family 内分类矩阵固定为：

| material family | category/title 的通用事实 | identity | covered | 必须排除的误判 |
|---|---|---|---|---|
| report | Annual/年度/年报 report | FY | `(FY,)` | 不得因 `FULL YEAR` 变成 Q4 |
| report | Interim/Half-Year/中期/半年 report | H1 | `(H1,)` | 不得因 `HALF YEAR` 变成 Q2 |
| report | quarter/results token、无唯一 FY/H1 或 FY/H1 同时命中 | `None` | — | report 永不产生 Q1～Q4 |
| results | Final Results，或 full-year/annual/twelve-month result | Q4 | `(FY,Q4)` | 不得变成 FY report；title 不含 fourth-quarter 字样仍可由 Final Results + full-year material contract分类 |
| results | Interim Results，或 six-month/half-year result | Q2 | `(H1,Q2)` | 标题即使同时含 three-month 也不得降为 Q1；不得变成 H1 report |
| results | Third Quarter / nine-month result，且未命中 Q4/Q2 | Q3 | `(Q3,)` | 不新增 9M period |
| results | First Quarter / three-month result，且未命中 Q4/Q3/Q2 | Q1 | `(Q1,)` | 单独 `three months` 只有在无更长 duration/category事实时成立 |
| results | period facts 冲突、只有泛化 `RESULTS` 而无唯一 duration/quarter | `None` | — | 不靠枚举顺序、日期或 filing month 猜测 |

正负例 owner tests 至少覆盖：`中期業績` + six/half-year -> Q2/H1 coverage；`中期報告` + 相同 half-year token -> H1 singleton；`末期業績` + annual/full-year -> Q4/FY coverage；`年度報告` + 相同 full-year token -> FY singleton；Q2 标题同时含 three/six months 仍为 Q2；category 缺失、report category + quarter title、互相冲突的 duration 返回 `None`。英文、繁中与简中 token 使用参数化 fixture，禁止冻结完整标题成为唯一匹配条件。

raw announcement 先按 provider `document_id` 去重，同一 ID 若 source URL、category、title、filing date 或语言等核心 source 事实冲突则 fail closed；随后按 `(identity_period, fiscal_year)` 分组选择 amended/best material。最终排序只用 `period_projection.identity_period`。

#### Identity、durable state 与 public projection

```text
HkexnewsRawAnnouncement
  -> CnReportPeriodProjection
  -> one CnReportCandidate
  -> build_cn_filing_ids(identity_period) exactly once
  -> one source document / one filing manifest item
  -> source meta {fiscal_period=identity_period,
                  covered_fiscal_periods=[...]}
  -> one workflow filing result
  -> one FinsDownloadDocumentResult
  -> one FinsDownloadPublicDocument
```

- `build_cn_filing_ids(...)` 的函数签名和 seed 不变；所有 download call site 明确传 `candidate.period_projection.identity_period`。不得遍历 `covered_periods` 生成 ID。
- `commit_cn_filing_source_document(...)` 与 `_build_base_meta(...)` 只删除**对各自 caller 暴露**的冗余 `form_type` 参数；`commit_cn_filing_source_document(...)` 内部唯一取局部值 `identity_period = candidate.period_projection.identity_period`，将 candidate 交给 `_build_base_meta(...)` 派生 meta 的 `form_type`/`fiscal_period`/`report_kind`，并继续显式调用 `_build_upsert_request(..., form_type=identity_period)`。`_build_upsert_request(...)` 的内部参数不删除，因为它机械构造 storage request；该值来自 candidate identity，不是 caller 可提供的第二真源。`covered_fiscal_periods` 只由 `candidate.period_projection.covered_periods` 转成 JSON list。
- source meta 新增必填 `covered_fiscal_periods` JSON array。`fiscal_period` 保持 identity period；storage 的现有 `FilingManifestItem.from_source_meta(...)` 继续把 identity period 投影到唯一 manifest item，因此不扩大通用 storage manifest schema、不创建第二 manifest entry。coverage 真值保存在同一 source meta。
- 所有 downloaded/skipped/failed workflow filing result 都从 candidate 写出必填 JSON array `covered_fiscal_periods`；rebuild 从 fresh-schema source meta 用严格 required-field parser 读取并原样投影。缺字段、非 list、非 canonical period、重复、乱序或不含 identity 一律 fail closed，不用 `.get(..., default)`、空 tuple 默认或旧 schema fallback。
- `FinsDownloadDocumentResult` 与 `FinsDownloadPublicDocument` 都新增**无默认值**的必填 `covered_fiscal_periods: tuple[str, ...]`。当前基线已存在 `dayu/fins/domain/filing_semantics.py::FISCAL_PERIODS`（定义于该模块现有第 79 行附近），公共类型直接复用它做成员校验，并校验 tuple 与无重复；无需创建新模块、常量或替代真源。`FISCAL_PERIODS` 只拥有通用 membership，`CN_FISCAL_PERIOD_ORDER` 只拥有 CN/HK download canonical order，两者不重叠。canonical order 与 identity-in-coverage 仍由 `CnReportPeriodProjection` 唯一拥有，CN/HK adapter 只机械投影该值。SEC 的 4 个 `sec_pipeline.py` 构造点与 `ingestion_runtime.py` 的 2 个 non-persisted generic adapter 构造点都显式传 `()`；不允许靠 dataclass 默认掩盖漏迁移。
- public JSON 全链固定为：CN/HK workflow row required array -> `cn_pipeline.py` strict parse -> `FinsDownloadDocumentResult` -> `ingestion_runtime.py::_public_download_summary` 原样复制 -> `FinsDownloadPublicDocument` -> `direct_events.py::FinsDownloadPublicDocument.to_json_value()` 显式写入 `"covered_fiscal_periods": list(self.covered_fiscal_periods)` -> `FinsDownloadPublicSummary.to_json_value()` 的 `documents[]` -> Service wait adapter 原样序列化。任何层不得从 `form_or_period`、标题或 meta 字符串重算 coverage。
- CLI typed row 不解析 JSON；`dayu/cli/output.py::_download_document_line` 直接从 `FinsDownloadPublicDocument` 显示现有 `form_or_period=<identity>`，并新增精确、业务可读的 `covered_fiscal_periods=[...]`。不新增 `optional`、policy id 或其它模糊内部 label。HK bare summary 的 forms 仍表示 applicable baseline FY/H1；实际 optional Q2/Q4 只通过 document row 的 identity/coverage 可见。
- `missing_periods` 只用 selected candidate 的 `identity_period`。所以 Q2 result 的 `covered=(H1,Q2)` 不满足 H1 report baseline，Q4 result 的 `covered=(FY,Q4)` 不满足 FY annual report baseline。

四材料 owner contract 固定为：

| material | identity period | covered periods | provider source / document identity |
|---|---|---|---|
| Q2 intermediate result | Q2 | H1,Q2 | 独立且唯一 |
| H1 interim report | H1 | H1 | 独立且唯一 |
| merged annual/Q4 final result | Q4 | FY,Q4 | 独立且唯一 |
| FY annual report | FY | FY | 独立且唯一 |

## 6. Implementation slices

实现严格分三片推进；每片只能修改列出的文件。allowed files 已由 §4.3 基线 `rg` 穷举校准。implementation 开始时必须重跑同一组 `rg` 防止基线漂移；若出现新 production call site，立即停止并交 gate owner 更新计划，禁止越界顺手修改或用 compatibility property/default 绕过。

### Slice 1 — F12 invocation invariant 与 help

**目标 / 可观察结果**

建立唯一 typed mutation-mode invariant；两种冲突 argv 顺序在任何 workspace/runtime/provider 副作用前 exit 2；help 自解释；三个合法组合不变。

**Allowed production files**

- `dayu/fins/download_contract.py`
- `dayu/cli/arg_parsing.py`

**Allowed test files**

- `tests/service/test_fins_direct.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_fins_commands.py`

**Exact changes / owner tests**

1. 新增 §5.1 唯一私有 mode helper；`FinsDownloadRequest.__post_init__` 与 `FinsDownloadEffectiveFilters.__post_init__` 复用它。补齐完整中文 docstring 与 TypeError/`FinsDownloadUsageError` 异常说明，不在 caller 复制判断。
2. 更新 download 两个 flag 的 help，不注册第二套冲突 validator。
3. 将 `test_download_command_maps_args_to_service` 改为单独 overwrite 与单独 rebuild 的参数映射测试，不再构造非法成功组合。
4. 将 `tests/service/test_fins_direct.py` 现有 Service pass-through fixture 中的双 true request 改成一个合法单 mode request；该测试只验证 Service 透传，不再固化非法 contract。
5. 新增 request 与 effective-filter owner matrix：两种类型的 `00/10/01` 均成功，`11` 均由同一 helper 抛精确 `FinsDownloadUsageError`；静态 guard 证明模块内只有 helper 含双 true 判断。
6. 新增两种 argv 顺序 CLI 测试：exit 2、actionable stderr、service factory 0 次、operation 0 次、workspace 路径不存在；同时保留一个合法 mode sentinel 证明不是无条件拒绝。
7. help owner test 断言两个 option 及明确互斥说明，不只断言 flag 名存在。

**Non-goals / stop condition**

- 不修改 `commands/fins.py`、Service、runtime 或 source workflow；不靠默认值、parser mutually-exclusive group 或下游 precedence 兼容。
- 若错误发生在 factory/workspace 之后、合法单 flag 回归、或 production 出现第二个冲突判断，立即停止，不进入 Slice 2。

### Slice 2 — F14 market form policy 与三路 data flow

**依赖**：Slice 1 owner tests 通过。

**目标 / 可观察结果**

以一个 market-specific typed policy 分离 effective、discovery、missing eligibility；CN/HK bare default 正确，显式 CN Q2/Q4 不变。

**Allowed production files**

- `dayu/fins/pipelines/cn_form_utils.py`
- `dayu/fins/pipelines/cn_download_models.py`
- `dayu/fins/pipelines/cn_download_protocols.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/cn_download_rebuild.py`
- `dayu/fins/pipelines/cn_report_selection.py`
- `dayu/fins/downloaders/cninfo_downloader.py`
- `dayu/fins/downloaders/hkexnews_downloader.py`

**Allowed test files**

- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_report_selection.py`
- `tests/fins/test_cninfo_downloader.py`
- `tests/fins/test_hkexnews_downloader.py`
- `tests/fins/test_cn_download_runtime.py`

**Exact changes / owner tests**

1. 在 `cn_download_models.py` 先定义唯一 `CN_FISCAL_PERIOD_ORDER`；新增 `CnDownloadPeriodPolicy`、语义化默认常量与 `resolve_download_period_policy(...)` 并复用该顺序；删除旧 type/function/constants。
2. `CnReportQuery.target_periods -> discovery_periods` 全量机械迁移 production/tests；其中 `cn_report_selection.py` 当前两处 `query.target_periods` 访问必须在本 slice 只机械改名为 `query.discovery_periods`，protocol/docstring 只使用 discovery 语义，不提前修改 classifier 或 candidate projection。
3. workflow/rebuild 严格按 §5.2 三路消费，不从 `filters.forms` 或 selected rows 反推其它集合。
4. policy owner matrix 精确断言四行表格、canonical order、subset invariant、非法/重复/alias 行为。
5. fake downloader spy 断言 HK bare query 收到六个 discovery periods，但 summary effective forms 仅 FY/H1；只返回 optional quarter 时 missing 仍为 FY/H1；返回 FY/H1 时 optional quarters不 missing。
6. CN bare 断言 query/effective/missing eligible 均为 FY/H1/Q1/Q3，summary 不出现 Q2/Q4 missing。
7. 显式 CN `Q2,Q4` owner test 继续断言 query/effective/missing eligible 都是 Q2,Q4，CNInfo 无独立分类时 missing 仍为 Q2,Q4；不得通过改 fixture 删除该行为。
8. rebuild owner test 断言 HK bare 会重建本地 optional quarter document，但 effective forms 仍为 FY/H1；无 provider HTTP。
9. CN bare 与 HK bare rebuild 都显式断言 workflow `missing_periods == []`、typed/public 投影 `missing_periods == ()`，provider/HTTP 为 0，不覆盖 source，也不触发 process/processed/reprocess；rebuild 只按 `discovery_periods` 选择 fresh-schema 本地 source。

**Non-goals / stop condition**

- 本 slice 不改变 HKEX category code或 candidate period schema。
- 若任一 consumer仍读取歧义 `target_periods`、HK optional discovery 被当 mandatory、或 CN explicit Q2/Q4 行为变化，立即停止，不进入 Slice 3。

### Slice 3 — F13 HKEX discovery、multi-period identity 与同源 projection

**依赖**：Slice 2 typed policy/query contract 稳定。

**目标 / 可观察结果**

全 results raw discovery 无发行人特例；四种 material 独立；一个 source 一个 identity；coverage 在 meta与public summary 可见；missing 只由 identity 满足。

**与 Slice 2 的共有文件边界**

| 共有文件 | Slice 2 只允许 | Slice 3 只允许 |
|---|---|---|
| `cn_download_models.py` | 定义唯一 `CN_FISCAL_PERIOD_ORDER`；完成 `CnReportQuery.target_periods -> discovery_periods` 与 query docstring | 新增 `CnReportPeriodProjection` 并复用既有 order 做 canonical validation；替换 candidate 字段与不变量 |
| `hkexnews_downloader.py` | 机械消费 `query.discovery_periods` | category spec 改为全 results group；不改 policy |
| `cn_download_workflow.py` | 三集合 policy/query/window/effective/missing data flow | 所有 candidate identity 访问、workflow filing coverage 与 ID call site |
| `cn_download_rebuild.py` | discovery windows、effective forms 与 empty missing contract | fresh-schema coverage required parse/projection |
| `cn_report_selection.py` | 仅将两处 `query.target_periods` 机械重命名为 `query.discovery_periods`；不改分类/候选语义 | 重写 category-first classification，构造/消费 `CnReportPeriodProjection`，selection sort 复用既有 `CN_FISCAL_PERIOD_ORDER` |

`cn_report_selection.py` 是 Slice 2/3 共有文件：Slice 2 只做 query field rename，使该 slice 独立通过 pyright；Slice 3 才做 classification/projection。`cn_download_filing_workflow.py`、`cn_download_source_upsert.py` 在 `rg` 中是 candidate identity/source-meta 的真实消费者，只属于 Slice 3；不得在 Slice 2 提前迁移。`cn_download_protocols.py` 与 `cninfo_downloader.py` 只属于 Slice 2 的 query rename，Slice 3 不再修改。

**Allowed production files**

- `dayu/fins/downloaders/hkexnews_downloader.py`
- `dayu/fins/pipelines/cn_download_models.py`
- `dayu/fins/pipelines/cn_report_selection.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`
- `dayu/fins/pipelines/cn_download_rebuild.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/download_contract.py`
- `dayu/fins/direct_events.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/cli/output.py`

**Allowed test files**

- `tests/fins/test_hkexnews_downloader.py`
- `tests/fins/test_cn_report_selection.py`
- `tests/fins/test_cninfo_downloader.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/cli/test_output.py`
- `tests/service/test_fins_wait_adapter.py`

**Allowed documentation files（仅在 Slice 3 行为与 tests 稳定后）**

- `README.md`
- `dayu/fins/README.md`
- `tests/README.md`

**Exact changes / owner tests**

1. category mapping test 精确断言 FY annual、H1 interim、Q1～Q4 共用一次全 results `t1code=10000,t2Gcode=3,t2code=-2` 查询；四个 quarter 只发一次 category request，production 不再引用 `13600`。HTTP fixture 必须保留 raw `category_text` 与 source URL，不把 selection 结果冒充 raw evidence。
2. 用通用 raw fixture（不含 0700/ticker分支）同时放入 Q2 result、H1 report、Q4 final result、FY report；selection owner test 断言四 candidates、四 source IDs、四不同 generated document IDs和 §5.3 period projections。
3. 完整实现并参数化测试 §5.3 category-first 矩阵及正负例；共享 `HALF YEAR`/`半年`、`FULL YEAR`/`全年` token 的结果只能由 material family 消歧，不得靠遍历优先级。不把冻结完整标题复制成唯一匹配条件。
4. candidate contract owner test 拒绝空 coverage、重复、非 canonical order、identity 不在 coverage。
5. workflow source upsert test 断言合并 Q4/FY result：只下载/转换/commit 一次；source meta 为 `fiscal_period=Q4`、`covered_fiscal_periods=[FY,Q4]`、正确 source provider/id/url；filing manifest 只有一个对应 document entry且 identity period 为 Q4。
6. 同批放入 FY annual report，断言其 document ID 与 Q4 result 不同；Q2 result 与 H1 report同理。禁止以 covered period 数量增加 document count。
7. missing owner test：只有 Q4 result 时 FY 仍 missing，只有 Q2 result 时 H1 仍 missing；存在各自 FY/H1 report 后 baseline 才满足。
8. ordinary、skip、failed、rebuild 四类 workflow result 都携带严格 typed coverage；fresh-schema meta 缺失/畸形 coverage fail closed，不加默认。CN/HK bare rebuild 继续显式断言空 missing 与 local-only/no-process 边界。
9. CNInfo singleton projection回归；CN 下载的 selection、ID、meta、summary、missing 保持原行为。
10. `cn_pipeline.py` 的 3 个构造点从 workflow required array 严格投影；`sec_pipeline.py` 的 4 个构造点和 `ingestion_runtime.py` 的 2 个 non-persisted 构造点显式传空 tuple。禁止给公共字段默认值。
11. CN adapter -> `FinsDownloadDocumentResult` -> runtime -> `FinsDownloadPublicDocument` -> 显式 `to_json_value()` -> `documents[]` -> wait adapter/CLI row 全链断言 identity + coverage 同源；SEC owner test 断言 public JSON 明确包含 `"covered_fiscal_periods": []` 且既有 identity/output 语义不变。
12. 按 §8 三份 README 的既有写作约束更新当前实现事实；不得写 plan/review 历史、future capability 或内部 evidence ID。

**Non-goals / stop condition**

- 不修改 storage protocol/implementation或通用 `FilingManifestItem` schema；一个 manifest item 继续代表一个 source identity。
- 若同一 `source_id` 产生多于一个 document、covered periods 能满足 report baseline missing、raw row 只靠 0700/日期/URL/完整标题识别、公共字段依赖默认值、SEC 未显式空 coverage、或 public projection从字符串重算 coverage，立即停止并修正 owner，不进入验证/审查。

## 7. 测试、coverage 与 static validation

所有命令都在实现完成后从仓库根执行，先 `source .venv/bin/activate`。plan gate 本身不运行这些实现验证。

### 7.1 Focused owner test union

```bash
pytest \
  tests/service/test_fins_direct.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_fins_commands.py \
  tests/cli/test_output.py \
  tests/service/test_fins_wait_adapter.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_report_selection.py \
  tests/fins/test_cninfo_downloader.py \
  tests/fins/test_hkexnews_downloader.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_cn_download_runtime.py \
  tests/fins/test_fins_ingestion_runtime.py
```

这组命令已经覆盖 §4.3 `rg` 找到的全部直接构造/消费 tests；不得在 implementation 时用更小的自选子集替换。pyright 负责发现不直接执行的 typed call site。真实 provider 不进入 unit test；HTTP fixtures只验证 request/category/selection owner，不冒充 production evidence。

### 7.2 单文件 coverage

对 `git diff --name-only -- '*.py'` 得到的**每一个实际修改 production Python 文件**用同一 focused union 采集整文件 line coverage，输出逐文件表；每个文件各自 `>=80%`，不得用 aggregate、changed-lines/incremental 口径、omit、pragma、降阈值或默认排除掩盖。`ingestion_runtime.py` 若为完成唯一 public projection 所必需并进入 diff，也适用相同整文件门槛；若实现证明无需修改，则必须从 diff 删除而不是申请豁免。测试文件本身不纳入 production 单文件阈值。

建议命令形态：

```bash
coverage erase
coverage run -m pytest <focused-owner-test-union>
coverage report -m <all-changed-production-files>
```

阈值口径是 `coverage report` 的逐文件 statement/line 百分比，不是只看 `TOTAL`。implementation artifact 必须粘贴所有 changed production files 的 file-level 行；任何一项低于 80% 都是 validation failure。若另跑 branch coverage，只作为补充，不得替代或放宽上述 line coverage。

### 7.3 Static / type validation

```bash
ruff check <all-changed-python-files>
ruff format --check <all-changed-python-files>
python -m compileall <all-changed-production-modules>
pyright
git diff --check
```

并执行以下精确 guards：

- `rg` 证明 production/tests 不再存在 `TargetPeriodResolution`、`resolve_target_periods`、`CnReportQuery.target_periods` 或 `CnReportCandidate` compatibility `.fiscal_period`；同名其它业务模型字段不做误删。
- `rg` 证明 HKEX production 不再存在 `13600`/`_HKEXNEWS_T2_QUARTERLY_RESULTS`。
- `rg`/AST 证明 runtime、adapter、workflow 不判断 overwrite/rebuild 冲突，且 CLI parser 没有第二个互斥 validator。
- `rg` 证明没有 `0700`、腾讯、`11793094`、`12056833` 或冻结完整标题进入 production；这些值只允许出现在测试说明/真实 evidence。
- `rg` 证明 download identity 只从 `period_projection.identity_period` 调用既有 `build_cn_filing_ids(...)`，不遍历 `covered_periods`。
- 构造 CN/HK/SEC public summary 并调用真实 `to_json_value()`，对返回对象做 `json.dumps(..., ensure_ascii=False)` + `json.loads(...)` strict round-trip；逐行断言 `documents[].covered_fiscal_periods` 始终存在且为 JSON array。无需修改独立 JSON schema/registry 文件，但显式 serializer 变化不能以“无 schema 文件”为由跳过 JSON validation。

## 8. README 决策

本 plan gate 不修改 README。implementation 完成后按 README 内部约束作以下职责判断：

- 根 `README.md`：**需要更新**。download 是最终用户公开 CLI；需说明 `--overwrite` / `--rebuild` 互斥、CN bare default `FY,H1,Q1,Q3`、HK bare effective baseline FY/H1且仍发现实际 optional quarter、missing 只针对 applicable baseline。
- `dayu/fins/README.md`：**需要更新**。Fins 开发者需要知道 market form policy 三集合、HKEX 全 results discovery、category-first matrix、identity/covered periods 与 missing 不变量、source meta/public JSON 字段，以及唯一 mode helper 的 contract 边界。
- `tests/README.md`：**需要更新**。它的职责包括当前测试分层、运行方式与 owner coverage；本 WU 会实质扩展 download owner matrix（mode invariant、market policy、HKEX material classification、SEC/public JSON coverage、rebuild empty missing）并固定整文件 line coverage 口径，属于其现有职责。只写实现后真实存在的测试事实，不写 work unit 过程。
- `dayu/README.md`：**不更新**。`UI -> Service -> Host -> Engine` 与 `dayu.runtime` 边界不变。
- `dayu/host/README.md`、`dayu/engine/README.md` 与两份 design doc：**不更新**。没有 Host/Engine contract 或装配变化。

README 只能在实现行为和 tests 已稳定后更新当前事实，不预写计划、历史迁移或未实现能力。

## 9. Production CLI post-fix evidence 步骤

这些步骤只在 implementation、slice reviews、aggregate deepreview全部通过并形成待测 commit 后执行；本 plan gate禁止执行。

### 9.1 Evidence run 共同前置

1. 按 `docs/cli_ci.md` 创建新 run id、CI-owned run root、detached clean validation worktree与独立 `.venv`；被测对象绑定不可变 commit SHA，不从当前主工作树 editable install运行。
2. 记录 repo/commit/runtime identity、实际 CLI path、workspace path、provider identity、非秘密配置、起止时间与资源预算。
3. 每个 scenario 使用 fresh workspace；保存 argv、exit、stdout/stderr、cast/log、before/after tree、source meta、filing manifest、PDF/Docling JSON digest与 public summary。真实 provider/network gap 如实登记，不用 fake 补成 PASS。
4. 生成新的 immutable `observed-behavior.md` 与 exact UTF-8 SHA-256；旧报告原样保留。该报告只记录 observation 与 Agent suggested disposition，不更新 Oracle/registry/readiness。

### 9.2 F12 real contract

- 执行两个顺序：`download ... --overwrite --rebuild`、`download ... --rebuild --overwrite`。
- 断言 exit 2、互斥诊断、无 workspace 业务树、无 network/service/operation evidence。
- 分别执行一个合法 `--overwrite` 与一个合法 `--rebuild` sentinel；overwrite 真实远端边界与 rebuild local-only/no-network 继续按前序 accepted oracle 对账。
- 保存 `download --help`，确认互斥说明与 parser inventory一致。

### 9.3 CN bare-default 与 explicit sentinel

- fresh 运行既有已接受 A股主体/窗口（前序证据为 `600519`），不传 `--forms`。
- 对账 effective forms 精确为 FY/H1/Q1/Q3，missing 不含 Q2/Q4；前序已接受的 9 份实际选择结果、约五年窗口、PDF、Docling JSON、meta/manifest与 production `process` 可消费性不得回归。
- 另运行低成本显式 CN `--forms Q2 Q4` sentinel；只裁定其仍是显式请求与相应 missing 行为，不将其提升为 CN bare default，也不要求 provider产生不存在的独立分类。

### 9.4 HK Main Board baseline issuer

- 在 run inventory 中先用 HKEX 官方全 results group 选择并冻结一个窗口内没有 optional quarter material 的 Main Board issuer；记录 ticker、stock id、窗口与原始 category evidence，不能仅凭预期指定。
- fresh bare-default 下载；断言 effective/missing baseline仅 FY/H1，screen不报告 Q1～Q4 missing；年度/中期 source URL、PDF、Docling、meta/manifest与 `process` 可消费。
- 若实际 source 新增 optional material，不能继续把它当“无 optional”样本；重新选择满足前置事实的发行人或登记 evidence gap。

### 9.5 0700 optional discovery 与四材料对账

- fresh `0700` bare-default，覆盖至少 `2025-01-01..2026-04-30`。
- 保存 HKEX annual report、interim report与全 results group原始 request/rows/category/source URL；精确对账 §4.2 冻结的 `t1code=10000,t2Gcode=3,t2code=-2` 与 `11793094`/`12056833`，但这些 ID/URL 不进入 production classifier。
- 对账 Q2 result、H1 interim report、merged FY/Q4 result、FY annual report四个 source URL、四个唯一 document IDs、各一份 PDF/Docling JSON、source meta、filing manifest entry与public document row。
- 断言 Q2 result为 `identity=Q2, covered=H1,Q2`，H1 report为 singleton H1；merged result为 `identity=Q4, covered=FY,Q4`，annual report为 singleton FY；没有 source duplication。
- 对 `12056833` 英文 PDF 的 production Docling 只读结果保存内容证据，确认 `Fourth Quarter of 2025` 与截至 12 月 31 日的三个月数据；明确 raw title 只证明 annual/final result，不单独证明 Q4 coverage。Q2 同理保存三个月与六个月正文证据。
- 对账 missing 只针对 FY/H1 baseline，且由对应 reports满足；Q2/Q4 optional material 的存在与否不改变 mandatory missing资格。
- 对四份 material 至少各执行一次 production read/process consumability检查；CLI summary、自报成功或文件存在不能替代实际解析/消费。

### 9.6 Evidence closeout

- 运行 mock/fake absence、secret scan、artifact presence/digest、cross-layer identity与source URL correlation检查。
- 每个场景分别记录 `evidence_status`、`gap_kind`、owner与next action；整体 verdict 按 `docs/cli_ci.md` 优先级聚合。
- 报告冻结后暂停，向用户提交 observation digest与 suggested adjudication。用户未裁决前不得将 DL-F12～F14写成 accepted oracle、不得生成 download readiness PASS。

## 10. 风险、反例与 residual owner

| 风险 / 反例 | 防线 | residual owner |
|---|---|---|
| parser/request/filter 复制校验导致错误文本/时序分叉 | `download_contract.py` 唯一私有 helper；request/filter 复用，parser只投影help | Fins download contract |
| HK全 results group数据量增大或分页增长 | 复用现有 cumulative rowRange、取消、重试、protocol validator；category spec只查询一次 | HKEX downloader |
| `中期業績` 被当 H1 report，`末期業績` 被当 FY report | category-first 封闭矩阵；共享 token 不靠遍历顺序 | report selection |
| Q2 coverage含 H1后错误关闭 H1 missing | missing只看 identity，不看 covered | CN/HK workflow |
| 一份 source按 covered periods复制 identity | ID helper只调用一次且只吃 identity period；manifest count invariant | filing workflow / storage publication |
| 同 provider ID的raw重复行事实冲突 | provider ID去重时比较核心字段并 fail closed | report selection |
| HK optional rows出现在document summary但不在effective forms | policy明确 effective是baseline、discovery可为超集；public row携带实际 material事实 | form policy / public summary |
| 新 meta字段与旧 workspace不兼容 | schema任务按 fresh schema起库；不做旧库fallback。真实证据使用fresh workspace | source meta schema owner |
| public row新增coverage造成下游漏迁移 | §4.3 穷举全部 result/public 构造、显式 serializer、CLI/wait consumer；字段无默认，SEC显式空 | download public contract |
| 全 results一般化规则误收非财报公告 | selection仍要求结果category、期间token、财年、语言与现有block/best规则；加入negative fixtures | report selection |
| 真实provider在evidence时变化/不可用 | 保存raw证据并标gap，不用unit/fake冒充production PASS | CLI CI evidence owner |

Blocking open question：无。若实现时发现 `covered_fiscal_periods` 必须进入通用 storage manifest schema才能满足现有 validator之外的新消费者，属于 scope expansion，必须停止并由用户重新确认；本计划明确选择“manifest唯一 identity + source meta完整coverage”的最小正确边界。

## 11. 为什么不是过度设计

- 只新增两个必要的值类型：一个仅含三集合的 market policy、一个 identity/coverage period projection；它们分别消除当前两个被直接数据证明的语义过载。policy 不携带无消费者的 notes。
- 不新增 provider abstraction、policy registry、issuer配置、状态机、数据库表、migration layer或 Host/Engine seam。
- HKEX 复用现有 category query、pagination、selection与HTTP error边界，只把季度查询从错误子类扩为已有 results group全类。
- document ID算法、storage repository、manifest schema和下载 transaction均保持不变；用一个 candidate/source/meta 表达多期间，不复制文档。
- public contract只增加完成当前用户核对所需的 coverage字段；CLI/wait adapter机械投影，不引入下游推断。
- 三个 slice 分别对应 invocation、market policy、provider/material projection三个独立 owner；继续合并会掩盖边界，继续拆分则只增加交接成本而没有新的可独立业务结果。

## 12. Gate completion / handoff

本 plan re-review fix loop 2 的交付物是本文件与 `docs/gateflow/wu-cli-download-02-plan-fix-2-20260810.md`；上一轮 fix artifact 原样保留。当前 gate 完成后必须停止，等待总控发起第二轮 MiMo/DS 独立 re-review；不得自行进入 accepted plan commit 或 implementation。后续只有在第二轮 re-review 与总控裁决通过后，implementation 才能逐 slice 遵守 allowed files、tests、stop conditions 与验证命令。本轮不修改产品代码、测试或 README，不运行 CLI，不 commit、不 push、不创建 PR。
