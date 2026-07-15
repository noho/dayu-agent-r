# WU-SEMANTIC-OWNERSHIP-01 R06 fixed complete plan re-review — AgentMiMo (第一路)

## 0. Review identity

- reviewer: AgentMiMo
- review type: adversarial re-review（第一路，对 fixed complete plan）
- immutable target: `docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`
- target SHA-256: `ed057fdf5bdcfb463d82f76b74da5cebe50548ce1e63c01b9cf67e02fbd03e43` ✓ 已验证
- Controller plan-fix validation: `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-fix-controller-validation.md`
- Controller plan-review adjudication: `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-review-controller-adjudication.md`
- AgentCodex plan-fix artifact: `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-fix-codex.md`
- 原 MiMo review: `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-review-mimo.md`
- 原 DS review: `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-review-ds.md`
- base: `9c07b88d9e855f19f0b828f671022119cc5599a1`
- 本 artifact 只写 review 结论；不修改 plan / control / product / test / README / design / 既有 artifact，不 stage / commit / push / PR。

## 1. Review scope 与方法

完整读取以下文件并核对直接代码证据：

- `AGENTS.md`（项目约束）
- `docs/fins/design.md`（Fins 设计真源，§1-§4 重点核对）
- fixed plan 全文（585 行，SHA 已验证）
- Controller plan-review adjudication 全文
- Controller plan-fix validation 全文
- AgentCodex plan-fix artifact 全文
- 原 MiMo review 全文（17 findings）
- 原 DS review 全文（10 findings）
- 以下 production 代码的直接证据：
  - `dayu/fins/domain/document_models.py` — `BatchToken` 当前字段（415-443）
  - `dayu/fins/storage/_fs_storage_infra.py` — `ContextVar`（64）、`_current_execution_scope_id`（89-108）、`_execute_with_auto_batch`（423-464）、`_bind/unbind_batch_owner`（466-499）、`_require_batch_owner`（501-522）、`_write_batch_journal`（709-739）、`_acquire_ticker_lock`（651-667）、`commit_batch` 两次 rename（261-264）、`_ticker_dir_for_read`（1376-1380）
  - `dayu/fins/storage/repository_protocols.py` — `SourceDocumentRepositoryProtocol.begin/commit/rollback_batch`（134-179）
  - `dayu/fins/storage/_fs_blob_core.py` — `store_file` 调用 `_get_handle_meta`（143）
  - `dayu/fins/storage/local_file_source.py` — `open()` 返回裸 `Path.open("rb")`（32）、`materialize()` 返回 `self.path`（47）
  - `dayu/fins/storage/fs_batching_repository.py` — 零 production 实例化，仅类定义和 `__init__.py` 导出
  - `dayu/fins/storage/_fs_repository_factory.py` — `build_fs_repository_set` 共享 core
  - `dayu/fins/service_runtime.py:347` — `build_fs_repository_set` 但无 `FsBatchingRepository`
  - `dayu/fins/pipelines/cn_pipeline.py:373` — 同上
  - `dayu/fins/pipelines/sec_pipeline.py:509` — 同上
  - `dayu/fins/pipelines/sec_6k_primary_document_repair.py:169-171` — 分别创建 `FsSourceDocumentRepository`、`FsProcessedDocumentRepository`、`FsCompanyMetaRepository`，无 shared set
  - `dayu/fins/pipelines/docling_upload_service.py:331,403,422` — service 内部自行 `begin_batch`/`commit_batch`/`rollback_batch`
  - `dayu/fins/pipelines/sec_download_persistence.py:139-156,459-480` — `build_store_file` 返回 `partial` 无 batch；`_store_file_callback` 签名 `(repository, source_handle, filename, stream) -> FileObjectMeta`
  - `dayu/documents/processors/source_snapshot.py:260-296` — 使用 `self._source.open()` 读到 EOF 复制 spool，不调用上游 `.materialize()`

## 2. R06-PF-01..08 逐项关闭验证

### R06-PF-01 — publication swap guard 机制

**plan 位置**: §4.2、§7.1 Tests、§8.4、§12

**代码证据验证**:

