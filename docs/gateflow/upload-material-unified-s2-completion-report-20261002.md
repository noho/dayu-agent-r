RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-c4d3c80b

# S2 同一 implementation continuation 交付报告

**终态 partial / dependency blocked：完整 S2 未完成。** 独立 storage owner、C01 当前公司事实合同与 T01 夹具迁移已实现验证；新 US2-C02 的 D→publication actual final 传递合同缺项待 root 明确裁决。不是 S2 pass、完整双审候选或 WU 完成，remaining 仍属同一 implementation，不拆 slice/gate、不自行延期。

本轮 runtime 未提供实际模型事件，模型记 unknown；不从 canary 或路由补推。label `upload-material-unified-s2-completion-sol-20261002-01`。不赋 gate accepted，不推进 S3、review、commit 或外部状态。

## 冻结身份

唯一 workspace `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`，HEAD `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`，main `fac32ecbff9bfe792b63ee9667c8697826b631f4`。首核 `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/preflight.json`：9891 件零漂移；input manifest SHA `7e6f64e99ad45f87a1e4fd93a390302ebd046b983bf4ccbd913fd822b68ab5e5`，accepted plan SHA `c99c35adba919a8baf371b0142e0ab1abf256a951e89b2fc15e8a2d38988e8ea`。C01 initial-None 与已有公司观察基准裁决、T01 fixture 白名单已读；不重开历史假设。

## 即时登记 US2-C02：完整 material final 缺传递通道

状态：requiring explicit root contract decision；不是 C01 公司历史问题。owner：D commit 返回合同和 material publication executor 的直接交接。

冻结计划 §6.2 要求 `commit_material_upload_batch(batch) -> MaterialUploadPublishedState` 在同 guard 形成 actual final；§6.7 要求 `MaterialUploadPublicationOutcome` 仅含该实际 `published_state` 与 `UploadOperationResult`。但 §6.7 对 D `commit_prepared_upload_batch` 的 required 扩展只有 `material_state_repository` 参数，`UploadOperationResult` 新增字段只有 `source_kind` 与 `published_amended`。现存 `dayu/fins/pipelines/docling_upload_service.py` 的 commit 函数返回 `UploadOperationResult`，无完整 final 状态传递字段；§6.7 未给材料分支不同返回类型或显式 final 通道。

直接路径：storage commit 正常返回完整 final → D 消费该 final、投影 bool → executor 只能收到 result。提交后新 read 会释放原 writer 后取得其它版本，不能作为该次 actual final；共享可变 side-channel、回调或 facade 会违反冻结合同和唯一生命周期要求。不得靠任意 raw readback 补齐。

已向 root 请求最窄补足：允许 `UploadOperationResult.material_published_state: MaterialUploadPublishedState | None`，仅传 storage 正常返回的同一 final；filing/取消为 None，不增加生命周期。未获裁决前不实施此字段、不用替代路径冒完整 executor 完成；独立仓储 owner/严格 amended/fixture 验证继续。

## 工具失败与恢复（原票据保留）

- 首 full pyright-01 actual exit 1，11 errors；原件在本轮 `pyright-01/{command.json,stdout.txt,stderr.txt,actual-exit.json}`。包括 FiscalPeriod 真实导入 owner、不可变 JSON list 继承签名和公司私有能力类型边界。修正真实路径与严格签名，不 ignore/exclude，不安装依赖。
- 两次 rg 批次的最后一个不存在匹配使实际 exit 1；属于定位无命中，已有输出保留，未冒产品验证通过。恢复为实际 `_fs_company_meta_core.py` 的 strict parser 和 infra 的 `_read_published_company_identity` 真源。

## 末核与取证边界

首核与末核 branch/HEAD/main/plan/input SHA 完全相同。实际 HEAD commit 为 accepted S1；读取 AGENTS.md、Gateflow implementation-slice 约束、冻结计划全文、S1 接受记录、C01/T01 root 裁决及前次 partial 报告后执行。本轮只检查冻结 manifest 的产品与技术路径，未全扫 venv/private workspace。

