# WU-CLI-SMOKE-01 AgentCodex Auto Validation

## Gate

- Work unit: `WU-CLI-SMOKE-01 dayu-cli Core Usability Smoke and Behavior Validation`
- Gate: plan
- Runner: AgentCodex
- Date: 2026-07-06
- Raw artifact directory: `workspace/tmp/wu-cli-smoke-01-auto/`
- Fresh workspace: `workspace/tmp/wu-cli-smoke-01-auto/fresh-workspace/`

## Summary

Automatable real-environment CLI validation was run with `source .venv/bin/activate`. Help surface, fresh init, public awaiting smoke, Fins direct low-risk validation, and focused regression tests passed. A reproducible PTY probe found a high-priority interactive behavior failure: after `dayu-cli interactive` reaches the idle `dayu>` input prompt, one Ctrl+C exits the process.

This failure matches the user concern for generic Agent terminal UX. It is input-state behavior, not yet evidence that the running Host cancel path is broken.

## Command Records

Full command metadata is in `workspace/tmp/wu-cli-smoke-01-auto/command-records.json`.

| ID | Command | Exit | Decision | Raw output / log |
|---|---:|---:|---|---|
| AUTO-01a | `source .venv/bin/activate && dayu-cli --help` | 0 | pass | `help-01.stdout.txt`, `help-01.stderr.txt` |
| AUTO-01b | `source .venv/bin/activate && dayu-cli init --help` | 0 | pass | `help-02.stdout.txt`, `help-02.stderr.txt` |
| AUTO-01c | `source .venv/bin/activate && dayu-cli prompt --help` | 0 | pass | `help-03.stdout.txt`, `help-03.stderr.txt` |
| AUTO-01d | `source .venv/bin/activate && dayu-cli interactive --help` | 0 | pass | `help-04.stdout.txt`, `help-04.stderr.txt` |
| AUTO-01e | `source .venv/bin/activate && dayu-cli session --help` | 0 | pass | `help-05.stdout.txt`, `help-05.stderr.txt` |
| AUTO-01f | `source .venv/bin/activate && dayu-cli download --help` | 0 | pass | `help-06.stdout.txt`, `help-06.stderr.txt` |
| AUTO-01g | `source .venv/bin/activate && dayu-cli upload_filing --help` | 0 | pass | `help-07.stdout.txt`, `help-07.stderr.txt` |
| AUTO-01h | `source .venv/bin/activate && dayu-cli upload_material --help` | 0 | pass | `help-08.stdout.txt`, `help-08.stderr.txt` |
| AUTO-01i | `source .venv/bin/activate && dayu-cli upload_filings_from --help` | 0 | pass | `help-09.stdout.txt`, `help-09.stderr.txt` |
| AUTO-01j | `source .venv/bin/activate && dayu-cli process --help` | 0 | pass | `help-10.stdout.txt`, `help-10.stderr.txt` |
| AUTO-01k | `source .venv/bin/activate && dayu-cli process_filing --help` | 0 | pass | `help-11.stdout.txt`, `help-11.stderr.txt` |
| AUTO-01l | `source .venv/bin/activate && dayu-cli process_material --help` | 0 | pass | `help-12.stdout.txt`, `help-12.stderr.txt` |
| AUTO-02 | `source .venv/bin/activate && dayu-cli --log-level debug --log-file workspace/tmp/wu-cli-smoke-01-auto/init.log init --base workspace/tmp/wu-cli-smoke-01-auto/fresh-workspace` | 0 | pass | `init-fresh-workspace.stdout.txt`, `init-fresh-workspace.stderr.txt`, `init.log` |
| AUTO-03a | filesystem scan after init | 0 | pass | `workspace-path-scan.stdout.txt`, `workspace-path-scan.stderr.txt` |
| AUTO-04 | `source .venv/bin/activate && python utils/smoke_host_public_awaiting_entrypoint.py --workspace-root workspace/tmp/wu-cli-smoke-01-auto/fresh-workspace --keep-workspace` | 0 | pass with diagnostic stderr | `awaiting-public-smoke.stdout.txt`, `awaiting-public-smoke.stderr.txt` |
| AUTO-05a | `source .venv/bin/activate && dayu-cli --log-level debug --log-file workspace/tmp/wu-cli-smoke-01-auto/fins-missing-source.log upload_filings_from --base <fresh> --ticker AAPL --from <missing>` | 2 | pass, expected usage failure | `fins-upload-filings-from-missing-source.stdout.txt`, `fins-upload-filings-from-missing-source.stderr.txt`, `fins-missing-source.log` |
| AUTO-05b | `source .venv/bin/activate && dayu-cli --log-level debug --log-file workspace/tmp/wu-cli-smoke-01-auto/fins-batch.log upload_filings_from --base <fresh> --ticker AAPL --from <fixtures> --output workspace/tmp/wu-cli-smoke-01-auto/fins-upload-batch.sh` | 0 | pass | `fins-upload-filings-from-script.stdout.txt`, `fins-upload-filings-from-script.stderr.txt`, `fins-batch.log`, `fins-upload-batch.sh` |
| AUTO-03b | post-smoke filesystem scan | 0 | pass | `workspace-path-scan-post-smoke.stdout.txt`, `workspace-path-scan-post-smoke.stderr.txt` |
| AUTO-06 | `source .venv/bin/activate && python workspace/tmp/wu-cli-smoke-01-auto/probe_interactive_ctrl_c.py` | 0 | fail behavior reproduced | `interactive-ctrl-c-pty.summary.txt`, `interactive-ctrl-c-pty.stdout.txt`, `interactive-ctrl-c.log` |
| TEST-01 | `source .venv/bin/activate && pytest tests/cli tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_fins_direct.py -q` | 0 | pass | command output in conversation; 234 passed, 3 warnings |
| FINAL-01 | `source .venv/bin/activate && git diff --check` | 0 | pass | no output |
| FINAL-02 | `source .venv/bin/activate && pyright` | 0 | pass | `0 errors, 0 warnings, 0 informations` |

