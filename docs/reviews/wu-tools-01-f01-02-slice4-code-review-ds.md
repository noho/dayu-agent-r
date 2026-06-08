# WU-TOOLS-01-F01-02 Slice 4 Code Review - AgentDS

## Metadata

- **Review target**: Slice 4 - Fins Read Tools Context Injection And Checkpoints
- **Reviewer**: AgentDS
- **Date**: 2026-06-08
- **Plan source**: `docs/host/wu-tools-01-f01-02-cancellation-plan.md` Slice 4
- **Implementation artifact**: `docs/reviews/wu-tools-01-f01-02-slice4-implementation-codex.md`
- **Reviewed files**: `dayu/fins/tools/fins_tools.py`, `dayu/fins/tools/read_runtime.py`, `dayu/fins/tools/search_engine.py`, `tests/fins/test_fins_storage_provider.py`, `tests/tools/test_combined_tools_acceptance.py`
- **Conclusion**: PASS (1 Medium-High finding requiring fix, otherwise clean)

## Reviewed Scope

- 369 lines added/changed across 5 files (3 production + 2 test)
- Nine Fins read tools context injection
- `FinsReadRuntime` 9 method signatures extended with `cancellation_token`
- `search_engine.py` `_execute_query_search` extended with `cancellation_token`
- 3 new module-level helpers: `_resolve_fins_cancellation_token` (fins_tools.py), `_raise_if_fins_cancelled` / `_raise_fins_cancelled` (read_runtime.py), `_raise_if_search_cancelled` (search_engine.py)
- `read_section` `**_kwargs` removed
- 6 new test functions (4 in test_fins_storage_provider.py, 1 in test_combined_tools_acceptance.py extended)

## Validation

| Command | Result |
|---|---|
| `pytest tests/fins/test_fins_storage_provider.py tests/tools/test_combined_tools_acceptance.py -q` | 25 passed, 3 warnings (edgar deprecation) |
| `pyright` | 0 errors, 0 warnings, 0 informations |

## Findings

### Finding 1 (Medium-High): `read_section` `except Exception` at `read_runtime.py:470` swallows `ToolBusinessError` from cancellation checkpoint

**File**: `dayu/fins/tools/read_runtime.py`, lines 466-471

```python
            try:
                _raise_if_fins_cancelled(cancellation_token)  # line 467
                parent_title = processor.get_section_title(str(parent_ref))
                _raise_if_fins_cancelled(cancellation_token)  # line 469
            except Exception:  # line 470
                parent_title = None
```

**Evidence**: `ToolBusinessError` inherits from `Exception` (`dayu/tools/_legacy_adapter/tool_errors.py:10`). The `except Exception:` at line 470 catches `ToolBusinessError` raised by `_raise_if_fins_cancelled` at lines 467 or 469. After the except block, the function continues through lines 473-521 with **no further cancellation checkpoints** until the return statement. If cancellation is signaled during this window, the tool returns a successful `SectionContentResult` instead of propagating `tool_cancelled`. The `ToolBusinessError` exception is converted to `parent_title = None`, and cancellation is silently dropped.

**Severity rationale**: The window between line 471 and the return at line 521 contains no other `_raise_if_fins_cancelled` calls, so once the exception is swallowed, the entire remaining execution (lines 473-521, including `resolve_section_semantic`, `build_section_path`, `_build_citation`) proceeds without cancellation awareness. This violates the plan's invariant: "Directory/file traversal stops promptly after checkpoint sees cancel."

**Pre-existing?** No. The `_raise_if_fins_cancelled` calls at lines 467 and 469 were added in this slice, which introduced the possibility of `ToolBusinessError` being raised inside a pre-existing broad `except Exception:` block.

**Recommended fix**:

Option A (narrower catch - preferred):
```python
            try:
                _raise_if_fins_cancelled(cancellation_token)
                parent_title = processor.get_section_title(str(parent_ref))
                _raise_if_fins_cancelled(cancellation_token)
            except (RuntimeError, TypeError, AttributeError, ValueError):
                parent_title = None
```

Option B (re-raise cancellation):
```python
            try:
                _raise_if_fins_cancelled(cancellation_token)
                parent_title = processor.get_section_title(str(parent_ref))
                _raise_if_fins_cancelled(cancellation_token)
            except ToolBusinessError:
                raise
            except Exception:
                parent_title = None
```

Option A is preferred per AGENTS.md "优先选择最小、类型清晰、测试可验证的方案" and avoids introducing awareness of `ToolBusinessError` in this helper block.

---

### Finding 2 (Low-Medium): `search_document` `except Exception: pass` at `read_runtime.py:620` swallows `ToolBusinessError` from cancellation checkpoints

**File**: `dayu/fins/tools/read_runtime.py`, lines 602-621