末核 `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/audit-04-final/` 记录：9891 input；9873 protected 零漂移；本轮 input delta 22 件；相对 HEAD 完整候选 25 件。完整 diff 包含继承正确增量，不能把 delta 冒全部交付。allowed 35 production/29 tests/3 README/唯一新 report 保持；T01 额外单测试窄迁移在白名单。

root control、原 plan、C01/T01、旧报告/技术目录、S1 双流/失败/Raw只读保留。没有 commit/stage/push/PR/merge/approve、子 Agent、外发、branch/worktree/main 变动、依赖安装或类型抑制。未重跑旧公司历史探针；C01 的不可观察历史不再作为 blocker。

## 实际实现与 owner 边界

| owner / 文件 | 实际行为 |
| --- | --- |
| `storage/repository_protocols.py` | 新 required immutable original descriptor/publication identity/published state 与材料状态公开协议；deep immutable source meta；revision 仅 classification 真源；不 raw 重算 ID/role/fingerprint；财期复用 FISCAL_PERIODS owner。source 协议新增 required metadata-only 方法。 |
| 新 `_fs_material_upload_state_core.py` / `fs_material_upload_state_repository.py` | 单 guard strict company/exact material 读取；不存在公司目录时 MISSING 零创建；writer view、登记与复验；提交/cleanup/release 全正常才返 actual final；独立公司 intent 提交。不是兼容 facade。 |
| `_fs_storage_core.py` / `storage/__init__.py` | 现 core/public contract 装配，不造第二状态机。 |
| `_fs_storage_infra.py` | typed 条件与 final；swap 前 source/company/alias 同 guard 复验，swap 后实际 inspector 形成 COMPLETE final 再 COMMITTED；沿原 capability/恢复/锁序；COMMITTED 后 release 错误抛出且保 durable，不 rollback/retry/readback 改 skip。 |
| `company_meta_contract.py` | material-specific 公司 merge 仍由公司 owner：已有 observed snapshot 严含 updated_at；初始 None 按 C01 当前 canonical/name-equivalence/full aliases/resolver/无合并增量作 no-op，零 swap/time refresh；alias 唯一性原 owner 优先。filing 一般 merge 保持。 |
| `_fs_source_integrity.py` | 同 inspector 从已验证 descriptor 投影 identity；严格 amended、坏原件/manifest不猜 MISSING；不新 parser，不从时间/JSON猜 revision。 |
| `_fs_source_document_core.py` / `fs_source_document_repository.py` | metadata-only 需已登记条件、COMPLETE active，从实际 writer canonical meta仅改 amended/维护 updated_at，原 owner 生成 revision/manifest；其它业务字段、首次时间、资产、版/指纹不动。前次独立删除/strict健康重删正确增量保留。 |
| `document_models.py` / `source_manifest_contract.py` | manifest amended required，从 strict source reader 同源产生，不 request/default 生 durable。 |
| `cn_pipeline.py` / `sec_upload_workflow.py` | 合法 material producer 明确写已有 raw.amended bool；没有未来 executor 装配，不改 filing 生命周期。 |
| 新 state test | 真实 Fs 15 cases：MISSING零写、actual final/deep freeze、metadata-only保版/资产/字段、登记/guard、坏状态failclosed、C01 no-op/观察漂移、COMMITTED-release durable、alias优先。fixture 用 S1 builder/D fingerprint/version owner，不 raw 算 ID/role。 |
| docling/atomicity/manifest tests | 旧合法 material producer 明确 amended；测试跟随 owner，不产品默认/compat；保原独立删除断言。 |
| provider test（T01） | 仅五个失效材料 fixture/共享 helper 迁真实 blob、DoclingDocument JSON primary/role和显式 amended；保 namespace/provenance/citation/meta-less原业务断言。same-ID namespace 用例也生成真实 Docling JSON，原件仍原bytes，不只给旧 raw 加role。 |

新 publication module/executor尚不存在。没有把独立仓储通过冒完整 state/company/amended/取消/CLI 集成。

## 精确 caller 与剩余实施

