# UF-FIX08 existing-source-auto-repair：Slice 2 implementation

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`implementation`
- slice：`Slice 2：统一 filesystem inspector`
- 日期：2026-08-16
- accepted plan commit：`cc07db75`
- accepted plan：`docs/gateflow/uf-fix08-existing-source-auto-repair-plan-20260816.md`
- design inputs：`docs/host/design.md`、`docs/engine/design.md`
- review inputs：`docs/reviews/code-review-20260816-142141.md`（FAIL）、`docs/reviews/code-review-20260816-143020.md`（PASS）
- completion status：`CODE REVIEW FIXED / awaiting re-review`
- blocking questions：无
- 下一入口：Slice 2 re-review

## 动机与 owner 裁决

动机成立。Slice 2 前，published/staged classifier、snapshot 与 commit validator 分别解析 source meta、业务文件和 manifest，存在同一
publication fact 被多个 consumer 重建的语义漂移风险。按 accepted plan §6.1，filesystem publication 完整性由
`dayu/fins/storage/_fs_source_integrity.py` 唯一拥有；document core、snapshot 与 commit validator 只消费同一次 typed inspection
payload。staging URI equality、ticker key/root containment、batch/swap/recovery 继续属于 commit validator，不进入 inspector。

本 slice 没有重新确认 goal，也没有扩展 repair、workflow、validator eligibility、Host、Engine、README、registry、oracle 或 evidence
范围。code-review fix cycle 仅按 Controller 明确授权同步 batching/upload-state owner contract 与私有 seam；没有实现 Slice 3 的 validator
eligibility 或 mutation。

## 实际修改

### 统一 filesystem inspector

- 新增 frozen `_InspectedSourceFile`、`_SourcePublicationInspection`、`_SourceKindPublicationInspection` typed payload，以及 accepted plan
  冻结的 exact-target/whole-kind `_inspect_source_kind_unguarded(...)` 和 snapshot COMPLETE gate。
- 一次 source-kind scan 同时产生稳定 document-ID inventory、target-local/content classification、shared manifest reasons、逐 source
  canonical item、全量 canonical aggregate 与 repair-blocked fact。
- canonical manifest item 只由 `FilingManifestItem` / `MaterialManifestItem` 从 trusted persisted meta 生成，不从现存 manifest 复制。
- fresh user-upload filing 严格要求至少一个 explicit original、唯一 primary Docling、`original_filename` 与 `derived_from` 精确关系；material
  与 download filing 保持 generic declared-file contract，不增加 fallback 或旧 schema shim。
- required meta、identity descriptor、revision、provenance、file declaration、actual tree 与 manifest 的结构损坏均闭合为 typed
  `REPAIR_REQUIRED` / `UNSAFE` reasons；既有 unsafe target 固定 `revision=None`。只有 whole-kind 无法归属 root corruption 时抛
  `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`。
- operational filesystem failures 继续经 storage utility 投影为 path-free `OSError`；inspector 不获取 publication guard、不解析 batch
  capability，也不拥有 staging URI 语义。

### Consumer 迁移

- `_fs_source_document_core.py`：published/staged exact classifier 机械投影 exact target；inventory 在单一 publication guard 内对 filing、
  material 各调用一次 whole-kind inspector，并按稳定 document ID 投影。删除本文件重复 classification、meta/file/manifest parser。
- `_fs_source_snapshot.py`：在既有 publication guard、marker retry 与 FD lifecycle 内消费 exact inspection；meta、provenance、revision、files、
  primary 全部来自同一 COMPLETE payload。保留 open-FD copy、`fstat`/digest、marker retry、close/cleanup；repairable/unsafe 固定抛
  `ValueError("source snapshot 只允许读取完整 source")`，missing 保持 `FileNotFoundError`。
- `_fs_storage_infra.py`：commit validator 对 staging filing/material 各调用一次 whole-kind inspector，要求 content/public classification
  均为 COMPLETE，canonical manifest 与实际 inventory exact equality。URI equality、staging ticker key/root containment、batch owner、swap、
  journal 与 recovery 状态机仍由原 commit owner 执行。
- revision meta field、revision parser 与 business-meta projection helper 统一由 inspector 拥有；document core 与 snapshot直接依赖该真源，
  infra 不保留常量、helper 或兼容 re-export。

### Tests 与 fresh fixtures

