# Plan review（state 第三轮复审）：UM-O14-F01 / UM-O15-F01 material 动作与目标状态 Gateflow plan

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-8227b431

## Reviewed target and scope

- reviewed target：`docs/gateflow/upload-material-state-plan-20260929.md`（Gate：plan fix 修订候选 fix3；work unit：UM-O14-F01 + UM-O15-F01）。本轮实测 SHA-256 `4ae27dadd044b3ed4185079a0397a90f9eeb4bbc1faad25fab6f2426b4f9a7f4`，与派发声明一致，无漂移。
- checkout：`/private/tmp/dayu-upload-state`，分支 `codex/upload-material-state`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`；`git status --porcelain` 仅五份未跟踪 gateflow/review 文档（goal、plan、adjudication、两轮旧 review），无产品代码改动，故上轮对同基线的代码事实核对仍有效，本轮再对 F8/F9/F10 涉及的全部代码引用逐条实读。
- binding scope contract：本 checkout `docs/gateflow/upload-material-state-goal-20260929.md`；主工作区只读 `docs/reviews/upload-material-um-o13-oracle-adjudication.md`（UM-A09）、`upload-material-um-o14-oracle-adjudication.md`、`upload-material-um-o15-oracle-adjudication.md`；总控裁决 `docs/gateflow/upload-material-state-plan-review-adjudication-20260929.md`（F8/F9/F10 全 accepted，fix3 候选待本轮复审）；上一轮 review `docs/reviews/plan-review-20260929-054535-state-mimo.md`。项目 `AGENTS.md` 与主工作区逐字一致，已核。
- 相邻 O12 候选：`/private/tmp/dayu-upload-o12/docs/gateflow/upload-material-o12-company-plan-20260929.md` 及其 `upload-material-o12-plan-review-adjudication-20260929.md` 实读全文。O12 仍是**未 accepted 候选**（fix3 候选 SHA `cf392652…`，Kimi/MiMo 有效双路未齐，产品未实施）；本 checkout 无任何 O12 落地代码。本 plan 是条件计划，缺依赖本身不构成“代码已坏”的断言；本轮判断只针对计划文本是否足以指导实施，且不把候选依赖冒充集成代码。
- review 范围：只做 adversarial plan review 并产出本 artifact；不修改 plan/goal/旧 review/裁决/产品/测试/README，不实施、不 commit/push/PR/merge，不派发子 Agent，不发外部消息。独立判断优先于总控裁决：已 accepted 的 F8/F9/F10 仍按证据重验。

## Assumptions tested

1. F8：plan 是否把 COMPLETE tombstone 全量可信 canonical business meta（含 `is_deleted=true`/`deleted_at`/`first_ingested_at`/`created_at`/`document_version`/`source_fingerprint`）+ 独立 opaque revision 钉成 O12 集成前硬依赖与停止条件，且与 O13 accepted A09、O12 候选现行文本可同真。
2. F9：三层 closed enum（`UploadOverwritePrecondition` / `FinsUploadUsageCode` / `FinsUploadFailureCode`）增量是否与实际代码逐字一致，public USAGE reason、typed 直通与 `test_upload_failure.py` 白名单/验证命令是否闭合，“无新 schema”矛盾是否消除。
3. F10：同内容 tombstone 恢复保留原 `document_version`（UM-A09 为 v3）、不同内容按现行 `_resolve_document_version` 递增——两格与 source version owner、O13 accepted A09、O12 候选测试合同是否冲突。
4. 旧 F1–F7、OQ1–OQ3、C1/C2 是否在 fix3 文本中无回退。
5. 状态矩阵全格、guard/alias/typed 投影在现行代码与 O12 候选契约下是否可实施；新 finding 需直接证据。

## F8 / F9 / F10 闭合表（本轮逐项实读判定）

| 项 | 总控裁决要求 | 本轮判定 | 直接证据 |
| --- | --- | --- | --- |
| F8 高：COMPLETE tombstone 全量 meta 硬依赖 | O12 同版状态必须保留 tombstone 完整可信 canonical meta（`is_deleted=true`、`deleted_at`、版本、首次时间）+ 独立 revision；`None` 只给真 missing/无可信 meta；同 meta 供 auto 解析、prepare 连续性、guard 比较；O14/O15 列为集成前硬核对与停止条件 | **闭合** | plan L24 硬依赖段逐字段列出 `is_deleted=true`、`deleted_at`、`first_ingested_at`、`created_at`、`document_version`、`source_fingerprint` 与独立 opaque revision，并要求“同一份 meta 须供 `auto` 动作解析、`prepare_upload(previous_meta=...)` 恢复连续性和唯一 guard 严格比较消费”；L38 接缝表 O12 行、L42 最小设计第 1 项（`is_deleted` 以可信 storage meta/`require_source_meta_is_deleted` 为真源，不从 `source_meta is None` 或目录存在性猜）、L74/L75 owner 测试断言、L115 停止条件全覆盖。与 O12 候选 §1（其 L42 已改为“可信 COMPLETE tombstone 的 `source_meta` 必须在场…`None` 仅用于真正 MISSING 或无可信 business meta 的 UNSAFE”）同向；`source_fingerprint` 在场是 F10 不同内容递增的前提（见下表 F10 行），plan L24/L38 明确列入。实读 `docling_upload_service.py:311-331`（`_build_upsert_meta` 从 previous_meta 保留 `first_ingested_at`/`created_at`、复位 `is_deleted=false`/`deleted_at=None`）、`:1892-1914`（`resolve_upload_action` 靠 previous_meta 非 None 把 auto 解析为 update）确认该 meta 合同确为行为真源 |
| F9 中：三层 closed enum 与 USAGE reason/test 白名单 | 准确列出三 enum 的 target 码增量；三 public target reason 统一 `FinsUploadFailureKind.USAGE`；`tests/fins/test_upload_failure.py` 入白名单与验证命令；“无新 schema”改述；owner 测试断言 kind/code/message、typed 直通、filing 文案不漂移 | **闭合** | plan L57 逐 enum 写死增量，与代码逐字一致：`UploadOverwritePrecondition` 现有 `ALLOWED`+`CREATE_TARGET_EXISTS`+`UPDATE_TARGET_MISSING`（`docling_upload_service.py:251-256`）仅增 `DELETE_TARGET_MISSING`；`FinsUploadUsageCode` 已有前两码（`ingestion_runtime.py:702-703`）仅增 `DELETE_TARGET_MISSING`；`FinsUploadFailureCode` 现无任何 target 码（`upload_failure.py:37-54`）增三码且“全部且仅归 USAGE 分组”——与 `upload_failure.py:179-211` 的 kind/code 完整互斥分组机制（import 期 RuntimeError 断言）相容。L57 要求 usage→public 映射产生同码 `FinsUploadFailureReason(kind=USAGE, code=...)`、`fins_upload_failure_from_exception` 精确直通 `FinsUploadFailureError.failure`（现缺该分支，`upload_failure.py:214-286` 会让 typed 错误落 `unexpected_runtime`——plan 要求补的正是此处）、material 文案不称 filing（现行 `upload_failure.py:415` 确为“目标 filing…”）、filing 既有文案逐字保持（`ingestion_runtime.py:1054-1055` 现文案可原样保留，kind-aware 文案由 L57 指定的 kind-aware Fins owner 承担，可实施）。L59 把“无新 schema”改述为“仅指不改数据形状/协议；closed public enum 成员会扩展”，上轮矛盾消除。白名单：S1/S2 测试均含 `tests/fins/test_upload_failure.py`（L67/L68），验证命令 L106-108 含该文件，与 S1/S2 全部测试白名单并集一致。filing 侧 typed 映射先例实读属实（`ingestion_runtime.py:1506-1514`） |
| F10 高：同内容保留版本 / 不同内容现行递增 | 两格：同内容 tombstone 恢复原 ID、版本不变（UM-A09 v3）；不同内容按既有版本规则递增不重置 v1；两格均保 `first_ingested_at`/`created_at`、清 `is_deleted`/`deleted_at`；不得把 O12“非 None 避免重置 v1”误读成“所有恢复都递增” | **闭合（源代码同真，跨 WU 风险已条件化）** | plan L24（“同内容 tombstone `auto` 恢复仍须遵循已接受 UM-A09 的原 ID、原版本（v3）语义”“O12 计划用不同旧指纹验证递增，只证明旧 meta 非 None、避免误重置 v1”）、L38、L75 两格测试、L94/L95 矩阵行、L115 停止条件（“若实测现行版本 owner 无法满足已接受 UM-A09，停止并报告…交 source version owner/goal 裁决”）。**源 version owner 实读同真**：`_resolve_document_version`（`docling_upload_service.py:1745-1770`）对 material（`identical_skip_safe=True`，`:1735`）在同指纹时保留旧版本、不同指纹时 `_increment_document_version`（`:1798-1817`，v3→v4）；`_can_skip_upload`（`:1616-1648`）对 tombstone（`require_source_meta_is_deleted`）不 skip，故同内容恢复必走 upsert 且保 v3（UM-A09 冻结行为）；`_build_upsert_meta`（`:311-331`）保 `first_ingested_at`/`created_at`、清删除态。**注意**：不同内容递增还依赖旧 `source_fingerprint` 在场（`:1767-1769`：旧指纹缺失时反而保旧版本）——F8 的字段清单含 `source_fingerprint` 正是此格前提，plan L24/L38 已列 |

## source version owner × O13 accepted A09 × O12 候选 三方冲突核验（本轮重点）

- **源 version owner 与 UM-A09 无冲突**：A09（同内容 auto 恢复、原 ID、版本保持 v3、仅 meta/manifest 改动）与 `_resolve_document_version`/`_can_skip_upload` 的现行规则直接同源；A03（不同内容 auto 升版 v1→v2）与不同内容递增同向。UM-A09 原文“该结论不外推至不同内容或并发恢复”——plan 不同内容格以“既有版本 owner 规则”为据（代码事实）而非外推 oracle，裁决 F10 亦按“满足既有版本规则才递增”表述，无越权。
- **O12 候选测试合同与 F10 无冲突**：O12 候选 plan L84 的恢复测试显式限定“**使用不同于旧版的文件指纹**，断言…`document_version` 从旧版递增”，只覆盖不同指纹格；plan L75/L115 明文防过度解读（“只证明非 None 旧 meta 避免 v1 重置，不能推出所有恢复都递增”），并在 L38 要求实读 O12 owner 测试后才进 S1。
- **风险点（非本 plan 缺陷，登记残余）**：O12 裁决跨项段（`upload-material-o12-plan-review-adjudication-20260929.md` L34）写“显式 update 恢复的…`document_version` **递增**”**未限定不同指纹**。若 O12 实施按裁决字面写同内容恢复递增测试，将直接违反 UM-A09 并与本 WU 的同内容保版本格互斥。O12 候选 plan 文本已正确收窄，但 O12 gate 未关；本 plan 的停止条件（L75/L115）能兜住集成期发现，冲突测试面应在 O12 plan gate 就近钉死。

## 旧 F1–F7、OQ1–OQ3、C1/C2 无回退核验

| 项 | fix3 文本现状 | 判定 |
| --- | --- | --- |
| F1 三态表封闭 | L45-52 全格覆盖 `SourceKind × 动作 × 三态 × overwrite`；L43 `ALLOWED`=“前置条件未拒绝，不替代后续 storage CRUD”；L26/L49 material tombstone create 无 overwrite 保留现有 storage 拒绝、非新 typed；L52 filing tombstone 仍 `CREATE_TARGET_EXISTS`（与 `ingestion_runtime.py:1506-1512` 现行一致） | 无回退 |
| F2 O12 硬依赖/决策顺序 | L24 硬依赖+禁第二槽位；L25 接收顺序固定；L55“读取一次 O12 同版状态…命中目标错误时不得被缺名遮蔽”；L76 混合第一错误用例 | 无回退 |
| F3 共享 publication owner | L56“只在该共享 owner…不在两市场 workflow 再写状态机”“本项不重新收拢 batch”；L77 双入口同 owner 测试；L70 workflow 只消费 contract | 无回退 |
| F4 漂移统一 conflict | L56 接收后漂移一律 `source_publication_conflict`（含并发 delete→tombstone），不改报 usage；L55 接收后不重判 usage；L57 直通+不按字符串反推 | 无回退 |
| F5 损坏 fail closed | L27/L59/L74：`REPAIR_REQUIRED`（含可信 tombstone）与 `UNSAFE` 全动作在动作表之前 typed fail closed，与健康重复 delete 分格 | 无回退 |
| F6 接缝/CLI 并发分层 | L29-38 接缝表（本轮逐符号实读命中：`FinsUploadMaterialFiles.from_upsert_paths/for_delete`、`build_material_ids`、`validate_material_upload_ids`、`normalize_ticker`、`_normalize_optional_upload_fiscal_period`、`require_source_meta_is_deleted`、`_inspect_source_kind_unguarded`、`_commit_batch_with_publication_guard`、`commit_prepared_upload_batch`、`fins_upload_failure_from_exception` 全部存在）；L81/L97 barrier 只在自动测试、真实 CLI 只跑稳定矩阵 | 无回退 |
| F7 skip 公司意图 | L77/L96 按 O12 已集成合同回归，本项不第二套设计 | 无回退 |
| OQ1 协议归属 | L70 以 O12 最终实现为准 | 已收敛保持 |
| OQ2 delete-during-delete | L56/L117 统一 post-admission conflict、重试走新状态 | 已收敛保持 |
| OQ3 同内容 overwrite 不 skip | L48/L75/L89；实读 `_can_skip_upload:1641`（overwrite 即不 skip）确认可回归 | 已收敛保持 |
| C1 不造第二状态源 | L42“不另建 published snapshot、独立 repository 或第二次公司读取”；L59“没有第二个 storage 状态源” | 无回退 |
| C2 不二次收拢 batch | L17 如实登记现状两 batch 与 O12 候选差异；L56/L68 只回归 | 无回退 |

## 状态矩阵与 guard/alias/typed 投影可实施性

- **矩阵与现行终态逐格对得上**：material/active+create 无 overwrite 现行落 skip/发布（`prepare_upload:462-463` 的 CREATE 拒绝被 kind 闸限定 filing；material 同指纹走 `_can_skip_upload`→skipped），升级为 typed conflict 正是本 WU 目标；material/missing+update 现行 `FileNotFoundError`（`:464-465`，迟至 prepare、公司提交后，落入 `upload_failure.py:272-279` 的 OSError→`storage_io`，即 A11/A12 现象）；delete 现行绕过 precondition（`:447-453`）落仓储异常（A13）——三格升级为 admission typed 拒绝可实施。material/tombstone+create 无 overwrite 现行经 `:281`（tombstone meta 非 None）→kind 闸放行→staging upsert `FileExistsError`（`_fs_source_document_core.py:1707` 一带），矩阵“ALLOWED 到现有 storage 拒绝、非新 typed”保终态成立。material/tombstone+create --overwrite 走 `replace_existing`→`reset_source_document`（`docling_upload_service.py:685-711`，行内注释明言“reset 前持有的 previous_meta 仍是版本与首次创建时间真源”），矩阵“保持现行终态、不作新承诺”成立。
- **guard/alias/typed 投影可实施**：L56 漂移键（presence/tombstone/完整 canonical meta/revision/company meta）与 O12 候选唯一纯比较函数的比较面（其 L44）完全一致，“若 O12 guard 已覆盖全部漂移键，只补投影与测试”避免第二比较路径；alias/identity 先于 material precondition 的优先级按 O12 既有 contract 保持（O12 L60），本项不重排。typed 面：三 target 码入 `FinsUploadFailureKind.USAGE` 分组与 `FinsUploadFailureReason.__post_init__` 的 kind/code 一致性校验（`upload_failure.py:97-122`）相容；漂移复用既有 `source_publication_conflict`（storage 组）不加第二 drift code。
- **纵深说明（非缺口）**：`prepare_upload` 内部对 UPDATE_TARGET_MISSING 仍抛 `FileNotFoundError`（`:464-465`）属 admission 之后的纵深防线；设计上全部公开入口（runtime direct/job/observation、CLI 预检、独立 SEC/CN/HK 共享 helper）先经同一 validator（L55），该分支对目标错误格不再可达。实施审查应确认没有绕过 admission 的新入口把该异常当作 typed 投影源。

## Findings

### 1-未修复-[低]-tool/记录投影面“同一 kind/code/message”存在两种读法，强读法与 W10 白名单互斥
- **位置**: 最小设计 §5 L57（“direct/job/observation、Service/tool 投影同一 kind/code/message”）；owner 与入口测试 L76（“tool/CLI 断言同源 code/message”）；切片说明 L70（“`dayu/fins/tools/upload_tools.py`…只消费已有 Fins contract，不在本项另写状态规则”）与 S1/S2 允许改动列表（均不含 `upload_tools.py`、`dayu/fins/tools/error_contract.py`）。
- **问题类型**: 契约措辞歧义 / 测试缺口（白名单与验收面张力）
- **当前写法**: 要求 tool 投影与 CLI/Service “同一 kind/code/message”，但 tool 层现状没有 Fins closed code/kind 的投影位置。
- **反例/失败场景（最强反例）**: 实读 `dayu/fins/tools/upload_tools.py:101-141`：tool 边界把 `FinsUploadUsageError`（`ValueError` 子类，`ingestion_runtime.py:743`，`str(exc)==failure.message`）归入 `except ValueError` → `_failed_outcome(error=_ERROR_INVALID_ARGUMENT, message=str(exc), …)`；tool 的 closed error 词表是 `dayu/fins/tools/error_contract.py:24` 的 `INVALID_ARGUMENT = "invalid_argument"` 等通用 slug，**没有** `create_target_exists`/`update_target_missing`/`delete_target_missing` 的位置，现有测试也只断言 `outcome.result.error == "invalid_argument"`（`tests/fins/test_fins_ingestion_tools.py:1236` 等）。若按字面强读（tool outcome 必须暴露 Fins 三码与 USAGE kind），实施必须改 `error_contract.py`/`upload_tools.py`——与 L70 及白名单直接冲突；若按弱读（tool code=既有 tool error 分类 + owner message 同源、不落 `job_start_failed`/`storage_io`），现有机制已满足、无须改 tool。两种读法写出的验收测试不同，实施 Agent 可能违规扩白名单或写出不可断言的用例。同类“验收面与白名单互斥”正是上轮 F2 的形态。另：L57 把 “direct/job/observation” 列入投影面亦偏松——本项拒绝发生在 producer/job/observation 创建前（L55/L76 自述），被拒请求本就无记录可投影，可断言的是“不创建记录 + 各入口错误事实同源”。
- **为什么有问题**: tool/LLM-facing 错误事实是 O15 验收面之一（“各入口消费同一状态结果/错误投影”）；措辞不收窄会在实施期逼出白名单违规或弱化测试，且与项目“语义 owner 唯一、测试断言 owner 级 contract”的硬约束摩擦。
- **直接证据**: `upload_tools.py:50、117-124`；`error_contract.py:24`；`ingestion_runtime.py:743-763`；`tests/fins/test_fins_ingestion_tools.py:1236` 等；`service_runtime.py:77`（Service 以 typed 异常传播，Service 面可字面满足）；plan L57/L70/L76 原文。
- **影响**: 实施 Agent 越权改 tool 契约 / 测试断言无法落地 / tool 层 code 同源性无验收
- **建议改法和验证点**:
  1. L57/L76 收窄为明确断言面：tool 层=既有 tool error 分类（usage/invalid-argument 类，不落 job-start-failure、不投 `storage_io`）+ message 与 owner 文案逐字同源 + 无路径/异常原文；CLI=既有 usage exit + owner message；Service=typed `FinsUploadUsageError` 携 `failure.code`/message 同源；direct/job/observation=拒绝发生在记录创建前、无 job/observation 产生，且凡形成 failure fact 的路径 kind/code/message 一致。
  2. 若总控要求 tool 结构化暴露 Fins closed code，则必须把 `dayu/fins/tools/upload_tools.py`（及 `error_contract.py` 若扩词表）显式加入 S1 允许改动与测试白名单，并定义 tool outcome 的投影形状——二选一，不可悬空。
  3. 验证点：`tests/fins/test_fins_ingestion_tools.py` 对三 target 码逐码断言 message 同源与 error 分类；不新增对 tool 协议字段的断言除非白名单先行扩入。
- **修复风险（低/中/高）**: 低（plan 一句话收窄，或扩白名单一处）
- **严重程度（低/中/高/严重）**: 低

## Open questions

1. **tool 层 code 同源的验收口径**（与 Finding 1 挂钩）：请总控在实施 gate 前二选一裁决——弱读（tool 沿用既有 error 分类）或强读（tool 暴露 Fins closed code 并扩白名单）。
2. **O12 裁决跨项段的“document_version 递增”未限定指纹**：建议总控在 O12 plan gate 就近把其 owner 测试的递增断言限定为不同指纹格，避免与 UM-A09/本 WU 同内容保版本格互斥（O12 候选 plan 文本已正确收窄，风险在裁决措辞的下游执行）。

## Residual risks and suggested tracking destination

| 残余风险 | 建议追踪去处 |
| --- | --- |
| O12 仍是未 accepted 候选（双路未齐、产品未实施），本 plan 全部 S1/S2 为条件计划；O12 最终 API/文件名可能与候选不同 | O12 gate 通过后按 plan L38/L63 实读校正；在此之前不得声称 implementation ready |
| O12 裁决跨项段“递增”措辞未限定不同指纹，若 O12 owner 测试按字面落地将与 UM-A09 同内容保版本互斥 | O12 plan gate（就近钉死测试断言范围）；本 WU 实施前硬核对 L38 已含读 O12 owner 测试 |
| 冻结 A04 不覆盖“已有不同内容 create 无 overwrite”，CLI 补跑前不能声称修复可用（plan L119 已登记） | 本 work unit final closeout 的真实 CLI 证据清单（O14-F01 标签） |
| O13 健康重复 delete 时间幂等（UM-O13-F01 未实施）、O18 amended、O33 auto 并发 skip | 各自 work unit；本项仅回归不误判 |
| 损坏（REPAIR_REQUIRED）tombstone 重复 delete fail closed 与 O13 幂等目标的潜在张力（总控已裁 fail closed） | O13/repair owner |
| material tombstone create 无 overwrite 仍是 storage 拒绝（`storage_io` 文案误导），用户可见终态未改善 | goal 未覆盖的 tombstoned create 语义 → 后续 goal confirmation |
| `REPAIR_REQUIRED`/`UNSAFE` 的 material repair 授权未裁决 | 后续 goal/repair owner |
| S2 “writer-owned 复验”若被实现为 O12 guard 内比较之外的第二比较路径 | plan L63 白名单校正条款；实现审查按“复用 O12 唯一 guard 比较，不新增第二比较函数”验收 |
| 两进程真实 CLI 竞态无确定性 barrier | plan 已定注入式测试为准 |

## 实际验证证据（本轮实读清单）

- SHA 实测：plan `4ae27dadd044b3ed4185079a0397a90f9eeb4bbc1faad25fab6f2426b4f9a7f4`（与派发一致）；`git status --porcelain` 仅五份未跟踪文档，无代码漂移；`AGENTS.md` 与主工作区逐字一致。
- 本轮实读代码：`docling_upload_service.py`（`UploadOverwritePrecondition`/`evaluate_upload_overwrite_precondition` 251-285、`_build_upsert_meta` 288-331、`prepare_upload` 370-545（delete 早退 447-453、filing 闸 462-463、update-missing `FileNotFoundError` 464-465、skip 分支 479-499）、`replace_existing`→`reset_source_document` 685-711、`_can_skip_upload` 1616-1648、`_build_upload_source_fingerprint` 1651-1742（material `identical_skip_safe=True` :1735）、`_resolve_document_version` 1745-1770、`_increment_document_version` 1798-1817、`resolve_upload_action` 1892-1914、`commit_prepared_upload_batch` 1382）；`upload_failure.py`（`FinsUploadFailureKind` 28-34、`FinsUploadFailureCode` 37-54（无 target 码）、`FinsUploadFailureReason.__post_init__` 97-122、`FinsUploadFailureError` 146-165、分组断言 168-211、`fins_upload_failure_from_exception` 214-286（无 typed 直通分支）、`fins_upload_source_publication_conflict_failure` 399-418（“目标 filing…”文案））；`ingestion_runtime.py`（`FinsUploadUsageCode` 673-704、`FinsUploadUsageError` 743-763、`_USAGE_MESSAGES`/`fins_upload_usage_failure` 1027-1097、`validate_fins_upload_filing_request` 1457-1529（filing typed usage 映射 1506-1514）、`_validate_runtime_upload_request` 4714-4750（material 只 normalize）、`_save_failed_from_exception` 5986-6013、`_classify_direct_error` 7046-7076）；`upload_tools.py` 50、101-141；`tools/error_contract.py:24`；`cli/commands/fins.py:185-205`（`FinsUploadUsageError`→`EXIT_USAGE_ERROR`+owner message）；`storage/source_meta_contract.py:13`、`_fs_source_integrity.py:170`（material 支持）、`repository_protocols.py:400-412`（`FilingUploadPublishedState` filing-only）、`_fs_storage_infra.py:417/676`、`_fs_source_document_core.py:349/1707/1822`；`sec_upload_workflow.py:502/536/537/562`（UPLOAD_STARTED→公司 batch commit→prepare→材料 commit 的两 commit 现状）。
- 文档实读：goal、plan、adjudication 全文；上轮 review 全文；主工作区 UM-O13/O14/O15 oracle 裁决全文（A04 系同内容 create、A09 同内容恢复保 v3 且不外推、A11-A13 `storage_io`+公司副作用、O13-F01 时间幂等未实施）；O12 候选 plan 与其 plan-review 裁决全文（fix3 候选含 F8 meta 合同、单 batch/guard/alias 优先、恢复测试限定不同指纹）。
- 符号存在性核验：接缝表 10 个定位点全部命中；O12 落地文件（`_fs_material_upload_state_core.py` 等）在本 checkout 不存在（条件计划确认，未以候选冒充集成代码）。
- 预检 canary：`/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.e2MzjU/canary.txt` 经工具读取，内容 `mimo-8227b431`（CANARY 行逐字登记于文首）。

## Final plan review conclusion

**pass-with-risks**

理由：fix3 把 F8/F9/F10 全部收敛进可验收文本且与实读代码同真——F8 的 COMPLETE tombstone 全量 meta（含 `source_fingerprint`）+ 独立 revision 硬依赖贯穿 L24/L38/L42/L115 并与 O12 候选现行合同、O13 A09 可同真；F9 三层 enum 增量与 `upload_failure.py`/`ingestion_runtime.py`/`docling_upload_service.py` 现状逐字吻合，`test_upload_failure.py` 已入双切片白名单与验证命令，“无新 schema”矛盾消除；F10 两格与 `_resolve_document_version`/`_can_skip_upload`/`_build_upsert_meta` 的现行行为逐格一致，且 plan 明文防止把 O12 不同指纹测试外推成“所有恢复递增”，与 source version owner、UM-A09 无冲突（O12 裁决措辞的下游执行风险登记至 O12 gate）。旧 F1–F7、OQ1–OQ3、C1/C2 逐项核验无回退；状态矩阵与 guard/alias/typed 投影在 O12 契约下可实施。新发现仅 **Finding 1（低）**：tool/记录投影面“同一 kind/code/message”存在强/弱两种读法，强读法与 L70 白名单互斥，需一句话收窄或显式扩白名单二选一。**本 plan 仍是条件计划**：O12 尚未 accepted+integrated，依其停止条件 O12 未就绪即停；Finding 1 可随下次 plan 触碰闭合或由总控登记为残余接受，不构成对设计的推翻。建议总控据此裁决 plan gate，并在 O12 gate 就近钉死其恢复测试的指纹范围措辞。
