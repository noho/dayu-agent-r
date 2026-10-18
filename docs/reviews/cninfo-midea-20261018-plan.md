# 巨潮美的下载失败：实施计划与根因证据

状态：plan 产出，待总控核对；没有实施、计划放行或修复验收通过结论。

## 绑定范围与版本

- Binding scope：[已确认目标](cninfo-midea-20261018-goal-confirmation.md)；授权进度以 [control](cninfo-midea-20261018-control.md) 和本次用户交接为准，不采用 goal 文件遗留的“等待确认”状态。
- 分支 `fix/cninfo-midea-report-identification-20261018`；HEAD/base 均为 `1b2166305428d894696974519615cfc4a0ca3b20`。预检时未跟踪文件只有总控拥有的 goal/control；本轮未改动它们。
- 已完整读取 AGENTS.md、goal、control、外部 `dayu-task.md` 和 Gateflow SKILL.md。本轮职责仅为 plan/必要取证，没有派 agent、修改生产代码、commit、push、开 PR 或运行写入业务仓储的 CLI。
- 下文证据根 `E` 为本仓库 `workspace/tmp/cninfo-midea-20261018/`。全部脚本、原始响应、PDF、提取文本和验证日志均在 E 内；原始调用证据只读并另存副本，没有覆盖。

## 动机、已证明根因及证明边界

动机成立：原调用退出 1，provider 为 cninfo、分类 provider_transport/protocol；全零结果来自发现未正常返回，不能当作无报告。当前同 ticker、同日期、同默认财期的真实官方发现也可稳定到达相同错误。

直接同源证据链如下：

1. `discovery-live-01/001-*` 保存生产 URL 的公司映射，HTTP 200，`000333` 对应 `orgId=9900005965`、美的集团。`002-*` 至 `005-*` 是生产 downloader 发出的四个分类 POST，查询日期均为 `2025-01-01~2026-10-18`，FY/H1/Q1/Q3 与 `cn_form_utils.CN_BARE_DEFAULT_PERIODS` 一致。各页 `hasMore=false`，公告数量分别为 4/4/2/1。
2. FY 响应中两份标题明确为摘要，先被现有准入规则排除；第一份实际准入原件是 source ID `1225065145`，标题“2025年年度报告”，URL 为 `http://static.cninfo.com.cn/finalpage/2026-03-31/1225065145.PDF`。`006-*` 记录真实 GET 200、PDF 字节及 SHA256；无本地缓存输入的生产 `CninfoDiscoveryClient.list_report_candidates` 在这里退出 1。
3. 相同 PDF、相同 pypdf 6.1.3、相同 facts owner 的真实首页提取结果，物理第 1 行为 `美的集团股份有限公司 2025 年年度报告全文`，第 6 行为 `2025 年年度报告`。`cn_annual_report_facts.py:43-51` 把第 1 行标签后的 `全文` 当作不支持后缀，立即抛出 `ValueError("年度标签后缀不明确")`，尚未处理后面的同年裸标签。
4. `cninfo_downloader.py:308-355` 在 selection 前逐个获取全部准入 FY 原件；`:1003-1010` 将上述异常包装为不可重试的 CNINFO/PROTOCOL，安全消息恰为原调用中的“巨潮年度报告原文无法确认财年或全文性质”。完整 cause 栈保存在 `discovery-live-01/failure-traceback.txt`；此时尚未生成 candidate/document_id、prepared 结果或 filing 处理结果。
5. `owner-replay.json` 记录原字节复放同样失败。仅在单独分析文本中移除首页首行的 `全文` 二字，现 owner 即返回 `(2025, full)`；对照文件为 `1225065145.counterfactual-text-only.txt`，没有修改 PDF，也没有给生产执行提供改写输入。该单因素对照将本次当前复现直接定位到封闭后缀遗漏，排除网络非 PDF、无文字、年份缺失、年份冲突等解释。
6. 同查询另一准入原件 `1222951181`（2024 年全文）也已真实取回，原 owner 返回 `(2024, full)`。它不是本次当前复现中的失败来源；不能笼统声称“美的所有报告均无法解析”。

因此，已证明的当前根因是：**年度事实 owner 的全文标签语法遗漏明确的“全文”后缀，导致一份具有同年一致全文证据的合法官方 PDF 在发现阶段被拒绝。** 伴随缺陷是三个边界把不同拒绝理由投影为相同外层说明，日志没有保留足以定位的来源和 owner 拒绝原因。