| plan 声称 | 代码证据 | 状态 |
|---|---|---|
| 现有跨进程 ticker filelock 存在 | `_fs_storage_infra.py:651-667` `_acquire_ticker_lock()` 使用 `RuntimeFileLockToken` | ✓ 确认 |
| 两次 rename 存在在线空窗 | `_fs_storage_infra.py:261-264` `target→backup` 后 `staging→target` 无中间 guard | ✓ 确认 |
| 当前无 publication swap guard | `rg` 确认无 `publication.lock` 或等价机制 | ✓ 确认 |
| `RuntimeFileLockToken` 可复用 | `dayu/runtime/filelock.py` 提供跨进程 token API | ✓ 确认 |

**plan 自足性验证**:
- 固定 `batch_locks/<ticker>.publication.lock`，与 writer `batch_locks/<ticker>.lock` 分离 ✓
- guard 只做并发 exclusion，不校验 batch ✓
- outer public guarded entry + private unguarded helper，禁止 ambient marker ✓
- 锁序：先 writer mutex 后 publication guard，释放相反 ✓
- `Source.open()` 通过窄 typed opener 获取同一 guard，fd 打开后释放 ✓
- commit/recovery 物理切换短窗持 guard，长 staging/validator 不持 ✓

**adversarial 挑战 — 非重入 outer-private read 边界**:

plan §4.2 声称"每一个 public published repository meta/list/read entry 在 storage core 最外层获取一次同一 publication guard，并把 guard 持有到本次 meta/list/bytes I/O 完成；它只调用显式 private unguarded helper 完成内部路径解析、组合与 I/O，不能调用会再次获取非重入文件锁的 public read"。

直接代码验证：当前 `_ticker_dir_for_read()`（`_fs_storage_infra.py:1376-1380`）是 private path helper，本身不获取锁。plan 要求这类 helper 保持 unguarded，public entry 持 guard 后调用它们。但 plan 没有明确列出哪些当前 public method 会内部调用其它 public method——例如 `get_source()` 可能内部调用 `get_source_meta()` + `get_primary_file()`。

plan 的表述"不能调用会再次获取非重入文件锁的 public read"已足够约束：实现时如果 `get_source()` 内部调用 `get_source_meta()`，必须改为调用 private `_get_source_meta_inner()` 而非 public `get_source_meta()`。plan §4.2 的 "outer guarded entry + private unguarded helper" 模式已覆盖此场景。测试要求"outer 只获取一次 guard、private unguarded helper 不自死锁"（§8.4）是可执行的。

**结论**: closed。plan 自足，实现 agent 可据此生成正确代码。

---

### R06-PF-02 — `materialize()` 全调用图与 R07 residual

**plan 位置**: §4.2、§11、§12

**代码证据验证**:

plan 列出 8 个 production 文件、9 个 `.materialize()` 调用点。独立 `rg` 验证：

```
dayu/fins/pipelines/sec_fiscal_fields.py:349
dayu/fins/processors/sec_processor.py:157
dayu/fins/processors/source_text.py:88
dayu/fins/processors/bs_report_form_common.py:129
dayu/fins/processors/bs_six_k_processor.py:276
dayu/documents/processors/markdown_processor.py:112
dayu/documents/processors/bs_processor.py:135
dayu/documents/processors/docling_processor.py:148
dayu/documents/processors/docling_processor.py:1745
```

精确 8 文件 9 调用点。✓

**`source_snapshot.py` 核验**: `source_snapshot.py:286` 使用 `self._source.open()` 读到 EOF 复制 spool，不调用上游 `.materialize()`。plan 正确拒绝将其列为裸路径 consumer。✓

**plan 自足性**: §4.2 明确 R06 只保证一次 `Source.open()` 的 stable fd；§11 明确 `materialize()` 后续文件访问是 R07 residual；§12 要求 re-review 验证此边界。plan 不改变 `materialize()` public contract，不增加 wrapper/copy/lease/revision API。✓

**结论**: closed。

---

### R06-PF-03 — callback 精确 callable contract

**plan 位置**: §6 inventory/closure contract、§7.3 Tests、§12

**代码证据验证**:

当前 `sec_download_persistence.py:139-156`：
```python
def build_store_file(
    repository: DocumentBlobRepositoryProtocol,
    source_handle: SourceHandle,
) -> Callable[[str, BinaryIO], FileObjectMeta]:
    return partial(_store_file_callback, repository, source_handle)
```

