# UF-FIX08 existing-source-auto-repair：Slice 4 implementation

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`implementation`
- slice：`Slice 4：Docling preparation 与 staged repair owner`
- 日期：2026-08-16
- baseline / current HEAD：`1fd52c96f5e07f6007c3c6442d20635f3d37182b`
- accepted plan：`docs/gateflow/uf-fix08-existing-source-auto-repair-plan-20260816.md`
- 前置 artifacts/reviews：Slice 1–3 的 implementation、code review、adjudication 与 code-review-fix artifacts
- code review：`docs/reviews/code-review-20260816-163507.md`、`docs/reviews/code-review-20260816-170139.md`
- completion status：`CODE REVIEW FIXED / awaiting re-review`
- blocking questions：无
- 下一入口：Slice 4 re-review

## 动机与语义 owner 裁决

动机成立。Slice 3 已由 validator 产生 required、closed `ExistingSourceRepairDisposition`，但 Docling preparation/publication 尚未消费该
authorization；若 `REPAIR_REQUIRED + auto` 继续走 identical skip，将不会以完整本地输入重建损坏 publication。若 service 自行扫描目录、读取
raw meta 或从异常字符串重判，则 revision/status 复核、reset 与 manifest 重写会产生第二个完整性 owner。

本 slice 将语义边界收敛为：

- validator 的 `repair_disposition` 是 service 唯一 repair authorization；prepared mutation 必须原样携带它。
- `DoclingUploadService` 只负责 preparation/publish orchestration：existing repair 禁用 identical skip，以完整 selection 准备 originals、primary
  Docling、meta 与 manifest；publish 时把 authorization 交给 storage。
- filesystem storage core 是 staged repair 的唯一 owner：在同一个 batch publication contract 内执行 exact-target inspection、expected
  revision/status 复核、target reset，以及基于 non-target inspection `canonical_manifest_item` 的 remaining manifest 重写。
- facade 只显式 delegate 到 shared core；protocol 只声明 method contract，不保留 Slice 1 transitional rejection/helper。
- `upload_failure.py` 继续是 public failure 的唯一 owner；service 只精确映射 storage typed exception，不捕获为 generic runtime。

没有由 service/workflow 扫目录、读取 raw meta、比较异常字符串或重新推导 source integrity，也没有引入 default、overload、wrapper 或
compatibility shim。

## Controller scope adjudication

最初 allowed files 与 required `repair_disposition` contract 存在真实冲突。直接代码证据是 `DoclingUploadService.prepare_upload()` 必须采用无
default 的 required keyword，而生产侧共有四个 caller，分布在原 scope 外的 `sec_upload_workflow.py` 与 `cn_pipeline.py`；另有一个真实
Docling integration caller。若不迁移这些 caller，全仓类型检查与运行时调用 contract 都不成立；为避免这一问题而添加 default、overload
或 compatibility wrapper 又会破坏 accepted plan 的 fail-closed contract。

Controller 因此授权最小扩展以下三份文件，实际 diff 严格限定为：

| 扩展文件 | 直接调用证据与唯一改动 |
| --- | --- |
| `dayu/fins/pipelines/sec_upload_workflow.py` | filing caller 机械传 `authoritative_request.repair_disposition`；material caller 显式传 `NoExistingSourceRepair()` |
| `dayu/fins/pipelines/cn_pipeline.py` | filing caller 机械传 `authoritative_request.repair_disposition`；material caller 显式传 `NoExistingSourceRepair()` |
| `tests/fins/test_docling_upload_service_integration.py` | 真实 Docling integration caller 显式传 `NoExistingSourceRepair()` |

三份扩展文件没有增加 fresh reread、integrity 判断、failure 映射、event 语义或其他 Slice 5 逻辑。全仓 `prepare_upload(` 调用扫描确认除 service
定义外，生产 caller 只有上述四处；其余 direct test caller 均在原 allowed owner test 文件内显式迁移。

## 实际修改

### Required disposition 与完整 preparation

- `_PreparedAssetMutation` 新增 required `repair_disposition`；`prepare_upload()` 接受并校验 closed disposition，随后原样携带至 publish。
- `ExistingSourceAutoRepair` 在 `_can_skip_upload()` 中固定返回不可 skip，因此即使 local fingerprint 与旧 publication 相同，也会重新执行
  converter 并使用完整 local selection 准备所有 originals、primary Docling、meta 和 manifest。
