# upload-filing-ticker-alias-contract second plan fix

## Gate metadata

| 字段 | 值 |
| --- | --- |
| Gate | `plan fix (round 2)` |
| Work unit | `upload-filing-ticker-alias-contract` |
| Fixed plan | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-codex.md` |
| Previous fix | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-fix-codex.md` |
| Rereview adjudication | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-rereview-controller-adjudication.md` |
| Reviewer artifacts | `docs/reviews/plan-rereview-20260814-222224-ds.md`; `docs/reviews/plan-rereview-20260814-222224-mimo.md` |
| Completion status | `second plan fix complete` |
| Current gate / next entry point | `plan re-review` |
| Artifact path | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-fix-2-codex.md` |

## Scope and evidence

本轮完整读取rereview controller adjudication、两份plan-rereview artifact、当前plan与第一份fix artifact。直接代码/data-flow证据确认：`FilingUploadPublishedState.company_meta=None`是公开合法状态；公开storage batch与文档先于meta的恢复/发布边界可形成只有descriptor的corpus；当前direct canonical probe可读取该corpus。因此`missing_meta`不能被提升为workspace corruption。controller补充校验最初把“ingestion runtime不构造material decision”误推成“material不持久化CompanyMeta”；随后基于更深直接数据流纠正：SEC `run_upload_material_stream`与CN `upload_material_stream`的create/update都调用`upsert_company_meta_for_upload`并传递`ticker_aliases`。本artifact以该完整producer/commit链为最终证据。

本轮及controller补充只修订plan与本artifact，不修改生产代码、测试或README，不实施、不提交。next entry point保持`plan re-review`。

## P1 — 已修复：meta-less corpus canonical-only identity

### Owner与index contract

- Storage ticker identity descriptor冻结为published corpus canonical的durable owner；valid CompanyMeta只拥有accepted aliases。二者不是重复grammar：descriptor只保存owner已产生的exact canonical，不解释或推断alias。
- `_scan_actual_published_company_identities()`只枚举`portfolio/`实际directories，strict读取每个descriptor，并返回descriptor canonical + optional valid CompanyMeta。
- `_build_unique_company_identity_index()`先登记每个合法descriptor canonical，再仅登记valid CompanyMeta的`accepted_aliases`。`missing_meta`仍可作为operator inventory诊断status，但从`CompanyTickerIdentityCorruptionKind`与authoritative failure条件移除。
- `invalid_meta`、descriptor invalid、meta/descriptor identity mismatch与durable duplicate owner继续typed fail closed；A4/A6分型不回退。

### Read semantics

- `resolve_company_ticker`机械消费同一unique index。meta-less corpus的canonical query返回自身descriptor canonical并可读取真实documents；它没有accepted aliases，alias query返回NOT_FOUND。
- 无关meta-less corpus不会阻断健康corpus的canonical/alias read；durable invalid/mismatch/duplicate仍投影`workspace_identity_corrupted`，guard failure仍投影`storage_unavailable`。
- meta-less是storage durable state，不由upload kind推断。正常SEC/CN material create/update仍写CompanyMeta；它们的accepted aliases只有成功CompanyMeta commit后才成为durable lookup facts。

### Commit/state transition

- `_ActiveBatchState`新增`publishes_new_corpus`，由`begin_batch`在same-ticker writer下根据首次descriptor publication冻结；不得在commit通过`meta.json`/目录存在重新猜测。
- `company_meta_intent is not None or publishes_new_corpus`进入`writer -> recovery -> identity -> publication`序列化。首次storage-public meta-less descriptor publication虽无meta，也必须在swap前验证descriptor canonical；只有既有corpus且无meta intent的document-only commit保持ticker-only。正常material create/update含meta intent，同样进入identity-changing路径。
- Incoming既有target descriptor合法但meta absent时，authoritative`current_published=None`。`refresh_if_stale(expected_non_identity=None)`允许给合法meta-less corpus首次补CompanyMeta；final canonical self-owner不误报冲突，新aliases仍对其它descriptor canonical/aliases做validation。
- Prevalidation曾观察CompanyMeta但commit-time合法descriptor已无meta时，`preserve_published`或非空`expected_non_identity`统一抛`CompanyMetaConcurrentUpdateError`，在backup/swap前失败；不得归为corruption或用旧snapshot重建。
- Unique validation不排除incoming existing descriptor：published index owner等于incoming canonical可继续，owner为其它canonical才抛`CompanyTickerAliasConflictError`。因此“健康alias先占新descriptor canonical”与“meta-less canonical先存在、后来alias碰撞”两个方向都原子拒绝。

### Validation

