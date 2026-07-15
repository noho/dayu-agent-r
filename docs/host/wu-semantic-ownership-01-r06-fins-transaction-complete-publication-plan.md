# WU-SEMANTIC-OWNERSHIP-01 R06 Fins 显式事务与完整 source 发布实施计划

## 0. Gate 身份与结论

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` continuation；本文件只覆盖内部 remediation sub-WU R06 plan gate，不创建新 WU、feature 或 issue，不重新做 goal confirmation。
- Controller transition base / 当前 HEAD：`9c07b88d9e855f19f0b828f671022119cc5599a1`。
- 当前 gate：`R06 remediation plan review fix`。本次只落实 Controller accepted `R06-PF-01..08`；修订后只允许 Controller 验证与 AgentMiMo / AgentDS 对 fixed complete plan 做两路完整 re-review。本文件不表示 plan accepted，不授权 implementation、commit、push 或 PR。
- 本 gate 只允许写入本 plan 与 `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-fix-codex.md`；product、test、README、design、control 与既有 review 均只读。
- 计划形态：S1、S2、S3 是同一次 breaking contract cutover 的三个代码生成 concern，不是三个可独立部署的兼容版本。required `batch=` 一旦进入 public protocol，就必须在同一累计 diff 中完成全部 producer/callback 迁移；禁止用 optional batch、默认值、Source facade、ambient lookup 或临时 wrapper 维持中间绿色。

第一性原理结论：

1. 事务写权限应回答“调用者是否持有 storage core 已登记且仍开放的显式 capability”，而不是“当前恰好是哪一个 task/thread”。当前 explicit token 只管 commit/rollback，mutation 却由 `ContextVar`、task/thread identity 决定，确实形成两个 authority。
2. 完整 source 的业务事实只有一份：final meta、完整 files manifest、primary file、provenance 和相关 blob 必须在同一发布点可见。`ingest_complete=false` 作为 blob staging acknowledgement 把 storage transaction state 泄漏进业务 schema，且迫使 producer 先写半 meta；动机成立，严重性没有被高估。
3. 当前 `target -> backup`、`staging -> target` 两次 rename 之间真实存在在线 target 缺失窗口。journal recovery 只能处理 crash 后状态，不能证明并发 reader 在线期间不见缺失/半发布；R06 必须同时关闭在线可见性窗口。
4. 最小正确修复是把 authority、staging、完整性校验、writer transaction mutex、短时 publication swap guard 和 recovery 都收回 `dayu.fins.storage`，producer 只拥有事务边界和完整业务输入。不能在 read runtime、测试 fixture、展示层或某个入口用 fallback 补偿。

## 1. 唯一目标、semantic owner 与非目标

### 1.1 唯一目标

建立如下唯一写链：

```text
top-level publication owner
  -> BatchingRepositoryProtocol.begin_batch(ticker)
  -> BatchToken(transaction_id, ticker)
  -> every repository mutation(..., batch=batch)
  -> storage staging（published readers 不可见）
  -> storage-owned complete-source validation
  -> storage-owned publication swap guard 下切换完整 ticker tree
  -> commit 或 rollback 消费 batch
