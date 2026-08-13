# UF-FIX01 validation-atomic-boundary — Plan Re-Review（AgentDS 第二路复核）

## Review Metadata

- **Reviewed target**: 修订后 `docs/gateflow/uf-fix01-validation-atomic-boundary-plan-20260813.md`（`plan-fix-complete / re-review-pending`）
- **Fix adjudication**: `docs/gateflow/uf-fix01-validation-atomic-boundary-plan-fix-20260813.md`
- **Reviewer**: AgentDS（第一路 review 的同一 reviewer，第二路独立复核）
- **Review date**: 2026-08-13 10:12:07
- **Plan baseline HEAD**: `b3cb1f1b16f4d552eb762de3be59dc75c7586ab6`
- **复核范围**: 仅复核 DS-01–08 与 MiMo F01–F04 的关闭情况，并检查修订是否引入新 material flaw。未启动子 agent、未扩散检索、未读 raw evidence、未修改任何文件。定点核验了三处对关闭结论有决定意义的已知生产符号片段（见下）。
- **代码事实定点核验**（均为关闭结论的直接依赖）:
  1. `dayu/fins/storage/_fs_identity.py:250,257` — identity read helper 在 directory/descriptor 不存在时抛 exact `FileNotFoundError`，证实 §6.3 的 absent 短路语义与真实代码一致。
  2. `_fs_company_meta_core.py:61`（`_get_company_meta_unguarded`）与 `_fs_source_document_core.py:800`（`_get_source_meta_unguarded`）— plan §6.3 点名的两个 unguarded reader 以同名真实存在，guard 内两次无守卫读取的组合同版本可直接实现。
  3. `dayu/fins/storage/_fs_repository_factory.py:29,51` — `build_fs_repository_set(create_directories: bool = True, ...)` 存在且已透传，证实 Q2 的 `rejected-with-reason` 裁决与 §6.4/§7"明确不修改"的代码前提为真。

## Assumptions Tested

1. 每个 finding 的修订是否落在其指出的位置（§6.x/§7/§8/§12），而不是用下游补偿或新抽象替代。
2. 修订是否只收敛规格、不引入 goal drift / scope creep / 新的第二套规则。
3. 修订后 plan 是否 code-generation-ready：签名、顺序、闭集、注入链是否全部确定性固定。
4. 修订是否与既有代码事实一致（以三处定点核验为准）。
5. 修复是否引入新的 material flaw（重新跑 architecture boundary / state machine / test gap lenses）。

## DS-01–08 逐项关闭裁决

### DS-01（workspace validator 模块归属矛盾）— **closed**

- **Direct plan evidence**: §6.1（line 157-185）现在明确三分：`ingestion_runtime.py` 只拥有 pure types/validator（`validate_fins_upload_filing_request`、`fins_upload_usage_failure`）；`service_runtime.py` 只拥有唯一 concrete assembly wrapper，且**改名为** `prevalidate_fins_upload_filing_request_for_workspace`（line 173-181），并明文禁止第二名字/兼容 alias（line 185）。§7 service_runtime.py 条目（line 527）与之完全一致。
- **核验**: 修订后全文已无旧名 `validate_fins_upload_filing_request_for_workspace`；fix doc self-check（line 86）陈述与 plan 实际文本一致。CLI 调用 wrapper 不 import `dayu.fins.storage`（wrapper 内部装配 concrete type，§6.1 line 183-184），S2 import boundary 断言（line 623）仍成立。**closed，无残余。**

### DS-02（SEC 侧装配链缺失）— **closed**

- **Direct plan evidence**: §7 新增 `dayu/fins/pipelines/sec_pipeline.py` 条目（line 541-544）：`SecPipeline.__init__(..., filing_upload_state_repository: FilingUploadStateRepositoryProtocol, ...)`、facade 改收 typed validated request、同一 repository identity 透传 workflow。`SecUploadWorkflowHost` 新增只读 `_filing_upload_state_repository` property（line 546）。装配源唯一：`DefaultFinsRuntime` 新增 `filing_upload_state_repository` 字段，`create` 用同一 `repository_set(create_directories=False)` 构造，`get_ingestion_runtime` 把同一实例注入 runtime、SEC、CN（line 528-529）。CN/HK 对称（line 551-553），且 §6.3（line 385-387）明确 CN/HK 不保留 `_safe_get_upload_document_meta` 作第二状态 owner。
- **验证点**: S3 断言 SEC 与 CN/HK facade 收到同一 protocol instance、HK 走真实 HK ticker 的 market route（line 642-644）。**closed，无残余。**

### DS-03（validated 传导链未 spec）— **closed**

