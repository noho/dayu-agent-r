# UF-FIX11 S3 Implementation Review

## Review metadata

- reviewer: MiMo (independent)
- date: 2026-08-17
- gate: S3 implementation review
- branch: `codex/upload-filing-oracle`
- scope: uncommitted diff (14 files, +666/-11)
- artifact: `docs/gateflow/uf-fix11-s3-implementation-20260817.md`
- prerequisites read: S3 plan, S3 projection boundary amendment, S3 projection boundary acceptance, S1+S2 implementation artifact

## Review methodology

- Read full diff, all modified production/test files, all plan/amendment/acceptance documents.
- Verified tests execute: 543 passed, 3 warnings (edgar deprecation).
- Verified pyright: 0 errors on all 5 modified production files.
- Verified AST regression: `_direct_result_event` exactly 2 callsites, `warnings` parameter has no default.
- Verified observation helpers zero diff.
- Verified Host/Engine/material/oracle/scenario/registry frozen boundary: zero diff outside allowed files.

---

## Findings

### F1 — [LOW] CANCELLED + non-empty warnings defense-in-depth relies on summary invariant, not direct builder guard

**Code evidence**: `ingestion_runtime.py:6482-6499` — the CANCELLED branch overrides `details`, `error_kind`, `error_message`, `download`, `failure` but does NOT override `warnings`. The `warnings` parameter passes through unchanged to `FinsResultSummary`.

**Design intent** (from amendment): "CANCELLED 分支不重写 warnings，非法非空组合由 FinsResultSummary constructor fail closed."

**Assessment**: Correct. The defense is layered:
1. `FinsUploadResultSummary.__post_init__` rejects non-empty warnings for cancelled/deleted/failed.
2. `FinsResultSummary.__post_init__` rejects non-empty warnings for non-SUCCESS.

Both layers are tested independently. The `_direct_upload_terminal_events` passes `summary.warnings` which is already validated. The generic `_emit_claimed_direct_result` hardcodes `warnings=()`. No path can reach `FinsResultSummary(status=CANCELLED, warnings=non-empty)` without one of the two constructors rejecting first.

**Risk**: If a future producer bypasses `FinsUploadResultSummary` and calls `_direct_result_event` directly with CANCELLED + non-empty warnings, the `FinsResultSummary` constructor will reject. This is the intended fail-closed behavior. No action needed.

---

### F2 — [LOW] `_direct_result_event` CANCELLED branch reassigns `details` to `()` — the `warnings` parameter is a tuple, so it cannot be accidentally mutated

**Code evidence**: `ingestion_runtime.py:6483` — `details = ()` reassigns the local variable. `warnings` is also a tuple but is NOT reassigned in the CANCELLED branch. Since tuples are immutable, even if the caller's reference were reused, no mutation is possible.

**Assessment**: No issue. The `warnings` tuple identity flows through unchanged. The `FinsResultSummary` constructor performs `type(warning) is not CompanyMetadataWarning` checks on each element, which would catch any non-precise-typed element regardless of source.

---

### F3 — [INFO] `FinsResultSummary.warnings` default is `()` — natural empty state, not compatibility fallback

**Code evidence**: `direct_events.py:612` — `warnings: tuple[CompanyMetadataWarning, ...] = ()`

**Assessment**: The amendment explicitly addresses this: "把 public field 改为 required 会迫使修改大量与本事实无关的 download/preprocess 构造点及当前 S3 allowed files 之外的测试，仅用于重复表达自然空状态，增加耦合而不提升 upload copy 的严格性，因此拒绝。"

The producer helper `_direct_result_event` has NO default for `warnings` (verified by AST test: `kw_defaults[warnings_index] is None`). Every production producer must explicitly declare the fact. The public field's default only covers downstream consumers that construct `FinsResultSummary` directly (tests, non-upload paths). This is correct.

---

### F4 — [PASS] Warning propagation chain is mechanical and single-sourced