- 三份 allowed tests 中旧 upload/user_upload generic fixtures 已迁移为 UF-FIX07 fresh explicit original、primary Docling 与 companion role
  contract；没有为旧 schema 放宽 production inspector。
- repairable grid 覆盖 original missing、primary Docling missing、generic declared missing、physical/meta size 与 digest mismatch、primary/
  derived projection mismatch、manifest missing 与 target projection mismatch，并断言 trusted revision 保持。
- unsafe grid 覆盖 identity、meta、revision、provenance、file declaration、undeclared file、symlink、FIFO special entry、multiple Docling、
  role ambiguity 与 physical missing 组合、manifest duplicate/dangling/ticker conflict、cross-source inconsistency；全部断言无 revision。
- owner tests直接比较同一 guard/batch 中 exact/whole inventory、shared reasons、canonical facts；证明 staged/published classifier、snapshot 与
  commit消费同一 payload。
- 调用次数测试证明 inventory 与 commit 对 filing/material 各恰好一次 whole-kind 调用；既有 commit validation grid 继续覆盖 staging
  `local://` URI mismatch、filename/URI containment escape 与 symlink escape拒绝。
- snapshot tests明确覆盖 COMPLETE-only、repairable/unsafe 固定 ValueError、missing FileNotFoundError，以及已有 FD/marker/lifecycle 并发回归。

## Changed files

Production：

- `dayu/fins/storage/_fs_source_integrity.py`（新）
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/storage/_fs_source_snapshot.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/repository_protocols.py`（Controller 授权的 Raises contract 同步）
- `dayu/fins/storage/fs_batching_repository.py`（Controller 授权的 Raises contract 同步）
- `dayu/fins/storage/_fs_filing_upload_state_core.py`（Controller 授权的 typed-state contract 同步）
- `dayu/fins/storage/fs_filing_upload_state_repository.py`（同一 public facade contract 同步）

Tests：

- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_processor_read_consistency.py`

Artifact：

- `docs/gateflow/uf-fix08-existing-source-auto-repair-slice2-implementation-20260816.md`

两份 review artifact 是本 fix cycle 的只读输入，由 review gate 生成；fix 未修改它们。

## Code review adjudication

| finding / Controller 裁决 | 状态与证据 |
| --- | --- |
| A：FAIL review #1，`commit_batch` 未声明 `SourceIntegrityPreflightError` | `已修复`；protocol 与 filesystem facade Raises 均声明 whole-tree 无法归属的 structural corruption；真实 descriptor corruption test断言 exception type、closed reason 与 capability终态消费 |
| B：FAIL review #2，upload-state behavior/docstring漂移 | `已修复`；保留 `UNSAFE/revision=None/source_meta=None` typed state；private seam改收 caller-held-guard ticker root，避免 inspector 前读取 damaged descriptor；core、protocol、facade Raises同步，meta/descriptor缺失 tests均断言 typed state与零mutation |
| C：FAIL review #6，trusted manifest + local UNSAFE虚构cross/shared reason | `已修复`；trusted manifest item存在但 damaged source无法产生canonical projection时不制造 mismatch；exact/whole均只保留local unsafe reason，shared reasons为空；独立 shared/content冲突仍产生cross reason |
| D：FAIL review #7，whole-kind `NON_TARGET_SOURCE_INCOMPLETE`语义失真 | `已修复`；whole-kind repairable incomplete固定 `CANONICAL_MANIFEST_UNAVAILABLE`，unsafe仍为`CROSS_SOURCE_PUBLICATION_UNSAFE`；direct payload tests覆盖两分支 |
| E：FAIL review #8 + PASS review #2，revision field/helper双owner | `已修复`；常量、revision parser、business-meta projection只在inspector定义；snapshot/document core直接import真源，infra定义已删除，无兼容re-export |
| F：FAIL review #3，commit通用 `ValueError` 文案 | `covered by later approved slice`；按Controller裁决不按raw reason字符串分支，Slice 5 bounded failure projection拥有公共failure语义 |
| G：FAIL review #4 exact扫描成本 | `residual / assigned to later work unit`；§6.1明确冻结exact扫描完整inventory，性能量化/契约调整不属于UF-FIX08 Slice 2 |
| FAIL review #5 containment | `rejected-with-reason`；`physical_path`由inspector以normalized单组件name构造，`physical_path.parent`即document directory；不改FD/open复核 |
| PASS review #1 marker retry旧读取 | `covered by later approved slice / pre-existing`；Controller要求保持marker retry与resource lifecycle，本fix不迁移 |
| PASS review #3 inventory排序 | `rejected-with-reason`；固定kind tuple与inspector内document-ID sort已提供稳定顺序，无correctness defect |

