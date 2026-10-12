# 601225.SH 年报全文：根因直接证据

- Work unit：`601225-annual-fulltext`；gate：plan / 取证，供总控裁决，未实施。
- Binding scope：[目标确认](601225-annual-fulltext-goal-confirmation-20261012.md)。
- 当前分支 `fix/601225-annual-fulltext`，HEAD / 基线均为 `7637bb0b4fbca212a4db0f4cfc09655e66516695`，包版本 `0.1.4`，Python `3.11.15`。
- 本轮只新增计划与证据文档；取证脚本、官方 PDF 和独立仓储在本仓库 `workspace/tmp/601225-evidence/`。没有生产代码/测试修改、commit、push、PR、其它 Agent 或任务操作。

## 证据定位与可证边界

下文 `O` 为只读原证据根 `/Users/leo/workspace/portfolio-manager-v2/orch/jobs/20261012-601225.SH-01/`；`E` 为新证据根 `/Users/leo/workspace/dayu-agent-r/workspace/tmp/601225-evidence/`。原证据没有改写，也没有读取/写入调用方受管财报目录。

完整逐文件路径、字节数和 SHA-256 见 `E/evidence-manifest.json`（134 个文件，SHA-256 `c58cd0e5259115478601ba7864e1d7250df60eb77210f3c43a3d88d54858bffd`）。当前树版本与五个根因模块内容 hash 另见 `E/current-version.json`，SHA-256 `dc29a4a8ed83b244d20d288e05cb3f141ca958aa29472d763e57af6135534803`；其中 `production_diff` 为空。取证程序也在 manifest 中，可审查请求是否使用生产实现。

| 原证据相对 O 路径 | SHA-256 |
| --- | --- |
| `g0-dayu-version-01.json` | `77fbdd3e583d6a477b018c85680c7876ad1c56fa2374a12e9a366bfff140088b` |
| `logs/dayu-maintenance-minimal-evidence-01.json` | `83fc660eea7b2d876e8fa08729b2b43add2c8a46d6afa56669bdbda4687c8faf` |
| `g0-ec-source-02-evidence/correspondence.json` | `22057ada7cbb28ca37f195635e2f5d3f6a0d1de4346cb4287e89e350c6720508` |
| `g0-dayu-source-catalog-01.json` | `53371e1a1a8314caa451a59c88c6f589ae772a99d44dc7be079c210218bcb3ec` |

原命令位于 `O/logs/g0-dayu-download-01.command.json`，使用本仓库 `.venv/bin/dayu-cli --base /Users/leo/workspace/portfolio-manager-v2/workspace --log-file <原日志> download --ticker 601225.SH --start 2018-01-01 --end 2026-10-12`。开始 `2026-10-12T02:43:01.926069+00:00`，结束 `03:39:54.832280+00:00`，退出 0。原 catalog 34 件、stdout 的 34 个 PDF 完成身份一致；downloaded/discovered=34，failed/rejected/uncertain=0，摘要显示 10 件与 omitted=24 是展示截断。三条全文 ID 与 host/path 均不在完整 catalog；2021、2024 年度件分别持有摘要 1213161682、1223301999，2023 无年度件。

历史版本采集发生在下载之后，`O/g0-dayu-version-01.json` 观察到 0.1.4 / 基线 HEAD，未冻结启动树。原始 HTTP raw 没有留存。本轮不能证明历史启动代码字节、历史 raw 的完整发现集合或原调用实际淘汰阶段；不能把日志中无 ID 当作明确拒绝，也不能把当前重现冒充历史 raw。

## 当前真实原参数发现

运行 `source .venv/bin/activate && PYTHONPATH=. python workspace/tmp/601225-evidence/capture_current.py`，退出 0。程序直接调用生产 `CninfoDiscoveryClient.resolve_company` 和 `list_report_candidates`，使用 `CnReportQuery('CN','601225','2018-01-01','2026-10-12',('FY','H1','Q1','Q3'))`；真实 httpx response hook 只保存原请求与响应，没有替换业务选择或网络载荷。没有执行 Docling 或受管财报写入。

FY 请求 `E/current-002.request.json`（SHA-256 `61f656a04c11cd7cdfdcd0f165d97a5a203a8fdd23da41680599ba48086534cf`）为：

