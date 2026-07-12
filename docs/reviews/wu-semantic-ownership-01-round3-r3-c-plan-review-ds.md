# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C Plan Review

## Artifact Metadata

- Review type: adversarial plan review
- Target: `docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md`
- Reviewer: DS (planreview skill)
- Timestamp: 2026-07-12T23:14:20+08:00
- Risk profile: production-high
- Status: pass-with-risks

## Reviewed Target And Scope

Target plan claims to close 5 owner-level semantics across 3 slices:

1. **S1** — Storage identity validation, batch commit point, LocalFileStore durability
2. **S2** — Single-document ingestion atomicity + CN/HK temp-less asset contract
3. **S3** — Host adapter snapshot + Service-owned Fins wait glue

Scope explicitly excludes: tool security (upload allowlist, URL/TLS/SSRF, byte budgets, LLM-facing security schema), R3-D financial semantics, R3-E Web egress, DR-024 Docling fallback.

## Sources Consulted

- `AGENTS.md` — semantic ownership, layering, coding constraints
- `docs/reviews/wu-semantic-ownership-01-round3-r3-c-goal-confirmation.md` — scope boundary and success signals
- `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md` — accepted findings and owner boundaries
- `docs/phaseflow-umbrella-optimization-control.md` — slice count, risk tier, validation profile constraints
- `docs/host/issues-implementation-control.md` (lines 1-250) — plan requirements and validation matrix rules
- `docs/host/design.md` (lines 1-100, 920-1000, 2300-2500) — Host architecture, wait record, adapter snapshot boundaries
- `docs/engine/design.md` (lines 1-100) — Engine contract boundaries
- `dayu/README.md` — cross-package boundaries, Service as composition boundary
- `dayu/fins/README.md` — Fins storage, ingestion, wait adapter contracts
- Source code verification (see findings for specific line evidence)

## Assumptions Tested

1. Storage identity owner is `dayu.fins.storage` and single-component validation can be enforced at that boundary — **CONFIRMED** by `_fs_storage_utils.py:82-125` (existing entry/document-id validators) and `_fs_storage_infra.py:939-958` (key builder reuses normalized forms).
2. `commit_batch()` can be rewritten with COMMITTED as sole commit point — **CONFIRMED** by `_fs_storage_infra.py:255-294` showing current flawed ordering and `_fs_storage_utils.py:463-487` showing fsync/replace precedent.
3. CN/HK workflow can separate network/convert from storage batch — **QUALIFIED** (see Finding 1).
4. `pdf_bytes` replacement doesn't change security/resource policy — **CONFIRMED** by `cninfo_downloader.py:337-353` and `hkexnews_downloader.py:334-350` showing `response.content` already fully loaded.
5. Service can own wait glue without importing Host durable internals — **CONFIRMED** by `host_assembly.py:28-38` showing existing Fins→Service import pattern and `test_import_boundary.py:10-32` showing enforced boundary.
6. Three slices cover distinct owner boundaries — **CONFIRMED** by analysis of blast radius, validation matrix, and dependency order.

---

## Findings

### 1-未修复-高-S2未明确commit_cn_filing_source_document在caller batch内的重构契约