```

最终不变量：

- 显式 `BatchToken` 是 mutation、commit、rollback 的唯一 authority；合法 helper、child task 或 thread 可显式转交同一个 token。
- `begin_batch` / `commit_batch` / `rollback_batch` 只属于 `BatchingRepositoryProtocol`。
- 所有业务 mutating repository method 都有 keyword-only、non-optional `batch: BatchToken`。
- published read 永远不路由到 staging；在线 reader 在现有两次 rename 的任一暂停点都只会完成为旧完整或新完整观察，不会得到 target missing、半 meta、半 blob 或半 processed。
- commit 前 storage owner 校验 staged final source；失败、取消、pre-commit crash 与 recovery 都只能保留旧完整或发布新完整。

### 1.2 语义 owner

| 语义 | 唯一 owner | R06 动作 |
| --- | --- | --- |
| public transaction capability | `BatchToken` + `BatchingRepositoryProtocol` | 收窄为 transaction identity 与 ticker；只有 batching protocol 声明 lifecycle |
| active/open/closed、core membership、ticker match | shared filesystem storage core | 只保存在进程内 active registry；每次 mutation/lifecycle 统一校验 |
| cross-process transaction writer exclusion | storage writer transaction/ticker mutex | 可覆盖 begin 至终态；仅作 writer mutex，持锁不授予 mutation authority |
| online physical swap/read exclusion | storage publication swap guard | 只覆盖 commit/recovery 的物理切换短窗与一次 published read/open；不覆盖下载、Docling或其它事务构造期 |
| staging / target / backup / journal locator | storage internal active state | 不进入 public token、producer 或业务 meta |
| crash recovery phase fact | storage journal | 只持 recovery 直接消费的 transaction/ticker/phase/relative locators |
| source 完整性与可发布资格 | source/storage validator | commit 前统一验证 meta/files/primary/provenance/manifest/物理 blob |
| source/blob/processed/company/maintenance 业务输入 | 各 producer/domain contract | producer 构造完整事实并显式传播 batch，不拥有 transaction state |
| incomplete ingestion resume | 无当前 owner | 删除；未来若真实需要，必须独立 ingestion-state design/issue |

### 1.3 明确非目标

- 不实施 R07 的 storage revision、snapshot handle、bounded retry、opaque external-id mapping、storage-key grammar 或 hash/ID grammar。
- 不实施 R08 financial/XBRL contract、R09 terminal validator、R10 HKEX、R11 CLI upload。
- 不实施 Issue 142/151/175/177/178，不引入 process isolation、统一 authorization、callback transport 或旧 schema 兼容。
- 不新增旧库 migration、兼容读取、兼容 re-export/facade/wrapper、loose parsing、`hasattr/getattr` fallback。
- 不预先发明具体新异常名、retry 次数、transaction ID 格式、revision 算法或类框架。错误继续使用 owner boundary 已有的参数/状态/I/O 错误类别；若实现证据需要 public error contract 变化，先停回 Controller。
- R06 的短时 publication swap guard 保证一次 published repository read/open 不落入 rename 空窗；跨多次 repository call、长生命周期 processor read 的同版本 snapshot 仍由 R07 独占。不得以 R06 guard 冒充 R07 snapshot。

## 2. 当前 base 的直接代码证据与 root cause

| 直接证据 | 当前事实 | root-cause 判定 |
| --- | --- | --- |
| `document_models.BatchToken` | 暴露 `token_id`、`owner_token`、`owner_scope_id`、target/staging/backup/journal/lock `Path` 与 `created_at` | public capability 泄漏进程内 owner 和物理布局 |
| `_fs_storage_infra.py` | `_BATCH_OWNER_CONTEXT`、`asyncio.current_task()`、thread id、`_require_batch_owner()` 决定 staging mutation/read | ambient identity 是第二 authority；explicit token 不能独立授权 helper/child task |
| `_execute_with_auto_batch()` | mutation 无 token 时自动 begin/commit；有 active batch 时由 ambient owner 加入 | caller contract 无法区分独立 mutation 与加入既有 transaction |
| `_active_batches` | 以 ticker 保存 public `BatchToken`，路径/lock/state 混在 token | active lifecycle 与 public capability 没有边界 |
| `_write_batch_journal()` | 写 owner token/scope、PID、hostname和绝对路径 | journal 持有 recovery 不消费的进程内事实 |
| `_ticker_dir_for_read()` | active owner 的普通 read 自动转到 staging | published read 与 transaction-internal read 无显式边界 |
| Source protocol/wrapper | 重复声明/实现 begin/commit/rollback | batching owner 被 Source facade 重复承诺 |
| 全部 mutating protocols | 没有 required batch | mutation authority 只能靠 ambient/auto-batch 猜测 |
| `stage_source_document()` | 写 `ingest_complete=false`、空 files/primary；重入比较 `_STAGING_STABLE_META_FIELDS` | source business meta 充当 storage staging acknowledgement |
| `_fs_blob_core.store_file()` | 先 `_get_handle_meta()`，无 source meta 就拒绝 blob | producer 被迫先发布半业务记录才能写 transaction staging |
| CN/SEC/Docling | 先 ack/staging，再 blob，再 final meta；测试固化该顺序 | 多个 producer 依赖错误 owner contract |
| commit 两次 rename | 先 target→backup，再 staging→target | 即使最终 recovery 正确，在线并发 reader 仍可在中间看到 target 不存在 |
| factory/assembly | production 默认 facade 可共享 `_FsRepositorySet`，但 batching facade 未进入 Default runtime / CN/SEC host contract；6-K repair 还分别建 core | required batch cutover 必须补齐真实 composition root，不能只改 storage 文件 |

根因是同一事实被三个层重复拥有：public token 暴露一部分事务事实，ambient execution context 决定 mutation authority，source business meta 又承担 blob staging acknowledgement。修复必须在 storage owner boundary 一次收敛，不能保留任一旧路径作为 fallback。

## 3. R06 public transaction contract

### 3.1 最小 `BatchToken`

public `BatchToken` 精确只保留：

```text
transaction_id: str   # storage 生成的 opaque bearer identity；不承诺格式
ticker: str           # 当前 transaction scope 的规范业务 key
```

- 不暴露 owner token/scope/task/thread/PID/hostname、Path、lock、phase、created time、staging/backup/journal locator。
- 测试只断言 opaque、非空、不同 begin 不相同及 registry 行为；不得断言 UUID、长度、字符集或 hash grammar。
- 同值 token 是 bearer capability 的显式传播；R06 所称“伪造拒绝”指未由当前 core 登记的未知/篡改 transaction identity、错误 ticker 或来自另一 core 的 token。不得用 Python object identity、task identity或 caller stack 另造 authority。

### 3.2 storage internal active state 边界

`_fs_storage_infra.py` 内部每个 active transaction 的 state record（具体私有类型名由实现按现有结构决定，不在 public contract 固定）只保存：

- public identity 的 canonical copy：`transaction_id`、normalized ticker；
- lifecycle：open/commit-started/closed 或等价单一状态；
- writer transaction/ticker mutex token；
- staging、target、backup、journal 的 storage-owned contained locators；
- 当前 durable journal phase；
- complete-source validation 所需的 staging ticker root；validator 必须遍历完整 staged ticker tree，不维护 touched identities/touched set。

storage core 使用 transaction-id registry 与 ticker→active-transaction index。所有 mutation 与 commit/rollback 先走同一个 internal resolver：

1. token ticker 与 mutation request/handle 的 ticker 都先规范化并精确相等；
2. transaction identity 必须在当前 core registry 登记；
3. registry 中 canonical token 与传入值匹配；
4. state 必须仍 open，commit/rollback 后立即失效；
5. token 来自另一 `_FsRepositorySet` / core 时，即使 workspace 与 ticker 相同也拒绝；
6. lock 是否恰好已持有不参与 authority 判断。

必须覆盖：未知/篡改 token、已 commit、已 rollback、ticker mismatch、cross-core token、同 core 显式跨 helper/child task/thread成功。不得检查 `ContextVar`、current task/thread 或 caller identity。

### 3.3 lifecycle 唯一协议

只有 `BatchingRepositoryProtocol` 声明：

```text
begin_batch(ticker) -> BatchToken
commit_batch(batch) -> None
rollback_batch(batch) -> None
recover_orphan_batches(*, dry_run=False) -> tuple[str, ...]
```

- `commit_batch` 开始即由 storage owner 消费 lifecycle；validator 或 physical commit 失败时 storage 自行恢复/保留 recovery evidence，caller 不二次 rollback。
- `rollback_batch` 只接收尚未进入 commit 的 open token并消费它。
- recovery 是 lifecycle/recovery operation，不要求一个不可能存在的 active batch；它不属于业务 mutation protocol 例外。
- `SourceDocumentRepositoryProtocol` 及 wrapper 删除 begin/commit/rollback，禁止兼容 re-export 或只透传 facade。

### 3.4 全部 mutating public protocol

下表是闭集；每个方法都新增 keyword-only、non-optional `batch: BatchToken`，无默认值、无 `None`：

| protocol | mutating methods |
| --- | --- |
| `CompanyMetaRepositoryProtocol` | `upsert_company_meta(meta, *, batch)` |
| `SourceDocumentRepositoryProtocol` | `create_source_document(req, source_kind, *, batch)`；`update_source_document(..., *, batch)`；`delete_source_document(req, *, batch)`；`reset_source_document(ticker, document_id, source_kind, *, batch)`；`restore_source_document(req, *, batch)`；`replace_source_meta(ticker, document_id, source_kind, meta, *, batch)` |
| `ProcessedDocumentRepositoryProtocol` | `create_processed(req, *, batch)`；`update_processed(req, *, batch)`；`delete_processed(req, *, batch)`；`clear_processed_documents(ticker, *, batch)`；`mark_processed_reprocess_required(ticker, document_id, required, *, batch)` |
| `DocumentBlobRepositoryProtocol` | `delete_entry(handle, name, *, batch)`；`store_file(handle, filename, data, *, batch, content_type=..., metadata=...)` |
| `FilingMaintenanceRepositoryProtocol` | `clear_filing_documents(ticker, *, batch)`；`save_download_rejection_registry(ticker, registry, *, batch)`；`store_rejected_filing_file(ticker, document_id, filename, data, *, batch, content_type=..., metadata=...)`；`upsert_rejected_filing_artifact(req, *, batch)`；`cleanup_stale_filing_documents(ticker, *, batch, active_form_types, valid_document_ids)` |

`stage_source_document()` 从 protocol、wrapper、core、producer和 tests 删除。所有 read method 默认只读 published tree，不接受 optional batch。当前唯一有直接代码需要的 staging read 是 SEC 在 blob 落盘后判断 XBRL instance；为它提供窄、显式、required-batch 的 `has_staged_filing_xbrl_instance(..., *, batch)` transaction-internal read，published `has_filing_xbrl_instance()` 继续只读 published tree。

### 3.5 shared-core composition

- `FsBatchingRepository` 当前没有 production 实例；R06 必须把它作为新的 production composition 显式加入，而不是把它描述成既有 wiring。
- `DefaultFinsRuntime`、`CnPipeline`、`SecPipeline` 与 standalone 6-K repair 是四个真实 composition owner：分别在 `service_runtime.py`、`cn_pipeline.py`、`sec_pipeline.py`、`sec_6k_primary_document_repair.py` 创建一个 `_FsRepositorySet`，并从同一 set 装配新的 `FsBatchingRepository` 以及 source/blob/processed/company/maintenance wrappers。不得从 source repository 反射、cast、拆出或重建 batching core。
- storage core registry 是最终 shared-core 校验：从另一 core 得到的 token在 mutation boundary 失败，而不是让 wrapper 根据路径、workspace string 或类型猜测兼容。

## 4. Writer mutex、publication swap guard、journal 与 recovery

### 4.1 writer transaction/ticker lock 只作 writer mutex

现有跨进程 ticker file lock保留，但语义收窄为一件事：

1. 从 begin 到 commit/rollback 终态排除同 ticker 第二 writer；它可以覆盖下载、Docling和完整transaction构造期。

它不授予 mutation authority，也不供published reader获取。无batch的caller即使持有/等待到writer lock也不能写；有同core open batch的helper不因task/thread变化失效。长下载或Docling占用writer lock只排斥同ticker第二writer，绝不能因此阻塞published reads。

### 4.2 在线 reader 空窗的 storage-owned 消除方案

R06 不允许只写“recovery 后正确”。现有两次 rename 保留为 physical commit primitive时，storage 必须在writer transaction/ticker mutex之外建立独立的storage-owned publication swap guard protocol：

- publication guard 是按 normalized ticker 分片的跨进程文件锁，复用 `dayu.runtime.filelock` / `RuntimeFileLockToken`；锁路径由固定 storage root 与 normalized ticker 唯一派生为 `batch_locks/<ticker>.publication.lock`。它不得复用从 begin 持有到终态的 `batch_locks/<ticker>.lock`，也不得写入 journal、public token 或业务 meta。
- publication guard 只负责 online physical publication/read exclusion，不是 mutation authority；它不读取、验证或推断 `BatchToken`、caller、task 或 thread identity。
- writer在begin后只持有writer transaction/ticker mutex；staging写入、下载、Docling和commit前complete-source validator均不获取publication swap guard，因此不会阻塞published readers。
- commit只有在validator通过、即将推进会触碰published target/backup的journal phase与执行 `target -> backup`、`staging -> target` 物理切换时才获取publication swap guard；切换完成为新完整，或失败恢复为旧完整后立即释放。普通pre-commit rollback只清理不可见staging，不获取该guard；任何会恢复/移动published target/backup的commit-failure处理必须仍在guard内。
- orphan recovery先获取同ticker writer transaction/ticker mutex，避免与活跃writer并行；读取并校验journal后，只有实际检查/移动/恢复target、backup、staging的物理切换短窗再获取同一个publication swap guard。完成old/new完整终态后立即释放swap guard，再完成recovery清理并释放writer mutex；recovery不能绕过任一对应互斥边界。
- writer/recovery 的唯一嵌套顺序是先 writer transaction mutex、后 publication guard；释放顺序相反，先 publication guard、后 writer mutex。published reader只获取publication guard，任何路径不得先持 publication guard 再尝试 writer mutex。
- 每一个 public published repository meta/list/read entry 在storage core最外层获取一次同一publication guard，并把guard持有到本次meta/list/bytes I/O完成；它只调用显式 private unguarded helper完成内部路径解析、组合与I/O，不能调用会再次获取非重入文件锁的 public read。`_ticker_dir_for_read()` 等 private path helper 本身不获取guard。
- 禁止用 `ContextVar`、task/thread-local、ambient“已持锁”标记、默认参数或 public compatibility 参数表达 guard 已持有；public-to-public 组合必须改为 outer guarded entry + private unguarded helper，而不是检测环境状态或重入获取锁。
- `get_source_meta`、manifest/list、company/processed/meta、blob bytes/list、provenance等都在outer read guard内完成I/O；transaction-internal staging read由required batch校验后直接调用private staging helper，不获取publication swap guard，也不改变published语义。
- `get_source()` / `get_primary_source()` 返回的Fins `LocalFileSource`必须带required storage-owned open guard：storage用一个窄typed opener把normalized ticker对应的publication-lock acquisition与`Path.open("rb")`绑定到延迟执行的`Source.open()`；该opener只绑定path/ticker等非authority输入，不绑定batch。`Source.open()`获取同一publication guard，在fd成功打开或打开失败后通过同一调用栈释放；成功fd固定本次old或new file。不能把guard只包住path拼接，也不能把“已持锁”状态存入source。该直接依赖把 `dayu/fins/storage/local_file_source.py` 加入R06 allowlist refinement，但不增加public snapshot/revision/lease API或通用callback framework。

因此在线状态序列为：

```text
writer holds transaction mutex -> 长时间下载/Docling/staging/validate；publication guard空闲，reader持续读取old
reader A holds publication guard -> 完成一次meta/list/bytes I/O或打开old stable fd -> release
commit acquires publication guard -> target->backup -> staging->target -> new完整或恢复old -> release
reader B acquires publication guard -> 完整打开/物化new（或失败恢复后的old）
```

任何reader都不能在两次rename中间进入，但writer在swap短窗之外不能用transaction mutex阻塞reader。测试必须同时证明：（a）writer停在长staging/validator barrier时独立published reader不阻塞且读取old；（b）writer停在两个rename barrier时reader被publication swap guard真实阻塞，并在guard释放后只得到旧完整或新完整。若reader在（a）被长事务阻塞，或在（b）得到 `FileNotFoundError`、空manifest、meta/blob mismatch或incomplete state，均失败。

边界说明：一次 `Source.open()` 得到的 fd属于 old 或 new，fd成功打开后即可释放publication guard，后续通过该fd的读取保持同一文件对象。多个先后独立 read call是否绑定同一版本不是 R06 contract，R07 才提供 storage snapshot/revision。R06 不得用 selector/generation/revision、retry 或 pointer layout提前实现 R07。

当前 production `.materialize()` 调用图有 8 个文件、9 个调用点：

- `dayu/documents/processors/bs_processor.py`；
- `dayu/documents/processors/docling_processor.py`（构造与 JSON sniff 两处）；
- `dayu/documents/processors/markdown_processor.py`；
- `dayu/fins/processors/sec_processor.py`；
- `dayu/fins/processors/bs_report_form_common.py`；
- `dayu/fins/processors/bs_six_k_processor.py`；
- `dayu/fins/processors/source_text.py`；
- `dayu/fins/pipelines/sec_fiscal_fields.py`。

这些调用在拿到裸 `Path` 后的延迟/多次读取没有 snapshot consistency，是 R07 storage revision/snapshot 的显式 residual。`dayu/documents/processors/source_snapshot.py` 不是第 9 个独立裸路径 consumer：它通过一次 upstream `Source.open()` 读到真实 EOF并复制进自有 spool，之后的 `materialize()` 只把该稳定 spool 写入自己拥有的临时文件。R06 不修改 `materialize()` public contract，不增加path copy、fd wrapper、lease或revision API，也不得声称覆盖全部 Source read。

### 4.3 最小 journal

journal 只保存 recovery 直接消费的：

- opaque transaction identity；
- normalized ticker；
- phase；
- 相对且经过 containment 校验的 staging/target/backup locator（能由固定 storage roots + identity/ticker推导的字段不重复持久化）。

删除 owner token/scope、task/thread、PID、hostname、created time、lock object/path和绝对路径。recovery 从固定 workspace roots解析 locator并重做 containment/symlink校验；不得信任 journal 提供任意绝对路径。

phase 结果：started/pre-swap 清 staging保留 old；已 backup/已 swap但未 committed 恢复 old（原目标不存在时撤掉 uncommitted new）；committed 保留 new并清 backup；rolled back保留 old并清 evidence。phase 具体常量沿用现有 state machine，计划不引入第二 phase framework。

## 5. Complete source 单 commit 可见点

### 5.1 producer 与 storage 的分工

- producer可在 batch staging 中先用业务 identity直接构造 `SourceHandle(ticker, document_id, source_kind)` 并写 blob；handle 不是 authority，`batch` 才是。
- blob core 对 SourceHandle 不再要求预先存在 source meta；它验证 batch/core/ticker/contained path 后写 staging。
- producer在所有 blob准备完成后只写一次 final source create/update/replace；禁止 preliminary create、`ingest_complete=false`、空 files/primary和 stable re-entry。
- final source 的 `ingest_complete` 是 storage-owned完成态 invariant：producer不再写 false，也不把它当流程控制。fresh schema中 storage只允许/产生完成态 true；false 在 commit validator失败关闭。保留 true 字段只服务当前 provenance/read contract，不是旧 staging 兼容分支。
- completed source已存在时 create仍失败；update/replace必须针对 staged copy中已存在的 completed source。overwrite用同 batch reset + blobs + final create，失败恢复旧完整。

### 5.2 commit 前 storage-owned validator

validator 在任何 target rename之前运行，至少验证 staged tree中的所有 source publication facts：

1. source `meta.json` 可解析，ticker/document/source-kind与目录路由一致；禁止 `ingest_complete=false`。
2. provenance使用唯一 typed owner解析，必需 ingest method/provider合法，完成态为 true；producer不能用 ID/path猜 provider。
3. `files` 是非空、无重复业务文件名的完整 manifest；每条 name/URI/size/sha（字段存在时）与同一 staged source下的物理 regular file一致、contained且无 symlink escape。
4. `primary_document` 非空，精确命中 files manifest且对应物理文件存在；不得以第一文件 fallback掩盖缺失 primary。
5. filing/material ticker manifest与 source目录一一对应；validator同时验证 source→manifest 与 manifest→source，禁止 dangling manifest 或 source缺manifest，且identity、provenance和完成态投影一致。这是R06新增的storage-owned commit-time invariant，不是read层补偿或对既有read行为的描述。
6. 与 source同 transaction 修改的 processed/company/maintenance facts必须处于同一 staging ticker tree；source validator不从这些消费者反推 source完整性。

validator必须遍历完整 staged ticker tree，不采用或维护 touched-identities tracking。当前 transaction 从完整 published ticker tree copy-on-stage，commit也发布完整ticker tree；全树校验无需第二套touched-set状态、闭包证明或fallback，是当前最小正确实现。`files`非空是complete-source publication contract的有意规则，当前所有producer都产生blob；未来若出现meta-only source需求，必须先修改storage owner contract，不能添加validator例外。不得把validator复制到producer、read runtime或tests fixture。

### 5.3 唯一可见点与 failure invariant

- validator通过前 target不变。
- 会触碰published target/backup的physical publication、相应journal phase推进与failure restore在短时publication swap guard内；commit成功是唯一新可见点。validator和长事务构造不占用该guard。
- validator/写入/取消在 commit前失败：caller rollback，published old不变。
- commit开始后失败：storage owner按现有 precommit rollback/recovery规则消费 token；caller不二次 rollback。
- crash-phase与在线reader是两套独立证据：recovery证明重开后old/new；publication swap guard barrier证明进程仍在线时reader不进入rename gap，长staging barrier则证明published reads未被writer全事务锁误阻塞。三者缺一不可。

## 6. 当前真实 producer / callback / protocol 完整 inventory

下表来自当前调用图，不以 umbrella 文件名清单替代：

| publication unit / 当前入口 | 当前 mutations / callback | R06 top-level唯一 lifecycle owner与传播 |
| --- | --- | --- |
| `FinsIngestionRuntime._store_downloaded_document` | reset、preliminary source create、blob callback、final update、processed marker | runtime新增 required batching repo；单文档 begin；blob-first + final source一次；所有 helper显式 `batch=`；runtime commit/rollback |
| `FinsIngestionRuntime._store_rejected_filing_artifact` | rejected files、artifact、registry save | helper作为单 artifact owner begin；file helper、artifact、registry同 batch；helper commit/rollback |
| `FinsIngestionRuntime._preprocess_one_document` | processed create/update | 单文档 preprocess helper begin，processed显式batch，helper终态 |
| `mark_downloaded_processed_rebuild_required` + CN/SEC adapters | summary后多个 processed markers | adapter为一次短 publication owner；函数显式接收 batch，不自行 begin |
| `run_cn_download_stream_impl` | company meta；rebuild delegation | workflow对 company meta短 transaction唯一负责；rebuild逐文档另有明确 owner，不把远端 discovery包进长事务 |
| `_commit_cn_filing_storage_batch` / `_commit_cn_filing_metadata_batch` | reset、incomplete source、PDF/Docling blobs、final source、processed marker | 改用 host batching repo begin；删除 incomplete helper；batch传给 blob/final source/processed；当前 helper保持每文档唯一 commit/rollback owner |
| `rebuild_cn_download_artifacts` / `_rebuild_single_cn_download_document` | update + replace source meta | 每个需变更文档一个 batch；收敛为一次 final source mutation并传 batch；不做 whole ticker长事务 |
| CN `upload_filing_stream` / `upload_material_stream` | upload company meta + `DoclingUploadService` source/blob/delete | company meta write是一个outer workflow拥有的短transaction；每个document的Docling write是另一个由top-level upload caller开启和终结的短transaction。company meta已commit而某document失败是可重试的分离publication unit，不做跨transaction rollback，不引入通用callback/profile/framework |
| `DoclingUploadService` | internal begin、reset、stage ack、blob、final source、delete | `_handle_storage_write(..., *, batch: BatchToken)`（或等价storage-write入口）只消费required caller batch；删除内部begin/commit/rollback，直接构造handle、blob-first、final source一次；cancel/exception返回给caller，由caller在commit开始前rollback |
| `run_download_stream_impl` | SEC company meta；最终 registry save + stale cleanup | company meta短 transaction一个 owner；末尾 maintenance transaction统一save+cleanup；不把全部网络/filing循环塞进一个 batch |
| `run_download_single_filing_stream` | source begin、stage helper、downloader store callback、staged XBRL read、final source、processed marker | 单 filing workflow唯一 begin/commit/rollback；batch传给 source/blob/downloader callback/processed；XBRL只走显式 staged read |
| `SecDownloader.download_files_stream/download_files` | 调用 `store_file(filename, stream)` | 两个downloader API都新增required keyword-only `batch: BatchToken`；每次调用callback都使用 `store_file(filename, stream, batch=batch)`，不得capture或查找batch |
| `sec_download_persistence.build_store_file` / rejected variant | `partial`隐藏 repo/handle，当前 callback无 batch | 返回callback的精确contract为 `(filename: str, stream: BinaryIO, *, batch: BatchToken) -> FileObjectMeta`；底层 `_store_file_callback(repository, source_handle, filename, stream, *, batch)` 与 rejected variant以keyword-only `batch=batch`调用repository。`partial`只可绑定repository/handle/ticker/document等非authority输入 |
| `persist_rejected_filing_artifact` | rejected blob callback + artifact upsert | 单 rejected artifact唯一 begin/commit/rollback owner；download stream/legacy path都显式传播 batch |
| `sec_download_state._save_rejection_registry` / `_cleanup_stale_filing_dirs` | maintenance callback | callback签名显式 batch；lifecycle只在 outer workflow，不在callback |
| `rebuild_download_artifacts` / `rebuild_single_local_filing` | source update + replace | 每个需写文档一个 batch；收敛一次 final source mutation；host batching显式传入 |
| `reconcile_active_6k_primary_documents` | source primary update + processed marker | standalone composition创建一个repository set和batching/source/processed/company wrappers；每个变更文档一个 batch；lambda不得 capture batch，改为显式参数/helper |
| SEC upload filing/material workflows | company upsert + Docling upload | top-level upload flow唯一 lifecycle owner；batch显式进入company helper和Docling service |
| wrappers/core internal manifest methods | 各 public mutation透传、manifest mutation | wrapper必须required batch并传给同一 core；core entry统一resolve active state；private manifest helper接显式 state/batch/path，不查询ambient |
| 当前无 production caller 的 mutators | blob delete、processed delete/clear、filing clear、source restore | public contract仍required batch；owner tests覆盖无token拒绝，未来caller不能获得auto-batch |

所有 closure审计以“authority是否显式”为准：允许现有下载器callback绑定 repository/handle/ticker/document identity；禁止绑定/capture batch。由于普通 `Callable[[...]]` 不能表达keyword-only参数，downloader/persistence边界使用一个窄callable protocol或等价严格类型来声明上述精确 `__call__` 签名；不引入callback framework。每次 callback invocation必须把batch作为required keyword实参传入，随后repository method以keyword-only `batch=`消费；测试断言该invocation token与top-level lifecycle token同值。

## 7. 三 slice 累计 breaking cutover

### 7.0 原子 cutover 规则

S1 改 public required signature后，当前 producer会立即类型错误；项目又禁止 optional/default/compat seam。因此：

- S1、S2、S3 是同一个 R06 breaking cutover 的累计 working-tree checkpoints，不是独立sub-WU、release、accepted commit或green state；不设置固定diff行数、文件数等magic gate。
- 每个slice完成后，在下一slice开始前执行Controller scope/focused-test验证与AgentMiMo/AgentDS双路cumulative slice review。验证只要求本slice owner contract与当前可运行的focused tests；因producer尚未propagation而预期存在的repo-wide类型错误必须如实记录，不能包装为绿色或通过。
- 每个cumulative slice review的accepted findings都必须在当前working tree修复并完成双路re-review后才能进入下一slice；这些gate不生成accepted commit，也不独立接受slice。
- S3完成全部propagation后，在同一累计final tree上分别运行S1/S2/S3完整focused tests和coverage归因，再运行全量pyright/Ruff/diff/scans；随后仍对完整R06 diff执行统一双路code review、fix/re-review，只有complete final tree可进入accepted local commit裁决。
- 不创建临时 compatibility commit，不保留 source lifecycle facade，不以 `# type: ignore`、cast、fake默认 token维持中间状态。
- Controller按semantic owner、实际diff与reviewer可审性裁决是否需要收窄某个slice实施任务，但不得用magic行数或拆出兼容中间版本；本plan仍不提前授权implementation。

