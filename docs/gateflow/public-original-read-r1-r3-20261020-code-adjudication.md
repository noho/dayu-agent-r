# R1–R3 完整代码审核裁决

当前 gate 为 `受影响面 re-review`：D3 窄修已实际交付并验证，尚待指定 MiMo/DS 双路核销，**不放行 PR**。D1/D2/D4/C1/C2/C3/C4/M1/T1/T2/L1 前轮已核销，D3 正式状态仍为部分修复。最新安装边界见 authorization-update.md，历史通知保留。

## 首轮完整审核裁决历史

当时双路已实际退出，完整 final/报告已读取；正式裁决完成，所有 accepted 项仍未修复，放行指定 gpt-6-sol 执行范围内 fix，**不放行 PR**。MiMo 外层/runtime 0、success、2172.731475 秒，[报告](../reviews/code-review-20261020-135446.md) 为 pass-with-one-finding；DS 为四项 material findings。两路独立核验同一冻结版本；主控检查 MiMo 工具轨迹，无打开另一路本轮报告/本裁决的命令。MiMo Scope 的无 untracked 描述仅属于早期清单，后续主控过程文档及 DS 报告新增均未改变生产源码；源码/测试版本一致。

审核版本：HEAD `cd37d5759b1152eb1571fd410ff6275c30c83e25`，base `8bf8daec8a022fd705e6cfe32c4283605f1fe6ca`，完整 diff/可取回版本见 control 第 5 节。源码保持冻结。DS 原始日志 `workspace/tmp/public-original-read-r1-r3-20261020/code-review-ds.jsonl/.stderr`，外层/runtime 均 0、success、1665.633812 秒；完整 final 与 [报告](../reviews/code-review-20261020-134629.md) 已读。DS 的 rate_limit/模型名称观察不改变真实退出或本轮报告；无自动重派。

## 正式 accepted 清单

| ID | 来源 | 裁决 / 修复状态 | 根因、正确 owner 与必要修复/验证 |
| --- | --- | --- | --- |
| D1 | DS Finding 1 | accepted / 已修复 | 原文 processor 错把技术 target 当资产内 ID 命名空间。按当前资产 exact ID 与期望元素类型解析 context/continuation，重复 ID 才 ambiguous；保留 fact target_raw/origin。主控另下载实读 FRC 指南，原文明确 resources/continuation/exclude 禁用 target、context/unit 进入所需目标，见 `workspace/tmp/public-original-read-r1-r3-20261020/inline-target-guidance.{pdf,txt}` 第 199–203 行。现有 target fixture 固化错误须迁移，不保兼容分组。已有 resource_target_* 字段可保留为原文声明存在/内容的投影，须说明不构成合法分组，不因语义修复删除已承诺原文。补 target fact + default resources + continuation 的公开入口、重复 ID/未决反例。 |
| D2 | DS Finding 2 | accepted / 已修复 | 懒 entry 发布后，诊断的 borrow.processor accessor 会构建未读 processor，违反零构建成本 owner 契约。诊断只能读取已完成 processor，未建就跳过；保持 revision 校验与借用资源收口。补枚举 B→A 坏 ref/table_ref 不构建 B 的实际 registry 计数回归。 |
| D3 | DS Finding 3 | accepted / 部分修复 | 原文 HTML 可省略闭合规则漏 head，合法省略 </head> 的 body 被当 head 子级且 complete。修复 head/本轮支持的可省略标签边界；其它无法确定的关系必须明确 partial/unknown，不能完整旗标下伪造父链；不引入浏览器 DOM 重建或平行 parser。补 head/body、行组及同类合法边界，XML 保大小写行为独立。 |
| D4 | DS Finding 4 | accepted / 已修复 | 新四 API 的 missing resource 语义在 runtime owner 未收束，落到旧工具 file_not_found/ref 提示。按 accepted plan 返回 typed not_found，恢复动作为重枚举当前 namespace 的 exact 资产；区分参数错、版本错、解码/损坏，不能把这些都降格为 missing。补 Python/API 与实际 process tool 的缺失文档/文件 code/hint。 |
| C1 | 主控反例 + DS XML question | accepted / 已修复 | 格式能力由 suffix/media 判定，索引模式却只按 .xml。真实 public runtime 的 sample.xhtml/application/xhtml+xml 将 <P>A</p> 标 complete/explicit。原文 processor 的同一个格式 owner 决定能力与 XML/HTML 模式，复用 descriptor 的媒体声明，禁止下游单入口特例。证据见 [主控取证](public-original-read-r1-r3-20261020-controller-review-evidence.md)。 |

## 其余问题和必要验证的正式裁决