- **Direct plan evidence**: 新增 §6.2.1（line 274-352）固定全链签名：CLI `_prevalidate_upload_filing_request` → `_open_direct_stream(..., upload_filing_request: ValidatedFinsUploadFilingRequest | None)` → `FinsDirectCommandService.upload_filing(request: ValidatedFinsUploadFilingRequest)` → `FinsIngestionRuntime.upload(request: FinsUploadRequest | ValidatedFinsUploadFilingRequest)` → `FinsUploadRunner.run_upload(request: ValidatedFinsUploadFilingRequest | FinsUploadMaterialRequest)` → SEC/CN facade `upload_filing(request: ValidatedFinsUploadFilingRequest)` / `upload_filing_stream(...)`，并明文"不得还原成散参或重建 request"（line 333-334）。
- **关键补充核验**: authoritative recheck 的语义比第一路建议更完整——preflight 只供 identity 定位（line 338），workflow 用同一 protocol 读 fresh snapshot、对 `preflight.request` 再调同一 `validate_fins_upload_filing_request`，只有 fresh `authoritative_request` 驱动 prepare/stage/commit，旧 snapshot/派生值必须丢弃（line 340-346）；non-CLI 消费者（upload/prepare_observed_upload/start_observed_upload/legacy start_upload）在业务启动前同步抛同一 typed error，且 `FinsUploadUsageError` 是 `ValueError` 子类，与 `FinsIngestionRuntime.upload` 现有 docstring 的 `Raises: ValueError` 契约兼容（第一路已核对的代码事实），不新增跨层类型（line 348-352）。
- **验证点**: S2 断言 object identity 保持（line 624-625）、raw non-CLI 入口零 mutation 抛 typed error（line 626-627）。**closed，无残余。**

### DS-04（resolve_upload_action/precondition 归属迁移未列）— **closed**

- **Direct plan evidence**: 新增 §6.5（line 403-428）把 `docling_upload_service.py` 固定为 action/overwrite/prepare 分支唯一 owner：`resolve_upload_action(requested_action, previous_meta)` 保留共享，新增同模块 `UploadOverwritePrecondition`（3 成员 typed disposition）与 `evaluate_upload_overwrite_precondition`；validator 与 SEC/CN/HK authoritative recheck 必须调用这两个同一 module symbols（line 424-426），`prepare_upload` 也调用同一 helper（line 426-427）。§7 对应条目（line 537-538）与之一致。
- **附带收益**: §6.5（line 430-439）同时固定 `prepare_upload` 的真实分支（cancellation→cancelled 无 batch；delete→`_PreparedDeleteMutation` 不求 files/fingerprint/转换；非 delete fingerprint 相同且 overwrite=False→terminal skipped 无 batch；其余→`_PreparedAssetMutation`，转换失败发生在 begin_batch 前），一并关闭了我第一路的 Open Question 1（fix doc Q1，line 48）。**closed，无残余。**

### DS-05（company stage / delete 失败注入缺失）— **closed**

- **Direct plan evidence**: S3 断言新增两条：company stage 写 staging 中途失败 → `rollback=1/commit=0`、published company/source before/after tree 与逐文件 SHA-256 完全相同、staging/journal 按既有 rollback/recovery contract 收口（line 652-653）；delete source stage 失败 → company tree/SHA 不变、source 完整恢复且所有文件 SHA 不变（line 654）。existing stale company 的注入点列表也补上 company stage（line 648）。**closed，无残余。**

### DS-06（UF-FIX09 断言落点未指定）— **closed**

- **Direct plan evidence**: S3（line 657-660）把断言落在 `DefaultFinsRuntime.get_ingestion_runtime` composition owner test（owner tests 列表 line 636 注明 `test_fins_ingestion_runtime.py` 的 DefaultFinsRuntime composition owner）：SEC upload、CN upload、CN download、HK download 持有的 `ProcessDoclingConverter` 均 `is` 同一实例，重复调用返回同一 runtime；cancellation token 沿 runtime→runner→facade→`prepare_upload`→converter 保持 object identity，`prepare_upload` 仍为 async/await；明文禁止 caller-local fake converter 证明共享装配事实。§12.1（line 782-783）同步更新。**closed，无残余。**

### DS-07（CLI catch 顺序未显式化）— **closed**

