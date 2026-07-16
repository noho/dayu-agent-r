# WU-SEMANTIC-OWNERSHIP-01 R06-S1 implementation checkpoint

## 1. Checkpoint identity 与范围

- Work unit：`WU-SEMANTIC-OWNERSHIP-01` / R06 / S1 storage explicit transaction protocol/core cumulative checkpoint。
- Accepted plan commit：`0d802220fd1ca4ec67addc85915df27becc9b594`。
- Implementation entry HEAD：`d048adf7ec1135aaf575384432ebf1137f8a34f2`。
- 实施依据仅为 accepted plan §3、§4、§7.0、§7.1、§8、§10、§11，以及 plan re-review Controller adjudication。
- 本实现只修改 §7.1 允许的 production/test 文件，并新增/更新 Codex implementation artifacts；Controller 另行修改的 control 与新增 validation artifact 保持原样。本实现未修改 design、README、Controller artifact 或其它 review artifact，未 stage、commit、push 或创建 PR。
- 这是 S1 累计 working-tree checkpoint，不宣称 R06 complete；S2 complete-source validator/blob-first/ack 删除与 S3 producer/callback/composition propagation 均未实施。

## 2. Root cause 与第一性原理判断

问题真实且严重性成立。入口实现把一个 transaction 的至少四类事实同时暴露或分散到 public token、ambient execution context、Source wrapper 与 filesystem core：

1. 旧 `BatchToken` 暴露 `owner_token`、`owner_scope_id`、九个物理 locator/时间类字段，public capability 因而同时承诺调用执行身份和内部目录布局。
2. `_BATCH_OWNER_CONTEXT`、`asyncio.current_task()`、thread ident 与 `_execute_with_auto_batch()` 让 mutation authority 可由环境推断或自动创建，不再由调用点显式提供。
3. batch lifecycle 同时出现在 batching repository 与 Source protocol/wrapper；physical writer mutex 又容易被误当作 business mutation authority。
4. published read 在 public 方法间组合调用时重复获取锁；若用 ambient “已持锁”标记规避，会重新引入隐式 authority，并形成 publication-to-writer 的反向顺序风险。

这些不是测试表象，而是 owner 数据同源问题：transaction identity、open/lifecycle、ticker scope、core binding、物理 locator 与 lock token 必须由 storage internal registry/state 唯一产生、校验、持久化和消费；public token 只能是 opaque capability。修复因此落在 storage owner boundary 与其 public protocol，而没有在 producer、fixture 或 adapter 加 optional/default/compatibility 分支。

## 3. S1 owner contract

### 3.1 Public capability 与 internal state

- Public `BatchToken` 是 frozen value，字段严格为 `transaction_id: str` 与 `ticker: str`。
- `_ActiveBatchState` 是 open transaction 的内部唯一 owner，持有 canonical token、`lifecycle`、writer lock token、target/staging/backup/journal locator 与 phase。
- `_active_batches[transaction_id]` 与 `_active_transaction_by_ticker[ticker]` 是唯一 active registry/index。每个 mutation 先通过 registry 解析 canonical value、core binding、ticker scope 与 `open` lifecycle；伪造、篡改、跨 core、跨 ticker 和 terminal token 均 fail closed。
- public token 不承诺物理布局。owner tests 的 `_active_batch_paths(core)` 只从 storage-owned 唯一 `_ActiveBatchState` 取得 failure-injection 路径；fixture 不再用 `batch.transaction_id` 推导 `repo_batches/<id>`、backup 名称或其它 locator。

### 3.2 Protocol 与 mutation authority

