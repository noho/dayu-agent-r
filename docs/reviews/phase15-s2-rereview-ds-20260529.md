# Phase 15 P15-S2 Re-Review — AgentDS

## Gate / Scope

- Gate: Phase 15 S2 re-review (follow-up).
- Original reviews: `docs/reviews/phase15-s2-code-review-ds-20260529.md`, `docs/reviews/phase15-s2-code-review-mimo-20260529.md`.
- Controller adjudication: `docs/reviews/phase15-s2-code-review-controller-adjudication-20260529.md`.
- Fix artifact: `docs/reviews/phase15-s2-fix-codex-20260529.md`.
- Scope: verify S2-ADJ-001 through S2-ADJ-005 only. Do not revisit rejected findings S2-REJ-001 / S2-REJ-002.

## Per-Finding Verification

### S2-ADJ-001 — Projection checkpoint reset lacks rebuildable consumer filter

**Controller requirement**: add explicit allowed consumer set, delete only when consumer is rebuildable AND referenced EventLog is in target session, raise `HostDurableError` for unsupported consumers before EventLog deletion, add focused tests.

**Evidence**:

- `_PURGE_REBUILDABLE_PROJECTION_CONSUMER_IDS` 已定义 (`purge.py:131-137`)，包含 5 个白名单 consumer: `host.minimal-read-model`, `host.memory.session.v1`, `host.audit-log-jsonl`, `host.tool-trace`, `host.outbox-terminal`。
- `_raise_for_unsupported_projection_reset_refs` (`purge.py:1744-1778`) 在删除前检测 `consumer_id NOT IN (...)` 且 `event_id IN target_event_ids` 的行，命中则 raise `HostDurableError`。
- `_delete_allowed_projection_reset_refs` (`purge.py:1781-1807`) 仅删除 `consumer_id IN (...)` 且 `event_id IN target_event_ids` 的行。
- `_delete_session_matrix` (`purge.py:1395-1418`) 先调 `_raise_for_unsupported_*` 再调 `_delete_allowed_*`，确保非白名单 consumer 检测在 allowed reset 删除之前发生。
- 新增测试 `test_purge_session_durable_rejects_unsupported_projection_checkpoint_and_rolls_back` (`test_purge_session.py:2409-2444`): 验证 HostDurableError 抛出 / 无 tombstone / EventLog 未删除 (12 rows) / 非白名单 checkpoint 保留 (1 row)。
- 新增测试 `test_purge_session_durable_rejects_unsupported_projection_failure_and_rolls_back` (`test_purge_session.py:2447-2482`): 同上模式验证 failure 路径。
- 主 matrix 测试 (`test_purge_session.py:2330-2335`) 验证 purge 后 projection checkpoints/failures 全部清零（白名单 consumer 已被正确删除）。

**Status**: 已修复。

---

### S2-ADJ-002 — Redundant target run id reads

**Controller requirement**: cache `_read_target_run_ids(...)` result in `_build_purge_precondition_digest(...)`.

**Evidence**:

- `_build_purge_precondition_digest` (`purge.py:1145`): `run_ids = _read_target_run_ids(transaction, session_id)` — 一次读取并局部缓存。
- 后续 Attempt precondition rows (`purge.py:1258`): `WHERE {_in_clause("run_id", run_ids)}` 使用缓存值。
- 条件守卫 (`purge.py:1263`): `if run_ids` 使用缓存值。
- 原实现在 `_build_purge_precondition_digest` 内调用了 3 次 `_read_target_run_ids`（一次用于 `in_clause` 参数, 一次用于 `in_clause` 占位符, 一次用于三元判空），现减少到 1 次。

**Status**: 已修复。

---

### S2-ADJ-003 — Missing blank lines between top-level definitions

**Controller requirement**: add missing top-level blank lines.

**Evidence**:

