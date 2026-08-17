# UF-FIX11 原子 S1+S2 Implementation 第二路独立严格 Review（DS）

- Work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- Gate：S1+S2 implementation review（第二路独立 review）
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- 基线：HEAD `0b4740fa`；review 对象为全部未提交 dirty diff（22 个已跟踪文件 + 2 个 untracked 文件）
- 审查输入：AGENTS.md/CLAUDE.md、gateflow SKILL.md、`docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`、`docs/gateflow/uf-fix11-slice-amendment-acceptance-20260817.md`、`docs/gateflow/uf-fix11-s1-s2-implementation-20260817.md`
- 验证复跑（全部从仓库根、venv 内执行）：
  - plan §12.1 focused suite：`706 passed, 3 warnings in 15.73s`，与 implementation doc 声明一致
  - plan §12.3.1 coverage（`pytest -q tests/fins`）：`1951 passed, 1 skipped`，12 个 S1+S2 生产文件逐文件 statement coverage 全部 ≥80%（最低 `company_metadata_warning.py` 80%，最高 `upload_company_meta.py` 97%，total 87%），与 implementation doc 声明一致
  - 全仓 pyright：exit 0（`0 errors, 0 warnings, 0 informations`）
  - §12.5 static boundary checks：`commit_batch` 全量收敛（dayu 3 定义 + test 7 文件/9 定义，其中 docling 文件 3 个）与 §9.2 清单 exact 对应；生产 `from_pipeline_json` callsite 恰为 service_runtime 4 处；变更文件无 `hasattr/getattr/Any/object` 违规；并发测试无 sleep/polling（全部 ThreadBarrier/Event 控制）
- Parallel review coverage：无；单一路径逐文件走读全部 production/test diff
- 本 review 未修改任何 production/test/doc 文件，未 stage/commit

## Scope

- Mode：current changes（未提交工作区，相对 HEAD）
- Included：S1+S2 allowed files 全集（12 个生产文件 + 11 个测试文件 + implementation artifact），另读入被改动文件的完整上下文（`_fs_storage_infra.py` commit 全链、`filing_upload_publication.py` 全状态机、`docling_upload_service.py` prepare/commit 链、`ingestion_runtime.py` parser 闭集）
- Excluded：无；`git status` 确认工作区 dirty 文件全部属于 S1+S2 allowed files，Host/Engine/material/oracle/scenario/frozen evidence 无 diff

## 结论

**findings**：3 项低 severity 测试缺口，无 correctness/stability/architecture 高 severity 发现。以下核心主张经代码走读与独立复跑验证成立：

