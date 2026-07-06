# WU-CLI-SMOKE-01 Goal Confirmation

## Gate

- Work unit: `WU-CLI-SMOKE-01 dayu-cli Core Usability Smoke and Behavior Validation`
- Type: immediate residual work unit / smoke and behavior validation
- Gate: goal confirmation
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Date: 2026-07-06

## First-principles judgment

The work unit is valid. `dayu-cli` is the user-facing local entrypoint for core research workflows, and the control document records a post-WU-WAIT-04 need to prove the CLI main paths are usable through public contracts. This is not a request to add new Host or Engine behavior. It is a bounded validation and hardening slice for the CLI entrypoint surface after the Host wait, lifecycle, cancellation, and public awaiting smoke work landed.

The severity is moderate. Existing tests cover many command-level behaviors, but they are distributed across focused unit tests and service path tests. The current repository still lacks a single accepted validation matrix that proves fresh-workspace CLI usability, workspace path placement, help surface consistency, Fins direct command behavior, and Host public entrypoint smoke together.

## Direct evidence

- `dayu/cli/main.py` only parses arguments, opens CLI logging, and dispatches commands through registered runners. It does not directly open Host, construct Engine requests, or access Fins storage.
- `dayu/cli/commands/prompt.py` and `dayu/cli/commands/interactive.py` route runtime setup through `prepare_entrypoint_runtime(...)` and use Host public session / submit / watch / outbox APIs through Service helpers.
- `dayu/service/entrypoint_runtime.py` documents and implements the product entrypoint Service boundary. It resolves runtime locations, prepares scenes, discovers tools, composes `open_host(...)`, and submits turns without importing Engine internals.
- `dayu/runtime/location.py` currently resolves default config overlay as `project_root / "workspace" / "config"`. Because CLI `--base` is treated as `workspace_root` by command code, this path rule is directly relevant to the `workspace/workspace` regression risk called out in the control document.
- `dayu/cli/commands/fins.py` is a CLI UI adapter for Fins direct streams. It maps parsed arguments to `FinsDirectCommandService` and does not import `dayu.fins.storage`; existing tests already guard this import boundary.
- `tests/cli/test_init_command.py`, `tests/cli/test_prompt_command.py`, `tests/cli/test_interactive_command.py`, `tests/cli/test_fins_commands.py`, and `tests/service/test_entrypoint_runtime_interactive_path.py` provide focused coverage, but do not by themselves define the current WU-level acceptance matrix.
- PR 171 was merged on 2026-07-06 as merge commit `19a600e0`, satisfying the control document entry condition that WU-CLI-SMOKE-01 starts after WU-WAIT-04 is handled.

## Goal

Confirm and harden the `dayu-cli` core usability path with a minimal accepted validation matrix covering:

- `dayu-cli init`;
- CLI help surface for core commands;
- `prompt` and `interactive` Host public entrypoint paths;
- session label / resume behavior where already exposed by CLI;
- Fins direct upload / download / process command behavior at the CLI-Service boundary;
- workspace path regression checks for `.dayu`, runtime artifacts, config overlay, and Fins portfolio placement;
- continued public-contract awaiting smoke validation.

## Success signals

- Fresh workspace validation does not create nested `workspace/workspace/.dayu` or `workspace/workspace/portfolio` as the default runtime / Fins location.
- CLI behavior tests or smoke scripts cover the accepted matrix without importing Host internals, Engine internals, durable wait rows, scheduler internals, dispatch rows, or Fins storage from CLI code.
- Public awaiting smoke remains public-contract only.
- Real-environment CLI verification is required for this WU. Mock or fake runner tests can support regression coverage, but they cannot replace the real CLI smoke evidence.
- README and `tests/README.md` are updated only where their documented responsibilities require it.
- Affected tests, pyright, and `git diff --check` pass or have explicit non-blocking manual-smoke limitations recorded.

## Non-goals

- Do not implement or migrate `dayu-cli write`; GitHub Issue 151 remains the owner.
- Do not implement Web UI, GUI, or WeChat entrypoints; GitHub Issues 84, 85, and 147 remain separate owners.
- Do not implement Tool Trace analyzer, audit viewer, retention cleanup, long-term memory, or memory eval work.
- Do not change Host / Engine public contracts, durable schema, EventLog semantics, or wait lifecycle behavior unless a plan review finds direct evidence that a CLI smoke cannot be made truthful without such a design change.
- Do not use test-private Host or durable storage mutation paths to fake CLI success.

## Scope boundary

Allowed planning scope:

- `dayu/cli/**`;
- `dayu/service/entrypoint_runtime.py` and related Service assembly tests only if required by CLI entrypoint truth;
- CLI and Service tests under `tests/cli/**` and focused `tests/service/**`;
- smoke scripts under `utils/` when the validation is intentionally manual or external-provider dependent;
- README files triggered by actual behavior or validation documentation changes;
- `docs/host/issues-implementation-control.md` and WU artifacts under `docs/reviews/`.

Planning must justify any broader file touch. Production code changes are not assumed; the plan must first decide whether this is test/documentation hardening, a small runtime path fix, or both.

## Overdesign guardrail

This WU should not become a new CLI framework, a new smoke harness platform, or a generic product entrypoint certification system. The correct shape is the smallest validation and fix set that proves the current CLI core path is usable and aligned with documented public contracts.

## Blocking open questions

- None blocking after user confirmation on 2026-07-06.

## User confirmations

- No new GitHub Issue is required before plan gate. WU-CLI-SMOKE-01 remains a user-adjudicated immediate residual WU.
- Real-environment validation is the purpose of this WU. Phaseflow controller defines the validation matrix and adjudicates evidence, but concrete command execution is delegated to Agents. AgentCodex should run the automatable real CLI commands with debug logging where feasible, collect log output and UI output, and leave only the genuinely interactive / user-secret-dependent checks for manual validation.

## Validation matrix

| ID | Validation | Mode | Command / action | Expected evidence | Status |
|---|---|---|---|---|---|
| AUTO-01 | CLI top-level and core help surface | AgentCodex auto | `dayu-cli --help`, `dayu-cli init --help`, `dayu-cli prompt --help`, `dayu-cli interactive --help`, Fins direct command `--help` variants with debug log routing where supported | UI output lists documented commands/options; help exits successfully; debug log path is explicit when command executes through normal `main` logging | Pending AgentCodex run |
| AUTO-02 | Fresh workspace init | AgentCodex auto | `dayu-cli --log-level debug --log-file <artifact>/init.log init --base <fresh-workspace>` | Config and prompt assets are created under the chosen workspace root; no legacy config files; UI output remains user-readable; diagnostic log stays out of stdout/stderr | Pending AgentCodex run |
| AUTO-03 | Workspace path regression scan after CLI setup | AgentCodex auto | Filesystem inspection under the fresh workspace used by AUTO-02 and follow-up smoke commands | No `workspace/workspace/.dayu`; no `workspace/workspace/portfolio`; Host durable/runtime paths and Fins default paths stay under the intended workspace root | Pending AgentCodex run |
| AUTO-04 | Public awaiting smoke remains public-contract only | AgentCodex auto | `python utils/smoke_host_public_awaiting_entrypoint.py --workspace-root <fresh-workspace> --keep-workspace` | Smoke passes through `open_host -> ensure_session -> submit_entrypoint_turn_and_wait` style public contracts; no durable wait row mutation or test-private wait-id bridge is used | Pending AgentCodex run |
| AUTO-05 | Fins direct command CLI-Service boundary without external download | AgentCodex auto | Help and low-risk argument validation / upload batch script generation with debug logging, using local fixtures if available | CLI calls Fins direct Service boundary, keeps user UI and diagnostic logs separated, and does not import Fins storage from CLI | Pending AgentCodex run |
| MANUAL-01 | Real `dayu-cli prompt` against the user's configured model/provider | User manual, controller records evidence | User runs a provided command with `--log-level debug --log-file <path>` in a real configured workspace | Real model call reaches terminal answer or clear provider/config diagnostic; UI output and log output are available for controller review | Pending manual evidence |
| MANUAL-02 | Real `dayu-cli interactive` terminal loop | User manual, controller records evidence | User runs a provided interactive command with `--log-level debug --log-file <path>`, enters at least one prompt, exits cleanly | Interactive enters input loop, submits through Host public path, returns terminal output, and preserves stdout/stderr/log separation | Pending manual evidence |
| MANUAL-03 | Optional real Fins direct download/process path if credentials/network are available | User manual, controller records evidence | User runs documented `download` / `process` commands for a chosen ticker with debug log | Fins direct stream emits progress and terminal result; failures are actionable diagnostics rather than hangs or tracebacks | Pending manual evidence |

## Decision

Goal confirmation is accepted by the user on 2026-07-06 with the confirmations above. The controller should dispatch the plan gate to AgentCodex with the validation matrix and real-environment validation requirement preserved. AgentCodex owns automatable validation execution and the plan artifact; the controller owns evidence adjudication and gate state updates.