实际 `rg --files dayu` + 全生产 Python AST 查出五处 `commit_prepared_upload_batch`，全部尚未迁 required 参数：SEC filing:250/material:529，CN filing:903/material:1179，filing_publication:859。前三 filing须显式 None，两 material须真实 repo；新 executor也应 required。证据 `environment-and-caller-audit.json` 含每处 keywords/缺参/新executor缺席。D source SHA `ad66b833c3cfe47af09210a73c98de92866fbada33491bf49cce416239751002` 本轮未改；直接合同缺项见 plan:195/201/381/404/409 与 D:110–127/1359/1404–1408。未删旧 stage_company helper实际调用，不以“四处”或 optional/default保旧mock冒迁移。

未实施依赖链：R state admission/required repo，U目标 typed拒绝/完整state格，D verified-skip/meta候选/八格与typedfinal，publication竞争/两阶段执行，5 caller/SEC/CN，job active-only/no-runner/progress双摘要，Service/direct/LLM read actualamended与真正双 CLI。它们仍是本 WU S2 必做，不裁为延期 residual。

## V7–V14 实际矩阵

| 验收 | 实际证据 | 当前边界 |
| --- | --- | --- |
| V7 | exact inspector坏状态不MISSING；MISSING读零目录写；C01 strict当前公司 | 部分；全action×state admission/首target再name/零started-job-handle尚缺。 |
| V8 | 真实registration/finalguard，源revision/公司snapshot/alias优先owner测试 | 部分；四mutation经新executor漂移与进程barrier尚缺。 |
| V9 | source/manifest strictbool，metadata-only保资产/业务字段/v1，producer显式bool | 部分；完整八格转换计数/版、terminal actualbool、delete defaultfalse投影true、失败取消null、LLM/job/schema尚缺。 |
| V10 | 继承首删/健康重删strictowner通过docling/atomicity/meta/manifest回归 | 独立删除部分通过；完整R/publication恢复矩阵不冒pass；不按mtime/inode，不要求首次两time字面同。 |
| V11 | C01 initialNone无增量no-op完整业务SHA不动；observed time/字段拒；COMMITTED后release错误保durable；alias优先 | 部分；两oldadmission新executor winner→loser/全role-amended-company损坏及IO/rollback/release集合缺。 |
| V12 | 未运行真实双CLI | 未完成，无顺序skip充数，六票据全缺。 |
| V13 | 原取消/filing/job回归，storage durable release-failure测试 | 部分；新no-runner/typed active-only/terminal progress双摘要/新executor latecancel尚缺。 |
| V14 | 28模块2134pass/3skip，source变化后469/620，最终provider+state124pass | 当前增量回归通过；remaining assembly未改，不冒完整S2 V14。 |

V12 六段票据逐项：①先wrap admission后import CLI/SEC/CN并验三个from-import binding/owned双CLI argv双流PID，②两ready同identity/companyNone/MISSING/revisionNone与公共Fs snapshot，③releaseA真实productionconverter/storage提交actualwait，④读winner健康exactstate/完整businessbytes，⑤releaseB旧handoff verifiedskip/actualwait，⑥winner→loser完整bytes零漂移、finally restore绑定且只terminate/wait自身Popen。**六段全部未执行/无票据**，原因新typed admission/executor未集成。没有 production testhook/fake仓储/结果；无共同oldadmission不可仅凭同步启动猜race。本轮owner单进程测试不是V12。

## 验证协议与最终结果

每轮 `source .venv/bin/activate`，实际 Python3.11.15、绝对 `.venv/bin/python`，dayu import来自唯一checkout，CLI同venv；环境原件保留。所有记录runner显式绝对cwd、stdinDEVNULL、独占输出/双流/actualwait/exit/COVERAGE_FILE。argv原样留存；个别argv为激活后的python/pyright，不假改绝对argv。pytest全部禁cacheprovider、独占basetemp/JUnit/coverage，不污染根.coverage。宽回归后只针对实际后改必要定向，不机械重复宽suite。