历史断言的边界：原调用开始于 2026-10-18 13:28:36 +08，现采集开始于 13:58:19 +08。原证据未保存该次官方响应/PDF、失败 source ID 或完整 cause；原 `dayu.log` 只有进入 CN/HK 流程的一行。同外层消息还可能来自 `_read_local_cn_annual_pdfs` 的本地原件声明失败。因此，不能证明原调用当时必然处理 `1225065145`，也不能排除当时先在本地声明预读中止。没有以间接时间/空计数补足这一缺失，也未手动读取调用方受管文档。本计划依据当前真实官方字节和生产发现链的可重复失败修复；历史具体来源不标成已确认 document_id。若总控要求追溯原调用的唯一来源，则缺少该次输入快照是该额外断言的 blocker，不能由本次取证恢复。

## 可取回证据、来源身份与文本

采集环境见 `owner-replay.json`：Python 3.11.15，pypdf 6.1.3，导入 `/Users/leo/workspace/dayu-agent-r/dayu/__init__.py`，包版本 0.1.4。原 CLI 入口未执行；该导入证据不能替代实际 CLI 验收。

官方请求入口：

- 公司映射：`http://www.cninfo.com.cn/new/data/szse_stock.json`。
- 分类查询：`http://www.cninfo.com.cn/new/hisAnnouncement/query`；form 原文在每个 `*-exchange.json` 的 `request_body_utf8` 和 `*-request.bin`，包含 `stock=000333,9900005965`、pageNum=1、pageSize=30、column=szse、plate=sz、tabName=fulltext、sortName=time、sortType=desc。
- 所有请求均使用生产默认 UA，未替换官方响应；只注入保存 response 的观察 hook，没有访问业务仓储。采集 UTC、HTTP 状态、选定响应头、字节数及 SHA256 均随 exchange 保存。

| 证据文件（E 下） | 官方响应 SHA256 | 内容 |
| --- | --- | --- |
| `discovery-live-01/001-response.bin` | `96bd665377233f6e93e3a9cb77d3a06ec7b7b881c0b111a96e061075923f0989` | 公司映射 |
| `discovery-live-01/002-response.bin` | `8a9dcceb21cfec553b6583e920b79d87278bd7c344f3e91033d3cbfe228bf9f9` | FY 四条原始公告 |
| `discovery-live-01/003-response.bin` | `bcba20685ee606a092f9a0bd04a73266e8015b139ef7c4ea1ecdfe441a107d1a` | H1 四条 |
| `discovery-live-01/004-response.bin` | `d1a8434201a53fabc609303f3843f8959984f1c860f43d041a91be86b6923f86` | Q1 两条 |
| `discovery-live-01/005-response.bin` | `1c1116e10479681d3c5adf8ee95ccb37e58c256076197cdbd4e9ef0f741a967a` | Q3 一条 |

FY 四份 PDF 均保存原始完整字节，不把派生首页冒称原件：

| source ID / 公告日期 / 官方路径（前缀 `http://static.cninfo.com.cn/`） | 完整原件 SHA256 / 字节 / 页数 | 原件与事实 |
| --- | --- | --- |
| `1225065145` / 2026-03-31 / `finalpage/2026-03-31/1225065145.PDF` | `16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6` / 5,942,399 / 276 | `annual-evidence/1225065145.pdf`；首页明确 2025 年年度报告全文，同年裸标签；原 owner 拒绝“全文”后缀 |
| `1222951181` / 2025-03-29 / `finalpage/2025-03-29/1222951181.PDF` | `b17a9b9b84bca1d2a4e4a3cadc5dd5ba5c85e3f1fd2d758acd3315b5b040ecd9` / 6,737,887 / 295 | `annual-evidence/1222951181.pdf`；首页“2024 年度报告”，原 owner 为 2024/full |
| `1225058109` / 2026-03-31 / `finalpage/2026-03-31/1225058109.PDF` | `ead2a179260377a5545989f8d02c001ca09e2b42e4027df8fb5e9ac8539f1a6b` / 293,678 / 7 | `annual-evidence/1225058109.pdf`；首页两处“2025 年年度报告摘要”，标题也明确摘要，实际 discovery 不 GET |
| `1222951198` / 2025-03-29 / `finalpage/2025-03-29/1222951198.PDF` | `383b609cc6c197b07e3c52c3ae8e1e22360ce8fb033785cafd51a86475108b62` / 517,769 / 8 | `annual-evidence/1222951198.pdf`；首页两处“2024 年年度报告摘要”，标题也明确摘要，实际 discovery 不 GET |

