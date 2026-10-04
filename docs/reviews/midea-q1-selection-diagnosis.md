# 美的 000333 2021Q1 完整报告漏选 — CN 候选选择诊断

## 诊断元数据

| 项 | 值 |
|---|---|
| 诊断类型 | Gateflow work unit 前诊断（只读，后续接 /planreview） |
| 问题描述 | 美的集团 000333 2021Q1：完整季度报告未进入最终候选，被"正文"版本顶替 |
| 检查范围 | `dayu/fins/pipelines/cn_report_selection.py`、`dayu/fins/downloaders/cninfo_downloader.py`、`dayu/fins/pipelines/cn_download_workflow.py`、`tests/fins/test_cn_report_selection.py`、`tests/fins/test_cninfo_downloader.py`、`tests/fins/test_cn_download_workflow.py` |
| 基线 HEAD | `d30a07c8`（codex/upload-material-oracle，工作区干净） |
| 代码修改 | 无 |
| 提交 | 无 |
| 远端证据 | **已证实**（用户冻结）：000333 2021Q1 同日 3 条——中文正文 `1209870319`、中文全文 `1209870320`、英文全文 `1209870381`；公开 CLI 实际下载到正文 |
| 后续计划 | `docs/plans/midea-q1-full-report.md`（已落盘，待 /planreview） |

## 一、语义 owner 与现有合同

### 1.1 唯一语义 owner

"哪一份 raw announcement 成为财报候选"这一业务事实的 owner 是
`cn_report_selection.py`（模块 docstring 自证：`CN/HK raw announcement 到财报候选的业务选择真源`）。
分层边界由 downloader docstring 明示（`cninfo_downloader.py:21-23`）：

> 产品级候选筛选、标题黑名单、fiscal year 推断、同 period/year 去重、amended 优先与
> ``CnReportCandidate`` 构造由 ``dayu.fins.pipelines.cn_report_selection`` 持有；
> 本 downloader 只拉取 provider raw announcement 并提供 HEAD / GET HTTP 边界。

关键 owner 链：

| 语义 | owner | 证据 |
|---|---|---|
| 同 (period, year) 唯一候选的选择与排序 | `cn_report_selection._pick_best_cninfo_announcement` | `cn_report_selection.py:409-429` |
| 标题黑名单 / 语言过滤 / 财年推断 | `cn_report_selection` 模块级规则 | `cn_report_selection.py:41-83, 343-406` |
| provider raw 字段解析与 URL 归一 | `cninfo_downloader._parse_raw_announcement` | `cninfo_downloader.py:808-841` |
| 披露时间归一为 **日粒度** `YYYY-MM-DD` | `cninfo_downloader._format_announcement_date` | `cninfo_downloader.py:861-895` |
| 候选构造投影（含 `language="zh"` 硬编码、`filing_date`、`report_date=None`、`amended` 标题派生） | `cn_report_selection._build_cninfo_candidate` | `cn_report_selection.py:454-467` |
| 候选二次选择 | `cn_download_workflow._select_candidates_for_a4`（**只做业务窗口过滤，不重排**） | `cn_download_workflow.py:512-543` |

**关键事实**：工作流层没有二次排序，落选的同组公告在任何下游都没有第二次机会——"漏选"一旦发生即结构性丢失。

### 1.2 被测试固化的现有合同

- 同 period/year 只保留一份；不同 fiscal_year 各保留一份（`test_cninfo_downloader.py:796, 848`）。
- amended token 优先于披露日期（`test_cninfo_downloader.py:749`；`test_cn_report_selection.py:300`）。
- 摘要 / 英文版 / （英文）/ 港股公告 等标题必须排除（`test_cninfo_downloader.py:325`）。
- `announcementTime` 毫秒时间戳归一为 `YYYY-MM-DD` 日粒度（`test_cninfo_downloader.py:1490`）——**intra-day 时间精度在此边界被有意丢弃，且被测试固化**。
- 全仓库无任何 "正文" 相关处理、无 "更新后" token、无平局 tie-break 测试。

## 二、根因判定：同日平局 + 输入顺序裁决（已证实）

美的 2021Q1 属 `category_yjdbg_szsh`（`cninfo_downloader.py:78-83`）。远端已证实同日 3 条公告，
announcementId 时序递增给出发布序：**正文 `1209870319` → 中文全文 `1209870320` → 英文全文 `1209870381`**。

当前选择链在美的场景的实际走法：

1. 标题过滤：正文与中文全文均不被拦截（"正文"不在 blocklist，`cn_report_selection.py:41-65`；
   两者含 "第一季度报告" report token、不含 notice token）。英文全文命中英文语言标记/黑名单被排除。
