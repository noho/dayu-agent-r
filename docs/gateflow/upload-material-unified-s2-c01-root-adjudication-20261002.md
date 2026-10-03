# S2 US2-C01 总控裁决：公司比较以受理时实际观察值为基准

## 范围与状态

本记录属于统一修复 WU 的 S2 implementation，不新增 slice、schema 或 gate，不表示 S2 验收通过。唯一工作区为 `/Users/leo/workspace/dayu-agent-r`，唯一开发分支为 `codex/upload-material-oracle`；核对时 HEAD 为 `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`。已接受计划 `upload-material-unified-repair-plan-20261002.md` 的 SHA-256 保持 `c99c35adba919a8baf371b0142e0ab1abf256a951e89b2fc15e8a2d38988e8ea`，不改写冻结计划。

## 已有裁决与直接证据

- `docs/reviews/upload-material-um-o33-oracle-adjudication.md`：相同 auto 请求在权威边界确认当前已发布 identity、fingerprint 和完整性相同后返回 skipped；不能把真实 I/O 或无法证明相同的状态改写为 skipped。
- `docs/reviews/upload-material-um-o12-oracle-adjudication.md`：公司名称由状态感知的公司 owner 判定，别名唯一性由发布 owner 保证。未要求保存首次公司创建的历史 provenance。
- 已接受计划 §6.5/§6.7：初始 company=None 时，允许公司 commit owner 对相同意图进行严格等价 no-op；**已有 company 输入时**必须检查原 non-identity snapshot，额外字段、时间或别名变化仍冲突。
- 实施者的真实 Fs 探针 `workspace/tmp/upload-material-unified-s2-implement-sol-20261002-01/company_history_probe.py`；票据 `company-history-probe-01/actual-exit.json` 记录 owned PID 25417、实际 exit 0。`company-history-evidence/single-create.json` 与 `create-then-refresh.json` 展示初始公司缺席、不同历史最终产生逐字段完全相同的当前 CompanyMeta。总控已读取探针、退出票据和两个结果。固定时钟仅生成对照历史，未替换仓储、merge 或提交结果；该探针不算 V11/V12 并发验收。

## 裁决

US2-C01 的不可观测性反例成立。把“额外时间变化拒绝”扩展成“必须识别受理时从未观察过的公司首次创建与所有中间刷新历史”，不属于已裁 O12/O33 或当前计划的验收承诺。该扩展要求裁为 **rejected-with-reason**；不为它新增公司 revision/provenance、source→company 历史关联或时间猜测。

按计划已有两个分支继续实施：

1. **受理时公司已经存在**：必须严格比较实际观察到的 non-identity snapshot。包括 updated_at 在内的额外变化不能被一般 resolver 同版 merge 分支忽略；相同材料也不能掩盖该冲突。
2. **受理时公司缺席**：只能由 material-specific 公司 commit owner，在其 writer/identity guard 下按已接受意图比较当前 canonical identity、名称等价、完整 aliases、resolver 及同意图 merge 结果；全部精确等价、无字段增量时，返回当前公司事实且不 stage/swap/刷新时间。任一不等、非法别名或不完整事实仍拒绝。材料发布阶段消费该 owner 的最终公司事实，不从公司/source 时间推断历史。

第二分支的“无额外变化”指当前事实相对同一已受理意图没有额外字段或合并增量；updated_at 没有初始观察基准时，不增加不可观测历史判别。现有公司分支的时间漂移校验继续保留。该解释直接来自计划中明确的 initial-None 例外与已有-company snapshot 条件，不另裁用户可见行为。

## 实施与验收要求

继续一次集中完成 S2 剩余 state/publication/callers、八格 amended、job/read 投影和 V7–V14；不得把独立删除/strict-reader 改动当完整 S2。补 owner 级测试分别验证上述两分支、额外字段/aliases/resolver 不等拒绝、现有公司仅时间变化拒绝及 initial-None no-op 不改业务字节；真实双 CLI old-admission barrier 和实际生产转换/仓储仍必需。

本次不是新增修复项，反例与裁决已登记以避免压缩遗失。实施者尚在运行，总控不修改其冻结输入、源码或报告；取得进程终态并核收后，将本裁决和完整剩余 S2 任务交接给 gpt-6-sol 继续同一 implementation gate。S2 全部完成后再由 MiMo/ds-flash 双路独立审查。

## 残余风险

当前 contract 不提供初始公司缺席前后的不可观测历史审计；该能力属于当前 WU 非目标，不列作已实现。已有公司漂移、当前 aliases/身份/完整性和真实 I/O 边界仍属于 S2 必须验证的条件。本记录没有延期任何已接受修复，没有改写正式 oracle/scenario registry。
