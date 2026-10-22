# TSM 6-K 普通增量拒绝调查计划

## 状态与判断

- current gate / next entry point：`plan`，待 Dayu 上游总控核对；本文件不是实施放行记录。
- 已确认目标、成功信号和非目标引用 [目标记录](tsm-6k-rejection-20261022.md) 的“目标确认提案 / 授权更新”。本轮用户明确收窄为只产出计划，不执行后续 gate、不派子 Agent。
- 已核对分支 `investigation/tsm-6k-20261022`、HEAD `26ed15b91fc3ee81d5c6cde4dbd0a4fa709d2536`、`pyproject.toml` 包版本 `0.1.5`。开始时仅目标记录为未跟踪文件，保留原样。
- 调查动机成立，修复动机尚未成立：退出 0、拒绝 1、正文含财务相关词或 report_date 为季度末，都不能证明该披露满足既有季度业绩保留规则。也不能仅凭拒绝标签断言拒绝正确。
- 建议一个调查 slice：S1“候选身份—发现集合—分类输入—拒绝与终态对账”。先得到可复核裁决；不预置生产补丁或新增保留政策。

## 已有直接证据与待查边界

只读证据根目录：`/Users/leo/workspace/portfolio-manager-v2/orch/workpapers/dayu-tsm-rejection-20261022/upstream-evidence/`。manifest 的 13 个条目已由总控核验，本轮读取 manifest 和相关内容，另复核原文大小及 SHA256；不修改、不向调用方 base 重放，也不继续访问证据包外的调用方运行目录。

| 事实及来源 | 目前可以支持的结论 | 不能据此认定的事项 |
| --- | --- | --- |
| `invocation.json`：历史公开 CLI，TSM，2025-01-01 至 2026-10-22，无 forms / overwrite / rebuild | 普通增量调用，非强制重抓 | 原调用之前的完整仓储快照、缓存和全部网络输入 |
| `dayu.log`、`stdout`、终态 JSON、退出记录：17 候选、16 skipped、1 rejected、failed / uncertain 均 0；目标行 `6k_filtered / NO_EX99_OR_XBRL` | 历史执行报告了此拒绝；内部 filing 行是 filtered skipped，汇总单列 rejected | 分类器直接输出就是 `NO_EX99_OR_XBRL`；退出 0 意味每份文件都被接受 |
| 终态 `documents` 10 条、`omitted_count=7`；目标在日志后部 | 与当前前十条投影契约吻合；不能把未展示目标直接定性为遗漏缺陷 | 历史目标 artifact / registry 已经通过仓储读回复核 |
| 原文副本 `tsm-monthend6kx20261022.htm`，59847 字节，SHA256 `021c698879a544fc41f2f0064d478480308ef1b0e9e30049299f8210945aa4a2` | 本地原文身份固定；正文是 2026 年 9 月持股、质押、资产、资本拨款、债券和注销事项披露；本地 HTML 无 href | 远端同版、完整附件集合、该字节就是历史分类输入 |
| `sec-links-002.json` 明示未经访问的构造链接及 `cik_from_accession_prefix` | 可作定位线索；accession 为 `0001046179-26-000728` | `1046179` 已经是核实的归档 CIK |
| 包版本 / commit 记录与本地基线一致 | 代码路径分析可以绑定该版本 | 历史进程的实参或网络响应已被捕获 |

本轮仅阅读原文可读内容，未调用分类器复现。历史实际 remote descriptors、各次响应字节、120 行提取结果、分类实参和仓储读回不在现有包中，均标为待查或不可恢复，不用日志推导值冒充捕获。

## 真源路径与语义 owner

以下为基线代码走读结果；实施记录须继续引用具体函数及证据文件，不能把下表当成候选已经跑过的结果。

