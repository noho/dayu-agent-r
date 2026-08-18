# UF-FIX01 validation-atomic-boundary — Plan Review（AgentDS 第二路独立裁决）

## Review Metadata

- **Reviewed target**: `docs/gateflow/uf-fix01-validation-atomic-boundary-plan-20260813.md`
- **Reviewer**: AgentDS（Gateflow fallback 第二次派发，独立第二路 review）
- **Review date**: 2026-08-13 09:47:50
- **Plan baseline HEAD**: `b3cb1f1b16f4d552eb762de3be59dc75c7586ab6`
- **派发约束**: 不得以 MiMo 结论替代；只允许读取冻结 plan、AGENTS.md、MiMo artifact、指定生产符号文件相关片段、plan 第 5 节冻结 evidence 摘要。已遵守；未启动子 agent、未做扩散检索、未修改任何代码/plan。
- **读取局限（独立裁决的诚实边界）**: 未读取 `dayu/fins/pipelines/sec_pipeline.py`、`_fs_repository_factory.py`、`docling_upload_service.py` 中 `prepare_upload`/`resolve_upload_action` 完整实现、`cn_pipeline.py` 完整实现、`_fs_company_meta_core.py`/`_fs_source_document_core.py`。依赖这些文件的结论均标注置信度，并落入 Open Questions。

## Assumptions Tested

1. **动机成立性**：当前 CLI 在 factory 创建后才解析 ticker/files，`DefaultFinsRuntime.create`/job store 构造即建目录 —— 已由 `dayu/cli/commands/fins.py:225-226`（factory 先于 `_upload_filing_stream`）、`ingestion_runtime.py:1834`（`__post_init__` 内 `mkdir`）、`_fs_storage_infra.py:452-457`（`create_directories` 构造即建目录）直接证实。动机成立。
2. **零 mutation 前校验可行性**：storage 已具备 `create_directories=False` 惰性语义（`_fs_storage_infra.py:419-445`、`_should_access_batch_state` line 1370-1372），`begin_batch` 首步 `_ensure_batch_storage_dirs()` 承担真实首写目录创建 —— 惰性 bootstrap 方向可行。
3. **fresh absent fast path 不创建 lock**：`_acquire_publication_guard` → `_acquire_lock_token` → file lock acquire 会真实创建 `_batch_lock_root` 下锁文件；fast path 必须先做 existence 判定，plan 未显式写实现顺序（详见 DS-08 / MiMo F01 裁决）。
4. **单一 BatchToken 可编码性**：`CompanyMetaRepositoryProtocol.upsert_company_meta(meta, *, batch)`（repository_protocols.py:335）与 source 写入共享同一 `BatchToken` 契约已存在，plan §5.3 陈述与代码一致。
5. **skip/delete/cancel/commit ownership 线性化**：`begin_batch`/`commit_batch`/`rollback_batch` 的 capability 消费语义（repository_protocols.py:246-282）与 `commit_batch` fail-closed 恢复语义（_fs_storage_infra.py:582-690）支持 plan 6.5 状态机。
6. **typed failure 无字符串匹配**：当前 `run_upload_filing_stream` 失败路径 `message=str(exc)`、`payload={"error": str(exc), ...}`（sec_upload_workflow.py:282-307）为真实现状，plan 6.6 修复点有直接证据。
7. **CLI exit 映射**：`run_fins_direct_command` 现有 generic `except Exception` 兜底 exit 1（fins.py:203-205）；新增 `FinsUploadUsageError`（ValueError 子类）必须显式置于其前，否则 UF-015–024 会继续投影为 exit 1 —— plan §7 已写"精确映射 exit 2"，但顺序约束未显式声明（见 DS-07 残余）。
8. **action/company-name 不越界**：6.2 step 7-9 的规则均为既有 workflow/DoclingUploadService 语义的前移，非新规则；UF-018/019 修复在 UF-FIX01 的 frozen evidence 范围内。不构成 UF-FIX02 越界。

## Findings

