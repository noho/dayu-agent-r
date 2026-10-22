# TSM 6-K 拒绝调查 S1

## 裁决建议

**候选 `fil_0001046179-26-000728` 的当前同版归档按既有规则应拒绝，未发现误拒绝、附件漏选或拒绝原件持久化错误。公开终态计数与当前持久化一致。另证实一处附带数量 warning 的语义误计，应交总控核对最小修复范围。**

正文是 2026 年 9 月月末持股、质押、资产交易、资本拨款、无担保债券及股份注销六类事项披露，不是季度业绩公告。真实发现只产生一个主文档；真实分类为 `NO_MATCH`，预筛为 `(False, NO_EX99_OR_XBRL, tsm-monthend6kx20261022.htm)`。因此不能把拒绝标签解释成“正文命中季度排除规则”，也不能把 `report_date=2026-09-30` 当成季度业绩强信号。

历史分类 GET 的实参不能恢复。本轮证明的是当前远端主文件、历史保存副本、当前实际分类 GET 及当前保存 GET 字节相同；历史日志与该判定一致。**没有重放历史全窗或恢复历史分类捕获。**

## 执行边界与证据入口

- 分支 `investigation/tsm-6k-20261022`；HEAD `26ed15b91fc3ee81d5c6cde4dbd0a4fa709d2536`；包 `0.1.5`；Python `3.11.15`，本仓库 `.venv`。
- 已阅读 `AGENTS.md`、授权记录及 Plan 总控核对；按 binding 收敛只实施调查 S1。未修改生产代码、测试、调用方原 base、只读证据包；未升级包、安装、stage/commit/push、发外部消息或派子 Agent。
- 只读上游：`/Users/leo/workspace/portfolio-manager-v2/orch/workpapers/dayu-tsm-rejection-20261022/upstream-evidence/`。开始及交付前均核验 manifest 13 条大小与 SHA256 一致。
- 隔离证据根：`/Users/leo/workspace/dayu-agent-r/workspace/tmp/tsm-6k-20261022/`，下文记作 **E**；具体执行数据在 `E/s1/`。
- [可取回证据导航](../../workspace/tmp/tsm-6k-20261022/S1-INDEX.md)、[精确命令和退出记录](../../workspace/tmp/tsm-6k-20261022/S1-COMMANDS.md)、[逐文件 SHA256 索引](../../workspace/tmp/tsm-6k-20261022/s1-evidence-index.json)。代码路径、解释器、依赖见 `E/s1/version.json`。
- 一次性有类型中文 docstring 脚本仅位于 `workspace/tmp/tsm_6k_s1.py`；没有新增 utils 工具或命令框架。已用 `zsh -ic` 加载既有 SEC 身份，不输出 UA 联系值，不改 `.zshrc`。

## 身份、远端版本与完整附件集合

真实 `SecDownloader.resolve_company("TSM")` 返回 `TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD`、CIK `1046179` / `0001046179`；真实 submissions 的 recent 表定位目标：form `6-K`，filing date `2026-10-22`，report date `2026-09-30`，primary `tsm-monthend6kx20261022.htm`。CIK 来自身份查询，不来自 accession 前缀推断。见 `E/s1/remote/identity.json` 和 `remote/requests/0001–0002`。

归档根 URL 为 `https://www.sec.gov/Archives/edgar/data/1046179/000104617926000728/`。补充核查与 pipeline 分开编号，全部实际 HTTP 200，无换入口绕过或合成索引。

| 对象 | 完整捕获 SHA256 | 字节数 | E 下原件 |
| --- | --- | ---: | --- |
| index.json | `414beca8b7d1bc2f158ee14dd05c667e75fec64ae61bc12092cd625d50e5127e` | 576 | `s1/supplement/requests/0001.body` |
| index-headers | `a61595ca5266c4fb0651902585fdb63600d8cb1e7882e82a5b04f86045b89e5d` | 2586 | `s1/supplement/requests/0002.body` |
| primary | `021c698879a544fc41f2f0064d478480308ef1b0e9e30049299f8210945aa4a2` | 59847 | `s1/supplement/primary.htm` |
| 完整 submission | `c2c53da625265fe30fdb676c8168611d0e2d9c27fed1861f955ebdac39d6d7b7` | 60876 | `s1/supplement/complete-submission.txt` |

