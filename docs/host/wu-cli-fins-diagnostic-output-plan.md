# WU-CLI-FINS-DIAG-01 Plan

## Gate Metadata

- Gate: plan
- Work unit: `WU-CLI-FINS-DIAG-01`
- Scope: close residuals `WU-CLI-FINS-OBS-01-R3` and `WU-CLI-FINS-OBS-01-R5`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Required outcome: code-generation-ready plan only
- Non-actions for this gate: no implementation, no commit, no push, no PR

## First-Principles Judgment

The work unit is valid.

`R3` and `R5` are not technically coupled by data dependency, state transition or contract dependency. They should be handled together because they are governed by the same CLI output policy and share implementation/review surfaces where coordinated test updates reduce avoidable churn:

- `R5` says stdout must be a stable command-result / user-UI channel, while diagnostic logs must move to stderr or an existing logging system.
- `R3` says diagnostic material became less useful because output/log policy over-generalized "sensitive" content; paths, document labels, provider diagnostic summaries and business summaries are not secrets by default.

The correct root cause is not missing activity UI, session management, durable jobs or sidecars. The direct code evidence points to CLI/log/output seams:

- `dayu/runtime/log.py` installs `logging.StreamHandler(stream=sys.stdout)` in `_build_marker_handler`, so all configured `dayu.*` diagnostic logs share stdout with command output.
- `dayu/cli/main.py` calls `runtime_log.set_level_from_flags(...)` without a CLI diagnostic stream policy; `argparse` already normalizes `--debug`, `--verbose`, `--quiet` into `args.log_level`, so this is not a flag parsing problem.
- `dayu/cli/output.py` currently redacts absolute paths in `_safe_text_value`; this treats path-like text as a secret rather than as bounded user-visible information.
- `dayu/cli/commands/fins.py` logs only `operation`, `event_type` and `result_status` in `_log_fins_direct_event_received`, although `FinsEvent` already carries bounded user/business diagnostic fields such as `message`, `document_label`, `progress`, `result` and `details`.
- `tests/cli/test_fins_commands.py` and `tests/runtime/test_log.py` currently assert verbose/debug logs in `captured.out`, which encodes the mixed-channel behavior.
- `dayu/README.md` says logs are diagnostic and do not carry UI output, audit truth, tool trace truth, EventLog canonical facts or projection checkpoints.

This is not `WU-CLI-ACTIVITY-01` because the goal is not a prompt/interactive activity stream, collapsible UI, hidden reasoning display, or final-answer activity decoration. It is not `WU-CLI-SESSION-01` because no session resume/list/purge semantics, `--new-session` removal, session label behavior or Host lifecycle transition is involved.

## Motivation and Success Signals

### R5 success signal

- CLI stdout contains only stable command result / user UI content.
- `--verbose` and `--debug` diagnostic logs from `dayu.*` go to stderr.
- Existing Fins progress and successful result UI still go to stdout.
- Fins failure, cancellation and local cancel notices still go to stderr as user-visible error/cancel output.
- Tests no longer assert diagnostic log lines in `captured.out`.
- The solution works through the central runtime log configuration path, so prompt, interactive and Fins commands share the same channel policy without per-command log plumbing.

### R3 success signal

- Fins direct UI output no longer redacts absolute file paths merely because they look like paths.
- User-visible Fins output remains bounded for size/readability.
- Fins verbose/debug logs include materially useful event summaries already present in `FinsEvent`: operation, event type, ticker, filing kind, document label, message, progress stage/counts, result status/title/error kind/exit code and bounded result details.
- No new diagnostic artifact is created.
- API key values from `dayu/config/models.json` references remain non-displayable; implementation must not add any path/document/business-summary redaction and must not log provider headers or resolved API key values.

## Design Alignment

Host design alignment:

