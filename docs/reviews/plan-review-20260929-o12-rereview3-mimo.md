# UM-O12-F01 plan 独立 adversarial 第三轮 re-review（o12-plan-rereview3-mimo）

- RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
- CANARY=mimo-d4fefe05
- Review target：`docs/gateflow/upload-material-o12-company-plan-20260929.md`（SHA-256 `cf39265253676c63b65a6e29f41bee0e0c7193c1853e40392b02675e15f979cb`，preflight `shasum -a 256` 实测匹配，无漂移）
- Review scope：修订后 plan 全文，重点为 O12 缺名准入、同版 snapshot、单 batch、alias 优先、typed 发布冲突五性质保持；COMPLETE tombstone `source_meta`、`auto` 解析、`prepare_upload` 时间/版本连续性、REPAIR_REQUIRED/UNSAFE 可信性、O13 同内容恢复保持版本 v3/不同内容递增的代码反证；语义所有权漂移、storage guard 可实施性、测试白名单、README
- 读码基线：隔离 checkout `/private/tmp/dayu-upload-o12` HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`（plan 声明一致；全部 code fact 于本 checkout 直接核读）
- Binding scope contract：`docs/gateflow/upload-material-o12-company-goal-20260929.md`（Goal Confirmation）；已接受裁决：`docs/gateflow/upload-material-o12-plan-review-adjudication-20260929.md`（含“COMPLETE tombstone 完整可信 meta 必须在 O12 storage owner”跨项裁决，高严重性 accepted）；主工作区 oracle：`/Users/leo/workspace/dayu-agent-r/docs/reviews/upload-material-um-o12/13/14/15-oracle-adjudication.md`；项目约束：`AGENTS.md`
- 方法：按 planreview skill 对修订 plan 逐假设证伪；本轮不复用前两轮结论作证据，全部关键声明独立重读代码；UM-A19/A20/A21 仅作旧 commit `fac32ecb...` 观察。未派发子 Agent，未实施任何修改。

## 1. Assumptions tested（压测结论）

| # | 待反证假设 | 压测结果 |
| --- | --- | --- |
| A1 | 五项硬性质在修订 plan 中保持 | **成立**。缺名准入：admission 只 catch `UploadCompanyNameRequiredError`→`COMPANY_NAME_REQUIRED`（§2），与 filing 先例 `ingestion_runtime.py:1517-1525` 同构；同版 snapshot：`read_material_upload_state` 单 publication guard 读（§1），镜像 `FilingUploadPublishedState`/`_fs_filing_upload_state_core.py:73-137` 先例；单 batch：§3 “prepare_upload 完成后才唯一一次 begin_batch……唯一一次 commit_batch”，明确消除两段 commit（现状实锤：`sec_upload_workflow.py:523-536` 公司 batch 先 commit→`:537-560` prepare→`:562-568` 另起 batch；`cn_pipeline.py:1139-1184` 同构），filing delete 单 batch 形状可复用（`sec_upload_workflow.py:236-260`）；alias 优先：§3 “alias/identity guard 先于 material observed-state precondition……双冲突保留 ticker_alias_conflict”，且点名现状 merge 早于 alias 扫描（`_fs_storage_infra.py:766-791`：merge 于 768、alias 扫描于 778-791，merge 可先抛 `CompanyMetaConcurrentUpdateError`）必须重排——声明与代码一致；typed 发布冲突：`source_publication_conflict` code 已存在（`upload_failure.py:51`），现有构造器文案确只指 filing（`fins_upload_source_publication_conflict_failure`，399-418），mapper 无 `FinsUploadFailureError` 提取分支、泛异常 fallthrough `UNEXPECTED_RUNTIME`（214-286）与 plan 缺口描述一致。 |
| A2 | 可信 COMPLETE tombstone `source_meta` 必须在场，可实施 | **成立**。`_fs_source_integrity.py:_inspect_source_directory`（457-631）对内容完整的 tombstone 返回 COMPLETE/REPAIR_REQUIRED，`business_meta` 为全量 meta 去私有 revision（`_source_meta_without_revision`，1781-1799），含 `is_deleted=true`、`deleted_at`、`document_version`、`first_ingested_at`、`created_at`、`source_fingerprint` 等全部 canonical 字段；`persisted_meta`/`revision` 同次读取同版。plan §1 的“在场+全量+revision 独立同版”与 inspector 能力精确匹配，跨项裁决的 O12 storage owner 要求已被 plan 吸收（§1、R1、测试 1/2）。 |
| A3 | `auto` 对可信 COMPLETE tombstone 解析为 `update` | **成立**。`resolve_upload_action`（`docling_upload_service.py:1892-1914`）仅按 `previous_meta is None` 分派：非 None→`update`，不看 `is_deleted`。snapshot 携带非 None tombstone meta 时 auto→update 由现有真源直接保证；plan “不能从 None 或独立 tombstone 标记猜测”正确。MISSING（meta=None）→create 也与现状一致。 |
| A4 | `prepare_upload` 时间/版本连续性依赖该 meta，plan 测试断言与代码机制吻合 | **成立**。`_build_upsert_meta`（288-331）：`first_ingested_at`/`created_at` 取自 `previous_meta`（缺失时 `_text_meta` 静默回退 now，2162-2176——正因如此 tombstone meta 必须全量保留，plan 测试断言该两项不变是对的）；`_can_skip_upload`（1616-1648）对 `is_deleted=true` 强制不 skip；`_resolve_document_version`（1745-1770）同指纹保持旧版本、异指纹 `_increment_document_version` 递增；`_build_upsert_meta` 复位 `is_deleted=False`、`deleted_at=None`。plan 测试 2 的不同指纹恢复断言（时间不变、版本从旧版递增、is_deleted 复位、deleted_at 清空）逐项可被现有机制证实。 |
| A5 | O13 同内容恢复保持 v3/不同内容才递增不被本 plan 破坏 | **成立（性质保持，端到端断言缺位降为残余）**。同内容 tombstone 恢复保持版本、异内容递增由 A4 的 `_can_skip_upload`/`_resolve_document_version` 现有语义保证，且已有参数化测试双分支覆盖：`tests/fins/test_docling_upload_service.py::test_execute_upload_deleted_input_republishes_complete_source`（2963-3066，`source_kind`×`changed_input`，断言 `expected_version = "v2" if changed_input else created_meta["document_version"]`、`first_ingested_at` 不变、`is_deleted` 复位）。plan 测试 2 只测不同指纹分支经 admission 供 meta 的路径；同内容端到端（auto+同指纹→真恢复非 skip）未新增断言，见 RR2。 |
| A6 | REPAIR_REQUIRED/UNSAFE 的可信性契约可直接实施 | **不成立，见 F1**。plan §1 与 §2 对 UNSAFE 的 `source_meta` 投影、fail closed 位置存在两种以上读法，且与 filing 先例的类型不变量和失败形态冲突；REPAIR_REQUIRED-with-meta 的 material 准入语义未定。 |
| A7 | storage guard/单 batch/alias 重排可实施 | **成立**。`commit_batch`（`_fs_storage_infra.py:533-611`）pre-commit 失败 `_rollback_precommit_batch` 零发布；`_commit_batch_with_publication_guard`（676-735）在 publication guard 内 backup/swap，插入点在 692 取 guard 与 702 首次 backup 之间；无 company intent 的 batch 也走该路径（560-563），keep/skip 注册 precondition 后可检查漂移；`begin_batch` copytree 复制既有 tree（486），空 batch commit 不毁数据；锁序 recovery→identity→publication（635-643）与 plan 一致，alias（identity guard 域）先于 precondition（publication guard 域）可成立；alias 前置判定后仍保留最终 staged identity 唯一性校验（plan 已要求），不改判定标准。一个实施陷阱见 RR1（guard 非重入）。 |
| A8 | typed 冲突投影链与 job/direct/observation 同源可实施 | **成立**。`FinsUploadFailureReason` 为 kind/code/message/retry_hint/file_label 的 closed 结构（80-141），job 已写 `failure_summary=reason.to_json()`（5024-5028）；plan 的 mapper 优先提取 `FinsUploadFailureError`、两个上传异常边界构造同一 summary、material 专用 conflict 构造器保留 filing 文案，均是对现有缺口的最小收口（缺口本身 A1 已核）。 |
| A9 | 白名单/签名迁移面/环境/README 可实施 | **成立**。`FinsIngestionRuntime.create(` 全仓 12 个代码调用点与 plan 清单逐条一致（`service_runtime.py:579` + 测试 11 处）；Service `upload_material` raw kwargs 调用点 3 处与 plan 一致（`fins.py:725`、`test_fins_direct.py:768`、`test_fins_commands.py:412` 假 Service 签名）；白名单 13 个测试文件全部存在；`.venv` 缺失声明实测属实（`ls .venv/bin/python .venv/bin/pyright .venv/pyvenv.cfg` 全部失败）；README 决策（本 plan 轮不改 + 触发规则核对四份 README）符合 AGENTS.md 触发节。新 test 文件边界见 RR3。 |
| A10 | 无 goal drift、无过度设计 | **成立**。tombstone meta 合同（跨项裁决）、单 batch（裁决 F1 accepted）、alias 次序与严格比较（裁决 F2 accepted）、typed 冲突（裁决 F1 accepted）、恢复连续性测试（裁决明文要求的 owner 测试清单）逐项映射到已确认 goal/裁决，无新增目标；`MaterialUploadPublishedState`/窄 facade/batch 注册镜像 filing 既有结构（`FilingUploadPublishedState` + `FsFilingUploadStateRepository` + `stage_company_meta_intent` 先例），batch-scoped precondition 为裁决已判“必要非过度”的最小机制。 |

## 2. Findings

### 1-未修复-[中]-REPAIR_REQUIRED/UNSAFE 的状态投影与 fail closed 形态存在多义，且与 filing 状态先例冲突，同一描述可实现出三种用户可见行为

- **位置**: §1 storage 同版状态段（“`source_meta=None` 仅用于真正 MISSING 或无可信 business meta 的 UNSAFE”“meta 与 revision 一致”“REPAIR_REQUIRED 若有可信完整 meta 则保留同版 meta/revision；若不具备，读取在 storage owner fail closed”）；§2（“MISSING 才可按 `None` 解析；UNSAFE、无可信完整 meta 的 REPAIR_REQUIRED 在状态 owner fail closed，不进入 action 解析”）；测试 1（“UNSAFE 不猜作 tombstone 或 MISSING，无可信完整 meta 的 REPAIR_REQUIRED fail closed”）。
- **问题类型**: 契约缺失 / 语义所有权 / 架构边界。
- **当前写法**: §1 允许 `source_meta=None` 只覆盖“无可信 business meta 的 UNSAFE”（暗示 UNSAFE 带可信 meta 时 meta 在场），§2 又说 UNSAFE 整体“在状态 owner fail closed，不进入 action 解析”；fail closed 的位置（read 抛错还是返回 typed state 由 validator 拒绝）和 typed 错误形态均未命名；REPAIR_REQUIRED-with-meta 的 material 准入语义（普通目标进 action 解析？还是 filing 式 auto+repair？）只用排除法暗示“可进入”。
- **反例/失败场景**:
  1. UNSAFE 带保留 meta 是**可达真实状态**：`_with_unsafe_classification`（`_fs_source_integrity.py:1595-1630`，“保留可信私有 content facts但不再公开 revision”）经 `_apply_manifest_facts`（1333-1338、1344-1347、1391-1394，shared manifest untrusted/cross-source inconsistency）作用于 exact target 时，`business_meta` 在场而 public revision=None。按 §1 字面实现会把该 meta 放进 `source_meta`，此时“meta 与 revision 一致”无定义（revision 不得对外投影）；若 validator 漏 status 门禁，该 meta 进入 `resolve_upload_action` → auto 解析为 `update`/`create`，把完整性损坏目标当正常目标推进 prepare/commit。
  2. 按 §2 字面让 read 对 UNSAFE 抛错：与 §1 的类型不变量（None-for-UNSAFE 描述的是**返回态**）、测试 1 的“UNSAFE 不猜作 tombstone 或 MISSING”（只能对返回态断言）以及 filing 先例都不一致；用户可见错误在“operational 读失败”与“typed 状态拒绝”之间分叉。
  3. REPAIR_REQUIRED-with-meta：filing 的既有 owner 行为是专用路径——非 auto 报 usage `EXISTING_SOURCE_REPAIR_REQUIRES_AUTO`、auto 强制 `resolved_action=update` + `ExistingSourceAutoRepair`（`ingestion_runtime.py:1484-1494`）；plan 未声明 material 是复用该语义、还是当普通目标进 `resolve_upload_action`、还是 fail closed。三种选择产生三种用户可见行为（usage 错误 / 普通 update 成功 / typed 拒绝），且 material 恒传 `NoExistingSourceRepair()`（`sec_upload_workflow.py:545-556`、`cn_pipeline.py:1155-1177`）使“普通 update 覆盖 repair 目标”成为隐式语义决定。
- **为什么有问题**: 项目约束要求状态语义与失败形态有唯一 owner 并在实施前定死；本 plan 的核心论点就是“复用 filing 先例”，而 filing 对这三问**全都有现成答案**：`FilingUploadPublishedState.__post_init__`（`repository_protocols.py:431-443`：MISSING/UNSAFE 强制 `source_meta=None`——**无论 business_meta 是否存在**；COMPLETE/REPAIR_REQUIRED 强制带 meta）、`_fs_filing_upload_state_core.py:115-122`（UNSAFE→None 投影、可信态缺 meta RuntimeError）、`_validate_filing_upload_published_state`（`ingestion_runtime.py:1416-1456`：status/meta 不变量在 admission 复核）、`validate_fins_upload_filing_request`（1481-1483：UNSAFE→`FinsUploadPrevalidationError(fins_upload_source_integrity_unsafe_failure())`，code `source_integrity_unsafe`，`upload_failure.py:355-373`）。plan 未钉死镜像这套先例，反而引入“无可信 business meta 的 UNSAFE”这一 filing 类型不变量不存在的类别。前两轮裁决已确立“owner 契约须在 plan gate 定死，不能留给实施 Agent”的口径（rereview2 F2 同类 accepted），本项按同一口径处置。
- **直接证据**: 见上列行号；另 plan 测试 2 的 admission 用例清单（fresh/existing/tombstone/缺损 meta）不含 REPAIR_REQUIRED-with-meta 的准入断言，测试 1 只测读侧，准入语义两头都无验收锚点。
- **影响**: 实施 Agent 在 degraded-state 角落自行发明投影（错误码分叉：`source_integrity_unsafe` vs operational `storage_io` vs 误入 action 解析）；UNSAFE-with-meta 漏门禁时可把损坏目标推进 prepare/commit（语义损坏面）；与 filing 行为漂移后，同一 `source_integrity` 语义在两 kind 下行为不一致，违反语义所有权约束。
- **建议改法和验证点**:
  1. plan 一句话钉死镜像 filing 类型不变量：MISSING/UNSAFE → `source_meta`/revision 强制 `None`（即使 inspector 私有 business meta 在场，也按“不得对外投影”丢弃）；COMPLETE/可信 REPAIR_REQUIRED → 强制 meta+revision 同版在场；REPAIR_REQUIRED 无可信完整 meta → read fail closed（typed 错误，非 `None`）。
  2. 钉死 UNSAFE 的 fail closed 位置与形态：read 返回 typed state（不抛），material validator 在 action 解析**之前**按 status 拒绝，抛 `FinsUploadPrevalidationError` + `source_integrity_unsafe` 类 typed reason（material 文案，处理方式与 `source_publication_conflict` 的 material 构造器一致）；明确不得进 `resolve_upload_action`/`resolve_upload_company_meta_decision`、不得映射 `COMPANY_NAME_REQUIRED` 或 `unexpected_runtime`。
  3. 显式三选一并写死 REPAIR_REQUIRED-with-meta 的 material 准入语义（推荐 O12 保守 fail closed 或“进普通 action 解析”，完整 repair 归 repair/O13+ work unit），并在测试 2 补对应 exact failure kind/code 断言。
  4. 验证点：状态类型 `__post_init__` 测试（含 UNSAFE-with-retained-meta 场景断言 None 投影）；read 测试四态投影；admission 测试断言 UNSAFE/REPAIR_REQUIRED 的 exact typed 错误（非缺名、非 generic、非 operational 混淆）。
- **修复风险（低/中/高）**: 低——纯 plan 文本钉死 + 测试断言补充，机制全部复用 filing 先例，无结构变更。
- **严重程度（低/中/高/严重）**: 中（用户可见错误形态分叉 + 一个潜在语义损坏路径 + 与直接可复用先例冲突；非 O12 主路径，核心缺名/冲突承诺不依赖它）。
- **残余风险**: material 与 filing 在 REPAIR_REQUIRED 上长期语义是否统一，归 repair/O13+ work unit 裁决。

### 2-未修复-[低]-测试 7 运行清单不含 filing publication 回归文件，与测试 4 自设的 filing 不漂移验收不闭合

- **位置**: 测试与验证命令第 4 条（“既有 filing 路径回归，确保 `validate_fins_upload_filing_request` 和 filing 的 conflict 文案/投影不漂移”）与第 7 条（13 文件 pytest 清单）。
- **问题类型**: 测试缺口 / 不可直接实施。
- **当前写法**: 第 7 条的 focused suite 未含 `tests/fins/test_filing_upload_publication.py`（覆盖 `FilingUploadPublishedState`/filing publication conflict 文案与投影的既有测试，grep 确认其引用该契约），也未含其它 filing publication/fresh-validation 套件；补跑条款只以覆盖率达标为触发条件，不以 filing 不漂移验收为触发条件。
- **反例/失败场景**: 实施修改 `upload_failure.py` mapper（优先提取 `FinsUploadFailureError`）或 `ingestion_runtime.py` 共享段后按第 7 条命令验证，filing conflict 投影漂移不会被 focused suite 全覆盖，第 4 条验收只能靠实施者自觉补跑；gate 复审时“filing 不漂移”缺可复现命令锚点。
- **为什么有问题**: plan 自设验收（第 4 条）与自设命令（第 7 条）不闭合；与裁决 F2“白名单/调用面机械完整”同一精神——验证面也须机械完整。
- **直接证据**: plan 第 4/7 条文本对照；`tests/fins/test_filing_upload_publication.py` 存在且覆盖 filing publication 契约；`validate_fins_upload_filing_request` 的测试分布在 `test_fins_ingestion_runtime.py`（已在清单）等文件。
- **影响**: 低——filing 行为本不应变且部分已被清单覆盖，主要是 gate 自证成本与漂移漏检风险。
- **建议改法和验证点**: 第 7 条命令补入 `tests/fins/test_filing_upload_publication.py`（如实施触及共享 mapper/runtime，再补 `tests/fins/test_filing_upload_fresh_validation.py` 等实际受影响的 filing 套件）；或第 4 条点名其验收以哪些命令为准。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## 3. Open Questions

- **OQ1（随 F1 收敛）**: REPAIR_REQUIRED-with-meta 的 material 准入语义三选一（fail closed / 普通 action 解析 / filing 式 auto+repair）；若选“普通 action 解析”，须声明其等价于借用 update 覆盖完成修复、完整 repair 语义留后续 WU。
- **OQ2（随 F1 收敛）**: material UNSAFE 的 typed reason 是复用 `fins_upload_source_integrity_unsafe_failure`（filing 文案）还是新增 material 专用构造器（与 `source_publication_conflict` 的处理方式对齐）。
- **OQ3**: 实施 gate 是否允许新增测试文件（“精确白名单”字面只把“回 plan gate”条件给到新增生产文件）；若允许新测试文件，写明规则；若不允许，明确新测试矩阵落位（如 `test_fins_storage_provider.py`）。

## 4. Residual Risks 与跟踪去向

- **RR1（实施陷阱，接受）**: publication guard 非重入——`RuntimeFileLock` 明示“不承诺 reentrant 语义”（`dayu/runtime/filelock.py:121-123`，py-filelock 每实例独立 OS 锁）。commit-guard 内重读必须走 unguarded 内部读取（`_inspect_source_kind_unguarded`、`_read_published_company_identity` 形态），不得在 guard 内调用 `read_material_upload_state` 公共读或 `_read_current_company_meta_for_commit`（其会重取 guard，`_fs_storage_infra.py:812`）；误用会自死锁，测试 1 的 guard 内同步点会暴露。→ 跟踪：storage owner 实施注意；建议 plan 顺手补一句“guard 内重读用 unguarded 读取”。
- **RR2（测试面，接受）**: O13 A09 同内容 tombstone 恢复（真恢复非 skip、版本保持）的端到端断言未入 plan 测试 2；机制层双分支已由 `tests/fins/test_docling_upload_service.py::test_execute_upload_deleted_input_republishes_complete_source` 参数化覆盖，plan 测试 1 的 tombstone 全量 meta 断言 + 测试 2 的不同指纹连续性断言共同覆盖 feed 面。建议测试 2 顺手补一条 auto+同指纹 restore 断言（不 skip、版本保持、时间不变）。→ 跟踪：O12 实施 gate 测试清单。
- **RR3（白名单边界）**: 新增测试文件是否越白名单未写明（见 OQ3）。→ 跟踪：plan gate 一句话。
- **RR4（plan R1/R2/R3/R4/R5 主体接受）**: COMPLETE tombstone 被投影为 None / UNSAFE 当 MISSING / REPAIR_REQUIRED 未 fail closed 时停止回 gate（R1）；严格全等使良性并发冲突、可基于新状态重试（R2）；三处只读时点差共用 validator（R3）；单 batch 是通过条件（R4）；first swap 后双重故障不属本项（R5）。与前两轮接受口径一致。→ 跟踪：对应 work unit / gate 复核。
- **RR5（oracle 边界，接受）**: `CompanyMetaConcurrentUpdateError` 双投影（material→`source_publication_conflict`，filing 维持既有 `STORAGE_IO`，accepted oracle 锁定）；material 恢复/repair 全语义、O14/O15 目标动作表、O13-F01 重复 delete 幂等均不属本项。→ 跟踪：O13/O14/O15 / repair WU。
- **RR6（环境，非产品）**: 本 checkout 无 `.venv`（本轮实测属实），plan 测试 6 的环境 gate（`VIRTUAL_ENV`/`sys.prefix`/`sys.executable`/3.11/`pip show pyright pytest pytest-cov`）是实施前置；环境缺失误判产品失败是显式非目标。→ 跟踪：实施 gate。

## 5. Final plan review conclusion

**fail**（一处中等 owner 契约钉死 + 一处低验证闭合，均为 plan 文本局部修订；非结构性重写）。

理由：修订 plan 对前两轮 accepted finding 的收口经逐条代码反证全部成立——单 batch/单 `commit_batch` 原子收拢写成无条件实施要求并覆盖旧两段 commit 注入窗口（§3、测试 3 窗口 C、R4 安全阀）；比较语义钉死为唯一纯函数 + `CompanyMeta` 五字段全等 + 完整 canonical business meta 与 opaque revision 严格比较 + alias 先行 + `prepare_upload(previous_meta=admission.observed_state.source_meta)`（§1/§3），与 `_fs_storage_infra`/`company_meta_contract`/`prepare_upload` 现状机制一一对应且可实施；跨项裁决的 COMPLETE tombstone 全量 `source_meta` 合同已被 §1/R1/测试 1/2 完整吸收，`auto`→update、时间/版本连续性与 O13 同内容保 v3/异内容递增性质均经 `resolve_upload_action`/`_build_upsert_meta`/`_can_skip_upload`/`_resolve_document_version` 及既有参数化测试证实保持；缺名准入、同版 snapshot、typed 发布冲突、签名迁移面（12+3 调用点）、环境声明、README 决策全部核实无漂移，无 goal drift、无过度设计。但 F1 暴露 REPAIR_REQUIRED/UNSAFE 的状态投影（UNSAFE-with-retained-meta 可达形态下 meta/revision 一致性无定义）、fail closed 位置（read 抛错 vs validator typed 拒绝）与 REPAIR_REQUIRED-with-meta 准入语义在 plan 文本内多义，且与 filing 状态先例（`FilingUploadPublishedState`/`validate_fins_upload_filing_request`）显式冲突——三种实现产生三种用户可见行为，其中一个漏门禁路径可把完整性损坏目标推进 prepare/commit；按“owner 契约须在 plan gate 定死”的既定裁决口径，修订前不进 implementation。F2 为测试命令与自设 filing 不漂移验收的闭合缺口。两处均为局部修订（F1 一句话镜像 filing 先例 + 测试断言，F2 补一行命令），修订并双路复审后可放行。
