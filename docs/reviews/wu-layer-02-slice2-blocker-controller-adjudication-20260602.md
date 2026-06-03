# WU-LAYER-02 Slice 2 Blocker Controller Adjudication

## Scope

- Work unit: WU-LAYER-02 Shared Runtime Helper Consolidation.
- Slice: Slice 2 Engine Agent Exception Diagnostic Migration.
- Source report: `docs/reviews/wu-layer-02-slice2-implementation-report-20260602.md`.
- Design source: `docs/host/design.md`.
- Control source: `docs/host/host-core-followup-implementation-control.md`.

## Finding

AgentCodex stopped before implementation because direct migration from Engine private exception secret detection to `dayu.runtime.diagnostic_text.contains_sensitive_diagnostic_value` would change Engine user-visible `RunFailedData.message` behavior at punctuation-only and closing-punctuation boundaries.

Direct evidence:

- Old Engine regex treats `api_key=;` and `token=;` as sensitive because `;` is not excluded by `[^,\s}\]]+`.
- Current runtime regex treats `api_key=;` and `token=;` as non-sensitive because `;` is excluded by `[^\s,;]+`.
- Old Engine regex treats `api_key=}`, `api_key=]`, `token=}`, `token=]`, `Bearer }` and `Bearer ]` as non-sensitive because closing braces/brackets are excluded.
- Current runtime regex treats those closing-punctuation value starts as sensitive because `}` and `]` are not excluded.

## Adjudication

Accepted blocking finding.

基于 `docs/host/design.md` 的分层目标和第一性原理，WU-LAYER-02 的正确 owner 是层中立 runtime diagnostic text primitive；如果迁移需要 Engine 私有 guard 才能维持行为，就说明 runtime primitive 没有完成共享语义收敛。直接迁移会改变 Engine 外部可见诊断消息，违反 plan 的 non-goal；在 Engine 内绕开 runtime 会保留重复 helper，违反本 work unit 目标。

## Required Fix

Implementation agent must first refine `dayu.runtime.diagnostic_text` so value-bearing sensitive detection keeps Engine punctuation-boundary behavior for Engine migration while preserving Host value-redaction requirements:

- `api_key=;`, `token=;` and equivalent assigned-key semicolon value starts remain sensitive.
- `api_key=}`, `api_key=]`, `token=}`, `token=]`, `Bearer }` and `Bearer ]` do not become sensitive.
- Existing broad `api key <plain-word>` behavior remains accepted.
- Runtime redaction tests must cover the punctuation-boundary matrix and must not weaken false-positive guards such as `JWT token has expired` and `Content-Type header is invalid`.

After runtime refinement, implementation agent may rerun Slice 2 Engine migration:

- Delete Engine private secret regexes and `_contains_sensitive_exception_value`.
- Use `contains_sensitive_diagnostic_value` and `truncate_diagnostic_text` for Engine exception/log safe-message paths.
- Preserve Engine policy: sensitive messages become whole-message `_EXCEPTION_MESSAGE_REDACTED`; Engine must not use Host-style value redaction.
- Preserve Agent state machine, `RunnerEvent`, `RunFailedData` fields, metadata and public contract.

## Allowed Files For Fix

- `dayu/runtime/diagnostic_text.py`
- `tests/runtime/test_diagnostic_text.py`
- `dayu/engine/agent.py`
- `tests/engine/test_agent_phase2.py`
- README files only if the actual code/test change triggers a stable documentation update under `AGENTS.md`.
- `docs/reviews/wu-layer-02-slice2-implementation-report-20260602.md` may be replaced or appended with the final implementation report.

## Validation

Required commands:

```bash
source .venv/bin/activate && pytest -q tests/runtime/test_diagnostic_text.py tests/engine/test_agent_phase2.py
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

## Residual Risk

No deferred residual risk is accepted at this point. The blocker must be closed in the current Slice 2 fix before code review gate.
