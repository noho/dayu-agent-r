# WU-TOOLS-CANCEL-01 S2 Aggregate Deepreview Controller Adjudication

## Scope

- Work unit: WU-TOOLS-CANCEL-01
- Gate: S2 aggregate validation / aggregate deepreview adjudication
- Branch: `phase/wu-tools-cancel-01`

## Inputs

- S2E aggregate validation: `docs/reviews/wu-tools-cancel-01-s2e-aggregate-validation-codex.md`
- Aggregate deepreview artifacts:
  - `docs/reviews/wu-tools-cancel-01-s2-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-s2-aggregate-deepreview-ds.md`
- Accepted S2 slice commits:
  - S2A1 `32030ca9`
  - S2A2 `0fea8da0`
  - S2B `03e546f5`
  - S2C `834b0df6`
  - S2D `94b3c196`

## Decision

S2 aggregate is accepted.

Typed execution capability forms a closed production path from `ToolDefinition.execution` through Host declaration-backed capsule selection and process-backed JSON envelope mapping. Engine-facing `ToolSchema` and LLM-facing tool schemas do not receive execution capability metadata.

Doc, Fins read, and Web production blocking paths now use process-backed execution. Fins download / preprocess / upload remain awaiting tools with `EXTERNAL_JOB` lifecycle semantics and are intentionally outside process-backed read closeout.

## Review Adjudication

- AgentMiMo aggregate deepreview: `PASS`, with four low-severity findings.
- AgentDS aggregate deepreview: `PASS`, with two low-severity findings.
- Controller accepts all findings as non-blocking residual / hardening items:
  - `FinsToolLimits` missing `slots=True`: style / memory concern only, not process correctness.
  - completed envelope missing-value test gap: code is correct; a low-priority test hardening item.
  - process target exception Host-level test gap: lower runtime layer and Host malformed / failure mapping are covered; low-priority test hardening.
  - `execution_capsule_factory` docstring precision: developer wording cleanup, not behavior.
  - process envelope constants duplicated across Host / Doc / Fins / Web: known contract-hardening follow-up.
  - process capsule terminate / kill grace constants: production tuning follow-up, not #87 closeout blocker.

No current-slice fix is required.

## Controller Validation

Controller reran:

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/tools/test_doc_tools_provider.py tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/web/test_web_tools_provider.py -q
source .venv/bin/activate && pytest tests/contracts tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q
source .venv/bin/activate && pyright
git diff --check
```

Observed:

- Host / Doc / Fins / Web focused matrix: 219 passed, 3 third-party `edgar` deprecation warnings.
- Contracts / runtime discovery matrix: 92 passed.
- `pyright`: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: passed.

## Residual Risk

All residual risks are classified and non-blocking:

- Web process cold-start cost: future performance work if telemetry warrants.
- Process envelope has no structured `hint` field: future Host process envelope contract hardening.
- Playwright nested process cleanup: future Web / Playwright smoke or stress coverage.
- Fins `query_xbrl_facts` spawned-child real XBRL fixture: future Fins fixture expansion.
- Doc FIFO test strategy / security review: future Doc test strategy hardening.
- Envelope constants single-source cleanup and process capsule grace tuning: future contract / production hardening.

No orphan residual risk remains for S2.

## Next Gate

Proceed to draft PR gate for WU-TOOLS-CANCEL-01 after committing the accepted aggregate artifacts and control document update.