1. **typed outcome 仅在真正 durable 成功后返回**：`_fs_storage_infra.py:533-611` 中 outcome 在 physical swap + `_PHASE_COMMITTED` journal + post-commit cleanup + capability close 全部成功后返回；任何失败路径（含 post-commit guard-release/cleanup 异常）都在返回前 raise，outcome 被丢弃（fail-closed，plan §13.5.4 accepted residual）。
2. **SKIP 双分支正确**：keep/no-intent → rollback + skipped(无 warning)（`filing_upload_publication.py:769-780`）；stage/preserve → stage → `batch_terminal_started=True` → `commit_batch` → exact outcome 投影（`filing_upload_publication.py:781-799`）。SKIP 分支不调用 publish/commit helper、不 stage filing/source asset。
3. **capability 转交与 rollback 唯一性正确**：`batch_terminal_started=True` 严格早于 `commit_batch`；outer finally 仅在 flag 为 False 时 rollback；commit 失败 0 次 caller rollback、commit 前 stage 失败恰 1 次，均有 terminal-aware spy 测试断言（`test_filing_upload_publication.py` 新增三测试）。
4. **publication-lock final truth**：warning predicate 使用 `_prepare_company_identity_commit` 在 publication guard 内重读合并出的 final `CompanyMeta`（`_fs_storage_infra.py:766-792`），与写入 staging 的值同一对象；writer lock 覆盖 batch 全生命周期，alias uniqueness 在全局 identity guard 内完成且 guard 跨越 prepare→swap，无 TOCTOU。
5. **并发反例**：barrier/event 测试证明 final-name winner 决定 loser warning、alias collision loser 得到 typed failure 且无 partial mutation、无 warning；无 sleep/polling。
6. **warning 不进 failed/cancelled 终态**：`FilingUploadPublicationOutcome.__post_init__` 与 `FinsUploadPipelineResult.__post_init__` 双重 invariant（仅 ok/skipped 可携带）；SEC/CN 全部 terminal producer（2 个 completed 路径 + 2 个 failure builder）显式 `warnings`，无消费者从 raw name/status/exception 反推。
7. **SEC/CN producer/parser closed schema**：filing terminal payload 必含 `warnings`，missing→fail closed（仅 MATERIAL 允许 missing→空 tuple）；null/非数组/未知 kind/错误文案/多字段/重复/超限全部 fail closed；真实 failure builder 经真实 workflow roundtrip 测试证明 typed reason 不退化。
8. **material 边界**：material 生产者未改、schema 未改；parser 对 MATERIAL 非空 warnings 拒绝（代码存在，测试缺口见 Finding 001）。
9. **测试 fake 未错误固化**：9 个 test `commit_batch` 定义全部 exact union 注解；需要 outcome 的 fake 返回 exact outcome 且由 owner 断言消费；无 fake 绕过 commit owner 直接注入 public warning。
10. **约束符合性**：所有新增函数中文 docstring 完整（参数/返回/异常）；pyright 0 报错；逐文件 coverage ≥80%；README 按 accepted plan 归 S3；diff 严格属于 allowed files。

三项 findings 均为测试缺口，不阻塞已声明的验证证据，但按 plan §12.3.1“低层协议/防御分支也应加 contract test”的精神与 fail-closed 分支的回归保护价值，建议 controller 裁决 `accepted` 并在 S3 测试切片（或本 review fix loop）内补齐。

## Findings