### DS-01-未修复-中-`validate_fins_upload_filing_request_for_workspace` 模块归属在 §6.1 与 §7 之间矛盾

- **位置**: §6.1 Fins typed usage contract / §7 Exact production files and symbols（service_runtime.py 条目）
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: §6.1 写"在 `dayu/fins/ingestion_runtime.py` 新增以下 closed contract（名称在实现中固定，不另设 alias）……新增 owner functions：`validate_fins_upload_filing_request(request, *, published_state)`、`validate_fins_upload_filing_request_for_workspace(request, *, workspace_root)`"；§7 的 `service_runtime.py` 修改条目又把 `validate_fins_upload_filing_request_for_workspace` 列为该文件的修改 symbol。同一函数名出现在两个不同模块的归属描述里，plan 未给出唯一 owner。
- **反例/失败场景**: 实现 agent 将其定义在 ingestion_runtime（按 §6.1 字面），但它需要装配 `FsFilingUploadStateRepository`——装配职责按现有代码属于 service_runtime（`DefaultFinsRuntime.create` 是唯一装配仓储的 assembly root，service_runtime.py:351-380）；或定义在 service_runtime（按 §7 字面），则 §6.1 的"在 ingestion_runtime.py 新增"语句失效。两条路径都让 plan 文本被违反一半。
- **为什么有问题**: AGENTS.md 语义所有权要求每个语义唯一清晰 owner；同一个 public function 的双重归属正是 plan 本 gate 要消灭的缺陷模式（"多个消费者复用同一 source of truth"）。且 S2 断言"CLI 不 import `dayu.fins.storage`"——若该函数定义在 ingestion_runtime 而装配 FS repository 需要 import storage，则该断言直接约束了定义位置，plan 必须显式收敛。
- **直接证据**: §6.1 原文与 §7 service_runtime.py 条目原文；service_runtime.py:351-380（`build_fs_repository_set` + 各 `Fs*Repository` 构造集中在该 assembly root）；CLI 当前 import 面（fins.py:49-75 未 import storage）。
- **影响**: 实施 Agent 放置错误导致 owner 漂移；pyright/import boundary 测试（`tests/cli/test_import_boundary.py`）可能被迫调整；review 无法验收唯一性。
- **建议改法和验证点**: 在 §6.1 与 §7 中固定唯一归属：建议定义在 `dayu/fins/ingestion_runtime.py`（typed contract owner），其内部以 `FilingUploadStateRepositoryProtocol` 工厂参数接收 state repository（不 import storage 具体实现）；`service_runtime.py` 只负责调用时传入 `FsFilingUploadStateRepository(create_directories=False)`，§7 的 service_runtime 条目相应改为"调用/接线"而非"该 symbol"。验证点：S2 的 `test_import_boundary` 断言 CLI 不 import `dayu.fins.storage`，且该函数定义处 pyright 无 storage 具体类型泄漏。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### DS-02-未修复-中-SEC 侧 state repository 装配路径缺失：§7 精确文件清单未包含 sec_pipeline.py，SEC host recheck 注入无法落地