| 语义 owner / 路径 | 当前行为与调查断言 |
| --- | --- |
| `dayu/fins/downloaders/sec_downloader.py:SecDownloader.resolve_company / fetch_submissions`；`sec_filing_collection.collect_filings_from_table` | ticker map / submissions 提供公司身份和 filing 行，收集器负责表单、日期、accession、主文件归一化。先绑定 TSM、真实 CIK、accession、filing / report date、primaryDocument；不从 accession 前缀定 CIK。 |
| `SecDownloader.list_filing_files` 及其 index helpers | 发现以 primary 为起点；读取 `index.json`，6-K 另读 `-index-headers.html`；加入 instance / taxonomy、EX-99 HTML、TYPE=6-K HTML、主文档同目录相对 HTML 补链，去重排序。它返回“现行规则选择的基础文件集合”，不是全部目录条目。保留完整原索引，与发现结果逐项对账。 |
| `pick_exhibit_files / pick_form_document_files / _parse_index_header_document_entries / _build_file_metadata_map` | 附件可按 SEC TYPE 或文件名识别；元数据合并时 index-headers 的有效 TYPE / DESCRIPTION 覆盖 index.json，`TEXT.GIF` 不作有效 TYPE。不得只检查文件名有没有 ex99。 |
| `extract_same_filing_linked_html_files` | 主文档只补同目录未编码相对 HTML，排除越界、绝对地址、自身等；不是递归全站抓取。保留原始链接及入选/排除依据；本地无 href 不能证明索引无附件。 |
| `sec_6k_rules._collect_6k_candidate_entries` | 当前 primary 始终列为候选，其余只取 HTML；大小写去重并优先非空文档类型。`classify_6k_remote_candidates` 只处理具有实际 descriptor 的候选。 |
| `sec_filing_collection.classify_6k_remote_candidates` | 对每个候选真实 GET 完整字节，再调用 `_extract_head_text(payload, max_lines=120)` 与 `_classify_6k_text`，形成同源 diagnosis；它是下载与规则的协调者，不另定保留政策。 |
| `sec_6k_rules._extract_head_text / _classify_6k_text / _select_best_positive_6k_candidate` | UTF-8 解码；HTML 提取 text_content，过滤空行后取前 120 行；分类器压缩空白，按既有排除判断及各自扫描窗口，再判断强保留信号。强保留/IFRS 扫描前 4000 字符，标题/强排除窗口分别 420/1600，其他 helper 按自身代码执行，不能概括成所有规则都只看 4000 字符。仅 RESULTS_RELEASE / IFRS_RECON 为阳性；多个阳性用类型/文件名优先级选文。 |
| `sec_pipeline.SecPipeline._precheck_6k_filter` | 先按当前 `_has_6k_xbrl_instance`（文件名 `_htm.xml` 后缀）放行；否则逐候选分类，存在阳性即保留，即使没有 EX-99。候选非空、无阳性且无 EX-99 才返回 NO_EX99_OR_XBRL；有 EX-99 则再区分 EXCLUDE_NON_QUARTERLY / NO_MATCH。provider 失败投影为 DOWNLOAD_FAILED。该汇总分类不证明哪个正文规则命中。 |
| `sec_download_filing_workflow.run_download_single_filing_stream`；`sec_download_state._record_rejection / _is_rejected` | 普通增量先查 active 完整性/当前下载版本快跳，再查同版本拒绝注册表。新拒绝先构造 registry，再持久化 artifact，成功后才发 filtered skipped 行；分类下载失败、拒绝原件保存失败走 failed。registry 是否复用由下载契约版本与 overwrite 决定。 |
| `sec_download_persistence.persist_rejected_filing_artifact`；`dayu.fins.storage` maintenance / batching 仓储 | 分类后再次 prefetch 文件，在同一 batch 发布 artifact 与 registry；因此保存副本不能自动等同分类 GET。通过 `FsFilingMaintenanceRepository.get_rejected_filing_artifact / read_rejected_filing_file_bytes / load_download_rejection_registry` 读回，不直接拼仓储路径或修改 JSON。source fingerprint 来自描述符元数据，不是正文 SHA256。 |
| `sec_download_workflow` 确认行；`sec_pipeline._project_sec_document_row / _build_sec_typed_summary` | 确认行产生状态事实；adapter 把 6k_filtered skipped 投影为 typed rejected，计数从完整行同源派生。filter_category、reason_category、正文 classification 是不同字段，不在 CLI 重算或合并。 |
| `download_contract.FinsDownloadResultSummary`；`direct_events.FinsDownloadPublicSummary.from_result_summary`；`dayu/cli/output.py` | 完整 typed summary 为终态真源，公共摘要取原序前 10 行、计数不截断，omitted 精确补足；CLI 机械渲染。`to_download_diagnostics_json_value()` 保留完整失败列表，但其中 summary 仍有界，不能把它误称完整拒绝列表。需在调查 harness 另保存完整 `download_result.document_rows`。 |