```python
        try:
            _raise_if_fins_cancelled(cancellation_token)  # line 603
            all_secs = processor.list_sections()
            _raise_if_fins_cancelled(cancellation_token)  # line 605
            enriched_for_search = self._enrich_sections_with_semantic(...)
            _raise_if_fins_cancelled(cancellation_token)  # line 611
            bm25f_index = build_section_bm25f_index(enriched_for_search)
            _raise_if_fins_cancelled(cancellation_token)  # line 613
            semantic_profiles, query_term_df = _build_section_semantic_profiles(...)
            for sec in enriched_for_search:
                _raise_if_fins_cancelled(cancellation_token)  # line 616
                ...
        except Exception:  # line 620
            pass
```

**Evidence**: Same `ToolBusinessError` subclass-of-`Exception` concern as Finding 1. However, the impact is lower — after this try/except block, the very next code paths (single-query `_execute_query_search` at line 653 or multi-query loop at line 787) both have entry cancellation checkpoints. Cancellation is re-detected at the next boundary. The only harm is degraded ranking quality (empty `bm25f_index`, `semantic_profiles`, `ref_to_topic`).

**Severity rationale**: Acceptable for this slice. The cancellation signal is not permanently lost, and the ranking degradation on mid-construction cancel is a quality issue, not a correctness violation. However, the broad catch should be tightened in a follow-up slice to avoid future maintenance risk.

**Recommended fix** (deferred): Catch `(RuntimeError, TypeError, AttributeError, ValueError)` specifically, or re-raise `ToolBusinessError`.

---

### Finding 3 (Pass): All nine Fins read tools declare `execution_context_param_name`

**Evidence**: `dayu/fins/tools/fins_tools.py` — each of the nine tool factory functions sets `execution_context_param_name="execution_context"` in the `@tool` decorator:

| Line | Tool |
|------|------|
| 197 | `list_documents` |
| 281 | `get_document_sections` |
| 363 | `read_section` |
| 460 | `search_document` |
| 563 | `list_tables` |
| 650 | `get_table` |
| 732 | `get_page_content` |
| 820 | `get_financial_statement` |
| 913 | `query_xbrl_facts` |

Test `test_fins_read_declarations_request_execution_context_injection` (`tests/fins/test_fins_storage_provider.py:510`) asserts all nine declarations have `execution_context_param_name == "execution_context"`.

---

### Finding 4 (Pass): `execution_context` / `cancellation_token` do not enter LLM-facing schema

**Evidence**: `tests/tools/test_combined_tools_acceptance.py:206-210`:
```python
for definition in discovered_tools.tool_bundle.definitions:
    properties = definition.schema.function.parameters.properties
    assert "execution_context" not in properties
    assert "cancellation_token" not in properties
    assert "execution_context" not in definition.schema.function.parameters.required
    assert "cancellation_token" not in definition.schema.function.parameters.required
```

The `execution_context_param_name` is only adapter metadata, not a schema parameter. The `@tool` decorator separates it from the LLM-facing JSON schema.

---

### Finding 5 (Pass): Token propagation chain is correct — no private cancel state

**Evidence**:
- `_resolve_fins_cancellation_token` (`fins_tools.py:37-54`): reads only from `execution_context.cancellation_token`, returns `CancellationToken | None`.
- Each tool function passes the resolved token as `cancellation_token=` to the corresponding `read_runtime` method.
- `FinsReadRuntime` methods receive `cancellation_token` as keyword-only parameter; no instance attribute stores cancellation state between calls.
- `_raise_if_fins_cancelled` (`read_runtime.py:121-133`) and `_raise_if_fins_cancelled` (`read_runtime.py:139-161`) are stateless — they only call `cancellation_token.is_cancelled()` and raise if true.
- `search_engine.py` `_raise_if_search_cancelled` (`search_engine.py:59-82`) is identically stateless.

The plan's invariant "No read runtime private cancel state is stored between calls" is satisfied.

---

### Finding 6 (Pass): Checkpoint density covers plan-required risk boundaries

**Evidence** — checkpoint locations by risk class:

| Risk boundary | Checkpoint locations |
|---|---|
| Repository list/meta/blob reads | `_normalize_document_identity` (1401, 1416), `_resolve_canonical_ticker` (1456, 1471, 1473), `_collect_source_documents_by_kind` (1644, 1646, 1649, 1672), `_resolve_source_kind` (2086, 2088, 2093, 2095), `_create_processor` (2042, 2048, 2054, 2057) |
| Processor creation/read | `_get_or_create_processor` (1993, 2002, 2011), `read_section` (417-425), `get_table` (1031-1039), `get_page_content` (1140, 1154, 1156), `get_financial_statement` (1219, 1233, 1235) |
| Search engine loops | `_execute_query_search` (584, 601, 603, 634, 636, 640, 642), `_search_document_multi` (788, 804, 808, 819, 821, 830) |
| XBRL fact query/filtering loops | `query_xbrl_facts` (1290, 1306, 1311, 1316, 1337, 1354, 1362) |
| Table/statement assembly loops | `list_tables` (934, 961-963), `get_financial_statement` (1251), `get_table` (1069-1071), `list_documents` (258-259, 269-270) |
| Section semantic enrichment loops | `_enrich_sections_with_semantic` (1788, 1797), `get_document_sections` (via `_enrich_sections_with_semantic`) |

