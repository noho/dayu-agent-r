RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-0c78ee24

# 统一修复 WU：剩余 S2 实施与验证交付

全部剩余 S2 已实现并完成下列实际验证，交总控 MiMo/ds-flash 双审及独立核收；不赋 gate pass。运行时未暴露精确模型 ID，填写 unknown。S3、正式 PR197 review、完整 CLI campaign/registry 与 WU closeout 不在本次实施范围。

## 最终身份与机器索引

唯一 workspace `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`；HEAD/base `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`，main `fac32ecbff9bfe792b63ee9667c8697826b631f4`。原计划 SHA `c99c35adba919a8baf371b0142e0ab1abf256a951e89b2fc15e8a2d38988e8ea`，10160 件 input manifest SHA `c3302141cb8117a17736d0dbf7dde5daf9c953141266a9eacf116761752aa806`；原 plan/input/allowed-files、旧两轮证据及报告均保全。

证据仅在 `workspace/tmp/upload-material-unified-s2-final-completion-sol-20261003-01/`。完整文件/命令双流/actual exit/验证路径与 hash 从 [delivery-machine-index.json](../../workspace/tmp/upload-material-unified-s2-final-completion-sol-20261003-01/delivery-machine-index.json) 读取；最终索引及本报告摘要由同目录 `delivery-sha256.json` 封印。首核 `initial.json`，末核 `final-freeze.json`，实际再次随机读取 `random-read-final.json`，保护输入零漂移。完整候选清单、diff、38 个生产 required 调用及旧 helper 零引用、逐生产覆盖率在 `final-audit/`，不在正文重复历史表格。

## 实施

- R/U：材料 typed state admission、纯 handoff 一致性和 required 同组仓储；静态身份/路径/角色/首错合同保留，目标错误先于公司名，unsafe/repair 前置失败。
- Publication/D：独立公司阶段后 prepare，材料 writer view 纯竞争仲裁、条件登记及 storage final guard；skip、metadata-only、八格覆盖、健康重删和恢复均消费真实 storage/guard final。C02 必填 material_published_state 直接传递，COMMITTED 后释放失败保 durable 并抛失败，无重读改 skip、重试或第二套取消/rollback。
- 全链：旧五处 caller 的材料路径归新 executor、三处 filing 显式 None；新增 constructor/executor 全集显式迁移。同组仓储贯通默认运行时及三个下载 adapter factory。Service 准入函数返回同一 handoff，CLI 不持仓储能力。市场、Service/direct/tool/job/读取/schema 同源 published_amended；metadata_updated 零转换/零 stored files、保内容版。filing 原 JSON/错误文案及状态合同保留。
- job：no-runner/generic exception 同 typed reason 双摘要、active-only；已保存 SUCCEEDED/FAILED/CANCELLED 后投影异常不覆盖终态。推荐值保持同次文档集合的 ID/null map；材料 true/false 均不额外过滤。三份 README 已先读职责后按实际行为更新。

## 实际验证

最终产品源码聚合集 `final-wide-03`：**actual exit0，2643pass / 3skip**。3skip 为两个必须真实 cmd.exe 的 Windows 用例及可选 PDF 集成；生产文本 Docling、tool-runtime-direct/CLI 与 Fs 成功链均实际执行。28 个修改生产文件全部 ≥80%，最低 **84.29%**，逐文件 statement/covered/missing 数据见 `final-audit/coverage-products.json`。

`final-pyright-03`：**actual exit0，0errors**；独立探针配置 `probe-types-delivery` actual0/0errors。aggregate 后只有一个测试的 job 文件检查从协议属性改用同一 concrete assembly store；产品字节完全一致，实际 4 个相关 owner 用例在 `final-owner-12` 再通过，全量 pyright 再通过。前后 SHA 与这一个测试 delta 明列 `final-audit/validation-summary.json`，不隐藏版本差异或为报告格式重跑宽套件。

