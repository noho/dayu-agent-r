# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch B1 Review Fix (AgentCodex)

## Scope

- Fix gate: Round 2 Batch B1 code-review accepted findings only.
- Accepted findings fixed:
  - B1-MIMO-01: HKEX explicit `total_count > row_count` truncation coverage.
  - B1-02: `_coerce_non_negative_int` accepts only non-negative integral floats.
- Rejected findings left unchanged:
  - B1-MIMO-02
  - B1-01
  - B1-03
- Batch B2/C/D/E not modified.

## Semantic Owner

HKEX title search completeness is owned by `dayu.fins.downloaders.hkexnews_downloader`.
The owner extracts rows plus provider-declared total count, narrows total count to a non-negative integer, and fails closed when a single-page response cannot prove completeness. Tests assert the owner-level behavior through `HkexnewsDiscoveryClient.list_report_candidates` with `httpx.MockTransport`.

## Changes

- `dayu/fins/downloaders/hkexnews_downloader.py`
  - Extended `_coerce_non_negative_int` to accept `float` values only when they are non-negative and integral.
  - Non-integral floats and negative floats still return `None`, preserving fail-closed behavior.
- `tests/fins/test_hkexnews_downloader.py`
  - Added explicit `total > rows` truncation coverage.
  - Added integral float total acceptance coverage.
  - Added non-integral and negative float total rejection coverage.
  - Widened the title-search test payload helper return type to `dict[str, JsonValue]` so tests can represent JSON numeric totals without type ignores.

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_hkexnews_downloader.py -q`
  - Passed: 26 passed.
- B1 focused matrix:
  - `source .venv/bin/activate && pytest tests/fins/test_hkexnews_downloader.py tests/fins/test_fins_storage_provider.py tests/fins/test_cn_download_runtime.py tests/fins/test_sec_pipeline_download.py -q`
  - Passed: 111 passed, 3 third-party `edgar` deprecation warnings.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Passed: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Passed.

## README Check

- `dayu/fins/README.md` and `tests/README.md` update constraints were reviewed.
- No README update was needed because this fix does not change Fins public capability, architecture, user workflow, command surface, or test layer structure.

## Residual Risk

- HKEX pagination remains outside Batch B1 scope. Current behavior still fails closed when completeness cannot be proven.
- `total_count < row_count` contradictory provider data behavior remains unchanged because it was not an accepted finding in this fix gate.
