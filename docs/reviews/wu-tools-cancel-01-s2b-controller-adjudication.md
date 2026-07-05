# WU-TOOLS-CANCEL-01 S2B Controller Adjudication

## Verdict

ACCEPTED.

S2B `Doc process-backed` 已通过 implementation、code review、fix 与 re-review gate。当前 controller 裁决 S2B 进入 accepted slice commit，下一步为 S2C `Fins read process-backed` implementation gate。

## Scope

- Work unit: `WU-TOOLS-CANCEL-01`
- Slice: S2B `Doc process-backed`
- Implementation artifact: `docs/reviews/wu-tools-cancel-01-s2b-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/wu-tools-cancel-01-s2b-code-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-s2b-code-review-ds.md`
- Fix artifact: `docs/reviews/wu-tools-cancel-01-s2b-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-cancel-01-s2b-rereview-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-s2b-rereview-ds.md`

## Accepted Findings

### F1 process-backed failed envelope hint

Decision: deferred-with-owner.

S2B did not modify Host process envelope contract because the accepted S2A contract defines process failed envelopes as `{status, error_type, message}`. AgentCodex added tests proving Doc process-backed failed messages preserve the original recovery hint text in `message`.

Owner / destination: S2E aggregate residual reconciliation, or a dedicated Host process envelope contract hardening follow-up if the project decides process-backed failed envelopes should carry structured `hint`.

### F2 real Doc process target cancel coverage

Decision: accepted and closed.

AgentCodex added a POSIX FIFO test that uses real `discover_tools(...)` definitions, production `DefaultToolRuntimeFactory`, and the real Doc `_DocProcessTargetFactory` / `_DocProcessTarget`. The child process blocks on `read_file` of a FIFO under the allowed root; parent cancellation returns governed `tool_runtime_cancelled` quickly and no late completed result is accepted.

### DS-03 argument validation failed envelope

Decision: accepted and closed.

AgentCodex added a process target invalid-arguments test for missing `file_path`, verifying `status=failed`, `error_type=invalid_argument`, and preservation of the recovery hint text inside `message`.

### Low findings

Decision: accepted and closed where changed; otherwise deferred as non-blocking.

- `_DocCancelledError` re-raise now has a comment explaining it is only for direct callable fallback; process-backed cancellation remains parent-owned.
- Dead local use of `timeout_seconds` inside `_DocProcessTarget.__call__` was removed.
- Generic exception envelope test was not required for this fix gate.

## FIFO Path Decision

Decision: accepted with residual risk.

S2B allows POSIX FIFO only for `read_file`, only after allowed-root containment and existence checks. This is a small production behavior broadening introduced to test a real blocking Doc process target deterministically. The controller accepts it because:

- the allowed-root safety boundary is unchanged;
- the behavior is limited to `read_file`;
- parent Host process-backed cancel / timeout governance bounds the blocking risk;
- both re-review agents judged it low risk and non-blocking.

Residual risk: FIFO is an IPC node, not a document file. If future security or product review rejects this semantic broadening, the follow-up owner is Doc process-backed test strategy hardening: replace the FIFO fixture with another deterministic real blocking fixture and remove FIFO support from `_is_supported_doc_file_path`.

## Controller Validation

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py -q`
  - `46 passed`
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q`
  - `55 passed`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed with no output

## Boundary Check

- No Engine public request, event, runner, or tool schema contract change.
- No durable schema or migration change.
- No Host public cancel API change.
- No `dayu.runtime.interruptible_process` return type change.
- No Fins / Web process-backed migration in this slice.
- Doc process targets do not capture provider locks, document processors, cancellation tokens, repositories, runtime/session objects, or Host internals.

## Next Gate

Proceed to S2C `Fins read process-backed` implementation gate. The next slice must migrate non-WAITING Fins read tools to process-backed execution through `ToolDefinition.execution`, reopen Fins runtime/storage inside the child process, and avoid crossing repository/runtime/processor cache objects across process boundaries.