- **位置**: S2 Exact allowed changes #5 (line 314) 与 S2 Allowed production files `cn_download_source_upsert.py` (line 294)
- **问题类型**: 契约缺失 / 可实施性缺口
- **当前写法**: Plan 要求 CN/HK workflow "把 reset/ack/blob/final source/processed marker 收束到一个无 yield/await 的 batch commit 段"（line 314:5），但对 `cn_download_source_upsert.py` 仅写"仅当需要使helper docstring明确'caller batch内执行'；不得新增第二个commit owner"（line 294）。
- **反例/失败场景**: 当前 `commit_cn_filing_source_document`（`cn_download_filing_workflow.py:519-535`）是 workflow 的最后一个存储步骤，它可能内部调用 `commit_batch()` 或直接写 final meta。如果该函数内部自己管理 batch commit，workflow 无法把所有 mutation 收束到同一个外层 batch——blob 写入和 final meta 会在不同事务中提交，违反 S2 的单 document atomicity 目标。
- **为什么有问题**: S2 的核心契约是"source acknowledgement、blob、final meta、processed marker 在同一 batch 内"。如果 `commit_cn_filing_source_document` 内部已有独立的 commit 语义，implementation agent 有两个选择：(a) 重构该函数为"仅 stage、不 commit"模式，但这改变了函数的 public contract；(b) 在 workflow 层绕过该函数自行编排，但这会导致代码重复。Plan 没有明确选择哪条路径，也没有说明该函数的现有 contract 是否需要修改、如何修改。
- **直接证据**:
  - `cn_download_filing_workflow.py:519-535` 调用 `commit_cn_filing_source_document(...)` 作为单 filing 的最后一步
  - Plan line 294 对该文件的修改授权过于模糊："仅当需要使helper docstring明确"
  - Plan line 189 的硬约束"batch 内不 yield/await"与该函数当前实现的关系未澄清
- **影响**: Implementation agent 在 S2 遇到此函数时可能：(a) 保留函数内部的独立 commit，导致 S2 的 atomicity 目标在 CN/HK 路径上不成立；(b) 重构该函数但触及未预期的 contract 变更，触发 stop condition（"若需要改变 repository protocol 方法集合"）。
- **建议改法和验证点**:
  1. Plan 应明确 `commit_cn_filing_source_document` 的重构契约：是改为"仅 stage 到 caller batch、不 commit"，还是保留内部 commit 但要求 caller 在调用前开启 batch 并将 token 传入？
  2. 若改为"仅 stage"，需验证 workflow 中 commit 的统一调用点确实覆盖了 reset → ack → blob → final meta → processed marker 的全部 mutation。
  3. 实现 artifact 中 `cn_download_source_upsert.py` 的 diff 应被显式 review，确认不引入第二个 commit owner。
- **修复风险**: 低——只需澄清设计决策，不改变整体方案
- **严重程度**: 高——若不澄清，S2 在 CN/HK 路径上可能无法实现单 document atomicity

### 2-未修复-中-commit_batch回滚阶段二次异常的报告语义未细化

- **位置**: Batch commit state machine (lines 161)
- **问题类型**: 状态机漏洞 / 可实施性缺口
- **当前写法**: "无法完成物理恢复的二次 filesystem error 必须保留 journal/backup供 recovery，且与原 commit error一起显式报告；不得删除恢复证据或声称 rollback 成功。"
- **反例/失败场景**: 原始 commit error（如 `OSError` from journal write）触发 rollback，rollback 中 backup restore 又失败（如磁盘满）。Python 3.11 支持 `ExceptionGroup`，但当前项目代码基线（`_fs_storage_infra.py:272-289`）使用 plain `raise`（重抛原异常）。Plan 没有指定使用 `ExceptionGroup`、chained exception（`raise ... from ...`）还是自定义 composite error type。
- **为什么有问题**: Implementation agent 需要在三种方案中选择，但选择会影响 caller 的异常处理代码和测试断言。若用 `ExceptionGroup`，现有 `except Exception` 调用方需要适配（Python 3.11 `except*` 语法或 `split()`）。若用 chained exception，原 commit error 和 rollback error 的语义关系不明确（哪个是"主要原因"？）。若用自定义 composite，需新增错误类型并更新所有调用方的 import 和 except 分支。
- **直接证据**:
  - Plan line 161 只描述"必须...一起显式报告"，没有指定 Python 异常传播机制
  - `_fs_storage_infra.py:272-289` 当前使用 plain `raise`（重抛原异常），没有 rollback error 报告
  - Plan 的 S1 Required assertions (line 253) 要求"注入每个pre-commit phase失败"但未说明如何断言双重异常