每个 source 的 `.evidence.json` 包含原公告、URL、取回时间/响应头、完整字节 hash、页数、原 owner 结果；`.page-001.txt` 至 `.page-008.txt`（以实际页数为限）及 `.all-pages.txt` 保存实际 pypdf 提取文本。四份总索引为 `annual-evidence/index.json`，全文件 hash 索引为 `evidence-files.json`。`006-response.bin` 与 `1225065145.pdf` 是同一组字节。

2025 原件的物理第 5 页目录列出“第八节 财务报告”，第 7 页释义直接写“报告期 指 2025 年1 月1 日至2025 年12 月31 日”；2024 原件目录列出“第十节 财务报告”，第 7 页释义直接写 2024 年1 月1 日至2024 年12 月31 日。摘要原件则直接声明“本年度报告摘要来自年度报告全文”。这些是本次人工核验身份的原文证据，并非拟新增 parser 的多页扫描规则。

本方案无需自然会计年度推断：2025、2024 均已有原件直接年度标签。**不使用发布日期推导财年，不以法规推定全文，不引入自然年度 fallback**，故没有需要采纳的外部法律规则；若实施发现必须依赖该规则，应先补权威 URL/原文证据并回到计划核对，不能凭常识添加。

当前官方响应中，按现有准入与同财期/财年选择规则、在补齐年度事实后预计形成以下七个来源候选（这是计划断言，不冒称已跑通 selection/CLI）：

| 财年/财期 | source ID | 公告日期 | 原标题 |
| --- | --- | --- | --- |
| 2026/H1 | `1225531404` | 2026-08-29 | 2026年半年度报告 |
| 2026/Q1 | `1225259066` | 2026-04-30 | 2026年一季度报告 |
| 2025/FY | `1225065145` | 2026-03-31 | 2025年年度报告 |
| 2025/H1 | `1224626720` | 2025-08-30 | 2025年半年度报告 |
| 2025/Q1 | `1223412432` | 2025-04-30 | 2025年一季度报告 |
| 2025/Q3 | `1224767336` | 2025-10-30 | 2025年三季度报告 |
| 2024/FY | `1222951181` | 2025-03-29 | 2024年年度报告 |

H1 另两条为标题明确的摘要 `1225531403`、`1224626731`。非 FY PDF 本阶段未取回，不能宣称其内容已核验；真实 CLI 必须完成它们的正常获取和转换。本请求显式 start，workflow 不应用默认数量截断。未凭来源 ID 构造任何猜测 document_id。

## 语义 owner、实际影响入口与不变量

| 事实/职责 | 唯一 owner | 本次处理 |
| --- | --- | --- |
| 实际原件的年度与全文/摘要事实、解析拒绝理由 | `cn_annual_report_facts` | 在此补齐明确全文标签；保留纯字节输入，无网络/仓储/标题/发布日期/LLM/OCR 依赖 |
| 准入、摘要排除、同年财期选择和 candidate 投影 | `cn_report_selection` | 消费 owner 事实，不从公告标题修补 FY，不放宽筛选、不静默跳过解析失败 |
| 远端公告/字节获取、provider 错误分类、发现请求 scope | `cninfo_downloader` | 为远端和本地缓存 facts 调用附带已知来源诊断，任一准入 FY 失败仍整体终止 |
| 本地唯一 original 的声明/descriptor/字节及 exact revision | `cn_annual_report_source` + storage | 不改变原件声明和仓储完整性规则；声明拒绝与文字解析拒绝分别可诊断 |
| 下载资产事实复核、COMPLETE 原件证明、单 filing 失败 scope | `cn_download_filing_workflow` | 复用相同 facts owner；补来源和拒绝理由，保持业务错误与完整性/取消类型的原边界 |
| 来源身份分配、持久化字段与真实投影 | `cn_download_identity` / `cn_download_source_upsert` | 不改规则；FY 的 fiscal_year_source 仍为 source_document，真源经同一路径写 source/manifest/result |

已逐处核查的实际受影响路径：

