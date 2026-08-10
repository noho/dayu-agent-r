# WU-CLI-DOWNLOAD-02-DL-F12-F14 goal confirmation

## Gate 与状态

- Gate：`goal confirmation`
- Work unit：`WU-CLI-DOWNLOAD-02-DL-F12-F14`
- 起始产品 HEAD：`3811f95c82fbf0daf15740a5d217eed4d8b49df5`
- 分支：`codex/download-oracle`
- 结论：`confirmed / next=plan`
- 用户确认：本 work unit 的目标语义已由 2026-08-10 用户消息冻结；本次调查未发现会改变冻结业务语义的 blocking contract contradiction。

## 目标成立性与动机

三个 finding 均由当前产品代码和真实 provider 数据直接复现，动机成立且严重性评估合理：

- DL-F12：download parser 当前把 `--overwrite`、`--rebuild` 注册成两个可同时为真的独立 flag；CLI 预校验随后把二者原样写入同一个 `FinsDownloadRequest`，因此组合可以进入业务 operation。互斥是公开调用契约，必须在 workspace/runtime/provider 之前拒绝。
- DL-F13：相同 0700、`2025-01-01..2026-04-30` 查询中，当前 `HkexnewsDiscoveryClient.list_report_candidates(...)` 只返回 FY、H1、Q1、Q3；直接查询 HKEX `公告及通告 -> 業績` 全组后，现有通用分类器能够额外识别 2025-08-13 Q2 和 2026-03-18 Q4。故漏选不是腾讯官网与 CLI summary 的间接差异，而是 HKEX discovery 只查询 `季度業績` 子类、遗漏 `中期業績` 与 `末期業績` 子类造成的原始候选缺失。
- DL-F14：`resolve_target_periods(...)` 当前用同一个 `target_periods` 同时表达 bare-default effective forms、provider discovery 范围和 missing eligibility，且 CN/HK 默认都写死为 `FY,H1,Q1,Q2,Q3,Q4`。这个单值契约无法表达“A股适用默认 FY/H1/Q1/Q3”或“港股 FY/H1 mandatory baseline + 实际 optional quarter discovery”。

## 直接代码与数据证据

### DL-F12

- `dayu/cli/arg_parsing.py::_register_download_command` 分别调用 `add_argument("--overwrite", ...)` 与 `add_argument("--rebuild", ...)`，没有互斥声明。
- `dayu/cli/commands/fins.py::_prevalidate_download_request` 在 workspace resolution 前调用 `build_direct_download_request(...)`，但把两个 bool 同时透传。
- `dayu/fins/download_contract.py::build_fins_download_request` 允许同时构造 `overwrite_existing=True`、`rebuild_local_artifacts=True`。
- `tests/cli/test_fins_commands.py::test_download_command_maps_args_to_service` 目前反而固化了组合成功；该测试应迁移到 owner contract，而不能驱动生产代码保留旧行为。

### DL-F13

真实读取 HKEX production endpoint 的结果：

- 当前 discovery 候选：2025 FY 年报（2026-04-09）、2025 H1 中期报告（2025-08-26）、2025 Q1、2025 Q3、2024 FY；没有 2025 Q2/Q4。
- HKEX `公告及通告 -> 業績` 原始全组存在：
  - `11793094`，2025-08-13，`截至二零二五年六月三十日止三個月及六個月業績公佈`，provider category 为 `中期業績`；现有 classifier 一般化识别为 2025 Q2。
  - `12056833`，2026-03-18，`截至二零二五年十二月三十一日止年度全年業績公佈`，provider category 为 `末期業績`；现有 classifier 一般化识别为 2025 Q4。
- `dayu/fins/downloaders/hkexnews_downloader.py::_PERIOD_TO_CATEGORY_SPEC` 当前 FY/H1 只查 annual/interim report，Q1-Q4 全部只查 `t2code=13600` quarterly results；这正好排除了上述中期/末期业绩 raw rows。
- `dayu/fins/pipelines/cn_report_selection.py::_infer_fiscal_period_from_text` 已能基于一般化的三/六个月、全年等文本识别 Q2/Q4；不需要 ticker、日期、URL 或腾讯标题特例。
- `CnReportCandidate`、source meta 与 `build_cn_filing_ids(...)` 当前只有一个 `fiscal_period`。年度/Q4合并披露若只保留单值，会丢失它同时覆盖 FY 与 Q4 的真实语义；若复制文档，又会制造无依据的重复 source identity。因此 typed candidate/meta 必须显式承载同一文档覆盖的期间集合，同时保留唯一文档 identity。

### DL-F14