### 7.1 R06-S1 — storage 显式 transaction protocol/core

#### Production allowlist

- `dayu/fins/domain/document_models.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/_fs_storage_core.py`
- `dayu/fins/storage/_fs_repository_factory.py`
- `dayu/fins/storage/_fs_blob_core.py`
- `dayu/fins/storage/_fs_company_meta_core.py`
- `dayu/fins/storage/_fs_maintenance_core.py`
- `dayu/fins/storage/_fs_processed_core.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/storage/fs_batching_repository.py`
- `dayu/fins/storage/fs_company_meta_repository.py`
- `dayu/fins/storage/fs_document_blob_repository.py`
- `dayu/fins/storage/fs_filing_maintenance_repository.py`
- `dayu/fins/storage/fs_processed_document_repository.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/storage/local_file_source.py`：仅 online published `Source.open()` mutex guard；是直接在线空窗证据要求的 refinement，不得实现 R07 snapshot/revision。

#### Tests allowlist

- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`

#### Contract handoff to S2

- S1交付最小token、internal registry resolver、shared-core rejection、全事务writer mutex、独立跨进程短时publication swap/read guard、最小journal和required mutation protocol。
- S1同时删除 `_execute_with_auto_batch`、`_BATCH_OWNER_CONTEXT`、`_bind_batch_owner`、`_unbind_batch_owner`、`_require_batch_owner`、`_current_execution_scope_id`、`asyncio.current_task()`/thread-id owner推断及相关ambient helper；全部private manifest helper显式接收resolved internal active state/batch/path，不保留implicit mutation入口。
- S2只能消费该 resolver/state/path；不得另建 source-specific transaction state或用 meta确认batch。

#### Tests

```bash
.venv/bin/python -m pytest -q \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_storage_provider.py \
  -k 'batch or token or owner or recovery or atomic or concurrent'