| ID | 来源 | 裁决 / 修复状态 | 直接依据与执行边界 |
| --- | --- | --- | --- |
| M1 | MiMo Finding 1 + DS leak gap | accepted / 已修复 | 工具扩至 13 后，completed_arguments/循环收缩为旧九，计划 §6.1-7 对四新工具成功/失败/取消的 nested 输出扫描缺失。实际四工具必须进入同一 owner 禁值扫描，允许 filename/hash/span 等解释清楚的公共标签，不放宽 local URI/path/revision/private key 禁值。静态未发现实际泄漏，不夸大为数据泄漏事故。 |
| C2 | DS close/lazy question + 主控同链路代码核证 | accepted / 已修复 | close 文档明确 active borrow 可以完成；三 lazy capability 构建完成后 _ensure_open 却拒绝已取得 borrow 的调用。补在 entry 已发布、active borrow 已取得后阻塞构建→close→释放 barrier 的真实公开入口回归；按 retired entry/borrow 的资源 owner 保留执行权与最终 release cleanup，关闭后新 read 仍拒绝。不得仅改文档撤销承诺。 |
| C3 | DS exact filename question + storage owner 核证 | accepted / 已修复 | storage 的合法单组件 filename 可含 [ ] * ?，枚举返回的受支持资产不应被 runtime 下游 glob 形状推断拒绝。移除额外限制，复用 source_asset_name_collision_key 的 owner 校验与原样匹配，仍拒绝目录穿越/非单组件/非原样值；补真实 Fs 枚举→回读。 |
| C4 | DS continuation completeness question | accepted / 已修复 | 同资产两 occurrence 后一条 continuedAt 未决时，第一页却 complete；当前 context 全资产校验、continuation 按返回页校验，形成同字段多义。明确 parse_status 为当前资产的解析/引用完整性，与分页分离；后续页的坏引用/歧义/循环/未知边界也不能让第一页冒充完整。复用同一索引 owner 校验，避免逐页重扫全文/长链 O(n²)，补跨页反例。 |
| T1 | DS facts paging gap | accepted / 已修复 | 新 offset/limit 必须实际跨页验证。补真实 process-backed Host 本页截断→一次省略 limit 的 fetch_more→next_offset 下一页，拼接 occurrence 无漏重。单页和 Python 正向不能替代。 |
| T2 | DS competing full snapshot gap | accepted / 已修复 | _borrow_processor full snapshot 在 creation lock 外获取，败方清理分支仍可达；现并发测试只验证能力单构建，不能代替两个 full snapshot 的竞争/loser cleanup。补真实仓储同步 barrier 和资源归属断言。 |
| L1 | DS LLM-facing/docs clarity | accepted / 已修复 | 按已承诺 schema 自足要求补 qname.status 枚举、attribute.quote/duplicate 含义、get_document_sections 的 source_asset 解释；provider/test 概览旧“九个”更新为实际工具集。不借此扩写无关文档。 |

## S1 itemless concepts schema：deferred-with-owner（非阻塞当前 draft）

两路均沿出站 serializer/共享参数投影/process/runtime 链核实内部可用，JSON Schema itemless array 合法，无本仓或已查公开文档要求非 strict 工具数组必须 items，也没有实际 provider 拒绝证据。条目业务 shape 在原文 runtime owner 严格校验、schema description 给出完整两字段和最小例。**不把未证实的 vendor 假设当缺陷，不为此扩建 dayu.runtime/Host 参数验证框架。** 前述部分裁决中的“拟支持对象 items”是未采用候选，不属于 accepted 修复。

- 正式裁决：deferred-with-owner；不是 accepted / 未修复逃逸，也不保留未解决的 needs-more-evidence 阻断本地 draft gate。
- 既有授权/非阻塞依据：当前 goal 成功标准是公开 DefaultFinsRuntime 与真实 process/Host 的读取契约；merge/live 安装与真实入口复验已明确分后续停点，未承诺当前开发树证明所有外部 LLM vendor 行为。有效出站 JSON Schema、严格运行时拒绝非法条目与已验证真实 process 链已满足当前边界；并无证据要求改变公共参数契约。
- owner/destination：Provider/Engine owner 与项目协作助手安排的调用方后续补验接续；最新用户纠正见 authorization-update.md。工程核收后本线只按 README 安装指定源码版本并检查自身公开入口（`dayu-cli --help`），报告命令/退出/commit/安装位置，不查调用方环境与入口，不把实际 LLM 出站/原失败用例变为安装门槛；若后续调用方发现拒绝，修在共享 schema/参数投影 owner 并复审，不能在 Fins consumer 下游 shim。
- 风险分类：assigned to later work unit（调用方补验接续已有明确 owner/destination，不新增本线安装门槛）；当前不声称实际 vendor 接受度已验证。

## 范围、计划与风险裁决

目标不变：保留原始声明和可回读定位，不做财报业务判断、不改 primary 或下载选文、不新增平行真源。D1 纠正技术规范解释，不删除已承诺原文声明字段，不扩大至跨资产 document set；不需要重新 goal confirmation。D3/C1/C4 是原文 processor 关系/完整性 owner 的范围内修复；C2/D2 是既有 lazy cache/borrow 合同的必要收束；C3/D4 是既有 exact 选择/错误契约修正。全清单作为一次范围内 fix，随后两路聚焦受影响面复审，不重做无变化部分完整审核。

