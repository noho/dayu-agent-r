# UF-FIX02 S2 Code Review — AgentMiMo

## 1. Review metadata

- Work unit: `UF-FIX02 action-and-update-identity`
- Gate: `code review`
- Slice: `S2 — Complete-set replacement, restore, and cross-market propagation`
- Reviewer: AgentMiMo
- Accepted plan: `docs/gateflow/uf-fix02-action-and-update-identity-plan-20260813.md`
- Implementation artifact: `docs/gateflow/uf-fix02-action-and-update-identity-s2-implementation-20260813.md`
- Accepted S1 commit (base): `08316516ca3da7f98299ee90d3fa753c32c59020`
- Branch: `codex/upload-filing-oracle`
- Review date: 2026-08-13

## 2. Review scope

独立核验 S2 uncommitted diff 的 correctness / stability / maintainability。审核维度：

1. shared Docling owner 对任一 existing full-input update/create-overwrite 在同一 caller-owned batch reset exact identity → blob-first → final create
2. reset 前 `previous_meta` 唯一派生 version / `first_ingested_at`
3. same basename / renamed / deleted equal+changed / material parity 是否 active、integrity complete、旧文件消失、非目标 filing/company 不变
4. blob / final create / final checkpoint / precommit cancellation 是否 old-or-new
5. SEC / CN / HK fresh action 是否丢弃 stale preflight 并在 converter / batch 前 fail closed
6. `_resolve_upsert_mode` 是否 Python 源码零命中且无 compat shim / 第二套决策
7. tests-first 证据、coverage >= 80%、pyright、README 三处、frozen registry / oracle / design no-touch
8. 无补偿删除 / 跨 batch / 字符串异常分类 / basename identity / lazy import / fallback / scope drift

## 3. Changed files audit

```
README.md                                              |   2 +
dayu/fins/README.md                                    |   8 +-
dayu/fins/pipelines/docling_upload_service.py          |  64 +---
tests/README.md                                        |   2 +
tests/fins/test_cn_pipeline.py                         | 110 ++++++-
tests/fins/test_docling_upload_service.py              | 362 +++++++++++++++++++--
tests/fins/test_sec_pipeline_upload_filing_stream.py   | 219 ++++++++++++-
```

所有 changed paths 均在 plan §6.1–§6.3 允许范围内。无其它 path 变更。

## 4. Per-criterion verification

### 4.1 `_resolve_upsert_mode` 完整删除

**PASS。** `rg -n '_resolve_upsert_mode' --glob '*.py' .` 零命中。生产代码 `dayu/fins/pipelines/docling_upload_service.py` 中该函数（原 lines 1055–1088）已被完整删除。测试 `test_docling_upload_service.py` 中 `_resolve_upsert_mode` import（原 line 34）和断言 `assert _resolve_upsert_mode("update", None, True) == "create"`（原 line 1880）均已移除。无 compat shim、re-export 或 wrapper 残留。

### 4.2 `replace_existing` 逻辑 — existing update / create-overwrite 都 reset

**PASS。** `docling_upload_service.py:477-479`:

```python
replace_existing = previous_meta is not None and (
    action == "update" or (action == "create" and overwrite)
)
```

此条件对所有 existing target 的 update（不论 overwrite）和 create-overwrite 均触发 `reset_source_document`。reset 后统一走 blob-first + `_create_source_document`（create-only）。旧逻辑 `overwrite and previous_meta is not None and action in {"create", "update"}` 对 `overwrite=False` 的 update 不触发 reset 的缺陷已修复。

### 4.3 `_create_source_document` — 收敛为 create-only

**PASS。** `docling_upload_service.py:784-837`: 原 `_upsert_source_document` 已重命名为 `_create_source_document`，删除 `upsert_mode` 参数，方法体只有 `self._source_repository.create_source_document(request, ...)`。无 update 分支残留。

### 4.4 `evaluate_upload_overwrite_precondition` — update-missing 无条件拒绝

**PASS。** `docling_upload_service.py:186-187`:

```python
if action == "update" and previous_meta is None:
    return UploadOverwritePrecondition.UPDATE_TARGET_MISSING
```

update-missing 不读取 overwrite；overwrite 只影响 create-existing（line 184-185）。与 plan §5.1 矩阵一致。

### 4.5 `_can_skip_upload` — logical deleted 不可 skip

**PASS。** `docling_upload_service.py:990-993`:

```python
if overwrite or previous_meta is None:
    return False
if require_source_meta_is_deleted(previous_meta):
    return False
```

deleted source 直接返回 False，不检查 fingerprint。与 plan §5.1 "skip 只允许 active + !overwrite + non-empty equal source_fingerprint" 一致。

### 4.6 `previous_meta` 在 reset 前持有，作为 version / `first_ingested_at` 真源

