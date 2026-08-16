# UF-FIX08 existing-source-auto-repair：实施计划

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`plan`
- 日期：2026-08-16
- 当前分支：`codex/upload-filing-oracle`
- 基线提交：`5859856e46af42c9ae5a2a5c07fab1ba59dc91d3`
- goal confirmation：用户已确认
- completion status：`ACCEPTED`
- artifact path：`docs/gateflow/uf-fix08-existing-source-auto-repair-plan-20260816.md`
- blocking questions：无
- review decision：两路终审 `plan-review-20260816-123328`=`pass`、`plan-review-20260816-123436`=`pass-with-risks`；
  RF1-RF4均已修复且无 blocker，Controller 接受本 plan。RF5（低）仅作为本 work unit implementation review/deepreview focus，
  不授权 workflow cache 或 scope expansion，也不阻塞 plan acceptance
- 下一入口：`Slice 1：冻结 public integrity/state/repair contracts` implementation；当前 gate 不提交、不创建 PR

## 1. 已读取输入、直接证据与执行边界

本计划以以下完整输入和当前代码为真源：

- `AGENTS.md`，SHA-256
  `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e`。
- 已确认 goal artifact：
  `docs/gateflow/uf-fix08-existing-source-auto-repair-goal-confirmation-20260816.md`，SHA-256
  `1f58ddef4551529b2e891a9f6b6fc55d556c2e07c04d624b7367ae8ff7d99997`。
- Host 设计真源：`docs/host/design.md`，SHA-256
  `7214cbcbef21b36c9020758da8fc4c5003c3813f6ded32ed77238af58327fe06`。
- Engine 设计真源：`docs/engine/design.md`，SHA-256
  `b190e3a8ee2df84d29546ca04d4fb7d81a73877b27a3bddd04d2aaa40db17b1e`。
- accepted oracle：`docs/cli_ci_oracles.json` 的
  `upload_filing.existing-source-integrity`，文件 SHA-256
  `88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`。
- accepted finding/scenario input：`docs/cli_ci_scenarios.json` 的 `UF-FIX08` 及冻结 `UF-I01`–`UF-I10`
  观察，文件 SHA-256
  `a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`。
- 三份 plan review：`docs/reviews/plan-review-20260816-120620.md`、
  `docs/reviews/plan-review-20260816-121010.md`、`docs/reviews/plan-review-20260816-122554.md`；Controller 已接受全部
  material findings，逐项裁决与修复映射见
  `docs/gateflow/uf-fix08-existing-source-auto-repair-plan-review-adjudication-20260816.md`。
- storage public protocols、filesystem batch/publication、source integrity、filing upload state、source snapshot、
  source document/meta/manifest 实现；filing validator、upload failure、Docling preparation/publication、SEC/CN/HK upload；
  SEC/CN download Phase A/Phase B；对应 storage、snapshot、runtime、service、upload/download tests 与 README 约束。

plan/fix gate 期间只维护本 plan 与 plan-review adjudication artifact；不修改生产代码、测试、README、oracle、registry 或 evidence，不执行测试、pyright、
coverage、真实 CLI，不 commit、不 push、不创建 PR。整个 work unit 的最终交付方式仍按用户要求为当前分支本地提交且无 PR；
该提交发生在 plan review 接受后的 Gateflow commit gate，而不是本 gate。

实现期间始终禁止：

- 不修改 `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、冻结 evidence、goal artifact、Host/Engine design。
- 不执行 UF-PF08、UF-PF12 或任何真实 CLI evidence；deterministic pytest 不属于真实 evidence。
- 不实现 UF-FIX10 的一般同请求竞争 success/skip 收敛，不实现 UF-FIX11 company meta warning。
- 不实现 material upload repair；material 的既有上传、skip、update/delete 行为只做回归保护。
- 不读取、迁移或兼容旧 schema；不保留旧 enum/name/default/wrapper/re-export/dual-read。
- 不修改 registry、rejection registry、oracle、scenario 状态或 calibration record。
- 不修改 CLI 参数、tool schema、Service/Host/Engine 生命周期、EventLog、memory、trace 或调度状态机。
- 不让 workflow、snapshot、adapter、测试 fixture 或 UI 从 raw meta、异常文本、路径/目录顺序重新推断完整性或 revision。

## 2. 第一性原理判断与 root cause

问题真实存在，且不是单一 `_can_skip_upload()` 条件错误。

一个可消费 source publication 的最小事实集合是：exact ticker/source kind/document identity、可信 source meta/provenance、
opaque persisted revision、完整且唯一的文件声明、对应 regular physical files、size/digest、唯一 primary、filing upload 的
authoritative originals 与 primary Docling derived 关系，以及 source-kind manifest 与 actual tree 的双向一致。任何 consumer 只验证
其中一部分，都会把损坏状态误当成完整状态。

直接代码证据如下：

1. `source_integrity.py` 只有 `MISSING/COMPLETE/REPAIR_REQUIRED` 和三种 physical reason；
   `_classify_source_integrity_unguarded()` 对 meta、identity、provenance、primary、extra file、manifest 问题仍抛 `ValueError`，
   并未形成封闭事实。
2. `_validate_complete_source_tree()`、`_validate_complete_source_directory()` 已在 commit 前验证 manifest、meta、revision、
   provenance、files、URI、physical set、size/digest 与 primary；读取侧 classifier、snapshot 与 commit validator 却各自解析一遍，
   同一语义存在漂移。
3. `FilingUploadPublishedState` 只含 `company_meta` 与 raw `source_meta`；validator 因而只能把存在解析为 update，无法区分
   complete、repairable、unsafe，也无法携带 published revision。
4. `DoclingUploadService.prepare_upload()` 在读取 originals 和计算 fingerprint 后、Docling conversion 前执行 identical skip；
   matching fingerprint 会直接返回 skipped，即便 published original/Docling/meta/manifest 已损坏。
5. SEC/CN/HK upload 的 fresh read -> prepare -> begin batch 链路没有把 Phase A classification/revision 传入 staging；
   `_store_upload_assets()` 只根据 `previous_meta` reset，不能证明准备期间 publication 没有变化。
6. filesystem batch 已经在 begin 时复制整棵 ticker tree、持有 ticker writer reservation，并在 commit 时验证 staging，随后通过
   target -> backup、staging -> target 的 rename/journal 恢复保证 old-or-new。根因不是缺第二套事务，而是缺 storage-owned
   expected-revision staged admission。
7. source snapshot 另行解析 persisted meta/files/primary/revision；损坏 classification 与 snapshot 可消费性不是同一 owner fact。
8. download 已有 Phase A/Phase B revision comparison，可复用同一 public classification，但新增 `UNSAFE` 后必须显式 fail closed，
   不能落入“非 missing 即 reset”的旧分支。

因此 root cause 是 storage source publication integrity contract 不闭合，导致 upload published state、repair authorization、skip、
snapshot 与 publication recheck 无法消费同一真源。正确路径是先收敛 storage owner，再由 filing validator 产生唯一 repair 授权，
最后让 Docling/workflow 机械传递；不能在 skip、pipeline 或 snapshot 下游加局部 fallback。

## 3. Goal、成功信号与非目标

### 3.1 Goal 与成功信号

1. published/staged exact target 都由 storage 返回同一 `SourceIntegrityClassification`，封闭区分 `MISSING`、`COMPLETE`、
   `REPAIR_REQUIRED`、`UNSAFE`，并覆盖 identity/meta/provenance/revision、original/primary Docling、file declaration/physical
   set/size/digest、primary/derived projection 和 source-kind manifest。
2. `COMPLETE` 是 identical skip、snapshot 与 commit publication 的唯一可消费状态；`REPAIR_REQUIRED` 仅表达事实，不授权修复；
   `UNSAFE` 永远不能比较 revision、读取 raw meta、reset 或 repair。
3. 仅当 exact filing target 为 `REPAIR_REQUIRED`、requested action 精确为 `auto`、static validator 已产生非空完整
   `FinsUploadFilingFiles` 时，validated request 产生 typed `ExistingSourceAutoRepair`；`MISSING` 仍 create，`COMPLETE` 走既有
   create/update/delete/skip，显式 create/update/delete 对损坏目标失败关闭。
4. repair preparation 全量读取 authoritative primary/companions，发布全部 originals，只转换 authoritative primary，重建
   derived、fingerprint、source meta、primary pointer 与 manifest；repair disposition 存在时 matching old fingerprint 也不得 skip。
5. begin batch 后，storage 在 reset 前重新分类真实 staging；只有同 exact target、同 trusted revision/presence 且仍为
   `REPAIR_REQUIRED` 才允许 reset。missing、complete、unsafe、revision 变化均抛 typed stale failure并 rollback；不做 UF-FIX10 retry/skip。
6. repair target reset、全部 assets、final source meta、新 persisted revision、canonical source-kind manifest 与 company meta decision
   位于同一 caller-owned ticker batch；转换、stage、recheck、validation、commit、rollback 任一步失败，published tree 仍为完整 old。
7. commit 返回后 public re-read 为 `COMPLETE`，new revision 与 Phase A revision 不同；light/full snapshot、primary、files、manifest、
   requested/stored summary 和 `process_filing` 只看到同一 new source。
8. original 缺失、original digest 改变、primary Docling 缺失、meta size/digest mismatch、primary/derived projection、rebuildable
   manifest missing/mismatch 被覆盖；非法 identity/meta/revision/provenance、重复声明、extra/symlink/special file、dangling/duplicate/
   conflicting/cross-source manifest 被 `UNSAFE` typed fail closed。
9. stale、unsafe、非 auto repair 使用 `dayu.fins.upload_failure`/usage typed owner 的 bounded path-free 文案；不暴露 revision token、
   raw meta、filesystem locator、异常 repr 或 traceback。
10. download、snapshot 与 commit validator 复用同一 internal inspection；没有 consumer-local loose parsing。受影响测试、单文件
    coverage >=80%、全仓 pyright 通过，README 按职责更新。

### 3.2 非目标

- 不把所有损坏变为可修复；不能由本请求唯一重建的状态必须 `UNSAFE`。
- 不建立 repair framework、adapter、repair journal、第二套 revision 或数据库。
- 不让 storage 仅因看见 `REPAIR_REQUIRED` 自动修；action 与 local selection 的授权属于 filing request validator。
- 不改变 material upload repair 资格，不把 filing asset-role 规则扩展到 material。
- 不改变一般 download provider/retry、rejection registry 或 overwrite policy；只让新增 `UNSAFE` 明确失败关闭并共享 inspector。
- 不修改 CLI/tool schema、requested/stored count、ticker/calendar/year、UF-FIX06 converter、UF-FIX07 role/asset identity、取消或
  commit linearization。
- 不做旧 schema compatibility，不做真实 CLI post-fix evidence，不修改 registry/oracle。

## 4. Design alignment 与语义 owner

- Host design 将财报业务存取排除在 Host durable/lifecycle owner 之外；本 work unit 不借 EventLog、trace、memory 或 Host state
  保存 repair/revision。
- Engine design 只负责单次 run、Runner 与 tool loop；Engine 不访问 Fins repository，不增加 repair event/schema。
- 所有财报文档读写继续只经过 `dayu.fins.storage`；pipeline 不直接访问财报目录。
- direct upload 保持 `UI -> Service -> Fins`，Service/CLI 只投影现有 typed failure，不新增 repair 分支。
- 不触及 `dayu.runtime`；完整性、repair 与 publication 都是 Fins 业务事实。

| 语义 | 唯一 owner | 其它模块只允许做什么 |
| --- | --- | --- |
| published/staged 完整性、presence、trusted revision、closed reasons | `dayu.fins.storage` public integrity contract + filesystem inspector | download/upload/snapshot/tests 消费 typed fact |
| complete source 的 meta/provenance/files/primary/manifest canonical projection | storage 私有统一 inspector | commit/snapshot/classifier 复用 inspection，不各自解析 |
| upload fresh company/source 同版状态 | `FilingUploadStateRepositoryProtocol` implementation | validator 读取 required `source_integrity` 与仅在可信状态提供的 `source_meta` |
| repair eligibility | `validate_fins_upload_filing_request()` | CLI/Service/workflow 不重判 action、selection 或 status |
| repair disposition contract | `dayu.fins.upload_repair_contract`；唯一 producer 是 ingestion validator | Docling service 只按 discriminator bypass skip并传 expected integrity |
| originals/primary/companions/derived/fingerprint/final source | `DoclingUploadService` | converter 只产 bytes；workflow 不拼 assets |
| Phase B revision/status recheck、repair reset、canonical manifest rewrite | source repository 的 `reset_source_document_for_repair()` | workflow 只传 expected classification 与 batch，失败回滚 |
| staging complete validation、old-or-new swap/recovery | 现有 filesystem batch commit | 不新增事务、journal或 per-file publish |
| path-free public failure | `dayu.fins.upload_failure` 与现有 usage failure owner | CLI/Service/pipeline 只投影 typed reason |

Owner 已清楚，不存在需要用户选择的语义边界。

## 5. Public contract、状态与失败设计

### 5.1 `SourceIntegrityClassification`

`dayu/fins/storage/source_integrity.py` 按 fresh schema 扩展，不保留旧行为兼容：

```python
class SourceIntegrityStatus(str, Enum):
    MISSING = "missing"
    COMPLETE = "complete"
    REPAIR_REQUIRED = "repair_required"
    UNSAFE = "unsafe"