**Code evidence** (verified each link):

1. `FinsUploadPipelineResult.warnings` — typed tuple from S1+S2 commit owner (zero diff in S3)
2. `_upload_summary_from_result` (`service_runtime.py:323`) — `warnings=result.warnings` (explicit copy, no default dependency)
3. `FinsUploadResultSummary.warnings` — same tuple, validated by `__post_init__`
4. `_direct_upload_terminal_events` (`ingestion_runtime.py:6577`) — `warnings=summary.warnings`
5. `_direct_result_event` → `FinsResultSummary(warnings=warnings)` — passes through unchanged
6. `render_fins_direct_event` (`output.py:242-243`) — `for warning in event.result.warnings: print(warning.message, file=effective_stderr)`
7. `_completed_result_value` (`fins_wait_adapter.py:582`) — `warnings: company_metadata_warnings_to_json(result.warnings)`
8. `FinsUploadResultSummary.to_json_summary` (`ingestion_runtime.py:1931`) — `warnings: company_metadata_warnings_to_json(self.warnings)`

Every link is an explicit typed copy. No raw field parsing, no inference from details/message/storage, no default value dependency. The same immutable `CompanyMetadataWarning` tuple flows from commit owner to every consumer.

---

### F5 — [PASS] Summary exact type / at-most-one / status closed set

**Code evidence**:

- `FinsResultSummary.__post_init__` (`direct_events.py:637-642`): `len > 1` → ValueError; `type(warning) is not CompanyMetadataWarning` → TypeError; `warnings and status is not SUCCESS` → ValueError.
- `FinsUploadResultSummary.__post_init__` (`ingestion_runtime.py:1863-1871`): `len > 1` → ValueError; `type(warning) is not CompanyMetadataWarning` → TypeError; `warnings and status not in {ok, skipped}` → ValueError.
- `FinsUploadPipelineResult.__post_init__` (`ingestion_runtime.py:1734-1742`): same pattern, `ok/skipped` closed set.

**Tests verified**:
- `test_fins_result_summary_warning_invariant_is_exact_bounded_and_success_only` — tests exact type, at-most-one, FAILURE/CANCELLED rejection.
- `test_upload_summary_warning_contract_is_exact_bounded_and_success_only` — tests exact type, at-most-one, failed/cancelled/deleted rejection, JSON round-trip.
- `test_pipeline_warning_invariant_rejects_non_success_status` — parametrized over all non-ok/skipped statuses.

All three layers enforce the same contract independently. No layer can bypass another.

---

### F6 — [PASS] Direct builder exact two callsites / no default / no silent zeroing

**Code evidence** (AST-verified):

1. `ingestion_runtime.py:6245` — inside `_emit_claimed_direct_result`: `warnings=()` (generic/non-upload)
2. `ingestion_runtime.py:6565` — inside `_direct_upload_terminal_events`: `warnings=summary.warnings` (upload)

**AST test**: `test_direct_result_builder_callsites_are_exact_and_never_rewrite_warnings`:
- `len(calls) == 2` — exact count
- `set(warning_expressions) == {"summary.warnings", "()"}` — exact argument set
- `builders[0].args.kw_defaults[warnings_index] is None` — no default
- All `warnings` references are `ast.Load` — no write-back in helper body

Adding a third callsite immediately fails the test. This is the correct regression guard.

---

### F7 — [PASS] CLI stdout/stderr/exit behavior

**Code evidence** (`output.py:236-243`):
```python
if event.result.status is FinsResultStatus.SUCCESS:
    print(_fins_event_line(_FINS_EVENT_SUCCEEDED_PREFIX, event), file=effective_stdout)
    _print_terminal_business_summary(event.result, effective_stdout)
    for warning in event.result.warnings:
        print(warning.message, file=effective_stderr)
    return
```

**Behavior**:
- stdout: unchanged (title + business summary, same as before)
- stderr: each `warning.message` printed as a separate line
- exit code: unchanged (EXIT_SUCCESS = 0)

