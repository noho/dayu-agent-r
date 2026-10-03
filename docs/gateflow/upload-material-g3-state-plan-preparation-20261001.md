# upload_material G3：公司 / 材料状态闭环 preparation proposal

- 任务 `pr197-g2g3-plan-preparation-sol-20261001-01`；**仅 preparation，非 accepted plan、非 gate pass、非产品实现、非测试 pass**。
- 唯一 workspace `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`；PR197 用户手工 merge，main 不动。
- 唯一产品/docs 证据版本 `3a836a463aab3eeffb050facd592e614801d6ca9`（pin），未读当前 F5 writer90509 产品或在途报告。
- 证据根 `workspace/tmp/pr197-g2g3-plan-preparation-sol-20261001-01/`；freeze SHA256 `14a696de1eb6ac568adf91dcb8f4b56fd637427a415ab17e31ec6c41d7898c47`，40 pinned 与 exact Git bytes 匹配；唯一 absent `tests/fins/test_filing_upload_state_repository.py` 不是现存测试。
- G1 preparation 副本 SHA256 `71f6a639a2b76974816999f54b7c553aaf16ef397c34ff986489be761f4f4e05`，只作 proposed 依赖；G2 proposal 同样不是 accepted role API。
- 必要 supplemental 只由 exact OID git show 落独占目录，hash/读取范围/实际 caller索引在 `evidence/`；无可变产品读取、网络、运行产品或修改旧裁决。

## 1. goal 映射与唯一行为增量

动机成立：pin material 在 started 后独立提交公司，再检查目标/转换；目标状态错误迟报且 amended 未入材料发布事实，重复 delete 重写 tombstone。根因分别在 state admission、publication、source mutation owner；不合成统一 godfact/godbag。
唯一增量 **G3-S1：同版公司/材料准入到独立公司 commit 与材料条件发布、终态事实**；以下时序/矩阵是同一个增量，不按动作、模块或 label 拆小 slice。
依据顺序：本轮用户明确要求→正式 UM adjudication→accepted goal→旧 planreview 的最新有效 root 裁决；保留 label 独立验收。

| label | binding（docs/reviews 的 `upload-material-um-*-oracle-adjudication.md`；docs/gateflow 对应 goal） | 本组兑现 |
| --- | --- | --- |
| O12-F01 | o12；`upload-material-o12-company-goal-20260929.md` + O34 | 状态条件 name 前置 typed；合法公司事实独立 commit，材料失败/取消可保留；不得新建公司+材料共同事务 |
| O14-F01 | o14；`upload-material-state-goal-20260929.md` | active create 无 overwrite，同/异 bytes 均前置 typed 拒绝；无公司/文档业务发布 |
| O15-F01 | o15；同 state goal | missing update 含 overwrite 拒；never-existed delete 拒；合法 tombstone 不等 missing |
| O13-F01 | o13；`upload-material-o13-tombstone-goal-20260929.md` | 首删记周期；重删 deleted 成功但日期/revision/meta/manifest/assets 不重写；恢复后再删新周期 |
| O18-F01 | o18 + 同字节/overwrite补充裁决；`upload-material-o18-amended-goal-20260929.md` | 非 overwrite 同字节异 amended 仅元数据；overwrite 强制转换发布，版本依含 G2role 的指纹；delete 请求默认 false 不清 published true |

O12 旧 plan gate pass **不是已实施 API**；state/O13/O18 旧 gate 状态不自动升级。本组 proposal 消化必要旧 fix，仍须最终 source/API 重绑及正式双审，不改旧 goal/plan/adju。

## 2. pin 实际 owner 与 proposed 最小 API

R=`dayu/fins/ingestion_runtime.py`，D=`dayu/fins/pipelines/docling_upload_service.py`，U=`dayu/fins/upload_usage_contract.py`，S=`dayu/fins/storage/`；行号均 pin。