- **位置**: §6.3 / §6.5 状态机 / §7 Exact production files and symbols
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: §6.3 要求"workflow 在 prepare 前用同一协议重读"；§6.5 状态机第一步"validate/re-read published state (no mutation)"同时适用于 SEC 与 CN/HK。§7 为 CN 侧写了"`CnPipeline.__init__` 注入 state repository"，但 SEC 侧只有"`sec_upload_workflow.py`: `run_upload_filing_stream` 单 publication unit + typed failure"；`dayu/fins/pipelines/sec_pipeline.py` 完全不在修改清单。
- **反例/失败场景**: SEC workflow 是模块级函数，通过 `SecUploadWorkflowHost` 协议从 facade 拿仓储（sec_upload_workflow.py:45-92，当前只有 `_safe_get_document_meta`）。要实现"workflow 用同一 state protocol 重读"，要么扩展 `SecUploadWorkflowHost` 协议（则实现该协议的 `SecPipeline` 类必须修改，而它在 `sec_pipeline.py`——超出 §7 清单），要么在 workflow 内自行构造 repository（违反分层：workflow 不是 assembly root）。实现 agent 无论走哪条路都超出或违反 plan 的精确文件授权。
- **为什么有问题**: §7 的"Exact production files and symbols"是 implementation agent 的边界授权清单；CN 侧注入了 state repository 而 SEC 侧对称装配缺失，意味着 plan 未覆盖 SEC 路径的 owner 变更。service_runtime.py:514-524 显示 `SecPipeline` 构造是 SEC 侧唯一 assembly 点，任何 state repository 注入都必须经过它。
- **直接证据**: §7 sec_upload_workflow.py 条目与 cn_pipeline.py 条目的不对称；service_runtime.py:514-524（`SecPipeline(workspace_root=..., ...)` 构造）；sec_upload_workflow.py:45-92（`SecUploadWorkflowHost` 协议无 state repository property，只有 `_safe_get_document_meta`）。
- **影响**: SEC 路径的 recheck 无法落地或产生越界修改；"同一协议重读"在 SEC 与 CN 之间分裂成两套装配方式，违反单一真源。
- **建议改法和验证点**: §7 增加 `dayu/fins/pipelines/sec_pipeline.py` 条目（`SecPipeline` 注入同一 `FilingUploadStateRepositoryProtocol` 并透传给 host/workflow），或显式声明 SEC host 协议扩展点与注入链（service_runtime → SecPipeline → workflow）。验证点：SEC 与 CN 的 workflow recheck 调用同一个 validator 函数与同一个 state repository 协议实现，owner test 各断言注入身份一致。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### DS-03-未修复-中-validated 契约在 runtime→runner→workflow 传导链未 spec：`ValidatedFinsUploadFilingRequest` 如何到达 workflow 的 recheck 点没有固定签名契约

- **位置**: §6.1 / §6.5 / §7（service_runtime.py、ingestion_runtime.py 条目）
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: §6.1 定义 `ValidatedFinsUploadFilingRequest`（含 `resolved_action`、`published_state`、`company_meta_decision`）；§7 修改 `ProductionFinsUploadRunner.run_upload / _run_filing_upload` 与 `FinsIngestionRuntime.create / upload`，但均未给出签名变化。§6.5 状态机只描述 workflow 内步骤，未说明 runner/workflow 接收的是 validated 对象还是原始 request 散参。
- **反例/失败场景**: 当前 `run_upload` 接收 `FinsUploadRequest`（service_runtime.py:61-105），`_run_filing_upload` 把字段散参传给 `sec_pipeline.upload_filing`（facade），workflow 内部自己 `resolve_upload_action(action, previous_meta)`（sec_upload_workflow.py:182）。若实现 agent 不改签名，则 validated 语义在 runtime 层被丢弃，workflow 要么重新解析（第二套规则），要么 runtime 内重复调用 `resolve_upload_action`（规则复制）；若改签名为接收 `ValidatedFinsUploadFilingRequest`，则 `FinsIngestionRuntime.upload`（同时服务 CLI direct stream 与 Host observed upload 的公共入口）的 recheck 语义、`_normalize_upload_request` 的现有启动边界校验与新 validator 的调用关系全部未定义。
- **为什么有问题**: 这正是本 WU 的核心交付物（"同一 Fins validator，不在 CLI/pipeline 复制规则"，§2.3）——但 plan 只定义了 validator 的输入输出类型，没有定义"已校验语义"在调用链上的传导契约。无签名契约 = 实现 agent 自行设计 = 最可能产生第二套规则或 god bag 传递的地方。
- **直接证据**: service_runtime.py:61-105（run_upload 接收 FinsUploadRequest）、132-171（_run_filing_upload 散参转 facade）；sec_upload_workflow.py:182（workflow 内自行 `resolve_upload_action`）；plan §6.1 `ValidatedFinsUploadFilingRequest` 字段与 §7 修改条目均无签名描述。
- **影响**: owner 重复、规则漂移；runtime 公共入口（Host observed upload）与 CLI direct 路径的校验一致性无法保证；review 不可验收。
- **建议改法和验证点**: 在 §6.5 或 §7 固定传导契约：`ProductionFinsUploadRunner.run_upload` 与 SEC/CN `upload_filing` facade 接收 typed validated handoff（或显式声明保持 FinsUploadRequest 且 workflow 以同一 `validate_fins_upload_filing_request(request, *, published_state)` 做 authoritative recheck 并丢弃 CLI 侧 validated 的派生字段，二选一必须唯一）；明确 `FinsIngestionRuntime.upload` 对 Host observed 路径的 recheck 行为（同一函数、同一 state 协议）。验证点：owner test 断言 SEC 与 CN workflow 内 recheck 调用的 validator 函数 identity 与 CLI 预校验相同。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### DS-04-未修复-中低-§7 修改清单未包含 `resolve_upload_action` 与 overwrite precondition 的 ownership 迁移条目，而 §6.2 step 7-8 依赖其"原样前移"

