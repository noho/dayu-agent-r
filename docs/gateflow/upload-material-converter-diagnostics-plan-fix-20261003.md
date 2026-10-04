# UM-CI-N01-F01 集中 plan fix：DN-R1..R6 / DN-D0

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6（模型运行身份声明；工具未独立提供权重ID）
CANARY=gpt-6-sol-c5fa9216

- 任务：`upload-material-converter-diagnostics-plan-fix-sol-20261003-01`；gate：plan fix；**只完成计划补足，未实施产品、未通过re-review或plan acceptance**。
- 唯一workspace `/Users/leo/workspace/dayu-agent-r`；branch `codex/upload-material-oracle`；实际HEAD `79977b3a52f8566672e3b462f786f1004dfd3f89`，与派发一致。
- 原计划SHA `a58b95afbc9898969bf85e0c79ed0d3597339d2bbc3ddd420aedc80d30bf7289`；本次最终更新计划SHA `33c00f8543a42c438e315f3294e8f8399cee972722b49ab55bde2bb041d6a141`。原全文/SHA先保存到本任务 `sources/original-plan.md/.sha256`，最终新版快照为 `updated-plan-final.md/.sha256`，精确delta为 `plan-final.diff`；初稿updated-plan.md/plan.diff亦保留；均未覆盖旧plan-sol或review证据。
- 绑定：goal-confirmation、control、root Markdown裁决及root-plan-review-adjudication.json；两份原报告与review.json全文已读取/独立快照。root裁决优先于两审pass-with-risks；DN-R5移除未授权第三项日志业务成功条件，无新增用户技术问题。
- 仍只有S1一个behavior slice。当前可写仅新版plan、本fixartifact及独占`workspace/tmp/upload-material-converter-diagnostics-20261003/plan-fix-sol-01/`。

## 逐项修订与待验证状态

下列“已修复”仅表示候选计划已补足；product_fixed=false、re_review_verified=false。最终finding状态须由同版双re-review/root接受核定，不能据本作者自报放行。

| rootID / 来源 | 状态与精确改动section | 当前来源/证据 | 未来行为验证 |
|---|---|---|---|
| DN-R1：MiMoF1 + DSF3 | 已修复（plan-only），§4.1/4.2.6/4.2.7/6.1。getMessage、formatException/stack、name/level/created验证、UTF-8编码与写入都contained；坏record只incident/drop，不能假record、旧fallback或改conversion分类。typed递归guard，第三方投影不在writer锁内；仅普通Exception contained，四类控制流BaseException原样传播/回收后re-raise，根补充已纳入 | 两原report/review.json、root要求、真源logging/Formatter；format_owner_probe实际坏%d抛TypeError，异常__str__由stdlib返回安全标记 | 真producer坏参数、非法字段/traceback、编码/写入/递归负例；success/failure/cancel原outcome不变，坏record无伪正常log；控制流同对象传播不降为secondary，reservation/depth释放 |
| DN-R2：DSF2 | 已修复（plan-only），§4.1/4.2.3..8/6.1。OPEN→CLOSING拒新reservation，撤销logger在锁外，等在途active=0，再incident/footer/close；stale emit只原stdio raw，footer后零追加 | DS report F2/root；closure_probe真实spawn、线程Event、递归__str__、关闭中late emit，rows=[inflight,end]，公开双流空 | 用真实新module测试并发close/filter/class撤销、在途投影、晚发、递归；typed且不patchhandler方法；故障保持body |
| DN-R3：MiMoF2 | 已修复（plan-only），§4.1/4.2.9/5.2/6.1。唯一exact capture_incident(code封闭)在end前，end不加payload；媒体坏/partialwrite使通道不完整。post-footer清理无新carrier且不保证自报，仅承诺parent实际可观察 | MiMo F2、root明确允许最小carrier/收窄；现result queue业务descriptor不变 | exact variant/多缺字段/非法code/footer后记录拒绝；partialwrite/incomplete、全媒体fault、post-footerclose；不造正常record或业务字段 |
| DN-R4：DSF1 | 已修复（plan-only），§6.1.1。显式a1_coverage.pth + concurrency multiprocessing + parallel数据，coverage run禁pytest-cov插件；完整配置/启动/combine--keep/report/json/逐文件检查；每文件全部生产行≥80%，零exclude/ignore/降标 | 只读现venv hook/coverage/pytest-cov源码；真实coverage_spawn child PID39939，child-only12/13行进merged，5/5=100%、excluded=[]、三份parallel data（另直接读child PID对应原始CoverageData，确认12/13行） | 三生产完整文件分别≥80且child-only行实收；fullpyright未来实际0。真实XBRL独立不带coverage、policy无新增read/write，skip不计正例 |
| DN-R5：MiMoF3 + rootDN-P02 | 已修复（plan-only），§4.1/4.2/5.2错误矩阵/6.1。只有双fd隔离不能建立在第三方前阻止转换（原construction）。capture建立后spool/record/cleanupfault不throw；原success descriptor+output验证后missing/badJSON/footer/read/projection/parentlogging全是安全secondary；后续Docling+manifest原成功owner决定 | root明确拒新增gate；converter原target/_read_terminal_result、runtime队列/cleanup；既有sourceSHA与799匹配 | 逐故障success仍返回已验证result，quiet无诊断；failure/cancel/cleanup原优先级/五字段不变；临时目录删除。禁止新DOCLING_IPC_PROTOCOL归因 |
| DN-R6：rootDN-P01 | 已修复（plan-only），§4.1/4.2.2/4.2.8/6.1。public API只独占一次worker，structured scope结束可撤销class/filters，stdio映射到worker最终退出，无restore bool/policy；真实spawn/finalizer测试替代parent direct context | 实际FD owner/stdlib spawn；closure_probe在scope后正常worker框架finalizer实际写入原fd，public空；普通Exception边界重跑通过，当前输出在closure-final/；原MiMo P5只是模拟fd晚写，不冒真实libc自动flush证据 | realspawn scope外真实libc flush/框架Finalize，parentfd保持；另独立解释器native自动flush。multiprocessing os._exit不假设自动libcflush |
| DN-D0：rootDN-P00 | 已修复（plan-only），开头/§9/报告格式。停止归父Agent本派发，不称主用户pause；下一入口同版双re-review/root接受再plancommit | 任务明确stop、root裁决、Gateflow总控链 | root继续完整gates；本任务不派发/review/commit/实施 |