```json
{
  "method": "POST",
  "url": "http://www.cninfo.com.cn/new/hisAnnouncement/query",
  "form": {
    "pageNum": "1", "pageSize": "30", "column": "sse",
    "tabName": "fulltext", "plate": "sh", "stock": "601225,9900023204",
    "searchkey": "", "secid": "", "category": "category_ndbg_szsh;",
    "trade": "", "seDate": "2018-01-01~2026-10-12",
    "sortName": "time", "sortType": "desc", "isHLtitle": "true"
  }
}
```

真实响应为 `E/current-002.response.bin`，SHA-256 `8d1e30a693127c4bea34847ed816091be1eb768872a0bf75477d971985366471`，HTTP 200，`totalRecordNum=19`、19 条公告、`hasMore=false`。三条全文及两条隐名摘要都在其中；分页没有在本窗口截断。其余分类对应 `current-003/004/005`，raw 总数分别 18/11/9，均 `hasMore=false`。公司映射来自 `current-001`。HEAD 请求也逐件留存，完整请求/响应 hash 在 manifest。

生产选择输出 `E/current-discovery.json`，SHA-256 `1bc8b4765ef7bcd15a3e4923c4185b5e771502c26a91df404160cb8278dd3420`：候选总数 34，其中 FY 8 条。其全部 34 个 source_id 与原 catalog **集合相同**。这加强当前可重复性的证据，但不填补历史 raw 缺失。

### 与历史补充搜索的区别

`O/g0-ec-source-02-evidence/cninfo-{2021,2023,2024}-{annual,report}.{request,response}.json` 的路径和 hash 都在 manifest。annual 请求是 HTTPS、`searchkey=<年份>`、单个披露年窗口、plate 空、asc、isHLtitle=false、pageSize=30；report 请求是无 category、searchkey=年度报告、pageSize=100。annual 的 2021/2023 空、2024 只含摘要，不能据此归责生产 category：多个参数同时不同，且“年报全文”索引标题无财年。

本轮用真实原参数发现已直接证明 category 请求能够返回目标全文，因此本方案不改变 category、排序、协议或搜索窗口，不增加无 category fallback 搜索。

## 原文直接确认财年与全文/摘要

只从真实 FY 响应中的官方 `adjunctUrl` 获取 PDF。全部 13 条通过现有标题准入的 FY 原文都已取得，共 45,175,888 字节；未把这些证据原件写为受管财报。GET URL、响应头、时间、SHA、总页数和前两页文字在 `E/official-pdf-evidence.json`。`pypdfium2 5.7.0` 提取文字并渲染封面；五份关键封面 PNG 已逐张视觉核对。另在临时依赖目录安装 `pypdf 6.1.3`，对全部 13 份首页独立提取，见 `E/pypdf-cover-probe.json`；每份均产生唯一的报告财年与全文/摘要标签。没有按披露年减一推断。

| ID | 官方 PDF 相对 `http://static.cninfo.com.cn/` 路径 | PDF 页数 | 首页直接原文 | 原件 SHA-256 |
| --- | --- | --- | --- | --- |
| 1213161683 | `finalpage/2022-04-28/1213161683.PDF` | 287 | `2021 年年度报告`，公司代码 601225 | `41ec9bdf696e9e40a650288d042346ad03d05325a921e88fdc735efd5a7ccdb8` |
| 1219815158 | `finalpage/2024-04-26/1219815158.PDF` | 297 | `2023 年年度报告`，公司代码 601225 | `080827a40f33e613f876e60606daae838b83b715701c12a4f124712aa8bcbb7e` |
| 1223301988 | `finalpage/2025-04-26/1223301988.PDF` | 294 | `2024 年年度报告`，公司代码 601225 | `f3422819a11c1962ed4ae74d9a62e47a44635fc9e8b9d4de1e446824bbb91b86` |
| 1213161682 | `finalpage/2022-04-28/1213161682.PDF` | 26 | `2021 年年度报告摘要` | `a15100380ee1ae7930c612700d685aa18f9b02d794d92c4aa097cfaec8a029aa` |
| 1223301999 | `finalpage/2025-04-26/1223301999.PDF` | 29 | `2024 年年度报告摘要` | `c6e5e1c9499c601b3cdd17cff87af9464ecf46afd3fa908d5a0e43113efd861f` |

本地原件为 `E/<ID>.pdf`，首页文字 `E/<ID>.first-pages.txt`，封面 `E/<ID>.cover.png`；源 URL 相对路径中的日期只是披露定位。2020 竞争者 1209875597 原文同样是摘要（22 页），这只用于证明共享 FY 规则不能把无“摘要”的索引标题当全文，不把它另立修复目标。页数/大小没有用于分类。

