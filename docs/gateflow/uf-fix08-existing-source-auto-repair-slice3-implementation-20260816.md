# UF-FIX08 existing-source-auto-repair：Slice 3 implementation

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`implementation`
- slice：`Slice 3：upload state 与 repair eligibility`
- 日期：2026-08-16
- baseline HEAD：`a29c8eb5437660318d60d9c4456c5de384f9c453`
- accepted plan：`docs/gateflow/uf-fix08-existing-source-auto-repair-plan-20260816.md`
- 前置 implementation：`docs/gateflow/uf-fix08-existing-source-auto-repair-slice2-implementation-20260816.md`
- 前置 reviews：`docs/reviews/code-review-20260816-142141.md`、`docs/reviews/code-review-20260816-143020.md`、
  `docs/reviews/code-review-20260816-144206.md`、`docs/reviews/code-review-20260816-144447.md`
- code review：`docs/reviews/code-review-20260816-153600.md`
- completion status：`CODE REVIEW FIXED / awaiting re-review`
- blocking questions：无
- 下一入口：Slice 3 re-review

## 动机与语义 owner 裁决

动机成立。Slice 2 已把 filesystem publication 完整性收敛到 typed inspector，但 upload-state 仍通过临时 classifier/meta 双读 seam，
validator 也没有把 `REPAIR_REQUIRED` 与 `UNSAFE` 转化为封闭 repair authorization / failure contract。若在 workflow、CLI 或 service
从 raw meta、异常字符串或文件存在性重判，将再次产生多 owner 漂移。

本 slice 的 owner 边界如下：

- `_fs_source_integrity.py` 是 filesystem source identity、role 与完整性分类唯一 owner；upload-state 只消费 inspection payload。
- `FilingUploadPublishedState` 是 validator 的唯一 published-state 输入；`MISSING/UNSAFE` 不携带 meta，`COMPLETE/REPAIR_REQUIRED`
  携带同次 inspection 的 trusted business meta。
- `validate_fins_upload_filing_request()` 是 repair eligibility 唯一 producer；`ValidatedFinsUploadFilingRequest.repair_disposition` 是后续
  consumer 可机械消费的 required typed contract。
- `upload_failure.py` 是 public failure code、文案和 retry hint 唯一 owner；本 slice 只将 `SOURCE_INTEGRITY_UNSAFE` 接入 prevalidation。
- raw runtime start 复用 validator 的 typed exception，并保持 validation 位于 job/observation 创建前；不落入 generic `str(exc)`。

未实现 reset、repair publication、workflow failure event 捕获或 Slice 5 语义；未从 consumer 增加 raw meta/path/异常文本 fallback。

## 实际修改

### Upload-state 与 immutable repair contract

- `_fs_filing_upload_state_core.py` 在同一既有 publication guard 内调用一次 exact-target inspector，同时取得 classification 与
  `business_meta`；删除临时 `_classify_source_integrity_unguarded()` / `_get_source_meta_unguarded()` seam。
- `MISSING/UNSAFE` 固定投影 `source_meta=None`；`COMPLETE/REPAIR_REQUIRED` 只使用同一 inspection 的非空 trusted business meta。
- `NoExistingSourceRepair` 与 `ExistingSourceAutoRepair` 保持 frozen/slots union，并严格校验 discriminator；existing repair 只接受
  `SourceKind.FILING + REPAIR_REQUIRED + trusted revision`。
- `ValidatedFinsUploadFilingRequest.repair_disposition` 为 required field，无 default、无旧构造兼容。其 `__post_init__` 校验 exact
  canonical ticker/document/filing target、published status、raw action exact `auto`、resolved `update`、expected classification exact
  equality，以及 non-empty 全量 file selection 与 raw request 的 primary/companions 精确一致。

### Validator precedence 与 runtime propagation

- static admission 后先校验 published target identity 与 status/meta invariant。
- `UNSAFE` 在 action/company decision 前抛
  `FinsUploadPrevalidationError(fins_upload_source_integrity_unsafe_failure())`。
- `REPAIR_REQUIRED` 仅 raw action 精确为 `auto` 时固定解析为 `update` 并产生 `ExistingSourceAutoRepair`；`create/update/delete`、大小写或
  带空白的伪 auto 均产生固定 `EXISTING_SOURCE_REPAIR_REQUIRES_AUTO` usage error。`overwrite` 与 logical deleted 不改变 repair eligibility。
- `MISSING` 与 `COMPLETE` 继续使用原 action/overwrite/deleted 解析并产生 `NoExistingSourceRepair`；company decision 保持最后解析。
- runtime start/observed start 的 Raises contract 显式包含 `FinsUploadPrevalidationError`。owner tests证明 raw start 在 durable job、
  observation、executor、runner 与 workspace mutation 前原样传播 typed failure；未增加 generic exception 持久化路径。

### Closed storage failures

