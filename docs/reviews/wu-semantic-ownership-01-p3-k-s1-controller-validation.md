# WU-SEMANTIC-OWNERSHIP-01 P3-K S1 Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub work unit: `P3-K - Test harness semantic coupling cleanup`
- Slice: `S1 - Owner-Level Contract Assertions`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-k-s1-implementation-codex.md`
- Accepted plan commit: `8515364a`

## Changed Scope

- `tests/host/test_memory_projection.py`
- `tests/contracts/test_tool_result_envelope.py`
- `tests/host/test_run_input_builder.py`

No production files, S2 raw SQL helpers, S3 cancellation / compaction fakes, or README files were changed.

## Controller Validation

- `source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/contracts/test_tool_result_envelope.py tests/host/test_run_input_builder.py -q`
  - Result: `166 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed
- Source scan:
  - `rg -n '_POLICY_FIELDS|_SNAPSHOT_FIELDS|tuple\(field\.name for field in fields\(MemoryProjectionPolicy\)\)|tuple\(field\.name for field in fields\(ConversationMemorySnapshotVNext\)\)|vague|keyword|模糊' tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/contracts/test_tool_result_envelope.py`
  - Result: no matches.

## Propagation Audit

- Memory projection policy / snapshot:
  - Owner: `dayu.host.memory`.
  - Test assertion boundary: required owner-level fields plus owner helper behavior (`default_memory_projection_policy`, policy JSON, digest, empty snapshot build, snapshot JSON round-trip).
  - Result: tests no longer act as exact ordered dataclass field registry.
- Tool result envelope:
  - Owner: `dayu.contracts.tool_result`.
  - Test assertion boundary: required result fields and forbidden awaiting fields.
  - Result: tests keep public discriminant / awaiting exclusion coverage without closed field-set ownership.
- Resume wait guidance:
  - Owner: `dayu.host.run_input`.
  - Test assertion boundary: file-local `_assert_resume_guidance_semantics(...)` distinguishes production-owned guidance lines from dynamic tool/status/result facts and preserves internal-leakage negative checks.
  - Result: scattered prose assertions are centralized without vague keyword matching.

## README Decision

`tests/README.md` update constraints were checked by AgentCodex. This slice adds only a file-local private helper and changes assertion style; it does not add a shared test helper convention, a new test layer, a new running pattern, or a reusable maintenance rule. `tests/README.md: no update needed`.

## Residual Risk

- None blocking for S1.
- S2 raw SQL helper coupling and S3 fake/protocol consolidation remain intentionally untouched and are assigned to later P3-K slices.