- 通过public storage batch/恢复fixture形成的meta-less corpus canonical `list_documents`可读、alias不命中；不得用正常material create伪造该fixture。
- meta-less与健康alias corpus共存时双方正常read。
- 对meta-less corpus补CompanyMeta成功，补齐后的canonical/aliases同corpus。
- canonical conflict双向顺序均在首次backup/swap前typed拒绝，winner tree SHA不变。
- invalid JSON/schema、descriptor invalid、identity mismatch、durable duplicate仍fail closed。
- prevalidation后meta消失走`CompanyMetaConcurrentUpdateError`及有界`storage/storage_io`重试投影，published tree不变。
- 首次meta-less descriptor commit取得global guards；既有corpusdocument-only commit不取，锁序与A7 recovery/read barrier保持不变。

## P2 — 已修复：补齐FmpCompanyInfo测试consumers

- `tests/cli/test_prompt_command.py`与`tests/service/test_entrypoint_runtime.py`已加入§9.3、S1 allowed tests和focused validation。
- 两个fixture必须使用`CompanyTickerIdentity`构造`FmpCompanyInfo`；canonical-equivalent token不得保留为accepted alias。
- Final residue command改为multiline `rg -U`，覆盖上述两文件及`test_upload_filings_from_command.py`的跨行旧constructor fields，避免原单行pattern漏检。

## P3 — 已修复：6-K repair direct branch validation

- 保留A2已关闭的production scope：`sec_6k_primary_document_repair._resolve_target_tickers`只机械迁移到`entry.company_meta.ticker_identity.canonical_ticker`。
- 删除“既有repair regression已直接覆盖”的错误表述。Plan明确现有module regressions没有触达该分支。
- S1必须新增或扩展public-path test，以`reconcile_active_6k_primary_documents(..., target_tickers=None)`精确经过inventory discovery并断言canonical projection；再由该生产文件逐文件branch coverage `>=80%`、residue scan与全量pyright兜底。

## P4 — 已修复：material aliases与filing同源、可靠持久化

### Controller纠正与rejected-with-reason

- 补充校验的首个P4方案曾依据`FinsUploadMaterialRequest`没有prevalidated decision，提出“material非空aliases typed拒绝、CLI改单ticker、删除pipeline消费”。该方案现为`rejected-with-reason`并已从plan完全撤回。
- 更深直接证据是`dayu/fins/pipelines/sec_upload_workflow.py::run_upload_material_stream`与`dayu/fins/pipelines/cn_pipeline.py::upload_material_stream`：两者create/update都在source document publication前开启CompanyMeta batch，调用`upsert_company_meta_for_upload(..., ticker_aliases=...)`并commit。`dayu/fins/service_runtime.py`也确实下传request aliases。ingestion runtime不构造decision不等于pipeline不持久化。
- 若按旧P4拒绝/删除，会破坏既有material CompanyMeta producer、使CLI/tool contract倒退，并把合法accepted aliases错误限缩为filing-only；因此不能实施，也不作为residual risk保留。

### 直接plan修订

- `ticker_aliases`冻结为filing/material共同参数。CLI `upload_material --ticker`继续CSV first canonical + accepted aliases；combined tool schema明确数组适用于两个`upload_kind`，信任声明、不联网核验，成功CompanyMeta commit后与canonical路由同corpus。
- S1将SEC/CN material direct producer明确列入builder迁移：保留request/service/pipeline aliases贯通，删除`upsert_company_meta_for_upload`内部重复fresh/normalization owner，改为稳定`stage_company_meta_for_upload`读取observed meta并调用与filing相同的`resolve_upload_company_meta_decision`和stage helper。fresh新增alias必须stage，不能接受后`keep`。
- S2让filing prevalidation与material direct producer都只stage同一个`CompanyMetaCommitIntent`。material CompanyMeta batch在writer/recovery/identity guards内authoritative重读、stable union aliases、保护更晚nonidentity durable facts并执行workspace uniqueness validation；storage只机械消费domain helper，不自创material merge。
- 正常SEC/CN material create/update继续写CompanyMeta。所有meta-less表述改为storage公开batch状态或文档先于meta的恢复/发布边界；不得再声称正常material create一定不写meta。

### Validation与residue

- SEC/CN material create以`DELTA,MSFT,V.BA`成功后，strict CompanyMeta identity保留`MSFT/V-BA`且不重复canonical；canonical与aliases经S2 route命中同corpus。
- fresh material update新增alias必须stage；跨进程barrier固定P1 filing prevalidation暂停、P2 material producer提交后P1继续，最终stable union两方aliases并保留P2更晚durable nonidentity facts；另测两个material进程由writer串行后均保留aliases，changed-stale仍走`CompanyMetaConcurrentUpdateError`。
- CLI test断言`upload_material --ticker DELTA,MSFT`把canonical/alias精确交给Service；combined schema与material request construction/test断言`ticker_aliases`适用于两个kind且未清空。
- final residue要求`upsert_company_meta_for_upload`零命中，证明重复owner已删除；同时implementation artifact必须列出`FinsUploadMaterialRequest.ticker_aliases -> service_runtime -> SEC/CN stage_company_meta_for_upload -> CompanyMetaCommitIntent`直接调用点，防止用删除数据流伪造零命中。

