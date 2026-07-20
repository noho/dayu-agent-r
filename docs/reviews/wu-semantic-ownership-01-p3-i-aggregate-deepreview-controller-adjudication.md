# WU-SEMANTIC-OWNERSHIP-01 P3-I Aggregate DeepReview Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub-WU: `P3-I - Public CLI/package entrypoints and terminal display watermark`
- Aggregate base: `b24b0a76`
- Aggregate validation: `docs/reviews/wu-semantic-ownership-01-p3-i-aggregate-validation.md`
- DeepReview artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-i-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-i-aggregate-deepreview-ds.md`

## Review Verdicts

| Reviewer | Verdict | Material findings |
|---|---|---|
| AgentMiMo | PASS | 0 |
| AgentDS | PASS | 0 |

## Controller Decision

P3-I aggregate deepreview is accepted with no fix gate. S1 and S2 are both accepted, all accepted plan/code-review/fix/re-review findings are closed, and no aggregate material finding remains open.

## Residual Risk Adjudication

- Diagnostic-only public entrypoints: accepted current-state risk. README and tests clearly state that `dayu-web`, `dayu-wechat`, and `dayu-render` are reserved public commands that currently provide help and unavailable diagnostics only.
- Cursor write failure after render may repeat a terminal on later reconnect: accepted local delivery trade-off from the P3-I plan; now covered by prompt/startup/interactive cursor failure propagation tests.
- `dayu.render` package-data resource globs are intentionally unused until future render capability work. Current P3-I only owns import/help/diagnostic truth.
- `dayu.runtime.argparse_exit` direct unit-test absence is accepted as non-blocking because the helper is covered through all three public entrypoint paths and no reviewer classified it as a material finding. Future runtime cleanup may add direct micro-tests if coverage tooling requires it.

## Validation Accepted

- `pytest tests/cli -q`: `294 passed, 3 warnings`
- `python -m pyright dayu/ tests/ utils/`: `0 errors, 0 warnings, 0 informations`
- `git diff --check b24b0a76..HEAD`: passed
- Module help smoke:
  - `python -m dayu.web --help`: passed
  - `python -m dayu.wechat.main --help`: passed
  - `python -m dayu.render.render --help`: passed
- Console script help smoke:
  - `dayu-web --help`: passed
  - `dayu-wechat --help`: passed
  - `dayu-render --help`: passed

## Propagation Audit

- Public entrypoint truth flows from `pyproject.toml` script targets to importable command modules, README declarations, and CLI tests.
- Terminal result truth remains Host/Service-owned; CLI renderers own output and exit code; CLI cursor store owns local delivery watermarks after successful rendering.
- S2 does not mutate terminal facts, renderer policy, Host/Service state, durable Host truth, trace, memory, audit, or LLM-facing content.

## Next Gate

P3-I is locally complete at aggregate deepreview. The umbrella WU is not complete. Continue with the next sub-WU (`P3-J` unless superseded by the control document) and later full-repository deepreview rounds before final closeout.
