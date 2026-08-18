# UF-FIX08 existing-source-auto-repair：Slice 4 code-review fix

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`code review -> fix`
- slice：`Slice 4：Docling preparation 与 staged repair owner`
- 日期：2026-08-16
- baseline / current HEAD：`1fd52c96f5e07f6007c3c6442d20635f3d37182b`
- accepted plan：`docs/gateflow/uf-fix08-existing-source-auto-repair-plan-20260816.md`
- implementation artifact：`docs/gateflow/uf-fix08-existing-source-auto-repair-slice4-implementation-20260816.md`
- review artifacts：`docs/reviews/code-review-20260816-163507.md`、`docs/reviews/code-review-20260816-170139.md`
- Controller decision：163507 Finding 1（高）与 Finding 2（中）为 blocker、Finding 3（低）同 gate闭环；
  170139 Finding 1（中）为 blocker并恢复 Slice 2 fix D frozen contract
- completion status：`CODE REVIEW FIXED / awaiting re-review`
- blocking questions：无
- 下一入口：Slice 4 re-review

## Controller scope 与 plan amendment

Controller 授权额外修改 `dayu/fins/storage/_fs_source_integrity.py`，因为
`_derive_repair_blocked_reason()` 是唯一 repair-blocked reason owner；其余改动仍限于 Slice 4 已授权 production/tests/artifacts。
没有越界到 SEC/CN/HK fresh reread、workflow event、material repair、README、oracle、scenario 或 evidence。

为闭环 accepted plan §11.3 的 material non-target 精确矩阵，Controller 批准最小 plan amendment：Phase B 在同一 active staged batch
内保留 `FILING + exact target` inspection 恰一次，并追加 `MATERIAL + whole-kind` inspection 恰一次。material clean/empty 不阻断；
material repair仍是 non-goal。该 amendment 只补足 already-promised `SOURCE_REPAIR_BLOCKED` typed projection，不增加新 workflow。

## Finding 裁决与修复状态

### Finding 1：material source damage 对 Phase B 不可见

- severity：高
- Controller decision：`accepted / blocker`
- 最终状态：`已修复`

修复：

- `reset_source_document_for_repair()` 在同一 batch staging tree 中执行 filing exact inspection一次；target conflict gate与 identity comparison
  通过后，再执行 material whole-kind inspection一次。
- material inspection 的 typed `repair_blocked_reason` 直接转为 `SourceIntegrityRepairBlockedError`；whole-kind inspector 因 root structural
  fact 抛出的 `SourceIntegrityPreflightError` 精确映射为
  `CROSS_SOURCE_PUBLICATION_UNSAFE`，不会泄漏到 commit-time普通 `ValueError`。
- filing与material任一 blocked 均发生在 target reset 前；service 既有 exact catch继续唯一投影
  `SOURCE_REPAIR_BLOCKED`，caller-owned batch恰好 rollback一次。
- material source clean与source root empty均允许 repair继续；未实现 material repair。

直接测试证据：

- storage successful facade测试用 inspector counter锁定调用序列：
  `[(FILING, exact target), (MATERIAL, None)]`，并在同一 fixture 保留 complete material；既有无material成功路径覆盖empty。
- service真实 filesystem测试分别注入 material declared content missing、material manifest missing、material root unexpected file，断言 public code
  固定为 `SOURCE_REPAIR_BLOCKED`，内部 reason分别为 `CANONICAL_MANIFEST_UNAVAILABLE`、
  `CANONICAL_MANIFEST_UNAVAILABLE`、`CROSS_SOURCE_PUBLICATION_UNSAFE`。
- 三类 failure 均断言 rollback calls `1`、commit calls `0`、published old tree SHA不变、filing/material meta不变、无单独 company meta、
  active batch为空且 batch root清空。

### Finding 2：repair-blocked predicate 双 owner且闭合不一致

- severity：中
- Controller decision：`accepted / blocker`
- 最终状态：`已修复`

修复：