既有规则依据为上述代码、`dayu/fins/README.md`“下载完整结果与有界投影”及 SEC 下载章节；文档记载季度业绩强信号、预告与经营更新排除，未承诺全部 6-K 入库。本候选具体命中何分支仍待 S1 输入实证。PDF 候选范围、XBRL 后缀范围、扫描窗口、拒绝缓存或其它发行人的旧问题，只能在与本候选同源证据建立因果关系后成为本任务 finding。

## S1：隔离实证与必要输出

总控核对后，所有调查数据放 `workspace/tmp/tsm-6k-20261022/`，各次运行使用独立子目录。建议只新增一个有类型、中文 docstring 的调查辅助程序 `utils/investigate_tsm_6k_rejection.py`；一次性脚本只能放 `workspace/tmp/`。下文是该程序待实现的最小命令接口，不是声称仓库已有这些命令。本轮不创建程序或运行目录。

### 1. 本地证据与历史对账

程序 `inspect-local` 只读证据包，复核 manifest 及原文，输出 `local/evidence.json` 和通过生产 `_extract_head_text` 重建的 `local/head.txt`、分类输入/结果及规则依据。输入明确标记 `reconstructed_from_saved_artifact`；保存原始文本、规范化文本、长度、相关信号位置与窗口，不另写业务分类器。复核 17 行日志与 10+7 终态、argv flags、失败列表和退出码；不能补造历史 descriptors、附件空列表、仓储状态或历史输入。

### 2. 当前远端可用时，绑定身份和完整发现

使用真实 `SecDownloader(workspace_root=隔离根, client=httpx.AsyncClient(...))`。远端 transport 用 `httpx.AsyncHTTPTransport` 加只读记录；保留真实限流、重试、取消和错误传播，不用裸 requests 绕过 owner。使用当前合法 SEC 身份；缺 `SEC_USER_AGENT` 时记录前提缺失，不能伪造联系身份或读取 live 安装补配置。

先由 `resolve_company("TSM")`、`fetch_submissions(cik)` 定位 accession；若 recent 无目标，只取 submissions 明示且覆盖日期的历史表。保存公司/filing 原始响应；再从已绑定的归档路径获取 index.json、index-headers、primary 和必要附件，并以 complete submission / filing index 交叉核实 accession、主体与文档集合。构造链接的 CIK 不作权威输入；响应为 200 仍须检查确为目标文件，不能把拦截页当原文。

每次响应记录用途（身份/发现/分类/保存/补充核查）、method、URL/重定向、时间、status、ETag/Last-Modified、字节数、SHA256、raw 文件位置；不输出 User-Agent 的联系值或其它配置。相同 URL 的重复 GET 按请求序号分别保留，不能以 URL 覆盖旧响应。补充核查请求与真实 pipeline 请求分开编号。

将完整目录、headers 的 TYPE / DESCRIPTION、主文件链接、实际 descriptors 和实际候选逐项列入 `remote/discovery.json`。核查目录中未入选的附件时，说明其是否属于既有规则承诺；不得因为人工看见一个未承诺格式就直接宣布发现器缺陷。缺必要索引/附件时记录缺项，不能当“没有附件”。

### 3. 真实链路捕获、仓储读回和离线重放

已有可复用例证是 `tests/fins/test_sec_earnings_repair.py:_SecNetwork / _cli`：只替换 HTTP transport 的装配，运行真实 downloader、公开 CLI、分类和 Fs 仓储。本调查采用相同隔离边界，禁止 StubDownloader 或 monkeypatch 文件选择/分类结果。

