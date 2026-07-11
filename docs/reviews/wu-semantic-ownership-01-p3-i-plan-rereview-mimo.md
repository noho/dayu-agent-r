# WU-SEMANTIC-OWNERSHIP-01 P3-I Plan Re-Review (AgentMiMo)

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P3-I - Public CLI/package entrypoints and terminal display watermark`
- Gate: plan re-review (verify plan-fix closes accepted findings)
- Review target: `docs/host/wu-semantic-ownership-01-p3-i-public-entrypoints-terminal-watermark-plan.md`
- Fix report: `docs/reviews/wu-semantic-ownership-01-p3-i-plan-fix-codex.md`
- Original review: `docs/reviews/wu-semantic-ownership-01-p3-i-plan-review-mimo.md`
- Other review: `docs/reviews/wu-semantic-ownership-01-p3-i-plan-review-ds.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-i-plan-review-controller-adjudication.md`

## Posture

Re-review scope is strictly limited to verifying that accepted findings are closed in the plan-fix. No new architecture review, no style review, no implementation.

## Sources Read

- All five artifacts listed above (full)

## Accepted Findings Verification

### MiMo F1 / DS M-F3 — Cursor write failure policy

**Controller policy:** propagate cursor write exception as local delivery persistence failure; do not catch and return render exit code. Record trade-off: render already happened, cursor not advanced, reconnect may repeat terminal, atomic writes prevent corruption.

**Plan evidence:**

- `Public Contract And State Changes` 段: "If `advance_cli_terminal_cursor(...)` raises an existing local cursor persistence exception, propagate that exception as a local CLI delivery persistence failure. Do not swallow it, do not return the stored render exit code instead, and do not convert it into Host terminal status."
- S2 step 1: "If cursor advancement raises, let that local persistence exception propagate; do not return `render_exit_code` as if delivery-state persistence succeeded."
- S2 step 2: "If cursor advancement raises, stop the startup reconnect path by propagating that local persistence exception."
- S2 step 3: "If cursor advancement raises, propagate that local persistence exception."
- Risks And Residuals: "Cursor write failures after render remain local delivery persistence errors. This WU must not disguise them as Host terminal status changes, must not swallow them, and must not convert them into the renderer's stored exit code."

**Verdict: ✓ closed.** Policy is explicit, matches controller decision, and correctly rejects MiMo's original suggestion (catch + log + return render exit code).

### MiMo F2 / DS M-F1 — README narrowing per-command checklist and README audit

**Controller requirement:** concrete per-command README target specification; `rg` audit after edits.

**Plan evidence:**

- S1 step 9 现在包含 per-command checklist:
  - `dayu-web`: keep command/help + extras installation facts; delete or mark unavailable Streamlit server/workflow claims.
  - `dayu-wechat`: keep command/help + current-capability diagnostic; delete or mark unavailable login/run/service/multi-instance workflows.
  - `dayu-render`: keep command/help + current-capability diagnostic; delete or mark unavailable DOCX/HTML/PDF conversion claims unless real renderer is implemented.
- S1 step 9 明确要求 `rg "dayu-web|dayu-wechat|dayu-render" README.md` audit after edits。

**Verdict: ✓ closed.** Per-command checklist is concrete and actionable; audit requirement is explicit.

### MiMo F3 — terminal is None negative cursor test

**Controller requirement:** at least one negative regression test proving terminal is None does not advance cursor.

**Plan evidence:**

- S2 step 7: "At least one negative local-exit test must prove no cursor advancement happens when `terminal is None`; extend or add a prompt SIGINT-before-run-id or equivalent local interrupt test that asserts the cursor record remains empty."

**Verdict: ✓ closed.** Test requirement is explicit and concretely scoped.

### DS M-F2 — dayu.render package-data non-goal / residual

**Controller requirement:** S1 must not create fake resource files; package-data completion is deferred risk.

**Plan evidence:**

- Non-Goals 段: "S1 must not create fake `dayu.render` CSS, HTML, Lua, DOCX, XLSX, Mermaid, or template resource files only to satisfy package-data globs. If a real renderer is not implemented in S1, package-data resource completion remains deferred render-capability work."
- S1 Propagation Audit 段: "Deferred render resources: if S1 does not implement real render behavior, `dayu.render` package-data resource files are not fabricated and remain a named render-capability residual for the future renderer owner."
- Risks And Residuals 段: "S1 does not create fake `dayu.render` package-data resources. If real render behavior is not restored, completing CSS/HTML/Lua/template and conversion resource files remains deferred render-capability work."

**Verdict: ✓ closed.** Non-goal, propagation audit residual, and risks residual all present and consistent.

## New Material Blocker Check

The four fixes are declarative/specification-only. They do not change:

- Plan architecture or owner boundaries
- Slice structure or sequencing
- Public contract semantics
- Test matrix shape (only adds required negative test)

The cursor write failure policy correctly aligns with the controller's rejected suggestion boundary. No new coupling, boundary violations, or specification contradictions were introduced.

**New material blockers: none.**

## Plan Review Conclusion

**Verdict: pass**

All four accepted findings are closed with evidence in the plan artifact. No new material plan blockers. The plan is ready for accepted plan commit.

## Review Metadata

- Review artifact: `docs/reviews/wu-semantic-ownership-01-p3-i-plan-rereview-mimo.md`
- Verdict: pass
- Open findings: 0
- New findings: 0