```

必须覆盖：public token精确字段；explicit child task/thread成功；unknown/altered/closed/ticker mismatch/cross-core拒绝；same-ticker writer mutex排斥第二writer；`batch_locks/<ticker>.lock`与独立`batch_locks/<ticker>.publication.lock`都不授权mutation；journal字段闭集且不含publication lock/relative containment；每个recovery phase；两个独立repository core/进程共享同一publication lock；outer guarded read + private unguarded helper无自死锁；published read在长staging/validator barrier不被writer mutex阻塞且读取old，并在两个rename barrier被swap guard阻塞、终态只见old/new；writer/recovery锁顺序无反向嵌套。

coverage：对S1实际 changed production files逐文件核对 `coverage json` >=80%；`--fail-under=80` 总体值不能替代逐文件检查。低于80只能在上述owner tests补分支，不得用pragma/omit或测试直调私有字段伪造覆盖。

### 7.2 R06-S2 — complete source 单 commit 可见点

#### Production allowlist

- S1中的 `document_models.py`、`repository_protocols.py`、`_fs_storage_infra.py`、`_fs_blob_core.py`、`_fs_source_document_core.py`、`fs_document_blob_repository.py`、`fs_source_document_repository.py`。
- 其它S1 storage文件只有实际 required-batch透传或validator共享事实命中时可有同一累计diff；不得顺手重构。

#### Tests allowlist

- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`