```

`SourceIntegrityReason` 冻结为以下 closed set；enum 顺序也是 `reasons` 的稳定去重顺序：

- repairable：`ORIGINAL_FILE_MISSING`、`PRIMARY_DOCLING_FILE_MISSING`、`DECLARED_FILE_MISSING`、
  `SIZE_MISMATCH`、`DIGEST_MISMATCH`、`PRIMARY_PROJECTION_MISMATCH`、`DERIVED_PROJECTION_MISMATCH`、
  `SOURCE_MANIFEST_MISSING`、`SOURCE_MANIFEST_PROJECTION_MISMATCH`。
- unsafe：`IDENTITY_UNTRUSTED`、`META_UNTRUSTED`、`REVISION_UNTRUSTED`、`PROVENANCE_UNTRUSTED`、
  `FILE_DECLARATION_UNTRUSTED`、`UNDECLARED_BUSINESS_FILE`、`UNSAFE_FILESYSTEM_ENTRY`、
  `SOURCE_MANIFEST_UNTRUSTED`、`CROSS_SOURCE_INCONSISTENCY`。

状态不变量：

- `MISSING`：exact target directory/meta locator 均不存在；`revision=None`、`reasons=()`。
- `COMPLETE`：`revision` 必填且可信；`reasons=()`。
- `REPAIR_REQUIRED`：`revision` 必填且可信；至少一个且只能包含 repairable reason。
- `UNSAFE`：即使磁盘上可解析出 token，也不对外承诺可比较 identity，固定 `revision=None`；至少一个且只能包含 unsafe reason。
  这是刻意丢弃不完整证据，防止 consumer 把部分可信 revision 当 repair authority。
- `has_same_source_publication_identity()` 只接受同 target 的 `MISSING/COMPLETE/REPAIR_REQUIRED`；任一参数 `UNSAFE` 立即
  `ValueError`，而不是返回相等或按 `None` 比较。
- `SourceIntegrityRevisionConflictError` 的语义收窄为“expected Phase A 与真实 staged target 的 presence/revision/repair status
  不再匹配”；错误文本不含 token/path。download 有界重试耗尽和 upload 零重试都复用该 typed conflict，不新增 revision 类型。
- 新增独立 storage typed failure：

  ```python
  class SourceIntegrityRepairBlockedReason(str, Enum):
      NON_TARGET_SOURCE_INCOMPLETE = "non_target_source_incomplete"
      CROSS_SOURCE_PUBLICATION_UNSAFE = "cross_source_publication_unsafe"
      CANONICAL_MANIFEST_UNAVAILABLE = "canonical_manifest_unavailable"

  class SourceIntegrityRepairBlockedError(RuntimeError):
      reason: SourceIntegrityRepairBlockedReason
  ```

  它只表达 target revision/presence 仍匹配、但 non-target/cross-source 状态使整 ticker 原子发布无法安全完成；不得与
  `SourceIntegrityRevisionConflictError` 互换，也不得携带 target/revision/path/raw reason 文本。
- `SourceIntegrityPreflightReason` 增加 `UNSAFE_PUBLICATION`；download whole-tree inventory 遇到任一 unsafe 或无法归属 target 的
  root/manifest structural corruption时，在任何副作用前抛 typed preflight error。

### 5.2 完整性分类矩阵

统一 inspector 使用以下 precedence，避免同一破坏在不同入口分类不同：

1. exact target 完全不存在且 source-kind root/manifest 没有指向该 target 的 dangling fact -> `MISSING`。
2. directory descriptor、meta locator/JSON、ticker/document/source-kind identity、persisted revision、provenance/completion 任一无法
   建立可信事实 -> `UNSAFE`；不得继续从剩余字段推断 repair。
3. `files[]` 非非空 array、entry 非 object、name/URI/size/digest/source 字段非法、name 重复或 containment 非法 -> `UNSAFE`。
4. 在读取 physical missing/size/digest reason 前先完成全部结构与 role 关系校验。任一实际业务 entry 是
   symlink/special/directory，actual regular file set 存在未声明文件，或 original/Docling identity/role 存在重复、歧义、非法关系，
   均立即 `UNSAFE`；即使同时存在 declared file missing，也不得降级为 `REPAIR_REQUIRED`。
5. 对 `source_kind=filing + source_provider=user_upload + ingest_method=upload`，要求至少一个 unique original、恰好一个 primary
   Docling entry，Docling 的 `derived_from` 精确命中一个 original 且 `original_filename` 同源，`primary_document` 精确指向该
   Docling。可由 authoritative primary 全量重建且不引入 identity 歧义的 primary/derived pointer mismatch 是 repairable；
   重复/非法 identity、多个 Docling 或无法唯一关联是 `UNSAFE`。其它 provider/source kind 只执行
   generic exact-primary 规则，避免把 user-upload schema 错加给 SEC/CN download 或 material。
6. 只有结构、role、identity 均已证明无歧义后，已声明 regular file 缺失、size 或 digest 不同才按 role 产生 repairable reason；
   已声明 original/primary Docling 分别产生对应 missing reason，其它 source file 使用 generic missing reason。
7. manifest 完全缺失是 source-kind 级 shared fact：per-target exact classification 和 whole inventory 中每个实际 source 都报告
   `SOURCE_MANIFEST_MISSING`。它不会把 sibling content 判为损坏；internal inspection 另外保留不含 shared manifest reasons 的
   `content_classification`。只有全部实际 source 的 content/meta/revision/role 均 `COMPLETE`，且 canonical items 可唯一生成时，
   该 shared reason 才属于同一次 canonical manifest rewrite 可消除的 repairable reason。target item 缺失或只与该 target
   canonical projection 不同，为
   `SOURCE_MANIFEST_PROJECTION_MISMATCH`。
8. manifest ticker/doc identity/shape 非法、duplicate/dangling/conflicting item，或非 target source 的 projection/physical state 同时
   损坏，为 `UNSAFE`；不得用 selected target repair 掩盖 cross-source damage。
9. 只有前述检查全部通过且没有 repair reason才为 `COMPLETE`。

Manifest missing 之所以可修复，不是容忍缺 manifest，而是 inspector 已证明所有 source metas 可唯一产生整份 canonical manifest；
实际重写仍必须在 staged repair method 内完成并经 commit validator重验。canonical item 的字段集合、规范化与排序只由现有
`FilingManifestItem.from_source_meta(...).to_dict()` / `MaterialManifestItem.from_source_meta(...).to_dict()` owner 决定；inspector、
workflow 与 tests 不自建字段白名单，不把 `etag/last_modified/ingested_at` 等 source file volatile 字段误当 manifest schema。

### 5.3 upload published state

`FilingUploadPublishedState` 改为 required fields：

```python
company_meta: CompanyMeta | None
source_integrity: SourceIntegrityClassification
source_meta: Mapping[str, JsonValue] | None
```

- `source_integrity` 必须精确对应 read 参数的 canonical ticker、filing kind、document ID。
- `MISSING/UNSAFE` 必须 `source_meta=None`；`COMPLETE/REPAIR_REQUIRED` 必须携带 inspector 已验证且已移除私有 revision 的
  business meta。
- `_FsFilingUploadStateMixin.read_filing_upload_state()` 在同一 publication guard 内取得 company meta 和 source inspection，不能
  先 classify 再调用 public `get_source_meta()` 二次加锁/回读。
- 所有测试/fake constructor 必须显式提供 classification；不增加 default 或从 `source_meta is None` 反推兼容。

### 5.4 repair disposition 与 validator precedence

新增 `dayu/fins/upload_repair_contract.py`，只定义共享 immutable contract，避免 `ingestion_runtime` 与 Docling pipeline 循环依赖：

```python
@dataclass(frozen=True, slots=True)
class NoExistingSourceRepair:
    kind: Literal["not_required"] = "not_required"