完整目录只有四项：`-index-headers.html`、`-index.html`、`.txt` 和 primary。前三项为归档索引/聚合容器，不是遗漏的业务附件。index.json 对条目写 `text.gif`，真实 headers 解析只得到 primary 的 `TYPE=6-K` / `DESCRIPTION=6-K`。完整 submission 明示 `PUBLIC DOCUMENT COUNT: 1`，唯一 DOCUMENT 的 filename/type/主体 CIK/accession/日期均匹配。主文件没有 href，生产补链结果为空。真实 downloader 描述符及候选也只有这个 primary；没有 EX-99、XBRL、其它 HTML、PDF 或图片附件可漏选。见 `E/s1/supplement/discovery.json`、`descriptors.json`。

index 中 primary size 为 59732；当前 primary GET 为 59847。没有用索引 size 代替实际字节：完整 submission 提取出的 DOCUMENT 块是 59731 字节（不含尾换行）；去除 primary 中一个外加 script 标签及边缘空白后与该块完全相等。两份原件均保留，比较见 `E/s1/final-verification.json`。该核查只解释字节差异，分类始终使用原始 GET 字节，没有先删 script 或重写正文。

真实 CLI 的发现 primary GET、分类 GET、拒绝 artifact 预取 GET 分别为 `E/s1/pipeline-clean-requests/0008`、`0009`、`0010`，各自保存请求元数据及响应原件，三者均为 59847 字节、SHA256 `021c…a4a2`，与上游副本完全相同。保存了每次 GET，没有按 URL 覆盖。每个 `.json` 含用途、方法、URL、时间、状态、响应头（包括 ETag/Last-Modified 若有）、字节数及 hash；`.body` 是 httpx 解压后的应用输入字节。没有将 wire 压缩长度冒作分类输入长度。

## 生产规则输入与拒绝因果链

语义 owner 是 `dayu/fins/pipelines/sec_6k_rules.py`；下载协调为 `sec_filing_collection.classify_6k_remote_candidates`，汇总决策为 `SecPipeline._precheck_6k_filter`。`dayu/fins/README.md` 的既有承诺是季度业绩强信号，未承诺全部 6-K 入 active。本轮没有扩大保留政策。

真实 CLI 在新 base 执行单日普通增量，无 forms/overwrite/rebuild。通过 transport 装配及透明函数观察，原样委托生产 downloader、候选选择、提取、分类、仓储和 CLI；未 stub 选择或分类。

| 字段 | 实测 |
| --- | --- |
| 输入标记 | 当前网络运行 `captured_current_run`；副本离线调用另标 `reconstructed_from_saved_artifact` |
| 实际 payload | 59847 字节；SHA256 `021c698879a544fc41f2f0064d478480308ef1b0e9e30049299f8210945aa4a2` |
| `max_lines` | 120 |
| head | 5 个非空行，4343 字符；SHA256 `ef3856f3965c61c06ad5738f49dc5bc39648449c8323ae564b790ba946a1bdcf` |
| 空白规范化后 | 4296 字符；SHA256 `f26fe8e0b72304c83848633a361a55e3f84effd93d7aa369a48430e46faac879` |
| 唯一 diagnosis | primary=true，filename_priority=3，classification=`NO_MATCH` |
| 预筛输入集合 | has_ex99=false，has_xbrl=false；存在且完成分类的唯一候选 |
| 原函数三元组 | `[false, "NO_EX99_OR_XBRL", "tsm-monthend6kx20261022.htm"]` |

输入原字节、head 和规范化文本可取自 `E/s1/capture-clean/inputs/0001.*`；实参、diagnoses 与三元组见 `observation.json`。副本重建的对应 hash/长度/分类逐项相等，见 `E/s1/local/evidence.json` 与 `final-verification.json`；这只建立重建与当前捕获相等，不把它升级为历史捕获。

生产提取保留了 DOCUMENT 包装的 TYPE、SEQUENCE、FILENAME、DESCRIPTION；HTML 正文集中在第五行，所以本文件未被 120 行上限截掉。分类器压缩空白，标题排除看前 420 字符、强排除看前 1600 字符、强保留/IFRS 看前 4000 字符；其余 helper 各用自身窗口，不能概括成统一 4000 字符。保存了所有这些正则在完整输入上的位置与窗口，本候选没有强保留/IFRS 命中，完整规范化输入中也没有被截在窗口外的相关正则命中。最终 `NO_MATCH` 表示此前排除分支及阳性分支均未命中；这里没有“月末持股专用排除规则”被触发。

