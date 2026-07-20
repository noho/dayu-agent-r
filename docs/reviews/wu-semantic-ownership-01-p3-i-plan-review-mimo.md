# WU-SEMANTIC-OWNERSHIP-01 P3-I Plan Review (AgentMiMo)

## Review Target

- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-i-public-entrypoints-terminal-watermark-plan.md`
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-I - Public CLI/package entrypoints and terminal display watermark`
- Gate: plan review

## Scope And Posture

Adversarial plan review. No code implementation, no plan modification, no commit/push/PR.

Review posture: default skeptical. Challenge motivation, scope, sequencing, hidden assumptions. Find failure modes, not style preferences.

## Sources Read

- `docs/host/wu-semantic-ownership-01-p3-i-public-entrypoints-terminal-watermark-plan.md` (review target)
- `docs/host/design.md` (partial, sections 1-3)
- `docs/engine/design.md` (full)
- `docs/host/issues-implementation-control.md` (grep for P3-I / terminal cursor / public entrypoint)
- `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md` (full)
- `docs/reviews/wu-semantic-ownership-01-p3-i-goal-confirmation.md` (full)
- `pyproject.toml` (full)
- `README.md` (sections 0-3, §6 render output, §7 config)
- `dayu/cli/session_execution.py` (full)
- `dayu/cli/session_terminal_cursor.py` (full)
- `tests/cli/test_prompt_command.py` (full)
- `tests/cli/test_interactive_command.py` (full)
- Code fact verification: `ls dayu/web/ dayu/wechat/ dayu/render/` confirms all three directories are absent.

## Assumptions Tested

1. **Public entrypoint modules are absent.** Verified: `ls dayu/web/ dayu/wechat/ dayu/render/` returns "No such file or directory" for all three.
2. **`pyproject.toml` declares the three console scripts.** Verified: lines 99-101.
3. **`pyproject.toml` has `dayu.render` package-data.** Verified: lines 127-134 declare CSS/HTML/Lua/DOCX/XLSX/MMD assets.
4. **README extensively documents all three commands.** Verified: `dayu-web` (§2.2, Streamlit-based Web UI), `dayu-wechat` (§2.3, login/service/run, ~50 lines of detailed usage), `dayu-render` (§6, format support, pandoc/chrome dependency).
5. **Current cursor advancement only on EXIT_SUCCESS.** Verified: `execute_prompt_on_session` line 374, `_run_existing_session_startup_reconnect` line 523-524, `_run_interactive_repl` line 854-855 all gate `advance_cli_terminal_cursor` on `render_exit_code == EXIT_SUCCESS`.
6. **`session_terminal_cursor.py` docstring says "已成功展示过的 terminal 水位".** Verified: line 3. The module owns workspace-local display delivery state.
7. **Host design says CLI cursor is downstream local delivery watermark.** Verified: plan line 37, consistent with `session_terminal_cursor.py` module docstring.
8. **Existing tests only verify SUCCEEDED cursor advancement.** Verified: `test_prompt_existing_session_execution_does_not_create_or_ensure` asserts cursor after SUCCEEDED; `test_interactive_existing_session_runs_startup_before_first_input` asserts cursor after SUCCEEDED startup + SUCCEEDED turn. No FAILED/CANCELLED/LOST cursor tests exist.
9. **Two slices is within control doc default.** Verified: goal confirmation says "one or two implementation slices; more than two slices requires explicit justification." Plan proposes exactly two.

## Findings

### 1-Unfixed-低-render/advance 重排序异常处理未规格化

- **位置**: Slice S2 Concrete Implementation Steps 1-3
- **问题类型**: 契约缺失
- **当前写法**: Plan says "After the render call returns, call `advance_cli_terminal_cursor(...)` unconditionally for that terminal" and "Once render returns without an output exception, call `advance_cli_terminal_cursor(...)`."
- **反例/失败场景**: `render_prompt_terminal_result` or `render_interactive_terminal_result` raises an exception (not returns non-zero). Under the plan's reordering, if render raises, cursor is not advanced (correct), but the exception propagates. In the startup reconnect path, if render returns EXIT_FAILURE but then `advance_cli_terminal_cursor` raises `CliTerminalCursorError`, the original render failure exit code is lost—the CLI shows a cursor-write error traceback instead of the render failure diagnostic.
- **为什么有问题**: The plan says "Cursor write failure handling must not mutate or reinterpret Host terminal status" (line 98), but does not specify whether `CliTerminalCursorError` should be caught to preserve the render exit code, or allowed to propagate as-is. This leaves an implementation agent to guess.
- **直接证据**: `session_terminal_cursor.py` line 125: `advance_cli_terminal_cursor` raises `CliTerminalCursorError` on write failure. `session_execution.py` currently does not catch this exception. Plan S2 step 1-3 reorders render and advance without specifying exception boundary.
- **影响**: Implementation agent may either silently swallow cursor errors (hiding delivery failures) or let them propagate (masking render exit codes). Both are plausible interpretations.
- **建议改法和验证点**: Plan should specify: "If `advance_cli_terminal_cursor` raises `CliTerminalCursorError`, log the cursor error and return the stored `render_exit_code`. Do not catch render exceptions for cursor advancement." This keeps cursor failure diagnostic visible while preserving render exit semantics.
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-Unfixed-低-README narrowing 范围未具体化