| 实际证据 | 最小设计 / gap |
| --- | --- |
| S `repository_protocols.py:401–505`、`_fs_filing_upload_state_core.py:73–235` | 同版 company/source/integrity 只支持 filing；不能直接用于 material。**proposed** 窄 `MaterialUploadPublishedState`（company_meta、source_integrity、source_meta 三项），deep immutable/构造不变量；`MaterialUploadStateRepositoryProtocol.read_material_upload_state(ticker: str, document_id: str)` 返回该 state，单 publication guard 内 exact-target inspector + strict company parser |
| S 同上 + `source_integrity.py` revision；`_fs_source_snapshot.py:733–829` | 使用 storage-owned classification/opaque revision，不从时间/JSON私有字段猜。COMPLETE active/tombstone 均保可信 business meta；MISSING/UNSAFE 公开 meta=None；REPAIR_REQUIRED 可携可信meta或None，但两格所有动作均fail closed。full read snapshot 拒 tombstone，不能拿它代替 admission state |
| R:1460/1526/4748；D:246 evaluator | **proposed** 在既有 validated material handoff 加 required state admission：canonical目标、observed state、resolved action、已有 UploadCompanyMetaDecision；与 G1最终 identity/action/selection/plan校验，不 optional/fallback。静态 factory 与状态 validator职责明确，独立 pipeline 同样在首事件前执行状态准入 |
| `pipelines/upload_company_meta.py:47/130` | `resolve_upload_company_meta_decision` 唯一纯 name/freshness决策；`stage_upload_company_meta_decision` 已可 stage 已判 intent。删除两 workflow 唯二生产使用的旧 `stage_company_meta_for_upload`/导出与旧测试引用，不发布期重读重判输入缺名 |
| D:246/438–455；SEC workflow:477–544；CN:1122–1189 | **proposed** evaluator 明确 source kind + exact missing/active/tombstone（来自 state）；扩 DELETE_TARGET_MISSING，O14/O15稳定非法格在公司决策前拒绝；市场只传同一 admission，不各造状态机 |
| S `_fs_storage_infra.py:417/533/676`；D:1360 | pin 无 material expected-source/post-company commit hook、无 material final outcome。**proposed** 扩 storage 窄协议：`register_material_upload_preconditions(batch, expected_source_state, expected_company_meta) -> None`；注册 writer初始view校验并记录 typed条件，commit publication guard 内最终复验；不得 callback/profile |
| 同上 | **proposed** `commit_material_upload_batch(batch) -> MaterialUploadPublishedState`：只接受已注册 material batch，复用底层 commit机制并在guard内形成实际published meta/integrity快照，正常返回后 caller投影；不是透传wrapper、另造成功契约或 release错误吞掉 |
| S 同版state owner | **proposed** `validate_material_upload_state(ticker, document_id, expected_source_state, expected_company_meta) -> MaterialUploadPublishedState`：单只读publication guard验证并返回同版事实，执行前/拟skip共用；无材料mutation/空材料batch，不从preparation旧值报告skip |
| S `_fs_source_document_core.py:1871–1946` | owner用 `require_source_meta_is_deleted` 精确校验，再 deleted且已deleted整段 no-op：不取新时间、不prepare meta/revision、不写meta/manifest/资产；恢复真实转换。异常/docstring沿四core入口、fs repository、protocol同步 |
| D:275/462/1560/1690；`domain/document_models.py:1029` | metadata-only基底为admission同版 previous business meta，只换amended及更新时间/revision/manifest维护值；不调用content `_build_upsert_meta`套request dates。新增严格 material amended reader于 `source_meta_contract.py`，source/manifest/terminal/read复用，禁止缺字段默认false |
| R:1710/1830/5036；`service_runtime.py:197/235` | pin闭集只有ok/skipped/deleted/failed/cancelled，结果无published_amended。按既裁O18扩metadata_updated及typed结果/summary投影；真实caller为 `_run_material_upload`，不存在旧 `_upload_material_with_pipeline` |

所有 proposed 名称/签名只作最小 review目标，**不是可调用的现存 symbol**。最终 O12 storage API 若由root采用不同名称，按同责任重绑，不保旧别名/re-export。state/decision/asset plan 分别由各owner持有，不复制业务字段为万能袋。

具体 proposed 接口类型与准入迁移：