- **位置**: §6.2 step 7-8 / §7 docling_upload_service.py 条目
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: §6.2 step 7 要求"auto 依 source absent/present 解析为 create/update；显式 create/update/delete 保持原动作"；step 8 要求"把当前 `DoclingUploadService` 已有 precondition 原样前移：create-existing 且不允许当前 overwrite 规则、update-missing 且 `overwrite=False` 均为 typed usage"。但 §7 对 docling_upload_service.py 的修改条目只列"`_validate_source_files` 提升为 Fins validator 可复用的 public pure predicate、`prepare_upload(..., previous_meta=...)` 不再自行读取 state、`commit_prepared_upload_batch` 生命周期不改"——`resolve_upload_action` 与 step 8 引用的 precondition 判定函数的归属迁移（提升为 validator 复用、还是 validator 调用既有 pure helper）未列出。
- **反例/失败场景**: 实现 agent 在 validator 内重新实现 auto→create/update 判定与 overwrite precondition（因为清单未授权改 `resolve_upload_action`），而 workflow 继续调用原函数——两套规则共存，auto 场景在 validator 通过后在 workflow recheck 中可能得到不同 resolved_action（如并发下 state 变化）；或实现 agent 修改 `resolve_upload_action` 但该改动超出 §7 精确清单，gate closeout 时被判越界。
- **为什么有问题**: plan §2.3 承诺"state-aware auto/create/update 使用同一 Fins validator 与同一 storage snapshot，不在 CLI/pipeline 复制规则"——不迁移 `resolve_upload_action` 的 ownership 就不可能兑现；且 §7 是精确文件授权，"原样前移"依赖的符号不在清单内就是契约缺失。
- **直接证据**: sec_upload_workflow.py:18-27（从 docling_upload_service import `resolve_upload_action`）与 182（workflow 调用它）；plan §7 docling_upload_service.py 条目全文（无 resolve_upload_action）；plan §6.2 step 7-8 原文。
- **影响**: 第二套规则或越界修改；S2 断言"auto absent/create、auto present/update……复用当前 overwrite precondition"无法验证单一真源。
- **建议改法和验证点**: §7 显式增加条目：`resolve_upload_action` 及 step 8 引用的 overwrite precondition 判定提升/复用的精确归属（validator 与 workflow 共用同一 pure helper 的调用点）；验证点：owner test 断言 validator 与 workflow 调用同一函数对象（或同一 helper 模块符号）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中低

### DS-05-未修复-低-S3 原子性断言未覆盖 company stage 失败注入与 delete 失败注入的 rollback 恢复

