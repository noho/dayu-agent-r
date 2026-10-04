# Plan review（state 修订复审）：UM-O14-F01 / UM-O15-F01 material 动作与目标状态 Gateflow plan

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-1919d834

## Reviewed target and scope

- reviewed target：`docs/gateflow/upload-material-state-plan-20260929.md`（Gate：plan fix 修订候选；work unit：UM-O14-F01 + UM-O15-F01）。本轮实测 SHA-256 `b4d98a8d57e3d3a959f1358b0ffff3406b4a691698f0d653229604cfa2ce1ba0`，与派发声明一致。
- checkout：`/private/tmp/dayu-upload-state`，分支 `codex/upload-material-state`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`；工作树仅四份未跟踪 gateflow/review 文档，无产品代码改动，故上一轮对同基线的代码事实核对仍然有效，本轮再对修订新增引用逐条实读。
- binding scope contract：本 checkout 的 `docs/gateflow/upload-material-state-goal-20260929.md`（goal confirmation pass，SHA-256 `6c673a48…eb2c91`）；主工作区只读 `docs/reviews/upload-material-um-o14-oracle-adjudication.md`、`upload-material-um-o15-oracle-adjudication.md`（另对照 o12/o16 裁决）。上一轮 review：`docs/reviews/plan-review-20260929-051004.md`；总控裁决：`docs/gateflow/upload-material-state-plan-review-adjudication-20260929.md`。
- 相邻 O12 候选：`/private/tmp/dayu-upload-o12/docs/gateflow/upload-material-o12-company-plan-20260929.md`（实读全文）**只是候选**：其总控登记显示仍处 plan re-review 循环、`agent_status=failed` 的 fix 产物仅作候选，Kimi/MiMo 有效双路未齐；本 checkout 无任何 O12 落地代码（无 `_fs_material_upload_state_core.py`、`fs_material_upload_state_repository.py`、`_material_upload_admission.py`）。**本 plan 因此只是条件计划；缺依赖本身不构成“代码已坏”的断言**，以下判断只针对计划文本是否足以指导实施。
- review 范围：只做 adversarial plan review 并产出本 artifact；不修改 plan/goal/adjudication/产品/测试/README，不实施、不 commit/push/PR/merge，不派发子 Agent，不发外部消息。独立判断优先于总控裁决：总控已 accepted 的项仍按证据重验，发现裁决遗漏照报。

## Assumptions tested

1. 修订后 `evaluate_upload_overwrite_precondition` 的 kind×三态纯函数是否封闭可实现，且能同时保持 filing 现行契约与 material tombstone create 不改现行终态（上轮 F1 的“数学上无法双保持”是否真正消除）。
2. O12 硬依赖的“条件合同”是否足以指导实施：同版状态字段形状、单 batch 边界、skip 公司意图、writer-owned 复验增量，是否与 O12 候选契约可对上；对不上的地方是否有具体反例。
3. 接收后漂移与 upfront usage 的优先级、投影 owner、closed code 面是否闭合（上轮 F4 + 总控 F4 裁决方向）。
4. REPAIR_REQUIRED/UNSAFE（含损坏 tombstone）fail closed 与健康 tombstone 重复 delete 的格子是否封闭且与 O13 边界不打架（上轮 F5）。
5. 真实 CLI 矩阵与注入并发的证据分层、混合第一错误用例是否可执行（上轮 F6）。
6. 修订新增代码引用（`FinsUploadMaterialFiles.from_upsert_paths/for_delete`、`build_material_ids`、`validate_material_upload_ids`、`normalize_ticker`、`_normalize_optional_upload_fiscal_period`、`require_source_meta_is_deleted`、`_inspect_source_kind_unguarded`、`_commit_batch_with_publication_guard`、`commit_prepared_upload_batch`、`fins_upload_failure_from_exception`）是否真实存在且语义与 plan 声称一致。
7. S1/S2 白名单、验证命令与项目约束（每改必测、pyright、单文件 >=80%）是否自洽；LLM-facing 文案 owner 是否唯一。

## 上一轮 F1–F7、OQ1–OQ3 与总控 C1/C2 闭合表

| 项 | 上轮结论 / 总控裁决 | 本轮逐项判定 | 证据（plan 行号指修订计划） |
| --- | --- | --- | --- |
| F1 高：三态强制格未收敛 | accepted；补 kind+三态输入、写死 tombstone 格 | **闭合** | 修订计划 §2 表（L45–52）封闭覆盖 `SourceKind × create/update/delete × missing/active/tombstone × overwrite` 全格；`ALLOWED` 明确定义为“前置条件未拒绝，不替代后续 storage CRUD”（L43）；material tombstone create 无 overwrite 保留现有 source upsert/storage 拒绝（L26/L49），filing tombstone create 保持 `CREATE_TARGET_EXISTS`（L52，与 `ingestion_runtime.py:1506-1512` 现行一致）。kind 入参后“filing-tombstone 冲突 / material-tombstone fallthrough”是合法纯函数，上轮“不可同时满足”不成立。隔离回归与“不固化与真实 storage 相反终态”写入 L75。**残余见 Finding 1**（tombstone 格所依赖的 previous_meta 形状未钉死，属新问题非本项未闭合） |
| F2 高：O12 依赖缺席、公司决策无槽位 | accepted，拒绝“O12 follower、预留槽位”；改 O12 硬依赖、消费实际契约 | **闭合** | L24 硬依赖与“不预造第二个 protocol/snapshot/公司决策槽位”；L25 接收顺序固定为静态字段/文件组合 → exact 目标动作状态 → O12 公司决策；L55 “读取一次 O12 同版状态…命中目标错误时不得被缺名遮蔽”；L76 混合第一错误用例（无 files+missing、delete 携 files+missing 先 O16；合法 files+missing+缺名先 O15）；L38 要求实读 O12 最终 API/测试/装配后才进 S1。与 O12 候选 §集成顺序（静态 → target → 公司名）一致 |
| F3 中：S2 可能复制 publication 状态机 | accepted；shared owner 由 O12 唯一 material commit 路径提供 | **闭合** | L56 “只在该共享 owner（`commit_prepared_upload_batch` 邻接入口或 O12 最终同义入口）…不在两市场 workflow 再写状态机”“本项不重新收拢 batch”；L77 Publication 测试断言 SEC 与 CN/HK 调用同一 material publication owner；L70 workflow 只消费 contract。S2 白名单不列两市场 workflow 文件 |
| F4 中：writer 冲突文案/优先级/分类 owner | accepted，拒绝“漂移后再按 fresh 动作表报 usage”；漂移统一 `source_publication_conflict` | **闭合（含 Finding 2 的落地面缺口）** | L56 “接收后…一律 typed `source_publication_conflict`；即使 fresh 状态本可满足另一动作格（包括并发 delete→tombstone），也不改报 usage/target-missing”；L55 “runtime 已接收后的变化不再重判为 usage”；L57 `fins_upload_failure_from_exception` 精确直通 `FinsUploadFailureError.failure`、usage→public 映射在 `ingestion_runtime.py`、material 文案不得称 filing、不按异常字符串重算。实读确认现状缺口属实：`fins_upload_failure_from_exception`（`upload_failure.py:214-286`）无 `FinsUploadFailureError` 分支（会落 `unexpected_runtime`），`fins_upload_source_publication_conflict_failure` 文案为“目标 filing…”（`upload_failure.py:414`） |
| F5 中：REPAIR_REQUIRED/UNSAFE 交叉格 | accepted 须明确，拒绝损坏 source 上放行 delete | **闭合** | L27 “`REPAIR_REQUIRED`（包括可信 tombstone）与 `UNSAFE` 的所有动作均由 storage typed integrity/operational 边界 fail closed；不得投影为 target missing、允许 delete 或擅自授权 material repair”；L59 “是动作表之前的 fail-closed 边界”；L74 owner 测试含“损坏 tombstone repeat delete 均 typed fail closed，绝非 target missing”。健康/损坏是不同格（L27），与 O13 边界一致 |
| F6 中：依赖接缝未名、CLI 并发不可验收 | accepted | **闭合** | L29–38 接缝表逐项列出本读码基线已有定位点并声明“不是未集成修复的 API 承诺”；本轮实读全部命中（`FinsUploadMaterialFiles.from_upsert_paths/for_delete`、`build_material_ids`、`validate_material_upload_ids`、`normalize_ticker`、`_normalize_optional_upload_fiscal_period` 均存在）。L81/L97 可控 barrier 仅在 owner/仓储自动测试，真实 CLI 只跑稳定可复现矩阵、不用 sleep 双进程冒充；L76 混合第一错误用例；L25/L63/O115 实施前逐项核对集成 API、未就绪即停 |
| F7 低：skip 公司意图未决 | accepted，由 O12 先定 | **闭合** | L77 “active + update/auto 同内容 skipped 且有合法公司更新意图时，按 O12 已集成合同由受 guard 保护的 company-only/空 batch 提交公司更新、材料零 diff；无意图 skip 与 cancel 分别回归”；L94 矩阵行；与 O12 候选 L58（skip 仍开唯一受 precondition 保护的 batch）一致，O14/O15 只回归不第二套设计 |
| OQ1 协议归属 | 总控：由 O12 最终实现决定，不预留第二协议 | **已收敛** | L70 “MiMo OQ1 的协议归属以其最终实现为准”；L63 白名单以集成代码收窄/校正、不新建第二套 |
| OQ2 并发 delete-during-delete | 总控：统一 post-admission drift conflict，重试走 O13 | **已收敛** | L56 明文（含并发 delete→tombstone 也报 conflict）；L117 残余登记“保守报 publication conflict，调用者可按新健康 tombstone 状态重试”；L77 Publication 测试含 active→tombstone 的并发 delete-during-delete |
| OQ3 create+overwrite 同内容 | 总控：遵循当前 overwrite 触发发布，不得变 skip | **已收敛** | L48 “同内容也不 skip”；L75 pure owner 断言；L89 矩阵行“仍走现有覆盖发布而非 skip”。实读 `_can_skip_upload`（`docling_upload_service.py:1641`）确认 overwrite 即不 skip，行为可回归 |
| C1 与 O12 状态 owner 重复 | 总控预登记，待复审 | **闭合** | L24 “只消费实际 public contract…不预造第二个 protocol/snapshot”；L42 “直接复用…不另建 published snapshot、独立 repository 或第二次公司读取”“若 O12 最终契约不能表达…停止并回 owner plan 裁决”；L59 “没有新增…第二个 storage 状态源”。本轮独立核对同意：O12 候选的 `MaterialUploadPublishedState`/guard 内比较与本项复验是同一事实面，修订计划不再另造 |
| C2 单 batch 重叠 | 总控预登记，待复审 | **闭合** | L17 如实登记“此读码基线的 material 仍有两个 batch…O12 候选计划要求修成同版状态加单 batch，但候选签名不是本 checkout 已有 API”；L56 “本项只在该共享 owner…加入…复验…本项不重新收拢 batch。若 O12 单 batch 或最终 guard 不成立，回 O12 gate 修其原目标，不让 O14/O15 补偿”；L68 S2 “O12 单 batch/单 commit 与 skip 公司意图只回归”。与总控裁决方向一致 |

## 新一轮主动挑战结果

- **kind×三态共享 evaluator 可实现性**：通过。表是 (kind, 三态, action, overwrite) 的封闭纯函数；`auto` 先经既有 `resolve_upload_action`（`docling_upload_service.py:1892-1914`）解析、显式 action 原样保留（L43），表列 post-resolution 动作，无漏格。上轮“纯函数无法双保持”的前提（无 kind 输入）已被消除。**但**三态与 previous_meta 的投影来源存在契约缺口，见 Finding 1。
- **O12 同版状态/单 batch 边界**：边界声明与停止条件总体正确（条件计划、缺依赖不停止判坏），但 O12 候选契约对 tombstone 目标的 `source_meta` 形状有两种可读语义，修订计划的两个格子只在其中一种下成立——见 Finding 1。S2 “writer-owned 复验”增量措辞（“增…复验”“读取 fresh staging”）有被实现为第二比较路径的残余风险，见 Residual 1。
- **接收后漂移与 upfront usage 优先级**：通过。admission 顺序（O16 静态 → 目标动作 → O12 公司决策）与 O12 候选集成顺序一致；“CLI 预检后、runtime 接收前按新 admission 判定，接收后不再重判 usage”（L55）与 O12 R3 一致；filing 已有同构先例（`filing_upload_publication.py:71-79、746-749` 将 state-dependent usage 在 fresh 校验期重投影为 `source_publication_conflict`），实现方向有机制先例支撑。
- **损坏 tombstone fail closed**：通过，与总控 F5 裁决一致；残余张力（O13 可能希望损坏 tombstone 重复 delete 成功）登记给 O13/repair owner。
- **skip 公司意图与现行事实**：通过。现行事实（`sec_upload_workflow.py:500-560`：UPLOAD_STARTED → 公司 batch 独立 commit → prepare/材料 batch）实读属实；skip+公司意图的用户可见结果（公司更新生效、材料零 diff）被矩阵 L94 与 L77 明确保留并以 O12 合同为准。
- **CLI/并发验收**：通过。真实 CLI 矩阵只含稳定态（L83–95），并发走注入式自动测试（L77、L97）；“先补 A04 未覆盖的不同内容 create 证据”（L81）与 O14 裁决的待补跑一致。
- **LLM-facing 文案 owner**：通过（局部缺口并入 Finding 2）。L57 要求 material public message 写“目标材料/来源文档”、不称 filing、不泄路径/异常原文/内部 ID，owner 收敛在 failure owner，保留 filing 既有文案；与 O12 候选的 material 专用 path-free 构造器计划相容（复用优先）。`_USAGE_MESSAGES` 现有目标类文案（`ingestion_runtime.py:1054-1055`）本身不称 filing，可承载 kind 化文案扩展。
- **过度耦合 / goal drift**：未发现 goal drift。filing 表行是防漂移护栏而非新承诺；O13/O16/O18/O33/tombstoned create 均显式排除（L26/L59）；无新增公开 schema 的声称需修正（Finding 2），但整体未把实现发现的风险升级成新目标。耦合面收敛在“O12 消费者”角色，未见跨层穿透或第二套编排。

## Findings

### 1-未修复-[高]-O12 同版状态对 tombstone 目标的 business meta 形状未钉死，两个“保持现行”格与 auto 解析在候选契约的另一种读法下静默失效
- **位置**: 边界与前置依赖 §L24（O12 硬依赖核对清单）、§L38 接缝表 O12 行；最小设计 §1 L42（“`is_deleted` 以可信 storage meta…为真源；不能由 `source_meta is None`…猜 tombstone”）；§2 表 L49（material/tombstone+update“ALLOWED，沿现有恢复路径”）、L49（create+overwrite“沿现有 reset/recreate 路径，保持其现行终态”）；§L43（“auto 先由既有 action resolver 解析”）；停止条件 L115（只覆盖“不能表达 exact 三态或复验”，未覆盖恢复元数据连续性）。
- **问题类型**: 契约缺失 / 状态机漏洞 / 不可直接实施
- **当前写法**: 计划要求 O12 同版状态“同次表达…source business meta、presence/tombstone…”（L42），并承诺 tombstone 的 update“沿现有恢复路径”、create+overwrite“保持现行终态”，auto 交给既有 resolver；但未写明 tombstone 目标必须在该状态里携带其**完整可信 business meta**。
- **反例/失败场景（最强反例）**: O12 候选计划 L42 自述 `source_meta=None` “只表示无有效 **active** material meta，不把 tombstone 当 never-existed；本项只比较 presence/tombstone 漂移”，且其 action 解析为 `resolve_upload_action(..., observed_state.source_meta)`（O12 候选 L48）——按此 None-reading 实施后：(a) **auto+tombstone**：现行 `resolve_upload_action(None, tombstone_meta)` 返回 `update`（`docling_upload_service.py:1912-1914`，meta 非 None），走恢复；None-reading 下解析为 `create`，落入“tombstone+create 无 overwrite → ALLOWED 到现有 storage create 拒绝”格，用户可见结果从恢复变为 `FileExistsError`/`storage_io`。(b) **显式 update+tombstone**：现行 `prepare_upload` 收到 tombstone meta，`_build_upsert_meta` 保留 `first_ingested_at/created_at`（`docling_upload_service.py:311-320`）、`_resolve_document_version` 从旧版本递增（`:1745-1767`）；O12 handoff `prepare_upload(previous_meta=admission.observed_state.source_meta)`（O12 候选 L58）若传 None，则版本重置为 `v1`、`first_ingested_at` 重置为 now——“沿现有恢复路径”静默变成“以 v1 重建”。(c) 计划 L16 的三态判别本身（“可信 source meta 的精确布尔 `is_deleted`”）在无 meta 时无从执行，只能退化到 presence/tombstone 字段，与 L42 “`is_deleted` 以可信 storage meta 为真源”自相矛盾。且“material update tombstone 保留恢复”（L75）这类粗粒度断言可能对 (b) 的版本/时间重置**照样通过**（恢复“发生了”但连续性丢了），静默语义漂移难以被现有验收抓住。
- **为什么有问题**: “沿现有恢复路径/保持其现行终态”是本 plan 对用户已接受行为的保持承诺（goal L13/L26 边界），其可实现性完全取决于 O12 状态的一个未写明字段语义。O12 候选文本倾向 None-reading，且其 R1 自认“当前 material `source_meta` 的 active/已删除表达不足以裁决 O13/O15”。O12 仍在候选期（未 accepted、未集成），现在钉死成本是一行合同；待 O12 按 None-reading 落地后再发现，返工横跨两个 work unit，并会触发本 plan 自己的停止条件（L26“若共享函数无法同时保持这些终态，停止并交最小代码证据回 goal 裁决”）——正是上轮 F1 批评的“把可预先确定的裁决推迟到实施期”。
- **直接证据**: `docling_upload_service.py:1892-1914`（auto 解析依赖 previous_meta 存在性）、`:311-320`（first_ingested_at/created_at 连续性）、`:1745-1767`（None → v1）；O12 候选 `upload-material-o12-company-plan-20260929.md` L42/L48/L58/L95（R1）；filing 先例 `repository_protocols.py:399-448`（`FilingUploadPublishedState` 对 COMPLETE/REPAIR_REQUIRED 强制携带 `source_meta`，tombstone filing 即“COMPLETE + is_deleted meta”，为 material 同构提供现成形态）；修订计划 L16/L26/L42/L49/L75/L115 原文。
- **影响**: 实施 Agent 停在停止条件返工 / 版本与 first_ingested_at 静默重置（用户可见元数据语义变化）/ auto+tombstone 从恢复翻成 storage 拒绝 / 两个 work unit 扯皮
- **建议改法和验证点**:
  1. 在 L24/L38 的 O12 核对清单与 L115 停止条件中钉死合同要求：O12 同版状态对 **tombstone 目标必须携带完整可信 canonical business meta（含 `is_deleted=true`/`deleted_at`）**（与 filing `FilingUploadPublishedState` 形态一致），供 (i) 三态投影、(ii) `resolve_upload_action` 的 auto 解析、(iii) `prepare_upload` 的版本/`first_ingested_at` 连续性消费；若 O12 最终选择 None-reading，则必须显式改写 auto+tombstone 与 update+tombstone 的语义并回 goal 裁决，不得默认。
  2. pure owner 测试矩阵补连续性断言：update+tombstone 恢复后 `first_ingested_at`/`created_at` 不变、`document_version` 从旧版本递增、`is_deleted` 复位；auto+tombstone 解析为 update 并走同一恢复格。
  3. 验证点：对 O12 集成代码实读其 `MaterialUploadPublishedState.source_meta` 对 tombstone 的取值与 `__post_init__` 约束（参照 filing 的 MISSING/UNSAFE→None、COMPLETE/REPAIR_REQUIRED→必有 meta），不满足即按停止条件回 O12 plan gate。
- **修复风险（低/中/高）**: 低（本 plan 加一行合同与两条测试断言；O12 若走 None-reading 则属其计划期修正）
- **严重程度（低/中/高/严重）**: 高

### 2-未修复-[中]-usage→public 投影的 closed code 面未声明，且 test_upload_failure.py 不在 S1/S2 测试白名单与验证命令内
- **位置**: 最小设计 §5 L54（“共享 enum 仅补本项必要的 `DELETE_TARGET_MISSING`”）、L57（“生成 `FinsUploadFailureKind.USAGE` 与对应 closed public code/reason”）、L59（“没有新增公开 schema”）；切片 S1 允许改动含 `dayu/fins/upload_failure.py`（L67）而测试“限”七文件（L67）、S2 测试“限”六文件（L68）；验证命令 L104 未含 `tests/fins/test_upload_failure.py`。
- **问题类型**: 契约缺失 / 测试缺口 / 不可直接实施
- **当前写法**: 只对 usage enum 的 `DELETE_TARGET_MISSING` 增量作了说明，把“对应 closed public code/reason”当作已存在或显然，同时声称“没有新增公开 schema”。
- **反例/失败场景**: 实读 `upload_failure.py:38-53`：`FinsUploadFailureCode`（自称 closed public reason code）**没有任何** target-exists/target-missing 成员，`_USAGE_FAILURE_CODES = {UNSUPPORTED_UPLOAD_FORMAT}`（`:179-181`）。实现 L57 的 `FinsUploadFailureReason(kind=USAGE, code=…)` 必然要给 `FinsUploadFailureCode` 增三个成员（或建立 usage→failure code 映射表）——这是 closed public contract 变更，与 L59 “没有新增公开 schema”直接矛盾。实施 Agent 面对矛盾文本可能：(i) 把 target 错误塞进 `STORAGE_IO`/`UNSUPPORTED_UPLOAD_FORMAT`（复现 goal 点名的误导投影）；(ii) 只投影 `FinsUploadUsageFailure` 便声称完成，direct/job/observation 的同一 reason 验收（L57）无从落地（现状 `_classify_direct_error` 把 `ValueError` 归 `USER_INPUT`、`_save_failed_from_exception` 仅存 message，`ingestion_runtime.py:7046-7070/5986-6000`）。同时 §5 强制修改 `upload_failure.py`（passthrough 直通、新码、material 文案），其 owner 级测试的自然归属 `tests/fins/test_upload_failure.py`（文件存在）被 S1“测试限…”、S2“测试限…”和 L104 验证命令共同排除，与项目“每次代码修改必须补测试/单文件 >=80%”硬约束冲突：要么违反白名单，要么违反项目测试约束。
- **为什么有问题**: 错误投影是 O15 的核心验收面（typed 原因取代误导性 `storage_io`）；code 面不钉死则 tool/CLI/job 断言无法写，白名单不闭合则 S1 无法在项目约束下完成。L54 证明 plan 知道要写清 enum 增量，却只写了一个 enum（实际至少两个：`UploadOverwritePrecondition` 与 `FinsUploadUsageCode` 都需 `DELETE_TARGET_MISSING`，`FinsUploadFailureCode` 还需 target 码）。
- **直接证据**: `upload_failure.py:38-53、179-181、214-286`；`ingestion_runtime.py:673-703、1027-1058、7046-7070、5986-6000`；`tests/fins/test_upload_failure.py` 存在但不在白名单；plan L54/L57/L59/L67/L68/L104 原文。
- **影响**: 实施 Agent 生成错误投影 / closed enum 漏扩或误映射 / 测试约束与白名单二选一违规 / review 不可验收
- **建议改法和验证点**:
  1. L54/L57 改写为完整契约面：`UploadOverwritePrecondition`、`FinsUploadUsageCode`、`FinsUploadFailureCode` 各自的成员增量（或明确 usage fact 只走 `FinsUploadUsageFailure`、并定义其进入 job/direct/observation summary 的唯一映射），L59 同步改为“仅补 closed enum 成员，无新 schema/协议”。
  2. S1/S2 测试白名单与 L104 验证命令补 `tests/fins/test_upload_failure.py`（S2 若保留 `upload_failure.py`“投影仅在确需时触及”则至少验证命令必须包含）。
  3. 验证点：owner 测试断言三码→`FinsUploadFailureKind.USAGE` 的 kind/code/message 同源、`fins_upload_failure_from_exception` 对 `FinsUploadFailureError` 直通不落 `unexpected_runtime`、filing 既有文案未漂移。
- **修复风险（低/中/高）**: 低（plan 文本与白名单补齐，不动架构）
- **严重程度（低/中/高/严重）**: 中

## Open questions

1. **O12 最终 `MaterialUploadPublishedState.source_meta` 对 tombstone 的取值**（与 Finding 1 挂钩）：O12 候选文本两种读法并存（“无有效 active meta” vs 比较“全部 canonical business meta 字段值”需 meta 在场）。建议总控在 O12 plan gate 就近裁决并在其计划中写死，而非留给集成期；本 plan 侧只需把合同要求写进核对清单。
2. **filing / missing + delete 的 kind 不对称**：表 L50 给 filing 保持现行（无 typed delete-missing），material 得到 `DELETE_TARGET_MISSING`。按 goal/O15 裁决的 material 范围读法这是正确边界，但 goal §2 字面（“对从未存在目标的显式 update（有/无 overwrite）和 delete…返回动作明确 typed target-missing”）未限定 kind，存在被读成覆盖 filing 的空间。请总控确认这是有意的范围切分；若未来要求 filing delete-missing 同源 typed，应走新 goal 确认而非本项夹带。

## Residual risks and suggested tracking destination

| 残余风险 | 建议追踪去处 |
| --- | --- |
| S2 “writer-owned 复验”可能被实现为 O12 guard 内比较之外的第二比较路径（“增…复验”“读取 fresh staging”措辞）；若 O12 precondition 已覆盖全部漂移键（presence/tombstone/meta/revision/company），S2 实为“投影语义 + 测试”，白名单应收窄 | 本 work unit S2 实施前的白名单校正确认（plan L63 已有条款）；实现审查按“复用 O12 既有 guard 内比较/注册，不新增第二比较函数”的标准验收 |
| 冻结 A04 不覆盖“已有不同内容 create 无 overwrite”，CLI 补跑前不能声称修复可用（plan L117 已登记） | 本 work unit final closeout 的真实 CLI 证据清单（O14-F01 标签） |
| O13 健康重复 delete 时间幂等、O18 amended、O33 auto 并发 skip | 各自 work unit；本项仅回归不误判 |
| 损坏（REPAIR_REQUIRED）tombstone 重复 delete fail closed 与 O13 幂等目标的潜在张力（总控已裁 fail closed） | O13/repair owner；若需放行须回 owner/goal 裁决（对应上轮 F5 的备选路径） |
| material tombstone create 无 overwrite 仍是 storage 拒绝（`storage_io` 文案误导），用户可见终态未改善 | goal 未覆盖的 tombstoned create 语义 → 后续 goal confirmation |
| O12 仍是未 accepted 候选（其 re-review 双路未齐），本 plan 全部 S1/S2 为条件计划；O12 最终 API/文件名可能与候选不同 | O12 gate 通过后按 plan L38/L63 实读校正；在此之前不得声称 implementation ready |
| 两进程真实 CLI 竞态无确定性 barrier | plan 已定注入式测试为准；两进程证据至多 best-effort 补充 |

## 实际验证证据（本轮实读/实测清单）

- SHA 实测：plan `b4d98a8d57e3d3a959f1358b0ffff3406b4a691698f0d653229604cfa2ce1ba0`（与派发一致）；goal/adjudication/上轮 review SHA 一并核对。
- 本轮实读代码：`docling_upload_service.py`（`UploadOverwritePrecondition`/`evaluate_upload_overwrite_precondition` 251-285、`prepare_upload` 430-539、`_build_upsert_meta` 288-331、`_can_skip_upload` 1616-1648、`_resolve_document_version` 1745-1767、`resolve_upload_action` 1892-1914、`_safe_get_document_meta` 828-852）；`sec_upload_workflow.py:470-570`（previous_meta → UPLOAD_STARTED → 公司 batch → prepare → 材料 batch 时序）；`ingestion_runtime.py`（`FinsUploadUsageCode`/`FinsUploadUsageError`/`FinsUploadUsageFailure` 673-740、`_USAGE_MESSAGES`/`fins_upload_usage_failure` 1027-1118、`_validate_runtime_upload_request` 4714-4748、`_classify_direct_error` 7046-7070、`_save_failed_from_exception` 5986-6000）；`upload_failure.py`（code 枚举 38-53、分组 179-210、`fins_upload_failure_from_exception` 214-286、`fins_upload_source_publication_conflict_failure` 393-418）；`filing_upload_publication.py` 55-83/725-775（state-dependent usage → conflict 先例）；`repository_protocols.py:399-448`（filing-only post_init）；`_fs_storage_infra.py:417-470/676-735`（begin_batch writer 锁、guard 内 swap）；`_fs_source_document_core.py:1707-1760`（`meta_path.exists()` + 普通 `FileExistsError`/`FileNotFoundError`）。
- 上轮同基线已核、本轮经 git status 确认无代码漂移后沿用：`_inspect_source_kind_unguarded`、`require_source_meta_is_deleted`、`_toggle_source_deleted` 存在性判定、两市场双 batch、`commit_prepared_upload_batch`、`FilingUploadPublishedState` filing-only。
- 符号存在性核验：`FinsUploadMaterialFiles.from_upsert_paths/for_delete`、`build_material_ids`、`validate_material_upload_ids`、`normalize_ticker`、`_normalize_optional_upload_fiscal_period`、`begin_batch`、`_commit_batch_with_publication_guard` 全部命中；O12 落地文件在本 checkout 不存在（条件计划确认）。
- 白名单测试文件存在性：10 个相关测试文件均在；`tests/fins/test_upload_failure.py` 存在但被修订计划排除（Finding 2）。
- 预检 canary：`/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.UCciXX/canary.txt` 经工具读取，内容 `mimo-1919d834`（CANARY 行逐字登记于文首）。

## Final plan review conclusion

**pass-with-risks**

理由：修订计划把上轮 F1–F7、OQ1–OQ3 与总控 C1/C2 全部收敛进可验收文本——kind×三态表封闭、`ALLOWED` 语义定义、健康/损坏 tombstone 分格、接收后漂移统一 publication conflict（与 filing `filing_upload_publication.py:746-749` 先例同构）、O12 硬依赖与单 batch 不补偿、skip 公司意图按 O12 合同回归、真实 CLI 与注入并发分层、混合第一错误用例、LLM-facing 文案 owner 收敛——本轮逐项复核确认闭合，且全部代码事实引用经实读属实、无 goal drift、无第二套状态/编排。剩余两个问题均可在 plan 文本层收敛：**Finding 1（高）**必须在 O12 plan 定稿/集成前钉死 tombstone business meta 合同，否则“沿现有恢复路径/保持现行终态”与 auto 解析在 O12 候选的 None-reading 下静默失效（最强反例：auto+tombstone 从恢复翻为 storage 拒绝；update+tombstone 版本/first_ingested_at 重置且粗粒度测试可能照过）；**Finding 2（中）**须补齐 usage→public 的 closed code 面与 `test_upload_failure.py` 白名单/验证命令，消除“没有新增公开 schema”与必然 enum 扩展的矛盾。两项均不推翻现有设计。**本 plan 是条件计划**：O12 尚未 accepted+integrated（当前仍是 re-review 中的候选），依其自身停止条件，O12 未就绪即停，不得以缺依赖断言本代码已坏；Finding 1 未闭合前不能计 plan pass，也不建议进入 implementation gate。