2. 财年推断：fallback `(\d{4})\s*年`（`cn_report_selection.py:82`）命中 "2021年" → 同组 (Q1, 2021)。
3. 排序 key `(1 if amended else 0, announcement_date)`（`cn_report_selection.py:425-427`）：
   正文与中文全文均非 amended，`announcement_date` 同为日粒度 → **完全平局**。
4. `max(items, key=sort_key)` 平局时返回**输入顺序第一个**（已用 Python 实测验证）。
5. 输入顺序 = 巨潮响应顺序（请求参数 `sortName=time, sortType=desc`，`cninfo_downloader.py:542-543`），
   但两条公告 intra-day 时间相近/相同，provider 在时间平局时的内部排序对消费方不透明。

**证据闭合**：

- 用户用公开 CLI 实际下载到正文（`1209870319`）并冻结证据 → 生产实际裁决为正文胜。
- 本诊断用同一事实集、交换输入顺序复现：英文全文在前、中文全文次之、正文在后的顺序下，
  当前代码选出的是中文全文 `1209870320` —— **同一事实集仅输入顺序不同，结果翻转**，
  平局机制（而非任何标题规则）即为根因，且生产形态落在"正文胜"一侧。

## 三、有限候选排序反例矩阵

矩阵覆盖用户指定六维度。远端已证实行以 ✅ 标记。

| 维度 | 输入 | 当前行为 | 判定 |
|---|---|---|---|
| A. 正文单独存在 | 分类内仅 "2021年第一季度报告正文" | 入选，fiscal_year=2021（fallback 正确） | **可接受**。若远端确实无完整版，这是正确行为；美的场景远端有中文全文，不适用此豁免 |
| B. 正文与完整报告同日 ✅ | 正文 `1209870319` + 中文全文 `1209870320` 同日，均非 amended | 平局取输入顺序第一个；生产实际返回序使**正文胜，完整报告漏选**（CLI 证据） | **反例成立（已证实）**。证据链：日粒度丢弃（`cninfo_downloader.py:861-895`）+ 平局无 tie-break（`cn_report_selection.py:425-429`）+ 无下游重选（`cn_download_workflow.py:512-543`） |
| B′. 同集合顺序翻转 ✅ | 英文全文在前、中文全文次之、正文在后的顺序 | 中文全文 `1209870320` 胜（本诊断实测复现） | 同一输入集合仅交换顺序结果翻转 → **选择非确定性，双向均已实证** |
| B″. 两版不同日 | 完整版 04-29、正文 04-30（或反之） | 日期 desc 决定，后发布者胜；若正文后发同样漏选 | 反例成立（B 的日期化变体）；**按已确认的最小修复口径（维持跨日期优先级），本行列为已知残余边界，不在本轮修复** |
| C. 真实更正版本 | "2021年第一季度报告（更新后）" + 原文同日 | "更新后" 不在 `_CNINFO_TITLE_AMENDED_TOKENS`（`cn_report_selection.py:80`，仅 更正/更正后/修订/补充/修正）→ 判为非 amended → 平局由输入顺序裁决 | 反例成立（独立残余 gap）。美的已证实 3 条标题无更正标记，**不是本次根因** |
| C′. 更正组合 | [全文（更新后）, 正文] 同日 | 两者均判非 amended → 平局 → 正文可能胜于更新后全文 | 组合反例（C × B），独立跟踪 |
| C″. 更正公告 | "关于2021年第一季度报告的更正公告" | 含报告 token + "公告" notice token → notice 组合规则拦截（`cn_report_selection.py:361-363`） | 正确；"补公告"类噪音已被规则覆盖 |
| D. Q1/Q3 财年推断 | "2021年第一季度报告" / "2021年第三季度报告" | FY_PATTERN 仅覆盖 年度报告/年报（`cn_report_selection.py:81`），Q1/Q3 走 fallback → 2021 正确 | 无已知缺陷。Q1/Q3 是"正文"变体高发财期（`category_yjdbg_szsh` / `category_sjdbg_szsh`）；FY/H1 的变体"摘要"已被 block |
| D′. 无年标题 | "第一季度报告正文"（无年份） | 走 announcement_date 年份 fallback（`cn_report_selection.py:404-405`） | 正确（A 股日历年，披露年即财年）。不构成反例 |
| E. 英文摘要排除 ✅ | 英文全文 `1209870381`（带英文版标记） | 命中英文语言标记/黑名单被排除（本诊断复现确认未入选） | **正确（美的实测行）**；摘要 / （英文）/ 英文摘要各形态均已有测试固化 |
| E′. 纯英文无标记标题 | "Midea Group: 2021 First Quarter Report" | 无 blocklist token、无中文 report token、无"年"字 → 语言过滤不命中；财年走 announcement_date fallback → 入选且 `language="zh"` 硬编码（`cn_report_selection.py:459`） | 边界反例（巨潮 A 股概率低，美的实际英文全文带标记已被排除，本行不构成本次根因） |
| F. 输入顺序稳定性 ✅ | 任意同组平局集合，仅交换 provider 返回顺序 | `max()` 平局取输入序第一个 → 结果翻转（本次 B/B′ 双向实证） | **反例成立**。sort_key 无 announcement_id / URL 字典序兜底，排序合同不含确定性保证 |

