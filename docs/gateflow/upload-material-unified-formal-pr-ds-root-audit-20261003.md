# 正式 PR197 review：DS 总控核收

## Gate / identity

正式 PR review，统一修复 WU；base fac32ecbff9bfe792b63ee9667c8697826b631f4 ... head 44c1892e7361dba799154fc01b2a4dfe43407e75。仅本路核收，不代表双审或 WU pass。

- dispatch：claude / ds-flash，label upload-material-unified-formal-pr-ds-flash-20261003-01，绝对 workspace /Users/leo/workspace/dayu-agent-r，独立 stream-json / stderr / prompt，no-persist。
- 托管 session84585 actual outer0；54421 个有效 LF 分隔事件；228 tools / 228 paired results；result.success / is_error=false / num_turns231；实际 assistant model deepseek-flash，init deepseek-flash[1m]。
- stderr 仅精确 `[claude-code:unrecognized_model]` SDK warning，按 sub-agents 规则记录非致命 warning；不能用空/非空 stderr 单独判成功。
- 当前校验文件读取与报告值精确匹配；report docs/reviews/pr-197-review-20261003-120416.md，SHA256 1b0e3721ae4c22a66b0a64ea1c83b0b40ca59fb8d6a3857c6978591ffd08fe6e。own-summary 完整结构已 root 解析，158 claimed paths 与 scope 人工维护集合精确相等，不只采 self-report。
- 两份 runner 全文件双备份：workspace/evidence/sub-agents/upload-material-unified-formal-pr-ds-flash-20261003-01；output/evidence-backup/sub-agents/upload-material-unified-formal-pr-ds-flash-20261003-01。full tool trace / backups / root coverage：workspace/tmp/upload-material-unified-repair-20261002/formal-pr-review-01/root-audit/。

## 实际 covered 核证

root 将每个 Read 的带行号实际结果逐行与原冻结 diff 对比：source14446/14446、tests23749/23749、utils2862/2862、configuration-readme904/904，合计41961行，零遗漏/错字。tests23750是工具额外展示的空白EOF行，逐字核为空，不是未读取源码。158人工维护文件全部完整 diff 覆盖；必要 owner 通过 exact git44 再定点读，不把 spotcheck 当完整diff。

875治理叙事与26fixture财务正文按内容排除，只核路径/引用/字节。1059逐项diff/headblobSHA由真实Bash7470核；19冻结输入初末及root再核均0漂移。UA-E01真正解码191字节及原SHA、manifest21/24/guide/currentvalidation同源；3README historicalSHA不是当前版本验收，不能刷新历史。F5六文件和SEC原文两manifest实际原字节核，root复用同源已有保全证据。

source/job/publication/摘要/取消 owner 主链已 root 对实际函数、现成裁决及新增finding核对。没有测试/pyright/CLI重跑；2841/3skip/38prod、真实XBRL5passed、671/fullpyright0只按对应samehash证据继承，不把跨平台延期当5样本未验。GitHubchecks[]仅观测事实，不代CLI campaign。

## 全工具失败及恢复（actual event index取full trace）

- 4764 GraphQL、7468 REST 均TLS失败，管道head掩盖外层非零；不能从is_error=false采成功。8235沙箱外读取真实成功；45709、54071末次实际同head/base。权限收紧仍按子工具默认审核，不是runner bypassPermissions。
- 19174分隔echo==== zsh失败，后两段未执行；首段取消投影已读，19642 direct result和19644 public summary恢复。
- 26776首次gitshow使用不存在的错误OID且stderr被隐藏、head管道掩码；不采该段，后半正确exactOID定位成功，26844正确commit_batch全段恢复。
- 31433 jq错误、31634 Python误将files list作dict；31637真实恢复26fixture列表。
- 31843 $H:path zsh修饰符破坏OID失败；31934正确${H}:path成功，31971carrier真实解码。
- 32500历史manifest与当前README三条不等是已声明历史快照；不虚称26全等，仅新carrier/validation/guide真同源。
- 35160错误top-level coverage键导致KeyError，原84source仅前半完成：实际80same/4已被aggregate supersede；35462从tests.coverage恢复38>=80/对应changed_paths10全等；36376实际5externalpassed。无论summary说Python/git无失败，都不能抹去此失败。
- 36378引用扫描出现简称/相对locator的MISSING；36893定点真实路径与receipt存在性恢复。检查存在不等于重验每receipt，原11receipt全核沿aggregate root证据继承，不冒DS重验。
- 37416 echo===失败，后README未执行；37452正确README全读恢复。
- 47678 cwd遗留在输入目录导致relative scope FileNotFound；47705绝对cwd恢复74文件ASTscan，47767核唯一生产旧裸dict不在本次新增hunk。78/79grep探索无匹配按no-match，不推生产全仓无旧问题。
- 临时H错误值在43395先赋再立即重赋，未对错误值发git请求，不能将其算一次Git失败。
- Read/Skill/任务记录/两Write/一Edit无is_error。实际写点只有own临时notes/summary和新report，TaskCreate不是派发Agent。关键结果无未恢复persisted/truncated缺口；所有114Read及88Bash/其余tools已核。

## 裁决与报告收窄

- F-1 → UPR-R01 accepted / 未修复，同源独立确认。
- F-2 → UPR-R02 accepted / 未修复。其声称“4文件8处AST闭集”不完整：AST只比顶层annotation字符串，漏 nested dict[str,dict] 与 list[dict]；root递归AST+真实owner数据链扩为已登记五脚本全部对应签名，不把部分扫描冒全闭集。
- 建议统一Mapping[str,JsonValue]不是accepted具体实现方案；优先复用producer已有DigestResult/DigestDocument等真实形状，避免下游新增loose解析/验证框架。DigestDocument实际是TypedDict而非报告所称dataclass。
- 额外私有helper依赖观察无真实行为违约证据，rejected-with-reason：辅助工具直接复用既有closed JSON检查，没有事实owner漂移或实际故障，不在当前gate顺带抽新公共helper。
- 报告全面无Python/git失败、closed AST全集以及“全继承证据由本路重验”的过宽自述不采；必要diff/输入/owner/两finding证据采纳，provider不构成失败，无重派。

## Residual / next

当前两项修复仍未修复，留当前PRgate集中fix/re-review（fixed in current slice目标，不能提前宣称已完成）；MiMo在途。CLI CI与正式registry为WUcloseout后的独立assessment；Linux/Windows XBRL部署按用户既有延期分配后续WU；历史治理/财務正文为scope内容排除。下一步收MiMo完整终态/证据，集中gpt-6-sol修复，不再切slice。
