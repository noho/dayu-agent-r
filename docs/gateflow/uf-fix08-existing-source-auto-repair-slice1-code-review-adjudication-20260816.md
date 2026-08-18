# UF-FIX08 existing-source-auto-repair：Slice 1 code review adjudication

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`code review fix`
- slice：`Slice 1：冻结 public integrity/state/repair contracts`
- 日期：2026-08-16
- accepted plan commit：`c8e75629`
- review inputs：
  - `docs/reviews/code-review-20260816-130711.md`
  - `docs/reviews/code-review-20260816-131113.md`
- re-review inputs：
  - `docs/reviews/code-review-20260816-132522.md`
  - `docs/reviews/code-review-20260816-132720.md`
- Controller decision：接受两份review的全部findings
- completion status：`ACCEPTED`
- artifact path：`docs/gateflow/uf-fix08-existing-source-auto-repair-slice1-code-review-adjudication-20260816.md`
- blocking questions：无
- 下一入口：Slice 2 `统一 filesystem inspector`

## 裁决原则

- 每项finding均以当前仓库直接代码、真实filesystem fixture或完整全仓命令为证据，不用隔离probe替代production/fake继承与实例化图。
- 当前fix只收紧Slice 1 contract、tests与durable artifacts；不实现Slice 2 inspector、Slice 3 eligibility、Slice 4 mutation或Slice 5 workflow。
- structural damage的最终语义owner仍是storage inspector；Slice 1只冻结临时fail-closed异常面并补零mutation owner tests，不在workflow重算
  integrity。
- transitional rejection helper不是永久facade。accepted plan已要求Slice 4删除它，并让production facade显式delegate真实core owner。

## Findings adjudication

### CR-130711-001：Protocol concrete rejection helper 非典型

- decision：`accepted`
- 直接证据：`SourceDocumentRepositoryProtocol`的显式子类会继承method body；空stub会产生runtime静默成功风险。Controller要求先用字面
  `raise NotImplementedError`执行真实全仓pyright再裁决。
- 复现实验：删除`NoReturn` helper/import、method body改为字面raise，运行
  `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`，得到`130 errors`，全部为
  `reportAbstractUsage`。首个是`dayu/fins/pipelines/cn_pipeline.py:392:56`，末个是
  `tests/tools/test_combined_tools_acceptance.py:890:25`，共同原因均为
  `SourceDocumentRepositoryProtocol.reset_source_document_for_repair is not implemented`。
- fix：恢复typed `NoReturn` rejection helper，保持runtime确定性拒绝且全仓concrete repository/fake可实例化；accepted plan Slice 4新增
  删除transitional body/helper、production facade delegate真实core与facade owner test的强制步骤。
- status：`已修复`

### CR-130711-002：Service/CLI fixture跨层依赖

- decision：`accepted`
- 直接证据：Service test新增`dayu.fins.pipelines.docling_upload_service.build_sec_filing_ids` import；同一request identity的实际owner入口是
  `ingestion_runtime._filing_upload_request_identity(request)`。CLI中的Docling helper import属于base已有依赖，并非本slice新增。
- fix：Service fixture改用`raw_filing_request -> ingestion_runtime._filing_upload_request_identity()`取得canonical ticker/document ID，删除新增
  Docling pipeline import；CLI保留既有import且未增加新依赖。
- status：`已修复`

### CR-131113-01：Slice 4缺少production facade接管路径

- decision：`accepted`
- 直接证据：`FsSourceDocumentRepository`只继承`SourceDocumentRepositoryProtocol`并组合`repository_set.core`，不继承
  `_FsSourceDocumentMixin`；只在core实现repair无法让production facade自动获得真实mutation。
- fix：accepted plan的production affected-files与Slice 4 allowed files新增
  `dayu/fins/storage/fs_source_document_repository.py`；明确Slice 4删除protocol transitional rejection body/helper，facade显式override并只
  delegate共享core，不复制status/revision/reason判断；`test_fins_storage_atomicity.py`增加真实facade owner test并移除/迁移Slice 1 rejection test。
- status：`已修复`

### CR-131113-02：129个pyright错误叙事缺少可复现证据

- decision：`accepted`
- 直接证据：review的隔离probe报告0 errors，但不包含全仓现有Protocol显式子类、fakes与实际实例化call sites；artifact原叙事未列精确首尾
  error证据，因而不足以裁决helper必要性。
- fix：按Controller指定A/B步骤在当前完整diff上重跑。字面raise得到130个同源`reportAbstractUsage`；相对implementation初轮129条增加的
  1条来自之后新增的`test_source_repository_repair_contract_rejects_mutation_before_owner_implementation`实例化。implementation artifact已
  回写精确命令、数量、首尾错误、差异来源与helper恢复理由；不把helper描述为单文件类型绕过。
- status：`已修复`

### CR-131113-03：damaged upload-state read异常面与owner tests未闭合

- decision：`accepted`
- 直接证据：当前临时classifier在既有source目录缺少`meta.json`时抛path-free `ValueError`；source identity descriptor缺失也经identity
  owner抛path-free `ValueError`。旧state read会捕获`FileNotFoundError`并错误投影为absent；新方向必须保持fail closed。
