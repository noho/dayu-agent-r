# 601225-annual-fulltext：plan fix r1 交付

- Gate：`plan review → fix`；本 artifact 是计划修订交付，尚无 re-review 验证，不自判 plan pass。
- Work unit / binding scope：`601225-annual-fulltext` / [目标确认](601225-annual-fulltext-goal-confirmation-20261012.md)。
- 分支 / HEAD / base：`fix/601225-annual-fulltext` / `7637bb0b4fbca212a4db0f4cfc09655e66516695`。
- 输入：[总控裁决](601225-annual-fulltext-plan-review-adjudication.md)、[MiMo review](../reviews/plan-review-20261012-131413.md)、[DS review](../reviews/plan-review-20261012-131414.md)、现有 plan/root-cause-evidence、AGENTS.md 及相应 owner 代码。
- 修改：[实施计划](601225-annual-fulltext-plan.md)；新建本文。root-cause-evidence无需追加，其根因与原始证据边界未变。
- 原 plan SHA256：`843b4a880fb6fd36b755f2efa2b33ec169f77f6e95824fed67100a93ffecfd79`；修订 plan SHA256：`37663c068ee5d6b3f39fd60642ecf4c8c134ff760d0649a0fe12c8a0bef34855`。
- 旧 plan 副本：`workspace/tmp/601225-plan-fix-r1/plan-before.md`。本轮保护性 hash、探针、结果都在该独立目录，旧证据记录未覆盖。
- 权限边界：没有生产代码/测试/依赖/README 修改，没有 commit/push/PR；没有改调用方目录、原证据、其它 review artifact 或总控 state；没有启动、运行、clear、等待或中止其它 Agent。

## 动机与 owner 核对

原修复动机成立：当前原参数返回全文但错财年分组淘汰，CN 财期身份又让 COMPLETE 摘要阻挡全文；无需重做官方取证或基线测试。review指出的是新增facts获取路径的顺序、同源键、publication连续性和验收证据缺口，不能借修计划扩历史恢复/一般日期/OCR/其它公告。

已直接核对 `source_integrity.py` 的 unsafe→multiple→unselected/rejected→selected 顺序，`read_source_meta_integrity_view` 同窗 entry 的实际字段 `integrity`，snapshot.revision/资源生命周期/完整文件物化合同，CN/HK discovery / result / candidate 构造与全部调用点，filing A/B、retry三轮、rollback、runtime失败投影，以及CLI现有进度与diagnostics输出。修订明确各语义仍由这些owner产生；新增local witness只绑定本次facts的opaque revision，不产生storage写授权或公开schema。

## Accepted findings 修订映射

下表只报告提交的具体修订，不改总控 finding 裁决或最终状态；总控现有 artifact 的 accepted 项仍为“未修复”，须待两路同版 re-review 验证后回写。