## Validation

运行环境：仓库 `.venv`，Python 3.11。

三份 allowed tests：

```text
pytest -q --tb=short \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_storage_provider.py \
  tests/fins/test_processor_read_consistency.py

351 passed, 3 warnings in 27.55s
```

3 条 warning 均来自已安装 `edgar` 包的 deprecated import，不是本 slice 新增 failure。

全仓类型检查：

```text
python -m pyright
0 errors, 0 warnings, 0 informations
```

逐文件 statement coverage 使用目录形式 `--source=dayu/fins/storage` 运行同一 351-test suite；模块名形式的首次尝试因 coverage 预导入四个
module 而触发 macOS NumPy `cannot load module more than once per process` 收集错误，未执行测试、未产生代码失败。最终可复现结果：

```text
dayu/fins/storage/_fs_source_integrity.py        86%
dayu/fins/storage/_fs_source_document_core.py    84%
dayu/fins/storage/_fs_source_snapshot.py         92%
dayu/fins/storage/_fs_storage_infra.py            85%
dayu/fins/storage/_fs_filing_upload_state_core.py 98%
dayu/fins/storage/fs_batching_repository.py       94%
dayu/fins/storage/fs_filing_upload_state_repository.py 100%
dayu/fins/storage/repository_protocols.py         92%
TOTAL                                             87%

351 passed, 3 warnings in 30.42s
```

- `git diff --check`：通过。
- scope guard：原 Slice 2 四个 production files、三份 tests、本 artifact，以及 Controller 明确授权的四个 owner-contract files发生变更；
  两份 review artifacts为review gate输入。
- `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/host/design.md`、`docs/engine/design.md` diff：无输出。
- 全部修改均未 commit、未 push、未创建 PR。
- 未运行真实 CLI、UF-PF08、UF-PF12、provider/converter evidence。

## README decision

用户明确禁止本 slice 修改 README；accepted plan 也把最终 README 汇总放在后续 slice。当前变更是 private storage owner 与内部 consumer
迁移，没有改变已发布 CLI 参数、tool schema 或最终用户工作流，因此本 slice 不修改 README。

## Residual risks 与 uncovered areas

| residual / uncovered area | 分类与 owner |
| --- | --- |
| old upload/user_upload generic schema 被 fresh inspector 拒绝，未提供 compatibility reader 或 migration | accepted plan 明确 residual；后续独立 migration work unit（若授权） |
| whole-kind 无法归属的 root structural corruption 以 typed preflight fail closed，不能投影到单一 target | frozen §6.1 contract；后续 caller只消费 typed preflight，不在 inspector猜归属 |
| exact-target mode 按§6.1扫描完整source-kind inventory，large corpus性能尚未量化 | Controller记录residual；后续独立performance work unit，当前不修改冻结契约 |
| manual filesystem writer 不受 repository publication guard协调 | storage operational policy residual；本 slice通过 Phase B/commit双检查缩小窗口但不承诺外部 writer治理 |
| upload state 已通过现有private classifier seam消费typed inspector classification，但Slice 3 validator eligibility尚未实现 | approved Slice 3 owner；本fix仅同步真实typed-state owner contract |
| repair authorization、staged reset/revision recheck、canonical manifest rewrite尚未实现 | approved Slice 3/4 owners |
| commit内部仍使用通用path-free `ValueError`，未把raw reasons重新格式化为公共failure | Controller裁决由Slice 5 bounded failure projection拥有，不在本slice按reason字符串分支 |
| snapshot marker retry保留既有独立revision读取 | Controller要求保持FD/marker/resource lifecycle；后续若迁移必须独立验证retry语义 |
| workflow、download unsafe投影、README与最终 evidence尚未完成 | approved later slices；registry/oracle/evidence 未修改 |
| material existing-source repair未授权 | 后续独立 work unit；本 slice仅统一读取与 commit完整性 |
| 合法并发更新与 company warning | 分别归属 UF-FIX10、UF-FIX11 |

没有未分类 blocking risk。

## 下一入口

Slice 2 code-review accepted findings 已完成fix并停在 re-review 入口。下一步应对当前未提交 diff执行独立 re-review；本 artifact不表示
re-review acceptance，也不授权继续 Slice 3。