- Respects `UI -> Service -> Host -> Engine`.
- CLI remains UI/entrypoint code; Fins direct commands continue consuming `dayu.service.fins_direct` `AsyncIterator[FinsEvent]`.
- No Host durable schema, EventLog, Tool Trace, projection, audit or recovery truth changes.
- No durable job, sidecar, cursor or Host Run is introduced for Fins direct operations.

Engine design alignment:

- Fins direct live events are not EngineEvent or Host event streams.
- Engine runner/provider diagnostic payload contracts are out of scope. Existing OpenAI-compatible runner diagnostic redaction and bounded raw payload behavior must not be rewritten in this work unit.

Runtime alignment:

- `dayu.runtime.log` is layer-neutral logging infrastructure. Moving its default diagnostic stream to stderr is a runtime policy fix, not CLI business logic.
- `dayu.runtime` must not import CLI, Service, Host, Engine, UI or Fins.

## Non-Goals and Scope Boundary

Non-goals:

- Do not implement prompt/interactive activity stream UI. That belongs to issue #144 / `WU-CLI-ACTIVITY-01`.
- Do not implement CLI session resume/list/purge or remove `--new-session`. That belongs to issue #145 / `WU-CLI-SESSION-01`.
- Do not add diagnostic artifacts.
- Do not modify Host durable schema, EventLog, Engine contract or Tool Trace contract.
- Do not convert Fins direct commands back to durable jobs or sidecars.
- Do not change Fins storage, repository protocols, ingestion runtime contracts or document processors.
- Do not rewrite Engine/OpenAI provider diagnostic payload redaction.
- Do not introduce a generic secret scanning framework.

Sensitive-data policy for this work unit:

- The only concrete secret class in scope is resolved API key values referenced by `dayu/config/models.json` `api_key_ref` and rendered provider headers.
- Paths, document labels, Fins event messages, provider diagnostic summaries and business summaries are not secrets by default.
- Display limits must be justified by volume, noise, copyright exposure or UI readability, not by treating these fields as secrets.

## Public Contract / Schema / State Changes

- No durable schema changes.
- No EventLog changes.
- No Engine event contract changes.
- No Tool Trace contract changes.
- No Fins direct stream contract changes.
- Runtime logging helper function signatures may gain an optional stream parameter; this is a local Python API change within the repository, not a durable/public data contract.
- CLI visible command flags do not change.

## Implementation Decisions

1. Logging channel separation:
   - Change `dayu.runtime.log.configure` and `set_level_from_flags` to support an optional diagnostic stream parameter typed as `TextIO | None`.
   - Default the runtime diagnostic stream to current `sys.stderr`, not `sys.stdout`.
   - Pass `stream=sys.stderr` explicitly from `dayu/cli/main.py` so CLI channel policy is visible at the composition root.
   - Code audit result for this plan: the current production call path is only CLI `main()` -> `runtime_log.set_level_from_flags(...)` -> `runtime_log.configure(...)`; no Host, Service or Engine production caller invokes `configure()` directly.
   - Keep the optional `stream` parameter so any future non-CLI caller can explicitly choose a different diagnostic stream.
   - Rename `_HANDLER_MARKER_VALUE` away from `stdout` to a stream-neutral private value such as `dayu.runtime.log:diagnostic`.
   - Do not add a logging sink registry, stream policy class, artifact writer or per-command logging configuration.
   - Do not add `args.debug`, `args.verbose` or `args.quiet` forwarding to `main()`: `dayu/cli/arg_parsing.py` already normalizes `--debug`, `--verbose`, `--info`, `--quiet` and `--silent` into `args.log_level`, and `main.py` already passes `log_level=args.log_level`. The boolean parameters on `set_level_from_flags` are legacy runtime-helper compatibility paths and are out of scope for this work unit.

2. Fins UI output policy:
   - In `dayu/cli/output.py`, remove absolute-path redaction from `_safe_text_value`.
   - Keep bounded display length and JSON string encoding.
   - Preserve stdout/stderr routing: progress and success to stdout; failure/cancel to stderr.
   - Rename docstrings and test names so they describe bounded display, not path redaction.

