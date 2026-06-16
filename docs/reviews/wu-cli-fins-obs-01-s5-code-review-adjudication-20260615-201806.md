# WU-CLI-FINS-OBS-01 Slice S5 Code Review Adjudication

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: S5 CLI logging assembly and command UI/log audit
- Reviewed implementation: `docs/reviews/wu-cli-fins-obs-01-s5-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/code-review-20260615-201047.md`
  - `docs/reviews/code-review-20260615-201327.md`
- Decision time: 2026-06-15 20:18:06 Asia/Shanghai

## Review Conclusion

Both review agents returned `PASS-WITH-FINDINGS`. The findings are low severity and do not require design-source changes, but they are accepted for this slice because they are directly tied to the project coding constraints and S5 observability quality bar.

## Accepted Findings

### S5-FIX-01 Shared logging helpers

- Source findings: MiMo 01; DS S5-F02
- Decision: accepted
- Required fix:
  - Move the layer-neutral logging helpers/constants used by both CLI and Service into `dayu.runtime.log`.
  - The helper must keep the module-specific logger at the call site; it may accept a `logging.Logger` argument.
  - The payload-key helper must continue to expose only bounded payload keys, never payload values.
  - Remove duplicated local helper implementations and duplicated constants from `dayu/cli/commands/fins.py` and `dayu/service/fins_direct.py`.
- Rationale:
  - This is a pure runtime logging utility and belongs in the layer-neutral `dayu.runtime` package.
  - Keeping two copies conflicts with the project rule that duplicated logic must be extracted.

### S5-FIX-02 Avoid duplicate ERROR logs for one exception

- Source findings: MiMo 02; DS S5-F01
- Decision: accepted
- Required fix:
  - Keep Service as the ERROR log truth source for event-stream and cancel-request failures.
  - Remove or downgrade CLI-layer exception logs in `_consume_fins_direct_events` and `_wait_for_terminal_handling_sigint` so one root cause does not produce duplicate ERROR tracebacks.
  - Do not change exception propagation, terminal handling, cancel semantics, or user-facing error rendering.
- Rationale:
  - CLI is the UI adapter and already renders user-facing errors at the outer command boundary.
  - Service has the root failure context and should own the internal ERROR diagnostic.

### S5-FIX-03 Direct default log-level coverage

- Source finding: MiMo 03
- Decision: accepted
- Required fix:
  - Extend CLI main log assembly spy coverage to include the no-flag default case.
  - The test must directly prove `runtime_log.set_level_from_flags` is invoked with the parser-normalized default log level.
- Rationale:
  - The current default Fins test proves verbose diagnostics do not pollute progress output, but it does not directly prove CLI main configured runtime logging.

## Rejected Findings

None.

## Deferred Risks

- Prompt / interactive token or content streaming remains outside S5 by accepted plan scope.
- Runtime log handler timing and stdout handler assumptions remain low residual risks for later runtime-log documentation or cleanup; they do not block S5 because current CLI main configures runtime logging immediately after argument parsing.

## Required Validation

After the fix, run:

```bash
source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py -q
source .venv/bin/activate && python -m pyright dayu/runtime/log.py dayu/cli/main.py dayu/cli/commands/fins.py dayu/service/fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py
git diff --check
```