- lifecycle 只保留在 `BatchingRepositoryProtocol` / `FsBatchingRepository`。
- `SourceDocumentRepositoryProtocol` / `FsSourceDocumentRepository` 删除 `begin_batch`、`commit_batch`、`rollback_batch`。
- company、blob、maintenance、processed、source 的所有 public business mutation 均要求 keyword-only `batch: BatchToken`，没有 optional/default/compat shim。
- wrapper 显式转发 `batch=`；各 core 立即 resolve 为 `_ActiveBatchState`，内部 mutation helper 只接收 state。
- `_execute_with_auto_batch`、`ContextVar`、bind/unbind/require owner、task/thread identity inference 与所有 ambient authority 已删除。
- per-ticker writer file lock 从 `begin_batch` 持有至 commit/rollback/异常终态，但它只排斥并发 writer；mutation authorization 只来自 registry resolve。

### 3.3 Journal 与 recovery

- journal payload 精确为 `transaction_id`、`ticker`、`phase` 三个字段；不存在 owner pid、hostname 或物理 locator。
- recovery 从受控 root 与严格 journal 重新派生物理路径，校验 exact fields、字符串类型、ticker normalize、phase allowlist、symlink 拒绝与 root containment。
- phase 保留 `started`、`backed_up_target`、`swapped_target`、`committed`、`rolled_back`，继续覆盖 crash recovery；journal/目录更新仍走 atomic JSON、rename 与 parent-directory fsync。
- successful commit 进入 cleanup 后，无论 cleanup 正常、`OSError` 被记录并保留恢复证据，还是 helper 抛出其它异常，`finally` 都消费 token、移除两个 registry index 并释放 writer lock。owner test 证明异常不会遗留 active state，且同 ticker 可立即重新 `begin_batch`。
- journal 已进入 `COMMITTED` 后 publication guard release 失败时，durable tree 绝不回滚，但 API 不静默成功：该 release exception 成为 post-commit primary；cleanup 与 writer release 仍尝试，其失败按发生顺序附着，registry/capability 仍终态消费。

## 4. Publication guard 与锁序

独立跨进程 guard 位于 `batch_locks/<normalized-ticker>.publication.lock`；它与 writer 的 `batch_locks/<normalized-ticker>.lock` 是两个不同锁文件。

锁序和持有窗口如下：

1. 普通 published read：只获取 publication guard；outer public entry 获取一次，内部组合只调用 private unguarded helper。
2. `LocalFileSource`：typed delayed opener 获取 publication guard，`open(path, "rb")` 成功或失败后都立即释放；后续流读取不持 guard。
3. 正常 writer：`begin_batch` 获取 writer mutex并跨整个 transaction 持有；staging mutation 与长 validator 窗口不取 publication guard。
4. commit：已持 writer，只有 target→backup、staging→target、journal phase 与失败 restore 的物理 swap/restore 短窗获取 publication guard；释放 publication guard 后才做长 cleanup，最后释放 writer。
5. rollback：已持 writer，只清理未发布 staging，不取 publication guard，最后释放 writer。
6. recovery：`global recovery -> per-ticker writer -> publication`；publication 只覆盖 published tree inspect/move/restore，随后先释放 publication，再清理证据、释放 writer 和 global recovery。

不存在 `publication -> writer` 路径，不存在 ambient “guard held” 标志，也不存在 nested public read 再入锁。

## 5. Public read 调用图审计

所有默认 read 只观察 published tree。下列是完整 public-to-private 组合图；箭头右侧 helper 不获取 publication guard：

### 5.1 Company

- `get_company_meta -> _get_company_meta_unguarded`。
- `scan_company_meta_inventory` 对每个 published ticker outer-guard 一次并直接解析，不调用另一个 public read。
- `resolve_existing_ticker` direct candidate 对各 ticker outer-guard；alias 分支为 `_resolve_existing_ticker_by_company_alias -> _build_company_alias_index -> _scan_company_meta_by_ticker`，每个 ticker 只在 owner entry 获取一次。
- `_published_ticker_directory_names` 合并 published directories 与持久 publication-lock ticker 名，避免 rename gap 暂时把 ticker 从 inventory 漏掉。

### 5.2 Blob

- `list_entries -> _list_entries_unguarded`。
- `read_file_bytes -> _read_file_bytes_unguarded`。
- `list_files -> _list_files_unguarded -> infra._list_handle_files_unguarded`。

