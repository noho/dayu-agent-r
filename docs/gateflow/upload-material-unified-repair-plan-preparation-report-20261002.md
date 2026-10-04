RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-4dd6e50a

# upload_material 统一计划准备报告

## 1. 交付与真实状态

任务`upload-material-unified-plan-sol-20261002-01`，唯一计划作者为本轮Codex，未派发子Agent。`gpt-6-sol`为任务指定路由；运行时没有暴露实际canonical model，故记unknown，不从canary或当前provider配置补猜。工具读取本轮指定canary原文件，其原字节另存`evidence/canary.raw`；未读取旧轮canary冒本轮证明。

交付：

- 正式候选计划：`docs/gateflow/upload-material-unified-repair-plan-20261002.md`。
- 本准备报告。
- 独占证据：`workspace/tmp/upload-material-unified-plan-sol-20261002-01/`。内部定位均相对唯一workspace，外部路径仅作为实际指令/运行身份描述。

**整体generation-ready=false，plan gate未通过。** S1/S2已写明可生成候选设计；S3仍缺macOS必要依赖实装、受信taxonomy/真实positive、强制隔离与同次采集证据，不能冻结生产pin、配置字段和OS启动接口。未把XBRL删出WU，未把已批准标签改为residual，未虚构review/implementation/PR/closeout pass。

首末branch均`codex/upload-material-oracle`；HEAD均`619d092ab4278645203c7ebe08515f7697d92b71`；本地main均`fac32ecbff9bfe792b63ee9667c8697826b631f4`。805个原有tracked源码、依赖/lock、测试代码和README的首末SHA无变化；Git产品diff为空。核验不打开私有财报/凭据，不把整个工作树称clean。

## 2. 读取依据及绑定范围

已读AGENTS、Gateflow SKILL、任务指定control、handoff第4–6节与最新排程、G1/G2/G3/G4/G5及XBRL P0的20261001 preparation、正式UM adjudication及真实goal/后续裁决。旧preparation pin `3a836...`不是accepted API，也未拿已闭环F2–F7/#198的旧状态重复实施。旧记忆只帮助定位handoff与核证边界；本轮用户授权和当前源码/正式裁决优先，不使用旧HEAD或旧私有fixture内容证明当前行为。

绑定control SHA为`cc5e5f761802fa00758a8af8730cad830bce66972613ab12c6a191227e66a357`，首末一致。收口期间其它owner新增`upload-material-unified-repair-goal-amendment-20261002.md`，SHA为`17c0d804d459091a5c5909f42511a75e7ab2e7a9250072b9bc8e5f6e15adc290`，明确记录用户选择macOS先验收、Linux/Windows延期。计划已按这份正式后续修订重绑S3，未重新要求用户确认。Linux/Windows无环境不再列本WU blocker；其部署/依赖/强制边界/继承归后续平台项，owner为平台部署/依赖及Documentsruntime，总控排程。其它原XBRL成功信号不变。

`source-index.json`共142项，记录现读SHA、大小、HEAD blob核对和独立exact byte副本。source位置与必要hash见计划§3，AST行号另在`symbols.json`。原control与新amendment未被HEAD追踪，`git show HEAD:<path>`的128仅说明其不在该commit；binding使用用户指定工作树字节，不把它们说成HEAD文件。公开资料另有URL/UTC/HTTP/SHA索引，安装源码和METADATA独立保全。

## 3. 全范围映射与三片理由

计划§4逐行列18标签及正式来源、slice和成功断言；artifact QA核18项恰各一次，没有漏项、多项或重复：