- delete mutation 与 existing repair authorization 的矛盾输入 fail closed；普通 upload/delete 路径显式使用 `NoExistingSourceRepair`，未改变
  原 publication 语义。
- publish 将 disposition 传入 `_store_upload_assets()`；仅 existing repair 调用 storage staged reset，普通 replacement 保持既有 reset 路径。

### Storage staged repair owner

- `repository_protocols.py` 删除 Slice 1 transitional rejection helper 与 `NoReturn`，恢复纯 `...` method contract。
- `_fs_source_document_core.py` 实现唯一 `reset_source_document_for_repair()`：验证 canonical identity/source kind 与 expected
  `REPAIR_REQUIRED` contract，在当前 batch snapshot 内 exact-target inspect，并复核 target status、content status 与 publication identity。
- target 缺失、staged `UNSAFE`、staged 非 `REPAIR_REQUIRED`、expected revision/status 漂移均抛
  `SourceIntegrityRevisionConflictError`；只有 storage-internal publication identity comparison 抛出的 `ValueError` 被精确转换为 revision
  conflict，调用方输入验证 `ValueError` 不被吞并。
- inspection 明确阻断 cross-source publication 时抛 `SourceIntegrityRepairBlockedError`；所有 non-target 必须逐项为 safe、complete、public
  reasons 与 shared reasons 一致，并提供 document-id 精确且唯一的 `canonical_manifest_item`，否则 fail closed 为 non-target repair blocked。
- remaining manifest 只消费每个 non-target inspection 的 `canonical_manifest_item`，按 document id 排序后重写；不读取、合并或信任损坏
  manifest，也不消费 aggregate `canonical_manifest_items` 来重建。
- 所有 staged recheck 通过后才 exact reset target directory并重写 company canonical manifest；操作仍位于 repository/batch 的原子
  publication contract 内。
- `FsSourceDocumentRepository` 新增显式 facade method，只 delegate 到 shared core，不重判任何 repair 语义。

### Closed failure mapping

- `SourceIntegrityRevisionConflictError` 精确映射为 `SOURCE_REVISION_STALE`。
- `SourceIntegrityRepairBlockedError` 精确映射为 `SOURCE_REPAIR_BLOCKED`。
- 两者均通过 Slice 3 已建立的 closed failure factory 产生 `FinsUploadFailureError`，没有落入 generic runtime；无需修改
  `upload_failure.py` 或 `upload_repair_contract.py` 的既有 owner contract。

## Changed files

Production：

- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/storage/_fs_source_integrity.py`（Controller 授权的 blocked-reason owner 修复）
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/sec_upload_workflow.py`（Controller 最小扩展）
- `dayu/fins/pipelines/cn_pipeline.py`（Controller 最小扩展）

Tests：

- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_docling_upload_service_integration.py`（Controller 最小扩展）

Artifact：

- `docs/gateflow/uf-fix08-existing-source-auto-repair-slice4-implementation-20260816.md`

`dayu/fins/upload_repair_contract.py` 与 `dayu/fins/upload_failure.py` 在 allowed scope 内核对后无需修改：Slice 3 的 required disposition 与 closed
failure factory 已满足本 slice consumer contract，重复修改会制造 owner 漂移。

## 测试 contract

新增/更新测试覆盖：

- successful staged repair 经真实 facade 进入 shared core，exact reset target 后可完整 commit 新 publication。
- identical fingerprint 在 existing repair 下不能 skip；converter 再次运行并收到完整 originals，最终 publication 含 originals、primary
  Docling、meta 与 manifest。
- staged expected revision drift、target missing、target `UNSAFE`、target 非 `REPAIR_REQUIRED`（含 `COMPLETE`）均 revision conflict。
- target-local damage 与 complete sibling 共存时，只用 sibling inspection 的 canonical item 重写 remaining manifest；测试故意让 aggregate
  canonical collection为空，证明未消费 aggregate 或 damaged manifest。
- comparison 内部 `ValueError` 精确转 conflict，而 invalid caller expected input 的 `ValueError` 保持原样。
- conversion、blob store、final commit 与 rollback secondary failure 路径；typed stale/blocked mapping。
- 所有 publication failure 均断言 old published tree SHA 不变、无单独 company meta、无普通临时 publication；成功 rollback 路径还断言无
  active batch 与空 batch root。rollback 自身失败遵循既有 recovery contract保留 recovery staging，测试在断言 primary failure 后显式清理。

## Validation

运行环境：仓库 `.venv`，Python 3.11。

受影响测试：

```text
pytest -q --tb=short \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_docling_upload_service_integration.py