### 5.3 Processed

- `get_processed_handle -> _get_processed_handle_unguarded`。
- `get_processed_meta -> _get_processed_meta_unguarded`。
- wrapper `list_processed_documents -> core.list_documents -> _list_documents_unguarded`，整个组合只取一次 publication guard。

### 5.4 Maintenance

- `load_download_rejection_registry -> _load_download_rejection_registry_unguarded`。
- `get_rejected_filing_artifact -> _get_rejected_filing_artifact_unguarded`。
- `list_rejected_filing_artifacts` 在一个 guard 内枚举并调用 private get helper。
- `read_rejected_filing_file_bytes` 在一个 outer guard 内完成路径解析与读取。

### 5.5 Source

- `get_document_meta -> _get_document_meta_unguarded`。
- `get_source_meta -> _get_source_meta_unguarded`。
- `get_source_revision` 在一个 guard 内读取 private meta 后投影。
- `get_source_document_provenance` 使用调用方已给 meta，或在同一个 guard 内读取 private meta，再投影 provenance。
- `list_documents -> _list_documents_unguarded`；`list_document_ids -> _list_document_ids_unguarded`。
- `has_source_storage_root` 在一个 guard 内直接检查 published root。
- `has_filing_xbrl_instance -> _has_filing_xbrl_instance_unguarded`，仅检查 published。
- `has_staged_filing_xbrl_instance(..., *, batch)` 是 accepted contract 的唯一显式 staged XBRL read：先 resolve active state，再检查该 transaction staging；它不伪装成 published read。
- `get_source_handle -> _get_source_handle_unguarded`。
- `get_primary_file -> _get_primary_file_unguarded`。
- `get_source -> _get_source_unguarded`。
- `get_source_by_filename` 在一个 guard 内使用 infra private file-list helper，再调用 private source helper。
- `get_primary_source` 在一个 guard 内串联 private handle、primary-file 与 source helper。
- wrapper `get_primary_file` 只构造 identity handle 后调用一个 core public read；wrapper `get_source` 只调用一次 `get_source_by_filename`，不再形成 public-to-public read 链。

审计 `dayu/fins/storage/_fs_*_core.py` 后，没有 core 的 public read 调用另一个 public read。并发真实进程测试证明长 staging writer 不阻塞 published reader；swap 两个 rename barrier 都证明 reader 在物理切换短窗阻塞，随后只看到完整新版本。

## 6. 精确 diff

### 6.1 Production（15 个实际修改；2 个 allowlist 文件无需修改）

