# WU-CLI-01 aggregate deepreview fix - Codex

## Gate

- gate: aggregate deepreview fix
- work unit: WU-CLI-01
- scope: 仅修复 controller accepted finding `AGG-RV-F01`
- artifact path: `docs/reviews/wu-cli-01-aggregate-deepreview-fix-codex.md`

## Goal confirmation

问题成立。`dayu/service/entrypoint_runtime.py` 的 `_close_watcher(...)` 原实现先 `await watcher.aclose()`，再
`drain_task.cancel()` / `await drain_task`。如果调用方 cancellation 或 watcher close 异常在第一个 await 点落地，
drain task 的取消与回收路径不会执行，影响 prompt / interactive 取消路径的资源确定性清理。

本轮只处理该 root cause，不处理 `AGG-RV-F02`、`AGG-RV-F03`、`AGG-RV-F04` 或 MiMo maintainability observations。

## Changed files

- `dayu/service/entrypoint_runtime.py`
  - 将 `_close_watcher(...)` 改为 `try/finally`：无论 `watcher.aclose()` 成功、普通异常还是
    `asyncio.CancelledError`，都会执行 `drain_task.cancel()` 并 await drain task 回收。
  - cleanup 只吞掉 drain task cancel 后产生的 `asyncio.CancelledError`，不吞掉 `watcher.aclose()` 的普通异常或取消。
- `tests/service/test_entrypoint_runtime.py`
  - 扩展 fake watcher，使测试可配置 `aclose()` 抛取消或普通异常。
  - 新增 `aclose()` 抛 `asyncio.CancelledError` 时 drain task 仍被 cancel / awaited 的回归测试。
  - 新增 `aclose()` 抛普通异常时 drain task 仍被 cancel / awaited，且原异常向上传播的回归测试。

## Behavior preserved

- 未改变 watcher attach-before-submit 语义。
- 未改变 outbox terminal fallback 语义。
- 未改变 cancel terminal observation 语义。
- 未新增 public contract、schema、状态机或跨层依赖。

## Validation

- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py -q`
  - result: passed, `20 passed`
- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`
  - result: passed, `56 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - result: passed, `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - result: passed

## Docs decision

- `dayu/service/README.md` checked: current entrypoint runtime description already covers watcher attach, terminal observation,
  outbox fallback and watcher failure diagnostics. This fix is internal cleanup hardening, so no README update is needed.
- `tests/README.md` checked: current `tests/service/` section already records entrypoint runtime watcher close / cancel coverage
  at the layer level. The new tests refine an existing behavior, so no README update is needed.

## Uncovered areas and residual risks

- `AGG-RV-F01`: fixed in current gate.
- `AGG-RV-F02`: deferred with owner by controller; not touched.
- `AGG-RV-F03`: deferred with owner by controller; not touched.
- `AGG-RV-F04`: rejected with reason by controller; not touched.
- MiMo maintainability observations: rejected with reason by controller; not touched.

No unclassified residual risk remains in this fix gate.

## Stop condition

Stop after AGG-RV-F01 fix, tests, pyright, `git diff --check`, and this artifact. Do not enter re-review, commit, push or PR.