- 新增 `SOURCE_INTEGRITY_UNSAFE`、`SOURCE_REVISION_STALE`、`SOURCE_REPAIR_BLOCKED` 三个 storage-kind closed code及唯一模块级 factory。
- 三个 factory 的 message/retry hint 均固定、path-free、无 revision/internal reason；JSON round-trip 保持 exact kind/code。
- 本 slice 仅 validator 使用 unsafe factory；stale/blocked factory 留给 accepted Slice 4/5 exact typed publication boundary，不提前接线。

### Controller 授权的 UF-FIX07 前置回归修复

完整 focused matrix 首次暴露两个既有 same-basename/ambiguous-primary 用例在 Slice 2 commit inspector 中失败。直接证据是
`_classify_role_projection()` 把 `original_filename` basename 的全局唯一性误当 authoritative asset identity，导致两个 storage-owned
name 不同、basename 相同的合法 originals 无法产生 canonical inspection。

Controller 明确裁决该回归不得排除或记录为残留，并授权回到唯一 owner `_fs_source_integrity.py` 修复。最小修复为：

- authoritative identity 只取已验证且唯一的 storage name；Docling `derived_from` 精确命中该 storage name后，只校验该 asset 的
  `original_filename` 同源，不要求不同 assets 的 basename 全局唯一。
- exact `derived_from` 损坏时，只有 basename 唯一命中一个 original 才投影 repairable derived mismatch；同 basename 命中多个 originals
  仍闭合为 `UNSAFE/FILE_DECLARATION_UNTRUSTED`。
- 既有重复 storage name、多个 Docling 与真实 role ambiguity 拒绝规则不放宽；没有旧 schema compatibility。

storage integrity 新增直接 owner 回归，同时验证合法 same-basename 为 `COMPLETE`，移除 exact derived identity 后的真实歧义为
`UNSAFE/revision=None`。两个 UF-FIX07 Docling 节点恢复通过，最终所有验证均无 deselect/skip workaround（完整 Fins suite 中唯一 skip
是仓库既有环境条件 skip）。

## Changed files

Production：

- `dayu/fins/storage/_fs_filing_upload_state_core.py`
- `dayu/fins/storage/_fs_source_integrity.py`（Controller 授权的 UF-FIX07 owner 回归修复）
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/upload_failure.py`
- `dayu/fins/upload_repair_contract.py`

Tests：

- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_service_runtime.py`
- `tests/fins/test_upload_failure.py`
- `tests/fins/test_fins_storage_atomicity.py`（Controller 授权的 direct owner regression）
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/cli/test_fins_commands.py`

后三份 consumer tests 只显式迁移 required validated/file-selection fixture contract并保持现有 workflow/CLI 语义；没有修改对应 production
workflow 或 CLI。`repository_protocols.py` 的 required public state shape 已由 Slice 1 提交，本 slice 核对后无需再改。

Artifact：

- `docs/gateflow/uf-fix08-existing-source-auto-repair-slice3-implementation-20260816.md`

## Controller 约束闭环

| Controller 提醒/裁决 | 实现证据 |
| --- | --- |
| `_published_state` fixture 不得以 `status=None` 或 `source_meta` presence 反推 | helper 的 `status`、`reasons` 均为 required keyword；全部调用显式迁移，revision/meta invariants由 `SourceIntegrityClassification` 与 `FilingUploadPublishedState` 构造校验锁定 |
| 新测试 factory 不得使用 `object`/伪 callable cast | 参数为 `collections.abc.Callable[[], FinsUploadFailureReason]`，已删除 cast；新增 diff 静态扫描无 `object`/`Any` 签名 |
| same-basename 两项 failure 不得排除，UF-FIX07 identity contract 不回退 | 在唯一 inspector owner 使用 storage name/role/derived_from，新增 direct integrity 回归；两个原失败节点及无排除 focused/coverage suite全部通过 |

## Code review fix：2026-08-16 复审入口前修复

Controller 将 `docs/reviews/code-review-20260816-153600.md` Finding 1 裁决为 blocker，并要求同 gate 同时闭环 Findings 2–4。
当前 fix 状态如下：

| Finding | 最终状态 | 修复与直接证据 |
| --- | --- | --- |
| 1：validated request 重复实现 static selection 派生规则 | `已修复` | 新增模块级纯 `_project_fins_upload_filing_selection()`，以 closed `_FinsUploadFilingSelectionFailure` 或 immutable projection 返回 files/selectors 的唯一结果；duplicate、selector cardinality、multi-file primary、membership、primary/companions 保序只在该 helper 定义。static 只把 failure 映射为既有 usage code，validated constructor把同一 failure映射为 `ValueError` 并用同一 projection 构造 expected `FinsUploadFilingFiles`；旧 `_select_fins_upload_filing_files()` 删除且无引用 |
| 2：三个 Raises docstring 遗漏 | `已修复` | `read_filing_upload_state()` 补 inspector producer invariant 的 `RuntimeError`；validated `__post_init__` 与 selection validator补 path normalization 可抛的 `FinsUploadUsageError`（其为 `ValueError` 子类） |
| 3：SEC/CN identity mismatch 测试未命中 workflow guard | `已修复` | 两个测试改为只漂移 `internal_document_id`，validated constructor合法构造后由 workflow `_assert_authoritative_filing_identity()` 抛固定 `RuntimeError("filing authoritative identity mismatch")`；继续断言零 batch/publication mutation |
| 4：derived exact identity 与 basename projection矛盾缺直接回归 | `已修复` | storage owner test新增双 original 异名、`derived_from` 精确指向 A、Docling `original_filename` 指向 B basename，断言 trusted revision 保留且仅 `DERIVED_PROJECTION_MISMATCH`；随后 exact derived丢失且同 basename fallback 多命中仍断言 `UNSAFE/revision=None` |

该修复未改变 static validation 的前置字段顺序、path normalization、duplicate-before-selector、membership-before-filesystem、逐文件
basename/existence/regular/role-format 顺序，也未改变 exact primary/companions 或 public usage code/message。

## Validation

运行环境：仓库 `.venv`，Python 3.11。

Slice 3 owner tests：

```text
pytest -q \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py \
  tests/fins/test_upload_failure.py

