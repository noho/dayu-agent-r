# WU-CM-01 Slice A Re-review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice A re-review adjudication |
| slice | Slice A - Compact Contract Closure |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| fix artifact | `docs/reviews/wu-cm-01-slice-a-fix-codex.md` |
| re-review artifacts | `docs/reviews/wu-cm-01-slice-a-rereview-mimo.md`; `docs/reviews/wu-cm-01-slice-a-rereview-ds.md` |
| adjudicator | AgentController |
| adjudication date | 2026-06-04 |

## Verdict

Slice A fix re-review is **accepted**.

AgentMiMo verdict: `pass`.

AgentDS verdict: `fix-accepted`.

Both reviewers confirmed that accepted findings A1 / A2 / A3 are closed and no new blocking regression was introduced.

## Closure Decisions

### A1: `context_governance.__all__` export

- Decision: closed.
- Evidence: `check_conversation_compact_output_vnext` is included in `dayu/host/context_governance.py` `__all__`.

### A2: vNext label contract single source

- Decision: closed.
- Evidence: vNext label-section allowlists and stale-label helper now live in `dayu/host/compaction.py`; `llm_compaction.py` and `context_governance.py` import them directly from the contract owner module.
- Regression check: no compatibility wrapper, compatibility re-export, lazy import seam, or old/new bridge was introduced.

### A3: direct material mapping tests

- Decision: closed.
- Evidence: `tests/host/test_compact_material.py` now directly covers user-turn trace mapping, assistant-turn answer mapping, evidence material mapping, previous view fact-only mapping, and current input anchor non-citability.

## Validation

Controller reproduced the fix validation:

```bash
source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compact_material.py -q
```

Result: `105 passed in 0.32s`.

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

## Deferred Residual Risks

| 风险 | 状态 | Owner |
|---|---|---|
| `previous_compacted_view` only maps evidence-backed facts | deferred | Slice B/C |
| Production compact operation still uses old contract | intentional Slice A boundary | Slice B |
| Memory durable/projection still uses old shape | intentional later slice boundary | Slice C |
| RunInputBuilder prompt assembly still uses old stable blocks | intentional later slice boundary | Slice D |

## Next Gate

Slice A can be committed as an accepted implementation slice. After the accepted commit is recorded, WU-CM-01 may proceed to Slice B - Compact Operation And Event Closure.
