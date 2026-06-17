# WU-CLI-INTERACTIVE-RESUME-01 Final Closeout

- Work unit: `WU-CLI-INTERACTIVE-RESUME-01`
- Date: 2026-06-17
- Final status: **completed locally; ready-to-open-draft-PR**
- Public Host / Engine API changes: **none**

## Scope Closed

本 work unit 收敛了 `prompt` / `interactive` existing-session startup 语义：

- `prompt` 不做离线 terminal backfill，不等待或重放历史未完成 Run；它只提交并展示本次 prompt terminal，成功渲染后推进 CLI terminal cursor，避免后续 interactive 重复展示同一 terminal。
- `interactive --label` 与 `session resume --mode interactive` 在进入 REPL 前执行 startup attach / reconnect barrier。
- startup reconnect 使用 watcher-first：先 attach `watch_session_events(session_id)` 并启动 drain task，再读取 session-scoped Outbox terminal 增量。
- session-scoped Outbox backfill 不按 `run_id` 过滤；`CAUGHT_UP` 且无新 terminal 是正常 idle。
- idle snapshot 后执行 tail closure：再次 backfill Outbox 并 drain watcher queue，发现 terminal 或首次 watcher failure 时重新读取 Session snapshot。
- existing active Run 会先观察 terminal；queued-only Session 会 bounded wait promotion，耗尽后结构化失败，不静默进入输入态。
- CLI terminal cursor 是 workspace-local UI state，async facade 使用 `asyncio.to_thread()` 包裹同步 file lock / JSON / atomic replace。

## Artifacts

- Plan: `docs/reviews/wu-cli-interactive-resume-01-plan-codex-20260617.md`
- Plan reviews: `docs/reviews/plan-review-20260617-183641.md`; `docs/reviews/plan-review-20260617-183910.md`
- Plan adjudication: `docs/reviews/wu-cli-interactive-resume-01-plan-adjudication-20260617.md`
- Revised plan: `docs/reviews/wu-cli-interactive-resume-01-plan-fix-codex-20260617.md`
- Idle-tail fix: `docs/reviews/wu-cli-interactive-resume-01-idle-tail-fix-codex-20260617.md`
- Implementation reviews: `docs/reviews/wu-cli-interactive-resume-01-implementation-review-mimo-20260617.md`; `docs/reviews/wu-cli-interactive-resume-01-implementation-review-20260617.md`

## Validation

- `source .venv/bin/activate && pytest tests/service -q`
  - Result: 110 passed, 3 third-party edgar deprecation warnings.
- `source .venv/bin/activate && pytest tests/cli/test_session_terminal_cursor.py tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/cli/test_session_command.py -q`
  - Result: 74 passed, 3 third-party edgar deprecation warnings.
  - Note: this CLI subset is slow; final run completed in 360.44s.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: 0 errors, 0 warnings.

## Review Result

AgentMiMo and AgentDS both returned PASS. Non-blocking observations were reviewed:

- Removed redundant `Path(prepared.workspace_root)` wrapping in interactive startup cursor calls.
- Added a comment clarifying why session-scoped Outbox scan records terminal ids even when a live dedupe key already covered the item.
- Empty `dedupe_key` was not changed because `HostEvent` and `OutboxTerminalItem` public DTOs already validate non-empty dedupe keys.

## README / Control Doc

- Updated `dayu/service/README.md` for Service startup reconnect boundary.
- Updated `tests/README.md` for startup reconnect and CLI terminal cursor coverage.
- Updated `docs/host/issues-implementation-control.md` with WU status, validation, artifacts, and residual owners.
- `dayu/README.md`, Host README, Engine README, Fins README, and Config README were not updated because their documented boundaries did not change.

## Residuals

- `WU-CLI-INTERACTIVE-RESUME-01-R1`: deferred to future CLI client-state / multi-client isolation WU. Current cursor is workspace-local and shared by local CLI clients.
- `WU-CLI-INTERACTIVE-RESUME-01-R2`: deferred to future CLI UX / error-handling WU. Startup `EntrypointRuntimeError` still follows existing CLI runtime error propagation.
- Rendering success followed by cursor write crash may duplicate terminal on next startup. This is accepted: no terminal loss is preferred over falsely acknowledging delivery.
