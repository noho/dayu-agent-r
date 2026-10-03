# PR197-R1/F3-C01：样本产物与固定汇总同路径

## 发现、证据与当前状态

- Sol implementation label `pr197-f3-implement-sol-20260930-01`、托管74222在途。其源码实施已经声明按停止条件暂停，仍待外层退出及完整结构化结果验收；不能把最终消息或文件大小作为终态。
- 受控反例 `workspace/tmp/pr197-f3-implement-sol-20260930-01/reserved_stem_probe.py` 与 `reserved-stem-evidence.json`：操作者清单包含 `_manifest.pdf`，通用 loader 接受；同目录基线存在，预先缓存的 `digests/_manifest.json` 是该样本的有效 digest。真实 `python -m utils.build_semantic_digests` exit0/待生成0，随后固定汇总写同一路径，原 `numbers` 丢失。
- 总控已经实读该探针/证据和生产 main：样本缓存、worker 写出、所选汇总均使用 `<stem>.json`，固定汇总为 `_manifest.json`。尚未独立运行反例；正式验收须待源码 writer 终态后冻结输入、独立核对。
- accepted plan `a88dcf8e...` 第3节允许无 `fil_cn_` 前缀的 PDF、只检查样本间 stem 唯一；第4节保持固定 `_manifest.json`。两条组合漏掉了样本与保留产物之间的冲突。普通504断言 harness 通过不能反证这一场景。

## 初步裁决与修复边界

**F3-C01 accepted-candidate／未修复／低。** 这是当前显式输入及产物保护契约的缺口，owner 在开发 digest 产物命名及其写入前预检；不属于上传材料业务，不改用户既有 upload/download 裁决。

优先最小方案是固定汇总命名保持，将会碰撞该保留产物的样本在相关入口写入前明确拒绝，中文诊断/exit2且已有字节不变。不得为解决该反例重命名整套产物、增加缓存来源鉴权、改 schema/token 算法或限制无关入口的合法名称。具体 owner/helper 与相关消费入口的边界需 Sol 修计划并经过 MiMo/Kimi 同版窄复审；未 accepted 的修订不能直接改代码。

该修订映射 binding goal 的正常显式样本定位与原产物语义保持，以及已 accepted plan 的冲突预检、不得覆盖样本原则；不得借此新增业务功能。若进一步取证证明必须改变用户可见既有行为或原 binding goal，而非本项必要正确性条件，依 Gateflow 先列出具体取舍交用户，不由总控或 reviewer 自行改裁决。

## 后续验证与防遗失

1. 收取Sol外层exit/terminal、全JSONL及每非零命令，冻结五源码/plan/goal；总控独立复现反例。
2. 成立后仅派Sol plan fix，原plan及五源码先保存原件；将最小拒绝/owner/命名/入口边界和非空正负验收钉死，双路计划窄复审后提交accepted amendment，再进入代码fix。
3. 反例应验证预检先于创建产物/执行worker，正常样本继续运行、无关脚本不被额外限制、重复运行不会误读固定汇总作样本缓存；已存在样本摘要/汇总保持字节。

本记录和主队列同步，当前F3仍未闭环、尚无accepted slice commit；保存已完成候选与失败证据，不回滚或丢弃源码。

## 终态收取与总控独立反例

Sol74222已取得外层exit0，108条有效JSONL/turn.completed、stderr空、canary匹配。最后报告明确implementation blocked，候选五源码/原plan/goal保持，未提交。本轮不因外层正常退出而放行。

总控激活venv，用独立 `workspace/tmp/pr197-f3-controller-c01-20260930/` 保存五源码/goal/acceptedplan/实施artifact原件与freeze，运行真实模块CLI的续跑路径。完全合成PDF/基线及已存在有效digest，没有真实转换/私语料：CLI exit0，写前numbers存在、写后numbers消失且stems含_manifest，八输入SHA前后均一致。反例脚本断言exit0只表示缺陷被证实，**不是产品验收通过**。结果保存在该目录result.json，产物保留便于复核。

据直接同源证据将 **F3-C01 改为 accepted／未修复**。它属于现有目标的必要正确性：预检防止样本占用固定汇总产物，保持原产物命名与算法，而非另加业务功能。用户已授权修复所有成立findings及继续；本项开发脚本的最小输入预检修订在该授权内，无需重新裁定 upload 行为。Sol的“requiring new issue or explicit user decision”仅在必须变更bindinggoal/固定产物布局时成立；当前更窄保全方案未到该条件，不能因局部计划遗漏自动把实现选择转给用户。

下一Sol **只修plan**，把保留产物命名owner/脚本特定预检/大小写及物理别名碰撞/中文诊断/产物字节保持反例写明；不直接改已停止的源码。优先只在digest写入owner拒绝与固定汇总冲突的样本，通用loader/schema/A-B/verify不得因此被无依据限名；验证相关消费影响，不顺带改缓存策略/消费者布局。重新冻结、MiMo/Kimi窄计划复审、accepted amendment commit之后才实施修复。

### implementation runner 裁决

```yaml
setup_status: ok
agent_status: blocked
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: partial
warnings:
  - 临时harness首次类型错误及缺参数中文诊断验收失败，均修后独立复跑恢复
  - locator无命中与no-index差异exit1为已解释的预期结果
  - 504断言与780文件类型门禁不能覆盖或豁免C01真实反例
evidence_gaps: []
retry_class: task
```

完整JSONL非零item_22（临时类型1错，修后3临时文件0错）、item_25（首次harness中文错误提示缺口，修后504断言/175子命令）、item_36（词边界locator无命中）、item_37/51/52/55（no-index新增文件差异，均无空白诊断）已逐项核对并保留恢复记录。item_37为组合命令，tracked检查随后独立复核0；不凭组合末项判断前置成功。候选实现仅部分采纳，不进入code review/pass；C01先修计划。本项不是provider失败、不通过重派抹掉已确认缺陷。
