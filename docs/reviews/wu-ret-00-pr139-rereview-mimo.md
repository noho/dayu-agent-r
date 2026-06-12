# WU-RET-00 PR 139 Fix Re-Review — MiMo

## Scope

- Gate: PR re-review（Codex fix → MiMo 复审）
- Input review artifacts:
  - `docs/reviews/wu-ret-00-pr139-review-mimo.md`
  - `docs/reviews/wu-ret-00-pr139-review-ds.md`
  - `docs/reviews/wu-ret-00-pr139-fix-codex.md`
- Review scope: 仅复审 Codex 对 PR review accepted findings 的修复，不审查原始 PR 实现
- Changed files under review:
  - `tests/host/test_storage_maintenance.py`（+163 / -50）
  - `tests/host/test_storage_orphan_proof.py`（+30）
  - `docs/host/issues-implementation-control.md`（+1 / -1）
  - `docs/reviews/wu-ret-00-pr139-fix-codex.md`（新增）

## Findings

### MiMo Finding 1 — 测试绕过公共 API 路径验证 recheck 行为

**修复状态：✅ 完整修复**

Codex 将 `test_storage_maintenance_reclaim_recheck_hit_skips_delete` 从直接调用 `storage_lifecycle_module.reclaim_orphan_artifact_files` 改为通过 `run_storage_maintenance()` 公共入口。修复手法：

1. monkeypatch `storage_maintenance_module.scan_orphan_artifact_files` 为 `scan_then_write_descriptor`，在原始 scan 完成后、返回候选前写入新 descriptor，精确模拟 scan/recheck 之间的 TOCTOU 窗口。
2. 断言通过公共 API 返回值验证：`orphan_artifact_candidates` 包含候选、`reclaimed_artifact_paths` 为空（recheck 跳过删除）、`file_errors` 为空。
3. 补充断言：文件仍存在于磁盘、descriptor 行数不变（`after_usage.payload_descriptor_rows == 1`）。
4. 移除了不再需要的 `_artifact_path_is_referenced` 私有辅助函数。

**评估**：修复直接命中 finding 根因——绕过公共 API。monkeypatch 位置精确（scan 之后、recheck 之前），不引入对 durable 层内部实现的耦合。测试现在完整验证了 `_ArtifactPathReferenceChecker` 在公共 facade 中的集成行为。

### MiMo Finding 2 — recheck callable 非文件级异常传播行为未测试

**修复状态：✅ 完整修复**

新增 `test_storage_maintenance_recheck_durable_error_fails_safe` 测试：

1. monkeypatch `storage_maintenance_module.artifact_relative_path_is_referenced` 为 `fail_recheck`，抛出 `HostDurableError`。
2. 通过 `run_storage_maintenance()` 公共入口触发。
3. 断言：`HostApiError` 被抛出，`code == HostApiErrorCode.INTERNAL_ERROR`，message 包含 `"durable operation failed"`，`__cause__` 是 `HostDurableError` 实例。
4. 断言：候选文件仍在磁盘（验证 fail-safe 不会误删）。

**评估**：测试覆盖了 `HostDurableError` 从 durable 层到公共 facade 的完整传播链路。断言同时验证了错误码、错误消息和 cause chain，以及文件安全性。与 Finding 1 中 recheck 跳过路径形成互补覆盖。

### MiMo Finding 3 — scan_orphan_artifact_files 边界校验未测试

**修复状态：✅ 完整修复**

在 `tests/host/test_storage_orphan_proof.py` 新增两个测试：

1. `test_scan_orphan_artifact_files_rejects_negative_grace_seconds`：传入 `grace_seconds=-1.0`，断言 `pytest.raises(ValueError, match="grace_seconds must be non-negative")`。
2. `test_scan_orphan_artifact_files_rejects_naive_datetime`：传入 `datetime(2026, 6, 12, 12, 0, 0)`（无 tzinfo），断言 `pytest.raises(ValueError, match="now must be timezone-aware")`。

**评估**：两个测试精确覆盖 `storage_lifecycle.py:423-424` 的两个 `ValueError` 守卫。`match` 参数与实现中的错误消息一致，确保校验逻辑不被意外移除或修改。