- harness 调用当前 checkout 的 `dayu.cli.main.main`，内部 argv 为 `download --base <remote/base> --ticker TSM --start 2026-10-22 --end 2026-10-22 --log-file <remote/cli.log>`，无 forms / overwrite / rebuild。只收窄日期以减少不相关下载，仍是普通增量；当天若还有其它候选，真实记录，不伪造只剩目标。
- 所有仓储、缓存、限流、临时目录、日志均显式落在调查根；不使用 `/Users/leo/.local/bin/dayu-cli`，不安装、不初始化或复用调用方 base，不复制其 16 份 active 文档。启动断言导入的 dayu 路径属于当前 checkout，base 是无外部 symlink 的隔离目录；日志与临时文件同样检查归属。
- 在隔离进程对提取/分类调用加透明观察：记录真实传入的 payload hash、max_lines、原始 head 字符串及分类返回值，原样委托生产函数，不改变参数、结果、异常或分支。记录 candidate filename 与调用序号，保存真实 diagnoses、最终 keep/category/selected_name。远端新捕获标记 `captured_current_run`，不能标为历史捕获。
- 按请求序列比较发现 GET、分类 GET、artifact prefetch 的主文件/附件 hash；仅当字节相等时才建立同字节关系。与已知 59847 字节副本比对；不同就分别保存版本并停止宣称同版重放，不通过替换远端响应抹平差异。
- 用真实 maintenance 仓储读回 artifact/registry/字节，用 source 仓储核实目标是否 active；保存 `remote/persistence.json`、完整 typed rows、公共 terminal、stdout/stderr、exit code。按实测 keep 或 reject 分支断言；不预填 NO_MATCH、NO_EX99_OR_XBRL 或拒绝数量。
- 有完整捕获包后，以 `httpx.MockTransport` 严格按 method/URL/调用序列回放保存的 status/headers/body，未知请求立即失败，禁止外网 fallback；真实下载器、规则、仓储和 CLI 仍执行。只回放该次 CLI 的响应序列，独立身份探测/补充核查记录不混入。回放到新的 `replay/base`，比较输入、diagnoses、选择、业务状态、仓储字节和终态，忽略耗时/本次生成时间等运行值。相同请求多版本须按捕获顺序回放。
- 再在该隔离 base 普通增量跑一次：若首轮拒绝且版本一致，应命中 rejection_registry、无目标 Archives 重抓；若首轮接受且完整，应按 active 完整性快跳。第二轮是缓存机制验证，不能用它替代首轮分类。

此运行是“当前单日隔离状态的实证”，不会重现历史 17 候选/16 已完整的初始状态。历史 17/16/1 只按原始日志/终态复核；10 行预算机制可复用既有 owner 测试，不为凑数造 16 份历史文件。若透明观察影响结果，保留失败证据，修正观察器后重跑，不在生产代码加诊断旁路。

### 4. 命令与预期断言

以下命令均在本仓库根目录、计划核对通过后执行；辅助程序实现必须满足上面约束并拒绝已有非空运行输出目录，避免混版。`replay` 自行创建独立 base 并执行两轮普通增量。

```bash
source .venv/bin/activate
git branch --show-current
git rev-parse HEAD
git status --short
tsm_evidence_root=/Users/leo/workspace/portfolio-manager-v2/orch/workpapers/dayu-tsm-rejection-20261022/upstream-evidence
tsm_probe_root="$PWD/workspace/tmp/tsm-6k-20261022"
mkdir -p "$tsm_probe_root"
python -m utils.investigate_tsm_6k_rejection inspect-local --evidence-root "$tsm_evidence_root" --root "$tsm_probe_root"
python -m utils.investigate_tsm_6k_rejection capture --evidence-root "$tsm_evidence_root" --root "$tsm_probe_root"
python -m utils.investigate_tsm_6k_rejection replay --capture-root "$tsm_probe_root/remote" --root "$tsm_probe_root"
```