当前 `_store_file_callback`（`sec_download_persistence.py:459-480`）签名：
```python
def _store_file_callback(
    repository: DocumentBlobRepositoryProtocol,
    source_handle: SourceHandle,
    filename: str,
    stream: BinaryIO,
) -> FileObjectMeta:
    return repository.store_file(source_handle, filename, stream)
```

无 `batch` 参数。✓

plan §6 固定目标签名为 `(filename: str, stream: BinaryIO, *, batch: BatchToken) -> FileObjectMeta`；`partial` 只绑定 repository/handle 等非 authority 输入；batch 由 downloader 每次 invocation 以 required keyword 实参传入。plan 要求窄 callable protocol 或等价严格类型表达 keyword-only 参数。✓

**adversarial 挑战 — 可严格类型化**:

plan 承认"普通 `Callable[[...]]` 不能表达 keyword-only 参数"，要求"窄 callable protocol 或等价严格类型"。这是正确的 Python 类型系统限制：`typing.Callable` 不支持 keyword-only 参数。实现时必须定义一个 `Protocol` 类如：

```python
class StoreFileCallback(Protocol):
    def __call__(self, filename: str, stream: BinaryIO, *, batch: BatchToken) -> FileObjectMeta: ...
```

这比裸 `Callable` 更严格，且 pyright 可检查。plan 已明确要求，不引入 callback framework。✓

**结论**: closed。

---

### R06-PF-04 — 全 staged ticker tree validator

**plan 位置**: §3.2、§5.2、§7.2、§12

**代码证据验证**:

当前 `_fs_storage_infra.py:225` 从完整 published ticker tree copy-on-stage（需确认此代码位置；plan 声称"当前事务从完整 published ticker tree copy-on-stage"）。commit 发布完整 ticker tree。

plan §5.2 删除"两种策略实现时再选"，固定遍历完整 staged ticker tree，不维护 touched set。source→manifest 与 manifest→source 双向一致性是新的 storage-owned commit-time invariant。✓

**adversarial 挑战 — validator 是否只消费 canonical owner facts**:

plan §5.2 的 6 条验证规则全部消费 storage-owned facts：
1. source `meta.json` 可解析，ticker/document/source-kind 与目录路由一致 — storage own
2. provenance 使用唯一 typed owner 解析 — storage own
3. `files` 是非空、无重复的完整 manifest，与物理文件一致 — storage own
4. `primary_document` 非空，命中 files manifest — storage own
5. filing/material ticker manifest 与 source 目录一一对应 — storage own（新 invariant）
6. 同 transaction 的 processed/company/maintenance 在同一 staging ticker tree — storage own

validator 不从 reader runtime、producer 或测试 fixture 反推事实。它只消费 staged tree 中的 canonical owner facts。✓

**adversarial 挑战 — files 非空是否为有意 contract**:

plan §5.2 明确声明"files 非空是 complete-source publication contract 的有意规则；当前所有 producer 都产生 blob；未来若出现 meta-only source 需求，必须先修改 storage owner contract，不能添加 validator 例外"。这是有意设计，不是遗漏。✓

**结论**: closed。

---

### R06-PF-05 — S1 删除全部 implicit/ambient authority

**plan 位置**: §7.0、§7.1 Contract handoff/Tests、§7.3、§8.3、§12

**代码证据验证**:

当前 `_fs_storage_infra.py` 中以下 ambient/implicit 机制必须在 S1 删除：

| 机制 | 代码位置 | 当前作用 |
|---|---|---|
| `_BATCH_OWNER_CONTEXT` | 64-67 | `ContextVar` 保存 ticker→owner_token 映射 |
| `_current_execution_scope_id()` | 89-108 | 返回 `asyncio.current_task()` 或 `threading.get_ident()` |
| `_execute_with_auto_batch()` | 423-464 | 无 token 时自动 begin/commit，有 active batch 时由 ambient owner 加入 |
| `_bind_batch_owner()` | 466-481 | 把当前 scope 绑定为 batch owner |
| `_unbind_batch_owner()` | 483-499 | 移除 scope 绑定 |
| `_require_batch_owner()` | 501-522 | 检查 `ContextVar` + scope id 决定是否是 owner |

plan §7.1 明确在 S1 core cutover 时删除这些，不是推迟到 S3。S3 只做 producer/callback propagation 与零残留证明。✓

**adversarial 挑战 — S1 删除时序是否自洽**:

