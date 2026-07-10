# WU-SEMANTIC-OWNERSHIP-01 P3-E S3 Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-E - Tool result, accepted status, wait callback, and Fins direct stream contracts`
- Slice: `S3 - Fins direct unique RESULT protocol error and docs sync`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s3-implementation-codex.md`

## Controller Result

`ready-for-code-review`

The S3 implementation satisfies the accepted plan target pending independent code review.

## Direct Checks

### Typed Protocol Error Contract

- `dayu/fins/direct_events.py` defines `FinsDirectStreamProtocolErrorKind` with `missing_result` and `duplicate_result`.
- `FinsDirectStreamProtocolError` carries typed `reason`, `operation_kind`, and non-empty `message`.
- Both symbols are exported from `__all__`.

### Runtime Owner

- `FinsIngestionRuntime._run_direct_stream(...)` buffers the first `RESULT`.
- It continues draining until `_DirectStreamProducerDone`.
- Duplicate `RESULT` raises `FinsDirectStreamProtocolError(DUPLICATE_RESULT, ...)`.
- Missing `RESULT` after sentinel raises `FinsDirectStreamProtocolError(MISSING_RESULT, ...)`.
- The old `_direct_missing_result_event(...)` synthetic business failure helper is removed.
- No-hang normal direct stream test passes through the drain-until-sentinel path.

### Service Boundary

- `dayu.service.fins_direct._ensure_result_event(...)` enforces the same missing / duplicate protocol errors for runtime streams.
- `FinsDirectUsageError` remains scoped to Service parameter misuse.
- The old `_missing_result_event(...)` synthetic business failure helper is removed.

### CLI Boundary

- `FinsDirectStreamContractViolation` is removed.
- CLI catches and renders `FinsDirectStreamProtocolError` directly.
- CLI no-result fallback creates the shared typed protocol error, not a second CLI-local exception and not a fabricated business `RESULT`.

### Business Failure Separation

- Existing business failures still flow as `FinsEventType.RESULT` with `FinsResultStatus.FAILURE`.
- S3 only changes direct stream protocol violations.

## Validation Commands

Passed:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q
```

Result: `124 passed, 3 warnings in 3.21s`. Warnings are existing `edgar` deprecation warnings.

Passed:

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

Passed coverage gate:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py --cov=dayu.fins.direct_events --cov=dayu.fins.ingestion_runtime --cov=dayu.service.fins_direct --cov-report=term-missing -q
```

Result: `124 passed, 3 warnings`; `dayu/fins/direct_events.py` coverage `92%`, `dayu/fins/ingestion_runtime.py` coverage `90%`, `dayu/service/fins_direct.py` coverage `92%`, total `90%`.

Passed:

```bash
rg -n "_DirectStreamProducerDone|FinsDirectStreamContractViolation|FinsDirectStreamProtocolError|_direct_missing_result_event|_missing_result_event" dayu/fins dayu/service dayu/cli tests/fins tests/service tests/cli
```

Classification:

- `_DirectStreamProducerDone`: expected sentinel type, queue item, producer finally, consumer drain, and queue fallback in `dayu/fins/ingestion_runtime.py`.
- `FinsDirectStreamProtocolError` / `FinsDirectStreamProtocolErrorKind`: expected shared contract, runtime, Service, CLI, README, and tests.
- `FinsDirectStreamContractViolation`: no matches.
- `_direct_missing_result_event`: no matches.
- `_missing_result_event`: no matches.

Passed:

```bash
git diff --check
```

Result: no output.

## README Decision

- `dayu/fins/README.md` update is accepted: it removes stale direct stream text that said missing result becomes a failure result and now states missing / duplicate `RESULT` raises `FinsDirectStreamProtocolError`.
- `dayu/service/README.md` update is accepted: it removes stale `fins_direct` synthetic missing-result behavior and documents typed protocol error behavior.
- `tests/README.md` update is accepted: it records updated Fins direct / CLI coverage semantics.
- Root `README.md` and `dayu/README.md` no-op is accepted: no user workflow, command syntax, installation, output channel, or top-level layer boundary changed.

## Propagation Audit

- Producer: Fins direct producers emit `PROGRESS` and exactly one business terminal `RESULT`; producer wrapper emits `_DirectStreamProducerDone`.
- Runtime validation owner: `FinsIngestionRuntime._run_direct_stream(...)` detects missing / duplicate terminal `RESULT` and raises shared typed protocol error.
- Service validation owner: `dayu.service.fins_direct._ensure_result_event(...)` preserves the same contract for mocked or alternative runtime streams.
- CLI projection: CLI renders the shared typed protocol error as command failure and does not synthesize a business `RESULT`.
- Documentation / tests: README and tests now distinguish stream protocol errors from legitimate business failure results.

## Residual Risk

- Runtime now delays terminal `RESULT` until producer done is observed. Target tests and the no-hang test pass for current producers. Future producers that emit `RESULT` then block before returning will surface a producer lifecycle bug at the runtime owner rather than being hidden downstream.
- Producer execution exceptions continue to become business failure `RESULT`, which is pre-existing Fins business-error behavior and remains distinct from stream protocol violations.