@dataclass(frozen=True, slots=True)
class ExistingSourceAutoRepair:
    expected_integrity: SourceIntegrityClassification
    kind: Literal["existing_source_auto_repair"] = "existing_source_auto_repair"
```

`ExistingSourceAutoRepair.__post_init__` 要求 filing、`REPAIR_REQUIRED`、non-null trusted revision；
`ValidatedFinsUploadFilingRequest.repair_disposition` 为 required union，并在自身 `__post_init__` 再验证 expected target 与
normalized ticker/document、raw action=`auto`、resolved action=`update`、non-empty `file_selection` 全部一致。

`validate_fins_upload_filing_request()` 在现有 static admission 完成后按以下精确 precedence 裁决：

1. 先验证 `published_state.source_integrity` 的 target identity 与 state/meta invariant；内部 producer 违约抛 `ValueError`。
2. `UNSAFE`：抛 `FinsUploadPrevalidationError(fins_upload_source_integrity_unsafe_failure())`；不进入 action/company decision。
3. `REPAIR_REQUIRED` 且 requested action 不是 exact `auto`：抛新增 usage code
   `EXISTING_SOURCE_REPAIR_REQUIRES_AUTO`，固定文案 `目标 filing 不完整；请使用 auto 并提供完整文件重新上传`。
4. `REPAIR_REQUIRED + auto`：static owner 已保证 upsert selection 非空且完整，resolved action 固定 `update`，产生
   `ExistingSourceAutoRepair(expected_integrity=...)`；`overwrite` 不扩大/缩小 repair 资格。
5. `MISSING`：`auto -> create`；显式 update 仍用 `UPDATE_TARGET_MISSING`；repair disposition=`NoExistingSourceRepair()`。
6. `COMPLETE`：按现有 raw meta/deleted/overwrite/action 解析，repair disposition=`NoExistingSourceRepair()`。
7. 最后用 resolved action 解析 company decision。repair 没有独立 company 分支，仍与 source 共用一个 batch。

### 5.5 public failure contract

`dayu/fins/upload_failure.py` 新增三个 storage-kind closed code，不复用 generic unexpected runtime：

- `SOURCE_INTEGRITY_UNSAFE`：`工作区中的目标 filing 状态不完整且无法安全自动修复`；retry hint
  `请先修复工作区 source 状态后再重试`。
- `SOURCE_REVISION_STALE`：`目标 filing 在上传准备期间已发生变化，本次上传未提交`；retry hint
  `请基于最新目标状态重新发起上传`。
- `SOURCE_REPAIR_BLOCKED`：`工作区中存在本次上传无法安全重建的其它 source，本次上传未提交`；retry hint
  `请先修复工作区中的其它 source 状态后再重试`。

对应模块级 factory 是唯一文案 owner。validator 用第一项产生 prevalidation error；Docling publication 捕获 exact
`SourceIntegrityRevisionConflictError` 并转换为第二项 `FinsUploadFailureError`，捕获 exact
`SourceIntegrityRepairBlockedError` 并转换为第三项；二者不得互相映射。SEC/CN/HK 继续消费 typed failure event owner；
不得让 workflow 捕获异常字符串、落入 `UNEXPECTED_RUNTIME`，或把 revision/path/internal reason 写入 result。

`FinsUploadPrevalidationError` 的传播边界同时冻结：

- `FinsIngestionRuntime._validate_runtime_upload_request()` 与 `start_upload()` 的 Raises 明确加入
  `FinsUploadPrevalidationError`；raw runtime start 必须在 job/observation 创建前原样抛出其 typed failure，不持久化 generic
  `str(exc)` job failure，也不把它改写为 `ValueError/OSError`。
- SEC `run_upload_filing_stream()` 与 CN/HK `upload_filing_stream()` 把 fresh state read + fresh validator 包在显式
  `try/except FinsUploadPrevalidationError` 内；命中时用 preflight validated request 的 deterministic identity 和
  `exc.failure` 产生唯一 `UPLOAD_FAILED` typed event后 return，converter/company stage/batch 均为零调用。不得使用 stale
  preflight disposition作为 expected truth；只有 fresh classification/failure 是 authoritative。
- pipeline failed event继续由既有 runtime result projection持久化 exact `failure_reason` JSON、retry hint与 failed terminal；
  `_run_upload_job` 不再看到这类 exception，因此不会走 `_save_failed_from_exception(str(exc))` generic path。

## 6. 统一 filesystem inspection 与 publication contract

### 6.1 私有 inspector

新增 `dayu/fins/storage/_fs_source_integrity.py`，使大体量 `_fs_storage_infra.py` 不继续承担另一套解析职责。该模块只依赖
storage low-level identity/JSON/path utilities、domain contracts 和 public integrity types，提供显式参数的模块级函数，不使用 callback、
factory、`Any`、`object`、`getattr/hasattr` 或 nested class/function。

私有类型与 `_unguarded` 函数签名冻结如下；实现不得改成接收可选 guard token、检测锁状态或内部二次加锁：

```python
@dataclass(frozen=True, slots=True)
class _InspectedSourceFile:
    descriptor: SourceSnapshotFileDescriptor
    physical_path: Path

