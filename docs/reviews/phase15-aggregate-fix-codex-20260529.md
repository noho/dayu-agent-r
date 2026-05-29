# Phase 15 Aggregate Fix Artifact

- Gate: Phase 15 aggregate fix pass
- Source adjudication: `docs/reviews/phase15-aggregate-deepreview-controller-adjudication-20260529.md`
- Accepted finding: AGG-ADJ-001
- Role: AgentCodex fix specialist
- Scope: dead-code cleanup only
- Stop status: complete

## Changed Files

- `dayu/host/durable/purge.py`
- `tests/host/test_package_exports.py`
- `docs/reviews/phase15-aggregate-fix-codex-20260529.md`

## Deleted Items

- Removed unused private helper `dayu.host.durable.purge._placeholders`.
- Confirmed `PurgePreconditionSnapshot` had no direct use in `dayu/` or `tests/`; only historical docs / review artifacts and the S6 package export guard referenced it.
- Removed unused `PurgePreconditionSnapshot` dataclass from `dayu/host/durable/purge.py`.
- Removed `PurgePreconditionSnapshot` from `dayu.host.durable.purge.__all__`.
- Removed `PurgePreconditionSnapshot` from the internal purge durable export guard list in `tests/host/test_package_exports.py`.

## Behavior / Contract Decision

- No purge behavior changed.
- No schema changed.
- No public API shape changed.
- No public error codes changed.
- No test semantics changed beyond removing the guard entry for a deleted internal dead-code symbol.

## README Decision

- Did not update `dayu/host/README.md`: the cleanup removed unused internal dead code only and did not change Host interface, purge semantics, audit retention, read-after-purge behavior, or architecture boundaries.
- Did not update `tests/README.md`: the testing facts and commands did not change.
- Did not update root `README.md` or `dayu/README.md`: no user workflow, CLI, config, trace/render entry, layering, or composition boundary changed.

## Validation

Direct-use check:

```text
rg -n "\bPurgePreconditionSnapshot\b|\b_placeholders\b" dayu tests
dayu/host/durable/projection.py:510:          AND consumer_id NOT IN ({_placeholders(rebuildable_consumer_ids)})
dayu/host/durable/projection.py:544:          AND consumer_id IN ({_placeholders(rebuildable_consumer_ids)})
dayu/host/durable/projection.py:558:    return f"{column_name} IN ({_placeholders(values)})"
dayu/host/durable/projection.py:561:def _placeholders(values: tuple[str, ...]) -> str:
```

The remaining `_placeholders` references are in `dayu.host.durable.projection`, not in the targeted purge module.

Required pytest:

```text
source .venv/bin/activate && pytest tests/host/test_purge_session.py tests/host/test_package_exports.py tests/host/test_weak_typing_guard.py -q
......................................                                   [100%]
38 passed in 1.39s
```

Required pyright:

```text
source .venv/bin/activate && python -m pyright dayu/host/durable/purge.py tests/host/test_purge_session.py tests/host/test_package_exports.py tests/host/test_weak_typing_guard.py
0 errors, 0 warnings, 0 informations
```

## Residual Risks

- Fixed in current pass: AGG-ADJ-001 dead-code cleanup.
- Covered by validation: targeted purge behavior tests, package export guard, weak typing guard, and pyright for touched modules/tests.
- Deferred / out of scope: AGG-ADJ-002 through AGG-ADJ-005 per controller adjudication; no action in this fix pass.
- Requiring controller decision: none.
