## Summary

- implement the frozen F01–F13 interactive conformance corrections across CLI, Service/Host lifecycle, Engine response identity, tests, and owned documentation
- remove prompt/interactive legacy options, unify label continuity, add terminal-aware composer/non-TTY/cancel/type-ahead behavior, and recover orphaned active Runs after a bounded stale deadline
- enforce one compaction terminal, per-Session pre-start governance single-flight, and durable compactor successful-response provider identity
- include the original interactive calibration/adjudication commits plus the full Gateflow plan, slice, aggregate review, and validation artifacts

## Scope boundaries

- this PR does not adjudicate or close G01–G07; those remain for the next formal CLI calibration campaign
- it does not add interactive resume, `/clear`, `/new`, `/resume`, legacy parameter/schema compatibility, or unrelated scheduler/locking abstractions
- it does not change the independent download/preprocess/process product oracles

## Validation

- affected CLI/Service: 1181 passed, 7 skipped
- affected Host: 775 passed
- full Engine/Host: 2957 passed, 1 skipped, 6 deselected; 6 phase5 scheduler/test race failures were reproduced on clean base and classified as non-regressions
- recovery: 116 passed plus a real POSIX owner-SIGKILL immediate-reconnect smoke that recovered within the same invocation after the stale deadline
- aggregate accepted-finding fix: 185 passed; production owner coverage 86% / 95% / 84%
- aggregate focused controller validation: 12 passed; real SQLite two-writer terminal competition test passed 10 consecutive runs
- full pyright: 0 errors, 0 warnings, 0 informations
- diff, scope, secret/credential/provider-payload scans: passed

## Provider identity evidence

A real successful compactor invocation produced durable, redacted response identity bound to the same compaction operation, semantic attempt, proposal manifest, candidate, and output. The evidence contains safe effective provider/model identity, client correlation, and an available provider request id; it contains no endpoint, credential/header value, secret, or raw provider payload. It remains raw validation evidence rather than an accepted formal interactive scenario until the later G01–G07 calibration and renderer-target closure.

## Review status

- independent AgentMiMo and AgentDS plan reviews: complete, findings adjudicated and re-reviewed
- every S1–S6 implementation: dual independent code review, accepted finding fix, and dual re-review complete
- aggregate deepreview: dual independent review, controller adjudication, 4 accepted findings fixed, dual re-review PASS
- PR-specific dual independent deepreview is intentionally performed only after this draft PR exists; its artifacts/fixes will be pushed to this draft before final closeout
