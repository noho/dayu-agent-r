# PR197 除 F5 外的 review findings：最终收口与用户指定停点

## gate 与已读回版本

2026-10-01；唯一 workspace /Users/leo/workspace/dayu-agent-r，唯一开发分支 codex/upload-material-oracle。
accepted PR review commit **c305067fb7434b2fd0bc5a10398fc65ac600fce8**，8份文档，cached diff-check0；普通 push81764 托管 outer0。root之后分别直接 gh PR 与 ls-remote 读回，本地/远端/PR197 head 均为该 commit，base/main本地/tracking/远端均为 fac32ecbff9bfe792b63ee9667c8697826b631f4。
PR https://github.com/noho/dayu-agent-r/pull/197 仍 OPEN/draft，statusCheckRollup=[]，不将无远端checks当通过。没有 merge/mark ready/approve/requestreview/comment/main修改。

c305067f仅审查报告/裁决/controller文档；37 source/test/README 与审定5fc5e4f0逐件字节相同。因此 PR review accepted commit、普通 push 与读回已满足，F3/F4/F6/F7 各 **draft-PR-pass → final closeout pass**。下表分别记录各 WU，不以组合审查合并其业务 owner/目标。

## 各 WU 最终状态

| 项目 | what changed / finding 状态 | what verified / docs / completion |
| --- | --- | --- |
| F1 | PATH候选原裁决 rejected-with-reason；未激活依赖环境，不成立新增代码缺陷 | 无修复WU，保持原证据，不重开 |
| F2 | 测试owner将取消拒绝断言移入三 failure 基线循环；accepted bb11ca22 已修复，当前组合保全 | 原431测试/两pyright版本；当前1377覆盖目标node，AST无位置同原；无产品/README变化。PR修复及最终状态闭环 |
| F3 | 四分析入口使用统一显式root/manifest，五utils清除当前私人locator；碰撞/链接环与必填预检在owner完成；原成立findings均已修复 | accepted slice03e8b9b0、aggregate244056c5；同字节真实合成CLI/类型证据及双路PR审查；utils免永久测试/coverage。README按原职责处理。final closeout pass |
| F4 | storage同guard批量meta观察、identity索引，批初共享/start-stream-retry新窗；前缀/原异常与身份优先序保全；原成立findings均已修复 | slice75fec034、aggregate87b5a642；794 owner测试/八prod≥80%历史证据，当前共享文件按F6及1377组合核；fins/tests README已更新。final closeout pass |
| F6 | storage并发版本冲突与仍需修复两typed事实贯通workflow→adapter→runtime→direct/job/CLI/wait；确认前缀守恒，不制造完成事件；AG-A1及原必修均已修复 | slice4f0b5b04、aggregate5fc5e4f0；1342原组合、19+21docfix、八prod≥80%、当前1377/783类型；root/fins/tests README已更新。final closeout pass |
| F7 | CN/HK三终态Literal/Final唯一owner，workflow/rebuild/adapter同源且入口子集互拒，无compat re-export；成立finding已修复 | slice31473fe1、aggregate2cc2f5ed；741原组合及四prod覆盖，F6后workflow按当前证据核，1377覆盖；fins/tests README已更新。final closeout pass |
| F5 | 原finding、N01/N02 accepted未修；仅计划提案和官方raw补证，无产品实现 | 用户要求本轮停下讨论；不是完成、不是deferred豁免。下一执行入口需用户具体Q1裁决，随后必要planfix/双审/实施 |

正式 PR review 裁决 docs/reviews/pr-197-review-20261001-175653.md；独立报告171136/173600均已入c305。两路outer0/canary/68冻结/37blob/715全快照和37段root实核，取证声明收窄与失败保全详正式裁决，不冒称Claude逐调用轨迹齐全。无新accepted未修项属于F3/F4/F6/F7；必要fix/re-review为明确no-fix pass。

## 真实验证与边界

root真实12testfiles **1377 passed/3既有edgar warnings/exit0**，全量项目pyright **783 checked/0 errors/exit0**，精确argv/双流/exit已核，同37输入字节；不是全仓pytest或最终真实CLI CI。当前仅文档checkpoint不重复无风险大矩阵；各原生产文件≥80%覆盖按可执行字节身份与后续F6更新证据复用，不用旧F7workflow数为当前保证。
本次未新增/修改Python产品源码、测试、README，故不触发额外对应测试/类型/README修改。DS122定向passed stdout仅补充，缺其独立argv/exit不作主门禁票据。
全PR fixture final-pyright.log新增EOF空行仍为已登记卫生项，留最终PR收口；不声称全PR diff-check通过。

## remaining risks / owners / next entry

沿用各accepted goal与aggregate裁决：
- F3历史公开内容/跨平台Unicode别名/换链和缓存/selected-only parity：requiring new issue or explicit user decision；分析输入/命名/consumer owner，独立goal。
- F4跨writer集合唯一性、总扫描成本/start-stream跨发布观察：requiring new issue or explicit user decision / assigned to later work unit；storage publication/identity owner，F4-R01/R02。
- F6完整job reason/hint持久化、publication indeterminate：assigned to later work unit；既有jobcontract/storagepublication owner。
- F7行级/SEC/公开disposition词表、空库rebuild取消不对称和helper治理：assigned to later work unit / requiring new issue or explicit user decision；对应协议owner，本增量未改变或放大。
- 原17标签+受控XBRL、最终真实CLI新mandatory矩阵/material oracle/scenarios/readiness：later approved work/gates；root按原裁决恢复后推进，当前未实施完成，不以局部审查替代。
- #198整项已有finalcloseout及授权comment，保留PR的Closes #198；不重复发布closeout评论。F3/F4/F6/F7是review finding WU，无另立GitHub issue，issue linking/comment为N/A。

**当前执行停止**：用户明确指定“其它 findings 完成后停下讨论F5”。所有runner终态已收取，无产品writer/在途审查；Sol只读粗分组交付已核收，只有后续提案，不推进计划/实施门禁。root将本收口和交接状态普通提交/推送保全后，解释F5并等具体讨论结论，不开始F5或原队列。

后续slice默认完整可验证行为增量，只有真实依赖/风险/独立验收才拆，理由写进plan；相关必要fix批量一轮交付/同版双审。仍只在指定分支开发，用户现成upload裁决不重裁。所有修改/验证/失败证据都进入artifact，不留会话-only修复事项。