3. Fins direct event diagnostic logs:
   - In `dayu/cli/commands/fins.py`, enrich `_log_fins_direct_event_received`.
   - `VERBOSE` log should remain compact execution skeleton plus event summary: operation, event type, optional ticker, optional document label, optional progress stage, optional result status and bounded message.
   - `DEBUG` log should include deeper bounded fields: filing kind, progress completed/total units, result title, error kind, exit code, and a bounded details summary.
   - Use module-level private helpers and constants for bounded diagnostic rendering.
   - Log values must remain simple scalar logging arguments; do not pass unbounded event objects or raw payload dictionaries to logging.
   - Do not log resolved provider headers, API key values, full document text, full prompt, full tool result or large provider payload.

4. Tests follow the new boundary:
   - Update existing stdout log assertions to stderr assertions.
   - Add explicit regression tests proving stdout stays clean when verbose/debug logs are enabled.
   - Add tests proving absolute paths remain visible but bounded in Fins UI output.
   - Add tests proving enriched Fins diagnostics include document/message/progress/result/details summaries in stderr and do not include job ids, sequences or new artifact refs.

## Slices

### Slice 1: Runtime and CLI Log Stream Separation

Objective:

- Move Dayu diagnostic logs off stdout through the central runtime logging path.

Allowed files/modules:

- `dayu/runtime/log.py`
- `dayu/cli/main.py`
- `tests/runtime/test_log.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_fins_commands.py` only for assertions directly broken by log stream movement

Exact allowed changes:

- Add `stream: TextIO | None = None` to `configure`.
- Add `stream: TextIO | None = None` to `set_level_from_flags` and forward it to `configure`.
- `_build_marker_handler` accepts the resolved stream and uses `sys.stderr` when stream is `None`.
- `main()` passes `stream=sys.stderr`.
- Update tests so configured logs are asserted in stderr.
- Update or add a CLI-main-level test that a fake command can write stdout UI while runtime logs go to stderr.
- Add or update prompt/interactive command regression tests so `--verbose` and `--debug` do not put `[VERBOSE]` or `[DEBUG]` diagnostic log lines in stdout.

Non-goals:

- No CLI flag changes.
- No per-command log handlers.
- No root logger behavior changes beyond using the selected stream for marker handlers.

Validation:

```bash
source .venv/bin/activate && pytest tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q
source .venv/bin/activate && pyright dayu/runtime/log.py dayu/cli/main.py tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py
```

Expected assertions:

- `configure(level=LogLevel.INFO)` emits `dayu.*` logs to `captured.err`.
- `captured.out` is empty for pure diagnostic logging.
- `main()` passes the parsed log level and stderr stream to runtime log assembly.
- Prompt and interactive command tests prove `--verbose` and `--debug` keep diagnostic `[VERBOSE]` and `[DEBUG]` log lines out of stdout.

Stop conditions:

- Stop only if new code evidence contradicts the plan audit and shows an existing non-CLI production caller of `runtime_log.configure()` or `runtime_log.set_level_from_flags()` that explicitly requires stdout and cannot pass the optional stream parameter.
- Stop if a fix appears to require changing root logger propagation semantics.

### Slice 2: Fins UI Output Bounded Display Without Path Redaction

Objective:

- Stop treating paths as secrets in Fins direct user-visible output while preserving bounded, readable CLI lines.

Contract boundary:

- `FinsEvent` construction already rejects absolute paths in its LLM/user-visible text fields through `dayu/fins/direct_events.py` validation.
- `dayu/cli/output.py` path redaction is therefore a presentation-layer redundant defense for current Fins event rendering, not the contract layer that protects `FinsEvent` inputs.
- Do not modify `dayu/fins/direct_events.py` path validation for this work unit.
- `_safe_text_value` is private output rendering code for the current Fins path. If it is later reused for non-`FinsEvent` inputs, path-redaction needs must be re-evaluated against that new input boundary.

