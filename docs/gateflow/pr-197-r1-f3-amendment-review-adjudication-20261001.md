# F3 C01 / PA01 窄复审：总控裁决

## 当前状态

MiMo 9959 与 Kimi 26494 均取得托管外层 exit0。报告分别为 `docs/reviews/plan-review-20261001-005120.md`、`docs/reviews/plan-review-20261001-005207.md`。完整结构化结果、冻结原件与必要反例仍由总控核验；作者 pass 不等于 gate 放行。现成上传、下载裁决保持。

## 新发现登记

| ID | 直接证据与 owner | 当前裁决 / 目的地 |
| --- | --- | --- |
| F3-PR2-A1 | MiMo 指出 plan 第三判据的 basename 未明确是 resolve 后名称。汇总 dangling symlink 指向 ALIAS.json，样本 alias.json；原名比较遗漏，解析后比较捕获。Owner 为 digest producer 的 alias 判据。 | needs-more-evidence；总控独立复核后决定最小文字澄清，交 Sol 修计划，不改上传规则。 |
| F3-C02 | 两路指出 loader 接受不同目录的 Alias.pdf / alias.pdf；当前卷上扁平产物同一物理文件。Kimi 真 CLI 缓存支路 exit0，只生成一份却计两份、字节双计。Owner 为共享输入唯一性契约与各 producer 写址。 | needs-more-evidence；先保存反例并独立核对，不默认 reviewer 的延后建议，不在未裁决前扩大 C01。 |

F3 原 C01 源码仍未修，PA01 是计划文字已修候选。五份 utils 候选保留。不得因此记录丢弃代码、重开用户业务裁决，或把计划探针冒称产品通过。


## 总控独立证据与裁决

冻结18 live SHA及18 originals全部匹配，独立receipt `workspace/tmp/pr197-controller-collection-20261001/receipt.json`。两报告完整读取；MiMo JSON success/is_error=false/58turns，Kimi success/false/40turns，outer均0。ModelUsage分别mimo-v2.6-pro[1m]、kimi-k3[1m]；两路stderr仅精确unrecognized_model warning，非quota故障。MiMo令牌在result/report匹配；Kimi指定报告首行令牌逐字匹配，JSON最终摘要没有重复身份/令牌。报告要求在报告开头，指定artifact满足；没有不同令牌，不伪称canary mismatch，也不声称摘要有该字段。Claude为summary_only，中间逐调用不可见，关键freeze/差异/反例由根补核。

根独立激活venv，以真实共享loader与真实digest缓存CLI运行两个目录的alias.pdf/ALIAS.pdf：loader接受2条，CLI0且待生成0，同一inode；唯一20字节产物，汇总total=2、total_bytes=40；原缓存内容不变。独立dangling汇总链接probe证明原basename不等，resolved basename分别alias.json/ALIAS.json、同parent，ASCII比较相等。证据 `workspace/tmp/pr197-controller-collection-20261001/f3-c02/result.json`，与两路方向一致。根第一版临时probe用中文bytes字面量SyntaxError/exit1，脚本解析失败未写素材；改为文本encode后exit0；保留该取证错误，不作为产品失败。源码直接检查loader仅set[str]精确stem，digest三处扁平写址/查址与汇总统计，根因同源。

- **F3-PR2-A1 accepted/低/未修**：第三判据明确比较resolved_target.name与resolved_summary.name及resolved parents；这是既有方案澄清，不是新命名规则。由Sol只改对应计划文字及必要矩阵表述，再同版窄双审。
- **F3-C02 accepted/低/未修**：静默错误缓存复用和重复计数是真缺陷。归原F3显式输入唯一性/产物保全目标的必要修复，登记为后续F3-S2纠正slice，必须在F3整体closeout前完成。拒绝reviewer自动转“新issue或用户再授权”的路径：已有成立findings修复授权足够；不重新裁决上传下载规则。当前C01仍只样本对固定汇总；不在C01顺带修改loader或其它consumer。
- C02语义owner是各producer实际目标命名/身份与共享输入契约的直接边界；目前不武断指定全局casefold或Unicode规范，Sol须先读四入口真实命名/输出根，基于本反例规划最小共同真源与拒绝时点。保留合法无碰撞输入/缓存/字节，禁止重命名输出、改分析算法、禁全部链接或下游统计补偿。四入口是否都受影响需各自真实写址证据，不能只由digest推广。
- **PA01计划文字已修证据可采**：两个准确最小diff和完整全量pyright义务保持，候选同版核验。先完成A1澄清的窄双审后统一回写accepted amendment，不以本报告直接放行。

两路工具非零披露：MiMo写前ls不存在与marker探针锚点错误后逐字差异恢复；Kimi首版collisionprobe先读不存在汇总exit1、cache-miss受ProcessPool沙箱限制exit1，已改全缓存分支得到真实CLI证据。这些不证明未跑的并发写支路成功；根缓存独立复现充分成立当前缺陷。原C01已根/两路独立真实覆盖反例，设计探针不能冒称修后源码。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: summary_only
required_evidence: complete
canary_status: match
result_status: partial
evidence_gap: none for accepted plan findings; source fixes not implemented
retry_class: none
```

## 下一入口与残余

Sol A1计划澄清 → 同版MiMo/Kimi窄审 → 根裁决/accepted amendment commit → C01源代码fix/code review。C02并列记录为F3-S2待plan，完成C01后按独立最小设计修复，再F3整体closeout；F3仍未闭环。非ASCII尚不存在别名、外部运行中换links/事务、跨运行缓存鉴权保持原风险目的地，不借C02扩充。全部候选与历史证据保留于唯一目标branch；未新建branch/worktree、未改main。


### 排程校正（同轮总控，尚未派发）

上节把C02先称未来F3-S2，但该slice尚未approved，不能据此放行本计划gate。实际下一入口统一为Sol修复当前计划：A1澄清，C02基于四真实producer规划必要唯一性/写前预检，映射原goal正常显式输入及产物保持；保留原单一可验证输入增量，不按四文件机械拆slice。当前计划gate fail pending A1/C02，随后同版窄双审必须同时覆盖二者；accepted amendment commit后才能源码fix。C01旧专属规则不扩到无关consumer；C02为独立根因须自身清晰owner/共用真源，无条件全stem casefold/Unicode规范不由本裁决武断指定。该校正不撤销accepted真实缺陷，也不改变用户业务规则。

F7候选32输入冻结前，生成Kimi报告路径时根曾用当前时间加1秒避免重名；未派发，已改为再次读取本机实际时钟的新路径，不以推算timestamp作为审查名称。