- `MaterialUploadPublishedState.company_meta: CompanyMeta | None`、`source_integrity: SourceIntegrityClassification`、`source_meta: Mapping[str, JsonValue] | None`；meta深层冻结，revision只在classification，不复制成第四个字段。
- 既有 `ValidatedFinsUploadMaterialRequest` 加 required `state_admission`：仅包含该observed state、`resolved_action: Literal['create','update','delete']`、`company_decision: UploadCompanyMetaDecision`；target来自G1身份和classification，不复制ID/日期/role。它不是第二套raw/validated request。
- 现存 `admit_fins_upload_material_request` **proposed改变签名**为 `(request: FinsUploadMaterialRequest, *, state_repository: MaterialUploadStateRepositoryProtocol) -> ValidatedFinsUploadMaterialRequest`；内部先调用最终G1/G2静态facts owner取得exact目标，再只读state、pure状态/公司decision校验，最后构造完整handoff。构造/validate只做同源pure不变量，不重复I/O或fallback补state。
- CLI按pin `prevalidate_fins_upload_filing_request_for_workspace` 的真实装配模式新增material prevalidator（proposed）：显式request/workspace_root、只读仓储create_directories=false，使用同一admission；Runtime/工具和SEC/CN独立入口显式注入state repository。CLI单次raw构造→同一handoff→Service，拒绝早于Service factory/started；不各自拼state。
- storage三个guard/commit方法的 `batch: BatchToken`、`ticker/document_id: str`、`expected_source_state: MaterialUploadPublishedState`、`expected_company_meta: CompanyMeta | None` 都显式required；skip/pre-execution使用同一个只读validator。guard源码以strict identity/alias parser先校验，再用canonical presence/revision及同版business事实比较。
- material阶段 `expected_source_state`只比较该snapshot的source部分，公司比较只使用显式post-company参数；不拿admission旧company与自己刚合法提交的新company作第三次冲突检查。执行前validator的company参数则为admission同版company，两阶段语义不混用。
- source漂移复用已存在 `SourceIntegrityRevisionConflictError`，company漂移复用 `CompanyMetaConcurrentUpdateError`；material上下文在Fins唯一failure owner投影 `source_publication_conflict`，filing旧投影保全。若最终O12采用统一storage conflict类型则只重绑一个typed合同，不加字符串/异常链猜测。
- material final snapshot在commit guard内由实际stage/published事实形成，source meta严格amended/primary及manifest同源校验在source/schema owner执行。新schema起库，所有合法生产caller显式提供字段；若发现其它material producer不能承诺这些字段，列具体caller gap回root，不默认填false或迁历史库。
- U的 `FinsUploadUsageFailure` **proposed**增加required `hint: str`、`file_label: str | None`，必填非空hint且bounded；普通/target/selector/planner均由U唯一producer产生code/message/hint，不在R保副本。target producer显式required `source_kind: SourceKind`区分同码文案：U仅新增DELETE_TARGET_MISSING；pin publicfailure尚无三个target code，须新增CREATE_TARGET_EXISTS/UPDATE_TARGET_MISSING/DELETE_TARGET_MISSING及kind=USAGE映射，非旧runtime枚举副本。
- format owner仍产生/校验kind与canonical安全label及格式说明（不复制direct_events标签算法）；**proposed**公开typed message/hint属性，U `fins_upload_format_usage_failure(error: FinsUploadFormatError) -> FinsUploadUsageFailure`只统一装箱、校验required hint并保label。R `_raise_upload_format_usage`、CLI早期raw-format及failure mapper全调用它，不各建message/hint表或str(exception)推reason；publicreason.retry_hint仍可空，target/format映入时必须非空。覆盖所有原usage/planner/format种类防必填字段破坏既有路径。
- D的metadata-only准备返回**proposed** `_PreparedMaterialMetaMutation`：仅typed ticker/document_id/internal_document_id与desired_amended，不装revision/company/任意request-meta。storage source owner **proposed** `update_material_amended(*, batch: BatchToken, document_id: str, amended: bool) -> None`在双guard注册通过后，以注册的admission business meta为基底stage，仅改marker及维护字段；D sharedpublication消费该mutation，final bool仍取commit outcome。真实content/delete原准备类型保留，不把三种mutation合成可空godbag。

## 3. 连贯时序：同版、两阶段、复验、certainty