| run | actual exit | 结果/范围 |
| --- | --- | --- |
| provider-01 | 0 | 109pass，早期T01，非完整S2 |
| repair-regression-02 | 0 | 529pass，amended fixture迁owner后 |
| final-regression-01 | 0 | 2134pass/3skip，JUnit2137/0fail/0error，28实际模块 |
| final-owner-06 | 0 | 469pass，alias priority最后源码后 |
| final-owner-08 | 0 | 620pass，FISCAL_PERIODS和精确year类型owner修后 |
| final-state-fixture-09 | 0 | 15pass，fixture使用S1/D真源后 |
| final-provider-10 | 0 | 124pass，最终实际Docling JSON夹具+state |
| final-pyright-10 | 0 | full 0 errors/0 warnings/0 informations，当前全部source/test |
| final-script-pyright-03 | 0 | 独占脚本0errors |
| scoped-diff-check-03 | 0 | 最终tracked白名单diff无whitespace error；untracked实际diff另存 |

不累加重复用例。`final-regression-selection.json` 明列 `test_material_upload_publication.py` 未实施blocked，不冒pytest skip。已知JUnit三skip：两Windows真实cmd.exe测试；可选Docling测试要求 `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1`。宽回归有三edgartools deprecation warnings。已有真实文本Docling集成已运行，不替代V12；完整可选Docling未启用记未覆盖。

逐production>=80覆盖四个最后改protocol/integrity/infra/materialcore用final-owner-08，其它用宽回归；document_models末次单行docstring非docAST/行数不变，docstring-audit保证line mapping；fixture whitespace同AST/行数票据保留。最终state/provider只改tests，未漂移prod。无新增exclude/ignore/安装改依赖。

## 其余内部失败与恢复（不outer0掩盖）

| 失败 | 恢复与影响 |
| --- | --- |
| pyright-02 exit1/1error | 冻结list.sort签名修为typed完整override，后续full0；原stdoutstderrexit保。 |
| state-01 exit1/4fail3pass | 复制reader错FILING，改真实owner到MATERIAL；不mockCOMPLETE。 |
| state-02 exit1/1fail6pass | MappingProxy不可serialize；metadata writer消费已strict实际canonical JSON，不fallback；state03及后续通过。 |
| affected-01 exit1/63fail650pass1skip | 合法旧fixture缺显式amended，另失败fixture未到checkpoint有threadwarning；只迁fixture，529/2134/124后续通过，原失败警告保。 |
| scoped-diff-check-01 exit2 | 十个新增amended行whitespace；只清新增行，非docAST/行数同，-02/-03通过。 |
| 取证复合批次内部cat不存在final-test-selection.json | 外层0不冒内部通过；恢复读真实final-regression-selection.json，不影响test结论，tool错误保。 |
| rg本轮生成文件输出过量截断 | 仅本轮E含basetemp identity造成；不当完整证据，转读取确切JSON；最终hash清单不遍历basetemp/private。 |
| 首次report patch失败 | 同一路径delete/add导致工具拒绝，未写文件；改单Update成功，无产品影响，tool失败保留。 |
| git --no-index exit1 | 每个新增文件expected differences=1，独立argv/双流/exit保存，是实际diff而非产品pass被吞。 |

audit-01完整生成输出在audit-01-snapshot保留；top-level generated delivery.diff曾audit-02刷新，不作最终不可变票据。audit-03/04分别新目录独立diff/hashes，保旧审核目录。旧implementation/Raw零改。全部非零test/type/diff原票据保，不outer0冒成功。

## README与分类残余

先读职责：根README前次合法独立删除说明本轮不改；Fins README只补实际storage/strictamended/no-op，不宣称新pipeline完整；tests README描述实际owner/fixture验收。没有Service/UI/Host/Engine/runtime边界/装配变动，不触发dayu README。LLM prompt/schema尚未改，对应remaining S2不冒已完成。