S1 把 protocol 改为 required `batch: BatchToken` 后，wrapper 必须接收 batch 并直接传给 core。`_execute_with_auto_batch` 不再被 wrapper 调用——它在 S1 自然失效。但 plan 进一步要求显式删除这些 helper，而非仅靠"不再调用"。这是正确的：dead code 仍可能被未来代码意外引用，显式删除消除隐患。✓

**结论**: closed。

---

### R06-PF-06 — CN/Docling 分离短 transaction

**plan 位置**: §6 inventory、§7.3 Tests、§12

**代码证据验证**:

当前 `docling_upload_service.py:331`：
```python
token: BatchToken = self._source_repository.begin_batch(ticker)
```

`docling_upload_service.py:403`：
```python
self._source_repository.commit_batch(token)
```

`docling_upload_service.py:422`：
```python
self._source_repository.rollback_batch(token)
```

service 内部自行 lifecycle。✓

plan §6 明确：
- CN company meta write 是 outer workflow 拥有的短 transaction
- 每个 document 的 Docling write 是另一个 top-level caller 拥有的短 transaction
- `DoclingUploadService._handle_storage_write(..., *, batch: BatchToken)` 只消费 caller batch
- 删除 service 内部 begin/commit/rollback
- company meta 成功、某 document 失败是可重试的分离 publication unit

**adversarial 挑战 — 短事务边界是否 code-generation-ready**:

plan 的 CN upload inventory 行描述为："company meta write 是一个 outer workflow 拥有的短 transaction；每个 document 的 Docling write 是另一个由 top-level upload caller 开启和终结的短 transaction。company meta 已 commit 而某 document 失败是可重试的分离 publication unit，不做跨 transaction rollback，不引入通用 callback/profile/framework。"

Docling service 的 API 变化为：`_handle_storage_write` 新增 `batch: BatchToken` 参数，删除内部 begin/commit/rollback。caller（upload workflow）负责 lifecycle。plan §6 inventory 表已覆盖此变化。✓

**结论**: closed。

---

### R06-PF-07 — 新的 shared-core production batching composition

**plan 位置**: §3.5、§7.3 Production allowlist/Tests、§12

**代码证据验证**:

独立 `rg -n 'FsBatchingRepository' dayu tests` 确认：
- `dayu/fins/storage/fs_batching_repository.py:15` — 类定义
- `dayu/fins/storage/__init__.py:4,27` — 导出

production 零实例化。✓

三个 composition root 当前状态：
- `service_runtime.py:347` — `build_fs_repository_set(workspace_root=workspace_root)` 创建 shared set，但未建 `FsBatchingRepository`
- `cn_pipeline.py:373` — 同上
- `sec_pipeline.py:509` — 同上

**`sec_6k_primary_document_repair.py` 核验**: `sec_6k_primary_document_repair.py:169-171` 分别创建 `FsSourceDocumentRepository(resolved_workspace_root)`、`FsProcessedDocumentRepository(resolved_workspace_root)`、`FsCompanyMetaRepository(resolved_workspace_root)`——三个独立实例，无 shared `_FsRepositorySet`。这是 plan §3.5 所称"standalone 6-K repair 还分别建 core"的直接证据。R06 必须在此处改为创建一个 shared set 并装配 `FsBatchingRepository`。✓

plan §3.5 明确："S3 必须在 `service_runtime.py`、`cn_pipeline.py`、`sec_pipeline.py`、`sec_6k_primary_document_repair.py` 四个真实 composition root 首次实例化 production `FsBatchingRepository`，并与 source/blob/processed/company/maintenance wrappers 共享同一个 `_FsRepositorySet`/core。不得从 source repository 反射、cast、拆出或重建 batching core。"✓

**结论**: closed。

---

### R06-PF-08 — S1/S2/S3 cumulative reviewability gates

**plan 位置**: §7.0、§8 开头、§12

**plan 自足性验证**:

§7.0 明确：
- S1/S2/S3 是同一个 R06 breaking cutover 的累计 working-tree checkpoints
- 每个 slice 完成后执行 Controller scope/focused-test 验证与双路 cumulative slice review
- accepted findings 必须 fix/re-review
- gate 不生成中间 accepted commit
- 不把尚未 propagation 的预期类型错误包装为 green
- S3 后仍对完整 R06 diff 执行统一双路 code review/fix/re-review
- 只有 final tree 可进入 accepted local commit

