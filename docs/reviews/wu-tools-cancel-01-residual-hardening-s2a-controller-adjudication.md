# WU-TOOLS-CANCEL-01 Residual Hardening S2A Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-CANCEL-01`
- Gate: implementation / code review / fix / re-review
- Slice: S2A `Runtime Process Group Cleanup Primitive`
- Branch: `phase/wu-tools-cancel-01`
- PR: draft/open `#170`

## Evidence

- Implementation artifact: `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-implementation-codex.md`
- Initial code review:
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-code-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-code-review-ds.md`
- Targeted re-review:
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-rereview-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-rereview-ds.md`

## Findings Adjudication

| Finding | Source | Decision | Rationale |
|---|---|---|---|
| Raw process S2B handoff missed session setup dependency | AgentDS 01 | fixed | Runtime now exports `enter_new_process_session_if_supported()` and `interrupt_multiprocessing_process(...)` documents that raw child entrypoints must call it, or equivalent POSIX setup, before spawning nested children. |
| pgid failure / unsafe branches had insufficient tests | AgentDS 02 | fixed | Runtime tests now cover `CHILD_PID_UNAVAILABLE`, `CHILD_ALREADY_EXITED`, `CURRENT_PGID_UNAVAILABLE`, `PARENT_PGID_UNAVAILABLE`, `PGID_MATCHES_PARENT_PROCESS_GROUP`, `GROUP_SIGNAL_FAILED`, and direct-signal `OSError` handling. |
| Direct-child signal exception handling was narrower than group signal handling | AgentDS 03 | fixed | Direct child signal now catches `OSError` as well as `ProcessLookupError`, records `direct_signal_sent=False`, and continues group diagnostic / join. |
| Unstarted raw process path lacked structured handling | AgentMiMo S2A-F01 | fixed | PID-unavailable raw process cleanup now returns `CHILD_PID_UNAVAILABLE` without signal or join. |
| `ProcessInterruptResult` docstring missed cleanup field | AgentMiMo S2A-F02 | fixed | The cleanup field is documented. |
| Successful pgid lookup baseline reason was semantically premature | AgentMiMo S2A-F03 | fixed | Safe lookup baseline uses `NOT_REQUESTED`; final cleanup result changes to `GROUP_SIGNALED` only after `os.killpg` succeeds. |

## Controller Decision

S2A is accepted for slice commit.

S2A provides a layer-neutral runtime primitive for interrupting a raw `multiprocessing.Process` and, on POSIX, safely signaling its child process group only after confirming the child pgid is available and differs from the caller/current and caller-parent process groups. Unsupported, unavailable, unsafe, and failed group-signal paths return explicit diagnostics instead of over-claiming nested cleanup.

S2A also exports the child-entry setup helper required by later raw-process users: `enter_new_process_session_if_supported()`. S2B must call this helper, or equivalent POSIX setup, inside the Playwright worker child before nested browser processes are created; otherwise S2B may only claim direct-child fallback.

## Residual Risk

- S2B still owns Web raw process integration, Playwright synthetic cleanup smoke, and any optional/manual real browser evidence.
- S3 still owns concrete Doc / Fins / Web envelope helper migration and the AAPL XBRL fixture breadth.
- PID / PGID reuse race remains a POSIX signal limitation. S2A mitigates available safety checks but does not claim cgroup / namespace-level isolation.