raw `announcementType` 也不能解开此问题：1213161682 与 1213161683 都是 `01010503||010113||010301`，目标三条全文也均为该值；1223301999 是 `01010501||010113||010301`。字段不稳定地对应本文观察的摘要/全文，不能把这些数值固化为生产类型枚举或质量排序。

## 全量跨年选择竞争（当前代码）

`E/replay_owners.py` 对完整 FY raw 使用生产 `_parse_raw_announcement`、`_is_title_blocked`、`_infer_cninfo_fiscal_year`、排序键重放；结果 `E/cross-year-replay.json`，SHA-256 `e221eadb339e25427feb378f26b2abd98be852213cc12b6ec19b8a54f04f6024`。下表覆盖全部 19 条，日期为当前 parser 的 UTC 日期，保留一天偏差事实，不扩展日期重构。

| 当前财年组 | 可参与竞争 ID（日期） | 被标题排除 ID | 当前胜出 |
| --- | --- | --- | --- |
| 2017 | 1205110621 修订（2018-06-29）；1204545056（2018-03-29） | 1204545048 摘要 | 1205110621 |
| 2018 | 1206005283（2019-04-10） | 1206005275 摘要 | 1206005283 |
| 2019 | 1207678369（2020-04-29） | 1207678363 摘要 | 1207678369 |
| 2020 | 1209875598 全文；1209875597 隐名摘要（均 2021-04-29） | — | 1209875598，ID 平手裁决 |
| 2021 | 1213161682 隐名摘要（2022-04-27） | — | 1213161682 |
| 2022 | 1213161683 **2021 全文**（2022-04-27）；1216619553 **2022 全文**（2023-04-26） | 1216615192 摘要 | 1216619553，日期较新 |
| 2023 | — | 1219815156 摘要 | 无 |
| 2024 | 1219815158 **2023 全文**（2024-04-25）；1223301999 **2024 摘要**（2025-04-25） | — | 1223301999，日期较新 |
| 2025 | 1223301988 **2024 全文**（2025-04-25）；1225178190 **2025 全文**（2026-04-24） | 1225178199 摘要 | 1225178190，日期较新 |

直接代码链：

1. `dayu/cli/commands/fins.py::_download_stream` → `FinsDirectCommandService.download` → `DefaultFinsRuntime` 的 CN adapter → `CnPipeline.download_stream` → `run_cn_download_stream_impl`。
2. `cninfo_downloader.py::_query_announcements` 获取 category 原始全集；parser 不保存正文内容、只有标题、日期、来源等。
3. `cn_report_selection.py::_infer_cninfo_fiscal_year` 没有标题年份时直接返回 `announcement_date[:4]`，于是三条全文被放进错误财年。
4. `select_cninfo_report_candidates` **先按错误财年分组，再丢弃同组其它来源**；排序先 amended、再日期、再非正文、再 ID/URL。三条目标均正常通过标题准入，但分别被上表直接竞争者淘汰。
5. 显式 start 不启用 workflow 默认数量限制；本例的三条全文已经在 selection 丢失，不能靠 CLI summary 长度、改默认 limit 或手动三条下载修复。

结论：当前基线可以用真实生产发现请求、完整 raw 集合和同一选择代码证明“返回全文 → 无年份错财年 → 跨年日期竞争淘汰”的完整链。历史仅能证明缺失结果与当前重现一致，不宣称历史逐阶段已证。

## 身份与 COMPLETE 增量阻挡（真实隔离仓储）

CN `build_cn_filing_ids` 的 seed 为 `ticker|form|fiscal_year|fiscal_period|amended`，不含 source_id；`read_cn_download_identity_index` 当前只读 HK；CN 的 `resolve_cn_download_ids` 直接返回财期 ID。因此，正确 FY 投影后的全文和已有摘要会占用同一个 ID：

| 财年 | 摘要 / 全文 ID | 共享 CN document_id |
| --- | --- | --- |
| 2021 | 1213161682 / 1213161683 | `fil_cn_465a3bb60a5b4314f4bf993c871bbc23f3b4d856` |
| 2024 | 1223301999 / 1223301988 | `fil_cn_aaacc5f8032608460b8d410e99b6ac742284f4d2` |

`E/replay_owners.py` 分别在 `E/seeded-owner-2021-v2/`、`E/seeded-owner-2024-v2/` 使用 production pipeline/workflow/storage 写入官方摘要 PDF，再送入财年由原文确认的全文 candidate。只替换 discovery 与 Docling converter，真实 Fs 的 COMPLETE 分类、ID、事务和 skip 没有替换；这些替身不会验证真实网络发现或真实转换质量。