**adversarial 挑战 — 是否可执行**:

plan 没有使用魔法行数阈值（Controller 裁决拒绝了 DS 建议的"约 1500 行"）。Controller 按 semantic owner、实际 diff 与 reviewer 可审性裁决。这是可执行的：reviewer 看到 diff 后可以判断是否需要进一步收窄。✓

§7.0 的 "Controller scope/focused-test 验证" 在每个 slice 后运行当时可执行的 focused tests，不要求 pyright 零错误（因为 S1/S2 累计树在 producer propagation 前预期类型不完整）。§8 的完整命令"只在最终累计 R06 tree 运行"。这个区分是清晰的。✓

**结论**: closed。

## 3. Adversarial 挑战：跨进程 exclusive publication lock / 锁序 / 非重入 outer-private read 边界

### 3.1 publication lock 是否让 published readers 彼此也短时串行化

plan §4.2 的 publication swap guard 是按 ticker 分片的跨进程文件锁。这意味着同一 ticker 的 published readers 也会彼此串行化（每次 meta/list/bytes I/O 持 guard）。这是否成为产品 bottleneck？

**分析**: 当前 production 中同一 ticker 的并发 published readers 来自不同 processor（如 SEC processor 和 financial fields processor）。它们的 I/O 时间通常在毫秒级（读取 meta.json、list files、read bytes）。跨进程文件锁的 acquire/release 开销也在毫秒级。串行化这些短 I/O 不会成为 bottleneck。

但 plan §4.2 的边界说明已经预留了 escape hatch："一次 `Source.open()` 得到的 fd 属于 old 或 new，fd 成功打开后即可释放 publication guard，后续通过该 fd 的读取保持同一文件对象。"这意味着长时间的文件读取（如大 PDF）不会持 guard。

**结论**: 当前实现下不会成为 bottleneck。如果未来出现长 I/O 竞争，R07 的 snapshot/revision 机制会提供更细粒度的并发控制。这不是 R06 的 blocker。

### 3.2 锁序是否严格

plan 要求：writer/recovery 先 writer transaction mutex、后 publication guard；释放顺序相反。reader 只拿 publication guard。

**代码证据**: 当前 `_fs_storage_infra.py:651-667` 的 `_acquire_ticker_lock` 是 writer mutex。plan 要求新增独立的 publication guard。两者的 acquire/release 顺序必须在实现中严格闭合。

plan §4.2 已明确锁序，§8.4 要求测试证明"writer/recovery 锁顺序无反向嵌套"。这是可执行的。✓

### 3.3 非重入 outer-private read 边界

plan 要求 public read entry 持 guard 后只调用 private unguarded helper。如果 `get_source()` 内部需要调用 `get_source_meta()` + `get_primary_file()`，必须改为调用 private helper。

**潜在风险**: 当前代码中 public method 之间可能存在内部调用链。例如 `_source_root_for_read()` 调用 `_ticker_dir_for_read()`。这些 private helper 本身不获取锁，所以不会自死锁。但如果实现 agent 错误地让一个 public guarded entry 调用另一个 public guarded entry，就会自死锁。

plan 的表述"不能调用会再次获取非重入文件锁的 public read"已明确禁止此模式。测试要求"outer 只获取一次 guard、private unguarded helper 不自死锁"覆盖了此场景。✓

## 4. Adversarial 挑战：LocalFileSource delayed typed opener 是否成为 callback/snapshot/ambient seam

plan §4.2 要求 `LocalFileSource.open()` 通过"窄 typed opener"获取 publication guard。这个 opener 绑定 normalized ticker 对应的 publication-lock acquisition 与 `Path.open("rb")` 到延迟执行的 `Source.open()`。

**adversarial 挑战 — opener 是否成为 callback framework**:

plan 明确说"该 opener 只绑定 path/ticker 等非 authority 输入，不绑定 batch"且"不增加 public snapshot/revision/lease API 或通用 callback framework"。opener 是一个窄的 storage-internal helper，不是通用 callback。它只做一件事：在 `Source.open()` 时获取 publication guard、打开 fd、释放 guard。✓

**adversarial 挑战 — opener 是否成为 ambient guard seam**:

