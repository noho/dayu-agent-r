# WU-TOOLS-01-F02 Aggregate Deepreview Re-Review Controller Adjudication

## Gate

- Work unit: `WU-TOOLS-01-F02`
- Current gate: aggregate deepreview re-review adjudication
- Fix artifact: `docs/reviews/wu-tools-01-f02-aggregate-deepreview-fix-codex.md`
- MiMo re-review artifact: `docs/reviews/wu-tools-01-f02-aggregate-deepreview-rereview-mimo.md`
- DS re-review artifact: `docs/reviews/wu-tools-01-f02-aggregate-deepreview-rereview-ds.md`
- Decision date: 2026-06-09

## Overall Decision

Aggregate deepreview re-review verdict is `pass`.

Both reviewers confirmed:

- accepted CLI mutual-exclusion fix is implemented and tested;
- accepted URL safety / header redaction deterministic tests are implemented;
- rejected/deferred findings were not accidentally changed;
- no new regressions, no scope creep, no default CI/Web smoke/Host/Engine/ToolRuntime change.

## Accepted Finding Status

| Finding | Status | Evidence |
|---|---|---|
| `--url` and `--url-file` mutual-exclusion validation missing. | fixed | `_validate_cli_mode(options)` now validates exactly one input mode before dispatch; `test_cli_requires_exactly_one_url_mode` covers conflict and missing cases. |
| URL normalization/safety and header redaction helper coverage missing. | fixed | Focused deterministic tests cover URL normalization failures, local/private host blocking, IPv4-mapped IPv6 evidence, explicit private-network allow behavior, and sensitive header redaction. |

## Residual Risks

All remaining residual risks are classified:

- live network, real Playwright, and storage-state environment behavior remain outside default CI; owner: WU-TOOLS-01-F03.
- F03 must explicitly declare any diagnostic JSON fields it consumes beyond the F02 minimum stable subset; owner: WU-TOOLS-01-F03.
- batch concurrency remains serial and is deferred; owner: WU-TOOLS-01-F03 or later maintenance only if it becomes a practical bottleneck.

## Validation Evidence

Controller validation after fix:

- `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_web_tools_provider.py -q`: `27 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`: `0 errors`
- `bash -n utils/diag_web.sh utils/diag_web_batch.sh`: passed
- `git diff --check`: passed
- precise forbidden import / wide-type scan: no matches

## Next Gate

Proceed to accepted deepreview commit, then ready-to-open-draft-PR.