- **Direct plan evidence**: §6.1（line 240-253）给出唯一 renderer 路径与 exact stderr 格式，并明文"该 catch 必须紧随既有 usage catch，位于 `FinsDirectStreamProtocolError`、`KeyboardInterrupt` 和最终 generic `except Exception` 之前；generic branch 只映射 runtime/content/storage failure 为 exit `1`"；同时明确消费对象是 `FinsUploadUsageFailure`、不得与 runtime `FinsUploadFailureReason` 混用。§6.6（line 490-492）固定 workflow catch 顺序（cancelled → Docling typed → storage typed/OSError → generic）。S2（line 616-617）与 S4（line 675-676）有对应断言（含 observable marker 断言 catch 顺序）。**closed，无残余。**

### DS-08（fresh absent fast path 顺序未写死）— **closed**

- **Direct plan evidence**: §6.3（line 370-380）按唯一顺序写死：先规范 external ticker → 调用既有 `_ticker_dir_for_read(external_ticker)` 判定 published root → 只有 exact `FileNotFoundError` 可短路 `(None, None)` 且该分支**不得**调用 `_acquire_publication_guard`、不得创建 `.dayu`/`portfolio`/lock → root existing 才 acquire guard **一次** → guard 内依次调用两个 unguided reader → release 同一 guard；symlink/broken symlink/descriptor 缺失或错配/非目录/meta corruption 必须 fail closed，禁止 fallback 到 `Path.exists()` 或新建空 root。
- **代码事实核验**: 上述语义与定点核验 1、2 一致——`_identity_directory_for_read` 对 absent 抛 exact `FileNotFoundError`，`_get_company_meta_unguarded`/`_get_source_meta_unguarded` 以点名形式真实存在。
- **验证点**: S1 新增路径级断言：fresh absent 后 `.dayu`、`portfolio`、batch lock root/publication lock 全部不存在（line 584），symlink/corruption fail-closed（line 585-586）。**closed，无残余。**

## MiMo F01–F04 独立复核

### F01（guard bypass 机制）— **closed**（与 DS-08 同源，分别独立关闭：修订落在 §6.3/S1/§12.1，见 DS-08 裁决；路径级断言 line 584 补齐了"只断言 helper 未调用"的不足）

### F02（usage code 闭集未显式枚举）— **closed**

- **Direct plan evidence**: §6.1（line 187-213）删除"至少"措辞，冻结 **23-member 穷尽闭集**（逐成员点名），line 187 明文"穷尽闭集，不得在实现时添加 ad-hoc 成员"；line 219-238 给出 UF-003–006、015–019、021–024、026–038 的 exact scenario→code→message 全量映射表与判定优先级（ticker → year → period → files presence → path/type → 两个 suffix owner → state/company）。我逐行复核了映射表与 §10.1 frozen argv 的一致性：UF-015/016/021/022/023/024/026/027/028/030-038 的 code 与 priority 顺序均自洽（如 UF-019 无 files → `MISSING_FILES` 先于 company 判定，与 priority 表一致；UF-030-032 第一层、UF-033-038 第二层，与 §6.2 step 4 一致）。line 236-237 要求 owner tests 逐成员 exhaustive 覆盖并断言不存在 default/unknown 分支。**closed，无残余。**

### F03（lazy bootstrap 回归路径覆盖）— **closed**

- **Direct plan evidence**: S1 断言从一句泛化陈述扩为五类 exact 路径：direct download（fresh root 真实 repository/batch 首写 source、无 jobs root，line 592-593）、runtime/durable download（create_job 首写 jobs root + queued/terminal schema/recovery 断言不变，line 594-595）、direct preprocess（seed 后首写 processed tree、不依赖 job root 预存在，line 596-597）、legacy preprocess/upload job（fresh jobs root 上 create/save terminal record，line 598）、isolated job-store 首写（`create_job` 单独断言 lock 前 mkdir、missing read/save 不建 root，line 599）。**closed，无残余。**

### F04（stderr 模板未定义）— **closed**

- **Direct plan evidence**: §6.1（line 240-253）固定唯一 renderer 路径 `render_cli_error(f"dayu-cli upload_filing: {usage_failure.message}")`，明确 `render_cli_error` 追加唯一换行 → exact stderr `f"dayu-cli upload_filing: {usage_failure.message}\n"`、stdout 为空；并明确类型边界（usage failure ≠ runtime failure reason）。S2（line 615-617）有 exact 断言。**closed，无残余。**

## Open Question 裁决核验（Q1–Q4）

- Q1（prepare 分支）：已由 §6.5 line 430-439 确定化，与第一路 Open Question 1 对应。**resolved。**
- Q2（repository factory 参数）：fix doc 判 `rejected-with-reason`；本路定点核验 3 证实 `build_fs_repository_set` 已有并透传 `create_directories: bool = True`，§7"明确不修改"（line 567-568）成立。**resolved，代码事实为真。**
- Q3（CN/HK snapshot 等价）：§6.3 line 385-387 + S3 HK market-route 断言（line 643-644）关闭。**resolved。**
- Q4（non-CLI usage 投影）：§6.2.1 line 348-352 关闭，与 `upload` 既有 ValueError 契约兼容（第一路已核对）。**resolved。**