333 passed, 3 warnings in 4.35s
```

Storage state/integrity owner回归：

```text
pytest -q tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py
297 passed, 3 warnings in 27.35s

pytest -q \
  tests/fins/test_docling_upload_service.py::test_filing_same_basename_assets_are_collision_free_and_path_private \
  tests/fins/test_docling_upload_service.py::test_ambiguous_filing_primary_forces_versions_then_recovers_safe_skip \
  tests/fins/test_fins_storage_atomicity.py::test_source_integrity_uses_storage_name_for_same_basename_asset_identity
3 passed in 0.77s
```

计划完整 focused matrix（无 deselect）：

```text
1181 passed, 3 warnings in 47.27s
```

覆盖率使用同一 focused owner matrix并额外包含 `tests/fins/test_upload_failure.py`，无 deselect：

```text
1196 passed, 3 warnings in 54.44s

dayu/fins/storage/_fs_source_integrity.py          85%
dayu/fins/storage/_fs_filing_upload_state_core.py  93%
dayu/fins/upload_repair_contract.py                 82%
dayu/fins/ingestion_runtime.py                      88%
dayu/fins/upload_failure.py                         92%
```

所有修改生产文件逐文件 branch coverage 均达到 `>=80%`。

完整 Fins suite：

```text
pytest -q tests/fins
1802 passed, 1 skipped, 3 warnings in 49.83s
```

唯一 skip 是仓库既有环境条件 skip；3 条 warning 均来自已安装 `edgar` 包的 deprecated imports。

全仓类型检查：

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

Scope 与格式：

- `git diff --check`：通过。
- 新增 diff 签名扫描：无 `object`、`Any` 或伪 `callable` cast。
- `README.md`、`dayu/fins/README.md`、`tests/README.md` diff：无输出。
- `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/host/design.md`、`docs/engine/design.md` diff：无输出。
- 未修改 workflow repair/publication production、oracle、scenario、evidence、registry 或 README。
- 未运行真实 CLI、provider/converter evidence、UF-PF08 或 UF-PF12。
- 未 commit、未 push、未创建 PR。

## README decision

用户明确要求本 slice 不修改 README，且最终 README 汇总属于后续 accepted slice。本轮 public CLI/tool schema 与最终用户 publication
workflow 尚未改变，因此 README 保持无 diff。

## Residual risks 与后续 owner

| residual / 未覆盖项 | 分类与 owner |
| --- | --- |
| repair disposition 尚未触发 staged reset、revision recheck 或原子 publication | accepted Slice 4；本 slice 只产生 authorization，不修改 source |
| stale/blocked failure factories 尚未接 publication exception | accepted Slice 4/5 exact typed boundary；本 slice 刻意不捕获 publication |
| SEC/CN/HK fresh prevalidation 的 async typed failed event 尚未实现 | accepted Slice 5 workflow projection；raw runtime start 本 slice 已原样传播 |
| material existing-source repair未授权 | 后续独立 work unit；本 slice filing-only fail closed |
| 旧 schema corpus无 compatibility reader/migration | accepted residual；后续显式 migration work unit（若授权） |
| 合法并发更新与 company warning | 分别归属 UF-FIX10、UF-FIX11 |
| 真实 CLI修复 evidence 与 registry/oracle状态 | UF-PF08/UF-PF12 evidence work unit；本 slice 禁止修改 |

没有未分类 blocking risk；UF-FIX07 same-basename regression 已在唯一 owner 修复且全套验证闭环。

## 下一入口

Slice 3 code-review fix 已完成并停在 re-review 入口。下一步应对当前未提交 diff执行独立 re-review；本 artifact 不表示 re-review
acceptance，也不授权进入 accepted slice commit、Slice 4、Slice 5、draft PR 或 commit。
