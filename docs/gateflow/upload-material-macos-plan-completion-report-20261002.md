RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-7d716624

# upload_material macOS plan-completion报告

任务label：`upload-material-macos-plan-completion-sol-20261002-01`。runtime为当前Codex，provider为本任务指定路由gpt-6-sol；实际模型未由事件/API暴露，unknown，不由canary推定。此文件是plan补证交付，**不是review/implementation、accepted plan或gate pass**。

## 结论与停止状态

**generation-ready=false / blocked-handoff-to-root**。B-X1完整候选依赖与锁变化、B-X2真实输入/闭包/配置契约候选、B-X4正样本同次采集可行性及B-X5无typed真实positive已补足；唯一执行资源阻塞是父层macOS强制启动/文件网络策略、继承/取消与必要特殊引用关系核证（B-X3及B-X4的边界部分）。runtime读取白名单是否允许XML引用越过所承诺taxonomy边界也必须具体核实，不能只把越界转换exit非0冒读取拒绝。

依用户停止条件，交可审查脚本/argv/预期后本子任务停止，总控接续。没有把Linux/Windows延期项列blocker；没有把最终产品标准安装/CLI→manifest验收当前化为先实施产品才能通过plan的条件。仍一个统一WU、三个完整行为slices；17标签＋O20F02、S1/S2现成UM裁决、全slices及aggregate后的PR review、WU后完整CLI campaign/registry均保留。

## 身份、授权与变化

唯一workspace `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`；首末HEAD `619d092ab4278645203c7ebe08515f7697d92b71`，main/base `fac32ecbff9bfe792b63ee9667c8697826b631f4`。`identity-before.json`、`identity-after.json`及最终票据在独占tmp。

本轮修改：统一计划§7–8、整体ready说明/必要交叉引用；新增本文；独占tmp内安装声明/约束、freshvenv、公开采集、原型脚本和双流票据；授权证据根中新增本label双份公开保全。原计划抬头旧canary明确保留为准备轮身份，本轮canary单独记录。

保护集合886文件首末SHA一致，涵盖dayu/tests/utils、README、pyproject/requirements/constraints及准备报告/控制/goal amendment；S1/S2章节按root原件base64逐字节比对一致。主.venv未安装包，未改产品、README、锁、registry或总控文件；无subagents、commit/push/PR/外发。初始四份既有脏文档保留。执行中新增的总控`upload-material-macos-probe-root-observations-20261002.md`只读并落实其原型协议约束，非本作者产出。

计划修订SHA256：`57beaee8f59b396d7bc748fe1115270d3b18f4b11b2b2d65a46340574360ea80`。准备报告仍SHA256 `f4ecf18b52665bc6e0b34b73dce0b8f4704c35e63ff9722ca093bf1dab6ec4da`；root可逆原件原SHA `5b2f76c661a27640fb42a8e4db7d8b6c7adae97f53212cfc8d0ecbc1cf27c3f0`未覆写。

## 安装/合法性/真实转换

独占freshPython3.11 venv完整解析安装Docling[xbrl]2.127.0/Core2.96.0/Arelle2.45.3，现有common/macOS约束复制到tmp并加候选pin，无no-deps。安装exit0（409.127s），pipcheck0；保存resolver install-report、freeze、全部安装METADATA/hash及实际pin回读。新closure五pin为arelle-release2.45.3/bottle0.13.4/isodate0.7.2/jaconv0.5.0/pyparsing3.3.3；Arelle实际METADATA jaconv>=0,<1，未发现旧jaconv声明冲突。候选完整闭包安装成立，不冒最终Dayu标准安装成立。

公开输入来自Docling官方固定commit `f1c42e394e3f5c40375c83edf01f8de762bb64f9`。MLAC为其官方notebook明确记载的SEC EDGAR取得财报，非合成引用图；本轮未向SEC源再做字节直取核验，不冒直接SEC下载。instance SHA `04a015790c25d5a5371117bc64100335e65bfe1b3acdb71b4f2240c97e09cdf1`；五issuer schema/linkbase＋官方顶层taxonomy ZIP逐URL/UTC/hash及每entry hash已冻结。混合许可记录仓库MIT、包内FASB授权使用notice/XBRL复制条款/SEC政府作品声明；FASB官方terms原文已采集，未修改taxonomy，不把MIT覆盖到第三方权利。原件/许可限制包不入PR，git check-ignore确认tmp/两证据根忽略。

Arelle离线MLAC/GRVE完整闭包validation各exit0，XML日志仅info、无error/warning。无hook MLAC Path/Stream均SUCCESS、errors=[]、实际key-value对象存在，JSON同SHA `c95431f8fd4321aea6276ff32dc179a81331b81325991726c5535d291e9e5c7c`。统计只证明转换不止标题，不增加财务准确率/内容量门槛。GRVE只报告已验证合法性，未验证Docling。

v4同次MLAC Path/Stream也SUCCESS，各2211个实际ModelDocument.load调用和32个ZipFile.read调用；模型480facts/93contexts/typed_contexts0、36登记documents、errors=[]。事件逐调用记uri/base/源文档/xpath/line/href/schemaLocation和archive/member、PID/run；是实际函数调用记录，不是独立重放/URI聚合，也不是全局OS trace或entry成功bytes消费证明。静态声明/缓存短路且无直接事件的关系unknown。每路实际pipeline边界普通值快照→原backend unload一次→model.isClosed=true、profiler恢复/原method身份未变。