## 新增 material flaw 检查

对修订后 plan 重新应用 architecture boundary / state machine / test gap lenses，未发现中高严重度新问题；发现一处低严重度文本不一致：

### R-DS1-未修复-低-`fins_upload_usage_failure` 的 basename 参数 code 数量与映射表矛盾（"两个文件 code" vs 表中四个）

- **位置**: §6.1 line 215-217 vs line 219-238 映射表
- **问题类型**: 不可直接实施（轻微）/ 契约缺失
- **当前写法**: line 215-217 写"除**两个**文件 code 可接收已经去路径化的 basename 外，其余文案完全由 code 决定"；但同一节的映射表显示**四个** code 使用 `{basename}`：`FILE_NOT_FOUND`（UF-026）、`FILE_NOT_REGULAR`（UF-027）、`FILE_SUFFIX_NOT_ALLOWED`（UF-028/030-032）、`CONVERTER_SUFFIX_UNSUPPORTED`（UF-033-038）。签名 `fins_upload_usage_failure(code, *, file_name: str | None = None)` 本身不区分数量。
- **反例/失败场景**: 实现 agent 实现该唯一 message source 时，按句子约束只允许两个 code 接收 `file_name`（哪两个？），则表中断言四个 code 的 `{basename}` 文案无法通过该函数生成，导致要么在函数内开第二个例外分支、要么改表——两个方向都违背"唯一 source mapping"与"exhaustive 断言无 default 分支"（line 236-237）。
- **为什么有问题**: 这是本 WU 的核心契约之一（唯一 message source），同一 section 内的数量矛盾会让实现 agent 自行裁决；fix doc self-check（line 86-88）未捕获此不一致。
- **直接证据**: plan §6.1 line 215-217 与 line 230-233 的原文对照；映射表四行 `{basename}` 文案。
- **影响**: message source 实现歧义或表/函数二选一被破坏；owner test 的逐成员 exact message 断言（S2 line 612）会暴露但不自愈。
- **建议改法和验证点**: 把 line 216 的"两个文件 code"改为"四个文件相关 code（`FILE_NOT_FOUND`、`FILE_NOT_REGULAR`、`FILE_SUFFIX_NOT_ALLOWED`、`CONVERTER_SUFFIX_UNSUPPORTED`）"或直接声明"所有文件相关 code 可接收已去路径化的 basename"；验证点：S2 的 exact message 断言覆盖四个 code 的 `{basename}` 文案。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Residual Risks

1. **TOCTOU**：§12.1 line 773-774 维持裁决（fresh recheck 非 commit lock，batch/storage fail closed），且 §6.2.1 line 336 的"preflight 不是 commit authorization"语义已写进 workflow 契约。接受。
2. **eager bootstrap 回归**：S1 五类路径断言后残余风险大幅收敛；仅剩实现质量风险。接受。
3. **format drift / failure redaction / UF-FIX09 / snapshot 误用**：分别由 approved S2/S4/S3/S5 docs 覆盖（§12.1）。接受。
4. **R-DS1**：唯一仍 open 的低严重度文本不一致，建议在 implementation gate 前随手修订；不构成 blocker。
5. **`_get_source_meta_unguarded` 的精确参数形态**：plan §6.3 以 `(external_ticker, document_id, SourceKind.FILING)` 点名调用，函数真实存在（`_fs_source_document_core.py:800`）但本路未核对其完整签名；若参数名/顺序有差异，实现 agent 按既有签名适配即可，不改变 guard 内两次无守卫读取的契约。低置信提醒，非缺陷。

## Plan Re-Review Conclusion

**pass-with-risks**

DS-01–08 全部 closed，MiMo F01–F04 全部 closed，Q1–Q4 全部 resolved（Q2 的 rejected 裁决经定点代码核验为真）。修订是收敛性的：无 goal drift、无 scope creep、无新的第二套规则；§6.2.1/§6.3/§6.5 的新增内容直接映射到两路 review 的 findings 与 open questions，且三处决定关闭结论的代码事实（identity helper 的 FileNotFoundError 语义、两个 unguarded reader 的真实存在、factory 的 create_directories 透传）均已独立核验为真。plan 已 code-generation-ready。

唯一未关闭项为新增的低严重度文本不一致 R-DS1（"两个文件 code" vs 映射表四个），不构成 blocker，建议由 controller 在进入 implementation gate 前并入 plan 一次性修订。