### MiMo Finding 4 — issues-implementation-control.md WU-RET-00 状态行未同步

**修复状态：✅ 完整修复**

第 215 行 Work Units 表 `WU-RET-00` 状态从 `planning` 改为 `ready-to-open-draft-PR`，与同文件第 146/149/536 行的当前状态一致。

**评估**：单行修改，精确修复文档不一致。

### MiMo Finding 8 — HostStorageMaintenanceResult.json_value() 未测试

**修复状态：✅ 完整修复**

新增 `test_storage_maintenance_result_json_value_is_stable_self_explaining_and_non_negative` 测试：

1. 通过 `run_storage_maintenance()` 公共入口获取 result，调用 `json_value()`。
2. 断言返回值是 `Mapping`。
3. 锁定顶层 key 顺序：`("usage", "physical_artifact_bytes", "orphan_artifact_candidates", "reclaimed_artifact_paths", "file_errors", "wal_checkpoint")`。
4. 断言 `usage` 是 `Mapping`、`physical_artifact_bytes >= 0`、`orphan_artifact_candidates` 包含预期路径、`reclaimed_artifact_paths` / `file_errors` 为空 list、`wal_checkpoint` 为 `None`。
5. 新增 `_json_int` 辅助函数用于类型安全的 JSON 整数读取。

**评估**：测试覆盖了 `json_value()` 的 key 名稳定性、类型正确性和非负约束，与 `test_storage_usage_report.py` 中的 `json_value()` 测试模式一致。`_json_int` 辅助函数 docstring 完整，类型签名正确。

## 范围外改动确认

| 检查项 | 结果 |
|--------|------|
| 生产行为改动 | ❌ 无。所有修改均在 `tests/` 和 `docs/` |
| schema 改动 | ❌ 无 |
| public API 改动 | ❌ 无 |
| README 改动 | ❌ 无 |
| 新增/修改的私有辅助函数 | `_json_int`（新增，测试文件内私有）、`_artifact_path_is_referenced`（移除）——均在测试文件内，不影响生产代码 |

## tests/README 不更新理由确认

Codex 声明："tests/README.md 已读取，其 Host testing section 已描述 storage usage、orphan proof、storage maintenance、recheck、file error、async handle、closed handle、json coverage responsibilities；本 fix 仅扩展现有 Host storage 测试，不新增测试层、命令或维护规则，因此无需 README 变更。"

**评估：理由成立。** 本次修复新增的 4 个测试均属于已有测试文件的扩展（`test_storage_maintenance.py` 新增 3 个、`test_storage_orphan_proof.py` 新增 1 个），覆盖的能力（recheck、durable error、boundary validation、json_value）均已在 README 的 Host testing section 中有对应描述。不触发 README 更新条件。

## 验证命令确认

```bash
source .venv/bin/activate && pytest tests/host/test_storage_maintenance.py tests/host/test_storage_orphan_proof.py -q
```

**结果**：`18 passed in 0.38s` ✅

```bash
source .venv/bin/activate && pyright tests/host/test_storage_maintenance.py tests/host/test_storage_orphan_proof.py
```

**结果**（Codex 报告）：`0 errors, 0 warnings, 0 informations` ✅

**评估**：验证命令覆盖了修改的两个测试文件的 pytest 和 pyright 检查，足够充分。

## Open Questions

无。

## Residual Risk

1. **DS Finding 001（async event loop 同步阻塞）未修复**：按当前 WU instruction 指示 defer，不在本次 fix 范围。已记录。
2. **DS Finding 002（DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS 包根导出）未修复**：按当前 WU instruction 指示 defer，不在本次 fix 范围。已记录。
3. **MiMo Finding 5/6/7（plan 命名偏离、facade 重导出、私有辅助函数重复）未修复**：按当前 WU instruction 指示不修改，属于低 severity 设计收敛问题。已记录。

## 结论

**PASS**

blocking finding 数量：**0**

MiMo Finding 1/2/3/4/8 均已完整修复。修复手法精确、测试断言充分、不引入范围外改动。tests/README 不更新理由成立。验证命令足够。Codex 对未修复 findings 的 defer 理由（WU instruction 边界）一致且合理。