1. F5/G1最终受理完成，G2最终角色API可消费：入口原词法/字段顺序→G1 action/files/identity→G2 selector/资产计划→exact company+source published state。非法输入零started/job/observation/业务写；允许必要read lock，不把lock文件当业务成功。
2. integrity优先fail closed；健康目标由共享action owner准入，然后公司decision。active create无overwrite两种bytes都拒，missing update有/无overwrite与never-existed delete拒；overwrite不变upsert。目标冲突+缺公司名先目标；无files+missing/delete+files+missing先G1组合。
3. 执行前用只读state validator复验admission的source/company，漂移在started/公司业务写前typed拒绝；后续至发布间漂移同样为 `source_publication_conflict`，不能重判原请求缺名/target missing或落generic unexpected_runtime。已接收请求使用immutabledecision；开始事件后允许job/observation存在，但材料失败不得伪造发布事实。
4. 公司stage decision时使用独立company batch与其既有identity/alias最终guard，合法commit正常返回取 `CompanyMetaCommitOutcome.company_meta` 为post-company expected；keep/skip无intent时expected仍为同版observed company，须guard验证而非下游重读。alias冲突优先沿公司owner，原/新公司不污染；公司commit异常不进入材料。
5. 每个content/metadata-only/delete材料batch都先begin（持ticker writer lock）→注册expected-source+post-company双条件→stage一个文档→最终取消checkpoint→commit。writer-owned初始view及publication guard最终复验全部required状态；材料mutation不能覆盖公司阶段后新变化。此后材料失败/取消不回滚已合法公司事实（O34）。
6. prepare拟skip也先完成合法公司阶段，再只读guard验证source/company→只用guard返回已发布事实报告。company-only变更可以独立成功，skip材料不写资产。metadata-only同样允许合法公司阶段更新意图，两事实独立成功，材料失败不撤公司。
7. delete首次/重复的最终published_amended由storage batch的guard通过后**实际tombstone/source meta**形成；不能来自request默认值或prepare旧meta。重删仍deleted、requested/stored=0，首删/重删同源输出；若新API不能返回此bool，具体blocked回storage owner裁决，不在summary补算。
8. material publication生命周期继续归D共享helper：commit前cancel可rollback；进入commit后capability交storage，不再取消/rollback；正常返回才投影本次final outcome。manifest在staging不是成功，公司/转换/started也不是文档成功（O34）。
9. **certainty硬边界**：infra:533–607/676–735已可能COMMITTED后release主异常且durable树保留，`commit_batch`仅回公司outcome或None，缺material final/异常certainty公共事实。本组提出storage正常返回final snapshot，但不自行把postswapreleaseindeterminate改成功、未提交或skip；不按exception字符串/adapter重读推commit阶段。
10. 若final API不能权威区分guard拒绝/未提交/已durable但release异常，记录具体storage gap、phase与owner目标供root，停止涉及certainty的实施/验收承诺；保主异常/既有durable事实、不rollback已提交。不得因此接入独立download indeterminate WU，也不替O33实现并发重试。

## 4. 状态 / amended owner 矩阵

| 状态与动作 | 允许结果 |
| --- | --- |
| COMPLETE active create，overwrite=false | 同/异role-aware指纹均前置typed CREATE_TARGET_EXISTS，不进入skip/公司/Docling |
| MISSING update（overwrite任意）、delete | typed UPDATE_TARGET_MISSING / DELETE_TARGET_MISSING；零公司/材料业务发布 |
| COMPLETE tombstone delete | 成功deleted no-op；首次deleted_at/updated_at/revision/meta/manifest/assets字节不变 |
| COMPLETE tombstone auto/update | update恢复；保ID/首次时间，清deleted态；同有效role-aware指纹保版，异指纹按版本owner增版 |
| tombstone create无overwrite | 保旧source upsert/storage拒绝；不新增typed O14规则或改成成功；若final owner无法保全则回root |
| UNSAFE/REPAIR_REQUIRED任意动作 | typed source-integrity/operational fail closed，不猜missing，不借delete修损坏source |

下表仅已通过动作/状态准入、可信有效旧指纹的active upsert；fingerprint包含G2role，amended不参与identity或fingerprint。

