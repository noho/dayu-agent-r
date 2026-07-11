# WU-SEMANTIC-OWNERSHIP-01 P3-I plan review controller adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P3-I - Public CLI/package entrypoints and terminal display watermark`
- Gate: plan review controller adjudication
- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-i-public-entrypoints-terminal-watermark-plan.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-i-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-i-plan-review-ds.md`

## Controller summary

Both reviewers accept the core plan direction:

- Restore minimal importable public entrypoints rather than deleting the public command surface.
- Keep Host / Service as the owner of terminal status facts.
- Move CLI cursor advancement to the CLI display-delivery boundary after terminal rendering returns.
- Use two implementation slices, which is within the control doc slice policy.

The reviews found specification gaps, not design blockers. A plan-fix gate is required before accepted plan commit.

## Findings disposition

| Finding | Disposition | Controller decision |
| --- | --- | --- |
| MiMo F1 / DS M-F3 - Cursor write failure policy is under-specified | accepted-with-modification | The plan must explicitly state that `advance_cli_terminal_cursor(...)` errors propagate as local CLI delivery persistence failures. The implementation must not catch and downgrade these errors to the stored render exit code. Returning the render exit code after a cursor write failure would hide a real local delivery-state failure and can make repeated display likely without an observable failure. The plan should record the trade-off: render already happened, cursor is not advanced, later reconnect may repeat the terminal, and the local cursor store uses atomic writes so corruption is not expected. |
| MiMo F2 / DS M-F1 - README narrowing scope is under-specified | accepted | The plan must add a concrete README target specification for `dayu-web`, `dayu-wechat`, and `dayu-render`, including which user workflows must be removed or narrowed when only import/help/current-capability diagnostics are restored. The implementation agent must not decide this editorial/product boundary from scratch. |
| MiMo F3 - `terminal is None` no-watermark invariant lacks explicit test | accepted | The plan must require at least one negative regression test proving local interrupt / `terminal is None` does not advance the cursor. |
| DS M-F2 - `dayu.render` package-data resource declaration not handled | accepted | The plan must explicitly record that S1 does not create render resource files and that existing `dayu.render` package-data globs remain a deferred render-capability resource risk unless implementation restores real render assets. The implementation must not fabricate resource files without real render behavior. |

## Required plan fixes

AgentCodex must update the plan artifact with these required fixes:

1. Add a per-command README narrowing checklist:
   - `dayu-web`: keep command/help and extras installation facts only if true; remove or explicitly mark unavailable any Streamlit server/workflow claims not implemented by the restored module.
   - `dayu-wechat`: keep command/help and current-capability diagnostic facts; remove or explicitly mark unavailable login/run/service/multi-instance workflows not implemented by the restored module.
   - `dayu-render`: keep command/help and current-capability diagnostic facts; remove or explicitly mark unavailable DOCX/HTML/PDF conversion claims unless a real renderer is implemented and tested in S1.
   - Require an `rg "dayu-web|dayu-wechat|dayu-render" README.md` audit after edits.
2. Add a `dayu.render` package-data residual / non-goal:
   - S1 must not create fake CSS/HTML/Lua/template files.
   - If real render behavior is not implemented, package-data resource completion remains a deferred render-capability risk.
3. Specify cursor write failure policy:
   - Render exceptions still prevent cursor advancement.
   - Cursor advancement happens after render returns.
   - Cursor write exceptions propagate as local CLI delivery persistence failures; they must not be swallowed or converted into Host terminal status.
   - The plan must record that repeated display after a cursor write failure is acceptable compared with silently hiding failed local persistence.
4. Add negative test requirement for `terminal is None`:
   - At minimum, extend or add a prompt SIGINT-before-run-id/local interrupt test that asserts the cursor record remains empty.

## Rejected suggestions

- MiMo's suggested implementation policy to catch `CliTerminalCursorError`, log it, and return the render exit code is rejected as stated. It optimizes exit-code preservation over surfacing local delivery-state persistence failure. The correct P3-I owner boundary is not only terminal-status projection; it is also the CLI display watermark. A failed watermark write is a real local delivery failure and should remain visible through existing command error handling.

## Next gate

Proceed to P3-I plan-fix by AgentCodex. After the plan fix, run plan re-review with AgentMiMo and AgentDS before accepted plan commit.