| 总控 finding | plan 修订位置 | 具体规格与验证要求 |
| --- | --- | --- |
| DS1 / MiMo3（facts失败作用域） | P3.5；P5.1/P5.3；P7 | 准入FY facts获取/解析不能确认时显式整次discovery失败，H1/Q也不发布，不猜年/静默排除/新partial或uncertain；protocol分别说明facts discovery和selected transport的失败作用域；端到端坏非目标FY+正常目标/H1Q，typed安全诊断、无FILING_STARTED、全部来源/公司零业务写入、无半成品。 |
| DS2（旧损坏摘要/repair） | P3.1；P4.2–P4.4；P5.3；P7 | COMPLETE摘要保留而全文独立；被排除损坏摘要是UNSELECTED_REPAIR_REQUIRED，真实accepted/rejected集合保持，不自动修/删/覆盖；可信同key selected全文repair由原gate/A-B收口，prepared可用且不二次GET；未知/损坏identity不依财期槽猜source，历史错年/损坏恢复不作全历史不变承诺。 |
| DS3（repeat实际集合） | P6.2–P6.3；P7风险表 | 官方集合不变时clean repeat实际PDF GET集合={1204545056,1209875597,1213161682,1223301999}；seeded={1204545056,1209875597}；逐项≤1，其它已持合法COMPLETE及三目标0GET/0conversion。明确1204545056是275页落选全文，保留成本，不加持久cache；脚本实际transport/wire集合与预期相等对账。 |
| DS4（依赖真源） | P1；P5.5 | 仅pyproject声明pypdf范围+common lock固定6.1.3；requirements不改。实施按平台约束安装、pipcheck、版本/strict type验证。 |
| MiMo1（提前inventory/I-O/取消/snapshot） | P3.1–P3.4；P4.2–P4.4；P5.2–P5.4 | 无写权限inventoryhelper只拒绝无需candidate可判的unsafe/多repair，final classifier复用且新窗真实selected检查；本地新增字节读取限定FY有效窗；同entry→fullsnapshot revision/identity核对，metadata/locator/bytes同snapshot；逐checkpoint和异常优先级固定；selectedrepair prepared使用与发布门、A/B变化/retry丢弃/rollback明确。 |
| MiMo2（source key与locator） | P3.2–P3.3；P4.1–P4.3；P5.2/P5.4；P7 | local/identity/COMPLETE唯一键统一(provider,source_id)；URL只是实际取得原件的locator。合法同源COMPLETE对scheme/path与远端same/differentbytes不GET、不改旧locator/meta，非overwrite不承诺刷新；本地facts witness遇真实publication变化typed停止，不能旧facts报当前成功。 |
| MiMo4（首页grammar） | P2.2；P5.1 | 物理行保留、闭合suffix fullmatch，识别直连/普通及全角括号/方括号摘要、可选冒号；未知/错括号/摘要版等拒绝，跨行残留摘要不默认为full；全部13官方原文正例及必要合成语法反例明确，无泛化标签/OCR。 |
| MiMo5（新路径测试/独立实际GET） | P3.3/P3.6；P4；P5.2–P5.4；P6.1–P6.3 | local/prepared/originalGET三个独立boundary matrix，逐候选/来源/URL/SHA/size/重复、provider/parser/converter/cancel、repair/unsafe/A-B/retry/rollback断言；不用旧注入点代替新路径。选定仅子CLI PID的scoped sitecustomize，原HTTPTransport和真实HTTP11发送头完成双观察、原Response原bytes透传，POST应用实际raw保存；真实bareCLIargv、输入/输出/退出与失败判定已固定，debug仅diagnostic。 |
| MiMo6（rejected-with-reason的澄清义务） | P1/P2.1；P3.3/P3.6；P5.1 | 沿总控rejected决定保留shared typed local/prepared/witness交付和既有fiscal_year_source准确取值；不拆新市场protocol、不加CLI/provenance字段、无shim/新默认兼容。完整列生产两实现、workflow唯一调用、selector/result/candidate、五个fake和直接tests迁移；HK原行为/空新增输入输出有明确不变断言。 |

新增`CnAnnualReportPublication`与result里的selected local witnesses是MiMo1/2/5要求的最小连续性证据：只有本次local facts产出的selected候选持有，A期核revision；不写库、不对LLM暴露、不引入任何恢复/新市场目标。不能将这项事实绑定交给implementation再发明。

## 实际 probe、记录与未运行项

本轮先创建独立`workspace/tmp/601225-plan-fix-r1/`并保留plan-before/protected-before。所有探针读取现有官方原件，无新官方HTTP请求，无受管财报写入。激活`.venv`后实际运行如下：

| 命令 / 记录 | 实际退出与结论 | 证据边界 |
| --- | --- | --- |
| `PYTHONPATH=. python workspace/tmp/601225-plan-fix-r1/probe_contracts.py`；`contracts-probe.log` / `contracts-probe.json` | 0；用既有临时pypdf6.1.3读取13官方原件首页，新封闭文字grammar13/13；9合成正例接受、13反例拒绝；现有纯finalclassifier重放unselected_summary→unselected_repair_required、selected→repair_selected、unsafe优先、multiple拒绝 | grammar临时原型和基线pureclassifier行为；未实施生产parser/helper，非owner回归通过证明 |
| `python workspace/tmp/601225-plan-fix-r1/probe_observer.py`第一次；`http-observer-probe.jsonl` / `bare-cli-help-observer.jsonl` | 0；实际loopback原件bytes/SHA、POST原bytes不变，transport两次；grandchild另一次真实GET未被hook记录；真实`.venv/bin/dayu-cli download --help`退出0且装载hook | 只验证透明进程observer机制；非官方download |
| 同命令第二次，补真实sendheaders观察；`http-observer-wire-probe.jsonl` / `bare-cli-help-wire-observer.jsonl` / `observer-probe.json` | 0；实际origin两父请求+一grandchild请求，父CLI机制scope内transport=2/wire_sent=2；httpx0.28.1/httpcore1.0.9；原件SHA=`ddc094e2cd9610e1293fe9ee5a99f894646e37d4541a5ba0292ac25e7ad7a2d3`；POST原bytes相同；bareCLIhelp0且零transport | 原件是probe自己loopback返回值，不是官方PDF；不证明clean/seeded/repeat零GET |
| 直接代码/签名读取 | scope/field/生命周期/调用点和现有public diagnostics字段核对；没有行为替换 | 未把staticread冒充新代码runtime验证 |
| 文档链接/内容和受保护hash核对 | 见`document-check.json` / `protected-after.json` | 仅文档完整性/越界检查，不是planreview |

