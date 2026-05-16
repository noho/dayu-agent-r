# Code Re-Review

## Scope

- Mode: current changes (re-review of fix pass)
- Branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base: main
- Output file: docs/reviews/host-phase7-code-re-review-s1-mimo-20260516.md
- Included scope: dayu/host/durable/schema.py fix diff, tests/host/test_wait_record_state.py new test, fix artifact, controller adjudication
- Excluded scope: all other P7-S1 files (unchanged in fix pass)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Verification Summary

### S1-F1 accepted - 长度常量重复定义 ✅ 已关闭

`dayu/host/durable/schema.py` 现在从 `dayu.host.api` 导入全部 8 个 `HOST_WAIT_*_MAX_LENGTH` 常量（第 13-20 行），本地无重复定义。DDL f-string 引用导入的常量（第 462-501 行）。无遗留本地副本。

### S1-F2 accepted - orphan snapshot_digest DDL gap ✅ 已关闭

`host_wait_records` DDL CHECK 约束已改为：

```sql
CHECK (
    (snapshot_ref IS NULL
      AND snapshot_captured_at IS NULL
      AND snapshot_digest IS NULL)
    OR
    (snapshot_ref IS NOT NULL AND snapshot_captured_at IS NOT NULL)
  ),
```

- 无 snapshot 时三列必须全为 NULL。
- 有 snapshot 时 `snapshot_ref` 与 `snapshot_captured_at` 必须非 NULL，`snapshot_digest` 可为 NULL。
- orphan `snapshot_digest`（`snapshot_ref IS NULL AND snapshot_captured_at IS NULL AND snapshot_digest IS NOT NULL`）被拒绝。

`tests/host/test_wait_record_state.py:486-571` 新增 `test_wait_record_ddl_rejects_orphan_snapshot_digest`，通过直接 SQL INSERT 写入 `snapshot_ref=NULL, snapshot_captured_at=NULL, snapshot_digest=<valid>` 行，断言 `HostDurableError("CHECK constraint")`。测试覆盖了 adjudication 要求的 orphan 场景。

### S1-F3 rejected - adapter_key regex DDL ✅ 未实施

`schema.py` DDL 中 `adapter_key` 只有长度 CHECK，无字符模式 CHECK。符合 adjudication 裁决。

### S1-F4 deferred - CAS_LOST race test ✅ 未实施

`test_wait_record_state.py` 未新增 CAS_LOST 并发测试。现有测试覆盖 UPDATED / NOT_FOUND / INVALID_STATE。符合 adjudication 裁决，deferred to P7-S4。

## Validation

- `pytest tests/host/test_durable_schema.py tests/host/test_wait_record_state.py -q` → 15 passed in 0.20s
- `python -m pyright dayu/host/durable/schema.py tests/host/test_wait_record_state.py` → 0 errors, 0 warnings, 0 informations

## Open Questions

无

## Residual Risk

无新增。P7-S4 将覆盖 CAS_LOST 并发竞态分支。
