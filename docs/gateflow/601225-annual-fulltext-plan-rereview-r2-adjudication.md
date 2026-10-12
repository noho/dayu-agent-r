# 601225-annual-fulltext：plan r2 re-review 总控裁决

- Gate：re-review → fix（r3，仅规格澄清）；尚未放行 implementation。
- target plan SHA256：5b506a9dca7af364e8b85f7ba3d12f38dc84b972bbb476f1c1150e420a4c4ae8。
- 两路实际退出0/completed；MiMo artifact153909为fail，DS153910为pass。已读两份，四项r1 accepted均有同版“已修复”证据，保持该闭环，不重设计。
- 新MiMo-r2-01 canonical covered periods：accepted，严重度裁决为低，状态未修复。它是code-generation-ready表述缺口，不是已证生产bug，原“高/所有合法增量都会失败”是假设实现者忽略现有writer与正向测试，严重性被高估。现写入owner已经明确covered_fiscal_periods=list(candidate.period_projection.covered_periods)，只需准确补同一真源表示，不引入新schema、helper abstraction或tuple兼容读取。

## 唯一修订

P4 publication匹配的canonical投影明确为meta['covered_fiscal_periods'] == list(candidate.period_projection.covered_periods)。持久侧必须是JSON list，非空、只含canonical期间字符串、顺序固定、无重复且与candidate投影完全相等；缺失/非list/空/未知/重复/顺序或值不一致统一period_metadata_mismatch。不能把坏持久tuple转为list继续接受。P3 expected_meta与snapshot同版比的是两份raw JSON表示，不拿candidate tuple拼接；保持HK现有list(...)语义。

补真实Fs合法['FY']与candidate('FY',)的COMPLETE skip，以及direct owner非法容器/缺字段/空/重复/乱序或extra期间反例；tests跟owner而非fixture兼容。原helper/类型/异常作用域/读取/observer/identity/grammar/GET集合不改。

顺带收束两个非阻塞OQ而不新增产品目标：

- 当前source_url只在local原件读取中保留实际取得时locator、不作身份或发起HTTP；明确精确非空string predicate（不trim/normalize重写，不从它反推source/year），不引入URL兼容或provider协议新规则。远端URL仍由现有provider owner产生/消费。
- P6“有效Docling”明确schema-valid与最小内容sanity区别，三完整年报实际转换应有非空body引用与至少一个非空文本item，核真实SDK字段；不要求财务表/数字提取或转换准确性研究，不扩财务数据处理。模型页、origin、两hash、fingerprint及真实转换进度仍必要；不能把仅空模型/pages当完整年报可消费产物。

## 边界、风险与下一入口

Sol仅修plan/新r3 fix artifact，禁止生产/测试/依赖/README实现与commit。新accepted项归fixed in current slice（plan fix/re-review责任，未修复），owner Sol/总控，destination r3修订与双路复核。旧风险分类/owner/destination保持；无新的业务目标、source owner或范围阻断，无需用户重新goal确认。

current gate / next entry point：fix（plan r3）；完成后两路聚焦同版复核，accepted全闭环后accepted plan commit。artifact：docs/gateflow/601225-annual-fulltext-plan-rereview-r2-adjudication.md。


## 总控最终回写（r3 同版复审后）

本轮历史结论保留；最终 finding 裁决与逐项状态以 [最终 plan 裁决](../gateflow/601225-annual-fulltext-plan-final-adjudication.md) 为准。全部 accepted 项已由后续双路同版复审验证为计划层已修复；MiMo-06 rejected-with-reason / 证据失效维持。r3 两路均 pass，不代表实施或真实验收完成。