没有重跑已证官方取证、432不变基线tests或pyright，没有安装/修改venv依赖。本轮没有生产代码或tests改变，不能宣称新矩阵/coverage/类型检查通过；这些都是P5.5列明的实施必做项。

**尚未运行/完成**：生产facts/DTO/helper/acquisition/identity/A-B修改；对应owner tests和三个boundary matrix；依赖安装/pipcheck/pyright/逐文件coverage；正式utils验证辅助；四次真实公开download、真实Docling与source读回/repeat实际GET集合对账；实施后README；双路同版re-review。临时probe能支撑规格收敛，但不能替代其中任何一项。

## Docs决定

本轮只改plan/新fix artifact，根因报告不变。根README、Fins README的Agent更新约束和tests README现有事实边界已读，P7规定**实施后**按用户下载/排障、Fins机制和落地测试三种读者职责分别更新，包括整次facts失败与损坏摘要历史恢复限制。现在能力未落地，不能把计划写为README当前能力。无分层/装配/入口参数变化，dayu/README和Engine/Host/Config README不触发。

## 分类 residual risk / owner / destination

| risk / 未覆盖 | 分类 | owner / destination | 是否阻塞及处置 |
| --- | --- | --- | --- |
| accepted项文档修订尚未复审 | fixed in current slice（plan fix责任，非已通过） | Sol/总控 / 本plan、本文、两路re-review artifacts | 总控核对实际退出后派同版MiMo/DS；不自放行 |
| 生产实现/新路径矩阵/依赖/type/coverage/docs未运行 | fixed in current slice（S1责任，尚未实施） | 实施Agent / S1 implementation/checks/code-review | 实施后必须闭环 |
| observer正式工具与四次真实CLI/真实Docling未运行 | fixed in current slice（验收责任） | 实施/验收Agent / P6四场景日志、http summaries、verify/compare | 机制probe不足以pass验收 |
| 旧损坏摘要被排除、未知identity/历史错年自动恢复 | assigned to later work unit | Fins完整性维护者/总控 / 独立历史完整性任务 | 本轮expected typed失败+零写；无rebuild承诺、不扩恢复 |
| 落选全文/摘要repeatGET成本 | assigned to later work unit | Fins维护者 / 后续按需性能任务 | 本轮精确核集合，不新cache |
| 扫描/OCR/跨行或未知布局、其它公司/公告 | assigned to later work unit | Fins年度事实维护者/总控 / 独立发现任务 | 未可靠facts整次失败；影响已确认目标则具体blocker |
| 历史启动树/raw缺失 | assigned to later work unit | 总控 / 原根因证据边界与后续可追溯任务 | 不伪造，不影响当前重复链 |
| UTC/本地披露日偏差 | assigned to later work unit | Fins日期维护者/总控 / 独立日期任务 | 当前目标远离边界；不扩一般日期 |
| origin集合/内容/网络/Docling变化或HTTP锁版本不符 | fixed in current slice（验收裁决责任） | 实施/验收Agent/总控 / 实际差异记录与裁决 | 保留真实差异，不降低验收、不无证计0GET |

当前未发现必须扩binding goal或变更storage schema才能实施的具体blocker。这个判断只表示规格可在授权owner边界内实现，**不表示accepted findings已修复通过或实际验收完成**。其余不变风险仍按原根因/裁决归属，无unclassified residual。

## 交付与总控下一动作

本轮交付仅为plan与fix artifact；不推进state。总控以本次运行实际退出及上述文件/保护性核对为准，随后同时派MiMo/DS复审相同plan hash。若复审仍有accepted未闭环项，继续总控裁决的plan fix；本artifact不得替代re-review或accepted-plan commit。