- 新US2-C02：root裁决D→publication显式final通道；不是C01，不凭实现者补字段改冻结contract。
- 本WU已接受未完成：上述完整S2依赖链/V7–V14/8格/5caller/真实双CLI仍必做，同一implementation继续，不列延期风险。
- 已裁非目标：initialNone未观察历史不增加revision/provenance/时间猜测；observed公司严格漂移已实现。
- 当前未覆盖：V12全部、新executor/job/read全链、完整optionalDocling、Windows两skip。
- 后续阶段：S3 taxonomy/OS/deps/UP-RR-T01、完整CLIcampaign/registry、aggregate/WUcloseout/正式PRreview未实施未推进。

停止本轮交root核实缺项和独立增量；不自行review/accepted/commit/push。获C02裁决后须继续同一S2集中完成remaining，再交root双review，不把此partial作为S2pass。

## 交付与验证索引

E=`workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01`；以下用项目相对路径。最终 `E/audit-04-final/candidate-hashes.json` 为全部25（含report自身hash）、delivery-hashes为本轮22、protected-hashes为9873、delivery-audit为首末身份/JUnit/零漂移，delivery.diff含tracked及新增完整actualdiff，diff-records含新增actualargv/双流/exit。本报告不自嵌自身hash。

`E/validation-ticket-manifest.json` 汇总所有独占实际command/stdoutstderr/exit/JUnit/coverage路径/SHA；`E/technical-hashes.json` 只枚举本轮明确脚本/票据/审核输出，不扫描basetemp/private，不编旧已删hash。所有owned记录runner实际wait终态，无pending。

### 逐修改 production coverage

| production | covered/statements | coverage % | 同版 coverage 文件 |
| --- | --- | --- | --- |
| `dayu/fins/domain/company_meta_contract.py` | 116/122 | 95.08 | `final-regression-01.coverage.json` |
| `dayu/fins/domain/document_models.py` | 430/450 | 95.56 | `final-regression-01.coverage.json` |
| `dayu/fins/pipelines/cn_pipeline.py` | 438/463 | 94.60 | `final-regression-01.coverage.json` |
| `dayu/fins/pipelines/sec_upload_workflow.py` | 162/171 | 94.74 | `final-regression-01.coverage.json` |
| `dayu/fins/storage/__init__.py` | 16/16 | 100.00 | `final-regression-01.coverage.json` |
| `dayu/fins/storage/_fs_source_document_core.py` | 478/556 | 85.97 | `final-regression-01.coverage.json` |
| `dayu/fins/storage/_fs_source_integrity.py` | 554/630 | 87.94 | `final-owner-08.coverage.json` |
| `dayu/fins/storage/_fs_storage_core.py` | 10/10 | 100.00 | `final-regression-01.coverage.json` |
| `dayu/fins/storage/_fs_storage_infra.py` | 988/1159 | 85.25 | `final-owner-08.coverage.json` |
| `dayu/fins/storage/fs_source_document_repository.py` | 92/95 | 96.84 | `final-regression-01.coverage.json` |
| `dayu/fins/storage/repository_protocols.py` | 328/401 | 81.80 | `final-owner-08.coverage.json` |
| `dayu/fins/storage/source_manifest_contract.py` | 8/8 | 100.00 | `final-regression-01.coverage.json` |
| `dayu/fins/storage/source_meta_contract.py` | 25/25 | 100.00 | `final-regression-01.coverage.json` |
| `dayu/fins/storage/_fs_material_upload_state_core.py` | 69/73 | 94.52 | `final-owner-08.coverage.json` |
| `dayu/fins/storage/fs_material_upload_state_repository.py` | 23/23 | 100.00 | `final-regression-01.coverage.json` |

### 全部 changed files / delivery SHA256

含继承正确增量；本轮delta和完整candidate机器清单分开。