- **影响**: Implementation agent 可能选择最简单的 plain `raise`（丢弃 rollback error），导致 operator 无法区分"commit 失败但已恢复"和"commit 失败且恢复也失败"——后者需要人工介入，前者可以安全重试。
- **建议改法和验证点**:
  1. Plan 应指定双重异常的传播方式。建议：用 `raise RuntimeError("commit and rollback both failed") from rollback_error` 包裹，原 commit error 作为 `__context__`，同时在 log WARN/ERROR 中记录两者。
  2. S1 测试应包含"commit 失败 + rollback 也失败"的 case，断言：(a) 双重异常被传播到 caller，(b) journal/backup 未被清理，(c) orphan recovery 能识别并等待人工决策。
- **修复风险**: 低——只在现有异常处理路径上增加语义
- **严重程度**: 中——不阻塞 S1 实施，但缺失会导致生产排障困难

### 3-未修复-中-DownloadedReportAsset契约变更的影响范围未穷举

- **位置**: S2 CN/HK downloaded asset contract (lines 195-198) 与 Required assertions (lines 337-338)
- **问题类型**: 可实施性缺口
- **当前写法**: Plan 声明 `pdf_path: Path` → `pdf_bytes: bytes`，并说"源码/测试不再引用`pdf_path`或`tempfile`"（line 337）。
- **反例/失败场景**: `DownloadedReportAsset` 类型定义可能在 `cn_download_models.py` 或 `cn_download_protocols.py`（均为 S2 allowed files）。但该类型的 consumers 不限于 S2 列出的文件——可能有其他 pipeline、测试 fixture、类型检查代码或序列化路径引用 `pdf_path` 属性。Plan 的 rg scan（line 348）只搜索文件名模式，不搜索属性访问 `asset.pdf_path` 或类型注解中的 `pdf_path`。
- **为什么有问题**: 如果 `DownloadedReportAsset` 是 NamedTuple，改变字段会破坏所有按位置解包的代码（`pdf_path, sha256, ... = asset`）。如果是 dataclass，改变字段类型从 `Path` 到 `bytes` 可能需要更新所有消费方的类型注解。Plan 的代码搜索范围（`dayu/fins/downloaders dayu/fins/pipelines tests/fins`）可能遗漏：
  - `dayu/fins/pipelines/cn_download_models.py` 中的类型定义本身
  - 任何 `hasattr(asset, 'pdf_path')` 或 `getattr(asset, 'pdf_path')` 的动态访问
  - 其他 downloader 或 pipeline 中导入 `DownloadedReportAsset` 做类型检查的代码
- **直接证据**:
  - Plan line 292-293 将 `cn_download_models.py` 和 `cn_download_protocols.py` 列入 allowed production files
  - Plan line 348 的 rg scan 只搜索字符串字面量 `pdf_path`，不搜索属性访问
  - `cninfo_downloader.py:347-353` 构造 `DownloadedReportAsset(candidate=..., pdf_path=pdf_path, ...)` 使用关键字参数，字段名改变是明确的
- **影响**: Implementation agent 可能遗漏非显而易见的 `pdf_path` 引用，导致：(a) 类型检查失败；(b) 运行时 `AttributeError`；(c) 测试 fixture 构造失败。
- **建议改法和验证点**:
  1. Plan 的 S2 validation 应增加 `rg -n '\.pdf_path\b' dayu/fins --glob '*.py'` 和 `rg -n 'pdf_path' tests/ --glob '*.py'`，覆盖属性访问而不仅仅是字符串字面量。
  2. 实现前应先确认 `DownloadedReportAsset` 的类型定义位置（NamedTuple/dataclass/Protocol），并在 plan 中记录。
  3. 若存在按位置解包的代码，plan 应明确要求改为关键字访问。
- **修复风险**: 低——纯搜索范围扩展
- **严重程度**: 中——可能导致 S2 实现遗漏引用，但修复成本低

### 4-未修复-中-S1 per-phase失败注入的测试机制未指定