**Tests verified**:
- `test_fins_success_warning_preserves_stdout_and_writes_each_message_to_stderr` — baseline stdout == warned stdout; baseline stderr == ""; warned stderr == canonical message.
- `test_upload_terminal_summary_renderer_uses_typed_requested_and_stored_counts` — parametrized with/without warning, checks both streams.
- `test_fins_download_failure_projects_typed_rows_missing_periods_and_recovery` — failure path stderr contains typed failure details.

**No issue**: Warning does not alter stdout or exit code. Canonical message goes to stderr only.

---

### F8 — [PASS] Wait completed JSON — failed/cancelled have no warnings field, no inference

**Code evidence**:

- `_completed_result_value` (`fins_wait_adapter.py:578-583`): adds `warnings` to completed value.
- `_failed_outcome` (`fins_wait_adapter.py:496-505`): uses `_failure_message` which serializes `failure.safe_message` — no warnings field.
- `_cancelled_outcome` (`fins_wait_adapter.py:517-525`): uses `ToolCancelledOutcome` — no warnings field.

**Tests verified**:
- `test_fins_wait_adapter_projects_completed_warning_exactly` — completed value has `warnings: [warning.to_json()]`.
- `test_fins_wait_poll_adapter_maps_observation_statuses` — `value["warnings"] == []` for download (no warning); `"warnings" not in failed_poll.outcome.result.message`; `"warnings" not in cancelled_poll.outcome.result.message`.

**Assessment**: The LLM-facing completed value includes `warnings` as a self-explanatory JSON array. Failed/cancelled outcomes do not include or infer warnings from error text. This matches the amendment contract.

**LLM-facing self-containment**: The `warnings` array contains `{"kind": "company_name_ignored", "message": "本次提交的公司名称未生效；已保留现有公司名称。请核对上传目标公司是否正确。"}`. Both fields are business-readable. No internal terminology (`event_id`, `payload_ref`, `digest`, cursor, etc.) is exposed.

---

### F9 — [PASS] Durable re-read — same object/value semantics

**Code evidence** (`ingestion_runtime.py:1931`):
```python
"warnings": company_metadata_warnings_to_json(self.warnings),
```

**Test**: `test_accepted_upload_terminal_store_rejects_mismatch_and_preserves_existing_fields` — saves summary with warning, re-reads, asserts `saved.result_summary["warnings"] == [_company_name_ignored_warning().to_json()]`.

**Test**: `test_upload_summary_json_always_contains_warnings_array` — empty warnings serializes as `[]` (not absent).

**Assessment**: The `to_json_summary` always includes the `warnings` key with a JSON array value. Empty state is `[]`, not `null` or missing. Re-read preserves exact JSON shape. No inference or re-derivation occurs.

---

### F10 — [PASS] Tests are real red tests, not fake bypasses

**Analysis of each test file**:

- `test_fins_direct_stream.py`: Tests `FinsResultSummary` public invariant directly. Uses real constructor, not mocked. Tests exact type rejection (cast to non-precise type), at-most-one rejection, FAILURE/CANCELLED rejection. These are genuine contract tests.

- `test_fins_ingestion_runtime.py`: Uses `_FakeUploadRunner` that returns a real `FinsUploadResultSummary` with the tested warning. The `_build_ingestion_runtime` helper creates a real `FinsIngestionRuntime` instance. The direct stream tests run the actual async generator and collect real events. The AST test parses the real production source file. The durable save/re-read test uses the real `FinsIngestionJobStore`.

- `test_fins_service_runtime.py`: Tests `_upload_summary_from_result` with a real `FinsUploadPipelineResult` and real `FinsUploadFilingRequest`. Asserts `summary.warnings is result.warnings` (identity, not just equality).

- `test_output.py`: Tests `render_fins_direct_event` with real `FinsEvent`/`FinsResultSummary` objects. Captures real stdout/stderr.