@dataclass(frozen=True, slots=True)
class _SourcePublicationInspection:
    classification: SourceIntegrityClassification
    content_classification: SourceIntegrityClassification
    persisted_meta: Mapping[str, JsonValue] | None
    business_meta: Mapping[str, JsonValue] | None
    provenance: SourceDocumentProvenance | None
    revision: SourceDocumentRevision | None
    files: tuple[_InspectedSourceFile, ...]
    primary_document: str | None
    canonical_manifest_item: Mapping[str, JsonValue] | None

@dataclass(frozen=True, slots=True)
class _SourceKindPublicationInspection:
    target: _SourcePublicationInspection | None
    inventory: tuple[_SourcePublicationInspection, ...]
    shared_manifest_reasons: tuple[SourceIntegrityReason, ...]
    canonical_manifest_items: tuple[Mapping[str, JsonValue], ...]
    repair_blocked_reason: SourceIntegrityRepairBlockedReason | None

def _inspect_source_kind_unguarded(
    *,
    ticker: str,
    source_kind: SourceKind,
    ticker_dir: Path,
    source_root: Path,
    requested_document_id: str | None,
) -> _SourceKindPublicationInspection: ...

def _require_complete_source_for_snapshot_unguarded(
    inspection: _SourcePublicationInspection,
) -> _SourcePublicationInspection: ...
```

`classification` 是含 target-local 与 shared manifest reasons 的 public fact；`content_classification` 只评价 exact source 的
identity/meta/revision/provenance/file declaration/role/physical facts，不含任何 manifest reason。`canonical_manifest_item` 只能通过
source-kind 对应的现有 `FilingManifestItem`/`MaterialManifestItem` owner从 trusted persisted meta生成；函数永不从现有 manifest
复制 item。每个 source 的 `canonical_manifest_item` 可用性只取决于该 source 自身的 trusted persisted meta 与
`content_classification=COMPLETE`，不受其它 source（包括 requested target）损坏影响。aggregate `canonical_manifest_items` 只有
inventory 每个 source 的 `content_classification=COMPLETE` 时才非空并按 document ID稳定排序。

调用约定是严格 capability-precondition，而不是参数：published caller 在进入函数前已持该 ticker 的 publication guard；staged caller
先用 `_resolve_active_batch(batch, ticker)` 验证真实 open batch capability，再传该 state 的 staging locator。函数不接收、不返回、
不探测 guard token，也不调用 `_acquire_publication_guard()` / `_release_lock_token()` / `_resolve_active_batch()`。因此
`read_filing_upload_state` 可在同一既有 guard 内同时读取 company meta 与 inspection，classifier/snapshot也不会发生嵌套锁；
`classify_staged_source_integrity` 与 repair reset则由 repository method先验证 batch再调用同一 `_unguarded` 函数。

冻结 inspector 有且只有两种调用形状：

- exact-target mode：`requested_document_id=<canonical document ID>`；一次调用在同一 scan 中返回该 exact `target` 与完整
  source-kind `inventory/shared_manifest_reasons/canonical_manifest_items`，`target` 必须非 `None`。
- whole-kind mode：`requested_document_id=None`；`target` 必须为 `None`，一次调用返回整个 source-kind 的
  `inventory/shared_manifest_reasons/canonical_manifest_items`，包括空 inventory 或无法归属单一 target 的 manifest/root facts。
  inventory 与 commit validator 每个 source kind 只能调用一次 whole-kind mode；inventory 在一个 publication guard 内、commit 在同一个
  已验证 batch capability 内消费这一份 payload，不得逐 document 重扫、重新聚合或跨 guard/batch 拼接结果。因此 shared reasons 与
  canonical facts 在该次 inventory/commit 决策内天然同源一致。

三类 caller 的规则：

- `_fs_source_document_core.py` 的 published/staged exact classifier 使用 exact-target mode并只投影非空
  `inspection.target.classification`；inventory 使用一次 whole-kind mode，按稳定 document ID顺序投影
  `inspection.inventory[*].classification`，不得循环调用 exact-target mode。
- `_fs_source_snapshot.py` 在原有 publication guard 内要求 inspection=`COMPLETE`，直接用同一 inspection 构造 meta/provenance/
  revision/files/primary；删除 `_parse_snapshot_files()` 的重复业务解析。full snapshot 的 opened-FD copy、fstat/digest、marker retry 和
  resource lifecycle继续保留，它们负责读取期间稳定性而非重新定义 publication 完整性。
- `_fs_storage_infra.py` 的 commit validator 对每个 staging source kind 使用一次 whole-kind mode，先用同一 payload要求每个 source
  content/public classification=`COMPLETE` 且全量
  canonical manifest exact equality；随后仍由 commit validator自己执行 staging-specific `local://<staging ticker key>/...` URI
  equality和 staging-root containment验证。URI规则不进入 inspector、不影响 published classification/snapshot；commit validator保留的
  只是 staging locator资格，不重复 meta/role/digest/manifest业务解析。原有 writer/publication/swap/recovery状态机不改。

Operational filesystem I/O 继续抛 path-free `OSError`；结构事实全部收敛为 classification/reason。只有无法把 root corruption 归属
任何 target 的 whole-inventory 调用才抛 typed `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`，不得恢复 raw `ValueError` 文案。

### 6.2 staged repair recheck 与 manifest rewrite

`SourceDocumentRepositoryProtocol` 新增且 filesystem repository 实现：

```python
def reset_source_document_for_repair(
    self,
    ticker: str,
    document_id: str,
    source_kind: SourceKind,
    expected_integrity: SourceIntegrityClassification,
    *,
    batch: BatchToken,
) -> None: ...
```

public protocol Raises固定为：invalid capability/identity/expected classification -> `ValueError`；target expected/staged
presence/revision/repair eligibility漂移 -> `SourceIntegrityRevisionConflictError`；target仍匹配但non-target/cross-source/canonical
manifest阻断 -> `SourceIntegrityRepairBlockedError`；filesystem operation -> path-free `OSError`。方法返回`None`，不得返回staged
classification让workflow二次裁决。

方法是 Phase B 唯一 owner，精确顺序如下：

1. 校验 open batch capability、ticker/kind/document 与 expected target；expected 必须 `REPAIR_REQUIRED` 且 revision可信。
2. 在真实 staging tree 用统一 inspector exact-target mode一次重分类 target，并取得同一次 scan 的完整 source-kind
   inventory/shared manifest facts。
3. 比较前先 gate：expected 或 staged 任一为 `UNSAFE`，或任一 public status 不是 `REPAIR_REQUIRED`，立即抛
   `SourceIntegrityRevisionConflictError`。通过 gate 后才调用
   `has_same_source_publication_identity(expected, staged)`；返回 false 同样抛 conflict。该比较函数在 storage method 内若仍抛
   `ValueError`（包括 identity/unsafe invariant 漂移），必须由 method 捕获并转换为同一个 path-free
   `SourceIntegrityRevisionConflictError`，禁止 raw `ValueError` 逃逸；上述转换只包围 staged comparison，不吞掉第 1 步 invalid
   capability/identity/expected classification 的 input `ValueError`。任何 conflict 都不 reset、不重写。
