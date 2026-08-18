# UF-FIX02 action-and-update-identity — S1 Implementation

## 1. Gate metadata

- Work unit：`UF-FIX02 action-and-update-identity`
- Gate：`implementation`
- Slice：`S1 — Action admission and logical-deleted no-skip`
- Binding scope：`docs/gateflow/uf-fix02-action-and-update-identity-goal-confirmation-20260813.md`
- Approved plan：`docs/gateflow/uf-fix02-action-and-update-identity-plan-20260813.md`
- Baseline accepted-plan commit：`56d159cb4bf13baf82858bb237b2f73075eaf717`
- Branch：`codex/upload-filing-oracle`
- Decision：**S1 IMPLEMENTATION PASS**
- Execution policy：local-only；implementation 后已完成指定 code review fix；未 commit、未 push、未创建 PR、未进入 re-review。

## 2. Scope and owner decision

问题真实且根因与 approved plan 一致：shared Docling admission owner 把 explicit `update + missing + overwrite=True`
错误放行为 upsert，skip owner 未消费 canonical logical-deletion fact，usage owner 的文案又错误建议 overwrite。修复位于三个唯一
语义 owner：

1. `evaluate_upload_overwrite_precondition(...)` 拥有 create/update admission matrix；
2. `_can_skip_upload(...)` 拥有 active identical input 的 no-op 条件；
3. `_USAGE_MESSAGES` 拥有 `FinsUploadUsageCode.UPDATE_TARGET_MISSING` 的唯一 public 文案。

canonical logical deletion 直接来自 published `source_meta["is_deleted"]`。code review fix 将严格 reader 收敛到
`dayu.fins.storage.source_meta_contract.require_source_meta_is_deleted(...)` 唯一 owner，并通过 storage 公共 contract boundary
正式导出；storage snapshot 与 upload skip 两个消费者直接复用该实现。字段缺失抛 `KeyError`、非精确 `bool` 抛
`ValueError`；未使用 `get`、默认值、fallback 或 loose truthiness。filing identity 继续由既有 canonical ticker、fiscal
year、normalized fiscal period 与 amended owner 生成，不接收文件名。

本 slice 未修改 publication mutation；未执行 S2 的完整集合 reset/create、`_resolve_upsert_mode` 删除或跨市场 workflow 集成改造。

## 3. Changed files and symbols

### Production

- `dayu/fins/pipelines/docling_upload_service.py`
  - `evaluate_upload_overwrite_precondition(...)`：update-missing 无条件返回
    `UPDATE_TARGET_MISSING`；overwrite 只允许 create-existing。
  - `_can_skip_upload(...)`：仅 active、非 overwrite、非空同指纹 source 可以 skip。
  - 直接复用 storage 公共 strict reader；删除重复 `_require_source_deleted_flag(...)`。
  - `prepare_upload(...)` Raises docstring 登记 source-meta corruption 的 `KeyError/ValueError`。
- `dayu/fins/ingestion_runtime.py`
  - `_USAGE_MESSAGES[FinsUploadUsageCode.UPDATE_TARGET_MISSING]`：精确改为
    `update 目标不存在；请改用 create`。
- `dayu/fins/storage/source_meta_contract.py`
  - 新增 canonical `is_deleted` strict reader 唯一 owner。
- `dayu/fins/storage/__init__.py`
  - 正式导出 `require_source_meta_is_deleted(...)`，形成新的公共契约，不保留旧 reader 名称。
- `dayu/fins/storage/_fs_source_snapshot.py`
  - 两个 snapshot 读取点直接复用公共 strict reader；删除重复 `_require_deleted_flag(...)`。

### Tests

- `tests/fins/test_fins_ingestion_runtime.py`
  - 新增 update-missing ± overwrite、create-existing false/true、deleted auto→update 与 renamed-file stable identity owner tests。
- `tests/fins/test_docling_upload_service.py`
  - 新增 filing/material update-missing ± overwrite converter-zero-call parity；
  - 新增 filing create-existing pre-conversion conflict；
  - 新增 canonical deleted bool fail-closed；
  - 新增 deleted + equal fingerprint 必须再次 conversion 的 owner test。
- `tests/cli/test_fins_commands.py`
  - 新增真实 storage published-state CLI conflict matrix与 workspace tree digest；
  - 固定 update-missing ± overwrite/create-existing conflict 均在 Service factory 前 exit `2`、stdout empty、精确单行 bounded
    stderr、business tree零 mutation；
  - 将旧参数映射测试从 missing `update + overwrite` 迁移为允许的 `create + overwrite`，不再固化 upsert 偶然行为。
  - 新增通过真实 storage seed 的 existing filing `update` 与 `update + overwrite` 成功 CLI→Service typed handoff。