| 指纹 | amended | overwrite | 结果 / 转换 / 内容版本 |
| --- | --- | --- | --- |
| 同 | 同 | false | skipped / 0 / 保持；guard返回published值 |
| 同 | 异 | false | metadata_updated / 0 / 保持；仅标记与维护字段变化 |
| 同 | 同 | true | ok / 全原件 / 保持 |
| 同 | 异 | true | ok / 全原件 / 保持，发布请求标记 |
| 异 | 同 | false | ok / 全原件 / 按既有owner增版 |
| 异 | 异 | false | ok / 全原件 / 按既有owner增版 |
| 异 | 同 | true | ok / 全原件 / 按既有owner增版 |
| 异 | 异 | true | ok / 全原件 / 按既有owner增版 |

首次合法publish v1，标记为请求bool；旧指纹缺失不冒称八格覆盖，保现版本owner规则并列残余，不新增兼容读取。恢复不得因tombstone本身升版。
字段contract：输入仍 `amended: bool`；material请求摘要/started为 `requested_amended: bool`；持久source/manifest内部仍required `amended: bool`；material upload结果/summary及LLM read两个真实列表使用 `published_amended: bool | null`。ok/skipped/deleted/metadata_updated必为storagefinal bool；failed/cancelled为null且不得声称本请求发布，不否定此前durable材料。
metadata_updated是completed，requested>=1/stored=0；ok stored=requested>=1，skip stored=0且requested>=1，delete两者0。最小material结果示例 `{"status":"metadata_updated","requested_file_count":2,"stored_file_count":0,"published_amended":true}`；失败示例 `{"status":"failed","published_amended":null}`。LLM schema说明skip/deleted为当前或最后发布事实、不是本次请求切标记；filing的amended/身份/读列表原字段保持。
新增metadata_updated只允许material，filing typed结果拒绝该status；D内部operation status→市场pipeline status→R terminal disposition映射由各已有owner显式扩展，事件仍terminal completed，不按0文件推skip。既有material warning/filing warning约束不顺手扩展。
`read_runtime`仅改真实 `documents`、`recommended_documents` 的material字段，内部typed meta可保amended；不发明详情表面。processed amended是preprocess时点快照，不能充当当前source；若消费它当现值，停在原owner，不在read默认/重算。

## 5. 必要旧 reviewfix 对应与验证矩阵

| root旧有效约束（docs/gateflow `upload-material-*-plan-review-adjudication-20260929.md`） | 本组owner验收 |
| --- | --- |
| o12 F1/F2/F4、二/三轮same-state/skip、O34替代单batch、PR4-F1–F4 | immutable admission、全部真实create callers、CLI同request/实际命令名、source+post-company双guard、UNSAFE/MISSING不变量；material company-concurrent/guard→publication conflict，filing仍storage_io；删除旧stage helper |
| o12 PR5-F1/F2/F3（accepted plan强制实施条件） | upload专属typed保存只走active-only原子终态API；SUCCEEDED/FAILED/CANCELLED不覆写；终态落盘后progress失败双摘要不变；no-runner同一reason→failure_summary/result_summary.failure；selection只构造不变量，O16组合不重复 |
| state F1–F11、O34/UM-A09更正、C3、PR-C3/C4/C5-F1–F3 | source-kind+三态、漂移不是usage、unsafe拒、同指纹恢复保版；U唯一fact/message/hint，failure.py唯一publicreason；format typed装箱包括safe file_label，不复制direct_events canonicalizer；hint必填只针对usage fact，不收紧全局reason optional hint |
| state PR-C5 | U producer显式source kind用于同码target文案，filing原target文案逐字保留；CLI早期raw-format和runtime/tool同fact，tool只消费message/hint且target协议仍invalid_argument；owner/tool/failure/alias JSON回归 |
| o13 F2/F3/F4/F5、PR2-F1/F2、PR4-F1 | 真storage filing/material首删/重删/恢复/新周期与corrupt is_deleted两方向；KeyError/ValueError链；四core入口/协议/fs façade docstring；不要求首次两个时间逐字相同，不按mtime/inode验业务no-op |
| o18 首轮/PR2/PR3有效项（PR3-F1缺plan推断已撤回） | metadata_updated计数/投影、双guard覆盖所有mutation和skip、真read schema/two lists、八格/overwrite、processed residual、不安全material指纹死分支删除；不再引用旧错误caller |
| **o18 PR4-F1** | A admission/合法公司commit/prepare→B完成source或company commit→A begin_batch/注册/commit拒；B必须在A取得writer锁前完成，避免挂起 |
| **o18 PR4-F2/F3** | 独立identity先publish true，delete无files省略amended（request false）→deleted/published true且0/0；首删/重删final bool由storage返回；failure/cancel请求true→null |
| **o18 PR4-F4/F5/F6** | action合法后才八格；delete/content/metadata-only/skip stale均真storageguard owner断言，O18只注册/消费；metadata-only传不同请求dates等，published所有非amended业务字段逐字段不变；公司更新意图独立正确 |