- fix：
  - 更新`FilingUploadStateRepositoryProtocol.read_filing_upload_state()`与mixin Raises，明确required meta/descriptor缺失或结构损坏属于
    `ValueError` fail-closed面，operational descriptor/meta读取失败属于path-free `OSError`；
  - 新增两个真实filesystem owner tests：发布完整filing后分别删除`meta.json`与source identity descriptor，断言path-free异常且读取前后
    corrupted tree结构/bytes完全一致；
  - plan Slice 2明确inspector把同类damage投影为`UNSAFE/revision=None`，Slice 3明确state core机械消费inspection并返回
    `UNSAFE + source_meta=None`，Slice 5明确fresh re-read与validator failures一并收敛typed failed event，不留raw
    `ValueError/FileNotFoundError`。
- status：`已修复`

### CR-131113-04：classification末分支缺少显式UNSAFE gate

- decision：`accepted`
- 直接证据：原`__post_init__`在MISSING/COMPLETE/REPAIR_REQUIRED返回后直接执行UNSAFE规则，未来第五个enum member会错误继承UNSAFE
  invariant。
- fix：UNSAFE invariant前新增`if self.status is not SourceIntegrityStatus.UNSAFE: raise ValueError("status 必须是封闭四态")`；contract test
  临时替换为含`FUTURE` member的等形enum，证明未来member命中显式四态gate而不是UNSAFE末分支。
- status：`已修复`

### CR-131113-05：Service fixture绕过request identity owner

- decision：`accepted`
- 直接证据：与CR-130711-002同源；当前validator尚未消费`source_integrity`不代表fixture可以使用惰性、跨pipeline推导，后续Slice 3会要求
  exact target一致。
- fix：Service fixture从raw request调用`ingestion_runtime._filing_upload_request_identity`并同时使用返回canonical ticker/document ID；删除
  新增Docling import，保持future validator fixture可直接复用。
- status：`已修复`

## Validation

- 新增finding-specific nodes：`4 passed, 3 warnings`；warnings均来自第三方`edgar` deprecated imports。
- focused四文件：`637 passed, 3 warnings in 27.33s`；3条warnings均来自第三方`edgar` deprecated imports。
- helper恢复后的最终全仓pyright：`0 errors, 0 warnings, 0 informations`。
- 字面raise A/B实验：`130 errors, 0 warnings, 0 informations`，helper恢复后必须最终回到0 errors。
- `git diff --check`：通过；README、registry、oracle、scenario、evidence、Host/Engine design forbidden-scope diff均为空。

## Re-review acceptance

- `docs/reviews/code-review-20260816-132522.md`裁决为`PASS`：按adjudication口径计数的7项findings全部闭环，plan amendments完整，
  无新blocking finding。
- `docs/reviews/code-review-20260816-132720.md`裁决为`Pass`：按去重口径计数的6项findings中5项已修复，
  `CR-131113-02`因原probe位于pyright排除目录而判定`证据失效`并撤回；非排除路径probe与全仓A/B均独立支持当前helper裁决。

逐项最终状态：

| finding | re-review最终状态 | 闭环证据 |
| --- | --- | --- |
| `CR-130711-001` | `已修复/已裁决闭环` | 字面raise产生全仓`130 errors`且均为`reportAbstractUsage`；helper恢复后全仓0 errors，Slice 4删除路径已冻结 |
| `CR-130711-002` | `已修复` | Service fixture消费`ingestion_runtime._filing_upload_request_identity()`真源，CLI既有import未扩张 |
| `CR-131113-01` | `已修复（plan层面）` | Slice 4纳入production facade、删除transitional helper/body、delegate真实core与facade owner test |
| `CR-131113-02` | `证据失效` | 原隔离probe被`pyrightconfig.json`的`workspace` exclude静默跳过；非排除路径probe及全仓A/B推翻原质疑并支持adjudication |
| `CR-131113-03` | `已修复` | damaged meta/descriptor异常承诺、真实filesystem owner tests、path-free零mutation及Slice 2/3/5 typed收敛均闭合 |
| `CR-131113-04` | `已修复` | 显式UNSAFE gate与future-member contract test已落地 |
| `CR-131113-05` | `已修复` | 与`CR-130711-002`共用request identity owner修复 |

最终验证为focused四文件`637 passed, 3 warnings`（第二路re-review复现用时`27.20s`），全仓pyright
`0 errors, 0 warnings, 0 informations`，`git diff --check`通过。两路re-review均未发现新的blocking
correctness/ownership/scope finding；全部residual risks保持已分类。

## Residual risks

| residual / uncovered area | 分类与owner |
| --- | --- |
| Slice 1 damaged-state read仍以path-free structural exception fail closed，尚未产出`UNSAFE` typed state | `covered by later approved slice`：Slice 2 inspector + Slice 3 state接入 |
| transitional rejection helper仍存在，production facade尚未delegate真实repair owner | `covered by later approved slice`：plan已amend Slice 4删除helper/body、实现facade override与owner test |
| fresh SEC/CN/HK re-read/runtime event尚未收敛全部failure | `covered by later approved slice`：plan已amend Slice 5 fresh read+validator同一typed event boundary |
| 当前classifier仍不产生完整structural/role/manifest UNSAFE reasons | `covered by later approved slice`：Slice 2 |

没有未分类residual risk；README仍由Slice 6更新，registry/oracle/evidence仍属后续evidence work unit。

## 下一入口

Slice 1 code review loop已接受。下一gate入口为Slice 2 `统一 filesystem inspector`；依Controller明确约束，本次不创建accepted slice
commit。
