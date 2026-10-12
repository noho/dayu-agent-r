# 601225.SH 年报全文普通增量下载修复：目标确认

- Work unit：`601225-annual-fulltext`，独立 bug fix；未提供 GitHub issue 编号，不自动创建 issue。
- Gate：`goal confirmation` 已由用户明确确认；已允许进入 plan，尚未进入 implementation。
- 分支：`fix/601225-annual-fulltext`。
- 基线：`7637bb0b4fbca212a4db0f4cfc09655e66516695`；preflight 原分支 main，工作区干净。
- 授权：创建本次工作分支、commit、push、新 draft PR 与正式审核/验收；不含 merge、转 ready、审批、邀请 reviewers、对外评论或操作其他任务。
- 本 artifact 路径：`docs/gateflow/601225-annual-fulltext-goal-confirmation-20261012.md`。

## 第一性原理判断

动机成立。普通公开下载入口成功返回，只说明已返回候选成功处理；同公司、请求窗口内的官方完整年报缺失，且独立摘要承担了年度件位置，会让下游分析取得不完整来源。修复范围应是 Dayu 财报下载的上游发现、业务选择与增量保留语义，不在调用方补下载三条已知 ID，也不能仅凭标题和日志缺席判定根因。

## 证据与限制

只读证据根：`/Users/leo/workspace/portfolio-manager-v2/orch/jobs/20261012-601225.SH-01/`。

已读取：

- `logs/dayu-maintenance-minimal-evidence-01.json`。
- `g0-dayu-version-01.json`（实际位于证据根，不在 logs 下）。
- `g0-ec-source-02-evidence/correspondence.json`。
- 三个年份的 `cninfo-*-annual.request.json` / `.response.json`、`cninfo-*-report.request.json` / `.response.json`。

完整目录 34 件与 stdout PDF 完成身份一致；退出 0，downloaded/discovered 均为 34，failed/rejected/uncertain 均为 0。summary 的 10 件与 omitted_count=24 是展示截断。

| 业务财年 | 全文公告 ID | 官方路径日期 | 现有年度件 |
| --- | --- | --- | --- |
| 2021 | 1213161683 | 2022-04-28 | 1213161682，独立摘要 |
| 2023 | 1219815158 | 2024-04-26 | 无年度件 |
| 2024 | 1223301988 | 2025-04-26 | 1223301999，独立摘要 |

三条全文同属 secCode=601225、orgId=9900023204，官方标题都是“年报全文”，完整目录中没有匹配 source ID / host-path 文档。两条已持摘要的官方索引标题本身未写“摘要”，不能归责为 Dayu 标题改写。

原下载后采集 dayu-agent 0.1.4、仓库 HEAD 7637bb0；没有下载启动时冻结代码树，不将采集版本冒充启动版本。官方补充请求与原调用参数有差异（包括 searchkey、plate、排序、协议等），不能将补充响应直接当作原调用响应。

官方补充年度分类加年份搜索在 2021/2023 返回空，2024 仅返回摘要 1223301999；无分类的“年度报告”搜索则包含三条全文。多个请求参数同时不同，当前不能隔离判定哪个参数造成发现差异。

## 直接代码证据与语义边界

- `dayu/fins/downloaders/cninfo_downloader.py`：按请求财期映射巨潮 category，发起 HTTP、分页、解析 raw 公告，并按 secCode 限定公司；raw DTO 当前未保留 announcementType 等更多分类字段。HTTP/provider 协议语义由此 owner 持有。
- `dayu/fins/pipelines/cn_report_selection.py`：产品级筛选、财年推断、同财期/财年分组与最优公告选择的唯一 owner。没有年份的标题回退到披露年份；排序先修订、再日期、再非“正文”，最后来源身份平手，不明确区分全文与标题无“摘要”的独立摘要。
- `dayu/fins/pipelines/cn_download_workflow.py`：应用用户披露日期窗；显式 start 时不启用默认数量限制。
- `dayu/fins/pipelines/cn_download_identity.py` / `cn_form_utils.py`：CN 候选按 ticker、财年、财期、修订状态分配文档身份。
- `dayu/fins/pipelines/cn_download_filing_workflow.py`：非 overwrite 且本地 source COMPLETE 时跳过远端传输；增量与发布事实由 filing workflow / storage 持有。此处需要证明既有摘要是否与后来正确全文发生身份冲突，不能先在 CLI 添加 bypass。
- 财报文档读写只能通过 `dayu.fins.storage` 的仓储协议与实现；公开入口只消费 owner 的真实结果。

已执行当前代码离线重放（激活 .venv，零网络、无下载/转换、无源码修改）：从官方 report 响应中选取年报分类记录，经现有 raw parser 和公开 selection helper，注入空 HEAD 元数据。

| 官方输入年度组 | 全文当前投影财年 | 同组其它选择 |
| --- | --- | --- |
| 2021 | 2022 | 1213161682 被选为 2021 |
| 2023 | 2024 | 显式摘要 1219815156 被排除 |
| 2024 | 2025 | 1223301999 被选为 2024 |

