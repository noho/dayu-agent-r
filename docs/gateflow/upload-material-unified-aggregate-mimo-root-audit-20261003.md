# aggregate MiMo 路总控审计与集中修复入口

## 生命周期与身份

label `upload-material-unified-aggregate-review-mimo-20261003-01`，托管 session 96594 已取得 actual outer exit 0，不再 poll。18853 个有效 JSONL events、119 个实际工具调用；terminal success/is_error=false/num_turns=120。init model `mimo-v2.6-pro[1m]`，实际 assistant message model `mimo-v2.6-pro`，报告采用后者；两者均如实保留，不将显示配置后缀误报 provider 变化。event188与18100实际 cat 原 canary，和 expected `mimo-3b692b80` 一致。
stderr 只有精确 `[claude-code:unrecognized_model]` warning。全119工具输入/result保存于 `workspace/tmp/upload-material-unified-repair-20261002/aggregate-review-01/root-audit/mimo-full-tool-trace.json`；runner原输出、stderr、prompt、canary逐字节双备份，详同目录 `mimo-runner-backups.json`。
正式 report `docs/reviews/code-review-20261003-104024.md` SHA d695b206c24424655423678d2c6ee2a5fc5c67418b4ddb7a2dd4493948c197e3 与 summary 均全文读取。原113 frozen inputs总控实扫0missing/0drift，head/source/diff未变。

## 工具与覆盖裁决

- 6962 `echo ===` shell解释导致actual1，第二段未读；6986直接sed恢复 `_prepare_complete_source_meta`。不把第一次复合工具当完整成功。
- runtime diff第一段1757进入persisted-output；1763/1769实际Read恢复1–701，1775 offset800产生短文件warning，无额外内容应读。1787/2369继续700–1600和2431尾段，按实际diff总长核，不将空读视作新增覆盖。
- 13042、17546 README diff 输出进入persisted-output，原完整输出没有实际Read；17564仅抽40新增行，13065只恢复pyproject/lock/dayuREADME。不能据此接纳所有6份配置/README完整covered的自述。下一MiMo re-review必须完整补读6份当前WU配置/README diff，输出截断/persisted必须定点恢复。
- 测试12603/12674契约组1159行确有完整Read（7文件）。其余主要是12757–13015、15306等grep/assert/name/head抽样；部分定点SIGINT/tombstone断言真实读过，但不等于整个38测试差异。下一MiMo re-review必须完整补31份未完整测试diff（保留7份已完整覆盖的exact原身份及新增delta）。文件清单将冻结为required-recovery-scope，不机械以grep名称算covered。
- 14213 actual输出38 coverage rows/below80=[]、真实5个external case及checkpoint，具备实际核验；初末113inputs扫描均0漂移。summary config_readme_files=7是自述计数错误，冻结真实为6；总控以scope和实际diff为准。
- 所有119调用核过，无伪造终态、无未恢复的生产源码关键读取失败。对已真实走读的38生产差异/必要完整owner链采纳；部分被改函数仅diff，未变全文不虚列全部covered。完整PR旧代码仍后续正式审查。

## Findings 与 gate

MiMo没有新产品finding；它未发现DS的CLI归属错误不推翻总控直接源码证明。最终本轮修复清单为 aggregate register 的 UA-R01/R02/R03/UA-E01，全部accepted/未修复，一次gpt-6-sol集中修复，不新增slice/WU。
setup_status=ok；agent_status=completed；canary_status=matched；result_status=partial（报告声称测试/README完整覆盖不成立，下一复审补齐）；retry_class=task。探索工具错误已恢复，不消费provider重试；补覆盖是同一gate必要证据，不新产品范围。aggregate不能pass，必须修复并完成同版双复审。

## Residual 按 Gateflow 分类

| 项 | 分类 | owner / destination |
| --- | --- | --- |
| Raw EOF及三项小修复 | fixed in current slice 的本gate收尾队列，尚未修 | 证据owner、CLI投影owner、runtime/测试维护；本次集中fix+双复审 |
| 私有backend卸载及依赖minor升级 | assigned to later work unit | Documents集成/依赖升级维护者；仅实际升级或真实字段漂移需求时评估，不把#4437冒称版本升级issue |
| Python3.11 dynload路径、Linux/Windows部署 | assigned to later work unit | 平台部署/中立runtime；当前用户固定macOS/Py311验收，跨平台已明确延期 |
| 全局/下载indeterminate、filing/processed amended与其它22候选 | assigned to later work unit | 既有独立residual队列对应storage/Fins各owner；不自动加入本次修复 |
| 完整CLI CI和正式registry | assigned to later work unit | 总控后续独立阶段，用户已授权继续，不作本修复slice |
| typed XBRL/抽取准确性 | tracked by existing issue | Docling #4437及上游；不本地修算法 |
| 历史生成文档全文、未重新执行同版tests/install/OS | assigned to later work unit 的验证边界 | 当前有same-source实际票据继承；历史人工叙述明确excluded，不是重跑门槛；源码变更后验证实际受影响范围；正式PR旧code在后续PR gate核 |
| 两路未完整covered范围 | fixed in current slice 的本gate必需取证队列 | DS补ZIP测试尾/架构README；MiMo补31tests+6docs；下一复审，不放行未分类缺口 |

## 下一入口

冻结集中fix身份/白名单/保护清单，派发一次gpt-6-sol。修复后同版两路并行复审，包含实际scope recovery；root核全部轨迹、代码、Raw载体及实际测试/type/覆盖，才accepted aggregate checkpoint，之后普通push至既有draft197，正式完整PRreview。修复WUcloseout后继续独立CLI CI/登记。
