# WU-SEMANTIC-OWNERSHIP-01 R06 累计 code review Controller 裁决

## 裁决身份

- Umbrella WU：`WU-SEMANTIC-OWNERSHIP-01`
- 内部 remediation sub-WU：R06 Fins 显式 batch authority 与完整 source publication
- Gate：累计 S1+S2+S3 双路 complete code review
- 实现基线：`d048adf7ec1135aaf575384432ebf1137f8a34f2`
- MiMo review：`docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-mimo.md`
- DS review：`docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-ds.md`
- 裁决日期：2026-07-16

## 结论

**FIX REQUIRED / 4 个 accepted fix groups / 0 个 blocking question。**

两路 reviewer 均确认 R06 的主体 contract 已收敛：54 个 production mutation 显式传递
`batch=`，callback 不捕获 authority，CN/SEC/Docling blob-first + final-once，
company/document/maintenance transaction 分离，rebuild/6-K source+processed 同 batch，
commit-start fence、四个 production composition root shared core、完整 source validator、
publication guard、containment/symlink 与 deferred-scope 边界均成立。

Controller 接受四组当前 owner 缺口：单个不可解析 journal 不能阻断后续 orphan recovery；
SEC rebuild 必须在取消与 operation/rollback 双失败时终结 capability 并保留主异常；
ingestion 两条 mutation path 必须保留 operation 主异常；关键跨进程 reader barrier 测试必须
在真实 reader lock-acquire 点同步，不能用调度时机推断阻塞。其它 finding 是 accepted plan
的直接误读、已明确 deferred 的 R07 contract、未修改的既有行为、重复下游断言或无当前
correctness 影响的实现偏好，不授权修改。

## Accepted fix groups

### R06-CR-F01 — 单个不可解析 journal 必须 fail-closed、保留 evidence，并继续同轮 recovery

- 来源：`R06-CR-DS-F01`。
- 直接证据：`_recover_single_batch_dir()` 在读取 `transaction.json` 时直接调用
  `_read_json_object()`；JSON 截断、空文件或非 object 根会抛 `ValueError`，当前异常会穿透
  `_recover_orphan_batch_dirs()` 的逐目录循环。
- Owner：`dayu/fins/storage/_fs_storage_infra.py` 的单 batch recovery entry。
- 必须修复：仅把不可解析/非 object 的 `ValueError` 归类为稳定
  `unparseable_journal`（或等价稳定 reason），skip 且保留该 token 目录；继续恢复同轮后续
  合法 orphan。不得捕获所有 `OSError` 并把真实 filesystem failure 静默降级，也不得删除
  malformed evidence、放宽 journal 字段闭集、ticker/containment/symlink 校验。
- 必须验证：至少覆盖截断或空 JSON + 同轮后续合法 orphan；断言 malformed 目录保留、
  合法 orphan 恢复、published old/new contract 不变。

### R06-CR-F02 — SEC rebuild 取消与 operation/rollback 双失败语义

- 来源：`R06-CR-MIMO-F02`、`R06-CR-MIMO-F16`，合并为同一 lifecycle-owner 修复。
- 直接证据：`_rebuild_single_document()` 只捕获 `Exception`；`KeyboardInterrupt` /
  `SystemExit` 会越过 rollback。普通 operation error 后若 rollback 也失败，rollback 异常会
  替换原始 operation error，而不是 review 所写的“被吞没”。
- Owner：`dayu/fins/pipelines/sec_rebuild_workflow.py` 的单文档 batch lifecycle owner。
- 必须修复：任何 commit 前 `BaseException` 都只 rollback 一次；rollback 成功时保留现有
  ordinary `Exception -> failed result` 行为，而取消类 `BaseException` 原样继续传播；
  rollback 也失败时以原 operation/cancellation 为主异常、rollback 为 cause并附稳定诊断，
  不得返回一个掩盖 recovery 不确定性的普通 failed result。commit 调用开始后仍不得二次
  rollback。
- 必须验证：直接覆盖 `KeyboardInterrupt` rollback + re-raise，以及 ordinary operation
  failure + rollback failure 的异常 identity/cause/note 与单次 rollback。

### R06-CR-F03 — ingestion mutation owner 保留 operation 主异常