#### Contract handoff to S3

- blob-first staging不再需要meta ack；producer可直接构造identity handle。
- final source mutation必须一次提供完整meta/files/primary/provenance；commit validator是唯一资格 owner。
- S3不得重写validator、不在producer保留stable re-entry或 `ingest_complete=false`。

#### Tests

```bash
.venv/bin/python -m pytest -q \
  tests/fins/test_fins_storage_provider.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  -k 'source or blob or incomplete or staging or commit or rollback or provenance or primary or manifest'
```

替换旧 ack/stable-retry tests，必须覆盖：blob先写成功但published read absent；complete final source commit后meta/files/blob/primary/provenance/manifest一致；缺meta、空/重复/dangling files、缺primary、非法provenance、false completion、symlink/escape均不能commit；rollback/cancel/crash不见half source；published readers在online rename barrier不见missing。

coverage：S2所有实际 changed production file逐文件 >=80%，尤其validator每个失败格、old-absent/new-source、logical delete/restore、filing/material两种manifest都要命中。

### 7.3 R06-S3 — 迁移所有真实 producer / callback 并证明零残留

#### Production allowlist（调用图 refinement后的闭集）

- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/service_runtime.py`
- `dayu/fins/downloaders/sec_downloader.py`
- `dayu/fins/pipelines/cn_download_protocols.py`
- `dayu/fins/pipelines/cn_download_company_meta.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_rebuild.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/sec_6k_primary_document_repair.py`
- `dayu/fins/pipelines/sec_company_meta.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/sec_download_persistence.py`
- `dayu/fins/pipelines/sec_download_source_upsert.py`
- `dayu/fins/pipelines/sec_download_workflow.py`
- `dayu/fins/pipelines/sec_download_state.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/sec_rebuild_workflow.py`
- `dayu/fins/pipelines/sec_upload_workflow.py`
- `dayu/fins/pipelines/upload_company_meta.py`

其中 `service_runtime.py`、`sec_downloader.py`、`cn_download_protocols.py`、`cn_pipeline.py`、`sec_download_workflow.py`、`sec_download_state.py`、`sec_pipeline.py`、`sec_upload_workflow.py` 不在 umbrella R06 closed row，但两路plan review与Controller已根据直接调用图接受为required allowlist：它们分别拥有新的batching composition、host protocol、download callback invocation、maintenance callback或upload top-level lifecycle；不加入就只能保留Source lifecycle facade、capture batch或让production无法类型检查。allowlist接受不等于implementation授权。

S3必须在 `service_runtime.py`、`cn_pipeline.py`、`sec_pipeline.py`、`sec_6k_primary_document_repair.py` 四个真实composition root首次实例化production `FsBatchingRepository`，并与既有source/blob/processed/company/maintenance wrapper共享同一个`_FsRepositorySet`/core；不得只在测试或单一入口补装配。

#### Tests allowlist

- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_docling_upload_service_integration.py`
- `tests/fins/test_sec_downloader.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_sec_pipeline_download_stream.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_sec_pipeline_upload_material_stream.py`
- `tests/tools/test_combined_tools_acceptance.py`
- S1/S2四个storage/read test files（只为required signature fixture迁移与完整publication回归，不改read business contract）。

