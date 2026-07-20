# WU-SEMANTIC-OWNERSHIP-01 P3-A S1 fix controller validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-A`
- Slice: S1 fix
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-a-s1-fix-codex.md`

## Controller Validation

Commands:

```bash
source .venv/bin/activate && pytest tests/host/test_lifecycle_events.py tests/host/test_state_schema.py -q
source .venv/bin/activate && python -c "from dayu.host.lifecycle_events import HostRunEventType, HostAttemptEventType, run_terminal_event_type_for_status, attempt_terminal_event_type_for_status; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"
source .venv/bin/activate && pyright
git diff --check
```

Results:

- Focused tests: `59 passed`
- Import-cycle validation: `import-ok`
- Pyright: `0 errors, 0 warnings, 0 informations`
- Diff check: passed

## Controller Notes

- The accepted S1 review findings are addressed in the diff: closeout-supported Attempt terminal subset is explicit, `SUSPENDED` / `STEERED` remain durable terminal but not closeout-supported, predicate tests are explicit, unordered frozenset serialization is covered, and lifecycle docstrings describe Attempt ownership.
- S2 must consume the closeout-supported Attempt helper for joint terminal closeout paths.

## Next Gate

Proceed to S1 re-review by AgentMiMo and AgentDS.