- **位置**: S1 Required assertions (lines 253-254)
- **问题类型**: 测试缺口 / 可实施性缺口
- **当前写法**: "注入每个pre-commit phase失败：旧target存在时内容完全恢复；旧target不存在时target保持不存在；token关闭且无业务可见staging。"
- **反例/失败场景**: Plan 要求测试注入 `BACKED_UP_TARGET`、`SWAPPED_TARGET` 等每个 phase 的失败，但未说明注入机制。`commit_batch()` 的 phase 通过 journal 写入表达。注入失败的可行方式包括：(a) mock `os.replace`/`shutil.move` 在特定调用次数时抛异常；(b) 在测试用临时目录中制造权限问题；(c) monkeypatch `_write_batch_journal`。不同机制有不同的可靠性、平台依赖和维护成本。
- **为什么有问题**: 如果 implementation agent 选择了脆弱的注入机制（如基于调用计数的 mock），测试可能：(a) 在代码重构后 silently pass（mock 不再被调用但测试不报错）；(b) 在不同 OS 上行为不一致（权限模型差异）；(c) 无法覆盖真正的文件系统边界条件（如 ENOSPC）。
- **直接证据**:
  - Plan lines 252-256 列出了每个 phase 的断言要求，但未指定测试工具或注入点
  - `_fs_storage_infra.py:255-294` 的 `commit_batch()` 没有明确的 seam 供测试注入失败
  - Plan 的 S1 test file 是新增的 `tests/fins/test_fins_storage_atomicity.py`，没有现有测试模式可参考
- **影响**: Implementation agent 可能选择过度 mock 的方案，导致测试不验证真实文件系统行为；或选择过于复杂的方案，导致测试本身成为维护负担。
- **建议改法和验证点**:
  1. Plan 应指定至少一种推荐的失败注入方式。建议：优先使用真实临时目录 + 有限权限（如 `os.chmod` 移除写权限）或 monkeypatch journal 写入函数来模拟特定 phase 失败。避免基于调用计数的 mock。
  2. 每个 phase 失败测试应包含最终的文件系统状态断言（`target_dir.exists()`、`backup_dir.exists()`、staging 清理），而不仅仅是异常类型断言。
  3. 实现 artifact 应记录选择的具体注入机制及理由。
- **修复风险**: 低——补充测试策略说明
- **严重程度**: 中——不阻塞实施，但可能导致测试覆盖空洞

### 5-未修复-低-commit_batch旧格式journal的恢复兼容性是一个已自解的低概率风险

- **位置**: Batch commit state machine (lines 145-161) 与 orphan recovery (S1 line 243)
- **问题类型**: 状态机漏洞（低概率）
- **当前写法**: Plan 重写 commit_batch 的 phase 解释——旧代码在 `SWAPPED_TARGET` 阶段当 backup+target 并存时视为成功（删除 backup）；新代码在 `SWAPPED_TARGET` 阶段视为未提交（恢复 backup）。
- **反例/失败场景**: 如果在代码部署瞬间存在一个旧格式的 SWAPPED_TARGET journal（进程在 `shutil.move(staging→target)` 之后、`shutil.rmtree(backup)` 或 `_write_batch_journal(COMMITTED)` 之前崩溃），新 recovery 代码会将其解释为"需要 rollback"并恢复 backup。这实际上恢复了 pre-batch 状态——比旧行为（错误地当作成功）更安全。唯一的数据丢失风险是：backup 已被旧代码删除但 COMMITTED 未写入——此时 SWAPPED_TARGET + 无 backup + 有 target。这是旧代码行 268-270 的窗口（backup 已 rmtree，COMMITTED 尚未写）。新 recovery 遇到此状态时，target 存在且 backup 不存在，按 line 161 逻辑无法恢复，只能保留 target 并报告。
- **为什么有问题**: 这不是 plan 引入的新风险——旧代码已经存在这个窗口。Plan 的新状态机通过调整顺序（COMMITTED 在 backup cleanup 之前写）关闭了这个窗口。但迁移瞬间的 in-flight batch 理论上可能处于旧窗口。实际概率极低：batch 是进程内 token，部署通常需要重启进程，此时没有 active batch。
- **直接证据**:
  - `_fs_storage_infra.py:266-270` 当前顺序：swap → delete backup → write COMMITTED（窗口在 delete backup 和 write COMMITTED 之间）
  - Plan lines 155-158 新顺序：swap → write COMMITTED → cleanup backup（窗口关闭）
  - Plan 没有显式讨论旧格式 journal 的迁移