- 来源：`R06-CR-DS-F02`、`R06-CR-MIMO-F04`，二者重复。
- 直接证据：`_store_downloaded_document()` 已用 `sys.exception()` 保留主异常，但
  `_store_rejected_filing_artifact()` 与 `_preprocess_one_document()` 的 `finally` 直接调用
  `rollback_batch()`，双失败时会用 rollback error 替换 operation error。
- Owner：`dayu/fins/ingestion_runtime.py` 的 caller-owned batch lifecycle helpers。
- 必须修复：两条缺失 path 与现有正确语义同源；允许抽取一个模块级私有 helper 供三条
  path 复用，不得跨模块建立通用 callback/facade/framework。
- 必须验证：两条 path 至少各有 operation + rollback 双失败 owner test，断言原 operation
  exception identity 保留、rollback 是 `__cause__`、诊断 note 稳定、只 rollback 一次。

### R06-CR-F04 — publication barrier test 必须同步到真实 reader lock-acquire 点

- 来源：`R06-CR-MIMO-F13`。
- 直接证据：`test_concurrent_reader_blocks_at_each_publication_rename_barrier` 的 child 在构造
  repository / 进入 public read 前就发送 `ready`，随后 parent 仅用 `poll(0.25)` 推断 reader
  已阻塞；child 在发送后被暂停时该断言可 vacuous pass。
- Owner：`tests/fins/test_fins_storage_atomicity.py` 的跨进程 online-read contract test。
- 必须修复：child 必须在实际 public reader 即将获取同一 publication guard 的调用点发送
  同步信号，然后进入真实 blocking acquire；parent 在该信号后证明结果尚未发布，再释放
  rename barrier。继续使用真实 filesystem、独立 process/core、Event/Pipe/deadline；不得加
  production debug flag、sleep 碰运气或复制 production policy 到 fake。
- 必须验证：两个 rename barrier 参数均通过，并继续断言最终只能观察完整 new/old 集合。

## Rejected / deferred finding ledger