### 001-未修复-低-material 非空 warnings 的 fail-closed 拒绝分支无测试
- **入口/函数**: `FinsUploadPipelineResult.from_pipeline_json`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1774`
- **输入场景**: material terminal payload 显式携带一个结构合法的 warning 对象（例如未来 material producer 误加 warnings，或错误调用方把 filing 结果传给 material parser）
- **实际分支**: `if source_kind is SourceKind.MATERIAL and warnings: raise ValueError("material terminal result 禁止携带 company metadata warning")`
- **预期行为**: 拒绝（plan §6.6.1 明文“material 非空 warning 均被拒绝”；§12.5 要求任一 source kind 都不被 loose parsing 弱化）
- **实际行为**: 生产代码正确拒绝，但没有任何测试走该 raise 路径；现有测试仅覆盖 material missing→空 tuple（`test_fins_ingestion_runtime.py:9230-9244`）与 material `null`→ValueError
- **直接证据**: `grep` 全部测试无 MATERIAL+非空 warnings 拒绝断言；coverage report Missing 列 `ingestion_runtime.py:1774` 未被覆盖（本 review 复跑确认）
- **影响**: 该 plan-mandated schema 边界当前只由实现保证；后续 S3 或 material work unit 若无意弱化此分支（如改为忽略非空 warnings），确定性测试全绿无法阻止，material 侧将泄漏 filing 专属 warning 语义
- **建议改法和验证点**: 在 `test_pipeline_warning_parser_requires_filing_field_but_allows_material_missing` 内补充：`source_kind=SourceKind.MATERIAL` + `warnings=[规范 warning]` → `pytest.raises(ValueError, match="material")`；同时补 MATERIAL + `warnings=[]` → 接受（空数组合法）。验证：coverage 1774 变绿、focused suite 保持全绿
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-未修复-低-cancelled-outcome invariant 与 closed codec 的 raise 分支缺直接测试
- **入口/函数**: `FilingUploadPublicationOutcome.__post_init__`；`CompanyMetadataWarning.__post_init__`；`company_metadata_warnings_to_json`；`project_company_name_ignored_warning`
- **文件(行号)**: `dayu/fins/pipelines/filing_upload_publication.py:181-182`；`dayu/fins/company_metadata_warning.py:56,58,97,103,135,156,158,160,180`
- **输入场景**: 构造 status="cancelled" 且 warnings 非空的 publication outcome；构造 kind 类型错误/文案非规范的 warning；`to_json` 收到 >1 个或非精确类型元素；projection 收到非精确 domain fact；outcome.warnings 与内部 commit outcome 投影不一致
- **实际分支**: 各 TypeError/ValueError fail-closed raise 分支
- **预期行为**: 全部拒绝（plan §6.3 closed codec、§6.5 success/skip-only invariant、§8.4 终态矩阵）
- **实际行为**: 生产代码正确，但这些 raise 分支无任何直接测试；正向不变量通过 producer 断言（`warnings == []`/`warnings == [规范对象]`）间接证明，拒绝能力本身未证明
- **直接证据**: coverage Missing 列 `filing_upload_publication.py:178,182,187` 与 `company_metadata_warning.py:56,58,97,103,135,156,158,160,180` 全部未覆盖（本 review 复跑确认）；`grep` 测试目录无“禁止携带 warning”类拒绝断言
- **影响**: “failure/cancel 不泄漏 warning”的正确性目标正向路径测试充分，但 invariant 本身可被静默移除而全绿；closed codec 的 fail-closed 分支（未知 kind、错误文案、多字段）虽经 parser 层间接测试（`test_filing_pipeline_warning_parser_fails_closed`），codec 模块自身的构造器/序列化 raise 路径未证明
- **建议改法和验证点**: ① `test_filing_upload_publication.py` 增加 1-2 个 direct invariant 测试：cancelled outcome + 非空 warnings → ValueError；outcome.warnings 与 `result.company_meta_commit_outcome` 投影不一致 → ValueError。② 为 `company_metadata_warning.py` 的 raise 分支补参数化测试（kind 类型错误、文案非规范、`to_json` 超限/错误元素类型、projection 非精确类型）。验证：coverage 相应行变绿、focused suite 全绿
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 003-未修复-低-service parser callsite 结构测试按顺序断言，对无关重排产生假回归且无法定位漂移方法
- **入口/函数**: `test_production_runner_parser_callsites_use_explicit_source_kind`
- **文件(行号)**: `tests/fins/test_fins_service_runtime.py:198`
- **输入场景**: 未来对 `ProductionFinsUploadRunner` 四个 `from_pipeline_json` callsite 做纯顺序调整（语义不变），或新增/删除合法 callsite
- **实际分支**: `assert source_kind_names == ["FILING", "FILING", "MATERIAL", "MATERIAL"]`
- **预期行为**: 测试应钉住语义契约——每个 callsite 显式传 `SourceKind`，且 `upload_filing` 路径传 FILING、`upload_material` 路径传 MATERIAL——顺序是偶然事实，不应成为契约
- **实际行为**: ① 顺序调整即红（假阳性）；② 断言是位置列表而非方法绑定，若两个 filing callsite 之一错传 MATERIAL 而顺序仍是 FILING,FILING,MATERIAL,MATERIAL 则假阴性（当前实现正确，此为结构性弱点而非现存缺陷）
- **直接证据**: `tests/fins/test_fins_service_runtime.py:184-198` 用 `ast.walk` 收集调用并断言固定顺序列表；AST 收集顺序依赖源码物理顺序
- **影响**: 轻微：未来无关重排触发假回归；测试的防漂移能力弱于其语义目标；可维护性
- **建议改法和验证点**: 解析每个 callsite 的所属 `FunctionDef.name`，断言 `upload_filing` 方法内 callsite 集合恰为 `{FILING}`（2 处）、`upload_material` 方法内恰为 `{MATERIAL}`（2 处），并保留总数断言。验证：callsite 顺序重排后测试仍绿，单点 kind 漂移后测试变红
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

1. **post-commit/guard-release/cleanup 异常时 outcome 被丢弃**（commit 已 durable 但对外抛出异常、无 warning）：plan §13.5.4 已分类 `assigned to later work unit`；本 slice 行为 fail-closed、无假 warning，但运维可见性缺口仍存在。
2. **name-only skip 执行整树 physical swap 的成本**：plan §13.4.1 accepted tradeoff；final company meta bytes/`updated_at`/source tree 不变已由测试 exact 证明。
3. **`CompanyMetaCommitOutcome`/`CompanyNameIgnoredChange` 无 `__post_init__` 自校验**：`ignored_company_name.published_company_name` 与 `company_meta.company_name` 的一致性未在构造时强制；当前唯一生产构造点为 `company_meta_contract.py:276-283`，且下游每跳有 type-exact 校验与 `FilingUploadPublicationOutcome` 同源交叉检查兜底，风险可接受。
4. **`commit_prepared_upload_batch` 的 outcome 附着**（`docling_upload_service.py:1426-1430`）在 `test_docling_upload_service.py` 内无直接断言，由 SEC/CN e2e warning 测试（uploaded/skipped 两条真实路径）与 SKIP owner 测试间接证明。
5. **下载回归**：`requested_company_name` 默认 None 仅由既有 download 测试回归覆盖，无专门的“download 不产生 upload warning 语义”断言（下载不使用 warning 投影链，风险低）。
6. **`CompanyMetadataWarning.__post_init__` 的消息校验结构**：`if kind is COMPANY_NAME_IGNORED and message != 规范` 对未来新增 kind 无消息校验（闭集当前仅 1 个 kind，无实际风险）。
7. **HK 市场**：service callsite 结构测试覆盖 HK（CN 分支），行为测试以 CN 实例（600519）覆盖同一 cn_pipeline 实现。
8. **未复跑项**：§12.2 combined regression 的 cli/service 部分未在本 review 复跑（该部分文件无 diff、不在 S1+S2 allowed files；本 review 已复跑 focused suite、tests/fins 全量 coverage、全仓 pyright，与 implementation doc 声明的其余证据一致）。
9. **material 侧同类 company-name 行为**：plan §13.5.2 `assigned to later work unit`；本 slice 只实现 accepted 的 material missing-warnings→空 tuple parser contract（且非空拒绝无测试，见 Finding 001）。

## 已核验清单（非 findings）

- `commit_batch` 全量收敛：dayu 3 定义（Protocol + `_fs_storage_infra` + `fs_batching_repository`）、test 7 文件/9 定义，全部 `CompanyMetaCommitOutcome | None` 注解；无 `-> None` 协变漏改。
- 生产 `from_pipeline_json` callsite 恰为 `service_runtime.py:181,189,229,250` 四处，显式 `SourceKind`。
- SEC/CN filing terminal producer 全集：completed（`sec_upload_workflow.py:306`、`cn_pipeline.py:937`）与 failed（`:412`、`:1878`，含 CN early fresh-resolution 失败 `:803`）均显式 `warnings`。
- `batch_terminal_started` 文本顺序严格早于 `commit_batch`（`filing_upload_publication.py:787-789`、`docling_upload_service.py:1425-1426`）。
- 规范化常量逐字等于 plan §6.3 固定文案；public warning 不含路径、raw company names、内部治理标识。
- 修改文件严格属于 S1+S2 allowed files；README/Host/Engine/material/oracle/scenario/frozen evidence 零 diff。