- **影响**: 极低概率的 in-flight batch 在新 recovery 下被正确处理（恢复 pre-batch 状态或保留 target + 报告异常）。不是数据损坏风险。
- **建议改法和验证点**: 无需 plan 修改。Implementation artifact 应记录：部署前确保没有 active batch（正常重启即可保证），并验证 orphan recovery 对新旧 phase 组合的处理。
- **修复风险**: 无需修复
- **严重程度**: 低——已自解，无需 plan 变更

### 6-未修复-低-S3的import-boundary测试更新时机与production代码变更有顺序依赖

- **位置**: S3 Required assertions (lines 416-423) 与 Allowed test files `tests/fins/test_fins_storage_provider.py` (line 237, 390)
- **问题类型**: 切片顺序
- **当前写法**: Plan 说 S3 与 S1/S2 无代码依赖（line 371），但 S1 的 `tests/fins/test_fins_storage_provider.py` 包含对 Fins wait adapter import Host 的特判（line 237: "S3再改import-boundary特判"）。S3 的 test 文件列表包括 `tests/fins/test_fins_storage_provider.py`（line 390），说明 S3 需要修改 S1 也修改的同一个测试文件。
- **反例/失败场景**: 如果 S1 和 S3 并行实施（plan 说 S3 无代码依赖），两个 implementation agent 可能同时修改 `tests/fins/test_fins_storage_provider.py`，产生合并冲突或语义冲突。如果串行实施（S3 after S2），S1 实现中留下的"S3 再改"注释可能被遗忘。
- **为什么有问题**: Plan 说"与S1/S2无代码依赖"（line 371）但 S1 的测试文件中有明确的 deferred-to-S3 项。这不是依赖循环，但是同一个文件的跨 slice 修改需要协调。
- **直接证据**:
  - Plan line 237: "S3再改import-boundary特判"（在 S1 的 test file 说明中）
  - Plan line 390: S3 allowed test files 包含 `tests/fins/test_fins_storage_provider.py`
  - Plan line 371: "与S1/S2无代码依赖；为减少review互相掩盖，建议在S2 accepted后实施并独立review"
- **影响**: 低——只是测试文件协调问题，不涉及 production 代码冲突。Plan 已建议 S3 在 S2 后独立实施。
- **建议改法和验证点**: Implementation artifact S1 应在修改 `test_fins_storage_provider.py` 时加明确的 `# TODO(S3): remove import-boundary exception` 注释，S3 实现时 grep 该注释确保不遗漏。
- **修复风险**: 无需修复 plan
- **严重程度**: 低——可操作的风险，已有缓解措施

---

## Focus Area Reports

### FA1: Scope Correction (Tool Security)

**结论: PASS** — 无安全策略漂移。

Plan 在 4 个层面防止 scope creep：
1. **Non-Goals** (lines 105-116) 明确排除 4 类安全策略
2. **Stop Conditions** (S2 line 359-361) 要求触及安全策略时立即停止
3. **Tool-Security Deferred Items** (lines 503-519) 清晰列出 4 项 deferred finding 及 destination WU
4. **Final Validation** (line 480) 用 `git diff -- dayu/config/prompts dayu/fins/tools dayu/config/tool_discovery.json` 验证无 LLM-facing 变更

F4 的 `pdf_bytes` 替换不构成安全策略漂移：`response.content` 已在内存中，改变的是字节的持有方式（从"写磁盘再读回"到"保持在 typed asset 中"），不改变网络读取、URL 策略或字节上限。详见 FA4。

### FA2: Storage Identity and LocalFileStore Atomicity

**结论: PASS** — S1 的 owner 级契约足够实施。

正面证据：
- Identity contract (lines 136-141) 明确 single-component validator、拒绝规则、local URI 约束和 handle existence check，覆盖了 `_normalize_ticker`、`_normalize_entry_name`、`_normalize_document_id`、`_build_store_key` 和 `store_file()` 的所有入口
- Commit state machine (lines 145-161) 精确定义了 5 个 phase 的转换、每个 phase 的异常恢复行为和 COMMITTED 的唯一 commit point 语义
- LocalFileStore put contract (lines 163-168) 参考了已验证的 `_write_json` 先例（`_fs_storage_utils.py:463-487`），指定 UUID temp、fsync、atomic replace、dir sync
- Stop conditions (lines 273-275) 覆盖了 atomic rename 可行性、recovery 正确性和 contract 稳定性