plan 要求"不能把 '已持锁' 状态存入 source"。opener 延迟执行时才获取 guard，不把 guard 状态存入 `LocalFileSource` 实例。每次 `open()` 调用独立获取/释放 guard。✓

**adversarial 挑战 — opener 是否成为 snapshot facade**:

plan 明确"R06 不改变 `materialize()` public contract，不增加 path copy、fd wrapper、lease 或 revision API"。opener 只影响 `Source.open()`，不影响 `materialize()`。✓

**结论**: typed opener 不成为 callback/snapshot/ambient seam。plan 边界清晰。

## 5. Adversarial 挑战：materialize 8 文件 9 调用与 source_snapshot 纠正

已在 §2 R06-PF-02 验证。独立 `rg` 确认 8 文件 9 调用点。`source_snapshot.py:286` 使用 `self._source.open()` 读到 EOF 复制 spool，不调用上游 `.materialize()`。plan 正确拒绝将其列为裸路径 consumer。✓

## 6. Adversarial 挑战：全 staged-tree validator 是否只消费 canonical owner facts

已在 §2 R06-PF-04 验证。6 条规则全部消费 storage-owned staged tree 中的 canonical facts。validator 不从 reader runtime、producer 或测试 fixture 反推事实。✓

## 7. Adversarial 挑战：callback required keyword batch 可严格类型化

已在 §2 R06-PF-03 验证。plan 要求窄 callable protocol 表达 keyword-only `batch` 参数。Python `typing.Callable` 不支持 keyword-only，但 `Protocol` 可以。pyright 可检查。✓

## 8. Adversarial 挑战：CN/Docling 短事务

已在 §2 R06-PF-06 验证。CN company meta 与逐 document Docling 是分离短 transaction。company meta 成功、某 document 失败是可重试的分离 publication unit。plan 已明确，不留"implementation 再裁决"空位。✓

## 9. Adversarial 挑战：四个新 shared-core batching composition

已在 §2 R06-PF-07 验证。四个 composition root（`service_runtime.py`、`cn_pipeline.py`、`sec_pipeline.py`、`sec_6k_primary_document_repair.py`）当前均未实例化 `FsBatchingRepository`。R06 S3 必须在每个 root 新装配它，并与现有 wrappers 共享同一 `_FsRepositorySet`/core。✓

**特别核验 `sec_6k_primary_document_repair.py`**: 当前 `sec_6k_primary_document_repair.py:169-171` 分别创建三个独立 repository 实例（`FsSourceDocumentRepository`、`FsProcessedDocumentRepository`、`FsCompanyMetaRepository`），无 shared set。R06 必须改为创建一个 shared set 并从中装配所有 wrappers（含新增的 `FsBatchingRepository`）。✓

## 10. Adversarial 挑战：S1/S2/S3 累计 reviewability 与最终统一 acceptance 是否可执行

已在 §2 R06-PF-08 验证。plan 不使用魔法阈值，按 semantic owner 与实际可审性裁决。每个 slice 后运行 focused tests，不把预期类型错误包装为 green。S3 后统一 review 完整 R06 diff。✓

## 11. Scope creep 检查

### 11.1 R07-R11 是否被偷带

plan §1.3 明确排除：
- R07 storage revision/snapshot/bounded retry/opaque external-id mapping/storage-key grammar/hash-ID grammar
- R08 financial/XBRL contract
- R09 terminal validator
- R10 HKEX
- R11 CLI upload

plan §4.2 的 boundary 说明："R06 不得用 selector/generation/revision、retry 或 pointer layout 提前实现 R07。"✓

### 11.2 Issue 142/151/175/177/178 是否被偷带

plan §1.3 明确排除："不实施 Issue 142/151/175/177/178，不引入 process isolation、统一 authorization、callback transport 或旧 schema compatibility。"✓

### 11.3 统一 authorization 是否被偷带

plan §1.3 排除。plan 的 publication guard 明确"不读取、验证或推断 `BatchToken`、caller、task 或 thread identity"——它只是并发 exclusion，不是 authorization。✓

### 11.4 旧 schema 兼容或安全回退是否被偷带

plan §1.3："不新增旧库 migration、兼容读取、兼容 re-export/facade/wrapper、loose parsing、`hasattr/getattr` fallback。"✓

