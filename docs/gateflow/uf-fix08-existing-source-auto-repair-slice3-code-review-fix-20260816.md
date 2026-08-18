# UF-FIX08 Slice 3 code-review fix

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`code review -> fix`
- slice：`Slice 3：upload state 与 repair eligibility`
- 日期：2026-08-16
- baseline HEAD：`a29c8eb5437660318d60d9c4456c5de384f9c453`
- review artifact：`docs/reviews/code-review-20260816-153600.md`
- implementation artifact：`docs/gateflow/uf-fix08-existing-source-auto-repair-slice3-implementation-20260816.md`
- completion status：`FIX COMPLETE / awaiting re-review`
- 下一入口：Slice 3 re-review

## Scope 与裁决

Controller 将 review Finding 1 提升为 blocker，并接受同 artifact 的 Findings 2–4 在本 fix gate 闭环。修复范围只包括：

- selection projection 唯一 owner；
- 三处中文 Raises contract；
- SEC/CN workflow identity guard 的真实测试覆盖；
- storage derived projection 的直接分类回归；
- 本 fix artifact 与 Slice 3 implementation artifact同步。

不修改 repair publication/reset、workflow production、oracle、scenario、design、evidence、registry 或 README；不进入 Slice 4/5，
不 commit。

## Finding 状态

| Finding | 状态 | 证据 |
| --- | --- | --- |
| 1：selection owner duplicated | `已修复` | `_project_fins_upload_filing_selection()` 是 duplicate/cardinality/implicit primary/membership/companions 的唯一纯 projection owner，返回 closed failure 或 immutable success；static 与 direct constructor 均调用该函数，旧 helper 已删除 |
| 2：Raises 遗漏 | `已修复` | state read补 `RuntimeError`；validated/helper补 `FinsUploadUsageError` |
| 3：workflow identity guard 测试空洞 | `已修复` | SEC/CN 注入 `internal_document_id` 漂移并断言 workflow 固定 RuntimeError与零 batch |
| 4：矛盾 derived projection 无测试 | `已修复` | exact A identity + B basename 为 `REPAIR_REQUIRED/DERIVED_PROJECTION_MISMATCH`；ambiguous basename fallback仍为 `UNSAFE` |

没有 `部分修复`、`证据失效` 或未分类 finding。

## Owner 设计

共享 helper只接受已规范化、保序的 `tuple[Path, ...]`，不读取 filesystem、不产生 usage 文案。失败面为封闭 enum：missing files、
duplicate path、multiple selectors、missing multi-file primary、primary not in files。success保存唯一 primary与保序 companions，并由同一
projection构造 `FinsUploadFilingFiles`。

static admission仍按原顺序完成 ticker/action/fiscal/delete/path normalization，再把 closed failure映射到原
`FinsUploadUsageCode`；逐文件 basename、exists、regular、role format顺序不变。validated constructor复用同一 normalization与 projection，
只把 closed failure暴露为 `ValueError`，path normalization的 typed `FinsUploadUsageError` 仍属于既有 `ValueError` surface。

## Changed files for this fix

- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/storage/_fs_filing_upload_state_core.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_cn_pipeline.py`
- `docs/gateflow/uf-fix08-existing-source-auto-repair-slice3-implementation-20260816.md`
- `docs/gateflow/uf-fix08-existing-source-auto-repair-slice3-code-review-fix-20260816.md`

## Validation

```text
pytest -q tests/fins/test_fins_ingestion_runtime.py
310 passed, 3 warnings in 4.62s

pytest -q <storage derived projection node + SEC/CN identity mismatch nodes>
3 passed, 3 warnings in 1.17s

完整 focused matrix（无 deselect）
1181 passed, 3 warnings in 47.27s

pytest -q tests/fins
1802 passed, 1 skipped, 3 warnings in 49.83s

coverage focused matrix + test_upload_failure（无 deselect）
1196 passed, 3 warnings in 54.44s
_fs_source_integrity.py          85%
_fs_filing_upload_state_core.py  93%
upload_repair_contract.py         82%
ingestion_runtime.py              88%
upload_failure.py                 92%

python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

- `git diff --check`：通过。
- 新增 diff 无 `object`、`Any`、`hasattr/getattr` 或伪 callable cast。
- README/oracle/scenario/design diff：无输出。
- 未运行真实 CLI/provider/converter evidence。
- HEAD 未变化；未 commit、push 或创建 PR。

## Docs decision

用户明确禁止 README 修改；本 fix不改变最终用户工作流或 public CLI/schema，README保持无 diff。implementation artifact按要求记录本次
review fix；review artifact作为只读裁决输入未修改。

## Residual risks

| residual | 分类 / owner |
| --- | --- |
| staged reset、revision recheck与repair publication尚未实现 | `covered by later approved slice`：Slice 4 |
| stale/blocked publication failure及SEC/CN/HK async typed event尚未接线 | `covered by later approved slice`：Slice 4/5 |
| material existing-source repair | `assigned to later work unit` |
| 旧 schema migration | `assigned to later work unit`（若另行授权） |
| UF-PF08/UF-PF12真实 evidence及registry/oracle状态 | `assigned to later work unit` |
| 合法并发更新与company warning | `assigned to later work unit`：UF-FIX10 / UF-FIX11 |

没有未分类 blocking risk。

## 下一入口

当前 fix 已完成，停在 Slice 3 re-review gate。不得在 re-review acceptance 前进入 accepted slice commit或后续 slice。