#### Contract handoff to R07

- S3交付所有production mutation required batch、唯一top-level owner、callback invocation-time显式token、无ambient/auto-batch/ack；implicit/ambient helper已由S1删除，S3只做完整调用图propagation与零残留证明。
- R07可假设published source始终完整、public read不进rename空窗；R07仍独占跨多次read的snapshot/revision、opaque identity mapping、retry与cache contract。

#### Tests

```bash
.venv/bin/python -m pytest -q \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_cn_download_runtime.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_docling_upload_service_integration.py \
  tests/fins/test_sec_downloader.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_sec_pipeline_download_stream.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/tools/test_combined_tools_acceptance.py
```

必须逐flow断言 begin/commit/rollback owner计数，helper/callback收到同一token且downloader每次invocation显式传入，cancel/failure在commit前只rollback一次，commit开始后caller不二次rollback；CN company meta与每个Docling document是分离短transaction，company成功/document失败可重试且不跨transaction rollback；CN/SEC/Docling blob-first、final source一次；rebuild/6-K/source+processed同batch；四个production composition root均使用shared-core `FsBatchingRepository`；company/maintenance独立publication unit边界明确；无 mutation在batch外成功。

coverage：在上述完整producer矩阵上收集S3实际 changed production files，逐文件 >=80%；`ingestion_runtime.py`、CN/SEC pipeline、SEC downloader等大文件也不豁免。若低于80，只能在对应test allowlist补真实owner分支；不得用总体coverage、mock-only delegation断言或omit掩盖。

