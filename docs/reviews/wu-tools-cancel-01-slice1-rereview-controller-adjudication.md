# WU-TOOLS-CANCEL-01 Slice S1 Re-Review Controller Adjudication

## Scope

- Work unit: WU-TOOLS-CANCEL-01 Tool/provider blocking I/O cancellation hardening
- Slice: WU-TOOLS-CANCEL-01-S1 interrupt capsule + local worker cleanup
- Gate: code re-review
- Fix artifact: `docs/reviews/wu-tools-cancel-01-slice1-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-cancel-01-slice1-rereview-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-slice1-rereview-ds.md`

## Verdict

Accepted. Slice S1 is ready for accepted slice commit.

## Evidence

- AgentMiMo verdict: pass; blocking findings: 0; all 5 accepted findings closed.
- AgentDS verdict: pass; blocking findings: 0; all 5 accepted findings closed.
- Both reviewers verified:
  - outer `CancelledError` now interrupts and closes the capsule before re-raising;
  - ToolRuntime executor-level terminate -> kill escalation is tested with a SIGTERM-ignoring process target;
  - local worker background close task failures are logged with worker id, cancel reason, and error type;
  - `capsule.close()` failures no longer hide governed cancel / timeout outcomes;
  - `_run_process_target(...)` catches `Exception`, not `BaseException`;
  - no `dayu.contracts`, Engine contract, durable schema, EventLog, public Host cancel API, or S2 production tool migration was introduced.

## Residual Risks

- S2 still must migrate production Doc / Fins / Web blocking paths to process-backed or request-abort-capable adapters before issue-87 closeout.
- `thread_backed` remains explicitly non-production-grade for non-cooperative blocking hard interrupt.
- AgentDS noted a very early synthetic outer-cancel timing where process-backed `terminate()` could run before the process handle starts. This was not considered production-reachable in current Host cancel propagation and is not blocking S1 acceptance, but S2 / aggregate review should keep it in mind if cancellation timing changes.
- AgentDS also noted that unexpected low-level `terminate()` / `kill()` exceptions could still skip later cleanup. Current helper implementations are best-effort and return structured results, so this is not blocking S1 acceptance.

## Next Gate

Proceed to accepted slice commit for S1. After commit, continue to the next implementation slice.
