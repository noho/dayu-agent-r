# WU-SEMANTIC-OWNERSHIP-01 / R06-S2 implementation（Codex）

## 1. Gate 结论

状态：`READY_FOR_CONTROLLER_VALIDATION`。

本次是既有 umbrella WU 的 R06-S2 implementation gate，工作树继续累计保留 S1，不是新 WU；未进入 S3，未 stage、commit、push 或创建 PR。

S2 唯一目标已经在 storage owner boundary 闭合：`SourceHandle` 只表达 source identity，open `BatchToken` 对应的 registry state 才是 mutation authority；source blob 可以先写入 transaction staging，但只有包含完整 meta、typed provenance、非空 files、精确 primary 与双向 manifest 投影的 staged source tree 才能在一次 `commit_batch` 中成为 published truth。

## 2. 第一性原理动机与 owner 判断

### 2.1 动机成立

实施前的当前代码与 accepted design 存在四个直接矛盾，不是由测试或下游表现间接推断：

1. source protocol/wrapper/core 仍暴露 `stage_source_document`，以 `ingest_complete=false` meta 表示 acknowledgement；
2. blob core 在 `SourceHandle` 写入前读取 source meta，要求 acknowledgement 先存在；
3. source upsert 保留 incomplete stable re-entry，并允许用第一项 file 补 primary；
4. `commit_batch` 在 physical swap 前没有 storage-owned complete-source validator。

这些事实会让 acknowledgement meta、blob、final meta 与 manifest 分别成为可见性资格的竞争真源，因此 S2 breaking cutover 必须实施。

### 2.2 唯一语义 owner

- mutation authority owner：shared `FsStorageCore` 的 active batch registry；`BatchToken(transaction_id, ticker)` 只是 opaque capability，`SourceHandle` 不是 authority；
- staged source identity owner：batch 对应的完整 staging ticker tree；validator 固定遍历树，不维护 touched identity 列表；
- source publication qualification owner：`commit_batch` 调用的唯一 complete-source validator；
- provenance owner：`SourceDocumentProvenance.from_meta(...)` typed contract；filing/material manifest 均复用同一 typed provenance 与 `from_source_meta(...)` projection；
- final completion owner：source mutation boundary 强制 `ingest_complete=True`，显式 false 当场 fail closed；commit validator再次拒绝被物理篡改成 false 的 staged meta。

没有在 read runtime、producer、fixture 或 adapter 重算或补偿 source 完整性。

## 3. 精确 authored scope

### 3.1 Production（7 个，全部在 S2 allowlist）

| Path | S2 authored change |
| --- | --- |
| `dayu/fins/domain/document_models.py` | filing/material manifest 增加 required typed provenance/completion 字段；新增唯一 `from_source_meta` 投影。 |
| `dayu/fins/storage/repository_protocols.py` | 删除 `stage_source_document`；blob write contract 改为 source blob-first、processed 仍要求 meta。 |
| `dayu/fins/storage/_fs_storage_infra.py` | `commit_batch` 在 publication guard 前调用完整 staged ticker tree validator；闭合 source/meta/files/primary/manifest/containment。 |
| `dayu/fins/storage/_fs_blob_core.py` | `SourceHandle` blob-first；只校验 active batch、ticker、handle/filename contract 与 staging containment，processed 路径仍校验 meta。 |
| `dayu/fins/storage/_fs_source_document_core.py` | 删除 acknowledgement/stable re-entry；final source 强制 typed provenance 与 true completion；删除 first-file primary fallback；manifest 统一投影。 |
| `dayu/fins/storage/fs_document_blob_repository.py` | 同步 blob-first public wrapper contract。 |
| `dayu/fins/storage/fs_source_document_repository.py` | 删除 acknowledgement wrapper。 |

没有修改其它 production path。工作树中其余 8 个 dirty storage production 文件是进入本 gate 前已存在并被要求原样保留的累计 S1 diff；本 gate 没有在那些文件追加 S2 语义。