- `_fs_source_integrity._derive_repair_blocked_reason()` 成为唯一 predicate owner。
- exact mode 从完整 inventory 排除 target，再检查所有 non-target 的 unsafe、content完整性、public reasons与shared reasons一致性，以及
  canonical item availability；whole-kind mode没有target/non-target参照，依 Slice 2 fix D把repairable content/public/shared/canonical
  incomplete统一关闭为 `CANONICAL_MANIFEST_UNAVAILABLE`。
- `SOURCE_MANIFEST_UNTRUSTED` 与 root structural fact闭合为 `CROSS_SOURCE_PUBLICATION_UNSAFE`；whole-kind shared repairable manifest问题闭合为
  `CANONICAL_MANIFEST_UNAVAILABLE`；non-target content/public mismatch闭合为 `NON_TARGET_SOURCE_INCOMPLETE`。
- `_fs_source_document_core` 删除对 content status、classification status/reasons 的二次业务判断，只机械消费 inspection reason并收集
  non-target `canonical_manifest_item`。
- owner声称 clean而 item document-id shape或unique不变量违约时，core抛固定 producer-invariant `RuntimeError`；不重新发明 blocked reason。

直接测试证据：

- owner-level whole material测试锁定 content missing与manifest missing均为 `CANONICAL_MANIFEST_UNAVAILABLE`。
- synthetic typed payload测试锁定 sibling manifest projection mismatch 由owner产生
  `NON_TARGET_SOURCE_INCOMPLETE`，Phase B collector机械传播同一 reason。
- producer-invariant测试用 clean typed payload注入canonical item identity mismatch，断言固定 `RuntimeError`而非
  `SourceIntegrityRepairBlockedError`。

### Controller 增量顺序审计

Controller 进一步裁决 filing blocked reason只能在 target presence/status/content conflict gate及
`has_same_source_publication_identity()` 之后消费。最终顺序为：

```text
filing exact inspect once
-> target presence gate
-> target staged status/content conflict gate
-> target publication identity comparison
-> material whole-kind inspect once
-> filing non-target blocked reason
-> material whole-kind blocked reason
-> reset target
-> rewrite filing manifest
```

因此 target-local `UNSAFE` 与 shared manifest untrusted即使 inspection同时携带 cross blocked reason，也优先抛
`SourceIntegrityRevisionConflictError`，service精确投影 `SOURCE_REVISION_STALE`。storage drift grid新增 `shared_untrusted`，service真实 staged
failure grid新增 `target_unsafe` 与 `shared_untrusted`，均验证未误投影 blocked。material whole-kind没有 repair target，故可直接消费其
typed reason。

### Finding 3：fail-closed 与 manifest rewrite failure缺测试

- severity：低
- Controller decision：`accepted / 同 gate闭环`
- 最终状态：`已修复`

新增测试：

- union之外的 `repair_disposition` 抛固定
  `ValueError("repair_disposition 必须是封闭 repair contract")`。
- delete mutation携带 `ExistingSourceAutoRepair` 抛固定
  `ValueError("delete 上传不得携带 existing source repair 授权")`。
- patch真实 `_rewrite_source_manifest_for_repair()` 所消费的 `_write_json` 抛 `OSError`，证明 target staging reset之后 caller恰好rollback一次，
  commit未开始，old tree SHA/source meta/company meta不变且 batch cleanup完成。

### Re-review 170139 Finding 1：不得隐式推翻 Slice 2 fix D

- severity：中
- Controller decision：`accepted / blocker；恢复 Slice 2 frozen contract`
- 最终状态：`已修复`

第一性原理裁决：whole-kind inspection 的 `target=None`，没有可定义“non-target”的参照对象。Slice 2 fix D 已据此冻结：whole-kind
repairable incomplete固定为 `CANONICAL_MANIFEST_UNAVAILABLE`，unsafe固定为
`CROSS_SOURCE_PUBLICATION_UNSAFE`。Slice 4接入 material whole-kind只增加该payload的consumer，不授权重定义owner reason。

最小修复：