- **位置**: §8 S3 Exact assertions / §6.5 状态机
- **问题类型**: 测试缺口
- **当前写法**: S3 断言"在 source stage、final checkpoint、commit 注入失败时 before/after company/source tree 和每个 file SHA 全相同""precommit cancel/stage error：rollback=1/commit=0"。但 6.5 状态机中"stage company decision on same BatchToken"是独立的可失败步骤（`stage_upload_company_meta_decision` 写 staging 时 OSError），"prepared delete: begin one batch, source delete only"也是独立路径——两者的失败注入断言均未列。
- **反例/失败场景**: company stage 在 staging 内半写后失败，实现若遗漏 rollback（当前 SEC 代码 company batch 是独立 commit 的，改造后顺序变化容易漏）→ orphaned staging/journal；delete 的 source 删除在 batch 内失败后 rollback 未恢复 source → 用户可见 source 丢失。测试若不覆盖，这两个回归将无法被 UF-PF01/I 系列之外的 owner test 捕获。
- **为什么有问题**: 本 WU 的核心 success criteria 是"任何 precommit failure/cancel 保持 company/source 的旧 published state 同时不变"（§2.3）——company stage 失败与 delete 失败正是该承诺的两条真实路径，缺断言即承诺未验证。
- **直接证据**: §8 S3 断言原文（只列 source stage/final checkpoint/commit 三个注入点）；§6.5 "stage company decision on same BatchToken (create/update only)"与"prepared delete: begin one batch, source delete only"。
- **影响**: 单 batch 改造的 rollback 回归在 company stage 与 delete 路径不可检测；后续 deepreview 无法验收原子性承诺。
- **建议改法和验证点**: S3 注入点列表增加 company stage 注入（断言 rollback=1/commit=0、before/after tree+SHA 全同）；增加 delete 路径失败注入（断言 company 不变、source 恢复、rollback=1/commit=0）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### DS-06-未修复-低-UF-FIX09 共享 converter identity 断言的落点测试文件未指定

- **位置**: §12.1 已裁决风险（UF-FIX09）/ §8 S3/S4 owner tests 列表
- **问题类型**: 测试缺口
- **当前写法**: §12.1 要求"S3/S4 tests 必须断言同一个 shared converter identity、cancellation token identity 与 async prepare 路径仍在"。但共享实例的事实存在于 `DefaultFinsRuntime.get_ingestion_runtime`（service_runtime.py:480 `docling_converter = ProcessDoclingConverter()`，随后传给 sec/cn 两套 pipeline）——S3/S4 的 owner tests（pipeline 单元测试）注入的是测试自建 converter，无法断言该共享事实。
- **反例/失败场景**: 实现 agent 在 §7 要求的 `service_runtime.py` 改动（DefaultFinsRuntime 字段/create/get_ingestion_runtime）中不小心为 SEC/CN 各构造一个 converter 或把构造移入各自 pipeline，UF-FIX09 被破坏——而 plan 指定的 S3/S4 owner tests 在 pipeline 层，结构上检测不到；实现 agent 要么被迫在 pipeline 测试里用 fake 断言（违反"测试必须断言 owner 级 contract 行为"，AGENTS.md），要么该断言根本无人写。
- **为什么有问题**: UF-FIX09 是 gate 明确要求保持的既有共享资产，其断言必须落在共享事实的 owner 层（`get_ingestion_runtime` 装配层）才能证明；plan 只写"必须断言"未写"在哪个测试文件、以什么方式断言"，等于把测试设计推给实现 agent。
- **直接证据**: service_runtime.py:480-534（单一 `ProcessDoclingConverter()` 实例传入 sec_pipeline 与 cn_pipeline 构造）；§8 S3/S4 owner tests 文件列表（均为 pipeline/service 单元测试，无 get_ingestion_runtime 装配层断言项）。
- **影响**: UF-FIX09 回归不可检测；或出现 fake 固化偶然行为的测试（违反 AGENTS.md 测试约束）。
- **建议改法和验证点**: 在 §8 指定 UF-FIX09 断言落在 `tests/fins/test_fins_ingestion_runtime.py` 或 `tests/service/test_fins_direct.py` 的装配层 owner test：构造一次 `DefaultFinsRuntime`，断言 `get_ingestion_runtime` 中 SEC 与 CN pipeline 持有的 converter `is` 同一实例、重复调用 `get_ingestion_runtime` 返回同一 runtime。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### DS-07-未修复-低-CLI 异常处理顺序约束未显式声明：`FinsUploadUsageError` 必须在 generic `except Exception` 之前映射 exit 2