除 S1 外，当前没有 deferred 的范围内已证缺陷或 needs-more-evidence 未决项；所有 accepted 必须修复并由双路复审核销。accepted 项风险归 fixed in current slice：11 项已核销，D3 仍为部分修复、由 gpt-6-sol writer/主控窄修，不据此提前标 pass。其余非目标/未覆盖风险沿实施回执/审核报告分类，owner/destination 不变；后续 gate 仍须核实际适用性。

## 其余边界

原样吞内容的任意长度裁剪未发现残留；DS 独立拼齐 ASML cold/warm 全文及 EOF，与原件相等。当前真实样本无 target，target 修复须新增规范有效合成输入；不以缺少 UKSEF 业务原件扩大取数范围。OLD 动态对照仍属后续差异任务，CSS/脚本、跨资产 inline document set、XBRL transformation/业务解释仍为明确非目标。merge 仍待用户另授；live 接续以最新用户纠正为准：工程交付后经 tmux 报 portfolio-manager，等待其核收通知，再按 README 安装指定源码版本并检查自身公开入口，不查调用方环境与入口，无需 merge，不额外业务回归。

## 第一轮受影响面复审裁决

- DS：会话 `16726` 外层/runtime 均 0，success，693.724303 秒；完整 final 与 [报告](../reviews/code-review-20261020-143203.md) 已读。
- MiMo：原会话 `15948` 实际 0/0、1224.371016 秒但无审核报告，不能放行；同 provider 补齐会话 `86892` 实际 0/0、success、2108.34396 秒，完整 final 与 [报告](../reviews/code-review-20261020-150149.md) 已读。未重派在途进程，原日志/错误/退出均保留。
- 两路独立对同一冻结 diff/源码取证，D1/D2/D4/C1/C2/C3/C4/M1/T1/T2/L1 均 accepted / **已修复**。其直接修复/验证证据见两报告逐项表、code-fix 回执及控制记录；34 文件可取回快照、API-8 的 182 模块指纹与当前树一致；所需受影响 tests、全量 pyright、完整文件覆盖率满足。旧完整集退出 1 的事实及测试边界迁移后的整文件 55 passed 原样保留，复用其余同版 1398 项，不伪称一次全绿。
- **D3 accepted / 部分修复，阻塞 review-pass**。原 head/body、行组等边界修复有效；`_HEAD_CONTENT` 缺少合法 head 子元素 `noscript`，触发同一个 `_close_optional` owner 提前闭合 head。DS 与主控用 `<noscript><link ...></noscript>` 的合法 head 输入，公开 Fs/runtime 分别证明省略 head 闭合时错误 parent+complete，以及显式闭合时误报 unmatched/partial。主控完整原始返回/源码 hash 在 `workspace/tmp/public-original-read-r1-r3-20261020/controller-noscript-probe/`。修复只补正确 owner 的合法内容边界并补省略/显式 head、body 对照真实公开入口回归；保现有 XML/partial/unknown/Host 交互。不加 DOM 重建、下游补偿或其它目标。
- MiMo 末句“无阻塞项”不能覆盖其 D3 部分修复的直接事实；按 Gateflow，D3 必须修复并双路复审核销后才可过 gate。其 noscript 探针内含 head 下的 p，不作为“合法 HTML”依据；本裁决使用 DS 与主控的合法 link 输入。
- MiMo 报告“API8 完成 182 次调用”混淆模块指纹数与调用数，主控以实际 receipt 的 **1774 次调用 / 182 个模块指纹**为准；L1 描述文本的实际 owner 为 `fins_tools.py`，provider 仅概览 docstring，主控已直接核实。保留独立报告原文，不沿用这两处笔误。
- MiMo XHTML context unresolved 疑点正式 rejected-with-reason：其旧探针将 URI 写成 `www.w3.org/2003/instance`，与真实 XBRL `www.xbrl.org/2003/instance` 不同；字节对照与正确输入公开入口 resolved 证明 owner 按元素类型拒绝无效引用是预期行为。不为错误探针增加生产 fallback。
- S1 维持 deferred-with-owner，原非阻塞依据/owner/destination 不变；实际 vendor 未验证，不追加安装门槛。验证复用/receipt head 标签风险为 fixed in current slice（已由实际 argv/退出、可取回源码与指纹核定）；其余非目标风险按既有 owner/destination assigned to later work unit，merge 仍另授权，安装仅工程核收并通知后执行。

本轮无需新增用户目标取舍；继续一次 D3 窄修与指定 MiMo/DS 双路受影响面复审。

### D3 窄修候选（待第二轮双路核销）

已读 code-fix-2 回执与完整实际diff，writer实际0/0退出。主控重核902份可取回快照/当前文件/manifest相符，99 tests、pyright0、完整文件97.2637%覆盖率及旧API8未受影响样本复用证据有效；生产仅同一owner集合新增noscript和意图注释，无runtime/Host/schema/存储改动。D3仍为accepted / 部分修复，正式改为已修复须收齐接下来指定双路受影响面复审的实际退出、完整final与报告。
