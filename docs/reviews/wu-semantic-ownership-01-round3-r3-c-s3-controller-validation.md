# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S3 Controller Validation

## Scope

- Slice: S3 Host Adapter Snapshot And Service-Owned Fins Wait Glue
- Controller: AgentCodex
- Status: pass
- Tool-security scope: not implemented; deferred items remain out of scope

## Validation Commands

### Focused S3 Matrix

```text
source .venv/bin/activate && pytest tests/service/test_fins_wait_adapter.py tests/service/test_host_assembly.py tests/service/test_import_boundary.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_observation_runner.py tests/host/test_open_host_runtime.py -q
```

Result:

```text
326 passed, 3 warnings
```

Warnings are existing `edgar` deprecation warnings unrelated to S3.

### Full Type Check

```text
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

### New Service Adapter Coverage

```text
source .venv/bin/activate && pytest tests/service/test_fins_wait_adapter.py --cov=dayu.service.fins_wait_adapter --cov-report=term-missing -q
```

Result:

```text
17 passed, 3 warnings
dayu/service/fins_wait_adapter.py coverage: 92%
```

### Diff Hygiene

```text
git diff --check
```

Result: pass.

### Boundary Scans

```text
rg -n '(^|[[:space:]])(from|import)[[:space:]]+dayu\.host' dayu/fins --glob '*.py'
```

Result: no matches.

```text
test ! -e dayu/fins/ingestion/wait_adapter.py
```

Result: pass.

```text
rg -n '(^|[[:space:]])(from|import)[[:space:]]+dayu\.(host|service)' tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py
```

Result: no matches.

## Controller Checks

- Host owns durable row to adapter snapshot projection.
- Service adapter imports Host public wait adapter/API types only; no `dayu.host.durable` import.
- Fins production has zero Host imports.
- Old Fins adapter module is deleted with no compatibility shim.
- Fins tests no longer import Host/Service wait adapter contracts.
- Service tests own Fins wait adapter behavior.
- README docs align with landed architecture and do not introduce tool-security commitments.

## Tool-Security Boundary

No tool-security issue was implemented in S3. The current diff does not implement upload allowlists, file authority, symlink-safe upload source policy, URL/TLS/redirect/SSRF provenance, remote byte budgets, or LLM-facing security schema/prompt changes.