缺口（已记录为 Finding 4 和 Finding 5）：
- Per-phase 失败注入的测试机制未指定（Finding 4，中）
- 旧格式 journal 迁移的概率性风险（Finding 5，低，已自解）

### FA3: Single-Document Ingestion Atomicity

**结论: PASS-WITH-CONCERN** — 方案正确但 CN/HK 路径的 batch 编排有契约缺口。

正面证据：
- Mutation contract (lines 170-192) 明确定义了 7 步序列：prepare → checkpoint → begin batch → reset/ack → blobs → final meta → processed → commit
- 硬约束"batch 内不 yield/await"（line 189）保证了 async generator close 的安全窗口
- State/rollback matrix (lines 318-329) 覆盖了 8 种路径 × 失败点的预期可观察状态
- Upload 路径（DoclingUploadService）的改造方向明确：conversion/validate 在 batch 外，ack/blob/final 在 batch 内

缺口（已记录为 Finding 1）：
- `commit_cn_filing_source_document` 在 caller batch 内的重构契约未明确（Finding 1，高）

### FA4: CN/HK Temp-Less Asset Contract

**结论: PASS** — 方案正确，不漂移到安全策略。

正面证据：
- `response.content` 已在下载时完整加载到内存（`cninfo_downloader.py:331` 读取 `payload`，`hkexnews_downloader.py:333` 同样），改 `pdf_bytes` 只是消除磁盘 roundtrip
- 不改变 HTTP request、URL、redirect、TLS 或 byte-budget 行为（line 198）
- 消除了跨 `asyncio.to_thread()` 边界的 cleanup handoff——这是取消路径泄漏的 root cause（详见 F4 第一性原理分析, lines 70-78）

缺口（已记录为 Finding 3）：
- `DownloadedReportAsset` 类型变更的影响范围搜索不够穷举（Finding 3，中）

### FA5: Wait Adapter Relocation

**结论: PASS** — 方案 clean，符合架构设计真源。

正面证据：
- 数据流清晰单向：`WaitRecordRow` (Host durable) → `WaitAdapterSnapshot` (Host projection) → Service adapter → Fins observation → Host resolve_wait pipeline（lines 202-209）
- Host 设计真源（`docs/host/design.md:2436-2442`）已要求 typed adapter binding 和 typed refs
- Service 已在 `host_assembly.py:28-38` 消费 Fins wait adapter imports，迁移到 Service 只需改变 import 源
- 不改变 Host wait state machine、Engine awaiting contract 或 LLM-facing result（line 215）

缺口：
- S3 与 S1 共享 `test_fins_storage_provider.py` 的修改协调（Finding 6，低）

### FA6: Slice Count

**结论: PASS** — 3 slices 合理，符合 umbrella control doc 约束。

验证：
- S1（Storage）和 S2（Ingestion）按不同 semantic owner 拆分：storage owner vs. ingestion consumer。符合 `phaseflow-umbrella-optimization-control.md:99`。
- S2（Ingestion）将 CN/HK temp lifecycle 与 download atomicity 合并，因为它们共享 `DownloadedReportAsset` contract 和同一 workflow。单独拆分 CN/HK temp 会导致中间 slice 保留 temp handoff。符合"禁止按 raw finding 拆分"规则（`phaseflow-umbrella-optimization-control.md:106-109`）。
- S3（Wait glue）有不同 owner (Service/Host boundary)、不同 validation matrix 和独立 blast radius。符合拆分标准。
- 3 slices ≤ 3，无需超限例外（`phaseflow-umbrella-optimization-control.md:119`）。

### FA7: Validation

**结论: PASS** — 验证方案充分，覆盖了关键风险面。