| 文件 | `+/-` | S1 语义变更 |
| --- | ---: | --- |
| `dayu/fins/domain/document_models.py` | `+3/-22` | `BatchToken` 收窄为 `transaction_id+ticker`。 |
| `dayu/fins/storage/repository_protocols.py` | `+681/-89` | lifecycle 归一到 batching；mutation required `batch`；新增 explicit staged XBRL read；补齐 touched contract 与 post-commit error 语义。 |
| `dayu/fins/storage/_fs_storage_infra.py` | `+717/-466` | internal registry/state、writer/publication/recovery 锁序、minimal journal、guarded opener、published/private read infra；validation recovery/terminal error-precedence 修复。 |
| `dayu/fins/storage/_fs_blob_core.py` | `+109/-30` | mutation state resolve、published outer/private read helper 与 touched contract docstring。 |
| `dayu/fins/storage/_fs_company_meta_core.py` | `+108/-116` | state mutation、per-ticker published reads、alias/inventory private graph 与 touched contract docstring。 |
| `dayu/fins/storage/_fs_maintenance_core.py` | `+148/-57` | state mutation、maintenance read private graph 与 touched contract docstring。 |
| `dayu/fins/storage/_fs_processed_core.py` | `+136/-52` | state mutation、processed published/private reads 与 touched contract docstring。 |
| `dayu/fins/storage/_fs_source_document_core.py` | `+517/-117` | state mutation、完整 source public read graph、published/staged XBRL split、guarded source opener与 touched contract docstring。 |
| `dayu/fins/storage/fs_batching_repository.py` | `+61/-8` | lifecycle 仅此 wrapper 暴露并转发 opaque token；补齐 lifecycle/post-commit contract docstring。 |
| `dayu/fins/storage/fs_company_meta_repository.py` | `+55/-7` | required keyword-only batch 显式转发；补齐 mutation/read contract docstring。 |
| `dayu/fins/storage/fs_document_blob_repository.py` | `+94/-8` | required keyword-only batch 显式转发；补齐 mutation/read contract docstring。 |
| `dayu/fins/storage/fs_filing_maintenance_repository.py` | `+148/-13` | required keyword-only batch 显式转发；补齐 mutation/read contract docstring。 |
| `dayu/fins/storage/fs_processed_document_repository.py` | `+136/-20` | required keyword-only batch、read wrapper 收口与 touched contract docstring。 |
| `dayu/fins/storage/fs_source_document_repository.py` | `+318/-107` | 删除 Source lifecycle；required batch；read wrapper 去 public nesting；explicit staged XBRL；补齐 touched contract docstring。 |
| `dayu/fins/storage/local_file_source.py` | `+45/-3` | 窄 typed delayed binary opener，fd open 后释放 publication guard；补齐 opener contract docstring。 |

§7.1 允许但未产生 diff 的 production 文件：`dayu/fins/storage/_fs_storage_core.py`、`dayu/fins/storage/_fs_repository_factory.py`。现有共享 core/factory 已能承载上述 owner contract，无需制造空洞 churn。

### 6.2 Tests（4 个实际修改）

| 文件 | `+/-` | Owner-level coverage |
| --- | ---: | --- |
| `tests/fins/test_fins_storage_atomicity.py` | `+1554/-177` | opaque token/registry、physical lock 非 authority、journal/recovery、安全 containment、cleanup terminal、真实进程 published barriers、read composition、delayed opener、staged XBRL、invalid recovery evidence 与 pre/post-commit terminal error precedence。 |
| `tests/fins/test_fins_storage_provider.py` | `+346/-92` | shared-core explicit batch、child task/thread 显式 capability、provider owner contract；没有 fake token/ambient fallback。 |
| `tests/fins/test_processor_read_consistency.py` | `+36/-13` | fixture 使用同一真实 batching core 显式包裹 mutation。 |
| `tests/fins/test_read_runtime_semantic_ownership_guards.py` | `+18/-1` | semantic guard fixture 迁移到 shared-core explicit batch。 |

production + tests 合计（写本 artifact 前）：19 files，`+5230/-1398`。

## 7. Tests 与 coverage

### 7.1 Focused / authorized matrix

- Plan §7.1 exact focused：
  - `.venv/bin/python -m pytest -q tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py -k 'batch or token or owner or recovery or atomic or concurrent'`
  - 结果：`108 passed, 61 deselected, 3 warnings in 3.23s`。
- 四个 S1 allowlist test 文件完整运行并在同一 coverage session 收集：`206 passed, 3 warnings in 10.16s`。
- warnings 均来自第三方 `edgar` deprecated module import，不是本 diff 新增行为或失败。

关键 owner 场景包括：