345 passed, 1 skipped, 3 warnings in 17.35s
```

完整 Fins suite 与 branch coverage：

```text
coverage run --branch --source=dayu/fins -m pytest -q tests/fins
1827 passed, 1 skipped, 3 warnings in 60.97s

dayu/fins/pipelines/cn_pipeline.py                    92%
dayu/fins/pipelines/docling_upload_service.py         87%
dayu/fins/pipelines/sec_upload_workflow.py            92%
dayu/fins/storage/_fs_source_document_core.py         80%
dayu/fins/storage/_fs_source_integrity.py              85%
dayu/fins/storage/fs_source_document_repository.py    97%
dayu/fins/storage/repository_protocols.py             96%
TOTAL                                                  87%
```

所有修改生产文件逐文件 branch coverage 均达到 `>=80%`。唯一 skip 是环境变量门控的真实 Docling integration；3 条 warning 均来自已安装
`edgar` 包的 deprecated imports。

全仓类型检查：

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

Scope 与格式：

- `git diff --check`：通过。
- HEAD 精确保持 `1fd52c96f5e07f6007c3c6442d20635f3d37182b`，未 commit、未 staged、未 push、未创建 PR。
- production/test diff 仅落在用户原 allowed files 与 Controller 明确扩展的三份 caller 文件；另新增本 artifact。
- Controller 扩展文件的 diff 已逐项核对，仅含 required argument import/传递。
- 未修改 SEC/CN/HK fresh reread、integrity/failure/event workflow、material repair、旧 schema compatibility、UF-FIX10 concurrency、README、
  oracle、scenario 或 evidence。
- 新实现未引入 `Any`、`object`、反射、compatibility shim、default 或 overload。

## README decision

用户明确禁止本 slice 修改 README，accepted plan 也把最终用户 workflow/documentation 汇总留给后续 slice。当前修改是 internal required
contract与 staged owner 接线，不改变完整对外工作流说明；`dayu/fins/README.md` 与 `tests/README.md` 的触发规则已核对，均保持无 diff。

## Residual risks 与后续 owner

| residual / 未覆盖项 | 分类与 owner |
| --- | --- |
| SEC/CN/HK fresh authoritative reread、typed failed event 与 workflow failure projection | accepted Slice 5；本 slice 扩展 caller 只机械传参 |
| material existing-source repair | 后续独立 work unit；本 slice material caller显式无 repair |
| 下载/snapshot/downstream 完整 workflow 与 README 汇总 | accepted Slice 5/6 |
| 旧 schema compatibility/migration | 后续显式 migration work unit（若授权）；本 slice 禁止兼容读取 |
| 一般并发更新 | UF-FIX10；本 slice 只复核 authorized repair 的 expected staged revision/status |
| 真实 CLI/provider evidence、oracle/scenario 状态 | UF-PF08/UF-PF12 evidence work unit；本 slice 禁止修改 |

没有未分类 blocking risk。rollback-secondary 场景保留 recovery staging 是既有 batching recovery contract，不是临时 publication 泄漏；测试同时
证明 old published tree 未变且 primary failure 未被覆盖。

## Code review fix：2026-08-16 re-review 入口前修复

Controller 将 `docs/reviews/code-review-20260816-163507.md` Finding 1（高）、Finding 2（中）均裁决为 blocker，并要求同 gate
一并闭环 Finding 3（低）。最终状态如下：

| Finding | 最终状态 | 修复与直接证据 |
| --- | --- | --- |
| 1：material source damage 在 Phase B 不可见 | `已修复` | `reset_source_document_for_repair()` 在同一 active staged batch 中保留 filing exact-target inspector 恰一次，并追加 material whole-kind inspector 恰一次；matching target 后 material content/public/shared/canonical/root structural 任一不完整都在 reset 前成为 `SourceIntegrityRepairBlockedError`，whole-kind `SourceIntegrityPreflightError` 精确映射 `CROSS_SOURCE_PUBLICATION_UNSAFE`。service 真实 storage tests覆盖 content missing、manifest missing、root unexpected entry，均为 `SOURCE_REPAIR_BLOCKED`、rollback once、commit zero、old tree/company/source meta/temp publication不变 |
| 2：blocked predicate 在 integrity/core 双派生 | `已修复` | 唯一 owner `_fs_source_integrity._derive_repair_blocked_reason()` 在 exact mode 跳过 target并检查全部 non-target content/public reasons/shared/canonical availability；whole-kind 没有 target/non-target 参照，repairable incomplete与shared manifest问题依 Slice 2 fix D统一闭合为 `CANONICAL_MANIFEST_UNAVAILABLE`。core 删除 content/status/reasons二次判断，只机械消费 typed reason并收集单点 item。clean payload 的 item shape/unique违约固定为 producer-invariant `RuntimeError`，不重建业务 reason。owner tests锁定 exact sibling projection mismatch 为 `NON_TARGET_SOURCE_INCOMPLETE`，material content/manifest missing 为 `CANONICAL_MANIFEST_UNAVAILABLE` |
| 3：非法 disposition、delete×repair 与 manifest rewrite failure 缺测试 | `已修复` | 新增非法 union与 delete×repair 固定 `ValueError`；patch真实 manifest rewrite `_write_json` 抛 `OSError`，断言 reset后的 staging 恰好 rollback once、commit zero、old tree/company/source meta不变且 batch root清空 |

### Controller 增量顺序裁决

filing `inspection.repair_blocked_reason` 的消费严格位于 target presence、staged status/content conflict gate 与
`has_same_source_publication_identity()` 之后；只有 target identity 仍匹配才消费 non-target reason。新增 storage/service 顺序回归分别覆盖
target-local `UNSAFE` 与 shared manifest untrusted，均保持 `SourceIntegrityRevisionConflictError -> SOURCE_REVISION_STALE`，不误映射
blocked。material whole-kind 没有 repair target，因此直接消费其 typed reason。

### Plan amendment：§11.3 精确矩阵闭环

Controller 明确批准对 frozen call matrix 的最小修订：Phase B 在同一 active staged batch 内执行
`FILING + requested_document_id=<exact target>` 恰一次，并执行 `MATERIAL + requested_document_id=None` 恰一次。前者负责 target
conflict precedence与 filing non-target blocked事实，后者只做 material whole-kind repair preflight；material clean/empty不阻断，任何
material repair仍不在本 slice 范围。该 amendment 是 §11.3 已承诺 material non-target damage 必须投影 `SOURCE_REPAIR_BLOCKED` 的
直接闭环，不扩展到 Slice 5 workflow 或 material repair。

修复后重新验证：affected matrix `345 passed, 1 skipped`；完整 `tests/fins` `1827 passed, 1 skipped`；七个修改生产文件逐文件
branch coverage `80%–97%`（integrity owner `85%`）；全仓 pyright `0 errors, 0 warnings, 0 informations`。

### Re-review 170139：Slice 2 fix D frozen contract 恢复

Controller 将 `docs/reviews/code-review-20260816-170139.md` 的中 severity finding 裁决为 blocker，并拒绝在 Slice 4隐式推翻
Slice 2 fix D。裁决依据是：whole-kind inspection 的 `target=None`，不存在“non-target”所需的参照对象；因此其任一 repairable
incomplete仍必须由冻结 owner contract投影 `CANONICAL_MANIFEST_UNAVAILABLE`，只有 unsafe投影
`CROSS_SOURCE_PUBLICATION_UNSAFE`。

最小修复只调整 `_derive_repair_blocked_reason()` 的 whole-kind分支优先级：unsafe gate之后，whole-kind的content/public/shared/
canonical incomplete统一返回 `CANONICAL_MANIFEST_UNAVAILABLE`；exact-target分支继续跳过target，并把sibling incomplete投影
`NON_TARGET_SOURCE_INCOMPLETE`。Slice 2 direct payload断言已恢复，本 slice material content-missing owner/service断言同步恢复为
`CANONICAL_MANIFEST_UNAVAILABLE`。public `SOURCE_REPAIR_BLOCKED`、Phase B调用次数、reset顺序、rollback与old-tree原子性均未改变。

本次最小裁决后重新运行两份owner files：`294 passed in 15.93s`；重新运行affected matrix：
`345 passed, 1 skipped, 3 warnings in 17.35s`；重新运行全仓pyright：`0 errors, 0 warnings, 0 informations`。完整Fins
`1827 passed, 1 skipped`与逐文件branch coverage `80%–97%` 复用同一fix gate紧邻上一轮结果；本次只改变内部reason值分支，direct
payload、真实service与完整affected matrix均已重新验证。

## 下一入口

Slice 4 code-review fix 已完成并停在 re-review gate。下一步应对当前未提交 diff执行独立 re-review；本 artifact 不表示 re-review
acceptance，也不授权进入 accepted slice commit、Slice 5、commit、draft PR 或 final closeout。