## 验证、范围与README

实际完成：branch/HEAD/inputSHA/canary/sourceSHA核验；原全文先保全；必要owner源码与双review读取；stdlib closure/FD/format小探针exit0；真实spawn coverage配方exit0、合并+JSON+child行校验；仅5个独占probe/辅助脚本pyright为0 errors/0 warnings/0 informations；另control_flow_probe在两个真实边界对四类控制流8/8同对象传播、普通TypeError contained，该probe单独pyright为0。**没有产品pytest/fullpyright/真实CLI/Docling/provider/network、没有产品实施与提交。** probe只证明机制可执行，不证明未来新module或CLI已修复。

计划生产编辑allowlist仍且仅三文件：`dayu/runtime/process_diagnostics.py`（新）、`dayu/runtime/log.py`、`dayu/fins/pipelines/docling_process_converter.py`。测试编辑仍原五文件；macos_sandbox/docling_upload_service既有回归只运行不改。文档未来仅根README/FinsREADME/testsREADME，按已读职责写实现后的事实；dayuREADME无需改。当前这些生产/tests/README全部只读。

风险分类已纠正：rawunknown INFO为Fins最小技术路由且明确unknown，无WARNING字符串猜级别，不称用户逐字接受新oracle；64KiB确定转义为已裁技术显示语义。外部自建Logger/daemon/quota/抽取质量outside此goal，runtime/converter/upstream owner、只待未来明确goal或新issue/用户决定，**没有已授权laterWU**。Windows/Linux是用户已延期；registry依赖是既有独立WU，本次不写。完整存储错误及post-footer清理不承诺可靠逐项自报，不扩日志框架或业务成功gate。

工具问题如实记录：独占目录已由父预建且为空，第一次mkdir(exist_ok=False)报FileExistsError，未写原计划，核空后才写本次sources；部分批量读取输出曾截断，必要report/findings另分段核读，不据截断自放行；一次猜测spawnhooks位置不存在，未编辑/伪造它。新proof独立使用现stdlib+collector，不依赖未知hook。详本次result。

来源复核期间root追加DN-R1控制流补充：初稿catch BaseException会吞KeyboardInterrupt/SystemExit，真实动机成立，已纠正为普通Exception边界；原root SHA745b2a66…与当前SHA05a01780…、新增root-control-flow-clarification.json均独立保存，不覆盖旧来源。这是明确适用于当前planfix的binding补充，不是未知来源不符或新目标；原固定HEAD/inputSHA/goal均保持，来源已按当前root版本刷新并复核。

当前blocking open questions：无。状态是计划补足候选，仍unreviewed。根control原文有MiMo in-flight等历史状态，已读取但不改；本次依据更晚binding root裁决（双runnerexit0由root核定），不回写或把control当新pass。下一入口：**同SHA双plan re-review → root接受 → accepted plan commit**。本次产物完成后停止；root保持原goal继续。

## 证据位置

- `workspace/tmp/upload-material-converter-diagnostics-20261003/plan-fix-sol-01/result.json`：身份、sources、状态、scope/notprod/unreviewed/oneS1、validation及未运行项。
- 同目录`source-manifest.json`/`sources/`：原计划、binding裁决、双review与owner来源快照及SHA。
- 同目录`updated-plan-final.md`/`plan-final.diff`：唯一更新版本与原版精确差异。
- 同目录`coverage-probe.ini`/`coverage-probe.json`/`.coverage.*`/`coverage-child-pid.txt`、`closure-result.json`/raw+public双流、`format-owner-result.json`/`control-flow-result.json`/`closure-final/`/`coverage-worker-proof.json`：本轮必要小probe，不进产品路径。
