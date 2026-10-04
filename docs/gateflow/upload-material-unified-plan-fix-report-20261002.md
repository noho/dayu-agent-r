RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-97b2d1bc

# upload_material 统一计划集中 fix 报告

任务 label：`upload-material-unified-plan-fix-sol-20261002-01`。模型运行事件没有暴露实际型号，unknown不由路由/canary补推。Gate=`plan review → fix`，本轮作者修复完成，**计划仍 not accepted**，下一入口由root冻结同版re-review；本任务现在停止，不自动推进下gate。

唯一workspace `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`；HEAD `619d092ab4278645203c7ebe08515f7697d92b71`、main `fac32ecbff9bfe792b63ee9667c8697826b631f4` 首末一致。没有产品实施、commit/push/PR/外发、安装/网络操作或子Agent派发。用户批准范围未重裁，仍一个WU/三个完整行为slice，全部slice与aggregate后PR197 review；完整CLI CI/registry在WU后。

## 绑定与哈希

- 修前plan（=正式冻结原件=本轮`plan-before.md`）：`2fc3d1911737e4afcd964a2cb586a2e661c5fd38a55cf62480c15ce6c3a9f9d7`。
- 修后plan：`c99c35adba919a8baf371b0142e0ab1abf256a951e89b2fc15e8a2d38988e8ea`。
- 正式冻结input manifest：`b685cc42b56cc3dff0f4a88c9f7ede09d987581cef8f1fad2ba5a1632e5a1356`（实际文件hash核验）；其中historical control entry=`232c397b9a5a281a9b22aeacf3990aa843666d8372d9ad82ce57e61808a352fd`。
- live control本轮hash=`4b1e4151a62e45ef357aec783c9176020af829f6454c32aa9726e0411771a85c`，其current-gate行政更新与正式冻结读入snapshot分开，不滚动改plan/control hash。未修改control。冻结历史control值依据正式manifest及binding裁决，不冒现场live字节仍为232c。
- macOS goal amendment=`17c0d804d459091a5c5909f42511a75e7ab2e7a9250072b9bc8e5f6e15adc290`；runtime amendment=`365aad6342d2baf68703938e72e05eb6de57c01764eb9ae13dd7489f72a26338`（实际读取/hash核验）。
- AGENTS.md、Gateflow技能、479行修前完整plan、双review全文、root裁决全文、control/两个amendments及macOS runtime consolidated root裁决均已读。Gateflow用户明确停止条件优先，本轮不派review、不checkpoint。

## 改动文件与owner

授权文档改动仅：`docs/gateflow/upload-material-unified-repair-plan-20261002.md`；新建本报告。新独占目录：`workspace/tmp/upload-material-unified-plan-fix-sol-20261002-01/`。

新采集器复制件：`parent_harness.py`、`boundary_child.py`、`probe_convert.py`、`convert_plain.py`、`harness_contract_checks.py`。只有新parent接线/错误判据修改，另四份保持复制source字节（仅新路径）。新脚本：`io_verdict.py`、`test_io_verdict.py`、`replay_receipts.py`、`validate_delivery.py`、`edit_plan.py`；新`pyrightconfig.json`明确非空include，只检查自身10份脚本，使用主.venv解释器与已装candidate第三方类型路径，没有改旧config、降格ignore或产品签名。全部函数签名typed且有中文参数/返回/异常docstring。其余本目录为独立stdout/stderr/exit、sha/validation清单、pytest临时产物。

**验证工具范围偏差如实登记**：首次pytest未显式设置coverage/cache位置，默认写了根`.coverage`及`.pytest_cache/v/cache/nodeids`。已把本轮coverage文件移至独占`coverage-default-first.sqlite`，保全修改后nodeids原字节并仅移除本轮4个测试nodeids，后续使用独占COVERAGE_FILE与`-p no:cacheprovider`。其它既有nodeids保持；不能证明首次运行前旧`.coverage`是否存在及其原字节，不能声称缓存完整历史已恢复。详`cache-recovery.json`。这是本轮技术输出路径错误，非产品改动，也不以git clean掩盖该范围偏差；没有删除旧Raw/probes/reports。