| Finding | 裁决 | 证据与理由 |
|---|---|---|
| `R06-CR-MIMO-F01` | REJECTED — non-defect | `COMMITTED` journal 是 accepted commit point；physical `staging -> target` 后、`COMMITTED` 前仍是 pre-commit。无旧 target 时 recovery 回到 absent 正是 plan §8.4.6 的 contract；现有 `test_swapped_target_recovery_without_old_target_deletes_new_target` 直接冻结该语义。把 `SWAPPED_TARGET` 当 committed 会让 crash state 提前提交。 |
| `R06-CR-MIMO-F03` | REJECTED — unsafe remedy / retained operational residual | publication unlock 失败后删除 lock file不能释放 kernel-held fd lock，反而可能让新 inode 的 writer 并行，形成 split brain；recovery 也不能安全“接管”活进程锁。accepted S1 contract 已要求 durable commit 保留、release failure 作为 post-commit terminal error。极低概率 unlock syscall failure 的进程内存活风险仍由 `dayu.runtime.filelock` owner 承担，安全恢复点是进程终止释放 fd，不在 Fins recovery 伪造 force-release。 |
| `R06-CR-MIMO-F05` | REJECTED — contradicts accepted plan | plan §3.1 明确规定 public `BatchToken` **精确**包含 `transaction_id` 与 `ticker`；opaque 只表示 transaction-id 格式不承诺，不表示字段对 holder 隐藏。 |
| `R06-CR-MIMO-F06` | REJECTED — non-defect | authority 由当前 core registry resolver 判定；unknown/altered/ticker mismatch token 必须能构造后在 owner boundary 被拒绝。新增格式/grammar validation 会扩大 public contract，plan 明确不承诺 transaction-id grammar。 |
| `R06-CR-MIMO-F07` | REJECTED — pre-existing/out of scope | processed manifest 的业务字段投影不是 R06 引入；本轮 diff 只把 mutation 接到 caller batch/staging。没有直接当前错误输入或消费者失败证据，且不得顺手修改 unrelated 既有语义。 |
| `R06-CR-MIMO-F08` | REJECTED — pre-existing/out of scope | `DocumentSummary.from_dict` 的 `source_kind` 默认值不是 R06 修改；finding 未证明当前 R06 path 产生缺失字段。 |
| `R06-CR-MIMO-F09` | REJECTED — pre-existing/out of scope | rejected-artifact 列表跳过损坏 entry 的既有读取契约未被 R06 改变；返回 partial/warnings 会变更 public protocol，当前无设计真源授权。 |
| `R06-CR-MIMO-F10` | REJECTED — non-defect / pre-existing | `_upsert_processed` 的中间写入只发生在不可见 transaction staging；任一写失败由 caller rollback 整个 staging。要求单 helper 内再实现 transaction 会重复 storage owner，且写入顺序是既有行为。 |
| `R06-CR-MIMO-F11` | REJECTED — contradicts accepted plan | plan §5.2.6 明确：processed/company/maintenance 位于同一 staged ticker tree，但 source validator**不得**从这些消费者反推 source 完整性。扩展为全 artifact validator 是当前禁止的过度设计。 |
| `R06-CR-MIMO-F12` | REJECTED — overdesign | blob-first 是 producer sequence；storage owner 在 commit 验证最终完整 tree。commit 时无法无第二套 touched/order state 地证明历史写入顺序，而 plan 明确禁止 touched tracking；当前没有 published half-source 风险。 |
| `R06-CR-MIMO-F14` | REJECTED — test intent misread | 测试证明单个 composed public read 内部不会嵌套 acquire 自死锁，并独立证明 delayed opener 释放 guard；`max_workers=1` 是 timeout harness，不是声称两个业务操作并发。跨进程并发由 F04 所述测试拥有。 |
| `R06-CR-MIMO-F15` | REJECTED — non-material | 同一模块的内部 adapter 访问同一 concrete pipeline 的私有 repository 不改变 contract/correctness；新增 passthrough property 会形成无有效语义的 facade，AGENTS 明确禁止。 |
| `R06-CR-DS-F03` | REJECTED — composition-root misread | `CnPipeline` / `SecPipeline` 本身是 plan §3.5 指定的 production composition root；未注入时创建**一个** repository set 并供所有默认 wrapper 共享正是 required behavior。production Service 路径也显式注入同一 shared set。不得把默认 root 改成 required external batching facade。 |
| `R06-CR-DS-F04` | REJECTED — duplicate impossible-state test | storage validator 已用两个 owner negative tests 拒绝 `ingest_complete=False` 发布；preprocess missing-field direct test关闭了 Controller finding。再伪造 published false 只重复不可发布状态，不增加 reachable contract。 |
| `R06-CR-DS-F05` | REJECTED — downstream duplicate assertion | `ingest_complete=True` 由 storage normalization/validator 与 owner tests保证；要求每个 SEC pipeline consumer 重复断言会把 storage invariant复制到下游测试。 |
| `R06-CR-DS-F06` | DEFERRED — R07 owned | 跨多次 read / processor cache 的 revision-change-after-build 是 accepted plan 明确交给 R07 的唯一 residual；R06 不得提前实现或用测试冻结 R07 contract。 |

`R06-CR-DS-F01/F02` 与 `R06-CR-MIMO-F02/F04/F13/F16` 已由上述 accepted groups
完整吸收；不存在未裁决 finding。

## 修复边界与验证 gate

AgentCodex 只可修改：

- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/pipelines/sec_rebuild_workflow.py`
- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_storage_atomicity.py`
- 与 SEC rebuild / ingestion owner 直接对应的既有 R06 test files
- `tests/README.md` 仅在其 Agent 更新约束判定当前测试职责说明确需同步时
- 新的 fix artifact

不得修改 `BatchToken` public shape、processed/company/maintenance validator scope、pipeline
composition defaults、R07 revision/snapshot、Issue 142/151/175/177/178、统一 authorization，
也不得顺手修未接受的既有行为。

修复后必须运行四组 direct owner tests、R06 S1/S2/S3/aggregate affected matrix、全部 changed
production file coverage gate、full pyright、cumulative scoped Ruff、full Ruff baseline fingerprint、
mutation/ambient/ack/deferred scans、README trigger check 与 `git diff --check`。Controller 独立复核
通过后，MiMo/DS 必须对完整累计 tree 并发 re-review；在全部 accepted groups关闭前不得创建
R06 accepted commit。

## 下一 gate

`R06 cumulative code-review fix by AgentCodex`。

## READY_FOR_AGENTCODEX_FIX