**PASS。** `_store_upload_assets` 接收 `previous_meta` 参数（line 443），reset 前该值已保存。`_build_upsert_meta`（line 338-343）在 `prepare_upload` 阶段用 `normalized_previous_meta` 派生 version 和 meta，不依赖 reset 后的 missing state。测试 `test_execute_upload_deleted_input_republishes_complete_source` 断言 `restored_meta["first_ingested_at"] == created_meta["first_ingested_at"]`；`test_execute_upload_existing_full_input_replaces_exact_complete_set` 断言 `final_meta["first_ingested_at"] == initial_meta["first_ingested_at"]`。

### 4.7 Same basename / renamed update — 旧文件消失，完整新集合

**PASS。** 测试 `test_execute_upload_existing_full_input_replaces_exact_complete_set` parameterized 覆盖三种场景：
- `(FILING, "update", False, "report.txt", "report.txt")` — 同名 changed update
- `(FILING, "update", False, "old-report.txt", "renamed-report.txt")` — 改名 update without overwrite
- `(MATERIAL, "create", True, "old-deck.txt", "new-deck.txt")` — material create-overwrite

每种均断言 `published_names == expected_names`（只有新文件名），`final_meta["first_ingested_at"] == initial_meta["first_ingested_at"]`，`final_meta["document_version"] == "v2"`，`integrity.status is SourceIntegrityStatus.COMPLETE`。

SEC workflow 测试 `test_upload_filing_stream_renamed_update_without_overwrite_replaces_complete_set` 断言文件集合精确为 `["q1_renamed.pdf", "q1_renamed_docling.json"]`，非目标 filing meta/files 和 company meta 不变。

CN workflow 测试 `test_upload_filing_stream_auto_resolves_create_update_skip` 断言改名 update 后文件集合为 `["renamed-annual.pdf", "renamed-annual_docling.json"]`。

### 4.8 Deleted equal / changed input — 恢复 active，integrity complete

**PASS。** 测试 `test_execute_upload_deleted_input_republishes_complete_source` parameterized 覆盖：
- `(FILING, False)` — filing deleted equal input
- `(FILING, True)` — filing deleted changed input
- `(MATERIAL, False)` — material deleted equal input

断言 `restored_meta["is_deleted"] is False`、`restored_meta["deleted_at"] is None`、`integrity.status is SourceIntegrityStatus.COMPLETE`、`restored_meta["first_ingested_at"] == created_meta["first_ingested_at"]`。changed input 时 version 递增为 `"v2"`，equal input 时保持原 version。

SEC workflow 测试 `test_upload_filing_auto_after_delete_republishes_active_source` parameterized `(False, True)`，断言 `source_meta["is_deleted"] is False`、`source_meta["deleted_at"] is None`。

### 4.9 Cancellation — blob / final create / precommit 三级

**PASS。** 测试 `test_existing_replacement_cancellation_keeps_entire_published_tree` parameterized `cancel_at=(2, 4, 5)`：

- `cancel_at=2`: blob 循环中第2次 `_is_cancelled`（`docling_upload_service.py:498`）— 第二个 blob 写入前取消
- `cancel_at=4`: `_create_source_document` 之后的 `_is_cancelled`（`docling_upload_service.py:542`）— final create 后取消
- `cancel_at=5`: `commit_prepared_upload_batch` 中的 precommit checkpoint（`docling_upload_service.py:873`）— commit 前最终取消检查

三种均断言 `result.status == "cancelled"`、`published_tree_sha256(tmp_path, "AAPL") == old_tree`、meta 和 blob entries 不变。

### 4.10 Blob failure — 整棵 published tree 不变

**PASS。** 测试 `test_existing_replacement_blob_failure_keeps_entire_published_tree` parameterized `fail_at=(1, 2)`，使用 `_FailingNthUploadBlobRepository` 注入失败。断言 `published_tree_sha256(tmp_path, "AAPL") == old_tree`。

### 4.11 Final create failure — 旧 meta / files / tree 不变

**PASS。** 测试 `test_execute_upload_update_failure_keeps_previous_document` parameterized `overwrite=(False, True)` 断言：
- `failing_source_repository.get_source_meta(...) == old_meta`
- `{entry.name for entry in seed_blob_repository.list_entries(handle)} == old_entries`
- `published_tree_sha256(tmp_path, "AAPL") == old_tree`
- `events[-1] == "create_failed"` — 确认 update 路径现在走 create（因 reset + create-only）

### 4.12 SEC fresh create-existing — converter/batch 前 fail closed

**PASS。** 测试 `test_upload_filing_fresh_create_existing_fails_before_conversion_and_batch` 断言：
- `exc_info.value.failure.code is FinsUploadUsageCode.CREATE_TARGET_EXISTS`
- `calls == []`（converter 零调用）
- `batching.begin_tokens == []`（batch 零开启）
- `published_tree_sha256(tmp_path, "AAPL") == published_tree`