Allowed files/modules:

- `dayu/cli/output.py`
- `tests/cli/test_fins_commands.py`

Exact allowed changes:

- Remove `_ABSOLUTE_PATH_PATTERN`, `_FINS_REDACTED_TEXT`, `_looks_like_absolute_path` and `_redact_absolute_path_match` if no longer used.
- Make `_safe_text_value` only apply bounded truncation.
- Keep `_bounded_json_text` JSON encoding behavior.
- Replace `test_output_redacts_embedded_absolute_paths` with tests such as:
  - absolute POSIX paths remain visible;
  - absolute Windows paths remain visible;
  - long path/message text is truncated with the existing suffix;
  - Fins progress/success output still routes to stdout.

Non-goals:

- Do not add generic secret redaction to Fins output.
- Do not change Fins event field names or result rendering format except where test names/docstrings mention redaction.

Validation:

```bash
source .venv/bin/activate && pytest tests/cli/test_fins_commands.py -q
source .venv/bin/activate && pyright dayu/cli/output.py tests/cli/test_fins_commands.py
```

Expected assertions:

- `_safe_text_value("/tmp/a") == "/tmp/a"`.
- `_safe_text_value("path=/Users/a/b") == "path=/Users/a/b"`.
- Long values still end with the existing truncation suffix and fit the configured maximum length.

Stop conditions:

- Stop if existing Fins direct events can contain resolved provider API key values or provider headers in user-visible message/detail fields; that would require a separate upstream data-boundary fix rather than path redaction.

### Slice 3: Fins Direct Diagnostic Event Summaries

Objective:

- Make verbose/debug diagnostics useful enough to troubleshoot Fins direct operations without adding artifacts or exposing unbounded payloads.

Allowed files/modules:

- `dayu/cli/commands/fins.py`
- `tests/cli/test_fins_commands.py`

Exact allowed changes:

- Extend `_log_fins_direct_event_received(event)`.
- Add private constants for maximum diagnostic field/detail length and detail count.
- Add private helpers to render optional scalar fields and result details into bounded strings.
- `VERBOSE` log includes operation, event type, ticker, document, progress stage, result status and message when present.
- `DEBUG` log includes operation, event type, filing kind, progress completed/total units, result title, error kind, exit code and bounded details.
- Preserve existing no-job semantics: no `job_id`, no `sequence`, no durable cursor, no artifact ref.

Non-goals:

- Do not change `FinsEvent` contract.
- Do not change Service/Fins direct stream call paths.
- Do not log entire `FinsEvent` objects or result dataclass representations.

Validation:

```bash
source .venv/bin/activate && pytest tests/cli/test_fins_commands.py -q
source .venv/bin/activate && pyright dayu/cli/commands/fins.py tests/cli/test_fins_commands.py
```

Expected assertions:

- Default INFO still does not emit Fins diagnostic log lines.
- `--verbose` emits event summaries to `captured.err`, not `captured.out`.
- `--debug` emits detail summaries to `captured.err`, not `captured.out`.
- Diagnostics include `message`, `document`, `stage`, `status` and representative result details from test `FinsEvent`.
- Diagnostics do not include `job_id=`, `sequence=` or new artifact identifiers.

Stop conditions:

- Stop if making useful diagnostics requires adding a new artifact, changing Tool Trace, changing Engine events, changing Host EventLog or changing Fins direct stream contract.

### Slice 4: Documentation and Control Closeout

Objective:

- Keep stable docs aligned only where implementation changes hit documented responsibilities.

Allowed files/modules:

- `dayu/README.md`
- `tests/README.md`
- `docs/host/issues-implementation-control.md`
- `docs/reviews/*` implementation/review artifacts only if the implementation gate proceeds later

Exact allowed changes:

