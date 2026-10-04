# CI-PREP-A1 文档修复交付总控核收

日期2026-10-01；唯一工作树 `/Users/leo/workspace/dayu-agent-r` / `codex/upload-material-oracle`，当前checkpoint20f7a5ac，mainfac32未动。artifact path：`docs/gateflow/upload-material-final-ci-preparation-planfix-receipt-20261001.md`。

接受Sol7371的文档修复交付候选，**不代表独立planreview通过或accepted最终CI计划/矩阵/registry/readiness/真实CI**。报告 `docs/gateflow/upload-material-final-ci-preparation-planfix-20261001.md` SHA `1db6e3667d64895a5d70f03c79773909a2cedc9182b794ebc1496b66c6a0427d` 已全文读，实际仅原proposal58/155两行变化；root独立对照真实workspace解析owner、F3五utils scope及原O03裁决，场景/入口/回归信号都保留。修复后proposal SHA `74f1423fe8c4f09475cfb723e1388ce7f4021b4bb7c26a752646dc8bdadb2b7a`，原72c0205a副本保留。

runtime=codex/provider=gpt-6-sol/modelunknown；labelpr197-final-ci-planfix-sol-20261001-01；独立output/stderr/last在 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.yRSH2V/`。托管outer0，39合法JSONL、turn.completed、16completedcommands，无turn.failed或error事件，stderr空，canary逐字匹配。root完整JSONL中两个command非零均已逐项读取：原initialHEAD等式过严，写入前失败无改动，后逐件45字节、ancestry/docs窗口验证并用新prefix23恢复；noindexdiffcheck差异exit1无whitespace诊断被wrapper错当失败，后实际worktree26diffcheck0和28身份恢复。四个正常diffcheck/diff非零与一个HEAD失败原流保留，37命令分流都有argv/innerexit/stdout/stderr，不能把外层0称所有内层0。

root再核44readonly current/45originals都同SHA，唯一changedproposal且准确两行；最终manifest **197件**逐项hash和bytes匹配，manifest SHA `fbf5c5cca16f74257a747625043d472449c2383fc8372b9de810dd0156337188`；报告和proposal实际diff已读，root worktree diffcheck0。旧报告/canary/HEAD按原交付时间窗保持，不顺带机械更新时间线。无产品源码、新持久Python脚本或用户工作流变化，pytest/pyright/coverage/README均N/A而非0files绿。

CI-PREP-A1：accepted / fixed candidate / 独立审查待完成。下一owner=root最终CI计划的同版独立审查与finalsource重绑定；该低级别文字纠正不造产品WU。本任务与F6 aggregate368输入无写重叠，F6两reviewer仍在途，不能借文档候选推进其gate。

后续待核计划映射候选CI-PREP-C02：§6 F4/F7行笼统引用shared upload admission/state/publication；实际F4是storage read view→CN/HK identity，F7是CN/HK下载终态词表。状态needs-more-evidence，owner=最终CI依赖映射，destination=final实际源码绑定/独立计划审查；不作为产品acceptedfinding或当前额外实施任务，不漏掉真实download/rebuild/status消费回归。

残余：完整mandatorymatrix/真实来源hash与XBRL依赖/taxonomy/OS、真实CLI执行和正式oracle/scenarios/readiness covered by later approved slice（root最终CI）；F5Q1 requiring explicit user decision（用户/F5）；旧Raw删除是证据限制（root新run lineage，不能补造旧验证）；最终同版PRreview/closeout covered by later approved slice（rootPR197）。用户已有36语义仍最高authority，不以本计划或parser/代码倒逼改裁决。

独立数据：`workspace/tmp/pr197-controller-collection-20261001/final-ci-planfix-delivery-receipt.json`，本轮原件：`workspace/tmp/pr197-final-ci-planfix-sol-20261001-01/`。下一入口继续F6整体deepreview，CI预备候选保全等待最终依赖与独立审查，真实CI not-run。
