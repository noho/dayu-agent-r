# WU-SEMANTIC-OWNERSHIP-01 R06 plan review Controller 裁决

## 1. 裁决对象

- umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01`
- internal remediation sub-WU：`R06 — Fins 显式 transaction 与 complete-source publication`
- immutable plan：`docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`
- reviewed SHA-256：`f147079bd9870f14402feb0782a3568109ccb710fa67d3bfe97add120f2336cd`
- base commit：`9c07b88d9e855f19f0b828f671022119cc5599a1`
- 第一路 review：`docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-review-mimo.md`
- 第二路 review：`docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-review-ds.md`
- Controller entry validation：`docs/reviews/wu-semantic-ownership-01-r06-plan-entry-controller-validation.md`

本裁决只决定 plan findings。它不修改产品代码，不接受当前 plan，不授权 implementation、commit、push 或 PR。

## 2. Controller 独立结论

两路 review 均以直接代码证据确认 R06 动机成立：public `BatchToken`、ambient task/thread authority、implicit auto-batch、incomplete source acknowledgement 与两次 rename 在线空窗确实同时存在；把 transaction authority、complete-source publication、writer mutex、publication swap guard、journal/recovery 收回 `dayu.fins.storage` 是正确 owner 修复，不是局部止血。

当前不存在与 controller discussion、`docs/fins/design.md` 或用户既定裁决直接矛盾的证据。两路提出的问题都可在既定 R06 owner boundary 内裁决，无需用户重新确认产品问题。

## 3. Accepted plan fixes

### R06-PF-01 — publication swap guard 必须是独立的跨进程短窗互斥

**来源**：MiMo `R06-REVIEW-002`；DS `F-DS-001`。

**裁决**：接受并合并。

Plan 必须明确：

1. guard 是按 normalized ticker 分片的跨进程文件锁，复用 `dayu.runtime.filelock` / `RuntimeFileLockToken` 基础能力；锁路径从固定 storage root 与 ticker 唯一派生，使用现有 `batch_locks/<ticker>.publication.lock`，不得复用长时间持有的 writer `batch_locks/<ticker>.lock`，不得持久化进 journal 或 public token。
2. guard 只是 online physical publication/read exclusion，不是 mutation authority；它不读取、验证或推断 `BatchToken`。
3. public published read entry 获取一次 guard，并在本次 meta/list/bytes I/O 完成后释放；内部 path/read core 使用显式 private unguarded helper，已持锁的 outer entry 不调用会再次获取非重入文件锁的 public read。禁止用 task/thread-local、ambient marker 或 public compatibility 参数表达“已持 guard”。
4. `LocalFileSource.open()` 获取同一 guard，到 fd 成功打开或打开失败后释放；成功 fd 的后续读取不继续持 guard。
5. commit/recovery 只在触碰 target/backup/staging 的物理切换与失败恢复短窗持 guard；长下载、Docling、staging、validator 与普通 pre-commit rollback 不持 guard。writer mutex 与 publication guard 的 acquire/release 顺序必须在 plan 与测试中闭合，禁止反向嵌套。

这关闭多 core/多进程读者在 rename 空窗不受保护以及嵌套 public read 自死锁两个问题，同时不提前实施 R07 snapshot/revision。

### R06-PF-02 — `materialize()` 缺口显式交给 R07，R06 不发明新 contract

**来源**：MiMo `R06-REVIEW-001`；DS `F-DS-002`。

**裁决**：接受并合并。

Plan 必须根据实际调用图记录所有当前 production `materialize()` consumers，至少覆盖 `dayu/documents/processors/bs_processor.py`、`docling_processor.py`、`markdown_processor.py`、`dayu/fins/processors/sec_processor.py`、`bs_report_form_common.py`、`bs_six_k_processor.py`、`source_text.py`、`dayu/fins/pipelines/sec_fiscal_fields.py`，并核对 `source_snapshot.py` 是否是当前调用图中的独立 consumer/adapter 后如实列入。

R06 只承诺一次 `Source.open()` 的 stable fd old-or-new；`materialize()` 返回裸 `Path` 后的延迟/多次读取没有 snapshot consistency，继续由 R07 storage revision/snapshot 唯一拥有。R06 不改变 `materialize()` public contract，不增加 path copy、fd wrapper、lease 或 revision API，也不得声称已经覆盖全部 Source read。

### R06-PF-03 — downloader/persistence callback contract 必须 code-generation-ready

**来源**：MiMo `R06-REVIEW-003`，合并其 `R06-REVIEW-009`；DS `F-DS-006` 中的 callback 证据。

**裁决**：接受签名澄清；拒绝“不能继续使用 `functools.partial`”这一错误推论。

Plan 必须明确 persistence callback 的目标 callable contract 为等价于：

```python
(filename: str, stream: BinaryIO, *, batch: BatchToken) -> FileObjectMeta
```

`build_store_file` / rejected variant 可以继续以 `partial` 绑定 repository 与 source handle 等非 authority 输入；`batch` 不得被绑定/capture，而由 `SecDownloader.download_files_stream` / `download_files` 的 required keyword 参数在每次 invocation 显式传入，随后 repository mutation 继续使用 keyword-only `batch=batch`。测试必须断言 invocation token 与 top-level lifecycle token 同一。

### R06-PF-04 — complete-source validator 选择全 staged tree，并声明新 manifest invariant

**来源**：MiMo `R06-REVIEW-006`；DS `F-DS-003`。

**裁决**：接受。选择全 staged ticker tree validation，不采用 touched-identities tracking。

R06 当前事务从完整 published ticker tree copy-on-stage，commit 又发布完整 ticker tree。全 staged tree 是无需第二套 touched-set 状态、闭包证明或 fallback 的最小正确实现。Plan 必须删除“两种策略实现时再选”的表述，并明确：

- commit validator 遍历完整 staged ticker tree；
- source→manifest 与 manifest→source 双向一致性是新的 storage-owned commit-time invariant，不是 read 层补偿；
- `primary_document` 必须精确命中 files manifest 和物理文件，禁止 first-file fallback；
- files 非空是当前 complete-source publication contract 的有意规则，当前 producer 都生成 blob；未来 meta-only source 需求必须先修改 owner contract，不能靠例外绕过 validator。

### R06-PF-05 — S1 即删除 implicit/ambient authority

**来源**：MiMo `R06-REVIEW-007`；DS `F-DS-005` / `F-DS-010` 的已覆盖证据。

**裁决**：接受 MiMo 的时序修正；DS 两项保持 no-action。

S1 required mutation protocol/core cutover 时必须同时删除 `_execute_with_auto_batch`、`_BATCH_OWNER_CONTEXT`、`_bind_batch_owner`、`_unbind_batch_owner`、task/thread owner 推断以及相关 ambient helper。private manifest helper 显式接收 resolved internal active state/batch/path；不得把 implicit authority 删除推迟到 S3，也不得为累计 breaking tree 添加兼容 seam。S3 只负责全部真实 producer/callback propagation 与最终零残留证明。

### R06-PF-06 — CN upload 与 Docling 使用分离的短 transaction

**来源**：DS `F-DS-004`；MiMo mandatory question 4。

**裁决**：接受 DS 裁决，关闭 plan 内“review 再决定”的空位。

Plan 必须明确：CN upload 的 company meta write 是一个短 transaction；每个 document 的 Docling upload 是另一个由 top-level upload caller 开启并终结的短 transaction。`DoclingUploadService` 只消费 required caller `batch`，删除内部 `begin_batch` / `commit_batch` / `rollback_batch`。company meta commit 成功而某个 Docling document 失败是可重试的分离 publication unit，不做跨 transaction rollback，不引入通用 callback/profile/framework。

### R06-PF-07 — `FsBatchingRepository` 是新的 production composition，不是既有 wiring

**来源**：DS `F-DS-007`；MiMo `R06-REVIEW-011`。

**裁决**：接受澄清；相关 allowlist refinement 全部接受。

Plan 必须明确：当前 production 没有实例化 `FsBatchingRepository`；S3 在 `service_runtime.py`、`cn_pipeline.py`、`sec_pipeline.py` 与 standalone `sec_6k_primary_document_repair.py` 的真实 composition root 新建该 wrapper，并与 source/blob/processed/company/maintenance wrappers 共享同一个 `_FsRepositorySet` / core。不得从 source repository 反射、cast 或拆出 batching core。review 已确认这些路径及 downloader/protocol/workflow callback paths 是 required allowlist，不是无关扩域。

### R06-PF-08 — S1/S2/S3 增加 cumulative reviewability gates，最终统一 review 才能接受

**来源**：DS `F-DS-006`。

**裁决**：接受 reviewability 原则，拒绝没有项目证据的“约 1500 行”魔法阈值。

Plan 必须明确：S1、S2、S3 是同一个 R06 breaking cutover 的累计 working-tree checkpoints，不是独立 sub-WU、release、accepted commit 或 green state。每个 slice 完成后，在下一 slice 实施前执行 Controller scope/focused-test 验证与 MiMo/DS 双路 cumulative slice review；只要求当前 slice owner contract 与可运行的 focused tests，不把因尚未 propagation 的预期类型错误包装成绿色。所有 accepted slice findings 必须修复并 re-review；S3 完成后仍必须对完整 R06 diff 执行统一双路 code review、fix/re-review，只有完整 final tree 才能 accepted local commit。

不采用固定 diff 行数作为 gate。Controller 以 semantic owner、实际 diff 与 reviewer 可审性裁决是否需要进一步收窄实现任务，但不得拆出兼容中间版本。

## 4. No-action / rejected-as-finding

| 来源 | 裁决 | 理由 |
| --- | --- | --- |
| MiMo `R06-REVIEW-004` | no-action | plan 已将 published XBRL read 与 required-batch staged XBRL read 分开。 |
| MiMo `R06-REVIEW-005` | no-action clarification | files 非空规则由 R06-PF-04 明确为有意 contract，不是当前 blocker。 |
| MiMo `R06-REVIEW-008`、`010`、`012`-`017` | evidence confirmation | journal 收窄、adapter lifecycle、allowlist、scan、baseline、R07/deferred Issue、安全机制均与 plan 一致。 |
| DS `F-DS-005`、`F-DS-010` | no-action | plan 已要求 private manifest helper 消费显式 state/batch/path；R06-PF-05 只补删除时序。 |
| DS `F-DS-008` | reviewer correction / no-action | `_fs_processed_core.py` 已在 S1 allowlist。 |
| DS `F-DS-009` | no-action | plan 已要求 Event/barrier + deadline，具体测试 primitive 是实现细节。 |
| “publication guard 可只做进程内锁” | rejected | 不能保护另一进程 reader，直接反例成立。 |
| “用 reentrant/ambient 持锁标记解决嵌套 read” | rejected | 会重新引入 task/thread ambient 状态；R06-PF-01 采用 outer guarded entry + private unguarded helper。 |
| “R06 改造 `materialize()` 为 wrapper/copy” | rejected | 侵入 R07 snapshot/revision owner。 |
| “callback 不得继续 `partial`” | rejected | repository/handle 不是 authority；只有 batch 必须 invocation-time 显式传递。 |
| “每个 slice 以固定约 1500 行作为 review gate” | rejected | 无项目数据支持，属于魔法阈值；用 semantic owner 与实际可审性裁决。 |

## 5. Final ledger 与 next gate

- accepted plan-fix groups：`8`
- no-action / evidence-confirmed groups：`12`
- rejected-as-finding alternatives：`5`
- unresolved user/product question：`0`
- implementation blocker after plan fix：`0`（修订后须经双路完整 re-review 才能确认）

当前 verdict：`PLAN_FIX_REQUIRED`。

下一 gate 是 AgentCodex 只修订同一 R06 plan 并新增 plan-fix artifact；不得修改 product/test/README/design/control 或既有 review artifact。修订后由 Controller 验证，再由 AgentMiMo / AgentDS 对 fixed complete plan 并发 re-review。R06 implementation、accepted commit、R07-R12、Issue 142/151/175/177/178、统一 tool authorization、push 与 PR 仍未授权。