1. 远端发现：`cninfo_downloader.py:320-335` 的 GET/实体校验/facts；未选中的准入年度原件也必须校验，不能先挑“目标年”避开失败。
2. 本地缓存发现：`:317-319` 对 `CnAnnualReportPdf` 再解析；来源 `(cninfo, source_id)` 不变，复用字节不是免检。
3. 下载资产复核：`cn_download_filing_workflow.py:285`，同时覆盖 prepared_asset 与直接 download_report_pdf；不允许 prepared 绕过复核。
4. COMPLETE 无 witness 的本地原件复核：同文件 `:1040-1071`。合法“全文”后缀须同样通过；摘要、错年、缺字/冲突仍失败，远端 prepared 不得替代本地证明。
5. COMPLETE 有同版 witness 的增量：共享事实 owner 已在 discovery 证明本地 exact 原件；保持 witness/revision 校验和 A/B 重观察规则，不重复推断财年。
6. 发现前本地声明读取：`cn_download_workflow.py:1150-1184`；不是文字 parser，当前也会投影相同外层说明，应记录明确的本地声明拒绝阶段，不能误报成远端 PDF 文本根因。

这些流程由现有 CLI、Service/direct、工具/awaiting 与既有 job 调用共享 runtime/adapter 到达，修复落在共享 owner；不在任何入口单独加分支。local-only rebuild 不调用本 facts owner，H1/Q 与 HK 不使用 CN 年度 facts 规则，均不新增行为。

## 最小必要行为与重要取舍

默认一个 implementation slice：**补齐明确全文标签、共享拒绝诊断、相应回归与真实普通增量验收**。没有依赖性迁移或需要先上线的步骤，无需拆 slice。

- 在 facts owner 的现有封闭语法中接受标签后的明确 `全文`，返回 `full`；裸年度标签保持既有 full 语义，已有摘要语法保持 summary 语义。空白归一、同年重复标签一致性继续在该 owner 处理。首页上“同年全文标签 + 同年裸标签”应返回唯一 full；年份不同、full/summary 混合、同一行多标签、未知或未闭合后缀仍拒绝。
- 不采用“找到一个合法标签就成功”的策略；不能删掉出错行、忽略页眉、遇到 `全文` 前缀即接受，也不能把任意后缀解释为全文。`全文摘要`、`全文说明`、`全文（未知）`、`补充`、冲突年份等必须仍拒绝。分行标签、无文字封面等本次未证明的新形式不扩大支持。
- 保留当前只读首页的能力边界。本次原件首页已经充分自证，增加多页扫描、自然年度 fallback、OCR 或 LLM 识别没有当前必要性。
- owner 的拒绝原因须保持安全且可稳定投影：解析/提取失败、同一行标签冲突、不支持后缀、年度/性质事实缺失或冲突。可在该 owner 用小型类型化异常携带封闭 reason，避免消费者解析异常字符串或暴露底层 pypdf cause；具体局部函数/类型拆分由实现者决定。不新增持久化 schema 或公共下载字段。
- 在上述实际拒绝边界写 warning/error 级诊断，使默认新 `--log-file` 可取得，不依赖 debug。最少包含 provider、已知 source ID、输入阶段（远端发现/本地缓存发现/下载复核/COMPLETE 原件复核/本地声明读取）、owner 拒绝理由；只有真实 document_id 已存在时才附带它。上下文必须显式传参，不能放 extra payload 或从 PDF 文件名/URL 反推身份。
- 共用一份窄的安全诊断投影规则，原因由 facts/source owner 产生，调用边界只提供身份/阶段并记录。不复制业务判断，不建通用诊断框架。身份引用须有界、转义控制字符；对无法安全展示的异常来源引用，只记录明确的不可展示标记及关联摘要，不能将其伪装成业务 source ID。不得记录 raw PDF、正文、任意 URL/查询串、绝对路径或底层异常内容。正常官方数字 source ID 必须可定位。本地声明错误保留自身 owner 的安全理由，不能归因为标签不支持。
- 外层 public 安全消息、provider_transport/protocol、不可重试语义和 summary schema 保持现有契约；详细原因写同次日志。发现前仍没有失败文档行/虚构 ID，单 filing 拒绝仍用现有 provider_protocol/source_document_facts_mismatch 范畴，完整性错误与取消继续保留原类型及已提交前缀。无须修改调用方、runtime/public schema、仓储协议或状态机。
- 实施文件限于上述 facts/调用诊断边界、必要共享窄投影及对应测试/fixture/README；selection、身份、存储、UI 无证据支持新增业务分支。若实现必须改变这些公共边界或已确认验收，应记录 blocker 回交总控，不自行扩大。