- public token exact fields 与 minimal journal exact fields；unknown/altered/cross-core/cross-ticker/closed capability 拒绝。
- child task、child thread 在显式传 token 时成功，证明执行身份不是 authority。
- 持有/伪造物理 writer lock 不能授权 mutation。
- post-commit `OSError` cleanup 保留恢复证据但不伪装 commit failure；任意 cleanup helper exception 仍消费 token、释放 registry/writer。
- fresh filesystem crash phases、orphan backup、invalid/extra journal fields、symlink transaction 与 containment。
- malformed journal ticker 与 malformed orphan-backup ticker 都在 recovery input-validation owner 内 fail closed：保留 evidence、记录 skip/preserve 并继续恢复同轮后续合法 orphan；backup 用例用跨平台单路径组件 `...bak.000-invalid-backup`，parser 精确得到必被拒绝的 ticker `..`。
- commit pre-commit primary error 与 rollback journal primary error 遇到 writer-token release failure 时，registry/capability 仍终态消费，secondary release failure 只作为 note/diagnostic 保留，不覆盖原始异常对象。
- ``COMMITTED`` 后 publication guard release failure 作为 post-commit primary 原对象抛出，不触发 pre-commit rollback；即使随后 cleanup/writer release 同时失败，也只按发生顺序附着 secondary notes，新 published tree 与 durable commit truth 保持。
- 长 writer staging 与独立进程 published reader 并行；target→backup、staging→target 两个 real rename barrier 均在线阻塞 reader，释放后观察完整新树。
- composed read 无自死锁；delayed opener 的 fd open 成功/失败都释放 guard；explicit staged XBRL 与默认 published absence 分离。

### 7.2 Changed production file line coverage

coverage JSON：`/tmp/dayu-r06-s1-vf-coverage.json`，branch coverage 未启用；逐文件 line coverage 如下：

| 文件 | covered/statements | coverage |
| --- | ---: | ---: |
| `document_models.py` | `384/399` | `96%` |
| `repository_protocols.py` | `60/60` | `100%` |
| `_fs_storage_infra.py` | `576/650` | `89%` |
| `_fs_blob_core.py` | `54/58` | `93%` |
| `_fs_company_meta_core.py` | `115/119` | `97%` |
| `_fs_maintenance_core.py` | `133/145` | `92%` |
| `_fs_processed_core.py` | `110/117` | `94%` |
| `_fs_source_document_core.py` | `378/460` | `82%` |
| `fs_batching_repository.py` | `17/18` | `94%` |
| `fs_company_meta_repository.py` | `18/18` | `100%` |
| `fs_document_blob_repository.py` | `20/20` | `100%` |
| `fs_filing_maintenance_repository.py` | `29/29` | `100%` |
| `fs_processed_document_repository.py` | `26/26` | `100%` |
| `fs_source_document_repository.py` | `71/79` | `90%` |
| `local_file_source.py` | `20/20` | `100%` |

全部实际 changed production files 均达到 `>=80%`；最低为 source core `82%`，infra `89%`。覆盖来自 public owner behavior、真实 filesystem/lock 与 failure injection，没有 pragma/omit，也没有通过 public token 反推布局。

## 8. Static validation

### 8.1 Pyright

- Scoped changed 15 production + 4 test files：`0 errors, 0 warnings, 0 informations`。
- 全仓 `.venv/bin/pyright`：`110 errors, 0 warnings, 0 informations`。
- 110 项均位于未修改、且 S1 明确禁止迁移的 S2/S3 consumer/producer/test-double：
  - mutation 调用缺 required `batch`；
  - producer 仍从 `SourceDocumentRepositoryProtocol` 调 lifecycle；
  - callback/subclass override 尚未加入 explicit batch；
  - 尚未迁移的 tests 仍访问旧 `token_id` 或构造旧型 fake owner。
- changed owner 与四个允许 test 文件没有 pyright error。未添加 optional/default、compat shim、`type: ignore`、cast 或 fake token；这 110 项不登记为 baseline，必须由 S3 propagation 在累计 tree 消除。

### 8.2 Ruff

- Scoped changed Python files：`All checks passed!`。
- 只读全量 `.venv/bin/python -m ruff check dayu tests utils`：`Found 160 errors`。
- accepted entry baseline 为 162；没有新增/扩散或 changed-owner 命中。减少两项来自 touched `_fs_processed_core.py` 的旧 `Optional` unused import 与 `_fs_source_document_core.py` 的旧 `Any` unused import，在必要签名重写时一并移除；没有借 R06 清理其它模块。