## 成立项状态与精确证据

以下“已修复”是作者fix状态，仍须root同版re-review验证，不赋accepted gate。

| ID | 作者状态 | 改动/精确证据 |
| --- | --- | --- |
| UP-DS-F1 | 已修复 | plan §6.6:274窄白名单加入filing_upload_publication；§6.7:409逐列5处真实caller（SEC252/544、CN905/1193、filing859）及required None、保filing返回/warnings/取消capability。实读filing859及SEC/CN真实调用。 |
| UP-DS-F2 | 已修复 | plan §5.2.1:109～139冻结A normalization/pure selector、typed失败出口、U唯一code/category/message/hint、R消费；success保tuple、失败不扩planner-exclusive；五元与delete/四code逐项表；material数量→路径/名称/格式→selector不前移。另点名A149/256删除第二次normalize及所有R迁移。实读A379～453、R807～979/1082～1185/1530～1578、U18～315。 |
| UP-DS-F3 | 已修复 | 新parent两处save_profile_verdict接线，删除exit0→unexpectedly converted；新io_verdict唯一typed判据。plan §7.4.1:474封闭字段/正反规则；`tests-delivery.stdout/exit`4passed/0、`collector-coverage-delivery.json`100%、`pyright-final.stdout/exit`0errors/0。 |
| UP-DS-F4 | 已修复 | plan §1实际manifest/hash/历史232c与live行政gate分清；`validation-summary.json`正式manifest及frozenplan实核。 |
| UP-DS-F5 | 已修复 | plan §1/§4 O20F02/§7.3～7.4/§8 B-X3/B-X4/§10/§11全部当前generation-ready一致；旧待核明确历史/原冻结引用。产品install/spawn/CLI/coverage留S3，非accepted。`validation-summary.json`obsolete current markers空。 |
| UP-DS-F6 | 已修复 | plan §5.2第15项/§5.2.1表明确U required source_kind，material业务文案、filing原REQUEST/message不变，同源hint；V1/V3/V6断言类别/文案。 |
| UP-M-F1 | 已修复 | plan §5.3:155显式删除tool material拒primary分支/否定字段；同format owner同步help/schema/files、单/多/delete/空字节；§5.5 V6:181真实tool路径与schema反例；实际读upload_tools398～420及formatowner现文案。 |
| UP-M-F2 | 已修复 | 与DS-F3/F5同根因合修，非微切；runtime receipt replay见下，当前状态/§7.4.1同源。 |
| UP-M-F3 | 已修复 | 与DS-F4同根因，历史snapshot和bindingmanifest闭合。 |
| P0-R09 | 已修复 | 判据owner及新复制采集器实际修订；转换exit/SUCCESS不参与IoObservation/decide。false单独unknown、true allowed、同PID/path errno/kernel拒绝才denied；listener未accept不作依据。正反合同及真实票据读回有独立原stdout/exit。原parent外层1/file-uri child0保持历史。 |

全部root questions已闭合：Q1保仓储finalguard与同owner复验，非第二状态机（§6.2/6.3）；Q2 S1一个pass/gate（§5.5）；Q3/M-Q2 identity builder六code直接typed FinsUploadUsageError/U（§5.2:92）；Q4真实CLI owner-return barrier完整启动/两old-admission/释放顺序/timeout/restore recipe（§6.6 V12:295），无生产hook/fake仓储或结果；Q5/M-Q1 Documents typed配置异常、factory/Process/worker精确CONVERTER_CONSTRUCTION映射、普通.xml/.xbrl同候选无默认converter fallback，README职责明确（§7.2/7.3/7.5）。本轮没有执行S2未来barrier或产品CLI。