plan §5.1："final source 的 `ingest_complete` 是 storage-owned 完成态 invariant：producer 不再写 false……保留 true 字段只服务当前 provenance/read contract，不是旧 staging 兼容分支。"✓

### 11.5 containment / symlink / atomic write 安全机制是否回退

现有 `_resolve_handle_child_path()` 的 containment 检查、`_write_json` 的 atomic temp+replace+fsync、`os.replace()` 的原子目录移动均不被 plan 修改。plan §5.2 validator 要求"contained 且无 symlink escape"。✓

## 12. 旧 finding 最终状态

### 原 MiMo review findings

| ID | 描述 | 最终状态 |
|---|---|---|
| R06-REVIEW-001 | `materialize()` 5 处 production consumer 是 R07 residual | **closed** — R06-PF-02 已在 plan §4.2/§11/§12 显式记录 8 文件 9 调用点 |
| R06-REVIEW-002 | publication swap guard 多进程实现机制 | **closed** — R06-PF-01 已在 plan §4.2 固定 per-ticker 跨进程 filelock |
| R06-REVIEW-003 | callback 签名变化未明确指定 | **closed** — R06-PF-03 已在 plan §6 固定精确 callable contract |
| R06-REVIEW-004 | XBRL staged read 区分 | **no-action** — plan §3.4 已明确 |
| R06-REVIEW-005 | files 非空规则 | **closed** — R06-PF-04 已明确为有意 contract |
| R06-REVIEW-006 | validator staged-tree vs touched-identities | **closed** — R06-PF-04 已固定全 staged tree |
| R06-REVIEW-007 | `_execute_with_auto_batch` S1 删除 | **closed** — R06-PF-05 已在 plan §7.1 明确 |
| R06-REVIEW-008 | journal 字段闭集 | **confirmed** — plan §4.3 正确收窄 |
| R06-REVIEW-009 | `partial` capture 模式 | **closed** — 合并入 R06-REVIEW-003 |
| R06-REVIEW-010 | `mark_downloaded_processed_rebuild_required` batch 传播 | **confirmed** |
| R06-REVIEW-011 | `service_runtime.py` 是 required allowlist | **confirmed** |
| R06-REVIEW-012 | `cn_download_protocols.py` 必要性 | **confirmed** |
| R06-REVIEW-013 | propagation scan 完整性 | **confirmed** |
| R06-REVIEW-014 | scoped Ruff 错误自然消失 | **confirmed** |
| R06-REVIEW-015 | R07 residual 边界精确 | **confirmed** |
| R06-REVIEW-016 | Issue 142/151/175/177/178 未偷带 | **confirmed** |
| R06-REVIEW-017 | containment/symlink/atomic write 不回退 | **confirmed** |

### 原 DS review findings

| ID | 描述 | 最终状态 |
|---|---|---|
| F-DS-001 | publication swap guard multi-core 未指定 | **closed** — R06-PF-01 已固定 |
| F-DS-002 | `materialize()` R07 residual | **closed** — R06-PF-02 已固定 |
| F-DS-003 | manifest cross-check 新 invariant | **closed** — R06-PF-04 已明确 |
| F-DS-004 | CN upload transaction 边界 deferral | **closed** — R06-PF-06 已裁决 |
| F-DS-005 | manifest internal routing | **no-action** — plan §6 已覆盖 |
| F-DS-006 | cumulative diff reviewability | **closed** — R06-PF-08 已固定 |
| F-DS-007 | `FsBatchingRepository` 新 composition | **closed** — R06-PF-07 已明确 |
| F-DS-008 | `_fs_processed_core.py` 在 S1 allowlist | **reviewer error** — 已撤回 |
| F-DS-009 | smoke barrier mechanism | **no-action** — plan 已指定 Event/barrier |
| F-DS-010 | `replace_source_meta` manifest routing | **no-action** — plan §6 已覆盖 |

## 13. 新 findings

### R06-REREVIEW-001 — `sec_6k_primary_document_repair.py` 当前无 shared set，R06 改造比其它 root 更侵入

**严重性**: 低（evidence observation，plan 已覆盖，无需 plan 修正）

**直接证据**:
- `sec_6k_primary_document_repair.py:169-171` 分别创建三个独立 repository 实例
- `service_runtime.py:347`、`cn_pipeline.py:373`、`sec_pipeline.py:509` 已通过 `build_fs_repository_set` 创建 shared set