本计划是局部 owner 语法补齐及可观测性修复，未提出公共契约、迁移、重要状态机或架构改动；建议由总控按简单 plan 核对，并最终裁决 planreview 适用性。本轮没有自行派 reviewer 或宣称 gate pass。

## 回归、类型与实际验收

### 本阶段实际已执行

所有命令均在仓库 cwd，先 `source .venv/bin/activate`，并使用 `PYTHONDONTWRITEBYTECODE=1`；各进程均等待真实退出。

| 命令（激活环境后） | 实际结果与证据 |
| --- | --- |
| `python workspace/tmp/cninfo-midea-20261018/capture_discovery.py` | exit 1；生产远端发现按上述 PDF/owner cause 失败；`discovery-live-01.stdout.txt`、`.stderr.txt`、子目录 exchange/cause |
| `python workspace/tmp/cninfo-midea-20261018/collect_annual_evidence.py` | exit 0；四份完整年度 PDF、全部文本和逐源事实结果；`annual-evidence.stdout.txt` / `.stderr.txt` |
| `python workspace/tmp/cninfo-midea-20261018/replay_owner.py` | exit 0；原字节和单因素对照见 `owner-replay.json`，原调用副本在 `original-call-evidence/` |
| `python -m pytest -p no:cacheprovider --basetemp=workspace/tmp/cninfo-midea-20261018/pytest-baseline tests/fins/test_cn_annual_report_facts.py tests/fins/test_cninfo_downloader.py tests/fins/test_cn_report_selection.py -q` | exit 0，190 passed、3 条 edgartools 弃用 warning；`pytest-baseline.stdout.txt` / `.stderr.txt` |
| `pyright` | exit 0，0 errors/0 warnings；`pyright-baseline.stdout.txt` / `.stderr.txt` |
| `pyright workspace/tmp/cninfo-midea-20261018/capture_discovery.py workspace/tmp/cninfo-midea-20261018/collect_annual_evidence.py workspace/tmp/cninfo-midea-20261018/replay_owner.py` | exit 0，0 errors/0 warnings；`pyright-evidence-scripts-final.stdout.txt` / `.stderr.txt` |

最终字节校验见 `plan-validation-receipt.json`：六次官方交互及四份年度 PDF 的字节数/hash 一致，94 个证据文件已纳入清单（排除临时 pytest 工作树及清单自身）。三个采集/重放进程、baseline pytest、全仓 pyright、取证脚本 pyright 均已观测到真实退出；清单生成脚本也经单独 pyright 并退出 0。

基线测试通过说明旧测试遗漏了本次合法全文标签，并不代表缺陷不存在或修复已完成。取证脚本为单次采集，目录已存在时拒绝覆盖；后续真实采集应使用新目录，不直接重跑覆盖证据。

### slice 的必要断言

1. **facts owner**：冻结本次 FY 官方响应和两份全文首页派生 PDF，附官方 URL、采集时点、原件/派生件 hash、生成方式及提取文本。使用真实 pypdf 调 public `resolve_cn_annual_report_facts`，断言 2025/full 和 2024/full。2025 正例必须在 base 失败、修复后通过；保留现有 13 份官方样本。派生页与完整原件分别标识，不把临时目录当长期 fixture 依赖。
2. **拒绝与语法**：同年“全文+裸标签”、空白归一；错年、full/summary 冲突、未知后缀及 `全文摘要` 等不能被新规则吞掉；摘要正例继续为 summary，明确标题摘要仍不取原件；现有摘要正文过于复杂而证据不足时明确拒绝，不能推定 full。坏字节/零页/加密/空白提取仍拒绝，并检查 owner reason 的边界。
3. **真实 discovery**：httpx.MockTransport 仅替换网络，输入冻结原响应和官方派生 PDF；不 mock facts，不伪造候选结果。按 bare FY/H1/Q1/Q3 全窗得到表中七个来源候选，FY year source 为 source_document。两个准入 FY 均完成 facts，摘要不 GET，prepared 原件与选中来源 hash 一致。
4. **本地/远端同源**：对相同官方全文，远端 prepared、直接资产下载、本地 discovery、无 witness COMPLETE 复核及有 witness repeat 分别通过；使用真实隔离 Fs 仓储与原件声明，断言来源、财年、覆盖财期、原件 hash、document_id/内部身份由现有 owner 生成并保持一致。对摘要/错年/坏原件仍拒绝；不得 mock 一个 full 结果替代真实 owner。
5. **失败 scope/诊断**：落选但准入的坏 FY 仍使整个 discovery 失败，不能产生部分候选或业务写入；本地声明失败与 parser 失败各有可定位日志；发现前无 document_id；下载/COMPLETE 复核仍保持单 filing 与完整性/取消边界。覆盖 raw cause 含 URL、绝对路径、正文、控制符等反例，验证详细日志仅用封闭原因和安全来源引用，public 失败消息/分类不泄漏或漂移。
6. **增量不重写**：首次完成后从仓储取得 exact publication；再次普通请求保持来源身份、revision、原件/Docling hash 和 manifest 不变，未重复 GET 已完整的两个 FY 原件、未重复转换；不能只用 summary 的 skipped 或没有 debug 行证明零 GET。