| 验收 | 同版证据 |
| --- | --- |
| V7 | 真实 target 首错、active create 同/异字节拒、missing update/delete、真实 unsafe/repair 在 direct/observation/job 前零写；publication/ingestion/service owner tests |
| V8 | delete/content/metadata/skip × source/company，B 在 A begin 前真实提交、A writer/注册拒；既有 storage registration/final guard、alias owner 用例 |
| V9–V10 | 八格 Fs status/转换次数/版/非 marker 字段；实际 true 删除/重删、恢复；列表/recommendations、strict bool；首删/重删字节/revision/time/manifest/assets 与损坏删除合同 |
| V11 | 两 old admission 正常 winner/skip、身份/role/fingerprint/primary/amended/company 时间差异、真实资产/manifest/同长度 digest 损坏；I/O 与实际 COMMITTED 锁释放故障、无 postcommit read/retry/rollback |
| V12 | `race-final-13` 顺序放行：双方实际 old MISSING/None，actual0/0、ok/skipped、winner→loser business_diff={}；`race-final-14` 同时放行：actual0/0、skipped/ok、business_diff=null 如实记录；此前同版 09–12 留存。生产 Docling/storage、Service/SEC/CN binding、实际安装源码/probe SHA、独立 stdout/stderr/debug、owner stage trace、owned PID/wait/资源、零 job 查询及恢复全部留存 |
| V13–V14 | no-runner、generic typed failure、active-only、三类 terminal 投影失败保全、observation 无 job、precommit cancel 与 late commit outcome；完整受影响 filing/download/Service/CLI 原回归 |

## 总控裁决与失败恢复

C01/C02 按既定 owner 落地。已实际读回 C03/C04/C05/C06/C07、execution 和 R01/evidence：六件额外测试仅按 required 接口及明确 fixture 补充迁移；C05 保 ID map；C06 移除泄漏仓储的 getter；C07 三个读取用例用真实 original+DoclingDocument/role/primary、保原业务断言。**曾提前将 C04 理解为包含其材料 helper fixture；C07 明确旧窄授权不自动包含该修改，候选与时间线保留，不以后续批准抹去。** processor alias fixture 在 C07 前未改。

US2-F08 与 root R01 是同一项。原 `race-final-06` A actual1、父 actual1、B 在 finally 被终止 -15，不能计通过；`company-race-root-cause` actual1 的真实 Fs traceback 精确证明 A read→B 公司提交→A validate(expected None) 提前误拒，未到 C01 公司 commit owner。最窄修复将 initial None 交该 writer/identity guard 下的真实等价 merge/no-op，已有公司仍严格 snapshot；未 catch/re-read/retry。root `r01-evidence-root-adjudication` 已 accepted，最终仍待双审。现探针两个 owned Popen 均实际 wait 完成，技术 wrapper 只记录真实入口/原 cause 并 re-raise、原样返回；新顺序/同时放行皆通过。材料文案由唯一 failure owner 的显式 required source_kind 产生，保既有 code/kind/schema 与 filing 原文。

全部非零和恢复逐票保留在 machine index：早期 required/type/fixture/API 迁移、owner-01/02 -15 超时/中断、不完整 JUnit 不计 pass；race-01 文本断言、race-final-01 不存在 list_jobs、独立 pyright include/exclude 配置及脚本类型错误均保失败。后续对应新标签修复验证。**本轮曾全局 ps 查询，违反 execution-root 协议；已登记，后续只用自身 Popen、启动票据、actual wait/timeout，未再全局扫描。** evidence runner 外层成功不代表内部命令成功，只按 actual-exit.json 计结果。即时报告原文保存在 `interim-report-before-final.md`。

## 剩余边界

无已知 S2 实现 blocker；交总控双审与核收，未做正式 PR review 或 gate pass。macOS 无真实 cmd.exe，可选 PDF 用例仍未启用；生产成功清理日志未暴露 Docling 子 PID，标 unknown，实际 process tree 只承诺 owned CLI PID/PPID/session 与资源/wait 证据，不伪称发现其它进程。未安装/修改依赖，未派子 Agent、stage/commit/push/创建分支或 worktree、修改 PR/merge/approve/外发；未实施 S3/XBRL、历史迁移或新增财期规则。