- **位置**: §7 dayu/cli/commands/fins.py 条目 / §2.3 Success criteria
- **问题类型**: 不可直接实施（轻微）
- **当前写法**: §7 写"`run_fins_direct_command` 对 `FinsUploadUsageError` 精确映射 exit `2`"，但未声明其相对现有 `except Exception` 兜底（fins.py:203-205，映射 exit 1）的放置顺序；而 `FinsUploadUsageError` 是 `ValueError` 子类（§6.1），现有 CLI 已有 `CliFinsUsageError`、`FinsDownloadUsageError` 等按序捕获的先例（fins.py:186-205）。
- **反例/失败场景**: 实现 agent 把新 except 子句加在 generic 兜底之后（或依赖依赖注入顺序失误）→ 所有 usage 失败继续被投影为 exit 1，UF-015–024 的修复全部失效——而这正是本 WU 要修的核心症状之一（§2.2 证据 UF-015–016、021–024）。
- **为什么有问题**: 已有先例顺序可循（低概率出错），但这是本 WU 验收矩阵（§10.1 全部 exit 2）的直接开关，一行顺序决定成败，plan 应显式化而非依赖实现 agent 常识。
- **直接证据**: fins.py:186-205（现有 except 链及 generic 兜底）；plan §2.2（UF-015–016、021–024 把 usage 投影为 exit 1 的证据陈述）；§7 条目原文。
- **影响**: 核心验收矩阵失败；若实现 agent 未注意，返工成本低但 review 会漏。
- **建议改法和验证点**: §7 明确：`FinsUploadUsageError` 捕获子句紧随既有 usage 类捕获之后、位于 `FinsDirectStreamProtocolError` 之前，禁止落入 generic 兜底。验证点：S2 每个 CLI case 断言 exit 2 已覆盖（该断言本身能捕获此错误，属兜底性防御说明）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### DS-08-未修复-中-fresh absent fast path 的 bypass 实现顺序未在 plan 显式固定（对 MiMo F01 的独立复证与补充）

- **位置**: §6.3 / §6.2 step 6 / §12.1
- **问题类型**: 不可直接实施 / 并发恢复风险
- **当前写法**: §6.3 要求"若 canonical published ticker root 明确不存在，storage owner 内部直接返回 `(None, None)`，不创建 `.dayu`、`portfolio`、lock"，同时要求"FS 实现在同一个 ticker publication guard 内调用既有 unguarded company/source readers"。plan 未写明实现顺序：必须先做 `_target_ticker_dir(ticker)` 的 existence 检查、再决定是否进入 publication guard。
- **反例/失败场景**: 代码事实：`_acquire_publication_guard`（_fs_storage_infra.py:1515-1529）→ `_acquire_lock_token` → file lock acquire 需要 `_batch_lock_root` 已存在（锁目录由 `_ensure_batch_storage_dirs` 创建，line 1374-1393），且 acquire 本身即创建 `{key}.publication.lock` 文件。若实现 agent 复用现有"先 acquire guard 再读"的模式（`read_source_snapshot` 的内部稳定读取即此形态），fresh absent ticker 也会先创建 `.dayu/locks/` 与锁文件——直接违反 UF-PF01 "无 `.dayu`、portfolio、lock" 断言。
- **为什么有问题**: MiMo F01 已指出该风险；本裁决独立复证并补充代码级证据：guard 是文件锁、锁目录在 lazy 模式下直到 begin_batch 才存在，因此"fresh absent 不创建 lock"的实现只有一条可行路径——`_target_ticker_dir(ticker).exists()` 为 False 时短路返回 `(None, None)`，只有存在时才 acquire guard 包裹两次 unguarded 读取。这条顺序是硬约束，不是实现风格选择。plan §12.1 已裁决风险、S1 已断言"lock acquire helper 未调用"，但实现策略未写死，留下失败空间。
- **直接证据**: _fs_storage_infra.py:1374-1393（锁目录创建归属 begin_batch 路径）、1515-1529（guard acquire 即文件锁 acquire）、479-516（begin_batch 先 `_ensure_batch_storage_dirs`）；`_ticker_dir_for_read`（2579-2598）与 `_company_meta_path_for_read`（2743-2758）为无 guard 的路径构造+descriptor 校验——证明"guard 内调用 unguarded readers"的组合同版本可行；plan §6.3/§12.1 原文。
- **影响**: 若实现顺序颠倒，UF-PF01 fresh workspace 断言失败；且该失败只在真实 CLI focused-real 验证（§10）才暴露，切片内 owner test 若用已存在 lock 目录的 fixture 会漏检。
- **建议改法和验证点**: §6.3 显式固定顺序：先 `_target_ticker_dir(ticker)` existence 判定（含 symlink 判定的既有 helper 语义），不存在→直接 `(None, None)`；存在→acquire guard once→两次 unguarded read→release。验证点：S1 断言除"lock acquire helper 未调用"外，增加"fresh absent 调用后 `.dayu`/`portfolio`/lock 目录均不存在"（路径级断言，而非只断言 helper 未调用）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## 对 MiMo F01–F04 的独立裁决