| slice | 完整行为／标签 | 真实完成边界 |
| --- | --- | --- |
| S1 | 准入→稳定身份/显式主角色→所有原件转换/manifest→内容失败同源。O05F01 O06F01 O07F01 O07F02 O09F01 O10F01 O16F01 O17F01 O25F01 O21F01 O22F01。 | V1–V6，包括A→B→B的v1/v2/v2、默认读取/processor主源B、真实空字节/损坏内容typed失败。 |
| S2 | 同版状态准入→独立公司→条件材料提交/终态→并发再裁决。O12F01 O13F01 O14F01 O15F01 O18F01 O33F01。 | V7–V14，包括八格amended、tombstone无变化、active-only双摘要及真正双CLI旧准入竞争。 |
| S3 | macOS受控部署→真实XBRL instance转换→实际CLI/仓储manifest提交。O20F02。 | P0证据先冻结技术契约，再真实成功/失败/取消验收；当前blocked，不能普通XML或标题Docling成功替代。 |

G1/G2/G4合S1、G3/G5合S2，不按六个旧proposal机械拆六slice，也不逐finding开gate。第三方受控转换有独立资源/证据链，合到状态修复同次pass会失去可核行为增量；平台、taxonomy、探针又不能拆成产品片。因此只三slice，各值得完整implementation/review pass。PR review仅在全部slice和aggregate之后。

完整upload_material CLI CI及oracle/scenario正式登记明确归WU后阶段，不列本WU slice/closeout条件；O33真实双CLI及XBRL真实instance依然本WU验收。22个独立residual不自动纳入。

## 4. 当前源码与上游直接证据

身份/admission、Docling、SEC/CN真实caller、资产命名helper、usage/failure、仓储exact inspector/guard、公司merge、manifest/read、CLI/tool/Service装配均已重新按真实HEAD读取。计划写明每个事实owner、拟API/schema、调用图、guard时序、异常/取消、类型闭集、文件白名单、精确断言和README职责。

- 现material handoff仅request/selection/asset_plan，identity仍市场晚期重算；D的material指纹无主角色、提前skip，material内容label丢失。动机由代码同源确认，不由storage_io猜存储故障。
- writer锁从begin_batch持到终态；source/company漂移测试必须B先commit、A后begin/register，不构造“A持writer让B先commit”的死锁探针。真正release异常可能发生在COMMITTED之后；计划不从异常承诺零durable发布，更不自动改skip。
- 现材料original资产`source`为仓储标记`original`；与provenance的`user_upload`不同，计划typed descriptor没有混同。
- 已有full-basename→Docling helper、版本owner、active-only保存和canonical file label优先复用；删除公开internal ID不删除持久内部字段。公司事务仍独立。
- manifest原领域模型不能反向import仓储eager导出导致repo/domain新环；计划把strict字段读取及唯一projection留在仓储新source_manifest_contract，向模型传required typed参数；Docling成员校验复用现声明parser，不让模型重解析files。精确caller迁移/新owner测试已纳S1/S2白名单。

本机元数据：Darwin arm64/macOS26.6.2、主树Python3.11.15；docling/slim2.127.0、core2.96.0；arelle-release未安装。只读metadata，没有Docling import或转换实测。pytest9.0.3/cov7.1.0/pyright1.1.409仅版本，不是验证通过。

安装XBRL backend的taxonomy输入为directory、可含顶层catalog zip，临时copytree；local/remote默认关闭、workOffline不是OS强制边界。生产DocumentStream没有sibling sidecar通道。`sandbox-exec`及Docker二进制存在也不证明可用，未运行daemon/沙箱探针。

安装BasePipeline在convert返回前finally unload；Docling backend随后关闭model；官方Arelle2.45.3的close清空模型。typed memberQname可为None而backend访问localName；本轮公开官方#4437 GET为open。它是源码/官方状态证据，不是有效instance本轮执行失败的实证。

公开只读GET六次HTTP200：Arelle2.45.3的ModelXbrl/ModelInstanceObject/ModelDocument/FileSource官方源码、PyPI版本JSON、Docling#4437。PyPI声明`jaconv>=0,<1`，没有据旧故事选生产pin；未resolve/wheel实装、未改锁、未外发issue。仅source/METADATA不能冒三平台或macOS可部署成功。