### 4.13 CN/HK fresh update-missing — overwrite 不得授予 upsert

**PASS。** 测试 `test_upload_filing_fresh_missing_update_fails_before_conversion` parameterized `overwrite=(False, True)`：
- 先手动 reset 源文档模拟 fresh missing
- 断言 `exc_info.value.failure.code is FinsUploadUsageCode.UPDATE_TARGET_MISSING`
- `converter.calls == 0`
- `batching.begin_tokens == []`
- `published_tree_sha256(tmp_path, "600519") == published_tree`

### 4.14 Frozen registry / design no-touch

**PASS。** SHA-256 验证通过：
- `docs/cli_ci_scenarios.json`: `a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`
- `docs/cli_ci_oracles.json`: `88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`

`git diff --exit-code` 对 `docs/cli_ci_scenarios.json`、`docs/cli_ci_oracles.json`、`docs/host/design.md`、`docs/engine/design.md` 均通过。

### 4.15 Production diff 静态审计

**PASS。** `git diff --check` 通过。生产 diff (`docling_upload_service.py`)：
- 无新增 `hasattr` / `getattr`
- 无新增 `Any` / `object` 类型
- 无 lazy import
- 无 compat re-export / wrapper
- 无 basename / stem filing identity
- 无字符串异常分类 `str(exc)`
- 无默认 deleted state
- 无下游 fallback
- 无补偿删除 / 跨 batch replacement / ticker 级清空
- 无 `UF-FIX03–08/10/11` 或 `UF-PF03–12` 内容

### 4.16 README 三处更新

**PASS。** 三处 README 均已更新：
- `README.md:318-319`: 最终用户 upload action 语义 — update 不是 upsert、auto 恢复 deleted、完整替换
- `dayu/fins/README.md:110`: 开发文档 — shared publication owner、exact reset、reset 前 meta 真源
- `tests/README.md:370-371`: 测试能力 — S2 owner/workflow coverage

`dayu/README.md` 未更新，符合 plan §10 决策（分层/装配不变）。

### 4.17 `_FailingFinalUploadSourceRepository` dead code

**OBSERVATION。** `tests/fins/test_docling_upload_service.py:94-105`: `_FailingFinalUploadSourceRepository.update_source_document` 方法仍然存在，但 S2 生产代码已不再调用 `update_source_document`（改为 `create_source_document`）。该方法不会被任何测试路径触及。测试已有 `events[-1] == "create_failed"` 断言确认走 create 路径。不影响正确性，但属 dead code。

## 5. Tests-first 证据

S2 implementation artifact §4 报告 RED 4 / GREEN all：

1. `test_execute_upload_existing_full_input_replaces_exact_complete_set[filing-update-False-...]` — commit validator 物理/meta 不一致 → 证明 non-overwrite renamed update 未 reset
2. `test_execute_upload_update_failure_keeps_previous_document[False]` — 记录到 `update_failed` 而非 `create_failed` → 证明 non-overwrite update 仍走 update 而非 reset+create
3. `test_upload_filing_stream_renamed_update_without_overwrite_replaces_complete_set` — SEC `status=failed`
4. `test_upload_filing_stream_auto_resolves_create_update_skip` — CN `status=failed`

四个 RED 由同一 shared owner 根因（existing update 未 reset）产生。

修复后 GREEN: `74 passed, 3 warnings`（我独立验证通过）。

## 6. Coverage

S2 implementation artifact §6.4:
- `dayu/fins/pipelines/docling_upload_service.py`: **87%** (>=80%)
- `dayu/fins/ingestion_runtime.py`: **91%** (>=80%)

## 7. Pyright

S2 implementation artifact §6.5: `0 errors, 0 warnings, 0 informations`。

## 8. Findings summary

| # | Severity | Category | File:Line | Description |
|---|----------|----------|-----------|-------------|
| F-1 | INFO | dead code | `tests/fins/test_docling_upload_service.py:94-105` | `_FailingFinalUploadSourceRepository.update_source_document` 不可达（S2 生产代码不再调用 `update_source_document`）。不影响正确性。 |

## 9. Conclusion

**PASS。**

S2 diff 正确实现了 plan 中 complete-set replacement、logical deleted restore 和 cross-market propagation 的所有要求。核心生产文件 `docling_upload_service.py` 的修改集中在 `_store_upload_assets`（reset 条件扩展）、`_create_source_document`（create-only 收敛）和 `_resolve_upsert_mode`（完整删除）三处，语义清晰、边界完整。所有74项测试通过，frozen files 未被触及，README 三处已更新。

唯一 finding F-1 为测试 dead code，不阻塞。