- `test_fins_commands.py`: Uses mocked direct stream but constructs real `FinsUploadResultSummary` with warnings. Tests the full CLI renderer path.

- `test_fins_wait_adapter.py`: Uses `_FakeObservationRuntime` but constructs real `FinsResultSummary` with warnings. Tests the real `FinsIngestionWaitPollAdapter.poll_wait` method.

**No fake bypassing owner**: All tests construct the typed warning through `CompanyMetadataWarning(kind=..., message=...)` and assert the same object/value flows through each layer. No test constructs warnings from raw strings, JSON, or internal fields.

---

### F11 — [PASS] README accuracy

**README.md** (user-facing):
- "已有且仍新鲜的公司信息不会被单次 filing 上传改名" — accurate, matches S1+S2 behavior.
- "若本次填写的公司名称未被采用，命令仍按成功或跳过结果退出 `0`，stdout 摘要保持不变，并在 stderr 提示核对上传目标公司" — accurate, matches CLI implementation.
- "合法的新别名即使 filing 内容因完全相同而跳过，也会与公司信息原子保存" — accurate, matches skip-with-preserve-intent behavior.

**dayu/fins/README.md** (developer-facing):
- Updated skip state machine description to reflect preserve-intent skip behavior — matches publication owner implementation.
- Updated company meta section to reflect `CompanyMetaCommitOutcome` and publication-final warning owner — accurate.
- "SEC/CN/HK 下载 producer 也提交同一 intent contract，但不获得 upload warning 语义" — accurate, verified by zero diff in download paths.

**tests/README.md**:
- Updated test matrix to include all S3 test files — accurate.
- Coverage description matches actual test assertions.

---

### F12 — [PASS] Docstring / types / pyright

**Docstring coverage**: All modified functions have complete Chinese docstrings with Args/Returns/Raises. New `warnings` parameter documented in all signatures.

**Type annotations**: All new fields have explicit type annotations. `tuple[CompanyMetadataWarning, ...]` is precise. No `Any`, `object`, or untyped parameters.

**Pyright**: 0 errors, 0 warnings, 0 informations on all 5 modified production files.

---

### F13 — [PASS] Host/Engine/material/oracle frozen boundary

**Evidence**: `git diff --name-only` shows only the 14 allowed files. No changes to `dayu/host/`, `dayu/engine/`, `dayu/fins/storage/`, `dayu/runtime/`, or any oracle/scenario/registry files.

The `_observation_failure_result`, `_observation_cancelled_result`, `_mark_observation_failed` functions have zero diff (verified by grep). These are non-SUCCESS observation construction points that naturally use `FinsResultSummary.warnings=()`.

---

### F14 — [PASS] Coverage evidence

**Branch coverage** (from artifact):
- `ingestion_runtime.py`: 89%
- `service_runtime.py`: 88%
- `direct_events.py`: 83%
- `output.py`: 82%
- `fins_wait_adapter.py`: 91%

All above 80% threshold. The artifact notes that `output.py` initially hit 78% and was raised to 82% by adding a typed download failure renderer test — this is legitimate coverage improvement, not gaming.

---

### F15 — [INFO] `company_metadata_warnings_to_json` enforces at-most-one and exact type at serialization boundary

**Code evidence** (`company_metadata_warning.py:155-161`):
```python
if len(warnings) > 1:
    raise ValueError("company metadata warnings 最多允许一个元素")
if any(type(warning) is not CompanyMetadataWarning for warning in warnings):
    raise TypeError("warnings 元素必须是 CompanyMetadataWarning")
```

**Assessment**: This is a third enforcement layer (after `FinsResultSummary.__post_init__` and `FinsUploadResultSummary.__post_init__`). It ensures that even if a caller bypasses the dataclass constructors and calls `company_metadata_warnings_to_json` directly with invalid data, it will fail closed. This is defense-in-depth, not redundancy — each layer guards a different boundary (public contract, runtime summary, serialization).