## 8. Aggregate validation、scans 与 smoke

本节完整命令只在最终累计 R06 tree运行；S1/S2/S3 cumulative reviewability gate按§7.0运行当时可执行的focused tests并如实记录尚未propagation造成的预期类型错误，不得在不类型完整的中间tree宣称pass。

### 8.1 Focused + full tests

先分别重跑§7.1/7.2/7.3命令，再运行：

```bash
.venv/bin/python -m pytest -q tests/fins tests/tools/test_combined_tools_acceptance.py
.venv/bin/pyright
```

pyright必须 `0 errors`；不得新增、扩散或ignore。任何changed owner内旧错误一并修复。

### 8.2 Ruff

最终所有changed Python files运行 scoped `python -m ruff check <changed files>` 必须全绿；不运行整文件 formatter制造unrelated churn。另运行只读全量：

```bash
.venv/bin/python -m ruff check dayu tests utils
```

全量只按§10 baseline六字段比对，不借R06清理无关模块；任何数量增加、规则/节点/指纹变化或changed owner命中都stop。

### 8.3 Source / propagation scans

```bash
rg -n 'ContextVar|_BATCH_OWNER_CONTEXT|owner_scope_id|owner_token|current_task|get_ident|thread.*ident|_execute_with_auto_batch|auto_batch' dayu/fins/storage tests/fins
rg -n 'stage_source_document|_STAGING_STABLE_META_FIELDS|staging.*ack|acknowledge_source|ingest_complete[^\n]*false|ingest_complete[^\n]*False' dayu/fins tests/fins
rg -n '\.(begin_batch|commit_batch|rollback_batch)\(' dayu/fins tests/fins
rg -n '\.(upsert_company_meta|create_source_document|update_source_document|delete_source_document|reset_source_document|restore_source_document|replace_source_meta|create_processed|update_processed|delete_processed|clear_processed_documents|mark_processed_reprocess_required|delete_entry|store_file|clear_filing_documents|save_download_rejection_registry|store_rejected_filing_file|upsert_rejected_filing_artifact|cleanup_stale_filing_documents)\(' dayu/fins tests/fins tests/tools/test_combined_tools_acceptance.py
rg -n 'owner_pid|hostname|target_dir|staging_root_dir|staging_ticker_dir|backup_dir|journal_path|ticker_lock_path' dayu/fins/storage/_fs_storage_infra.py tests/fins
```

判定：第一、二条旧authority/ack目标零命中（completed `ingest_complete=True` 可逐条归属）；lifecycle命中只能在 batching protocol/wrapper与inventory列出的top-level owners；每个mutation命中人工逐条确认keyword `batch=`或callback显式batch参数，不能靠regex零命中代替人工调用图审计；journal物理字段只能存在internal active state，不能出现在public token/journal payload。

再执行 allowlist diff：

```bash
git diff --name-only 9c07b88d --
git diff --check
```

最终implementation diff只可含§7闭集、`dayu/fins/README.md`、`tests/README.md`及该阶段授权artifacts。任何其它production/test文件先停回plan review/Controller，不现场扩域。

### 8.4 Fresh filesystem crash-phase + concurrent-reader smoke

smoke写在 `tests/fins/test_fins_storage_atomicity.py`，使用fresh `tmp_path`、真实filesystem、独立repository core/进程，不加production debug flag：

1. 构造完整A：source meta + 至少两个blob + primary + provenance + manifest + processed artifact；关闭repository后重开验证A完整。
2. child writer在batch staging构造完整B；用test-only barrier分别停在validator前、target已backup、staging已target、COMMITTED journal后/cleanup前。
3. 每个precommit phase让child进程硬退出，不运行finally；parent创建fresh repository触发recovery，观察只能完整A或（仅committed）完整B，不能missing/mixed。
4. 在线并发测试不杀writer：先把writer停在长staging与validator barrier，另一进程用独立repository core调用meta/manifest/blob bytes/processed read与 `LocalFileSource.open()`时必须及时完成并只见完整A，证明writer全事务mutex没有阻塞reader；再在两次rename每个barrier启动同样reader，reader必须通过`batch_locks/<ticker>.publication.lock`等待，不能提前返回missing/half，swap完成或失败恢复并释放guard后结果逐项属于完整A或完整B。另用会组合多个read的public entry证明outer只获取一次guard、private unguarded helper不自死锁。
5. 循环reader/writer多轮，但同步依赖Event/barrier与deadline，不以sleep碰运气；输出phase、reader阻塞/完成、journal和最终tree摘要。
6. 另测原target不存在的新source：precommit crash/rollback仍是absent，commit后是完整B；不得留下空ticker/half source。

在线reader测试失败不能用recovery成功豁免。若现有filelock无法把 `LocalFileSource.open()`纳入guard，implementation必须停回storage owner设计；不得把该case延期给R07或仅缩小测试。

## 9. README 触发决策

- `dayu/fins/README.md`：必须更新。先遵守其 `Agent更新约束`，只写implementation完成后的current contract：explicit BatchToken、batching-only lifecycle、required mutation batch、published-only reads、blob-first staging、complete-source commit、全事务writer mutex、短时publication swap guard与recovery；删除现有 acknowledgement/ambient owner说明。不写计划、测试清单或R07未来路线。
- `tests/README.md`：必须更新。只记录当前test suite覆盖explicit authority、complete publication、online rename barrier和crash recovery，不写gate/review过程。
- 根 `README.md`：无用户命令、安装、输出通道、workspace位置或排障变化，预期no diff。
- `dayu/README.md`：没有改变 `UI -> Service -> Host -> Engine` 分层，预期no diff。
- `docs/fins/design.md`：已是本次稳定设计truth，当前plan/implementation不机械改写；若代码正确实现需要改变其owner决策，立即stop回Controller。