- `tests/fins/test_source_meta_contract.py`
  - 新增 storage owner contract/export 测试，覆盖精确 bool、字段缺失与非 bool fail closed。
- `dayu/fins/README.md`
  - 记录 storage 公共 strict reader 与 fail-closed 语义；`tests/README.md` 因测试层级、运行方式和维护规则均未变化而不更新。
- `docs/gateflow/uf-fix02-action-and-update-identity-s1-implementation-20260813.md`
  - 本 implementation artifact。

除上述文件与 gate/review artifacts 外无写入；Service、material workflow、registry、design 与 evidence 均未修改。

## 4. Tests-first RED evidence

生产修复前执行：

```bash
source .venv/bin/activate && pytest \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_docling_upload_service.py \
  tests/cli/test_fins_commands.py -q
```

结果：exit `1`，`9 failed, 259 passed, 3 warnings in 11.03s`。精确 failure 集合：

- validator update-missing `overwrite=False` 文案仍包含“或允许覆盖”；
- validator update-missing `overwrite=True` 未抛 `FinsUploadUsageError`；
- filing/material update-missing `overwrite=True` 未在 converter 前抛 `FileNotFoundError`；
- canonical `is_deleted` 缺失或为字符串时未 fail closed；
- deleted + equal fingerprint 返回 `skipped` 而非 `uploaded`；
- CLI update-missing false 文案不精确，true 错误 exit `0`。

这组红灯与 owner root cause 同源，没有暴露 S2 或非目标生产依赖。

## 5. GREEN evidence

最小生产修复后的首次 focused run 暴露一个旧测试 pin：新增契约均已通过，但
`test_upload_commands_map_args_and_validate_files` 仍期待 fresh missing `update + overwrite` 成功，结果为
`1 failed, 267 passed`。该测试只验证参数透传，已迁移为 `create + overwrite`，没有增加生产兼容分支。

迁移后执行同一 focused command：exit `0`，`268 passed, 3 warnings in 8.59s`。

coverage run 再次执行相同三文件测试：`268 passed, 3 warnings in 9.87s`。code review fix 的新增 RED/GREEN 与最终
coverage 证据见 §9。

## 6. Validation

### S1 affected tests

- Command：见 §4。
- Result：`268 passed`，exit `0`。
- 三条 warning 均来自 `.venv` 中 `edgar` deprecated module，与本 slice 无关。

### UF-FIX01 / atomicity / cancellation regressions

```bash
source .venv/bin/activate && pytest \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_storage_provider.py \
  tests/fins/test_docling_process_converter.py \
  tests/fins/test_fins_service_runtime.py \
  tests/service/test_fins_direct.py \
  tests/cli/test_import_boundary.py -q
```

结果：`343 passed, 3 warnings in 27.48s`，exit `0`。fresh authoritative、zero mutation、atomic batch、bounded failure
与 cancellation/commit linearization 未回归。

### Per-production-file coverage

使用 `mktemp -d` 下的独立 coverage data，未在 repo 写 coverage artifact：

| Production file | Statements | Miss | Coverage | Result |
| --- | ---: | ---: | ---: | --- |
| `dayu/fins/pipelines/docling_upload_service.py` | 406 | 55 | 86% | PASS |
| `dayu/fins/ingestion_runtime.py` | 2134 | 194 | 91% | PASS |
| `dayu/fins/storage/__init__.py` | 13 | 0 | 100% | PASS |
| `dayu/fins/storage/_fs_source_snapshot.py` | 443 | 63 | 86% | PASS |
| `dayu/fins/storage/source_meta_contract.py` | 13 | 0 | 100% | PASS |

五个修改生产文件分别高于 `80%`，未用 aggregate coverage 替代单文件结论。最终 coverage run 为
`428 passed, 3 warnings in 24.53s`。