## 5. 实际命令、非零与恢复

具体argv/cwd/exit及独立stdout/stderr见`preflight-commands.json`和`final-commands.json`，源读/hash见`source-index.json`，官方GET见`official-source-index.json`。没有把未来计划里的命令混进本轮执行记录。

| 实际动作／命令 | 结果／非零处理 |
| --- | --- |
| 工具读取指定`.../sub-agents.6JQuXr/canary.txt` | exact内容`gpt-6-sol-4dd6e50a`，原字节保全，不修改。 |
| `git branch --show-current`、`git rev-parse HEAD`、`git rev-parse main`，首末各一轮 | 全0，指定branch/HEAD/base均一致。 |
| `git status --porcelain=v1`、`git diff --name-only`，首末；开始`git diff --stat`、`git log -5 --oneline` | 全0；原有/外部docs dirty如实区分，产品无改。未查询远端/PR live，不声称远端同步或PR状态本轮核过。 |
| `git diff --check main...HEAD`，首末 | 均2，唯一既有Raw日志EOF空行；没有恢复为0。计划登记最终PR可逆bytes/SHA/base64封装及引用同步，不trim、不本轮修改、不新slice。 |
| `git diff --no-index --check /dev/null <各新增计划artifact>` | 各1且双流为空；no-index差异1是新文件与/dev/null有内容差异，不是空白错误。独立逐行QA无trailing whitespace，不用`|| true`伪0。 |
| `source .venv/bin/activate && python workspace/tmp/upload-material-unified-plan-sol-20261002-01/capture-final-evidence.py` | 0；子命令真实非零另留记录，805个既有代码/依赖/README哈希不变、18标签唯一、3slice。该脚本仅交付核证，未启动产品。 |
| `git show HEAD:<control/amendment>` | 各128，因为两个用户工作树文档未追踪；读取工作树exact bytes并留SHA/snapshot恢复定位，未将128误记源码错误/pass。 |
| 源码locator涉及不存在路径或无match | `docling_conversion.py`、DocumentsREADME、runtime/subprocess、storage/_fs_company_meta等ENOENT；某些`rg ... | head`最终exit0而stderr仍有ENOENT。后续沿实际`docling_runtime.py`、`interruptible_process.py`、`company_meta_contract.py`及infra核源。新定位中`domain/source_provenance.py`、`storage/filing_upload_contract.py`也不存在；直接`rg`资产plan无match观察exit1，实际type/常量定位恢复为repository_protocols与storage/__init__，最终捕获rg exit0。末轮误查`dayu/fins/direct_types.py`的rg exit2，纠正为全Fins/contracts真实定义搜索exit0：唯一UploadFileEventPayload在D:90，pipeline result在R:1712，direct_events无该类型、不需为它开新模块。没有用管道0掩盖定位失败或虚构产品运行结论。 |
| 激活venv后Python metadata/source只读探测、哈希/AST/index生成 | 0；结果及exact副本独立存，不安装、不运行converter。 |
| 官方资料Python只读HTTP GET | 六个200；URL/UTC/SHA/原响应保存，未有对外写。 |
| 文档编号补丁 | 一次apply_patch因只给行前缀、未匹配整行而verification failed，未写任何产品；随后对本作者计划逐个assert存在再替换编号的Python命令exit0，最终artifact QA重核。该失败不冒充shell exit或产品失败。 |

未出现自动审批拒绝；未请求或绕过沙箱升级。未运行pytest、coverage、pyright、CLI、Docling/Arelle转换、P0-A/B/C、真实双CLI、真实instance、fresh安装；没有这些项目的pass。只写计划与证据，不触发代码修改后的产品测试义务；计划已列未来accepted实施的激活venv、受影响测试、逐文件≥80%、全量pyright与README检查。

## 6. 外部文档变动与写入归属