All plan-required risk boundaries in Slice 4 are covered.

---

### Finding 7 (Pass): Cancellation projects as stable `tool_cancelled` via legacy adapter

**Evidence**:
- `_raise_if_fins_cancelled` raises `ToolBusinessError(code="tool_cancelled", ...)` (`read_runtime.py:156-161`)
- `_raise_if_search_cancelled` raises `ToolBusinessError(code="tool_cancelled", ...)` (`search_engine.py:78-82`)  
- Both produce the same stable error code `"tool_cancelled"`
- Tests assert `outcome.result.error == "tool_cancelled"` in all cancellation scenarios (lines 590, 622, 659, 692 in `test_fins_storage_provider.py`)
- Plan R3 acknowledges that legacy adapter projects `ToolBusinessError(code="tool_cancelled")` as `ToolFailedOutcome`, not `ToolCancelledOutcome` — consistent with plan decision
- Existing `ToolArgumentError` behavior preserved — `test_representative_failures_project_to_current_failed_outcomes` (`test_combined_tools_acceptance.py:411`) passes with `invalid_argument` error codes for argument failures
- Existing `NotSupportedResult` behavior preserved — `get_page_content`, `get_financial_statement`, `query_xbrl_facts` return `_build_not_supported_result` when processor lacks capability

---

### Finding 8 (Pass): Storage access remains through `dayu.fins.storage` protocols

**Evidence**: All data access in `FinsReadRuntime` goes through instance attributes initialized in `__init__`:
- `self._company_repository: CompanyMetaRepositoryProtocol` — for company metadata
- `self._source_repository: SourceDocumentRepositoryProtocol` — for source document metadata and handles
- `self._processed_repository: ProcessedDocumentRepositoryProtocol` — for processed document metadata (capability flags)

No direct filesystem access, no bypass of storage protocols. The test `test_fins_import_boundaries_do_not_reverse_depend` (`test_fins_storage_provider.py:844`) confirms no reverse dependencies into Host/Service/UI/Engine.

---

### Finding 9 (Pass): `read_section` `**_kwargs` removal is safe

**Evidence**: `fins_tools.py` line 372 — `read_section` function signature is `(ticker, document_id, ref, execution_context)` — no `**_kwargs`. The `@tool` decorator (`fins_tools.py:355-371`) declares `parameters` with only `ticker`, `document_id`, `ref` properties (all required). The only other parameter is `execution_context` injected by the adapter. The schema validator validates against the declared `parameters` schema, which has not changed. No test failure indicates schema validation breakage.

---

### Finding 10 (Pass): Test coverage matches plan requirements

**Evidence** — plan-required test scenarios vs implementations:

| Plan requirement | Test | File:Line |
|---|---|---|
| `list_documents` pre-cancel returns `tool_cancelled` | `test_list_documents_pre_cancel_returns_tool_cancelled` | `test_fins_storage_provider.py:574` |
| `search_document` cancellation during search stops before all candidates | `test_search_document_cancellation_during_search_stops_before_all_candidates` | `test_fins_storage_provider.py:593` |
| `read_section` cancellation before processor read returns `tool_cancelled` | `test_read_section_cancelled_before_processor_read_returns_tool_cancelled` | `test_fins_storage_provider.py:626` |
| `query_xbrl_facts` cancellation during filtering stops promptly | `test_query_xbrl_facts_cancellation_during_filtering_stops_promptly` | `test_fins_storage_provider.py:663` |
| Nine tools declaration injection | `test_fins_read_declarations_request_execution_context_injection` | `test_fins_storage_provider.py:510` |
| Combined schema no pollution | `test_combined_discovery_returns_single_bundle_without_reserved_names` | `test_combined_tools_acceptance.py:188` |

Additional coverage:
- `test_search_document_cancellation_during_search_stops_before_all_candidates` asserts only 1 `search_calls` entry (exact match call before cancel), proving no fallback to later queries
- `test_read_section_cancelled_before_processor_read_returns_tool_cancelled` asserts `processor.read_section_calls == 0`, proving processor.read_section was never invoked
- `test_query_xbrl_facts_cancellation_during_filtering_stops_promptly` asserts `processor.query_calls == 1`, proving query was executed but filtering/cancel propagated

