# UM-O18-F01 amended 单一发布事实 plan re-review 2（adversarial，MiMo）

- RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
- CANARY=mimo-9a523e3e
- Review 类型：planreview（adversarial plan review，独立审查，不实施任何 fix；单路审查，不构成 Kimi/MiMo 双路 gate 通过）。
- 审查对象：`docs/gateflow/upload-material-o18-amended-plan-20260929.md`，SHA-256 `162e28ca093379e55a7cd2f34b071169c54c4fd46caa6ad23cf5e70db5a03bc6`（预检一致）。
- 工作区：`/private/tmp/dayu-upload-o18`，分支 `codex/upload-material-o18`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`（预检一致），工作树仅含本 WU 预期未跟踪文档。
- Binding goal：`docs/gateflow/upload-material-o18-amended-goal-20260929.md`。
- 总控裁决：`docs/gateflow/upload-material-o18-plan-review-adjudication-20260929.md`（F1–F6 六项）；Sol 修订记录：`docs/gateflow/upload-material-o18-plan-fix-20260929.md`；上一轮 MiMo review：`docs/reviews/plan-review-20260929-044006.md`。
- 上游裁决只读来源：主工作区 `docs/reviews/upload-material-um-o18-oracle-adjudication.md`、`upload-material-um-o12-oracle-adjudication.md`、`upload-material-um-o14-oracle-adjudication.md`、`upload-material-um-o15-oracle-adjudication.md`。
- O12 跨工作区候选计划（只读核对）：`/private/tmp/dayu-upload-o12/docs/gateflow/upload-material-o12-company-plan-20260929.md`，SHA-256 `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60`，O12 工作区 HEAD `b201d9f3b1c84e49fe0751d75ea7dc31e2c0f14c`——与本计划 §2 引用一致。O14/O15 **无任何 plan artifact**，仅有 2026-09-28 oracle 裁决（UM-O14-F01/UM-O15-F01，均「尚未实施」）。
- 证据基础：plan/goal/裁决/fix/旧 review 文本 + 本 checkout 生产代码实读（引用行号均为本 HEAD 实读）。本轮只产出本 artifact；未修改 plan、产品代码、测试、README 或其它文档，未运行 pytest/pyright/coverage/CLI，未提交或对外发出任何内容。

## 1. 审查范围与重点

按任务指定重点逐一 adversarial 挑战 F1–F6 修订后的文本：O12 同版 guard 与 O14/O15 准入的「已集成硬前置」表述（禁止用未集成 O12 计划冒充现有 API）、active create-existing typed conflict 归属、`metadata_updated` 闭集终态与 requested/stored/LLM-facing 字段、requested/published amended 真源分离、真实双 batch A/B stale 守恒、`service_runtime` 实际符号与 prepare 期 material skip、tool schema 与完整实施白名单/逐文件 coverage/README、O13/O33/filing amended 边界。同时执行 planreview 标准 lenses（goal-bound minimal design、architecture boundary、best practice、optimal solution、overengineering、overcoupling）。

停止条件核验：计划 SHA/HEAD 一致；关键 owner（service_runtime、docling_upload_service、ingestion_runtime、storage、read_runtime、upload_tools、document_models）均有本 HEAD 直接代码证据；同版 guard 可表述（O12 计划「storage 同版状态与分阶段 guard」节定义了完整 business meta + opaque revision snapshot、材料 batch `expected_source_state` 与 guard 内全值比较）。停止条件未触发，本审查继续并完成。

## 2. Assumptions tested（修订文本关键假设与证伪结果）

| # | 假设 | 证伪结果 |
| --- | --- | --- |
| A1 | F4 已改为真实符号 `service_runtime._run_material_upload` | **成立**。`service_runtime.py:198` 为真实调用点；US 走 `sec_pipeline.upload_material`、CN/HK 共用 `cn_pipeline.upload_material`（:230/:251，market in {CN,HK}），实参列表确无 `amended`。旧符号 `_upload_material_with_pipeline` 全仓零命中，plan 已不再引用。 |
| A2 | `metadata_updated` 可作为新闭集终态映射 COMPLETED | **成立（可实施）**。现状 status 闭集为 `ok/skipped/deleted/failed`（`ingestion_runtime.py:264-267`），`_UPLOAD_TERMINAL_DISPOSITIONS`（:327-332）另接受 `cancelled` 并映射 CANCELLED；`FinsUploadTerminalDisposition.COMPLETED` 存在（:319-324）。新增 `metadata_updated`→COMPLETED 与现有映射结构兼容。 |
| A3 | 计数规则（ok stored=requested；metadata_updated/skipped requested>=1、stored=0；deleted requested=0；failed/cancelled requested 0+、stored=0）与现状校验形状兼容 | **成立**。`FinsUploadPipelineResult.__post_init__`（:1731-1738）现状即「ok→stored>=1，非 ok→stored=0」；`FinsUploadResultSummary.__post_init__`（:1853-1862）即「ok→requested>=1 且 stored=requested；skipped→requested>=1、stored=0；其余 stored=0」。plan 规则是在其上加 `metadata_updated` 一档并钉死 deleted/failed 的 requested，未与现状冲突。 |
| A4 | `_resolve_upload_status` 对 `metadata_updated` 原样透传 | **成立**。两处实现（`sec_upload_workflow.py:635-650`、`cn_pipeline.py:1901-1916`）仅把 `uploaded`→`ok`，其余原样返回，无需改动即可透传。 |
| A5 | 条件元数据发布没有现成机制：`replace_source_meta` 无条件、公开 meta 读取剥离 revision、commit guard 无条件 | **成立**。`_fs_source_document_core.py:950-958` 签名无 expected 参数；`_get_source_meta_unguarded`（:801-827）返回前经 `_source_meta_without_revision`（`_fs_source_integrity.py:1781+`）剥离 `_published_source_revision`（:67）；`_fs_storage_infra.py:676` `_commit_batch_with_publication_guard` 仅在 guard 内 swap，无 precondition 比较钩子。plan §2/§4.3 对此的描述准确，未冒充现有 API。 |
| A6 | skip/版本/身份事实与 plan 表一致 | **成立**。`_can_skip_upload`（`docling_upload_service.py:1616-1648`）只看 repair、overwrite、`is_deleted`、`identical_skip_safe` 与指纹，无 action、无 amended；`_resolve_document_version`（:1745-1770）初版 v1、异指纹/不安全升版、同指纹保版；`build_material_ids`（:1820-1856）seed 仅 form/name/fiscal。 |
| A7 | read/tool 现状与 plan 动机描述一致 | **成立**。`read_runtime.py:632` `_read_bool_meta_field(..., "amended", default=False)`（共享 filing/material 投影 `_parse_source_document_meta`，:607-637）；`upload_tools.py:276-278` 描述仍为「上传文件是否为修订版本。」；请求摘要裸键 `"amended"`（`ingestion_runtime.py:7812`）；`MaterialManifestItem` 无 amended 字段（`document_models.py:1029-1069`）。 |
| A8 | F1/F3 硬前置表述不冒充未集成 API | **成立**。plan §2 明示「该计划自身仍待双路 re-review，且这些接口在本 O18 HEAD 尚不存在」「必须已实施并集成才允许启动 O18 implementation」；O14/O15 裁决确为「尚未实施」且无 plan artifact。硬前置诚实地阻塞 implementation，但对 O12 消费面的具体描述不完整（见 F-1）。 |
| A9 | `metadata-only` 数据流可按 plan 文本直接实现 | **不成立（缺口）**。`_PreparedMaterialMetaMutation` 被指定携带「O12 公开的完整 expected source state（含 opaque revision…）」，但该 mutation 在 `prepare_upload` 内构造，而 O12 计划中 `prepare_upload` 只收 `previous_meta=admission.observed_state.source_meta`（business meta，revision 是 snapshot 的独立字段），plan §4.1 接口决策只列「携带 amended」——opaque revision 到达 mutation 的通道未定义（见 F-1）。 |
| A10 | skip 归属表述与 O12 前置契约一致 | **不成立（矛盾）**。O12 计划要求 skip 报告前 guard 内比较（证据表「skip 要在 storage guard 下验证 expected source 后才报告」、guard 节「material skip 无 mutation 时在同一 storage guard 下只读比较 expected source/company 后才报告 skipped」、验收矩阵 D「skip 漂移 → typed conflict，不虚报 skipped」），而 plan §4.2/§7 把 skip 的 stale 窗口划归 O33 并称「不声称这是 commit 时 canonical recheck」（见 F-2）。 |
| A11 | 状态机表覆盖同内容×标记×overwrite 全矩阵 | **不成立（缺口）**。表 row3 限定「非 overwrite」、row4（metadata-only）无限定、同内容同标记+overwrite 无任何行（见 F-3）。 |
| A12 | F6 命名规则（requested_amended/published_amended）可无歧义落地 | **部分成立**。job 请求摘要/started/结果三面可分，但 §3 禁令「不再向结果、摘要或 LLM 输出裸 `amended` 键」与同节存储 schema 裸 `amended`、read tool 现状输出键、tool 输入名、filing 请求摘要保留四项互相冲突，read 投影键名未钉死（见 F-4）。 |
| A13 | 白名单与验证配方完整可执行 | **基本成立**。14 个测试白名单文件全部存在；生产白名单各文件均可定位到 plan 声称的职责（含 HK 共用 `cn_pipeline`，无需独立文件）；逐文件 coverage 与 README 触发判定符合项目约束。小缺口：canary 各步 action 未钉死（见 F-6）。 |
| A14 | 双 batch 交错验收口径可履行 F3 证明义务 | **成立**。§6「A prepare metadata-only → B commit → A commit 必须 typed stale 拒绝且 B 事实不回退；单线程 stale 测不替代」与上一轮 F3 要求一致，且要求真实仓储。 |

## 3. Findings

### 1-未修复-[中]-metadata-only 条件发布的 O12 消费面不可按文本直接实现：opaque revision 通道未定义、注册契约只写了一半
- **位置**: plan §4.2（`_PreparedMaterialMetaMutation` 字段清单）、§4.3（「注册给 O12 材料 batch 条件提交」）、§4.1（接口决策只列 `prepare_upload` 的 material typed 输入携带 amended）；对照 O12 候选计划「storage 同版状态与分阶段 guard」节与 §67 行（材料 batch 注册契约）。
- **问题类型**: 不可直接实施 / 契约缺失
- **当前写法**: §4.2「仅标记不同构造独立 `_PreparedMaterialMetaMutation`，携带稳定身份、O12 公开的完整 expected source state（含 opaque revision、active、fingerprint、旧标记）及目标布尔值」；§4.3「把 admission 同版 snapshot 的完整 expected source business meta + opaque revision…注册给 O12 材料 batch 条件提交」。
- **反例/失败场景**: (1) revision 通道：`_PreparedMaterialMetaMutation` 在 `prepare_upload` 内构造，但按 O12 计划 `prepare_upload` 只接收 `previous_meta=admission.observed_state.source_meta`（canonical **business** meta）；opaque revision 在 `MaterialUploadPublishedState` 里是**独立字段**，且当前 `get_source_meta`/`_source_meta_without_revision`（`_fs_source_integrity.py:1781+`）会剥离它。实施 Agent 按 plan 字面构造 mutation 时取不到 revision，只能三选一：扩 `prepare_upload` 签名收 snapshot（§4.1 未列此接口决策）、把注册责任移到 workflow（与 §4.2「mutation 携带并注册」冲突）、或退回 `get_source_meta` 猜 revision——后者是 plan 明令禁止的旧陷阱。(2) 注册契约只写一半：O12 计划的材料 batch 注册是**两件套**——「注册 admission 的 `expected_source_state`（status、完整可信 meta、revision）和**公司阶段完成后**的 `expected_company_meta`（stage 取 `CompanyMetaCommitOutcome.company_meta`，keep/skip 取 admission.company_meta）」；plan 的注册描述只覆盖 source 部分，metadata-only 路径是否走公司阶段、company precondition 从何而来均未写。
- **为什么有问题**: 这是本计划核心新机制（metadata-only 条件发布）的输入面与注册面；plan 一面要求「O18 消费实际 public contract」，一面对该 public contract 的消费形状做了具体但不完整的预设（「O12 公开的完整 expected source state」≠ O12 注册契约的全部参数）。实施 Agent 被迫在核心路径 improvisation，或一进实施就误触发「O12 contract 不能表达→回 plan review」的停止条件——两者都意味着 plan 尚未 code-generation-ready。
- **直接证据**: plan §4.2/§4.3/§4.1 上述引文；O12 计划 guard 节注册契约引文与其「`prepare_upload(selection=admission.file_selection, previous_meta=admission.observed_state.source_meta)`」执行约定；`_fs_source_integrity.py:67/1781+`（revision 私有且读取时剥离）；`docling_upload_service.py:370+`（现 `prepare_upload` 签名无任何 snapshot/revision 输入）。
- **影响**: 实施 Agent 跑偏（非法 revision 推断或擅自改注册归属）/ 实施 gate 即停返工 / 条件发布缺 company precondition 成为并发覆盖缺口。
- **建议改法和验证点**: §4.2/§4.3 钉死二选一并写全：(a) `_PreparedMaterialMetaMutation` 由**持有 O12 同版 snapshot 的 workflow/准入层**构造或向 `prepare_upload` 显式传入 snapshot 的 typed 参数（在 §4.1 接口决策列出），mutation 携带的 expected state 含 opaque revision；(b) mutation 只带业务目标值，expected state（含 revision 与 post-company company meta）由调用方在材料 batch 注册时从 admission 提交。同时明确 metadata-only 路径的公司阶段与 `expected_company_meta` 消费方式（或写明 O12 实际契约允许免注册的条件）。验证点：实施前对照 O12 实际 public contract 的注册签名逐参数核对本节描述，缺参即停。
- **修复风险（低/中/高）**: 低（plan 文本补全；实现随 O12 实际契约）。
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-[中]-prepare 期 identical skip 的 guard 归属与 O12 前置契约互相矛盾：同一 skip 路径被同时承诺 guard 内验证与「窗口归 O33」
- **位置**: plan §4.2 尾句与 §7 第四条（O33 界限）；对照 O12 候选计划证据表、guard 节与验收矩阵 D。
- **问题类型**: 状态机漏洞 / 架构边界（归属矛盾）
- **当前写法**: §4.2「active、可安全同指纹、无 overwrite、标记相同时可在 prepare 期返回 identical `skipped`，不声称这是 commit 时 canonical recheck…O33 拥有一般 skip 的 prepare→commit stale 窗口」；§7「O12 guard 保护本项 metadata-only 条件发布；一般 prepare 期 identical skip 的 stale 窗口、success+skip 竞争…仍归 O33」。
- **反例/失败场景**: A 在 prepare 期以同版 snapshot 判定同标记→拟报 `skipped`（`published_amended` 取「既有发布值」）；B 并发切换标记并成功提交。两种读法行为分裂：(i) 若 skip 报告沿用 O12 前置契约（其计划明确「material skip 无 mutation 时在同一 storage guard 下只读比较 expected source/company 后才报告 skipped」「skip 的 expected 状态漂移 → typed conflict，不虚报 skipped」），A 应转 typed conflict，窗口实际被 guard 关闭；(ii) 若按 plan §7 字面把窗口留给 O33、skip 做纯 prepare 期 early return（「本请求无业务写入」），A 会向用户报出陈旧的 `skipped`+`published_amended`，正是 goal 要消灭的「请求/已发布事实分叉」。实施 Agent 面对互相冲突的承诺，测试要么固化 (ii) 的陈旧行为、要么按 (i) 断言 typed conflict 而与 §7 文本不符。
- **为什么有问题**: O18 把 O12 guard 列为硬前置，却在 skip 路径上不消费该前置并把其已解决的窗口转手 O33；同一业务事实（skip 时的已发布值）出现两种权威边界读法，违反语义所有权单一原则。注：总控裁决 F5 行有「其一般并发 stale 窗口归 O33，metadata-only 条件发布则由 O12 guard 保护」的表述，但该表述与作为硬前置来源的 O12 计划文本（skip 亦 guard 验证）不相容，需在 plan 层裁决调和，不能让实施 Agent 自行二选一。
- **直接证据**: O12 计划「`prepare_upload` 在 material 相同指纹 skip…skip 要在 storage guard 下验证 expected source 后才报告」「material skip 无 mutation 时在同一 storage guard 下只读比较 expected source/company 后才报告 skipped，不以空 batch 重发布 ticker tree」「**D** material skip 的 expected 状态漂移 → typed conflict，不虚报 skipped」；plan §4.2/§7 引文；当前 early skip 实现 `docling_upload_service.py:479-499`（prepare 期直接 return，无 guard 比较）。
- **影响**: 实施 Agent 生成错误 skip 语义（陈旧 skip 报告 / 或绕开 O12 前置契约）；用户可见 `published_amended` 与真实发布事实分叉；与 O33 双重跟踪同一窗口。
- **建议改法和验证点**: 在 §4.2/§7 钉死：identical skip 的对外报告**必须**经 O12 材料 guard 的 expected 状态比较后成立（与 O12 象限 D 一致），漂移转 typed conflict；§7 的 O33 界限改写为「该 guard 比较之外的线性化/重试/诊断问题」。若总控坚持 skip 不消费 O12 guard，则 plan 须写明这是对 O12 前置契约的显式偏离及理由，并把陈旧 skip 的后果列为已接受风险。验证点：Slice 1 增加 skip 路径的双 batch 交错（A 拟 skip→B toggle 并 commit→A 报 skip 前须 typed conflict）。
- **修复风险（低/中/高）**: 低（plan 文本；实现侧沿 O12 已有 guard 验证路径）。
- **严重程度（低/中/高/严重）**: 中

### 3-未修复-[中]-「同内容×标记×overwrite」矩阵覆盖不全：row3 排除 overwrite、row4 未限定，同内容同标记+overwrite 无行，canary 零覆盖
- **位置**: plan §3 状态机表 row3/row4/row6；§6 真实 CLI canary 九步。
- **问题类型**: 状态机漏洞 / 测试缺口
- **当前写法**: row3「active upsert `(F,vN,A)` + 同内容、同标记，**非 overwrite** → prepare 期 identical skip」；row4「active upsert + 同内容、标记不同 → **metadata-only publication**」（无 overwrite 限定）；row6 把「显式 create/update 的目标存在性、**overwrite** 与 tombstone 组合」整体交 O14/O15 准入裁决后，未说明准入放行（如 `create --overwrite`/`update --overwrite`）后落入哪条机制行。
- **反例/失败场景**: (1) active 目标、同内容、同标记、`--overwrite`：row3 被「非 overwrite」排除，row4 因标记相同不适用，row5/5b 因内容不变不适用——状态机表无行，实施 Agent 只能猜「全量重发布（现状 fall-through）」还是「skip」。(2) active 目标、同内容、标记不同、`--overwrite`：row4 字面适用（metadata-only、不重写文件字节），但 O14 裁决把 `create --overwrite` 语义定为「对已有目标明确替换」——显式替换却零文件写入是否成立未裁决；若 Agent 反向理解为 overwrite 排除一切元数据捷径，则 goal 的「同内容仅切标记保持原件、派生文件、fingerprint 与内容版本」在带 `--overwrite` 的 toggle 上失效。两实现对 `stored_file_count`、转换/文件事件、文件字节可见差异，测试只能固化猜测。
- **为什么有问题**: §3 自称「新发布契约与状态机」，toggle/metadata-only 是本目标核心行为，其在 `--overwrite` 维度上留白且 canary 九步（首发/toggle/skip/toggle/新内容/delete/恢复/新内容/fresh）无一带 `--overwrite`，实现与验证都无法可依、无测可锁。
- **直接证据**: plan §3 表 row3/row4/row6 引文；§6 canary 配方（无 overwrite 步骤）；O14 裁决「`create --overwrite` 可对已有目标明确替换：A05 证明…保留稳定 ID，内容升版且 meta/manifest 一致」；现状 `_can_skip_upload`（:1640）`overwrite or previous_meta is None → False`（现状 overwrite 即禁 skip，全量重发布）。
- **影响**: 实施 Agent 跑偏或两入口行为不一；`--overwrite` 路径的 toggle 达不到 goal 成功信号；测试固化偶然行为后返工。
- **建议改法和验证点**: 补齐 2（内容同/异）×2（标记同/异）×2（overwrite）矩阵全部八格的 owner 决策（或显式规则「overwrite 只影响准入与 skip 门，不改变 metadata-only 判定」）；§6 canary 增至少两步 `--overwrite` 对照（同内容同标记 overwrite、同内容切标记 overwrite），断言逐格 stored/事件/文件字节/版本。验证点：八格各有 owner 测试，Slice 1 验收组点名 overwrite 维度。
- **修复风险（低/中/高）**: 低（plan 文本 + canary 两步）。
- **严重程度（低/中/高/严重）**: 中

### 4-未修复-[中]-已发布事实的 LLM-facing 命名规则自相矛盾：禁令、存储 schema、read 投影、tool 输入、filing 请求摘要五方键名未统一收口
- **位置**: plan §3 命名句与 schema 句、§4.5 read 投影句与 tool schema 句、§6 入口测试「禁止出现边界」；对照 `read_runtime.py` 现状输出键。
- **问题类型**: 契约缺失 / 自相矛盾（请求字段与持久事实分界的命名面）
- **当前写法**: §3「请求/started 只命名 `requested_amended`，已发布事实只命名 `published_amended`；不再向结果、摘要或 LLM 输出裸 `amended` 键」；同节「新 material source meta 的 `amended` 必填…manifest item 的同名字段必填」；「LLM-facing 工具参数 `amended` 仍是输入名」；「filing 的原有请求语义保持原样」。§4.5「read runtime 的 material 投影改为严格读取…列表和具体读取跨命令仍从 source meta 获取该字段」——read tool 的**输出键名**只字未提。
- **反例/失败场景**: 禁令字面覆盖一切「LLM 输出」，但 (a) 存储/manifest schema 明确保留裸 `amended`；(b) tool 输入名保留 `amended`；(c) filing 请求摘要保留裸 `amended`；(d) read tool 现状即向 LLM 输出裸 `"amended"`（`read_runtime.py:632`、:910、:2571）。实施 Agent 若全面执行禁令，会把 read/manifest 键改名 `published_amended`——与同节「manifest 同名字段」直接冲突且扩大变更面；若保留 read 裸键，则违反禁令，且同一 job/会话面上 read 回显的 `amended` 与上传结果的 `published_amended` 并排出现，LLM 只能靠结构猜语义——恰是 F6 要消灭的形态。§6 要求入口测试检查两键的「禁止出现边界」，read 投影键名不定则该断言不可执行。
- **为什么有问题**: 项目 LLM-facing 约束要求投给 LLM 的字段名自解释、同一业务事实跨表面一致、关键规则写在当前输入中；plan 的命名规则没有按「存储 schema / 请求面 / 结果与 LLM 输出面」分域列出**逐表面键名清单**，反而用一句全称禁令制造与四处现状/例外的冲突。
- **直接证据**: plan §3/§4.5/§6 引文；`read_runtime.py:632/910/2571`（read 投影输出 `"amended"`）；`upload_tools.py:344/361`（输入名 `amended`）；`ingestion_runtime.py:7812`（请求摘要裸键，filing/material 共用 `_upload_request_summary`）。
- **影响**: 实施 Agent 两种过改/欠改都会产生用户可见与 LLM 可见的键名分叉；review 无法验收「禁止出现边界」；后续对齐返工。
- **建议改法和验证点**: §3 改为三域键名清单——持久 schema（source meta/manifest：`amended`）、请求/started（material：`requested_amended`；filing 请求摘要键名明确保留或改名的裁决）、结果/摘要/LLM 输出（material：`published_amended`，并钉死 read tool material 输出键名选型）；「禁止出现」测试按清单逐表面列正/反名单。验证点：对 read 输出、tool schema、job record、direct/CLI 四面逐一列键名断言。
- **修复风险（低/中/高）**: 低（plan 文本；read 键名若改属 whitelist 内）。
- **严重程度（低/中/高/严重）**: 中

### 5-未修复-[低]-`published_amended` 在 skipped/deleted 的「非本请求变更」语义只存在于计划表注，未被要求进入 LLM-facing 结果说明
- **位置**: plan §3 表注（「同一 `published_amended=true` 在 skip/delete 行代表旧发布或最后发布事实，不能据此声称本请求成功改变了标记」）；§4.5 tool schema 要求只覆盖请求语义。
- **问题类型**: 契约缺失（LLM-facing 语义）
- **当前写法**: §4.5 只要求「共享 schema 必须按 `upload_kind` 自足说明」请求布尔语义；结果摘要「用 `published_amended` 的 bool/null」，无字段含义的 LLM-facing 说明要求。
- **反例/失败场景**: 无状态 LLM 读到 `{"status":"skipped","published_amended":true}`，无自足说明时极易向用户声称「已将该材料标记为修订」——而该值只是既有/最后发布事实。
- **为什么有问题**: 项目 LLM-facing 约束要求结构化输出自足说明字段含义；plan 自己立的防误读规则不落到 LLM 可读文本就形同虚设。
- **直接证据**: plan §3 表注与 §4.5 引文；AGENTS.md LLM-facing 文本约束（字段名、含义、必填性、允许值须在当前输入自足说明）。
- **影响**: LLM 消费面误报发布事实；用户可见结论错误。
- **建议改法和验证点**: §4.5/§6 增加硬要求：tool/Job/CLI 结果投影中 `published_amended` 的含义（含 skip/delete 表示既有/最后发布事实、不代表本请求改变标记）必须写入 LLM-facing 字段说明；`tests/fins/test_fins_ingestion_tools.py` 验收该文案存在且覆盖 skip/delete 语义。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低

### 6-未修复-[低]-真实 CLI canary 配方未钉死各步 `--action`，在 O14 准入后 action 直接决定 toggle 走 metadata-only 还是 typed conflict
- **位置**: plan §6 canary 段。
- **问题类型**: 测试缺口
- **当前写法**: 九步只写 ticker/form/name、内容 hash 顺序、标记与预期终态，无一步写 action。
- **反例/失败场景**: O14/O15 落地后，对已存在目标用裸 `--action create` 无 overwrite 将 typed conflict（row6）；canary 的 toggle/skip 步若误用 create 将得到 conflict 而非 `metadata_updated`/`skipped`，配方不可复现。
- **为什么有问题**: canary 是真实 CLI 证据的固定配方，参数不全则补跑 lineage 不可比对。
- **直接证据**: plan §6 canary 引文；O14 裁决（active create 无 overwrite → typed conflict）。
- **影响**: 真实 CLI 验收返工；轻微。
- **建议改法和验证点**: canary 逐步补 `--action`（delete 步显式 delete；toggle/skip 步显式 auto 或 update 并注明不得用裸 create）。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低

## 4. 其它 lens 结论（无独立 finding）

- **Goal-bound minimal design**：F1–F6 修订均能映射回 binding goal 与总控裁决，无新增目标漂移；`metadata_updated`、命名分裂、O12/O14/O15 前置均由裁决背书。filing/O13/O33 边界维持外置正确。
- **架构边界**：amended owner 链（Fins 请求精确 bool 校验 → 共同 preparation/publication 状态机 → source meta 真源 → manifest/read/结果投影）判定正确；入口只保真传输；`MaterialManifestItem.from_source_meta` 保持唯一 manifest 投影点；filing 身份规则未被触及。本报告的 F-1/F-2 是消费面/归属描述问题，不是 owner 判定错误。
- **过度设计/过度耦合**：`_PreparedMaterialMetaMutation`、独立短 batch、typed publication outcome 均有直接风险支撑，无过度抽象；Slice 1/2 允许一次 pass 合并且保留两组验收，合理。
- **F4/F5 术语与符号**：`_run_material_upload` 已对准真实符号；「prepare 期 identical skip」命名与现状 early-return 位置一致（F-2 只争归属，不争术语）。
- **验证面**：逐文件 coverage ≥80%、不以合并覆盖率替代、真实双 batch 交错、fresh-only 新 schema、README 触发判定——均符合项目约束；唯一缺口是 overwrite 维度与 canary action（F-3/F-6）。
- **F1 硬前置诚实性**：plan 未用未集成 O12 计划冒充现有 API，硬前置+停止条件方向正确；F-1 只是其消费面描述残缺。

## 5. Open Questions

1. metadata-only 是否适用于 `--overwrite` 路径（`create/update --overwrite` 同内容切标记）？——F-3 裁决点，建议与 O14「明确替换」语义一次对齐。
2. read tool 的 material 已发布标记输出键名最终选 `amended` 还是 `published_amended`？——F-4 裁决点。
3. metadata-only 路径是否执行公司阶段、材料 batch 的 `expected_company_meta` 如何注册？——F-1 裁决点，需对照 O12 实际 public contract。
4. identical skip 是否强制经 O12 guard 内 expected 比较？若总控维持「窗口归 O33」的 F5 裁决措辞，需要给出与 O12 计划文本（skip 亦 guard 验证、象限 D）的调和说明。——F-2 裁决点。
5. O13 重复 delete 幂等若最终返回 0 文件的 `skipped` 类终态，与 §3「skipped requested>=1」计数规则的冲突在合流时如何裁决？（plan §7 已声明合流核对，此处只登记冲突面。）

## 6. Residual Risks（含跟踪去向）

| 残余风险 | 建议跟踪去向 |
| --- | --- |
| O12 同版 guard、O14/O15 共享准入均未实施集成，O18 implementation 硬停 | O12/O14/O15 各自 work unit；O18 §4.1/§8 已声明，同意保持 |
| O13 重复 tombstone 幂等时间/终态与 O18 计数规则的合流冲突面 | O13 合流回归（plan §7 已列） |
| 旧 workspace material source meta 缺 `amended` 时 strict read fail closed 的运维/排障说明 | `dayu/fins/README.md` 职责判定内一条排障提示，或后续 issue |
| 同 identity 并发 auto 的线性化、success+skip 竞争策略、L06 底层异常诊断 | O33 work unit（O12 guard 关闭 stale 报告窗口后仍剩的策略面） |
| filing identical skip 吞 amended（`_can_skip_upload` 对 filing 同样不比较标记） | `fins-filing-amended-identical-skip`（plan 非目标已列，同意外置） |
| Sol fix 批次曾有三条 exit1 与终报「两条非零」不符 | 总控已纠正并记录于裁决 artifact 尾节，无需再跟踪 |

## 7. Final Plan Review Conclusion

**fail**（须修订 plan 后再交实施 Agent 或进入实施 gate；全部为契约缝级窄修订，非结构性重写）。

理由：F1–F6 六项裁决均已落进文本，动机、owner 判定、核心状态机主干（首发/toggle/内容变/delete/恢复）、`metadata_updated` 终态与计数闭集、requested/published 分离骨架、O12/O14/O15 硬前置的诚实表述、真实双 batch 交错验收总体扎实且大部分直接证据复核成立；但本轮在修订引入的新文本上复现四类「实施 Agent 必须猜」的缺口：(F-1) metadata-only 条件发布的 O12 消费面——opaque revision 通道与 post-company 注册件——按 plan 字面不可实现；(F-2) identical skip 的 guard 归属与 O12 硬前置契约互相矛盾，同一 stale 窗口被双重承诺；(F-3) 同内容×标记×overwrite 矩阵留白且 canary 零覆盖；(F-4) 已发布事实命名禁令与四处保留裸 `amended` 的现状/例外自相矛盾，read 投影键名未钉死。四处均落在核心新行为（metadata-only 与 skip）的契约面上，修订前不宜交实施 Agent。F-5/F-6 为低严重度补强项。

按 orchestration 状态：F-1～F-4 为 `accepted-candidate`（应由 controller 裁决后修订 plan）；F-5、F-6 为 `accepted-candidate`（低严重度文本补强）；无 `needs-evidence` 项；Residual 表各项维持既有跟踪去向。本轮为单路（MiMo）审查结论，Kimi 第二路未出，不得据此宣称双路 re-review 通过。