- Before editing `dayu/README.md` or `tests/README.md`, read each file's `Agent更新约束【必须遵守】` section or equivalent.
- Update `dayu/README.md` only if the existing logging section needs to explicitly say CLI/runtime diagnostic logs use stderr and stdout remains command-result/UI.
- Update `tests/README.md` only if new/changed tests fall within its documented update scope.
- Update `docs/host/issues-implementation-control.md` only at implementation closeout to mark `WU-CLI-FINS-OBS-01-R3` and `WU-CLI-FINS-OBS-01-R5` as closed or reclassified with evidence.

Non-goals:

- Do not rewrite Host/Engine design truth for this WU.
- Do not create or update GitHub Issues.

Validation:

```bash
source .venv/bin/activate && pytest tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py -q
source .venv/bin/activate && pyright dayu/runtime/log.py dayu/cli/main.py dayu/cli/output.py dayu/cli/commands/fins.py tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py
```

Expected assertions:

- Docs describe actual implemented behavior only.
- Control doc residual state matches implementation evidence.

Stop conditions:

- Stop if README update would require changing design truth beyond CLI/runtime logging channel language.

## Aggregate Validation

Minimum validation after all slices:

```bash
source .venv/bin/activate && pytest tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py -q
source .venv/bin/activate && pyright dayu/runtime/log.py dayu/cli/main.py dayu/cli/output.py dayu/cli/commands/fins.py tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py
```

Required stdout cleanliness checks:

```bash
source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py -q
```

Expected assertions:

- Prompt and interactive stdout stay free of `[VERBOSE]` and `[DEBUG]` diagnostic log lines under `--verbose` and `--debug`.
- Fins stdout remains user-visible progress/success output only; verbose/debug diagnostics are asserted in stderr.

README trigger checks:

- `dayu/runtime/log.py` and `dayu/cli/*` changes may affect the cross-package logging contract; check `dayu/README.md`.
- `tests/*` changes trigger `tests/README.md` check.
- No `dayu/engine/`, `dayu/host/`, `dayu/fins/` or `dayu/config/` production code change is planned; their README files should not be mechanically edited.

## Why This Is Not Over-Designed

- The plan changes the existing central logging assembly instead of adding a new logging framework.
- It reuses stdout/stderr and stdlib logging rather than adding diagnostic artifacts.
- It enriches existing `FinsEvent` logs from fields already present in the contract rather than adding new event fields.
- It removes over-broad redaction instead of replacing it with a larger secret policy engine.
- It keeps Fins direct as an `AsyncIterator[FinsEvent]` and does not introduce durable jobs, sidecars, cursors or Host runs.

## Residual Risks

- Existing Engine/OpenAI provider diagnostic redaction remains broader than the current R3 user裁决. This is intentionally out of scope because changing it would touch Engine provider diagnostic payload contracts and tests.
- Fins event messages/details are assumed not to contain resolved provider API key values. If code evidence disproves this, implementation must stop and fix the upstream data boundary or escalate to controller裁决.
- Current code audit found no Host, Service or Engine production caller of `dayu.runtime.log.configure`; the only production path is CLI `main()` -> `set_level_from_flags()` -> `configure()`. Repository tests should be updated to the new diagnostic convention; future non-CLI production callers that truly require stdout should pass `stream=sys.stdout` explicitly.
- Prompt/interactive activity readability remains assigned to issue #144; this WU only prevents diagnostic logs from polluting stdout.
- Session lifecycle UX remains assigned to issue #145.

## Controller Questions

No blocking architecture question is required for this plan.

Controller裁决建议:

- Accept `WU-CLI-FINS-DIAG-01` as the work unit name.
- Accept stderr as the default runtime/CLI diagnostic log stream.
- Accept removal of path redaction in Fins direct UI output.
- Accept that Engine/provider diagnostic redaction is out of scope for this WU.

## Completion Report Format

Implementation closeout should report:

- Changed files by slice.
- R3 success evidence.
- R5 success evidence.
- Tests and pyright commands run, with results.
- README/control-doc decisions.
- Remaining residual risks and their owner/destination.
