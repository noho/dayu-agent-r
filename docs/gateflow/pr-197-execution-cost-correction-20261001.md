# PR197 执行成本纠正

用户指出已执行八小时仍未完成原PR findings。root确认：F2/F3/F4/F7代码修复已接受；F6代码已接受，唯一AG-A1类docstring修复候选等待MiMo25203/Kimi91784终态；F5代码尚未实施，Q1业务选择未答。不得把后续PR门禁与真实代码未修混为一个进度数。

执行修正（不改变用户裁决或Gateflow通过条件）：

- 非关键报告计数、历史head、模型自报、缩略argv等问题在root裁决中收窄可信声明；必要证据已独立复核时，不再派发报告修复循环。
- 已完成的测试与覆盖率按实际源码/执行AST身份复用；只有具体剩余风险或必需门禁才补验证。不重复同一矩阵来增加通过票数。
- F3/F4/F6/F7的后续同版PR review使用一组MiMo/Kimi并行审查，以逐WU目标/源码/依赖映射分别记录结论，root分别裁决各WU；不机械为四项派四组全PR审查，也不以组合通过冒充其它未修项目通过。各WU gate仍保持artifact、finding裁决和closeout要求。
- 已启动runner继续通过托管句柄核收；不依据空文件或运行久认定死亡，不为抢时间重复派发同任务。两路同版意见及root必要证据未齐前不放行源码。
- F5只等待真正缺失的业务选择；原上传队列和最终真实CLI CI不得靠替用户选择、修改oracle或扩大修复范围提前启动。最终CLI新matrix/oracle/scenarios/readiness仍必须完成。

下一入口仍是F6 AG-A1双路复审核收→必要源码accepted deepreview commit/push→F3/F4/F6/F7同版组合PR review/分别closeout。F5回答到达后由Sol固化既有N01/N02及Q2/Q3合同，完成必要计划/实现/双审。该记录是root编排成本纠正，不是新产品WU或门禁豁免。

## 用户追加实施约束

用户明确要求：后续WU也如此，实施slice不要切分太细。默认单一完整可验证行为增量；只有实际依赖、隔离风险或独立验收边界需要时才拆，plan写具体理由；禁止按文件、模块、技术层或零碎文字机械拆分。相关必要修复在同一gate汇总后一轮交付/同版双审。此约束必须传入后续Sol plan/implement/fix prompt及MiMo/Kimi planreview prompt，planreview挑战不必要拆分；不因此省略必要Gateflow门禁。