同源因果链为：完整归档仅有月末事项主文件 → 真实发现唯一候选且无 EX-99/XBRL → 真实 GET / 120 行提取 → 真源分类 `NO_MATCH` → 无阳性候选 → `_precheck_6k_filter` 在“无 EX-99”汇总分支返回拒绝。若 primary 有阳性强信号，即使无 EX-99 也会保留；本案不能归因为缺 EX-99 的提前拒绝、扫描窗口或未发现附件。

## 持久化、公开终态与历史对账

所有当前仓储读取均经 `FsFilingMaintenanceRepository` / `FsSourceDocumentRepository`，没有拼目录读取 meta。`E/s1/capture-clean/persistence.json` 及 `readback/` 显示：

- active document IDs 为空；拒绝 artifact 及 registry 均存在且绑定该 accession、primary 和公司。
- registry reason=`6k_filtered`、category=`NO_EX99_OR_XBRL`、download_version=`sec_pipeline_download_v1.3.0`；artifact rejection/category/classification_version 与其一致。
- 读回原件 59847 字节、SHA256 `021c…a4a2`，与当前分类/预取字节相同。
- source_fingerprint 为 `95e790461a39b308bb6b4c1d1463d06f84ffe2262051772427a2d31e44bff739`，来自生产描述符，不是正文 SHA256。新 base 的真实 CLI 按生产参数未请求文件 HEAD；补充核查的 HEAD 独立保存，没有灌入真实 pipeline 描述符。

当前完整 typed row 是 `rejected / 6k_filtered`；公开 summary 为 discovered=1、rejected=1，downloaded/skipped/failed/uncertain 均为 0，omitted=0，failed_documents=[]，terminal_disposition=succeeded，实际 CLI 退出 0，stderr 为空。见 `typed-rows.json`、`terminal.json`、`stdout`、`exit-code.txt`。拒绝是正常筛选结果，不能把退出 0 解释为该文档进入 active。底层工作流的 `status=skipped` / 进度“跳过下载”是跳过 active 收录动作，公开终态从同一已确认行投影为 rejected；“跳过落盘”的旧日志用语也不能证明系统没有保存拒绝原件。

历史证据复核得到 17 条完成行：16 条 `already_downloaded_complete`，目标 1 条 `6k_filtered / NO_EX99_OR_XBRL`。历史公开终态保留原序前 10 条（均为已有完整下载的跳过），omitted=7，目标位于省略部分；计数仍是 17/0/16/1/0/0，失败列表为空，退出 0。raw diagnostics 与 parsed JSON 完全一致，前十条 ID 与日志顺序一致；符合 public summary 前十行预算，未找到目标漏计或状态重分类错误。见 `E/s1/historical-verification.json`。

历史 registry/meta 本轮未读取，不声称已核验历史发布原子性；上游副本存在及历史成功确认行只能支持代码路径与保存结果一致，不能替代历史仓储快照。

## 严格离线重放与缓存

使用 `httpx.MockTransport`，按 method/URL/调用顺序重放真实 CLI 的 10 次响应；未知请求立即失败，重放对象不持有网络 transport。身份/补充核查响应未混入此序列。解压后的响应重放移除 wire Content-Encoding/Content-Length，保留应用字节和状态，其它业务输入未改。

`E/s1/replay-clean/` 使用新 base：10/10 响应消费完毕，输入 hash、max_lines、分类、diagnoses、预筛三元组、完整 typed rows、公开终态均与网络捕获相等；registry、artifact 业务字段及原件字节相等，仅忽略本次生成时间/耗时。实际 CLI 退出 0。

再在该 base 普通增量，`E/s1/cache-clean/registry-decisions.json` 捕获目标 `is_rejected=true`、overwrite=false。只消费 ticker map / 当前 submissions 两次请求，历史 submissions/browse 已由第一轮生产缓存；无目标 Archives GET，无提取/分类/预筛调用，artifact 完整对象未变化。工作流在候选汇总前过滤已拒绝文档，因此这一轮 discovered=0、其余计数=0、退出 0；没有伪造“本轮又拒绝 1”或“active 已完整快跳”。全部断言见 `E/s1/replay-verification.json`。

这是当前单日隔离初态的重放，不是历史 17/16/1 初态复现，没有复制调用方 16 份 active。

## 已证实的附带诊断缺陷与最小建议（待总控核对）

**D1，P2：数量 warning 把被拒绝的 6-K 计入“有效落盘数”。** 不影响本候选分类/拒绝、持久化或公开终态计数；历史原日志因数量超过阈值未触发季报数量 warning，不能用此缺陷解释历史拒绝。