## Evidence Details

### Help Surface

Top-level help lists `init`, `prompt`, `interactive`, Fins direct commands, and `session`. All tested help commands exited 0 with empty stderr.

### Fresh Workspace Init

`dayu-cli init` created `fresh-workspace/config` and current config assets. Stdout remained user-readable:

```text
dayu-cli init: initialized workspace config at .../fresh-workspace/config
```

The explicit debug log path exists. The log file is empty because this command path did not emit debug records.

### Workspace Path Regression

The post-smoke scan found no nested `workspace/workspace/.dayu` and no nested `workspace/workspace/portfolio`. Host artifacts were created directly under the fresh workspace, including `host.sqlite3`, `lane.sqlite3`, and `artifacts/`.

### Public Awaiting Smoke

The public awaiting smoke printed:

```text
SMOKE CONTRACT open_host -> ensure_session -> submit_entrypoint_turn_and_wait
SMOKE OBSERVED_WAITING true
SMOKE TERMINAL_STATUS SUCCEEDED
SMOKE OUTBOX_TERMINAL_MATCH true
SMOKE PASS Host public awaiting entrypoint
```

Stderr contained one dispatch diagnostic:

```text
dispatch.worker_events.clean_eof_without_terminal ...
```

Because the smoke exited 0 and produced the expected pass markers, this is not a blocking failure for AUTO-04, but the diagnostic is worth preserving as raw evidence.

### Fins Direct Boundary

Low-risk Fins validation avoided external download. `upload_filings_from` missing-source returned a user-facing usage diagnostic and exit 2. Local batch generation returned 0 and produced:

```text
dayu-cli upload_filing --ticker AAPL --action create --files .../aapl-2025-10k.pdf
```

The CLI path wrote Fins diagnostics to the explicit log files and did not require live SEC/network access.

### Interactive Ctrl+C

The PTY probe waited for the actual `dayu>` prompt and then sent one Ctrl+C. Summary:

```text
prompt_seen=True
sent_first_ctrl_c=true
exited_after_first_ctrl_c=True
decision=fail
reason=interactive input-state Ctrl+C exited process
```

This reproduces the user's high-priority behavior concern for the idle input state. Running-state cancellation remains limited-signal in this gate because a real model/provider run was intentionally not started.

## Manual Evidence Still Required

- Real `dayu-cli prompt` with the user's configured model/provider.
- Real `dayu-cli interactive` running-state cancellation during an accepted run.
- Optional real Fins download/process with credentials/network if available.