4. 将 target-local stale 与 cross-source block分开裁决：target presence/revision变化、public staged status不再是
   `REPAIR_REQUIRED`、`content_classification`变为`MISSING/UNSAFE`，或content reasons出现非repairable事实，只抛
   `SourceIntegrityRevisionConflictError`。whole-manifest-missing-only target允许
   `content_classification=COMPLETE`且public reasons只含shared reasons；有target-local repair时允许
   `content_classification=REPAIR_REQUIRED`。target仍匹配时，逐个检查 non-target 的 internal
   `content_classification`。non-target 不要求 public `classification` 字面 `COMPLETE`——whole manifest missing时它可因 shared
   `SOURCE_MANIFEST_MISSING` 为 `REPAIR_REQUIRED`——但必须满足 `content_classification=COMPLETE`，且 public reasons 只能等于
   `inspection.shared_manifest_reasons`。任一 non-target 有 physical/meta/revision/role/target-local manifest damage，或存在
   cross-source/root structural unsafe，抛 `SourceIntegrityRepairBlockedError` 的精确 closed reason；不借本次 target repair修其它 source。
5. canonical remaining items 明确只取同一次 exact-target inspection payload中每个 non-target
   `_SourcePublicationInspection.canonical_manifest_item`，按 canonical document ID稳定排序；该单点字段由 trusted persisted meta 调用
   `FilingManifestItem.from_source_meta(...).to_dict()` / `MaterialManifestItem.from_source_meta(...).to_dict()` 生成。此步骤绝不消费
   `_SourceKindPublicationInspection.canonical_manifest_items` aggregate——target-local damage 会使 aggregate 为空，但不得因此丢弃
   complete sibling 的单点 canonical item——也绝不读取、merge或复制损坏 manifest中的 item。任一 non-target 单点 item为空、重复
   或不能组成全量唯一 remaining items时，抛
   `SourceIntegrityRepairBlockedError(CANONICAL_MANIFEST_UNAVAILABLE)`。
6. reset exact target directory；用第 5 步的 canonical items重写该 source-kind manifest（无剩余 source 时写合法空 manifest或按现有
   storage canonical empty 规则处理）。这一步修复 whole-manifest missing 和 target-only projection mismatch，不保留损坏 manifest。
7. 返回后 `DoclingUploadService` blob-first 写入完整 assets并 final create；现有 upsert owner把新 target canonical item合入 manifest，
   `_prepare_complete_source_meta()` 生成新的 opaque persisted revision。
8. commit validator再次要求整棵 staged ticker tree `COMPLETE`，并独立验证 staging URI/containment后，现有 batch owner才进入 swap。

普通 complete update/create-overwrite/material 继续调用现有 `reset_source_document()`；repair 专用方法不是兼容 wrapper，它增加 staged
expected-revision、status 和 manifest canonicalization 的有效语义。

## 7. Upload、download、snapshot 数据流

### 7.1 filing auto repair

```text
raw filing request
  -> static validation: exact target + complete non-empty primary/companions
  -> publication guard: company meta + source inspection (Phase A)
  -> validator: ExistingSourceAutoRepair(expected REPAIR_REQUIRED revision)
  -> SEC/CN/HK fresh read + same validator; old preflight disposition discarded
  -> Docling prepare: read every authoritative original; repair disables identical skip
  -> convert authoritative primary; build complete pending source
  -> begin ticker batch (copies current publication while writer reserved)
  -> stage company decision
  -> storage reset_source_document_for_repair(expected) (Phase B)
  -> reset target + canonical remaining manifest
  -> blobs + final source meta + new manifest item
  -> commit complete-tree validation
  -> existing old-or-new directory swap
  -> public COMPLETE/new revision -> snapshot/process_filing
```

具体 production changes：

- `DoclingUploadService.prepare_upload()` 新增 required keyword，签名精确为：

  ```python
  async def prepare_upload(
      self,
      *,
      # 既有 required keywords保持原顺序与类型
      repair_disposition: NoExistingSourceRepair | ExistingSourceAutoRepair,
      cancellation: CancellationToken | None,
  ) -> PreparedDoclingUpload: ...
  ```

  filing workflow只传 workflow fresh validator产生的 authoritative disposition；material caller显式传
  `NoExistingSourceRepair()`，不得用 default隐式兼容。
- `_can_skip_upload()` 精确扩展为：

  ```python
  def _can_skip_upload(
      previous_meta: Mapping[str, JsonValue] | None,
      source_fingerprint: _UploadSourceFingerprint,
      overwrite: bool,
      *,
      repair_disposition: NoExistingSourceRepair | ExistingSourceAutoRepair,
  ) -> bool: ...
  ```

  函数第一条规则是 `ExistingSourceAutoRepair -> False`；只有 `NoExistingSourceRepair` 才继续执行既有
  overwrite/deleted/identical-safe/fingerprint判断。`prepare_upload()` 必须原样传入 disposition，不允许在调用点另包一层 boolean
  或复制 skip规则。
- `_PreparedAssetMutation` 保存同一 disposition；repair仍计算 fingerprint/version并保留 reset 前 trusted meta 的
  `first_ingested_at/created_at/document_version` 规则。
- `_store_upload_assets()` 仅在 typed repair disposition 时调用 `reset_source_document_for_repair()`；其它 replacement 保持现有 reset。
- Phase A expected truth只来自 workflow fresh authoritative request，入口 preflight request上的旧 classification/disposition会被丢弃。
  SEC/CN workflow 的 `_assert_authoritative_filing_identity()` 只比较 canonical ticker、document ID、internal document ID 三个
  deterministic identity，不比较旧/fresh disposition、status、revision或reasons；fresh validated request 的 `__post_init__` 已保证
  `ExistingSourceAutoRepair.expected_integrity` 与其自身 identity一致，workflow不得增加第二套断言或推断。
- company decision 仍先 stage 到同 batch；若 repair recheck失败，`commit_prepared_upload_batch()` 现有 finally rollback exactly once，
  company/source 都不可见。

### 7.2 download 与 snapshot

- SEC/CN download Phase A 在读取 raw previous meta 前显式拒绝 `UNSAFE`；whole-tree preflight 同样拒绝 unsafe。
- whole manifest missing 在 inventory中投影为每个实际 source 的 shared `SOURCE_MANIFEST_MISSING`。存在多个实际 source、accepted
  selection 不是唯一 repair target，或出现非 selected repair target时，download whole-tree preflight以既有 typed
  `SourceIntegrityPreflightError` fail closed；只有一个实际 filing且它正是 accepted selected target时，保持既有
  `SelectedSourceRepairRequired` 路径，由 download reset、重新下载并通过 upsert重建 canonical manifest。该单-source行为不是把 upload
  rewrite授权泛化到 download，多-source/非-selected仍严格拒绝。
- Phase B 只允许 expected identity一致后的 `MISSING/COMPLETE/REPAIR_REQUIRED`；`UNSAFE` 立即 typed fail closed，不能进入
  `status is not MISSING -> reset`。
- 不改变 download retry次数、provider transport、overwrite、rejection registry 或结果收敛。
- snapshot 只接受 `COMPLETE` inspection。light/full snapshot 对 `REPAIR_REQUIRED` 或 `UNSAFE` 都抛既有异常面内的固定
  path-free `ValueError("source snapshot 只允许读取完整 source")`，不得新增异常类型、拼接 status/reason/path；因此无需修改
  `dayu/fins/tools/read_runtime.py`。repair batch未commit期间，published snapshot仍读取 old publication：若old本来损坏则按上述
  ValueError拒绝，published classification仍返回同一个Phase A revision；同ticker的complete non-target snapshot仍返回old bytes/revision。
  测试在begin/reset与commit之间设置staging barrier，证明published view永不观察staging MISSING/半写状态。repair成功后snapshot
  revision/files/primary全部来自new inspection。

## 8. Affected files 与精确修改

### 8.1 Production