## 真实票据回读与P0-R09边界

只读parent-run-20261002-01原97张actualchild收据及root-continuation-20261002-01 **10条关系case+managed-cancel，共11张owned收据**。root文字的“10case”按关系数解释，本轮由actual-child文件实核，不把取消吞计。source18/input14/原parentfreeze16逐件现场hash均一致；869保护文件（产品/测试/依赖/README/旧script/control/reviews）全部未变，`protected_changed={}`。

`receipt-replay-02`每用例保存精确profile/actual receipt path+hash、PID、request_target、stream及typed verdict：

- file-uri actual PID93381/exit0，实际load URI与open_file_stream false；absolute PID93692、traversal PID93697同false。离线原件未附kernel raw，三者严格unknown，不从root摘要伪造kernel事件。
- root binding已独立核PID93381精准kernel deny file-read-data根外outside.xsd，保持该外层证据结论；本轮kernel原日志不在指定收据包内，不冒本轮自行重新采集/验证kernel。typed KernelDenial只有匹配owned PID/target/operation/window与原件ref才可参与denied。
- runtime-schema实际stream true→allowed，符合用户runtime只读例外。没有要求taxonomy独占或“runtime请求一律拒绝”。
- remote/encoded-file/FTP实际ModelDocument.load调用存在，OS拒绝证不足→unknown；encoded只观察字面%6f路径，不反推canonical哨兵已读取。ENTITY/XInclude/PI未观察目标请求→not-attempted（此profile scope），不冒请求后拒绝。
- selected-boundary实际read syscall：1个根内allowed+3个根外EPERM/EACCES denied；实际connect EPERM→denied，独立listener accepted=false只作补充，不充拒绝证明。原转换SUCCESS均不作资源结论或财务准确性承诺。

没有重跑昂贵macro/安装/MLAC合法性/OS矩阵，没有新public resource code、parser/graph/namespace补丁或量阈。

## 实际验证命令、退出与恢复

所有以下命令cwd为唯一workspace；执行验证前均`source .venv/bin/activate`。原双流与exit分文件保于本轮独占根，摘要不替代原结果。

| 实际命令 | actual exit / 原件 |
| --- | --- |
| `python3 workspace/tmp/upload-material-unified-plan-fix-sol-20261002-01/edit_plan.py` | 0；集中替换完成（后续仅授权plan补合同段）。 |
| `python -m pytest -q workspace/tmp/upload-material-unified-plan-fix-sol-20261002-01/test_io_verdict.py --cov=io_verdict --cov-report=json:workspace/tmp/upload-material-unified-plan-fix-sol-20261002-01/collector-coverage.json --cov-report=term` | 0，4passed/100%；tests.stdout/stderr/exit；默认缓存路径偏差已上述登记。 |
| `python .../replay_receipts.py` 第一次 | 0；replay.stdout/stderr/exit与receipt-replay。首次only-stream判据把remote/encoded/FTP作为未观察目标，真实事件抽查后补明确loader请求标签（未将其错误推成denied）。 |
| `python -m pyright --project workspace/tmp/upload-material-unified-plan-fix-sol-20261002-01/pyrightconfig.json` 第一版 | 0errors/exit0；pyright-01双流/exit。 |
| 同pytest加独占`COVERAGE_FILE=.../.coverage`与`-p no:cacheprovider` | 0，4passed/97%；tests-final双流/exit，补loader负对照后最终100%。 |
| `python .../replay_receipts.py` 修正loader版 | 0；replay-02双流/exit与receipt-replay-02（remote/encoded/FTP unknown）。 |
| `python .../validate_delivery.py` 第一版 | **1**；delivery-validation双流/exit、validation-summary-01.json；自身把10关系case误当含取消总10，实读managed-cancel收据后修正为11。 |
| 同有限delivery核验修正后 | 0；delivery-validation-02双流/exit、validation-summary.json；97/11（关系10）与全部hash/合同标记成立。 |
| 最终独占coverage pytest（`COVERAGE_FILE=.../.coverage-final`、`-p no:cacheprovider`、coverage输出collector-coverage-delivery.json） | 0，4passed/100%；tests-delivery双流/exit。 |
| 新脚本全include pyright中间版 | **1**，replay cases推断str未含None；pyright-delivery双流/exit。补`list[tuple[str, Path, Path, str, str | None, bool]]`，无ignore/cast逃避。 |
| 最终同explicitconfig pyright | 0，0errors/0warnings/0informations；pyright-final双流/exit。stderr只有pyright1.1.409→1.1.414更新提示，没有安装。 |
| `git diff --no-index --check .../plan-before.md docs/gateflow/upload-material-unified-repair-plan-20261002.md` | **1**、双流空，no-index因文件有差异返回1；没有whitespace诊断，不伪称actual0/full PR check。plan-diffcheck双流/exit。 |