- `_derive_repair_blocked_reason()` 先保持 whole/exact共用unsafe gate；随后 whole-kind独立分支把任一repairable content/public/shared/
  canonical incomplete收敛为 `CANONICAL_MANIFEST_UNAVAILABLE`并返回。
- exact-target分支保持以target为参照排除target，sibling content/public incomplete仍返回
  `NON_TARGET_SOURCE_INCOMPLETE`。
- 恢复 Slice 2 direct payload断言；本 slice material content-missing owner/service expected reason同步改为
  `CANONICAL_MANIFEST_UNAVAILABLE`。
- public service仍统一投影 `SOURCE_REPAIR_BLOCKED`；Phase B inspection次数、target conflict precedence、reset前失败、rollback exactly once与
  old-tree/company/source-meta不变量均未改变。

## Changed files

本 fix新增或实质修改：

- `dayu/fins/storage/_fs_source_integrity.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_docling_upload_service.py`
- `docs/gateflow/uf-fix08-existing-source-auto-repair-slice4-implementation-20260816.md`
- `docs/gateflow/uf-fix08-existing-source-auto-repair-slice4-code-review-fix-20260816.md`

工作树中的其它 Slice 4文件仍是同一未提交 implementation diff；本 fix未扩大它们的语义。

## Validation

定向类型检查与repair节点：

```text
python -m pyright \
  dayu/fins/storage/_fs_source_integrity.py \
  dayu/fins/storage/_fs_source_document_core.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_docling_upload_service.py
0 errors, 0 warnings, 0 informations

pytest -q tests/fins/test_fins_storage_atomicity.py -k 'repair or material_whole_inspection or damaged_fixture' \
  tests/fins/test_docling_upload_service.py -k repair
37 passed
```

两份完整 owner test files：

```text
pytest -q tests/fins/test_fins_storage_atomicity.py tests/fins/test_docling_upload_service.py
294 passed in 15.93s
```

完整 affected matrix：

```text
pytest -q --tb=short \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_docling_upload_service_integration.py

345 passed, 1 skipped, 3 warnings in 17.35s
```

完整 Fins suite与branch coverage：

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

全仓类型检查：

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

唯一skip是环境变量门控的真实Docling integration；3条warning均来自已安装 `edgar` 包的deprecated imports。

170139 Controller裁决后的验证边界：两份owner files、完整affected matrix与全仓pyright均重新运行并得到上述最新结果；完整Fins
`1827 passed, 1 skipped`与逐文件branch coverage `80%–97%` 复用同一fix gate紧邻上一轮结果。此次最小变更只恢复whole-kind内部
reason值，direct payload、exact sibling reason、真实material service failure与public rollback矩阵均已包含在重新运行的测试中。

## Docs decision

用户明确禁止本 slice 修改 README，且本 fix只闭环 internal staged integrity owner与测试矩阵，不改变完整最终用户workflow。
`README.md`、`dayu/fins/README.md`、`tests/README.md` 均保持无diff；oracle、scenario、evidence亦未修改。

## Residual risks 与后续 owner

| residual / 未覆盖项 | 分类与 owner |
| --- | --- |
| SEC/CN/HK fresh authoritative reread、typed failed event与workflow failure projection | covered by later approved Slice 5 |
| material existing-source repair | assigned to later work unit；本 fix只阻断damaged material，不授权修复 |
| 下载/snapshot/downstream完整workflow与README汇总 | covered by later approved Slice 5/6 |
| 旧 schema compatibility/migration | assigned to later migration work unit（若授权） |
| 一般并发更新 | assigned to UF-FIX10；本 slice只做authorized repair staged recheck |
| 真实CLI/provider evidence与oracle/scenario状态 | assigned to UF-PF08/UF-PF12 evidence work unit |

没有未分类blocking risk。Findings 1–3均已修复；re-review 尚未执行。

## 下一入口

Slice 4 code-review fix已完成并停在 re-review gate。下一步应对当前未提交diff执行独立re-review；本 artifact不表示re-review
acceptance，也不授权进入accepted slice commit、Slice 5、aggregate deepreview、draft PR或commit。