- **位置**: Slice S1 Concrete Implementation Steps 9, Expected Outcome line 119
- **问题类型**: 不可直接实施
- **当前写法**: "Narrow root README command sections to the behavior actually implemented in this slice." / "Public README no longer promises behavior that the restored modules do not provide."
- **反例/失败场景**: README §2.3 documents ~50 lines of WeChat login/service/run behavior including `service install`, `service start`, `service restart`, `service stop`, `service status`, `service list`, `service uninstall`, `--relogin`, multi-instance `--label` management, and environment variable snapshot semantics. §6 documents render to DOCX/HTML/PDF with pandoc/chrome dependencies. If the restored modules only provide `--help` + diagnostic, the README narrowing would need to delete or rewrite most of §2.3 and §6. An implementation agent may either narrow too aggressively (removing useful future reference) or too conservatively (leaving README promising unimplemented behavior).
- **为什么有问题**: The plan commits to README truth but does not define the target README state. The gap between "extensive documented behavior" and "minimal stub with diagnostic" is large enough that an implementation agent cannot deterministically produce the correct README.
- **直接证据**: README lines 349-700 (WeChat section), lines 1083-1108 (render section). These are not brief mentions; they are detailed user workflow documentation.
- **影响**: Implementation agent must make editorial judgment calls about which README content to keep, rewrite, or delete. Different agents will produce different README states, making review difficult.
- **建议改法和验证点**: Plan should add a concrete README target specification per command, e.g.: "For `dayu-web`: keep the section header and note that Web UI requires `[web]` extras; remove Streamlit-specific usage details. For `dayu-wechat`: keep the section header and note that WeChat integration is not yet available in this version; remove login/service/run details. For `dayu-render`: keep the section header and note that render requires `pandoc`; remove format-specific details until implementation provides real render behavior."
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-Unfixed-低-terminal is None 路径 cursor 不推进缺乏显式测试规格

- **位置**: Slice S2 Tests / Validation Commands
- **问题类型**: 测试缺口
- **当前写法**: Plan parametrizes FAILED/CANCELLED/LOST for prompt, interactive, and startup reconnect paths. Does not explicitly require a test for `terminal is None` → cursor not advanced.
- **反例/失败场景**: An implementation agent could mistakenly advance cursor before the `terminal is None` check, or in the SIGINT-returns-None path. Without an explicit test, this regression would not be caught.
- **为什么有问题**: The plan says "`terminal is None` local exits remain unwatermarked because no terminal was rendered" (line 97). This is a negative invariant that should be tested.
- **直接证据**: `execute_prompt_on_session` line 371: `if terminal is None: return EXIT_KEYBOARD_INTERRUPT`. The cursor call is after this check. `test_prompt_sigint_before_run_id_returns_local_interrupt` verifies the None return but does not assert cursor state.
- **影响**: Low. The `terminal is None` check is before the cursor call in current code, and the plan does not propose moving it. But without explicit test coverage, a future refactor could break this invariant silently.
- **建议改法和验证点**: Add one test to the S2 matrix: "prompt SIGINT before run-id returns EXIT_KEYBOARD_INTERRUPT and cursor remains at empty record."
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

None. All five review focus areas have been assessed with evidence.

## Residual Risks

1. **`dayu.render` package-data coexistence**: `pyproject.toml` declares `dayu.render` package-data (CSS/HTML/Lua/DOCX/XLSX/MMD). The new `dayu/render/__init__.py` must not interfere with setuptools package-data discovery. Risk is low if the new module is minimal and does not override `__path__` or package structure. Destination: implementation agent awareness.

2. **Console script install verification**: If console scripts are not installed in the local venv, `dayu-web --help` / `dayu-wechat --help` / `dayu-render --help` will fail. The plan addresses this (line 384-385) by requiring import/help tests as the primary verification, with console script smoke as optional. This is acceptable. Destination: plan residual risks section already covers this.

3. **`RUN_LOST` outbox availability**: The plan notes (line 386) that `RUN_LOST` may not always produce public outbox items per Host design. The S2 cursor fix only handles terminal results that Service/CLI already receives. This is correctly scoped. Destination: plan residual risks section already covers this.

## Plan Review Conclusion

**Verdict: pass-with-risks**

The plan is code-generation-ready for both slices. The semantic ownership boundaries are correct: CLI display delivery owns cursor advancement; Host/Service own terminal status facts. The two-slice structure is justified and within control doc limits. The test matrix covers the critical regression paths.

Three low-severity findings were identified:

1. **F1** (render/advance exception boundary): Plan should specify `CliTerminalCursorError` handling during the reordered advance-after-render flow. Without this, implementation agents may inconsistently handle cursor write failures.
2. **F2** (README narrowing scope): Plan should define concrete target README state per command. The gap between documented behavior and minimal stubs is too large for deterministic implementation.
3. **F3** (terminal=None cursor test): Plan should explicitly require one negative test for the `terminal is None` → no cursor advancement invariant.

None of these are blockers. F1 and F2 are specification gaps that could cause implementation variance; F3 is a test completeness improvement. The plan's core design is sound and the implementation sequencing is correct.

Review artifact: `docs/reviews/wu-semantic-ownership-01-p3-i-plan-review-mimo.md`
Verdict: pass-with-risks
Material findings: 3 (F1, F2, F3 — all low severity)
Open questions: none