## 9. Source scans 与 allowlist 判定

按 plan §8.3 执行五条精确 `rg`：

1. ambient authority scan：0 命中。`ContextVar`、owner context/scope/token、task/thread inference、auto batch 均从 storage 与 S1 tests 删除。
2. S2 ack scan：59 命中。命中属于本 S1 明确保留的 `stage_source_document`、`_STAGING_STABLE_META_FIELDS`、`ingest_complete=False` ack 业务，以及未修改 producers/tests/README；这些只能在 S2/S3 按 accepted sequencing 删除或迁移。本 checkpoint 不把 final-R06 零命中 gate 伪报为通过。
3. lifecycle scan：168 命中。较初始 checkpoint 增加项来自 VF-03/VF-04 owner tests 对 commit/rollback terminal path 与 consumed-token retry 的显式调用；changed storage 中 lifecycle 定义/转发只在 `repository_protocols.py::BatchingRepositoryProtocol`、`fs_batching_repository.py` 与 infra internal core。其余命中是 S3 尚未迁移的 top-level producers/tests，并与全仓 pyright attribution一致。
4. mutation propagation scan：165 命中。changed wrapper/core 与四个 allowlist tests 已逐调用审计并显式 `batch=`；scoped pyright 0 是类型证明。其余缺参命中属于 S3 producer/callback propagation，未用 regex 零命中掩盖。
5. locator scan：118 命中。增加项来自 VF owner tests 对 storage-owned recovery evidence 的内部断言；物理字段只存在 `_ActiveBatchState`、storage recovery/path helper 与 owner-core failure-injection tests。public `BatchToken` 与 journal payload 均无 locator。test helper 从 storage-owned active state 或 filesystem/journal 事实读取 locator，不从 token 值反推 staging/backup 布局。

另外执行 public read source audit：core 中没有 `self.<public-read>(...)` 的 public-to-public read 调用；所有组合链已列在 §5。

allowlist 与 whitespace：

- 本实现 authored paths 精确为 15 个允许 production + 4 个允许 tests + 2 个 Codex artifacts；Controller 自有 `docs/host/issues-implementation-control.md` 与 `docs/reviews/wu-semantic-ownership-01-r06-s1-controller-validation.md` 单独识别并保持原样。无其它路径。
- `git diff --check`：pass，无输出。
- 两个 untracked Codex artifacts 的 `git diff --no-index --check` 均无 whitespace error；staged diff 为空，HEAD 仍为 entry commit。

## 10. README decision

未修改 README，理由不是遗漏：

- `dayu/fins/README.md` 当前描述旧 Source lifecycle 与 source acknowledgement；S1 是 required-signature/core checkpoint，S2 ack cutover 与 S3 producers/composition 尚未发生。
- 此时把 README 写成最终 explicit-transaction truth 会与实际未迁移 producers 冲突；保留旧描述又不能准确表达累计中间树。
- 用户与 S1 allowlist 明确禁止修改 README。应在 S3/final cumulative tree 中，待 ack 删除、producer propagation 与 shared composition 同源完成后一次更新 `dayu/fins/README.md` 与 `tests/README.md`，避免文档承诺半迁移 contract。
- 根 README、`dayu/README.md` 不触发：S1 不改变用户安装/CLI workflow，也不改变 UI→Service→Host→Engine 分层。

## 11. 安全保留

- ticker/document/entry normalize、local URI 与 root containment 保持 fail closed。
- symlink transaction/journal 拒绝，recovery 不跟随越界 locator。
- atomic JSON、file-store atomic replace、directory fsync 与 rename crash ordering 保留。
- commit primary error/rollback cause 关系与 recovery evidence 保留；cleanup 不改变已发布 commit 事实。
- readers 只见 published old/new 完整版本；writer mutex 与 publication guard 独立。
- `LocalFileSource` 只把 publication guard 持到 fd open，不把长内容消费置于锁内。
- S2 staging/ack 业务原样保留，只做 required explicit batch 所需的最小签名/owner state 迁移。