每格使用真实Fs仓储与controlled converter；fake/mock不能固化迟报/默认amended/旧first-primary。补admission→job执行、pre-yield→batch、prepare→skipguard的真实漂移窗口；稳定输入拒绝与已接收后typed conflict分别断言。竞争重试“一success一skip”的O33验收留G5，当前FileExistsError/真实I/O不转skip。

## 6. 后续允许文件、验证与 README

| 源码 / 测试（仓库相对路径） | 必要范围 |
| --- | --- |
| `dayu/fins/storage/repository_protocols.py`、`_fs_storage_infra.py`、`_fs_storage_core.py`、`fs_batching_repository.py`、`__init__.py` | 窄materialstate/guard/final-outcome协议与装配；复用storage内部锁，不改变download/filing成功契约 |
| proposed `dayu/fins/storage/_fs_material_upload_state_core.py`、`fs_material_upload_state_repository.py` | 仿既有filing稳定view机制但material typed语义；不复制path/lock/canonicalizer，非兼容facade |
| `dayu/fins/storage/_fs_source_document_core.py`、`fs_source_document_repository.py`、`source_meta_contract.py` | tombstone no-op、严格amended、metadata mutation、四入口docstring与实际异常 |
| `dayu/fins/ingestion_runtime.py`、`upload_usage_contract.py`、`upload_failure.py`、`upload_format_contract.py` | 统一state admission/U source-kind fact+hint/format包装、publicreason、typedstatus/amended summary、upload active-only终态 |
| `dayu/fins/pipelines/docling_upload_service.py`、`upload_company_meta.py`、`sec_pipeline.py`、`sec_upload_workflow.py`、`cn_pipeline.py` | 共同准入/公司阶段/materialpublication/metadata-only；去旧stage重判；SEC/CN不复制状态机 |
| `dayu/fins/service_runtime.py`、`dayu/service/fins_direct.py`、`dayu/cli/commands/fins.py`、`dayu/fins/tools/upload_tools.py` | 显式仓储注入/同request/真实命令名、typed事实机械投影；shared download失败路径保持 |
| `dayu/fins/domain/document_models.py`、`tools/read_runtime.py`、`tools/fins_tools.py` | MaterialManifestItem required amended（与G2primary合并），source-reader helper同源；两个LLM列表/schema；触及签名严格JsonValue，不扩processed/filing字段 |
| `tests/fins/test_fins_storage_atomicity.py`、proposed `test_material_upload_state_repository.py`、`test_source_meta_contract.py`、`test_company_identity_storage_contract.py`、`test_filing_upload_publication.py` | 同版/guard/alias/tombstone/metadata/final-outcome/certainty owner；absent filing-state测试不当现有套件 |
| `tests/fins/test_docling_upload_service.py`、`test_upload_failure.py`、`test_upload_usage_contract.py`、`test_upload_format_contract.py`、`test_fins_ingestion_runtime.py`、`test_fins_ingestion_tools.py`、`test_fins_service_runtime.py`、`test_fins_direct_stream.py`、`test_fins_read_runtime.py`、`test_sec_pipeline_upload_material_stream.py`、`test_cn_pipeline.py` | 矩阵及request/published分离、同源错误/计数、active-only/no-runner与filing/download回归 |
| `tests/cli/test_fins_commands.py`、`tests/service/test_fins_direct.py`、`tests/fins/test_cn_download_runtime.py` | CLI/Service真caller；若create新仓储required参数，最后一项仅机械fixture注入并保旧download断言 |