| path | SHA256 |
| --- | --- |
| `README.md` | `7a8b9ee639fcee9684e170cf9a5101a41b2d4cd884090de391e146168a55f6c0` |
| `dayu/fins/README.md` | `f35e59871957055cc2dea61cee523de50b1e1efc743fbd6c4ecc95182e84ef2a` |
| `dayu/fins/domain/company_meta_contract.py` | `8ce7c5683e4b30186d1a230ea6c08cff27a475dc7fa9f9adf666d1d6be78b81d` |
| `dayu/fins/domain/document_models.py` | `d04206ce9be11aac14b6245915742f2c6a5421176d8c9ad823dc0483d2687f4c` |
| `dayu/fins/pipelines/cn_pipeline.py` | `b28591538d5335ff4ccfd5987d74942764e5d30987950c5b7df010e2c902ddca` |
| `dayu/fins/pipelines/sec_upload_workflow.py` | `31d408b426fb699241b9b3c3cab73fff6e13f6ccba085a617feb5aa3c447b51f` |
| `dayu/fins/storage/__init__.py` | `92e7560b335dd4daf8808a2fe29141ed39c6a2f0fbdfa9336ffd88ed8393d944` |
| `dayu/fins/storage/_fs_source_document_core.py` | `4002cc67116cd773dc959e3eb27617289a0e69ed6b210a882480b71b0a0db4f3` |
| `dayu/fins/storage/_fs_source_integrity.py` | `89f7adee03e68fc434db8cbe061b8dcfb14d81c422d6079df1d04dcf8a3e67eb` |
| `dayu/fins/storage/_fs_storage_core.py` | `897588e86d7e206a9abf5677f27240e395c3d0a08269d614b9b62485e2e1497d` |
| `dayu/fins/storage/_fs_storage_infra.py` | `5acf5445ea60f98d33a04f11469cde121fdcc9b5b22fda1b09acec711c47ad37` |
| `dayu/fins/storage/fs_source_document_repository.py` | `3443fae747ad326b3f96a325d3c586364369d298684f11dd8d03756565227b51` |
| `dayu/fins/storage/repository_protocols.py` | `1d55f4c40b9b7bad1a2ab20e115b0f20f785fd2be5a13d0aaf2760a8901b86e3` |
| `dayu/fins/storage/source_manifest_contract.py` | `6aad93fc998b512b120fa69cf2f855facb9c353ad7adbb7343c7290fa6a58216` |
| `dayu/fins/storage/source_meta_contract.py` | `c4657260b8c30cf2e799eac84579bfa8c418679a7c2fc206cd505cefc6799855` |
| `tests/README.md` | `aabd1c91665d2d7086f47882cca2f6343e7106d637211cfa2df0bfdf0a6dedbb` |
| `tests/fins/test_docling_upload_service.py` | `55f6d051a77de1a1ea5c33a3717593a49938d4bd7d28f2ff5274ed7e47b581d0` |
| `tests/fins/test_fins_storage_atomicity.py` | `531d4abc228164c40f76db74c6c072278132bc9bfff29c81adea4713b26b0928` |
| `tests/fins/test_fins_storage_provider.py` | `3799f8b0269f5a177bf2fa6c2ebf6069130ecccb8463ededd73e27f964e0fe73` |
| `tests/fins/test_source_manifest_contract.py` | `8f9a243c86cca66023d31c00575eac97587a15998df5fe336e036f242364af57` |
| `tests/fins/test_source_meta_contract.py` | `c2022ac19541a41e449e6d797662e6e31119721bb4489e9634dd7cb290cff4e4` |
| `dayu/fins/storage/_fs_material_upload_state_core.py` | `2a55d3fbd0ef021baafead223bb3509d7a836191e39c7ef9f8db19c5b20fd9f6` |
| `dayu/fins/storage/fs_material_upload_state_repository.py` | `701b8e73e22153b595cc6c7736b7bed1197544320cd9538847517d459eeda2ec` |
| `docs/gateflow/upload-material-unified-s2-completion-report-20261002.md` | 最终 `audit-04-final/candidate-hashes.json`（避免自引用） |
| `tests/fins/test_material_upload_state_repository.py` | `54360147789688735654d237fc4ef9d5cec2181fb72d8d6746fe5b723d3b4076` |

### 实际 runner 终态清单

各 `E/<run>/command.json` 存原argv/绝对cwd/COVERAGE_FILE；同目录stdout/stderr/actual-exit独占，hash存ticket manifest。run编号是独占文件标签，不新gate或slice。

