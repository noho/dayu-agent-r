# UF-FIX08 existing-source-auto-repair：Slice 1 implementation

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`implementation`
- slice：`Slice 1：冻结 public integrity/state/repair contracts`
- 日期：2026-08-16
- accepted plan commit：`c8e75629`
- accepted plan：`docs/gateflow/uf-fix08-existing-source-auto-repair-plan-20260816.md`
- design inputs：`docs/host/design.md`、`docs/engine/design.md`
- re-review inputs：
  - `docs/reviews/code-review-20260816-132522.md`
  - `docs/reviews/code-review-20260816-132720.md`
- completion status：`ACCEPTED`
- artifact path：`docs/gateflow/uf-fix08-existing-source-auto-repair-slice1-implementation-20260816.md`
- blocking questions：无
- 下一入口：Slice 2 `统一 filesystem inspector`

## Scope 与 owner 裁决

本 slice 只冻结 storage-owned publication integrity、upload published state、repair disposition 与 repository method shape。
Host/Engine 不拥有财报业务语义，未修改 Host、Engine、Service、CLI production、tool schema、EventLog、memory、trace 或 lifecycle。

implementation preflight 直接证据显示：

- accepted plan 要删除旧 public reason `PHYSICAL_FILE_MISSING`，冻结以 `DECLARED_FILE_MISSING` 为 generic declared-file reason 的 fresh
  closed enum；
- 当前 `_fs_source_document_core.py` 第 647、671 行仍直接引用旧 enum member；
- 若不修改这两处，删除旧 member 后 focused runtime 与全仓 pyright 都无法闭合；保留 alias 又会违反 fresh schema 与禁止兼容代码约束。

Controller 裁决动机成立，并批准 implementation-time boundary amendment：把
`dayu/fins/storage/_fs_source_document_core.py` 纳入 Slice 1，但只允许上述两处
`PHYSICAL_FILE_MISSING -> DECLARED_FILE_MISSING` 机械替换。accepted plan 的 Slice 1 allowed files 与 step 1 已记录该 amendment。
实际 diff 仅有这两处 enum member 替换，没有实现 Slice 2 inspector、改变 classifier precedence 或修改其它 source-document 逻辑。

## 实际修改

### Public integrity contract

- `SourceIntegrityStatus` 新增 `UNSAFE`。
- `SourceIntegrityReason` 删除旧 physical reason，按 accepted plan 冻结 9 个 repairable reasons 与 9 个 unsafe reasons；enum 顺序同时是
  classification reasons 的唯一稳定顺序。
- `SourceIntegrityClassification` 强制四态 revision/reasons 不变量：
  - `MISSING`：无 revision、无 reasons；
  - `COMPLETE`：required trusted revision、无 reasons；
  - `REPAIR_REQUIRED`：required trusted revision、非空且仅 repairable reasons；
  - `UNSAFE`：固定无 revision、非空且仅 unsafe reasons。
- reasons 必须按 enum 顺序去重；错误类型、重复或乱序组合均拒绝构造。
- `__post_init__` 在末分支显式要求 `status is UNSAFE`；未来新增 enum member不能静默继承UNSAFE不变量。
- `has_same_source_publication_identity()` 对任一 `UNSAFE` 输入立即 `ValueError`，其余只比较同 target presence/revision。
- preflight 新增 `UNSAFE_PUBLICATION` 并在 inventory 出现 unsafe 时优先 fail closed。
- 新增 `SourceIntegrityRepairBlockedReason/Error`；错误不携带 target、revision、路径或 raw reason。
- `SourceIntegrityRevisionConflictError` 收窄为 Phase A 与 staged presence/revision/repair status 不再匹配的 path-free typed conflict。

### Upload state 与 repository protocol

- `FilingUploadPublishedState` 新增 required `source_integrity`，无 default、无 dual-read、无从 `source_meta` 反推。
- state owner 强制 filing kind 与 status/meta presence：`MISSING/UNSAFE -> source_meta=None`，
  `COMPLETE/REPAIR_REQUIRED -> source_meta required`。
- `_FsFilingUploadStateMixin.read_filing_upload_state()` 在现有 publication guard 内调用当前
  `_classify_source_integrity_unguarded()`，再从同一 guarded view读取 business meta；fresh absent 仍保持既有 lock-free、无目录副作用路径，
  但显式返回 required `MISSING` classification。该临时 classifier 调用将在已批准 Slice 3 机械替换为 Slice 2 inspector payload。
- Slice 1临时读取对既有 source required meta或identity descriptor缺失会path-free fail closed，不再静默视为absent；protocol/mixin
  Raises与真实filesystem owner tests已闭合该异常面。Slice 2/3将其从临时raw structural failure收敛为`UNSAFE` typed state。
