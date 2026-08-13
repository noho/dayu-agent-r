# UF-FIX02 action-and-update-identity — S1 Code Review Fix

## 1. Gate metadata

- Work unit：`UF-FIX02 action-and-update-identity`
- Gate：`S1 code review fix`
- Binding goal：`docs/gateflow/uf-fix02-action-and-update-identity-goal-confirmation-20260813.md`
- Approved plan：`docs/gateflow/uf-fix02-action-and-update-identity-plan-20260813.md`
- Adjudication：`docs/gateflow/uf-fix02-action-and-update-identity-s1-code-review-adjudication-20260813.md`
- Reviewed implementation：`docs/gateflow/uf-fix02-action-and-update-identity-s1-implementation-20260813.md`
- Reviews：`docs/reviews/code-review-20260813-175624.md`、`docs/reviews/code-review-20260813-180034.md`
- Baseline：`56d159cb4bf13baf82858bb237b2f73075eaf717`
- Branch：`codex/upload-filing-oracle`
- Decision：**FIX PASS**
- Execution policy：local-only；未 commit、未 push、未创建 PR、未进入 re-review。

## 2. First-principles judgment and owner decision

DS-02/03/04 的动机均成立，且严重性与 adjudication 一致：

1. `is_deleted` 由 storage source publication 写入，storage snapshot 与 upload skip 只消费该 canonical business fact；两份逐字相同
   strict reader 使字段存在性、精确 bool 类型与错误语义出现多真源，违反语义所有权约束。
2. CLI 原 projection fixture 从 missing `update + overwrite` 迁移为 `create + overwrite` 后，确实只剩 conflict path 覆盖 update，
   没有成功进入 Service 的 typed handoff 证据。
3. `prepare_upload(...)` 新增了 corruption `KeyError/ValueError` 外抛路径，但公共 Raises 未登记，契约文档不完整。

strict reader 的唯一 owner 定为新建最小
`dayu.fins.storage.source_meta_contract.require_source_meta_is_deleted(...)`，而不是 `repository_protocols.py`。直接证据是
`repository_protocols.py` 当前只承载 Protocol、dataclass 与 typed exception，字段读取/校验是可执行 storage 语义；放入独立 contract
模块可以由 storage 内部与 pipeline 直接依赖同一实现，不把行为塞入协议集合，也不需要 wrapper、facade、lazy import 或兼容导出。
`dayu.fins.storage.__init__` 正式导出新契约名；旧 private reader 直接删除，不保留旧名称。

DS-01 的 material create-existing 缺口不是本 fix 的同一契约：要闭合它必须新增 material typed admission/public failure 设计并修改
material workflow。binding scope 明确禁止本轮实施，因此保持 `deferred-with-owner`，不以删除 filing guard、下游 fallback 或字符串投影
局部止血。

## 3. Changed files

### Production

- `dayu/fins/storage/source_meta_contract.py`
  - 新增 canonical `is_deleted` strict reader 唯一实现；字段缺失抛 `KeyError`，非精确 bool 抛 `ValueError`。
- `dayu/fins/storage/__init__.py`
  - 正式导出 `require_source_meta_is_deleted(...)`。
- `dayu/fins/storage/_fs_source_snapshot.py`
  - acquisition 与 post-copy marker 两个读取点复用公共 helper；删除 `_require_deleted_flag(...)`。
- `dayu/fins/pipelines/docling_upload_service.py`
  - skip owner 复用 storage 公共 helper；删除 `_require_source_deleted_flag(...)`。
  - `prepare_upload(...)` Raises 登记 source-meta corruption `KeyError/ValueError`。

### Tests

- `tests/fins/test_source_meta_contract.py`
  - 新增正式 package export、精确 `False/True`、字段缺失与 `None/int/string` 非 bool fail-closed owner tests。
- `tests/cli/test_fins_commands.py`
  - 新增真实 storage seeded existing filing 的 `update` 与 `update + overwrite` CLI→Service typed handoff，精确断言
    action、overwrite、identity fields 与 stream operation。
  - 既有 missing update ± overwrite conflict tests 保持不变。

### Documentation/artifacts

- `dayu/fins/README.md`
  - 记录 storage 公共 strict reader 与 fail-closed contract。
- `docs/gateflow/uf-fix02-action-and-update-identity-s1-implementation-20260813.md`
  - 补充 fix、最终验证、finding status 与 deferred material residual 证据。
- `docs/gateflow/uf-fix02-action-and-update-identity-s1-code-review-fix-20260813.md`
  - 本 fix artifact。

`tests/README.md` 未修改：其更新边界只要求测试层级、运行方式或维护规则变化时同步；本轮仅在既有 `tests/fins` 与 `tests/cli`
层内补 owner/handoff coverage。

## 4. Tests-first RED evidence

### DS-03 CLI projection RED

新增 update ± overwrite 成功 handoff test 后，先保留 fresh-missing workspace：

```bash
source .venv/bin/activate && pytest \
  tests/cli/test_fins_commands.py::test_upload_filing_existing_update_projects_typed_request_to_service -q
```

结果：exit `1`，`2 failed, 3 warnings in 1.33s`。两个 case 均在 prevalidation 得到 exit `2`，stderr 精确为
`dayu-cli upload_filing: update 目标不存在；请改用 create`，Service factory 未进入。这直接证明成功 handoff fixture 必须先通过
storage owner 发布同 identity filing。随后仅迁移测试 fixture，加入 `_seed_cli_filing_source(workspace_root)`。

