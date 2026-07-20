# R3-E Slice S4 Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Slice: `R3-E S4`
- Gate: controller validation after implementation
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s4-implementation-codex.md`
- Plan truth: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`

## Result

Controller validation passes. S4 is ready for code review.

The implementation stays inside the accepted S4 boundary: bounded Documents source snapshot, doc tool read/list/search producer budgets, processor factory minimum接入, and corresponding tests. No Fins, tool-security, S5, aggregate, or control-bookkeeping implementation is present.

## Validation Commands

| Command | Result |
| --- | --- |
| `source .venv/bin/activate && pytest tests/documents/test_processors.py tests/documents/test_import_boundary.py -q` | PASS: `17 passed` |
| `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py -q -k "list_files or read_file or search_files or limit or bounded or cancellation"` | PASS: `37 passed, 29 deselected` |
| `source .venv/bin/activate && pytest tests/documents tests/tools/test_doc_tools_provider.py -q` | PASS: `83 passed` |
| `source .venv/bin/activate && pytest tests/documents tests/tools/test_doc_tools_provider.py -q --cov=dayu.documents.processors.bounded_source --cov=dayu.tools.doc_tools --cov-report=term-missing` | Expected tooling failure: collection fails before tests with NumPy native module double-load under dotted `--cov=...` source discovery. |
| `source .venv/bin/activate && coverage erase && coverage run -m pytest tests/documents tests/tools/test_doc_tools_provider.py -q && coverage report --include='dayu/documents/processors/bounded_source.py,dayu/tools/doc_tools.py' -m` | PASS: `83 passed`; `bounded_source.py` `88%`, `doc_tools.py` `81%`, total `82%`. |
| `source .venv/bin/activate && pyright` | PASS: `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | PASS |

The exact pytest-cov invocation failure is classified as validation tooling residual, not as product failure, because the same test set passes under normal pytest and under `coverage run`, and the affected files meet the >=80% threshold. No package initializer workaround was applied.

## Contract Checks

- `BoundedSourceSnapshot` is layer-neutral and imports only standard library plus the local `Source` protocol.
- `SourceBudgetExceeded` is typed and carries source URI, byte limit, and observed bytes.
- `create_doc_file_processor` now consumes caller-provided `Source` instead of reopening an unbounded local path.
- `DocResourceBudget` is fixed in `doc_tools.py`, enters the process target, and is not configurable by provider input.
- `read_file` returns self-describing `returned_chars`, `content_truncated`, `scan_complete`, `total_lines`, and optional `line_range`.
- `list_files` reports bounded directory iteration with `scanned_entries`, `scan_complete`, `total`, and `truncated_reason`.
- `search_files` reports bounded directory/source/result outcomes with `total_matches`, `scanned_entries`, `skipped_oversized_files`, `scan_complete`, and `truncated_reason`.
- Tool descriptions mention partial fields and next action, keeping LLM-facing semantics self-contained.

## Source Scans

- `git diff --name-only` plus untracked scan is limited to:
  - `dayu/documents/processors/_doc_processor_factory.py`
  - `dayu/documents/processors/bounded_source.py`
  - `dayu/tools/doc_tools.py`
  - `tests/documents/test_import_boundary.py`
  - `tests/documents/test_processors.py`
  - `tests/tools/test_doc_tools_provider.py`
  - S4 implementation / validation artifacts.
- No diff-added `Any`, `object`, `getattr`, `hasattr`, `type: ignore`, or pyright suppression.
- No `dayu.documents` import of `dayu.tools`, Host, Engine, Service, UI, or Fins.
- No Fins, tool-security, file-authority, symlink-safe upload, SSRF/TLS policy, or generic capability implementation. Keyword hits are limited to explicit exclusions/residual notes in artifacts or the import-boundary forbidden list.

## README Decision

S4 changes tests and user-visible tool result fields, but the accepted plan says `tests/README.md` should be updated after S1-S4 behavior is accepted. Controller keeps README unchanged at implementation validation and will revisit it after S4 code review/re-review acceptance.

## Residual Classification

| Residual | Classification |
| --- | --- |
| SIGKILL / host crash may leave at most one bounded system temp file. | Accepted operational limitation with owner `dayu.documents.processors.bounded_source`; future durable cleanup belongs to a Documents temp-artifact cleanup WU. |
| Processor internal object expansion can exceed raw byte size. | Accepted processor-complexity limitation; S4 owns byte cap before processor construction, not per-format object complexity. |
| Path validation to `open()` symlink/rename race remains possible. | Assigned authority residual; S4 guarantees byte cap on the actually opened handle and does not implement file-authority/tool-security. |
| Directory cap and source skip make totals unknown. | Accepted partial semantics; `scan_complete=false`, `total=null`, skipped count, and reason are explicit. |
| pytest-cov dotted source fails with NumPy double-load. | Validation tooling residual; equivalent coverage path passes. |

## Next Gate

Dispatch R3-E S4 code review to AgentMiMo and AgentDS. If findings are accepted, return to fix gate; otherwise accept and commit S4.