## 四、完整性与更正优先级的可证据化 tradeoff

当前排序证据只有两个：标题 amended token（更正等）与日粒度日期。**两者都不携带"完整性"信息**，因此平局裁决在证据层面是空白，只能落到输入顺序——美的场景即为该空白被 provider 顺序填成错误结果。

可选完整性证据源与代价：

| 证据源 | 优点 | 代价 / 局限 | 结论 |
|---|---|---|---|
| a. 标题质量语义（非正文 > 正文） | 零远端依赖、确定性、改在 selection owner 内 | 需枚举标题形态（正文/全文/无后缀）；是产品规则而非 provider 事实 | **已确认为最小修复的 tie-break** |
| b. content_length（HEAD） | 已有 HTTP 边界 | 现 HEAD 只对胜者调用一次（`cn_report_selection.py:279`），平局裁决需对组内每成员 HEAD（throttle 0.3s/请求）；远端依赖 + `None` 退化；"正文 < 全文"只是统计规律而非 contract | 不采用 |
| c. intra-day 时间戳 | 保留 provider 原始事实 | 需在 downloader 归一化边界保留精度 → `CninfoRawAnnouncement` 字段变更 → 按项目 schema 规则全新起库，成本最高；且"后发布"只能证明时间序，不证明"更完整" | 不采用；与测试固化的日粒度合同冲突 |

**已确认的最小修复口径**（与 `docs/plans/midea-q1-full-report.md` 对齐）：
排序 key 扩展为 `(amended, 日期, 非正文优先, ID/URL 字典序)` 全序——

- 维持现有 amended 第一、跨日期优先级不动的合同（`test_cninfo_downloader.py:749, 848` 继续有效）；
- 同日平局按标题质量（非正文优先）裁决，ID/URL 字典序兜底剩余平局；
- 只解决同日形态；跨日期"正文后发"（B″）按口径维持现状，作为已知残余边界记录；
- 改动收敛在 owner boundary `_pick_best_cninfo_announcement`，零 schema 变更、零新远端依赖。

"（更新后）" token 缺失（C 行）与 `language="zh"` 硬编码（E′ 行）均为独立残余 gap，与美的本次根因无因果，不并入本轮修复。

## 五、最小验证建议

1. **单元级反例先行**：在 `tests/fins/test_cn_report_selection.py` 增加参数化矩阵测试，用美的已证实事实集
   （正文 `1209870319`、中文全文 `1209870320`、英文全文 `1209870381`，同日）断言：
   a. 英文全文被排除；
   b. 两种输入顺序（正文在前 / 全文在前）均选出中文全文 → 断言 owner 级全序确定性，不固化输入顺序；
   c. amended 优先与跨日期优先级合同不回归。
2. **远端验证已完成**：3 条同日事实与 CLI 下载证据已冻结，无需再采集；如修复后需回归证据，
   复用已冻结的正文 PDF 与 raw 快照即可。
3. **修复边界**：只改 `cn_report_selection._pick_best_cninfo_announcement` 的 sort_key；
   不动 downloader、不动 schema、不动 workflow 二次选择。

## 六、风险与未覆盖项

- B″（跨日期正文后发）按已确认口径维持现状，属已知残余边界；若未来出现同类案例再单独裁决。
- C（"更新后" token 缺失）与 E′（纯英文无标记标题 + language 硬编码）为独立残余 gap，本轮不扩散。
- HK 路径 `_pick_best_hk_announcement`（`cn_report_selection.py:748-767`）存在同构 `(amended, filing_date)` 平局问题，但 HK 财报无"正文"惯例，本轮不扩散。
- 标题质量规则若覆盖"全文"变体标题（"……报告全文"），需一并枚举，避免只修"正文"留下同类平局。