建议实施验证命令（所有输出写 E 下新的 `implementation-validation/`；目录先由临时验证脚本创建）：

```bash
source .venv/bin/activate
PYTHONDONTWRITEBYTECODE=1 COVERAGE_FILE=workspace/tmp/cninfo-midea-20261018/implementation-validation/.coverage \
python -m pytest -p no:cacheprovider \
  --basetemp=workspace/tmp/cninfo-midea-20261018/implementation-validation/pytest \
  tests/fins/test_cn_annual_report_facts.py tests/fins/test_cn_annual_report_source.py \
  tests/fins/test_cninfo_downloader.py tests/fins/test_cn_report_selection.py \
  tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py \
  tests/fins/test_cn_download_identity.py \
  --cov=dayu.fins --cov-report=term-missing \
  --cov-report=json:workspace/tmp/cninfo-midea-20261018/implementation-validation/coverage.json -q
PYTHONDONTWRITEBYTECODE=1 pyright
```

核对覆盖率 JSON 中每个实际修改生产文件目标 >=80%，不足则补充有意义的 owner/失败路径断言；不拿全包平均数替代单文件核对。新增 fixture/helper/测试也必须过全仓 pyright。若实际修改触及 runtime/CLI 的公共投影，再补跑 `tests/cli/test_fins_commands.py`、`tests/service/test_fins_direct.py`、`tests/service/test_fins_wait_adapter.py`；本计划未授权更换投影真源。测试命令按实际修改增减相关依赖用例，不能删除以上目标断言来换 pass。

### 正式 CLI 首次及再次普通增量

修复并通过受影响离线验证后，执行原绝对入口、原 base/ticker/日期，**仅更换全新日志路径**，不得追加 forms/overwrite/rebuild，不预删、播种或手工改写调用方仓储：

```bash
/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli \
  --base /Users/leo/workspace/portfolio-manager-v2/workspace \
  --log-file /Users/leo/workspace/dayu-agent-r/workspace/tmp/cninfo-midea-20261018/cli-first-01/dayu.log \
  download --ticker SZ:000333 --start 2025-01-01 --end 2026-10-18

/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli \
  --base /Users/leo/workspace/portfolio-manager-v2/workspace \
  --log-file /Users/leo/workspace/dayu-agent-r/workspace/tmp/cninfo-midea-20261018/cli-repeat-01/dayu.log \
  download --ticker SZ:000333 --start 2025-01-01 --end 2026-10-18
```

