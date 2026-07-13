# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S1 Controller Validation

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S1 — Financial Result, XBRL Execution, And LLM Projection Contracts`
- Gate: `controller validation before code review`
- Timestamp: 2026-07-13 09:12:00 CST
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-implementation-codex.md`
- Accepted plan: `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`

## Scope Check

Controller confirmed the implementation diff is limited to accepted S1 production/test files plus S1 artifacts. No Host/Engine files, R3-E files, upload/download security schema, tool-security policy, 6-K dual-engine routing, or full `DocumentMeta` migration were introduced.

## Validation Commands

```text
source .venv/bin/activate
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q
72 passed, 3 warnings
```

```text
pytest tests/fins/test_fins_storage_provider.py -q -k "financial_statement or xbrl_query or financial_tool"
4 passed, 45 deselected, 3 warnings
```

```text
coverage run -m pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py -q
58 passed, 3 warnings

coverage report --include="dayu/fins/domain/financial_result_contract.py,dayu/fins/domain/xbrl_result_contract.py" --fail-under=80
financial_result_contract.py: 84%
xbrl_result_contract.py: 85%
TOTAL: 85%
```

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

```text
git diff --check
pass
```

## Propagation Scan Notes

- `_ProcessorFinancialStatementPayload|data_quality: NotRequired|reason: NotRequired`: zero matches.
- `query_obj.execute()` catch-and-continue empty-success shape: zero matches.
- `_DECIMALS_SCALE_MAP`: zero matches.
- `units.*millions|units.*thousands|units.*billions` with `tests/fins/fixtures/**` excluded: only domain enum, producer enum narrowing, negative tests, and LLM description/test text matched.
- `deduped_fact_count` in `dayu/fins/domain dayu/fins/processors`: only domain fail-closed guard matched; processors had zero matches.

## Controller Decision

S1 is ready for AgentMiMo and AgentDS code review.

## Blocking Questions

None.