既有承诺：`sec_download_diagnostics.warn_insufficient_filings` 文档和消息声称统计有效下载/已存在文档数量。当前真实单日运行只有该拒绝候选，active=0，typed row=rejected，却输出“季报（10-Q/6-K）有效落盘数 1……另有 1 份 6-K 被分类过滤”。

严格离线补证 `E/s1/diagnostic-proof-configured/quantity-warning-observation.json` 透明记录原函数全部实参与返回值：唯一 raw row 的 `status=skipped`，但 `skip_reason=reason_code=6k_filtered`，registry 同时登记拒绝。原函数在 `dayu/fins/pipelines/sec_download_diagnostics.py:94` 按 form 与 `status in {downloaded, skipped}` 累加，未消费确认 disposition，因此得到 1。仓储读回 active=[]，完整 typed terminal rejected=1，形成直接同源反例。其 CLI 和公开终态与网络捕获完全相等，见 `finding-verification.json`。

owner：有效收录状态应由已有确认结果/disposition 真源负责；数量 warning 是消费者，不能独自从底层 status 反推。最小建议：把数量诊断接到同一确认 disposition 投影之后，消费已有 typed rows（或抽出当前唯一投影供 summary 与 diagnostics 共用），仅统计 downloaded 与真正的 skipped；不要在 CLI、warning 文本、测试 fixture 中补一个 `6k_filtered` 特例重算。保留现行季度筛选和拒绝版本。修复验证应使用本次同源行断言有效数 0，并包含真正已完整快跳的正例及 warning/public summary 一致性；当前 S1 不改生产代码或测试，不预定版本变化。

“跳过落盘”措辞有 active / rejected artifact 的歧义，也应在总控核对诊断范围时一并考虑；本轮仅记录，未据此声称原件丢失。

## 验证、失败尝试与交接

- 本轮补充 `test_sec_downloader.py`、`test_sec_earnings_repair.py`、`test_download_failure_diagnostics.py`：129 passed，退出 0，62.38 秒；只有 3 条现存 edgartools 弃用提示。
- 复用总控同 HEAD 的 43 项 6-K 基线回归与全量 pyright 0 错。生产和测试未改，不以这些测试替代远端实证，也不声称它们覆盖 D1。
- 一次性脚本单独 pyright：专用配置取消 workspace exclude，verbose 确认 Found 1 source file；0 errors / warnings / informations，退出 0。最初直接指定文件被 exclude 排除的“0 错”不计验证；实际检查发现的脚本类型问题已修正。
- 初轮探针出现跨循环连接收尾、仓储字段误用及缓存断言过窄；另有一次重放过早启动、一次离线补证未加载 UA。全部失败记录和脚本快照保留，详见 `S1-COMMANDS.md`。权威结果仅使用 `capture-clean` / `replay-clean` / `cache-clean` 及已加载身份的 `diagnostic-proof-configured`；均实际退出 0。没有把探针错误归因于生产。
- README 触发核对：本轮未改生产能力、入口、测试或用户流程，只有调查报告/隔离脚本，不触发 README 更新；无包升级。

| 风险/未完项 | 分类 | owner | destination |
| --- | --- | --- | --- |
| 历史实际分类 GET 与完整初始 base 不可恢复 | requiring new issue or explicit user decision | Dayu 总控 | 接受“当前同版规则拒绝、历史记录一致”的限定结论，或另行请求额外只读历史证据；不冒充历史捕获 |
| D1 数量诊断语义误计，尚未修复 | requiring new issue or explicit user decision | 确认 disposition 真源 / SEC 数量诊断 owner；Dayu 总控裁决 | 核对上述最小修复边界后派后续 work unit；当前交回，不自行补丁 |
| “跳过落盘”未明确 active 与拒绝 artifact | assigned to later work unit | SEC filing 工作流诊断 owner | 随总控诊断范围核对；不改变收录政策 |
| 月末持股/资本事项是否也应纳入 active | requiring new issue or explicit user decision | portfolio-manager | 独立政策需求；本轮不扩大 6-K 保留范围 |
| 未来远端内容、规则或版本变化 | assigned to later work unit | 对应 downloader / 分类 owner | 本报告只对保留的当前响应和基线版本负责；完整响应及索引可复核 |

S1 证据已落盘可取回。下一入口为总控审查本报告，裁决正确拒绝的收口及 D1 条件修复范围；没有提交、发布或 live 同步动作等待本实施者继续执行。