- `SourceDocumentRepositoryProtocol` 冻结 required `reset_source_document_for_repair(...) -> None` method shape 与异常面。
- Slice 1 不授权 repair mutation：protocol 的 concrete rejection helper确定性抛 `NotImplementedError`，避免 concrete repository/fake 被
  pyright 视为 abstract，也避免 inherited stub 静默返回成功；真实 Phase B 实现属于已批准 Slice 4。

### Repair union 与 exports

- 新增 `dayu/fins/upload_repair_contract.py`：immutable `NoExistingSourceRepair`、`ExistingSourceAutoRepair` 与 closed type alias。
- `ExistingSourceAutoRepair` 只接受携带 trusted revision 的 `REPAIR_REQUIRED` filing classification。
- storage package 导出新增 repair-blocked public types；repair disposition 从其独立业务模块导出，不建立兼容 re-export。

### Tests 与 fixtures

- storage contract tests覆盖 exact enum set/order、四态非法组合、unsafe first/second/both comparison、cross-target comparison、unsafe
  preflight、repair union、repair-blocked reason、published/staged existing classifier generic missing reason及未授权 mutation rejection。
- ingestion runtime tests新增 upload state owner-level invariant，并用私有 typed helper为每个 request 显式构造 exact target、matching
  classification 与 source meta presence；没有 production default/fallback。
- Service direct fixture通过`ingestion_runtime._filing_upload_request_identity(raw_request)`真源取得canonical ticker/document ID，不新增
  Docling pipeline import；CLI保留base已有identity import且没有扩张依赖。两者均显式构造required exact filing classification并保持原
  direct/CLI contract回归。
- storage owner tests真实删除published source的`meta.json`与identity descriptor，断言读取抛path-free fail-closed异常且corrupted tree
  bytes/structure零mutation。
- 全仓 `FilingUploadPublishedState(...)` direct constructors 已收敛到允许文件中的 production owner或显式 test fixture。

## Changed files

- `dayu/fins/storage/source_integrity.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/_fs_filing_upload_state_core.py`
- `dayu/fins/storage/_fs_source_document_core.py`（仅两处 Controller 批准的机械替换）
- `dayu/fins/storage/__init__.py`
- `dayu/fins/upload_repair_contract.py`（新）
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_ingestion_runtime.py`（required fixture/type contract）
- `tests/service/test_fins_direct.py`（fixture迁移/direct contract回归）
- `tests/cli/test_fins_commands.py`（fixture迁移/CLI contract回归）
- `docs/gateflow/uf-fix08-existing-source-auto-repair-plan-20260816.md`（Controller 要求的 boundary amendment）
- `docs/gateflow/uf-fix08-existing-source-auto-repair-slice1-implementation-20260816.md`（本 artifact）

## Validation

运行环境：仓库 `.venv`，Python 3.11。

指定 focused suite：

```text
python -m pytest tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/service/test_fins_direct.py \
  tests/cli/test_fins_commands.py -q

637 passed, 3 warnings in 27.33s
```

3 条 warning 均来自已安装 `edgar` 包的 deprecated import，不是本 slice 新增 failure。

implementation中间态曾记录protocol method字面`raise NotImplementedError`后出现129个`reportAbstractUsage`。code-review fix gate按
Controller要求在当前完整仓库diff上删除helper/`NoReturn`并恢复字面raise，再运行精确全仓命令：

```text
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

结果可复现为`130 errors, 0 warnings, 0 informations`；首个错误是
`dayu/fins/pipelines/cn_pipeline.py:392:56`不能实例化`FsSourceDocumentRepository`，末个错误是
`tests/tools/test_combined_tools_acceptance.py:890:25`同一`reportAbstractUsage`。全部错误均指向
`SourceDocumentRepositoryProtocol.reset_source_document_for_repair is not implemented`。相对初次129条增加的1条来自implementation后新增的
`test_source_repository_repair_contract_rejects_mutation_before_owner_implementation`实例化，因而数量差异有直接代码来源；review中的隔离probe
没有覆盖全仓现有Protocol显式子类与实例化图，不能替代该精确命令。

因此恢复repository-protocol owner内的`NoReturn` rejection helper：它同时保持runtime确定性拒绝、避免继承空body静默成功，并使当前全仓
concrete repositories/fakes保持可实例化；不是仅为绕过单文件或关闭pyright规则。accepted plan已进一步冻结Slice 4删除transitional
body/helper、production facade显式delegate真实core owner与facade owner test的接管路径。最终结果：

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

- 现存 pyright errors：0
- 本 slice 新增且未修复 pyright errors：0
- `git diff --check`：通过
- 未运行 UF-PF08、UF-PF12、真实 CLI、provider 或 converter evidence。
- 未修改 registry、oracle、scenario、frozen evidence、Host/Engine design。
- 未 commit、未 push、未创建 PR。

## README decision

- `dayu/fins/README.md`：命中 Fins stable contract 触发，但当前仅完成 public contract slice，inspector、validator authorization、Phase B
  repair、workflow 与 download 尚未落地；依 accepted plan 由已批准 Slice 6 在完整行为成立后一次更新。分类为
  `covered by later approved slice`。
