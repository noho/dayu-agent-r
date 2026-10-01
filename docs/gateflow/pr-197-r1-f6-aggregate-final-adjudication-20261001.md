# PR197 F6 aggregate 最终总控裁决

2026-10-01；唯一workspace `/Users/leo/workspace/dayu-agent-r` / `codex/upload-material-oracle`，当前HEADfc10882e，mainfac32未动。**aggregate deepreview pass；F6-AG-A1 已修复，没有accepted未修项。** 下一入口accepted deepreview commit/push→现有PR197同版组合PR review→分别closeout；不是全PR或所有WU完成。

## 双路终态与必要证据

MiMo25203与Kimi91784均托管outer exit0；完整JSON success/is_error=false，各44turns，permission_denials=[]。actual modelUsage分别mimo-v2.6-pro[1m]/kimi-k3[1m]，自报无遥测不采为总控事实。stderr仅精确unrecognized_model warning。完整报告`docs/reviews/code-review-20261001-164920.md`（SHA59c116104770e170eff4c2b93f13462c980b787cdbec9278858455cff78a8732）及`164914.md`（SHAaccad55a8ced6abd6b4d70c1d354fb7dd8c5068700ee252c913568d3fae61642）已全文读，两报告的本轮canary均逐字匹配expected。Kimi最终summary未重复协议首部，但完整报告有正确身份/令牌，不以summary缺字否定实际读取证据。

root末轮独立52current+52originals SHA相等；source `direct_events.py` SHA6db072215b02a1d048fe895e8aa493bffc044d754ed5ef37497be2c62abe232a；与raw-before精确仅195行措辞替换；只删除指定FinsPublicFailure类docstring后AST含全部位置严格相等；20其它slice与accepted4f0b5b04 blob相同。root再次直接读同owner六reason枚举与runtime三来源完整性写入分支，描述完整覆盖两新原因且不改变字段、校验、序列化、业务文本。原两个full aggregate报告155916/160049的可执行行为意见保持适用；本轮两窄报告不是全21重新走读，原覆盖限制继续披露。

真实验证沿用同版Sol19+21passed/fullpyright783checked/2282parsed/0errors/exit0，精确argv/双流/exit已root核；无排除coverage direct89.0380、七其它prod保持且CLI修复后85，复用不冒称重跑。root组合12testfiles/1377passed/3既有warnings/exit0补核共享F4/F7/F6变化。README N/A，三README字节不变。

## 取证声明收窄与非零

Claude仅summary_only，不声称全部中间工具成功。MiMo01早期argv及16末核argv、Kimi inline argv含占位/缩略，不能采“全部精确可重放”声明；root独立重算必要身份/AST/源码，不补造轨迹、不另派报告修复。Kimi noindexdiff1为预期差异，zsh组合echo失败及恢复仅作者披露，旧失败原流未独立取得，不能采原流保全声明；实际后续21节点参数/源映射及必要证据已核。25项Kimi manifest逐件SHA匹配。

MiMo新临时证据使用`workspace/tmp/pr197-f6-aggregate-docfix-rereview-20261001-01/`，偏离指定provider目录；未覆盖任何既有label或产品文件，不采其精确写入scope遵从声明。该目录四个未提交scratch helper另经root实际类型检查：首轮受workspace排除检查0files无效；absolute include被pyright忽略，误扫10旧文件，非本轮产品错误；恢复relative include后实查4files，AST helper的Optional位置返回注解有1error。**这些scratch代码不采纳、不提交、不作为产品类型pass依据**；root自身inline AST独立证明与Kimi独立核验满足本gate必要证据，不为非交付scratch扩出harness修复WU。MiMo关键静态审查意见采纳，整体取证声明partial；Kimi报告accepted。产品代码必要类型门禁仍为同版真实783files0error，不掩盖scratch检查结果。

独立receipt：`workspace/tmp/pr197-controller-collection-20261001/f6-aggregate-docfix-rereview-{mimo,kimi}-receipt.json`。两路setup_status=ok/agent_status=completed/tool_evidence=yes/tool_trace=summary_only/required_evidence=complete/canary_status=match/retry_class=none/evidence_gaps=[]；MiMo result_status=partial仅收窄上述非关键声明，critical_review_opinion=accepted；Kimi result_status=accepted。不是两票放行，裁决依据是root同源事实及必要修复合同。

## Findings 与残余

F6-AG-A1 accepted→已修复，经独立同版双窄审及root验证；原A1/A2/SEC275已修不重开。job完整structured reason/hint持久化与publication indeterminate为assigned to later work unit（既有jobcontract/storagepublication目标）；取消/helper/行级常量/test结构治理requiring new issue/user decision；未动态触达防御分支保留原覆盖限制，不制造非法状态补coverage。F5Q1仍用户pending。PRreview/closeout以及全部批准修复后的完整真实CLI新matrix/material oracle/scenarios/readiness属later approved gates，未执行。

既有用户裁决保持；后续slice默认完整行为增量，相关gate内修复批量交付，不为非关键报告问题起循环；详execution-cost-correction。原required-fix裁决/两full报告/Sol失败流均保留为历史阶段，当前状态以本最终裁决与controllers有效块为准。
