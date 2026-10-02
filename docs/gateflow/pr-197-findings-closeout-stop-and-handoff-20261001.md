# PR197 findings 闭环后停止并交接：最新用户执行边界

用户最新指令：PR review findings尚未fix完、20多小时，要求调整工作方法，slice不要如此小；修复完PR review findings后给handoff prompt，交新Agent执行。

## 本轮终点（覆盖此前“完成所有WU再停”的执行时序）

- 当前PR197 review F2/F3/F4/F6/F7已经正式闭环、F1 rejected；本轮完成剩余F5与其真实必要修复、验证、正常review/PR197闭环。
- F5只保留一个完整F5-S1；IV01–04及当前诊断确证必要项一次集中实现/测试/类型/README，集中同版双审。不得单finding/字段/文案各开slice。非实质metadata/nit不反复开修复reviewloop；错误reviewfinding由root依据证据拒绝，不改源码迁就。
- 用户已授权额外一次gpt-6-sol集中收尾重试（明确答复call_qc0XHTx67pv90Rt7Tyr94a4U），不是无限retry。现Kimi只读租约结束后立即用原route集中交付，MiMo已outer0及root裁决保全。
- 所有开发仅 `/Users/leo/workspace/dayu-agent-r` 的 `codex/upload-material-oracle`，不动main、不分支/开发worktree。runner子进程绝对cwd/独立双流/canary；gpt-6-sol plan/implement/fix，MiMo/Kimi并行review，Kimi实际quota不足才DS-flash备份，root独立裁决。
- F5必要门禁按Gateflow正常推进；同字节且确已独立检查的旧证据保存并作精确来源引用，不重新裁已有业务、不为文档文字另分细slice。实际新源码/高风险路径仍需正式审查与真实验证，不能跳过或假pass。
- 完整修复/闭环代码及必要裁决资料进入OPEN/draft PR197，普通push后独立读回local/tracking/remote/PR head，main与remote main一致。用户手工merge，root不merge或标ready。
- 最后更新 `docs/upload_material_repair_handoff_prompt_3.md` 为最终可执行交接prompt，写实际commit/PR状态、已闭环findings、所有未实施WU/依赖/既有用户裁决、runner角色与独占日志、唯一分支约束、现存资料/旧Raw已删事实，以及新Agent必须继续原修复清单后真实重跑CI和oracle/scenarios。交接内容中不得把prepare当accepted/实施或把旧CI当最终验收。
- 此后本轮停止。原upload17label分组、受控XBRL、完整真实CLI CI/registry/proof/readiness交新Agent；本轮不开始其产品实施或附加资源调查。之前已取得G1–G5/XBRL/CI准备资料全部保全供交接，不报其完成。

没有新业务裁决待问；本轮按当前明确授权执行。修复项始终先登记artifact/三controller，不因压缩遗失。

## Gateflow slice 切分原则（用户要求，后续 Agent 必须遵守）

- 以可验证行为增量为边界，不按模块、文件、owner 或技术层机械拆分；数量尽量少，每个 slice 必须值得一次 implementation pass 和一次 review pass 的门禁成本。
- 默认避免一个 WU 超过 3 个 implementation slices；超过时 plan 必须说明为何不能合并或减少。用户、design_doc 或上游 handoff 明确定义的不同规则/阈值优先。
- planreview 必须检查：是否过多、是否机械拆分、是否能够合并、gate 成本是否超过实现风险、是否诱发提前实施 future-slice work。
- 每个 slice 同时适合一次 implementation/review 并构成可验证行为；必须写清 id/objective/outcome、allowed files、依赖、精确 allowed changes、函数/调用链/数据流/状态/异常/不变量、非目标、验证与断言、completion signal 和 stop condition。
- 只能实施当前 approved slice，除非 accepted plan 明确允许一次做多个；scope 外项登记 residual/deferred follow-up，不顺带扩展。减少 slice 不等于跳过、合并或重排 Gateflow 门禁。
- 当前 F5 只有完整 F5-S1：四项必要修复及同次必要文档/导出维护集中交付，不按 finding/字段/文件另切 slice；剩余 WU 分组准备只是 proposal，须按上述原则重新绑定最终代码并正式 planreview。


## 最新审查路由（2026-10-02，覆盖旧路由）

用户指定双路同时并行审查改为 **MiMo / MiMo-flash**；gpt-6-sol负责plan/implement/fix，总控读取全部结构化结果和真实证据后独立裁决。全部通过 `$sub-agents` runner 子进程，显式绝对workspace，独立output/stderr、当前canary/no-persist。历史Kimi及ds-flash记录保持原样，后续不再默认派Kimi。
