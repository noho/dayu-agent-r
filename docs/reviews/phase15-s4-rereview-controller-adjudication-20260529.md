# Phase 15 P15-S4 Re-Review Controller Adjudication

- **Gate**: Phase 15 S4 re-review adjudication
- **Date**: 2026-05-29
- **Fix artifact**: `docs/reviews/phase15-s4-fix-codex-20260529.md`
- **Re-review artifacts**:
  - `docs/reviews/phase15-s4-rereview-mimo-20260529.md`
  - `docs/reviews/phase15-s4-rereview-ds-20260529.md`

## Decision

Both re-reviews confirm accepted findings S4-ADJ-001, S4-ADJ-002 and S4-ADJ-003 are fixed, and no new blocker was introduced.

## Finding Closure

| ID | Closure | Evidence |
| --- | --- | --- |
| S4-ADJ-001 | Fixed | `host_purge_tombstones.audit_record_ref` and `audit_record_digest` are `TEXT NOT NULL`; `PurgeTombstoneRow` fields are `str`; row decode requires non-empty audit ref and sha256 digest. |
| S4-ADJ-002 | Fixed | `open_host.py` and `command.py` both use `dayu.host.audit.default_log_audit_sink_options`; duplicate audit path constants/helpers were removed from `open_host.py`. |
| S4-ADJ-003 | Fixed | `LogAuditSink._append_line` delegates directory creation to `_append_audit_json_line`. |
| S4-ADJ-005 | Deferred residual | Cross-medium orphan JSONL line after audit append success but SQLite commit failure remains a known residual for S6 / follow-up audit tooling. |

## Controller Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_purge_session.py tests/host/test_durable_schema.py tests/host/test_open_host_runtime.py -q
```

Result: `63 passed in 0.72s`.

Passed:

```bash
source .venv/bin/activate && python -m pyright dayu/host/audit.py dayu/host/durable/audit.py dayu/host/durable/purge.py dayu/host/durable/schema.py dayu/host/command.py dayu/host/open_host.py tests/host
```

Result: `0 errors, 0 warnings, 0 informations`.

Passed: `git diff --check`.

## Final Verdict

S4 is accepted. Proceed to accepted S4 slice commit, then continue to P15-S5.
