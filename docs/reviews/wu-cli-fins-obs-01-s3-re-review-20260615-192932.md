# WU-CLI-FINS-OBS-01 Slice S3 Re-Review

## Scope

- Mode: scoped re-review
- Branch: `phaseflow/host-issues-implementation`
- Base: `main`
- Output file: `docs/reviews/wu-cli-fins-obs-01-s3-re-review-20260615-192932.md`
- Included scope:
  - `dayu/service/fins_direct.py` — S3-FIX-01/02/03 新增或调整的内容
  - `tests/service/test_fins_direct.py` — S3-FIX-01/02/03 新增测试
  - `docs/reviews/wu-cli-fins-obs-01-s3-fix-codex.md` — fix artifact
- Excluded scope: deferred / non-actions（terminal fallback 不写回 sidecar、wait_for_terminal 与 stream 不加互斥、CLI/Host/Engine/Fins runtime 不修改）

## Findings

未发现实质性问题。

## Fix Verification

### S3-FIX-01: terminal event / job record inconsistency — 3/3 ✓

- **新增异常类**: `FinsDirectRuntimeStateError(RuntimeError)` (fins_direct.py:49-50)，docstring "Fins direct runtime 持久化状态不一致。"，继承 `RuntimeError` 而非 `ValueError`，语义明确区分于 `FinsDirectUsageError`。
- **逻辑变更**: `_terminal_result_for_event` (fins_direct.py:583-604) 在 terminal event 到达后读取 job record，若 record 非终态，raise `FinsDirectRuntimeStateError`，消息包含 job_id、sequence、event_type、record_status，不再抛 `FinsDirectUsageError`。
- **正常 terminal mapping 不变**: record 为终态时正常走 `_terminal_result(record)` 返回 (fins_direct.py:604)。
- **测试覆盖**: `test_stream_job_events_reports_terminal_record_inconsistency` (test_fins_direct.py:488-510) 构造 terminal event + RUNNING record，断言 `FinsDirectRuntimeStateError` 且 match "terminal job event observed before terminal job record"。
- **`__all__` 导出**: `FinsDirectRuntimeStateError` 已加入 `__all__` (fins_direct.py:781)。

### S3-FIX-02: negative after_sequence validation coverage — ✓

- **测试覆盖**: `test_stream_job_events_rejects_negative_after_sequence` (test_fins_direct.py:471-484) 传入 `after_sequence=-1`，断言 `FinsDirectUsageError` match "after_sequence"，且 `runtime.event_read_calls == []` 确认不读取 runtime。

### S3-FIX-03: terminal event read_job failure propagation coverage — ✓

- **测试覆盖**: `test_stream_job_events_propagates_read_job_failure_after_terminal_event` (test_fins_direct.py:514-533) 构造 terminal event batch + `read_job_error=LookupError("unknown job")`，断言 `LookupError` match "unknown job" 向调用方透传。

### Code Quality (AGENTS.md compliance)

- 新异常类 `FinsDirectRuntimeStateError` 提供中文 docstring ✓
- 新测试均提供中文 docstring ✓
- 无 `Any`、`object`、裸容器或无类型签名 ✓

### Validation

- `pytest tests/service/test_fins_direct.py -q`: 17 passed ✓
- `pyright dayu/service/fins_direct.py tests/service/test_fins_direct.py`: 0 errors ✓
- `git diff --check`: clean ✓

## Open Questions

无。

## Residual Risk

无。三个 accepted fixes 全部关闭，未引入新问题。

## Conclusion

**PASS** — 3/3 fixed。