### DS-02 shared helper RED

生产 helper/export 尚不存在时先加入 storage owner contract test：

```bash
source .venv/bin/activate && pytest tests/fins/test_source_meta_contract.py -q
```

结果：collection `ImportError: cannot import name 'require_source_meta_is_deleted' from 'dayu.fins.storage'`，exit `2`。

## 5. GREEN and validation

### CLI fixture migration GREEN

真实 storage seed 后重跑 DS-03 test：`2 passed, 3 warnings in 1.23s`，exit `0`。

### Production fix affected suite

```bash
source .venv/bin/activate && pytest \
  tests/fins/test_source_meta_contract.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/cli/test_fins_commands.py::test_upload_filing_existing_update_projects_typed_request_to_service -q
```

结果：`183 passed, 3 warnings in 15.05s`，exit `0`。

### Final S1/storage coverage suite

使用 `mktemp -d` 下独立 coverage data 执行：

```bash
source .venv/bin/activate && python -m coverage run -m pytest \
  tests/fins/test_source_meta_contract.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/cli/test_fins_commands.py -q
```

结果：`428 passed, 3 warnings in 24.53s`，exit `0`。warnings 均来自 `.venv` 中 `edgar` deprecated modules。

| Modified production file | Statements | Miss | Coverage | Result |
| --- | ---: | ---: | ---: | --- |
| `dayu/fins/ingestion_runtime.py` | 2134 | 194 | 91% | PASS |
| `dayu/fins/pipelines/docling_upload_service.py` | 406 | 55 | 86% | PASS |
| `dayu/fins/storage/__init__.py` | 13 | 0 | 100% | PASS |
| `dayu/fins/storage/_fs_source_snapshot.py` | 443 | 63 | 86% | PASS |
| `dayu/fins/storage/source_meta_contract.py` | 13 | 0 | 100% | PASS |

每个修改生产文件均独立达到 `>=80%`。

### Type check

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`，exit `0`；仅有 pyright 新版本提示。

## 6. Finding status

| Finding | Adjudication | Fix status | Evidence |
| --- | --- | --- | --- |
| DS-01 material create-existing | deferred-with-owner | 未修复（按 binding scope） | 未改 material workflow/typed usage；已登记后续独立 work unit |
| DS-02 duplicated strict reader | accepted | 已修复 | storage 公共 helper 唯一实现；snapshot/Docling 复用；两 private readers 删除 |
| DS-03 CLI update projection gap | accepted | 已修复 | seeded existing update ± overwrite 两个成功 typed handoff tests |
| DS-04 `prepare_upload` Raises | accepted | 已修复 | public docstring 登记 corruption `KeyError/ValueError` |

以上是 fix gate 状态，尚未由 re-review 裁决；本任务明确禁止进入 re-review。

## 7. Static, diff and no-touch audit

- `git diff --check`：PASS。
- strict reader 静态扫描：只有 `source_meta_contract.py` 定义实现；snapshot 两处与 Docling 一处均调用同一 helper；不存在
  `_require_deleted_flag` / `_require_source_deleted_flag`。
- `dayu/fins/ingestion_runtime.py:5102` 的既有 `bool(meta.get("is_deleted", False))` 未修改，继续归 `UF-FIX08`。
- 未修改 material workflow/typed usage，未删除 filing-only create-existing guard。
- 未实施 S2 reset/create、未修改 `_resolve_upsert_mode`。
- 未修改 registry、design、evidence；未新增 fallback、compat re-export、wrapper、glue seam、lazy import、`Any`、`object`、
  `hasattr` 或 `getattr`。
- 未 commit、push、创建 PR 或执行 re-review。

## 8. README decision

- `dayu/fins/README.md`：已按其 Agent 更新约束同步当前已实现的 storage public contract 与 fail-closed 语义。
- `tests/README.md`：不更新；测试层级、运行方式与维护规则未变化。
- 根 README / `dayu/README.md`：无用户入口、命令参数、工作流、排障方式、分层或装配边界变化，不触发。

## 9. Residual risks

| Residual | Classification / owner |
| --- | --- |
| material create-existing 可被 skip 或 conversion 后才失败，且尚无 filing 同形 typed admission/public failure contract | deferred-with-owner；后续独立 `upload_material action-contract` work unit |
| existing full-input update 尚未执行 exact complete-set replacement；`_resolve_upsert_mode` 尚未删除 | covered by later approved slice `S2` |
| `ingestion_runtime.py:5102` loose deleted reader 与 existing source corruption repair | assigned to `UF-FIX08` |
| prevalidation/fresh recheck 到 publication 的同请求竞争 | assigned to `UF-FIX10` |
| multi-file primary/collision | assigned to `UF-FIX07` |
| frozen `UF-A08` observed evidence intentionally stale | assigned to later unified conformance refresh；本轮 no-touch |

无未分类 residual risk，无 blocking open question。

## 10. Completion

- Completion status：**FIX PASS**。
- Accepted DS-02/03/04 均已修复并有 RED/GREEN、coverage 与 pyright 证据。
- DS-01 保持 deferred-with-owner，未越界修改 material/S2/UF-FIX08。
- Artifact path：`docs/gateflow/uf-fix02-action-and-update-identity-s1-code-review-fix-20260813.md`。
- Next Gateflow entry：`S1 re-review`；本任务明确禁止进入，故停止在 fix gate。
