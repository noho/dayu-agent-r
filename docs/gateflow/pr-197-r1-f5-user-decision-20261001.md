# F5 用户裁决：先同源推断，仍不确定则保全已知并单列未知

## 最新 binding 决定与当前入口

用户原话：**“可以推断就推断，推断失败就：继续处理 A，明确列出 B 的不确定状态，不猜 B 的财期。”**

该答复解除 F5-Q1 的公开行为阻塞，并授权按既有 Gateflow 继续本 F5 修复。原计划 P1“整请求写前失败、已知也不处理”不采纳；需要将实际方案固化为该裁决对应的最小完整计划，再同版 MiMo/Kimi Planreview、总控裁决、accepted plan commit 后实施。原 upload 修复队列仍在 F5 闭环后依既有顺序进入，不在本 F5 顺带做。

## 语义边界

- 先收集并利用同公司可用的可信原始年度截止日证据；A 满足可信证据条件时可用于 B 的推断。下载 discovery 与本地 rebuild 消费同一 owner 的可信与邻近/冲突规则，不因窄窗口缺年度公告而忽略可信本地年度来源。
- 可确定的报告正常处理；全部可用可信证据仍不足或冲突时，明确列出该报告的不确定状态，不猜财年/财期，不用请求季度、披露日期、旧季度标签或文件名补造事实。不将“发现但不确定”当作“未发现”。
- 此处推断沿用已确认 F5 年度证据/规则月末财政日历范围，不新增 52/53 周、过渡财年、超范围网络历史爬取或从旧标签反推年结日。不能因为泛称“同公司”就忽略年结日变化/冲突/删除或损坏来源。
- 未知报告没有确定文档身份时，必须使用真实来源引用表达；不得虚构 document_id，不把未知当成一次文档发布成功。不确定状态与已确认处理行/计数/终态由公开契约 owner 同源投影到 direct/CLI/job/wait；不在消费者层重算或仅显示层修正。
- 重建遇不确定时保留源文档，当前结果不沿用旧 form/coverage/report_date 冒充本次确认事实。原 F5-N01（远年证据压制显式季度）、N02（未知结果携带旧标签）仍 accepted 未修，需同一个完整行为 slice 修复；N03 非空官方 Raw gap 已补，不重采或篡改 provenance。
- Q2（本地可信输入读取失败原样终止、不吞为无依据）、Q3（同证据集合窄/宽/rebuild一致；新真实冲突保留未知）原技术裁决保持。各读写/取消/完整性异常、F6 public 原因及 F7 终态 owner 保全。

## 实施纪律与依赖

唯一主工作树 /Users/leo/workspace/dayu-agent-r，唯一开发分支 codex/upload-material-oracle；本次开始 HEAD26979bd109a94417e227f55cff3ff64b42bb5d8e，main未动。F2/F3/F4/F6/F7 已最终收口，F4 API 必须按现有真实源码重绑，不能调用旧计划不存在的接口，不能把 raw meta view 当完整性证明。

默认 F5 一个完整可验证行为 slice，不按模块/字段机械拆；同 gate 必要修复集中交付/一组同版双审。Sol负责plan/implement/fix；MiMo/Kimi同时并行review，真实Kimi quota失败按已有授权用DS备份。全部用runner子进程，显式绝对cwd、独立output/stderr/no-persist/读取凭据；总控核结构化结果及实际源证据独立裁决。修复项即时登记artifact与三controller。

当前仅登记用户决定，未产品实现、未accepted plan或代码gate pass。下一入口 Sol 重绑/固化计划→双路 Planreview；所有材料进入现有draft PR197，用户手工merge。最终全部修复后的真实CLI CI/material oracle/scenarios/readiness义务继续保留。