| run | owned PID | actual exit |
| --- | --- | --- |
| `affected-01` | 28127 | 1 |
| `audit-script-pyright-01` | 28755 | 0 |
| `delivery-audit-01` | 28770 | 0 |
| `delivery-audit-02` | 29114 | 0 |
| `delivery-audit-03` | 30295 | 0 |
| `final-environment-01` | 29365 | 0 |
| `final-owner-06` | 28656 | 0 |
| `final-owner-08` | 29705 | 0 |
| `final-provider-10` | 30122 | 0 |
| `final-pyright-05` | 28353 | 0 |
| `final-pyright-06` | 28658 | 0 |
| `final-pyright-07` | 29111 | 0 |
| `final-pyright-08` | 29707 | 0 |
| `final-pyright-09` | 29881 | 0 |
| `final-pyright-10` | 30231 | 0 |
| `final-regression-01` | 28351 | 0 |
| `final-script-pyright-02` | 29398 | 0 |
| `final-script-pyright-03` | 30275 | 0 |
| `final-state-fixture-09` | 29879 | 0 |
| `provider-01` | 28047 | 0 |
| `pyright-01` | 27887 | 1 |
| `pyright-02` | 28008 | 1 |
| `pyright-03` | 28096 | 0 |
| `pyright-04` | 28209 | 0 |
| `repair-regression-02` | 28207 | 0 |
| `scoped-diff-check-01` | 29372 | 2 |
| `scoped-diff-check-02` | 29396 | 0 |
| `scoped-diff-check-03` | 31105 | 0 |
| `state-01` | 28071 | 1 |
| `state-02` | 28094 | 1 |
| `state-03` | 28117 | 0 |
| `state-04` | 28271 | 0 |

最终独占审核runner为 `delivery-audit-04`（其实际argv/streams/exit在ticket manifest，未加入上述先生成表，避免report→自身audit回环）。

### 原路径/SHA证据（关键验证）

| path | SHA256 |
| --- | --- |
| `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/preflight.json` | `9a063d5c9d6100037c6f2578feddaa9cf2be517459bc50f83b3471a0f01b629e` |
| `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/environment-and-caller-audit.json` | `655b52e16490fb7518658ee679a01376e82702ef8b7f57ffc2278986e017c1e7` |
| `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/final-regression-selection.json` | `3f66839a0304147da4372cc68912fecc84b4140780bca25543c7a0af730c43c5` |
| `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/final-regression-01.junit.xml` | `81307a3f1d6db4c735ac2617cd568df0b823c43998959fd08fd3067bcbf7c7cd` |
| `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/final-regression-01.coverage.json` | `485eb52e064f042df526622170e102b1ceccd486c8219ce1863338beeacfbaa9` |
| `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/final-owner-08.junit.xml` | `37323b48fa7d5d4ec39107c3a6d73770ac2bb6a666972bab9d3501e9eeb84980` |
| `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/final-owner-08.coverage.json` | `764c043e42406446739c779544359077eaa015acb4ad7df1dd8669137717e845` |
| `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/final-provider-10.junit.xml` | `79139c656972e7d3b3fe42923b8122a66db6dfbb436a1b9887142c6ec2e085db` |
| `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/final-pyright-10/command.json` | `7804499011482680af00f5e40906b32066445b5298230b5ff4f7838ac6c3e998` |
| `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/final-pyright-10/stdout.txt` | `46a6c7834c9080ada23a415afd925abecc37d531f5c6e3d14ad0a7ff579096cb` |
| `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/final-pyright-10/stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/final-pyright-10/actual-exit.json` | `9ede1f8617ecfa68528efddcfe32d607babc356702c3f3461cb8b7b44a6ee47e` |
| `workspace/tmp/upload-material-unified-s2-completion-sol-20261002-01/scoped-diff-check-03/actual-exit.json` | `09b9387211da03f9de8852b562bb5cb0c2b872a6da3ee70d535d8d04b5dd408c` |