## P5 — 已修复：descriptor corruption closed kind完整

- `CompanyTickerIdentityCorruptionKind`闭集明确加入`"invalid_descriptor"`，与`invalid_meta`、`identity_mismatch`、`duplicate_owner`并列；descriptor缺失不能只出现在prose而不进入public typed contract。
- `invalid_descriptor`精确覆盖实际published ticker directory缺descriptor、symlink/non-regular、JSON/schema/namespace/external identity/private locator双向关系非法，以及external ticker不是该目录exact canonical。scan把相应`FileNotFoundError`/validation `ValueError`投影该kind；permission/普通I/O仍走storage unavailable/storage_io，不误报durable corruption。
- read测试逐一断言上述descriptor结构损坏为`workspace_identity_corrupted`；identity-changing commit在首次backup/swap前以同kind fail closed且tree SHA不变。合法missing `meta.json`继续canonical-only，不属于`invalid_descriptor`。

## Preserved closed findings

- A1保持closed：commit-time authoritative current、stable alias union、nonidentity optimistic precondition与changed-stale typed failure不变；meta disappearance只纠正为concurrent update。
- A2保持closed：6-K production consumer仍在scope，仅提高测试证据精度。
- A3保持closed：S1 `alias -> list[canonical]`临时contract与S2原子route切换不变。
- A4保持closed：incoming conflict与durable corruption继续分型；只从corruption closed kinds移除合法`missing_meta`，并由P5补齐`invalid_descriptor`。
- A5保持closed：只捕获`UploadCompanyNameRequiredError`。
- A6保持closed：invalid descriptor/meta、identity mismatch与duplicate owner仍在published mutation前fail closed；P5只闭合typed枚举，没有放宽时点。
- A7保持closed：recovery/read barrier及identity guard acquire/release failure测试不变；recovery仍对所有recovered trees取guard。
- A8保持closed：S1仅local checkpoint，S2强制连续完成。
- R1保持`rejected-with-reason`：不以`meta.json`存在推断recovery mutation；新增`publishes_new_corpus`也是live transaction-local fact，crash recovery不依赖它。
- R2保持`rejected-with-reason`：`_STORAGE_FAILURE_CODES`仍是S2 planned-new code，不是当前遗漏。

## Validation and docs decision

- Plan状态已改为`second plan fix complete`，next entry point仍为`plan re-review`。
- P1语义已进入owner、public route、private state、lock/commit state machine、S2 slice、test matrix、README decision与goal alignment。
- P2两个测试已进入affected/allowed/focused清单，并补multiline residue scan。
- P3改为新增direct public-path branch test，不再声称既有coverage。
- P4按完整material producer数据流撤回错误的filing-only拒绝方案，冻结material与filing共用builder/intent/authoritative merge，并补SEC/CN owner、CLI/schema、跨进程与residue验证。
- P5把descriptor缺失/非法加入closed corruption kind及read/commit fail-closed测试；合法missing meta语义不回退。
- 本fix不修改README；implementation仍按plan更新`dayu/fins/README.md`与根`README.md`，其它README decision不变。

## Residual risks

| Risk / uncovered area | Classification | Owner / destination |
| --- | --- | --- |
| 旧workspace歧义alias/旧CompanyMeta schema | `assigned to later work unit` | fresh schema边界；如需升级另立migration WU |
| UF-PF05真实CLI evidence | `assigned to later work unit` | 用户明确排除 |
| oracle/scenario registry、冻结evidence、其它finding | `assigned to later work unit` | 用户明确排除 |
| workspace descriptor/meta scan成本 | `assigned to later work unit` | 仅在真实profile超标后另立性能WU；不新增durable index/cache |
| recovery对所有orphan tree取得identity guard的等待 | `assigned to later work unit` | R1 correctness优先；实测contention后才能优化且不得猜mutation |
| SEC upload/SEC download/CN download既有resolver version不一致 | `assigned to later work unit` | rereview controller裁决为既有行为且本WU不恶化 |

没有unclassified residual risk，没有blocking open question。

## Completion status

第二轮plan fix完成，P1–P5均为`已修复`；旧P4“material拒绝aliases/删除producer”为`rejected-with-reason`且已撤回，A1–A8与R1/R2保持closed。next entry point为`plan re-review`；本轮未进入implementation、未创建commit、未执行PR/push。