---

## Open questions

None. All design decisions from the amendment are correctly implemented.

---

## Residual risks

### Accepted tradeoffs (no action needed)

1. Warning collection is at-most-one. This is a frozen business closed set for company-name-ignored. Not a general warning framework.
2. `FinsResultSummary.warnings=()` default covers download/preprocess paths that don't carry company metadata warnings. The producer helper has no default, so every upload/generic producer must explicitly declare the fact.
3. Branch coverage misses belong to non-S3 branches in the modified files.

### Assigned to later work units (not in scope)

1. Name-only metadata batch writer lock / physical swap cost.
2. Material upload company-name behavior.
3. Real CLI/network/scenario/oracle/frozen evidence.
4. Post-commit guard-release/cleanup error visibility.

---

## Adversarial analysis

### Failure path: upload pipeline returns failed status with warning

- `FinsUploadPipelineResult.__post_init__` rejects: `ValueError("只有 ok/skipped upload pipeline result 可携带 warning")`.
- `FinsUploadResultSummary.__post_init__` would also reject if somehow reached.
- `FinsResultSummary.__post_init__` would also reject for non-SUCCESS.
- Triple defense. No path to corrupt state.

### Cancel path: direct stream cancelled mid-upload

- `_emit_direct_cancelled_result` calls `_emit_direct_result` with `warnings=()` (hardcoded in `_emit_claimed_direct_result`).
- `_direct_upload_terminal_events` with CANCELLED disposition passes `summary.warnings` which is empty (enforced by summary invariant).
- `FinsResultSummary(status=CANCELLED, warnings=())` passes constructor.

### Rollback path: publication batch rollback after skip-with-preserve-intent

- S3 does not modify publication owner code. The README accurately describes the new skip-with-preserve-intent behavior from S1+S2.
- The warning is produced by the commit owner (S1+S2), not by S3's projection layer.

### Kill path: process killed mid-direct-stream

- No new kill-handling code in S3. The existing direct stream infrastructure handles producer death via queue exhaustion detection.
- Warnings are in-memory tuples that don't survive process death. This is expected — warnings are transient projection, not durable state.

### Concurrency: multiple uploads to same ticker

- Each upload gets its own `FinsIngestionRuntime` instance and `_FinsIngestionExecutionContext`.
- The publication owner (S1+S2) handles per-ticker writer reservation and fresh view serialization.
- S3's warning projection is purely mechanical copy within a single upload's execution context.

### Semantic owner drift

- `CompanyMetadataWarning` owner: `dayu.fins.company_metadata_warning` — zero diff in S3.
- `FinsUploadPipelineResult.warnings` owner: `ingestion_runtime.py` — added in S1+S2, zero diff in S3.
- `FinsUploadResultSummary.warnings` owner: `ingestion_runtime.py` — new field in S3, validated by `__post_init__`.
- `FinsResultSummary.warnings` owner: `direct_events.py` — new field in S3, validated by `__post_init__`.
- Service/direct/CLI/wait are mechanical copy points — no semantic ownership, just propagation.

No owner drift detected. Each semantic fact has a single clear owner.

---

## Verdict

**PASS**

All findings are LOW/INFO severity. No blocker, no medium, no high. The implementation correctly follows the accepted amendment:
- Warning flows mechanically from commit owner through runtime summary, durable JSON, direct public result, CLI, and completed wait projection.
- Each layer enforces the same contract independently (exact type, at-most-one, success-only).
- The direct builder has exactly two callsites with no default, guarded by AST regression.
- CLI preserves stdout/exit, writes warnings to stderr.
- Wait completed includes warnings; failed/cancelled do not.
- Tests are real contract tests, not fakes.
- READMEs are accurate.
- All frozen boundaries are respected.
- Pyright clean, coverage above threshold.

The implementation is ready for the next gate.