结果 `E/seeded-owner-replay.json`，SHA-256 `91ac14bc257f672eeac18a33161c52337bffb3ac343f3b20e85987b8f6cd43f8`：两例均 COMPLETE；第二次 downloaded=0 / skipped=1 / converted=0；下载、转换调用各保持 1 次；meta 不变，source_id 仍为摘要。

`cn_download_filing_workflow.py` 的 Phase A `COMPLETE && !overwrite` 在 CN 分支不比较候选 source_id 即返回 `integrity_complete`；Phase B 也有相同 COMPLETE skip。另有现存测试 `test_cn_complete_phase_a_skips_transport_without_source_mutation` 明确固化“不同 source_id 的全文候选被完整旧来源挡住”，因此必须迁移该测试到新的 FY 来源身份 contract，不能靠旧 fixture 倒逼保留行为。

源 ID 变化的含义：同一来源重复发现应复用现有身份；不同 source_id 的摘要/全文或新版全文不得因为财期 ID 相同而视为同一已完成源。修复选择 alone 会让 2021、2024 全文取得正确财年，却被本段阻挡；修复身份 alone 则没有三条全文 candidate。二者是同一个最小行为 slice 的必要部分。

## 已运行命令与真实结果

均在 `.venv` 激活后执行，结果日志位于 E：

| 命令 | 结果与边界 |
| --- | --- |
| `PYTHONPATH=. python workspace/tmp/601225-evidence/capture_current.py` | 0；真实发现、请求/响应、34 候选；无 Docling/财报写入 |
| `PYTHONPATH=. python workspace/tmp/601225-evidence/read_official_pdfs.py` | 0；13 份原文读取；无受管入库 |
| `PYTHONPATH=. python workspace/tmp/601225-evidence/replay_owners.py` | 修正取证脚本一次不存在的 `pipeline.close()` 调用后重跑，最终 0；v2 日志独立保留；初次失败记录仍在 `owner-replay.stderr.txt` |
| `pytest -q tests/fins/test_cninfo_downloader.py tests/fins/test_cn_report_selection.py tests/fins/test_cn_download_identity.py tests/fins/test_cn_download_models.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py` | 0；432 passed，3 warnings；`baseline-tests.log`；证明基线绿，未验证修复 |
| `pyright` | 0；0 errors / 0 warnings；`baseline-pyright.log`（另有升级提示） |
| `pyright --project workspace/tmp/601225-evidence/pypdf-type-pyright.json` | 0；strict PDFReader / BytesIO / 首页 extract_text 签名通过；`pypdf-type-probe.log` |
| `dayu-cli download --help` | 0；公开 base/date/overwrite/rebuild 参数确认；非下载验收 |

`pypdf 6.1.3` 仅装在 `E/python-deps/`，未改变 `.venv`、生产依赖文件或 lock。覆盖率本轮未测，没有代码修改；实施必须测修改文件 >=80%。

## 尚未完成与风险归属

- 历史启动树和 raw 不存在：**assigned to later work unit**，owner 总控，destination 本报告的历史证据边界；当前修复用已复现链裁决，不补造历史记录，不阻塞当前目标。
- 修复后的 clean base、seeded 摘要增量与再增量、真实 Docling 尚未执行：**fixed in current slice**（计划归属，尚未 fixed），owner 实施/验收 Agent，destination plan 的 S1 验证；是实施 gate 的必做未完成项，不能以此报告代替。
- 通用 UTC/本地披露日期偏差：**assigned to later work unit**，owner Fins 日期语义维护者 / 总控，destination 后续独立日期任务；当前三条披露都远离请求边界，不纳入本 slice。
- 扫描件、非封面年度标题、其它公告、H1/Q、其它公司异常，以及历史同 source 已存错误财年的自动纠正：**assigned to later work unit**，owner Fins 发现/财期维护者 / 总控，destination 后续独立 work unit；当前 13 个相关封面全部可解，方案对缺失/冲突 fail closed，不猜年度或用下游补偿。
- 巨潮、真实 Docling 外部可用性：**fixed in current slice**（验证责任，未完成），owner 实施/验收 Agent，destination 独立 CLI 日志及验收 artifact；无法完成真实验收则 gate 不得宣称通过。

当前没有仍需取证才能决定本目标最小方案的 open question；是否接受该 plan、允许实施由总控与后续 plan review 裁决。
