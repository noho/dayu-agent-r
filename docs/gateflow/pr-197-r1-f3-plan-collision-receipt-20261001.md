# F3 A1 / C02 计划修复：总控核收

Sol34569/yi22SR已托管outerexit0，116 JSONL逐行解析，turn.completed、无turn.failed/error，stderr空。last与指定fixartifact令牌各逐字匹配。自报gpt-6仅可见基础型号，不是canonical部署回执；provider路由仍gpt-6-sol，精确型号未知不作为业务审批。

根完整读取最终fixartifact及计划C01/C02公共契约、caller顺序、矩阵、scope。当前plan SHA38d115621fc81ebeba7d06af88331ed2439ef076670897b93e171b5a297a1bed。独立20live readonly/21originals SHA均匹配，计划唯一许可变化；原最大Python类型块5049字符逐字保留，原CLI字段/特殊类型义务未借碰撞修复撤销。完整两artifact no-indexcheck分别1、双流0，无围栏豁免。原件与freeze保留，五utils源码不变。

两条可观测非零：JSONL79子探针漏PYTHONPATH导致import utils失败1，随后明确仓库PYTHONPATH恢复，不加源码兼容导入；JSONL101收尾断言误要求HEAD仍2a失败1，违反当前允许无关checkpoint的输入边界，作者删错误伪依赖并重读现场head/两checkpoint实际scope恢复。最后closeout.json真实head31473fe1，最终报告也已改正确首尾2a→314，并记录89/314均未写此plan；根早读草稿时的旧head不能当最终事实。所有失败与原双流保持。预期no-index差异1单独理解，不误报命令0。

根把作者设计/probe复制到独立prefix，只调整repo路径指向绝对当前仓库，避免覆盖作者输出，激活venv真实复跑19矩阵/四原模块缓存CLI反例，outer0；独立strict配置relative include/exclude=[]，实际filesAnalyzed2、errors0/warnings0，outer0。证据workspace/tmp/pr197-controller-collection-20261001/f3-new-design/root-result.json及双流。此为设计规则与现有缺陷证据，源码仍未修，不冒称产品验收；原全量源码门禁仍必须在真实codefix后重跑。

动机/owner采纳为可审查计划候选：四真实扁平路径直接证据支持C02，多入口传实际Path分组给唯一只读身份判据，C01保留digest专属固定汇总owner。实际文件身份与同父ASCII保全规则在docstring区分，允许无冲突链接/Unicode不casefold；完整caller预检早于业务读取/worker/write。是否最小、全部副作用时点与原A1A4/PA01保持，必须下一同版MiMo/授权备份路独立Planreview审查，不靠该root交付核收放行。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
evidence_gap: none for plan-fix delivery; plan re-review and source fix pending
retry_class: none
```

下一入口同版A1/C02窄双审→根裁决必要fix/re-review→accepted amendment commit→同一S1源码fix/code review。F3仍未闭环；C01/C02产品accepted/未修，PA01验证义务保持。无用户上传下载规则改变、无主干改动、新branch/worktree或源码越权。未知文件系统未建非ASCII别名/外部并发换链接/跨运行缓存来源仍原目的地，不顺带事务或鉴权。
