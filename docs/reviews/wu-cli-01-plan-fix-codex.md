# WU-CLI-01 Plan Fix Report

## Gate

- Work unit: WU-CLI-01 CLI entrypoint integration aligned with dayu-agent CLI
- Gate: plan fix
- Plan artifact: `docs/host/wu-cli-01-cli-entrypoint-plan.md`
- Fix report artifact: `docs/reviews/wu-cli-01-plan-fix-codex.md`

## Scope

本 fix gate 只修改了 `docs/host/wu-cli-01-cli-entrypoint-plan.md`，未修改生产代码、测试、README、总控文档或既有 review artifacts。

## Accepted Findings Status

| Finding | Status |
| --- | --- |
| CancelRunRequest construction: context、client_request_id、reason、CancelMode 与幂等策略 | 已修复 |
| ReadOutboxTerminalItemsRequest cursor / projection handling | 已修复 |
| HostCallContext construction strategy and UI adapter / Service boundary split | 已修复 |
| compose submit follow-up override helper strategy | 已修复 |
| FinsDirectCommandService upload wrapper to FinsIngestionRuntime.start_upload | 已修复 |
| Interactive watcher lifecycle, per-turn isolation and fast terminal race tests | 已修复 |
| explicit `--config` behavior | 已修复 |
| `--ticker` context slot mapping for `prompt.json` / `interactive.json` | 已修复 |
| `init --reset` deletion whitelist | 已修复 |
| unsupported old debug / trace / duplicate flags behavior | 已修复 |
| Fins direct job poll interval | 已修复 |
| interactive failed / cancelled / lost terminal fatal vs non-fatal policy | 已修复 |

## Validation

- pytest: 未运行。本 gate 仅修 plan 文档，未进入 implementation。
- pyright: 未运行。本 gate 仅修 plan 文档，未修改生产代码或测试。

## Residual Risks / Blocking Open Questions

- Blocking open questions: none.
- Residual risks: no new unowned residual risk introduced by this plan fix gate.