### 3.2 Tests（4 个，全部在 S2 allowlist）

- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`

旧 acknowledgement/stable retry fixture 已由 blob-first + complete final source owner fixture 替换；测试不实现 validator，不放宽 schema，不从 public token 推导路径。为注入真实 staged filesystem corruption，owner test 读取同一 shared core 已登记的唯一 active state；校验逻辑仍只由 production commit owner 执行。

### 3.3 Artifact

本文件是本 gate 唯一新增/更新的 artifact。既有 control、controller/reviewer、design、README 与 S1 artifacts 均未修改。

## 4. Complete-source validator 算法

validator 是 `_fs_storage_infra.py` 中的单一 storage-owned precommit barrier，顺序固定如下：

1. 校验 staging ticker root 是 batch staging root 内的 non-symlink directory，目录名与 transaction ticker 一致；
2. 固定遍历 `filings` 与 `materials` 两棵完整 staged source tree；source-free transaction 允许对应 root 不存在；
3. filing root 中只把既有 maintenance owner 的 `_download_rejections.json` 与 `.rejections` 排除出 source identity 集合，不读取它们反推 source；
4. 读取 kind 对应 manifest，校验 regular file、ticker、documents 数组、canonical/unique document identity；
5. 构造目录 identity 集合与 manifest identity 集合，分别计算 `source - manifest` 和 `manifest - source`，任一非空即失败；
6. 对每个 source 读取 `meta.json`，校验 ticker/document/source-kind 与目录一致，并复用 `SourceDocumentProvenance` 校验 ingest method、provider 与 true completion；
7. 校验 `files` 为非空数组、业务文件名 canonical 且唯一；每项必须命中同一 source 目录内 non-symlink regular file，URI 精确等于 staged source URI，存在的 size/sha256 与 physical file 一致；再反向比较 physical business filenames，拒绝未声明文件；
8. 校验 `primary_document` 为非空 canonical filename，精确命中 `files`；没有 first-file fallback；
9. 通过 `FilingManifestItem.from_source_meta` / `MaterialManifestItem.from_source_meta` 构造唯一期望投影，与对应 manifest item 做 exact equality，闭合 identity/provenance/completion；
10. validator 不检查 processed/company/maintenance 业务语义；这些 mutation 只需位于同一 staging ticker tree，不能成为 source 推断输入。

validator 没有 touched identities、兼容 parsing、default/fallback 或 consumer-derived repair。

## 5. Failure grid 与错误语义

参数化 owner test 对每格都先发布 `old_source`，再构造包含 `new_source` 的 staged tree并只破坏一项事实。所有格均在 target rename 前抛出 `ValueError`，由 commit owner 执行既有 precommit rollback、消费 token并保留 old；caller 对已消费 token 的二次 rollback 被拒绝。

| Failure grid | Storage owner error semantics |
| --- | --- |
| missing meta | source directory 缺少 `meta.json`，不能成为 complete source。 |
| empty files | `files` 不是非空数组。 |
| duplicate files | 同一 source 的业务 filename 重复。 |
| dangling file | manifest file 没有同目录 physical regular file。 |
| missing primary | `primary_document` 缺失或为空。 |
| invalid ingest method | typed provenance 拒绝未知 ingest method。 |
| invalid provider | typed provenance 拒绝未知 source provider。 |
| false completion | complete source 禁止 `ingest_complete=false`。 |
| ticker mismatch | meta ticker 与 transaction/source directory 不一致。 |
| document mismatch | meta document identity 与 source directory 不一致。 |
| source-kind mismatch | meta source kind 与 filing/material directory 不一致。 |
| URI mismatch | file URI 不等于同一 staged source physical locator。 |
| size mismatch | 声明 size 与 physical regular file 不一致。 |
| sha mismatch | 声明 sha256 与 physical regular file 摘要不一致。 |
| symlink file escape | declared file 是 symlink/escape，不是 contained regular file。 |
| filename escape | filename 不是单一 canonical entry，拒绝 `..` escape。 |
| unmanifested physical file | physical business files 与 `files` 反向集合不一致。 |
| missing manifest item | source directory 存在但 manifest 缺少同 identity 项目。 |
| dangling manifest item | manifest identity 没有对应 source directory。 |
| manifest projection mismatch | source 与 manifest 的 identity/provenance/completion exact projection 不一致。 |
| duplicate manifest identity | manifest document identity 重复。 |
| manifest ticker mismatch | manifest ticker 与 transaction ticker 不一致。 |
| blob-only old-absent source | blob 创建了 source directory但没有 meta/manifest，commit失败并保持 published absent。 |

另有 final mutation boundary test：producer 直接提交 false completion 时，在写 final source 之前即 `ValueError("final source ingest_complete 必须为 true")`。

## 6. Commit 顺序与可见性

`commit_batch` 的 authoritative 顺序为：

1. registry 解析 opaque token，lifecycle 进入 `commit_started`；
2. 不持 publication guard，遍历并校验完整 staged ticker tree；
3. validator 成功后才获取独立 `batch_locks/<ticker>.publication.lock`；
4. existing target rename 到 backup，journal 写 `backed_up_target`；
5. staging ticker rename 到 target，journal写 `swapped_target`；
6. journal写 `committed`，释放 publication guard；
7. post-commit cleanup，最后消费 registry state并释放 writer lock。

validator或其 filesystem read 失败走既有 precommit failure path：storage commit owner恢复 old、消费 capability并保留 primary error；caller不得二次 rollback。validator通过后，publication guard仍只覆盖 physical swap与其失败恢复短窗。

## 7. S1 不变量保留证据

- opaque token：public `BatchToken` 仍精确只有 `transaction_id` 与 `ticker`；没有 locator/lock/owner identity；
- authority：active registry + ticker/open/core 校验仍是唯一 mutation authority；ambient authority scan为0；
- locks：全事务 writer mutex 与独立 publication guard 未合并；validator barrier reader test在1秒deadline内读到old；两个 rename barrier 的既有 tests 仍只观察 old/new，不观察 missing；
- journal/recovery：journal仍是 transaction/ticker/phase闭集；无 PID、hostname 或 absolute locator；STARTED complete-source orphan recovery 与 rollback 均不发布 half source；
- read graph：AST public-read self-call scan为 `[]`；outer guard/private unguarded helper与 `LocalFileSource` delayed opener未改变；
- containment/symlink/atomic write、pre/post-commit error precedence、cleanup terminal semantics均由四文件累计 S1/S2 suite继续覆盖；
- logical delete/restore 在同一 batch 中保留 files、primary、typed provenance、true completion并重写同源 manifest，complete source invariant未降级；
- 未实施 R07、Issue 175/177、统一 authorization、revision/snapshot selector或 S3 producer propagation。

## 8. Tests 与 coverage

### 8.1 Plan §7.2 focused command

```text
88 passed, 144 deselected, 3 warnings in 2.70s
```

覆盖：blob-first unpublished、complete commit同源、22格 validator failure、old保留、old-absent/new-source、filing/material manifest、typed provenance、false completion、rollback/precommit recovery、validator barrier reader畅通、online rename barrier、logical delete/restore。

storage owner没有 cancellation input；caller cancellation的唯一合法事务收束是 `rollback_batch`。complete-source rollback case因此同时证明 cancellation rollback 不发布 staging/half source，没有为 cancellation 另造 storage 状态。

### 8.2 四个累计 S1/S2 test files

```text
232 passed, 3 warnings in 9.40s
```

### 8.3 S2实际 changed production逐文件 line coverage

同一四文件完整测试 session，`coverage run --branch --source=dayu.fins` 后按 `covered_lines / num_statements` 逐文件计算；branch综合百分比未冒充line coverage：

| File | Covered / statements | Line coverage |
| --- | ---: | ---: |
| `dayu/fins/domain/document_models.py` | 417 / 434 | 96.08% |
| `dayu/fins/storage/repository_protocols.py` | 59 / 59 | 100.00% |
| `dayu/fins/storage/_fs_storage_infra.py` | 727 / 813 | 89.42% |
| `dayu/fins/storage/_fs_blob_core.py` | 58 / 64 | 90.62% |
| `dayu/fins/storage/_fs_source_document_core.py` | 328 / 397 | 82.62% |
| `dayu/fins/storage/fs_document_blob_repository.py` | 20 / 20 | 100.00% |
| `dayu/fins/storage/fs_source_document_repository.py` | 72 / 77 | 93.51% |

validator每个任务要求的失败格均由真实 `commit_batch` 命中，没有测试直调 validator或复制判断。

## 9. Typing 与 Ruff

### 9.1 Scoped

- 7个S2 production + 4个allowlist tests：`pyright` = `0 errors, 0 warnings, 0 informations`；
- 同一11文件 scoped Ruff：`All checks passed!`；
- changed owner命中 full Ruff：0。

### 9.2 Full pyright预期 residual

全量结果：`108 errors, 0 warnings, 0 informations`，682 files analyzed。全部属于 accepted S3 propagation residual；7个changed owner与4个allowlist tests经scoped检查证明为0。

| Deferred S3 production file | Errors |
| --- | ---: |
| `dayu/fins/ingestion_runtime.py` | 13 |
| `dayu/fins/pipelines/cn_download_company_meta.py` | 1 |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 8 |
| `dayu/fins/pipelines/cn_download_rebuild.py` | 2 |
| `dayu/fins/pipelines/cn_download_source_upsert.py` | 5 |
| `dayu/fins/pipelines/docling_upload_service.py` | 9 |
| `dayu/fins/pipelines/sec_6k_primary_document_repair.py` | 2 |
| `dayu/fins/pipelines/sec_company_meta.py` | 1 |
| `dayu/fins/pipelines/sec_download_filing_workflow.py` | 5 |
| `dayu/fins/pipelines/sec_download_persistence.py` | 4 |
| `dayu/fins/pipelines/sec_download_source_upsert.py` | 3 |
| `dayu/fins/pipelines/sec_download_state.py` | 1 |
| `dayu/fins/pipelines/sec_pipeline.py` | 1 |
| `dayu/fins/pipelines/sec_rebuild_workflow.py` | 2 |
| `dayu/fins/pipelines/upload_company_meta.py` | 1 |
| **Production subtotal** | **58** |

| Deferred S3 test file | Errors |
| --- | ---: |
| `tests/fins/test_cn_download_runtime.py` | 1 |
| `tests/fins/test_cn_download_workflow.py` | 15 |
| `tests/fins/test_cn_pipeline.py` | 1 |
| `tests/fins/test_docling_upload_service.py` | 15 |
| `tests/fins/test_fins_ingestion_runtime.py` | 8 |
| `tests/fins/test_sec_pipeline_download.py` | 1 |
| `tests/fins/test_sec_pipeline_download_stream.py` | 3 |
| `tests/fins/test_sec_pipeline_upload_filing_stream.py` | 2 |
| `tests/tools/test_combined_tools_acceptance.py` | 4 |
| **Tests subtotal** | **50** |

按根因分类：63项 mutation 缺 required `batch`；27项 producer/test fake仍从 Source repository/object/class调用已删除 lifecycle；4项仍引用已删除 `stage_source_document`；12项 callback/override/protocol fake尚未增加required batch；2项测试仍读取旧 `token_id`。合计108，均是S3调用图迁移，不在S2 owner修复边界。

### 9.3 Full Ruff

只读 `ruff check dayu tests utils --output-format json`：160，未高于当前160；规则分布为 E402=66、F401=79、F541=3、F821=1、F841=11；changed owner命中0。

## 10. §8.3 scans 与额外 owner scans

### 10.1 Accepted exact scans

| Scan | Result | Attribution |
| --- | ---: | --- |
| ambient authority | 0 | storage/tests无 ContextVar、task/thread identity、auto-batch第二authority。 |
| storage ack owner | 0 | `dayu/fins/storage` 中 `stage_source_document`、stable fields、ack、false completion残留清零。 |
| aggregate ack/false scan | 35 | 14条deferred S3 producer、15条deferred S3 tests、4条中间checkpoint未更新README叙述、2条allowlist owner test故意注入false并断言拒绝。 |
| lifecycle | 183 | batching wrapper/core与owner tests合法；4个deferred top-level producer仍有16条Source lifecycle调用，精确归入S3；其余为累计owner tests。 |
| mutation | 170 | changed storage + 4个allowlist tests的106条均人工审计为显式`batch=`或core已解析state；其余64条位于S3 producer/tests调用图，其中63条由full pyright精确报缺参。 |
| locator | 128 | infra internal active/recovery state 82，owner tests 46；`owner_pid/hostname`为0，journal payload locator key为0，public token不含locator。 |

S3 ack residual的精确 production paths与命中数：

- `cn_download_filing_workflow.py` 2；
- `sec_download_source_upsert.py` 4；
- `sec_pipeline.py` 2；
- `cn_download_source_upsert.py` 1；
- `docling_upload_service.py` 5。

deferred tests为 `test_docling_upload_service.py` 7与 `test_sec_pipeline_download_stream.py` 8。没有为得到零扫描而越界修改 producer/tests。

### 10.2 Validator/compat/read/docstring scans

- source→manifest与manifest→source：validator同时计算 `source_ids - manifest_ids`、`manifest_ids - source_ids`，owner tests分别命中 missing与dangling；filing/material均使用同一 `from_source_meta` projection；
- false completion：source mutation只存在显式false拒绝与owner强制true；validator复核typed completion true；storage无false staging；
- fallback/compat：对S2 owner扫描 `setdefault(primary/completion)`、`files[0]` primary选择、stable re-entry、compat、fallback为0；
- public read self-call：对全部 `_fs_*_core.py` AST扫描结果 `[]`；
- 中文 docstring AST：累计diff触及的11个production/test文件函数均有中文概览及 `Args/Returns/Raises`，结果 `[]`；
- allowlist：S2 authored production=7、tests=4、本artifact=1；其它dirty paths均为pre-existing cumulative S1/control/review evidence；
- staged diff为空。

## 11. README 决定

已阅读 `dayu/fins/README.md` 的 `Agent更新约束` 与 `tests/README.md` 当前职责。S2仍是同一breaking cutover的累计中间checkpoint：storage contract已经切换，但producer propagation、composition与final repo typing尚待S3；此时改写README会把不可运行的中间态承诺成整个Agent的current contract，也会违反本gate只新增本artifact的明确约束。

因此本 gate 不修改 `dayu/fins/README.md`、`tests/README.md`、根README或 `dayu/README.md`。ack scan中的4条README旧叙述被明确记录为S3/final cumulative README更新输入，不伪报为最终零。

## 12. Residual risk 与 stop boundary

1. full pyright 108与producer/test ack residual意味着整个R06 breaking cutover尚不可运行完成；它们是S3唯一已知传播风险，不是S2 owner缺口；
2. README仍描述pre-cutover acknowledgement，按本gate约束有意保留到S3/final cumulative tree；
3. validator允许source-free transaction，并只排除filing tree中两个既有maintenance-owned entry；新增任何同层非source事实都需要回到正确owner设计，不能用宽松ignore扩展；
4. 本gate没有运行S3 focused/full Fins aggregate，也不声明final R06 green/accepted；
5. 未发现需要新production path、下游fallback、兼容shim、R07 selector或Controller扩域裁决的问题。

## 13. Handoff

R06-S2 implementation 已满足本gate目标与验证要求，保持累计S1/S2 working tree未暂存，停止在S3之前：

`READY_FOR_CONTROLLER_VALIDATION`