| 文件 | 修改 |
| --- | --- |
| `dayu/fins/storage/source_integrity.py` | 新增 `UNSAFE`、closed reasons/invariants、unsafe comparison/preflight、target conflict与cross-source repair-blocked types |
| `dayu/fins/storage/_fs_source_integrity.py`（新） | 唯一 filesystem publication/manifest inspector 与 typed private payload |
| `dayu/fins/storage/repository_protocols.py` | `FilingUploadPublishedState.source_integrity`、state invariants、repair reset method contract |
| `dayu/fins/storage/_fs_filing_upload_state_core.py` | 单 guard company + source inspection 投影 |
| `dayu/fins/storage/_fs_source_document_core.py` | classifier/inventory委托 inspector；实现 repair staged recheck/reset/manifest rewrite |
| `dayu/fins/storage/_fs_storage_infra.py` | commit validator委托统一 inspector；保留 batch/swap/recovery owner |
| `dayu/fins/storage/_fs_source_snapshot.py` | descriptor/meta/primary/revision消费 inspection，移除重复 parser |
| `dayu/fins/storage/__init__.py` | 导出新增 public status/reason/contract；不做旧名 re-export |
| `dayu/fins/upload_repair_contract.py`（新） | no-repair / existing-auto-repair immutable union |
| `dayu/fins/ingestion_runtime.py` | validator eligibility、required disposition、target/state invariants、usage failure、raw runtime start Raises与typed failure持久化边界 |
| `dayu/fins/upload_failure.py` | unsafe/stale closed storage failures及 factories |
| `dayu/fins/pipelines/docling_upload_service.py` | typed disposition、repair skip bypass、Phase B repair reset与 stale failure映射 |
| `dayu/fins/pipelines/sec_upload_workflow.py` | fresh authoritative disposition mechanical handoff；fresh prevalidation error -> typed failed event |
| `dayu/fins/pipelines/cn_pipeline.py` | CN/HK fresh authoritative disposition mechanical handoff；fresh prevalidation error -> typed failed event |
| `dayu/fins/pipelines/sec_download_filing_workflow.py` | `UNSAFE` Phase A/B typed fail closed |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | `UNSAFE` Phase A/B typed fail closed |

明确不改 `dayu/host/`、`dayu/engine/`、`dayu/service/`、`dayu/cli/`、tool schema、material upload production branch、
registry/oracle/evidence。

### 8.2 Tests

| 文件 | owner-level assertions |
| --- | --- |
| `tests/fins/test_fins_storage_atomicity.py` | 四状态/reason矩阵、UNSAFE无revision、published=staged、manifest/cross-source、repair reset Phase B conflict、old保持 |
| `tests/fins/test_fins_storage_provider.py` | commit validator 与 inspector同源、manifest canonical rebuild、new revision、snapshot COMPLETE-only |
| `tests/fins/test_fins_ingestion_runtime.py` | state constructor/invariants、auto eligibility、显式 action拒绝、missing/complete/unsafe、raw start Raises、typed failed job、exact disposition |
| `tests/fins/test_fins_service_runtime.py` | unsafe prevalidation path-free failure、read-only零 mutation |
| `tests/fins/test_docling_upload_service.py` | identical fingerprint repair不skip、全量 assets/primary/derived、stale reset failure、conversion/blob/final/rollback保留 old |
| `tests/fins/test_sec_pipeline_upload_filing_stream.py` | US UF evidence corruption组合、revision变化、same batch、stale/blocked/unsafe typed terminal、non-target不变 |
| `tests/fins/test_cn_pipeline.py` | CN success + revision conflict/rollback + unsafe/company atomicity；HK success + stale/unsafe typed projection |
| `tests/fins/test_sec_pipeline_download.py` | 新 `UNSAFE` Phase A/whole-tree fail closed且 provider/company/registry零副作用 |
| `tests/fins/test_cn_download_workflow.py` | 新 `UNSAFE` Phase A/B 不落入 reset，既有 repair/retry保持 |
| `tests/fins/test_processor_read_consistency.py` | repair commit 后 `process_filing`/snapshot消费 new primary/revision；repair前拒绝损坏 snapshot |
| `tests/service/test_fins_direct.py` | required upload state fixture迁移；direct prevalidation typed failure保持path-free且factory/job零调用 |
| `tests/cli/test_fins_commands.py` | required upload state fixture迁移；CLI typed prevalidation exit/failure投影保持闭合 |
| `tests/README.md` | 更新当前 owner coverage 与 focused 命令，不写 work-unit过程 |

所有旧 `FilingUploadPublishedState(...)` fixture 必须显式构造 matching classification；不得给 production dataclass 加 default 来保旧测试。

## 9. Small implementation slices

每个 slice 必须独立保持 pyright 可检查、测试边界清楚；不得把 consumer 分支先于 owner contract合入。

### Slice 1：冻结 public integrity/state/repair contracts

prerequisites：goal confirmation已接受；无代码 slice依赖。该 slice只建立可被后续 inspector消费的public types和required state shape。

allowed files（本 slice 之外不得修改）：

- `dayu/fins/storage/source_integrity.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/_fs_filing_upload_state_core.py`
- `dayu/fins/storage/__init__.py`
- `dayu/fins/upload_repair_contract.py`（新）
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_ingestion_runtime.py`（仅更新 required fixture/type contract；不实现 eligibility）
- `tests/service/test_fins_direct.py`（仅 required fixture迁移与direct contract回归）
- `tests/cli/test_fins_commands.py`（仅 required fixture迁移与CLI contract回归）

1. 扩展 status/reason/invariants/comparison/preflight。
2. 新增 repair contract union。
3. 扩展 repository protocol 与 upload state required field/method；为保持 slice独立可运行，state core在现有 publication guard内调用
   当前 `_classify_source_integrity_unguarded()` 并显式构造 required field，slice 2再机械替换为统一 inspector，不增加default或双读。
4. 更新 storage exports和全仓所有 required `FilingUploadPublishedState(...)` constructors，包括两个跨目录 tests。
5. 写 contract tests，证明 invalid combinations不能构造、`has_same_source_publication_identity(UNSAFE, *)` 与
   `has_same_source_publication_identity(*, UNSAFE)` 均为 `ValueError`。
6. slice validation：

   ```bash
   source .venv/bin/activate
   python -m pytest tests/fins/test_fins_storage_atomicity.py \
     tests/fins/test_fins_ingestion_runtime.py \
     tests/service/test_fins_direct.py \
     tests/cli/test_fins_commands.py -q
   python -m pyright dayu/ tests/ utils/
   ```

完成条件：类型面闭合；没有 production fallback/default；尚不授权 repair mutation。

### Slice 2：统一 filesystem inspector

prerequisites：Slice 1 public status/reason/state types和required constructors已通过。实现必须严格遵守§6.1的两个 `_unguarded`
签名与caller-held guard/batch precondition；不得在本 slice重设计guard接口。

allowed files（本 slice 之外不得修改）：

- `dayu/fins/storage/_fs_source_integrity.py`（新）
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/_fs_source_snapshot.py`
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_processor_read_consistency.py`（仅 snapshot COMPLETE-only contract）

1. 新增 private inspector及完整 classification precedence。
2. published/staged classifier按 exact-target mode机械投影；inventory每个 source kind只调用一次 whole-kind mode并投影同一 payload。
3. commit validator每个 staging source kind只调用一次 whole-kind mode并只接受 `COMPLETE`；不得逐 document重扫或重建 shared/
   canonical aggregate。
4. snapshot改用 inspection payload，保留 FD/marker/lifecycle稳定读取。
5. 扩展完整 corruption grid与 published/staged/snapshot/commit同源测试；同一 publication guard/batch 中 exact-target 与 whole-kind
   payload的 inventory/shared reasons/canonical facts一致，inventory/commit各 source kind调用 whole-kind mode恰好一次。
6. slice validation：运行三个allowed test files及全仓pyright；测试同时断言commit仍拒绝staging URI mismatch/containment escape。

完成条件：同一 fixture在 classifier、snapshot、commit得到一致状态；raw structural `ValueError` 不再旁路 public classification。

### Slice 3：upload state 与 repair eligibility

prerequisites：Slice 2 inspector signatures和inspection payload已冻结并通过；state core只把Slice 1的临时现有classifier调用替换为
`_inspect_source_kind_unguarded()`，不得增加新locking seam。

allowed files（本 slice 之外不得修改）：

- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/_fs_filing_upload_state_core.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/upload_failure.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_service_runtime.py`

1. 同 guard read返回 classification + trusted meta。
2. validator按 status/action/selection precedence产生 disposition或 typed failure。
3. 补 state、service prevalidation、path-free failure tests。
4. 更新 `_validate_runtime_upload_request()` / `start_upload()` Raises和raw start zero-job contract测试；本 slice不处理workflow async event。

完成条件：`REPAIR_REQUIRED + auto + full selection` 是唯一 repair producer；此 slice仍不修改 source。

### Slice 4：Docling preparation 与 staged repair owner

prerequisites：Slice 3是唯一 `ExistingSourceAutoRepair` producer；Slice 2 inspection已能区分content classification、shared manifest
reasons和repair-blocked reason。

allowed files（本 slice 之外不得修改）：

- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/upload_repair_contract.py`
- `dayu/fins/upload_failure.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_docling_upload_service.py`

1. required disposition贯穿 prepared mutation。
2. repair bypass identical skip并全量准备。
3. 实现 `reset_source_document_for_repair()` 的 staged revision/status recheck、storage-internal `ValueError -> revision conflict`转换、
   target reset，以及仅消费 non-target inspection单点 `canonical_manifest_item` 的 canonical remaining manifest rewrite。
4. exact conflict映射为 bounded stale upload failure。
5. service-level tests覆盖 successful stage、revision/status drift（含 staged UNSAFE与非 `REPAIR_REQUIRED` gate）、target-local damaged +
   complete sibling per-source canonical item rewrite、conversion/blob/final/rollback。
6. service tests精确覆盖`SourceIntegrityRevisionConflictError -> SOURCE_REVISION_STALE`与
   `SourceIntegrityRepairBlockedError -> SOURCE_REPAIR_BLOCKED`，二者不得落generic runtime。

完成条件：staging只在 expected仍有效时被重写；所有失败保持 published old tree SHA不变。

### Slice 5：SEC/CN/HK workflow 与 downstream

prerequisites：Slice 4 shared service/storage成功、stale和repair-blocked paths均已通过；本 slice只接线fresh authoritative disposition和
market-specific typed event，不重判integrity。

allowed files（本 slice 之外不得修改）：

- `dayu/fins/pipelines/sec_upload_workflow.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_fins_ingestion_runtime.py`（仅typed failed job projection）

1. fresh authoritative disposition传入 shared service。
2. US/CN/HK真实 filesystem deterministic tests覆盖四类 repair与 atomic company/source publication。
3. assert public `COMPLETE`、revision changed、manifest/new files/primary/digest一致、requested=stored originals。
4. 通过 snapshot和 `process_filing` spy/真实 processor入口证明只消费 new primary。
5. fresh validator的 `FinsUploadPrevalidationError` 在SEC/CN/HK async stream收敛为typed failed event；runtime job持久化同一
   `failure_reason`，不记录generic `str(exc)`。

完成条件：端到端 owner chain闭合，pipeline没有完整性重算。

### Slice 6：download unsafe 回归、文档与全量验证

prerequisites：Slices 1-5全部通过；shared manifest reason和snapshot ValueError契约已冻结。

allowed files（本 slice 之外不得修改）：

- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_cn_download_workflow.py`
- `README.md`
- `dayu/fins/README.md`
- `tests/README.md`

1. SEC/CN Phase A/B显式 unsafe fail closed，保护既有 retry/repair；补 whole-manifest-missing 的多-source/非-selected typed拒绝与
   单一 accepted selected filing继续 repair重建的回归。
2. 按 README 更新约束修改根 README、`dayu/fins/README.md`、`tests/README.md`。
3. 运行 focused tests、Fins suite、coverage、pyright与 scope guard。

完成条件：所有验证通过；禁止文件无 diff；不执行真实 evidence/registry修改。

## 10. Exact tests、pyright、coverage 与 docs commands

实现 gate 每次代码修改后先执行当前 slice 的 node IDs；收尾必须在 Python 3.11 venv 中依次执行：

```bash
source .venv/bin/activate
python -m pytest \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_storage_provider.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_processor_read_consistency.py \
  tests/service/test_fins_direct.py \
  tests/cli/test_fins_commands.py -q
python -m pytest tests/fins -q
python -m pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q
python -m pyright dayu/ tests/ utils/
```

覆盖率使用同一 focused owner suite采集，并逐个修改生产文件检查，不用 aggregate 覆盖率掩盖低覆盖文件：

```bash
source .venv/bin/activate
coverage erase
coverage run --branch -m pytest \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_storage_provider.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_processor_read_consistency.py \
  tests/service/test_fins_direct.py \
  tests/cli/test_fins_commands.py
coverage report --include='dayu/fins/storage/source_integrity.py' --fail-under=80
coverage report --include='dayu/fins/storage/_fs_source_integrity.py' --fail-under=80
coverage report --include='dayu/fins/storage/repository_protocols.py' --fail-under=80
coverage report --include='dayu/fins/storage/_fs_filing_upload_state_core.py' --fail-under=80
coverage report --include='dayu/fins/storage/_fs_source_document_core.py' --fail-under=80
coverage report --include='dayu/fins/storage/_fs_storage_infra.py' --fail-under=80
coverage report --include='dayu/fins/storage/_fs_source_snapshot.py' --fail-under=80
coverage report --include='dayu/fins/upload_repair_contract.py' --fail-under=80
coverage report --include='dayu/fins/ingestion_runtime.py' --fail-under=80
coverage report --include='dayu/fins/upload_failure.py' --fail-under=80
coverage report --include='dayu/fins/pipelines/docling_upload_service.py' --fail-under=80
coverage report --include='dayu/fins/pipelines/sec_upload_workflow.py' --fail-under=80
coverage report --include='dayu/fins/pipelines/cn_pipeline.py' --fail-under=80
coverage report --include='dayu/fins/pipelines/sec_download_filing_workflow.py' --fail-under=80
coverage report --include='dayu/fins/pipelines/cn_download_filing_workflow.py' --fail-under=80
```

文档与 scope 验证：

```bash
git diff --check
git diff -- README.md dayu/fins/README.md tests/README.md
git diff -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json docs/host/design.md docs/engine/design.md
git status --short
```

第三条命令必须无输出。禁止运行 `dayu-cli`、UF-PF08、UF-PF12 或任何真实 provider/converter evidence 命令。

## 11. Exact test matrix

### 11.1 Storage classification

- target absent -> `MISSING/no revision/no reasons`。
- valid user-upload filing、download filing、material -> `COMPLETE/revision/no reasons`。
- declared original/primary Docling/generic file missing，same-size digest变化，size变化，meta declared size/digest与physical不一致 ->
  exact repair reasons + trusted same revision。
- primary pointer/derived_from target-only mismatch、manifest missing、target item missing/projection mismatch且其它 sources complete ->
  `REPAIR_REQUIRED`。
- meta/descriptor/revision/provenance malformed，duplicate/invalid name，undeclared file，symlink/special entry，multiple Docling，manifest
  duplicate/dangling/ticker conflict，other-source damage -> `UNSAFE/no revision`。
- role/identity歧义与physical missing同时存在 -> `UNSAFE`，不允许missing repair reason覆盖结构失败。
- whole manifest missing + target/siblings content complete -> per-target/inventory均含shared manifest reason；internal
  `content_classification`仍为COMPLETE，canonical items逐项等于ManifestItem owner从trusted meta产生的结果。
- 同一 publication guard/batch 中，exact-target mode 与 whole-kind mode 的 inventory/shared reasons/canonical facts完全相等；whole-kind
  mode的`target is None`，exact-target mode的`target`精确命中requested document；inventory/commit对每个source kind只调用一次
  whole-kind mode并消费该单一payload。
- 同一 fixture 的 published/staged classification一致；
  `has_same_source_publication_identity(UNSAFE, COMPLETE)`、`(COMPLETE, UNSAFE)`、`(UNSAFE, UNSAFE)`均抛`ValueError`，跨target同样拒绝。
- commit inspector COMPLETE后仍由commit validator拒绝staging URI mismatch和containment escape；published inspector不执行staging URI规则。

### 11.2 Validator eligibility

- `MISSING + auto -> create/no repair`；`COMPLETE + auto -> update/no repair`；logical deleted complete仍 update且不skip恢复。
- `REPAIR_REQUIRED + auto + one/multi-file authoritative selection -> update/existing repair`。
- matching status但 expected target ticker/document/kind错配无法构造 validated request。
- `REPAIR_REQUIRED + create/update/delete` 精确 usage code/message，converter/batch零调用。
- `UNSAFE + any action` 精确 path-free prevalidation failure，company decision/converter/batch零调用。
- raw runtime start遇到UNSAFE时在job/observation创建前抛typed `FinsUploadPrevalidationError`；Raises、failure code/message/retry hint与
  zero durable job均精确断言。
- logical `is_deleted=True` 且target同时repairable damaged，`auto + complete selection`仍授权repair；成功新meta固定
  `is_deleted=False/deleted_at=None`，恢复active。
- material request没有 repair disposition变化或 auto repair入口。

### 11.3 Preparation/publication

- fingerprint相同 + complete -> existing skip；fingerprint相同 + repair -> converter被调用且不skip。
- multi-file repair重写全部 originals、只产生一个 primary Docling、metadata/pointer/fingerprint/version同源。
- Phase A repair；Phase B revision不同、变 missing、变 complete、变 unsafe分别 stale失败，storage method在比较前拒绝非
  `REPAIR_REQUIRED/UNSAFE`并把comparison `ValueError`转换为`SourceIntegrityRevisionConflictError`；service最终只投影
  `SOURCE_REVISION_STALE`，不得出现raw `ValueError/UNEXPECTED_RUNTIME`，rollback exactly once，old tree SHA不变。