- `tests/README.md`：新增 owner-level contract assertions，但未新增测试层级或改变当前运行规则；accepted plan仍要求 Slice 6汇总完整
  auto-repair/unsafe/stale/downstream矩阵与 focused 命令。分类为 `covered by later approved slice`。
- 根 `README.md`：本 slice 没有用户可见 CLI 参数、输出、工作流或排障变化，不更新。
- `dayu/README.md`：没有改变 `UI -> Service -> Host -> Engine` 分层或 Fins assembly，不更新。

当前 slice allowed files 不包含 README，未越界修改。

## Residual risks 与 uncovered areas

| residual / uncovered area | 分类与 owner |
| --- | --- |
| 当前 filesystem classifier 仍只产生既有 physical subset；完整 structural/role/manifest classification 与 `UNSAFE` producer 尚未落地 | `covered by later approved slice`：Slice 2 unified inspector |
| filing upload state 当前使用 accepted plan要求的临时 existing classifier；required meta/descriptor损坏已由doc/test保证path-free零mutation fail-closed，但尚未成为`UNSAFE` typed state | `covered by later approved slice`：Slice 2产出inspection，Slice 3机械接入state |
| validator 尚未产生 `ExistingSourceAutoRepair`，也未实现 status/action/selection precedence | `covered by later approved slice`：Slice 3 |
| repository repair method 只冻结 contract并确定性拒绝调用，没有 reset、revision recheck、manifest rewrite 或其它 mutation；transitional helper与facade接管路径已写入plan | `covered by later approved slice`：Slice 4删除helper/body、facade delegate真实core并补owner test |
| Docling skip bypass、SEC/CN/HK wiring、download unsafe、snapshot/commit unified inspection 均未实现 | `covered by later approved slice`：Slices 2、4、5、6 |
| Fins/test README 尚未描述完整最终行为 | `covered by later approved slice`：Slice 6 |

没有未分类 residual risk。UF-FIX10、UF-FIX11、material repair、old-schema migration、真实 evidence/registry 仍按 accepted plan归属各自后续
work unit，不因本 slice 扩大范围。

## Code review fix

- 完整读取并接受`docs/reviews/code-review-20260816-130711.md`与`docs/reviews/code-review-20260816-131113.md`全部findings。
- finding逐项裁决、直接证据、修复与状态记录在
  `docs/gateflow/uf-fix08-existing-source-auto-repair-slice1-code-review-adjudication-20260816.md`。
- accepted plan已补Slice 2/3 damaged-state typed收敛、Slice 4 protocol/facade接管、Slice 5 fresh read+validator typed event边界。

## Re-review acceptance

两路独立 re-review 均为 PASS：

- `docs/reviews/code-review-20260816-132522.md`：7项既有findings全部闭环，plan amendments已落地，无新blocking finding；
- `docs/reviews/code-review-20260816-132720.md`：复核代码、owner边界、plan amendments与A/B证据后再次PASS，无新blocking
  correctness/ownership/scope finding。

逐项最终闭环结论：

| finding | 最终结论 |
| --- | --- |
| `CR-130711-001` protocol rejection helper | `已修复/已裁决闭环`；全仓A/B与排除目录外probe均证明helper是Slice 4接管前的必要transitional rejection design |
| `CR-130711-002` Service/CLI fixture跨层依赖 | `已修复`；Service改用request identity真源，CLI未扩张既有依赖 |
| `CR-131113-01` Slice 4 production facade接管路径 | `已修复（plan层面）`；allowed files、helper删除、facade delegate与owner test均已冻结 |
| `CR-131113-02` pyright错误叙事证据 | `证据失效并撤回`；原review probe被`workspace` exclude，非排除路径probe与全仓A/B均支持当前adjudication证据 |
| `CR-131113-03` damaged state异常面与owner tests | `已修复`；protocol/mixin Raises、真实filesystem fail-closed与零mutation tests、后续typed收敛均闭环 |
| `CR-131113-04` 显式UNSAFE gate | `已修复`；future-member contract test证明四态封闭 |
| `CR-131113-05` Service fixture identity owner | `已修复`；与`CR-130711-002`同一真源修复闭环 |

最终验证数字与状态：focused四文件为`637 passed, 3 warnings`（第二路re-review复现用时`27.20s`）；全仓pyright为
`0 errors, 0 warnings, 0 informations`；两路re-review均确认`git diff --check`通过。3条warning仍来自第三方`edgar`
deprecated imports。所有residual risks均已分配给approved later slices，没有未分类风险。

## 下一入口

Slice 1已接受。下一 gate 入口是Slice 2 `统一 filesystem inspector`；本次acceptance bookkeeping不创建accepted slice commit，遵守
Controller“不提交”的明确约束。