正面证据：
- 每 slice 有明确的 pytest 文件列表、pyright 全量、`git diff --check`
- S2 增加 temp PDF contract scan（rg `NamedTemporaryFile|dayu_cn_downloads|...`）
- S3 增加 Fins→Host import scan（rg `from dayu.host`）
- Final validation 增加 LLM-facing diff 检查和 per-file coverage >= 80%
- Pre-existing failure 的处理引用了 umbrella control doc 的 baseline registry 机制（line 487）

缺口：
- S1 的 per-phase 失败注入机制未指定（Finding 4，中）
- 80% per-file coverage 对 storage/worfklow 代码可能 ambitious，但这是目标而非硬阻塞条件

---

## Open Questions

1. **S1 commit_batch 的 post-COMMITTED cleanup 是否需要 fsync directory？** Plan 说"每次关键 rename 后刷新受影响 parent directory"（line 156）但没有明确 COMMITTED journal 写入后的 directory sync 是否属于"关键 rename"。当前 `_write_json` 在 replace 后调用 `_fsync_directory`（line 487），plan 应明确 journal commit 使用同一模式。

2. **S2 中 `DoclingUploadService` 的 create 路径当前使用 repository auto-batch，改为显式 batch 后，`_acknowledge_source_before_blob_write` 的行为是否会改变？** 该函数当前在无 batch 时创建 staging source。改为始终在显式 batch 内调用时，其内部 staging 逻辑是否需要适配 batch 上下文？

3. **S3 中 `WaitAdapterSnapshot` 的 `resume_token` 解析失败时，Host 应抛什么异常？** Plan 说"非法 durable timestamp 在 Host owner 处 fail closed，不由 Service 回退到 now"（line 420）。但异常类型（`ValueError` vs 自定义 `WaitRecordCorruptedError`）会影响 Host poller 的错误处理路径。

---

## Residual Risks

| Risk | Classification | Owner / Destination |
| --- | --- | --- |
| `commit_cn_filing_source_document` 的重构契约未明确 | plan gap — 应在 plan 中澄清 | Plan author 在 S2 实施前补充 |
| commit+rollback 双重异常的传播机制未指定 | plan gap — 应在 plan 中补充 | Plan author 在 S1 实施前补充 |
| `DownloadedReportAsset` 属性变更的影响范围可能不完整 | implementation risk — 扩大代码搜索即可缓解 | Implementation agent 在 S2 实施时执行全量 attribute scan |
| Per-phase 失败注入测试机制未指定 | implementation risk — agent 需自行选择 | Implementation agent 在 S1 实施时记录选择的机制 |
| `pdf_bytes` 内存驻留时间延长（从"写磁盘后释放"变为"保持到 workflow 处理完成"）对于极大 PDF 的理论风险 | accepted risk — 当前 `response.content` 已全量加载，不新增内存压力 | N/A |
| S3 与 S1 共享测试文件的修改协调 | implementation risk — 已有缓解（S3 after S2） | Implementation agent 在 S1 加 TODO 注释 |
| Post-COMMITTED journal directory sync 的必要性 | open question — 见 Open Questions #1 | Plan author 或 implementation agent 确认 |

所有 residual 已分类，有 owner 或 destination。

---

## Final Plan Review Conclusion

**Status: pass-with-risks**

**Findings count: 6** (1 high, 3 medium, 2 low)

**Blocking questions: 0**

Plan 在 scope boundary、architecture alignment、state machine design 和 validation coverage 方面是 solid 的。三个 slice 的拆分合理，符合 umbrella control doc 约束。Security scope exclusion 在多个层面被 enforce。

两个 material gap 需要在实施前收敛：
1. **Finding 1 (高)**: `commit_cn_filing_source_document` 在 S2 caller batch 内的重构契约需明确，否则 CN/HK 路径的 single-document atomicity 无法保证。
2. **Finding 2 (中)**: commit+rollback 双重异常的 Python 传播语义需指定，否则生产排障缺少关键诊断信息。

这些不是 plan 方案层面的缺陷，而是 specification completeness 层面的缺口——补充后 plan 即可 code-generation-ready。

**Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-review-ds.md`