本作者工具写入仅两个允许artifact及独占tmp。开始工作树已有M handoff与未追踪control；结束还看到其它owner修改/新增总控资料，不能说“全部工作树变更均由本任务产生”。

`external-document-observation.json`以首末SHA列三个旧docs漂移：PR197 adjudication、issue198 sequence、repair-scope-and-ci-closeout。其新增提示指向统一control/新排程，本作者没有写这些文件。handoff首末SHA相同；control首末SHA相同。外部新增`docs/gateflow/evidence/upload-material-unified-repair-20261002/`和上述goal amendment也非本作者写入。

source-index第一次读取所留142项在最终核验无read→end字节漂移；产品805项首末无变更。独占tmp被Git忽略，仍实际存在可读，不将未显示在status误记“无证据”。本轮没有commit/push/branch/worktree/clone/detached/merge/PR/registry操作。

## 7. Blockers与风险归属

| 项目 | 具体缺口／分类／owner与destination |
| --- | --- |
| B-X1 | macOS fresh标准resolve/实装/pipcheck/lock回读未做，Arelle未安装；needs-more-evidence，依赖/平台owner→S3 plan/fix，冻结实际pin及common/macOSlock。Linux/Windows已授权延期，不阻塞此WU。 |
| B-X2 | 受信taxonomy来源/许可/完整闭包及合法真实positive未取得；显式配置位置/typed字段/copy复验owner未冻结；requiring resource/owner evidence，管理员归档+Documentsruntime+Fins→S3 plan/fix。 |
| B-X3 | macOS可执行强制文件/网络策略、子进程继承与trace未核；requiring implementation-strategy evidence，中立runtime/平台owner→S3 plan/fix。二进制存在不等验收。 |
| B-X4 | unload前同run普通值快照/恢复、逐元素失败URI与zipentry关系没有原型证据；needs-more-evidence，P0证据owner→S3 plan/fix。重放或聚合日志不能升级observed。 |
| B-X5 | typed维度上游分支/公开#4437 open；tracked by existing issue，Docling上游及真实positive/支持声明owner→S3。不能本地修财务抽取内容、自行退支持或伪success。 |
| S1/S2 | 候选API不是已实现事实；未来同版planreview与owner contract实测尚未做。Fins/storage→accepted后实施/复审；新合法producer若不能提供required事实需精确caller归owner阻塞，不用默认值。 |
| COMMITTED后release certainty | 本WUfail-closed与回归覆盖；全局/download indeterminate属既有后续storage residual，不能借O33扩scope。 |
| Raw EOF卫生 | 最终PR收口证据owner→全部slices之后；可逆原bytes/SHA封装，当前未修且fullPRcheck仍2。 |
| Linux/Windows XBRL | 正式平台修订授权后续；平台部署/依赖和Documentsruntime→总控排程；未覆盖，不能从macOS外推。 |
| 完整CLI CI／正式registry | WU后独立阶段；CI/oracle owner→既有closeout文档/cli_ci，未启动，不是本WU验收缺口。 |

计划没有把未知owner通过fallback藏起来：S3未冻结的字段/接口/资源明确阻塞整份generation-ready；S1/S2接口统一source of truth，市场/CLI/LLM仅投影，事实不能各自重算。README的实际职责已读，未来只在变更属于其读者范围时改。本轮README无改。

## 8. 停止与下一入口

本轮交付完成并停止。当前gate仍为plan，**没有plan-pass**；下一未完成入口是补macOS S3必要设计证据、冻结接口/配置/文件与修改候选计划，然后正式同版MiMo/ds-flash planreview和总控独立裁决；本作者不派评审、不推进implementation。用户已裁业务语义不再索取确认。两个平台延期不抹去其后续owner，也不移除O20F02。

完整证据manifest与交付文件SHA在独占根最终生成的`delivery-manifest.json`；manifest自身不纳自hash，避免循环。最终报告以实际首末核验和双流票据为准，不能把本报告的文字自证当产品或gate验收。