## 12. Controller validation-fix follow-up

Controller validation 的 R06-S1-VF-01..04 已在同一 owner boundary 闭合：

1. **VF-01 recovery input validation**：`_recover_single_batch_dir` 只捕获不可信 journal ticker 的 `ValueError`，保留 batch evidence、记录 `skip ... reason=invalid_journal_ticker` 并返回；`_recover_orphan_backup_dirs` 只捕获目录名 ticker normalization 的 `ValueError`，保留目录、记录 `preserve ... reason=invalid_backup_ticker` 并继续扫描。没有放宽 normalizer，也没有吞掉无关 filesystem I/O error。owner tests 同轮布置 invalid evidence 与后续合法 orphan，证明 protected published tree 未触碰、invalid evidence 未删除且合法 orphan 仍恢复。backup malformed case 使用所有平台可创建的 `...bak.000-invalid-backup` 单路径组件，由 parser 产生 ticker `..`，不依赖反斜杠语义。
2. **VF-02 touched contract docstrings**：审计 15 个 changed production files 中本次新增或修改签名/行为的函数与方法，并补齐中文概览、`Args`、`Returns`、`Raises`。AST 审计结果为 `missing_sections=[]`、`missing_batch_contract=[]`；required batch、published/staged read、lifecycle terminal/exception 与 publication guard 异常均在 owner contract 中显式说明。没有机械修改 allowlist 外函数或文件。
3. **VF-03 terminal error precedence**：`_close_active_batch` 在尝试 writer release 前先把 lifecycle 置为 closed 并移除 transaction/ticker registry；有更早 authoritative operation error 时，writer release failure 通过 exception note 与 warning diagnostic 保留，不能替换原异常对象；没有更早主异常时 release failure 按 contract 抛出。commit pre-commit primary failure 与 rollback journal primary failure 的双重 failure-injection tests 均断言原异常 identity、secondary note 与 registry/capability consumption。
4. **VF-04 committed publication-release outcome**：commit state machine 将 post-commit error 与 pre-commit `commit_error` 分离。journal 已进入 ``COMMITTED`` 后，publication guard release failure 成为 post-commit primary，不调用 `_rollback_precommit_batch`；cleanup failure 先附着，registry/capability 终态消费后仍尝试 writer release并附着其 failure，最终抛出同一个 publication release error object。owner test 同时注入 publication/cleanup/writer 三类 failure，证明新 published tree 保持、phase 仍为 ``COMMITTED``、token 终态且 rollback 未调用。

独立 validation-fix 证据见 `docs/reviews/wu-semantic-ownership-01-r06-s1-validation-fix-codex.md`。

## 13. Residual、stop condition 与 handoff

当前 residual 全部属于 accepted sequencing，而非 S1 内 fallback：

- S2：complete-source validator、blob-first/complete-source 业务 cutover、删除 staging ack/incomplete contract；本 checkpoint 未提前实施。
- S3：所有 ingestion/download/upload producer、callback、subclass/test-double 与 repository composition 迁移到独立 `BatchingRepositoryProtocol` 并显式传播 batch；当前全仓 110 个 pyright error 是其机器可见清单之一。
- R07：revision/snapshot/opaque-id/materialization 等后续设计；本 checkpoint 未进入。

S1 implementation 与 validation-fix stop conditions 已满足：owner contract、locks、read graph、cleanup terminal、recovery fail-closed continuation、pre/post-commit terminal error precedence、touched doc contract、focused tests、逐文件 coverage、scoped Ruff/pyright、diff-check 与 allowlist 均闭合。final-R06 条件未满足且没有被伪报：ack/producer scans 与全仓 pyright 必须在后续 cumulative slices 清零。

本实现停在未暂存 working-tree checkpoint，等待 Controller 对 R06-S1 validation-fix 复验；不继续 S2/S3，不 stage/commit/push/PR。