## 10. Baseline failure registry

本plan只复用 `docs/host/issues-implementation-control.md` 的唯一baseline机制，不创建平行registry。base probe：

- `.venv/bin/pyright`：`0 errors, 0 warnings, 0 informations`。
- `.venv/bin/python -m ruff check dayu tests utils`：`Found 162 errors`；这是只读全量baseline计数，最终仍须逐六字段匹配，计数相同本身不够。
- 对§7计划changed Python闭集的scoped Ruff当前有10项；这些文件将在R06修改，故不能作为 inherited failure保留，最终必须清零：

| path / stable location | rule | text fingerprint | base SHA |
| --- | --- | --- | --- |
| `dayu/fins/ingestion_runtime.py:26:20` | F401 | `typing.TYPE_CHECKING imported but unused` | `9c07b88d` |
| `dayu/fins/ingestion_runtime.py:2499:29` | F841 | `Local variable exc is assigned to but never used` | `9c07b88d` |
| `dayu/fins/pipelines/cn_download_source_upsert.py:21:5` | F401 | `SourceHandle imported but unused` | `9c07b88d` |
| `dayu/fins/pipelines/sec_download_filing_workflow.py:12:36` | F401 | `SourceKind imported but unused` | `9c07b88d` |
| `dayu/fins/pipelines/sec_download_workflow.py:13:36` | F401 | `SourceKind imported but unused` | `9c07b88d` |
| `dayu/fins/pipelines/sec_pipeline.py:147:44` | F401 | `normalize_ticker imported but unused` | `9c07b88d` |
| `dayu/fins/storage/_fs_processed_core.py:6:20` | F401 | `typing.Optional imported but unused` | `9c07b88d` |
| `dayu/fins/storage/_fs_source_document_core.py:9:20` | F401 | `typing.Any imported but unused` | `9c07b88d` |
| `tests/fins/test_fins_ingestion_runtime.py:54:5` | F401 | `FinsObservationHandle imported but unused` | `9c07b88d` |
| `tests/fins/test_sec_downloader.py:10:16` | F401 | `io.BytesIO imported but unused` | `9c07b88d` |

六字段中的exact command是§8.2 scoped changed-file Ruff command；test/node为上表path，error type/rule、stable location、fingerprint与base SHA如表。实现触及这些文件时只做必要lint hygiene，不授权其它语义清理。full Ruff其它failure只有exact command、node、rule、stable frame、text fingerprint、base SHA六项均同且与R06 propagation无交集才可继承；任一新增/扩散立即stop，不能登记成新baseline。

## 11. Stop conditions 与 residual boundary

任一条件命中立即停止并交Controller，不用fallback/兼容shim继续：

1. implementation直接调用图要求超出§7.3已接受closed allowlist的新production/test文件，或四个composition root仍不能在shared core上表达required batching composition/callback。
2. 任何producer不能把一个完整source及相关blob/processed mutation放进一个显式batch，或需要恢复 `ingest_complete=false` / stable re-entry。
3. online reader在两次rename barrier返回missing/half，或解决方案要求提前实现R07 selector/snapshot/revision/opaque ID。
4. 正确source validator owner不清，或需要read runtime/producer重复校验/补偿。
5. 需要optional/default batch、Source lifecycle facade、captured batch closure、ContextVar/task/thread检查、`hasattr/getattr`或跨core兼容。
6. journal/recovery需要PID/hostname/absolute path或读取未经containment验证的locator。
7. retained containment/symlink/atomic write、commit failure primary-cause、cancellation或recovery安全行为回退。
8. changed production file coverage <80%、pyright非零、scoped Ruff非零、新/扩散baseline、allowlist外diff或README current-truth无法同源。
9. 实现触及R07—R11、Issue 142/151/175/177/178、统一authorization、旧schema migration/compatibility。

R06完成后仍由R07拥有的唯一residual是“跨多个repository call或长生命周期processor消费的同版本snapshot/revision”，包括§4.2列出的8个production文件/9个`.materialize()`调用点在取得裸`Path`后的延迟或多次读取。`source_snapshot.py`通过一次`Source.open()`复制稳定spool，不是独立裸路径consumer。该residual不能削弱R06的一次published read/open在线old/new完整性，也不能作为rename空窗失败的借口。

## 12. Review gate 与 R07 handoff

本次plan fix artifact完成后的唯一授权动作：

```text
Controller验证R06-PF-01..08 plan fix与scope
  -> AgentMiMo + AgentDS对fixed complete plan做两路独立完整re-review
  -> Controller accepted-plan decision/local commit
```

在上述闭环前：不得声称plan accepted，不得implementation、修改control/design truth、stage/commit/push/PR。两路re-review必须特别验证：

- umbrella外allowlist refinement是否为required closed set；
- writer transaction/ticker mutex与独立`batch_locks/<ticker>.publication.lock`是否严格分离；outer guarded entry/private unguarded helper是否无ambient marker、自死锁和反向锁序；swap guard是否只覆盖commit/recovery物理切换短窗和一次published read/`LocalFileSource.open()`，长事务是否保持published read畅通，且没有偷做R07；
- callback精确签名是否让batch在每次downloader invocation显式传入而非capture；
- validator是否固定遍历全staged ticker tree并双向校验manifest；
- S1是否删除全部implicit/ambient authority，S3是否只做propagation；
- CN company meta与逐document Docling是否为分离短transaction，四个production composition root是否新装配shared-core `FsBatchingRepository`；
- 三slice累计reviewability gate是否无magic行数、compat中间态、green/accepted中间声明或中间accepted commit。

未来R06 completion handoff给R07必须包含：accepted plan/implementation SHA、最终production/test allowlist、public token与mutation signatures、deleted ambient/ack contracts、shared-core/composition图、validator contract、writer mutex/swap guard边界、长事务reader畅通/online swap/crash phase证据、逐文件coverage、full pyright/scoped+full Ruff baseline delta、diff/scans、README decision、双路reviews及全部finding状态。Controller明确进入R07前不得开始revision/snapshot/opaque-id设计或实现。

## 13. 本 plan gate 最终 stop

本文件与指定plan-fix artifact写完只执行artifact whitespace、`git diff --check`、scope/SHA与`git status --short`核验，确认只写入这两个允许文件。随后停止并向Controller报告；不修改product/test/README/control/design/既有review artifact，不stage/commit/push。