- target revision/presence仍匹配但non-target filing/material content损坏或cross-source unsafe ->
  `SOURCE_REPAIR_BLOCKED`，不得投影`SOURCE_REVISION_STALE/UNEXPECTED_RUNTIME`，rollback exactly once且old tree SHA不变。
- conversion、Nth blob、final source、manifest rewrite、commit validation、rollback secondary failure保持既有主失败规则且无半发布。
- successful repair re-read complete，新 revision != old；old source files不残留，non-target filing/material/company除明确decision外不变。
- manifest missing repair允许non-target public classification只携带shared manifest reason；storage证明其
  `content_classification=COMPLETE`后，基于所有remaining trusted metas经ManifestItem owner重写全量canonical manifest，不丢
  non-target item，也不读取损坏manifest item。
- target `content_classification=REPAIR_REQUIRED` + 至少一个 complete sibling + 原manifest一致时，repair成功；remaining items逐项来自
  每个 non-target inspection的`canonical_manifest_item`，即使aggregate `canonical_manifest_items`因target损坏为空也不得阻断或丢项。
- 在reset已发生但commit barrier尚未释放时，published exact target classification仍等于Phase A old
  `REPAIR_REQUIRED/revision`且snapshot仍抛同一fixed path-free ValueError；一个complete non-target的full snapshot仍读取old bytes/revision，
  published tree SHA不出现staging MISSING或半写状态。

### 11.4 US/CN/HK、snapshot 与 downstream

- shared `DoclingUploadService`/storage owner tests覆盖完整 corruption/failure grid：original missing/digest、Docling missing、meta
  size/digest、primary/derived projection、manifest missing/target mismatch、role unsafe、identical fingerprint、revision conflict、
  repair blocked、conversion/staging/publication rollback、snapshot/downstream。
- US market tests覆盖UF evidence组合：original missing/digest、Docling missing、meta size/digest、manifest missing auto成功；显式action、
  unsafe、stale/blocked typed terminal与company/source atomicity。
- CN market tests精确覆盖：一个repair success并断言new revision/active state；一个Phase B revision conflict并rollback old tree；一个
  unsafe fresh validation typed failed event；一个company stage/source repair同批atomic success或failure。
- HK market tests精确覆盖：一个repair success并断言new revision；另一个fresh unsafe或Phase B stale场景投影exact typed failed event，
  converter/batch或commit副作用按对应阶段为零/rollback。不得以“共享CN facade”替代这两个HK wiring assertions。
- pipeline started/completed/failed terminal、requested/stored original count、failure JSON均消费typed owner，不泄漏path/revision。
- repair前 light/full snapshot对`REPAIR_REQUIRED/UNSAFE`精确抛
  `ValueError("source snapshot 只允许读取完整 source")`，message不含path/status/reason；无需改read runtime。成功后snapshot
  meta/provenance/revision/files/primary来自new publication，close语义不变。
- `process_filing` 只取得新 snapshot primary derived，processed publication记录同一 source revision；不扫描 original/companion。
- SEC/CN download unsafe在provider/company/maintenance/rejection mutation前失败；whole-manifest-missing 的多-source或非-selected
  target以typed preflight error fail closed；单一实际 filing且为accepted selected target时继续既有
  `SelectedSourceRepairRequired -> reset -> download/upsert manifest rebuild`，并断言完成后source/manifest COMPLETE；既有Phase A/B
  retry回归通过。
- SEC/CN/HK fresh validator prevalidation failure产生typed failed event；raw runtime start原样抛typed prevalidation error；异步job路径
  持久化exact `failure_reason` JSON/retry hint且不走generic exception message。

## 12. README 决策

- `README.md`：命中最终用户 workflow 触发条件。只在现有 upload/action 段补充：`auto` 在完整本地输入且目标为安全可重建损坏时
  原子重建；显式 create/update/delete 或 unsafe state失败并给出可行动错误。不写 storage enum、revision、work unit或测试。
- `dayu/fins/README.md`：命中 `dayu/fins/` 修改且属于 developer stable contract。更新 Storage/upload 段，说明四态完整性、trusted
  revision、validator repair authorization、staged recheck、existing batch old-or-new与snapshot complete-only；删除当前仅三类physical
  corruption的过时说明。不写未来计划或文件流水账。
- `tests/README.md`：命中 tests 修改。更新 Fins focused命令和 owner coverage，记录 auto repair/unsafe/stale/snapshot/downstream矩阵。
- `dayu/README.md`：不更新；Fins 与 UI/Service/Host/Engine 分层及 assembly方式没有变化。
- Host/Engine/config README：不更新；对应职责无变化。

## 13. 风险、缓解与 residual owner

| 风险 | 本 work unit 缓解 | residual owner / destination |
| --- | --- | --- |
| inspector refactor改变既有 download/material classification | provider-aware规则、published/staged/commit/snapshot同fixture测试、Fins全套回归 | 本 work unit |
| manifest missing repair误删其它 source item | Phase B先验证所有 non-target complete并生成全量canonical items，commit再双向校验 | 本 work unit |
| 同 revision的外部静默篡改 | Phase B不仅比revision，还重分类且必须仍 `REPAIR_REQUIRED`；unsafe/complete均拒绝 | 本 work unit |
| preparation期间合法并发更新 | 零重试 stale typed failure并保留old/new；不扩成一般收敛 | `UF-FIX10` |
| fresh company meta warning | 不改变company decision/result warning | `UF-FIX11` |
| material existing-source repair | 明确无authorization，保持fail closed/既有语义 | 后续独立 work unit |
| 旧 schema corpus无法通过fresh inspector | 按用户要求不compat、不迁移 | 后续显式 migration work unit（若授权） |
| 真实 CLI修复效果与frozen evidence | 本轮只做deterministic owner tests，不篡改registry | UF-PF08/UF-PF12 evidence work unit |
| registry/oracle仍标记fix-required | 本轮禁止修改 | 后续registry/evidence adjudication |
| manual filesystem writer绕过repository lock | Phase B inspector + commit validator缩小窗口，但不承诺治理外writer协调 | storage operational policy；非本 work unit |

## 14. Code review focus 与完成报告要求

后续 implementation review/deepreview 必须重点检查：

- 是否仍有 classifier/snapshot/commit任一处复制 meta/manifest完整性规则。
- `UNSAFE` 是否可能因 `revision=None` 与 `MISSING` 被比较为相同，或落入 reset/skip。
- repair disposition是否只能由 validator产生，是否存在 workflow/service boolean/fallback授权。
- Phase B是否在任何 target reset/manifest rewrite之前完成 exact target + revision + status recheck。
- manifest rebuild是否包含所有且仅包含 trusted remaining sources，是否会修复/覆盖非 target damage。
- stale、unsafe、usage failure是否path-free/bounded，同一 typed reason是否贯穿 pipeline/runtime/direct result。
- company/source/assets/meta/manifest是否仍在一个 batch，commit ownership/cancel/rollback linearization是否保持。
- 是否意外修改 material、UF-FIX10/11、旧 schema、CLI/schema、registry/oracle/evidence或Host/Engine。
- 新增函数/类/模块是否有完整中文 docstring、严格类型、无 `Any/object/getattr/hasattr`逃逸。

最终 closeout 必须明确报告：

1. 改了哪些 owner/public contracts/state transitions与README。
2. focused tests、Fins suite、逐文件 coverage、全仓 pyright、`git diff --check` 的实际结果。
3. 未执行 UF-PF08/UF-PF12/真实 CLI evidence，未修改 registry/oracle，未创建 PR。
4. residual risks分别归属 UF-FIX10、UF-FIX11、material、migration、evidence/registry owner。

## 15. 为什么没有过度设计

- 复用 persisted source revision、现有 writer batch、publication guard、complete-tree validator、backup/journal和old-or-new swap；
  不新增 repair transaction、journal或第二套revision。
- 只新增一个 private filesystem inspector消除三套重复规则，以及一个小型 repair disposition contract解决现有 import方向；
  不建立通用 repair framework/adapter。
- repair授权只组合已经存在的 exact target、action、typed selection与storage fact；不扫描用户目录、不猜附件、不恢复unsafe raw meta。
- manifest修复只在全部 canonical inputs已被storage证明唯一时重写；其它结构保持fail closed。
- pipeline不拥有业务判断，Host/Engine/Service/CLI/tool schema不改，分层与public surface扩张保持最小。
