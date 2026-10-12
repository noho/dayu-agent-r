# 601225-annual-fulltext：plan review 总控裁决

- Gate：plan review → fix；当前 plan 不通过，修订后必须双路 re-review。
- Binding scope：601225-annual-fulltext-goal-confirmation-20261012.md，用户已确认且明确财年原文证据、不伪造历史 raw、不扩一般日期/其它公告。
- 被审计划 SHA256：843b4a880fb6fd36b755f2efa2b33ec169f77f6e95824fed67100a93ffecfd79。
- MiMo artifact：docs/reviews/plan-review-20261012-131413.md（fail）。
- DS Flash artifact：docs/reviews/plan-review-20261012-131414.md（pass-with-risks）。
- 总控已读两份 artifact，核对 source_integrity.py、identity、protocol、filing A/B、requirements 单一真源等代码；DS 的条件性结论不足以放行 accepted 未闭环项。
- 两路意见不以多数表决；下列裁决基于直接语义 owner 与用户 scope。

## Finding 裁决与必须修订的决策

| Finding | 裁决 | 当前最终状态 | 修订要求 |
| --- | --- | --- | --- |
| DS-1 / MiMo-03：原文失败作用域 | accepted | 未修复 | 明确 FY facts 属于 discovery 完整性判断，不能猜年或静默丢候选；维持显式整次发现失败，修订旧 protocol 的候选传输隔离承诺及文档，补真实 workflow typed失败、既有来源零变更和无半成品断言。不要新增 CN uncertain / partial schema。 |
| DS-2：损坏旧摘要与 preflight | accepted（边界澄清与测试） | 未修复 | 维持正确选中来源语义：COMPLETE 摘要独立保留；已被选择排除的损坏摘要为 unselected repair，沿既有 typed拒绝，不塞 accepted/rejected 绕过，不自动重下摘要/覆盖/删除。明确这不是所有历史损坏数据自动修复承诺；可信同来源选中全文的 repair 必须继续受原 owner 收口，并测完整/损坏两类。未知/损坏身份不能靠财期槽猜 source。 |
| DS-3：再增量重复获取口径 | accepted | 未修复 | 当前官方集合不变时，clean repeat 允许非持久化候选 GET 集合为 {1204545056,1209875597,1213161682,1223301999}，seeded repeat 为 {1204545056,1209875597}，每项最多一次；三目标及已持久完整源零 GET/转换。明确包含落选全文，记录成本；不新建候选持久缓存。验证脚本比对实际获取记录，不只描述“可能”。 |
| DS-4：依赖单一真源 | accepted | 未修复 | 只在 pyproject 声明、公共 lock 固定 pypdf；requirements.txt 不改。安装后 pip check 与 strict type 验证。 |
| MiMo-01：读取顺序、repair、取消、snapshot | accepted（具体顺序与验证） | 未修复 | 在年度原文读取/远端 PDF GET 前，经 source integrity owner 拒绝无需候选即可判定的 UNSAFE/多处损坏；不要伪造 accepted 集合。必要时在 source_integrity.py 抽取无写权限的 inventory 检查供现有完整 preflight 复用，不改 storage schema/仓储实现。之后 final selected preflight 仍新窗检查。限定本地读取到请求 FY/窗口；精确写明 checkpoint、同一 snapshot 字节/元数据、prepared repair、异常优先级及发布变化处理；已读取原文不授予写权限。若本地 facts 与后来 A/B publication 不一致，不能把旧事实当当前完整源成功。 |
| MiMo-02：URL 与身份矛盾 | accepted | 未修复 | source identity 唯一键为 (provider,source_id)，URL 为取得原件时的 locator。local复用与 identity/COMPLETE 必须同键；同源 COMPLETE 不因 raw URL 改变而冲突、重取或改写旧 locator。非 overwrite 不承诺刷新同 source_id 的远端内容，保留原实际原件/locator。测 scheme/path 变化，以及远端不同 bytes 仍不触发合法 COMPLETE 刷新；A/B 同源一致。不要 loose URL parsing 或 metadata-only locator 更新。 |
| MiMo-04：首页括号摘要误判 | accepted | 未修复 | facts grammar 自足且封闭，识别普通括号/方括号摘要标签；未知后缀不得因“未紧邻摘要”默认为 full。给出精确解析规则与正/负例；仍以官方13份首页为主、合成语法反例为补充，不扩 OCR 或公告类型。 |
| MiMo-05：prepared/local/retry 与真实零GET证据 | accepted | 未修复 | 新 acquisition 路径各自覆盖身份/SHA/size/重复、取消、provider/parser/conversion失败、选中 repair、UNSAFE、A/B变化/retry丢弃及回滚；不能只说旧tests覆盖。真实 bare CLI 除现有 owner debug 外，用仅验证进程的 HTTP 请求观察/透明转发记录等独立实际网络证据核对 GET 集合，保持真实origin响应，不换业务结果、不绕公开入口、不观察其他任务。允许新增独立 utils 验证辅助；不为验收扩生产计数/schema。 |
| MiMo-06：共同协议/既有provenance值范围漂移 | rejected-with-reason（保留必要变更，澄清文案） | 证据失效 | 协议已有跨市场 local_annual_ends 显式输入；direct typed local原件/prepared handoff 是避免重复GET所需，分裂protocol/adapter会增加层与专用dispatch。持久字段 fiscal_year_source 已存在，若从原文得年却仍写 title_or_category_inferred，会违反同源事实约束；准确改取值必要。无新增CLI/provenance公开字段。要求完整调用点迁移清单及 HK 行为不变断言，禁止 shim/default兼容。 |

