# UF-FIX02 S2 Code Re-Review — AgentMiMo

## 1. Review metadata

- Work unit: `UF-FIX02 action-and-update-identity`
- Gate: `code review → re-review`
- Slice: `S2 — Complete-set replacement, restore, and cross-market propagation`
- Reviewer: AgentMiMo
- Base: `08316516ca3da7f98299ee90d3fa753c32c59020`
- Branch: `codex/upload-filing-oracle`
- Fix artifact: `docs/gateflow/uf-fix02-action-and-update-identity-s2-code-review-fix-20260813.md`
- Controller adjudication: `docs/gateflow/uf-fix02-action-and-update-identity-s2-code-review-adjudication-20260813.md`
- Review date: 2026-08-13

## 2. Scope

独立核验 Controller adjudication 接受的两项 fix 是否正确实现，以及原 S2 主路径是否存在回归。

### 2.1 Accepted findings to verify

| Source | Finding | Required fix |
|--------|---------|-------------|
| DS F1 | reset→create 重置 `created_at` | `_build_upsert_meta` 从 reset 前 `previous_meta` 派生稳定 `created_at`；缺失时使用 `now` |
| MiMo F1 | `_FailingFinalUploadSourceRepository.update_source_document` dead override | 删除该方法；保留 create failure 注入与 `create_failed` 断言 |

### 2.2 Regression guard

- S2 原始 exact reset/create、rollback、fresh-state 路径无回归
- `_resolve_upsert_mode` 全仓零命中无回归
- focused / regression / coverage >= 80% / pyright / README / frozen no-touch

## 3. Independent verification

### 3.1 `_build_upsert_meta` — `created_at` 从 reset 前 `previous_meta` 派生

**PASS。** `dayu/fins/pipelines/docling_upload_service.py:772-787`:

```python
now = now_iso8601()
previous_first_ingested_at = (
    _text_meta(previous_meta, "first_ingested_at") if previous_meta is not None else None
)
previous_created_at = _text_meta(previous_meta, "created_at") if previous_meta is not None else None
merged = dict(base_meta)
merged["updated_at"] = now
merged["first_ingested_at"] = previous_first_ingested_at or now
merged["created_at"] = previous_created_at or now          # ← fix: 保持旧值
```

- Line 776：从 `previous_meta` 提取 `previous_created_at`（reset 前持有的值）。
- Line 780：`previous_created_at or now` — 旧值存在时复用，缺失时使用本次 `now`。
- 与 `first_ingested_at`（line 779）同形派生，同一 owner boundary。
- 无 storage downstream fallback、loose parsing 或二次重算。

### 3.2 `_FailingFinalUploadSourceRepository.update_source_document` — dead override 删除

**PASS。** `tests/fins/test_docling_upload_service.py:106-121`:

```python
class _FailingFinalUploadSourceRepository(_SpyUploadSourceRepository):
    """在 final create 阶段失败的 source 仓储 spy。"""

    def create_source_document(self, req, source_kind, *, batch) -> DocumentHandle:
        del req, source_kind, batch
        self._events.append("create_failed")
        raise RuntimeError("forced final upsert failure")
```

- 只保留 `create_source_document` override。
- `update_source_document` 已删除。
- `test_execute_upload_update_failure_keeps_previous_document` 断言 `events[-1] == "create_failed"`，确认走 create 路径。

### 3.3 Owner test `created_at` 断言

**PASS。** 两处关键断言：

- `test_execute_upload_deleted_input_republishes_complete_source` line 1440:
  `assert restored_meta["created_at"] == created_meta["created_at"]`
- `test_execute_upload_existing_full_input_replaces_exact_complete_set` line 1535:
  `assert final_meta["created_at"] == initial_meta["created_at"]`

覆盖 renamed update、deleted equal/changed restore、material shared-owner parity。

### 3.4 S2 原始路径无回归

**PASS。** 所有 S2 主路径测试通过（74 passed），包括：
- exact reset/create（`replace_existing` 条件 line 477-479）
- rollback（cancellation tests `cancel_at=2,4,5`）
- fresh-state（SEC `CREATE_TARGET_EXISTS`、CN `UPDATE_TARGET_MISSING`）
- `_resolve_upsert_mode` 全仓零命中

## 4. Validation suite (independent re-run)

| Check | Result | Evidence |
|-------|--------|----------|
| S2 focused (`test_docling_upload_service` + `test_sec_pipeline` + `test_cn_pipeline`) | **74 passed, 3 warnings** | 2.13s |
| Full owner/boundary focused (5 files) | **321 passed, 3 warnings** | 10.62s |
| UF-FIX01 / atomicity / cancellation regression (6 files) | **343 passed, 3 warnings** | 27.40s |
| `docling_upload_service.py` coverage | **87%** (391 stmts, 51 missed) | `--cov` with S2 focused set |
| pyright `dayu/ tests/ utils/` | **0 errors, 0 warnings, 0 informations** | independent run |
| `_resolve_upsert_mode` 全仓 Python 零命中 | **exit 1, 无输出** | `rg -n '_resolve_upsert_mode' --glob '*.py' .` |
| frozen registry / design no-touch | **PASS** | `git diff --exit-code` exit 0 |
| `git diff --check` | **PASS** | exit 0 |
| production diff 静态审计 | **PASS** | 无 `hasattr/getattr/Any/object/str(exc)/lazy/.stem` |
| `created_at` owner assertion exists | **PASS** | lines 1440, 1535 |
| dead `update_source_document` override removed | **PASS** | `grep` 无该方法定义 |

## 5. Findings

无新 finding。

## 6. Conclusion

**PASS。**

两项 accepted findings 的 fix 均已正确实现：

1. **DS F1（`created_at` 漂移）**：`_build_upsert_meta` 从 reset 前 `previous_meta` 派生稳定 `created_at`，与 `first_ingested_at` 同形；owner tests 断言 `created_at` 保持。独立验证通过。
2. **MiMo F1（dead override）**：`_FailingFinalUploadSourceRepository.update_source_document` 已删除，`create_failed` 断言保留。独立验证通过。

S2 原始路径（exact reset/create、rollback、fresh-state、`_resolve_upsert_mode` 零命中）无回归。focused/regression/coverage/pyright/frozen/static 全部通过。
