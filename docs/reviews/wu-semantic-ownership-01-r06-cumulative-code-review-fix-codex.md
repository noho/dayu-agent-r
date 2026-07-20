# WU-SEMANTIC-OWNERSHIP-01 R06 cumulative code-review fix / validation

## 1. Gate 身份与结论

- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`。
- 内部 remediation sub-WU：R06 Fins 显式 batch authority 与完整 source publication。
- Gate：R06 cumulative S1+S2+S3 code-review fix；不是新 WU、不是新 feature、不是 R07。
- Controller adjudication：`docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-controller-adjudication.md`。
- 实现基线 / 当前 HEAD：`d048adf7ec1135aaf575384432ebf1137f8a34f2`。
- Branch：`phaseflow/host-issues-control`。
- Controller override：累计 working tree checkpoint；不创建 intermediate/accepted commit。
- 结论：Controller accepted `R06-CR-F01..F04` 均已修复并有直接 owner tests；完整验证通过。
- 下一状态：`READY_FOR_CONTROLLER_REVALIDATION`。

本 gate 开始前完整读取了：

- `AGENTS.md`；
- `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`；
- `docs/fins/design.md`；
- `docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`；
- `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-controller-adjudication.md`；
- `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-ds.md`；
- `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-mimo.md`；
- `docs/reviews/wu-semantic-ownership-01-r06-s3-controller-validation.md`。

## 2. 第一性原理与 semantic owner 判断

四个 accepted finding 都由直接 owner 证据成立，严重性没有被高估：

1. 单个 `transaction.json` 是单 orphan recovery entry 的输入。其 JSON 解析失败属于该 entry 的 malformed evidence，不是其它 token 目录的 recovery failure；因此只有 `_recover_single_batch_dir()` 可以稳定分类并 skip，外层循环应继续。
2. SEC 单文档 rebuild 在 `begin_batch` 后、`commit_batch` 调用前拥有 capability 终结责任。operation、取消与 rollback 双失败的异常优先级只能在该 lifecycle owner 决定；普通业务 failed result 不能掩盖 rollback 不确定性。
3. ingestion 三条 caller-owned mutation path 拥有相同的 pre-commit rollback 语义。已有 `_store_downloaded_document()` 语义正确，另外两条路径必须在同一模块 owner 中复用同一 helper，不能各自复制或跨模块建立框架。
4. publication barrier 测试要证明的是 public reader 在真实 storage publication guard acquire 点被 writer 持有的同一锁阻塞。child 在 repository 构造前发 `ready` 不能证明 reader 已到达该 owner boundary；测试必须把同步 seam 收紧到真实 acquire 调用点。

本 gate 没有重新审议 Controller rejected/deferred finding，也没有用测试 fixture、consumer fallback、loose parsing 或下游补偿改变语义 owner。

## 3. 精确修改

### 3.1 Production

#### `dayu/fins/storage/_fs_storage_infra.py`

- `_recover_single_batch_dir()` 只捕获 `_read_json_object()` 的 `ValueError`。
- 截断 JSON、空文件和非-object 根稳定返回：
  `skip batch transaction=<id> reason=unparseable_journal`。
- malformed token 目录与 journal 原文均保留，外层同轮扫描继续处理后续合法 orphan。
- 没有捕获 `OSError`；真实 filesystem failure 仍向上传播。
- journal 字段闭集、transaction identity、ticker normalize、containment、symlink、phase、writer mutex 与 publication guard 逻辑均未放宽。

#### `dayu/fins/pipelines/sec_rebuild_workflow.py`

- `rebuild_single_local_filing()` 在 batch mutation 区间捕获 `BaseException`。
- commit 前任意 operation/cancellation 只调用一次 `rollback_batch()`。
- rollback 成功：
  - ordinary `Exception` 保持既有 `status=failed / reason_code=rebuild_write_failed` result；
  - `KeyboardInterrupt`、`SystemExit` 与其它非-`Exception` `BaseException` 原 identity 继续传播。
- rollback 也失败：原 operation/cancellation exception 保持主异常 identity；rollback exception 是 `__cause__`；主异常附加稳定 note 前缀
  `rollback_batch failed; recovery evidence retained`；不返回普通 failed result。
- `commit_batch()` 仍在 mutation rollback catch 之外；commit 调用开始后 caller 不二次 rollback。

#### `dayu/fins/ingestion_runtime.py`

- 新增模块级私有 `_rollback_batch_before_commit()`，只供本模块 caller-owned transaction path 复用。
- helper 用 `sys.exception()` 取得当前 operation/cancellation 主异常；rollback 双失败时保留主异常 identity、以 rollback 为 cause，并使用与既有语义相同的稳定 note。
- `_store_downloaded_document()`、`_store_rejected_filing_artifact()`、`_preprocess_one_document()` 三条 path 统一调用该 helper。
- helper 捕获 rollback 的 `BaseException`，因此 rollback 自身为取消类异常时也不会替换已有 operation 主异常。
- 没有建立跨模块 callback/facade/framework，没有改变 batch、source、processed、maintenance public contract。

### 3.2 Direct owner tests

#### `tests/fins/test_fins_storage_atomicity.py`

- `test_unparseable_journal_preserves_evidence_and_later_orphan_recovers` 参数化覆盖截断 JSON（`"{"`）、空文件与非-object（`[]`）。
- 每个 case 同时构造排序更后的合法 orphan，断言 malformed journal 原文/目录保留、合法 orphan 同轮恢复、published old 保持完整。
- F04 child 显式 `build_fs_repository_set()`，再把同一个 set 注入 `FsSourceDocumentRepository`；使用已经持有的 `repository_set.core` patch acquire seam，不从 concrete repository 私有属性反射 core。
- `_PublicationGuardAcquireSignal` 在 public reader 真实调用 `_acquire_publication_guard()` 的位置发送 `publication_acquire_entered`，随后立即进入原 storage blocking acquire。
- parent 收到 acquire-point 信号后，用同一 publication lock 的真实 non-blocking acquire 断言 writer 正持有 guard；删除 `poll(0.25)` 调度时机推断。
- 保留真实 filesystem、spawn 独立 process/core、Event、Pipe、deadline、两个 rename barrier 与最终 complete old/new 断言；无 production debug flag、sleep 或 policy-copy fake。
- 共享 child helper 的长 staging test 同步更新为 acquire-point 消息；它继续证明 writer transaction mutex 不阻塞 published reader。

#### `tests/fins/test_sec_pipeline_download.py`

- 参数化 `KeyboardInterrupt` / `SystemExit`：断言取消 identity 原样传播、cause 缺席、rollback 一次。
- ordinary operation + rollback 双失败：断言 operation identity、rollback cause、稳定 note 与单次 rollback。
- ordinary operation + rollback 成功：断言保留既有 failed result。
- rollback spy 先执行真实 shared-core rollback 再注入次级失败，测试不遗留活动 lock/token。

#### `tests/fins/test_fins_ingestion_runtime.py`

- rejected artifact operation + rollback 双失败 direct owner test。
- preprocess processed-create operation + rollback 双失败 direct owner test。
- 两条测试均断言原 operation exception identity、rollback `__cause__`、稳定 note 与 exactly-once rollback。
- 所有 wrapper 显式消费同一 `_FsRepositorySet`；没有 optional batch、fake authority 或 compatibility shim。

## 4. Accepted finding closure

| Finding | 状态 | Owner closure | 直接证据 |
| --- | --- | --- | --- |
| `R06-CR-F01` | 已修复 | 单 batch recovery entry 对 `ValueError` 稳定 skip/preserve，外层继续；`OSError` 不降级 | 三种 malformed journal + later valid orphan：`3 passed` |
| `R06-CR-F02` | 已修复 | SEC rebuild pre-commit `BaseException` exactly-once rollback；ordinary failed result、取消传播、双失败 cause/note/identity 分流 | cancellation 两 case、双失败、ordinary rollback-success：`4 passed` |
| `R06-CR-F03` | 已修复 | ingestion 模块级 helper 统一三条 caller-owned path；两条缺失 path 保留 operation 主异常 | rejected + preprocess 双失败：`2 passed` |
| `R06-CR-F04` | 已修复 | child 在真实 public reader acquire point 同步；parent 以同一真实 lock contention 证明 guard 正被 writer 持有 | 两个 rename barrier：`2 passed` |

## 5. Validation

所有 Python 命令均在 `source .venv/bin/activate` 后运行。

### 5.1 四组 direct owner tests

| 组 | Exact command | Exit | Result |
| --- | --- | ---: | --- |
| F01 | `python -m pytest -q tests/fins/test_fins_storage_atomicity.py::test_unparseable_journal_preserves_evidence_and_later_orphan_recovers` | 0 | `3 passed in 0.66s` |
| F02 | `python -m pytest -q tests/fins/test_sec_pipeline_download.py::test_sec_rebuild_rolls_back_once_and_reraises_cancellation_identity tests/fins/test_sec_pipeline_download.py::test_sec_rebuild_operation_and_rollback_failure_preserve_primary_exception tests/fins/test_sec_pipeline_download.py::test_sec_rebuild_ordinary_failure_with_successful_rollback_returns_failed_result` | 0 | `4 passed, 3 warnings in 0.72s` |
| F03 | `python -m pytest -q tests/fins/test_fins_ingestion_runtime.py::test_store_rejected_artifact_double_failure_preserves_operation_identity tests/fins/test_fins_ingestion_runtime.py::test_preprocess_double_failure_preserves_operation_identity` | 0 | `2 passed, 3 warnings in 0.79s` |
| F04 | `python -m pytest -q tests/fins/test_fins_storage_atomicity.py::test_concurrent_reader_blocks_at_each_publication_rename_barrier` | 0 | `2 passed in 1.26s` |

三条 warning 均来自 `edgar` 依赖的既有 deprecation warning。

### 5.2 R06 S1/S2/S3/aggregate affected matrix

| Matrix | Exact command | Exit | Result |
| --- | --- | ---: | --- |
| S1 initial | `python -m pytest -q tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py -k 'batch or token or owner or recovery or atomic or concurrent'` | 1 | `1 failed, 136 passed, 64 deselected`；共享 child helper 已改为 acquire-point 消息，长-staging test 仍断言旧 `ready`。只更新同文件旧消息断言。 |
| S1 final | 同上 | 0 | `137 passed, 64 deselected, 3 warnings in 2.93s` |
| S2 | `python -m pytest -q tests/fins/test_fins_storage_provider.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_processor_read_consistency.py tests/fins/test_read_runtime_semantic_ownership_guards.py -k 'source or blob or incomplete or staging or commit or rollback or provenance or primary or manifest'` | 0 | `91 passed, 147 deselected, 3 warnings in 2.45s` |
| S3 | `python -m pytest -q tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_pipeline.py tests/fins/test_docling_upload_service.py tests/fins/test_docling_upload_service_integration.py tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/tools/test_combined_tools_acceptance.py` | 0 | `325 passed, 1 skipped, 3 warnings in 13.00s` |
| Aggregate affected | `python -m pytest -q tests/fins tests/tools/test_combined_tools_acceptance.py` | 0 | `732 passed, 1 skipped, 3 warnings in 21.42s` |

唯一 skip 是既有可选 Docling integration 环境门控。

### 5.3 Coverage

S3 exact matrix 与 aggregate affected matrix 都用：

```text
COVERAGE_FILE=<workspace/tmp file> python -m coverage erase
COVERAGE_FILE=<workspace/tmp file> python -m coverage run --branch --source=dayu -m pytest -q <matrix>
COVERAGE_FILE=<workspace/tmp file> python -m coverage json -o <workspace/tmp json>
```

- S3 coverage matrix：`325 passed, 1 skipped, 3 warnings`，exit 0。
- Aggregate coverage matrix：`732 passed, 1 skipped, 3 warnings`，exit 0。
- JSON：`workspace/tmp/r06-cumulative-fix-coverage.json` 与
  `workspace/tmp/r06-cumulative-fix-aggregate-coverage.json`。
- 门槛按 accepted Controller 口径核对 statement line coverage，即
  `covered_lines / num_statements`；不能用 overall 或 branch-inclusive display 替代。
- 22 个实际 production files 全部 `>=80%`；无 omit、pragma、coverage config 或 mock-only delegation。

| Production file | covered/statements | line coverage |
| --- | ---: | ---: |
| `dayu/fins/downloaders/sec_downloader.py` | 789/864 | 91.31% |
| `dayu/fins/ingestion_runtime.py` | 1535/1693 | 90.66% |
| `dayu/fins/pipelines/cn_download_company_meta.py` | 26/28 | 92.85% |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 191/218 | 87.61% |
| `dayu/fins/pipelines/cn_download_protocols.py` | 40/40 | 100.00% |
| `dayu/fins/pipelines/cn_download_rebuild.py` | 132/164 | 80.48% |
| `dayu/fins/pipelines/cn_download_source_upsert.py` | 73/78 | 93.58% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 195/238 | 81.93% |
| `dayu/fins/pipelines/cn_pipeline.py` | 274/326 | 84.04% |
| `dayu/fins/pipelines/docling_upload_service.py` | 313/372 | 84.13% |
| `dayu/fins/pipelines/sec_6k_primary_document_repair.py` | 148/181 | 81.76% |
| `dayu/fins/pipelines/sec_company_meta.py` | 42/45 | 93.33% |
| `dayu/fins/pipelines/sec_download_filing_workflow.py` | 127/147 | 86.39% |
| `dayu/fins/pipelines/sec_download_persistence.py` | 100/122 | 81.96% |
| `dayu/fins/pipelines/sec_download_source_upsert.py` | 39/39 | 100.00% |
| `dayu/fins/pipelines/sec_download_state.py` | 119/148 | 80.40% |
| `dayu/fins/pipelines/sec_download_workflow.py` | 150/169 | 88.75% |
| `dayu/fins/pipelines/sec_pipeline.py` | 332/379 | 87.59% |
| `dayu/fins/pipelines/sec_rebuild_workflow.py` | 125/138 | 90.57% |
| `dayu/fins/pipelines/sec_upload_workflow.py` | 109/129 | 84.49% |
| `dayu/fins/pipelines/upload_company_meta.py` | 57/61 | 93.44% |
| `dayu/fins/service_runtime.py` | 90/106 | 84.90% |

Aggregate coverage 另证明本轮 storage owner 文件
`dayu/fins/storage/_fs_storage_infra.py` 为 733/817 = **89.71%**。

### 5.4 Pyright / Ruff

| Validation | Exact command | Exit | Result |
| --- | --- | ---: | --- |
| Full pyright | `pyright` | 0 | `0 errors, 0 warnings, 0 informations`；仅有可用新版本提示 |
| Cumulative scoped Ruff | `git diff --name-only d048adf7ec1135aaf575384432ebf1137f8a34f2 -- '*.py' \| xargs .venv/bin/python -m ruff check` | 0 | `All checks passed!` |
| Full Ruff current JSON | `python -m ruff check dayu tests utils --output-format json > workspace/tmp/r06-fix-current-ruff.json` | 1（预期 baseline findings） | 152 项：E402=66、F401=72、F541=3、F821=1、F841=10 |
| Full Ruff base JSON | 在只读 `workspace/tmp/r06-base-9c07b88d` 运行同一命令并输出 `workspace/tmp/r06-fix-base-ruff.json` | 1（预期 baseline findings） | 162 项 |

机器可比 fingerprint 使用相对 path、rule、row、column、message 排序：

- base normalized SHA-256：`94945899fc586cb898354da872ba4e2d9d720920ebc6edfdb8142a4a08c7adaa`；
- current normalized SHA-256：`5671e8ecabff71c05d5b30a557a0297c19014e0193a1cba2351a0c19cdb0ed23`；
- `current-only=0`；
- `base-only=10`；十条精确等于 accepted plan §10 的 changed-owner cleanup ledger；
- current 152 条均逐 path/rule/location/message 匹配 base，无新增、扩散、节点或指纹漂移，且 cumulative changed Python scoped Ruff 为 0。

## 6. Scans 与人工 owner 审计

| Scan | Exact command / boundary | Result |
| --- | --- | --- |
| mutation AST | `python workspace/tmp/r06_s3_ast_scan.py` | production=54、tests=129、`missing_explicit_batch_keyword=0` |
| ambient authority | `rg -n 'ContextVar\|_BATCH_OWNER_CONTEXT\|owner_scope_id\|owner_token\|current_task\|get_ident\|thread.*ident\|_execute_with_auto_batch\|auto_batch' dayu/fins/storage tests/fins` | 0 命中 |
| ack / false completion | plan §8.3 exact ack scan | 2 命中，仅 `test_fins_storage_provider.py:1444` 与 `:3478` 的 storage owner negative tests；production=0 |
| optional/default batch | 对 storage、ingestion、downloader、pipelines 扫描 `BatchToken \| None`、`Optional[BatchToken]`、`BatchToken =`、`batch=None` | 0 命中 |
| lifecycle | `rg -n '\.(begin_batch\|commit_batch\|rollback_batch)\(' dayu/fins tests/fins` | 283；production=76。两条 ingestion path 收敛到同一个 module helper，所以 production textual calls 比 S3 少 2；人工审计仍是同一三个 owner、每个 pre-commit path exactly-once rollback，commit-start fence不变 |
| journal process facts | `rg -n 'owner_pid\|hostname' dayu/fins/storage/_fs_storage_infra.py tests/fins` | 0 命中 |
| journal physical names | plan §8.3 locator scan | 只命中 private `_ActiveBatchState`、recovery owner 与 owner tests；journal payload仍精确 `{transaction_id,ticker,phase}` |
| deferred scope | 对本轮三个 production owner 扫描 `SourceDocumentRevision`、`source_snapshot`、`snapshot_handle`、`bounded_retry`、Issue 142/151/175/177/178、unified authorization、force-release | 0 命中 |
| F04 obsolete proof | `rg -n 'poll\(0\.25\)\|send_bytes\(b"ready"\)\|_repository_set\.core' tests/fins/test_fins_storage_atomicity.py` | 0 命中 |

人工审计确认：

- `BatchToken` public shape/validation 完全未改；
- `_PHASE_SWAPPED_TARGET` commit point/recovery 完全未改；
- publication lock release/force-release 完全未改；
- processed/company/maintenance validator 与既有 read contract 完全未改；
- composition defaults 与四个 production shared-core root 完全未改；
- R07 revision/snapshot/opaque-id/retry/cache contract 未进入；
- Issue 142/151/175/177/178、统一 authorization 未进入；
- containment、ticker、symlink、atomic write/fsync、writer/recovery/publication lock order 未放宽。

## 7. README trigger audit

修复前已读取 `dayu/fins/README.md` 的 `Agent更新约束【必须遵守】` 与
`tests/README.md` 的职责说明。

- `dayu/fins/README.md` 已陈述：batching-only lifecycle、commit 前失败/取消 exactly-once rollback、commit-start 后不二次 rollback、publication guard 与 crash recovery owner。F01-F03 是这些已公开 current contract 的错误分支修复，没有新增 public capability、schema、用户流程或稳定架构边界；不追加 review/finding 实现细节。
- `tests/README.md` 已陈述：commit/rollback fence、两个 rename window、fresh recovery 与完整 old/new 测试职责。F01/F04 只增强同一测试层的 owner case 与同步证明，不形成新测试层级；不写 gate 过程。
- 根 `README.md`：无安装、CLI、输出、workspace、用户流程或排障变化。
- `dayu/README.md`：无 `UI -> Service -> Host -> Engine` 分层/装配变化。
- `docs/fins/design.md`：stable owner 决策未变。

因此本 gate **无新增 README/design diff**。累计 working tree 中既有
`dayu/fins/README.md`、`tests/README.md` 与 control doc 修改属于此前 R06 checkpoint；本 gate 未编辑这些文件，也未编辑任何 Controller/reviewer/既有 implementation/validation/control artifact。

## 8. Scope、风险与未覆盖项

本 gate 新增/修改只涉及 Controller allowlist：

- production：
  - `dayu/fins/storage/_fs_storage_infra.py`；
  - `dayu/fins/pipelines/sec_rebuild_workflow.py`；
  - `dayu/fins/ingestion_runtime.py`。
- tests：
  - `tests/fins/test_fins_storage_atomicity.py`；
  - `tests/fins/test_sec_pipeline_download.py`；
  - `tests/fins/test_fins_ingestion_runtime.py`。
- 本 artifact。

已分类 residual：

- R06-CR-F01..F04 correctness residual：无。
- R07 独占的跨多 repository call / processor lifetime snapshot、revision、opaque ID mapping、bounded retry/cache contract：保持 deferred，未修改。
- Issue 142/151/175/177/178：保持原 owner，未修改。
- publication lock release syscall 失败的 retained operational residual：仍由 `dayu.runtime.filelock` / process termination owner承担；未实施 Controller rejected force-release。
- full Ruff 152 条：精确复现 accepted base fingerprint且不命中 cumulative changed owner；不是本 gate 新增风险。
- 唯一 test skip 与三条 warning：既有可选 Docling environment gate及 `edgar` deprecation warning。

## 9. Final workspace state

- `git diff --name-only d048adf7ec1135aaf575384432ebf1137f8a34f2 --`：累计 57 个 tracked paths，保持 R06 cumulative checkpoint。
- `git diff --check`：exit 0；artifact trailing-whitespace scan 0 命中。
- staged paths：0。
- 未 commit、未 push、未创建/修改 PR。
- scope/status 复核确认本 gate 只新增/修改 §8 列出的六个 allowlist 文件与本 artifact；其它 dirty/untracked paths 都是此前累计 R06 checkpoint，未被本 gate 清理、覆盖或重写。

## READY_FOR_CONTROLLER_REVALIDATION