纠正旧计划生命周期：XBRL SimplePipeline继承的BasePipeline._unload是no-op；execute finally不等于backend已经close。P0在实际边界捕获并显式关闭，不改第三方转换算法；产品候选在Documents owner finally负责一次关闭。真实样本无typed，#4437继续上游跟踪，不重复issue/不宣称typed通过/不删XBRL候选。

## 真实失败、恢复与证据局限

可独立回读的非零run：[('convert-mlac-path-v2.json', 1), ('convert-mlac-path.json', 1), ('prototype-pyright-configured.json', 1), ('prototype-pyright-root-observation-fix.json', 1), ('sandbox-start.json', 71), ('validate-mlac.json', 3)]。

- sandbox-start exit71：sandbox_apply Operation not permitted，保原stderr；父层已有启动0只作启动证据，本轮没有同样重试/审批绕过/全局配置变更。
- validate-mlac exit3：原型instance与XSD未同级；修正validation布局后同bytes闭包exit0，初始日志不改。
- convert-mlac-path/v2 exit1：P0 profiler误匹配ZipExtFile.read，KeyError name使profile失活，干扰加载而出现None parent qname报错。原失败/原脚本/原错误保留；无hook成功及精确ZipFile.read代码身份的v3/v4成功证明这是探针owner错误，不归Docling上游。
- configured pyright exit1为metadata路径类型错误；改用明确str(path)后恢复0。parent protocol修订第一次pyright exit1为signal handler FrameType签名错误；修正后恢复0。原票据保留。
- 两次初始公开tree下载的目标JSON与run票据同名碰撞，body被run票据替换；保下载SHA/provenance、重新独立获取为payload-*.json，后一run源body完整。旧raw body缺失如实记录，不冒首轮完整保全。
- 辅助locator的zsh未引号URL问号/目录glob各报no matches found（exit1）；随后精确引号/路径读取恢复。其它无匹配rg只是定位，不作为通过。一次inline Arelle profile诊断输出被工具截断且未存独立双流，明确不作验收；验收均使用上述独立run票据。
- 初版pyright对workspace脚本受根exclude影响，0不作脚本覆盖证明；随后独占pyrightconfig显式include所有交付原型，错误及恢复已列。全量产品pyright baseline0，没有产品代码改动，因此不虚报运行生产受影响pytest/coverage。

## 父层脚本、范围与预期

精确cwd：`/Users/leo/workspace/dayu-agent-r`。首次父层精确argv（目录必须尚不存在；重跑换全新目录，禁止覆盖）：

```text
/Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-macos-plan-completion-sol-20261002-01/venv/bin/python /Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-macos-plan-completion-sol-20261002-01/sandbox_parent_probe.py /Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-macos-plan-completion-sol-20261002-01/parent-run-20261002-01
```

`inputs-before/after`冻结脚本/instance/taxonomy，policy首末hash；各run argv/双流/exit/时间及输入hash。仅建立/private/tmp本label全新公开根及独占output，不改任何既有taxonomy/用户配置。env -i的PATH仅系统工具，Arelle正式XDG_CONFIG_HOME和backendTMPDIR只在该run设置；这是prototype cache recipe，不冒生产配置。早期无隔离对照使用临时HOME仅为本子进程，argv原样保留，未改全局HOME或用户配置；最终父层recipe已改。

C0真实读取根内成功/C1-3根外file/绝对/穿越拒绝/C4本地实际listener connect拒绝/C5编码/C6symlink、hardlink nlink上游拒绝及真实catalogZIP、直接sandbox_init、exec子进程继承、同次真实Docling正/负、外部ENTITY和process组取消均有有界命令。文件/网络probe记录实际syscall返回，不能靠转换失败判断OS拒绝。C8 XInclude/PI/其它scheme/plugin、runtime白名单可被XML引用及完整loader/IPC继承仍unknown；脚本成功也不等于全matrixpass或产品pass。启动/正对照失败立即stop；没有机制无限重试。

总控P0-R01协议修订已落脚本但**外层未执行验证**：每run新目录，取消不kill-0/不查进程列表；受管parent捕获SIGTERM后实际wait其child，driver实际wait parent，原票据记两终态。`cancel-protocol-control`无隔离对照exit0，parent0/child-15、cancel_received=true；只证明票据协议，不冒隔离/生产取消通过。脚本失败的真实原因及未能取得的关系由总控归因，必要时继续同WU plan/fix，不进入review或实施。

## 双份保全、副作用与下一入口

首批公开/依赖/转换票据373文件、27,343,419bytes双份逐件hash一致并从各副本独立回读；`dual-archive-readback.json`。final handoff脚本/报告与后续票据另存两份`handoff/`，不覆写首批或失败票据。两根：`workspace/evidence/upload-material-o20-f02/upload-material-macos-plan-completion-sol-20261002-01/`及`output/evidence-backup/upload-material-o20-f02/upload-material-macos-plan-completion-sol-20261002-01/`；同磁盘不是灾备，未重启回读/未删或遮蔽source，不冒做过。

副作用仅独占venv/公开下载/原型日志、两份公开保全及授权两文档；主venv/产品/README/锁/Git身份无改。未创建branch/worktree/clone，未commit/push/PR/评论/issue，未派Agent。最终hash和身份票据为独占tmp `delivery-hashes.json`/`identity-final.json`。下一入口：总控审查脚本后按已有授权在父层执行、独立核必要证据，收核S3接口/策略及unknown关系；只有必要边界成立才改generation-ready=true，随后正式同版planreview。当前任务完成到授权的blocked handoff停止点，不宣称plan-ready目标已经达成。