MiMo-06 的 rejected 是对“这些改动必然超出 scope”的判断，非否定需要核对耦合和迁移。公开结果 prepared字段用于同一次 acquisition 的明确跨 owner 交付，没有新市场业务目标；fiscal_year_source 只纠正既有事实来源，不新增用户验收标准。无需重新 goal confirmation。

## 修订边界与实现前条件

只派发 Sol 修订 plan 与 fix artifact，不实施生产代码/测试、commit 或 PR。新增允许边界仅为上述必要的 source_integrity owner 窄纯函数、对应 owner tests，以及独立 utils HTTP 验收观察辅助；不放宽原 source 完整性合同、不扩一般 repair/日期/其它公告，不采用仓储 callback/fallback 逃避 owner。

Sol 必须把每项决策写成 code-generation-ready 的接口/状态机/错误/测试规格；如果任何要求只能通过扩大确认边界或无可靠 owner 实现，报告具体 blocker，不发明方案。修订后两路 planreview 复核同版，accepted 项全为已修复才通过；不存在 accepted-with-note 放行。

## 残余风险、验证与下一入口

- 原 plan 的历史 raw/启动树、日期偏差、OCR/其它公告风险维持 assigned to later work unit，owner 总控/Fins维护者，destination 原根因文档及后续独立任务；不改变本次三全文验收。
- 非持久淘汰候选 repeat 获取成本：assigned to later work unit，owner Fins维护者，destination 后续按需性能任务；本轮仅如实核对允许集合，不增加缓存目标。
- 被排除的损坏摘要/未知旧身份安全恢复：assigned to later work unit，owner Fins完整性维护者，destination 独立历史完整性任务；本轮必须有安全失败与零写入证据，不承诺 rebuild 可自动解决。
- accepted plan findings：fixed in current slice（plan fix/re-review 归属，尚未修复）；owner Sol及总控，destination 修订plan/fix/re-review artifacts。
- 实际验证：总控核对134条manifest hash全部保持；基线432测试、pyright 0；pip check退出0。修复尚未实现，真实CLI尚未验收。
- 当前 current gate / next entry point：fix（计划修订）；状态完成判定须以两个 runner 实际退出、修订 artifact 及双路 re-review 为准。
- 本 artifact：docs/gateflow/601225-annual-fulltext-plan-review-adjudication.md。


## 总控最终回写（r3 同版复审后）

本轮历史结论保留；最终 finding 裁决与逐项状态以 [最终 plan 裁决](../gateflow/601225-annual-fulltext-plan-final-adjudication.md) 为准。全部 accepted 项已由后续双路同版复审验证为计划层已修复；MiMo-06 rejected-with-reason / 证据失效维持。r3 两路均 pass，不代表实施或真实验收完成。