只读命令包括：git status/branch/rev-parse、cat canary/AGENTS/skill/绑定全文、分段sed完整plan和必要source行、限定目录rg定位、明确清单hash核验和有限ls目录。一次联合rg尝试不存在`.coveragerc/pytest.ini/setup.cfg`产生**内部exit2**；同条shell随后ls成功outer0，定位改为现有pyproject pytest配置；不把outer0当内部全部成功。一次rg输出命中巨型旧receipt command字符串而被工具截断，改为JSON字段/精确profile事件摘要读取，没有靠截断摘要裁结论。所有source locator失败/核验脚本失败已以上述恢复实证区分。

精确最终验证argv另保本目录`validation-commands.txt`。测试覆盖只指新io_verdict owner100%，不冒新parent整体OS运行覆盖或产品测试/全量pyright通过。

## docs decision、分类residual与未覆盖

本轮修改plan+新fix报告，没有产品或用户工作流落地变化，README本轮无实际更新触发；计划按根/Fins/dayu/tests各职责冻结未来S1/S2/S3实际README改动。没有修改既有报告/reviews/evidence/control/旧探针。

| 风险/未覆盖 | 分类；owner/destination |
| --- | --- |
| 本轮全部正式plan findings/P0-R09 | fixed in current plan fix；仍由root同版re-review验证、当前notaccepted。 |
| S1/S2准入/真实tool、状态/guard/并发与S3标准install/production spawn/cleanup/真实CLI→manifest/coverage/README | covered by later approved-scope slices；对应Fins/storage/Documents/runtime owner，未来实施gate，不前置plan循环。 |
| 新parent整个OS宏执行/集成运行覆盖 | covered by later approved-scope S3必要机制验收；本轮只修副本/合同+实际旧票据读回，不冒新OSpass。 |
| kernel raw外层PID93381日志 | root-owned existing evidence；binding结论保持；本轮离线分类明确未附raw，不冒自己验证，冻结复审由root联原件。 |
| Linux/Windows | assigned to later platform work unit，用户正式amendment；平台依赖/Documentsruntime/总控排程，未验不外推。 |
| typed XBRL/抽取准确性 | tracked by existing upstream #4437；不patch/不量阈。 |
| COMMITTED后release全局indeterminate及其它既有22 residual | assigned to later work unit/原residual队列；现WU只failclosed、不新增scope。 |
| 完整CLI CI/registry与RawEOF可逆封装 | 前者assigned to WU后独立阶段；后者由全slice后最终PR证据owner收口，本轮不改旧Raw。 |
| 首次pytest默认cache/旧coverage历史未知 | requiring explicit root disposition of this technical scope deviation；本轮错误已如实保全/回收，旧coverage原字节无法证明，不应作为产品结果证据。 |

完成交付：作者集中fix与必要validation完成，**notaccepted plan**；root冻结本plan hash后同版双路re-review。没有自行进入下一gate。