`inspect-local` 必须无网络，hash 精确匹配，报告直接事实与重建值。`capture` 必须先核实身份；缺身份/网络/文件就留下明确 incomplete 记录，不伪造成功。`replay` 只允许完整捕获包；现有 upstream 包不具备 replay 的索引/响应前提，不能拿合成 index 空集合冒充真实归档。

关键条件断言：无 XBRL 命中、候选已完成分类、无阳性、无 EX-99 时 `_precheck_6k_filter` 才应为 `(False, NO_EX99_OR_XBRL, selected_name)`；任一阳性应接受，不能因没有 EX-99 提前拒绝。拒绝保存成功须 artifact、registry、分类版本和已确认行一致，目标不进入 active，完整 typed row 为 rejected / 6k_filtered，计数互斥守恒；保存或必要下载失败应为 failed。公共行数为 `min(已确认行数, 10)`，omitted 补足，其省略不改变计数，failed / uncertain 为零时退出 0 可以与 rejected 共存。数据缺失时不强行断言该分支实际发生。

复用现有离线 owner 回归，覆盖发现/类型/补链、120 行输入、季度阳性与排除、primary-only 阳性、拒绝保存及失败、typed 计数与公共诊断：

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_earnings_repair.py tests/fins/test_download_failure_diagnostics.py -q --basetemp=workspace/tmp/tsm-6k-20261022/pytest-base -o cache_dir=workspace/tmp/tsm-6k-20261022/pytest-cache
python -m pyright
```

`--basetemp` 会由 pytest 管理，只能给这个专用未使用目录，不能指向调查根/捕获包。保存命令、退出码、被测 HEAD、依赖/配置及失败详情。若条件修复触及 CLI 输出，追加 `python -m pytest tests/cli/test_fins_commands.py -q --basetemp=workspace/tmp/tsm-6k-20261022/pytest-cli-base -o cache_dir=workspace/tmp/tsm-6k-20261022/pytest-cache`。若只新增 utils 调查程序，按 AGENTS 无单测/覆盖率要求，仍须全量 pyright；不把已有基线失败归因于候选。

必要交付为 `docs/gateflow/tsm-6k-rejection-20261022-investigation.md`（S1 后创建）及其可取回证据索引：版本/命令、身份绑定、原索引与选择差集、逐候选真实/重建输入和 hash、规则分支、持久化/终态对账、验证结果、证据等级、未覆盖项和裁决建议。raw、仓储和日志只在指定隔离目录；报告引用保存路径和 SHA256，hash 不能替代可取回文件。

## 有限度裁决与条件修复边界

1. **远端可用、身份和附件完整、同版且规则拒绝一致**：可提出“当前核实的同版归档依既有规则应拒绝，历史记录与此一致”；明确历史分类实参未捕获的剩余限制。由总控复核后交回停止；不为调查结果升级包或制造修复。不得声称完整历史运行已重放。
2. **远端不可用/缺身份/索引或附件不完整/版本不一致**：完成本地副本提取、真源分类重建和日志/代码对账；记录具体失败和未取回对象。最多判断“现有副本在重建输入下是否满足规则；是否已找到反例”，不能证明远端没有其它阳性附件，也不能定性历史误拒绝或历史正确拒绝。交总控作有限证据结论/后续补证裁决，不循环换入口绕过失败，不以合成 fixture 填事实缺口。
3. **同源反例证实既有能力缺陷**：先形成“既有承诺—目标原文/附件—实际输入/分支—错误结果”的因果链和失败回归，标明 owner。只有既有规则应保留却在发现、提取、分类或持久化/投影边界违背承诺，才进入已授权条件修复；先回写具体修复范围供总控核对，不把尚未定位的扫描窗口或附件猜测写成根因。
4. **内容有用但超出现行保留范围**：例如希望月末持股/资本事项也进入 active，单列需求缺口交 portfolio-manager 裁决，不修改全 6-K 政策，不用公司/文件名特例放行。相邻潜在问题无本候选因果证据时仅登记线索，不混入本候选根因。

条件修复必须位于上述 owner 或直接上游输入校验处；禁止 CLI/adapter 下游重分类、fallback、兼容 shim、重算和 fixture 固化错误语义。修复测试保存有来源的必要真实样本并断言 owner 契约，另覆同类正反例及此次链路，不能只断言文件名命中。受影响生产文件覆盖率目标 >=80%，使用 `python -m pytest <已确定受影响测试> --cov=<实际 owner 模块> --cov-report=term-missing` 检查，覆盖率数据写到隔离目录；全量 pyright 必须通过且不扩散旧错。

若生产缺陷修复成立，包版本由 `pyproject.toml` 管理，拟 `0.1.5 -> 0.1.6`，实施前核对无并发版本变化；不为本计划/纯证据输出升级。下载发现、分类或认证语义改变时，还须评估并更新 `SEC_PIPELINE_DOWNLOAD_VERSION`（基线 `sec_pipeline_download_v1.3.0`），验证旧拒绝项不会被同版本缓存挡住、active 重新认证及普通增量保持正确；不靠用户 overwrite 才生效。仅诊断展示修复不机械刷新下载版本。不安装、不 sync live；后续提交/push/PR、审核及版本交付由总控按目标记录另行派发，本轮均不执行。

## README、计划审核与风险去向

本轮只有计划文档，未改变已实现能力/用户流程，不触发 README 修改。已阅读根 README 与 `dayu/fins/README.md` 的 Agent 更新约束、`tests/README.md` 的职责说明。条件修复若触及 Fins，检查 Fins README 的稳定契约/机制是否实际变化；新增回归检查 tests README 是否需说明新增维护约定；用户入口/诊断/排障变化才按根 README 用户手册边界更新。若触及分层/装配，另读 `dayu/README.md` 并检查更新；本计划不改 Host / Engine / config，不机械同步其 README。

本调查保留既有契约、架构、schema 和状态机，**无需独立 planreview**，由总控做简单计划核对。若实证修复需改变保留承诺、公共错误/状态、持久化 schema、跨层装配或其它重大决策，先明确新决策和目标边界，按适用条件进入 planreview；新增需求另获裁决，不让调查计划预批这些变化。

| 风险/未覆盖项 | 分类 | owner | destination / 处理 |
| --- | --- | --- | --- |
| 历史分类实参和初始 base 不在包内；保存副本来自后续下载，无法承诺恢复 | requiring new issue or explicit user decision | Dayu 总控 | S1 报告列证据上限；总控裁定是否接受有限结论或请求额外只读证据；不访问原 base 补抓 |
| 真实归档 CIK、附件完整性、同版绑定仍待查，远端可能不可用 | requiring new issue or explicit user decision | S1 实施者取证；Dayu 总控裁决 | 按远端可用/不可用两路收口，缺证不能升级成历史正确或误拒绝结论 |
| 当前隔离单日运行与历史 17 候选初始状态不同 | requiring new issue or explicit user decision | Dayu 总控 | 验证单候选规则/仓储链路和既有投影机制，历史计数仅对原记录；不伪称端到端历史复现 |
| 潜在既有缺陷尚未成立 | requiring new issue or explicit user decision | 对应语义 owner；Dayu 总控 | S1 同源证据成立后核对最小修复/版本/验证范围；范围内条件修复按已确认目标推进 |
| 月末披露保留或全部 6-K 入库的新增需求 | requiring new issue or explicit user decision | portfolio-manager | 独立需求缺口待裁决，不纳入修复 |
| 与本候选无因果证据的附件格式、窗口、XBRL、缓存等相邻线索 | assigned to later work unit | Dayu 总控 | S1 报告的非根因线索区；仅保留证据和建议去向，不默认创建外部 issue 或扩范围 |

本轮完成：代码走读、只读证据核对及本计划。未做联网复现、测试运行、pyright、生产改动、修复、版本升级、提交、push 或安装。无阻塞本计划交付的输入缺口；下一入口仍为总控核对本计划，S1 尚未实施。