### F01（publication guard bypass 机制未显式描述）——**接受，裁决一致（中）**

独立复证成立，并已在 DS-08 补充直接代码证据（锁目录创建归属、guard acquire 即文件锁 acquire）。裁决与 MiMo 相同的 severity 中：plan §12.1 已裁决风险、S1 已有关键断言，但实现顺序未写死。required fix 同 DS-08 建议。

### F02（FinsUploadUsageCode 闭集未显式枚举）——**接受但降权为低，与 MiMo 部分分歧**

分歧点：MiMo 认为 implementation agent 需自行补全 code 映射可能导致不一致。本裁决认为 §10.1 已冻结 21 个 UF scenario 的 exact argv 矩阵，§6.1 的 code 语义描述（"ticker/csv-invalid、missing/invalid year……"）加上 S2 断言"逐项返回 exact code"，足以确定性推导枚举成员——信息量足够。但同意一个残余缺陷：§6.1 措辞"闭集**至少**覆盖"与 closed contract 自相矛盾（closed 意味着穷尽且不得新增），"至少"给实现 agent 留了添加未冻结 code 的口子。required fix 缩小为：把"至少覆盖"改为"穷尽覆盖且不得新增成员"，并可选附 UF scenario→code 映射表。

### F03（lazy bootstrap 回归验证需覆盖 download/preprocess 路径）——**接受，裁决一致（低）**

独立复证：`create_job` 现有 `file_lock(self.root_dir / _LOCK_FILE_NAME)`（ingestion_runtime.py:1871）在 lazy 模式下若无 `_ensure_root_for_write()` 会直接失败，plan §6.4 已 spec 该前置。S1 断言"download/preprocess/legacy job 的首次真实写仍成功"已覆盖主要写入口（begin_batch 与 create_job）。残余风险（下载 adapter 是否存在不经这两个入口的直写路径）因未读 `_fs_repository_factory.py`/download adapter 实现而无法证伪，列入 Residual Risks。

### F04（CLI stderr 格式模板未显式定义）——**接受但降权为低，与 MiMo 部分分歧**

分歧点：MiMo 认为需在 §6.1/6.6 定义 `"dayu-cli upload_filing: {failure.message}\n"` 模板。本裁决认为格式已由既有 `render_cli_error(f"dayu-cli {args.command_name}: {exc}")` 路径（fins.py:187 等）与 S2 断言"stderr 恰一行 `dayu-cli upload_filing: <reason>\n`"共同固定；reason 即 `FinsUploadUsageFailure.message`（§6.1 已定义其 bounds 与派生规则）。实现 agent 沿用现有 render 路径即可满足，无需新模板。残余：plan 未声明 usage stderr 是否复用 `render_cli_error` 还是新增渲染路径——若新增，需保证与现有 download/CLI usage 错误同格式；此为低风险一致性提醒，非契约缺失。

## Open Questions