Missing coverage (non-blocking):
- No test for the `read_section` parent_title try/except window (Finding 1). Adding a targeted test after fixing Finding 1 would improve coverage.
- No test for cancel during `_enrich_sections_with_semantic` loop cancellation in `get_document_sections` — the function does have checkpoints in the loop, but no test triggers cancellation there.

---

### Finding 11 (Pass): AGENTS.md type discipline — no new Any/object/untyped parameters

**Evidence**: All new type signatures are fully specified:

| Addition | File | Signature |
|---|---|---|
| `_resolve_fins_cancellation_token` | `fins_tools.py:37` | `-> CancellationToken \| None` |
| `_raise_if_fins_cancelled` | `read_runtime.py:121` | `-> None` |
| `_raise_fins_cancelled` | `read_runtime.py:139` | `-> NoReturn` |
| `_raise_if_search_cancelled` | `search_engine.py:59` | `-> None` |
| Tool function `execution_context` parameters | `fins_tools.py` | `BatchToolExecutionContext \| None` (9x) |
| Runtime method `cancellation_token` parameters | `read_runtime.py` | `CancellationToken \| None` (9x + private helpers) |
| `_execute_query_search` `cancellation_token` | `search_engine.py:567` | `CancellationToken \| None` |
| `_search_document_multi` `cancellation_token` | `read_runtime.py:757` | `CancellationToken \| None` |
| `_enrich_sections_with_semantic` `cancellation_token` | `read_runtime.py:1770` | `CancellationToken \| None` |
| `_normalize_document_identity` `cancellation_token` | `read_runtime.py:1382` | `CancellationToken \| None` |
| `_resolve_canonical_ticker` `cancellation_token` | `read_runtime.py:1430` | `CancellationToken \| None` |
| `_resolve_canonical_document_id` `cancellation_token` | `read_runtime.py:1494` | `CancellationToken \| None` |
| `_collect_source_documents` `cancellation_token` | `read_runtime.py:1587` | `CancellationToken \| None` |
| `_collect_source_documents_by_kind` `cancellation_token` | `read_runtime.py:1628` | `CancellationToken \| None` |
| `_get_or_create_processor` `cancellation_token` | `read_runtime.py:1976` | `CancellationToken \| None` |
| `_create_processor` `cancellation_token` | `read_runtime.py:2024` | `CancellationToken \| None` |
| `_resolve_source_kind` `cancellation_token` | `read_runtime.py:2069` | `CancellationToken \| None` |

No `object`, `Any`, or untyped parameters/returns introduced. All docstrings are in Chinese with complete Args/Returns/Raises sections.

Pre-existing type debt (not this slice, not addressed): `_meta_cache` field typed as `dict[tuple[str, str], Optional[dict[str, Any]]]` contains `Any` in the value type. Not spread by this slice.

---

### Finding 12 (Pass): pyright clean, tests pass

- `pyright`: 0 errors, 0 warnings, 0 informations
- `pytest tests/fins/test_fins_storage_provider.py tests/tools/test_combined_tools_acceptance.py -q`: 25 passed
- 3 third-party `edgar` deprecation warnings — pre-existing, not introduced by this slice

---

## Open Questions

1. **Q1**: Should `_read_capability_flags` in `read_runtime.py` have a `cancellation_token` checkpoint? It accesses `self._processed_repository.get_processed_meta()` which reads a JSON file. However, this is called from `_collect_source_documents_by_kind` which already has double `_raise_if_fins_cancelled` bracketing (lines 1649, 1672). Low priority.

2. **Q2**: The `_diagnose_cross_document_locator` method at `read_runtime.py:1916` does not take `cancellation_token`. It iterates over cached processors and calls `read_section`/`read_table`. Since it's called only within `read_section`/`get_table` KeyError handlers, and is purely best-effort diagnostic, the cancel check before entering it (line 425 of `read_section`, line 1039 of `get_table`) provides sufficient bounding. No action needed.

## Conclusion

**Result: PASS** — 1 Medium-High finding (Finding 1) requiring fix before merge, 1 Low-Medium finding (Finding 2) acceptable for this slice. All other review items pass.

The implementation correctly:
- Injects `execution_context` into all nine Fins read tools
- Propagates `CancellationToken` from `BatchToolExecutionContext` through `FinsReadRuntime` into `search_engine`
- Preserves Host as cancel truth source (no private cancel state)
- Maintains storage protocol boundaries
- Covers plan-required checkpoint risk boundaries
- Projects cancellation as stable `tool_cancelled` through legacy adapter
- Removes `read_section` `**_kwargs` safely
- Passes type checking and all tests

**Required fix before merge**: Tighten `except Exception` at `read_runtime.py:470` to not swallow `ToolBusinessError` (Finding 1). Recommended approach: catch `(RuntimeError, TypeError, AttributeError, ValueError)` specifically.