- `dayu/fins/pipelines/cn_form_utils.py` 当前定义 `DEFAULT_FORMS_CN == DEFAULT_FORMS_HK == (FY,H1,Q1,Q2,Q3,Q4)`。
- `resolve_target_periods(...)` 只返回 `TargetPeriodResolution.target_periods`；`run_cn_download_stream_impl(...)` 同时用它构造 query、period windows、effective `filters.forms` 和 `_resolve_missing_periods(...)`。
- CNInfo downloader 对 Q2/Q4 明确记为“不支持独立分类并按无候选跳过”，所以当前 A股 bare-default 会机械产生错误 Q2/Q4 missing。
- HKEX downloader 又只按同一个 target set决定查询分类，所以把 missing mandatory policy 与 optional discovery 绑定在一起。

## Semantic owner 与修复边界

- CLI option 组合的用户输入 owner：download CLI parser / pre-workspace typed request construction boundary。错误必须在该边界收口，不能让 runtime、adapter 或 rebuild workflow再决定优先级。
- 市场默认、optional discovery 与 missing eligibility owner：`dayu.fins.pipelines.cn_form_utils` 的 market-specific typed form policy。workflow 只能分别消费 owner 产生的 effective forms、discovery periods 与 missing-eligible periods。
- HKEX 原始候选范围 owner：`HkexnewsDiscoveryClient` 的 provider category query；它应查询通用的业绩分类集合，再交给既有 selection owner做语言、期间、财年和去重，不在 downloader 写发行人特例。
- 公告期间/文档投影 owner：CN/HK typed candidate 与 source upsert。一个 provider source 只产生一个 document identity；同一披露覆盖多个业务期间时由 typed period projection写入同一 meta/manifest truth，不复制 source，也不让 CLI重算。
- missing owner：CN/HK workflow；它只基于 form policy 的 missing eligibility 与已选择候选的 owner-level period projection计算，CLI/output 只机械投影 typed summary。
- storage 仍只经 `dayu.fins.storage` repository protocol写入；Host/Engine 不参与，也不修改 `docs/host/design.md`、`docs/engine/design.md`。

## 成功信号

- F12 两种 argv 顺序均 exit 2，并在 Service factory、operation、网络和 workspace 业务写入前停止；help 清楚说明互斥；单独 overwrite/rebuild 既有语义不变。
- CN bare-default effective forms 精确为 `FY,H1,Q1,Q3`，missing 不含 Q2/Q4；显式 CN `--forms Q2/Q4` 本轮保持现有公开行为，不引入新裁决。
- HK Main Board bare-default effective baseline 为 FY/H1，missing 只针对 baseline；discovery 仍主动发现发行人实际 optional quarter results。
- 通用 HKEX raw category/selection owner test证明 Q2、H1、合并年度/Q4结果、FY 年报是四个不同 material/identity，不使用 ticker/title/date/URL特例；合并披露的多期间覆盖写入同一 typed identity。
- summary、manifest/meta、source URL、document identity 与 missing periods从上述 typed owner同源。
- affected tests、修改生产文件覆盖率、完整 pyright、changed-files Ruff/format、compileall、JSON parse、`git diff --check`通过；触发的 README按各自写作边界更新。
- 最终产品 HEAD 上完成用户要求的四类 production CLI observation，只生成 observed-behavior 与 Agent裁决建议，不更新 formal Oracle/scenario/readiness。

## Non-goals 与防过度设计

- 不修改其它 CLI 命令、Host/Engine、process契约、accepted Oracle、formal registries、readiness、PR或 issue。
- 不引入通用状态机、后台 job、事务框架、兼容 shim、loose parsing、下游隐藏、harness framework或报告生成器。
- 不把 optional quarter建模成所有港股 mandatory，也不把 A股 Q2/Q4 alias到 H1/FY。
- 不重构现有 storage publication；只在既有 candidate/meta 写入路径补足当前业务事实所需的最小 typed 字段。
- 不为了设计文档参数而无意义修改 Host/Engine；两份 design document明确 Host不承载财报业务语义、Engine只执行单次 run，本修复完整落在 CLI/Service/Fins边界。

## 风险与 open questions

- 风险：HKEX title/category 文本仍是 provider业务输入，需用 raw category fixture、腾讯式通用样本和真实补跑同时验证；不得只以单个网页标题证明。
- 风险：新增多期间投影必须避免把 Q2结果当作 H1报告、把 Q4结果当作 FY年报来满足 mandatory missing；identity period与covered periods需在 plan中明确不变量。
- 风险：真实 Docling 场景耗时与 provider可用性动态；失败只能形成真实 observed gap，不能切 fake。
- Blocking open question：无。显式 A股 Q2/Q4行为可在 bare-default policy与explicit policy分离后保持不变，因此无需用户新增裁决。

## Validation 与 artifact

- 已读取：`AGENTS.md`、两份 design doc、`docs/cli_ci.md`、Oracle裁决、两份真实观察报告、相关 production owner与 owner tests。
- 已执行只读 HKEX production discovery调查；未下载 PDF、未写 workspace业务状态。
- Artifact：`docs/gateflow/wu-cli-download-02-goal-confirmation-20260810.md`
- Residual risks：全部属于 approved plan/implementation/真实 post-fix observation 范围；无未分类 residual risk。