### Type check

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`，exit `0`。仅报告 pyright `1.1.409 -> 1.1.411` 可升级提示。

### Diff, docs and frozen no-touch

- `git diff --check`：PASS。
- `git diff --exit-code -- docs/cli_ci_scenarios.json docs/cli_ci_oracles.json docs/host/design.md docs/engine/design.md`：PASS。
- Frozen digest 保持：
  - `docs/cli_ci_scenarios.json`：`a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`
  - `docs/cli_ci_oracles.json`：`88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`
- README trigger：按 `dayu/fins/README.md` 的更新约束记录新增 storage 公共契约；`tests/README.md` 的测试层级、运行方式和
  维护规则未变化，因此不更新。

### Static audit

- 新增 diff 中无 `Any`、`object`、`hasattr`、`getattr`、lazy import、compat wrapper/re-export。
- S1 logical-deletion 路径无 `get/default/fallback`、loose bool 或 basename/stem identity。
- action rule 只改 shared owner；无 CLI/Service duplicated rule、字符串异常分类或 `str(exc)` public projection增量。
- storage diff 仅包含 owner contract、正式 package export 与 snapshot consumer 迁移；无 Service/material workflow/registry/design/
  evidence diff，无反向依赖。
- 无 S2 reset/create publication 改造。现存 `_resolve_upsert_mode`、overwrite-only reset 及其旧 internal helper test 按 approved plan
  留给 S2 删除/迁移；S1 admission 已使 missing-update publication 分支不可达。
- 所有新增/修改函数均有严格类型与完整中文 docstring（参数、返回、异常）。

## 7. Residual risks and uncovered areas

| Residual | Classification / owner |
| --- | --- |
| existing full-input update 仍未执行 exact complete-set reset/create；renamed update 可能残留旧文件 | covered by later approved slice `S2` |
| `_resolve_upsert_mode` 与 overwrite-only reset 尚未收敛 | covered by later approved slice `S2` |
| material create-existing 仍可能 skip 或 conversion 后失败，尚无 filing 同形 typed admission/public failure contract | deferred-with-owner：后续独立 `upload_material action-contract` work unit；本 S1 不改 material workflow/typed usage |
| prevalidation/fresh recheck 到 publication 的同请求竞争 | assigned to `UF-FIX10` |
| existing source corruption auto repair 与 `ingestion_runtime.py:5102` loose deleted reader | assigned to `UF-FIX08`；S1 仅统一本调用链 strict reader并对损坏 deletion flag fail closed |
| multi-file primary/collision | assigned to `UF-FIX07` |
| broader summary/error、format、company warning 与 full-real conformance | 按 approved plan 分别归属 `UF-FIX03`、`UF-FIX06`、`UF-FIX11`、`UF-PF12` |
| frozen `UF-A08` observed evidence 在修复后 intentionally stale | assigned to later unified conformance refresh；本 slice no-touch |

所有 residual 均已有 approved destination；无未分类或需要本 slice 扩 scope 的风险。

## 8. Completion

- Completion status：**S1 IMPLEMENTATION PASS**。
- Admission、logical-deleted no-skip、stable filing identity、filing CLI typed boundary与 zero-mutation success signals 已满足；material
  create-existing 缺口按 DS-01 明确 deferred，不宣称 material 全矩阵闭合。
- S2 publication mutation 明确未开始。
- Artifact path：`docs/gateflow/uf-fix02-action-and-update-identity-s1-implementation-20260813.md`。
- Next Gateflow entry：`S1 re-review`；本任务明确禁止进入 re-review，因此未执行。

## 9. S1 code review fix addendum

### Finding status

- DS-01：`deferred-with-owner`，未修改 material create-existing workflow/typed usage；见 §7 residual。
- DS-02：`已修复`，strict reader 收敛到 storage 公共 owner，两个 private reader 已删除。
- DS-03：`已修复`，新增 seeded existing filing 的 update ± overwrite CLI→Service typed handoff。
- DS-04：`已修复`，`prepare_upload(...)` Raises 已登记 corruption `KeyError/ValueError`。

### Tests-first RED / GREEN

- CLI RED：在尚未 seed existing filing 时运行新增 handoff test，两个参数 case 均以 exit `2` 失败，精确原因均为
  `update 目标不存在；请改用 create`；结果 `2 failed, 3 warnings in 1.33s`。随后只迁移测试 fixture，通过真实 storage owner
  seed published filing，结果 `2 passed, 3 warnings in 1.23s`。
- storage helper RED：新增 owner/export contract test 后，在生产 helper 尚不存在时 collection `ImportError`，exit `2`。
- 生产 fix 后 affected suite：`183 passed, 3 warnings in 15.05s`，覆盖 helper、Docling consumer、storage snapshot/atomicity consumer
  与 CLI handoff。
- 最终 S1 + storage coverage suite：`428 passed, 3 warnings in 24.53s`。
- 完整 pyright：`0 errors, 0 warnings, 0 informations`。

### Fix completion

- Decision：**FIX PASS**。
- Fix artifact：`docs/gateflow/uf-fix02-action-and-update-identity-s1-code-review-fix-20260813.md`。
- 未 commit、未 push、未创建 PR、未进入 re-review。