这直接证明：三条全文输入当前选择代码后不会被标题黑名单排除，但其财年会偏为披露年份。它是当前 owner contract 缺口的证据，尚非原下载完整遗漏链的定论。未重放全部年度集合的跨年分组竞争，未取得原调用全量 raw 响应，也未执行真实公开入口复现。

## 待确认目标

普通公开 `dayu-cli download` 在 `601225.SH`、`2018-01-01~2026-10-12` 下，使用通常非 overwrite / 非 rebuild 行为，正确发现、下载并持久保留三个官方完整年报，分别归属 2021、2023、2024 财年。准确区分全文与独立摘要，摘要不能冒充或阻挡完整年报；不以三条公告 ID、公司代码、特定年份作生产特例。

实现前基于同源原始响应与 owner 行为证实遗漏链，改在对应 owner 或其直接上游输入校验处，保留真实诊断、取消/失败与既有合法增量行为。

## 非目标与范围

- 不扩展到其它公告下载、财务数据提取/处理、调用方工程、其他市场下载重设计。
- 不改调用方受管目录，不覆盖原日志，不盲目 overwrite，不迁移或批量清理调用方历史资料。
- 不为此引入通用公告平台、通用内容分类框架、兼容 shim 或新的 Host/Engine 架构。
- 无年份的财年识别、全文/摘要选择、跨年去重与已有摘要阻挡问题，仅在证实其对本目标必要时纳入；具体 contract/schema 方案留给确认后的 plan。
- 其它财期/公司只作共享规则回归验证；发现独立问题归后续 work unit，不扩成本轮新增目标。

## 成功信号

1. 根因报告可追到原始来源事实、真实请求参数、选择/身份/增量 owner；区分原调用已证事实、当前代码复现与未证限制。
2. 在新建独立临时 base 中，经真实普通公开 CLI 入口获取上述三条全文，仓储读回 source ID/URL、正确财年、PDF 与转换产物、完成状态一致；全文身份和内容可核验。不能以摘要或三条直链下载替代。
3. 独立临时 base 的已有摘要场景，经普通增量调用仍取得正确全文；再次增量调用保持合法完整来源跳过/复用，不重复转换，不要求用户 overwrite。摘要身份与完整年报语义不能混同。具体受控样本构造由 plan 决定。
4. owner 级回归覆盖原始字段、无年份标题、全文/摘要竞争、跨年去重及增量；共享现有行为保留。激活 .venv 后受影响测试与 pyright 通过，新增/修改文件覆盖率目标至少 80%，README 按职责触发检查。
5. gpt-6-sol 经 sub-agents runner 负责 plan / implement / fix；mimo、ds-flash 同版同时并行审核，分别应用 planreview / deepreview；总控逐 gate 裁决并保存 artifact。所有 accepted findings 修复并复审，完成 draft PR 后 PR review 与 final closeout，交付 PR、commit、真实验证、剩余风险及公开入口可用性。

## 待定问题与风险归属

- 待取证：原参数下全文是否被返回、分页完整性、分类与标题字段的实际语义、全量跨年选择结果。属于确认后 plan 的根因调查输入，不预设标题过滤。
- 待设计：无年份全文如何可靠确定财年；无“摘要”标题如何区分；正确全文与既有摘要身份冲突如何在 owner 消除。必须由直接证据支撑最小方案；所有权仍不明确则停止实现。
- 非阻塞假定：按未关联 GitHub issue 的独立 bug fix 推进；如用户给出既有 issue，重新核对其范围和已授权关联操作。
- 历史启动版本未冻结：取证边界保留在本 artifact，原调用精确代码不可追溯风险交后续根因报告 owner（总控），不伪造确定性。
- 外部网络/巨潮/Docling 可用性可能影响真实验收：由实施与验收 gate 总控负责，真实入口验收不能由 mocks 或建 PR 代替。
- 日期归一化已看到 UTC 与中国本地日历存在一天差异；不将通用日期重构加入本轮，只有证实阻碍已确认成功信号才重新审视范围。

## 当前决策与下一入口

- Decision：用户已确认本文目标、非目标、owner 边界和成功信号，允许按固定 gates 持续到 final closeout。
- 确认补充约束：三条年报财年归属必须由可靠官方信息或原文证实，禁止将披露年减一当通用结论；不要求伪造历史 raw 响应；只修实现目标必要的具体问题，不扩一般日期重构或其它公告。
- Finding 状态：尚无正式 review findings；未作根因最终裁决。
- Validation：证据只读核对及现有代码离线重放退出 0；未修改生产代码/测试，尚无修复验证。
- Docs decision：本轮仅保存 goal artifact；实现后的 README 决定属于 plan/implementation gates。
- Current gate / next entry point：`plan`。
- 后续按 runner 子进程分工推进；不 clear 或打断其它任务。