`FinsIngestionRuntime.create` pin实际生产caller是service_runtime:521，测试callers全表见 `evidence/runtime-create-callers-at-pin.txt`；新增依赖required keyword，全部机械迁移，不optional/fallback。独立SEC/CN与DefaultFinsRuntime显式装配同一shared repository set；最终rebind核其它构造caller，不靠getattr发现。
新改函数完整中文参数/返回/异常docstring，类/模块中文概览；严格签名/JsonValue、模块级helper，不引Any/object/getattr兼容、callback/profile、runtime包业务副本或反向依赖。material no-op在canonical deletion及必要provenance完整性验证后才早返，不能吞损坏必需字段；仅no-op跳过revision/manifest写入。

```bash
source .venv/bin/activate
python -m pytest -q tests/fins/test_material_upload_state_repository.py tests/fins/test_source_meta_contract.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_company_identity_storage_contract.py tests/fins/test_filing_upload_publication.py tests/fins/test_docling_upload_service.py tests/fins/test_upload_failure.py tests/fins/test_upload_usage_contract.py tests/fins/test_upload_format_contract.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_service_runtime.py tests/fins/test_fins_direct_stream.py tests/fins/test_fins_read_runtime.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_cn_download_runtime.py tests/cli/test_fins_commands.py tests/service/test_fins_direct.py --cov=dayu --cov-report=json:workspace/tmp/pr197-g3-implementation/coverage.json --cov-report=term-missing
pyright
```

proposed测试需实施新增后才能运行；本轮未pytest/pyright/cov/真实CLI。后续唯一workspace Python3.11/package/最终HEAD绑定；affected pytest/fullpyright及逐改生产文件>=80%必验，触及旧type错误一并修、不只报总覆盖。大文件不足补有意义owner/入口测试，剩余缺口如实给root。
README允许 `README.md`（用户状态/公司条件/name/amended/可行动错误）、`dayu/fins/README.md`（同版/两阶段/终态/重删/revision/严格reader已实现contract）、`tests/README.md`（现存矩阵/运行方式）；按已读职责实施后更新，不写未来pass。新增仓储装配需检查 `dayu/README.md` 边界并按需同步，不改Host/Engine/config。
整体真实CLI由root按 `upload-material-repair-scope-and-ci-closeout-20261001.md`→最终 `docs/cli_ci.md` 重建完整mandatory/new authorized inputs/lineage；本组提供状态链、八格及true→省略amended delete反例，旧Raw不存在不借旧票；本轮不做registry/readiness。

## 7. 分类残余与最终重绑 / 停止

| 分类 | owner / destination |
| --- | --- |
| 本组必要fix，尚未实施 | 五label、O12PR5、statePR-C5、O18PR4-F1–F6及上表有效rootfix；本proposal不标已修/accepted |
| accepted later组 | O33/G5并发authority retry，G4内容失败；本组只完成已裁same-stateguard，不拿I/O/exists当skip |
| 独立残余WU | processed amended时点投影、restore-active幂等、filing amended identical skip、全局usage中立化、历史material迁移；若processed消费者伪装current则停止回原owner |
| API/实施硬停 | 无可信material同版state/两阶段guard/actualpublisheddeletebool/commitcertainty接口；F5/G1/G2最终版本未重绑；具体gap给root，不重问裁决、不造fallback |
| 尚待验证 | 所有自动测试/fullpyright/逐prod80/README/真实CLI/正式双审/PR收口；不借G3做download indeterminate或历史迁移 |

root最终重绑清单：①F5最终writer退出与commit/hash；②G1实际identity/action/request/handoff及局部首错（不是preparation类型）；③G2accepted角色plan/fingerprint API；④O12acceptedplan强制条件与materialstate/公司decision/alias owner实际API；⑤所有mutation及skip的source/post-companyguard、writer锁时序；⑥storage实际finaloutcome/deletebool与releasecertainty能表达的边界，不能表达即具体blocked；⑦source/manifest严格amended与两列表schema/terminal字段计数；⑧production/constructor/caller/fixture全迁移、测试80%/pyright/README清单；⑨锁同版正式双审与root裁决后再实施。两proposal和证据交付即停，不推进gate。
