# PR197 F4 新scope同版双路复审合并裁决

## Kimi收取与独立证据

MiMo79430已验收见pr-197-r1-f4-rereview-mimo-adjudication-20261001.md。Kimi label pr197-f4-planrereview-kimi-20260930-01，runtime claude/provider kimi，modelUsage与自报kimi-k3[1m]；托管44800已outerexit0，S2fZDn有效JSON/subtype success/is_error false/89turns。result与report235546 token逐字匹配expected，stderr仅精确unrecognized_model。两路审查同plan SHA0080f24590b7ce4b6b8434c7a7d45d72bdb3cc26a63ab86fdd99f6a749a71cb8。

    setup_status: ok
    agent_status: completed
    tool_evidence: yes
    tool_trace: summary_only
    required_evidence: complete
    canary_status: match
    result_status: accepted
    retry_class: none
    evidence_gaps: []

Warnings逐项：Claude仅汇总，不能证明逐调用都成功；stderr精确model warning；作者P1三次probe失败（随机拒绝未包装、随机坏数据计数浮动、混合批次错误误套非HK），改确定计数和批次/单候选双层比较恢复；P2持guard误调publicget引出不可重入错误，改guard内unguarded、释放后比较恢复；README zsh glob/错误helper所在文件无匹配，经拆条/真实infra定位恢复。原probe含ducktype/未参数化dict/type-ignore，不作严格类型证据，不复制到产品/tests；只采旧运行期contract与计划模拟。

总控分段完整读Kimi报告、源码/caller/errorowner，与MiMo逐条核对，32现场SHA再MATCH。Kimi两probe复制到workspace/tmp/pr197-f4-controller-rereview-20261001独立namespace、不覆盖作者证据；激活venv分别实跑：fs_contract_probe outer0，同序载荷/原异常类型/guard互斥/前缀/空root通过；equivalence_probe托管32680 outer0，60000compare/0mismatch/3708非contractruntime单列。新API不存在，不以旧运行期模拟作新API或type验收。作者126pytest仅其基线自报，根不伪称重跑；根先前679受影响基线包含这些未变源码，后续新源码门禁仍须实际跑。

## 裁决与下一gate

- F4-PR2-A1 accepted/未修复/低。缺席allocated_periods键返回原allocated，不填None猜changed；真实键存在且任一财期直接比较不同才纠正digest；read_error必须先抛。根空Fs独立证实旧ID。MiMo提示文字缺口，Kimi模拟正确实现缺席而未要求显式文字，二者不冲突，不能凭无finding免总控成立项。
- MiMoF2 rejected-with-reason，保持前次根理由：无合法caller未读空index证据，不加view_loaded/新状态或拒绝真实D=0。
- KimiN1采用事实补充并登记：company只有无repair时先于loop；repair在loop内gate后。只更正证据表，不动流程，非新blockingfinding。
- N2并入A1精确操作数period_projection.identity_period/fiscal_year。N3非法allocated输入在合法canonical/literal域不可达；N4契约外bug异常差异和N5开发ticker误用只是既有前提/证据局限，不新增业务fix或承诺。

两路报告可采，但plan review gate仍fail pendingA1。旧A1～A5越权方案撤回可接受；方向认可不是acceptedplan。下一Sol仅plan文字及三态矩阵fix→MiMo/Kimi同版窄re-review→acceptedplancommit→单S1实施。F4产品未实施，不宣称整PRpass。

## 风险、README与现场

F4-R01 requiring new issue or explicit user decision、R02 assigned to later work unit；新guard计数/barrier/事件/取消/错误projection/types/coverage属于fixed in current slice（未完成义务）。其它WU独立，未来F5不倒逼API。纯review/plan不触发产品README。用户现成裁决优先，manifest成功原则不变；不做错误迁移/trustedinventory强制/整runlinear/长锁/uniqueness。主树codex/upload-material-oracle，mainfac32不动、不newbranch/worktree/外部comment。
总控前一次写此artifact的functions脚本发生JS语法错误，exec未执行、未写文件或启动runner；修正为原始多行字符串后创建，属于controller setup修复，无provider重派。
