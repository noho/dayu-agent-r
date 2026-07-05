# WU-TOOLS-CANCEL-01 Residual Hardening S3 Implementation - Codex

## Gate

- Work unit: `WU-TOOLS-CANCEL-01`
- Slice: S3 - Tool Migration And Fins AAPL XBRL Fixture Breadth
- Agent: AgentCodex
- Branch: `phase/wu-tools-cancel-01`
- Status: implementation completed; no commit, push, PR state change, issue close, or external comment performed per user instruction.

## Changed

- Migrated Doc, Fins read, and Web process-backed targets to `dayu.contracts` process envelope helpers:
  - `process_tool_completed_envelope(...)`
  - `process_tool_failed_envelope(...)`
- Removed local duplicated process envelope constants from:
  - `dayu/tools/doc_tools.py`
  - `dayu/fins/tools/fins_tools.py`
  - `dayu/tools/web/web_tools.py`
- Stopped appending recovery `hint` text into failed envelope `message`; failed process envelopes now emit `hint` as a separate structured field when available.
- Added tests that assert Doc/Web/Fins failed process target envelopes keep `message` and `hint` separate.
- Added tests that prevent `_DOC_PROCESS_*`, `_FINS_PROCESS_*`, and `_WEB_PROCESS_*` local envelope constants from reappearing.
- Added repository fixture files under `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/` copied from the existing downloaded AAPL filing:
  - `meta.json`
  - `aapl-20240928.htm`
  - `aapl-20240928_htm.xml`
  - `aapl-20240928.xsd`
  - `aapl-20240928_pre.xml`
  - `aapl-20240928_cal.xml`
  - `aapl-20240928_def.xml`
  - `aapl-20240928_lab.xml`
- Added spawned process-backed Fins coverage for `query_xbrl_facts` using the AAPL fixture. The test constructs a repository-valid temporary Fins workspace through `dayu.fins.storage` repositories and asserts a completed outcome containing verified `NetIncomeLoss` facts.

## Verified

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py tests/fins/test_fins_storage_provider.py -q`
  - Result: `114 passed, 1 skipped`
  - Notes: edgartools deprecation warnings only.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed.
- `git status --short`
  - Result before this artifact: only the intended production/test files and new `tests/fins/fixtures/` were modified/untracked.
- Additional grep check:
  - Production files no longer contain `_DOC_PROCESS_*`, `_FINS_PROCESS_*`, `_WEB_PROCESS_*`, `_process_failure_message`, or `Hint:` message concatenation.

## Docs

- `tests/README.md`: checked; no update needed because this adds an ordinary Fins fixture and does not change test-running rules.
- `dayu/fins/README.md`: checked due `dayu/fins/` production change; no update needed because Fins public capability, architecture boundary, and developer-facing workflow did not change.

## Residual Risks

- Live SEC/network taxonomy resolution was not used or required; the AAPL XBRL test passes through local fixture files only.
- The fixture is intentionally minimal but includes the full local files required by current `xbrl_file_discovery` and processor loading paths. Future processor changes that require additional taxonomy assets should update this fixture through the storage-backed helper rather than inventing facts.
- Existing optional Web live browser cleanup smoke remains skipped unless its environment flag is set; this is an S2B residual, not introduced by S3.

## Blockers

- None.

## Completion Status

- READY_FOR_CONTROLLER
- Artifact: `docs/reviews/wu-tools-cancel-01-residual-hardening-s3-implementation-codex.md`
- Blocking open question: None

## Review Fix Addendum

- Controller decision: AgentMiMo PASS; AgentDS PASS_WITH_FINDINGS.
- Accepted DS-02 LOW: `_build_fins_aapl_xbrl_workspace` now writes `CompanyMeta` inside the same `begin_batch("AAPL")` try/rollback window as the source document and blob writes.
- Accepted DS-03 LOW: `_web_process_failed_envelope` now returns `JsonValue` directly and no longer casts the contract helper result to `WebPayload`.
- Rejected DS-01 LOW remains intentionally unchanged: Doc generic exceptions do not have a concrete business recovery hint, and failed envelope `hint` is optional by contract.
- Fix validation:
  - `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py tests/fins/test_fins_storage_provider.py -q`: `114 passed, 1 skipped`.
  - `source .venv/bin/activate && pyright`: `0 errors, 0 warnings, 0 informations`.
  - `git diff --check`: passed.
  - `git status --short`: intended S3 files, review artifacts, implementation artifact, and fixture files remain uncommitted.