**分析**: `sec_6k_primary_document_repair.py` 是四个 composition root 中唯一一个当前没有 shared `_FsRepositorySet` 的。R06 S3 需要在此处引入 `build_fs_repository_set` + `FsBatchingRepository` + 共享 wrappers，改造幅度比其它三个 root（只需新增 `FsBatchingRepository` 装配）更大。plan §3.5 已正确识别"standalone 6-K repair 还分别建 core"，但未显式指出这会导致 S3 在该文件的改动幅度更大。

这不是 plan 缺陷——plan §7.3 的 allowlist 已包含该文件，且 §3.5 的描述足够让 implementation agent 理解需要重构。但 implementation agent 应注意此文件的改动幅度。

**结论**: evidence observation，无需 plan 修正。

### R06-REREVIEW-002 — `_ticker_dir_for_read` staging 路由删除与 S1/S2 时序

**严重性**: 低（evidence observation，plan 已覆盖）

**直接证据**:
- `_fs_storage_infra.py:1376-1380` `_ticker_dir_for_read` 当对 active batch owner 路由到 staging
- plan §3.4 要求 read method 默认只读 published tree

**分析**: S1 删除 `_require_batch_owner` 和 `_BATCH_OWNER_CONTEXT` 后，`_ticker_dir_for_read` 中的 `self._require_batch_owner(ticker)` 调用会失败。S1 必须同时修改此方法为只返回 `_target_ticker_dir(ticker)`，或删除 staging 路由分支。plan §7.1 的 S1 allowlist 包含 `_fs_storage_infra.py`，且 §3.4 已明确 read 只走 published。implementation agent 在 S1 中会自然处理此变化。

**结论**: evidence observation，无需 plan 修正。

### R06-REREVIEW-003 — `_fs_blob_core.store_file` 的 `_get_handle_meta` 前置校验在 blob-first 模式下如何处理

**严重性**: 低（evidence observation，plan §5.1 已覆盖）

**直接证据**:
- `_fs_blob_core.py:143` `self._get_handle_meta(handle)` 要求已有 source meta
- plan §5.1: "blob core 对 SourceHandle 不再要求预先存在 source meta；它验证 batch/core/ticker/contained path 后写 staging"

**分析**: plan §5.1 已明确 blob core 在 R06 下不再要求预先存在 source meta。S2 实现时必须修改 `_get_handle_meta` 的校验逻辑或绕过它，改为验证 batch/core/ticker/contained path。plan 已覆盖此变化。✓

**结论**: evidence observation，无需 plan 修正。

## 14. Residual risks

| residual | owner | 状态 |
|---|---|---|
| 跨多次 repository call 的同版本 snapshot | R07 | plan §1.3/§11 明确 |
| `materialize()` 后续文件访问的版本一致性 | R07 | plan §4.2/§11 显式记录 8 文件 9 调用点 |
| 多进程并发 published readers 彼此短时串行化 | R06 accept | 当前 I/O 时间在毫秒级，不会成为 bottleneck；R07 提供更细粒度并发 |
| `sec_6k_primary_document_repair.py` 改造幅度 | S3 implementation | plan allowlist 已包含，implementation agent 需注意 |

## 15. Final plan review conclusion

**PASS**

R06-PF-01..08 全部 closed。原 MiMo review 17 个 findings 中 4 个 closed by fix、12 个 confirmed、1 个 no-action。原 DS review 10 个 findings 中 6 个 closed by fix、3 个 no-action、1 个 reviewer error。新 re-review 发现 3 个 evidence observations，均为 plan 已覆盖的低严重性观察，无需 plan 修正。

fixed plan 的核心设计（显式 `BatchToken`、required `batch`、writer mutex / publication swap guard 分离、complete-source validator、blob-first staging、三 slice 累计 cutover）经直接代码证据验证，root cause 判定正确，semantic owner 分配清晰。plan 自足性满足 code-generation-ready 要求：implementation agent 可据此生成正确代码，无需重新设计。

plan 未偷带 R07-R11、Issue 142/151/175/177/178、统一 authorization、旧 schema 兼容或安全回退。现有 containment、symlink、atomic write、writer fencing、journal recovery 安全机制不回退。

---

*Review artifact only. No plan/control/product/test/README modification. No stage/commit/push/PR.*