- 两次各自保存 invocation、开始/结束时点、pid、实际 exit、stdout/stderr、完整 diagnostics、全新 dayu.log、HEAD/dirty diff、解释器/包导入位置、实际网络响应和字节摘要。以实际进程退出及资源关闭为终点，不能在仍有 runtime/转换子进程运行时宣称完成。若首跑未成功，先分类解决范围内问题或报告外部阻塞，不用 repeat 掩盖首跑失败。
- 入口生效要核对 CLI shebang/实际解释器与导入路径，再以该绝对 CLI 的成功行为证明；editable 记录、测试或 draft PR 不能替代。
- 通过 `dayu.fins.storage` 协议读取首次与再次的 source inventory、exact snapshots、声明原件和 Docling 主文档，核对 COMPLETE、source_provider/source_id、FY 年份/来源、覆盖财期、原件 sha256、descriptor/manifest、实际 Docling 内容与 origin；不得直接读写受管文件绕过仓储。保留本次前后差异，已有合法来源可以 skipped，不要求为了制造 downloaded 而清空或 overwrite。
- 若官方响应保持本次快照，七个选中来源应正常完成（downloaded 或合法 skipped）、两份 FY 分别对应 2025/2024 全文；明确摘要不进入结果身份，failed/rejected/uncertain 为 0，exit 0，终态成功。missing periods 如实按现有规则报告，不以其重造不存在的报告。若来源集合实际变化，逐条与新冻结响应对账，不硬编码七条冒充通过。
- repeat 应复用已完整来源，不改变业务文档及 revision，不重复下载 FY 原件或转换。使用只读 transport/wire 观察记录验证实际 GET；可以参考既有 `utils/observe_601225_cli_http.py` 的观察方法，但该工具硬编码 601225 和独立 base，不能原样用于本任务，也不能改本次命令绕过它的限制。所需窄临时观察脚本仅放 E，不替换 HTTP 响应、不改生产行为。若缺完整观察证据，只能报告复用证据未齐，不能从 skipped/静默日志推断零下载。

## README 责任判断

- 已读 `dayu/fins/README.md` 的 Agent 更新约束及 Downloaders/CN FY 段。实施后应核对并按实际规则更新该段，说明首页明确全文标签与一致性、拒绝诊断的稳定边界；只写已实现事实，不写本任务状态、测试命令或实现文件流水账。
- 已读 `tests/README.md` 的定位和 CN 年度 owner 回归段（约 710 行）。新增官方 fixture 后更新样本/provenance 与回归覆盖说明，去掉不再准确的固定样本数量；测试仍属于原分层。
- 已读根 `README.md` 的 Agent 更新约束。CLI 参数、默认通道、日志路径用法和用户流程未变化，预计无需更新；若最终增加面向用户的新排障操作，再按职责补充。不能为了机械同步写内部机制。
- 不涉及 Engine/Host/config/整体分层装配变更，相应 README 不触发。本 plan 阶段未改任何 README。

## 风险分类、owner/destination 与未覆盖项

下表“fixed in current slice”是计划处置分类，**不是已经修复声明**。

| 风险/未覆盖项 | 分类 | owner / destination / 放行要求 |
| --- | --- | --- |
| 合法“全文”被误拒及各实际入口语义漂移 | fixed in current slice | gpt-6-sol；本 slice 的 owner/真实 Fs 回归与组合审核，完成前不得标修复通过 |
| 原因/来源日志缺失或不安全；本地声明与文本失败混淆 | fixed in current slice | gpt-6-sol；本 slice 的安全诊断与失败 scope 测试；reviewer 核对默认日志可定位性 |
| 当前绝对 CLI、完整下载及 repeat 尚未验证；非 FY 原件本阶段未取 | fixed in current slice | gpt-6-sol / 总控；implementation validation，需正式首跑/重复跑、仓储读回及真实退出证据，不能以离线测试豁免 |
| 官方实时响应/网络风控/Docling 模型或转换环境阻止正式验收 | requiring new issue or explicit user decision | 总控；implementation validation。先按实际原因完成范围内排查，确属外部无法完成时保持验收未通过并报告，不改日期/表单规避 |
| 原始调用缺当次响应和本地 revision，不能唯一归属历史来源 | requiring new issue or explicit user decision | 总控；若要求作“原调用唯一 source ID”额外断言，需补原始快照/另行取舍；当前记录证明边界，保持已确认的当前真实修复验收 |
| 无文字/跨页/其他未证实新布局，及自然会计年度规则推断 | assigned to later work unit | Fins 维护者；实际新来源被拒绝后另立证据驱动任务。本次保持 fail closed，不新增扫描/OCR/法律 fallback，不承诺其识别成功 |

未完成：生产修改、修复后回归/覆盖率、真实 CLI 首跑及 repeat、仓储产物读回、mimo-flash/ds-flash 最终组合独立双审和必要修复复审、README 实际更新、提交/push/draft PR/交付核对。后续全部交总控按既定 gate 推进；本任务不拥有这些执行步骤，也不改 control/goal。
