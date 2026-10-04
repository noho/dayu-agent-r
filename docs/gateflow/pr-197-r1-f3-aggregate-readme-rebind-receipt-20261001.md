# F3-AG-PV01：输入重绑定复审核收

## 裁决与证据

F3-AG-PV01 为 root 冻结清单生产步骤的配置错误；**accepted／已修复**。产品源码没有变化。旧 freeze、originals、失败记录及原报告保留，当前 F6 README 未回滚。此前候选记录保持原件，本记录补最终修复状态。

DS14599 外层 exit0；完整 JSON 为 success、is_error=false、48 turns、无 permission denial，actual modelUsage 为 deepseek-flash[1m]。报告 `docs/reviews/code-review-20261001-135600.md` 的 SHA 为 `377876696a57986e659a8ae9d01292daf581e5a149e81f19d6417e658c22b655`；报告及结构化终态的本轮 token 均匹配。stderr 只有精确 unrecognized_model warning。Claude 汇总 JSON 不暴露逐个中间工具事件；报告列出的失败与恢复不能据汇总 success 扩为“所有工具通过”。

root 独立逐件重算：新清单 1117 live／1117 originals 全匹配；旧 1117 originals 匹配，旧 live 唯一差异仍为 F6 合法修改的 README；1116 公共键 SHA 一致。pinned README 与 accepted slice `03e8b9b013a30298ba3055b900368102db05e22c` 的 Git blob 逐字节一致；五源码分别与该 commit blob 一致；F6 全部 21 可写路径与新冻结集合交集为空。结果在 `workspace/tmp/pr197-controller-collection-20261001/f3-aggregate-readme-rereview-receipt.json`。

旧 DS65682 同五源码的完整代码意见可以采纳为审查证据，统计以原始流为准：九 CLI 为 5×exit0／4×exit2，54 命名 PASS；helper 实际 225 行，旧报告 226 行叙述不采。执行期异常按原 worker 折叠，采纳范围是输入 resolve／argparse 不误归，不承诺所有执行期 RuntimeError 原样传播。原报告不改写，不新增产品修复。

## 范围与下一入口

此核收仅关闭输入配置修复项；**F3 aggregate gate 尚未通过**，等待 MiMo50118 完整审查终态及输入身份核收，必要时窄复审同 snapshot 重绑定。不能用单路无 finding 或此次窄复审代替完整双路代码审查、最终 PR review／closeout、完整真实 CLI CI／registry。当前 F6 Sol69038 仍是唯一产品 writer，候选未提交。

残余：历史 Raw 已删除及最终 CI 重建归整体收口；旧报告统计/汇总可见性限制归本核收说明；最终双路输入一致性与 aggregate 裁决归 root 下一个 gate，均不借此改变业务裁决。