1. **`prepare_upload` 的 prepared-delete 状态与 fingerprint skip 语义未读全**（docling_upload_service.py 188 之后未读）：§6.5 状态机"prepared delete: begin one batch, source delete only"与"skip 不 begin batch"依赖该既有语义的精确性。若 prepare 的 delete 路径实际不产生 prepared 对象（而是直接结果），状态机分支需按现状微调。低置信风险，实现前应由实现 agent 在 S3 首步核对。
2. **`build_fs_repository_set` 是否已透传 `create_directories` 参数**（_fs_repository_factory.py 未读）：S1 要求 `DefaultFinsRuntime.create` 使用 `build_fs_repository_set(..., create_directories=False)`，若工厂当前不透传，S1 需先改工厂——§7 未列该文件。中置信风险，需在 S1 实现时确认；若需改工厂，§7 清单应同步补齐。
3. **CN/HK 侧 source meta 读取的等价性**（cn_pipeline.py 实现未读）：`FilingUploadPublishedState.source_meta` 的语义对齐 SEC 的 `_safe_get_document_meta`（JsonObject | None），CN 侧 `upload_filing_stream` 是否用同一形态读取未证实；§6.3 快照契约对 CN 的适用性依赖此对齐。
4. **Host observed upload 路径的 usage 错误投影**：`FinsIngestionRuntime.upload` / `start_observed_upload` 是 Host 可触达的公共入口，plan 未声明该路径遇到 typed usage 失败时的投影（usage error 语义属于 CLI exit 2 契约还是 Host 侧 runtime 失败）。§6.1 的 recheck 声明了"同一 validator"，但未声明 Host 路径的失败投影。此问题与 DS-03 相关但范围不同，若 gate 认为 Host 路径不在 UF-FIX01 范围，应在 non-goals 显式声明。

## Residual Risks

1. **TOCTOU**：plan §12.1 已裁决（validation 非 commit authorization，workflow 重读 + batch fail-closed）。接受。
2. **eager bootstrap 回归**：plan §12.1 已裁决；残余为 F03/Open Question 2 未读路径，建议跟踪到 S1 实现首步确认。
3. **format drift**：plan §12.1 已裁决为 later WU。接受。
4. **failure redaction**：plan §12.1 已裁决（typed 分类→固定文案→bounds）。接受。
5. **UF-FIX09 converter 回归**：断言落点未指定（DS-06）；修复后风险降为低。
6. **现有 `read_source_snapshot` 的内部稳定读取（含 guard 重试）与新快照协议的并存**：plan §6.3 声明新协议是 validation/read model、非 commit concurrency guarantee；但两个读取协议并存可能让后续消费者选错协议。建议跟踪到 `dayu/fins/README.md` 更新时注明两者适用边界。
7. **§7 清单完整性**：DS-02（sec_pipeline.py）、Open Question 2（_fs_repository_factory.py）均为清单可能缺文件；建议 gate closeout 时以 git diff 反向核对 §7 授权边界。

## Plan Review Conclusion

**pass-with-risks**

独立裁决结论：plan 动机成立、证据链与代码事实一致（factory 先于校验、eager mkdir、双 batch、`str(exc)` 泄漏均经直接代码复核）、owner 表与 slice 顺序合理、action/company-name 处理未越界（均为既有规则前移）、UF-FIX09 与两套 allow-list 的不可变边界清晰。未发现应推翻该 plan 的结构性问题。

与 MiMo 的一致性：F01–F04 全部独立复核后接受（F02、F04 降权，理由见上）。本路新增 8 项 findings，其中 4 项中等（DS-01 函数归属矛盾、DS-02 SEC 装配链缺失、DS-03 validated 传导契约未 spec、DS-08 fast path 顺序未写死）——均属于 plan 文本可低成本修复的规格收敛问题（修复风险均为低），不要求重做设计，但建议在进入 implementation gate 前由 controller 裁决并入 plan 修正，否则实现 agent 将在 owner 归属、文件授权边界与签名契约上自行设计，产生本 WU 正在消灭的那类缺陷。
