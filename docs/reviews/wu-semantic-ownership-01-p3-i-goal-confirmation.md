# WU-SEMANTIC-OWNERSHIP-01 P3-I goal confirmation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P3-I - Public CLI/package entrypoints and terminal display watermark`
- Gate: goal confirmation
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Controller source adjudication: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`

## First-principles judgment

The motivation is valid. P3-I is not a cosmetic cleanup:

- `pyproject.toml` declares public console scripts `dayu-web`, `dayu-wechat`, and `dayu-render`.
- `README.md` documents those commands as user-facing product commands.
- Current package inspection found no `dayu/web`, `dayu/wechat`, or `dayu/render` Python modules, so installed console scripts would fail during module import before reaching a useful help or runtime path.
- `dayu.cli.session_execution` currently advances the CLI terminal cursor only when terminal rendering returns `EXIT_SUCCESS`. A failed, cancelled, or lost terminal result can still be successfully rendered to the terminal, but the local display watermark is not advanced. That makes reconnect/startup backfill treat already displayed terminal items as unseen and can duplicate user-visible terminal output.

The owner boundary is coherent:

- Packaging entrypoints and public README own the set of public commands the package declares.
- The concrete command modules own importable command entrypoints and help/smoke behavior.
- CLI display delivery owns the local terminal cursor/watermark because it records what this CLI process has successfully displayed, not whether the Host Run succeeded.
- Host and Service remain the source of terminal status, terminal event id, terminal event sequence, and final answer/error/cancel/lost facts. P3-I must not rewrite those facts downstream.

## Goal

Close the accepted P3-I findings by making public package entrypoints truthful and making CLI terminal watermark advancement follow successful display delivery rather than successful Run outcome.

## Success signals

- Every console script declared in `pyproject.toml` resolves to an importable module and exposes a smoke-testable `main` function, or the command is removed consistently from `pyproject.toml` and user documentation. Given current README/product surface, the preferred plan direction is to restore minimal importable entrypoints rather than delete the commands.
- Prompt, interactive turn, and interactive startup reconnect advance `dayu.cli.session_terminal_cursor` after terminal output is rendered, including failed, cancelled, and lost Run statuses.
- CLI process exit code remains derived from rendered terminal status and is not conflated with the local watermark write.
- Tests cover public entrypoint import/help smoke and terminal cursor advancement for non-success terminal statuses.
- Pyright, affected tests, `git diff --check`, README-trigger decision, and propagation audit pass.

## Non-goals

- Do not build full Web, WeChat, or render product functionality beyond restoring the public entrypoint contract already declared by package metadata and README.
- Do not change Host terminal status semantics, Service terminal observation semantics, Outbox terminal projection, or EventLog cursor truth.
- Do not make terminal cursor a durable Host truth. It remains workspace-local CLI delivery state under `.dayu/cli`.
- Do not preserve compatibility shims for old entrypoint paths beyond the public console script targets that are current package metadata.

## Direct evidence

- `pyproject.toml` declares:
  - `dayu-web = "dayu.web.__main__:main"`
  - `dayu-wechat = "dayu.wechat.main:main"`
  - `dayu-render = "dayu.render.render:main"`
- Repository file listing found no files under `dayu/web`, `dayu/wechat`, or `dayu/render`.
- `README.md` includes user-facing instructions for `dayu-web --help`, `dayu-wechat --help`, `dayu-render --help`, and usage sections for these commands.
- `execute_prompt_on_session`, `_run_existing_session_startup_reconnect`, and `_run_interactive_repl` call `advance_cli_terminal_cursor(...)` only after checking `render_exit_code == EXIT_SUCCESS`.
- Existing tests already assert successful terminal cursor advancement, but do not prove failed/cancelled/lost terminals are watermarked after being displayed.

## Plan handoff constraints

- AgentCodex must produce a code-generation-ready plan in `docs/host/wu-semantic-ownership-01-p3-i-public-entrypoints-terminal-watermark-plan.md`.
- The plan must follow the control doc slice policy. This sub WU is small enough that the default expectation is one or two implementation slices; more than two slices requires explicit justification.
- The plan must explicitly choose restore-vs-remove for public entrypoints and justify the choice against `pyproject.toml`, README, existing dependencies, and minimal production surface.
- The plan must keep terminal status/exit-code facts separate from CLI display-delivery watermark facts.
- The plan must include affected tests, pyright, README decision, and propagation audit.

## Blocking questions

None. The user has instructed the controller to continue through sub WUs until all accepted findings are fixed.