- `purge.py` 中 `_PRECONDITION_COUNTS` 后面有空白行，`_PURGE_REBUILDABLE_PROJECTION_CONSUMER_IDS` 与 `_SESSION_FACT_SCOPE_KINDS` 之间也有空行。
- `test_purge_session.py` 中新增常量 `_OUT_OF_SCOPE_IDEMPOTENCY_SCOPE_KIND`、`_OUT_OF_SCOPE_IDEMPOTENCY_KEY`、`_UNSUPPORTED_PROJECTION_CONSUMER_ID` 之间均有空行分隔。
- pyright 0 errors 通过。

**Status**: 已修复。

---

### S2-ADJ-004 — Non-terminal rejection should assert tombstone absence

**Controller requirement**: add tombstone absence assertion for non-terminal Run rejection tests.

**Evidence**:

- `test_purge_session_durable_rejects_non_terminal_runs` (`test_purge_session.py:2389-2406`):
  ```python
  tombstone: PurgeTombstoneRow | None = None
  with open_host_durable_store(_options(tmp_path)) as store:
      store.transaction_runner.run_write(...)
      with pytest.raises(PurgeSessionInvalidStateError):
          store.transaction_runner.run_write(_PurgeMatrixOperation())
      tombstone = store.transaction_runner.run_read(
          _ReadTombstoneBySessionOperation()
      )
  assert tombstone is None
  ```
- 6 种非终态 Run status 的参数化测试 (`@pytest.mark.parametrize("run_status", _NON_TERMINAL_RUN_STATUSES)`) 全部覆盖此断言。
- 与 `test_purge_session_durable_rejects_open_session` 中的 tombstone 断言模式一致。

**Status**: 已修复。

---

### S2-ADJ-005 — Idempotency records outside purge session-fact scope should be preserved

**Controller requirement**: seed an out-of-scope idempotency record and assert purge preserves it.

**Evidence**:

- `_insert_old_idempotency_rows` (`test_purge_session.py:2169-2183`) 新增第三条幂等记录: `scope_kind="external_projection_ack"`, `scope_id=_SESSION_ID`, `idempotency_key="external-ack-key"`。`"external_projection_ack"` 不在 `_SESSION_FACT_SCOPE_KINDS` 中。
- `_ReadOutOfScopeIdempotencyOperation` (`test_purge_session.py:594-616`) 精确读取该记录，返回 bool。
- 主 matrix 测试 (`test_purge_session.py:2279,2287-2289,2340`):
  ```python
  out_of_scope_idempotency_exists = store.transaction_runner.run_read(
      _ReadOutOfScopeIdempotencyOperation()
  )
  assert out_of_scope_idempotency_exists is True
  ```
- 同时确认 `result.deleted_counts.idempotency_records == 2` (`test_purge_session.py:2362`) — 仅 2 条 in-scope 旧记录被删除，第 3 条 out-of-scope 记录保留。

**Status**: 已修复。

## Validation

| Item | Result |
|---|---|
| `pytest ... -q` (S2 suite) | 112 passed in 0.71s |
| `pyright dayu/host/durable/purge.py ... tests/host` | 0 errors, 0 warnings, 0 informations |
| New tests added | 2 (unsupported checkpoint + unsupported failure) |
| New helper functions | `_raise_for_unsupported_projection_reset_refs`, `_delete_allowed_projection_reset_refs`, `_placeholders`, `_event_sequence_for_id` |
| New test operations | `_ReadOutOfScopeIdempotencyOperation`, `_InsertUnsupportedProjectionCheckpointOperation`, `_InsertUnsupportedProjectionFailureOperation` |

## No New Blockers

- No regression detected in existing tests or behavior.
- All 5 accepted findings verified as fixed with direct code/test evidence.
- No new findings introduced by the fix.
- Pyright clean.

## Status Summary

| Finding | Status |
|---|---|
| S2-ADJ-001 (projection consumer filter) | 已修复 |
| S2-ADJ-002 (cached run id reads) | 已修复 |
| S2-ADJ-003 (missing blank lines) | 已修复 |
| S2-ADJ-004 (tombstone absence assertion) | 已修复 |
| S2-ADJ-005 (out-of-scope idempotency preservation) | 已修复 |

**PASS** — 5/5 已修复，0 new blockers.
