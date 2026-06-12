# WU-RET-00 PR 139 Fix Re-review — DS

## Scope

- Gate: PR re-review
- Input review artifacts:
  - `docs/reviews/wu-ret-00-pr139-review-mimo.md`
  - `docs/reviews/wu-ret-00-pr139-review-ds.md`
  - `docs/reviews/wu-ret-00-pr139-fix-codex.md`
- Review target: AgentCodex fixes for MiMo accepted findings 1/2/3/4/8
- Workspace diff scope: `tests/host/test_storage_maintenance.py`, `tests/host/test_storage_orphan_proof.py`, `docs/host/issues-implementation-control.md`
- Excluded: production behavior, schema, public API, README changes — none present in diff
- Review date: 2026-06-12

## Verification

```bash
source .venv/bin/activate && pytest tests/host/test_storage_maintenance.py tests/host/test_storage_orphan_proof.py -q
```

Result: **18 passed in 0.38s**

```bash
source .venv/bin/activate && pyright tests/host/test_storage_maintenance.py tests/host/test_storage_orphan_proof.py
```

Result: **0 errors, 0 warnings, 0 informations**

## Findings

### Finding 1 (MiMo #1) — 测试绕过公共 API 路径验证 recheck 行为

**状态: FIXED** ✅

`test_storage_maintenance_reclaim_recheck_hit_skips_delete` 已从直接调用 `storage_lifecycle_module.reclaim_orphan_artifact_files` 改为通过 `run_storage_maintenance()` 公共 facade 入口。monkeypatch 策略正确：在 `scan_orphan_artifact_files` 返回 candidates 后、per-file recheck 前写入新 descriptor，模拟 scan/recheck 之间的新引用。断言验证 candidate 仍被报告、文件未删除、无 file error、descriptor 可见。

### Finding 2 (MiMo #2) — recheck callable 非文件级异常传播行为未测试

**状态: FIXED** ✅

新增 `test_storage_maintenance_recheck_durable_error_fails_safe`。monkeypatch `artifact_relative_path_is_referenced` 抛出 `HostDurableError`，验证 `run_storage_maintenance` 抛出 `HostApiError(code=INTERNAL_ERROR)`、message 包含 "durable operation failed"、`__cause__` 为 `HostDurableError`、candidate 文件未被删除。覆盖了 fail-safe 传播路径。

### Finding 3 (MiMo #3) — scan_orphan_artifact_files 边界校验未测试

**状态: FIXED** ✅

新增两个测试：
- `test_scan_orphan_artifact_files_rejects_negative_grace_seconds` — `pytest.raises(ValueError, match="grace_seconds must be non-negative")`
- `test_scan_orphan_artifact_files_rejects_naive_datetime` — `pytest.raises(ValueError, match="now must be timezone-aware")`

### Finding 4 (MiMo #4) — issues-implementation-control.md WU-RET-00 状态行未同步

**状态: FIXED** ✅

Work Units 表第 215 行 `WU-RET-00` 状态已从 `planning` 更新为 `ready-to-open-draft-PR`，与同文件 current-state 表一致。

### Finding 8 (MiMo #8) — HostStorageMaintenanceResult.json_value() 未测试

**状态: FIXED** ✅

新增 `test_storage_maintenance_result_json_value_is_stable_self_explaining_and_non_negative`。验证 top-level keys 集合 (`usage`, `physical_artifact_bytes`, `orphan_artifact_candidates`, `reclaimed_artifact_paths`, `file_errors`, `wal_checkpoint`)、`usage` 为 Mapping、`physical_artifact_bytes` 非负、candidates/reclaimed/errors/checkpoint 字段形状。

### Scope creep 检查

**无范围外改动。** 工作区 diff 仅包含 3 个文件：
- `tests/host/test_storage_maintenance.py` — 仅新增/修改测试函数和测试辅助函数
- `tests/host/test_storage_orphan_proof.py` — 仅新增 2 个边界拒绝测试
- `docs/host/issues-implementation-control.md` — 仅修改 1 行状态字段

无 `dayu/` 生产代码、schema、public API、README 或 `pyproject.toml` 变更。

### tests/README 不更新理由

Codex 报告声明 `tests/README.md` 已被读取，其 Host testing 节（第 162 行）已描述 `test_storage_maintenance.py` 覆盖"删除前 recheck 跳过"、"单文件错误诊断"以及 `test_storage_usage_report.py` 的 `json_value()` 覆盖。本次 fix 在既有测试文件和既有类别内扩展测试，未新增测试层级、命令或维护规则。理由成立。

### 验证命令足够性

Codex 报告的验证命令 `pytest tests/host/test_storage_maintenance.py tests/host/test_storage_orphan_proof.py -q` 覆盖了本次修改的全部测试文件，`pyright` 覆盖了类型检查。当前环境重新执行均已通过。命令足够。

## Open Questions

- 无。

## Residual Risk

- **R1**: DS Finding 001（async event loop 同步阻塞 I/O）和 DS Finding 002（`DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS` 包根导出）由当前 WU 指令明确延后，不在本次 fix scope。——风险已记录，非 blocking。
- **R2**: 原始 MiMo review 的 residual risks（TOCTOU 窗口、并发 maintenance、CI checks 缺失）未被本次 fix 变更。——无新增或放大的 residual risk。

## 结论

**PASS**

blocking finding 数量: **0**

AgentCodex 对 MiMo accepted findings 1/2/3/4/8 的修复全部完整且正确。18 个测试通过，pyright 0 errors。无生产代码、schema、public API、README 的范围外改动。tests/README 不更新理由成立。验证命令充分。
